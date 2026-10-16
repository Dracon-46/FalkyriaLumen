"""Coletor ao vivo contra a apuração simulada (arquivos reais do TSE, etapas fictícias)."""

from __future__ import annotations

import json
import shutil
import urllib.request
from pathlib import Path

import pytest

from lumen_eleicoes import tse
from lumen_eleicoes.coletor import ColetorAoVivo, plano_padrao
from lumen_eleicoes.feeds import EscritorFeeds
from lumen_eleicoes.simulacao import Cenario, ServidorSimulado
from lumen_ingestao.bronze import ArmazemBronzeLocal
from lumen_ingestao.cliente_http import ClienteHttp

FIX = Path(__file__).resolve().parents[3] / "testes" / "fixtures" / "tse"
UA = "Lumen/teste (+contato@exemplo.org)"


def cliente():
    return ClienteHttp("tse_resultados", user_agent=UA, rpm=60000, dormir=lambda s: None,
                       abridor=urllib.request.build_opener(urllib.request.ProxyHandler({})))


def eleicao(eid: str):
    return {e.id: e for e in tse.ler_catalogo((FIX / "ele-c_recorte.json").read_bytes())}[eid]


def ler(raiz: Path, *partes) -> dict:
    return json.loads(raiz.joinpath(*partes).read_text(encoding="utf-8"))


@pytest.fixture
def ambiente(tmp_path):
    cen = Cenario(FIX, etapas=3)
    with ServidorSimulado(cen) as srv:
        yield cen, srv, tmp_path


def montar(srv, tmp_path, eid="2026-1t-geral", **kw):
    plano = plano_padrao(eleicao(eid), simulacao=True, **kw)
    escritor = EscritorFeeds(tmp_path / "feeds")
    bronze = ArmazemBronzeLocal(tmp_path / "bronze")
    return ColetorAoVivo(cliente(), escritor, plano, bronze=bronze, base=srv.base,
                         estado=tmp_path / "estado" / "coleta.json"), escritor, bronze


def test_plano_padrao_de_eleicao_geral():
    e = eleicao("2026-1t-geral")
    plano = plano_padrao(e)
    assert "zz" in plano.ufs and "sp" in plano.ufs and len(plano.ufs) == 28
    assert 1 in plano.municipios_para and 3 in plano.municipios_para
    assert 6 not in plano.municipios_para                 # proporcional estadual: só se pedido
    assert plano_padrao(e, municipios_proporcionais=True).municipios_para >= {6, 7}
    assert plano.fotos_para == {1, 3, 5}                  # conselheiro distrital é municipal
    grupos = plano.grupos()
    assert [c.slug for c in grupos[6257]] == ["presidente"]
    assert 6261 in grupos
    with pytest.raises(ValueError):
        plano_padrao(e, cargos=["prefeito"])


def test_plano_padrao_municipal():
    t2 = plano_padrao(eleicao("2024-2t-municipal"))
    assert t2.ufs == ["am", "sp"]
    t1 = plano_padrao(eleicao("2024-1t-municipal"))
    assert "df" not in t1.ufs and "zz" not in t1.ufs
    assert t1.municipios_para == {11, 13}                 # vereador só existe por município


