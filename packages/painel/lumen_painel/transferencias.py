"""Transferências da União a estados, municípios e entidades, pelo arquivo mensal de dados abertos da CGU (ADR-054).

O Portal da Transparência publica um arquivo por mês, de janeiro de 2014 em diante
(``portaldatransparencia.gov.br/download-de-dados/transferencias/AAAAMM``, que redireciona para
``dadosabertos-download.cgu.gov.br/.../AAAAMM_Transferencias.zip``; de 1 a 6 MB compactados), sem chave. A página
de download lista os meses disponíveis. O CSV tem uma linha por favorecido, ação e mês:

- **o quê:** o tipo da transferência (constitucionais e royalties; legais, voluntárias e específicas), a função
  (saúde, educação, assistência social, encargos especiais…), o programa e a ação, com o nome que o portal usa
  para o cidadão (``LINGUAGEM CIDADÃ``: FPM, PDDE, merenda escolar, teto MAC…);
- **para quem:** o tipo e o nome do favorecido, a UF e o município (pelo nome; o código é o do SIAFI);
- **quanto:** o valor transferido no mês.

Por ente (código IBGE) e ano, somado:

- **governo:** o que foi para o próprio governo (a prefeitura e os fundos municipais, no município; o estado e os
  fundos estaduais, na UF), com o total por tipo, por função e por ação;
- **entidades:** o que foi para entidades sem fins lucrativos do município (as escolas pelo PDDE, associações),
  com o total por função.

Ficam de fora, só contados: empresas, organismos internacionais e agentes intermediários (a Petrobras recebe
bilhões que não são repasse a ente), e a linha sem lugar. O favorecido "Administração Pública" sem esfera
declarada (os fundos) é do estado quando o nome o diz ("ESTADUAL", "ESTADO DE", "SECRETARIA DE ESTADO"…), e do
município nos outros casos.

Coleta gentil: o servidor de arquivos da CGU responde com uma verificação humana (AWS WAF) a quem pede demais
(26/10/2026). Os três meses mais recentes, que a CGU ainda corrige, são baixados de novo a cada execução e ficam
somados à parte (``recentes``); os mais antigos são somados uma vez e fixados no ano (``anos``). Cada execução
baixa no máximo ``LIMITE_MESES`` meses, com pausa entre eles, e grava o estado depois de cada um: a primeira carga
(mais de 150 meses) se espalha por alguns dias, do mais recente para o mais antigo.
"""

from __future__ import annotations

import csv
import io
import re
import shutil
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

from lumen_normalizacao.transformacoes import chave_texto

from .cadastro import Cadastro
from .comum import gravar_json, grupo_do_ente, instante_utc, ler_json
from .emendas import APELIDOS, indice_de_lugares

PAGINA = "https://portaldatransparencia.gov.br/download-de-dados/transferencias"
FONTE = "Portal da Transparência (CGU), transferências de recursos, arquivo mensal de dados abertos"
ARQUIVO = "transferencias.json.gz"
VERSAO_ESTADO = 1
PRIMEIRO_ANO = 2014
RECENTES = 3            # meses mais recentes, baixados de novo a cada execução
LIMITE_MESES = 24       # downloads por execução, os recentes incluídos
PAUSA_S = 5.0           # entre um download e o seguinte
# Ações nomeadas por ente e ano no que vai para o site (as demais somam em "Outras ações"): o bastante para FPM,
# FUNDEB, SUS e educação, sem inchar o arquivo de quem recebe de dezenas de ações pequenas
ACOES_POR_ANO = 12
TIPOS = {"constitucionais e royalties": "constitucionais", "legais, voluntarias e especificas": "legais"}
_ESTADUAL = re.compile(r"\b(ESTADUAL|ESTADO D[EOA]S?|SECRETARIA DE ESTADO|GOVERNO D[OA] ESTADO|DISTRITO FEDERAL)\b")
_MUNICIPAL = re.compile(r"\b(MUNICIPAL|MUNICIPIO|PREFEITURA)\b")


class VerificacaoHumana(RuntimeError):
    """O servidor de arquivos da CGU pediu verificação humana (AWS WAF): a coleta para e tenta outro dia."""


def _cabecalhos(contato: str) -> dict[str, str]:
    """User-Agent com o contato do Lumen."""
    return {"User-Agent": f"Lumen (contato: {contato})"}


