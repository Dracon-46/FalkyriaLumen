"""Preço de revenda da ANP para o modal (ADR-037): coleta incremental das semanas, estado e arquivos por UF e ano."""

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from lumen_mercado import anp

from lumen_ingestao.bronze import ArtefatoBruto
from lumen_ingestao.coleta_http import ErroColeta
from lumen_painel import cli, mercado
from lumen_painel.cadastro import Cadastro, Ente

AMOSTRA = Path(__file__).resolve().parents[2] / "mercado" / "testes" / "fixtures" / "revendas_lpc_amostra.xlsx"
AGORA = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
BASE = "https://www.gov.br/anp/pt-br/assuntos/precos-e-defesa-da-concorrencia/precos/arquivos-lpc"
SEMANAS = ["2024-12-29_2025-01-04", "2025-12-28_2026-01-03", "2026-09-27_2026-10-03"]
PAGINA = "".join(f'<a href="{BASE}/{s[:4]}/revendas_lpc_{s}.xlsx">semana</a>' for s in SEMANAS).encode()
CADASTRO = Cadastro({"3550308": Ente("3550308", "São Paulo", "SP", "M"),
                     "2611606": Ente("2611606", "Recife", "PE", "M"),
                     "4317103": Ente("4317103", "Sant'Ana do Livramento", "RS", "M")})


class _Cliente:
    """Responde a página do levantamento e, para cada planilha, a amostra real; ``falhar`` escolhe quais erram."""

    def __init__(self, falhar=(), pagina=PAGINA, status_pagina=200):
        self.falhar, self.pagina, self.status_pagina, self.pedidos = set(falhar), pagina, status_pagina, []

    def obter(self, url, cabecalhos=None):
        self.pedidos.append(url)
        if url == anp.PAGINA_SEMANAS:
            return ArtefatoBruto(conteudo=self.pagina, fonte_id=mercado.FONTE_ID, url_solicitada=url, url_efetiva=url,
                                 status_http=self.status_pagina, tipo_midia="text/html")
        if any(s in url for s in self.falhar):
            raise ErroColeta("sem resposta")
        return ArtefatoBruto(conteudo=AMOSTRA.read_bytes(), fonte_id=mercado.FONTE_ID, url_solicitada=url,
                             url_efetiva=url, status_http=200, tipo_midia="application/octet-stream")


def test_estatistica_e_resumo_da_semana():
    assert mercado.estatistica([Decimal("6.10"), Decimal("5.90"), Decimal("6.30"), Decimal("6.00")]) == [
        4, 5.9, 5.975, 6.05, 6.15, 6.3]
    coletas = [anp.Coleta(uf="SP", municipio="SAO PAULO", produto="GASOLINA", data=AGORA.date(), valor=Decimal(v),
                          cnpj=str(i), revenda=None) for i, v in enumerate(["6.19", "6.39"])]
    assert mercado.resumir_semana(coletas) == {"GASOLINA": {"SP": [2, 6.19, 6.24, 6.29, 6.34, 6.39],
                                                            "SP/SAO PAULO": [2, 6.19, 6.24, 6.29, 6.34, 6.39]}}


def test_coleta_so_as_semanas_que_faltam_desde_o_inicio_e_as_mais_recentes_primeiro(tmp_path):
    c = _Cliente()
    r = mercado.coletar(c, tmp_path, agora=AGORA)
    assert r.falha is None and r.na_pagina == 3 and r.lidas == ["2026-09-27", "2025-12-28"]   # 2024 fica de fora
    dados = mercado.ler_estado(tmp_path)
    semana = dados["semanas"]["2026-09-27"]
    assert semana["fim"] == "2026-10-03" and semana["coletas"] == 8
    assert semana["produtos"]["GLP"]["PE/RECIFE"][0] == 2
    c2 = _Cliente()
    r2 = mercado.coletar(c2, tmp_path, agora=AGORA)
    assert r2.lidas == [] and r2.guardadas == 2 and c2.pedidos == [anp.PAGINA_SEMANAS]


