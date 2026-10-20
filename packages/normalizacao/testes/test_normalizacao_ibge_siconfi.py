"""Normalização das respostas reais do IBGE (localidades e população) e do SICONFI (entes e extrato)."""

import json
from datetime import date, datetime, timezone

import pytest

from lumen_canonico.fato import Esfera
from lumen_canonico.identidade import id_canonico
from lumen_canonico.porte import classificar_porte
from lumen_canonico.ufs import UFS, sigla_da_uf
from lumen_normalizacao import ibge, siconfi

PROV = dict(fonte_id="teste", documento_fonte_id="reg1")


def test_ufs_conferem_com_o_ibge(fixture_bytes):
    estados = json.loads(fixture_bytes("ibge/estados.json"))
    assert {str(e["id"]): (e["sigla"], e["nome"], e["regiao"]["sigla"]) for e in estados} == UFS


def test_sigla_da_uf():
    assert sigla_da_uf("4319604") == "RS" and sigla_da_uf(53) == "DF"
    assert sigla_da_uf("1") is None and sigla_da_uf(None) is None and sigla_da_uf("99") is None


def test_estados(fixture_bytes):
    r = ibge.normalizar_estados(fixture_bytes("ibge/estados.json"), **PROV)
    assert len(r.registros) == 27 and r.quarentena == []
    df = next(e for e in r.registros if e.codigo_ibge == "53")
    assert df.esfera is Esfera.DISTRITAL
    assert next(e for e in r.registros if e.codigo_ibge == "43").esfera is Esfera.ESTADUAL


def test_municipios_e_populacao(fixture_bytes):
    r = ibge.normalizar_municipios(fixture_bytes("ibge/municipios_nivelado_amostra.json"), **PROV)
    entes = r.registros
    assert [e.codigo_ibge for e in entes] == ["3550308", "4319604"]
    pop = ibge.ler_populacao(fixture_bytes("ibge/populacao_6579_amostra.json"))
    assert pop["4319604"] == (21551, "2026")
    ibge.aplicar_populacao(entes, pop)
    sepe = entes[1]
    assert sepe.populacao == 21551 and sepe.porte == "20_a_50_mil"
    assert sepe.populacao_referencia == "IBGE estimativa 2026"
    assert entes[0].porte == "acima_500_mil"


def test_populacao_ignora_marcadores_de_ausencia_do_sidra():
    bruto = json.dumps([{"resultados": [{"series": [
        {"localidade": {"id": "1"}, "serie": {"2026": "-"}},
        {"localidade": {"id": "2"}, "serie": {"2026": "..."}},
        {"localidade": {"id": "3"}, "serie": {"2026": "10"}}]}]}]).encode()
    assert ibge.ler_populacao(bruto) == {"3": (10, "2026")}


def test_codigo_invalido_vai_para_quarentena():
    r = ibge.normalizar_municipios(json.dumps([{"municipio-id": 12}]).encode(), **PROV)
    assert r.registros == [] and r.quarentena[0].campo == "municipio-id"
    r = ibge.normalizar_estados(json.dumps([{"id": 123}]).encode(), **PROV)
    assert r.quarentena[0].campo == "id"


@pytest.mark.parametrize("pop,faixa", [
    (None, None), (0, "ate_5_mil"), (5000, "ate_5_mil"), (5001, "5_a_10_mil"),
    (50000, "20_a_50_mil"), (500001, "acima_500_mil"),
])
def test_porte(pop, faixa):
    assert classificar_porte(pop) == faixa


def test_porte_negativo():
    with pytest.raises(ValueError):
        classificar_porte(-1)


def test_entes_do_siconfi_e_suas_peculiaridades(fixture_bytes):
    r = siconfi.normalizar_entes(fixture_bytes("siconfi/entes_amostra.json"), **PROV)
    por_codigo = {e.codigo_ibge: e for e in r.registros}
    assert set(por_codigo) == {"3550308", "4319604", "5300108", "1", "43"}
    sp = por_codigo["3550308"]
    assert sp.capital is True and sp.cnpj == "46395000000139" and sp.uf == "SP"
    assert por_codigo["4319604"].capital is False
    rs = por_codigo["43"]
    assert rs.uf == "RS" and siconfi.UF_DIVERGENTE in rs.marcacoes_qualidade  # fonte diz "BR"
    uniao = por_codigo["1"]
    assert uniao.esfera is Esfera.UNIAO and siconfi.POPULACAO_INCONSISTENTE in uniao.marcacoes_qualidade


