"""Estatais federais pelos dados abertos da SEST: cadastro e PDG, com linhas reais (BB, Caixa, EBSERH e Correios)."""

import io
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pytest
from lumen_economia import estatais, sest
from lumen_economia.sest import ArquivoSestIlegivel, membro, numero

from lumen_ingestao.bronze import ArtefatoBruto
from lumen_ingestao.coleta_http import ErroColeta

FIX = Path(__file__).resolve().parents[3] / "testes" / "fixtures" / "sest"
AGORA = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)


class _Cliente:
    def __init__(self, falhar=(), corpos=None, status=200):
        self.falhar, self.corpos, self.status = falhar, corpos or {}, status

    def obter(self, url, cabecalhos=None):
        nome = url.rsplit("/", 1)[-1]
        if nome in self.falhar:
            raise ErroColeta("sem resposta")
        corpo = self.corpos.get(nome) or (FIX / nome).read_bytes()
        return ArtefatoBruto(conteudo=corpo, fonte_id="sest_dados_abertos", url_solicitada=url, url_efetiva=url,
                             status_http=self.status, tipo_midia="application/zip")


@pytest.mark.parametrize("texto,valor", [("1.500.002.908", 1_500_002_908.0), ("21.490.205,00", 21_490_205.0),
                                         ("1.234,56", 1234.56), (" 0 ", 0.0), ("-", 0.0), ("", None),
                                         ("-1.000", -1000.0), ("(2.000)", -2000.0)])
def test_numero(texto, valor):
    assert numero(texto) == valor


def test_numero_ilegivel_e_zip_invalido():
    with pytest.raises(ArquivoSestIlegivel, match="ilegível"):
        numero("n/d")
    with pytest.raises(ArquivoSestIlegivel, match="não é ZIP"):
        membro(b"<html>", "x.csv")
    with pytest.raises(ArquivoSestIlegivel, match="não tem"):
        membro((FIX / "sestpdg.zip").read_bytes(), "outro.csv")


def test_cadastro_e_pdg_reais():
    z = (FIX / "sestidentificacao.zip").read_bytes()
    e = sest.empresas(membro(z, "empresas-ativas.csv"), membro(z, "empresas-inativas.csv"))
    assert e["4006"]["sigla"] == "ECT" and e["4006"]["cnpj"] == "34.028.316/0001-03"
    assert e["4006"]["dependente"] is False and e["4006"]["grupo"] is None and e["4006"]["situacao"] == "ativa"
    assert e["3612"]["dependente"] is True   # EBSERH: despesa no Orçamento da União, sem PDG
    assert e["5002"]["grupo"] == "BB" and e["5002"]["capital"] == "Capital Aberto"
    inativa = next(v for v in e.values() if v["situacao"] == "inativa")
    assert inativa["inativa_desde"]
    p = sest.pdg(membro((FIX / "sestpdg.zip").read_bytes(), "sest-pdg.csv"))
    ect = p["4006"]["exercicios"]
    assert ect["2025"]["2201000000"] == [15_606_584_495.0, 15_210_551_820.0, 12]
    assert ect["2024"]["2300000000"] == [29_728_089_571.0, 28_230_888_138.0, 12]
    assert p["4006"]["rubricas"]["2107000000"].startswith("INVESTIMENTOS NO ATIVO")
    assert "3612" not in p


def test_realizado_ate_o_ultimo_mes_publicado():
    cab = ";".join(sest.COLUNAS_PDG)
    linha = "2026;4006;ECT;2201000000;DESPESAS DE PESSOAL;100;10;20;30" + ";" * 9
    vazia = "2026;4006;ECT;2204000000;MATERIAIS E PRODUTOS;5" + ";" * 12
    p = sest.pdg(f"{cab}\r\n{linha}\r\n{vazia}\r\n".encode("cp1252"))
    assert p["4006"]["exercicios"]["2026"]["2201000000"] == [100.0, 30.0, 3]
    assert p["4006"]["exercicios"]["2026"]["2204000000"] == [5.0, None, None]   # ausente, não zero


def test_colunas_ausentes():
    with pytest.raises(ArquivoSestIlegivel, match="colunas ausentes"):
        sest.pdg(b"a;b\r\n1;2\r\n")


def test_coleta_publicacao_e_ligacao_com_a_cvm(tmp_path):
    resumo = sest.coletar(_Cliente(), tmp_path, agora=AGORA)
    assert resumo.para_json() == {"empresas": 5, "empresas_pdg": 3, "exercicios": ["2024", "2025"], "falhas": {}}
    feed = estatais.montar(estatais.ler_estado(tmp_path), sest_dados=sest.ler_estado(tmp_path), agora=AGORA)
    f = feed["federais"]
    assert f["urls"]["pdg"] == sest.URL_PDG and {r["id"] for r in f["rubricas"]} >= {"pessoal", "investimentos"}
    siglas = [e["sigla"] for e in f["empresas"]]
    assert siglas[:3] == ["BB", "CAIXA", "ECT"]
    por = {e["sigla"]: e for e in f["empresas"]}
    assert por["ECT"]["exercicios"]["2025"]["pessoal"] == {"aprovado": 15_606_584_495.0,
                                                          "realizado": 15_210_551_820.0, "ate_mes": 12}
    assert por["EBSERH"]["exercicios"] == {} and por["EBSERH"]["dependente"] is True
    assert por["ECT"]["na_cvm"] is False   # nenhuma companhia da CVM neste estado
    assert f["empresas"][-1]["situacao"] == "inativa"   # ativas primeiro


def test_falha_mantem_o_que_havia(tmp_path):
    sest.coletar(_Cliente(), tmp_path, agora=AGORA)
    resumo = sest.coletar(_Cliente(falhar=("sestpdg.zip",), corpos={"sestidentificacao.zip": b"<html>"}),
                          tmp_path, agora=AGORA)
    assert set(resumo.falhas) == {"identificacao", "pdg"} and resumo.empresas_pdg == 3
    dados = sest.ler_estado(tmp_path)
    assert dados["pdg"]["ultima_falha"] and dados["identificacao"]["ultima_falha"]
    assert sest.coletar(_Cliente(status=404), tmp_path / "novo", agora=AGORA).falhas


def test_identificacao_sem_inativas(tmp_path):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("x/sest-identificacao-empresas-ativas.csv",
                   membro((FIX / "sestidentificacao.zip").read_bytes(), "empresas-ativas.csv"))
    resumo = sest.coletar(_Cliente(corpos={"sestidentificacao.zip": b.getvalue()}), tmp_path, agora=AGORA)
    assert resumo.empresas == 4 and not resumo.falhas


def test_estado_de_outra_versao(tmp_path):
    from lumen_painel.comum import gravar_json
    gravar_json(tmp_path / sest.ARQUIVO_ESTADO, {"versao": 7}, comprimir=True)
    with pytest.raises(ValueError, match="versão 7"):
        sest.ler_estado(tmp_path)


def test_publicar_com_os_dois_estados(tmp_path):
    sest.coletar(_Cliente(), tmp_path, agora=AGORA)
    r = estatais.publicar(tmp_path, tmp_path / "site", agora=AGORA)
    assert r["federais_sest"] == 5 and r["federais_com_pdg"] == 3 and r["companhias"] == 0