def meses_na_pagina(html: str) -> list[str]:
    """Os meses (``AAAAMM``) que a página de download lista, do mais antigo ao mais recente."""
    meses = {f"{a}{m}" for a, m in re.findall(r'"ano"\s*:\s*"(\d{4})"\s*,\s*"mes"\s*:\s*"(\d{2})"', html)}
    return sorted(m for m in meses if int(m[:4]) >= PRIMEIRO_ANO)


def meses_disponiveis(*, contato: str) -> list[str]:
    """Os meses publicados, lidos da página de download."""
    pedido = urllib.request.Request(PAGINA, headers=_cabecalhos(contato))
    with urllib.request.urlopen(pedido, timeout=120) as r:
        return meses_na_pagina(r.read().decode("utf-8", "replace"))


def baixar(mes: str, destino: Path, *, contato: str) -> Path:
    """Baixa o ZIP do mês para ``destino``; a página de verificação humana, no lugar do ZIP, vira erro."""
    pedido = urllib.request.Request(f"{PAGINA}/{mes}", headers=_cabecalhos(contato))
    try:
        with urllib.request.urlopen(pedido, timeout=600) as r:
            if "zip" not in (r.headers.get("Content-Type") or "") and "octet" not in (r.headers.get("Content-Type") or ""):
                raise VerificacaoHumana(f"{mes}: a CGU respondeu {r.headers.get('Content-Type')!r} no lugar do ZIP")
            with open(destino, "wb") as f:
                shutil.copyfileobj(r, f, 1 << 20)
    except urllib.error.HTTPError as erro:
        if erro.code in (403, 405, 429):
            raise VerificacaoHumana(f"{mes}: HTTP {erro.code} do servidor de arquivos da CGU") from erro
        raise
    return destino


def _valor(texto: str) -> float:
    """``4654210,67`` → 4654210.67; vazio vira zero."""
    try:
        return float(texto.replace(".", "").replace(",", ".")) if texto else 0.0
    except ValueError:
        return 0.0


def esfera(tipo_favorecido: str, nome: str) -> str | None:
    """De quem é a transferência: ``municipal``, ``estadual``, ``entidade`` ou None (fica de fora)."""
    tipo = chave_texto(tipo_favorecido)
    nome = (nome or "").upper()
    if tipo == "administracao publica municipal":
        return "municipal"
    if tipo == "administracao publica estadual ou do distrito federal":
        return "estadual"
    if tipo == "administracao publica":
        return "estadual" if _ESTADUAL.search(nome) else "municipal"
    if tipo == "sem informacao":
        return "municipal" if _MUNICIPAL.search(nome) else None
    if tipo == "entidades sem fins lucrativos":
        return "entidade"
    return None


def _acumular(destino: dict[str, float], chave: str, valor: float) -> None:
    """Acumula ``valor`` em ``destino[chave]``."""
    destino[chave] = destino.get(chave, 0.0) + valor


def soma_vazia() -> dict[str, Any]:
    """A soma de um período (mês ou ano): por ente, o do governo e o das entidades; e o que ficou de fora."""
    return {"governo": {}, "entidades": {}, "fora": {}}


def _linhas(arquivo: Path) -> Iterable[dict[str, str]]:
    """As linhas do CSV do mês (Latin-1, ``;``)."""
    with zipfile.ZipFile(arquivo) as z:
        nome = next(i.filename for i in z.infolist() if i.filename.lower().endswith(".csv"))
        with z.open(nome) as f:
            yield from csv.DictReader(io.TextIOWrapper(f, encoding="latin-1", newline=""), delimiter=";")


