"""Adaptadores do SICONFI (Tesouro Nacional), API de dados abertos.

Base: ``https://apidatalake.tesouro.gov.br/ords/siconfi/tt`` — sem cadastro.
Paginação ORDS por ``offset`` com ``hasMore``, até 5.000 itens por página.
O Tesouro recomenda cerca de uma requisição por segundo; o padrão aqui é 50
por minuto, abaixo disso.

Recursos usados:

``/entes``              cadastro dos 5.598 entes com código IBGE, CNPJ e
                         população (base do cadastro e do grupo de pares)
``/extrato_entregas``   o que cada ente entregou num exercício: é daqui que
                         sai a lista de ausentes (família I, RF-CF-01)
``/rreo``, ``/rgf``,
``/dca``                os demonstrativos em si (gasto por função, H-01)
"""

from __future__ import annotations

from typing import Iterable, Iterator

from ...portas import Janela, Periodicidade
from ._simples import FontePaginadaPorDeslocamento

BASE_SICONFI = "https://apidatalake.tesouro.gov.br/ords/siconfi/tt"
DISPOSITIVO_SICONFI = "LC 101/2000, arts. 48, 51, 52 e 55"


class FonteSiconfiEntes(FontePaginadaPorDeslocamento):
    """Cadastro de entes do SICONFI (``/entes``), com código IBGE, CNPJ e população."""

    fonte_id = "siconfi_entes"
    objetos = frozenset({"EnteFederativo"})
    periodicidade = Periodicidade.ANUAL
    dispositivo = DISPOSITIVO_SICONFI

    def __init__(self, cliente, base: str = BASE_SICONFI):
        """Usa ``BASE_SICONFI`` como base padrão."""
        super().__init__(cliente, base)

    def _consultas(self, janela: Janela) -> Iterator[tuple[str, str, dict, dict]]:
        """Uma única consulta a ``/entes``; a janela não se aplica a cadastro."""
        yield ("EnteFederativo", "/entes", {}, {})


class FonteSiconfiExtrato(FontePaginadaPorDeslocamento):
    """Extrato de entregas de cada ente informado, no exercício informado."""

    fonte_id = "siconfi_extrato"
    objetos = frozenset({"EntregaSiconfi"})
    periodicidade = Periodicidade.MENSAL
    dispositivo = DISPOSITIVO_SICONFI

    def __init__(self, cliente, entes: Iterable[str | int], exercicio: int, base: str = BASE_SICONFI):
        """Normaliza os códigos IBGE dos entes para texto e exige ao menos um."""
        self.entes = tuple(str(e) for e in entes)
        if not self.entes:
            raise ValueError("informe ao menos um ente (código IBGE)")
        self.exercicio = int(exercicio)
        super().__init__(cliente, base)

    def _consultas(self, janela: Janela) -> Iterator[tuple[str, str, dict, dict]]:
        """Uma consulta a ``/extrato_entregas`` por ente, no exercício informado."""
        for ente in self.entes:
            yield ("EntregaSiconfi", "/extrato_entregas",
                   {"id_ente": ente, "an_referencia": self.exercicio},
                   {"ente": ente, "exercicio": self.exercicio})


class FonteSiconfiDemonstrativo(FontePaginadaPorDeslocamento):
    """RREO, RGF ou DCA de um conjunto de entes, num exercício e período."""

    objetos = frozenset({"Demonstrativo"})
    periodicidade = Periodicidade.BIMESTRAL
    dispositivo = DISPOSITIVO_SICONFI
    RECURSOS = {"rreo", "rgf", "dca"}

    def __init__(self, cliente, recurso: str, entes: Iterable[str | int], exercicio: int, *,
                 periodo: int | None = None, tipo_demonstrativo: str | None = None,
                 anexo: str | None = None, poder: str | None = None,
                 periodicidade_rgf: str = "Q", base: str = BASE_SICONFI):
        """Valida o recurso e os parâmetros obrigatórios; o ``fonte_id`` passa a ser ``siconfi_<recurso>``.

        RREO e RGF exigem o período; a periodicidade do RGF é ``Q`` ou ``S`` (LRF, art. 63).
        """
        if recurso not in self.RECURSOS:
            raise ValueError(f"recurso é um de {sorted(self.RECURSOS)}")
        if recurso != "dca" and periodo is None:
            raise ValueError("RREO e RGF exigem o período")
        self.fonte_id = f"siconfi_{recurso}"
        self.recurso = recurso
        self.entes = tuple(str(e) for e in entes)
        self.exercicio = int(exercicio)
        self.periodo = periodo
        self.tipo_demonstrativo = tipo_demonstrativo
        self.anexo = anexo
        self.poder = poder
        if periodicidade_rgf not in ("Q", "S"):
            raise ValueError("periodicidade do RGF é Q (quadrimestral) ou S (semestral, LRF art. 63)")
        self.periodicidade_rgf = periodicidade_rgf
        super().__init__(cliente, base)

    def _consultas(self, janela: Janela) -> Iterator[tuple[str, str, dict, dict]]:
        """Uma consulta por ente, com os parâmetros que cada recurso exige.

        RREO leva período e tipo de demonstrativo; RGF leva também periodicidade e poder
        (``E`` por padrão); DCA, só o exercício. ``no_anexo`` entra quando informado.
        """
        for ente in self.entes:
            p: dict = {"an_exercicio": self.exercicio}
            if self.recurso == "rreo":
                p.update(nr_periodo=self.periodo,
                         co_tipo_demonstrativo=self.tipo_demonstrativo or "RREO")
            elif self.recurso == "rgf":
                p.update(in_periodicidade=self.periodicidade_rgf, nr_periodo=self.periodo,
                         co_tipo_demonstrativo=self.tipo_demonstrativo or "RGF",
                         co_poder=self.poder or "E")
            if self.anexo:
                p["no_anexo"] = self.anexo
            p["id_ente"] = ente
            yield ("Demonstrativo", f"/{self.recurso}", p, {"ente": ente, "recurso": self.recurso})
