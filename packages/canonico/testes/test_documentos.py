"""Testes de CNPJ e CPF, incluindo o CNPJ alfanumérico de 2026."""

import pytest

from lumen_canonico.documentos import (
    TipoDocumento,
    calcular_dv_cnpj,
    classificar,
    cnpj_raiz,
    cnpj_valido,
    cpf_valido,
    documento_publicavel,
    limpar,
    mascarar_cpf,
)

# CNPJs reais lidos nas fixtures do PNCP e do SICONFI
CNPJS_REAIS = [
    "97229181000164",  # Município de São Sepé/RS
    "07854402000100",  # EMASA, Balneário Camboriú/SC
    "00360305000104",  # Caixa Econômica Federal
    "07954480000179",  # Estado do Ceará
    "46395000000139",  # Município de São Paulo
    "44281151000130",  # fornecedor MEI em Xique-Xique/BA
]


@pytest.mark.parametrize("cnpj", CNPJS_REAIS)
def test_cnpjs_reais_das_fixtures_sao_validos(cnpj):
    assert cnpj_valido(cnpj)


def test_cnpj_alfanumerico_do_exemplo_oficial_da_receita():
    """Exemplo publicado pela Receita Federal: 12.ABC.345/01DE-35."""
    assert calcular_dv_cnpj("12ABC34501DE") == "35"
    assert cnpj_valido("12.ABC.345/01DE-35")
    assert cnpj_valido("12abc34501de35")  # caixa baixa é normalizada


def test_cnpj_alfanumerico_com_dv_errado():
    assert not cnpj_valido("12ABC34501DE36")


def test_dv_do_cnpj_numerico_continua_igual():
    assert calcular_dv_cnpj("972291810001") == "64"


@pytest.mark.parametrize("ruim", [
    None, "", "123", "00000000000000", "11111111111111", "9722918100016X",
    "97229181000165", "972291810001640",
])
def test_cnpj_invalido(ruim):
    assert not cnpj_valido(ruim)


def test_base_de_cnpj_mal_formada():
    with pytest.raises(ValueError):
        calcular_dv_cnpj("12AB")


def test_raiz_identifica_a_empresa_em_todas_as_filiais():
    assert cnpj_raiz("97.229.181/0001-64") == "97229181"
    with pytest.raises(ValueError):
        cnpj_raiz("abc")


def test_limpar():
    assert limpar(" 97.229.181/0001-64 ") == "97229181000164"
    assert limpar(None) == ""


@pytest.mark.parametrize("cpf,valido", [
    ("529.982.247-25", True),
    ("52998224725", True),
    ("52998224724", False),
    ("11111111111", False),
    ("123", False),
    (None, False),
])
def test_cpf(cpf, valido):
    assert cpf_valido(cpf) is valido


def test_mascara_de_cpf_preserva_so_os_seis_digitos_centrais():
    assert mascarar_cpf("529.982.247-25") == "***.982.247-**"
    assert mascarar_cpf("abc") is None
    assert mascarar_cpf(None) is None


def test_classificacao_respeita_o_tipo_declarado():
    assert classificar("97229181000164", "PJ") is TipoDocumento.CNPJ
    assert classificar("52998224725", "PF") is TipoDocumento.CPF
    # PF com 14 dígitos é inconsistência da fonte; não vira CNPJ
    assert classificar("97229181000164", "PF") is TipoDocumento.INVALIDO
    assert classificar("52998224725", "PJ") is TipoDocumento.INVALIDO
    assert classificar("X123", "PE") is TipoDocumento.ESTRANGEIRO


def test_classificacao_sem_tipo_usa_o_formato():
    assert classificar("97229181000164") is TipoDocumento.CNPJ
    assert classificar("52998224725") is TipoDocumento.CPF
    assert classificar("1") is TipoDocumento.INVALIDO


def test_documento_publicavel_nunca_expoe_cpf():
    assert documento_publicavel("52998224725", "PF") == "***.982.247-**"
    assert documento_publicavel("97.229.181/0001-64", "PJ") == "97229181000164"
    assert documento_publicavel("52998224724", "PF") is None  # CPF inválido não segue
    assert documento_publicavel("AB-123", "PE") == "AB123"
    assert documento_publicavel("", "PE") is None
