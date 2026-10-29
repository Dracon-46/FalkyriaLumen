"""Contratos dos municípios cearenses na API do SIM do TCE-CE (ADR-050)."""

from __future__ import annotations

import json
import re
from datetime import date

import pytest

from lumen_painel import comum, tce, tce_ce
from lumen_painel.cadastro import Cadastro, Ente

CADASTRO = Cadastro({"2300101": Ente("2300101", "Abaiara", "CE", "M", 12_000),
                     "2304400": Ente("2304400", "Fortaleza", "CE", "M", 2_400_000)})
MUNICIPIOS = [{"codigo_municipio": "001", "nome_municipio": "T.C.M.", "codigo_municipio_ibge": None},
              {"codigo_municipio": "002", "nome_municipio": "ABAIARA", "codigo_municipio_ibge": "2300101"},
              {"codigo_municipio": "057", "nome_municipio": "FORTALEZA", "codigo_municipio_ibge": "2304400"}]


def _contrato(numero, valor, modalidade="OR", data="2023-01-05T00:00:00"):
    return {"codigo_municipio": "002", "data_contrato": data, "numero_contrato": numero,
            "modalide_contrato": modalidade, "valor_total_contrato": valor}


def _contratado(numero, documento, tipo="1", nome="EMPRESA", data="2023-01-05T00:00:00"):
    return {"codigo_municipio": "002", "data_contrato": data, "numero_contrato": numero,
            "numero_documento_negociante": documento, "codigo_tipo_negociante": tipo, "nome_negociante": nome}


CONTRATOS = [
    _contrato("1", 7200.0),                       # uma empresa
    _contrato("2", 500.0),                        # pessoa física (CPF cifrado pelo tribunal)
    _contrato("3", 900.0),                        # duas empresas: só no total
    _contrato("4", 40.0),                         # sem contratado registrado: só no total
    _contrato("5", 60.0),                         # duas pessoas físicas: soma anônima
    _contrato("101", 100.0, "AA"),                # aditivos: o valor ora é o acréscimo, ora o total
    _contrato("102", 30.0, "AR"),
    _contrato("103", -20.0, "AR"),
    _contrato("104", 1000.0, "AP"),
]
CONTRATADOS = [
    _contratado("1", "09537392000105", nome="EMPRESA X 123.456.789-09"),
    _contratado("1", "09537392000105", nome="EMPRESA X 123.456.789-09"),   # a mesma linha repetida
    _contratado("2", "/Z6NNEXjaEoDtstd4z59aw==", tipo="2", nome="FULANA DE TAL"),
    _contratado("3", "00000000000191", nome="BANCO DO BRASIL SA"),
    _contratado("3", "11111111000191", nome="EMPRESA Z"),
    _contratado("5", "abc==", tipo="2", nome="BELTRANO"),
    _contratado("5", "def==", tipo="2", nome="CICRANO"),
    _contratado("1", "00000000000191", data="2023-02-01T00:00:00", nome="BANCO DO BRASIL SA"),  # outro contrato
]


def test_ano_por_municipio_com_pessoa_fisica_varios_contratados_e_aditivos():
    nomes = {}
    r = tce_ce.somar_ano({"2300101": (CONTRATOS, CONTRATADOS)}, lambda ente: tce_ce.teto_do_ente(ente, CADASTRO),
                         nomes)
    assert r["entes"]["2300101"] == [5, 8700.0, 0, 2, 560.0, 4, None]   # aditivos contam, sem valor
    assert r["fornecedores"]["2300101"] == {"09537392000105": [1, 7200.0]}
    assert nomes == {"09537392000105": "EMPRESA X ***.456.789-**", "00000000000191": "BANCO DO BRASIL SA",
                     "11111111000191": "EMPRESA Z"}
    assert "FULANA" not in str(r) and "Z6NNEX" not in str(r)
    assert r["sem_ente"] == [0, 0.0]