def somar_mes(arquivo: Path, lugares: dict[tuple[str, str], str]) -> dict[str, Any]:
    """A soma das linhas de um mês."""
    soma = soma_vazia()
    for d in _linhas(arquivo):
        valor = _valor(d.get("VALOR TRANSFERIDO") or "")
        if not valor:
            continue
        quem = esfera(d.get("TIPO FAVORECIDO") or "", d.get("NOME FAVORECIDO") or "")
        if quem is None:
            _acumular(soma["fora"], "outros_favorecidos", valor)
            continue
        uf = (d.get("UF") or "").upper()
        if quem == "estadual":
            ente = lugares.get((uf, ""))
        else:
            chave = (uf, chave_texto(d.get("NOME MUNICÍPIO")))
            chave = (uf, chave_texto(APELIDOS[chave])) if chave in APELIDOS else chave
            ente = lugares.get(chave)
        if ente is None:
            _acumular(soma["fora"], "sem_lugar", valor)
            continue
        area = (d.get("NOME FUNÇÃO") or "").strip() or "Sem informação"
        if quem == "entidade":
            e = soma["entidades"].setdefault(ente, {"total": 0.0, "por_area": {}})
            e["total"] += valor
            _acumular(e["por_area"], area, valor)
            continue
        g = soma["governo"].setdefault(ente, {"total": 0.0, "por_tipo": {}, "por_area": {}, "por_acao": {}})
        g["total"] += valor
        _acumular(g["por_tipo"], TIPOS.get(chave_texto(d.get("TIPO TRANSFERÊNCIA")), "outros"), valor)
        _acumular(g["por_area"], area, valor)
        acao = (d.get("LINGUAGEM CIDADÃ") or "").strip()
        if not acao or chave_texto(acao) == "sem informacao":
            acao = (d.get("NOME AÇÃO") or "").strip().capitalize() or "Sem informação"
        _acumular(g["por_acao"], acao, valor)
    return arredondar(soma)


def arredondar(valor: Any) -> Any:
    """Os números com centavos, em qualquer profundidade."""
    if isinstance(valor, dict):
        return {k: arredondar(v) for k, v in valor.items()}
    return round(valor, 2) if isinstance(valor, float) else valor


