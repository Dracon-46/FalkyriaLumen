"""Painel de contratações: o dia compacto, a coleta de um dia e a soma por ente (ADR-028)."""

from __future__ import annotations

import gzip
import json
from datetime import date
from types import SimpleNamespace

import pytest

from lumen_ingestao.coleta_http import ErroColeta
from lumen_painel import comum, contratacoes, dia
from lumen_painel.cadastro import Cadastro, Ente
from lumen_painel.site import Site

DIA = date(2026, 9, 1)


# ------------------------------------------------------------------------------------------ comum

def test_comum_entes_links_e_valores(tmp_path):
    assert [comum.tipo_do_ente(c) for c in ("1", "53", "35", "3550308", "99", "9912345", "", None, "12")] == [
        "uniao", "df", "estado", "municipio", None, None, None, None, "estado"]
    assert comum.uf_do_ente("3550308") == "SP" and comum.uf_do_ente("53") == "DF" and comum.uf_do_ente("1") is None
    assert comum.link_pncp("07854402000100-1-000060/2026") == "https://pncp.gov.br/app/editais/07854402000100/2026/60"
    assert comum.link_pncp("13880257000127-2-000239/2026") == "https://pncp.gov.br/app/contratos/13880257000127/2026/239"
    assert comum.link_pncp("x") is None and comum.link_pncp(None) is None
    assert comum.valor("1966713.60") == 1966713.6 and comum.valor(28608) == 28608.0
    assert comum.valor("") is None and comum.valor(None) is None and comum.valor("abc") is None
    assert comum.somar(0.1, 0.2) == 0.3 and comum.somar(1.0, None) == 1.0
    caminho = comum.gravar_json(tmp_path / "a" / "x.json.gz", {"á": 1}, comprimir=True)
    assert caminho.read_bytes()[:2] == b"\x1f\x8b" and comum.ler_json(caminho) == {"á": 1}
    assert comum.ler_json(comum.gravar_json(tmp_path / "y.json", [1])) == [1]
    assert not list(tmp_path.rglob("*.tmp"))
    assert comum.hoje_brasilia(comum.datetime(2026, 10, 14, 2, 0, tzinfo=comum.timezone.utc)) == date(2026, 10, 13)
    assert comum.instante_utc(comum.datetime(2026, 10, 14, 2, 0, 5, 9, tzinfo=comum.timezone.utc)) == "2026-10-14T02:00:05Z"


def test_site_nao_grava_fora_da_raiz(tmp_path):
    site = Site(tmp_path / "site")
    site.gravar("a/b.json", {"x": 1})
    with pytest.raises(ValueError, match="fora do site"):
        site.gravar("../fora.json", {})
    site.finalizar()
    assert (tmp_path / "site" / ".nojekyll").exists() and site.arquivos == 1
    Site(tmp_path / "site")                       # refeito do zero
    assert not (tmp_path / "site" / "a").exists()


# ------------------------------------------------------------------------------------------ dia

def test_resumir_dia_com_as_respostas_reais(tmp_path, apoio):
    silver = apoio.silver_pncp(tmp_path / "silver")
    d = dia.resumir_dia(silver, DIA, agora="2026-09-02T10:00:00Z")
    assert d["dia"] == "2026-09-01" and d["gerado_em"] == "2026-09-02T10:00:00Z"
    processos = [dict(zip(d["colunas"]["processos"], p)) for p in d["processos"]]
    contratos = [dict(zip(d["colunas"]["contratos"], c)) for c in d["contratos"]]
    assert processos and contratos
    emasa = next(p for p in processos if p["chave"] == "07854402000100-1-000060/2026")
    assert (emasa["ente"], emasa["uf"], emasa["modalidade"], emasa["valor_estimado"]) == ("4202008", "SC", 8, 19977.0)
    caixa = next(p for p in processos if p["orgao"] == "00360305000104")
    assert caixa["ente"] is None                   # órgão sem esfera no PNCP: só no panorama
    assert all(len(p["objeto"] or "") <= dia.LIMITE_OBJETO for p in processos)
    xique = next(c for c in contratos if c["chave"] == "13880257000127-2-000239/2026")
    assert (xique["ente"], xique["tipo_pessoa"], xique["fornecedor_cnpj"], xique["valor_global"]) == (
        "2933604", "PJ", "44281151000130", 28608.0)
    assert d["orgaos"]["07954480000179"] == ["ESTADO DO CEARA", "E", "23"]
    # Outro dia: nada
    vazio = dia.resumir_dia(silver, date(2026, 9, 2))
    assert vazio["processos"] == [] and vazio["contratos"] == [] and vazio["orgaos"] == {}


