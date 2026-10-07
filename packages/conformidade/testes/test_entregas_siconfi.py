"""Conformidade das entregas ao SICONFI, com o extrato real de São Sepé/RS (2025)."""

from datetime import date, datetime, timezone

import pytest

from lumen_canonico.fato import EntregaSiconfi, Esfera
from lumen_conformidade.entregas_siconfi import (
    ausentes,
    avaliar_dca,
    avaliar_rgf,
    avaliar_rreo,
    periodicidade_rgf_declarada,
)
from lumen_deteccao.parametros_legais import ParametrosLegais
from lumen_ingestao.portas import ResultadoCriterio as R
from lumen_normalizacao import siconfi

HOJE = date(2026, 10, 5)


@pytest.fixture(scope="module")
def params():
    return ParametrosLegais.carregar()


@pytest.fixture
def extrato(fixture_bytes):
    return siconfi.normalizar_extrato(fixture_bytes("siconfi/extrato_entregas_4319604_2025.json"),
                                      fonte_id="siconfi_extrato", documento_fonte_id="r", hoje=HOJE).registros


def _entrega(entregavel, periodo, quando, *, periodicidade="B", status="HO", instituicao="Prefeitura X", ex=2025):
    return EntregaSiconfi(id=f"{entregavel}{periodo}{quando}", ente_id="e", ente_codigo_ibge="9999999",
                          exercicio=ex, instituicao=instituicao, entregavel=entregavel, periodo=periodo,
                          periodicidade=periodicidade, status_relatorio=status,
                          entregue_em=datetime.fromisoformat(quando).replace(tzinfo=timezone.utc) if quando else None,
                          forma_envio=None, tipo_relatorio=None, populacao_declarada=None)


def test_dca_de_sao_sepe_entregue_no_ultimo_dia_do_prazo(extrato, params):
    a = avaliar_dca("4319604", Esfera.MUNICIPAL, 2025, extrato, params, hoje=HOJE)
    assert a.avaliacao.resultado is R.CUMPRE
    assert a.prazo == date(2026, 4, 30)
    assert a.avaliacao.dispositivo_legal == "LC 101/2000, art. 51, § 1º"
    assert a.periodo_referencia == "2025"


def test_rreo_simplificado_conta_como_rreo(extrato, params):
    a = avaliar_rreo("4319604", 2025, 1, extrato, params, hoje=HOJE)
    assert a.avaliacao.resultado is R.CUMPRE      # 28/03 para prazo de 30/03
    assert a.prazo == date(2025, 3, 30)


def test_rreo_entregue_depois_do_prazo(extrato, params):
    a = avaliar_rreo("4319604", 2025, 5, extrato, params, hoje=HOJE)
    # 5º bimestre termina em 31/10; prazo 30/11; entrega em 30/01/2026
    assert a.avaliacao.resultado is R.CUMPRE_PARCIALMENTE
    assert a.entregue_em.date() == date(2026, 1, 30)


def test_rgf_semestral_declarado_pelo_ente(extrato, params):
    assert periodicidade_rgf_declarada(extrato, 2025) == "S"
    a = avaliar_rgf("4319604", 2025, 1, extrato, params, hoje=HOJE, instituicao_contem="Prefeitura")
    assert a.periodo_referencia == "2025-S1"
    # a versão original não está no extrato, só a retificada (RE): data original desconhecida
    assert a.avaliacao.resultado is R.CUMPRE  # RE em 18/07/2025, dentro do prazo de 30/07
    camara = avaliar_rgf("4319604", 2025, 1, extrato, params, hoje=HOJE, instituicao_contem="Câmara")
    assert camara.avaliacao.resultado is R.CUMPRE
    with pytest.raises(ValueError):
        avaliar_rgf("4319604", 2025, 3, extrato, params, hoje=HOJE)


def test_so_retificada_fora_do_prazo_fica_indeterminada(params):
    entregas = [_entrega("Relatório Resumido de Execução Orçamentária", 1, "2025-06-01T10:00:00", status="RE")]
    a = avaliar_rreo("9999999", 2025, 1, entregas, params, hoje=HOJE)
    assert a.avaliacao.resultado is R.INDETERMINADO
    assert "retificada" in a.avaliacao.motivo_indeterminado


def test_ausencia_com_prazo_vencido(params):
    a = avaliar_dca("9999999", Esfera.MUNICIPAL, 2025, [], params, hoje=HOJE)
    assert a.avaliacao.resultado is R.NAO_CUMPRE


def test_prazo_ainda_nao_vencido_nao_atribui_nada(params):
    a = avaliar_dca("9999999", Esfera.MUNICIPAL, 2025, [], params, hoje=date(2026, 4, 30))
    assert a.avaliacao.resultado is R.INDETERMINADO and "não venceu" in a.avaliacao.motivo_indeterminado


def test_coleta_falha_protege_o_ente(params):
    a = avaliar_dca("9999999", Esfera.MUNICIPAL, 2025, [], params, hoje=HOJE, coleta_ok=False)
    assert a.avaliacao.resultado is R.INDETERMINADO and "coleta" in a.avaliacao.motivo_indeterminado


def test_prazo_do_estado_antes_e_depois_da_lc_178(params):
    antes = avaliar_dca("43", Esfera.ESTADUAL, 2020, [], params, hoje=HOJE)
    depois = avaliar_dca("43", Esfera.ESTADUAL, 2021, [], params, hoje=HOJE)
    assert antes.prazo == date(2021, 5, 31)   # exercício 2020, envio em 2021
    assert depois.prazo == date(2022, 4, 30)  # exercício 2021, envio em 2022


def test_entrega_sem_data(params):
    a = avaliar_rreo("9", 2025, 1, [_entrega("Relatório Resumido de Execução Orçamentária", 1, None)], params, hoje=HOJE)
    assert a.avaliacao.resultado is R.INDETERMINADO


def test_rgf_sem_nenhuma_entrega_nao_vira_ausencia(params):
    a = avaliar_rgf("9", 2025, 1, [], params, hoje=HOJE)
    assert a.avaliacao.resultado is R.INDETERMINADO and "art. 63" in a.avaliacao.motivo_indeterminado


def test_rgf_quadrimestral_declarado(params):
    e = [_entrega("Relatório de Gestão Fiscal", 1, "2025-05-20T10:00:00", periodicidade="Q")]
    a = avaliar_rgf("9", 2025, 1, e, params, hoje=HOJE)
    assert a.periodo_referencia == "2025-Q1" and a.avaliacao.resultado is R.CUMPRE
    falta = avaliar_rgf("9", 2025, 2, e, params, hoje=HOJE)
    assert falta.avaliacao.resultado is R.NAO_CUMPRE


def test_rreo_periodo_invalido(params):
    with pytest.raises(ValueError):
        avaliar_rreo("9", 2025, 7, [], params, hoje=HOJE)


def test_lista_de_ausentes(extrato):
    lista = ausentes(["4319604", "1100015", "9999999"], extrato, exercicio=2025,
                     coletados={"4319604", "1100015"})
    # 9999999 não teve coleta bem-sucedida: não entra em lista nenhuma
    assert lista == {"dca": ["1100015"], "rreo": ["1100015"], "rgf": ["1100015"]}