def test_noite_simulada_do_inicio_ao_fim(ambiente):
    cen, srv, tmp = ambiente
    coletor, escritor, bronze = montar(srv, tmp, cargos=["presidente", "governador", "deputado-federal"],
                                       ufs=["sp"])
    r1 = coletor.passada()
    assert not r1.erros, r1.erros
    assert r1.baixados >= 4 and r1.ausentes >= 1          # há arquivos de UF que o recorte não tem
    br1 = ler(escritor.raiz, "2026-1t-geral", "presidente", "br.json")
    assert br1["ao_vivo"] is True and br1["origem"]["simulacao"] is True
    assert br1["totalizacao"]["pct_secoes"] == pytest.approx(33.33, abs=0.01)
    cores_1 = {c["numero"]: c["cor"] for c in br1["candidatos"]}
    assert br1["origem"]["registro_bronze"]
    indice = ler(escritor.raiz, "indice.json")
    assert indice["eleicoes"][0]["ao_vivo"] is True and indice["eleicoes"][0]["simulacao"] is True
    assert [c["slug"] for c in indice["eleicoes"][0]["cargos"]] == ["presidente", "governador", "deputado-federal"]

    # Sem avançar: tudo volta 304, nada é regravado
    r_igual = coletor.passada()
    assert r_igual.baixados == 0 and r_igual.nao_modificados >= 4 and r_igual.feeds == 0

    cen.avancar()
    coletor.passada()
    cen.avancar()
    r3 = coletor.passada()
    assert not r3.erros
    br3 = ler(escritor.raiz, "2026-1t-geral", "presidente", "br.json")
    final = tse.ler_resultado((FIX / "br-c0001-e006257-u.json").read_bytes())
    assert {c["numero"]: c["votos"] for c in br3["candidatos"]} == {c.numero: c.votos for c in final.candidatos}
    # As cores não mudam durante a noite, mesmo que a ordem mude
    assert {c["numero"]: c["cor"] for c in br3["candidatos"]} == cores_1

    evolucao = ler(escritor.raiz, "2026-1t-geral", "presidente", "historico-br.json")
    assert len(evolucao["pontos"]) == 3
    assert evolucao["pontos"][-1]["votos"]["22"] == 56104503
    assert [round(p["pct_secoes"]) for p in evolucao["pontos"]] == [33, 67, 100]

    gov = ler(escritor.raiz, "2026-1t-geral", "governador", "uf-sp.json")
    assert gov["candidatos"][0]["eleito"] is True and gov["ao_vivo"] is False
    dep = ler(escritor.raiz, "2026-1t-geral", "deputado-federal", "uf-sp.json")
    assert dep["quociente_eleitoral"] == 338203

    # Município de SP fora do recorte do cadastro: entra pela chave TSE
    mu = ler(escritor.raiz, "2026-1t-geral", "presidente", "mu-sp-61000.json")
    assert mu["candidatos"][0]["numero"] == "13"
    # cor do município segue a do Brasil
    assert mu["candidatos"][0]["cor"] == cores_1["13"]
    # Prova: cada resposta 200 está no bronze
    assert sum(1 for _ in bronze.listar_registros("tse_resultados")) >= r1.baixados


def test_executar_encerra_e_desliga_ao_vivo(ambiente):
    cen, srv, tmp = ambiente
    coletor, escritor, _ = montar(srv, tmp, cargos=["governador"], ufs=["sp"])
    avisos = []

    def dormir(_s):
        cen.avancar()

    coletor.executar(intervalo_s=0, max_passadas=10, dormir=dormir, aviso=avisos.append)
    # Governador de SP finaliza na última etapa: o coletor para sozinho
    assert avisos[-1].finalizada
    assert len(avisos) == 3
    assert ler(escritor.raiz, "indice.json")["eleicoes"][0]["ao_vivo"] is False


def test_estado_sobrevive_a_reinicio(ambiente):
    cen, srv, tmp = ambiente
    coletor, escritor, _ = montar(srv, tmp, cargos=["presidente"], ufs=["sp"])
    coletor.passada()
    cores = dict(coletor.estado.cores["1/br"])
    cen.avancar()
    novo, _, _ = montar(srv, tmp, cargos=["presidente"], ufs=["sp"])
    assert novo.estado.cores["1/br"] == cores
    assert len(novo.estado.evolucao["1/br"]) == 1
    novo.passada()
    assert len(novo.estado.evolucao["1/br"]) == 2


def test_orcamento_municipal_e_fila(tmp_path):
    cen = Cenario(FIX, etapas=1)
    with ServidorSimulado(cen) as srv:
        coletor, escritor, _ = montar(srv, tmp_path, cargos=["presidente"], ufs=["sp"], orcamento_municipal=1)
        r = coletor.passada()
        # O -ab de SP lista três municípios; um por passada
        assert r.pendentes_municipais == 2
        coletor.passada()
        r3 = coletor.passada()
        assert r3.pendentes_municipais == 0


