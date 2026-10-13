"""Regra A-05 de ponta a ponta: silver do PNCP + preço de bomba da ANP + ofertas do varejo → relatório silencioso.

Confere a razão contra a mediana, o limiar de cada categoria, a referência do município com recuo para a
UF, o preço estimado separado do homologado, o item sem amostra de mercado ("sem referência"), o item não
reconhecido, o gás de cozinha contra a planilha semanal, os parâmetros, o relatório (JSON Lines, CSV,
distribuição para calibrar e resumo) e os comandos ``lumen mercado``, inclusive a busca das planilhas
semanais na página da ANP.
"""

import csv
import json
import threading
from datetime import date, datetime, timezone
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest
from lumen_mercado import anp, cli, relatorio, varejo
from lumen_mercado.comparacao import (
    ACIMA,
    DENTRO,
    FORA_DE_ESCALA,
    NAO_COMPARAVEL,
    SEM_REFERENCIA,
    ItemParaComparar,
    ParametrosMercado,
    comparar,
    itens_da_silver,
)
from lumen_mercado.especificacao import reconhecer

from lumen_ingestao.bronze import ArmazemBronzeLocal
from lumen_normalizacao.silver import consolidar, ler_entidade
from lumen_orquestracao.cli import main as main_lumen

URL_ANP = anp.url_semestre(2026, 1)


def _postos(municipio_nome="SAO PAULO", uf="SP", produto="GASOLINA", quando="09/03/2026", valores=()):
    prefixo = sum(map(ord, municipio_nome)) % 10**6     # CNPJ diferente em cada município
    return [(uf, municipio_nome, f"{prefixo:06d}0000{i:04d}", produto, quando, v) for i, v in enumerate(valores)]


def _precos_sp(apoio):
    linhas = _postos(valores=["5,99", "6,09", "6,19", "6,29", "6,39"])                 # mediana 6,19
    linhas += _postos(municipio_nome="CAMPINAS", valores=["6,00", "6,10", "6,20", "6,30", "6,40",
                                                          "6,50", "6,60", "6,70", "6,80", "6,90"])
    linhas += _postos(produto="DIESEL S10", valores=["6,00", "6,05", "6,10", "6,15", "6,20"])
    return apoio.csv_anp(linhas)


def test_parametros_do_pacote():
    p = ParametrosMercado.carregar()
    assert p.modo == "silencioso" and not p.calibrado
    assert p.combustivel_limiar == Decimal("1.20") and p.varejo_limiar == Decimal("1.50")
    assert p.gas_de_cozinha_limiar == Decimal("1.25")
    assert "notebook i5 8gb ssd 256gb" in p.consultas_padrao
    # cada consulta padrão é exatamente a que o reconhecimento produz: é por ela que a referência é achada
    for consulta in p.consultas_padrao:
        assert reconhecer(consulta, "unidade").consulta == consulta


