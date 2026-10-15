"""Dados abertos do TSE: leitura dos CSV, agregação e geração dos feeds históricos.

Duas fontes de teste:

- as linhas reais em ``testes/fixtures/tse/dados_abertos`` (cabeçalho e
  primeiras linhas dos arquivos de 2022), que garantem que o leitor entende
  o formato publicado;
- arquivos sintéticos montados aqui com o mesmo cabeçalho, pequenos o
  bastante para conferir as somas à mão. Os números sintéticos não são de
  eleição nenhuma: servem para testar a aritmética.
"""

from __future__ import annotations

import csv
import io
import json
import zipfile
from pathlib import Path

import pytest

from lumen_eleicoes import dados_abertos as da
from lumen_eleicoes import tse
from lumen_eleicoes.feeds import EscritorFeeds
from lumen_eleicoes.historico import ProcessadorAno
from lumen_eleicoes.municipios import CadastroMunicipios

FIX = Path(__file__).resolve().parents[3] / "testes" / "fixtures" / "tse"
DA = FIX / "dados_abertos"


def cabecalho(nome: str) -> list[str]:
    with open(DA / nome, encoding="latin-1", newline="") as fh:
        return next(csv.reader(fh, delimiter=";"))


CAB_VOTACAO = cabecalho("votacao_candidato_munzona_2022_CE_inicio.csv")
CAB_DETALHE = cabecalho("detalhe_votacao_munzona_2022_BRASIL_inicio.csv")


def csv_bytes(cab: list[str], linhas: list[dict]) -> bytes:
    saida = io.StringIO()
    w = csv.writer(saida, delimiter=";", quoting=csv.QUOTE_ALL, lineterminator="\r\n")
    w.writerow(cab)
    for linha in linhas:
        w.writerow([linha.get(c, "#NULO#") for c in cab])
    return saida.getvalue().encode("latin-1")


def voto(ano, turno, abr, uf, ue, mun, nome_mun, zona, cargo, sq, nr, urna, partido, votos, *,
         validos=None, destino="Válido", situacao="NÃO ELEITO", coligacao="PARTIDO ISOLADO",
         transito="N", tipo=2, cd_eleicao=546):
    return {
        "DT_GERACAO": "04/10/2026", "HH_GERACAO": "03:16:54", "ANO_ELEICAO": ano, "CD_TIPO_ELEICAO": tipo,
        "NM_TIPO_ELEICAO": "Eleição Ordinária", "NR_TURNO": turno, "CD_ELEICAO": cd_eleicao,
        "DS_ELEICAO": "ELEIÇÃO DE TESTE", "DT_ELEICAO": "02/10/2022" if ano == 2022 else "06/10/2024",
        "TP_ABRANGENCIA": abr, "SG_UF": uf, "SG_UE": ue, "NM_UE": "TESTE", "CD_MUNICIPIO": mun,
        "NM_MUNICIPIO": nome_mun, "NR_ZONA": zona, "CD_CARGO": cargo, "DS_CARGO": "Cargo",
        "SQ_CANDIDATO": sq, "NR_CANDIDATO": nr, "NM_CANDIDATO": f"NOME COMPLETO {urna}",
        "NM_URNA_CANDIDATO": urna, "SG_PARTIDO": partido, "NM_COLIGACAO": coligacao,
        "DS_COMPOSICAO_COLIGACAO": partido, "ST_VOTO_EM_TRANSITO": transito, "QT_VOTOS_NOMINAIS": votos,
        "NM_TIPO_DESTINACAO_VOTOS": destino,
        "QT_VOTOS_NOMINAIS_VALIDOS": votos if validos is None else validos, "DS_SIT_TOT_TURNO": situacao,
    }


def detalhe(ano, turno, abr, uf, ue, mun, zona, cargo, *, aptos, comp, validos, brancos, nulos,
            legenda=0, anulados=0, tipo=2, secoes=10):
    return {
        "DT_GERACAO": "05/10/2026", "HH_GERACAO": "04:36:32", "ANO_ELEICAO": ano, "CD_TIPO_ELEICAO": tipo,
        "NM_TIPO_ELEICAO": "Eleição Ordinária", "NR_TURNO": turno, "CD_ELEICAO": 546, "DS_ELEICAO": "X",
        "DT_ELEICAO": "02/10/2022", "TP_ABRANGENCIA": abr, "SG_UF": uf, "SG_UE": ue, "NM_UE": "X",
        "CD_MUNICIPIO": mun, "NM_MUNICIPIO": "X", "NR_ZONA": zona, "CD_CARGO": cargo, "DS_CARGO": "X",
        "QT_APTOS": aptos, "QT_TOTAL_SECOES": secoes, "QT_COMPARECIMENTO": comp, "QT_ABSTENCOES": aptos - comp,
        "ST_VOTO_EM_TRANSITO": "N", "QT_VOTOS": comp, "QT_TOTAL_VOTOS_VALIDOS": validos,
        "QT_VOTOS_NOMINAIS_VALIDOS": validos - legenda, "QT_TOTAL_VOTOS_LEG_VALIDOS": legenda,
        "QT_VOTOS_LEG_VALIDOS": legenda, "QT_TOTAL_VOTOS_ANULADOS": anulados, "QT_VOTOS_BRANCOS": brancos,
        "QT_TOTAL_VOTOS_NULOS": nulos, "QT_VOTOS_NULOS": nulos, "QT_VOTOS_NULOS_TECNICOS": 0,
        "QT_TOTAL_VOTOS_ANUL_SUBJUD": 0, "HH_ULTIMA_TOTALIZACAO": "20:12:54", "DT_ULTIMA_TOTALIZACAO": "02/10/2022",
    }


