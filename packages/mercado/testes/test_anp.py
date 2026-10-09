"""Leitura dos arquivos de preços da ANP e montagem da referência de bomba por lugar e época.

Confere a leitura tolerante (colunas pelo nome, ``;`` ou ``,``, UTF-8 ou Windows-1252, ZIP, CSV ou a
planilha semanal .xlsx), os descartes contados por motivo, os nomes de produto da ANP nas duas publicações,
a UF pela sigla ou pelo nome, a unidade de cada produto, a mesma coleta lida em dois arquivos, o endereço
de cada semestre, os links da página semanal e a referência por município com recuo para a UF.

A planilha ``fixtures/revendas_lpc_amostra.xlsx`` foi gravada com openpyxl 3.1.5 no leiaute das planilhas
semanais reais, conferido na primeira execução do fluxo ``mercado-referencia.yml`` (9/10/2026): sete linhas
de título antes do cabeçalho, CNPJ só com dígitos (às vezes como número, sem o zero à esquerda), UF pelo
nome do estado, preço como número (``4.1900000000000004``) e data como número de série do Excel.
"""

import io
import zipfile
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from lumen_mercado import anp

PLANILHA = Path(__file__).parent / "fixtures" / "revendas_lpc_amostra.xlsx"


def test_url_de_cada_semestre():
    assert anp.url_semestre(2026, 1).endswith("/ca/ca-2026-01.zip")
    assert anp.url_semestre(2021, 2).endswith("/ca/ca-2021-02.csv")
    assert anp.url_semestre(2022, 1).endswith("/ca/precos-semestrais-ca.zip")
    assert anp.url_semestre(2026, 1, "glp").endswith("/glp/glp-2026-01.csv")
    assert anp.url_semestre(2022, 1, "glp").endswith("/glp/precos-semestrais-glp-2022-01.csv")
    assert anp.url_semestre(2021, 1, "glp").endswith("/glp/precos-semestrais-glp2021-01.csv")
    assert anp.url_semestre(2004, 2, "glp").endswith("/glp/glp-2004-02.csv")
    with pytest.raises(ValueError):
        anp.url_semestre(2026, 3)
    with pytest.raises(ValueError, match="série desconhecida"):
        anp.url_semestre(2026, 1, "querosene")


def test_leitura_com_descartes(apoio):
    conteudo = apoio.csv_anp([
        ("SP", "SÃO PAULO", "1", "GASOLINA", "02/01/2026", "6,29"),
        ("SP", "SÃO PAULO", "2", "DIESEL S10", "02/01/2026", "6,09"),
        ("SP", "SÃO PAULO", "3", "DIESEL S500", "02/01/2026", "5,99"),
        ("SP", "SÃO PAULO", "4", "GLP", "02/01/2026", "110,00"),          # GLP "por litro": unidade errada
        ("SP", "SÃO PAULO", "5", "ETANOL", "sem data", "4,19"),
        ("SP", "SÃO PAULO", "6", "ETANOL", "02/01/2026", ""),
        ("SP", "SÃO PAULO", "7", "ETANOL", "02/01/2026", "0,00"),
        ("SP", "SÃO PAULO", "8", "DIESEL S50", "02/01/2026", "6,19"),     # fora da série atual
        ("XX", "SÃO PAULO", "9", "GASOLINA", "02/01/2026", "6,29"),
    ]) + b"SE;SP;CURTA\n"
    resumo = anp.ResumoLeitura()
    coletas = list(anp.ler_csv(conteudo, resumo))
    assert [c.produto for c in coletas] == ["GASOLINA", "DIESEL S10", "DIESEL"]
    assert coletas[0].valor == Decimal("6.29") and coletas[0].data == date(2026, 1, 2)
    assert coletas[0].municipio == "SAO PAULO" and coletas[0].uf == "SP" and coletas[0].cnpj == "1"
    assert coletas[0].revenda == "POSTO 1"
    assert resumo.aproveitadas == 3 and resumo.produtos["GLP"] == 1
    assert resumo.descartadas == {"produto fora da comparação": 1, "data ilegível": 1, "UF ilegível": 1,
                                  "valor ausente ou não positivo": 2, "linha incompleta": 1,
                                  "unidade de outro produto": 1}
    assert resumo.cabecalho[1] == "Estado - Sigla"