def test_combustivel_contra_a_anp(cfg, apoio):
    apoio.guardar_no_bronze(cfg, anp.FONTE_ID, URL_ANP, _precos_sp(apoio), tipo="text/csv")
    apoio.municipio(cfg)
    apoio.compra(cfg, itens=[
        (1, "GASOLINA COMUM", "Litro", "10000", "7.00", "7.80"),           # 7,80 / 6,19 = 1,260
        (2, "ÓLEO DIESEL S10", "Litro", "5000", "6.50", "6.30"),           # 6,30 / 6,10 = 1,033
        (3, "Etanol hidratado combustível", "Litro", "100", "4.00", "4.50"),   # sem coleta de etanol
        (4, "Pneu 175/70 aro 13", "Unidade", "4", "300", "280"),           # não comparável
        (5, "Gasolina aditivada", "Litro", "2000", "9.00", None),          # sem coleta: sem referência
    ])
    precos = cli.carregar_anp(ArmazemBronzeLocal(cfg.bronze))
    processos = consolidar(ler_entidade(cfg.silver, "processo_contratacao"))
    itens = consolidar(ler_entidade(cfg.silver, "item_contratacao"))
    resultados = consolidar(ler_entidade(cfg.silver, "resultado_item"))
    r = {c.descricao: c for c in comparar(itens_da_silver(processos, itens, resultados), ParametrosMercado.carregar(),
                                           anp=precos, municipios={"3550308": "São Paulo"})}
    gasolina = r["GASOLINA COMUM"]
    assert gasolina.situacao == ACIMA and gasolina.razao == Decimal("1.260") and gasolina.tipo_preco == "homologado"
    assert gasolina.referencia.escopo == "municipio" and gasolina.referencia.mediana == Decimal("6.190")
    assert gasolina.referencia.quantidade == 5 and gasolina.valor_total == Decimal("78000.00")
    assert "acima_do_maior_preco_observado" in gasolina.marcacoes
    diesel = r["ÓLEO DIESEL S10"]
    assert diesel.situacao == DENTRO and diesel.razao == Decimal("1.033")
    assert r["Etanol hidratado combustível"].situacao == SEM_REFERENCIA
    assert r["Pneu 175/70 aro 13"].situacao == NAO_COMPARAVEL
    aditivada = r["Gasolina aditivada"]
    assert aditivada.situacao == SEM_REFERENCIA and aditivada.tipo_preco == "estimado"


def test_recuo_para_a_uf_e_janela(cfg, apoio):
    precos = anp.PrecosAnp(anp.ler_csv(_precos_sp(apoio)))
    # município sem coleta: vale a UF (15 coletas de gasolina), marcado no escopo
    ref = precos.referencia("GASOLINA", "SP", "Guarulhos", date(2026, 3, 12))
    assert ref.escopo == "uf" and ref.quantidade == 15
    # fora da janela de 7 dias: nada
    assert precos.referencia("GASOLINA", "SP", "São Paulo", date(2026, 4, 30)) is None
    # amostra pequena no município: recua para a UF
    assert precos.referencia("GASOLINA", "SP", "São Paulo", date(2026, 3, 9), minimo_municipio=6).escopo == "uf"
    assert precos.referencia("GASOLINA", "RJ", None, date(2026, 3, 9)) is None


def _busca(ofertas):
    return json.dumps({"site_id": "MLB", "results": [
        {"id": f"MLB{i}", "title": t, "price": p, "currency_id": "BRL", "condition": "new",
         "permalink": f"https://produto.mercadolivre.com.br/MLB-{i}", "seller": {"id": 10 + i},
         "shipping": {"free_shipping": True}, "official_store_id": None}
        for i, (t, p) in enumerate(ofertas)]}).encode()


def test_informatica_contra_o_varejo(cfg, apoio):
    titulos = [(f"Notebook Marca{i} Intel Core i5 8GB 256GB SSD 15.6", 3000 + i * 100) for i in range(10)]
    quando = datetime(2026, 3, 11, 10, tzinfo=timezone.utc)
    apoio.guardar_no_bronze(cfg, varejo.FONTE_ID, varejo.url_busca("notebook i5 8gb ssd 256gb"), _busca(titulos),
                      quando=quando)
    apoio.compra(cfg, chave="11222333000181-1-000011/2026", objeto="Aquisição de notebooks", itens=[
        (1, "NOTEBOOK processador Intel Core i5, 8GB RAM, SSD 256GB", "Unidade", "20", "6000", "5900"),
        (2, "Monitor 24 polegadas full hd", "Unidade", "20", "900", "850"),   # sem coleta do monitor
    ])
    ofertas = varejo.OfertasVarejo.do_bronze(ArmazemBronzeLocal(cfg.bronze))
    processos = consolidar(ler_entidade(cfg.silver, "processo_contratacao"))
    itens = consolidar(ler_entidade(cfg.silver, "item_contratacao"))
    resultados = consolidar(ler_entidade(cfg.silver, "resultado_item"))
    r = {c.especificacao.categoria: c for c in comparar(itens_da_silver(processos, itens, resultados),
                                                        ParametrosMercado.carregar(), varejo=ofertas)}
    nb = r["notebook"]
    assert nb.situacao == ACIMA and nb.referencia.mediana == Decimal("3450.000") and nb.razao == Decimal("1.710")
    assert nb.referencia.evidencias[0].endereco.startswith("https://produto.mercadolivre.com.br/")
    assert r["monitor"].situacao == SEM_REFERENCIA


