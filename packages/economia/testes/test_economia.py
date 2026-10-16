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
AGORA = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)


def _resposta(codigo: int) -> bytes:
    nome = "sgs_7326_2015_2025.json" if codigo == 7326 else f"sgs_{codigo}_2024_2025.json"
    return (FIX / nome).read_bytes()


class _Cliente:
    """Cliente falso que responde com as fixtures reais; ``falhar`` lista códigos que dão erro."""

    def __init__(self, falhar=(), status=200, corpo=None):
        self.falhar, self.status, self.corpo, self.pedidos = set(falhar), status, corpo, []

    def obter(self, url, cabecalhos=None):
        codigo = int(url.split("bcdata.sgs.")[1].split("/")[0])
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
    assert sorted(cliente.pedidos) == sorted(s.codigo for s in SERIES)


def test_falha_mantem_o_anterior_e_registra(tmp_path):
    coleta.coletar(_Cliente(), tmp_path, agora=AGORA)
    r = coleta.coletar(_Cliente(falhar={433}), tmp_path, agora=datetime(2026, 1, 16, tzinfo=timezone.utc))
    assert "ipca" in r.falhas and "ipca" not in r.atualizadas
    guardado = coleta.ler_estado(tmp_path)["series"]["433"]
    assert guardado["coletado_em"] == "2026-01-15T12:00:00+00:00" and len(guardado["observacoes"]) == 24
    assert guardado["ultima_falha"].startswith("2026-01-16") and "sem resposta" in guardado["motivo_da_falha"]


@pytest.mark.parametrize("cliente,motivo", [(_Cliente(status=500), "respondeu 500"), (_Cliente(corpo=b"[]"), "nenhuma"),
                                            (_Cliente(corpo=b'[{"data": "01/01/2025", "valor": "x"}]'), "ValueError")])
def test_respostas_que_nao_servem(tmp_path, cliente, motivo):
    r = coleta.coletar(cliente, tmp_path, [series_por_id()["ipca"]], agora=AGORA)
    assert motivo in r.falhas["ipca"]


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
    monkeypatch.setattr(cli, "_cliente", lambda args: _Cliente(falhar={188}))
    assert cli.main(["coletar", "--estado", str(tmp_path), "--series", "ipca,inpc"]) == 1
    saida = json.loads(capsys.readouterr().out)
    assert saida["atualizadas"] == {"ipca": 24} and "inpc" in saida["falhas"]
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
