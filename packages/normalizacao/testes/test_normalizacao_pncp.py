"""Normalização das respostas reais do PNCP (fixtures de 05/10/2026)."""

from datetime import date, datetime
from decimal import Decimal

import pytest

from lumen_canonico.fato import (
    AmparoLegal,
    AtaRegistroPreco,
    Contrato,
    Esfera,
    ItemContratacao,
    Modalidade,
    Orgao,
    Poder,
    ProcessoContratacao,
    ResultadoItem,
    TipoPessoa,
    UnidadeGestora,
)
from lumen_canonico.identidade import id_canonico
from lumen_normalizacao import pncp
from lumen_normalizacao import qualidade as q
from lumen_normalizacao.transformacoes import BRT

HOJE = date(2026, 10, 5)
PROV = dict(fonte_id="pncp_contratacoes", documento_fonte_id="reg0001", hoje=HOJE)


def _de(resultado, tipo):
    return [r for r in resultado.registros if isinstance(r, tipo)]


@pytest.fixture
def dispensas(fixture_bytes):
    return pncp.normalizar_contratacoes(
        fixture_bytes("pncp/contratacoes_publicacao_dispensa_20260901_p1.json"), **PROV)


def test_pagina_real_de_dispensas_e_aceita_inteira(dispensas):
    assert dispensas.lidos == 4
    assert dispensas.quarentena == []
    assert len(_de(dispensas, ProcessoContratacao)) == 4


def test_campos_de_sao_sepe(dispensas):
    p = next(x for x in _de(dispensas, ProcessoContratacao) if x.orgao_cnpj == "97229181000164")
    assert p.chave_origem == "97229181000164-1-000406/2026"
    assert p.id == id_canonico("processo_contratacao", "97229181000164-1-000406/2026")
    assert p.modalidade is Modalidade.DISPENSA and p.modalidade_codigo_origem == 8
    assert p.amparo_legal_codigo == 18
    assert p.valor_estimado == Decimal("1640.00")
    assert p.valor_homologado == Decimal("1640.00")
    assert p.publicado_em == datetime(2026, 9, 1, 0, 10, 3, tzinfo=BRT)
    assert p.data_publicacao == date(2026, 9, 1)
    assert p.municipio_codigo_ibge == "4319604" and p.uf == "RS"
    assert p.sistema_origem == "LicitaCon - TCE-RS"
    assert p.ente_id == id_canonico("ente_federativo", "4319604")
    # poderId "N" para um município: nulo, com marcação
    assert q.PODER_NAO_INFORMADO in p.marcacoes_qualidade


def test_esfera_nao_se_aplica_vira_nulo_e_ente_fica_sem_resolver(dispensas):
    caixa = next(x for x in _de(dispensas, Orgao) if x.cnpj == "00360305000104")
    assert caixa.esfera is None and caixa.poder is None
    assert caixa.ente_id is None
    assert q.ENTE_NAO_RESOLVIDO in caixa.marcacoes_qualidade


def test_valor_estimado_zero_e_marcado_e_nao_apagado(dispensas):
    funcate = next(x for x in _de(dispensas, ProcessoContratacao) if x.orgao_cnpj == "51619104000110")
    assert funcate.valor_estimado == Decimal("0")
    assert funcate.valor_homologado is None
    assert q.VALOR_ESTIMADO_ZERO in funcate.marcacoes_qualidade
    assert q.VALOR_HOMOLOGADO_AUSENTE in funcate.marcacoes_qualidade


def test_amparo_de_dispensa_por_valor_aponta_para_o_parametro_legal(dispensas):
    amparos = {a.codigo_pncp: a for a in _de(dispensas, AmparoLegal)}
    assert amparos[19].parametro_limite == "dispensa_compras_servicos"
    assert amparos[18].parametro_limite == "dispensa_obras_engenharia"
    assert amparos[19].natureza == "dispensa"
    # Lei 13.303 (estatal), dispensa que não é por valor
    assert amparos[88].parametro_limite is None
    assert amparos[88].natureza == "dispensa"
    # o texto desatualizado do PNCP é guardado como veio, mas não é o limite
    assert "R$ 50.000,00" in amparos[19].descricao_publicada