def _servidor(por_municipio, *, falha=None, pedidos=None):
    """Um ``baixar`` de mentira que responde como a API: páginas de ``POR_PAGINA``, por município e ano."""

    def baixar(url, *, contato):
        if pedidos is not None:
            pedidos.append(url)
        if "/municipios?" in url:
            return json.dumps({"name": "dv_municipios", "elements": MUNICIPIOS}).encode()
        metodo = re.search(r"/sim/(\w+)\?", url).group(1)
        codigo = re.search(r"codigo_municipio=(\d+)", url).group(1)
        ano = re.search(r"data_inicio=(\d{4})", url).group(1)
        inicio = int(re.search(r"\$start_index=(\d+)", url).group(1))
        if (codigo, ano) == falha:
            return json.dumps({"__errors__": [{"code": 50001, "message": "Error executing query"}]}).encode()
        registros = por_municipio.get((codigo, ano), ([], []))[metodo == "contratados"]
        return json.dumps({"elements": registros[inicio:inicio + tce_ce.POR_PAGINA]}).encode()

    return baixar


def test_consulta_pagina_ate_a_ultima_pagina_incompleta(monkeypatch):
    monkeypatch.setattr(tce_ce, "POR_PAGINA", 2)
    pedidos = []
    baixar = _servidor({("002", "2023"): (CONTRATOS[:5], [])}, pedidos=pedidos)
    r = tce_ce.consultar("contratos", contato="c", baixar_fn=baixar, codigo_municipio="002",
                         data_inicio="20230101", data_fim="20231231")
    assert [c["numero_contrato"] for c in r] == ["1", "2", "3", "4", "5"]
    assert [re.search(r"start_index=(\d+)", u).group(1) for u in pedidos] == ["0", "2", "4"]
    assert pedidos[0].endswith("data_fim=20231231&$start_index=0")


def test_erro_da_api_sobe():
    with pytest.raises(ValueError, match="Error executing query"):
        tce_ce.consultar("contratos", contato="c", baixar_fn=_servidor({}, falha=("002", "2023")),
                         codigo_municipio="002", data_inicio="20230101", data_fim="20231231")


def test_coleta_grava_o_ano_e_deixa_de_fora_o_ano_com_municipio_que_falhou(tmp_path):
    pedidos = []
    baixar = _servidor({("002", "2023"): (CONTRATOS, CONTRATADOS),
                        ("057", "2023"): ([_contrato("9", 10.0)], [_contratado("9", "00000000000191")]),
                        ("002", "2022"): (CONTRATOS, CONTRATADOS)},
                       falha=("057", "2022"), pedidos=pedidos)
    r = tce_ce.coletar(tmp_path, CADASTRO, contato="c", hoje=date(2023, 6, 1), anos=[2021, 2022, 2023],
                       baixar_fn=baixar)
    assert r.lidos == [2023] and r.ausentes == [2021]
    assert len(r.problemas) == 1 and r.problemas[0].startswith("2022: 1 município(s) não responderam: 057 (")
    assert sum("/municipios?" in u for u in pedidos) == 1               # o cadastro de municípios uma vez só
    assert not any("codigo_municipio=001" in u for u in pedidos)        # o próprio tribunal não é município
    estado = comum.ler_json(tmp_path / tce_ce.ARQUIVO)
    assert estado["tribunal"] == "TCE-CE" and estado["primeiro_ano"] == 2003
    assert set(estado["anos"]) == {"2023"} and estado["anos"]["2023"]["entes"]["2304400"][:2] == [1, 10.0]
    assert estado["anos"]["2023"]["etiqueta"] == "10/9"
    # Sem anos pedidos, a idade decide: 2023 foi lido agora e não volta
    r2 = tce_ce.coletar(tmp_path, CADASTRO, contato="c", hoje=date(2023, 6, 2), baixar_fn=_servidor({}))
    assert 2023 in r2.pulados and 2003 in r2.ausentes


def test_coleta_para_no_prazo(tmp_path):
    instantes = iter([0.0, 0.0, 120.0])
    r = tce_ce.coletar(tmp_path, CADASTRO, contato="c", hoje=date(2023, 6, 1), anos=[2022, 2023], limite_minutos=1,
                       baixar_fn=_servidor({}), relogio=lambda: next(instantes))
    assert r.interrompida and r.ausentes == [2022]


def test_contrato_sem_fornecedor_fica_so_no_total():
    soma = tce.SomaAno(lambda ente: 1e9)
    soma.contrato("1", 10.0, sem_fornecedor=True)
    soma.contrato("1", 5.0)
    soma.aditivo("1", 3.0)
    soma.aditivo("1", None)
    soma.aditivo("1", 4.0)
    soma.aditivo("2", 7.0)
    assert soma.para_json()["entes"]["1"] == [2, 15.0, 0, 1, 5.0, 3, None]
    assert soma.para_json()["entes"]["2"][5:] == [1, 7.0]
