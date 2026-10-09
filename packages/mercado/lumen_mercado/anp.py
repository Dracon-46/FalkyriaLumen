"""Preço de bomba dos combustíveis pela série histórica da ANP (ADR-027, seção 2.1).

A ANP pesquisa toda semana, por empresa contratada, o preço de venda ao consumidor em postos de centenas de
municípios e publica o resultado como dado aberto, posto a posto, em arquivos semestrais::

    https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/shpc/dsas/ca/ca-AAAA-0S.zip

(até 2021, ``.csv`` direto; o primeiro semestre de 2022 tem nome próprio, ``precos-semestrais-ca.zip``).
O gás de cozinha (GLP no botijão de 13 kg) tem série própria, no mesmo formato, na pasta ``glp``, sempre em
``.csv`` (``glp-AAAA-0S.csv``).

A série semestral só sai depois que o semestre fecha. Para o presente, a ANP publica na página do
levantamento semanal uma planilha por semana (``revendas_lpc_<início>_<fim>.xlsx``), também posto a posto,
com combustíveis e GLP; em outubro de 2026 a página citava 192 semanas, de setembro de 2022 em diante. Os nomes dos arquivos não seguem um padrão fixo, então os endereços são
tirados da própria página (``links_semanais``), e a planilha é lida sem dependências (``xlsx``).

É a melhor régua de mercado que existe para um item público: é oficial, independente de quem compra, tem
data, lugar e posto de cada preço, e cobre o passado — dá para comparar uma compra de março com o preço de
bomba de março, coisa que nenhuma loja online oferece.

A leitura é tolerante ao formato, porque o arquivo já mudou de compactação e de nome ao longo dos anos: as
colunas são achadas pelo nome sem acento e sem pontuação (``Estado - Sigla`` → ``estadosigla``), a linha
do cabeçalho é procurada (a planilha semanal tem título antes dela), o separador é detectado, e a
codificação é UTF-8 com recuo para Windows-1252. A UF vem como sigla ou pelo nome do estado; a data, como
texto ou como número de série do Excel. Linha sem produto conhecido, sem UF, sem data, sem valor positivo
ou com unidade de outro produto é contada e descartada, nunca adivinhada. A mesma coleta (posto, produto e
data) lida em dois arquivos, o semanal e o semestral, conta uma vez só.
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from html import unescape
from pathlib import Path
from typing import Iterable, Iterator
from urllib.parse import urljoin

from lumen_canonico.ufs import UFS

from . import xlsx
from .especificacao import (
    DIESEL_S10,
    DIESEL_S500,
    ETANOL,
    GASOLINA,
    GASOLINA_ADITIVADA,
    GLP,
    GNV,
    sem_acento,
    unidade_do_produto,
)
from .referencia import Evidencia, ReferenciaMercado

BASE_SERIES = "https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/shpc/dsas"
PAGINA_SERIES = "https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/serie-historica-de-precos-de-combustiveis"
PAGINA_SEMANAS = ("https://www.gov.br/anp/pt-br/assuntos/precos-e-defesa-da-concorrencia/precos/"
                  "levantamento-de-precos-de-combustiveis-ultimas-semanas-pesquisadas")
FONTE_ID = "anp_precos_combustiveis"
PRODUTOS = {GASOLINA, GASOLINA_ADITIVADA, ETANOL, DIESEL_S10, DIESEL_S500, GNV, GLP}
SERIES = {"ca": "combustíveis automotivos", "glp": "gás de cozinha (GLP P13)"}

# Nomes de coluna sem acento, sem espaço e sem pontuação, com as variações já vistas na série semestral
# (``Estado - Sigla``, ``Valor de Venda``) e na planilha semanal (``ESTADO``, ``PREÇO DE REVENDA``).
_COLUNAS = {
    "uf": ("estadosigla", "siglaestado", "siglauf", "estado", "uf"),
    "municipio": ("municipio",),
    "produto": ("produto",),
    "data": ("datadacoleta", "datacoleta", "data"),
    "valor": ("valordevenda", "precovenda", "valorvenda", "precoderevenda", "precorevenda"),
    "unidade": ("unidadedemedida", "unidade"),
    "cnpj": ("cnpjdarevenda", "cnpj"),
    "revenda": ("revenda", "nomedarevenda", "razao", "razaosocial"),
}
_MAX_LINHAS_ANTES_DO_CABECALHO = 30


# Nomes fora do padrão, tirados da página da série histórica (conferidos em 9/10/2026).
_NOMES_SEMESTRAIS = {
    ("ca", 2022, 1): "precos-semestrais-ca.zip",
    ("glp", 2022, 1): "precos-semestrais-glp-2022-01.csv",
    ("glp", 2021, 1): "precos-semestrais-glp2021-01.csv",
}


def url_semestre(ano: int, semestre: int, serie: str = "ca") -> str:
    """Endereço do arquivo semestral de uma série da ANP: ``ca`` (combustíveis) ou ``glp`` (gás de cozinha).

    Combustíveis: ``ca-AAAA-0S.zip`` desde 2022 e ``.csv`` antes. Gás de cozinha: sempre ``.csv``
    (``glp-AAAA-0S.csv``). Os semestres com nome próprio estão em ``_NOMES_SEMESTRAIS``; o teste de contrato
    confere que a página da série continua citando o endereço montado aqui.
    """
    if semestre not in (1, 2):
        raise ValueError(f"semestre deve ser 1 ou 2: {semestre}")
    if serie not in SERIES:
        raise ValueError(f"série desconhecida: {serie!r}; use {sorted(SERIES)}")
    nome = _NOMES_SEMESTRAIS.get((serie, ano, semestre))
    if nome is None:
        extensao = "zip" if serie == "ca" and ano >= 2022 else "csv"
        nome = f"{serie}-{ano}-{semestre:02d}.{extensao}"
    return f"{BASE_SERIES}/{serie}/{nome}"


@dataclass(frozen=True)
class SemanaAnp:
    """Uma planilha semanal do levantamento de preços: a semana que ela cobre e o endereço."""

    inicio: date
    fim: date
    url: str


_LINK_SEMANAL = re.compile(
    r"""href=["']([^"']*?revendas_lpc_(\d{4})-(\d{1,2})-(\d{1,2})[_-](\d{4})-(\d{1,2})-(\d{1,2})[^"']*?\.xlsx[^"']*)["']""",
    re.IGNORECASE)