def test_unidade_gestora_e_preservada(dispensas):
    ugs = {u.orgao_cnpj: u for u in _de(dispensas, UnidadeGestora)}
    ug = ugs["97229181000164"]
    assert ug.codigo == "05005"
    assert ug.id == id_canonico("unidade_gestora", "97229181000164", "05005")


def test_mesmo_artefato_gera_os_mesmos_registros(fixture_bytes):
    """RF-NO-11: idempotência, inclusive dos ids."""
    bruto = fixture_bytes("pncp/contratacoes_publicacao_dispensa_20260901_p1.json")
    a = pncp.normalizar_contratacoes(bruto, **PROV)
    b = pncp.normalizar_contratacoes(bruto, **PROV)
    assert [r.para_dict() for r in a.registros] == [r.para_dict() for r in b.registros]


def test_pregao_com_datas_de_proposta(fixture_bytes):
    r = pncp.normalizar_contratacoes(
        fixture_bytes("pncp/contratacoes_publicacao_pregao_20260901_p1.json"), **PROV)
    p = _de(r, ProcessoContratacao)[0]
    assert p.modalidade is Modalidade.PREGAO
    assert p.abertura_propostas_em == datetime(2026, 8, 25, 8, 0, 1, tzinfo=BRT)
    assert p.atualizado_em == datetime(2026, 10, 1, 0, 3, 43, tzinfo=BRT)
    assert _de(r, AmparoLegal)[0].natureza == "licitacao"


def test_detalhe_da_compra(fixture_bytes):
    r = pncp.normalizar_contratacao_detalhe(
        fixture_bytes("pncp/compra_97229181000164_2026_406.json"), **PROV)
    assert len(_de(r, ProcessoContratacao)) == 1


def test_itens_e_resultado(fixture_bytes):
    chave = "97229181000164-1-000406/2026"
    itens = pncp.normalizar_itens(fixture_bytes("pncp/compra_97229181000164_2026_406_itens.json"),
                                  processo_chave_origem=chave, **PROV)
    lista = _de(itens, ItemContratacao)
    assert [i.numero_item for i in lista] == [1, 2, 3]
    assert lista[1].valor_unitario_estimado == Decimal("900.0000")
    assert sum(i.valor_total_estimado for i in lista) == Decimal("1640")
    assert all(i.processo_id == id_canonico("processo_contratacao", chave) for i in lista)

    res = pncp.normalizar_resultados(
        fixture_bytes("pncp/compra_97229181000164_2026_406_item1_resultados.json"),
        processo_chave_origem=chave, **PROV)
    r = _de(res, ResultadoItem)[0]
    assert r.item_id == lista[0].id
    assert r.fornecedor_documento == "43590137000156"
    assert r.fornecedor_tipo_pessoa is TipoPessoa.JURIDICA
    assert r.valor_unitario_homologado == Decimal("40.0000")
    assert r.data_resultado == date(2026, 8, 26)


def test_contratos_reais(fixture_bytes):
    r = pncp.normalizar_contratos(fixture_bytes("pncp/contratos_20260901_p1.json"),
                                  **{**PROV, "fonte_id": "pncp_contratos"})
    assert r.quarentena == []
    contratos = {c.chave_origem: c for c in _de(r, Contrato)}
    xique = contratos["13880257000127-2-000239/2026"]
    assert xique.tipo_instrumento == "Contrato (termo inicial)"
    assert xique.valor_parcela == Decimal("2860.8")
    assert xique.fornecedor_documento == "44281151000130"   # MEI: CNPJ, dado público
    assert xique.processo_id == id_canonico("processo_contratacao", "13880257000127-1-000062/2026")
    ceara = contratos["07954480000179-2-031780/2026"]
    assert ceara.tipo_instrumento == "Empenho"
    assert ceara.valor_acumulado == Decimal("0")