def test_ente_com_esfera_desconhecida():
    bruto = json.dumps({"items": [{"cod_ibge": 4319604, "esfera": "X"}]}).encode()
    r = siconfi.normalizar_entes(bruto, **PROV)
    assert r.quarentena[0].campo == "esfera"


def test_resposta_ords_sem_items_vai_para_quarentena():
    r = siconfi.normalizar_entes(b'{"erro": "x"}', **PROV)
    assert "items" in r.quarentena[0].motivo


def test_extrato_de_entregas(fixture_bytes):
    r = siconfi.normalizar_extrato(fixture_bytes("siconfi/extrato_entregas_4319604_2025.json"), **PROV,
                                   hoje=date(2026, 10, 5))
    assert len(r.registros) == 37 and r.quarentena == []
    dca = [e for e in r.registros if e.entregavel == "Balanço Anual (DCA)"]
    assert len(dca) == 1
    assert dca[0].entregue_em == datetime(2026, 4, 30, 8, 28, 58, tzinfo=timezone.utc)
    assert dca[0].ente_id == id_canonico("ente_federativo", "4319604")
    assert dca[0].status_relatorio == "HO"


# ---------------------------------------------------------------- demonstrativos (RREO, RGF, DCA)

def test_rreo_anexo03_real_com_a_rcl(fixture_bytes):
    r = siconfi.normalizar_demonstrativo(fixture_bytes("siconfi/rreo_anexo03_amostra.json"),
                                         fonte_id="siconfi_rreo", documento_fonte_id="doc-1")
    assert len(r.registros) == 28 and not r.quarentena
    assert len({x.id for x in r.registros}) == 28
    (rcl,) = [x for x in r.registros
              if x.cod_conta == "RREO3ReceitaCorrenteLiquida" and x.coluna == "TOTAL (ÚLTIMOS 12 MESES)"]
    assert (rcl.ente_codigo_ibge, rcl.exercicio, rcl.periodo, rcl.demonstrativo) == ("4319604", 2025, 6,
                                                                                     "RREO Simplificado")
    assert str(rcl.valor) == "127898463.53" and rcl.anexo == "RREO-Anexo 03"
    assert rcl.ente_id == id_canonico("ente_federativo", "4319604")


def test_dca_anexo_i_e_real_sem_o_campo_demonstrativo(fixture_bytes):
    # A DCA não traz "demonstrativo" nem "periodo": o demonstrativo vem do anexo
    r = siconfi.normalizar_demonstrativo(fixture_bytes("siconfi/dca_anexo_i_e_sao_sepe_2025.json"),
                                         fonte_id="siconfi_dca", documento_fonte_id="doc-dca")
    assert len(r.registros) == 152 and not r.quarentena
    assert {(x.demonstrativo, x.periodo, x.anexo) for x in r.registros} == {("DCA", None, "DCA-Anexo I-E")}
    (saude,) = [x for x in r.registros if x.conta == "10 - Saúde" and x.coluna == "Despesas Liquidadas"]
    assert str(saude.valor) == "32108759.99" and saude.populacao_declarada == 21189


def test_rreo_anexo02_mesmo_codigo_de_conta_com_contas_diferentes(fixture_bytes):
    r = siconfi.normalizar_demonstrativo(fixture_bytes("siconfi/rreo_anexo02_amostra.json"),
                                         fonte_id="siconfi_rreo", documento_fonte_id="doc-2")
    assert {x.cod_conta for x in r.registros} == {"RREO2TotalDespesas"}
    assert len({x.id for x in r.registros}) == len(r.registros) == 4


def test_linha_de_demonstrativo_incompleta_vai_para_quarentena():
    base = {"cod_ibge": 4319604, "exercicio": 2025, "periodo": 6, "demonstrativo": "RREO", "anexo": "RREO-Anexo 03",
            "coluna": "TOTAL", "cod_conta": "X", "conta": "Y", "valor": 1.5}
    itens = [base, {**base, "conta": None}, {**base, "periodo": None},
             {**base, "demonstrativo": "DCA", "periodo": None, "conta": "Z"}, {**base, "valor": "abc", "conta": "W"}]
    r = siconfi.normalizar_demonstrativo(json.dumps({"items": itens}).encode(), fonte_id="siconfi_rreo",
                                         documento_fonte_id="doc-3")
    assert [x.conta for x in r.registros] == ["Y", "Z"]
    assert {e.campo for e in r.quarentena} == {"conta", "periodo", "valor"}
