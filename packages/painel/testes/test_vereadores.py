"""Os vereadores pelo SAPL (ADR-062): a coleta de uma câmara, a leitura incremental e a publicação."""

import io
import json
import urllib.error
import urllib.parse
from datetime import date

from lumen_painel import camaras, vereadores
from lumen_painel.cadastro import Cadastro, Ente
from lumen_painel.comum import gravar_json

HOST = "sapl.itapeva.mg.leg.br"


def _sapl(tabelas: dict[str, list[dict]], pedidos: list[str] | None = None):
    """Um SAPL de mentira: as linhas de cada caminho, filtradas pelos parâmetros e paginadas como a API."""
    def ler(url: str) -> dict:
        partes = urllib.parse.urlsplit(url)
        caminho = partes.path.removeprefix("/api/").rstrip("/")
        q = dict(urllib.parse.parse_qsl(partes.query))
        if pedidos is not None:
            pedidos.append(f"{caminho}?{partes.query}")
        pagina, tamanho = int(q.pop("page", 1)), int(q.pop("page_size", 100))
        linhas = [x for x in tabelas.get(caminho, []) if all(str(x.get(k)) == v for k, v in q.items())]
        fatia = linhas[(pagina - 1) * tamanho:pagina * tamanho]
        proxima = pagina + 1 if pagina * tamanho < len(linhas) else None
        return {"pagination": {"total_entries": len(linhas), "next_page": proxima}, "results": fatia}
    return ler


def _tabelas() -> dict[str, list[dict]]:
    return {
        "parlamentares/parlamentar": [{"id": 1, "nome_parlamentar": "Ana"}, {"id": 2, "nome_parlamentar": "Beto"},
                                      {"id": 3, "nome_parlamentar": "Caio (2013)"}],
        "parlamentares/mandato": [{"parlamentar": 1, "data_inicio_mandato": "2021-01-01", "data_fim_mandato": "2028-12-31"},
                                  {"parlamentar": 2, "data_inicio_mandato": "2025-01-01", "data_fim_mandato": None},
                                  {"parlamentar": 3, "data_inicio_mandato": "2013-01-01", "data_fim_mandato": "2016-12-31"}],
        "parlamentares/partido": [{"id": 10, "sigla": "PT"}, {"id": 11, "sigla": "PL"}],
        "parlamentares/filiacao": [{"parlamentar": 1, "partido": 10, "data": "2016-01-01", "data_desfiliacao": "2024-03-01"},
                                   {"parlamentar": 1, "partido": 11, "data": "2024-03-02", "data_desfiliacao": None}],
        "base/tipoautor": [{"id": 1, "descricao": "Parlamentar", "content_type": 26},
                           {"id": 9, "descricao": "Poder Executivo", "content_type": None}],
        "base/autor": [{"id": 50, "content_type": 26, "object_id": 1}, {"id": 51, "content_type": 26, "object_id": 2},
                       {"id": 60, "content_type": None, "object_id": None}],
        "materia/tipomaterialegislativa": [{"id": 1, "sigla": "PLO", "descricao": "Projeto de Lei Ordinária"},
                                           {"id": 3, "sigla": "REQ", "descricao": "Requerimento"},
                                           {"id": 13, "sigla": "EPL", "descricao": "Emenda à Projeto de Lei"}],
        "materia/materialegislativa": [
            {"id": 100, "tipo": 1, "numero": 7, "ano": 2025, "ementa": "Cria  o parque", "data_apresentacao": "2025-03-01",
             "autores": [50, 51]},
            {"id": 101, "tipo": 1, "numero": 1, "ano": 2025, "ementa": "Do Executivo", "data_apresentacao": "2025-02-01",
             "autores": [60]},
            {"id": 102, "tipo": 3, "numero": 4, "ano": 2025, "ementa": "Pede", "data_apresentacao": "2025-04-01",
             "autores": [50]},
            {"id": 103, "tipo": 13, "numero": 1, "ano": 2025, "ementa": "Emenda", "data_apresentacao": "2025-04-01",
             "autores": [51]}],
        "sessao/sessaoplenaria": [{"id": 5, "data_inicio": "2025-03-10"}, {"id": 6, "data_inicio": "2025-03-17"},
                                  {"id": 7, "data_inicio": "2025-03-24"}, {"id": 1, "data_inicio": "2016-05-01"}],
        "sessao/sessaoplenariapresenca": [{"sessao_plenaria": 5, "parlamentar": 1}, {"sessao_plenaria": 5, "parlamentar": 2},
                                          {"sessao_plenaria": 6, "parlamentar": 1}, {"sessao_plenaria": 1, "parlamentar": 3}],
        "sessao/tiporesultadovotacao": [{"id": 1, "nome": "Aprovado", "natureza": "A"},
                                        {"id": 2, "nome": "Rejeitado", "natureza": "R"}],
        "sessao/registrovotacao": [{"id": 900, "materia": 100, "ordem": 40, "expediente": None, "tipo_resultado_votacao": 1},
                                   {"id": 901, "materia": 102, "ordem": 41, "expediente": None, "tipo_resultado_votacao": 1},
                                   {"id": 902, "materia": 101, "ordem": 42, "expediente": None, "tipo_resultado_votacao": 2}],
        "sessao/votoparlamentar": [{"votacao": 900, "parlamentar": 1, "voto": "Sim"},
                                   {"votacao": 900, "parlamentar": 2, "voto": "Não"},
                                   {"votacao": 901, "parlamentar": 1, "voto": "Sim"}],
        "sessao/ordemdia": [{"id": 40, "materia": 100, "data_ordem": "2025-03-17"},
                            {"id": 42, "materia": 101, "data_ordem": "2025-03-24"}],
        "sessao/expedientemateria": [],
    }