def juntar(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """A soma de duas somas (``a`` mais ``b``), campo a campo, sem mudar as duas."""
    saida = dict(a)
    for k, v in b.items():
        if isinstance(v, dict):
            saida[k] = juntar(saida.get(k) or {}, v)
        else:
            saida[k] = round((saida.get(k) or 0) + v, 2)
    return saida


@dataclass
class ResultadoTransferencias:
    """O que a coleta fez: os meses publicados, os baixados, os que faltam e se a CGU pediu verificação."""

    meses: int = 0
    baixados: list[str] = field(default_factory=list)
    faltam: int = 0
    verificacao: str | None = None

    def para_json(self) -> dict:
        """Resumo para imprimir na linha de comando."""
        return {"meses": self.meses, "baixados": self.baixados, "faltam": self.faltam,
                "verificacao_humana": self.verificacao}


def coletar(estado: Path | str, cadastro: Cadastro, *, contato: str, temporario: Path | None = None,
            anos: list[int] | None = None, limite: int = LIMITE_MESES, pausa: float = PAUSA_S,
            meses_fn=meses_disponiveis, baixar_fn=baixar, dormir: Callable[[float], None] = time.sleep,
            ) -> ResultadoTransferencias:
    """Baixa os meses recentes e os que faltam (até ``limite``) e grava ``ARQUIVO`` depois de cada um.

    Os ``RECENTES`` meses mais novos vão somados à parte e são refeitos a cada execução; o mês que sai dessa
    janela é fixado no ano dele. Os meses antigos que faltam vêm do mais novo para o mais antigo. Com a
    verificação humana da CGU, para e devolve o que conseguiu (``verificacao``). ``anos`` limita a coleta.
    """
    caminho = Path(estado) / ARQUIVO
    dados = ler_json(caminho) if caminho.exists() else {}
    if dados.get("versao") != VERSAO_ESTADO:
        dados = {}
    fixados: set[str] = set(dados.get("fixados") or [])
    por_ano: dict[str, Any] = dict(dados.get("anos") or {})
    recentes: dict[str, Any] = dict(dados.get("recentes") or {})
    meses = [m for m in meses_fn(contato=contato) if not anos or int(m[:4]) in anos]
    janela = meses[-RECENTES:]
    # O que saiu da janela desde a última execução vai para o ano, de vez
    for mes in sorted(set(recentes) - set(janela)):
        if mes not in fixados:
            por_ano[mes[:4]] = juntar(por_ano.get(mes[:4]) or soma_vazia(), recentes[mes])
            fixados.add(mes)
        del recentes[mes]
    antigos = [m for m in reversed(meses) if m not in janela and m not in fixados]
    fila = [*reversed(janela), *antigos][:limite]
    resultado = ResultadoTransferencias(meses=len(meses))

    def gravar() -> None:
        Path(estado).mkdir(parents=True, exist_ok=True)
        gravar_json(caminho, {"versao": VERSAO_ESTADO, "coletado_em": instante_utc(), "fonte": FONTE,
                              "fixados": sorted(fixados), "anos": dict(sorted(por_ano.items())),
                              "recentes": dict(sorted(recentes.items()))}, comprimir=True)

    lugares = indice_de_lugares(cadastro)
    pasta = Path(tempfile.mkdtemp(prefix="transferencias-", dir=temporario))
    try:
        for i, mes in enumerate(fila):
            if i:
                dormir(pausa)
            try:
                arquivo = baixar_fn(mes, pasta / f"{mes}_Transferencias.zip", contato=contato)
            except VerificacaoHumana as erro:
                resultado.verificacao = str(erro)
                break
            soma = somar_mes(arquivo, lugares)
            arquivo.unlink(missing_ok=True)
            if mes in janela:
                recentes[mes] = soma
            else:
                por_ano[mes[:4]] = juntar(por_ano.get(mes[:4]) or soma_vazia(), soma)
                fixados.add(mes)
            resultado.baixados.append(mes)
            gravar()
    finally:
        shutil.rmtree(pasta, ignore_errors=True)
    if not caminho.exists():
        gravar()
    resultado.faltam = len([m for m in meses if m not in janela and m not in fixados])
    return resultado


def _acoes_nomeadas(por_acao: dict[str, float]) -> dict[str, float]:
    """As ``ACOES_POR_ANO`` maiores ações, do maior valor ao menor, e o resto em "Outras ações"."""
    ordem = sorted(por_acao.items(), key=lambda kv: -kv[1])
    saida = dict(ordem[:ACOES_POR_ANO])
    resto = round(sum(v for _, v in ordem[ACOES_POR_ANO:]), 2)
    if resto:
        saida["Outras ações"] = resto
    return saida


def _ordenar(d: dict[str, float]) -> dict[str, float]:
    """Do maior valor ao menor."""
    return dict(sorted(d.items(), key=lambda kv: -kv[1]))


def publicar(estado: Path | str, gravar: Callable[[str, Any], Any], *, gerado_em: str) -> dict | None:
    """Grava ``transferencias/ente/<grupo>.json.gz`` (comprimido, ``comum.grupo_do_ente``): por ente do grupo e
    por ano, o que foi para o governo e para as entidades (os meses fixados e os recentes, somados)."""
    caminho = Path(estado) / ARQUIVO
    if not caminho.exists():
        return None
    dados = ler_json(caminho)
    if dados.get("versao") != VERSAO_ESTADO:
        raise ValueError(f"{caminho}: versão {dados.get('versao')!r} do estado das transferências não suportada")
    anos = dict(dados.get("anos") or {})
    for mes, soma in (dados.get("recentes") or {}).items():
        anos[mes[:4]] = juntar(anos.get(mes[:4]) or soma_vazia(), soma)
    por_ente: dict[str, dict[str, dict]] = {}
    for ano, a in anos.items():
        for ente, g in a.get("governo", {}).items():
            por_ente.setdefault(ente, {}).setdefault(ano, {})["governo"] = {
                "total": g["total"], "por_tipo": _ordenar(g["por_tipo"]), "por_area": _ordenar(g["por_area"]),
                "por_acao": _acoes_nomeadas(g["por_acao"])}
        for ente, e in a.get("entidades", {}).items():
            por_ente.setdefault(ente, {}).setdefault(ano, {})["entidades"] = {
                "total": e["total"], "por_area": _ordenar(e["por_area"])}
    grupos: dict[str, dict[str, dict]] = {}
    for ente, por_ano in sorted(por_ente.items()):
        grupos.setdefault(grupo_do_ente(ente), {})[ente] = dict(sorted(por_ano.items()))
    meses = sorted({*(dados.get("fixados") or []), *(dados.get("recentes") or {})})
    for grupo, entes in sorted(grupos.items()):
        gravar(f"transferencias/ente/{grupo}.json.gz", {
            "versao": 1, "tipo": "transferencias-entes", "gerado_em": gerado_em, "fonte": dados.get("fonte"),
            "meses": meses, "entes": entes,
        })
    return {"entes": len(por_ente), "arquivos": len(grupos), "meses": len(meses),
            "ultimo_mes": meses[-1] if meses else None,
            "fora": {ano: a.get("fora") for ano, a in sorted(anos.items())}}
