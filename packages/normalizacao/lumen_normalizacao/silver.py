"""Camada silver: registros canônicos gravados em JSON Lines particionado.

Por que JSON Lines e não Parquet nesta fase (ADR-016)
----------------------------------------------------
O DOC-04 prevê Parquet consultado por DuckDB. A Fase 1 grava JSON Lines no
mesmo particionamento Hive (``entidade/exercicio=AAAA/uf=XX/``), por três
motivos: não exige dependência nova (ADR-015), o DuckDB lê JSON Lines
particionado diretamente com ``read_json_auto(..., hive_partitioning=true)``,
e a conversão para Parquet vira um passo de compactação que não muda nenhum
contrato. Quando o volume justificar, a compactação entra sem tocar nos
normalizadores.

Idempotência
------------
Cada artefato do bronze vira exatamente um arquivo por partição, com nome
derivado do ``documento_fonte_id``. Reprocessar o mesmo artefato reescreve o
mesmo arquivo com o mesmo conteúdo, em ordem estável, por troca atômica. Não
existe "acrescentar no fim": acrescentar duplicaria o registro a cada
reprocessamento.

Duplicidade entre artefatos
---------------------------
O mesmo contrato aparece em mais de um artefato: na coleta por publicação e
na coleta por atualização, ou em duas coletas do mesmo dia. A silver guarda
todas as ocorrências, cada uma com sua proveniência (RF-NO-05); a visão
consolidada escolhe a mais recente por ``atualizado_em`` e, no empate, pela
coleta mais recente (ver ``sql/silver_consolidada.sql``).
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Iterable

from lumen_canonico.fato import RegistroCanonico

from .qualidade import EntradaQuarentena

_SEGURO = re.compile(r"^[A-Za-z0-9_\-]{1,128}$")


def _particao(registro: RegistroCanonico) -> tuple[str, str]:
    """Partição Hive do registro: exercício e UF, com ``NA`` quando não há como determinar.

    O exercício vem de ``ano`` e, na falta dele, do ano da primeira data disponível entre publicação,
    assinatura, início de vigência e resultado.
    """
    dados = registro.para_dict()
    exercicio = dados.get("ano")
    if exercicio is None:
        for campo in ("data_publicacao", "data_assinatura", "vigencia_inicio", "data_resultado"):
            valor = dados.get(campo)
            if valor:
                exercicio = str(valor)[:4]
                break
    uf = dados.get("uf") or "NA"
    return (str(exercicio) if exercicio else "NA", str(uf).upper())


def _seguro(nome: str) -> str:
    """Devolve o nome se ele servir como nome de arquivo seguro; senão levanta ``ValueError``.

    Os nomes vêm dos ids da fonte e do artefato; recusar barras, pontos e afins impede que um id leve a
    gravação para fora do diretório da silver.
    """
    if not _SEGURO.match(nome):
        raise ValueError(f"nome de arquivo inseguro: {nome!r}")
    return nome


def _gravar_atomico(destino: Path, linhas: list[str]) -> None:
    """Grava as linhas num temporário do mesmo diretório e o troca pelo destino com ``os.replace``.

    Nenhum leitor vê arquivo pela metade, e uma falha no meio deixa o arquivo anterior intacto e remove o
    temporário.
    """
    destino.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=destino.parent, prefix=".tmp-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            for linha in linhas:
                fh.write(linha)
                fh.write("\n")
        os.replace(tmp, destino)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


class EscritorSilver:
    """Grava na silver os registros e a quarentena de cada artefato do bronze.

    Cada linha leva a versão do normalizador que a produziu, para que se saiba de qual código saiu cada
    dado depois de um reprocessamento.
    """

    def __init__(self, raiz: Path | str, versao_normalizador: str):
        """Raiz da silver e versão do normalizador que vai em cada linha gravada."""
        self.raiz = Path(raiz)
        self.versao = versao_normalizador

    def gravar(self, documento_fonte_id: str, registros: Iterable[RegistroCanonico],
               coletado_em: str | None = None) -> list[Path]:
        """Grava os registros de um artefato. Devolve os arquivos escritos.

        ``coletado_em`` é o instante da coleta do artefato no bronze. Ele vai
        em cada linha como ``_coletado_em`` e desempata a consolidação.
        """
        nome = _seguro(documento_fonte_id) + ".jsonl"
        grupos: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
        for r in registros:
            exercicio, uf = _particao(r)
            dados = r.para_dict()
            dados["_versao_normalizador"] = self.versao
            dados["_coletado_em"] = coletado_em
            grupos[(r.ENTIDADE, exercicio, uf)].append(dados)
        escritos = []
        for (entidade, exercicio, uf), lista in sorted(grupos.items()):
            # Ordem estável: o mesmo artefato produz byte a byte o mesmo arquivo.
            lista.sort(key=lambda d: (str(d.get("chave_origem")), str(d.get("id"))))
            vistos: set[str] = set()
            linhas = []
            for d in lista:
                # Dentro de um artefato, o mesmo órgão aparece em cada
                # contratação da página; basta uma linha por id.
                if d["id"] in vistos:
                    continue
                vistos.add(d["id"])
                linhas.append(json.dumps(d, ensure_ascii=False, sort_keys=True))
            destino = self.raiz / entidade / f"exercicio={exercicio}" / f"uf={uf}" / nome
            _gravar_atomico(destino, linhas)
            escritos.append(destino)
        return escritos

    def gravar_quarentena(self, fonte_id: str, documento_fonte_id: str,
                          entradas: Iterable[EntradaQuarentena]) -> Path | None:
        """Grava a quarentena de um artefato em ``_quarentena/<fonte>/<artefato>.jsonl`` e devolve o caminho.

        Sem entradas, apaga o arquivo anterior e devolve None: a quarentena reflete o normalizador atual, e o
        histórico fica no bronze.
        """
        entradas = list(entradas)
        destino = self.raiz / "_quarentena" / _seguro(fonte_id) / (_seguro(documento_fonte_id) + ".jsonl")
        if not entradas:
            # Reprocessamento que já não gera quarentena apaga a anterior:
            # a quarentena descreve o estado atual do normalizador, não o
            # histórico (o histórico está no bronze, que é imutável).
            destino.unlink(missing_ok=True)
            return None
        linhas = [json.dumps(e.para_dict(), ensure_ascii=False, sort_keys=True) for e in entradas]
        _gravar_atomico(destino, linhas)
        return destino


def ler_entidade(raiz: Path | str, entidade: str) -> list[dict]:
    """Todas as linhas de uma entidade, de todas as partições. Para testes e
    volumes pequenos; em volume real, use DuckDB sobre o mesmo diretório."""
    linhas = []
    for arquivo in sorted(Path(raiz, entidade).glob("exercicio=*/uf=*/*.jsonl")):
        with open(arquivo, encoding="utf-8") as fh:
            linhas.extend(json.loads(linha) for linha in fh if linha.strip())
    return linhas


def consolidar(linhas: Iterable[dict]) -> list[dict]:
    """Uma linha por ``id``: a de ``atualizado_em`` mais recente.

    Mesma lógica de ``sql/silver_consolidada.sql``, em Python, para testes e
    para quem não tem DuckDB instalado. Empate em ``atualizado_em`` (ou ambos
    nulos) é decidido pela coleta mais recente (``_coletado_em``).
    """
    def ordem(linha: dict) -> tuple[str, str]:
        return (str(linha.get("atualizado_em") or ""), str(linha.get("_coletado_em") or ""))

    melhor: dict[str, dict] = {}
    for linha in linhas:
        atual = melhor.get(linha["id"])
        if atual is None or ordem(linha) >= ordem(atual):
            melhor[linha["id"]] = linha
    return [melhor[k] for k in sorted(melhor)]