def test_tipo_de_projeto_pela_descricao():
    assert vereadores.e_projeto("Projeto de Lei (Executivo)")
    assert vereadores.e_projeto("emenda a lei organica")
    assert vereadores.e_projeto("Proposta de Emenda à Lei Orgânica")
    assert not vereadores.e_projeto("EMENDA À PROJETO DE LEI DO EXECUTIVO")
    assert not vereadores.e_projeto("Requerimento")
    assert vereadores.no_mandato("2028-12-31", [2025]) and not vereadores.no_mandato("2029-01-01", [2025])


def test_coleta_de_uma_camara():
    c = vereadores.vazia(HOST)
    pedidos: list[str] = []
    api = vereadores.Api(HOST, contato="c", ler_fn=_sapl(_tabelas(), pedidos))
    assert vereadores.coletar_camara(c, api, date(2025, 6, 1))
    assert c["autores"] == {"50": "1", "51": "2"}
    assert c["materias"]["2025"]["projetos"] == {"100": ["PLO", 7, "Cria o parque", "2025-03-01", ["1", "2"]],
                                                 "101": ["PLO", 1, "Do Executivo", "2025-02-01", []]}
    assert c["materias"]["2025"]["contagem"] == {"1": {"PLO": 1, "REQ": 1}, "2": {"PLO": 1, "EPL": 1}}
    assert c["presencas"] == {"lidas": 4, "por_sessao": {"5": ["1", "2"], "6": ["1"]}}
    # 901 é de requerimento: fica de fora; 902 é simbólica: registrada sem votos e sem buscar a pauta
    assert c["votacoes"] == {"900": ["100", "2025-03-17", "Aprovado", 1, {"1": "S", "2": "N"}],
                             "902": ["101", None, "Rejeitado", 0, {}]}
    assert not any("materia=101" in p for p in pedidos if p.startswith("sessao/ordemdia"))
    assert c["registros_lidos"] == 3


