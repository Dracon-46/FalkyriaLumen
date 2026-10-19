"""Portais de transparência de cada ente pelo PNTP, para a visão 360 do portal (ADR-032, ADR-035).

O Programa Nacional de Transparência Pública (tribunais de contas e Atricon) avalia, a cada ciclo, o portal de
transparência de cada entidade: a prefeitura e a câmara de cada município, os poderes estaduais e federais,
consórcios e estatais. A planilha do ciclo traz o índice, o percentual dos critérios essenciais, o nível e o
endereço do portal.

``coletar`` lê a lista de ciclos do Radar da Transparência e, do ciclo mais recente, só a planilha de dentro
do ZIP (por ``Range``, ADR-032), se o ZIP mudou desde a última coleta; normaliza com o mesmo normalizador da
silver e guarda as entidades no estado (``transparencia-pntp.json.gz``). ``publicar`` grava um arquivo por
UF (``transparencia/uf-<sigla>.json``, e ``transparencia/uniao.json``), com as entidades agrupadas pelo
ente, que o portal lê na página do ente.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from lumen_ingestao.adaptadores.api.pntp import BASE_RADAR, ciclos_publicados, membro_de_avaliacoes
from lumen_ingestao.cliente_http import ClienteHttp
from lumen_ingestao.coleta_http import ErroColeta
from lumen_ingestao.zip_remoto import baixar_membro
from lumen_normalizacao.pntp import normalizar_avaliacoes

from .comum import UFS, gravar_json, ler_json

ARQUIVO_ESTADO = "transparencia-pntp.json.gz"
VERSAO_ESTADO = 1
FONTE_ID = "pntp_avaliacoes"
URL_RADAR = f"{BASE_RADAR}/downloads.html"
COLUNAS = ("ente", "codigo_entidade", "entidade", "poder", "esfera", "avaliada", "indice", "essenciais",
           "nivel", "nivel_anterior", "link", "data_envio")


def url_zip(ciclo: int) -> str:
    """Endereço do ZIP de dados do ciclo no Radar da Transparência."""
    return f"{BASE_RADAR}/dados/dados_pntp_{ciclo}.zip"


@dataclass
class ResumoTransparencia:
    """O que a coleta fez: ciclo lido (ou mantido), entidades, quarentena e falha."""

    ciclo: int | None = None
    entidades: int = 0
    quarentena: int = 0
    mantido: bool = False
    falha: str | None = None

    def para_json(self) -> dict:
        """Resumo para imprimir na linha de comando."""
        return {"ciclo": self.ciclo, "entidades": self.entidades, "quarentena": self.quarentena,
                "mantido": self.mantido, "falha": self.falha}


def ler_estado(estado: Path | str) -> dict:
    """O estado gravado, ou um estado vazio na versão atual."""
    caminho = Path(estado) / ARQUIVO_ESTADO
    if not caminho.exists() or caminho.stat().st_size == 0:
        return {"versao": VERSAO_ESTADO, "ciclo": None}
    dados = ler_json(caminho)
    if dados.get("versao") != VERSAO_ESTADO:
        raise ValueError(f"{caminho}: versão {dados.get('versao')!r} do estado da transparência não suportada")
    return dados


def _linha(r) -> list:
    """Uma entidade normalizada como a linha compacta do estado (``COLUNAS``)."""
    return [r.ente_codigo_ibge, r.codigo_entidade, r.entidade, r.poder,
            r.esfera.value if r.esfera else None, r.avaliada,
            float(r.indice) if r.indice is not None else None,
            float(r.percentual_essenciais) if r.percentual_essenciais is not None else None,
            r.nivel, r.nivel_anterior, r.link_portal, r.data_envio.isoformat() if r.data_envio else None]


def coletar(cliente: ClienteHttp, estado: Path | str, *, baixar: Callable = baixar_membro,
            agora: datetime | None = None) -> ResumoTransparencia:
    """Lê o ciclo mais recente do PNTP e grava o estado; falha mantém o ciclo que o estado já tinha."""
    instante = (agora or datetime.now(timezone.utc)).isoformat(timespec="seconds")
    dados = ler_estado(estado)
    resumo = ResumoTransparencia()
    try:
        artefato = cliente.obter(URL_RADAR, {"Accept": "text/html"})
        if artefato.status_http != 200:
            raise ErroColeta(f"{URL_RADAR} respondeu {artefato.status_http}")
        ciclos = ciclos_publicados(artefato.conteudo.decode("utf-8", errors="replace"))
        if not ciclos:
            raise ErroColeta("nenhum ciclo do PNTP na página de downloads")
        ciclo = max(ciclos)
        url = url_zip(ciclo)
        membro = baixar(cliente, url, membro_de_avaliacoes(ciclo))
        resumo.ciclo = ciclo
        marca = membro.ultima_modificacao or membro.etag
        if dados.get("ciclo") == ciclo and marca and dados.get("marca") == marca:
            resumo.mantido = True
            resumo.entidades = len(dados.get("entidades") or [])
        else:
            resultado = normalizar_avaliacoes(membro.conteudo, ciclo=ciclo, fonte_id=FONTE_ID, documento_fonte_id=url)
            if not resultado.registros:
                raise ErroColeta(f"planilha do ciclo {ciclo} sem nenhuma entidade normalizada "
                                 f"({len(resultado.quarentena)} na quarentena)")
            dados = {"versao": VERSAO_ESTADO, "ciclo": ciclo, "url": url, "marca": marca, "coletado_em": instante,
                     "colunas": list(COLUNAS), "quarentena": len(resultado.quarentena),
                     "entidades": [_linha(r) for r in resultado.registros]}
            resumo.entidades = len(dados["entidades"])
            resumo.quarentena = len(resultado.quarentena)
        dados["conferido_em"] = instante
        dados.pop("ultima_falha", None)
    except (ErroColeta, ValueError) as erro:
        resumo.falha = f"{type(erro).__name__}: {erro}"
        dados["ultima_falha"] = {"em": instante, "motivo": resumo.falha}
    Path(estado).mkdir(parents=True, exist_ok=True)
    gravar_json(Path(estado) / ARQUIVO_ESTADO, dados, comprimir=True)
    return resumo


@dataclass
class Publicacao:
    """Os arquivos por UF: nome do arquivo → conteúdo."""

    arquivos: dict[str, dict] = field(default_factory=dict)


def arquivo_do_ente(codigo: str) -> str:
    """Em que arquivo está o ente: ``transparencia/uniao.json`` para a União, senão o da UF do ente."""
    if codigo == "1":
        return "transparencia/uniao.json"
    return f"transparencia/uf-{UFS[codigo[:2]].lower()}.json"


def montar(dados: dict, *, gerado_em: str) -> Publicacao:
    """Agrupa as entidades do estado por ente e as divide nos arquivos por UF."""
    pub = Publicacao()
    if not dados.get("entidades"):
        return pub
    colunas = dados["colunas"]
    for linha in dados["entidades"]:
        e = dict(zip(colunas, linha))
        codigo = e.pop("ente")
        if not codigo or (codigo != "1" and codigo[:2] not in UFS):
            continue
        nome = arquivo_do_ente(codigo)
        arquivo = pub.arquivos.setdefault(nome, {
            "versao": 1, "tipo": "transparencia", "gerado_em": gerado_em, "ciclo": dados["ciclo"],
            "fonte": "Programa Nacional de Transparência Pública (tribunais de contas e Atricon)",
            "url": dados.get("url"), "coletado_em": dados.get("coletado_em"), "entes": {}})
        arquivo["entes"].setdefault(codigo, []).append(e)
    for arquivo in pub.arquivos.values():
        for lista in arquivo["entes"].values():
            lista.sort(key=lambda x: (x["poder"] or "", x["entidade"]))
    return pub


def publicar(estado: Path | str, gravar: Callable[[str, dict], None], *, gerado_em: str) -> dict:
    """Grava os arquivos por UF com ``gravar`` e devolve o resumo; sem estado, não grava nada."""
    dados = ler_estado(estado)
    pub = montar(dados, gerado_em=gerado_em)
    for nome, conteudo in sorted(pub.arquivos.items()):
        gravar(nome, conteudo)
    return {"ciclo": dados.get("ciclo"), "arquivos": len(pub.arquivos),
            "entes": sum(len(a["entes"]) for a in pub.arquivos.values())}