def test_virgula_cp1252_zip_e_iso():
    texto = ("Estado - Sigla,Município,Produto,Data da Coleta,Valor de Venda\n"
             'SP,SÃO PAULO,GASOLINA ADITIVADA,2026-01-02,"6,49"\n'
             "SP,SÃO PAULO,GNV,2026-01-02,4.99\n")
    coletas = list(anp.ler_bytes(texto.encode("cp1252")))
    assert [(c.produto, c.valor) for c in coletas] == [("GASOLINA ADITIVADA", Decimal("6.49")),
                                                      ("GNV", Decimal("4.99"))]
    memoria = io.BytesIO()
    with zipfile.ZipFile(memoria, "w") as z:
        z.writestr("ca-2026-01.csv", texto.encode("utf-8"))
        z.writestr("LEIAME.txt", b"nada")
    assert len(list(anp.ler_bytes(memoria.getvalue()))) == 2


def test_arquivo_no_disco(tmp_path, apoio):
    caminho = tmp_path / "ca.csv"
    caminho.write_bytes(apoio.csv_anp([("RJ", "NITERÓI", "1", "ETANOL", "05/01/2026", "4,59")]))
    assert [c.municipio for c in anp.ler_arquivo(caminho)] == ["NITEROI"]


def test_cabecalho_sem_colunas_essenciais():
    with pytest.raises(ValueError, match="sem as colunas"):
        list(anp.ler_csv(b"Produto;Valor\nGASOLINA;6,00\n"))
    assert list(anp.ler_csv(b"")) == []
    with pytest.raises(ValueError, match="sem linha de cabe"):
        list(anp.ler_csv(b"".join(b"titulo %d\n" % i for i in range(40))))


def test_planilha_semanal():
    resumo = anp.ResumoLeitura()
    coletas = list(anp.ler_arquivo(PLANILHA, resumo))
    assert [c.produto for c in coletas] == ["GASOLINA", "ETANOL", "DIESEL S10", "GASOLINA ADITIVADA", "DIESEL",
                                            "GNV", "GLP", "GLP"]
    primeira = coletas[0]
    assert (primeira.uf, primeira.municipio, primeira.data) == ("SP", "SAO PAULO", date(2026, 9, 29))
    assert anp._cnpj("198451000185") == "00198451000185" == anp._cnpj(" 00.198.451/0001-85")
    assert anp._cnpj("") == "" and anp._cnpj("123") == "123"
    assert primeira.cnpj == "11111111000101" and primeira.revenda == "AUTO POSTO UM LTDA"
    assert coletas[3].valor == Decimal("6.490")                  # 6.4899999999999993 da planilha
    glp = coletas[6:]
    assert [(c.uf, c.valor, c.data) for c in glp] == [("PE", Decimal("115"), date(2026, 9, 30)),
                                                    ("PE", Decimal("119.9"), date(2026, 9, 30))]
    assert resumo.cabecalho[0] == "CNPJ" and resumo.cabecalho[-1] == "DATA DA COLETA"
    assert resumo.descartadas == {"unidade de outro produto": 1, "valor ausente ou não positivo": 1,
                                  "UF ilegível": 1}
    assert resumo.produtos["GLP"] == 3 and resumo.produtos["DIESEL S10"] == 1 and resumo.produtos["ETANOL"] == 1
    assert glp[1].cnpj == "04444444000104"          # número no Excel: o zero à esquerda volta


