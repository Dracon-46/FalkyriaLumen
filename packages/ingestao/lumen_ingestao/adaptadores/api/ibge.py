"""Adaptadores do IBGE: cadastro de UFs e municípios e população estimada.

- Localidades: ``https://servicodados.ibge.gov.br/api/v1/localidades``. A
  visão ``nivelado`` traz município, microrregião, região imediata e UF numa
  linha só, que é o formato que a normalização precisa.
- População: agregado 6579 do SIDRA (estimativas anuais), variável 9324
  ("População residente estimada"). ``periodos/-1`` é o último disponível.

Ambas sem autenticação. O IBGE contava 5.571 municípios em 05/10/2026.
"""

from __future__ import annotations

from typing import Iterator

from ...portas import Janela, Periodicidade
from ._simples import FonteListaFixa

BASE_IBGE = "https://servicodados.ibge.gov.br/api"


class FonteIbgeLocalidades(FonteListaFixa):
    """Cadastro de UFs e municípios do IBGE (``/v1/localidades``), em duas consultas fixas."""

    fonte_id = "ibge_localidades"
    objetos = frozenset({"EnteFederativo"})
    periodicidade = Periodicidade.ANUAL
    dispositivo = "Lei 5.878/1973 (IBGE); Decreto 8.777/2016 (dados abertos)"

    def __init__(self, cliente, base: str = BASE_IBGE):
        """Usa ``BASE_IBGE`` como base padrão."""
        super().__init__(cliente, base)

    def _consultas(self, janela: Janela) -> Iterator[tuple[str, str, dict, dict]]:
        """Estados por nome e municípios na visão ``nivelado``; a janela não se aplica a cadastro."""
        yield ("EnteFederativo", "/v1/localidades/estados", {"orderBy": "nome"}, {"nivel": "uf"})
        yield ("EnteFederativo", "/v1/localidades/municipios", {"view": "nivelado"}, {"nivel": "municipio"})


class FonteIbgePopulacao(FonteListaFixa):
    """População residente estimada (SIDRA, agregado 6579, variável 9324) por UF e por município."""

    fonte_id = "ibge_populacao"
    objetos = frozenset({"PopulacaoEstimada"})
    periodicidade = Periodicidade.ANUAL
    dispositivo = "Lei 8.443/1992, art. 102 (estimativas populacionais do IBGE)"

    def __init__(self, cliente, *, periodo: str = "-1", base: str = BASE_IBGE):
        """Aceita como período um ano (``AAAA``) ou ``-1``, o mais recente disponível."""
        if periodo != "-1" and not (periodo.isdigit() and len(periodo) == 4):
            raise ValueError("periodo é um ano (AAAA) ou '-1' para o mais recente")
        self.periodo = periodo
        super().__init__(cliente, base)

    def _consultas(self, janela: Janela) -> Iterator[tuple[str, str, dict, dict]]:
        """Uma consulta para todas as UFs (``N3``) e outra para todos os municípios (``N6``) do período."""
        caminho = f"/v3/agregados/6579/periodos/{self.periodo}/variaveis/9324"
        yield ("PopulacaoEstimada", caminho, {"localidades": "N3[all]"}, {"nivel": "uf"})
        yield ("PopulacaoEstimada", caminho, {"localidades": "N6[all]"}, {"nivel": "municipio"})
