"""Testes do bloco de fato administrativo e dos ids determinísticos."""

from dataclasses import dataclass, field, fields
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from lumen_canonico.fato import (
    ENTIDADES_FATO,
    EnteFederativo,
    Esfera,
    Modalidade,
    RegistroCanonico,
    Sensibilidade,
)
from lumen_canonico.identidade import NAMESPACE_LUMEN, id_canonico


@pytest.mark.parametrize("entidade", ENTIDADES_FATO, ids=lambda e: e.__name__)
def test_todo_campo_tem_classificacao_de_sensibilidade(entidade):
    """RNF-18: nenhum campo chega à camada consultável sem classificação."""
    classificados = set(entidade.sensibilidade_completa())
    campos = {f.name for f in fields(entidade)}
    assert campos <= classificados, campos - classificados


def test_campo_sem_classificacao_e_recusado_na_criacao():
    @dataclass
    class Esquecido(RegistroCanonico):
        ENTIDADE = "esquecido"
        id: str
        campo_novo: str
        marcacoes_qualidade: list = field(default_factory=list)

    with pytest.raises(TypeError, match="campo_novo"):
        Esquecido(id="1", campo_novo="x")


def test_documento_de_fornecedor_e_sensivel():
    from lumen_canonico.fato import Contrato, ResultadoItem
    assert Contrato.SENSIBILIDADE["fornecedor_documento"] is Sensibilidade.SENSIVEL
    assert ResultadoItem.SENSIBILIDADE["fornecedor_documento"] is Sensibilidade.SENSIVEL
    from lumen_canonico.fato import Sancao
    assert Sancao.SENSIBILIDADE["documento"] is Sensibilidade.SENSIVEL


def test_serializacao_preserva_decimal_como_texto_e_datas_em_iso():
    ente = EnteFederativo(
        id=id_canonico("ente_federativo", "4319604"), codigo_ibge="4319604",
        nome="São Sepé", esfera=Esfera.MUNICIPAL, uf="RS", populacao=21551,
    )
    d = ente.para_dict()
    assert d["esfera"] == "municipal"
    assert d["_entidade"] == "ente_federativo"

    from lumen_canonico.fato import _serializar
    brt = timezone(timedelta(hours=-3))
    assert _serializar(Decimal("19977.00")) == "19977.00"
    assert _serializar(date(2026, 9, 1)) == "2026-09-01"
    assert _serializar(datetime(2026, 9, 1, 0, 10, 3, tzinfo=brt)) == "2026-09-01T00:10:03-03:00"
    assert _serializar([Decimal("1"), {"a": Decimal("2")}]) == ["1", {"a": "2"}]


def test_modalidade_contratacao_direta():
    assert Modalidade.DISPENSA.eh_contratacao_direta
    assert Modalidade.INEXIGIBILIDADE.eh_contratacao_direta
    assert not Modalidade.PREGAO.eh_contratacao_direta


# --------------------------------------------------------------------------
# Identidade
# --------------------------------------------------------------------------

def test_id_e_deterministico_entre_execucoes():
    a = id_canonico("processo_contratacao", "97229181000164-1-000406/2026")
    b = id_canonico("processo_contratacao", "97229181000164-1-000406/2026")
    assert a == b


def test_id_conhecido_nao_muda_nunca():
    """Se este valor mudar, todos os ids emitidos pelo projeto mudaram junto."""
    assert str(NAMESPACE_LUMEN) == "6f1d3a52-6b0e-5c1e-9a57-4c756d656e00"
    assert id_canonico("ente_federativo", "4319604") == id_canonico("ente_federativo", " 4319604 ")


def test_entidades_diferentes_com_a_mesma_chave_nao_colidem():
    assert id_canonico("processo_contratacao", "X") != id_canonico("contrato", "X")


def test_partes_da_chave_nao_se_confundem():
    assert id_canonico("item", "ab", "c") != id_canonico("item", "a", "bc")


@pytest.mark.parametrize("ruim", [(), (None,), ("",), ("  ",)])
def test_chave_vazia_ou_nula_e_recusada(ruim):
    with pytest.raises(ValueError):
        id_canonico("x", *ruim)
