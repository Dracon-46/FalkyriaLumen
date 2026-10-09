"""Leitura de planilhas .xlsx só com a biblioteca padrão (ADR-015), para os arquivos semanais da ANP.

Um .xlsx é um ZIP de XML (Office Open XML, ECMA-376). Para tirar as linhas de uma aba bastam três peças:
o ``xl/workbook.xml`` e o ``xl/_rels/workbook.xml.rels`` (qual arquivo é a primeira aba), o
``xl/sharedStrings.xml`` (os textos, guardados uma vez só e referenciados por índice) e a própria aba
(``xl/worksheets/sheetN.xml``), lida em fluxo com ``iterparse`` para não carregar dezenas de milhares de
linhas de XML na memória de uma vez.

Fica de fora tudo o que não muda o valor: estilos, fórmulas (vale o valor calculado que vem gravado),
mesclagem e formatação. Datas chegam como o número de série do Excel; quem lê sabe qual coluna é data e
converte com ``data_do_excel``.
"""

from __future__ import annotations

import io
import re
import zipfile
from datetime import date, timedelta
from typing import Iterator
from xml.etree import ElementTree

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
NS_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
NS_PKG = "{http://schemas.openxmlformats.org/package/2006/relationships}"
EPOCA_EXCEL = date(1899, 12, 30)


def eh_xlsx(conteudo: bytes) -> bool:
    """O conteúdo é um ZIP com ``xl/workbook.xml`` (uma pasta de trabalho do Excel)?"""
    if conteudo[:4] != b"PK\x03\x04":
        return False
    try:
        with zipfile.ZipFile(io.BytesIO(conteudo)) as z:
            return "xl/workbook.xml" in z.namelist()
    except zipfile.BadZipFile:
        return False


def coluna_da_referencia(referencia: str) -> int:
    """Índice (a partir de 0) da coluna de uma referência de célula: ``A1`` → 0, ``AB12`` → 27."""
    letras = re.match(r"[A-Z]+", referencia or "")
    if not letras:
        raise ValueError(f"referência de célula inválida: {referencia!r}")
    indice = 0
    for letra in letras.group(0):
        indice = indice * 26 + (ord(letra) - ord("A") + 1)
    return indice - 1


def data_do_excel(valor: str) -> date | None:
    """Data a partir do número de série do Excel (dias desde 30/12/1899); None se não for um número plausível."""
    try:
        serie = float(valor)
    except (TypeError, ValueError):
        return None
    if not 1 <= serie <= 200000:
        return None
    return EPOCA_EXCEL + timedelta(days=int(serie))


def _textos_compartilhados(z: zipfile.ZipFile) -> list[str]:
    """Os textos de ``sharedStrings.xml``, na ordem dos índices; lista vazia se a planilha não tiver."""
    if "xl/sharedStrings.xml" not in z.namelist():
        return []
    textos = []
    for _, elemento in ElementTree.iterparse(io.BytesIO(z.read("xl/sharedStrings.xml"))):
        if elemento.tag == f"{NS}si":
            textos.append("".join(t.text or "" for t in elemento.iter(f"{NS}t")))
            elemento.clear()
    return textos


def _caminho_da_aba(z: zipfile.ZipFile, indice: int) -> str:
    """Caminho dentro do ZIP da aba de número ``indice`` (0 é a primeira), pela relação do workbook."""
    pasta = ElementTree.fromstring(z.read("xl/workbook.xml"))
    abas = pasta.findall(f"{NS}sheets/{NS}sheet")
    if not abas:
        raise ValueError("planilha sem abas")
    if indice >= len(abas):
        raise ValueError(f"a planilha tem {len(abas)} aba(s); pedida a {indice + 1}ª")
    rid = abas[indice].get(f"{NS_REL}id")
    if "xl/_rels/workbook.xml.rels" in z.namelist() and rid:
        relacoes = ElementTree.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        for r in relacoes.findall(f"{NS_PKG}Relationship"):
            if r.get("Id") == rid:
                alvo = r.get("Target", "").lstrip("/")
                return alvo if alvo.startswith("xl/") else f"xl/{alvo}"
    return f"xl/worksheets/sheet{indice + 1}.xml"


def _valor(celula: ElementTree.Element, textos: list[str]) -> str:
    """Valor de uma célula como texto: string compartilhada, string em linha, booleano ou número cru."""
    tipo = celula.get("t")
    if tipo == "inlineStr":
        return "".join(t.text or "" for t in celula.iter(f"{NS}t"))
    v = celula.find(f"{NS}v")
    if v is None or v.text is None:
        return ""
    if tipo == "s":
        indice = int(v.text)
        return textos[indice] if 0 <= indice < len(textos) else ""
    return v.text


def linhas(conteudo: bytes, aba: int = 0) -> Iterator[list[str]]:
    """Linhas de uma aba como listas de texto, com as colunas vazias preenchidas com ``""``.

    Linhas que o arquivo pula (por estarem vazias) não aparecem. Os números vêm como o Excel os gravou
    (``6.29``, ``45900``), sem formatação.
    """
    with zipfile.ZipFile(io.BytesIO(conteudo)) as z:
        textos = _textos_compartilhados(z)
        caminho = _caminho_da_aba(z, aba)
        with z.open(caminho) as fh:
            for _, elemento in ElementTree.iterparse(fh):
                if elemento.tag != f"{NS}row":
                    continue
                valores: dict[int, str] = {}
                proxima = 0
                for celula in elemento.findall(f"{NS}c"):
                    referencia = celula.get("r")
                    coluna = coluna_da_referencia(referencia) if referencia else proxima
                    valores[coluna] = _valor(celula, textos)
                    proxima = coluna + 1
                elemento.clear()
                if valores:
                    yield [valores.get(i, "") for i in range(max(valores) + 1)]