def test_pessoa_fisica_sem_nome_nem_documento(tmp_path, apoio):
    silver = apoio.silver_pncp(tmp_path / "silver")
    # Troca o primeiro contrato por um de pessoa física na silver
    arquivo = next((silver / "contrato").rglob("*.jsonl"))
    linhas = [json.loads(x) for x in arquivo.read_text(encoding="utf-8").splitlines()]
    linhas[0].update(fornecedor_tipo_pessoa="PF", fornecedor_documento="***.123.456-**", fornecedor_nome="FULANO")
    arquivo.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in linhas) + "\n", encoding="utf-8")
    d = dia.resumir_dia(silver, DIA)
    pf = [dict(zip(d["colunas"]["contratos"], c)) for c in d["contratos"] if c[5] == "PF"]
    assert pf and pf[0]["fornecedor_cnpj"] is None and pf[0]["fornecedor_nome"] is None
    assert "FULANO" not in json.dumps(d, ensure_ascii=False) and "123.456" not in json.dumps(d)


def test_ler_dia_e_dias_guardados(tmp_path, apoio):
    estado = tmp_path / "estado"
    comum.gravar_json(estado / dia.nome_do_arquivo(DIA), dia.resumir_dia(apoio.silver_pncp(tmp_path / "s"), DIA),
                      comprimir=True)
    (estado / "contratacoes-lixo.json.gz").write_bytes(b"")
    assert dia.dias_guardados(estado) == {DIA}
    assert dia.ler_dia(estado / dia.nome_do_arquivo(DIA))["dia"] == "2026-09-01"
    comum.gravar_json(tmp_path / "v2.json", {"versao": 2})
    with pytest.raises(ValueError, match="versão"):
        dia.ler_dia(tmp_path / "v2.json")


def _resumo(guardados=1, falhas=(), erros=0):
    return SimpleNamespace(guardados=[object()] * guardados, falhas=list(falhas), respostas_de_erro=erros)


def test_coletar_dia_grava_so_o_dia_completo(tmp_path, apoio, cfg):
    chamadas = []

    def coletar(c, fonte, janela, **kw):
        chamadas.append((fonte, janela.inicio, janela.fim, kw))
        assert c.raiz_dados != cfg.raiz_dados        # diretório temporário do dia
        return _resumo(3)

    def normalizar(c, fontes):
        assert fontes == list(dia.FONTES)
        apoio.silver_pncp(c.silver)

    estado = tmp_path / "estado"
    r = dia.coletar_dia(cfg, DIA, estado, coletar=coletar, normalizar=normalizar, modalidades=(6, 8))
    assert r.gravado and r.paginas == 6 and r.processos > 0 and r.contratos > 0 and r.problemas == []
    assert chamadas[0] == ("pncp_contratacoes", DIA, DIA, {"modalidades": (6, 8)})
    assert chamadas[1][0] == "pncp_contratos"
    assert (estado / "contratacoes-2026-09-01.json.gz").exists()
    assert not list(tmp_path.glob("painel-*"))      # temporário apagado
    assert r.para_json()["gravado"] is True


@pytest.mark.parametrize("resposta, trecho", [
    (_resumo(falhas=[("u", "x")]), "página(s) com falha"),
    (_resumo(erros=2), "resposta(s) de erro"),
    (ErroColeta("fonte suspensa"), "coleta interrompida"),
])
def test_coletar_dia_incompleto_nao_grava(tmp_path, cfg, resposta, trecho):
    def coletar(c, fonte, janela, **kw):
        if isinstance(resposta, Exception):
            raise resposta
        return resposta

    def normalizar(c, fontes):  # pragma: no cover - não chega a normalizar
        raise AssertionError

    r = dia.coletar_dia(cfg, DIA, tmp_path / "estado", coletar=coletar, normalizar=normalizar,
                        temporario=tmp_path)
    assert not r.gravado and any(trecho in p for p in r.problemas)
    assert not (tmp_path / "estado").exists() or not list((tmp_path / "estado").iterdir())
    assert not list(tmp_path.glob("painel-*"))


# ------------------------------------------------------------------------------------------ soma

