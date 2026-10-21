"""Convênios da União com estados, municípios e entidades, pelo arquivo de dados abertos da CGU (ADR-045).

O Portal da Transparência publica a lista inteira dos convênios todo dia
(``portaldatransparencia.gov.br/download-de-dados/convenios/AAAAMMDD``, que redireciona para
``dadosabertos-download.cgu.gov.br/.../AAAAMMDD_Convenios.zip``; 67 MB em outubro de 2026), sem chave. A página
de download declara a data do arquivo mais recente, como nas sanções (ADR-030). O CSV principal,
``AAAAMMDD_Convenios.csv``, tem um convênio por linha, de 1990 em diante:

- **onde e com quem:** UF e município (pelo nome; o código é o do SIAFI, não o do IBGE), o tipo do convenente
  (administração municipal, estadual, entidade sem fins lucrativos, empresa, pessoa física) e o CNPJ e o nome;
- **o quê:** objeto, órgão superior e órgão concedente;
- **quanto e quando:** valor do convênio, valor liberado, contrapartida, início e fim da vigência e a última
  liberação;
- **situação:** como o SIAFI a registra (em execução, concluído, prestação de contas em análise ou aprovada,
  inadimplente, inadimplência suspensa, arquivado…).

No estado (``convenios.json.gz``) entram os convênios com início de vigência de 2001 em diante, por ente:

- **governo municipal, entidade, empresa e o resto** no município da linha; **governo estadual** na UF;
- **pessoa física** só na soma por ano, sem nome nem documento (ADR-043);
- o convênio **excluído** ou **anulado** fica de fora (não chegou a valer) e só entra na contagem.

O município pelo nome usa o mesmo cruzamento das emendas (``emendas.indice_de_lugares`` e ``emendas.APELIDOS``).
"""

from __future__ import annotations

import csv
import io
import re
import shutil
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from lumen_canonico.documentos import mascarar_cpfs_no_texto
from lumen_ingestao.adaptadores.api.cgu import data_do_arquivo as data_na_pagina
from lumen_normalizacao.transformacoes import chave_texto

from .cadastro import Cadastro
from .comum import gravar_json, grupo_do_ente, instante_utc, ler_json
from .emendas import APELIDOS, indice_de_lugares

PAGINA = "https://portaldatransparencia.gov.br/download-de-dados/convenios"
FONTE = "Portal da Transparência (CGU), convênios, arquivo de dados abertos"
ARQUIVO = "convenios.json.gz"
VERSAO_ESTADO = 1
PRIMEIRO_ANO = 2001
LIMITE_OBJETO = 200
COLUNAS = ["numero", "situacao", "objeto", "orgao", "categoria", "cnpj", "convenente", "valor", "liberado",
           "contrapartida", "inicio", "fim", "ultima_liberacao"]
CATEGORIAS = {"governo_municipal": "Governo municipal", "governo_estadual": "Governo estadual",
              "entidade": "Entidade sem fins lucrativos", "empresa": "Empresa", "pessoa_fisica": "Pessoa física",
              "outro": "Outro"}
_TIPOS = {"administracao publica municipal": "governo_municipal",
          "administracao publica estadual ou do distrito federal": "governo_estadual",
          "entidades sem fins lucrativos": "entidade", "entidades empresariais privadas": "empresa",
          "pessoa fisica": "pessoa_fisica"}
FORA = {"excluido", "convenio anulado"}


def _cabecalhos(contato: str) -> dict[str, str]:
    """User-Agent com o contato do Lumen."""
    return {"User-Agent": f"Lumen (contato: {contato})"}


def data_do_arquivo(*, contato: str) -> str:
    """A data (``AAAAMMDD``) do arquivo mais recente, declarada na página de download."""
    pedido = urllib.request.Request(PAGINA, headers=_cabecalhos(contato))
    with urllib.request.urlopen(pedido, timeout=120) as r:
        html = r.read().decode("utf-8", "replace")
    return data_na_pagina(html, "Convenios").strftime("%Y%m%d")


