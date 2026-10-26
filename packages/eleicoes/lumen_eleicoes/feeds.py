"""Contrato dos feeds JSON que o portal lê (ADR-019).

O portal é estático e não fala com o TSE. Tudo o que ele mostra sai destes
arquivos, gravados num diretório servido como arquivo comum (no
desenvolvimento, ``packages/portal/public/dados/eleicoes``)::

    indice.json                              eleições disponíveis e seus cargos
    municipios.json                          cadastro TSE ↔ IBGE (busca)
    geo/br-uf.json, geo/uf-<sigla>-mu.json   malhas do IBGE (TopoJSON)
    geo/zonas-<ano>/…                        locais de votação por zona, para o mapa das zonas (``zonas.py``)
    <eleição>/<cargo>/br.json                resultado no Brasil, com as UFs em ``partes``
    <eleição>/<cargo>/uf-<sigla>.json        resultado na UF, com os municípios em ``partes``
    <eleição>/<cargo>/mu-<chave>.json        resultado no município, com as zonas eleitorais em ``partes``
                                             quando ele tem mais de uma (só nos dados abertos)
    <eleição>/<cargo>/historico-<abr>.json   evolução da totalização
    fotos/...                                fotos dos candidatos (sistema de resultados)

Regras do contrato:

- ``versao`` em todo arquivo. Mudança incompatível sobe a versão e o portal
  recusa o que não conhece, em vez de exibir número errado.
- Números são números (inteiros para votos, decimais para percentuais com
  até 6 casas), nunca texto com vírgula. Datas em ISO 8601 com fuso.
- Cargo municipal (prefeito, vereador) não tem resultado único na UF nem no
  Brasil: nesses níveis o arquivo é um **panorama** (``tipo: panorama``),
  com o líder de cada município e a contagem por partido.
- Cores: o feed não traz cor, traz ``cor`` = índice de 0 a ``N_CORES - 1``
  (ou -1, cinza). PL (azul) e PT (vermelho) têm índice fixo (ADR-052); os
  demais seguem a ordem de votação no nível mais alto do cargo, e o índice é
  o mesmo em todos os níveis (o candidato tem a mesma cor no mapa do Brasil
  e no da UF). A paleta é do portal (ADR-020).
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping

from . import VERSAO_ESQUEMA_FEED
from .modelo import CARGOS, Candidato, Cargo, Eleicao, Nivel, ResultadoAbrangencia, TipoCargo, slug_do_cargo
from .municipios import Municipio, codigo_ibge_da_uf, nome_da_uf

N_CORES = 8
SEM_COR = -1
# Partidos de cor fixa (ADR-052): índice na paleta do portal (0 = azul, 1 = vermelho).
CORES_DOS_PARTIDOS = {"PL": 0, "PT": 1}
_SEGURO = re.compile(r"^[a-z0-9][a-z0-9-]{0,80}$")


def _seguro(parte: str) -> str:
    """Valida um trecho do caminho de um feed: só minúsculas, dígitos e hífen, sem começar por hífen.

    Os trechos vêm de dados externos (ids, slugs, códigos) e viram nome de arquivo; isso impede
    barras e ``..`` de saírem do diretório dos feeds.
    """
    if not _SEGURO.match(parte):
        raise ValueError(f"nome de arquivo de feed inválido: {parte!r}")
    return parte


def _iso(valor: datetime | date | None) -> str | None:
    """Data ou instante em ISO 8601; ``None`` passa direto."""
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.isoformat()
    return valor.isoformat()


def _r(valor: float | None, casas: int = 6) -> float | None:
    """Arredonda para ``casas`` decimais, preservando ``None``."""
    return None if valor is None else round(float(valor), casas)


# ---------------------------------------------------------------- abrangência

@dataclass(frozen=True)
class Abrangencia:
    """Recorte geográfico de um feed: Brasil, UF ou município, com os códigos IBGE e TSE quando há."""

    tipo: str                    # br, uf, mu; zn (zona eleitoral) só como parte do feed do município
    codigo: str                  # "br", sigla da UF em minúsculas, chave do município
    nome: str
    uf: str | None = None
    ibge: str | None = None
    tse: str | None = None

    @property
    def arquivo(self) -> str:
        """Nome do feed sem extensão: ``br``, ``uf-<sigla>`` ou ``mu-<chave>``, validado por ``_seguro``."""
        if self.tipo == "br":
            return "br"
        return _seguro(f"{self.tipo}-{self.codigo}")

    def para_json(self) -> dict:
        """Bloco ``abrangencia`` do feed."""
        return {"tipo": self.tipo, "codigo": self.codigo, "nome": self.nome, "uf": self.uf,
                "ibge": self.ibge, "tse": self.tse}


def abrangencia_brasil() -> Abrangencia:
    """A abrangência nacional."""
    return Abrangencia("br", "br", "Brasil")


def abrangencia_uf(sigla: str) -> Abrangencia:
    """Abrangência da UF pela sigla, com o nome e o código IBGE."""
    s = sigla.lower()
    return Abrangencia("uf", s, nome_da_uf(s), uf=s, ibge=codigo_ibge_da_uf(s))


def abrangencia_municipio(m: Municipio) -> Abrangencia:
    """Abrangência de um município do cadastro; o código é a ``chave`` dele (o IBGE, quando há)."""
    return Abrangencia("mu", m.chave, m.nome, uf=m.uf, ibge=m.ibge, tse=m.tse)


def abrangencia_zona(uf: str, zona: str) -> Abrangencia:
    """Zona eleitoral de um município, pelo número (sem zeros à esquerda). Não tem feed próprio: aparece
    como parte do feed do município, com o número da zona como código."""
    numero = str(int(zona))
    return Abrangencia("zn", numero, f"Zona {numero}", uf=uf.lower())


# ---------------------------------------------------------------- cores

def atribuir_cores(chaves_em_ordem: Iterable[str], anteriores: Mapping[str, int] | None = None,
                   n: int = N_CORES, partidos: Mapping[str, str | None] | None = None) -> dict[str, int]:
    """Índice de cor por candidato (ou partido), estável entre atualizações.

    A chave é o número do candidato (``partidos`` diz o partido de cada um) ou
    a sigla do partido. PL e PT têm cor fixa (``CORES_DOS_PARTIDOS``, ADR-052)
    em qualquer cargo, nível e eleição, e ninguém mais as recebe. Os demais
    seguem a ordem de votação: quem já tem cor a mantém — no meio da apuração,
    a troca de posição entre dois candidatos não troca a cor deles no mapa —,
    e quem chega pega o menor índice livre. Do ``n``-ésimo em diante, cinza.
    """
    partidos = partidos or {}
    reservadas = set(CORES_DOS_PARTIDOS.values())

    def fixa(chave: str) -> int | None:
        return CORES_DOS_PARTIDOS.get(partidos.get(chave) or chave)

    cores = {k: v for k, v in (anteriores or {}).items()
             if 0 <= v < n and (fixa(k) == v or (fixa(k) is None and v not in reservadas))}
    livres = [i for i in range(n) if i not in reservadas and i not in cores.values()]
    for chave in chaves_em_ordem:
        if (f := fixa(chave)) is not None:
            cores[chave] = f
        elif chave not in cores:
            cores[chave] = livres.pop(0) if livres else SEM_COR
    return cores


def cores_dos_candidatos(r: ResultadoAbrangencia, anteriores: Mapping[str, int] | None = None) -> dict[str, int]:
    """Cores dos candidatos válidos de um resultado, na ordem dele, com a cor fixa do partido quando houver."""
    return atribuir_cores((c.numero for c in r.candidatos if c.valido), anteriores,
                          partidos={c.numero: c.partido for c in r.candidatos})


def ranking_partidos(r: ResultadoAbrangencia) -> list[tuple[str, int]]:
    """Partidos em ordem de votação: a total publicada pela fonte, ou a nominal somada.

    O recorte de candidatos de um arquivo pode não ter todos os candidatos
    (município com limite); a votação do partido publicada pelo TSE tem.
    """
    if r.votos_partido:
        soma = dict(r.votos_partido)
    else:
        soma = {}
        for c in r.candidatos:
            if c.valido and c.partido:
                soma[c.partido] = soma.get(c.partido, 0) + c.votos
    return sorted(((p, v) for p, v in soma.items() if v > 0), key=lambda kv: (-kv[1], kv[0]))


# ---------------------------------------------------------------- blocos

def resumo_eleicao(e: Eleicao) -> dict:
    """Bloco ``eleicao`` dos feeds e do índice: id, nome, ano, turno, tipo e data."""
    return {"id": e.id, "nome": e.nome, "ano": e.ano, "turno": e.turno, "tipo": e.tipo, "data": _iso(e.data)}


def cargo_json(c: Cargo, vagas: int | None = None) -> dict:
    """Bloco ``cargo`` do feed; ``vagas``, quando informado, substitui o número de vagas do cargo."""
    return {"slug": c.slug, "codigo": c.codigo, "nome": c.nome, "tipo": c.tipo.value,
            "nivel": c.nivel.value, "vagas": vagas if vagas is not None else c.vagas}


def _totalizacao(r: ResultadoAbrangencia) -> dict:
    """Bloco ``totalizacao``: seções, percentual totalizado, finalizada e matematicamente definida."""
    t = r.totalizacao
    return {"secoes": t.secoes, "secoes_totalizadas": t.secoes_totalizadas, "pct_secoes": _r(t.pct_secoes, 4),
            "finalizada": t.finalizada, "matematicamente_definida": t.matematicamente_definida}


def _comparecimento(r: ResultadoAbrangencia) -> dict:
    """Bloco ``comparecimento``: eleitorado, comparecimento, abstenção e os percentuais."""
    c = r.comparecimento
    return {"eleitorado": c.eleitorado, "comparecimento": c.comparecimento, "abstencao": c.abstencao,
            "pct_comparecimento": _r(c.pct_comparecimento), "pct_abstencao": _r(c.pct_abstencao)}


def _votos(r: ResultadoAbrangencia) -> dict:
    """Bloco ``votos``: válidos, brancos, nulos, anulados, de legenda e os percentuais."""
    v = r.votos
    return {"validos": v.validos, "brancos": v.brancos, "nulos": v.nulos, "anulados": v.anulados,
            "legenda": v.legenda, "pct_validos": _r(v.pct_validos), "pct_brancos": _r(v.pct_brancos),
            "pct_nulos": _r(v.pct_nulos)}


def _pct(c: Candidato, r: ResultadoAbrangencia) -> float | None:
    """Percentual do candidato nos válidos: o publicado ou, se faltar, calculado sobre os válidos do recorte."""
    if c.pct_validos is not None:
        return _r(c.pct_validos)
    if c.valido and r.votos.validos:
        return _r(100.0 * c.votos / r.votos.validos)
    return None


def candidato_json(c: Candidato, r: ResultadoAbrangencia, cores: Mapping[str, int],
                   foto: str | None = None) -> dict:
    """Um candidato no feed, com o índice de cor e a foto.

    Nos cargos proporcionais as cores são por partido: sem cor pelo número, vale a da sigla.
    """
    return {
        "numero": c.numero, "nome_urna": c.nome_urna, "nome": c.nome, "partido": c.partido,
        "agremiacao": c.agremiacao, "composicao": c.composicao, "votos": c.votos, "pct": _pct(c, r),
        "situacao": c.situacao, "eleito": c.eleito, "segundo_turno": c.segundo_turno,
        "valido": c.valido, "destinacao": c.destinacao, "vice": c.vice,
        # Proporcional: a cor é a do partido (as chaves de partido são siglas,
        # as de candidato são números, e não colidem).
        "cor": cores.get(c.numero, cores.get(c.partido or "", SEM_COR)), "foto": foto,
        # Só aparece quando falso: eleições antigas, sem número de urna; o portal esconde o número.
        **({} if c.numero_publicado else {"sem_numero": True}),
    }


def parte_json(abr: Abrangencia, r: ResultadoAbrangencia, cores: Mapping[str, int], *,
               por_partido: bool = False) -> dict:
    """Resumo de uma abrangência filha, para colorir o mapa do nível de cima."""
    base = {"codigo": abr.codigo, "nome": abr.nome, "ibge": abr.ibge,
            "pct_secoes": _r(r.totalizacao.pct_secoes, 4), "finalizada": r.totalizacao.finalizada,
            "eleitorado": r.comparecimento.eleitorado}
    if por_partido:
        ranking = ranking_partidos(r)
        bancada: dict[str, int] = {}
        for c in r.candidatos:
            if c.eleito and c.partido:
                bancada[c.partido] = bancada.get(c.partido, 0) + 1
        if not ranking:
            return {**base, "lider": None, "cor": SEM_COR, "bancada": bancada}
        partido, votos = ranking[0]
        total = r.votos.validos or sum(v for _, v in ranking)
        segundo = ranking[1][1] if len(ranking) > 1 else 0
        return {**base, "lider": partido, "partido": partido, "nome_urna": None, "votos": votos,
                "pct": _r(100.0 * votos / total) if total else None,
                "margem": _r(100.0 * (votos - segundo) / total) if total else None,
                "cor": cores.get(partido, SEM_COR), "eleito": False, "segundo_turno": False,
                "bancada": bancada}
    lider, segundo = r.lider, r.segundo
    if lider is None or lider.votos == 0:
        return {**base, "lider": None, "cor": SEM_COR}
    pl, ps = _pct(lider, r), (_pct(segundo, r) if segundo else None)
    return {**base, "lider": lider.numero, "partido": lider.partido, "nome_urna": lider.nome_urna,
            "votos": lider.votos, "pct": pl, "margem": _r(pl - ps) if pl is not None and ps is not None else None,
            "cor": cores.get(lider.numero, SEM_COR), "eleito": lider.eleito,
            "segundo_turno": lider.segundo_turno}


def parte_zona_json(abr: Abrangencia, r: ResultadoAbrangencia, cores: Mapping[str, int], *,
                    por_partido: bool = False) -> dict:
    """Uma zona no feed do município: como ``parte_json``, sem a bancada nem os selos de eleito e de 2º turno.

    Quem se elege (ou vai ao 2º turno) é decidido no município, na UF ou no Brasil; na zona, esses campos
    dariam a impressão de que cada zona elegeu alguém.
    """
    parte = parte_json(abr, r, cores, por_partido=por_partido)
    for campo in ("bancada", "eleito", "segundo_turno"):
        parte.pop(campo, None)
    return parte


def origem_json(fonte: str, url: str | None = None, sha256: str | None = None,
                coletado_em: datetime | str | None = None, registro_bronze: str | None = None) -> dict:
    """Bloco ``origem`` do feed: fonte, URL, SHA-256, instante da coleta e registro no bronze.

    É o que liga cada número exibido à resposta guardada como prova.
    """
    return {"fonte": fonte, "url": url, "sha256": sha256,
            "coletado_em": coletado_em if isinstance(coletado_em, str) or coletado_em is None
            else _iso(coletado_em), "registro_bronze": registro_bronze}


def feed_resultado(*, eleicao: Eleicao, cargo: Cargo, abr: Abrangencia, resultado: ResultadoAbrangencia,
                   cores: Mapping[str, int], origem: dict, partes: list[dict] | None = None,
                   limite_candidatos: int | None = None, fotos: Mapping[str, str] | None = None,
                   ao_vivo: bool = False) -> dict:
    """Feed de resultado de um cargo numa abrangência (``tipo: resultado``).

    Com ``limite_candidatos``, leva só os mais votados e os eleitos, e conta os demais em
    ``candidatos_omitidos``: um município pode ter centenas de candidatos a deputado, e a lista completa
    está no feed da UF. ``partes`` traz as abrangências filhas, que colorem o mapa.
    """
    fotos = fotos or {}
    candidatos = resultado.candidatos
    omitidos = 0
    if limite_candidatos is not None and len(candidatos) > limite_candidatos:
        # Município com centenas de candidatos a deputado: o arquivo leva os
        # mais votados e os eleitos; o total completo está no da UF.
        mantidos = candidatos[:limite_candidatos] + [c for c in candidatos[limite_candidatos:] if c.eleito]
        omitidos = len(candidatos) - len(mantidos)
        candidatos = mantidos
    return {
        "versao": VERSAO_ESQUEMA_FEED,
        "tipo": "resultado",
        "eleicao": resumo_eleicao(eleicao),
        "cargo": cargo_json(cargo, resultado.vagas),
        "abrangencia": abr.para_json(),
        "atualizado_em": _iso(resultado.atualizado_em),
        "ao_vivo": ao_vivo,
        "origem": origem,
        "totalizacao": _totalizacao(resultado),
        "comparecimento": _comparecimento(resultado),
        "votos": _votos(resultado),
        "quociente_eleitoral": resultado.quociente_eleitoral,
        "candidatos": [candidato_json(c, resultado, cores, fotos.get(c.sq or "")) for c in candidatos],
        "candidatos_omitidos": omitidos,
        "agremiacoes": [{"nome": a.nome, "tipo": a.tipo, "composicao": a.composicao, "votos": a.votos,
                         "vagas": a.vagas} for a in resultado.agremiacoes],
        "partes": partes or [],
        "avisos": list(resultado.avisos),
    }


def feed_panorama(*, eleicao: Eleicao, cargo: Cargo, abr: Abrangencia, partes: list[dict],
                  origem: dict, atualizado_em: datetime | None, ao_vivo: bool = False,
                  avisos: Iterable[str] = ()) -> dict:
    """Um cargo visto de cima: o líder de cada parte e o placar por partido.

    Usado onde não existe resultado único: cargo municipal na UF e no Brasil
    (prefeitos, vereadores) e cargo estadual no Brasil (governadores,
    senadores, deputados). Cada parte já vem com ``partido`` (do líder, ou o
    mais votado nos proporcionais) e ``eleito``; nos proporcionais, também
    com ``bancada`` = {partido: eleitos}. O placar conta, por partido, as
    partes que lidera (``liderados``) e as vagas que obteve (``eleitos``), e a
    cor sai da ordem do placar.
    """
    placar: dict[str, dict] = {}

    def item(partido: str) -> dict:
        return placar.setdefault(partido, {"partido": partido, "liderados": 0, "eleitos": 0, "votos": 0})

    for p in partes:
        partido = p.get("partido")
        if partido:
            i = item(partido)
            i["liderados"] += 1
            i["votos"] += p.get("votos") or 0
            if "bancada" not in p and p.get("eleito"):
                i["eleitos"] += 1
        for sigla, n in (p.get("bancada") or {}).items():
            item(sigla)["eleitos"] += n
    ordem = sorted(placar.values(), key=lambda i: (-i["eleitos"], -i["liderados"], -i["votos"], i["partido"]))
    cores = atribuir_cores(i["partido"] for i in ordem)
    for i in ordem:
        i["cor"] = cores[i["partido"]]
    for p in partes:
        p["cor"] = cores.get(p.get("partido") or "", SEM_COR)
    finalizadas = sum(1 for p in partes if p.get("finalizada"))
    return {
        "versao": VERSAO_ESQUEMA_FEED,
        "tipo": "panorama",
        "eleicao": resumo_eleicao(eleicao),
        "cargo": cargo_json(cargo),
        "abrangencia": abr.para_json(),
        "atualizado_em": _iso(atualizado_em),
        "ao_vivo": ao_vivo,
        "origem": origem,
        "totalizacao": {"partes": len(partes), "partes_finalizadas": finalizadas,
                        "pct_partes": _r(100.0 * finalizadas / len(partes), 4) if partes else None},
        "partidos": ordem,
        "partes": partes,
        "avisos": list(avisos),
    }


def parte_de_panorama(abr: Abrangencia, panorama: dict) -> dict:
    """Linha de uma UF no panorama nacional de cargo municipal: o partido que lidera mais municípios nela.

    Leva a ``bancada`` da UF (eleitos por partido), para que o placar
    nacional some as vagas de todos os partidos, não só as do líder.
    """
    partidos = panorama.get("partidos") or []
    topo = partidos[0] if partidos else None
    t = panorama.get("totalizacao") or {}
    return {"codigo": abr.codigo, "nome": abr.nome, "ibge": abr.ibge,
            "lider": topo["partido"] if topo else None, "partido": topo["partido"] if topo else None,
            "nome_urna": None, "votos": topo["votos"] if topo else None,
            "pct": _r(100.0 * topo["liderados"] / t["partes"]) if topo and t.get("partes") else None,
            "margem": None, "eleito": False, "segundo_turno": False,
            "liderados": topo["liderados"] if topo else 0,
            "bancada": {i["partido"]: i["eleitos"] for i in partidos if i["eleitos"]},
            "pct_secoes": t.get("pct_partes"), "finalizada": t.get("partes") == t.get("partes_finalizadas"),
            "eleitorado": None}


def panorama_nacional(*, eleicao: Eleicao, cargo: Cargo, por_uf: Mapping[str, dict], origem: dict,
                      atualizado_em: datetime | None, ao_vivo: bool = False) -> dict:
    """Panorama do Brasil a partir dos panoramas das UFs (cargo municipal).

    O placar soma o de todas as UFs (municípios liderados e eleitos por
    partido); as partes são as UFs, cada uma com o partido que lidera mais
    municípios nela.
    """
    placar: dict[str, dict] = {}
    total = finalizadas = 0
    for p in por_uf.values():
        t = p.get("totalizacao") or {}
        total += t.get("partes") or 0
        finalizadas += t.get("partes_finalizadas") or 0
        for i in p.get("partidos", []):
            soma = placar.setdefault(i["partido"], {"partido": i["partido"], "liderados": 0, "eleitos": 0,
                                                    "votos": 0})
            for k in ("liderados", "eleitos", "votos"):
                soma[k] += i[k]
    ordem = sorted(placar.values(), key=lambda i: (-i["eleitos"], -i["liderados"], -i["votos"], i["partido"]))
    cores = atribuir_cores(i["partido"] for i in ordem)
    for i in ordem:
        i["cor"] = cores[i["partido"]]
    partes = []
    for uf, p in sorted(por_uf.items()):
        linha = parte_de_panorama(abrangencia_uf(uf), p)
        linha["cor"] = cores.get(linha.get("partido") or "", SEM_COR)
        partes.append(linha)
    return {
        "versao": VERSAO_ESQUEMA_FEED,
        "tipo": "panorama",
        "eleicao": resumo_eleicao(eleicao),
        "cargo": cargo_json(cargo),
        "abrangencia": abrangencia_brasil().para_json(),
        "atualizado_em": _iso(atualizado_em),
        "ao_vivo": ao_vivo,
        "origem": origem,
        "totalizacao": {"partes": total, "partes_finalizadas": finalizadas,
                        "pct_partes": _r(100.0 * finalizadas / total, 4) if total else None},
        "partidos": ordem,
        "partes": partes,
        "avisos": [],
    }


def feed_historico(*, eleicao: Eleicao, cargo: Cargo, abr: Abrangencia, pontos: list[dict],
                   candidatos: list[dict], origem: dict) -> dict:
    """``pontos``: [{"t": ISO, "pct_secoes": float, "votos": {numero: votos}}], em ordem."""
    return {
        "versao": VERSAO_ESQUEMA_FEED,
        "tipo": "historico",
        "eleicao": resumo_eleicao(eleicao),
        "cargo": cargo_json(cargo),
        "abrangencia": abr.para_json(),
        "origem": origem,
        "candidatos": candidatos,
        "pontos": pontos,
    }


# ---------------------------------------------------------------- índice

def entrada_indice(e: Eleicao, *, origem: str, ao_vivo: bool, atualizado_em: datetime | None,
                   ufs: Iterable[str] = (), vagas: Mapping[int, int] | None = None,
                   ufs_por_cargo: Mapping[int, Iterable[str]] | None = None,
                   municipios: bool = True) -> dict:
    """Linha da eleição no ``indice.json``.

    Com ``ufs_por_cargo``, cada cargo leva as UFs em que há dados (Deputado
    Distrital só no DF; Conselheiro Distrital só em PE), e cargos sem dado
    nenhum ficam fora: o portal não mostra aba que não leva a nada.

    ``municipios=False`` marca a eleição publicada só por UF (1933 a 1990): o
    portal não oferece o mapa de municípios nem a busca por município nela.
    """
    vagas = vagas or {}
    cargos = []
    for c in e.cargos:
        item = cargo_json(c, vagas.get(c.codigo))
        if ufs_por_cargo is not None:
            ufs_c = sorted({u.lower() for u in ufs_por_cargo.get(c.codigo, ())})
            if not ufs_c and c.codigo not in ufs_por_cargo:
                continue
            item["ufs"] = ufs_c
        cargos.append(item)
    return {
        **resumo_eleicao(e),
        "origem": origem,
        "ao_vivo": ao_vivo,
        "atualizado_em": _iso(atualizado_em),
        "cargos": cargos,
        "ufs": sorted({u.lower() for u in ufs}),
        **({} if municipios else {"municipios": False}),
    }


def eleicao_de_indice(item: dict) -> Eleicao:
    """Reconstrói o essencial de uma ``Eleicao`` a partir do índice gravado."""
    cargos = []
    for c in item.get("cargos", []):
        # Cargo de eleição antiga (slug fora da tabela CARGOS): slug e nível vêm do próprio índice
        proprio = c.get("slug") and c["slug"] != slug_do_cargo(c["codigo"])
        cargos.append(Cargo(codigo=c["codigo"], nome=c["nome"], tipo=TipoCargo(c["tipo"]), eleicao_tse=0,
                            vagas=c.get("vagas"), slug_fixo=c["slug"] if proprio else None,
                            nivel_fixo=Nivel(c["nivel"]) if proprio and c.get("nivel") else None))
    return Eleicao(id=item["id"], ano=item["ano"], turno=item["turno"], tipo=item["tipo"], nome=item["nome"],
                   data=date.fromisoformat(item["data"]) if item.get("data") else None, ciclo="",
                   pleito=None, origem=item.get("origem", ""), cargos=cargos, abrangencias=item.get("ufs", []))


def nome_eleicao(ano: int, turno: int, tipo: str) -> str:
    """Nome exibido da eleição, ex.: ``Eleições Gerais 2022 — 1º turno``."""
    rotulo = {"geral": "Eleições Gerais", "municipal": "Eleições Municipais"}.get(tipo, "Eleição")
    return f"{rotulo} {ano} — {turno}º turno"


# ---------------------------------------------------------------- escrita

def substituir_arquivo(tmp: Path, caminho: Path, tentativas: int = 20, espera_s: float = 0.05,
                dormir=time.sleep) -> None:
    """``os.replace`` com novas tentativas enquanto o destino estiver aberto por outro processo.

    No Windows, trocar um arquivo que o servidor local está enviando ao navegador falha com
    ``PermissionError`` (o arquivo aberto não permite exclusão). A leitura de um feed leva
    milissegundos; esperar um pouco e tentar de novo resolve, e a última falha é propagada.
    """
    for tentativa in range(tentativas):
        try:
            os.replace(tmp, caminho)
            return
        except PermissionError:
            if tentativa == tentativas - 1:
                raise
            dormir(espera_s * (tentativa + 1))


def _gravar_json(caminho: Path, dados: dict) -> Path:
    """Grava o JSON compacto de forma atômica: arquivo temporário e ``os.replace``.

    O portal nunca lê um feed pela metade; o PID no nome do temporário evita que dois processos
    gravando o mesmo feed usem o mesmo arquivo.
    """
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tmp = caminho.with_name(f".{caminho.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(dados, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    substituir_arquivo(tmp, caminho)
    return caminho


class EscritorFeeds:
    """Grava e lê os feeds sob ``raiz``, em ``<eleição>/<cargo>/<arquivo>.json``, e mantém o ``indice.json``."""

    def __init__(self, raiz: Path | str):
        """Escritor dos feeds sob o diretório ``raiz``."""
        self.raiz = Path(raiz)

    def caminho(self, eleicao_id: str, cargo_slug: str, arquivo: str) -> Path:
        """Caminho de um feed; cada trecho passa por ``_seguro``."""
        return self.raiz / _seguro(eleicao_id) / _seguro(cargo_slug) / f"{_seguro(arquivo)}.json"

    def gravar(self, eleicao_id: str, cargo_slug: str, abr: Abrangencia, feed: dict) -> Path:
        """Grava o feed da abrangência e devolve o caminho."""
        return _gravar_json(self.caminho(eleicao_id, cargo_slug, abr.arquivo), feed)

    def gravar_historico(self, eleicao_id: str, cargo_slug: str, abr: Abrangencia, feed: dict) -> Path:
        """Grava o feed de evolução da totalização da abrangência (``historico-<arquivo>.json``)."""
        return _gravar_json(self.caminho(eleicao_id, cargo_slug, f"historico-{abr.arquivo}"), feed)

    def ler(self, eleicao_id: str, cargo_slug: str, arquivo: str) -> dict | None:
        """Lê um feed já gravado; ``None`` se ele não existe."""
        caminho = self.caminho(eleicao_id, cargo_slug, arquivo)
        if not caminho.exists():
            return None
        return json.loads(caminho.read_text(encoding="utf-8"))

    # ------------------------------------------------------------ índice

    @property
    def caminho_indice(self) -> Path:
        """Caminho do ``indice.json``."""
        return self.raiz / "indice.json"

    def ler_indice(self) -> dict:
        """Lê o índice; sem arquivo, devolve um índice vazio, com a ``versao`` atual."""
        if not self.caminho_indice.exists():
            return {"versao": VERSAO_ESQUEMA_FEED, "gerado_em": None, "eleicoes": []}
        return json.loads(self.caminho_indice.read_text(encoding="utf-8"))

    def atualizar_indice(self, entrada: dict) -> dict:
        """Insere ou substitui a eleição no índice, mantendo a ordem (mais recente primeiro)."""
        indice = self.ler_indice()
        eleicoes = [e for e in indice.get("eleicoes", []) if e.get("id") != entrada["id"]]
        eleicoes.append(entrada)
        eleicoes.sort(key=lambda e: (e.get("ano") or 0, e.get("data") or "", e.get("turno") or 0, e.get("id")),
                      reverse=True)
        indice = {"versao": VERSAO_ESQUEMA_FEED,
                  "gerado_em": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                  "eleicoes": eleicoes}
        _gravar_json(self.caminho_indice, indice)
        return indice

    def remover_do_indice(self, eleicao_id: str) -> None:
        """Tira a eleição do índice e regrava o arquivo."""
        indice = self.ler_indice()
        indice["eleicoes"] = [e for e in indice.get("eleicoes", []) if e.get("id") != eleicao_id]
        _gravar_json(self.caminho_indice, indice)


def proporcional(cargo: Cargo | int) -> bool:
    """O cargo é proporcional (deputados e vereador)? Aceita o cargo ou o código.

    Cargo com ``slug_fixo`` (eleições de 1933 a 1990) decide pelo próprio ``tipo``: o código, ali, não
    segue a tabela atual.
    """
    if isinstance(cargo, Cargo) and cargo.slug_fixo:
        return cargo.tipo is TipoCargo.PROPORCIONAL
    codigo = cargo if isinstance(cargo, int) else cargo.codigo
    return codigo in CARGOS and CARGOS[codigo][0] in ("deputado-federal", "deputado-estadual",
                                                     "deputado-distrital", "vereador")


def municipal(cargo: Cargo | int) -> bool:
    """O cargo é disputado no município (prefeito, vereador, conselheiro distrital)? Aceita o cargo ou o código."""
    if isinstance(cargo, Cargo) and cargo.nivel_fixo is not None:
        return cargo.nivel_fixo is Nivel.MUNICIPIO
    codigo = cargo if isinstance(cargo, int) else cargo.codigo
    return codigo in CARGOS and CARGOS[codigo][2] is Nivel.MUNICIPIO