def _dia_sintetico(dia_iso: str, processos: list, contratos: list, orgaos: dict) -> dict:
    return {"versao": 1, "dia": dia_iso, "colunas": {"processos": dia.COLUNAS_PROCESSOS,
                                                      "contratos": dia.COLUNAS_CONTRATOS,
                                                      "orgaos": dia.COLUNAS_ORGAOS},
            "orgaos": orgaos, "processos": processos, "contratos": contratos}


def _p(chave, orgao, ente, modalidade=8, estimado=100.0, objeto="obj"):
    return [chave, orgao, ente, None, None, modalidade, estimado, None, objeto, "Divulgada no PNCP", False]


def _c(chave, orgao, ente, tipo="PJ", cnpj="11111111000111", nome="EMPRESA A", valor=50.0):
    return [chave, orgao, ente, None, None, tipo, cnpj, nome, valor, "2026-01-02", None, "Contrato", "obj"]


@pytest.fixture
def estado_sintetico(tmp_path):
    orgaos = {"00000000000100": ["MUNICIPIO X", "M", "3550308"], "00000000000200": ["ESTADO", "E", "35"],
              "00000000000300": ["UNIAO", "F", "1"], "00000000000400": ["SEM ESFERA", None, None]}
    estado = tmp_path / "estado"
    d1 = _dia_sintetico("2026-01-02", [
        _p("00000000000100-1-000001/2026", "00000000000100", "3550308", 8, 100.0),
        _p("00000000000100-1-000002/2026", "00000000000100", "3550308", 6, None),
        _p("00000000000200-1-000001/2026", "00000000000200", "35", 9, 1000.0),
        _p("00000000000400-1-000001/2026", "00000000000400", None, 8, 7.0),
    ], [
        _c("00000000000100-2-000001/2026", "00000000000100", "3550308", valor=60.0),
        _c("00000000000100-2-000002/2026", "00000000000100", "3550308", "PF", None, None, 40.0),
        _c("00000000000300-2-000001/2026", "00000000000300", "1", cnpj="22222222000122", nome="B", valor=500.0),
    ], orgaos)
    d3 = _dia_sintetico("2026-02-04", [
        _p("00000000000100-1-000003/2026", "00000000000100", "3550308", 8, 300.0),
    ], [
        _c("00000000000100-2-000003/2026", "00000000000100", "3550308", nome="EMPRESA A NOVA", valor=90.0),
    ], orgaos)
    comum.gravar_json(estado / "contratacoes-2026-01-02.json.gz", d1, comprimir=True)
    comum.gravar_json(estado / "contratacoes-2026-02-04.json.gz", d3, comprimir=True)
    return estado


def _cadastro():
    return Cadastro({"3550308": Ente("3550308", "São Paulo", "SP", "M", 11_900_000, True),
                     "3509502": Ente("3509502", "Campinas", "SP", "M", 1_100_000),
                     "35": Ente("35", "São Paulo", "SP", "E", 46_000_000)}, "2026-10-14T00:00:00Z")


