"""Painel de conformidade: estado por UF, avaliação na data da publicação e arquivos publicados (ADR-028)."""

from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace

import pytest

from lumen_ingestao.coleta_http import ErroColeta
from lumen_painel import comum
from lumen_painel import conformidade as conf
from lumen_painel.cadastro import Cadastro, Ente

SAO_SEPE = "4319604"


def _cadastro():
    return Cadastro({SAO_SEPE: Ente(SAO_SEPE, "São Sepé", "RS", "M", 21551),
                     "43": Ente("43", "Rio Grande do Sul", "RS", "E", 11_000_000),
                     "1": Ente("1", "União", None, "F")})


def test_coletas_por_ente_pela_url():
    r = lambda url, status: SimpleNamespace(url_solicitada=url, status_http=status)  # noqa: E731
    base = "https://apidatalake.tesouro.gov.br/ords/siconfi/tt/extrato_entregas"
    coletas = conf.coletas_por_ente([
        r(f"{base}?id_ente=4319604&an_referencia=2025", 200),
        r(f"{base}?an_referencia=2026&id_ente=4319604", 200),
        r(f"{base}?an_referencia=2026&id_ente=4319604&offset=5000", 503),
        r(f"{base}?id_ente=43&an_referencia=2025", 204),
        r(f"{base}?outra=1", 200),
    ])
    assert coletas == {("4319604", 2025): True, ("4319604", 2026): False, ("43", 2025): True}


def test_estado_da_uf_guarda_so_as_entregas_da_lrf(tmp_path, apoio):
    silver = apoio.silver_siconfi(tmp_path / "silver")
    e = conf.estado_da_uf("rs", [SAO_SEPE, "43"], [2025, 2026], silver, {(SAO_SEPE, 2025): True}, agora="A")
    assert (e["uf"], e["coletado_em"], e["exercicios"]) == ("RS", "A", [2025, 2026])
    sepe = e["entes"][SAO_SEPE]
    assert sepe["coleta"] == {"2025": True, "2026": False}
    entregaveis = {linha[1] for linha in sepe["entregas"]}
    assert "MSC Agregada" not in entregaveis and "Balanço Anual (DCA)" in entregaveis
    assert e["entes"]["43"] == {"coleta": {"2025": False, "2026": False}, "entregas": []}
    # Ida e volta da linha, com o instante no horário de Brasília
    entrega = conf.Entrega.da_lista(SAO_SEPE, sepe["entregas"][0])
    assert entrega.entregue_em.utcoffset().total_seconds() == -3 * 3600
    assert conf.Entrega.da_lista(SAO_SEPE, ["i", "e", 2025, 1, "A", None, None]).entregue_em is None
    assert conf._em_brasilia("2025-01-01T10:00:00") == datetime(2025, 1, 1, 10)


def _avaliar(tmp_path, apoio, hoje, coleta=None):
    silver = apoio.silver_siconfi(tmp_path / "silver")
    e = conf.estado_da_uf("RS", [SAO_SEPE, "43"], [2025], silver, coleta or {(SAO_SEPE, 2025): True})
    comum.gravar_json(tmp_path / "estado" / conf.nome_do_arquivo("RS"), e, comprimir=True)
    return conf.avaliar((tmp_path / "estado").glob("conformidade-*.json.gz"), _cadastro(), hoje=hoje, gerado_em="G")


