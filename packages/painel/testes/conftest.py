"""Apoio dos testes dos painéis: silver montada com as respostas reais do PNCP e do SICONFI das fixtures.

Os testes recebem as funções pela fixture ``apoio`` (o modo de importação da suíte não deixa um teste
importar o ``conftest`` vizinho).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from lumen_normalizacao import pncp as n_pncp
from lumen_normalizacao import siconfi as n_siconfi
from lumen_normalizacao.silver import EscritorSilver
from lumen_orquestracao.configuracao import Configuracao

FIXTURES = Path(__file__).resolve().parents[3] / "testes" / "fixtures"


def silver_pncp(raiz: Path) -> Path:
    """Silver com uma página de dispensas e uma de contratos de 01/09/2026 (respostas reais do PNCP)."""
    for i, (arquivo, funcao) in enumerate((("contratacoes_publicacao_dispensa_20260901_p1.json",
                                            n_pncp.normalizar_contratacoes),
                                           ("contratacoes_publicacao_pregao_20260901_p1.json",
                                            n_pncp.normalizar_contratacoes),
                                           ("contratos_20260901_p1.json", n_pncp.normalizar_contratos))):
        r = funcao((FIXTURES / "pncp" / arquivo).read_bytes(), fonte_id="pncp_x", documento_fonte_id=f"pncp{i}")
        EscritorSilver(raiz, "pncp-1").gravar(f"pncp{i}", r.registros, coletado_em="2026-09-02T10:00:00Z")
    return raiz


def silver_siconfi(raiz: Path) -> Path:
    """Silver com o cadastro de entes de amostra e o extrato de 2025 de São Sepé (RS)."""
    for i, (arquivo, funcao) in enumerate((("entes_amostra.json", n_siconfi.normalizar_entes),
                                           ("extrato_entregas_4319604_2025.json", n_siconfi.normalizar_extrato))):
        r = funcao((FIXTURES / "siconfi" / arquivo).read_bytes(), fonte_id="siconfi_x", documento_fonte_id=f"sic{i}")
        EscritorSilver(raiz, "siconfi-1").gravar(f"sic{i}", r.registros, coletado_em="2026-09-02T10:00:00Z")
    return raiz


@pytest.fixture
def apoio():
    """As funções de apoio, para os testes chamarem."""
    return SimpleNamespace(silver_pncp=silver_pncp, silver_siconfi=silver_siconfi, FIXTURES=FIXTURES)


@pytest.fixture
def cfg(tmp_path):
    """Configuração do pipeline com contato e raiz temporária."""
    return Configuracao(contato="c@exemplo.org", raiz_dados=tmp_path / "dados")
