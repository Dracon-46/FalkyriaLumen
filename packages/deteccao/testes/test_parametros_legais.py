"""Parâmetros legais datados: valores conferidos no texto oficial, vigência contínua desde a lei e recusa do não verificado."""

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


LIMITES_HISTORICOS = [
    # (data do ato, art. 75 I, art. 75 II, § 7º, norma) — anexos lidos no Planalto
    (date(2021, 4, 1), "100000.00", "50000.00", "8000.00", "Lei 14.133/2021"),
    (date(2021, 12, 31), "100000.00", "50000.00", "8000.00", "Lei 14.133/2021"),
    (date(2022, 1, 1), "108040.82", "54020.41", "8643.27", "Decreto 10.922/2021"),
    (date(2023, 7, 1), "114416.65", "57208.33", "9153.34", "Decreto 11.317/2022"),
    (date(2024, 12, 31), "119812.02", "59906.02", "9584.97", "Decreto 11.871/2023"),
    (date(2025, 1, 1), "125451.15", "62725.59", "10036.10", "Decreto 12.343/2024"),
    (date(2026, 10, 5), "130984.20", "65492.11", "10478.74", "Decreto 12.807/2025"),
]


@pytest.mark.parametrize("dia,obras,compras,veiculos,norma", LIMITES_HISTORICOS)
def test_limites_historicos_por_data_do_ato(params, dia, obras, compras, veiculos, norma):
    assert params.obter("dispensa_obras_engenharia", dia).valor == Decimal(obras)
    assert params.obter("dispensa_compras_servicos", dia).valor == Decimal(compras)
    assert params.obter("dispensa_manutencao_veiculos", dia).valor == Decimal(veiculos)
    assert params.obter("dispensa_compras_servicos", dia).atualizado_por == norma


@pytest.mark.parametrize("chave", [
    "dispensa_obras_engenharia",
    "dispensa_compras_servicos",
    "dispensa_manutencao_veiculos",
    "dispensa_fator_consorcio_agencia",
    "aditivo_acrescimo_geral",
    "aditivo_acrescimo_reforma",
])
def test_cobertura_continua_desde_a_lei(params, chave):
    """Nenhum dia sem valor entre a vigência da Lei 14.133 e hoje.

    Quando o decreto do ano seguinte for cadastrado, este teste continua
    passando; se alguém esquecer de encerrar a vigência anterior, a carga
    recusa por sobreposição; se esquecer de cadastrar, este teste acusa o
    buraco.
    """
    assert params.lacunas(chave, date(2021, 4, 1), date(2026, 12, 31)) == []


def test_ato_anterior_a_lei_nao_tem_parametro_e_a_regra_deve_calar(params):
    """Antes de 1º/04/2021 a Lei 14.133 não existia. A regra não dispara em vez
    de aplicar um limite que não se aplicava ao ato."""
    with pytest.raises(ParametroIndisponivel, match="nenhum valor cadastrado"):
        params.obter("dispensa_compras_servicos", date(2021, 3, 31))


def test_arquivo_oficial_nao_tem_pendencia_de_verificacao(params):
    """Todos os valores foram conferidos no Planalto em 05/10/2026."""
    assert params.pendentes_de_verificacao() == []


def test_aditivos_do_art_125_conferidos(params):
    assert params.obter("aditivo_acrescimo_geral", date(2026, 6, 1)).valor == Decimal("0.25")
    assert params.obter("aditivo_acrescimo_reforma", date(2026, 6, 1)).valor == Decimal("0.50")


def test_fator_de_consorcio_e_agencia_executiva(params):
    assert params.obter("dispensa_fator_consorcio_agencia", date(2024, 2, 1)).valor == Decimal("2")


@pytest.mark.parametrize("ano_envio,mes,dia", [(2021, "5", "31"), (2022, "4", "30"), (2026, "4", "30")])
def test_prazo_das_contas_anuais_do_estado_mudou_em_2022(params, ano_envio, mes, dia):
    """LC 178/2021 unificou o prazo em 30/04, com efeito só a partir de 2022."""
    referencia = date(ano_envio, 1, 1)
    assert params.obter("prazo_contas_anuais_estado_mes", referencia).valor == Decimal(mes)
    assert params.obter("prazo_contas_anuais_estado_dia", referencia).valor == Decimal(dia)


def test_prazo_das_contas_anuais_do_municipio_sempre_30_de_abril(params):
    for ano in (2019, 2022, 2026):
        assert params.obter("prazo_contas_anuais_municipio_mes", date(ano, 1, 1)).valor == Decimal("4")
        assert params.obter("prazo_contas_anuais_municipio_dia", date(ano, 1, 1)).valor == Decimal("30")


NAO_VERIFICADO = """
[[limite]]
valor = "0.25"
vigente_de = 2021-04-01
fundamento = "Lei X, art. 1"
atualizado_por = "Lei X"
verificado = false
"""


def test_parametro_nao_verificado_e_recusado_por_padrao(tmp_path):
    params = ParametrosLegais.carregar(_toml(tmp_path, NAO_VERIFICADO))
    with pytest.raises(ParametroIndisponivel, match="ainda não foi conferido"):
        params.obter("limite", date(2026, 6, 1))


def test_parametro_nao_verificado_pode_ser_lido_explicitamente(tmp_path):
    params = ParametrosLegais.carregar(_toml(tmp_path, NAO_VERIFICADO))
    p = params.obter("limite", date(2026, 6, 1), aceitar_nao_verificado=True)
    assert p.valor == Decimal("0.25")
    assert p.verificado is False
    assert [x.chave for x in params.pendentes_de_verificacao()] == ["limite"]


def test_lacunas_acusam_ano_esquecido(tmp_path):
    buraco = """
[[limite]]
valor = "1"
vigente_de = 2024-01-01
vigente_ate = 2024-12-31
fundamento = "Lei X"
atualizado_por = "Decreto A"
verificado = true
verificado_em = 2026-01-01

[[limite]]
valor = "3"
vigente_de = 2026-01-01
fundamento = "Lei X"
atualizado_por = "Decreto C"
verificado = true
verificado_em = 2026-01-01
"""
    params = ParametrosLegais.carregar(_toml(tmp_path, buraco))
    assert params.lacunas("limite", date(2023, 6, 1), date(2026, 3, 1)) == [
        (date(2023, 6, 1), date(2023, 12, 31)),
        (date(2025, 1, 1), date(2025, 12, 31)),
    ]
    assert params.lacunas("limite", date(2026, 1, 1), date(2026, 12, 31)) == []
    with pytest.raises(ValueError):
        params.lacunas("limite", date(2026, 1, 2), date(2026, 1, 1))


def test_lacuna_no_fim_do_intervalo(tmp_path):
    so_um_ano = """
[[limite]]
valor = "1"
vigente_de = 2024-01-01
vigente_ate = 2024-12-31
fundamento = "Lei X"
atualizado_por = "Decreto A"
verificado = true
verificado_em = 2026-01-01
"""
    params = ParametrosLegais.carregar(_toml(tmp_path, so_um_ano))
    assert params.lacunas("limite", date(2024, 6, 1), date(2025, 2, 1)) == [(date(2025, 1, 1), date(2025, 2, 1))]
    assert params.vigencias("limite")[0].valor == Decimal("1")
    with pytest.raises(ParametroIndisponivel):
        params.vigencias("outro")


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