def test_avaliacao_de_um_municipio_com_o_extrato_real(tmp_path, apoio):
    av = _avaliar(tmp_path, apoio, date(2026, 10, 14))
    sepe = av.entes[SAO_SEPE]
    por_periodo = {(o["periodo"], o["poder"]): o for o in sepe["obrigacoes"]}
    dca = por_periodo[("2025", None)]
    assert (dca["resultado"], dca["prazo"], dca["rotulo"]) == ("cumpre", "2026-04-30", "Contas anuais (DCA) de 2025")
    assert por_periodo[("2025-B1", None)]["resultado"] == "cumpre"
    b5 = por_periodo[("2025-B5", None)]                     # entregue em 30/01/2026, prazo 30/12/2025
    assert (b5["resultado"], b5["rotulo_resultado"]) == ("cumpre_parcialmente", "Entregue após o prazo")
    # RGF semestral declarado; o do 1º semestre da prefeitura só existe retificado, mas antes do prazo
    rgf1 = por_periodo[("2025-S1", "executivo")]
    assert (rgf1["resultado"], rgf1["entregue_em"][:10], rgf1["prazo"]) == ("cumpre", "2025-07-18", "2025-07-30")
    assert rgf1["rotulo"] == "RGF do 1º semestre de 2025 — Poder Executivo"
    assert por_periodo[("2025-S1", "legislativo")]["resultado"] == "cumpre"
    assert {o["exercicio"] for o in sepe["obrigacoes"]} == {2025}
    assert sepe["resumo"]["avaliaveis"] == sum(sepe["resumo"][r] for r in ("cumpre", "cumpre_parcialmente",
                                                                           "nao_cumpre"))
    # O estado sem coleta: tudo indeterminado, nada atribuído a ele
    rs = av.entes["43"]
    assert rs["resumo"]["avaliaveis"] == 0 and rs["resumo"]["no_prazo"] is None
    assert all(o["resultado"] == "indeterminado" for o in rs["obrigacoes"])
    assert {o["poder"] for o in rs["obrigacoes"] if o["criterio"] == "rgf_entregue_no_prazo"} == {"executivo"}


def test_obrigacoes_so_ate_a_data_da_avaliacao(tmp_path, apoio):
    av = _avaliar(tmp_path, apoio, date(2025, 8, 1))
    periodos = [o["periodo"] for o in av.entes[SAO_SEPE]["obrigacoes"]]
    assert "2025" not in periodos                           # DCA de 2025 só depois do exercício
    assert [p for p in periodos if "-B" in p] == ["2025-B1", "2025-B2", "2025-B3"]
    assert [p for p in periodos if "-S" in p] == ["2025-S1", "2025-S1"]


def test_instituicao_nao_identificada_vira_indeterminado(tmp_path):
    params = conf.ParametrosLegais.carregar()
    entrega = conf.Entrega(SAO_SEPE, "Município de São Sepé", "Relatório de Gestão Fiscal", 2025, 1, "Q", "HO",
                           datetime(2025, 5, 20, 10, tzinfo=comum.FUSO_BRASILIA))
    obrigacoes = conf.avaliar_ente(SAO_SEPE, "M", [entrega], {"2025": True}, [2025], params, date(2025, 7, 1))
    rgf = {o["poder"]: o for o in obrigacoes if o["periodo"] == "2025-Q1"}
    assert rgf["executivo"]["resultado"] == "indeterminado" and "não foi identificada" in rgf["executivo"]["motivo"]
    assert rgf["legislativo"]["resultado"] == "indeterminado"
    # Sem nenhum RGF do período: não consta
    sem = conf.avaliar_ente(SAO_SEPE, "M", [entrega], {"2025": True}, [2025], params, date(2025, 11, 1))
    q2 = [o for o in sem if o["periodo"] == "2025-Q2"]
    assert q2 and all(o["resultado"] == "nao_cumpre" and o["rotulo_resultado"] == "Não consta no extrato"
                      for o in q2)


def test_resumo_uf_e_panorama(tmp_path, apoio):
    av = _avaliar(tmp_path, apoio, date(2026, 10, 14))
    uf = conf.uf_para_json("RS", av, "G")
    assert [e["codigo"] for e in uf["entes"]] == ["43", SAO_SEPE]          # o estado primeiro, depois por nome
    assert uf["coletado_em"] and uf["avaliado_em"] == "2026-10-14"
    p = conf.panorama_para_json(av, "G")
    assert p["entes"] == 2 and len(p["ufs"]) == 27
    rs = next(u for u in p["ufs"] if u["uf"] == "RS")
    assert rs["entes"] == 2 and rs["avaliaveis"] == p["brasil"]["avaliaveis"]
    assert {c["nome"] for c in p["criterios"]} == {"Contas anuais (DCA)", "RREO", "RGF"}
    assert next(u for u in p["ufs"] if u["uf"] == "SP")["no_prazo"] is None
    assert conf.resumo([]) == {"cumpre": 0, "cumpre_parcialmente": 0, "nao_cumpre": 0, "indeterminado": 0,
                               "avaliaveis": 0, "no_prazo": None}


