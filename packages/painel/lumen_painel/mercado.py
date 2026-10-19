"""Preço de revenda da ANP por semana, município e UF, para a comparação de mercado no modal (ADR-037).

A regra A-05 (ADR-027) compara o preço pago em combustível e gás de cozinha com o preço de revenda que a ANP
pesquisa toda semana, posto a posto. O portal faz essa comparação no modal da contratação, item a item, e
precisa da distribuição do preço na semana e no lugar da compra.

``coletar`` lê a página do levantamento semanal, baixa só as planilhas das semanas que o estado ainda não tem
(desde ``INICIO_PADRAO``), lê com o leitor do ``lumen_mercado.anp`` e guarda, por semana, produto e lugar
(a UF e cada município), a quantidade de coletas e o mínimo, os quartis, a mediana e o máximo
(``anp-semanas.json.gz``). Uma semana que falha fica para a próxima execução; as outras seguem.

``publicar`` grava um arquivo por UF e ano (``mercado/anp/uf-<sigla>-<ano>.json``, pelo início da semana), com
os municípios pelo código IBGE (o nome da ANP casado com o cadastro de entes). O portal lê o arquivo da UF da
unidade compradora no ano da compra.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Callable, Iterable

from lumen_mercado import anp
from lumen_mercado.referencia import quantil

from lumen_ingestao.cliente_http import ClienteHttp
from lumen_ingestao.coleta_http import ErroColeta

from .cadastro import Cadastro
from .comum import UFS, gravar_json, ler_json, tipo_do_ente

ARQUIVO_ESTADO = "anp-semanas.json.gz"
VERSAO_ESTADO = 1
FONTE_ID = anp.FONTE_ID
# O painel de contratações começa em 2025; a comparação precisa das semanas desde então.
INICIO_PADRAO = date(2025, 1, 1)
# Quantas planilhas uma execução baixa, no máximo: a primeira carga leva várias execuções, sem estourar o prazo.
MAXIMO_SEMANAS = 40
COLUNAS_ESTATISTICA = ("n", "minimo", "q1", "mediana", "q3", "maximo")


@dataclass
class ResumoMercado:
    """O que a coleta fez: semanas na página, já guardadas, lidas agora, que falharam, e a falha geral."""

    na_pagina: int = 0
    guardadas: int = 0
    lidas: list[str] = field(default_factory=list)
    falhas: dict[str, str] = field(default_factory=dict)
    falha: str | None = None

    def para_json(self) -> dict:
        """Resumo para imprimir na linha de comando."""
        return {"na_pagina": self.na_pagina, "guardadas": self.guardadas, "lidas": self.lidas,
                "falhas": self.falhas, "falha": self.falha}


def ler_estado(estado: Path | str) -> dict:
    """O estado gravado, ou um estado vazio na versão atual."""
    caminho = Path(estado) / ARQUIVO_ESTADO
    if not caminho.exists() or caminho.stat().st_size == 0:
        return {"versao": VERSAO_ESTADO, "semanas": {}}
    dados = ler_json(caminho)
    if dados.get("versao") != VERSAO_ESTADO:
        raise ValueError(f"{caminho}: versão {dados.get('versao')!r} do estado da ANP não suportada")
    return dados


def estatistica(valores: list[Decimal]) -> list:
    """``[n, mínimo, 1º quartil, mediana, 3º quartil, máximo]``, em reais com três casas (como a ANP publica)."""
    v = sorted(valores)

    def r(x: Decimal) -> float:
        return float(round(x, 3))

    return [len(v), r(v[0]), r(quantil(v, "0.25")), r(quantil(v, "0.5")), r(quantil(v, "0.75")), r(v[-1])]


def resumir_semana(coletas: Iterable[anp.Coleta]) -> dict:
    """As coletas de uma planilha agrupadas por produto e lugar: ``{produto: {"UF": [...], "UF/MUNICÍPIO": [...]}}``."""
    grupos: dict[str, dict[str, list[Decimal]]] = {}
    for c in coletas:
        g = grupos.setdefault(c.produto, {})
        g.setdefault(c.uf, []).append(c.valor)
        g.setdefault(f"{c.uf}/{anp.chave_municipio(c.municipio)}", []).append(c.valor)
    return {produto: {lugar: estatistica(v) for lugar, v in sorted(lugares.items())}
            for produto, lugares in sorted(grupos.items())}


def coletar(cliente: ClienteHttp, estado: Path | str, *, inicio: date = INICIO_PADRAO,
            maximo: int = MAXIMO_SEMANAS, agora: datetime | None = None) -> ResumoMercado:
    """Baixa as planilhas semanais que faltam no estado (as mais recentes primeiro) e grava o estado."""
    instante = (agora or datetime.now(timezone.utc)).isoformat(timespec="seconds")
    dados = ler_estado(estado)
    semanas_estado: dict = dados.setdefault("semanas", {})
    resumo = ResumoMercado()
    try:
        pagina = cliente.obter(anp.PAGINA_SEMANAS, {"Accept": "text/html"})
        if pagina.status_http != 200:
            raise ErroColeta(f"{anp.PAGINA_SEMANAS} respondeu {pagina.status_http}")
        semanas = anp.links_semanais(pagina.conteudo.decode("utf-8", errors="replace"),
                                     pagina.url_efetiva or anp.PAGINA_SEMANAS)
        if not semanas:
            raise ErroColeta("nenhuma planilha semanal na página do levantamento da ANP")
        resumo.na_pagina = len(semanas)
        faltam = sorted((s for s in semanas if s.inicio >= inicio and s.inicio.isoformat() not in semanas_estado),
                        key=lambda s: s.inicio, reverse=True)
        for s in faltam[:maximo]:
            chave = s.inicio.isoformat()
            try:
                artefato = cliente.obter(s.url, {"Accept": "application/octet-stream"})
                if artefato.status_http != 200:
                    raise ErroColeta(f"respondeu {artefato.status_http}")
                leitura = anp.ResumoLeitura()
                produtos = resumir_semana(anp.ler_bytes(artefato.conteudo, leitura))
                if not produtos:
                    raise ErroColeta("planilha sem nenhuma coleta aproveitada")
                semanas_estado[chave] = {"fim": s.fim.isoformat(), "url": s.url, "coletado_em": instante,
                                         "coletas": leitura.aproveitadas, "descartadas": dict(leitura.descartadas),
                                         "produtos": produtos}
                resumo.lidas.append(chave)
            except (ErroColeta, ValueError) as erro:
                resumo.falhas[chave] = f"{type(erro).__name__}: {erro}"
        dados["conferido_em"] = instante
        if resumo.falhas:
            dados["ultima_falha"] = {"em": instante, "semanas": resumo.falhas}
        else:
            dados.pop("ultima_falha", None)
    except (ErroColeta, ValueError) as erro:
        resumo.falha = f"{type(erro).__name__}: {erro}"
        dados["ultima_falha"] = {"em": instante, "motivo": resumo.falha}
    resumo.guardadas = len(semanas_estado)
    Path(estado).mkdir(parents=True, exist_ok=True)
    gravar_json(Path(estado) / ARQUIVO_ESTADO, dados, comprimir=True)
    return resumo


def _sem_espaco(lugar: str) -> str:
    """``UF/NOME`` sem os espaços do nome: ``SANT ANA DO LIVRAMENTO`` (IBGE) e ``SANTANA DO LIVRAMENTO`` (ANP)."""
    return lugar.replace(" ", "")


def indice_municipios(cadastro: Cadastro) -> dict[str, str]:
    """``UF/NOME`` (o nome como a ANP o escreve, por ``anp.chave_municipio``) → código IBGE do município.

    Cada nome entra também sem espaços, para as grafias que só diferem no apóstrofo ou na separação.
    """
    indice: dict[str, str] = {}
    for codigo, e in cadastro.entes.items():
        if tipo_do_ente(codigo) == "municipio" and e.uf:
            lugar = f"{e.uf.upper()}/{anp.chave_municipio(e.nome)}"
            indice[lugar] = codigo
            indice.setdefault(_sem_espaco(lugar), codigo)
    return indice


def montar(dados: dict, cadastro: Cadastro, *, gerado_em: str) -> tuple[dict[str, dict], list[str]]:
    """Os arquivos por UF e ano e os municípios da ANP que o cadastro não reconheceu (``UF/NOME``)."""
    indice = indice_municipios(cadastro)
    semanas = sorted(dados.get("semanas", {}).items())
    arquivos: dict[str, dict] = {}
    sem_codigo: set[str] = set()
    por_ano: dict[str, list[tuple[str, dict]]] = {}
    for inicio, semana in semanas:
        por_ano.setdefault(inicio[:4], []).append((inicio, semana))
    for ano, do_ano in sorted(por_ano.items()):
        _montar_ano(ano, do_ano, indice, arquivos, sem_codigo, gerado_em)
    return dict(sorted(arquivos.items())), sorted(sem_codigo)


def _montar_ano(ano: str, semanas: list[tuple[str, dict]], indice: dict[str, str], arquivos: dict[str, dict],
                sem_codigo: set[str], gerado_em: str) -> None:
    """Acrescenta a ``arquivos`` os arquivos das UFs no ano, com as semanas dele."""
    for i, (_, semana) in enumerate(semanas):
        for produto, lugares in semana["produtos"].items():
            for lugar, est in lugares.items():
                uf, _, municipio = lugar.partition("/")
                if uf not in UFS.values():
                    continue
                arquivo = arquivos.setdefault(f"mercado/anp/uf-{uf.lower()}-{ano}.json", {
                    "versao": 1, "tipo": "anp-precos", "uf": uf, "ano": int(ano), "gerado_em": gerado_em,
                    "fonte": "ANP, levantamento semanal de preços de combustíveis e GLP (revenda, posto a posto)",
                    "pagina": anp.PAGINA_SEMANAS, "colunas": ["semana", *COLUNAS_ESTATISTICA],
                    "semanas": [[s, d["fim"], d["url"]] for s, d in semanas], "produtos": {}})
                p = arquivo["produtos"].setdefault(produto, {"uf": [], "municipios": {}})
                if not municipio:
                    p["uf"].append([i, *est])
                    continue
                codigo = indice.get(lugar) or indice.get(_sem_espaco(lugar))
                if codigo is None:
                    sem_codigo.add(lugar)
                    continue
                p["municipios"].setdefault(codigo, []).append([i, *est])


def publicar(estado: Path | str, cadastro: Cadastro, gravar: Callable[[str, dict], None], *, gerado_em: str) -> dict:
    """Grava os arquivos por UF com ``gravar`` e devolve o resumo; sem semanas no estado, não grava nada."""
    dados = ler_estado(estado)
    arquivos, sem_codigo = montar(dados, cadastro, gerado_em=gerado_em)
    for nome, conteudo in arquivos.items():
        gravar(nome, conteudo)
    semanas = sorted(dados.get("semanas", {}))
    return {"semanas": len(semanas), "de": semanas[0] if semanas else None, "ate": semanas[-1] if semanas else None,
            "arquivos": len(arquivos), "municipios_sem_codigo": len(sem_codigo), "exemplos_sem_codigo": sem_codigo[:10]}