def test_orgao_estadual_na_capital_tem_o_estado_como_ente(fixture_bytes):
    """Secretaria estadual em Fortaleza: o código IBGE é da capital, o ente é o Ceará."""
    r = pncp.normalizar_contratos(fixture_bytes("pncp/contratos_20260901_p1.json"), **PROV)
    ceara = next(o for o in _de(r, Orgao) if o.cnpj == "07954480000179")
    assert ceara.esfera is Esfera.ESTADUAL
    assert ceara.ente_codigo_ibge == "23"
    assert ceara.ente_id == id_canonico("ente_federativo", "23")


def test_ata_com_vigencia_no_ano_7203_vai_para_a_quarentena(fixture_bytes):
    r = pncp.normalizar_atas(fixture_bytes("pncp/atas_20260901_p1.json"), **PROV)
    assert r.lidos == 2
    assert len(_de(r, AtaRegistroPreco)) == 1
    assert len(r.quarentena) == 1
    entrada = r.quarentena[0]
    assert entrada.chave_origem == "45780103000150-1-000001/2023-000001"
    assert entrada.campo == "vigenciaFim"
    assert "7203-07-27" in entrada.valor_recebido
    assert entrada.posicao == 1


def test_pagina_vazia_204_nao_gera_nada():
    r = pncp.normalizar_contratacoes(b"", **PROV)
    assert r.lidos == 0 and r.registros == [] and r.quarentena == []


@pytest.mark.parametrize("fixture", [
    "pncp/erro_400_parametro_ausente.json",
    "pncp/erro_422_janela_maior_que_365_dias.json",
])
def test_resposta_de_erro_preservada_no_bronze_nao_vira_registro(fixture_bytes, fixture):
    r = pncp.normalizar_contratacoes(fixture_bytes(fixture), **PROV)
    assert r.registros == []
    assert len(r.quarentena) == 1 and "data" in r.quarentena[0].motivo


def test_json_ilegivel_vai_para_quarentena():
    r = pncp.normalizar_contratacoes(b"<html>manutencao</html>", **PROV)
    assert r.registros == [] and "JSON ilegível" in r.quarentena[0].motivo


def _minimo(**extra):
    base = {
        "numeroControlePNCP": "97229181000164-1-000001/2026",
        "orgaoEntidade": {"cnpj": "97229181000164", "razaoSocial": "X", "esferaId": "M", "poderId": "E"},
        "unidadeOrgao": {"codigoIbge": "4319604", "codigoUnidade": "1", "ufSigla": "RS"},
        "anoCompra": 2026, "sequencialCompra": 1, "objetoCompra": "objeto",
        "dataPublicacaoPncp": "2026-09-01T10:00:00", "modalidadeId": 8,
    }
    base.update(extra)
    return base


def _pagina(*itens):
    import json
    return json.dumps({"data": list(itens), "totalRegistros": len(itens)}).encode()


@pytest.mark.parametrize("extra,campo,motivo", [
    ({"objetoCompra": None}, "objetoCompra", "obrigatório"),
    ({"objetoCompra": "   "}, "objetoCompra", "obrigatório"),
    ({"anoCompra": None}, "anoCompra", "obrigatório"),
    ({"sequencialCompra": None}, "sequencialCompra", "obrigatório"),
    ({"dataPublicacaoPncp": None}, "dataPublicacaoPncp", "obrigatório"),
    ({"dataPublicacaoPncp": "31/02/2026"}, "dataPublicacaoPncp", "ilegível"),
    ({"valorTotalEstimado": -5}, "valorTotalEstimado", "negativo"),
    ({"valorTotalEstimado": "abc"}, "valorTotalEstimado", "numérico"),
    ({"orgaoEntidade": {"cnpj": "97229181000165"}}, "orgaoEntidade.cnpj", "verificador"),
    ({"orgaoEntidade": {}}, "orgaoEntidade.cnpj", "obrigatório"),
    ({"numeroControlePNCP": None}, "numeroControlePNCP", "obrigatório"),
])
def test_quarentena_com_campo_e_motivo(extra, campo, motivo):
    r = pncp.normalizar_contratacoes(_pagina(_minimo(**extra)), **PROV)
    assert r.registros == []
    assert r.quarentena[0].campo == campo
    assert motivo in r.quarentena[0].motivo


