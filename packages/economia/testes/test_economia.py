"""Economia e Contas Públicas: coleta do SGS, indicadores derivados e o arquivo do portal, com respostas reais."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from lumen_economia import catalogo, cli, coleta, indicadores
from lumen_economia.catalogo import DERIVADOS, GRUPOS, SERIES, series_por_id
from lumen_economia.coleta import SerieIlegivel, ler_resposta
from lumen_economia.indicadores import acumulado, diferenca, juro_real, lacunas, mes_anterior, montar, no_ano

from lumen_ingestao.bronze import ArtefatoBruto
from lumen_ingestao.coleta_http import ErroColeta

FIX = Path(__file__).resolve().parents[3] / "testes" / "fixtures" / "bcb"
RELEASES = (FIX.parent / "ibge" / "noticias_releases_9256.json").read_bytes()
SIDRA_RENDIMENTO = (FIX.parent / "ibge" / "sidra_6390_rendimento_2024_2025.json").read_bytes()
SERIES_SGS = tuple(s for s in SERIES if s.codigo)   # as do SIDRA têm coleta própria
AGORA = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)


def _resposta(codigo: int) -> bytes:
    nome = "sgs_7326_2015_2025.json" if codigo == 7326 else f"sgs_{codigo}_2024_2025.json"
    return (FIX / nome).read_bytes()


RECUSA = (FIX / "sgs_recusa_firewall.html").read_bytes()


class _Cliente:
    """Cliente falso que responde com as fixtures reais; ``falhar`` lista códigos que dão erro.

    ``recusar`` faz o SGS responder com a página de recusa do firewall do BC nas primeiras ``recusar`` vezes
    que cada série é pedida (``float("inf")``: sempre). No Ipeadata, responde a fixture do código, se houver.
    """

    def __init__(self, falhar=(), status=200, corpo=None, recusar=0, espelho_falha=False, releases_falha=False,
                 sidra_falha=False):
        self.falhar, self.status, self.corpo, self.pedidos = set(falhar), status, corpo, []
        self.releases_falha, self.sidra_falha = releases_falha, sidra_falha
        self.recusar, self.espelho_falha, self.vezes, self.espelhos = recusar, espelho_falha, {}, []

    def obter(self, url, cabecalhos=None):
        if "apisidra.ibge.gov.br" in url:
            if self.sidra_falha:
                raise ErroColeta("SIDRA sem resposta")
            return ArtefatoBruto(conteudo=SIDRA_RENDIMENTO, fonte_id="ibge_sidra", url_solicitada=url, url_efetiva=url,
                                 status_http=200, tipo_midia="application/json")
        if "servicodados.ibge.gov.br/api/v3/noticias" in url:
            if self.releases_falha:
                raise ErroColeta("IBGE sem resposta")
            return ArtefatoBruto(conteudo=RELEASES, fonte_id="ibge_noticias", url_solicitada=url, url_efetiva=url,
                                 status_http=200, tipo_midia="application/json")
        if "ipeadata" in url:
            codigo = url.split("'")[1]
            self.espelhos.append(codigo)
            arquivos = list(FIX.glob(f"ipeadata_{codigo}_*.json"))
            if self.espelho_falha or not arquivos:
                raise ErroColeta("Ipeadata sem resposta")
            return ArtefatoBruto(conteudo=arquivos[0].read_bytes(), fonte_id="ipeadata", url_solicitada=url,
                                 url_efetiva=url, status_http=200, tipo_midia="application/json")
        codigo = int(url.split("bcdata.sgs.")[1].split("/")[0])
        self.vezes[codigo] = self.vezes.get(codigo, 0) + 1
        if self.vezes[codigo] <= self.recusar:
            return ArtefatoBruto(conteudo=RECUSA, fonte_id="bcb_sgs", url_solicitada=url, url_efetiva=url,
                                 status_http=200, tipo_midia="text/html")
        self.pedidos.append(codigo)
        if codigo in self.falhar:
            raise ErroColeta("sem resposta")
        return ArtefatoBruto(conteudo=self.corpo if self.corpo is not None else _resposta(codigo), fonte_id="bcb_sgs",
                             url_solicitada=url, url_efetiva=url, status_http=self.status, tipo_midia="application/json")


# ------------------------------------------------------------------ catálogo

def test_catalogo_consistente():
    ids = [s.id for s in SERIES] + [d.id for d in DERIVADOS]
    assert len(ids) == len(set(ids))
    grupos = {g for g, _ in GRUPOS}
    assert all(s.grupo in grupos for s in SERIES) and all(d.grupo in grupos for d in DERIVADOS)
    assert all(set(d.usa) <= set(series_por_id()) for d in DERIVADOS)
    assert all(s.periodicidade in ("mensal", "anual") for s in SERIES)
    assert {s.id for s in SERIES if s.agregacao == "variacao_mensal"} == {"ipca", "inpc", "selic_mes"}
    assert {s.id for s in SERIES if s.agregacao == "variacao_anual"} == {"pib_real"}
    assert all(d.agregacao == "nivel" for d in DERIVADOS)
    assert catalogo.url_sgs(433) == "https://api.bcb.gov.br/dados/serie/bcdata.sgs.433/dados?formato=json"
    nfsp = series_por_id()["primario_12m"]
    assert "positivo é déficit" in nfsp.leitura


# ------------------------------------------------------------------ coleta

def test_ler_resposta_real():
    obs = ler_resposta(_resposta(433))
    assert obs[0] == ("2024-01-01", "0.42") and len(obs) == 24
    assert ler_resposta(b'[{"data": "01/02/2025", "valor": ""}, {"data": "01/01/2025", "valor": "1.5"}]') == [
        ("2025-01-01", "1.5")]


@pytest.mark.parametrize("corpo,motivo", [(b"<html>erro</html>", "não é JSON"), (b'{"erro": 1}', "não é uma lista"),
                                          (b'[{"data": "2025-01-01", "valor": "1"}]', "DD/MM/AAAA")])
def test_ler_resposta_ilegivel(corpo, motivo):
    with pytest.raises(SerieIlegivel, match=motivo):
        ler_resposta(corpo)


def test_coletar_grava_o_estado(tmp_path):
    cliente = _Cliente()
    r = coleta.coletar(cliente, tmp_path, agora=AGORA)
    assert not r.falhas and r.atualizadas["ipca"] == 24 and r.atualizadas["pib_real"] == 11
    estado = coleta.ler_estado(tmp_path)
    assert estado["series"]["433"]["coletado_em"] == "2026-01-15T12:00:00+00:00"
    assert sorted(cliente.pedidos) == sorted(s.codigo for s in SERIES_SGS)


def test_falha_mantem_o_anterior_e_registra(tmp_path):
    coleta.coletar(_Cliente(), tmp_path, agora=AGORA)
    r = coleta.coletar(_Cliente(falhar={13762}), tmp_path, agora=datetime(2026, 1, 16, tzinfo=timezone.utc))
    assert "divida_bruta" in r.falhas and "divida_bruta" not in r.atualizadas
    guardado = coleta.ler_estado(tmp_path)["series"]["13762"]
    assert guardado["coletado_em"] == "2026-01-15T12:00:00+00:00" and len(guardado["observacoes"]) == 24
    assert guardado["ultima_falha"].startswith("2026-01-16") and "sem resposta" in guardado["motivo_da_falha"]


@pytest.mark.parametrize("cliente,motivo", [(_Cliente(status=500), "respondeu 500"), (_Cliente(corpo=b"[]"), "nenhuma"),
                                            (_Cliente(corpo=b'[{"data": "01/01/2025", "valor": "x"}]'), "ValueError")])
def test_respostas_que_nao_servem(tmp_path, cliente, motivo):
    r = coleta.coletar(cliente, tmp_path, [series_por_id()["divida_bruta"]], agora=AGORA)
    assert motivo in r.falhas["divida_bruta"]


# ------------------------------------------------------------------ firewall do BC e espelho

def test_pagina_de_recusa_do_firewall():
    assert coleta.recusa_do_bc(RECUSA) == "14273271137322755349"
    assert coleta.recusa_do_bc(b"<html>outra coisa</html>") is None and coleta.recusa_do_bc(b"[]") is None
    with pytest.raises(coleta.SgsRecusou, match="firewall do Banco Central"):
        ler_resposta(RECUSA)


def test_recusa_passageira_repete_depois_da_pausa(tmp_path):
    pausas = []
    cliente = _Cliente(recusar=1)
    r = coleta.coletar(cliente, tmp_path, agora=AGORA, espera_s=30, dormir=pausas.append)
    assert pausas == [30] and not r.falhas and not r.pelo_espelho and len(r.atualizadas) == len(SERIES_SGS)
    assert all(v == 2 for v in cliente.vezes.values()) and not cliente.espelhos


def test_recusa_persistente_usa_o_espelho_conferido(tmp_path):
    coleta.coletar(_Cliente(), tmp_path, agora=AGORA)
    cliente = _Cliente(recusar=float("inf"))
    r = coleta.coletar(cliente, tmp_path, agora=datetime(2026, 1, 16, tzinfo=timezone.utc), dormir=lambda s: None)
    com_espelho = {s.id for s in SERIES if s.espelho}
    assert com_espelho == {"ipca", "inpc", "selic_mes", "primario_12m", "nominal_12m", "pib_real", "desocupacao"}
    # só há fixture do espelho do IPCA e do PIB real: as outras com espelho falham nele, e as sem espelho falham
    assert set(r.pelo_espelho) == {"ipca", "pib_real"} and "firewall" in r.pelo_espelho["ipca"]
    assert set(r.falhas) == {s.id for s in SERIES_SGS} - {"ipca", "pib_real"}
    assert "espelho do Ipeadata" in r.falhas["inpc"] and "espelho" not in r.falhas["divida_bruta"]
    estado = coleta.ler_estado(tmp_path)["series"]
    ipca = estado["433"]
    assert ipca["fonte_coleta"] == "ipeadata" and ipca["url_coleta"].endswith("SERCODIGO='PRECOS12_IPCAG12')")
    assert ipca["observacoes"] == [list(x) for x in ler_resposta(_resposta(433))]  # o espelho dá os mesmos valores
    assert estado["7326"]["observacoes"] == [list(x) for x in ler_resposta(_resposta(7326))]  # duas casas, como no SGS
    assert estado["13762"]["ultima_falha"].startswith("2026-01-16") and estado["13762"]["observacoes"]


def test_espelho_tambem_fora(tmp_path):
    r = coleta.coletar(_Cliente(recusar=float("inf"), espelho_falha=True), tmp_path,
                       [series_por_id()["ipca"]], agora=AGORA, dormir=lambda s: None)
    assert "Ipeadata sem resposta" in r.falhas["ipca"] and not r.pelo_espelho


@pytest.mark.parametrize("corpo,motivo", [(b"<html>", "ilegível"), (b'{"x": 1}', "ilegível"),
                                          (b'{"value": [{"VALDATA": "jan", "VALVALOR": 1}]}', "sem data")])
def test_ipeadata_ilegivel(corpo, motivo):
    with pytest.raises(SerieIlegivel, match=motivo):
        coleta.ler_ipeadata(corpo)
    assert coleta.ler_ipeadata(b'{"value": [{"VALDATA": "2025-01-01T00:00:00-03:00", "VALVALOR": null}]}') == []


def test_estado_de_outra_versao(tmp_path):
    from lumen_painel.comum import gravar_json
    gravar_json(tmp_path / coleta.ARQUIVO_ESTADO, {"versao": 9}, comprimir=True)
    with pytest.raises(ValueError, match="versão 9"):
        coleta.ler_estado(tmp_path)


# ------------------------------------------------------------------ contas

def test_mes_anterior_e_lacunas():
    assert mes_anterior("2025-01") == "2024-12" and mes_anterior("2025-10") == "2025-09"
    assert lacunas({"2025-01": 1, "2025-04": 1}, "mensal") == ["2025-02", "2025-03"]
    assert lacunas({"2020": 1, "2023": 1}, "anual") == ["2021", "2022"]
    assert lacunas({}, "mensal") == []


def test_acumulado_so_com_os_meses_todos():
    v = {f"2025-{m:02d}": 1.0 for m in range(1, 13)}
    assert acumulado(v, 12) == {"2025-12": 12.68}
    del v["2025-06"]
    assert acumulado(v, 12) == {}        # um mês ausente: sem acumulado, e não um acumulado menor
    assert no_ano({"2025-01": 1.0, "2025-02": 1.0, "2025-04": 1.0}) == {"2025-01": 1.0, "2025-02": 2.01}


def test_juro_real_e_diferenca():
    assert juro_real({"2025-12": 15.0, "2025-11": 14.0}, {"2025-12": 5.0}) == {"2025-12": 9.52}
    assert diferenca({"a": 9.48, "b": 1.0}, {"a": 0.62}) == {"a": 8.86}


def test_indicadores_conferem_com_o_ibge(tmp_path):
    """IPCA em 12 meses e no ano, calculados das variações mensais, contra o que o IBGE publica (SIDRA 1737)."""
    coleta.coletar(_Cliente(), tmp_path, agora=AGORA)
    feed = montar(coleta.ler_estado(tmp_path), agora=AGORA)
    calculado = {"2265": dict(feed["indicadores"]["ipca_12m"]["serie"]),
                 "69": dict(feed["indicadores"]["ipca_ano"]["serie"])}
    sidra = json.loads((FIX / "sidra_1737_ipca_acumulados_2025.json").read_text(encoding="utf-8"))[1:]
    conferidos = 0
    for linha in sidra:
        mes = f"{linha['D3C'][:4]}-{linha['D3C'][4:]}"
        if mes in calculado[linha["D2C"]]:
            assert calculado[linha["D2C"]][mes] == pytest.approx(float(linha["V"]), abs=0.011), (mes, linha["D2C"])
            conferidos += 1
    assert conferidos >= 13


def test_arquivo_do_portal(tmp_path):
    coleta.coletar(_Cliente(), tmp_path, agora=datetime(2025, 12, 10, tzinfo=timezone.utc))
    feed = montar(coleta.ler_estado(tmp_path), agora=AGORA)
    assert feed["versao"] == 1 and feed["tipo"] == "economia"
    assert [g["id"] for g in feed["grupos"]] == [g for g, _ in GRUPOS]
    ind = feed["indicadores"]
    assert set(ind) == {s.id for s in SERIES} | {d.id for d in DERIVADOS}
    assert ind["ipca"]["codigo_sgs"] == 433 and ind["ipca"]["url"].endswith("sgs.433/dados?formato=json")
    assert ind["ipca"]["ultimo"] == {"periodo": "2025-12", "valor": 0.33}
    # A Selic de dezembro estava em curso na coleta (10/12): fica de fora, marcada
    assert ind["selic_mes"]["ultimo"]["periodo"] == "2025-11"
    assert ind["selic_mes"]["periodo_parcial_omitido"] == "2025-12"
    assert ind["pib_real"]["ultimo"] == {"periodo": "2025", "valor": 2.29} and ind["pib_real"]["lacunas"] == []
    assert ind["juros_nominais_12m"]["derivado_de"] == ["nominal_12m", "primario_12m"]
    assert ind["ipca_12m"]["serie"][0][0] == "2024-12"   # o primeiro com 12 meses na fixture
    assert ind["juro_real_12m"]["coletado_em"] == "2025-12-10T00:00:00+00:00"
    assert ind["ipca"]["coletado_de"] == "sgs" and ind["ipca"]["url_coleta"] is None


def test_arquivo_do_portal_diz_quando_veio_do_espelho(tmp_path):
    coleta.coletar(_Cliente(recusar=float("inf")), tmp_path, agora=AGORA, dormir=lambda s: None)
    ind = montar(coleta.ler_estado(tmp_path), agora=AGORA)["indicadores"]
    assert ind["ipca"]["coletado_de"] == "ipeadata" and "PRECOS12_IPCAG12" in ind["ipca"]["url_coleta"]
    assert ind["ipca"]["url"].endswith("sgs.433/dados?formato=json")      # a referência continua o SGS
    assert ind["divida_bruta"]["coletado_de"] is None and ind["divida_bruta"]["ultima_falha"]


def test_derivado_sem_coleta_fica_sem_data():
    feed = montar({"versao": 1, "series": {}}, agora=AGORA)
    assert feed["indicadores"]["ipca_12m"]["coletado_em"] is None and feed["indicadores"]["ipca"]["ultimo"] is None


def test_publicar(tmp_path):
    coleta.coletar(_Cliente(), tmp_path / "estado", agora=AGORA)
    r = indicadores.publicar(tmp_path / "estado", tmp_path / "site", agora=AGORA)
    assert r["indicadores"]["divida_bruta"] == "2025-12"
    assert json.loads((tmp_path / "site" / "economia" / "indicadores.json").read_text())["tipo"] == "economia"


# ------------------------------------------------------------------ linha de comando

def test_cli(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "_cliente", lambda args, fonte=None: _Cliente(falhar={13762}))
    assert cli.main(["coletar", "--estado", str(tmp_path), "--series", "ipca,divida_bruta"]) == 1
    saida = json.loads(capsys.readouterr().out)
    assert saida["atualizadas"] == {"ipca": 24} and "divida_bruta" in saida["falhas"]
    assert saida["releases"] == {"produtos": 1, "falhas": {}}
    assert cli.main(["coletar", "--estado", str(tmp_path), "--series", "ipca,nada"]) == 2
    assert "nada" in capsys.readouterr().err
    assert cli.main(["publicar", "--estado", str(tmp_path), "--saida", str(tmp_path / "site")]) == 0
    assert (tmp_path / "site" / "economia" / "indicadores.json").exists()


def test_cli_pela_orquestracao_usa_o_cliente_do_lumen(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("LUMEN_CONTATO", "a@b.org")
    from lumen_orquestracao import etapas
    monkeypatch.setattr(etapas, "cliente", lambda cfg, fonte_id: _Cliente())
    from lumen_orquestracao.cli import main
    assert main(["--config", str(tmp_path / "x.toml"), "economia", "coletar", "--estado", str(tmp_path),
                 "--series", "pib_real"]) == 0
    assert json.loads(capsys.readouterr().out)["atualizadas"] == {"pib_real": 11}


# ------------------------------------------------------------------ releases do IBGE

def test_ler_releases_real():
    itens = coleta.ler_releases(RELEASES)
    assert [(i["data"], i["titulo"]) for i in itens] == [("2026-10-09", "IPCA fica em 0,82% em setembro"),
                                                           ("2026-09-11", "IPCA fica em -0,32% em agosto")]
    assert itens[0]["link"].startswith("https://agenciadenoticias.ibge.gov.br/") and itens[0]["introducao"]


@pytest.mark.parametrize("corpo", [b"<html>fora</html>", b'{"count": 0}', b"[]"])
def test_ler_releases_ilegivel(corpo):
    with pytest.raises(SerieIlegivel):
        coleta.ler_releases(corpo)


def test_ler_releases_ignora_item_incompleto():
    corpo = json.dumps({"items": [{"titulo": "Sem data", "link": "http://x"},
                                  {"titulo": "Ok", "link": "http://x/y", "data_publicacao": "01/09/2026 09:00:00"}]})
    assert [i["titulo"] for i in coleta.ler_releases(corpo.encode())] == ["Ok"]


def test_coletar_releases_grava_e_mantem_o_anterior_na_falha(tmp_path):
    series = [s for s in SERIES if s.id in ("ipca", "pib_real", "selic_mes")]
    assert coleta.coletar_releases(_Cliente(), tmp_path, series, agora=AGORA) == {"produtos": 2, "falhas": {}}
    guardado = coleta.ler_estado(tmp_path)["releases"]
    assert set(guardado) == {"9256", "9300"} and len(guardado["9256"]["itens"]) == 2
    resumo = coleta.coletar_releases(_Cliente(releases_falha=True), tmp_path, series, agora=AGORA)
    assert resumo["produtos"] == 0 and set(resumo["falhas"]) == {"9256", "9300"}
    assert coleta.ler_estado(tmp_path)["releases"]["9256"]["itens"] == guardado["9256"]["itens"]


def test_indicador_do_ibge_leva_os_releases(tmp_path):
    coleta.coletar(_Cliente(), tmp_path, [series_por_id()["ipca"]], agora=AGORA)
    coleta.coletar_releases(_Cliente(), tmp_path, [series_por_id()["ipca"]], agora=AGORA)
    feed = montar(coleta.ler_estado(tmp_path), agora=AGORA)
    releases = feed["indicadores"]["ipca"]["releases"]
    assert releases["fonte"] == "IBGE, Agência de Notícias" and releases["itens"][0]["data"] == "2026-10-09"
    # Indicador do Banco Central não tem releases do IBGE; o do IBGE sem coleta, lista vazia
    assert "releases" not in feed["indicadores"]["selic_mes"]
    # O derivado de uma série só herda os releases dela; o de duas (juro real), não
    assert feed["indicadores"]["ipca_12m"]["releases"] == releases
    assert "releases" not in feed["indicadores"]["juro_real_12m"]
    assert feed["indicadores"]["pib_real"]["releases"]["itens"] == []


# ------------------------------------------------------------------ séries do SIDRA

def test_ler_sidra_real_no_formato_do_sgs():
    obs = coleta.ler_sidra(SIDRA_RENDIMENTO)
    assert len(obs) == 24 and obs[0] == ("2024-01-01", "3456") and obs[-1] == ("2025-12-01", "3742")
    corpo = json.dumps([{"D3C": "Mês (Código)", "V": "Valor"}, {"D3C": "202601", "V": "..."},
                        {"D3C": "202602", "V": "3800"}, {"D3C": "x", "V": "1"}]).encode()
    assert coleta.ler_sidra(corpo) == [("2026-02-01", "3800")]


@pytest.mark.parametrize("corpo", [b"<html/>", b"[]", b'[{"V": "Valor"}]'])
def test_ler_sidra_ilegivel(corpo):
    with pytest.raises(SerieIlegivel):
        coleta.ler_sidra(corpo)


def test_coletar_sidra_grava_e_mantem_na_falha(tmp_path):
    rendimento = series_por_id()["rendimento_real"]
    assert rendimento.codigo is None and rendimento.chave == "sidra/t/6390/n1/all/v/5933/p/all"
    r = coleta.coletar_sidra(_Cliente(), tmp_path, agora=AGORA)
    assert r.atualizadas == {"rendimento_real": 24} and not r.falhas
    guardado = coleta.ler_estado(tmp_path)["series"][rendimento.chave]
    assert guardado["fonte_coleta"] == "sidra" and guardado["url"].startswith("https://apisidra.ibge.gov.br/values/")
    r = coleta.coletar_sidra(_Cliente(sidra_falha=True), tmp_path, agora=AGORA)
    assert "rendimento_real" in r.falhas
    depois = coleta.ler_estado(tmp_path)["series"][rendimento.chave]
    assert depois["observacoes"] == guardado["observacoes"] and depois["ultima_falha"]
    feed = montar(coleta.ler_estado(tmp_path), agora=AGORA)
    ind = feed["indicadores"]["rendimento_real"]
    assert ind["codigo_sgs"] is None and ind["coletado_de"] == "sidra" and ind["ultimo"] == {"periodo": "2025-12",
                                                                                          "valor": 3742.0}
    assert ind["fonte"].startswith("IBGE, Sistema IBGE de Recuperação") and ind["grupo"] == "trabalho"