def test_avaliar_recusa_versao_desconhecida_e_ignora_codigo_estranho(tmp_path):
    comum.gravar_json(tmp_path / "conformidade-XX.json.gz", {"versao": 2}, comprimir=True)
    with pytest.raises(ValueError, match="versão"):
        conf.avaliar([tmp_path / "conformidade-XX.json.gz"], _cadastro())
    comum.gravar_json(tmp_path / "ok" / "conformidade-RS.json.gz",
                      {"versao": 1, "uf": "RS", "exercicios": [2025],
                       "entes": {"999": {"coleta": {}, "entregas": []}, "1": {"coleta": {}, "entregas": []}}},
                      comprimir=True)
    av = conf.avaliar((tmp_path / "ok").glob("*.gz"), _cadastro(), hoje=date(2026, 1, 10))
    assert av.entes == {}


def test_coletar_uf_com_coleta_de_mentira(tmp_path, apoio, cfg):
    from lumen_ingestao.bronze import ArmazemBronzeLocal, ArtefatoBruto
    chamadas = []

    def coletar(c, fonte, janela, **kw):
        chamadas.append((fonte, kw))
        if kw["exercicio"] == 2026:
            raise ErroColeta("fonte suspensa")
        armazem = ArmazemBronzeLocal(c.bronze)
        for ente in kw["entes"]:
            url = (f"https://apidatalake.tesouro.gov.br/ords/siconfi/tt/extrato_entregas?id_ente={ente}"
                   f"&an_referencia={kw['exercicio']}")
            armazem.guardar(ArtefatoBruto(fonte_id="siconfi_extrato", url_solicitada=url, url_efetiva=url,
                                          status_http=200, conteudo=b"{}", tipo_midia="application/json",
                                          coletado_em=datetime(2026, 10, 14, tzinfo=comum.timezone.utc)))
        return SimpleNamespace(falhas=[])

    def normalizar(c, fontes):
        apoio.silver_siconfi(c.silver)

    r = conf.coletar_uf(cfg, "rs", _cadastro(), [2025, 2026], tmp_path / "estado", coletar=coletar,
                        normalizar=normalizar, temporario=tmp_path)
    assert r.gravado and (r.entes, r.consultas, r.consultas_ok) == (2, 4, 2)
    assert any("2026: coleta interrompida" in p for p in r.problemas)
    assert [k["exercicio"] for _, k in chamadas] == [2025, 2026] and chamadas[0][1]["entes"] == ["43", SAO_SEPE]
    estado = comum.ler_json(tmp_path / "estado" / "conformidade-RS.json.gz")
    assert estado["entes"][SAO_SEPE]["coleta"] == {"2025": True, "2026": False}
    assert not list(tmp_path.glob("conformidade-RS-*"))
    assert r.para_json()["uf"] == "RS"
    vazio = conf.coletar_uf(cfg, "AP", _cadastro(), [2025], tmp_path / "estado", coletar=coletar,
                            normalizar=normalizar)
    assert not vazio.gravado and vazio.problemas == ["nenhum ente da UF no cadastro"]


def test_exercicios_a_coletar_mantem_os_encerrados_completos_e_busca_um_que_falta_por_vez():
    hoje = date(2026, 10, 21)
    assert conf.exercicios_a_coletar(None, hoje) == ([2024, 2025, 2026], [])
    assert conf.exercicios_a_coletar(None, hoje, maximo_anteriores=0) == ([2025, 2026], [])
    anterior = {"exercicios": [2023, 2024, 2025, 2026],
                "entes": {"1": {"coleta": {"2023": True, "2024": True, "2025": True, "2026": True}},
                          "2": {"coleta": {"2023": False, "2024": True, "2025": True, "2026": True}}}}
    # 2024 completo fica; 2023 teve falha e volta à fila; a fila vai do mais recente ao mais antigo
    assert conf.exercicios_a_coletar(anterior, hoje) == ([2023, 2025, 2026], [2024])
    assert conf.exercicios_a_coletar(anterior, hoje, maximo_anteriores=3) == ([2021, 2022, 2023, 2025, 2026], [2024])
    tudo = {"exercicios": list(range(2021, 2027)),
            "entes": {"1": {"coleta": {str(a): True for a in range(2021, 2027)}}}}
    assert conf.exercicios_a_coletar(tudo, hoje) == ([2025, 2026], [2021, 2022, 2023, 2024])


