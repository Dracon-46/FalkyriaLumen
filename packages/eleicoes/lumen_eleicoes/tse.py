"""Sistema de divulgação de resultados do TSE (``resultados.tse.jus.br/oficial``).

Estrutura dos arquivos, observada em 05/10/2026 (ver ``testes/fixtures/tse``):

``/oficial/comum/config/ele-c.json``
    catálogo: pleitos (``pl``), cada um com suas "eleições" (``e``), cargos
    (``cp``) e, nas municipais, os municípios com eleição (``mu``).
``/oficial/{ciclo}/{eleicao}/config/mun-e{eleicao:06d}-cm.json``
    municípios com código TSE (``cd``) e IBGE (``cdi``); vazio no exterior.
``/oficial/{ciclo}/{eleicao}/dados/{uf}/{uf}[{mun}]-c{cargo:04d}-e{eleicao:06d}-u.json``
    resultado de um cargo numa abrangência: ``br``, uma UF, ``zz`` (exterior)
    ou um município (código TSE colado à UF: ``sp71072``).
``/oficial/{ciclo}/{eleicao}/dados/{uf}/{uf}-e{eleicao:06d}-ab.json``
    andamento da totalização em cada município da UF (e ``br`` por UF).
``/oficial/{ciclo}/{eleicao}/fotos/{uf}/{sqcand}.jpeg``
    foto do candidato.

Números vêm como texto, com vírgula decimal (``"47,03"``); datas e horas em
campos separados (``dt`` e ``ht``), no horário de Brasília. O servidor
responde a ``If-Modified-Since`` com 304, o que o coletor usa para não baixar
de novo o que não mudou.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable

from .modelo import (
    CARGOS,
    Agremiacao,
    AndamentoAbrangencia,
    Candidato,
    Cargo,
    Comparecimento,
    Eleicao,
    MunicipioTse,
    ResultadoAbrangencia,
    TipoCargo,
    Totalizacao,
    Votos,
)

BASE = "https://resultados.tse.jus.br/oficial"
BRT = timezone(timedelta(hours=-3), "BRT")

# Siglas como o TSE usa nas URLs. "zz" é o exterior (só Presidente).
UFS_TSE = ("ac", "al", "am", "ap", "ba", "ce", "df", "es", "go", "ma", "mg", "ms", "mt", "pa", "pb", "pe",
           "pi", "pr", "rj", "rn", "ro", "rr", "rs", "sc", "se", "sp", "to")
UF_EXTERIOR = "zz"

TIPOS_ELEICAO = {"1": "geral", "8": "geral", "3": "municipal", "4": "suplementar", "7": "consulta"}


# ---------------------------------------------------------------- URLs

def url_catalogo(base: str = BASE) -> str:
    """URL do catálogo de pleitos e eleições (``ele-c.json``)."""
    return f"{base}/comum/config/ele-c.json"


def url_municipios(ciclo: str, eleicao: int, base: str = BASE) -> str:
    """URL do cadastro de municípios de uma eleição (``mun-e<eleição>-cm.json``)."""
    return f"{base}/{ciclo}/{eleicao}/config/mun-e{eleicao:06d}-cm.json"


def url_resultado(ciclo: str, eleicao: int, cargo: int, uf: str, municipio: str | None = None,
                  base: str = BASE) -> str:
    """URL do resultado de um cargo numa abrangência: Brasil, UF, exterior ou, com ``municipio``, um
    município (código TSE colado à UF)."""
    uf = uf.lower()
    abr = f"{uf}{municipio}" if municipio else uf
    return f"{base}/{ciclo}/{eleicao}/dados/{uf}/{abr}-c{cargo:04d}-e{eleicao:06d}-u.json"


def url_andamento(ciclo: str, eleicao: int, uf: str, base: str = BASE) -> str:
    """URL do andamento da totalização (``-ab``) de uma UF, ou de ``br``."""
    uf = uf.lower()
    return f"{base}/{ciclo}/{eleicao}/dados/{uf}/{uf}-e{eleicao:06d}-ab.json"


def url_foto(ciclo: str, eleicao: int, uf: str, sq: str, base: str = BASE) -> str:
    """URL da foto do candidato pelo sequencial (``sqcand``)."""
    return f"{base}/{ciclo}/{eleicao}/fotos/{uf.lower()}/{sq}.jpeg"


# ---------------------------------------------------------------- conversões

def _ler(conteudo: bytes | str | dict) -> Any:
    """JSON de bytes, texto ou objeto já lido; bytes são decodificados aceitando o BOM do UTF-8."""
    if isinstance(conteudo, dict):
        return conteudo
    if isinstance(conteudo, bytes):
        conteudo = conteudo.decode("utf-8-sig")
    return json.loads(conteudo)


def numero(texto: Any) -> float | None:
    """``"47,03"`` → 47.03. Vazio vira None."""
    if texto is None:
        return None
    t = str(texto).strip()
    if not t:
        return None
    try:
        return float(t.replace(".", "").replace(",", ".")) if "," in t else float(t)
    except ValueError:
        return None


def inteiro(texto: Any) -> int | None:
    """Texto do TSE → int; vazio ou inválido vira None."""
    if texto is None or str(texto).strip() == "":
        return None
    try:
        return int(str(texto).strip())
    except ValueError:
        return None


def _soma(*valores: int | None) -> int | None:
    """Soma das parcelas publicadas; None só quando a fonte não publica nenhuma."""
    presentes = [v for v in valores if v is not None]
    return sum(presentes) if presentes else None


def data_br(texto: str | None) -> date | None:
    """``"dd/mm/aaaa"`` → ``date``; vazio ou inválido vira None."""
    if not texto:
        return None
    try:
        return datetime.strptime(texto.strip(), "%d/%m/%Y").date()
    except ValueError:
        return None


def instante(dt: str | None, ht: str | None) -> datetime | None:
    """Junta os campos ``dt`` e ``ht`` do TSE num ``datetime`` no horário de Brasília.

    Sem data, devolve None; hora ausente ou inválida vira meia-noite.
    """
    d = data_br(dt)
    if d is None:
        return None
    try:
        h = datetime.strptime((ht or "00:00:00").strip(), "%H:%M:%S").time()
    except ValueError:
        h = datetime.min.time()
    return datetime.combine(d, h, tzinfo=BRT)


# ---------------------------------------------------------------- catálogo

def _id_eleicao(ano: int, turno: int, tipo: str, pleito: str | None) -> str:
    """Id da eleição na aba: ``<ano>-<turno>t-<tipo>``, com um código do TSE no fim fora das gerais e municipais.

    Suplementares e consultas acontecem cada uma num lugar e num dia diferentes; o sufixo as separa.
    """
    base = f"{ano}-{turno}t-{tipo}"
    return base if tipo in ("geral", "municipal") else f"{base}-{pleito}"


def ler_catalogo(conteudo: bytes | str | dict) -> list[Eleicao]:
    """Eleições do catálogo, agrupadas por pleito e turno (ver ``modelo.Eleicao``).

    Consultas populares e eleições suplementares ficam com id próprio,
    porque cada uma acontece num lugar e num dia diferentes.
    """
    dados = _ler(conteudo)
    saida: dict[str, Eleicao] = {}
    for pleito in dados.get("pl", []):
        ciclo = pleito.get("c") or ""
        data = data_br(pleito.get("dt"))
        ano = data.year if data else int(ciclo[-4:]) if ciclo[-4:].isdigit() else 0
        for e in pleito.get("e", []):
            tipo = TIPOS_ELEICAO.get(str(e.get("tp")), "outra")
            turno = inteiro(e.get("t")) or 1
            codigo_tse = inteiro(e.get("cd"))
            cargos_e = [cp for a in e.get("abr", []) for cp in a.get("cp", [])]
            # "Eleição municipal" dentro do pleito geral (Fernando de Noronha):
            # entra na eleição geral do mesmo dia, não vira eleição à parte.
            tipo_grupo = tipo
            if tipo == "municipal" and any(str(p.get("cd")) == "25" for p in cargos_e):
                tipo_grupo = "geral"
            eid = _id_eleicao(ano, turno, tipo_grupo, e.get("cd") if tipo_grupo not in ("geral", "municipal") else pleito.get("cd"))
            el = saida.get(eid)
            if el is None:
                rotulo = {"geral": "Eleições Gerais", "municipal": "Eleições Municipais"}.get(tipo_grupo)
                nome = f"{rotulo} {ano} — {turno}º turno" if rotulo else (e.get("nm") or "").strip()
                el = Eleicao(id=eid, ano=ano, turno=turno, tipo=tipo_grupo, nome=nome, data=data,
                             ciclo=ciclo, pleito=pleito.get("cd"), origem="resultados")
                saida[eid] = el
            vistos = {c.codigo for c in el.cargos}
            for cp in cargos_e:
                cod = inteiro(cp.get("cd"))
                if cod is None or cod in vistos:
                    continue
                el.cargos.append(Cargo(
                    codigo=cod,
                    nome=(CARGOS.get(cod, (None, (cp.get("ds") or "").strip()))[1]),
                    tipo=TipoCargo.PROPORCIONAL if str(cp.get("tp")) == "2" else TipoCargo.MAJORITARIO,
                    eleicao_tse=codigo_tse,
                ))
                vistos.add(cod)
            for a in e.get("abr", []):
                if a.get("cd") and a["cd"] != "br" and a["cd"] not in el.abrangencias:
                    el.abrangencias.append(a["cd"])
    for el in saida.values():
        el.cargos.sort(key=lambda c: c.codigo)
        el.abrangencias.sort()
    return sorted(saida.values(), key=lambda e: (e.ano, e.data or date.min, e.turno, e.id), reverse=True)


def ler_municipios(conteudo: bytes | str | dict) -> list[MunicipioTse]:
    """Lê ``mun-e<eleição>-cm.json``: municípios de cada UF com código TSE, código IBGE (``cdi``, vazio no
    exterior), capital e zonas."""
    dados = _ler(conteudo)
    saida = []
    for abr in dados.get("abr", []):
        uf = (abr.get("cd") or "").lower()
        for m in abr.get("mu", []):
            saida.append(MunicipioTse(
                uf=uf, codigo_tse=str(m.get("cd")), codigo_ibge=(m.get("cdi") or None),
                nome=(m.get("nm") or "").strip(), capital=m.get("c") == "s",
                zonas=tuple(m.get("z") or ()),
            ))
    return saida


# ---------------------------------------------------------------- resultados

def _candidatos(cargo: dict) -> tuple[list[Candidato], list[Agremiacao], dict[str, int]]:
    """Candidatos, agremiações e votos por partido de um cargo do arquivo de resultado.

    Percorre agremiação → partido → candidato. A situação fica como o TSE publica e dela saem ``eleito`` e
    ``segundo_turno``; o vice (ou o primeiro suplente) vem de ``vs``. Candidatos e agremiações saem em
    ordem decrescente de votos; o total por partido (``tvtn``) só entra quando publicado.
    """
    candidatos: list[Candidato] = []
    agremiacoes: list[Agremiacao] = []
    partidos: dict[str, int] = {}
    tipos = {"i": "isolado", "c": "coligacao", "f": "federacao"}
    for a in cargo.get("agr", []):
        agremiacoes.append(Agremiacao(
            nome=(a.get("nm") or "").strip(), tipo=tipos.get(a.get("tp"), a.get("tp") or ""),
            composicao=a.get("com"), votos=inteiro(a.get("tvtn")) or sum(inteiro(p.get("tvtn")) or 0 for p in a.get("par", [])),
            vagas=inteiro(a.get("vag")),
        ))
        for p in a.get("par", []):
            if p.get("sg") and p.get("tvtn") not in (None, ""):
                partidos[p["sg"]] = partidos.get(p["sg"], 0) + (inteiro(p.get("tvtn")) or 0)
            for c in p.get("cand", []):
                vice = next((v.get("nmu") for v in c.get("vs", []) if v.get("tp") in ("v", "s1")), None)
                situacao = (c.get("st") or "").strip()
                candidatos.append(Candidato(
                    numero=str(c.get("n")), sq=c.get("sqcand"),
                    nome=(c.get("nm") or "").strip(), nome_urna=(c.get("nmu") or c.get("nm") or "").strip(),
                    partido=p.get("sg"), agremiacao=(a.get("nm") or "").strip(), composicao=a.get("com"),
                    votos=inteiro(c.get("vap")) or 0, pct_validos=numero(c.get("pvapn") or c.get("pvap")),
                    situacao=situacao, eleito=situacao.lower().startswith("eleito"),
                    segundo_turno="2º turno" in situacao.lower() or "2o turno" in situacao.lower(),
                    destinacao=(c.get("dvt") or "").strip() or None, vice=vice,
                ))
    candidatos.sort(key=lambda c: (-c.votos, c.numero))
    agremiacoes.sort(key=lambda a: (-a.votos, a.nome))
    return candidatos, agremiacoes, partidos


def ler_resultado(conteudo: bytes | str | dict) -> ResultadoAbrangencia:
    """Converte um arquivo de resultado (``-u``) em ``ResultadoAbrangencia``.

    Lê o cargo do arquivo (o primeiro de ``carg``; cada arquivo é de um cargo). Nos percentuais, o
    campo de precisão completa (``pstn``, ``pvapn``...) tem preferência sobre o arredondado; ``md`` só
    vira ``matematicamente_definida`` quando presente.
    """
    d = _ler(conteudo)
    cargo = (d.get("carg") or [{}])[0]
    candidatos, agremiacoes, partidos = _candidatos(cargo)
    s, e, v = d.get("s") or {}, d.get("e") or {}, d.get("v") or {}
    return ResultadoAbrangencia(
        eleicao_tse=inteiro(d.get("ele")),
        cargo=inteiro(cargo.get("cd")) or 0,
        vagas=inteiro(cargo.get("nv")),
        abrangencia_tipo=(d.get("tpabr") or "").lower(),
        abrangencia_codigo=(d.get("cdabr") or "").lower(),
        atualizado_em=instante(d.get("dt"), d.get("ht")),
        totalizacao=Totalizacao(
            secoes=inteiro(s.get("ts")), secoes_totalizadas=inteiro(s.get("st")),
            pct_secoes=numero(s.get("pstn") or s.get("pst")),
            finalizada=d.get("tf") == "s", andamento=d.get("and"),
            matematicamente_definida=(d.get("md") == "s") if d.get("md") else None,
        ),
        comparecimento=Comparecimento(
            eleitorado=inteiro(e.get("te")), comparecimento=inteiro(e.get("c")),
            abstencao=inteiro(e.get("a")), pct_comparecimento=numero(e.get("pcn") or e.get("pc")),
            pct_abstencao=numero(e.get("pan") or e.get("pa")),
            eleitorado_secoes_nao_instaladas=inteiro(e.get("esni")),
        ),
        # "tvn" é o total de nulos (os "vn" mais os técnicos, "vnt"), o mesmo de "ptvn" e dos dados abertos;
        # os anulados somam os sub judice, também como nos dados abertos
        votos=Votos(
            validos=inteiro(v.get("vv")), brancos=inteiro(v.get("vb")),
            nulos=inteiro(v.get("tvn")) if v.get("tvn") is not None else inteiro(v.get("vn")),
            nulos_tecnicos=inteiro(v.get("vnt")),
            anulados=_soma(inteiro(v.get("van")), inteiro(v.get("vansj"))), legenda=inteiro(v.get("vl")),
            pct_validos=numero(v.get("pvvcn") or v.get("pvvc")),
            pct_brancos=numero(v.get("pvbn") or v.get("pvb")),
            pct_nulos=numero(v.get("ptvnn") or v.get("ptvn")),
        ),
        candidatos=candidatos,
        agremiacoes=agremiacoes,
        quociente_eleitoral=inteiro(cargo.get("qe")),
        votos_partido=partidos,
    )


def ler_andamento(conteudo: bytes | str | dict) -> list[AndamentoAbrangencia]:
    """Converte o arquivo de andamento (``-ab``) em uma linha por abrangência, com o instante e as seções
    totalizadas."""
    d = _ler(conteudo)
    saida = []
    for a in d.get("abr", []):
        s = a.get("s") or {}
        saida.append(AndamentoAbrangencia(
            tipo=(a.get("tpabr") or "").lower(), codigo=(a.get("cdabr") or "").lower(),
            andamento=a.get("and"), atualizado_em=instante(a.get("dt"), a.get("ht")),
            pct_secoes=numero(s.get("pstn") or s.get("pst")),
            secoes_totalizadas=inteiro(s.get("st")), secoes=inteiro(s.get("ts")),
        ))
    return saida


def mudaram(antes: Iterable[AndamentoAbrangencia], agora: Iterable[AndamentoAbrangencia]) -> list[str]:
    """Códigos cuja totalização avançou entre duas leituras do ``-ab``.

    É o que permite ao coletor baixar só os municípios que mudaram, em vez dos
    5.570 a cada passada.
    """
    anterior = {a.codigo: (a.atualizado_em, a.secoes_totalizadas) for a in antes}
    return sorted(a.codigo for a in agora
                  if anterior.get(a.codigo) != (a.atualizado_em, a.secoes_totalizadas))