def test_limite_por_execucao_e_semana_com_falha_fica_para_depois(tmp_path):
    r = mercado.coletar(_Cliente(falhar={"2026-09-27"}), tmp_path, maximo=1, agora=AGORA)
    assert r.lidas == [] and "2026-09-27" in r.falhas and mercado.ler_estado(tmp_path)["ultima_falha"]
    r2 = mercado.coletar(_Cliente(), tmp_path, maximo=1, agora=AGORA)
    assert r2.lidas == ["2026-09-27"] and "ultima_falha" not in mercado.ler_estado(tmp_path)


def test_pagina_sem_planilha_ou_fora_do_ar_registra_a_falha_e_mantem_o_estado(tmp_path):
    mercado.coletar(_Cliente(), tmp_path, agora=AGORA)
    r = mercado.coletar(_Cliente(pagina=b"<html>nada</html>"), tmp_path, agora=AGORA)
    assert r.falha and r.guardadas == 2
    r = mercado.coletar(_Cliente(status_pagina=503), tmp_path, agora=AGORA)
    assert "503" in r.falha and len(mercado.ler_estado(tmp_path)["semanas"]) == 2


def test_arquivos_por_uf_e_ano_com_o_municipio_pelo_codigo_ibge(tmp_path):
    mercado.coletar(_Cliente(), tmp_path, agora=AGORA)
    gravados = {}
    resumo = mercado.publicar(tmp_path, CADASTRO, lambda n, c: gravados.__setitem__(n, c), gerado_em="G")
    assert sorted(gravados) == ["mercado/anp/uf-pe-2025.json", "mercado/anp/uf-pe-2026.json",
                                "mercado/anp/uf-sp-2025.json", "mercado/anp/uf-sp-2026.json"]
    assert resumo["semanas"] == 2 and resumo["municipios_sem_codigo"] == 0
    sp = gravados["mercado/anp/uf-sp-2026.json"]
    assert sp["ano"] == 2026 and sp["semanas"] == [["2026-09-27", "2026-10-03", f"{BASE}/2026/revendas_lpc_2026-09-27_2026-10-03.xlsx"]]
    assert sp["colunas"] == ["semana", "n", "minimo", "q1", "mediana", "q3", "maximo"]
    assert sp["produtos"]["GASOLINA"]["uf"][0][:2] == [0, 1]
    assert list(sp["produtos"]["GASOLINA"]["municipios"]) == ["3550308"]


def test_nome_que_so_difere_no_apostrofo_casa_e_o_desconhecido_e_contado():
    indice = mercado.indice_municipios(CADASTRO)
    dados = {"semanas": {"2026-09-27": {"fim": "2026-10-03", "url": "u", "produtos": {"GLP": {
        "RS": [1, 1, 1, 1, 1, 1], "RS/SANTANA DO LIVRAMENTO": [1, 1, 1, 1, 1, 1], "RS/INEXISTENTE": [1, 1, 1, 1, 1, 1],
        "XX/LUGAR": [1, 1, 1, 1, 1, 1]}}}}}
    arquivos, sem_codigo = mercado.montar(dados, CADASTRO, gerado_em="G")
    assert indice["RS/SANT ANA DO LIVRAMENTO"] == "4317103"
    assert list(arquivos["mercado/anp/uf-rs-2026.json"]["produtos"]["GLP"]["municipios"]) == ["4317103"]
    assert sem_codigo == ["RS/INEXISTENTE"] and list(arquivos) == ["mercado/anp/uf-rs-2026.json"]


def test_linha_de_comando(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("LUMEN_CONTATO", "a@b.org")
    monkeypatch.setattr("lumen_orquestracao.etapas.cliente", lambda cfg, fonte: _Cliente())
    assert cli.main(["anp", "--estado", str(tmp_path), "--maximo-semanas", "1"]) == 0
    assert '"lidas": [\n    "2026-09-27"' in capsys.readouterr().out
    monkeypatch.setattr("lumen_orquestracao.etapas.cliente", lambda cfg, fonte: _Cliente(falhar={"2025-12-28"}))
    assert cli.main(["anp", "--estado", str(tmp_path)]) == 1