def test_juntar_estados_traz_os_exercicios_mantidos_do_estado_anterior():
    linha = lambda ano: ["Prefeitura", "RREO", ano, 1, "B", "HO", "2024-03-01T10:00:00"]  # noqa: E731
    novo = {"exercicios": [2025, 2026], "entes": {"1": {"coleta": {"2025": True, "2026": True},
                                                         "entregas": [linha(2025)]}}}
    anterior = {"exercicios": [2024, 2025], "entes": {"1": {"coleta": {"2024": True, "2025": False},
                                                             "entregas": [linha(2024), linha(2025)]}}}
    junto = conf.juntar_estados(novo, anterior, [2024])
    assert junto["exercicios"] == [2024, 2025, 2026]
    assert junto["entes"]["1"]["coleta"] == {"2024": True, "2025": True, "2026": True}
    assert [e[2] for e in junto["entes"]["1"]["entregas"]] == [2024, 2025]   # a de 2025 é a coleta nova
    assert conf.juntar_estados(novo, None, [2024]) is novo


def test_coleta_da_uf_reaproveita_o_exercicio_encerrado(tmp_path, apoio, monkeypatch):
    monkeypatch.setattr(conf, "hoje_brasilia", lambda: date(2026, 10, 21))
    estado = tmp_path / "estado"
    pedidos = []

    def coletar(cfg, fonte, janela, *, entes, exercicio):
        pedidos.append(exercicio)

    anterior = {"versao": 1, "uf": "RS", "exercicios": [2024],
                "entes": {SAO_SEPE: {"coleta": {"2024": True}, "entregas": [["P", "RREO", 2024, 1, "B", "HO", None]]},
                          "43": {"coleta": {"2024": True}, "entregas": []}}}
    comum.gravar_json(estado / conf.nome_do_arquivo("RS"), anterior, comprimir=True)
    cfg = type("Cfg", (), {})()
    monkeypatch.setattr(conf, "replace", lambda c, **kw: type("C", (), {"bronze": tmp_path / "b", "silver": tmp_path / "s"})())
    monkeypatch.setattr(conf, "estado_da_uf", lambda uf, entes, anos, silver, coletas: {
        "versao": 1, "uf": uf, "exercicios": anos, "entes": {c: {"coleta": {str(a): True for a in anos}, "entregas": []}
                                                             for c in entes}})
    monkeypatch.setattr(conf, "coletas_por_ente", lambda registros: {})
    import lumen_ingestao.bronze as bronze
    monkeypatch.setattr(bronze, "ArmazemBronzeLocal", lambda raiz: type("A", (), {"listar_registros": lambda s, f: []})())
    r = conf.coletar_uf(cfg, "RS", _cadastro(), None, estado, coletar=coletar, normalizar=lambda c, f: None)
    assert r.gravado and r.exercicios == [2023, 2025, 2026] and pedidos == [2023, 2025, 2026]
    gravado = comum.ler_json(estado / conf.nome_do_arquivo("RS"))
    assert gravado["exercicios"] == [2023, 2024, 2025, 2026]
    assert gravado["entes"][SAO_SEPE]["entregas"] == [["P", "RREO", 2024, 1, "B", "HO", None]]


def test_resumo_por_exercicio_no_ente_na_uf_e_no_panorama(tmp_path, apoio):
    av = _avaliar(tmp_path, apoio, date(2026, 10, 14))
    ente = av.entes[SAO_SEPE]
    assert set(ente["por_exercicio"]) == {"2025"}
    assert ente["por_exercicio"]["2025"]["avaliaveis"] + ente["por_exercicio"]["2025"]["indeterminado"] == len(ente["obrigacoes"])
    assert set(conf.uf_para_json("RS", av, "G")["entes"][-1]["por_exercicio"]) == {"2025"}
    p = conf.panorama_para_json(av, "G")
    assert p["brasil_por_exercicio"]["2025"] == p["brasil"]
    assert all("por_exercicio" in c for c in p["criterios"]) and all("por_exercicio" in u for u in p["ufs"])
