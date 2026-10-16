"""Leitor de .xlsx sem dependências: as formas de célula que o Excel e outras ferramentas gravam.

A planilha da ANP é lida pelo teste de ``anp``; aqui as pastas de trabalho são montadas à mão, em XML, para
cobrir o que uma ferramenta grava e outra não: texto compartilhado com trechos formatados, texto em linha,
célula sem a referência ``r``, coluna pulada, linha vazia, aba indicada pela relação do workbook com
caminho absoluto, segunda aba e arquivo que não é planilha.
"""

import io
import zipfile
from datetime import date

import pytest
from lumen_mercado import xlsx

_NS = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
_NS_R = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'


def _pasta(abas: dict[str, str], textos: list[str] | None = None, alvo_absoluto: bool = False) -> bytes:
    """Monta um .xlsx mínimo com as abas dadas ({nome: XML das linhas}) e os textos compartilhados."""
    memoria = io.BytesIO()
    with zipfile.ZipFile(memoria, "w") as z:
        folhas = "".join(f'<sheet name="{nome}" sheetId="{i + 1}" r:id="rId{i + 1}"/>' for i, nome in enumerate(abas))
        z.writestr("xl/workbook.xml", f"<workbook {_NS} {_NS_R}><sheets>{folhas}</sheets></workbook>")
        prefixo = "/xl/" if alvo_absoluto else ""
        relacoes = "".join(
            f'<Relationship Id="rId{i + 1}" Type="worksheet" Target="{prefixo}worksheets/aba{i + 1}.xml"/>'
            for i in range(len(abas)))
        z.writestr("xl/_rels/workbook.xml.rels",
                   f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   f"{relacoes}</Relationships>")
        for i, linhas in enumerate(abas.values()):
            z.writestr(f"xl/worksheets/aba{i + 1}.xml", f"<worksheet {_NS}><sheetData>{linhas}</sheetData></worksheet>")
        if textos is not None:
            itens = "".join(t if t.startswith("<si>") else f"<si><t>{t}</t></si>" for t in textos)
            z.writestr("xl/sharedStrings.xml", f"<sst {_NS}>{itens}</sst>")
    return memoria.getvalue()


def test_formas_de_celula():
    linhas = (
        '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="C1" t="s"><v>1</v></c></row>'
        '<row r="2"/>'
        '<row r="3"><c r="B3" t="inlineStr"><is><t>em linha</t></is></c><c r="D3"><v>6.29</v></c>'
        '<c r="E3" t="b"><v>1</v></c><c r="F3"/><c r="G3" t="s"><v>99</v></c></row>'
        '<row r="4"><c t="s"><v>2</v></c><c><v>46294</v></c></row>'
    )
    conteudo = _pasta({"Dados": linhas}, ["PRODUTO", "VALOR", "<si><r><t>GASOLINA </t></r><r><t>COMUM</t></r></si>"])
    assert xlsx.eh_xlsx(conteudo)
    assert list(xlsx.linhas(conteudo)) == [
        ["PRODUTO", "", "VALOR"],
        ["", "em linha", "", "6.29", "1", "", ""],
        ["GASOLINA COMUM", "46294"],
    ]


def test_aba_pela_relacao_e_segunda_aba():
    conteudo = _pasta({"Capa": '<row r="1"><c r="A1" t="inlineStr"><is><t>capa</t></is></c></row>',
                       "Dados": '<row r="1"><c r="B1"><v>7</v></c></row>'}, alvo_absoluto=True)
    assert list(xlsx.linhas(conteudo)) == [["capa"]]
    assert list(xlsx.linhas(conteudo, aba=1)) == [["", "7"]]
    with pytest.raises(ValueError, match="2 aba"):
        list(xlsx.linhas(conteudo, aba=2))


def test_sem_relacoes_usa_o_nome_padrao():
    memoria = io.BytesIO()
    with zipfile.ZipFile(memoria, "w") as z:
        z.writestr("xl/workbook.xml", f'<workbook {_NS} {_NS_R}><sheets><sheet name="a" sheetId="1" r:id="rId9"/>'
                                      "</sheets></workbook>")
        z.writestr("xl/worksheets/sheet1.xml", f'<worksheet {_NS}><sheetData><row><c><v>1</v></c></row>'
                                               "</sheetData></worksheet>")
    assert list(xlsx.linhas(memoria.getvalue())) == [["1"]]


def test_planilha_sem_abas():
    memoria = io.BytesIO()
    with zipfile.ZipFile(memoria, "w") as z:
        z.writestr("xl/workbook.xml", f"<workbook {_NS}><sheets/></workbook>")
    with pytest.raises(ValueError, match="sem abas"):
        list(xlsx.linhas(memoria.getvalue()))


def test_nao_e_planilha():
    memoria = io.BytesIO()
    with zipfile.ZipFile(memoria, "w") as z:
        z.writestr("ca-2026-01.csv", "a;b\n")
    assert not xlsx.eh_xlsx(memoria.getvalue())
    assert not xlsx.eh_xlsx(b"PK\x03\x04 corrompido") and not xlsx.eh_xlsx(b"Produto;Valor\n")


def test_coluna_e_data():
    assert [xlsx.coluna_da_referencia(r) for r in ("A1", "Z9", "AA1", "AB12", "XFD1")] == [0, 25, 26, 27, 16383]
    with pytest.raises(ValueError):
        xlsx.coluna_da_referencia("12")
    assert xlsx.data_do_excel("46294") == date(2026, 9, 29) and xlsx.data_do_excel("46294.75") == date(2026, 9, 29)
    assert xlsx.data_do_excel("0") is None and xlsx.data_do_excel("abc") is None and xlsx.data_do_excel(None) is None