def _preferencia(url: str) -> tuple[int, int]:
    """Ordem de escolha entre links da mesma semana: o arquivo direto, depois o ``@@download``, depois o resto."""
    caminho = url.split("?", 1)[0].rstrip("/")
    nivel = 0 if caminho.lower().endswith(".xlsx") else 1 if "@@download" in caminho else 2
    return nivel, len(url)


def links_semanais(html: str, base: str = PAGINA_SEMANAS) -> list[SemanaAnp]:
    """Planilhas semanais (``revendas_lpc_...xlsx``) citadas na página do levantamento, da mais antiga à mais nova.

    O nome do arquivo varia (``2026-09-27_2026-10-03``, ``2026-08-30-2026-09-5``); as datas são lidas com
    dia e mês de um ou dois dígitos, e os links relativos viram absolutos. Quando a mesma semana aparece em
    mais de um link (o arquivo, a página de visualização, o ``@@download``), vale o do arquivo. Link com data
    impossível é ignorado.
    """
    semanas: dict[tuple[date, date], SemanaAnp] = {}
    for m in _LINK_SEMANAL.finditer(html or ""):
        try:
            inicio = date(int(m.group(2)), int(m.group(3)), int(m.group(4)))
            fim = date(int(m.group(5)), int(m.group(6)), int(m.group(7)))
        except ValueError:
            continue
        url = urljoin(base, unescape(m.group(1)))
        atual = semanas.get((inicio, fim))
        if atual is None or _preferencia(url) < _preferencia(atual.url):
            semanas[(inicio, fim)] = SemanaAnp(inicio=inicio, fim=fim, url=url)
    return [semanas[k] for k in sorted(semanas)]