def test_soma_por_ente_e_panorama(estado_sintetico):
    painel = contratacoes.somar_dias(estado_sintetico.glob("contratacoes-*.json.gz"))
    assert set(painel.entes) == {"3550308", "35", "1"}
    cobertura = painel.cobertura()
    assert (cobertura["de"], cobertura["ate"], cobertura["dias"]) == ("2026-01-02", "2026-02-04", 2)
    assert len(cobertura["faltando"]) == 32 and cobertura["faltando"][0] == "2026-01-03"

    sp = contratacoes.ente_para_json("3550308", painel.entes["3550308"], painel, _cadastro(), "G")
    assert sp["ente"] == {"codigo": "3550308", "nome": "São Paulo", "uf": "SP", "tipo": "municipio",
                          "populacao": 11_900_000}
    t = sp["totais"]
    assert (t["processos"], t["valor_estimado"], t["processos_sem_valor"], t["contratos"], t["valor_contratos"]) == (
        3, 400.0, 1, 3, 190.0)
    assert [m["mes"] for m in sp["meses"]] == ["2026-01", "2026-02"]
    assert sp["meses"][0]["processos"] == 2 and sp["meses"][1]["valor_contratos"] == 90.0
    assert sp["modalidades"][0] == {"codigo": 8, "nome": "Dispensa", "processos": 2, "valor_estimado": 400.0}
    assert sp["fornecedores"] == [{"cnpj": "11111111000111", "nome": "EMPRESA A NOVA", "contratos": 2, "valor": 150.0}]
    assert sp["pessoas_fisicas"] == {"contratos": 1, "valor": 40.0}
    assert sp["recentes"][0]["chave"] == "00000000000100-1-000003/2026"          # mais recente primeiro
    assert sp["recentes"][0]["link"] == "https://pncp.gov.br/app/editais/00000000000100/2026/3"
    assert sp["recentes"][0]["orgao"] == "MUNICIPIO X" and sp["recentes"][0]["modalidade"] == "Dispensa"
    pf = next(c for c in sp["contratos_recentes"] if c["tipo_pessoa"] == "PF")
    assert pf["fornecedor"] is None and pf["fornecedor_cnpj"] is None
    assert sp["orgaos"][0]["nome"] == "MUNICIPIO X" and "municipios" not in sp

    estado = contratacoes.ente_para_json("35", painel.entes["35"], painel, _cadastro(), "G")
    assert [m["nome"] for m in estado["municipios"]] == ["Campinas", "São Paulo"]
    assert estado["municipios"][0]["processos"] == 0 and estado["municipios"][1]["processos"] == 3

    p = contratacoes.panorama_para_json(painel, _cadastro(), "G")
    assert p["totais"]["processos"] == 5 and p["totais"]["contratos"] == 4
    assert [e["esfera"] for e in p["esferas"]] == ["F", "E", "M", "?"]
    assert p["sem_ente"]["processos"] == 1 and p["entes_com_publicacao"] == 3
    sp_uf = next(u for u in p["ufs"] if u["uf"] == "SP")
    assert sp_uf["estado"]["processos"] == 1 and sp_uf["municipios"]["processos"] == 3
    assert sp_uf["municipios_com_publicacao"] == 1 and sp_uf["municipios_no_cadastro"] == 2
    assert len(p["ufs"]) == 27
    assert p["fornecedores"][0]["cnpj"] == "22222222000122"
    assert contratacoes.Painel().cobertura() == {"de": None, "ate": None, "dias": 0, "faltando": []}


def test_arquivo_de_cada_orgao(estado_sintetico):
    painel = contratacoes.somar_dias(estado_sintetico.glob("contratacoes-*.json.gz"))
    assert set(painel.por_orgao) == {"00000000000100", "00000000000200", "00000000000300", "00000000000400"}
    o = contratacoes.orgao_para_json("00000000000100", painel.por_orgao["00000000000100"], painel, _cadastro(), "G")
    assert o["tipo"] == "contratacoes-orgao" and o["orgao"] == {"cnpj": "00000000000100", "nome": "MUNICIPIO X",
                                                                "esfera": "M"}
    assert o["ente"] == {"codigo": "3550308", "nome": "São Paulo", "uf": "SP", "tipo": "municipio"}
    assert o["totais"]["processos"] == 3 and "orgaos" not in o
    assert painel.por_orgao["00000000000100"].recentes.maxlen == contratacoes.RECENTES_ORGAO
    sem = contratacoes.orgao_para_json("00000000000400", painel.por_orgao["00000000000400"], painel, _cadastro(), "G")
    assert sem["ente"] is None and sem["orgao"]["esfera"] is None


def test_orgaos_para_a_busca(estado_sintetico):
    painel = contratacoes.somar_dias(estado_sintetico.glob("contratacoes-*.json.gz"))
    busca = contratacoes.orgaos_para_busca(painel, "G")
    assert busca["tipo"] == "orgaos" and busca["colunas"] == ["cnpj", "nome", "ente", "esfera", "processos",
                                                               "contratos"]
    linhas = {linha[0]: linha for linha in busca["orgaos"]}
    assert [linha[0] for linha in busca["orgaos"]] == sorted(linhas)
    assert linhas["00000000000100"] == ["00000000000100", "MUNICIPIO X", "3550308", "M", 3, 3]
    assert linhas["00000000000300"][2:] == ["1", "F", 0, 1]
    assert linhas["00000000000400"][2:4] == [None, None]       # órgão sem esfera: sem ente


def test_nome_de_reserva_sem_cadastro(estado_sintetico):
    painel = contratacoes.somar_dias(estado_sintetico.glob("*.json.gz"))
    vazio = Cadastro({})
    assert contratacoes.ente_para_json("1", painel.entes["1"], painel, vazio, "G")["ente"]["nome"] == "União"
    assert contratacoes.ente_para_json("35", painel.entes["35"], painel, vazio, "G")["ente"]["nome"] == "São Paulo"
    assert vazio.nome("3550308") == "3550308" and vazio.nome("53") == "Distrito Federal"
    assert len(gzip.compress(b"x")) > 0