def test_mesma_coleta_em_dois_arquivos(apoio):
    semestral = apoio.csv_anp([("SP", "SÃO PAULO", "11.111.111/0001-01", "GASOLINA", "29/09/2026", "6,29"),
                               ("SP", "SÃO PAULO", "99.999.999/0001-99", "GASOLINA", "29/09/2026", "6,39")])
    precos = anp.PrecosAnp(anp.ler_bytes(semestral))
    assert [precos.adicionar(c) for c in anp.ler_arquivo(PLANILHA)][:2] == [False, True]
    assert precos.repetidas == 1 and precos.total == 9
    assert precos.produtos()["GASOLINA"] == 2 and precos.produtos()["GLP"] == 2
    # sem CNPJ não há como saber se é a mesma coleta: entra
    sem_cnpj = anp.Coleta(uf="SP", municipio="SAO PAULO", produto="GASOLINA", data=date(2026, 9, 29),
                          valor=Decimal("6.29"))
    assert precos.adicionar(sem_cnpj) and precos.adicionar(sem_cnpj)


def test_milesimo_arredondado():
    precos = anp.PrecosAnp([anp.Coleta(uf="SP", municipio="X", produto="GASOLINA", data=date(2026, 1, 1),
                                       valor=Decimal("6.2896"), cnpj=str(i)) for i in range(5)])
    assert precos.referencia("GASOLINA", "SP", "X", date(2026, 1, 1)).mediana == Decimal("6.290")


@pytest.mark.parametrize("produto, unidade, confere", [
    ("GASOLINA", "R$ / litro", True), ("GASOLINA", "", True), ("GASOLINA", "R$ / m³", False),
    ("GASOLINA", "R$ / 13 kg", False), ("GNV", "R$ / m³", True), ("GNV", "R$ / litro", False),
    ("GLP", "R$ / 13 kg", True), ("GLP", "R$/13kg", True), ("GLP", "R$ / 45 kg", False),
    ("GLP", "R$ / litro", False), ("GLP", "R$ / botijão", True),
])
def test_unidade_de_cada_produto(produto, unidade, confere):
    assert anp._unidade_confere(produto, unidade) is confere


def test_uf_pela_sigla_ou_pelo_nome():
    assert anp._uf("sp") == "SP" and anp._uf("SAO PAULO") == "SP" and anp._uf("Rio Grande do Norte") == "RN"
    assert anp._uf("Distrito Federal") == "DF" and anp._uf("Mato Grosso") == "MT"
    assert anp._uf("Mato Grosso do Sul") == "MS" and anp._uf("XX") is None and anp._uf("") is None


def test_produtos_com_os_nomes_das_duas_publicacoes():
    nomes = {"GASOLINA COMUM": "GASOLINA", "ETANOL HIDRATADO": "ETANOL", "OLEO DIESEL S10": "DIESEL S10",
             "ÓLEO DIESEL S-10": "DIESEL S10", "OLEO DIESEL": "DIESEL", "DIESEL S500": "DIESEL", "GLP": "GLP",
             "GNV": "GNV", "GASOLINA ADITIVADA": "GASOLINA ADITIVADA", "DIESEL S50": None, "QUEROSENE": None}
    assert {n: anp._produto(n) for n in nomes} == nomes


def test_data_em_texto_ou_numero_de_serie():
    assert anp._data("02/01/2026") == date(2026, 1, 2) == anp._data("2026-01-02 00:00:00")
    assert anp._data("46294") == date(2026, 9, 29) and anp._data("46294.0") == date(2026, 9, 29)
    assert anp._data("6") is None and anp._data("") is None


