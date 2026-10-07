"""Etapas do pipeline como funções sobre diretórios (futuros ativos do Dagster)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Iterable

from lumen_ingestao.adaptadores.api.ibge import FonteIbgeLocalidades, FonteIbgePopulacao
from lumen_ingestao.adaptadores.api.pncp import (
    MODALIDADES_PNCP,
    FontePncpAtas,
    FontePncpContratacoes,
    FontePncpContratos,
)
from lumen_ingestao.adaptadores.api.siconfi import FonteSiconfiEntes, FonteSiconfiExtrato
from lumen_ingestao.bronze import ArmazemBronze, ArmazemBronzeLocal, RegistroColeta
from lumen_ingestao.cliente_http import ClienteHttp
from lumen_ingestao.coleta_http import user_agent_lumen
from lumen_ingestao.portas import Janela, ResumoColeta, coletar_janela
from lumen_normalizacao import ibge as n_ibge
from lumen_normalizacao import pncp as n_pncp
from lumen_normalizacao import siconfi as n_siconfi
from lumen_normalizacao.qualidade import ResultadoNormalizacao
from lumen_normalizacao.silver import EscritorSilver

from .configuracao import VERSAO_LUMEN, Configuracao

log = logging.getLogger("lumen.pipeline")


def cliente(cfg: Configuracao, fonte_id: str) -> ClienteHttp:
    """Cliente HTTP da fonte, com o User-Agent do Lumen (versão e contato) e o limite de requisições dela."""
    return ClienteHttp(fonte_id, user_agent=user_agent_lumen(VERSAO_LUMEN, cfg.contato),
                       rpm=cfg.rpm(fonte_id))


# ------------------------------------------------------------------ coleta

FABRICAS: dict[str, Callable[..., object]] = {
    "pncp_contratacoes": lambda c, **kw: FontePncpContratacoes(c, modo="publicacao", **kw),
    "pncp_contratacoes_atualizacao": lambda c, **kw: FontePncpContratacoes(c, modo="atualizacao", **kw),
    "pncp_contratos": lambda c, **kw: FontePncpContratos(c, modo="publicacao", **kw),
    "pncp_contratos_atualizacao": lambda c, **kw: FontePncpContratos(c, modo="atualizacao", **kw),
    "pncp_atas": lambda c, **kw: FontePncpAtas(c, modo="vigencia", **kw),
    "pncp_atas_atualizacao": lambda c, **kw: FontePncpAtas(c, modo="atualizacao", **kw),
    "ibge_localidades": lambda c, **kw: FonteIbgeLocalidades(c, **kw),
    "ibge_populacao": lambda c, **kw: FonteIbgePopulacao(c, **kw),
    "siconfi_entes": lambda c, **kw: FonteSiconfiEntes(c, **kw),
    "siconfi_extrato": lambda c, **kw: FonteSiconfiExtrato(c, **kw),
}


def coletar(cfg: Configuracao, fonte_id: str, janela: Janela, armazem: ArmazemBronze | None = None,
            **opcoes) -> ResumoColeta:
    """Coleta a janela de uma fonte para o bronze e devolve o resumo da coleta.

    A fonte é criada pela fábrica de ``FABRICAS``, com as ``opcoes`` específicas dela (modalidades, entes,
    exercício). Sem ``armazem``, usa o bronze local da configuração.
    """
    if fonte_id not in FABRICAS:
        raise KeyError(f"fonte desconhecida: {fonte_id}. Conhecidas: {sorted(FABRICAS)}")
    armazem = armazem or ArmazemBronzeLocal(cfg.bronze)
    fonte = FABRICAS[fonte_id](cliente(cfg, fonte_id), **opcoes)
    resumo = coletar_janela(fonte, janela, armazem)
    log.info("coleta_concluida", extra={"fonte": fonte_id, "listados": resumo.listados,
                                        "guardados": len(resumo.guardados), "falhas": len(resumo.falhas),
                                        "conteudos_novos": resumo.conteudos_novos})
    return resumo


# ------------------------------------------------------------------ normalização

def _normalizador_de(registro: RegistroColeta) -> Callable[[bytes, str], ResultadoNormalizacao] | None:
    """Escolhe o normalizador do artefato pela fonte e, no IBGE, pela URL pedida; None se não houver.

    Devolve uma função que recebe só o conteúdo, com a proveniência (fonte e id do registro no bronze) já
    aplicada.
    """
    f = registro.fonte_id
    url = registro.url_solicitada
    kw = lambda: dict(fonte_id=f, documento_fonte_id=registro.registro_id)  # noqa: E731
    if f.startswith("pncp_contratacoes"):
        return lambda c: n_pncp.normalizar_contratacoes(c, **kw())
    if f.startswith("pncp_contratos"):
        return lambda c: n_pncp.normalizar_contratos(c, **kw())
    if f.startswith("pncp_atas"):
        return lambda c: n_pncp.normalizar_atas(c, **kw())
    if f == "ibge_localidades" and "/estados" in url:
        return lambda c: n_ibge.normalizar_estados(c, **kw())
    if f == "ibge_localidades" and "/municipios" in url:
        return lambda c: n_ibge.normalizar_municipios(c, **kw())
    if f == "siconfi_entes":
        return lambda c: n_siconfi.normalizar_entes(c, **kw())
    if f == "siconfi_extrato":
        return lambda c: n_siconfi.normalizar_extrato(c, **kw())
    return None


VERSOES = {"pncp": n_pncp.VERSAO_NORMALIZADOR, "ibge": n_ibge.VERSAO_NORMALIZADOR,
           "siconfi": n_siconfi.VERSAO_NORMALIZADOR}


@dataclass
class ResumoNormalizacao:
    """Contagens de uma rodada de normalização.

    Artefatos processados e ignorados, registros gravados, entradas de quarentena e, em ``por_fonte``,
    quantos artefatos de cada fonte foram processados.
    """

    artefatos: int = 0
    ignorados: int = 0
    registros: int = 0
    quarentena: int = 0
    por_fonte: dict[str, int] = field(default_factory=dict)


def normalizar(cfg: Configuracao, fontes: Iterable[str] | None = None,
               armazem: ArmazemBronzeLocal | None = None) -> ResumoNormalizacao:
    """Reprocessa o bronze inteiro (ou as fontes pedidas) para a silver.

    É idempotente (RF-NO-11) e pode ser rodada a qualquer momento: apagar a
    silver e rodar de novo reconstrói tudo sem tocar nas fontes (RF-NO-12).
    Respostas de erro (4xx/5xx) ficam no bronze como prova e não geram linha.
    """
    armazem = armazem or ArmazemBronzeLocal(cfg.bronze)
    filtro = set(fontes) if fontes else None
    resumo = ResumoNormalizacao()
    for registro in armazem.listar_registros():
        if filtro and registro.fonte_id not in filtro:
            continue
        normalizador = _normalizador_de(registro)
        if normalizador is None or registro.status_http not in (200, 204):
            resumo.ignorados += 1
            continue
        _, conteudo = armazem.recuperar(registro.registro_id)  # hash reconferido aqui
        resultado = normalizador(conteudo)
        familia = registro.fonte_id.split("_", 1)[0]
        escritor = EscritorSilver(cfg.silver, VERSOES.get(familia, "?"))
        escritor.gravar(registro.registro_id, resultado.registros, coletado_em=registro.coletado_em)
        escritor.gravar_quarentena(registro.fonte_id, registro.registro_id, resultado.quarentena)
        resumo.artefatos += 1
        resumo.registros += len(resultado.registros)
        resumo.quarentena += len(resultado.quarentena)
        resumo.por_fonte[registro.fonte_id] = resumo.por_fonte.get(registro.fonte_id, 0) + 1
    return resumo


def janela_de(de: str, ate: str | None = None) -> Janela:
    """Janela de coleta a partir de datas ``AAAA-MM-DD``; sem ``ate``, a janela é só o dia ``de``."""
    inicio = date.fromisoformat(de)
    return Janela(inicio, date.fromisoformat(ate) if ate else inicio)


__all__ = ["coletar", "normalizar", "janela_de", "cliente", "FABRICAS", "MODALIDADES_PNCP"]