def test_eleicao_municipal_gera_panoramas(tmp_path):
    arquivos = tmp_path / "tse"
    arquivos.mkdir()
    shutil.copy(FIX / "ele-c_recorte.json", arquivos / "ele-c.json")
    shutil.copy(FIX / "sp71072-c0011-e000619-u.json", arquivos)
    (arquivos / "sp-e000619-ab.json").write_text(json.dumps({"abr": [
        {"tpabr": "mun", "cdabr": "71072", "and": "f", "dt": "06/10/2024", "ht": "22:00:00",
         "s": {"ts": "26513", "st": "26513", "pst": "100,00"}}]}))
    (arquivos / "mun-e000619-cm.json").write_text(json.dumps({"abr": [
        {"cd": "sp", "mu": [{"cd": "71072", "cdi": "3550308", "nm": "SÃO PAULO", "c": "s", "z": ["0001"]}]}]}))
    cen = Cenario(arquivos, etapas=2)
    with ServidorSimulado(cen) as srv:
        coletor, escritor, _ = montar(srv, tmp_path, eid="2024-1t-municipal", cargos=["prefeito"], ufs=["sp"])
        coletor.passada()
        cen.avancar()
        r = coletor.passada()
        assert r.finalizada
    mu = ler(escritor.raiz, "2024-1t-municipal", "prefeito", "mu-3550308.json")
    assert [c["numero"] for c in mu["candidatos"] if c["segundo_turno"]] == ["15", "50"]
    pan = ler(escritor.raiz, "2024-1t-municipal", "prefeito", "uf-sp.json")
    assert pan["tipo"] == "panorama" and pan["partes"][0]["partido"] == "MDB"
    nacional = ler(escritor.raiz, "2024-1t-municipal", "prefeito", "br.json")
    assert nacional["partes"][0]["codigo"] == "sp"


def test_falha_de_rede_vira_erro_sem_derrubar(tmp_path):
    e = eleicao("2026-1t-geral")
    plano = plano_padrao(e, cargos=["presidente"], ufs=["sp"])
    c = ClienteHttp("tse_resultados", user_agent=UA, rpm=60000, dormir=lambda s: None,
                    abridor=urllib.request.build_opener(urllib.request.ProxyHandler({})), timeout=1)
    from lumen_ingestao.cliente_http import PoliticaRetentativa
    c.politica = PoliticaRetentativa(max_tentativas=1, falhas_para_suspender=1000)
    coletor = ColetorAoVivo(c, EscritorFeeds(tmp_path), plano, base="http://127.0.0.1:9/oficial")
    r = coletor.passada()
    assert r.erros and r.baixados == 0


def test_executar_para_quando_estavel_sem_marca_de_finalizada(ambiente, monkeypatch):
    """Rondônia em 2026: 100% das seções e o TSE sem ``tf = "s"``; o coletor para depois do tempo estável."""
    cen, srv, tmp = ambiente
    coletor, _, _ = montar(srv, tmp, cargos=["governador"], ufs=["sp"])
    monkeypatch.setattr(coletor, "_finalizada", lambda: False)
    agora = [0.0]

    def dormir(_s):
        cen.avancar()
        agora[0] += 600

    avisos = []
    coletor.executar(intervalo_s=0, max_passadas=20, dormir=dormir, aviso=avisos.append, estavel_s=1800,
                     relogio=lambda: agora[0])
    assert coletor.secoes_completas()
    assert coletor.pendentes_ao_parar == []          # a fixture marca tudo como finalizado no fim
    assert 3 < len(avisos) < 20                       # parou pela estabilidade, não pelo limite de passadas
    limite = len(avisos) + 3                          # max_passadas conta as passadas desde o início
    coletor.executar(intervalo_s=0, max_passadas=limite, dormir=dormir, estavel_s=None, relogio=lambda: agora[0])
    assert coletor.passadas == limite                 # sem a parada por estabilidade, vai até o limite


def test_sem_marca_de_finalizada_lista_os_resultados(ambiente):
    cen, srv, tmp = ambiente
    coletor, _, _ = montar(srv, tmp, cargos=["governador"], ufs=["sp"])
    coletor.passada()
    assert not coletor.secoes_completas()             # primeira etapa da fixture: apuração parcial
    assert coletor.sem_marca_de_finalizada() == sorted(k for k in coletor.ultimo if "/mu-" not in k)
