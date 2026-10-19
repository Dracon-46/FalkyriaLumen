"""Testes dos grupos de pares (RF-EN-02)."""

from datetime import datetime, timezone

from lumen_canonico.fato import EnteFederativo, Esfera
from lumen_canonico.pares import MINIMO_ENTES, NACIONAL, VERSAO_PARES, formar_grupos, regiao_do_codigo

AGORA = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)


def _municipio(codigo: int, populacao: int | None) -> EnteFederativo:
    # A região vem do código (1 N, 2 NE, 3 SE, 4 S, 5 CO); o campo regiao, de propósito, diz outra coisa
    return EnteFederativo(id=f"m{codigo}", codigo_ibge=str(codigo), nome=f"M{codigo}", esfera=Esfera.MUNICIPAL,
                          uf="XX", regiao="SU", populacao=populacao)


def _municipios(inicio: int, quantos: int, populacao: int) -> list[EnteFederativo]:
    return [_municipio(inicio + i, populacao) for i in range(quantos)]


def test_municipios_do_mesmo_porte_e_regiao_formam_grupo_regional():
    entes = _municipios(2100000, MINIMO_ENTES, 4_000)
    r = formar_grupos(entes, AGORA)
    assert len(r.grupos) == 1
    g = r.grupos[0]
    assert (g.esfera, g.faixa_populacional, g.regiao) == ("municipal", "ate_5_mil", "NE")
    assert g.quantidade_entes == MINIMO_ENTES and not g.abaixo_do_minimo
    assert all(r.grupo_de[e.codigo_ibge] == g.id for e in entes)
    assert g.criterios["versao"] == VERSAO_PARES and "motivo" not in g.criterios
    assert "não usada" in g.criterios["receita_corrente_liquida"]


def test_grupo_regional_pequeno_cai_para_o_porte_no_pais():
    grandes_ne = _municipios(2100000, MINIMO_ENTES, 600_000)
    grandes_n = _municipios(1500000, 3, 700_000)
    grandes_co = _municipios(5200000, 2, 800_000)
    r = formar_grupos(grandes_ne + grandes_n + grandes_co, AGORA)
    regional = r.grupo(grandes_ne[0].codigo_ibge)
    nacional = r.grupo(grandes_n[0].codigo_ibge)
    assert regional.regiao == "NE" and nacional.regiao == NACIONAL
    # Norte e Centro-Oeste, os dois abaixo do mínimo, dividem o grupo nacional do porte
    assert r.grupo(grandes_co[0].codigo_ibge) is nacional
    # O grupo nacional é o porte no país inteiro, inclusive os municípios que têm grupo regional
    assert nacional.quantidade_entes == MINIMO_ENTES + 5
    assert "abaixo de 15" in nacional.criterios["motivo"]
    assert len(r.grupos) == 2


def test_grupo_nacional_abaixo_do_minimo_fica_com_ressalva():
    r = formar_grupos(_municipios(3500000, 4, 50_000), AGORA)
    (g,) = r.grupos
    assert g.regiao == NACIONAL and g.abaixo_do_minimo and g.quantidade_entes == 4


def test_estados_e_df_num_grupo_e_a_uniao_fora():
    estados = [EnteFederativo(id=f"e{c}", codigo_ibge=str(c), nome=str(c), esfera=Esfera.ESTADUAL, uf="XX",
                              regiao="SE") for c in (31, 33, 35)]
    df = EnteFederativo(id="df", codigo_ibge="53", nome="DF", esfera=Esfera.DISTRITAL, uf="DF", regiao="CO")
    uniao = EnteFederativo(id="u", codigo_ibge="1", nome="União", esfera=Esfera.UNIAO, uf=None)
    r = formar_grupos([*estados, df, uniao], AGORA)
    (g,) = r.grupos
    assert g.esfera == "estadual" and g.faixa_populacional is None and g.membros == ("31", "33", "35", "53")
    assert r.grupo_de["53"] == g.id
    assert r.fora == {"1": "a União não tem entes comparáveis"}
    assert r.grupo("1") is None


def test_sem_populacao_ou_com_codigo_invalido_fica_fora_sem_inferencia():
    sem_pop = _municipio(1200001, None)
    sem_regiao = _municipio(9200002, 3_000)
    sem_esfera = EnteFederativo(id="x", codigo_ibge="1200003", nome="X", esfera=None, uf="AC")
    r = formar_grupos([sem_pop, sem_regiao, sem_esfera], AGORA)
    assert r.grupos == [] and r.grupo_de == {}
    assert r.fora == {"1200001": "população desconhecida", "9200002": "código IBGE de município inválido",
                      "1200003": "esfera desconhecida"}


def test_id_do_grupo_depende_da_celula_e_nao_dos_membros_nem_da_data():
    a = formar_grupos(_municipios(4100000, MINIMO_ENTES, 15_000), AGORA).grupos[0]
    b = formar_grupos(_municipios(4200000, MINIMO_ENTES + 3, 18_000), datetime(2027, 1, 1)).grupos[0]
    assert a.id == b.id and a.membros != b.membros
    outro = formar_grupos(_municipios(3100000, MINIMO_ENTES, 15_000), AGORA).grupos[0]
    assert outro.id != a.id


def test_regiao_pelo_codigo_ibge():
    assert [regiao_do_codigo(c) for c in ("1302603", "2611606", "3550308", "4314902", "5300108")] == [
        "N", "NE", "SE", "S", "CO"]
    assert regiao_do_codigo("35") is None and regiao_do_codigo("6000000") is None and regiao_do_codigo("1") is None


def test_descricao_do_grupo():
    from lumen_canonico.pares import ROTULOS_FAIXA, descrever
    from lumen_canonico.porte import FAIXAS
    assert set(ROTULOS_FAIXA) == {rotulo for _, rotulo in FAIXAS}
    regional = formar_grupos(_municipios(4100000, MINIMO_ENTES, 30_000), AGORA).grupos[0]
    assert descrever(regional) == "Municípios de 20 mil a 50 mil habitantes do Sul"
    nacional = formar_grupos(_municipios(1100000, 2, 600_000), AGORA).grupos[0]
    assert descrever(nacional) == "Municípios acima de 500 mil habitantes de todo o país"
    estados = formar_grupos([EnteFederativo(id="e", codigo_ibge="43", nome="RS", esfera=Esfera.ESTADUAL, uf="RS")],
                            AGORA).grupos[0]
    assert descrever(estados) == "Estados e Distrito Federal"