def test_sem_fontes_carregadas_e_sem_preco():
    processo = {"id": "p", "chave_origem": "X-1-000001/2026", "data_publicacao": "2026-03-10", "uf": "SP"}
    entradas = [
        ItemParaComparar(processo=processo, item={"id": "a", "processo_id": "p", "descricao_original": "GASOLINA COMUM",
                                                  "unidade_medida": "Litro", "valor_unitario_estimado": "6.5",
                                                  "quantidade": "10"}),
        ItemParaComparar(processo=processo, item={"id": "b", "processo_id": "p",
                                                  "descricao_original": "Monitor 24 polegadas",
                                                  "unidade_medida": "UN", "valor_unitario_estimado": "800",
                                                  "quantidade": "1"}),
        ItemParaComparar(processo=processo, item={"id": "c", "processo_id": "p", "descricao_original": "GASOLINA COMUM",
                                                  "unidade_medida": "Litro", "valor_unitario_estimado": None,
                                                  "quantidade": "10"}),
    ]
    r = list(comparar(entradas, ParametrosMercado.carregar()))
    assert [c.motivo for c in r] == ["preços da ANP não carregados", "ofertas de varejo não carregadas",
                                     "item sem preço unitário publicado"]


def test_relatorio(cfg, apoio, tmp_path):
    apoio.guardar_no_bronze(cfg, anp.FONTE_ID, URL_ANP, _precos_sp(apoio), tipo="text/csv")
    apoio.municipio(cfg)
    apoio.compra(cfg, itens=[(1, "GASOLINA COMUM", "Litro", "10000", "7.00", "7.80"),
                       (2, "Pneu", "Unidade", "4", "300", "280")])
    precos = cli.carregar_anp(ArmazemBronzeLocal(cfg.bronze))
    lista = list(comparar(itens_da_silver(consolidar(ler_entidade(cfg.silver, "processo_contratacao")),
                                          consolidar(ler_entidade(cfg.silver, "item_contratacao")),
                                          consolidar(ler_entidade(cfg.silver, "resultado_item"))),
                          ParametrosMercado.carregar(), anp=precos, municipios={"3550308": "São Paulo"}))
    contagem = relatorio.escrever(lista, tmp_path / "rel", ParametrosMercado.carregar())
    grupos = contagem.pop("distribuicao")
    assert contagem == {"itens": 2, ACIMA: 1, NAO_COMPARAVEL: 1}
    assert grupos == json.loads((tmp_path / "rel" / "distribuicao.json").read_text(encoding="utf-8"))
    assert [(g["categoria"], g["tipo_preco"], g["escopo"], g["itens"]) for g in grupos] == [
        ("combustivel", "homologado", "municipio", 1)]
    linhas = [json.loads(linha) for linha in (tmp_path / "rel" / "comparacoes.jsonl").read_text(encoding="utf-8").splitlines()]
    acima = next(linha for linha in linhas if linha["situacao"] == ACIMA)
    assert acima["referencia"]["mediana"] == "6.190" and acima["produto"] == "GASOLINA" and acima["modo"] == "silencioso"
    with open(tmp_path / "rel" / "comparacoes.csv", encoding="utf-8-sig") as fh:
        csv_linhas = list(csv.DictReader(fh, delimiter=";"))
    assert len(csv_linhas) == 1 and csv_linhas[0]["ref_mediana"] == "6.190" and csv_linhas[0]["razao"] == "1.260"
    resumo = (tmp_path / "rel" / "resumo.md").read_text(encoding="utf-8")
    assert "modo silencioso" in resumo and "1.260×" in resumo and "R$ 78.000,00" in resumo
    assert "ainda não calibrado" in resumo and "gás de cozinha 1.25×" in resumo
    assert "Distribuição da razão" in resumo and "| combustivel | homologado | municipio | 1\\* |" in resumo