PAGINA = """<html><body>
<a href="https://www.gov.br/anp/pt-br/assuntos/precos/arquivos-lpc/2026/revendas_lpc_2026-09-27_2026-10-03.xlsx">
Revendas 27/09 a 03/10</a>
<a href='/anp/pt-br/arquivos-lpc/2026/revendas_lpc_2026-08-30-2026-09-5.xlsx'>Revendas 30/08 a 05/09</a>
<a href="arquivos-lpc/2026/revendas_lpc_2026-09-13_2026-09-19.xlsx/@@download/file">Revendas 13/09</a>
<a href="https://www.gov.br/anp/pt-br/assuntos/precos/arquivos-lpc/2026/revendas_lpc_2026-09-27_2026-10-03.xlsx">
de novo</a>
<a href="arquivos-lpc/2026/revendas_lpc_2026-09-13_2026-09-19.xlsx/view">visualizar</a>
<a href="/arquivos-lpc/2026/revendas_lpc_2026-02-30_2026-03-06.xlsx">data impossível</a>
<a href="/arquivos-lpc/2026/resumo_semanal_lpc_2026-09-27_2026-10-03.xlsx">síntese, não é posto a posto</a>
</body></html>"""


def test_links_da_pagina_semanal():
    semanas = anp.links_semanais(PAGINA, "https://www.gov.br/anp/pt-br/assuntos/precos/semanas")
    assert [(s.inicio, s.fim) for s in semanas] == [(date(2026, 8, 30), date(2026, 9, 5)),
                                                    (date(2026, 9, 13), date(2026, 9, 19)),
                                                    (date(2026, 9, 27), date(2026, 10, 3))]
    assert semanas[0].url == "https://www.gov.br/anp/pt-br/arquivos-lpc/2026/revendas_lpc_2026-08-30-2026-09-5.xlsx"
    assert semanas[1].url.endswith("/assuntos/precos/arquivos-lpc/2026/revendas_lpc_2026-09-13_2026-09-19.xlsx"
                                   "/@@download/file")      # entre a visualização e o download, o download
    assert anp.links_semanais("") == []
    janela = anp.semanas_na_janela(semanas, date(2026, 9, 6), date(2026, 9, 27))
    assert [s.inicio for s in janela] == [date(2026, 9, 13), date(2026, 9, 27)]
    assert anp.semanas_na_janela(semanas, None, None) == semanas


def test_chave_de_municipio():
    assert anp.chave_municipio("Santa Bárbara d'Oeste") == anp.chave_municipio("SANTA BARBARA D OESTE")
    assert anp.chave_municipio("São Paulo") == "SAO PAULO"


def test_referencia_por_municipio_e_uf(apoio):
    linhas = [("PE", "RECIFE", str(i), "GASOLINA", f"{d:02d}/02/2026", f"6,{40 + i}") for i, d in
              enumerate([2, 3, 4, 5, 6, 20])]
    linhas += [("PE", "CARUARU", str(10 + i), "GASOLINA", "04/02/2026", f"6,{60 + i}") for i in range(6)]
    precos = anp.PrecosAnp(anp.ler_csv(apoio.csv_anp(linhas)))
    assert precos.total == 12 and precos.municipios() == {("PE", "RECIFE"), ("PE", "CARUARU")}
    assert precos.periodo() == (date(2026, 2, 2), date(2026, 2, 20))
    ref = precos.referencia("GASOLINA", "pe", "Recife", date(2026, 2, 4))
    assert ref.escopo == "municipio" and ref.quantidade == 5 and ref.mediana == Decimal("6.420")
    assert ref.periodo == (date(2026, 2, 2), date(2026, 2, 6)) and ref.unidade == "litro"
    assert ref.evidencias[0].descricao == "posto 0" and ref.para_dict()["minimo"] == "6.400"
    # Petrolina não tem coleta: vale a UF, com as 11 coletas da janela
    ref = precos.referencia("GASOLINA", "PE", "Petrolina", date(2026, 2, 4))
    assert ref.escopo == "uf" and ref.quantidade == 11
    glp = anp.PrecosAnp(anp.ler_arquivo(PLANILHA)).referencia("GLP", "PE", "Recife", date(2026, 10, 1),
                                                               minimo_municipio=2)
    assert glp.unidade == "botijao_13kg" and glp.mediana == Decimal("117.450") and glp.escopo == "municipio"
    assert precos.referencia("ETANOL", "PE", "Recife", date(2026, 2, 4)) is None
    assert anp.PrecosAnp().periodo() is None