def test_leitura_incremental_e_prazo():
    tabelas = _tabelas()
    c = vereadores.vazia(HOST)
    vereadores.coletar_camara(c, vereadores.Api(HOST, contato="c", ler_fn=_sapl(tabelas)), date(2025, 6, 1))
    tabelas["sessao/registrovotacao"].append({"id": 903, "materia": 100, "ordem": 40, "expediente": None,
                                              "tipo_resultado_votacao": 1})
    tabelas["sessao/votoparlamentar"].append({"votacao": 903, "parlamentar": 2, "voto": "Abstenção"})
    pedidos: list[str] = []
    assert vereadores.coletar_camara(c, vereadores.Api(HOST, contato="c", ler_fn=_sapl(tabelas, pedidos)),
                                     date(2025, 6, 1))
    assert c["votacoes"]["903"][4] == {"2": "A"}
    assert sum(1 for p in pedidos if p.startswith("sessao/votoparlamentar")) == 1  # só a votação nova

    # o prazo no meio: guarda o que leu, sem marcar a câmara como lida
    relogio = iter([0, 0, 0, 0, 0, 10**9])
    d = vereadores.vazia(HOST)
    api = vereadores.Api(HOST, contato="c", ler_fn=_sapl(tabelas), prazo=1, relogio=lambda: next(relogio, 10**9))
    assert not vereadores.coletar_camara(d, api, date(2025, 6, 1))
    assert d["lido_em"] is None and d["parlamentares"]


def test_pagina_que_sumiu_volta_ao_comeco():
    tabelas = _tabelas()
    c = vereadores.vazia(HOST)
    vereadores.coletar_camara(c, vereadores.Api(HOST, contato="c", ler_fn=_sapl(tabelas)), date(2025, 6, 1))
    c["presencas"]["lidas"] = c["registros_lidos"] = 250       # a câmara apagou linhas: a página 3 não existe mais
    base = _sapl(tabelas)

    def ler(url: str) -> dict:
        if "page=3" in url:
            raise urllib.error.HTTPError(url, 404, "Invalid page", {}, io.BytesIO())  # type: ignore[arg-type]
        return base(url)
    pausas: list[float] = []
    api = vereadores.Api(HOST, contato="c", ler_fn=ler, esperar=pausas.append)
    assert vereadores.coletar_camara(c, api, date(2025, 6, 1))
    assert c["presencas"]["lidas"] == 4 and c["registros_lidos"] == 3
    assert pausas == [3, 6, 3, 6]   # cada página que sumiu foi pedida 3 vezes antes de voltar ao começo


def test_404_passageiro_e_pedido_de_novo():
    base, falhas = _sapl(_tabelas()), {"n": 0}

    def ler(url: str) -> dict:
        if "ordemdia" in url and falhas["n"] < 1:
            falhas["n"] += 1
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, io.BytesIO())  # type: ignore[arg-type]
        return base(url)
    c, pausas = vereadores.vazia(HOST), []
    assert vereadores.coletar_camara(c, vereadores.Api(HOST, contato="c", ler_fn=ler, esperar=pausas.append),
                                     date(2025, 6, 1))
    assert pausas == [3] and c["votacoes"]["900"][1] == "2025-03-17"


def test_camara_com_erro_guarda_o_que_leu_e_espera(tmp_path):
    cadastro = Cadastro({"3133600": Ente("3133600", "Itapeva", "MG", "M", 9000)})
    gravar_json(tmp_path / camaras.ARQUIVO, {"versao": 1, "camaras": {"3133600": [HOST, 3]}}, comprimir=True)
    base = _sapl(_tabelas())

    def ler(url: str) -> dict:
        if "registrovotacao" in url:
            raise urllib.error.HTTPError(url, 500, "erro", {}, io.BytesIO())  # type: ignore[arg-type]
        return base(url)
    r = vereadores.coletar(tmp_path, cadastro, contato="c", hoje=date(2025, 6, 1), ler_fn=ler, esperar=lambda s: None)
    assert list(r["falhas"]) == ["3133600"] and r["ufs"] == ["MG"]
    c = vereadores.ler_estado(tmp_path, "MG")["3133600"]
    assert c["lido_em"] is None and c["falhou_em"] and c["materias"]["2025"]["projetos"]
    assert vereadores.coletar(tmp_path, cadastro, contato="c", ler_fn=ler)["na_fila"] == 0