def test_cli_comparar_e_anp_resumo(cfg, apoio, capsys):
    apoio.guardar_no_bronze(cfg, anp.FONTE_ID, URL_ANP, _precos_sp(apoio), tipo="text/csv")
    apoio.municipio(cfg)
    apoio.compra(cfg, itens=[(1, "GASOLINA COMUM", "Litro", "10000", "7.00", "7.80")])
    assert main_lumen(["mercado", "anp", "resumo"]) == 0
    saida = json.loads(capsys.readouterr().out)
    assert saida["coletas"] == 20 and saida["periodo"] == ["2026-03-09", "2026-03-09"] and saida["municipios"] == 2
    assert main_lumen(["mercado", "comparar", "--de", "2026-03-01", "--ate", "2026-03-31"]) == 0
    saida = json.loads(capsys.readouterr().out)
    assert saida[ACIMA] == 1 and saida["processos"] == 1 and saida["municipios_com_nome"] == 1
    assert (cfg.raiz_dados / "mercado" / "relatorio" / "resumo.md").exists()


def test_cli_reconhecer(capsys):
    assert cli.main(["reconhecer", "ÓLEO DIESEL S10", "--unidade", "Litro"]) == 0
    assert json.loads(capsys.readouterr().out)["produto"] == "DIESEL S10"
    assert cli.main(["reconhecer", "Pneu"]) == 1