def semanas_na_janela(semanas: Iterable[SemanaAnp], de: date | None, ate: date | None) -> list[SemanaAnp]:
    """As semanas que se sobrepõem à janela ``[de, ate]`` (sem limite do lado que for None)."""
    return [s for s in semanas if (de is None or s.fim >= de) and (ate is None or s.inicio <= ate)]


def chave_municipio(nome: str | None) -> str:
    """Nome de município comparável entre fontes: sem acento, sem pontuação, em maiúsculas.

    ``Santa Bárbara d'Oeste`` e ``SANTA BARBARA D OESTE`` viram a mesma chave.
    """
    return re.sub(r"[^a-z0-9]+", " ", sem_acento(nome)).strip().upper()


def _coluna(cabecalho: list[str]) -> dict[str, int]:
    """Posição de cada coluna necessária no cabeçalho; levanta ``ValueError`` se faltar alguma essencial."""
    normal = [re.sub(r"[^a-z0-9]", "", sem_acento(c)) for c in cabecalho]
    posicoes: dict[str, int] = {}
    for campo, nomes in _COLUNAS.items():
        for nome in nomes:
            if nome in normal:
                posicoes[campo] = normal.index(nome)
                break
    faltando = {"uf", "municipio", "produto", "data", "valor"} - set(posicoes)
    if faltando:
        raise ValueError(f"arquivo da ANP sem as colunas {sorted(faltando)}; cabeçalho: {cabecalho}")
    return posicoes


def _valor(texto: str) -> Decimal | None:
    """``6,49`` ou ``6.49`` em ``Decimal``; None se vazio, inválido ou não positivo."""
    t = (texto or "").strip().replace("R$", "").replace(" ", "")
    if not t:
        return None
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        v = Decimal(t)
    except InvalidOperation:
        return None
    if v.as_tuple().exponent < -3:     # número de planilha (6.2899999999999991): milésimo de real basta
        v = v.quantize(Decimal("0.001"), rounding=ROUND_HALF_EVEN)
    return v if v > 0 else None


def _data(texto: str) -> date | None:
    """``02/01/2026``, ``2026-01-02`` ou número de série do Excel (``46024``) em ``date``; None se nenhum."""
    t = (texto or "").strip()
    if re.fullmatch(r"\d{5}(\.\d+)?", t):
        return xlsx.data_do_excel(t)
    for formato in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(t[:10], formato).date()
        except ValueError:
            continue
    return None


# Nomes da planilha semanal que diferem dos da série semestral.
_NOMES_SEMANAIS = {"GASOLINA COMUM": GASOLINA, "ETANOL HIDRATADO": ETANOL, "DIESEL S500": DIESEL_S500,
                   "GLP P13": GLP, "GAS LIQUEFEITO DE PETROLEO": GLP}


def _produto(texto: str) -> str | None:
    """Produto canônico a partir do nome da ANP (``DIESEL S10``, ``OLEO DIESEL S10``, ``GLP``); None se fora."""
    t = re.sub(r"\s+", " ", sem_acento(texto)).upper().replace("S-10", "S10").replace("S-500", "S500")
    t = re.sub(r"^OLEO ", "", t)
    t = _NOMES_SEMANAIS.get(t, t)
    return t if t in PRODUTOS else None


_UF_POR_NOME = {re.sub(r"[^a-z]", "", sem_acento(nome)): sigla for sigla, nome, _ in UFS.values()}
_SIGLAS = set(_UF_POR_NOME.values())


