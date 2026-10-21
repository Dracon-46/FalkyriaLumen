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
    mascarar_cpfs_no_texto,
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


@pytest.mark.parametrize("texto,esperado", [
    # Nomes reais de MEI publicados no PNCP em outubro de 2026 (o CPF do titular no fim da razão social)
    ("NYARA OLIVEIRA CAVALCANTE 01987103300", "NYARA OLIVEIRA CAVALCANTE ***.871.033-**"),
    ("JACKSON GOSSMANN DA SILVA03863498003", "JACKSON GOSSMANN DA SILVA***.634.980-**"),
    ("JOSÉ HUMBERTO ALVES -61492388653", "JOSÉ HUMBERTO ALVES -***.923.886-**"),
    ("J SILVA 123.456.789-09", "J SILVA ***.456.789-**"),
    ("EMPRESA X 12345678000190", "EMPRESA X 12345678000190"),      # CNPJ não é CPF
    (None, None),
])
def test_cpf_no_nome_sempre_mascarado(texto, esperado):
    assert mascarar_cpfs_no_texto(texto) == esperado


def test_cpf_no_objeto_so_com_forma_de_cpf():
    objeto = "por intermédio de NELSON SARAIVA ALVES 32620487803, emenda 20253666000, CNPJ 12.345.678/0001-90"
    assert mascarar_cpfs_no_texto(objeto, todos=False) == (
        "por intermédio de NELSON SARAIVA ALVES ***.204.878-**, emenda 20253666000, CNPJ 12.345.678/0001-90")
    assert mascarar_cpfs_no_texto("CPF 123.456.789-00.", todos=False) == "CPF ***.456.789-**."
    assert mascarar_cpfs_no_texto("protocolo 123456789012", todos=False) == "protocolo 123456789012"