# ------------------------------------------------------------------ cenário 2022 (sintético)

def presidente():
    p = dict(ano=2022, turno=1, abr="F", ue="BR")
    return [
        voto(**p, uf="AC", mun=1120, nome_mun="ACRELÂNDIA", zona=8, cargo=1, sq="1", nr=22, urna="ALFA", partido="PA", votos=100),
        voto(**p, uf="AC", mun=1120, nome_mun="ACRELÂNDIA", zona=8, cargo=1, sq="2", nr=13, urna="BETA", partido="PB", votos=50),
        voto(**p, uf="AC", mun=1120, nome_mun="ACRELÂNDIA", zona=9, cargo=1, sq="1", nr=22, urna="ALFA", partido="PA", votos=10),
        voto(**p, uf="AC", mun=1120, nome_mun="ACRELÂNDIA", zona=9, cargo=1, sq="2", nr=13, urna="BETA", partido="PB", votos=40),
        voto(**p, uf="AC", mun=1570, nome_mun="ASSIS BRASIL", zona=6, cargo=1, sq="1", nr=22, urna="ALFA", partido="PA", votos=5),
        voto(**p, uf="AC", mun=1570, nome_mun="ASSIS BRASIL", zona=6, cargo=1, sq="2", nr=13, urna="BETA", partido="PB", votos=30),
        voto(**p, uf="SP", mun=71072, nome_mun="SÃO PAULO", zona=1, cargo=1, sq="1", nr=22, urna="ALFA", partido="PA", votos=300),
        voto(**p, uf="SP", mun=71072, nome_mun="SÃO PAULO", zona=1, cargo=1, sq="2", nr=13, urna="BETA", partido="PB", votos=200),
        voto(**p, uf="SP", mun=71072, nome_mun="SÃO PAULO", zona=1, cargo=1, sq="2", nr=13, urna="BETA", partido="PB", votos=5, transito="S"),
        voto(**p, uf="SP", mun=71072, nome_mun="SÃO PAULO", zona=1, cargo=1, sq="3", nr=99, urna="GAMA", partido="PC", votos=20, validos=0, destino="Anulado"),
        voto(**p, uf="ZZ", mun=29254, nome_mun="ABIDJÃ", zona=1, cargo=1, sq="1", nr=22, urna="ALFA", partido="PA", votos=3),
        voto(**p, uf="ZZ", mun=29254, nome_mun="ABIDJÃ", zona=1, cargo=1, sq="2", nr=13, urna="BETA", partido="PB", votos=7),
        # Linha de eleição suplementar no mesmo arquivo: fica fora
        voto(**{**p, "abr": "F"}, uf="AC", mun=1120, nome_mun="ACRELÂNDIA", zona=8, cargo=1, sq="1", nr=22, urna="ALFA", partido="PA", votos=999, tipo=1),
    ]


def estaduais_ac():
    e = dict(ano=2022, turno=1, abr="E", uf="AC", ue="AC")
    return [
        voto(**e, mun=1120, nome_mun="ACRELÂNDIA", zona=8, cargo=3, sq="10", nr=45, urna="DELTA", partido="PD", votos=80, situacao="ELEITO"),
        voto(**e, mun=1120, nome_mun="ACRELÂNDIA", zona=8, cargo=3, sq="11", nr=10, urna="ÉPSILON", partido="PE", votos=60),
        voto(**e, mun=1570, nome_mun="ASSIS BRASIL", zona=6, cargo=3, sq="10", nr=45, urna="DELTA", partido="PD", votos=10, situacao="ELEITO"),
        voto(**e, mun=1570, nome_mun="ASSIS BRASIL", zona=6, cargo=3, sq="11", nr=10, urna="ÉPSILON", partido="PE", votos=25),
        voto(**e, mun=1120, nome_mun="ACRELÂNDIA", zona=8, cargo=6, sq="20", nr=4501, urna="ZETA", partido="PD", votos=30, situacao="ELEITO POR QP"),
        voto(**e, mun=1120, nome_mun="ACRELÂNDIA", zona=8, cargo=6, sq="21", nr=1301, urna="ETA", partido="PB", votos=20, situacao="SUPLENTE"),
        voto(**e, mun=1570, nome_mun="ASSIS BRASIL", zona=6, cargo=6, sq="22", nr=1302, urna="TETA", partido="PB", votos=15, situacao="SUPLENTE"),
        voto(**e, mun=1570, nome_mun="ASSIS BRASIL", zona=6, cargo=6, sq="21", nr=1301, urna="ETA", partido="PB", votos=12, situacao="SUPLENTE"),
    ]