def _uf(texto: str) -> str | None:
    """Sigla da UF a partir da sigla ou do nome do estado (``SP``, ``SAO PAULO``, ``São Paulo``)."""
    t = (texto or "").strip().upper()
    if t in _SIGLAS:
        return t
    return _UF_POR_NOME.get(re.sub(r"[^a-z]", "", sem_acento(texto)))


def _cnpj(texto: str) -> str:
    """CNPJ só com dígitos e com os zeros à esquerda que a planilha semanal perde (``198451000185``)."""
    digitos = re.sub(r"\D", "", texto or "")
    return digitos.zfill(14) if 8 <= len(digitos) <= 14 else digitos


def _unidade_confere(produto: str, texto: str | None) -> bool:
    """A unidade de medida da linha é compatível com a do produto? Vazia ou desconhecida, aceita.

    Só recusa o que é claramente de outro produto: preço por quilo ou por m³ numa linha de combustível
    líquido, por litro no GNV, ou por botijão de outro tamanho no GLP.
    """
    t = sem_acento(texto).replace("³", "3")
    if not t:
        return True
    esperada = unidade_do_produto(produto)
    if esperada == "botijao_13kg":
        return not re.search(r"litro|m3", t) and (not re.search(r"kg", t) or bool(re.search(r"\b13 ?kg", t)))
    if esperada == "m3":
        return not re.search(r"litro|kg", t)
    return not re.search(r"\bkg\b|\d ?kg|m3", t)


@dataclass(frozen=True)
class Coleta:
    """Um preço de venda pesquisado pela ANP: posto, lugar, produto, data e valor."""

    uf: str
    municipio: str
    produto: str
    data: date
    valor: Decimal
    cnpj: str | None = None
    revenda: str | None = None


@dataclass
class ResumoLeitura:
    """Contagem de uma leitura: linhas aproveitadas, descartadas por motivo e o cabeçalho encontrado."""

    aproveitadas: int = 0
    descartadas: dict[str, int] = field(default_factory=dict)
    cabecalho: list[str] = field(default_factory=list)
    produtos: dict[str, int] = field(default_factory=dict)
    arquivos: list[dict] = field(default_factory=list)

    def descartar(self, motivo: str) -> None:
        """Conta uma linha descartada pelo motivo dado."""
        self.descartadas[motivo] = self.descartadas.get(motivo, 0) + 1


def _texto(conteudo: bytes) -> str:
    """Bytes do CSV em texto: UTF-8 (com ou sem BOM) e, se não for, Windows-1252."""
    try:
        return conteudo.decode("utf-8-sig")
    except UnicodeDecodeError:
        return conteudo.decode("cp1252")


def _normal(celula: str) -> str:
    """Nome de coluna sem acento, sem espaço e sem pontuação."""
    return re.sub(r"[^a-z0-9]", "", sem_acento(celula))


