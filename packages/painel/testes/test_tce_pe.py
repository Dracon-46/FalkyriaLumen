"""Contratos dos órgãos pernambucanos na API do TCE-PE (ADR-050)."""

from __future__ import annotations

import json
from datetime import date

from lumen_painel import comum, tce, tce_pe
from lumen_painel.cadastro import Cadastro, Ente

CADASTRO = Cadastro({"2614105": Ente("2614105", "Sertânia", "PE", "M", 36_000),
                     "26": Ente("26", "Pernambuco", "PE", "E", 9_500_000)})
MUNICIPIOS = [{"CODIGOIBGE": "2614105", "UNIDADEFEDERATIVA": "PE", "MUNICIPIO": "Sertânia"},
              {"CODIGOIBGE": "1100338", "UNIDADEFEDERATIVA": "RO", "MUNICIPIO": "Nova Mamoré"}]
CONTRATOS = [
    {"CodigoContrato": "1", "Esfera": "M ", "Municipio": "Sertânia", "UnidadeGestora": "Câmara Municipal de Sertânia",
     "TipoDocumento": "CNPJ", "CPF_CNPJ": "09537392000105    ", "RazaoSocial": "EMPRESA X 123.456.789-09", "Valor": "7200.00"},
    {"CodigoContrato": "2", "Esfera": "M ", "Municipio": "Sertânia", "UnidadeGestora": "Prefeitura de Sertânia",
     "TipoDocumento": "CPF", "CPF_CNPJ": "***.456.789-**", "RazaoSocial": "FULANA DE TAL", "Valor": "500.00"},
    {"CodigoContrato": "3", "Esfera": "E ", "Municipio": "Recife", "UnidadeGestora": "Secretaria de Saúde",
     "TipoDocumento": "CNPJ", "CPF_CNPJ": "00000000000191", "RazaoSocial": "BANCO DO BRASIL SA", "Valor": "1000.00"},
    {"CodigoContrato": "4", "Esfera": "M ", "Municipio": "Sertânia", "UnidadeGestora": "Consórcio do Moxotó",
     "TipoDocumento": "CNPJ", "CPF_CNPJ": "11111111000191", "RazaoSocial": "EMPRESA Z", "Valor": "70.00"},
]
ADITIVOS = [{"CodigoContrato": "1", "ValorTermoAditivo": "100.0000"},
            {"CodigoContrato": "9", "Esfera": "E ", "Municipio": "Recife", "UnidadeGestora": "X", "ValorTermoAditivo": "5"}]


def _resposta(conteudo, *, limite=100000):
    return json.dumps({"resposta": {"status": "OK", "tamanhoResultado": str(len(conteudo)),
                                    "limiteResultado": str(limite), "conteudo": conteudo}}).encode("latin-1")


def test_ano_por_ente_com_consorcio_pessoa_fisica_e_aditivos():
    nomes = {}
    r = tce_pe.somar_ano(CONTRATOS, ADITIVOS, tce_pe.municipios(MUNICIPIOS),
                         lambda ente: tce_pe.teto_do_ente(ente, CADASTRO), nomes)
    assert r["entes"]["2614105"] == [2, 7700.0, 0, 1, 500.0, 1, 100.0]
    assert r["entes"]["26"] == [1, 1000.0, 0, 0, 0.0, 1, 5.0]          # o aditivo do contrato 9, de outro ano
    assert r["sem_ente"] == [1, 70.0]
    assert nomes == {"09537392000105": "EMPRESA X ***.456.789-**", "00000000000191": "BANCO DO BRASIL SA",
                     "11111111000191": "EMPRESA Z"}
    assert "FULANA" not in str(r)


def test_coleta_le_os_anos_pela_idade_e_avisa_consulta_cortada(tmp_path):
    pedidos = []

    def baixar(url, *, contato):
        pedidos.append(url)
        if "Municipios" in url:
            return _resposta(MUNICIPIOS)
        if "AnoContrato=2021" in url:
            return _resposta(CONTRATOS if "Contratos" in url else ADITIVOS, limite=2)   # cortada
        return _resposta(CONTRATOS if "Contratos" in url else ADITIVOS) if "AnoContrato=2022" in url else _resposta([])

    r = tce_pe.coletar(tmp_path, CADASTRO, contato="c", hoje=date(2022, 6, 1), anos=[2020, 2021, 2022],
                       baixar_fn=baixar)
    assert r.lidos == [2022] and r.ausentes == [2020] and r.problemas[0].startswith("2021:")
    assert sum("Municipios" in u for u in pedidos) == 1                # o cadastro de municípios uma vez só
    estado = comum.ler_json(tmp_path / tce_pe.ARQUIVO)
    assert estado["tribunal"] == "TCE-PE" and estado["anos"]["2022"]["entes"]["2614105"][0] == 2
    # Sem anos pedidos, a idade decide: 2022 foi lido agora e não volta
    r2 = tce_pe.coletar(tmp_path, CADASTRO, contato="c", hoje=date(2022, 6, 2), baixar_fn=baixar)
    assert 2022 in r2.pulados


def test_releitura_por_idade():
    lido = {"lido_em": "2026-10-01T00:00:00Z"}
    assert tce.precisa_ler_por_idade(None, 2020, date(2026, 10, 21))
    assert not tce.precisa_ler_por_idade(lido, 2020, date(2026, 10, 21))   # fechado: 20 dias, menos de 30
    assert tce.precisa_ler_por_idade(lido, 2020, date(2026, 11, 2))
    assert tce.precisa_ler_por_idade(lido, 2026, date(2026, 10, 21))       # corrente: mais de 6 dias