def detalhes_2022():
    br = dict(ano=2022, turno=1, abr="F", ue="BR", cargo=1)
    ac = dict(ano=2022, turno=1, abr="E", uf="AC", ue="AC")
    return [
        detalhe(**br, uf="AC", mun=1120, zona=8, aptos=200, comp=160, validos=150, brancos=5, nulos=5),
        detalhe(**br, uf="AC", mun=1120, zona=9, aptos=60, comp=55, validos=50, brancos=3, nulos=2),
        detalhe(**br, uf="AC", mun=1570, zona=6, aptos=50, comp=40, validos=35, brancos=4, nulos=1),
        detalhe(**br, uf="SP", mun=71072, zona=1, aptos=600, comp=540, validos=505, brancos=10, nulos=5, anulados=20),
        detalhe(**br, uf="ZZ", mun=29254, zona=1, aptos=20, comp=12, validos=10, brancos=1, nulos=1),
        detalhe(**ac, mun=1120, zona=8, cargo=3, aptos=200, comp=160, validos=140, brancos=10, nulos=10),
        detalhe(**ac, mun=1570, zona=6, cargo=3, aptos=50, comp=40, validos=35, brancos=3, nulos=2),
        detalhe(**ac, mun=1120, zona=8, cargo=6, aptos=200, comp=160, validos=55, brancos=50, nulos=55, legenda=5),
        detalhe(**ac, mun=1570, zona=6, cargo=6, aptos=50, comp=40, validos=30, brancos=5, nulos=5, legenda=3),
    ]