def _ler_linhas(linhas: Iterable[list[str]], resumo: ResumoLeitura) -> Iterator[Coleta]:
    """Coletas de linhas já separadas em células: acha o cabeçalho e converte o resto, contando os descartes.

    O cabeçalho é a primeira linha com a coluna ``produto`` entre as ``_MAX_LINHAS_ANTES_DO_CABECALHO``
    primeiras (a planilha semanal tem título e notas antes dele). Arquivo com conteúdo e sem esse cabeçalho
    (uma página de erro no lugar da planilha, um formato novo) levanta ``ValueError``; vazio não dá nada.
    """
    pos = None
    antes = 0
    for linha in linhas:
        if pos is None:
            if "produto" in {_normal(c) for c in linha}:
                resumo.cabecalho = [c.strip() for c in linha]
                pos = _coluna(resumo.cabecalho)
                continue
            antes += 1
            if antes > _MAX_LINHAS_ANTES_DO_CABECALHO:
                break
            continue
        if not linha or all(not c.strip() for c in linha):
            continue
        if len(linha) <= max(pos.values()):
            resumo.descartar("linha incompleta")
            continue
        nome_produto = linha[pos["produto"]].strip()
        resumo.produtos[nome_produto] = resumo.produtos.get(nome_produto, 0) + 1
        produto = _produto(nome_produto)
        if produto is None:
            resumo.descartar("produto fora da comparação")
            continue
        uf = _uf(linha[pos["uf"]])
        if uf is None:
            resumo.descartar("UF ilegível")
            continue
        quando = _data(linha[pos["data"]])
        if quando is None:
            resumo.descartar("data ilegível")
            continue
        valor = _valor(linha[pos["valor"]])
        if valor is None:
            resumo.descartar("valor ausente ou não positivo")
            continue
        if "unidade" in pos and not _unidade_confere(produto, linha[pos["unidade"]]):
            resumo.descartar("unidade de outro produto")
            continue
        resumo.aproveitadas += 1
        cnpj = _cnpj(linha[pos["cnpj"]]) if "cnpj" in pos else ""
        yield Coleta(uf=uf, municipio=chave_municipio(linha[pos["municipio"]]), produto=produto, data=quando,
                     valor=valor, cnpj=cnpj or None,
                     revenda=linha[pos["revenda"]].strip() or None if "revenda" in pos else None)
    if pos is None and antes:
        raise ValueError("arquivo da ANP sem linha de cabeçalho com a coluna 'Produto'")


def ler_csv(conteudo: bytes, resumo: ResumoLeitura | None = None) -> Iterator[Coleta]:
    """Coletas de um CSV da série histórica, na ordem do arquivo, contando o que foi descartado e por quê."""
    resumo = resumo if resumo is not None else ResumoLeitura()
    texto = _texto(conteudo)
    primeira = texto.split("\n", 1)[0]
    separador = ";" if primeira.count(";") >= primeira.count(",") else ","
    yield from _ler_linhas(csv.reader(io.StringIO(texto), delimiter=separador), resumo)


def ler_xlsx(conteudo: bytes, resumo: ResumoLeitura | None = None) -> Iterator[Coleta]:
    """Coletas da planilha semanal do levantamento (primeira aba), contando o que foi descartado e por quê."""
    resumo = resumo if resumo is not None else ResumoLeitura()
    yield from _ler_linhas(xlsx.linhas(conteudo), resumo)


def ler_bytes(conteudo: bytes, resumo: ResumoLeitura | None = None) -> Iterator[Coleta]:
    """Coletas do conteúdo de um arquivo da ANP: planilha .xlsx, CSV direto ou ZIP com um ou mais CSV."""
    if xlsx.eh_xlsx(conteudo):
        yield from ler_xlsx(conteudo, resumo)
    elif conteudo[:4] == b"PK\x03\x04":
        with zipfile.ZipFile(io.BytesIO(conteudo)) as z:
            for nome in sorted(n for n in z.namelist() if n.lower().endswith(".csv")):
                yield from ler_csv(z.read(nome), resumo)
    else:
        yield from ler_csv(conteudo, resumo)


def ler_arquivo(caminho: Path | str, resumo: ResumoLeitura | None = None) -> Iterator[Coleta]:
    """Coletas de um arquivo da ANP no disco (``.csv``, ``.zip`` ou ``.xlsx``)."""
    yield from ler_bytes(Path(caminho).read_bytes(), resumo)