def test_valor_acima_do_teto_fica_fora_das_somas(estado_sintetico):
    orgaos = {"00000000000100": ["MUNICIPIO X", "M", "3550308"], "00000000000500": ["MUNICIPIO PEQUENO", "M", "3509502"],
              "00000000000300": ["UNIAO", "F", "1"]}
    comum.gravar_json(estado_sintetico / "contratacoes-2026-02-05.json.gz", _dia_sintetico("2026-02-05", [
        _p("00000000000500-1-000001/2026", "00000000000500", "3509502", 6, 30_000_000_000.0),   # acima de R$ 10 bi
    ], [
        _c("00000000000300-2-000009/2026", "00000000000300", "1", cnpj="33333333000133", nome="C",
           valor=239_842_000_000.0),
        _c("00000000000500-2-000009/2026", "00000000000500", "3509502", cnpj="44444444000144", nome="D",
           valor=25_000_000_000.0),
        _c("00000000000500-2-000010/2026", "00000000000500", "3509502", cnpj="44444444000144", nome="D",
           valor=1_000.0),
        _c("00000000000500-2-000011/2026", "00000000000500", "3509502", cnpj="55555555000155", nome="E",
           valor=300_000_000.0),                                                       # acima de R$ 200 mi
    ], orgaos), comprimir=True)
    cadastro = _cadastro()
    cadastro.entes["3509502"] = Ente("3509502", "Cidade Pequena", "SP", "M", 10_000)
    assert contratacoes.teto_do_ente("3509502", cadastro) == 200_000_000.0          # R$ 20 mil × 10 mil
    assert contratacoes.teto_do_ente("3550308", cadastro) == contratacoes.TETO_ABSOLUTO
    assert contratacoes.teto_do_ente("1", cadastro) == contratacoes.TETO_ABSOLUTO
    assert contratacoes.teto_do_ente("3509502", None) == contratacoes.TETO_ABSOLUTO

    painel = contratacoes.somar_dias(estado_sintetico.glob("contratacoes-*.json.gz"), cadastro)
    campinas = contratacoes.ente_para_json("3509502", painel.entes["3509502"], painel, cadastro, "G")
    t = campinas["totais"]
    assert (t["processos"], t["valor_estimado"], t["processos_sem_valor"]) == (1, 0.0, 0)
    assert (t["contratos"], t["valor_contratos"], t["valores_a_conferir"]) == (3, 1_000.0, 3)
    assert campinas["fornecedores"][0] == {"cnpj": "44444444000144", "nome": "D", "contratos": 2, "valor": 1_000.0}
    assert campinas["fornecedores"][1]["valor"] == 0.0
    assert [(x["tipo"], x["valor"]) for x in campinas["a_conferir"]] == [
        ("contrato", 300_000_000.0), ("contrato", 25_000_000_000.0), ("processo", 30_000_000_000.0)]
    assert campinas["a_conferir"][1]["link"] == "https://pncp.gov.br/app/contratos/00000000000500/2026/9"
    assert campinas["a_conferir"][1]["fornecedor"] == "D" and campinas["a_conferir"][2]["fornecedor"] is None
    assert [c["a_conferir"] for c in campinas["contratos_recentes"]] == [True, False, True]

    p = contratacoes.panorama_para_json(painel, cadastro, "G")
    assert p["totais"]["valor_contratos"] == 1_000.0 + 60.0 + 40.0 + 500.0 + 90.0      # sem os 3 valores
    assert p["totais"]["valores_a_conferir"] == 4 and len(p["a_conferir"]) == 4
    assert p["totais"]["contratos"] == 4 + 4
    assert all(f["cnpj"] != "33333333000133" or f["valor"] == 0 for f in p["fornecedores"])
    federal = next(e for e in p["esferas"] if e["esfera"] == "F")
    assert federal["valor_contratos"] == 500.0 and federal["valores_a_conferir"] == 1
    sp = next(u for u in p["ufs"] if u["uf"] == "SP")
    assert sp["municipios"]["valores_a_conferir"] == 3
    o = contratacoes.orgao_para_json("00000000000500", painel.por_orgao["00000000000500"], painel, cadastro, "G")
    assert o["totais"]["valores_a_conferir"] == 3 and len(o["a_conferir"]) == 3