def zip_de(caminho: Path, arquivos: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(caminho, "w", zipfile.ZIP_DEFLATED) as zf:
        for nome, conteudo in arquivos.items():
            zf.writestr(nome, conteudo)
        zf.writestr("leiame.pdf", b"%PDF-1.4")
    return caminho


@pytest.fixture
def zips_2022(tmp_path):
    pres = presidente()
    votacao = zip_de(tmp_path / "votacao_candidato_munzona_2022.zip", {
        "votacao_candidato_munzona_2022_BR.csv": csv_bytes(CAB_VOTACAO, pres),
        # O arquivo da UF repete as linhas de Presidente; devem ser ignoradas
        "votacao_candidato_munzona_2022_AC.csv": csv_bytes(CAB_VOTACAO, estaduais_ac() + pres[:6]),
        "votacao_candidato_munzona_2022_BRASIL.csv": csv_bytes(CAB_VOTACAO, pres + estaduais_ac()),
    })
    det = detalhes_2022()
    detalhe_zip = zip_de(tmp_path / "detalhe_votacao_munzona_2022.zip", {
        "detalhe_votacao_munzona_2022_BR.csv": csv_bytes(CAB_DETALHE, det[:5]),
        "detalhe_votacao_munzona_2022_AC.csv": csv_bytes(CAB_DETALHE, det[5:] + det[:2]),
    })
    return votacao, detalhe_zip


@pytest.fixture
def cadastro():
    return CadastroMunicipios.de_tse(tse.ler_municipios((FIX / "mun-e006257-cm_recorte.json").read_bytes()),
                                     {"1200013": "Acrelândia", "1200054": "Assis Brasil", "3550308": "São Paulo"})


# ------------------------------------------------------------------ endereços e CKAN

def test_urls_dos_conjuntos():
    assert da.url_conjunto(da.CONJUNTO_VOTACAO, 2022) == (
        "https://cdn.tse.jus.br/estatistica/sead/odsele/votacao_candidato_munzona/votacao_candidato_munzona_2022.zip")
    assert da.url_pacote(2020).endswith("package_show?id=resultados-2020")
    assert da.url_historico_presidente(2022, 2).endswith("eleicoes2022/Historico_Totalizacao_Presidente_BR_2T_2022.zip")
    assert da.tipo_do_ano(2022) == "geral" and da.tipo_do_ano(2024) == "municipal"
    assert da.ANOS_GERAIS[0] == 1994 and da.ANOS_MUNICIPAIS[-1] == 2024


def test_pacote_ckan_classificado_pela_url():
    resposta = {"success": True, "result": {"resources": [
        {"name": "Votação nominal por município e zona", "url": da.url_conjunto(da.CONJUNTO_VOTACAO, 2022), "format": "CSV"},
        {"name": "Detalhe", "url": da.url_conjunto(da.CONJUNTO_DETALHE, 2022), "format": "CSV"},
        {"name": "BR - Histórico", "url": da.url_historico_presidente(2022, 1), "format": "CSV"},
        {"name": "Seção", "url": "https://cdn.tse.jus.br/estatistica/sead/odsele/votacao_secao/votacao_secao_2022_AC.zip"},
        {"name": "sem url"},
    ]}}
    grupos = da.classificar_recursos(da.ler_pacote(json.dumps(resposta)))
    assert len(grupos[da.CONJUNTO_VOTACAO]) == 1
    assert len(grupos[da.CONJUNTO_DETALHE]) == 1
    assert len(grupos["historico_totalizacao"]) == 1
    assert len(grupos["outros"]) == 1
    with pytest.raises(ValueError):
        da.ler_pacote({"success": False, "error": {"message": "Not found"}})


def test_entradas_pula_brasil_e_poe_br_primeiro():
    nomes = ["x_2022_SP.csv", "x_2022_BRASIL.csv", "x_2022_BR.csv", "leiame.pdf", "x_2022_AC.csv"]
    assert da.entradas_csv(nomes) == ["x_2022_BR.csv", "x_2022_AC.csv", "x_2022_SP.csv"]
    assert da.entradas_csv(["x_2024_BRASIL.csv", "leiame.pdf"]) == ["x_2024_BRASIL.csv"]
    assert da.tem_arquivo_br(nomes) and not da.tem_arquivo_br(["x_2024_AC.csv"])


# ------------------------------------------------------------------ linhas reais

def test_linhas_reais_de_votacao_2022():
    agg = da.AgregadorVotacao()
    with open(DA / "votacao_candidato_munzona_2022_CE_inicio.csv", "rb") as fh:
        agg.ler(fh)
    assert agg.linhas_lidas == 3
    chave = ("2022-1t-geral", 6, ("uf", "ce"))
    r = agg.resultado(chave, None)
    assert {c.numero for c in r.candidatos} == {"7001", "7011", "7020"}
    marcos = next(c for c in r.candidatos if c.numero == "7011")
    assert (marcos.nome_urna, marcos.partido, marcos.votos, marcos.situacao) == ("DR MARCOS", "AVANTE", 4, "Não eleito")
    assert marcos.agremiacao == "AVANTE"            # partido isolado
    assert agg.datas["2022-1t-geral"].isoformat() == "2022-10-02"
    assert agg.codigos_tse[("2022-1t-geral", 6)] == 546
    # Sem detalhe da apuração para o recorte: avisa e usa a soma dos candidatos
    assert da.AVISO_SEM_DETALHE in r.avisos
    assert r.votos.validos == 6
    # Município com código TSE zerado à esquerda (14435 → "14435")
    assert ("2022-1t-geral", 6, ("mu", "ce", "14435")) in agg.votos


def test_linhas_reais_de_detalhe_2022():
    with open(DA / "detalhe_votacao_munzona_2022_BRASIL_inicio.csv", "rb") as fh:
        totais = da.ler_detalhe([("detalhe_votacao_munzona_2022_BR.csv", fh)], pular_presidente_nos_estados=True)
    br = totais[("2022-1t-geral", 1, ("br",))]
    assert br.aptos == 4071 + 3209
    assert br.comparecimento == 2779 + 2638
    assert br.validos == 2631 + 2553
    assert br.brancos == 37 + 25 and br.nulos == 111 + 60
    assert br.ultima_totalizacao.hour == 20
    mg = totais[("2022-1t-geral", 1, ("mu", "mg", "40061"))]
    assert mg.aptos == 4071 and mg.secoes == 14


def test_historico_totalizacao_real():
    with open(DA / "Historico_Totalizacao_Presidente_BR_1T_2022_inicio.csv", "rb") as fh:
        pontos = da.ler_historico_totalizacao(fh)
    assert len(pontos) == 3
    p = pontos[0]
    assert p.instante.isoformat() == "2022-10-02T17:04:47-03:00"
    assert p.votos["LULA"] == 31612 and p.votos["JAIR_BOLSONARO"] == 19974
    assert "BRANCO" not in p.votos and "NULO" not in p.votos
    assert p.pct_secoes == pytest.approx(0.0405)
    assert pontos[-1].votos["LULA"] == 70889


def test_reducao_preserva_extremos():
    assert da.reduzir(list(range(10)), 20) == list(range(10))
    r = da.reduzir(list(range(1000)), 5)
    assert r[0] == 0 and r[-1] == 999 and len(r) == 5


def test_casar_rotulo_do_historico():
    from lumen_eleicoes.modelo import Candidato

    def c(n, urna):
        return Candidato(numero=n, sq=None, nome=urna, nome_urna=urna, partido=None, agremiacao=None,
                         composicao=None, votos=0, pct_validos=None, situacao="", eleito=False,
                         segundo_turno=False, destinacao="Válido")
    cands = [c("13", "LULA"), c("22", "JAIR BOLSONARO"), c("30", "FELIPE D'AVILA"), c("15", "SIMONE TEBET")]
    assert da.casar_rotulo("LULA", cands) == "13"
    assert da.casar_rotulo("JAIR_BOLSONARO", cands) == "22"
    assert da.casar_rotulo("FELIPE_DAVILA", cands) == "30"
    assert da.casar_rotulo("NINGUEM", cands) is None


def test_formato_sem_colunas_minimas():
    with pytest.raises(da.FormatoNaoReconhecido):
        da.AgregadorVotacao().ler(io.BytesIO(b'"A";"B"\r\n"1";"2"\r\n'))
    with pytest.raises(da.FormatoNaoReconhecido):
        da.AgregadorVotacao().ler(io.BytesIO(b""))


def test_situacoes_publicadas():
    assert da.situacao_publicada("ELEITO POR QP") == "Eleito por QP"
    assert da.situacao_publicada("2º TURNO") == "2º turno"
    assert da.situacao_publicada("#NULO#") == ""
    assert da.situacao_publicada("RENUNCIOU") == "Renunciou"


# ------------------------------------------------------------------ anos com layout antigo

def test_layout_de_2014_sem_destinacao_avisa(tmp_path):
    # 2014: 38 colunas, sem QT_VOTOS_NOMINAIS_VALIDOS nem destinação
    cab = [c for c in CAB_VOTACAO if c not in ("QT_VOTOS_NOMINAIS_VALIDOS", "NM_TIPO_DESTINACAO_VOTOS",
                                               "NR_FEDERACAO", "NM_FEDERACAO", "SG_FEDERACAO",
                                               "DS_COMPOSICAO_FEDERACAO")]
    linhas = [voto(2014, 1, "E", "AC", "AC", 1120, "ACRELÂNDIA", 8, 3, "1", 50, "X", "PX", 7)]
    agg = da.AgregadorVotacao()
    agg.ler(io.BytesIO(csv_bytes(cab, linhas)))
    r = agg.resultado(("2014-1t-geral", 3, ("uf", "ac")), None)
    assert r.candidatos[0].votos == 7
    assert r.candidatos[0].destinacao is None and r.candidatos[0].valido
    assert da.AVISO_SEM_DESTINACAO in r.avisos


def test_layout_de_2000_voto_so_na_coluna_de_validos():
    linhas = [voto(2000, 1, "M", "MA", "09610", 9610, "ACAILANDIA", 71, 11, "41", 15, "DEUSDETE", "PMDB", 0,
                   validos=11657, destino="#NE")]
    agg = da.AgregadorVotacao()
    agg.ler(io.BytesIO(csv_bytes(CAB_VOTACAO, linhas)))
    r = agg.resultado(("2000-1t-municipal", 11, ("mu", "ma", "09610")), None)
    assert r.candidatos[0].votos == 11657
    assert r.candidatos[0].valido


def test_totais_de_1994_sao_reconciliados():
    t = da.Totais(aptos=4704, comparecimento=3967, abstencoes=737, validos=0, nominais_validos=1813,
                  brancos=1271, nulos=0, nulos_simples=807)
    t.reconciliar()
    assert t.validos == 1813 and t.nulos == 807 and t.votos == 1813 + 1271 + 807
    assert t.reconciliado


# ------------------------------------------------------------------ processamento completo

def ler_feed(raiz: Path, *partes: str) -> dict:
    return json.loads((raiz.joinpath(*partes)).read_text(encoding="utf-8"))


def test_processa_eleicao_geral_sintetica(zips_2022, cadastro, tmp_path):
    votacao, detalhe_zip = zips_2022
    saida = tmp_path / "feeds"
    proc = ProcessadorAno(2022, EscritorFeeds(saida), cadastro)
    resumo = proc.processar(votacao, detalhe_zip)
    assert resumo.eleicoes == ["2022-1t-geral"]
    assert resumo.arquivos == 2                     # _BR e _AC; o _BRASIL fica de fora

    br = ler_feed(saida, "2022-1t-geral", "presidente", "br.json")
    assert br["versao"] == 1 and br["tipo"] == "resultado"
    votos = {c["numero"]: c["votos"] for c in br["candidatos"]}
    # 22: 100+10+5+300+3 ; 13: 50+40+30+200+5(trânsito)+7 ; a suplementar (999) fica de fora
    assert votos == {"22": 418, "13": 332, "99": 20}
    assert [c["numero"] for c in br["candidatos"]] == ["22", "13", "99"]   # anulado por último
    anulado = br["candidatos"][2]
    assert anulado["valido"] is False and anulado["pct"] is None
    assert br["votos"]["validos"] == 150 + 50 + 35 + 505 + 10
    assert br["comparecimento"]["eleitorado"] == 200 + 60 + 50 + 600 + 20
    assert br["candidatos"][0]["pct"] == pytest.approx(100 * 418 / 750)
    assert br["candidatos"][0]["cor"] == 0 and br["candidatos"][1]["cor"] == 1
    partes = {p["codigo"]: p for p in br["partes"]}
    assert set(partes) == {"ac", "sp", "zz"}
    assert partes["ac"]["lider"] == "13" and partes["ac"]["cor"] == 1        # 120 x 115
    assert partes["sp"]["lider"] == "22"
    assert partes["ac"]["ibge"] == "12"
    assert br["origem"]["fonte"] == "dados_abertos"

    ac = ler_feed(saida, "2022-1t-geral", "presidente", "uf-ac.json")
    assert {c["numero"]: c["votos"] for c in ac["candidatos"]} == {"13": 120, "22": 115}
    mu = {p["codigo"]: p for p in ac["partes"]}
    assert set(mu) == {"1200013", "1200054"}
    assert mu["1200013"]["lider"] == "22" and mu["1200013"]["cor"] == 0      # 110 x 90
    assert mu["1200054"]["nome"] == "Assis Brasil"

    sp_capital = ler_feed(saida, "2022-1t-geral", "presidente", "mu-3550308.json")
    assert sp_capital["abrangencia"]["tse"] == "71072"
    assert sp_capital["votos"]["anulados"] == 20
    exterior = ler_feed(saida, "2022-1t-geral", "presidente", "mu-zz-29254.json")
    assert exterior["abrangencia"]["ibge"] is None

    gov = ler_feed(saida, "2022-1t-geral", "governador", "uf-ac.json")
    assert gov["candidatos"][0]["numero"] == "45" and gov["candidatos"][0]["eleito"]
    assert gov["cargo"]["vagas"] == 1

    # Cargo estadual visto do Brasil: panorama por UF
    gov_br = ler_feed(saida, "2022-1t-geral", "governador", "br.json")
    assert gov_br["tipo"] == "panorama"
    assert [(p["codigo"], p["lider"], p["partido"], p["eleito"]) for p in gov_br["partes"]] == [("ac", "45", "PD", True)]
    assert gov_br["partidos"] == [{"partido": "PD", "liderados": 1, "eleitos": 1, "votos": 90, "cor": 0}]
    dep_br = ler_feed(saida, "2022-1t-geral", "deputado-federal", "br.json")
    assert dep_br["partes"][0]["bancada"] == {"PD": 1}
    assert {p["partido"]: p["eleitos"] for p in dep_br["partidos"]} == {"PB": 0, "PD": 1}

    dep = ler_feed(saida, "2022-1t-geral", "deputado-federal", "uf-ac.json")
    assert {c["numero"]: c["votos"] for c in dep["candidatos"]} == {"4501": 30, "1301": 32, "1302": 15}
    assert dep["votos"]["legenda"] == 8
    assert [a["nome"] for a in dep["agremiacoes"]] == ["PD", "PB"]           # PD elegeu 1
    partes_dep = {p["codigo"]: p for p in dep["partes"]}
    assert partes_dep["1200013"]["lider"] == "PD"                            # por partido
    assert partes_dep["1200054"]["lider"] == "PB"

    indice = ler_feed(saida, "indice.json")
    e = indice["eleicoes"][0]
    assert e["id"] == "2022-1t-geral" and e["origem"] == "dados_abertos" and e["ao_vivo"] is False
    assert [c["slug"] for c in e["cargos"]] == ["presidente", "governador", "deputado-federal"]
    assert e["data"] == "2022-10-02"
    assert e["ufs"] == ["ac", "sp", "zz"]
    assert e["nome"] == "Eleições Gerais 2022 — 1º turno"


def test_reprocessar_gera_os_mesmos_bytes(zips_2022, cadastro, tmp_path):
    votacao, detalhe_zip = zips_2022
    a, b = tmp_path / "a", tmp_path / "b"
    ProcessadorAno(2022, EscritorFeeds(a), cadastro).processar(votacao, detalhe_zip)
    ProcessadorAno(2022, EscritorFeeds(b), cadastro).processar(votacao, detalhe_zip)
    arquivos_a = sorted(p.relative_to(a) for p in a.rglob("*.json") if p.name != "indice.json")
    arquivos_b = sorted(p.relative_to(b) for p in b.rglob("*.json") if p.name != "indice.json")
    assert arquivos_a == arquivos_b and arquivos_a
    for rel in arquivos_a:
        assert (a / rel).read_bytes() == (b / rel).read_bytes(), rel


def test_processa_municipal_com_panorama(tmp_path):
    m = dict(ano=2024, turno=1, abr="M", uf="AP", cd_eleicao=619)
    linhas = [
        voto(**m, ue="06130", mun=6130, nome_mun="LARANJAL DO JARI", zona=7, cargo=11, sq="1", nr=12, urna="UM", partido="PDT", votos=3000, situacao="ELEITO"),
        voto(**m, ue="06130", mun=6130, nome_mun="LARANJAL DO JARI", zona=7, cargo=11, sq="2", nr=15, urna="DOIS", partido="MDB", votos=2000),
        voto(**m, ue="06009", mun=6009, nome_mun="MUNICÍPIO B", zona=1, cargo=11, sq="3", nr=40, urna="TRÊS", partido="PSB", votos=50000, situacao="2º TURNO"),
        voto(**m, ue="06009", mun=6009, nome_mun="MUNICÍPIO B", zona=1, cargo=11, sq="4", nr=22, urna="QUATRO", partido="PL", votos=40000, situacao="2º TURNO"),
        voto(**m, ue="06009", mun=6009, nome_mun="MUNICÍPIO B", zona=1, cargo=11, sq="5", nr=12, urna="CINCO", partido="PDT", votos=10000),
        voto(**m, ue="06130", mun=6130, nome_mun="LARANJAL DO JARI", zona=7, cargo=13, sq="6", nr=12111, urna="SEIS", partido="PDT", votos=340, situacao="SUPLENTE"),
        voto(**m, ue="06130", mun=6130, nome_mun="LARANJAL DO JARI", zona=7, cargo=13, sq="7", nr=12456, urna="SETE", partido="PDT", votos=261, situacao="ELEITO POR QP"),
        voto(**m, ue="06130", mun=6130, nome_mun="LARANJAL DO JARI", zona=7, cargo=13, sq="8", nr=15000, urna="OITO", partido="MDB", votos=500, situacao="ELEITO POR MÉDIA"),
    ]
    votacao = zip_de(tmp_path / "v.zip", {"votacao_candidato_munzona_2024_AP.csv": csv_bytes(CAB_VOTACAO, linhas),
                                          "votacao_candidato_munzona_2024_BRASIL.csv": csv_bytes(CAB_VOTACAO, linhas)})
    saida = tmp_path / "feeds"
    proc = ProcessadorAno(2024, EscritorFeeds(saida), CadastroMunicipios())
    resumo = proc.processar(votacao, None)
    assert resumo.eleicoes == ["2024-1t-municipal"]
    # Municípios fora do cadastro: entram sem IBGE e ficam registrados
    assert resumo.municipios_sem_ibge == {"ap06130", "ap06009"}

    pan = ler_feed(saida, "2024-1t-municipal", "prefeito", "uf-ap.json")
    assert pan["tipo"] == "panorama"
    placar = {p["partido"]: p for p in pan["partidos"]}
    assert placar["PDT"]["eleitos"] == 1 and placar["PDT"]["liderados"] == 1
    assert placar["PSB"]["eleitos"] == 0 and placar["PSB"]["liderados"] == 1
    assert pan["partidos"][0]["partido"] == "PDT" and pan["partidos"][0]["cor"] == 0
    linhas_mu = {p["codigo"]: p for p in pan["partes"]}
    assert linhas_mu["ap-06009"]["segundo_turno"] is True
    assert linhas_mu["ap-06009"]["nome"] == "Município B"

    nacional = ler_feed(saida, "2024-1t-municipal", "prefeito", "br.json")
    assert nacional["tipo"] == "panorama"
    assert [p["codigo"] for p in nacional["partes"]] == ["ap"]
    assert nacional["partes"][0]["partido"] == "PDT"
    assert nacional["totalizacao"]["partes"] == 2

    ver = ler_feed(saida, "2024-1t-municipal", "vereador", "mu-ap-06130.json")
    assert ver["cargo"]["vagas"] == 2
    assert {a["nome"]: a["vagas"] for a in ver["agremiacoes"]} == {"PDT": 1, "MDB": 1}
    pan_ver = ler_feed(saida, "2024-1t-municipal", "vereador", "uf-ap.json")
    assert pan_ver["partes"][0]["partido"] == "PDT"                          # 601 x 500 votos nominais

    pref = ler_feed(saida, "2024-1t-municipal", "prefeito", "mu-ap-06130.json")
    assert pref["candidatos"][0]["eleito"] is True
    indice = ler_feed(saida, "indice.json")
    assert indice["eleicoes"][0]["cargos"][0]["slug"] == "prefeito"


def test_zonas_no_feed_do_municipio(zips_2022, cadastro, tmp_path):
    votacao, detalhe_zip = zips_2022
    saida = tmp_path / "feeds"
    ProcessadorAno(2022, EscritorFeeds(saida), cadastro).processar(votacao, detalhe_zip)

    # Acrelândia tem as zonas 8 e 9 no Presidente: o feed do município leva as duas em `partes`
    acre = ler_feed(saida, "2022-1t-geral", "presidente", "mu-1200013.json")
    zonas = {p["codigo"]: p for p in acre["partes"]}
    assert list(zonas) == ["8", "9"]
    z8, z9 = zonas["8"], zonas["9"]
    assert (z8["nome"], z8["ibge"], z8["lider"], z8["cor"], z8["eleitorado"]) == ("Zona 8", None, "22", 0, 200)
    assert z8["pct"] == pytest.approx(100 * 100 / 150) and z8["margem"] == pytest.approx(100 * 50 / 150)
    assert (z9["lider"], z9["cor"], z9["eleitorado"]) == ("13", 1, 60)       # as cores são as do Brasil
    assert z9["pct"] == pytest.approx(80.0) and z9["finalizada"] is True
    # A soma das zonas é o município
    assert {c["numero"]: c["votos"] for c in acre["candidatos"]} == {"22": 110, "13": 90}

    # Município de uma zona só: nada a dividir
    assert ler_feed(saida, "2022-1t-geral", "presidente", "mu-1200054.json")["partes"] == []
    assert ler_feed(saida, "2022-1t-geral", "presidente", "mu-3550308.json")["partes"] == []
    # No Governador, Acrelândia só tem linhas da zona 8: sem partes
    assert ler_feed(saida, "2022-1t-geral", "governador", "mu-1200013.json")["partes"] == []
    # O feed da UF continua com os municípios, e não com as zonas
    assert {p["codigo"] for p in ler_feed(saida, "2022-1t-geral", "presidente", "uf-ac.json")["partes"]} == {
        "1200013", "1200054"}


def test_municipios_com_zonas_saem_do_detalhe():
    assert da.zona_da_linha("0008") == "8" and da.zona_da_linha("#NULO#") is None and da.zona_da_linha("0") is None
    t = da.Totais()
    totais = {("e", 1, ("zn", "ac", "01120", "8")): t, ("e", 1, ("zn", "ac", "01120", "9")): t,
              ("e", 1, ("zn", "ac", "01570", "6")): t, ("e", 3, ("zn", "ac", "01570", "6")): t,
              ("e", 1, ("mu", "ac", "01120")): t}
    assert da.municipios_com_zonas(totais) == {("ac", "01120")}
    assert da.abrangencias_da_linha(1, "ac", "01120", "8")[-1] == ("zn", "ac", "01120", "8")
    # Sem a lista de municípios com zonas, o agregador não soma por zona
    agg = da.AgregadorVotacao()
    agg.ler(io.BytesIO(csv_bytes(CAB_VOTACAO, presidente())))
    assert not any(k[2][0] == "zn" for k in agg.votos)
    agg = da.AgregadorVotacao(zonas_de={("ac", "01120")})
    agg.ler(io.BytesIO(csv_bytes(CAB_VOTACAO, presidente())))
    assert sorted(k[2] for k in agg.votos if k[2][0] == "zn") == [("zn", "ac", "01120", "8"), ("zn", "ac", "01120", "9")]


def test_zonas_de_cargo_proporcional_sem_bancada(tmp_path):
    m = dict(ano=2024, turno=1, abr="M", uf="AP", ue="06009", mun=6009, nome_mun="MUNICÍPIO B", cd_eleicao=619)
    linhas = [
        voto(**m, zona=2, cargo=13, sq="1", nr=12111, urna="UM", partido="PDT", votos=300, situacao="ELEITO POR QP"),
        voto(**m, zona=2, cargo=13, sq="2", nr=15111, urna="DOIS", partido="MDB", votos=100, situacao="SUPLENTE"),
        voto(**m, zona=10, cargo=13, sq="1", nr=12111, urna="UM", partido="PDT", votos=50, situacao="ELEITO POR QP"),
        voto(**m, zona=10, cargo=13, sq="2", nr=15111, urna="DOIS", partido="MDB", votos=150, situacao="SUPLENTE"),
    ]
    d = dict(ano=2024, turno=1, abr="M", uf="AP", ue="06009", mun=6009, cargo=13)
    detalhes = [detalhe(**d, zona=2, aptos=500, comp=450, validos=400, brancos=30, nulos=20),
                detalhe(**d, zona=10, aptos=250, comp=220, validos=200, brancos=10, nulos=10)]
    votacao = zip_de(tmp_path / "v.zip", {"votacao_candidato_munzona_2024_AP.csv": csv_bytes(CAB_VOTACAO, linhas)})
    det = zip_de(tmp_path / "d.zip", {"detalhe_votacao_munzona_2024_AP.csv": csv_bytes(CAB_DETALHE, detalhes)})
    saida = tmp_path / "feeds"
    ProcessadorAno(2024, EscritorFeeds(saida), CadastroMunicipios()).processar(votacao, det)
    ver = ler_feed(saida, "2024-1t-municipal", "vereador", "mu-ap-06009.json")
    assert [(p["codigo"], p["lider"]) for p in ver["partes"]] == [("2", "PDT"), ("10", "MDB")]   # ordem numérica
    assert all("bancada" not in p for p in ver["partes"])
    assert ver["partes"][1]["pct"] == pytest.approx(75.0) and ver["partes"][1]["eleitorado"] == 250


def test_limite_de_candidatos_no_municipio(tmp_path):
    e = dict(ano=2022, turno=1, abr="E", uf="AC", ue="AC")
    linhas = [voto(**e, mun=1120, nome_mun="ACRELÂNDIA", zona=8, cargo=7, sq=str(i), nr=10000 + i, urna=f"C{i}",
                   partido="PX", votos=100 - i, situacao="ELEITO POR QP" if i == 70 else "SUPLENTE")
              for i in range(80)]
    votacao = zip_de(tmp_path / "v.zip", {"votacao_candidato_munzona_2022_AC.csv": csv_bytes(CAB_VOTACAO, linhas)})
    saida = tmp_path / "f"
    ProcessadorAno(2022, EscritorFeeds(saida), CadastroMunicipios(), limite_candidatos_municipio=50).processar(
        votacao, None)
    mu = ler_feed(saida, "2022-1t-geral", "deputado-estadual", "mu-ac-01120.json")
    numeros = [c["numero"] for c in mu["candidatos"]]
    assert len(numeros) == 51 and "10070" in numeros                        # 50 primeiros + o eleito
    assert mu["candidatos_omitidos"] == 29
    uf = ler_feed(saida, "2022-1t-geral", "deputado-estadual", "uf-ac.json")
    assert len(uf["candidatos"]) == 80 and uf["candidatos_omitidos"] == 0


def test_evolucao_do_presidente(zips_2022, cadastro, tmp_path):
    votacao, detalhe_zip = zips_2022
    saida = tmp_path / "feeds"
    proc = ProcessadorAno(2022, EscritorFeeds(saida), cadastro)
    proc.processar(votacao, detalhe_zip)
    cab = "DT_TOTALIZACAO;PE_SECOES_TOT_ACUMULADO;ALFA_QT_VOTOS_TOT_ACUMULADO;BETA_QT_VOTOS_TOT_ACUMULADO;OUTRO_QT_VOTOS_TOT_ACUMULADO;BRANCO_QT_VOTOS_TOT_ACUMULADO\n"
    corpo = ("02/10/2022 17:00:00;0,1;10;20;1;3\n"
             "02/10/2022 18:00:00;0,5;200;180;2;5\n"
             "02/10/2022 20:00:00;1;418;332;3;9\n")
    assert proc.gravar_evolucao(1, io.BytesIO((cab + corpo).encode("latin-1")))
    h = ler_feed(saida, "2022-1t-geral", "presidente", "historico-br.json")
    assert h["tipo"] == "historico"
    assert [p["pct_secoes"] for p in h["pontos"]] == [10.0, 50.0, 100.0]
    assert h["pontos"][-1]["votos"] == {"22": 418, "13": 332, "OUTRO": 3}
    numeros = [c["numero"] for c in h["candidatos"]]
    assert numeros[:2] == ["22", "13"] and "OUTRO" in numeros
    # Sem a eleição processada, não há o que casar
    assert not ProcessadorAno(2018, EscritorFeeds(saida), cadastro).gravar_evolucao(1, io.BytesIO(b""))
