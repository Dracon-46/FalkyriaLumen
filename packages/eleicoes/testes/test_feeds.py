"""Contrato dos feeds: cores, abrangências, índice, panorama e a amostra versionada."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pytest

from lumen_eleicoes import feeds as f
from lumen_eleicoes import tse
from lumen_eleicoes.modelo import Cargo, Eleicao, TipoCargo
from lumen_eleicoes.municipios import Municipio
from lumen_eleicoes.simulacao import gerar_amostra
from lumen_eleicoes.verificacao import verificar_diretorio, verificar_feed

RAIZ = Path(__file__).resolve().parents[3]
FIX = RAIZ / "testes" / "fixtures" / "tse"
AMOSTRA = RAIZ / "testes" / "fixtures" / "eleicoes_feed"


def eleicao():
    return Eleicao(id="2026-1t-geral", ano=2026, turno=1, tipo="geral", nome="Eleições Gerais 2026 — 1º turno",
                   data=date(2026, 10, 4), ciclo="ele2026", pleito="3220", origem="resultados",
                   cargos=[Cargo(1, "Presidente", TipoCargo.MAJORITARIO, 6257),
                           Cargo(8, "Deputado Distrital", TipoCargo.PROPORCIONAL, 6259),
                           Cargo(25, "Conselheiro Distrital", TipoCargo.MAJORITARIO, 6261)])


# ------------------------------------------------------------------ cores

def test_cores_por_ordem_e_estaveis():
    # Sem partido de cor fixa, a ordem começa depois do azul e do vermelho
    assert f.atribuir_cores(["20", "12", "70"]) == {"20": 2, "12": 3, "70": 4}
    # O 12 passou o 20: cada um mantém a cor
    assert f.atribuir_cores(["12", "20", "70"], {"20": 2, "12": 3, "70": 4}) == {"20": 2, "12": 3, "70": 4}
    # Quem chega pega o menor índice livre
    assert f.atribuir_cores(["14", "20"], {"20": 2, "12": 3}) == {"20": 2, "12": 3, "14": 4}


def test_pl_azul_e_pt_vermelho_sempre():
    partidos = {"22": "PL", "13": "PT", "15": "MDB"}
    # Pela sigla (panoramas e proporcionais) e pelo partido do candidato, em qualquer posição
    assert f.atribuir_cores(["MDB", "PT", "PL"]) == {"MDB": 2, "PT": 1, "PL": 0}
    assert f.atribuir_cores(["15", "13", "22"], partidos=partidos) == {"15": 2, "13": 1, "22": 0}
    # Cor anterior trocada (estado gravado antes da regra) é corrigida, e o azul e o vermelho não ficam com outro
    assert f.atribuir_cores(["13", "15"], {"13": 0, "15": 1}, partidos=partidos) == {"13": 1, "15": 2}
    # Sem PL na disputa, o azul fica sem dono
    assert f.atribuir_cores(["13", "15"], partidos=partidos) == {"13": 1, "15": 2}


def test_partes_guardadas_ganham_a_cor_atual():
    # Parte guardada pela regra anterior (o 13 na posição 0) regravada com as cores de agora
    guardadas = [{"codigo": "a", "lider": "13", "partido": "PT", "cor": 0},
                 {"codigo": "b", "lider": "22", "partido": "PL", "cor": 1},
                 {"codigo": "c", "lider": "99", "partido": "PT", "cor": 5},
                 {"codigo": "d", "lider": None, "cor": -1}]
    cores = f.atribuir_cores(["13", "22"], partidos={"13": "PT", "22": "PL"})
    assert [p["cor"] for p in f.recolorir(guardadas, cores)] == [1, 0, 1, -1]


def test_cores_acabam_em_cinza():
    numeros = [str(i) for i in range(12)]
    cores = f.atribuir_cores(numeros, n=8)
    assert [cores[n] for n in numeros[:6]] == list(range(2, 8))
    assert all(cores[n] == f.SEM_COR for n in numeros[6:])
    # Cor anterior fora da paleta é descartada
    assert f.atribuir_cores(["1"], {"1": 99})["1"] == 2


# ------------------------------------------------------------------ abrangências

def test_abrangencias_e_nomes_de_arquivo():
    assert f.abrangencia_brasil().arquivo == "br"
    sp = f.abrangencia_uf("SP")
    assert (sp.arquivo, sp.nome, sp.ibge, sp.uf) == ("uf-sp", "São Paulo", "35", "sp")
    assert f.abrangencia_uf("zz").nome == "Exterior"
    capital = f.abrangencia_municipio(Municipio("sp", "71072", "3550308", "São Paulo", "SÃO PAULO", True))
    assert (capital.arquivo, capital.tse) == ("mu-3550308", "71072")
    fora = f.abrangencia_municipio(Municipio("zz", "29254", None, "Abidjã", "ABIDJÃ"))
    assert fora.arquivo == "mu-zz-29254"
    with pytest.raises(ValueError):
        f.EscritorFeeds("/tmp").caminho("../x", "presidente", "br")
    with pytest.raises(ValueError):
        f.EscritorFeeds("/tmp").caminho("2026-1t-geral", "Presidente", "br")


# ------------------------------------------------------------------ resultado e partes

def test_feed_resultado_a_partir_do_tse():
    r = tse.ler_resultado((FIX / "br-c0001-e006257-u.json").read_bytes())
    cores = f.cores_dos_candidatos(r)
    feed = f.feed_resultado(eleicao=eleicao(), cargo=eleicao().cargos[0], abr=f.abrangencia_brasil(), resultado=r,
                            cores=cores, origem=f.origem_json("resultados", url="u"), ao_vivo=True,
                            fotos={"280002551544": "fotos/x.jpeg"})
    assert feed["versao"] == 1 and feed["tipo"] == "resultado" and feed["ao_vivo"] is True
    lider = feed["candidatos"][0]
    assert (lider["numero"], lider["votos"], lider["cor"], lider["foto"]) == ("22", 56104503, 0, "fotos/x.jpeg")
    assert lider["pct"] == pytest.approx(47.027772)
    assert feed["atualizado_em"] == "2026-10-05T02:58:39-03:00"
    assert feed["votos"]["validos"] == 119300788
    assert feed["eleicao"]["data"] == "2026-10-04"
    rel = verificar_feed_ok(feed)
    assert rel == []


def verificar_feed_ok(feed):
    from lumen_eleicoes.verificacao import Relatorio
    rel = Relatorio()
    verificar_feed(Path("x.json"), feed, rel)
    return rel.problemas


def test_parte_traz_lider_margem_e_cor():
    r = tse.ler_resultado((FIX / "sp-c0001-e006257-u.json").read_bytes())
    cores = {"22": 0, "13": 1}
    p = f.parte_json(f.abrangencia_uf("sp"), r, cores)
    assert (p["codigo"], p["lider"], p["cor"], p["partido"]) == ("sp", "22", 0, "PL")
    assert p["margem"] == pytest.approx(51.931238 - 38.200510, abs=1e-5)
    assert p["eleitorado"] == 34122892
    vazio = tse.ler_resultado({"carg": [{"cd": "1", "agr": []}]})
    assert f.parte_json(f.abrangencia_uf("ac"), vazio, cores)["lider"] is None


def test_parte_por_partido_nos_proporcionais():
    r = tse.ler_resultado((FIX / "sp-c0006-e006259-u_recorte.json").read_bytes())
    p = f.parte_json(f.abrangencia_uf("sp"), r, {"MISSÃO": 3}, por_partido=True)
    assert p["lider"] == "MISSÃO" and p["cor"] == 3
    assert p["pct"] is not None


def test_candidato_proporcional_herda_cor_do_partido():
    r = tse.ler_resultado((FIX / "sp-c0006-e006259-u_recorte.json").read_bytes())
    c = next(x for x in r.candidatos if x.partido == "MISSÃO")
    assert f.candidato_json(c, r, {"MISSÃO": 2})["cor"] == 2


def test_limite_de_candidatos_preserva_eleitos():
    r = tse.ler_resultado((FIX / "sp-c0005-e006259-u_recorte.json").read_bytes())
    feed = f.feed_resultado(eleicao=eleicao(), cargo=eleicao().cargos[0], abr=f.abrangencia_uf("sp"), resultado=r,
                            cores={}, origem={}, limite_candidatos=1)
    assert [c["numero"] for c in feed["candidatos"]] == ["111", "222"]
    assert feed["candidatos_omitidos"] == len(r.candidatos) - 2


# ------------------------------------------------------------------ panorama

def test_panorama_conta_municipios_e_eleitos():
    partes = [{"codigo": "a", "partido": "PX", "eleito": True, "votos": 10, "finalizada": True},
              {"codigo": "b", "partido": "PY", "eleito": False, "votos": 50, "finalizada": False},
              {"codigo": "c", "partido": "PX", "eleito": False, "votos": 5, "finalizada": True},
              {"codigo": "d", "partido": None}]
    pan = f.feed_panorama(eleicao=eleicao(), cargo=eleicao().cargos[2], abr=f.abrangencia_uf("pe"), partes=partes,
                          origem={}, atualizado_em=datetime(2026, 10, 4, 20, 0, tzinfo=tse.BRT))
    assert [(p["partido"], p["liderados"], p["eleitos"], p["cor"]) for p in pan["partidos"]] == [
        ("PX", 2, 1, 2), ("PY", 1, 0, 3)]
    assert [p["cor"] for p in pan["partes"]] == [2, 3, 2, -1]
    assert pan["totalizacao"] == {"partes": 4, "partes_finalizadas": 2, "pct_partes": 50.0}
    linha = f.parte_de_panorama(f.abrangencia_uf("pe"), pan)
    assert (linha["partido"], linha["liderados"], linha["bancada"], linha["finalizada"]) == ("PX", 2, {"PX": 1}, False)
    vazio = f.parte_de_panorama(f.abrangencia_uf("pe"), {"partidos": [], "totalizacao": {}})
    assert vazio["lider"] is None


# ------------------------------------------------------------------ índice

def test_indice_insere_substitui_e_ordena(tmp_path):
    esc = f.EscritorFeeds(tmp_path)
    e = eleicao()
    esc.atualizar_indice(f.entrada_indice(e, origem="resultados", ao_vivo=True, atualizado_em=None))
    antiga = Eleicao(id="2022-1t-geral", ano=2022, turno=1, tipo="geral", nome="x", data=date(2022, 10, 2),
                     ciclo="", pleito=None, origem="dados_abertos", cargos=[])
    esc.atualizar_indice(f.entrada_indice(antiga, origem="dados_abertos", ao_vivo=False, atualizado_em=None))
    indice = esc.atualizar_indice(f.entrada_indice(e, origem="resultados", ao_vivo=False, atualizado_em=None))
    assert [x["id"] for x in indice["eleicoes"]] == ["2026-1t-geral", "2022-1t-geral"]
    assert indice["eleicoes"][0]["ao_vivo"] is False
    esc.remover_do_indice("2022-1t-geral")
    assert [x["id"] for x in esc.ler_indice()["eleicoes"]] == ["2026-1t-geral"]
    assert f.EscritorFeeds(tmp_path / "vazio").ler_indice()["eleicoes"] == []


def test_indice_esconde_cargo_sem_dado_e_lista_ufs():
    entrada = f.entrada_indice(eleicao(), origem="resultados", ao_vivo=False, atualizado_em=None,
                               ufs_por_cargo={1: set(), 8: {"DF"}})
    assert [(c["slug"], c["ufs"]) for c in entrada["cargos"]] == [("presidente", []), ("deputado-distrital", ["df"])]
    reconstruida = f.eleicao_de_indice(entrada)
    assert reconstruida.cargo("deputado-distrital").tipo is TipoCargo.PROPORCIONAL
    assert reconstruida.data == date(2026, 10, 4)


def test_classificacao_de_cargos():
    assert f.proporcional(6) and f.proporcional(13) and not f.proporcional(1)
    assert f.municipal(11) and f.municipal(25) and not f.municipal(3)
    assert f.nome_eleicao(2024, 2, "municipal") == "Eleições Municipais 2024 — 2º turno"


# ------------------------------------------------------------------ amostra versionada

def test_amostra_versionada_confere_com_o_gerador(tmp_path):
    """A amostra lida pelos testes do portal sai deste gerador, byte a byte.

    Se este teste falhar depois de uma mudança intencional no contrato,
    apague a pasta e regenere com
    ``lumen eleicoes --saida testes/fixtures/eleicoes_feed amostra --sem-referencias``.
    """
    gerar_amostra(FIX, tmp_path)
    gerados = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*.json"))
    versionados = sorted(p.relative_to(AMOSTRA).as_posix() for p in AMOSTRA.rglob("*.json"))
    assert gerados == versionados
    for rel in gerados:
        assert (tmp_path / rel).read_bytes() == (AMOSTRA / rel).read_bytes(), rel


def test_amostra_passa_na_verificacao():
    rel = verificar_diretorio(AMOSTRA)
    assert rel.ok, rel.problemas
    assert rel.arquivos >= 10
    indice = json.loads((AMOSTRA / "indice.json").read_text(encoding="utf-8"))
    assert all(e["amostra"] for e in indice["eleicoes"])


def test_troca_do_arquivo_tenta_de_novo_enquanto_ele_esta_aberto(tmp_path, monkeypatch):
    """No Windows, o feed aberto pelo servidor local não pode ser trocado; a gravação espera e tenta de novo."""
    import lumen_eleicoes.feeds as f
    falhas = iter([PermissionError("em uso"), PermissionError("em uso")])
    original = f.os.replace

    def replace(a, b):
        erro = next(falhas, None)
        if erro:
            raise erro
        original(a, b)
    monkeypatch.setattr(f.os, "replace", replace)
    esperas = []
    destino = tmp_path / "x.json"
    tmp = tmp_path / ".x.tmp"
    tmp.write_text("{}", encoding="utf-8")
    f.substituir_arquivo(tmp, destino, dormir=esperas.append)
    assert destino.read_text(encoding="utf-8") == "{}" and len(esperas) == 2
    tmp.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(f.os, "replace", lambda a, b: (_ for _ in ()).throw(PermissionError("em uso")))
    with pytest.raises(PermissionError):
        f.substituir_arquivo(tmp, destino, tentativas=3, dormir=lambda s: None)

