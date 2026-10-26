"""Conferência seção a seção: a votação de cada seção, somada, contra o total divulgado (ADR-053).

O TSE publica o resultado de duas formas independentes. O sistema de
resultados divulga o total (o que a aba Eleições mostra), por Brasil, UF e
município. Os dados abertos trazem, em ``votacao_secao_<ano>_BR.zip``, a
votação de Presidente em cada seção eleitoral: um registro por seção e
número votado, o boletim de urna em forma de tabela. Somar as seções e
comparar com o total divulgado mostra se as duas publicações contam a mesma
eleição, voto a voto, no Brasil e em cada UF (o exterior incluído).

Números votados: os candidatos, 95 (branco) e 96 (nulo). Um número que está
na urna mas não na lista de candidatos do resultado é de candidatura com os
votos anulados, e o sistema de resultados o conta como nulo técnico (em 2026,
o 28: 5.246 votos no 1º turno).

O arquivo traz os turnos que o TSE já publicou (o 2º entra no mesmo arquivo
depois); cada turno vira ``<eleição>/presidente/conferencia.json``.
"""

from __future__ import annotations

import csv
import io
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Mapping

from lumen_ingestao.bronze import ArmazemBronze

from . import VERSAO_ESQUEMA_FEED, carga
from . import dados_abertos as da
from .configuracao import ConfiguracaoEleicoes
from .feeds import EscritorFeeds, _gravar_json, cargo_json, origem_json, resumo_eleicao
from .modelo import Eleicao, ResultadoAbrangencia
from .municipios import nome_da_uf
from .transferencia import Manifesto, baixar_arquivo

CONJUNTO_SECAO = "votacao_secao"
# Anos com a votação por seção de Presidente conferida pela carga: o em aberto (os outros já foram conferidos
# pelo TSE e pela imprensa; entram quando alguém quiser, pela linha de comando)
ANOS_SECAO = (2026,)
BRANCO = "95"
NULO = "96"
CARGO_PRESIDENTE = 1
# Sobe quando o que a conferência grava muda para a mesma entrada; ano registrado com revisão menor é refeito
REVISAO_CONFERENCIA = 1


def url_secao(ano: int) -> str:
    """URL do ZIP da votação por seção de Presidente (o arquivo do Brasil) de um ano."""
    return f"{da.CDN}/{CONJUNTO_SECAO}/{CONJUNTO_SECAO}_{ano}_BR.zip"


def baixar_secoes(cfg: ConfiguracaoEleicoes, ano: int, *, bronze: ArmazemBronze | None = None,
                  atualizar: bool = False, saida: Callable[[str], None] | None = None) -> tuple[Path, Manifesto]:
    """Baixa o ZIP da votação por seção do ano para ``<arquivos>/secoes/`` (retomável, com manifesto) e
    registra o manifesto no bronze."""
    url = url_secao(ano)
    destino = cfg.arquivos / "secoes" / url.rsplit("/", 1)[-1]
    escrever = saida or (lambda msg: print(msg, flush=True))
    escrever(f"{ano}  {CONJUNTO_SECAO}  {url}")
    manifesto = baixar_arquivo(url, destino, user_agent=cfg.user_agent, atualizar=atualizar,
                               progresso=carga.progresso_mb(saida=escrever))
    carga.registrar_manifesto(bronze, manifesto)
    return destino, manifesto


# ---------------------------------------------------------------- soma

@dataclass
class SomaTurno:
    """Votos de Presidente num turno, somados das seções: no Brasil e por UF, com os nomes dos números."""

    turno: int
    eleicao_tse: int
    brasil: Counter = field(default_factory=Counter)
    por_uf: dict[str, Counter] = field(default_factory=lambda: defaultdict(Counter))
    nomes: dict[str, str] = field(default_factory=dict)
    secoes: set[tuple[str, str, str, str]] = field(default_factory=set)
    secoes_por_uf: Counter = field(default_factory=Counter)


def somar_secoes(fluxo: io.BufferedIOBase | Iterable[bytes]) -> dict[int, SomaTurno]:
    """Soma o CSV da votação por seção (``;``, Latin-1, aspas), turno a turno, só o cargo de Presidente."""
    texto = io.TextIOWrapper(fluxo, encoding="latin-1", newline="")  # type: ignore[arg-type]
    leitor = csv.reader(texto, delimiter=";")
    cab = next(leitor)
    ix = {c: i for i, c in enumerate(cab)}
    turnos: dict[int, SomaTurno] = {}
    for linha in leitor:
        if int(linha[ix["CD_CARGO"]]) != CARGO_PRESIDENTE:
            continue
        turno = int(linha[ix["NR_TURNO"]])
        soma = turnos.get(turno)
        if soma is None:
            soma = turnos[turno] = SomaTurno(turno, int(linha[ix["CD_ELEICAO"]]))
        uf = linha[ix["SG_UF"]].strip().lower()
        numero = linha[ix["NR_VOTAVEL"]].strip()
        votos = int(linha[ix["QT_VOTOS"]])
        soma.brasil[numero] += votos
        soma.por_uf[uf][numero] += votos
        soma.nomes.setdefault(numero, linha[ix["NM_VOTAVEL"]].strip())
        secao = (uf, linha[ix["CD_MUNICIPIO"]], linha[ix["NR_ZONA"]], linha[ix["NR_SECAO"]])
        if secao not in soma.secoes:
            soma.secoes.add(secao)
            soma.secoes_por_uf[uf] += 1
    return turnos