def baixar(data: str, destino: Path, *, contato: str) -> Path:
    """Baixa o ZIP do dia ``data`` para ``destino``."""
    pedido = urllib.request.Request(f"{PAGINA}/{data}", headers=_cabecalhos(contato))
    with urllib.request.urlopen(pedido, timeout=600) as r, open(destino, "wb") as f:
        shutil.copyfileobj(r, f, 1 << 20)
    return destino


def _valor(texto: str) -> float:
    """``2110457,00`` → 2110457.0; vazio vira zero."""
    try:
        return float(texto.replace(".", "").replace(",", ".")) if texto else 0.0
    except ValueError:
        return 0.0


def _data(texto: str) -> str | None:
    """``28/02/1996`` → ``1996-02-28``."""
    m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", (texto or "").strip())
    return f"{m[3]}-{m[2]}-{m[1]}" if m else None


def ler(arquivo: Path, cadastro: Cadastro) -> dict:
    """Os convênios por ente (código IBGE), as somas sem identificação e as contagens do que ficou de fora."""
    lugares = indice_de_lugares(cadastro)
    por_ente: dict[str, list] = {}
    pessoa_fisica: dict[str, dict[str, float]] = {}
    fora = {"anulados_ou_excluidos": 0, "antes_de_2001": 0, "sem_lugar": 0}
    with zipfile.ZipFile(arquivo) as z:
        nome = next(i.filename for i in z.infolist() if i.filename.endswith("_Convenios.csv"))
        with z.open(nome) as f:
            for d in csv.DictReader(io.TextIOWrapper(f, encoding="latin-1", newline=""), delimiter=";"):
                situacao = (d.get("SITUAÇÃO CONVÊNIO") or "").strip()
                if chave_texto(situacao) in FORA:
                    fora["anulados_ou_excluidos"] += 1
                    continue
                inicio = _data(d.get("DATA INÍCIO VIGÊNCIA") or "")
                if not inicio or int(inicio[:4]) < PRIMEIRO_ANO:
                    fora["antes_de_2001"] += 1
                    continue
                categoria = _TIPOS.get(chave_texto(d.get("TIPO CONVENENTE")), "outro")
                uf = (d.get("UF") or "").upper()
                chave = (uf, "") if categoria == "governo_estadual" else (uf, chave_texto(d.get("NOME MUNICÍPIO")))
                chave = (uf, chave_texto(APELIDOS[chave])) if chave in APELIDOS else chave
                ente = lugares.get(chave)
                if ente is None:
                    fora["sem_lugar"] += 1
                    continue
                valor, liberado = _valor(d.get("VALOR CONVÊNIO") or ""), _valor(d.get("VALOR LIBERADO") or "")
                if categoria == "pessoa_fisica":
                    soma = pessoa_fisica.setdefault(ente, {})
                    soma[inicio[:4]] = round(soma.get(inicio[:4], 0.0) + liberado, 2)
                    continue
                documento = re.sub(r"\D", "", d.get("CÓDIGO CONVENENTE") or "")
                objeto = " ".join((d.get("OBJETO DO CONVÊNIO") or "").split())
                objeto = mascarar_cpfs_no_texto(objeto, todos=False) or ""
                if len(objeto) > LIMITE_OBJETO:
                    objeto = objeto[: LIMITE_OBJETO - 1].rstrip() + "…"
                por_ente.setdefault(ente, []).append([
                    (d.get("NÚMERO CONVÊNIO") or "").strip(), situacao, objeto, (d.get("NOME ÓRGÃO SUPERIOR") or "").strip(),
                    categoria, documento if len(documento) == 14 else None,
                    mascarar_cpfs_no_texto((d.get("NOME CONVENENTE") or "").strip()), round(valor, 2), round(liberado, 2),
                    round(_valor(d.get("VALOR CONTRAPARTIDA") or ""), 2), inicio, _data(d.get("DATA FINAL VIGÊNCIA") or ""),
                    _data(d.get("DATA ÚLTIMA LIBERAÇÃO") or ""),
                ])
    return {"convenios": {e: sorted(ls, key=lambda x: (x[10], x[0])) for e, ls in sorted(por_ente.items())},
            "pessoa_fisica": dict(sorted(pessoa_fisica.items())), "fora": fora}


