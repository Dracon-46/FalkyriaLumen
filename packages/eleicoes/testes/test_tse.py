"""Leitura do sistema de divulgação de resultados do TSE, com arquivos reais."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest

from lumen_eleicoes import tse
from lumen_eleicoes.modelo import AndamentoAbrangencia, Nivel, TipoCargo

FIXTURES = Path(__file__).resolve().parents[3] / "testes" / "fixtures" / "tse"


def ler(nome: str) -> bytes:
    return (FIXTURES / nome).read_bytes()


# ------------------------------------------------------------------ URLs


def test_urls_seguem_o_layout_do_sistema_de_resultados():
    assert tse.url_catalogo() == "https://resultados.tse.jus.br/oficial/comum/config/ele-c.json"
    assert tse.url_municipios("ele2026", 6257) == (
        "https://resultados.tse.jus.br/oficial/ele2026/6257/config/mun-e006257-cm.json")
    assert tse.url_resultado("ele2026", 6257, 1, "br") == (
        "https://resultados.tse.jus.br/oficial/ele2026/6257/dados/br/br-c0001-e006257-u.json")
    assert tse.url_resultado("ele2026", 6257, 1, "SP", "61000") == (
        "https://resultados.tse.jus.br/oficial/ele2026/6257/dados/sp/sp61000-c0001-e006257-u.json")
    assert tse.url_andamento("ele2026", 6257, "sp") == (
        "https://resultados.tse.jus.br/oficial/ele2026/6257/dados/sp/sp-e006257-ab.json")
    assert tse.url_foto("ele2026", 6259, "SP", "250002541303") == (
        "https://resultados.tse.jus.br/oficial/ele2026/6259/fotos/sp/250002541303.jpeg")


def test_base_alternativa_para_testes_e_espelhos():
    assert tse.url_catalogo("http://localhost:1") == "http://localhost:1/comum/config/ele-c.json"


# ------------------------------------------------------------------ conversões


@pytest.mark.parametrize("texto, esperado", [
    ("47,03", 47.03), ("100", 100.0), ("0,000970278", 0.000970278), ("1.234,5", 1234.5),
    ("", None), (None, None), ("abc", None), ("  ", None),
])
def test_numero_com_virgula_decimal(texto, esperado):
    assert tse.numero(texto) == esperado


@pytest.mark.parametrize("texto, esperado", [("56104503", 56104503), ("", None), (None, None), ("x", None)])
def test_inteiro(texto, esperado):
    assert tse.inteiro(texto) == esperado


def test_instante_no_horario_de_brasilia():
    t = tse.instante("05/10/2026", "02:58:39")
    assert t == datetime(2026, 10, 5, 2, 58, 39, tzinfo=tse.BRT)
    assert t.utcoffset().total_seconds() == -3 * 3600
    assert tse.instante("05/10/2026", None).hour == 0
    assert tse.instante("05/10/2026", "25:99").hour == 0
    assert tse.instante(None, "10:00:00") is None
    assert tse.data_br("31/02/2026") is None


# ------------------------------------------------------------------ catálogo


@pytest.fixture
def catalogo():
    return {e.id: e for e in tse.ler_catalogo(ler("ele-c_recorte.json"))}


def test_catalogo_agrupa_eleicoes_do_mesmo_dia(catalogo):
    assert set(catalogo) >= {"2026-1t-geral", "2024-1t-municipal", "2024-2t-municipal"}
    geral = catalogo["2026-1t-geral"]
    # Federal (presidente), estadual e o conselho distrital de Fernando de
    # Noronha, que o TSE publica como "municipal", viram uma eleição só.
    assert [c.codigo for c in geral.cargos] == [1, 3, 5, 6, 7, 8, 25]
    assert geral.cargo("presidente").eleicao_tse == 6257
    assert geral.cargo(3).eleicao_tse == 6259
    assert geral.cargo("conselheiro-distrital").eleicao_tse == 6261
    assert geral.data == date(2026, 10, 4)
    assert geral.ciclo == "ele2026"
    assert geral.nome == "Eleições Gerais 2026 — 1º turno"


def test_catalogo_tipos_de_cargo_e_nivel(catalogo):
    geral = catalogo["2026-1t-geral"]
    assert geral.cargo("presidente").tipo is TipoCargo.MAJORITARIO
    assert geral.cargo("presidente").nivel is Nivel.BRASIL
    assert geral.cargo("deputado-federal").tipo is TipoCargo.PROPORCIONAL
    assert geral.cargo("governador").nivel is Nivel.UF
    with pytest.raises(KeyError):
        geral.cargo("prefeito")


def test_catalogo_segundo_turno_municipal_traz_os_municipios(catalogo):
    t2 = catalogo["2024-2t-municipal"]
    assert t2.turno == 2
    assert [c.slug for c in t2.cargos] == ["prefeito"]
    assert t2.abrangencias == ["am", "sp"]


def test_consulta_popular_tem_id_proprio_e_nao_se_mistura(catalogo):
    consultas = [e for e in catalogo.values() if e.tipo == "consulta"]
    assert len(consultas) == 1
    assert consultas[0].id.startswith("2024-1t-consulta-")
    assert consultas[0].abrangencias == ["mg"]
    assert all(c.codigo != 53 for c in catalogo["2024-1t-municipal"].cargos)


def test_catalogo_ordenado_do_mais_recente(catalogo):
    ids = [e.id for e in tse.ler_catalogo(ler("ele-c_recorte.json"))]
    assert ids[0] == "2026-1t-geral"
    assert ids.index("2024-2t-municipal") < ids.index("2024-1t-municipal")


def test_catalogo_aceita_bytes_texto_e_dict():
    bruto = ler("ele-c_recorte.json")
    import json
    assert len(tse.ler_catalogo(bruto)) == len(tse.ler_catalogo(bruto.decode())) == len(
        tse.ler_catalogo(json.loads(bruto)))


# ------------------------------------------------------------------ municípios


def test_municipios_tse_para_ibge():
    municipios = tse.ler_municipios(ler("mun-e006257-cm_recorte.json"))
    por_codigo = {m.codigo_tse: m for m in municipios}
    assert len(municipios) == 9
    sp = por_codigo["71072"]
    assert (sp.uf, sp.codigo_ibge, sp.nome, sp.capital) == ("sp", "3550308", "SÃO PAULO", True)
    assert len(sp.zonas) > 50
    assert por_codigo["01120"].codigo_ibge == "1200013"
    # Exterior: sem código IBGE
    assert por_codigo["29254"].uf == "zz"
    assert por_codigo["29254"].codigo_ibge is None


# ------------------------------------------------------------------ resultados


def test_presidente_brasil_primeiro_turno_2026():
    r = tse.ler_resultado(ler("br-c0001-e006257-u.json"))
    assert (r.eleicao_tse, r.cargo, r.vagas) == (6257, 1, 1)
    assert (r.abrangencia_tipo, r.abrangencia_codigo) == ("br", "br")
    assert len(r.candidatos) == 12
    assert r.lider.numero == "22"
    assert r.lider.votos == 56104503
    assert r.lider.pct_validos == pytest.approx(47.027772356)
    assert r.lider.vice == "ALFREDO GASPAR"
    assert r.votos.validos == 119300788
    assert sum(c.votos for c in r.candidatos) == r.votos.validos
    assert r.votos.brancos == 2300798
    # O total de nulos ("tvn"), com os técnicos à parte: válidos + brancos + nulos fecham o comparecimento
    assert r.votos.nulos == 3674249 and r.votos.nulos_tecnicos == 5246
    assert r.votos.validos + r.votos.brancos + r.votos.nulos == r.comparecimento.comparecimento
    assert r.comparecimento.eleitorado_secoes_nao_instaladas == 423
    assert r.comparecimento.eleitorado == 158745502
    assert r.comparecimento.pct_abstencao == pytest.approx(21.083641906)
    assert r.totalizacao.secoes == r.totalizacao.secoes_totalizadas == 499248
    assert r.totalizacao.finalizada is False          # "tf": "n"
    assert r.totalizacao.matematicamente_definida is True
    assert r.atualizado_em == datetime(2026, 10, 5, 2, 58, 39, tzinfo=tse.BRT)
    # Ordem decrescente de votos
    assert [c.votos for c in r.candidatos] == sorted((c.votos for c in r.candidatos), reverse=True)
    # Sem situação publicada enquanto a totalização não termina
    assert not any(c.eleito or c.segundo_turno for c in r.candidatos)


def test_governador_sp_eleito_no_primeiro_turno():
    r = tse.ler_resultado(ler("sp-c0003-e006259-u.json"))
    assert r.abrangencia_codigo == "sp"
    assert r.totalizacao.finalizada is True
    eleitos = [c for c in r.candidatos if c.eleito]
    assert [c.numero for c in eleitos] == ["10"]
    assert eleitos[0].nome_urna == "TARCÍSIO"
    assert eleitos[0].agremiacao == "CORAGEM PARA SEGUIR AVANÇANDO"
    assert "REPUBLICANOS" in eleitos[0].composicao
    assert sum(c.votos for c in r.candidatos) == r.votos.validos


def test_senador_com_duas_vagas_e_suplentes():
    r = tse.ler_resultado(ler("sp-c0005-e006259-u_recorte.json"))
    assert r.vagas == 2
    eleitos = sorted(c.numero for c in r.candidatos if c.eleito)
    assert eleitos == ["111", "222"]
    derrite = next(c for c in r.candidatos if c.numero == "111")
    assert derrite.vice == "VICENTE SANTINI"      # 1º suplente ("s1")


def test_deputado_federal_traz_quociente_e_agremiacoes():
    r = tse.ler_resultado(ler("sp-c0006-e006259-u_recorte.json"))
    assert r.vagas == 70
    assert r.quociente_eleitoral == 338203
    assert r.votos.legenda == 685880
    nomes = [a.nome for a in r.agremiacoes]
    assert "PARTIDO MISSÃO" in nomes
    missao = next(a for a in r.agremiacoes if a.nome == "PARTIDO MISSÃO")
    assert missao.vagas == 1
    assert missao.tipo == "isolado"


def test_prefeito_sp_2024_segundo_turno_e_voto_anulado():
    r = tse.ler_resultado(ler("sp71072-c0011-e000619-u.json"))
    assert (r.abrangencia_tipo, r.abrangencia_codigo) == ("mu", "71072")
    finalistas = [c.numero for c in r.candidatos if c.segundo_turno]
    assert sorted(finalistas) == ["15", "50"]
    assert r.lider.numero == "15"
    anulado = next(c for c in r.candidatos if c.numero == "27")
    assert anulado.destinacao == "Anulado"
    # O líder considera só votos válidos, mesmo que um anulado tivesse mais.
    validos = [c for c in r.candidatos if c.destinacao == "Válido"]
    assert sum(c.votos for c in validos) == r.votos.validos
    assert r.votos.anulados == 833


def test_presidente_num_municipio():
    r = tse.ler_resultado(ler("sp61000-c0001-e006257-u.json"))
    assert (r.abrangencia_tipo, r.abrangencia_codigo) == ("mu", "61000")
    assert r.lider.numero == "13"
    assert sum(c.votos for c in r.candidatos) == r.votos.validos == 4368


def test_lider_sem_candidatos_validos():
    r = tse.ler_resultado({"carg": [{"cd": "11", "agr": []}]})
    assert r.lider is None
    assert r.candidatos == []
    assert r.cargo == 11


# ------------------------------------------------------------------ andamento


def test_andamento_por_uf_e_por_municipio():
    br = tse.ler_andamento(ler("br-e006257-ab_recorte.json"))
    assert {a.codigo for a in br} == {"ac", "sp", "zz"}
    ac = next(a for a in br if a.codigo == "ac")
    assert (ac.tipo, ac.andamento, ac.secoes, ac.secoes_totalizadas) == ("uf", "f", 2270, 2270)
    assert ac.pct_secoes == 100.0
    sp = tse.ler_andamento(ler("sp-e006257-ab_recorte.json"))
    # O arquivo da UF traz os municípios e a própria UF
    assert sorted(a.tipo for a in sp).count("mun") == len(sp) - 1
    assert {a.codigo for a in sp if a.tipo == "uf"} == {"sp"}
    assert "61000" in {a.codigo for a in sp}


def test_mudaram_detecta_so_quem_avancou():
    agora = tse.ler_andamento(ler("sp-e006257-ab_recorte.json"))
    assert tse.mudaram([], agora) == sorted(a.codigo for a in agora)
    assert tse.mudaram(agora, agora) == []
    alterado = [AndamentoAbrangencia(a.tipo, a.codigo, a.andamento, a.atualizado_em, a.pct_secoes,
                                     (a.secoes_totalizadas or 0) - 1, a.secoes)
                if a.codigo == "61000" else a for a in agora]
    assert tse.mudaram(alterado, agora) == ["61000"]