def test_coletar_grava_por_uf_e_publica(tmp_path):
    cadastro = Cadastro({"3133600": Ente("3133600", "Itapeva", "MG", "M", 9000),
                         "3509502": Ente("3509502", "Campinas", "SP", "M", 1_100_000)})
    gravar_json(tmp_path / camaras.ARQUIVO, {"versao": 1, "camaras": {"3133600": [HOST, 3], "3509502": ["x", 0]}},
                comprimir=True)
    r = vereadores.coletar(tmp_path, cadastro, contato="c", hoje=date(2025, 6, 1), ler_fn=_sapl(_tabelas()))
    assert r["lidas"] == ["3133600"] and r["ufs"] == ["MG"] and not r["falhas"]
    assert set(vereadores.ler_estado(tmp_path, "MG")) == {"3133600"}
    # lida há menos de DIAS_ENTRE_COLETAS: fica para depois
    assert vereadores.coletar(tmp_path, cadastro, contato="c", ler_fn=_sapl(_tabelas()))["na_fila"] == 0

    gravados: dict[str, dict] = {}
    resumo = vereadores.publicar(tmp_path, cadastro, lambda nome, x: gravados.setdefault(nome, x), gerado_em="x")
    assert resumo == {"camaras": 1, "vereadores": 2, "assembleias": 0, "deputados_estaduais": 0}
    indice = gravados["parlamentares/municipal/3133600/indice.json"]
    assert indice["tipo"] == "municipal-indice" and indice["anos"] == ["2025"]
    assert indice["legislaturas"] == {"2017": [2017, 2020], "2021": [2021, 2024], "2025": [2025, 2028]}
    ana = gravados["parlamentares/municipal/3133600/1.json.gz"]
    assert ana["tipo"] == "municipal-vereador" and ana["partido"] == "PL" and ana["legislaturas"] == [2021, 2025]
    ano = ana["anos"]["2025"]
    assert ano["votos"] == {"900": "S"} and ano["presenca"] == [2, 2] and ano["contagem"] == {"PLO": 1, "REQ": 1}
    assert [p[0] for p in ano["autoria"]] == ["100"]
    votacao = gravados["parlamentares/municipal/3133600/votacoes-2025.json.gz"]["votacoes"]
    assert votacao == {"900": ["2025-03-17", "PLO 7/2025", "Cria o parque", "Aprovado", 1, 1, 1, 0, None, "100"]}
    votos = gravados["parlamentares/municipal/3133600/votos-2025.json.gz"]["votos"]
    assert votos == {"900": [["1", "S", "PL"], ["2", "N", ""]]}
    assert gravados["parlamentares/municipal/indice.json"]["camaras"] == [
        ["3133600", "Itapeva", "MG", HOST, 2, 1, ["2025"], "sapl"]]
    json.dumps(gravados)


def test_assembleia_com_sapl_publica_na_esfera_estadual(tmp_path):
    cadastro = Cadastro({"13": Ente("13", "Amazonas", "AM", "E", 4_000_000)})
    gravar_json(tmp_path / camaras.ARQUIVO, {"versao": 1, "camaras": {"13": ["sapl.al.am.leg.br", 3]}}, comprimir=True)
    r = vereadores.coletar(tmp_path, cadastro, contato="c", hoje=date(2025, 6, 1), ler_fn=_sapl(_tabelas()))
    assert r["lidas"] == ["13"] and r["ufs"] == ["AM"]
    gravados: dict[str, dict] = {}
    resumo = vereadores.publicar(tmp_path, cadastro, lambda nome, x: gravados.setdefault(nome, x), gerado_em="x")
    assert resumo == {"camaras": 0, "vereadores": 0, "assembleias": 1, "deputados_estaduais": 2}
    indice = gravados["parlamentares/estadual/13/indice.json"]
    assert indice["tipo"] == "estadual-indice"
    assert indice["legislaturas"] == {"2015": [2015, 2018], "2019": [2019, 2022], "2023": [2023, 2026]}
    ana = gravados["parlamentares/estadual/13/1.json.gz"]
    assert ana["tipo"] == "estadual-deputado" and ana["legislaturas"] == [2019, 2023]
    assert gravados["parlamentares/estadual/indice.json"]["camaras"] == [
        ["13", "Amazonas", "AM", "sapl.al.am.leg.br", 2, 1, ["2025"], "sapl"]]
    assert gravados["parlamentares/municipal/indice.json"]["camaras"] == []
    assert vereadores.no_mandato_estadual("2027-01-31", [2023]) and not vereadores.no_mandato_estadual("2023-01-31", [2023])