@dataclass
class ResultadoConvenios:
    """O que a coleta fez: a data do arquivo, se baixou, quantos entes e convênios."""

    data_arquivo: str | None = None
    baixado: bool = False
    entes: int = 0
    convenios: int = 0

    def para_json(self) -> dict:
        """Resumo para imprimir na linha de comando."""
        return {"data_arquivo": self.data_arquivo, "baixado": self.baixado, "entes": self.entes,
                "convenios": self.convenios}


def coletar(estado: Path | str, cadastro: Cadastro, *, contato: str, temporario: Path | None = None,
            data_fn=data_do_arquivo, baixar_fn=baixar) -> ResultadoConvenios:
    """Baixa e lê o arquivo do dia mais recente quando a data mudou; grava ``ARQUIVO``."""
    caminho = Path(estado) / ARQUIVO
    anterior = ler_json(caminho) if caminho.exists() else {}
    data = data_fn(contato=contato)
    resultado = ResultadoConvenios(data_arquivo=data)
    if anterior.get("data_arquivo") == data:
        conv = anterior.get("convenios") or {}
        resultado.entes, resultado.convenios = len(conv), sum(len(v) for v in conv.values())
        return resultado
    pasta = Path(tempfile.mkdtemp(prefix="convenios-", dir=temporario))
    try:
        dados = ler(baixar_fn(data, pasta / f"{data}_Convenios.zip", contato=contato), cadastro)
    finally:
        shutil.rmtree(pasta, ignore_errors=True)
    resultado.baixado = True
    resultado.entes = len(dados["convenios"])
    resultado.convenios = sum(len(v) for v in dados["convenios"].values())
    Path(estado).mkdir(parents=True, exist_ok=True)
    gravar_json(caminho, {"versao": VERSAO_ESTADO, "data_arquivo": data, "coletado_em": instante_utc(),
                          "fonte": FONTE, "colunas": COLUNAS, **dados}, comprimir=True)
    return resultado


def publicar(estado: Path | str, gravar: Callable[[str, Any], Any], *, gerado_em: str) -> dict | None:
    """Grava ``convenios/ente/<grupo>.json.gz`` (comprimido, ``comum.grupo_do_ente``): por ente do grupo, os
    convênios e a soma de pessoa física."""
    caminho = Path(estado) / ARQUIVO
    if not caminho.exists():
        return None
    dados = ler_json(caminho)
    if dados.get("versao") != VERSAO_ESTADO:
        raise ValueError(f"{caminho}: versão {dados.get('versao')!r} do estado dos convênios não suportada")
    convenios = dados.get("convenios") or {}
    pf = dados.get("pessoa_fisica") or {}
    grupos: dict[str, dict[str, dict]] = {}
    for ente in sorted(set(convenios) | set(pf)):
        grupos.setdefault(grupo_do_ente(ente), {})[ente] = {"convenios": convenios.get(ente, []),
                                                            "pessoa_fisica": pf.get(ente, {})}
    for grupo, entes in sorted(grupos.items()):
        gravar(f"convenios/ente/{grupo}.json.gz", {
            "versao": 1, "tipo": "convenios-entes", "gerado_em": gerado_em, "data_arquivo": dados.get("data_arquivo"),
            "fonte": dados.get("fonte"), "categorias": CATEGORIAS, "colunas": dados.get("colunas"), "entes": entes,
        })
    return {"data_arquivo": dados.get("data_arquivo"), "entes": len(set(convenios) | set(pf)), "arquivos": len(grupos),
            "convenios": sum(len(v) for v in convenios.values()), "fora": dados.get("fora")}
