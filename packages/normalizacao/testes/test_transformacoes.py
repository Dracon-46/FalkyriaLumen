"""Transformações comuns da normalização: datas, valores monetários, documentos e chaves de texto."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from lumen_normalizacao.transformacoes import (
    BRT,
    ValorIlegivel,
    booleano_ou_nulo,
    chave_texto,
    data_ou_nula,
    decimal_ou_nulo,
    instante_brt_ou_nulo,
    inteiro_ou_nulo,
    ler_json,
    moeda_br,
    texto_ou_nulo,
)

HOJE = date(2026, 10, 5)


def test_ler_json_preserva_casas_decimais():
    d = ler_json(b'{"v": 19977.00, "w": 0.1}')
    assert d["v"] == Decimal("19977.00") and isinstance(d["w"], Decimal)
    assert ler_json('﻿{"a": 1}'.encode("utf-8")) == {"a": 1}


@pytest.mark.parametrize("entrada,saida", [
    (None, None), ("", None), (5, Decimal(5)), (Decimal("1.50"), Decimal("1.50")),
    ("  2.5 ", Decimal("2.5")), (0.1, Decimal("0.1")),
])
def test_decimal(entrada, saida):
    assert decimal_ou_nulo(entrada) == saida


@pytest.mark.parametrize("ruim", ["abc", True])
def test_decimal_ilegivel(ruim):
    with pytest.raises(ValorIlegivel):
        decimal_ou_nulo(ruim)


@pytest.mark.parametrize("entrada,saida", [
    ("R$ 1.234,56", Decimal("1234.56")), ("65.492,11", Decimal("65492.11")),
    ("100", Decimal("100")), ("-3,5", Decimal("-3.5")), ("", None), (None, None),
    ("R$ 130.984,20", Decimal("130984.20")),
])
def test_moeda_br(entrada, saida):
    assert moeda_br(entrada) == saida


def test_moeda_br_ilegivel():
    with pytest.raises(ValorIlegivel):
        moeda_br("1,234.56")


@pytest.mark.parametrize("entrada,saida", [(None, None), ("", None), ("7", 7), (3, 3), ("8.0", 8)])
def test_inteiro(entrada, saida):
    assert inteiro_ou_nulo(entrada) == saida


@pytest.mark.parametrize("ruim", ["1.5", "x", False])
def test_inteiro_ilegivel(ruim):
    with pytest.raises(ValorIlegivel):
        inteiro_ou_nulo(ruim)


@pytest.mark.parametrize("entrada,saida", [
    (True, True), (False, False), ("S", True), ("n", False), ("1", True), (None, None), ("", None),
])
def test_booleano(entrada, saida):
    assert booleano_ou_nulo(entrada) is saida


def test_booleano_ilegivel():
    with pytest.raises(ValorIlegivel):
        booleano_ou_nulo("talvez")


def test_datas():
    assert data_ou_nula("2026-09-01", hoje=HOJE) == date(2026, 9, 1)
    assert data_ou_nula("2026-09-01T00:10:03", hoje=HOJE) == date(2026, 9, 1)
    assert data_ou_nula("01/09/2026", hoje=HOJE) == date(2026, 9, 1)
    assert data_ou_nula(None) is None


@pytest.mark.parametrize("ruim", ["7203-07-27", "1900-01-01", "2026-13-01", "ontem"])
def test_data_implausivel_ou_ilegivel(ruim):
    with pytest.raises(ValorIlegivel):
        data_ou_nula(ruim, hoje=HOJE)


def test_instante_sem_fuso_e_brasilia():
    i = instante_brt_ou_nulo("2026-09-01T00:10:03", hoje=HOJE)
    assert i == datetime(2026, 9, 1, 0, 10, 3, tzinfo=BRT)
    assert i.utcoffset() == timedelta(hours=-3)


def test_instante_com_fuso_e_respeitado():
    i = instante_brt_ou_nulo("2026-10-05T11:45:25.307+00:00", hoje=HOJE)
    assert i.tzinfo is not None and i.utcoffset() == timedelta(0)
    z = instante_brt_ou_nulo("2025-03-12T16:30:46Z", hoje=HOJE)
    assert z == datetime(2025, 3, 12, 16, 30, 46, tzinfo=timezone.utc)
    assert instante_brt_ou_nulo("", hoje=HOJE) is None


def test_instante_ilegivel():
    with pytest.raises(ValorIlegivel):
        instante_brt_ou_nulo("amanhã", hoje=HOJE)


def test_texto_preserva_o_publicado():
    assert texto_ou_nulo("  MEDICAMENTOS  ") == "  MEDICAMENTOS  "
    assert texto_ou_nulo("   ") is None
    assert texto_ou_nulo(None) is None


def test_chave_texto_so_para_comparar():
    assert chave_texto("  Educação   Infantil ") == "educacao infantil"
    assert chave_texto(None) == ""