def somar_zip(caminho: Path | str) -> dict[int, SomaTurno]:
    """Soma o CSV do ZIP da votação por seção (um só, o do Brasil)."""
    with zipfile.ZipFile(caminho) as zf:
        nomes = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if not nomes:
            raise ValueError(f"{caminho}: ZIP sem CSV")
        with zf.open(nomes[0]) as fluxo:
            return somar_secoes(fluxo)


# ---------------------------------------------------------------- conferência

def _linha(rotulo: str, numero: str | None, secoes: int, divulgado: int | None, detalhe: str | None = None) -> dict:
    """Uma linha da conferência: a soma das seções, o divulgado e a diferença (None quando não há divulgado)."""
    return {"rotulo": rotulo, "numero": numero, "detalhe": detalhe, "secoes": secoes, "divulgado": divulgado,
            "diferenca": None if divulgado is None else secoes - divulgado}


def linhas_da_conferencia(votos: Mapping[str, int], r: ResultadoAbrangencia, nomes: Mapping[str, str]) -> list[dict]:
    """As linhas de uma abrangência: cada candidato do resultado, brancos, nulos e, se houver, os nulos técnicos.

    Os nulos do resultado são o total (comuns e técnicos); a conferência compara os comuns (o 96) e, à parte,
    os técnicos: os números votados que não estão na lista de candidatos do resultado.
    """
    candidatos = {c.numero for c in r.candidatos}
    linhas = [_linha(c.nome_urna, c.numero, votos.get(c.numero, 0), c.votos) for c in r.candidatos]
    linhas.append(_linha("Brancos", BRANCO, votos.get(BRANCO, 0), r.votos.brancos))
    tecnicos = r.votos.nulos_tecnicos or 0
    nulos = None if r.votos.nulos is None else r.votos.nulos - tecnicos
    linhas.append(_linha("Nulos", NULO, votos.get(NULO, 0), nulos))
    fora = sorted(((n, v) for n, v in votos.items() if n not in candidatos and n not in (BRANCO, NULO) and v),
                  key=lambda kv: -kv[1])
    if fora or tecnicos:
        detalhe = ", ".join(f"{n} ({nomes.get(n, '')}): {v:,}".replace(",", ".") for n, v in fora) or None
        linhas.append(_linha("Nulos técnicos", None, sum(v for _, v in fora), r.votos.nulos_tecnicos, detalhe))
    return linhas


def _confere(linhas: list[dict]) -> bool:
    """Se todas as linhas com divulgado batem."""
    return all(linha["diferenca"] in (0, None) for linha in linhas)


def feed_conferencia(*, eleicao: Eleicao, soma: SomaTurno, divulgado: Mapping[str, ResultadoAbrangencia],
                     manifesto: Manifesto | None, urls_divulgado: Mapping[str, str],
                     conferido_em: datetime | None = None) -> dict:
    """O feed ``conferencia``: o Brasil e cada UF (com o exterior), a soma das seções contra o divulgado.

    ``divulgado`` tem o resultado do sistema de resultados por abrangência ("br" e as siglas); a UF que
    falta nele aparece sem conferência (``divulgado`` vazio), em vez de sumir.
    """
    cargo = eleicao.cargo(CARGO_PRESIDENTE)
    br = divulgado.get("br")
    brasil = linhas_da_conferencia(soma.brasil, br, soma.nomes) if br else []
    ufs = []
    for uf in sorted(soma.por_uf):
        r = divulgado.get(uf)
        linhas = linhas_da_conferencia(soma.por_uf[uf], r, soma.nomes) if r else []
        ufs.append({"uf": uf, "nome": nome_da_uf(uf) or uf.upper(), "secoes": soma.secoes_por_uf[uf],
                    "secoes_divulgadas": r.totalizacao.secoes if r else None,
                    "conferida": bool(r), "confere": bool(r) and _confere(linhas), "linhas": linhas})
    instante = (conferido_em or datetime.now(timezone.utc)).isoformat(timespec="seconds")
    return {
        "versao": VERSAO_ESQUEMA_FEED,
        "tipo": "conferencia",
        "eleicao": resumo_eleicao(eleicao),
        "cargo": cargo_json(cargo),
        "conferido_em": instante,
        "origem_secoes": origem_json("dados_abertos", url=manifesto.url if manifesto else None,
                                     sha256=manifesto.sha256 if manifesto else None,
                                     coletado_em=manifesto.baixado_em if manifesto else None),
        "origem_divulgado": origem_json("resultados", url=urls_divulgado.get("br")),
        "secoes": {"no_arquivo": len(soma.secoes), "divulgadas": br.totalizacao.secoes if br else None},
        "brasil": {"conferida": bool(br), "confere": bool(br) and _confere(brasil), "linhas": brasil},
        "ufs": ufs,
        "confere": bool(br) and _confere(brasil) and all(u["confere"] for u in ufs),
    }


def gravar_conferencia(escritor: EscritorFeeds, eleicao: Eleicao, feed: dict) -> Path:
    """Grava ``<eleição>/presidente/conferencia.json``."""
    return _gravar_json(escritor.caminho(eleicao.id, eleicao.cargo(CARGO_PRESIDENTE).slug, "conferencia"), feed)