class PrecosAnp:
    """Índice em memória das coletas, por produto, UF e município, para montar referências por período.

    Os valores ficam em milésimos de real (inteiros, arredondados) e as datas em ordinal, o que cabe um
    semestre inteiro (centenas de milhares de coletas) na memória de uma máquina comum. A mesma coleta (posto,
    produto e data) vinda de dois arquivos entra uma vez só e é contada em ``repetidas``.
    """

    def __init__(self, coletas: Iterable[Coleta] = ()):
        """Índice vazio, ou com as coletas dadas."""
        self._municipio: dict[tuple[str, str, str], list[tuple[int, int, str]]] = {}
        self._uf: dict[tuple[str, str], list[tuple[int, int, str]]] = {}
        self._vistas: set[int] = set()
        self.total = 0
        self.repetidas = 0
        for c in coletas:
            self.adicionar(c)

    def adicionar(self, c: Coleta) -> bool:
        """Inclui uma coleta nos índices do município e da UF; False se ela já estava (mesmo posto e data)."""
        if c.cnpj:
            marca = hash((c.produto, c.uf, c.cnpj, c.data.toordinal()))
            if marca in self._vistas:
                self.repetidas += 1
                return False
            self._vistas.add(marca)
        milesimos = int((c.valor * 1000).to_integral_value(rounding=ROUND_HALF_EVEN))
        registro = (c.data.toordinal(), milesimos, c.cnpj or "")
        self._municipio.setdefault((c.produto, c.uf, c.municipio), []).append(registro)
        self._uf.setdefault((c.produto, c.uf), []).append(registro)
        self.total += 1
        return True

    def produtos(self) -> dict[str, int]:
        """Quantidade de coletas por produto."""
        contagem: dict[str, int] = {}
        for (produto, _), lista in self._uf.items():
            contagem[produto] = contagem.get(produto, 0) + len(lista)
        return dict(sorted(contagem.items()))

    def municipios(self) -> set[tuple[str, str]]:
        """Pares (UF, município) com alguma coleta, em qualquer produto."""
        return {(uf, m) for (_, uf, m) in self._municipio}

    def periodo(self) -> tuple[date, date] | None:
        """Primeira e última data de coleta no índice; None se vazio."""
        datas = [d for lista in self._uf.values() for d, _, _ in lista]
        return (date.fromordinal(min(datas)), date.fromordinal(max(datas))) if datas else None

    def referencia(self, produto: str, uf: str, municipio: str | None, quando: date, *, janela_dias: int = 7,
                   minimo_municipio: int = 5, minimo_uf: int = 10) -> ReferenciaMercado | None:
        """Distribuição do preço de bomba do produto em torno da data, no município ou, sem amostra, na UF.

        Usa as coletas entre ``quando - janela_dias`` e ``quando + janela_dias``. O município só vale com ao
        menos ``minimo_municipio`` coletas; senão, a UF inteira, com ao menos ``minimo_uf``. Sem isso, None:
        a comparação fica sem referência, e o relatório diz por quê.
        """
        uf = (uf or "").upper()
        inicio, fim = (quando - timedelta(days=janela_dias)).toordinal(), (quando + timedelta(days=janela_dias)).toordinal()
        candidatos: list[tuple[str, str, list[tuple[int, int, str]], int]] = []
        if municipio:
            chave = chave_municipio(municipio)
            candidatos.append(("municipio", f"{chave}/{uf}", self._municipio.get((produto, uf, chave), []),
                               minimo_municipio))
        candidatos.append(("uf", uf, self._uf.get((produto, uf), []), minimo_uf))
        for escopo, local, lista, minimo in candidatos:
            dentro = [r for r in lista if inicio <= r[0] <= fim]
            if len(dentro) < minimo:
                continue
            datas = [r[0] for r in dentro]
            evidencias = tuple(Evidencia(descricao=f"posto {cnpj or 'sem CNPJ'}", valor=Decimal(v) / 1000,
                                         data=date.fromordinal(d).isoformat())
                               for d, v, cnpj in sorted(dentro)[:50])
            return ReferenciaMercado.de_valores(
                (Decimal(v) / 1000 for _, v, _ in dentro), fonte="anp", produto=produto, escopo=escopo,
                local=local, periodo=(date.fromordinal(min(datas)), date.fromordinal(max(datas))),
                unidade=unidade_do_produto(produto), evidencias=evidencias)
        return None
