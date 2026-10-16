"""Locais de votação de cada zona eleitoral, para o mapa das zonas dentro do município (ADR-029).

A Justiça Eleitoral não publica os limites das zonas eleitorais. Publica, no
Portal de Dados Abertos, o eleitorado de cada seção com o local de votação, a
zona e as coordenadas do local (``eleitorado_local_votacao_AAAA.zip``, de 2018
em diante; de 2026 em diante, um CSV por UF e um ``_BRASIL`` que é a soma deles
e é ignorado). Daqui sai, para cada município com duas zonas ou mais, a lista
dos locais com a zona e o eleitorado. O portal desenha cada zona como a região
mais próxima dos locais dela (diagrama de Voronoi recortado pelo contorno do
município, ``src/lib/voronoi.ts``) e diz que o contorno é aproximado.

Formato observado em 15/10/2026, de 2018 a 2026: uma linha por seção, Latin-1,
``;``, aspas; coordenadas em ``NR_LATITUDE`` e ``NR_LONGITUDE``, com ponto
decimal até 2024 e vírgula em 2026, e ``-1`` quando o local não tem coordenada.

Locais descartados, e contados no arquivo do município:

- sem coordenada, ou com coordenada fora do Brasil;
- fora do município. Com o contorno fino do município (``geo/mu/<ibge>.json``,
  qualidade ``maxima``; ver ``geo.py``), fica o local dentro dele ou a menos de
  ``TOLERANCIA_M`` da borda (a fronteira publicada e a coordenada têm erro de
  alguns metros). Sem ele, vale a malha ``minima`` da UF, que simplifica tanto
  a fronteira que um local de verdade pode cair do lado de fora: fica o que
  está dentro, ou fora de todos os municípios mas perto da caixa do próprio.

Arquivos gravados no diretório dos feeds::

    geo/zonas-<ano>/indice.json         municípios com duas zonas ou mais (código IBGE → zonas)
    geo/zonas-<ano>/mu-<ibge>.json      as zonas do município e os locais de votação de cada uma
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import zipfile
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from lumen_ingestao.bronze import ArmazemBronze

from . import carga
from . import dados_abertos as da
from .configuracao import ConfiguracaoEleicoes
from .feeds import _gravar_json, origem_json
from .municipios import CadastroMunicipios
from .referencias import DIR_DADOS
from .transferencia import Manifesto, baixar_arquivo

ANOS_LOCAIS = (2026, 2024, 2022, 2020, 2018)
CONJUNTO_LOCAIS = "eleitorado_locais_votacao"
VERSAO_ZONAS = 1
# Revisão do cálculo (filtro dos locais, campos gravados). Sobe quando o que sai do mesmo ZIP muda: o
# ``preparar`` grava de novo os anos gravados por uma revisão anterior. É independente de ``VERSAO_ZONAS``,
# a versão do formato que o portal lê.
REVISAO_ZONAS = 1
DIR_ZONAS = "geo/zonas-{ano}"

COLUNAS_LOCAIS = ("NR_TURNO", "SG_UF", "CD_MUNICIPIO", "NR_ZONA", "NR_LOCAL_VOTACAO", "NM_LOCAL_VOTACAO",
                  "NR_LATITUDE", "NR_LONGITUDE", "QT_ELEITOR_SECAO")
# Caixa do território brasileiro, com folga: coordenada fora dela é erro de cadastro
LATITUDES = (-34.0, 5.5)
LONGITUDES = (-74.5, -28.5)
# Sem contorno fino: local fora do contorno fica se está a menos desta fração do tamanho do município
FOLGA_CONTORNO = 0.05
# Com contorno fino: local fora do contorno fica se está a menos desta distância da borda, em metros
TOLERANCIA_M = 300.0
METROS_POR_GRAU = 111_320.0
CASAS_COORDENADA = 5          # 5 casas decimais: cerca de 1 m, mais que a precisão das coordenadas publicadas

Ponto = tuple[float, float]   # (longitude, latitude)


def url_locais(ano: int) -> str:
    """Endereço do ZIP de locais de votação de um ano na CDN do TSE."""
    return f"{da.CDN}/{CONJUNTO_LOCAIS}/eleitorado_local_votacao_{ano}.zip"


def baixar_locais(cfg: ConfiguracaoEleicoes, ano: int, *, bronze: ArmazemBronze | None = None,
                  atualizar: bool = False, saida: Callable[[str], None] | None = None) -> tuple[Path, Manifesto]:
    """Baixa o ZIP de locais de votação do ano para ``<arquivos>/locais/`` (retomável, com manifesto, ADR-021)
    e registra o manifesto no bronze. Devolve o caminho e o manifesto."""
    url = url_locais(ano)
    destino = cfg.arquivos / "locais" / url.rsplit("/", 1)[-1]
    escrever = saida or (lambda msg: print(msg, flush=True))
    escrever(f"{ano}  {CONJUNTO_LOCAIS}  {url}")
    manifesto = baixar_arquivo(url, destino, user_agent=cfg.user_agent, atualizar=atualizar,
                               progresso=carga.progresso_mb(saida=escrever))
    carga.registrar_manifesto(bronze, manifesto)
    return destino, manifesto


def coordenada(valor: str | None) -> float | None:
    """Texto da coordenada como número: aceita ponto ou vírgula decimal; ``-1``, vazio e texto viram None."""
    if valor is None:
        return None
    v = valor.strip().replace(",", ".")
    if not v or v.startswith("#"):
        return None
    try:
        n = float(v)
    except ValueError:
        return None
    return n if math.isfinite(n) and n != -1 else None


# ---------------------------------------------------------------- leitura

@dataclass
class LocalVotacao:
    """Um local de votação de uma zona, com o eleitorado somado das seções e as coordenadas publicadas."""

    zona: str
    numero: str
    nome: str
    eleitores: int = 0
    lon: float | None = None
    lat: float | None = None


@dataclass
class LocaisMunicipio:
    """Locais de votação de um município (chave: zona e número do local)."""

    uf: str
    tse: str
    nome_tse: str
    locais: dict[tuple[str, str], LocalVotacao] = field(default_factory=dict)

    @property
    def zonas(self) -> list[str]:
        """Números das zonas do município, em ordem numérica."""
        return sorted({z for z, _ in self.locais}, key=int)


def ler_locais(fluxo: io.BufferedIOBase, municipios: dict[tuple[str, str], LocaisMunicipio] | None = None,
               ) -> dict[tuple[str, str], LocaisMunicipio]:
    """Lê um CSV de locais de votação e acumula, por município (``(uf, código TSE)``), os locais de cada zona.

    Só as linhas do 1º turno contam: as do 2º repetem as seções dos municípios que tiveram 2º turno. O
    eleitorado do local é a soma das seções dele; a coordenada é a primeira válida que aparece.
    """
    municipios = {} if municipios is None else municipios
    linhas = da.Linhas(fluxo, COLUNAS_LOCAIS)
    ix = linhas.colunas
    i_nome_mun = ix.get("NM_MUNICIPIO")
    for linha in linhas:
        if da._int(linha[ix["NR_TURNO"]]) != 1:
            continue
        zona = da.zona_da_linha(linha[ix["NR_ZONA"]])
        if zona is None:
            continue
        uf = linha[ix["SG_UF"]].strip().lower()
        tse = str(da._int(linha[ix["CD_MUNICIPIO"]])).zfill(5)
        m = municipios.get((uf, tse))
        if m is None:
            nome = linha[i_nome_mun].strip() if i_nome_mun is not None and i_nome_mun < len(linha) else tse
            m = municipios[(uf, tse)] = LocaisMunicipio(uf, tse, nome)
        numero = str(da._int(linha[ix["NR_LOCAL_VOTACAO"]]))
        local = m.locais.get((zona, numero))
        if local is None:
            local = m.locais[(zona, numero)] = LocalVotacao(zona, numero, linha[ix["NM_LOCAL_VOTACAO"]].strip())
        local.eleitores += da._int(linha[ix["QT_ELEITOR_SECAO"]])
        if local.lat is None:
            lat, lon = coordenada(linha[ix["NR_LATITUDE"]]), coordenada(linha[ix["NR_LONGITUDE"]])
            if (lat is not None and lon is not None and LATITUDES[0] <= lat <= LATITUDES[1]
                    and LONGITUDES[0] <= lon <= LONGITUDES[1]):
                local.lat, local.lon = lat, lon
    return municipios


def ler_zip_locais(caminho: Path | str) -> dict[tuple[str, str], LocaisMunicipio]:
    """Lê todos os CSV do ZIP de locais (um só até 2024; um por UF depois, sem o ``_BRASIL``)."""
    municipios: dict[tuple[str, str], LocaisMunicipio] = {}
    with zipfile.ZipFile(caminho) as zf:
        for nome in da.entradas_csv(zf.namelist()):
            with zf.open(nome) as fluxo:
                ler_locais(fluxo, municipios)
    return municipios


# ---------------------------------------------------------------- contorno do município

def aneis_da_malha(topo: dict) -> dict[str, list[list[Ponto]]]:
    """Anéis (contornos fechados, em longitude e latitude) de cada área de uma malha TopoJSON do IBGE.

    É a mesma decodificação de ``src/lib/topojson.ts``: soma das diferenças e ``transform``.
    """
    sx, sy = (topo.get("transform") or {}).get("scale", (1, 1))
    tx, ty = (topo.get("transform") or {}).get("translate", (0, 0))
    arcos: list[list[Ponto]] = []
    for arco in topo["arcs"]:
        x = y = 0
        pontos = []
        for dx, dy in arco:
            if "transform" in topo:
                x += dx
                y += dy
                pontos.append((x * sx + tx, y * sy + ty))
            else:
                pontos.append((dx, dy))
        arcos.append(pontos)

    def anel(indices: list[int]) -> list[Ponto]:
        pontos: list[Ponto] = []
        for i in indices:
            arco = arcos[~i][::-1] if i < 0 else arcos[i]
            pontos.extend(arco[1:] if pontos else arco)
        return pontos

    saida: dict[str, list[list[Ponto]]] = {}
    for g in next(iter(topo["objects"].values()))["geometries"]:
        codigo = str((g.get("properties") or {}).get("codarea", ""))
        if g["type"] == "Polygon":
            saida[codigo] = [anel(r) for r in g["arcs"]]
        elif g["type"] == "MultiPolygon":
            saida[codigo] = [anel(r) for p in g["arcs"] for r in p]
    return saida


def dentro(ponto: Ponto, aneis: Iterable[list[Ponto]]) -> bool:
    """Se o ponto está dentro da área (regra par-ímpar sobre todos os anéis: buracos e ilhas inclusive)."""
    x, y = ponto
    dentro_ = False
    for r in aneis:
        n = len(r)
        for i in range(n):
            (x1, y1), (x2, y2) = r[i], r[i - 1]
            if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
                dentro_ = not dentro_
    return dentro_


def caixa(aneis: Iterable[list[Ponto]]) -> tuple[float, float, float, float]:
    """Caixa envolvente (lon mín., lat mín., lon máx., lat máx.) dos anéis."""
    xs = [p[0] for r in aneis for p in r]
    ys = [p[1] for r in aneis for p in r]
    return min(xs), min(ys), max(xs), max(ys)


def distancia_borda_m(ponto: Ponto, aneis: Iterable[list[Ponto]]) -> float:
    """Distância aproximada, em metros, do ponto ao contorno mais próximo (equiretangular na latitude do ponto)."""
    x, y = ponto
    k = math.cos(math.radians(y))
    menor = math.inf
    for r in aneis:
        for i in range(len(r)):
            (ax, ay), (bx, by) = r[i - 1], r[i]
            ax, bx, px = ax * k, bx * k, x * k
            dx, dy = bx - ax, by - ay
            t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, ((px - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy)))
            menor = min(menor, math.hypot(px - (ax + t * dx), y - (ay + t * dy)))
    return menor * METROS_POR_GRAU


def no_contorno_fino(ponto: Ponto, aneis: list[list[Ponto]]) -> bool:
    """Se o local pertence ao município pelo contorno fino: dentro, ou a menos de ``TOLERANCIA_M`` da borda."""
    return dentro(ponto, aneis) or distancia_borda_m(ponto, aneis) <= TOLERANCIA_M


def no_municipio(ponto: Ponto, proprio: list[list[Ponto]], vizinhos: Iterable[list[list[Ponto]]]) -> bool:
    """Se o local pertence ao município: dentro do contorno dele; ou fora de todos, mas perto da caixa dele.

    Dentro do contorno de outro município, ou longe, é coordenada de outro lugar.
    """
    if dentro(ponto, proprio):
        return True
    x0, y0, x1, y1 = caixa(proprio)
    fx, fy = (x1 - x0) * FOLGA_CONTORNO, (y1 - y0) * FOLGA_CONTORNO
    if not (x0 - fx <= ponto[0] <= x1 + fx and y0 - fy <= ponto[1] <= y1 + fy):
        return False
    return not any(dentro(ponto, outro) for outro in vizinhos)


# ---------------------------------------------------------------- arquivos

@dataclass
class ResumoZonas:
    """O que ``gravar_zonas`` produziu num ano, para o resumo da linha de comando."""

    ano: int
    municipios: int = 0
    zonas: int = 0
    locais: int = 0
    sem_coordenada: int = 0
    fora_do_municipio: int = 0
    sem_malha: list[str] = field(default_factory=list)
    # Municípios (código IBGE) sem o contorno fino: conferidos pela malha simplificada da UF.
    # ``lumen eleicoes mapas --contornos`` baixa o que falta.
    sem_contorno: list[str] = field(default_factory=list)
    removidos: int = 0

    def para_json(self) -> dict:
        """Dicionário para imprimir em JSON."""
        return {"ano": self.ano, "municipios": self.municipios, "zonas": self.zonas, "locais": self.locais,
                "sem_coordenada": self.sem_coordenada, "fora_do_municipio": self.fora_do_municipio,
                "sem_malha": self.sem_malha, "sem_contorno": self.sem_contorno, "removidos": self.removidos}


def assinatura_contornos() -> str:
    """SHA-256 dos contornos finos que vêm com o pacote (nome e conteúdo de cada um, em ordem): mudou um
    contorno, o mapa das zonas precisa ser gravado de novo."""
    h = hashlib.sha256()
    for p in sorted((DIR_DADOS / "geo" / "mu").glob("*.json")):
        h.update(p.name.encode())
        h.update(p.read_bytes())
    return h.hexdigest()


def municipios_dos_indices(raiz_feeds: Path | str) -> set[str]:
    """Códigos IBGE de todos os municípios listados nos índices ``geo/zonas-<ano>/indice.json``."""
    codigos: set[str] = set()
    for indice in Path(raiz_feeds).glob("geo/zonas-*/indice.json"):
        codigos.update(json.loads(indice.read_text(encoding="utf-8")).get("municipios") or {})
    return codigos


def arquivo_municipio(m: LocaisMunicipio, *, ano: int, ibge: str, nome: str, origem: dict,
                      aneis: list[list[Ponto]], vizinhos: list[list[list[Ponto]]],
                      fino: list[list[Ponto]] | None = None) -> tuple[dict, int, int]:
    """Conteúdo de ``mu-<ibge>.json`` e as contagens de locais sem coordenada e fora do município.

    Com ``fino`` (o contorno em qualidade ``maxima``), o local é conferido por ele (``no_contorno_fino``);
    sem, pela malha da UF (``aneis`` do município e ``vizinhos``).

    ``locais`` é uma lista de ``[longitude, latitude, zona, eleitores, nome]``, em ordem de zona e de
    número do local (bytes iguais a cada geração). ``zonas`` traz todas as zonas, mesmo a que ficou sem
    local com coordenada (``locais = 0``): a tabela do portal a mostra, o mapa não.
    """
    sem_coordenada = fora = 0
    por_zona: dict[str, dict] = {z: {"zona": z, "locais": 0, "eleitores": 0} for z in m.zonas}
    locais = []
    for (zona, _numero), local in sorted(m.locais.items(), key=lambda kv: (int(kv[0][0]), int(kv[0][1]))):
        por_zona[zona]["eleitores"] += local.eleitores
        if local.lat is None or local.lon is None:
            sem_coordenada += 1
            continue
        ponto = (local.lon, local.lat)
        if not (no_contorno_fino(ponto, fino) if fino else no_municipio(ponto, aneis, vizinhos)):
            fora += 1
            continue
        por_zona[zona]["locais"] += 1
        locais.append([round(local.lon, CASAS_COORDENADA), round(local.lat, CASAS_COORDENADA), zona,
                       local.eleitores, local.nome])
    dados = {
        "versao": VERSAO_ZONAS, "tipo": "zonas", "ano": ano,
        "municipio": {"ibge": ibge, "tse": m.tse, "uf": m.uf, "nome": nome},
        "origem": origem,
        "zonas": list(por_zona.values()),
        "locais": locais,
        "descartados": {"sem_coordenada": sem_coordenada, "fora_do_municipio": fora},
    }
    return dados, sem_coordenada, fora


def gravar_zonas(ano: int, zip_locais: Path | str, raiz_feeds: Path | str, cadastro: CadastroMunicipios, *,
                 malhas: Path | str | None = None, manifesto: Manifesto | None = None,
                 progresso: Callable[[str], None] | None = None) -> ResumoZonas:
    """Lê o ZIP de locais de um ano e grava ``geo/zonas-<ano>/``: um arquivo por município com duas zonas
    ou mais e o índice. Devolve o resumo.

    O contorno de cada município vem de ``malhas`` (por padrão, o ``geo`` do diretório dos feeds e, na
    falta, o do pacote): o fino, ``mu/<ibge>.json``, quando existe, e a malha da UF. Arquivo de município
    que ficou de fora nesta gravação (deixou de ter mais de uma zona, por exemplo) é apagado: o portal só
    lê os que o índice lista, mas o diretório fica igual ao que foi gravado. Município sem código IBGE ou sem área na malha da
    UF fica de fora (o portal não teria onde desenhá-lo) e é anotado no resumo.
    """
    raiz = Path(raiz_feeds)
    # As malhas do diretório dos feeds (podem ser mais novas) e, na falta delas, as que vêm com o pacote
    dirs_malhas = [Path(malhas)] if malhas else [raiz / "geo", DIR_DADOS / "geo"]

    def malha(relativo: str) -> dict | None:
        for d in dirs_malhas:
            if (d / relativo).exists():
                return json.loads((d / relativo).read_text(encoding="utf-8"))
        return None

    escrever = progresso or (lambda _msg: None)
    origem = origem_json("dados_abertos", url=manifesto.url if manifesto else url_locais(ano),
                         sha256=manifesto.sha256 if manifesto else None,
                         coletado_em=manifesto.baixado_em if manifesto else None)
    escrever(f"{ano}: lendo os locais de votação")
    municipios = ler_zip_locais(zip_locais)
    resumo = ResumoZonas(ano=ano)
    destino = raiz / DIR_ZONAS.format(ano=ano)
    indice: dict[str, int] = {}
    por_uf: dict[str, list[LocaisMunicipio]] = defaultdict(list)
    for m in municipios.values():
        if len(m.zonas) > 1:
            por_uf[m.uf].append(m)
    for uf in sorted(por_uf):
        topo_uf = malha(f"uf-{uf}-mu.json")
        aneis_uf = aneis_da_malha(topo_uf) if topo_uf else {}
        for m in sorted(por_uf[uf], key=lambda x: x.tse):
            cad = cadastro.por_tse(uf, m.tse)
            if cad is None or not cad.ibge or cad.ibge not in aneis_uf:
                resumo.sem_malha.append(f"{uf}{m.tse}")
                continue
            vizinhos = [a for codigo, a in aneis_uf.items() if codigo != cad.ibge]
            topo_fino = malha(f"mu/{cad.ibge}.json")
            fino = aneis_da_malha(topo_fino).get(cad.ibge) if topo_fino else None
            if fino is None:
                resumo.sem_contorno.append(cad.ibge)
            dados, sem, fora = arquivo_municipio(m, ano=ano, ibge=cad.ibge, nome=cad.nome, origem=origem,
                                                 aneis=aneis_uf[cad.ibge], vizinhos=vizinhos, fino=fino)
            _gravar_json(destino / f"mu-{cad.ibge}.json", dados)
            indice[cad.ibge] = len(dados["zonas"])
            resumo.municipios += 1
            resumo.zonas += len(dados["zonas"])
            resumo.locais += len(dados["locais"])
            resumo.sem_coordenada += sem
            resumo.fora_do_municipio += fora
    for antigo in destino.glob("mu-*.json") if destino.exists() else ():
        if antigo.stem[3:] not in indice:
            antigo.unlink()
            resumo.removidos += 1
    _gravar_json(destino / "indice.json", {"versao": VERSAO_ZONAS, "tipo": "zonas-indice", "ano": ano,
                                           "origem": origem, "municipios": dict(sorted(indice.items()))})
    escrever(f"{ano}: {resumo.municipios} municípios com mais de uma zona, {resumo.locais} locais")
    return resumo