def test_um_registro_ruim_nao_derruba_o_lote():
    r = pncp.normalizar_contratacoes(_pagina(_minimo(objetoCompra=None), _minimo()), **PROV)
    assert r.lidos == 2 and r.aceitos == 1
    assert len(_de(r, ProcessoContratacao)) == 1


def test_modalidade_nova_do_pncp_nao_derruba_o_registro():
    r = pncp.normalizar_contratacoes(_pagina(_minimo(modalidadeId=99)), **PROV)
    p = _de(r, ProcessoContratacao)[0]
    assert p.modalidade is None and p.modalidade_codigo_origem == 99
    assert q.MODALIDADE_DESCONHECIDA in p.marcacoes_qualidade


def test_poder_e_esfera_mapeados():
    r = pncp.normalizar_contratacoes(_pagina(_minimo()), **PROV)
    o = _de(r, Orgao)[0]
    assert o.esfera is Esfera.MUNICIPAL and o.poder is Poder.EXECUTIVO
    assert o.marcacoes_qualidade == []


@pytest.mark.parametrize("esfera,ibge,esperado", [
    (Esfera.MUNICIPAL, "4319604", "4319604"),
    (Esfera.ESTADUAL, "2304400", "23"),
    (Esfera.DISTRITAL, "5300108", "53"),
    (Esfera.UNIAO, None, "1"),
    (None, "4319604", None),
    (Esfera.MUNICIPAL, None, None),
    (Esfera.MUNICIPAL, "43", None),
])
def test_resolver_ente(esfera, ibge, esperado):
    assert pncp.resolver_ente(esfera, ibge) == esperado


def test_fornecedor_pessoa_fisica_tem_cpf_mascarado_na_origem():
    import json
    contrato = {
        "numeroControlePNCP": "97229181000164-2-000001/2026",
        "orgaoEntidade": {"cnpj": "97229181000164", "esferaId": "M", "poderId": "E"},
        "unidadeOrgao": {"codigoIbge": "4319604", "codigoUnidade": "1"},
        "anoContrato": 2026, "sequencialContrato": 1, "objetoContrato": "serviço",
        "tipoPessoa": "PF", "niFornecedor": "52998224725", "nomeRazaoSocialFornecedor": "Fulano",
    }
    r = pncp.normalizar_contratos(json.dumps({"data": [contrato]}).encode(), **PROV)
    c = _de(r, Contrato)[0]
    assert c.fornecedor_documento == "***.982.247-**"
    assert "52998224725" not in json.dumps(c.para_dict())
    assert c.fornecedor_tipo_pessoa is TipoPessoa.FISICA


def test_documento_de_fornecedor_invalido_e_marcado():
    import json
    contrato = {
        "numeroControlePNCP": "97229181000164-2-000002/2026",
        "orgaoEntidade": {"cnpj": "97229181000164", "esferaId": "M", "poderId": "E"},
        "unidadeOrgao": {"codigoIbge": "4319604"},
        "anoContrato": 2026, "sequencialContrato": 2, "objetoContrato": "serviço",
        "tipoPessoa": "PJ", "niFornecedor": "123",
    }
    r = pncp.normalizar_contratos(json.dumps({"data": [contrato]}).encode(), **PROV)
    c = _de(r, Contrato)[0]
    assert c.fornecedor_documento is None and c.fornecedor_id is None
    assert q.DOCUMENTO_FORNECEDOR_INVALIDO in c.marcacoes_qualidade
    assert c.unidade_gestora_id is None  # sem codigoUnidade não há UG


@pytest.mark.parametrize("descricao,natureza", [
    ("Dispensa de Licitação: para contratação...", "dispensa"),
    ("Inexigibilidade de Licitação: profissional do setor artístico", "inexigibilidade"),
    ("pregão: modalidade de licitação obrigatória", "licitacao"),
    ("Credenciamento: chamamento público", "credenciamento"),
    ("Critério de desempate: sorteio", "criterio_desempate"),
    ("algo novo", None),
    (None, None),
])
def test_natureza_do_amparo(descricao, natureza):
    assert pncp.natureza_do_amparo(500, descricao) == natureza


def test_natureza_por_codigo_quando_a_descricao_falta():
    assert pncp.natureza_do_amparo(19, None) == "dispensa"
