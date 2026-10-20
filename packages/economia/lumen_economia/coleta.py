"""Coleta das séries do SGS para o estado da área Economia (``economia-sgs.json.gz``).

Uma requisição por série, com a série inteira (as séries do catálogo são mensais ou anuais; o SGS limita a
dez anos por consulta só as diárias). O estado guarda os valores como a fonte os publicou (texto, com o
ponto decimal), a URL e a hora da coleta de cada série. Uma série que falha na coleta mantém o que o estado
já tinha e registra a falha: o portal mostra o dado anterior com a data em que foi coletado, sem fingir que
é de hoje.

O firewall do Banco Central às vezes recusa requisições de servidores em nuvem, com uma página HTML de
"Requisição inválida" no lugar do JSON (``SgsRecusou``). Quando isso acontece, a coleta tenta de novo depois
de uma pausa e, se a série tem espelho conferido no Ipeadata (``catalogo.Serie.espelho``), coleta de lá e
registra no estado que usou o espelho e por quê.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

from lumen_ingestao.cliente_http import ClienteHttp
from lumen_ingestao.coleta_http import ErroColeta
from lumen_painel.comum import gravar_json, ler_json

from .catalogo import SERIES, Serie, url_ipeadata, url_releases_ibge, url_sgs

ARQUIVO_ESTADO = "economia-sgs.json.gz"
VERSAO_ESTADO = 1
FONTE_ID = "bcb_sgs"
FONTE_ESPELHO = "ipeadata"
FONTE_RELEASES = "ibge_noticias"
ESPERA_ANTES_DE_REPETIR_S = 60
_DATA = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")


class SerieIlegivel(ErroColeta):
    """O SGS respondeu, mas não com a lista de observações (página de erro, JSON inesperado)."""


class SgsRecusou(SerieIlegivel):
    """O firewall do Banco Central recusou a requisição: não é mudança de formato, é bloqueio de acesso."""


def recusa_do_bc(conteudo: bytes) -> str | None:
    """O código de erro da página de recusa do firewall do Banco Central, ou ``None`` se não é essa página."""
    texto = conteudo[:20_000].decode("utf-8", errors="replace")
    if "<html" not in texto[:600].lower() or "rejeitada" not in texto:
        return None
    m = re.search(r"digo de erro \S*:?\s*(\d+)", texto)
    return m.group(1) if m else "sem código"


def ler_resposta(conteudo: bytes) -> list[tuple[str, str]]:
    """Observações da resposta do SGS como (``AAAA-MM-DD``, valor em texto), em ordem de data.

    O SGS publica ``[{"data": "01/01/2025", "valor": "0.16"}]``. Valor vazio é ausência e fica fora (não vira
    zero). Resposta que não é essa lista levanta ``SerieIlegivel``.
    """
    codigo = recusa_do_bc(conteudo)
    if codigo:
        raise SgsRecusou(f"o firewall do Banco Central recusou a requisição (código {codigo})")
    try:
        dados = json.loads(conteudo.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as erro:
        raise SerieIlegivel(f"resposta não é JSON: {conteudo[:80]!r}") from erro
    if not isinstance(dados, list):
        raise SerieIlegivel(f"resposta não é uma lista: {str(dados)[:80]}")
    saida = []
    for item in dados:
        m = _DATA.match(str(item.get("data", "")).strip()) if isinstance(item, dict) else None
        valor = str(item.get("valor", "")).strip() if isinstance(item, dict) else ""
        if not m:
            raise SerieIlegivel(f"observação sem data no formato DD/MM/AAAA: {str(item)[:80]}")
        if not valor:
            continue
        float(valor)  # confere que é número; ValueError sobe como erro de coleta logo abaixo
        saida.append((f"{m.group(3)}-{m.group(2)}-{m.group(1)}", valor))
    return sorted(saida)


def ler_ipeadata(conteudo: bytes, casas: int | None = None) -> list[tuple[str, str]]:
    """Observações da resposta do Ipeadata como (``AAAA-MM-DD``, valor em texto), em ordem de data.

    O Ipeadata publica ``{"value": [{"VALDATA": "2024-01-01T00:00:00-03:00", "VALVALOR": 0.42}]}``. Valor nulo
    é ausência. Com ``casas``, o valor é arredondado como o SGS publica (o PIB real tem duas casas no SGS).
    """
    try:
        dados = json.loads(conteudo.decode("utf-8"))
        valores = dados["value"]
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as erro:
        raise SerieIlegivel(f"resposta do Ipeadata ilegível: {conteudo[:80]!r}") from erro
    saida = []
    for item in valores:
        data, valor = str(item.get("VALDATA", ""))[:10], item.get("VALVALOR")
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", data):
            raise SerieIlegivel(f"observação do Ipeadata sem data: {str(item)[:80]}")
        if valor is None:
            continue
        saida.append((data, str(round(float(valor), casas) if casas is not None else float(valor))))
    return sorted(saida)


@dataclass
class ResumoColetaEconomia:
    """O que a coleta fez: séries atualizadas, as que vieram do espelho e as que falharam, com o motivo."""

    atualizadas: dict[str, int] = field(default_factory=dict)   # id → observações
    pelo_espelho: dict[str, str] = field(default_factory=dict)  # id → por que o SGS não serviu
    falhas: dict[str, str] = field(default_factory=dict)        # id → motivo

    def para_json(self) -> dict:
        """Resumo para imprimir na linha de comando."""
        return {"atualizadas": self.atualizadas, "pelo_espelho": self.pelo_espelho, "falhas": self.falhas}


def ler_estado(estado: Path | str) -> dict:
    """O estado gravado, ou um estado vazio na versão atual."""
    caminho = Path(estado) / ARQUIVO_ESTADO
    if not caminho.exists() or caminho.stat().st_size == 0:
        return {"versao": VERSAO_ESTADO, "series": {}}
    dados = ler_json(caminho)
    if dados.get("versao") != VERSAO_ESTADO:
        raise ValueError(f"{caminho}: versão {dados.get('versao')!r} do estado da economia não suportada")
    return dados


def _obter(cliente: ClienteHttp, url: str, ler: Callable[[bytes], list[tuple[str, str]]]) -> list[tuple[str, str]]:
    """Baixa e lê uma série; levanta ``ErroColeta`` (ou ``ValueError``) se não veio a lista de observações."""
    artefato = cliente.obter(url, {"Accept": "application/json"})
    if artefato.status_http != 200:
        raise SerieIlegivel(f"{url} respondeu {artefato.status_http}")
    observacoes = ler(artefato.conteudo)
    if not observacoes:
        raise SerieIlegivel("série sem nenhuma observação")
    return observacoes


def coletar(cliente: ClienteHttp, estado: Path | str, series: Iterable[Serie] = SERIES, *,
            agora: datetime | None = None, espelho: ClienteHttp | None = None,
            espera_s: float = ESPERA_ANTES_DE_REPETIR_S,
            dormir: Callable[[float], None] = time.sleep) -> ResumoColetaEconomia:
    """Baixa cada série do SGS e grava o estado; a série que falha mantém o que já havia.

    As séries que o firewall do BC recusou são pedidas de novo uma vez, depois de ``espera_s``. As que
    continuam falhando e têm espelho são coletadas do Ipeadata (com o cliente ``espelho``, ou o mesmo).
    """
    dados = ler_estado(estado)
    resumo = ResumoColetaEconomia()
    instante = (agora or datetime.now(timezone.utc)).isoformat(timespec="seconds")
    series = tuple(series)
    motivos: dict[str, str] = {}

    def gravar(s: Serie, observacoes: list[tuple[str, str]], **extra) -> None:
        dados["series"][str(s.codigo)] = {"url": url_sgs(s.codigo), "coletado_em": instante,
                                           "observacoes": observacoes, **extra}
        resumo.atualizadas[s.id] = len(observacoes)

    def pelo_sgs(s: Serie) -> bool:
        try:
            gravar(s, _obter(cliente, url_sgs(s.codigo), ler_resposta))
        except (ErroColeta, ValueError) as erro:
            motivos[s.id] = f"{type(erro).__name__}: {erro}"
            return False
        motivos.pop(s.id, None)
        return True

    falharam = [s for s in series if not pelo_sgs(s)]
    recusadas = [s for s in falharam if motivos[s.id].startswith(SgsRecusou.__name__)]
    if recusadas:
        dormir(espera_s)
        falharam = [s for s in falharam if s not in recusadas or not pelo_sgs(s)]
    for s in falharam:
        if s.espelho:
            url = url_ipeadata(s.espelho)
            try:
                gravar(s, _obter(espelho or cliente, url, lambda c, casas=s.espelho_casas: ler_ipeadata(c, casas)),
                       fonte_coleta=FONTE_ESPELHO, url_coleta=url, falha_sgs=motivos[s.id])
                resumo.pelo_espelho[s.id] = motivos[s.id]
                continue
            except (ErroColeta, ValueError) as erro:
                motivos[s.id] += f"; espelho do Ipeadata: {type(erro).__name__}: {erro}"
        resumo.falhas[s.id] = motivos[s.id]
        anterior = dados["series"].get(str(s.codigo), {})
        dados["series"][str(s.codigo)] = {**anterior, "url": url_sgs(s.codigo), "ultima_falha": instante,
                                           "motivo_da_falha": motivos[s.id]}
    Path(estado).mkdir(parents=True, exist_ok=True)
    gravar_json(Path(estado) / ARQUIVO_ESTADO, dados, comprimir=True)
    return resumo


# ------------------------------------------------------------------------------------------- releases

def ler_releases(conteudo: bytes) -> list[dict]:
    """Os releases da resposta da API de notícias do IBGE: título, data (ISO), link e a introdução.

    A API publica ``data_publicacao`` como ``09/10/2026 09:00:00`` e o link em ``http``; o link vai em ``https``,
    que a Agência de Notícias também serve. Item sem título, data ou link fica de fora.
    """
    try:
        dados = json.loads(conteudo)
    except (UnicodeDecodeError, json.JSONDecodeError) as erro:
        raise SerieIlegivel(f"resposta não é JSON: {conteudo[:80]!r}") from erro
    itens = dados.get("items") if isinstance(dados, dict) else None
    if not isinstance(itens, list):
        raise SerieIlegivel("resposta sem a lista items")
    saida = []
    for item in itens:
        titulo, link = (item.get("titulo") or "").strip(), (item.get("link") or "").strip()
        m = _DATA.match((item.get("data_publicacao") or "").split(" ")[0])
        if not (titulo and link and m):
            continue
        dia, mes, ano = m.groups()
        saida.append({"titulo": titulo, "data": f"{ano}-{mes}-{dia}",
                      "link": "https://" + link.removeprefix("http://").removeprefix("https://"),
                      "introducao": (item.get("introducao") or "").strip()})
    return saida


def coletar_releases(cliente: ClienteHttp, estado: Path | str, series: Iterable[Serie] = SERIES, *,
                     agora: datetime | None = None) -> dict:
    """Guarda no estado os releases mais recentes do IBGE de cada produto das ``series`` (``ibge_produto``).

    O produto que falha mantém os releases que já havia; a falha vai no resumo e não derruba a coleta das séries.
    """
    dados = ler_estado(estado)
    instante = (agora or datetime.now(timezone.utc)).isoformat(timespec="seconds")
    produtos = sorted({s.ibge_produto for s in series if s.ibge_produto})
    guardados = dados.setdefault("releases", {})
    falhas: dict[str, str] = {}
    for produto in produtos:
        url = url_releases_ibge(produto)
        try:
            artefato = cliente.obter(url, {"Accept": "application/json"})
            if artefato.status_http != 200:
                raise SerieIlegivel(f"{url} respondeu {artefato.status_http}")
            guardados[str(produto)] = {"url": url, "coletado_em": instante, "itens": ler_releases(artefato.conteudo)}
        except (ErroColeta, ValueError) as erro:
            falhas[str(produto)] = f"{type(erro).__name__}: {erro}"
    Path(estado).mkdir(parents=True, exist_ok=True)
    gravar_json(Path(estado) / ARQUIVO_ESTADO, dados, comprimir=True)
    return {"produtos": len(produtos) - len(falhas), "falhas": falhas}