def test_cli_sem_contato(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("LUMEN_CONTATO", raising=False)
    assert cli.main(["--config", str(tmp_path / "x.toml"), "comparar"]) == 2


def test_cli_anp_baixar_e_consultas_da_silver(cfg, apoio, sem_proxy, monkeypatch, capsys):
    """``anp baixar`` guarda o semestre no bronze (404 vira código 1) e o varejo acha as consultas na silver."""
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    from lumen_ingestao.cliente_http import ClienteHttp

    conteudo = _precos_sp(apoio)

    class _Anp(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            existe = self.path.endswith("/ca/ca-2026-01.zip")
            self.send_response(200 if existe else 404)
            self.end_headers()
            self.wfile.write(conteudo if existe else b"nao encontrado")

    s = ThreadingHTTPServer(("127.0.0.1", 0), _Anp)
    threading.Thread(target=lambda: s.serve_forever(poll_interval=0.05), daemon=True).start()
    monkeypatch.setattr(anp, "BASE_SERIES", f"http://127.0.0.1:{s.server_address[1]}")
    monkeypatch.setattr(cli, "_cliente", lambda c, f: ClienteHttp(f, user_agent="Lumen/teste (+t@e.org)", rpm=6000,
                                                                abridor=sem_proxy, dormir=lambda x: None))
    assert cli.main(["anp", "baixar", "--semestres", "2026-1"]) == 0
    saida = json.loads(capsys.readouterr().out)
    assert saida[0]["status"] == 200 and saida[0]["bytes"] == len(conteudo) and saida[0]["arquivo"] == "ca-2026-1"
    assert cli.main(["anp", "baixar", "--semestres", "2025-02,"]) == 1
    capsys.readouterr()
    assert cli.main(["anp", "baixar", "--semestres", "2026-1", "--series", "ca,glp"]) == 1   # glp: 404 aqui
    assert [a["status"] for a in json.loads(capsys.readouterr().out)] == [200, 404]
    with pytest.raises(SystemExit):
        cli.main(["anp", "baixar", "--semestres", "2026-1", "--series", "querosene"])
    capsys.readouterr()
    assert cli.main(["anp", "resumo"]) == 0
    s.shutdown()

    apoio.compra(cfg, chave="11222333000181-1-000012/2026", objeto="Aquisição de equipamentos de informática",
                 itens=[(1, "Notebook Intel Core i5, 8GB RAM, SSD 256GB", "Unidade", "5", "5000", None),
                        (2, "Monitor 24 polegadas full hd", "Unidade", "5", "900", None),
                        (3, "Cadeira giratória", "Unidade", "5", "500", None)])
    assert cli._consultas_da_silver(cfg, date(2026, 3, 1), date(2026, 3, 31)) == [
        "monitor 24 polegadas full hd", "notebook i5 8gb ssd 256gb"]
    assert cli._consultas_da_silver(cfg, date(2026, 4, 1), None) == []


PLANILHA = Path(__file__).parent / "fixtures" / "revendas_lpc_amostra.xlsx"


def test_gas_de_cozinha_contra_a_planilha_semanal(cfg, apoio, tmp_path):
    apoio.guardar_no_bronze(cfg, anp.FONTE_ID, "https://www.gov.br/anp/arquivos-lpc/2026/revendas_lpc_2026-09-27_"
                            "2026-10-03.xlsx", PLANILHA.read_bytes(), tipo="application/octet-stream")
    apoio.municipio(cfg, codigo="2611606", nome="Recife", uf="PE")
    apoio.compra(cfg, chave="10000000000191-1-000020/2026", uf="PE", municipio="2611606", publicado=date(2026, 10, 1),
                 objeto="Aquisição de gás de cozinha", itens=[
                     (1, "Recarga de gás GLP P13, mediante troca do vasilhame vazio", "Recarga", "40", "150", "150"),
                     (2, "Gás GLP P45", "Unidade", "4", "500", "480")])
    # a amostra é pequena (2 revendas): mínimo do município baixado num arquivo de parâmetros do teste
    texto = (Path(__file__).parents[1] / "lumen_mercado" / "parametros_mercado.toml").read_text(encoding="utf-8")
    parametros = tmp_path / "p.toml"
    parametros.write_text(texto.replace("minimo_municipio = 5", "minimo_municipio = 2"), encoding="utf-8")
    p = ParametrosMercado.carregar(parametros)
    r = {c.descricao[:9]: c for c in comparar(
        itens_da_silver(consolidar(ler_entidade(cfg.silver, "processo_contratacao")),
                        consolidar(ler_entidade(cfg.silver, "item_contratacao")),
                        consolidar(ler_entidade(cfg.silver, "resultado_item"))),
        p, anp=cli.carregar_anp(ArmazemBronzeLocal(cfg.bronze)), municipios={"2611606": "Recife"})}
    glp = r["Recarga d"]
    assert glp.especificacao.produto == "GLP" and glp.referencia.unidade == "botijao_13kg"
    assert glp.referencia.mediana == Decimal("117.450") and glp.razao == Decimal("1.277")
    assert glp.situacao == ACIMA and glp.limiar == Decimal("1.25") and glp.valor_total == Decimal("6000.00")
    assert r["Gás GLP P"].situacao == NAO_COMPARAVEL


class _PaginaAnp(BaseHTTPRequestHandler):
    """Servidor local com a página semanal (links relativos) e as planilhas."""

    html = ""

    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path == "/semanas":
            corpo, status = _PaginaAnp.html.encode(), 200
        elif self.path.endswith("revendas_lpc_2026-09-27_2026-10-03.xlsx"):
            corpo, status = PLANILHA.read_bytes(), 200
        elif self.path.endswith("revendas_lpc_2026-09-20_2026-09-26.xlsx"):
            corpo, status = b"<html>pagina de erro</html>", 200     # chega, mas não é planilha
        else:
            corpo, status = b"nao encontrado", 404
        self.send_response(status)
        self.end_headers()
        self.wfile.write(corpo)


def test_cli_anp_semanas(cfg, sem_proxy, monkeypatch, capsys):
    from lumen_ingestao.cliente_http import ClienteHttp

    s = ThreadingHTTPServer(("127.0.0.1", 0), _PaginaAnp)
    threading.Thread(target=lambda: s.serve_forever(poll_interval=0.05), daemon=True).start()
    pagina = f"http://127.0.0.1:{s.server_address[1]}/semanas"
    monkeypatch.setattr(cli, "_cliente", lambda c, f: ClienteHttp(f, user_agent="Lumen/teste (+t@e.org)", rpm=6000,
                                                                abridor=sem_proxy, dormir=lambda x: None))
    _PaginaAnp.html = ('<a href="lpc/revendas_lpc_2026-09-13_2026-09-19.xlsx">13</a>'
                       '<a href="lpc/revendas_lpc_2026-09-20_2026-09-26.xlsx">20</a>'
                       '<a href="lpc/revendas_lpc_2026-09-27_2026-10-03.xlsx">27</a>')
    assert cli.main(["anp", "semanas", "--pagina", pagina, "--de", "2026-09-20", "--ate", "2026-10-03"]) == 0
    saida = json.loads(capsys.readouterr().out)
    assert saida["planilhas_na_pagina"] == 3 and saida["periodo_na_pagina"] == ["2026-09-13", "2026-10-03"]
    assert [b["arquivo"] for b in saida["baixadas"]] == ["2026-09-20_2026-09-26", "2026-09-27_2026-10-03"]
    assert cli.main(["anp", "semanas", "--pagina", pagina, "--ultimas", "1"]) == 0
    assert [b["arquivo"] for b in json.loads(capsys.readouterr().out)["baixadas"]] == ["2026-09-27_2026-10-03"]
    # o resumo lê a planilha e registra a que não deu para ler, sem parar a carga
    assert cli.main(["anp", "resumo"]) == 0
    resumo = json.loads(capsys.readouterr().out)
    assert resumo["coletas"] == 8 and resumo["repetidas_entre_arquivos"] == 8 and resumo["por_produto"]["GLP"] == 2
    erros = [a for a in resumo["arquivos"] if a["erro"]]
    assert len(erros) == 1 and erros[0]["url"].endswith("2026-09-20_2026-09-26.xlsx")
    # semana fora da janela: nada a baixar
    assert cli.main(["anp", "semanas", "--pagina", pagina, "--de", "2027-01-01"]) == 1
    capsys.readouterr()
    # a ANP mudou o nome dos arquivos: falha mostrando os links .xlsx que achou
    _PaginaAnp.html = '<a href="lpc/precos_2026-09-27.xlsx">x</a>'
    assert cli.main(["anp", "semanas", "--pagina", pagina]) == 1
    assert json.loads(capsys.readouterr().out)["links_xlsx"] == ["lpc/precos_2026-09-27.xlsx"]
    assert cli.main(["anp", "semanas", "--pagina", pagina.replace("semanas", "sumiu")]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == 404
    s.shutdown()


def _comparacao(categoria, razao, tipo="homologado", escopo="municipio"):
    return SimpleNamespace(razao=Decimal(razao), tipo_preco=tipo, especificacao=SimpleNamespace(categoria=categoria),
                           referencia=SimpleNamespace(escopo=escopo))


def test_distribuicao_e_sensibilidade_ao_limiar():
    lista = [_comparacao("combustivel", r) for r in ("0.95", "1.00", "1.05", "1.10", "1.15", "1.20", "1.25",
                                                     "1.30", "1.60", "2.40")]
    lista += [_comparacao("combustivel", "1.40", escopo="uf"), _comparacao("notebook", "1.10", tipo="estimado"),
              SimpleNamespace(razao=None, tipo_preco="homologado", especificacao=None, referencia=None)]
    grupos = relatorio.distribuicao(lista)
    assert [(g["categoria"], g["tipo_preco"], g["escopo"], g["itens"]) for g in grupos] == [
        ("combustivel", "homologado", "municipio", 10), ("combustivel", "homologado", "uf", 1),
        ("notebook", "estimado", "municipio", 1)]
    g = grupos[0]
    assert g["mediana"] == "1.175" and g["p10"] == "0.995" and g["p90"] == "1.680" and g["maximo"] == "2.40"
    assert g["acima_de"]["1.20"] == {"itens": 5, "fracao": "0.500"}
    assert g["acima_de"]["1.50"] == {"itens": 2, "fracao": "0.200"}
    assert g["acima_de"]["2.00"] == {"itens": 1, "fracao": "0.100"} and g["amostra_pequena"]
    assert relatorio.distribuicao([]) == []


def test_preco_fora_de_escala_zero_e_razao_extrema(cfg, apoio, tmp_path):
    """Dados da primeira execução real: estimado de R$ 1,28 o litro, orçamento sigiloso gravado como zero."""
    apoio.guardar_no_bronze(cfg, anp.FONTE_ID, URL_ANP, _precos_sp(apoio), tipo="text/csv")
    apoio.municipio(cfg)
    apoio.compra(cfg, itens=[
        (1, "Diesel S10", "Litro", "1", "1.28", None),                   # 1,28 / 6,10: simbólico
        (2, "GASOLINA COMUM", "Litro", "100", "0", None),               # sigiloso: sem preço
        (3, "GASOLINA COMUM", "Litro", "500", "20.00", None),           # 20 / 6,19 = 3,23: conferir unidade
    ])
    p = ParametrosMercado.carregar()
    assert p.razao_minima_plausivel == Decimal("0.50") and p.razao_extrema == Decimal("3.00")
    lista = list(comparar(itens_da_silver(consolidar(ler_entidade(cfg.silver, "processo_contratacao")),
                                          consolidar(ler_entidade(cfg.silver, "item_contratacao")),
                                          consolidar(ler_entidade(cfg.silver, "resultado_item"))),
                          p, anp=cli.carregar_anp(ArmazemBronzeLocal(cfg.bronze)), municipios={"3550308": "São Paulo"}))
    r = {c.quantidade: c for c in lista}
    simbolico, sigiloso, extremo = r[Decimal("1")], r[Decimal("100")], r[Decimal("500")]
    assert simbolico.situacao == FORA_DE_ESCALA and simbolico.razao == Decimal("0.210")
    assert "provável preço simbólico" in simbolico.motivo
    assert sigiloso.situacao == SEM_REFERENCIA and sigiloso.motivo == "item sem preço unitário publicado"
    assert extremo.situacao == ACIMA and "razao_extrema_conferir_unidade" in extremo.marcacoes
    contagem = relatorio.escrever(lista, tmp_path / "rel", p)
    assert contagem[FORA_DE_ESCALA] == 1
    assert [g["itens"] for g in contagem["distribuicao"]] == [1]            # o fora de escala não entra
    resumo = (tmp_path / "rel" / "resumo.md").read_text(encoding="utf-8")
    assert "Fora de escala" in resumo and "preço estimado (pesquisa de preços" in resumo
    assert "| 3.231× | GASOLINA |" in resumo and "razao_extrema_conferir_unidade" in resumo


def test_parametros_antigos_sem_os_limites_de_escala(tmp_path):
    texto = (Path(__file__).parents[1] / "lumen_mercado" / "parametros_mercado.toml").read_text(encoding="utf-8")
    sem = "\n".join(linha for linha in texto.splitlines()
                    if not linha.startswith(("razao_minima_plausivel", "razao_extrema")))
    (tmp_path / "p.toml").write_text(sem, encoding="utf-8")
    p = ParametrosMercado.carregar(tmp_path / "p.toml")
    assert p.razao_minima_plausivel == 0 and p.razao_extrema > 1000
