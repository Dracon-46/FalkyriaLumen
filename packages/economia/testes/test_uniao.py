"""Testes da despesa da União por função (RREO, Anexo 2) e da receita (Anexo 1)."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from lumen_economia import coleta, uniao
from lumen_economia.coleta import SerieIlegivel
from lumen_economia.indicadores import montar

from lumen_ingestao.bronze import ArtefatoBruto
from lumen_ingestao.coleta_http import ErroColeta

FIX = Path(__file__).resolve().parents[3] / "testes" / "fixtures" / "siconfi"
RREO = {ano: (FIX / f"rreo_uniao_anexo02_{ano}.json").read_bytes() for ano in (2015, 2025)}
RECEITAS = {ano: (FIX / f"rreo_uniao_anexo01_{ano}.json").read_bytes() for ano in (2015, 2025)}
AGORA = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)


def test_le_as_funcoes_de_2015_e_de_2025():
    # 2015: coluna "Até o Bimestre (d)" e rótulo nulo; 2025: coluna nova e o bloco das intraorçamentárias repetido
    antigo, novo = uniao.ler_despesas(RREO[2015]), uniao.ler_despesas(RREO[2025])
    assert round(antigo["despesa_uniao_total"] / 1e9, 1) == 1683.1
    assert round(novo["despesa_uniao_total"] / 1e9, 1) == 3705.4
    assert round(novo["despesa_uniao_saude"] / 1e9, 1) == 217.1      # não 1,5 (o bloco intra)
    assert round(novo["despesa_uniao_previdencia"] / 1e9, 1) == 1101.5
    assert set(novo) == {i for i, *_ in uniao.MOSTRADAS}


def test_soma_das_funcoes_diferente_do_total_e_erro_de_leitura():
    dados = json.loads(RREO[2025])
    saude = next(i for i in dados["items"] if i["conta"] == "Saúde")
    saude["valor"] *= 2
    with pytest.raises(SerieIlegivel, match="somam"):
        uniao.ler_despesas(json.dumps(dados).encode())


@pytest.mark.parametrize("corpo,motivo", [(b"<html/>", "ilegível"), (b'{"items": []}', "coluna"),
                                          (b'{"items": [{"coluna": "DESPESAS LIQUIDADAS AT\\u00c9 O BIMESTRE (d)", '
                                           b'"conta": "Sa\\u00fade", "valor": 1}]}', "total")])
def test_resposta_que_nao_serve(corpo, motivo):
    with pytest.raises(SerieIlegivel, match=motivo):
        uniao.ler_despesas(corpo)


def test_le_as_receitas_de_2015_e_de_2025():
    # Os códigos de conta são os mesmos; o nome da conta muda ("RECEITA TRIBUTÁRIA" virou "IMPOSTOS, TAXAS...")
    antigo, novo = uniao.ler_receitas(RECEITAS[2015]), uniao.ler_receitas(RECEITAS[2025])
    assert round(antigo["receita_uniao_corrente"] / 1e9, 1) == 1282.5
    assert round(novo["receita_uniao_corrente"] / 1e9, 1) == 2981.8
    assert round(novo["receita_uniao_impostos"] / 1e9, 1) == 1136.7
    assert round(novo["receita_uniao_contribuicoes"] / 1e9, 1) == 1455.3
    assert round(novo["receita_uniao_credito"] / 1e9, 1) == 711.8
    assert set(novo) == {i for i, *_ in uniao.RECEITAS}


def test_receitas_que_nao_somam_a_corrente_ou_sem_as_contas():
    dados = json.loads(RECEITAS[2025])
    patrimonial = next(i for i in dados["items"] if i["cod_conta"] == "ReceitaPatrimonial")
    patrimonial["valor"] *= 2
    with pytest.raises(SerieIlegivel, match="somam"):
        uniao.ler_receitas(json.dumps(dados).encode())
    with pytest.raises(SerieIlegivel, match="sem as contas"):
        uniao.ler_receitas(b'{"items": []}')
    with pytest.raises(SerieIlegivel, match="ilegível"):
        uniao.ler_receitas(b"<html/>")


class _Cliente:
    """Responde 2015 e 2025 com as fixtures; os outros anos, com a de 2025; ``falhar`` lista anos sem resposta.

    O anexo vem do endereço: o 1 (receitas) ou o 2 (despesa por função).
    """

    def __init__(self, falhar=()):
        self.falhar, self.anos = set(falhar), []

    def obter(self, url, cabecalhos=None):
        ano = int(url.split("an_exercicio=")[1].split("&")[0])
        self.anos.append(ano)
        if ano in self.falhar:
            raise ErroColeta("SICONFI fora do ar")
        fixtures = RECEITAS if "Anexo%2001" in url else RREO
        return ArtefatoBruto(conteudo=fixtures.get(ano, fixtures[2025]), fonte_id="siconfi_rreo", url_solicitada=url,
                             url_efetiva=url, status_http=200, tipo_midia="application/json")


def test_coleta_os_anos_que_faltam_e_reconfere_os_ultimos(tmp_path):
    cliente = _Cliente()
    r = uniao.coletar(cliente, tmp_path, ano_corrente=2026, agora=AGORA)
    assert r == {"anos": list(range(2015, 2026)), "falhas": {}}
    cliente = _Cliente(falhar={2025})
    r = uniao.coletar(cliente, tmp_path, ano_corrente=2026, agora=AGORA)
    # Só os dois últimos voltam; o que falha mantém o que havia
    assert cliente.anos == [2024, 2025] and r["anos"] == [2024] and "2025" in r["falhas"]
    assert coleta.ler_estado(tmp_path)["despesas_uniao"]["2025"]["valores"]["despesa_uniao_total"] > 3.7e12


def test_publicados_em_bilhoes_de_reais_do_ano_base(tmp_path):
    uniao.coletar(_Cliente(), tmp_path, ano_corrente=2026, agora=AGORA)
    assert uniao.coletar(_Cliente(), tmp_path, ano_corrente=2026, agora=AGORA, receitas=True)["falhas"] == {}
    dados = coleta.ler_estado(tmp_path)
    # IPCA de 0,5% ao mês em 2024 e 2025: a média de 2025 é 1,005^12 vezes a de 2024
    meses = [f"{a}-{m:02d}-01" for a in (2024, 2025) for m in range(1, 13)]
    dados["series"]["433"] = {"observacoes": [[d, "0.5"] for d in meses]}
    feed = montar(dados, agora=AGORA)
    total = feed["indicadores"]["despesa_uniao_total"]
    assert total["unidade"] == "R$ bilhões de 2025" and total["agregacao"] == "valor_anual"
    serie = dict(total["serie"])
    assert set(serie) == {"2024", "2025"}       # sem IPCA de 2015 a 2023, esses anos ficam de fora
    assert serie["2025"] == 3705.42 and serie["2024"] == pytest.approx(3705.42 * 1.005 ** 12, abs=0.01)
    assert {g["id"]: g["indicadores"][:2] for g in feed["grupos"]}["despesa_uniao"] == [
        "despesa_uniao_total", "despesa_uniao_previdencia"]
    receita = feed["indicadores"]["receita_uniao_corrente"]
    assert (receita["grupo"], receita["fonte"], receita["agregacao"]) == ("receita_uniao", uniao.FONTE_RECEITAS,
                                                                          "valor_anual")
    assert dict(receita["serie"])["2025"] == 2981.8 and "Anexo%2001" in receita["url"]
    assert [g["id"] for g in feed["grupos"]][-2:] == ["receita_uniao", "despesa_uniao"]
