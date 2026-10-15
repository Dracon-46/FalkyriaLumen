"""Malhas do IBGE para o mapa da aba Eleições.

API de malhas v3 do IBGE (``servicodados.ibge.gov.br/api/v3/malhas``), sem
autenticação, com CORS aberto. ``formato=application/json`` devolve
**TopoJSON**: arcos compartilhados entre vizinhos e coordenadas quantizadas,
o que deixa o arquivo várias vezes menor que o GeoJSON equivalente. O
portal decodifica TopoJSON sozinho (``src/lib/topojson.ts``), sem biblioteca.

Tamanhos medidos em 05/10/2026, qualidade ``minima``: Brasil por UF 31 KB;
São Paulo por município 136 KB; Acre 10 KB. A qualidade ``intermediaria``
dobra o tamanho (SP: 292 KB) e quase não muda o desenho no tamanho em que o
mapa é exibido, por isso o padrão é ``minima``.

Arquivos gravados (sempre os bytes publicados pelo IBGE, depois de
validados)::

    geo/br-uf.json          Brasil, uma geometria por UF (codarea = código da UF)
    geo/uf-<sigla>-mu.json  UF, uma geometria por município (codarea = código IBGE)
    geo/mu/<ibge>.json      contorno de um município na qualidade ``maxima``, para os que têm mais de
                            uma zona eleitoral (``baixar_contornos``)

Na qualidade ``minima``, um município pequeno vira um polígono de quatro ou
cinco pontos (Taboão da Serra, SP: 4; Olinda, PE: 6), bom para o mapa da UF e
inútil quando o município ocupa a tela inteira com as zonas eleitorais. Por
isso os municípios com mais de uma zona têm também o contorno em ``maxima``
(São Paulo: 1.157 pontos, 10,6 KB; Taboão da Serra: 74 pontos, 0,9 KB).

Certificado: o servidor ``servicodados.ibge.gov.br`` envia só o certificado
final, sem o intermediário (Sectigo Public Server Authentication CA DV R36,
verificado em 15/10/2026). Navegadores completam a cadeia sozinhos; o Python
não, e a conexão falha com ``unable to get local issuer certificate`` até o
intermediário estar no repositório de certificados da máquina.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from lumen_canonico.ufs import UFS
from lumen_ingestao.bronze import ArmazemBronze
from lumen_ingestao.cliente_http import ClienteHttp

from .feeds import substituir_arquivo

BASE_MALHAS = "https://servicodados.ibge.gov.br/api/v3/malhas"
BASE_LOCALIDADES = "https://servicodados.ibge.gov.br/api/v1/localidades"
QUALIDADES = ("minima", "intermediaria", "maxima")
FONTE_ID = "ibge_malhas"
DIR_CONTORNOS = "geo/mu"


class MalhaInvalida(ValueError):
    """A malha recebida não serve ao portal: HTTP diferente de 200 ou TopoJSON fora da estrutura esperada."""
    pass


def url_brasil_por_uf(qualidade: str = "minima") -> str:
    """URL da malha do Brasil com uma geometria por UF, na ``qualidade`` pedida."""
    return f"{BASE_MALHAS}/paises/BR?formato=application/json&intrarregiao=UF&qualidade={qualidade}"


def url_uf_por_municipio(codigo_uf: str, qualidade: str = "minima") -> str:
    """URL da malha de uma UF (código IBGE de 2 dígitos) com uma geometria por município."""
    return (f"{BASE_MALHAS}/estados/{codigo_uf}?formato=application/json&intrarregiao=municipio"
            f"&qualidade={qualidade}")


def url_municipio(codigo_ibge: str, qualidade: str = "maxima") -> str:
    """URL da malha de um município (código IBGE de 7 dígitos), na ``qualidade`` pedida."""
    return f"{BASE_MALHAS}/municipios/{codigo_ibge}?formato=application/json&qualidade={qualidade}"


def url_municipios_ibge() -> str:
    """URL da lista de municípios da API de localidades do IBGE, de onde vêm os nomes acentuados."""
    return f"{BASE_LOCALIDADES}/municipios"


def validar_topojson(conteudo: bytes | str | dict) -> dict:
    """Confere a estrutura mínima que o portal usa e devolve o objeto."""
    topo = json.loads(conteudo) if isinstance(conteudo, (bytes, str)) else conteudo
    if topo.get("type") != "Topology":
        raise MalhaInvalida("não é TopoJSON (type != Topology)")
    arcos = topo.get("arcs")
    objetos = topo.get("objects") or {}
    if not isinstance(arcos, list) or len(objetos) != 1:
        raise MalhaInvalida("TopoJSON sem arcos ou com mais de um objeto")
    colecao = next(iter(objetos.values()))
    geometrias = colecao.get("geometries") or []
    if not geometrias:
        raise MalhaInvalida("TopoJSON sem geometrias")
    n = len(arcos)
    for g in geometrias:
        if not (g.get("properties") or {}).get("codarea"):
            raise MalhaInvalida("geometria sem codarea")
        if g.get("type") not in ("Polygon", "MultiPolygon"):
            raise MalhaInvalida(f"geometria de tipo {g.get('type')}")
        aneis = g["arcs"] if g["type"] == "Polygon" else [a for p in g["arcs"] for a in p]
        for anel in aneis:
            for i in anel:
                if not (-n <= i < n):
                    raise MalhaInvalida("índice de arco fora da malha")
    return topo


def codigos_da_malha(topo: dict) -> list[str]:
    """Códigos ``codarea`` das geometrias de uma malha já validada, como texto e em ordem crescente."""
    colecao = next(iter(topo["objects"].values()))
    return sorted(str(g["properties"]["codarea"]) for g in colecao["geometries"])


def _gravar(destino: Path, conteudo: bytes) -> Path:
    """Grava ``conteudo`` em ``destino`` por troca atômica (``.tmp`` e ``os.replace``), criando o diretório.

    Quem lê o diretório dos feeds vê a malha anterior ou a nova, nunca um arquivo pela metade; com a
    malha aberta pelo servidor local (Windows), a troca espera e tenta de novo (``feeds.substituir_arquivo``).
    """
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_name(destino.name + ".tmp")
    tmp.write_bytes(conteudo)
    substituir_arquivo(tmp, destino)
    return destino


def baixar_malhas(cliente: ClienteHttp, raiz_feeds: Path | str, *, ufs: Iterable[str] | None = None,
                  qualidade: str = "minima", bronze: ArmazemBronze | None = None) -> list[Path]:
    """Baixa o Brasil por UF e cada UF por município. Devolve os arquivos gravados."""
    if qualidade not in QUALIDADES:
        raise ValueError(f"qualidade deve ser uma de {QUALIDADES}")
    raiz = Path(raiz_feeds) / "geo"
    pedidos = {s.upper() for s in ufs} if ufs else None
    alvos = [("br-uf.json", url_brasil_por_uf(qualidade))]
    for codigo, (sigla, _, _) in sorted(UFS.items()):
        if pedidos is None or sigla in pedidos:
            alvos.append((f"uf-{sigla.lower()}-mu.json", url_uf_por_municipio(codigo, qualidade)))
    gravados = []
    for nome, url in alvos:
        art = cliente.obter(url, {"Accept": "application/json"})
        if art.status_http != 200:
            raise MalhaInvalida(f"{url}: HTTP {art.status_http}")
        validar_topojson(art.conteudo)
        if bronze:
            bronze.guardar(art)
        gravados.append(_gravar(raiz / nome, art.conteudo))
    return gravados


def baixar_contornos(cliente: ClienteHttp, raiz_feeds: Path | str, codigos: Iterable[str], *,
                     qualidade: str = "maxima", bronze: ArmazemBronze | None = None) -> list[Path]:
    """Baixa o contorno de cada município (código IBGE) para ``geo/mu/<código>.json``. Devolve os gravados.

    São os bytes do IBGE, conferidos por ``validar_topojson`` e pelo código da única geometria.
    """
    if qualidade not in QUALIDADES:
        raise ValueError(f"qualidade deve ser uma de {QUALIDADES}")
    raiz = Path(raiz_feeds) / DIR_CONTORNOS
    gravados = []
    for codigo in sorted(set(codigos)):
        if not (codigo.isdigit() and len(codigo) == 7):
            raise ValueError(f"código IBGE de município inválido: {codigo!r}")
        url = url_municipio(codigo, qualidade)
        art = cliente.obter(url, {"Accept": "application/json"})
        if art.status_http != 200:
            raise MalhaInvalida(f"{url}: HTTP {art.status_http}")
        topo = validar_topojson(art.conteudo)
        if codigos_da_malha(topo) != [codigo]:
            raise MalhaInvalida(f"{url}: a malha não é só do município {codigo}")
        if bronze:
            bronze.guardar(art)
        gravados.append(_gravar(raiz / f"{codigo}.json", art.conteudo))
    return gravados
