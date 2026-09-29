from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from lumen_deteccao.parametros_legais import (
    ConfiguracaoInvalida,
    ParametroIndisponivel,
    ParametrosLegais,
)


@pytest.fixture(scope="module")
def params() -> ParametrosLegais:
    return ParametrosLegais.carregar()


def _toml(tmp_path: Path, texto: str) -> Path:
    arquivo = tmp_path / "p.toml"
    arquivo.write_text(texto, encoding="utf-8")
    return arquivo


# --------------------------------------------------------------------------
# Arquivo oficial do projeto
# --------------------------------------------------------------------------

def test_arquivo_oficial_carrega_sem_erro(params):
    assert "dispensa_compras_servicos" in params.chaves
    assert "dispensa_obras_engenharia" in params.chaves


def test_limites_de_dispensa_2026(params):
    """Valores do Decreto 12.807/2025, conferidos em 18/09/2026."""
    compras = params.obter("dispensa_compras_servicos", date(2026, 3, 15))
    obras = params.obter("dispensa_obras_engenharia", date(2026, 3, 15))
    assert compras.valor == Decimal("65492.11")
    assert obras.valor == Decimal("130984.20")
    assert compras.atualizado_por == "Decreto 12.807/2025"


def test_valor_e_decimal_exato_e_nao_float(params):
    p = params.obter("dispensa_compras_servicos", date(2026, 1, 1))
    assert isinstance(p.valor, Decimal)
    # a soma que a regra B-01 faz precisa ser exata ao centavo
    assert p.valor - Decimal("65492.10") == Decimal("0.01")


def test_primeiro_dia_de_vigencia_esta_coberto(params):
    assert params.obter("dispensa_compras_servicos", date(2026, 1, 1))


def test_ato_de_2025_nao_tem_parametro_e_a_regra_deve_calar(params):
    """Anos anteriores ainda não foram cadastrados. Por projeto, a regra não
    dispara em vez de usar o limite errado."""
    with pytest.raises(ParametroIndisponivel, match="nenhum valor cadastrado"):
        params.obter("dispensa_compras_servicos", date(2025, 12, 31))


def test_parametro_nao_verificado_e_recusado_por_padrao(params):
    with pytest.raises(ParametroIndisponivel, match="ainda não foi conferido"):
        params.obter("aditivo_acrescimo_geral", date(2026, 6, 1))


def test_parametro_nao_verificado_pode_ser_lido_explicitamente(params):
    p = params.obter("aditivo_acrescimo_geral", date(2026, 6, 1), aceitar_nao_verificado=True)
    assert p.valor == Decimal("0.25")
    assert p.verificado is False


def test_pendencias_de_verificacao_sao_listaveis(params):
    pendentes = {p.chave for p in params.pendentes_de_verificacao()}
    assert pendentes == {"aditivo_acrescimo_geral", "aditivo_acrescimo_reforma"}


def test_chave_desconhecida(params):
    with pytest.raises(ParametroIndisponivel):
        params.obter("limite_inventado", date(2026, 1, 1))


def test_citacao_para_acompanhar_o_indicio(params):
    p = params.obter("dispensa_compras_servicos", date(2026, 5, 1))
    assert p.citacao() == "Lei 14.133/2021, art. 75, II, valor fixado pelo Decreto 12.807/2025"


# --------------------------------------------------------------------------
# Sucessão de vigências
# --------------------------------------------------------------------------

SUCESSAO = """
[[limite]]
valor = "100.00"
vigente_de = 2025-01-01
vigente_ate = 2025-12-31
fundamento = "Lei X"
atualizado_por = "Decreto A"
verificado = true
verificado_em = 2026-01-01

[[limite]]
valor = "110.00"
vigente_de = 2026-01-01
fundamento = "Lei X"
atualizado_por = "Decreto B"
verificado = true
verificado_em = 2026-01-01
"""


def test_consulta_usa_a_data_do_ato_e_nao_a_de_hoje(tmp_path):
    params = ParametrosLegais.carregar(_toml(tmp_path, SUCESSAO))
    assert params.obter("limite", date(2025, 12, 31)).valor == Decimal("100.00")
    assert params.obter("limite", date(2026, 1, 1)).valor == Decimal("110.00")


def test_ordem_no_arquivo_nao_importa(tmp_path):
    blocos = SUCESSAO.strip().split("\n\n")
    invertido = "\n\n".join(reversed(blocos))
    params = ParametrosLegais.carregar(_toml(tmp_path, invertido))
    assert params.obter("limite", date(2025, 6, 1)).valor == Decimal("100.00")


# --------------------------------------------------------------------------
# Configuração inválida é rejeitada na carga
# --------------------------------------------------------------------------

def test_vigencias_sobrepostas_sao_rejeitadas(tmp_path):
    sobreposto = SUCESSAO.replace("vigente_ate = 2025-12-31", "vigente_ate = 2026-02-01")
    with pytest.raises(ConfiguracaoInvalida, match="sobrepostas"):
        ParametrosLegais.carregar(_toml(tmp_path, sobreposto))


def test_vigencia_anterior_sem_fim_e_rejeitada(tmp_path):
    sem_fim = SUCESSAO.replace("vigente_ate = 2025-12-31\n", "")
    with pytest.raises(ConfiguracaoInvalida, match="sobrepostas"):
        ParametrosLegais.carregar(_toml(tmp_path, sem_fim))


def test_valor_sem_aspas_e_rejeitado(tmp_path):
    """65492.11 sem aspas viraria float impreciso antes de chegar ao Decimal."""
    com_float = SUCESSAO.replace('valor = "100.00"', "valor = 100.00")
    with pytest.raises(ConfiguracaoInvalida, match="aspas"):
        ParametrosLegais.carregar(_toml(tmp_path, com_float))


def test_verificado_sem_data_e_rejeitado(tmp_path):
    sem_data = SUCESSAO.replace("verificado_em = 2026-01-01\n", "", 1)
    with pytest.raises(ConfiguracaoInvalida, match="verificado_em"):
        ParametrosLegais.carregar(_toml(tmp_path, sem_data))


def test_campo_obrigatorio_ausente_e_rejeitado(tmp_path):
    sem_fundamento = SUCESSAO.replace('fundamento = "Lei X"\n', "", 1)
    with pytest.raises(ConfiguracaoInvalida, match="fundamento"):
        ParametrosLegais.carregar(_toml(tmp_path, sem_fundamento))


def test_fim_antes_do_inicio_e_rejeitado(tmp_path):
    invertido = SUCESSAO.replace("vigente_ate = 2025-12-31", "vigente_ate = 2024-12-31")
    with pytest.raises(ConfiguracaoInvalida, match="anterior"):
        ParametrosLegais.carregar(_toml(tmp_path, invertido))
