"""Dados abertos do TSE: resultados de todas as eleições desde 1994.

O sistema de divulgação de resultados só mantém as eleições recentes (ver
``tse.py``). As anteriores vêm do Portal de Dados Abertos
(``dadosabertos.tse.jus.br``, CKAN), que aponta para arquivos ZIP na CDN do
tribunal. Um pacote por ano (``resultados-AAAA``), com, entre outros:

``votacao_candidato_munzona_AAAA.zip``
    votos de cada candidato em cada zona de cada município. Um CSV por UF
    (cargos estaduais e municipais), um ``_BR.csv`` com o cargo de
    Presidente em todos os municípios e no exterior, e um ``_BRASIL.csv``
    que é a concatenação de todos — este é ignorado, para não contar duas
    vezes.
``detalhe_votacao_munzona_AAAA.zip``
    por zona: aptos, comparecimento, abstenção, brancos, nulos, válidos e
    votos de legenda. Mesma divisão em arquivos.
``Historico_Totalizacao_Presidente_BR_<T>T_AAAA.zip``
    (2018 em diante) a evolução da totalização do Presidente, minuto a
    minuto, que alimenta o gráfico de evolução.

Formato observado em 05/10/2026, de 1994 a 2024 (ver ``testes/fixtures/tse``):
CSV com cabeçalho, separador ``;``, aspas duplas, codificação Latin-1.
Valores ausentes como ``#NULO#``, ``#NULO``, ``#NE`` ou códigos ``-1``/``-3``.
O número de colunas varia por ano (38, 44 ou 50), e por isso a leitura é
sempre pelo nome da coluna, nunca pela posição.

Diferenças entre anos que mudam o resultado e são tratadas aqui:

- ``QT_VOTOS_NOMINAIS_VALIDOS`` e ``NM_TIPO_DESTINACAO_VOTOS`` não existem
  nos arquivos de 2002 a 2014. Nesses anos a fonte não distingue voto válido
  de voto anulado por candidatura indeferida; o feed registra o aviso.
- Em 2000, ``QT_VOTOS_NOMINAIS`` vem zerado e o voto está em
  ``QT_VOTOS_NOMINAIS_VALIDOS``: a votação do candidato é o maior dos dois.
- Em 1994, os totais do detalhe vêm parcialmente zerados
  (``QT_TOTAL_VOTOS_VALIDOS`` = 0 com ``QT_VOTOS_NOMINAIS_VALIDOS`` > 0). Os
  totais são reconciliados pelas parcelas (``_reconciliar``).
"""

from __future__ import annotations

import csv
import io
import json
import zipfile
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterable, Iterator

from lumen_normalizacao.transformacoes import chave_texto

from .modelo import (
    CARGOS,
    Agremiacao,
    Candidato,
    Comparecimento,
    Nivel,
    ResultadoAbrangencia,
    Totalizacao,
    Votos,
)

CKAN = "https://dadosabertos.tse.jus.br/api/3/action/package_show"
CDN = "https://cdn.tse.jus.br/estatistica/sead/odsele"
CDN_ELEICOES = "https://cdn.tse.jus.br/estatistica/sead/eleicoes"

ANOS_GERAIS = tuple(range(1994, 2027, 4))
ANOS_MUNICIPAIS = tuple(range(1996, 2025, 4))
# Ano mais recente dos dados abertos: o TSE ainda acrescenta o 2º turno e corrige os arquivos. O ``preparar``
# o confere na fonte a cada execução, e só a eleição (ano e turno) já processada sai da coleta ao vivo.
ANO_EM_ABERTO = max(ANOS_GERAIS + ANOS_MUNICIPAIS)

CONJUNTO_VOTACAO = "votacao_candidato_munzona"
CONJUNTO_DETALHE = "detalhe_votacao_munzona"

BRT = timezone(timedelta(hours=-3), "BRT")
ORDINARIA = "2"
NULOS = frozenset({"", "#NULO#", "#NULO", "#NE", "#NE#", "-1", "-3", "-4"})

AVISO_SEM_DESTINACAO = (
    "A fonte não informa a destinação dos votos nesta eleição: votos dados a "
    "candidaturas indeferidas podem aparecer somados aos válidos."
)
AVISO_TOTAIS_RECONCILIADOS = (
    "Totais do detalhe da apuração incompletos na fonte; reconciliados pelas parcelas."
)
AVISO_SEM_DETALHE = (
    "Sem detalhe da apuração para este recorte na fonte; votos válidos calculados "
    "pela soma dos candidatos."
)


def aviso_validos_da_epoca(ano: int) -> str | None:
    """Aviso sobre o que contava como voto válido no ano, ou None a partir de 1998.

    Pelo Leia-me do TSE, votos nulos foram considerados válidos até o Código Eleitoral de 1965 (Lei
    4.737/65) e votos em branco até a Lei 9.504/97. O Lumen calcula os percentuais sempre do mesmo
    jeito — sobre os votos dados a candidatos e legendas —, e por isso eles podem diferir dos da época.
    """
    if ano >= 1998:
        return None
    if ano <= 1962:
        regra = "votos em branco e nulos também contavam como válidos"
    else:
        regra = "votos em branco também contavam como válidos"
    return ("Percentuais calculados sobre os votos dados a candidatos e legendas. Pelas regras da época, "
            f"{regra}, e os percentuais oficiais do resultado podem ser menores.")


class FormatoNaoReconhecido(ValueError):
    """O arquivo não tem as colunas mínimas esperadas."""


# ---------------------------------------------------------------- endereços

def url_pacote(ano: int) -> str:
    """URL do ``package_show`` do CKAN para o pacote ``resultados-<ano>``."""
    return f"{CKAN}?id=resultados-{ano}"


def url_conjunto(conjunto: str, ano: int) -> str:
    """Endereço conhecido do ZIP de um conjunto na CDN do TSE, usado quando o CKAN não informa outro."""
    return f"{CDN}/{conjunto}/{conjunto}_{ano}.zip"


def url_historico_presidente(ano: int, turno: int) -> str:
    """Endereço do ZIP com a evolução da totalização do Presidente num turno (2018 em diante)."""
    return f"{CDN_ELEICOES}/eleicoes{ano}/Historico_Totalizacao_Presidente_BR_{turno}T_{ano}.zip"


def tipo_do_ano(ano: int) -> str:
    """Eleições ordinárias: gerais nos anos pares não múltiplos de 4."""
    return "geral" if ano % 4 == 2 else "municipal"


@dataclass(frozen=True)
class Recurso:
    """Um arquivo listado num pacote do CKAN: nome, URL e formato declarado."""

    nome: str
    url: str
    formato: str | None


def ler_pacote(conteudo: bytes | str | dict) -> list[Recurso]:
    """Resposta de ``package_show`` do CKAN → recursos do pacote."""
    dados = json.loads(conteudo) if isinstance(conteudo, (bytes, str)) else conteudo
    if not dados.get("success", True):
        raise ValueError(f"CKAN recusou a consulta: {dados.get('error')}")
    resultado = dados.get("result") or {}
    return [Recurso(nome=(r.get("name") or "").strip(), url=r.get("url") or "", formato=r.get("format"))
            for r in resultado.get("resources", []) if r.get("url")]


def classificar_recursos(recursos: Iterable[Recurso]) -> dict[str, list[Recurso]]:
    """Agrupa pelo conjunto, reconhecido pela URL (o nome do recurso varia)."""
    grupos: dict[str, list[Recurso]] = defaultdict(list)
    for r in recursos:
        arquivo = r.url.rsplit("/", 1)[-1].lower()
        if arquivo.startswith(CONJUNTO_VOTACAO + "_"):
            grupos[CONJUNTO_VOTACAO].append(r)
        elif arquivo.startswith(CONJUNTO_DETALHE + "_"):
            grupos[CONJUNTO_DETALHE].append(r)
        elif arquivo.startswith("historico_totalizacao"):
            grupos["historico_totalizacao"].append(r)
        else:
            grupos["outros"].append(r)
    return dict(grupos)


# ---------------------------------------------------------------- leitura

def entradas_csv(nomes: Iterable[str]) -> list[str]:
    """CSVs a ler de um ZIP: os por UF e o ``_BR``; o ``_BRASIL`` só se for o único.

    O ``_BR`` vem primeiro: as linhas de Presidente são lidas dele, e os
    arquivos por UF as pulam (ver ``ler_linhas``).
    """
    csvs = [n for n in nomes if n.lower().endswith(".csv")]
    partes = [n for n in csvs if not n.upper().endswith("_BRASIL.CSV")]
    escolhidos = partes or csvs
    return sorted(escolhidos, key=lambda n: (not n.upper().endswith("_BR.CSV"), n))


def tem_arquivo_br(nomes: Iterable[str]) -> bool:
    """O ZIP tem o ``_BR.csv``? Se tiver, o Presidente vem dele e é pulado nos arquivos por UF."""
    return any(n.upper().endswith("_BR.CSV") for n in nomes)


def _texto(valor: str | None) -> str | None:
    """Valor da célula sem espaços nas pontas; os marcadores de ausência do TSE (``NULOS``) viram ``None``."""
    if valor is None:
        return None
    v = valor.strip()
    return None if v in NULOS else v


def _int(valor: str | None) -> int:
    """Valor da célula como inteiro não negativo: vazio, ``#...``, texto e códigos negativos viram 0."""
    if valor is None:
        return 0
    v = valor.strip()
    if not v or v.startswith("#"):
        return 0
    try:
        n = int(v)
    except ValueError:
        return 0
    return n if n > 0 else 0


class Linhas:
    """Iterador sobre um CSV do TSE dentro do ZIP, com acesso por nome de coluna."""

    def __init__(self, fluxo: io.BufferedIOBase | io.RawIOBase, obrigatorias: Iterable[str] = ()):
        """Lê o cabeçalho (Latin-1, separador ``;``) e confere as colunas obrigatórias.

        Os nomes de coluna perdem espaços e um eventual BOM no início. Levanta ``FormatoNaoReconhecido``
        se o arquivo estiver vazio ou faltar coluna obrigatória.
        """
        texto = io.TextIOWrapper(fluxo, encoding="latin-1", newline="")
        self._leitor = csv.reader(texto, delimiter=";", quotechar='"')
        try:
            cabecalho = next(self._leitor)
        except StopIteration as erro:
            raise FormatoNaoReconhecido("arquivo vazio") from erro
        self.colunas = {nome.strip().lstrip("﻿"): i for i, nome in enumerate(cabecalho)}
        faltando = [c for c in obrigatorias if c not in self.colunas]
        if faltando:
            raise FormatoNaoReconhecido(f"colunas ausentes: {', '.join(faltando)}")

    def tem(self, coluna: str) -> bool:
        """A coluna existe neste arquivo? O conjunto de colunas varia por ano."""
        return coluna in self.colunas

    def indice(self, coluna: str) -> int | None:
        """Posição da coluna no arquivo, ou ``None`` se ela não existe."""
        return self.colunas.get(coluna)

    def __iter__(self) -> Iterator[list[str]]:
        """Linhas de dados como listas de texto, pulando as vazias."""
        for linha in self._leitor:
            if linha:
                yield linha


# ---------------------------------------------------------------- chaves

def id_eleicao(ano: int, turno: int, tp_abrangencia: str | None) -> str:
    """Id da eleição no feed, ``<ano>-<turno>t-<tipo>``; ``TP_ABRANGENCIA`` = ``M`` é municipal, o resto geral."""
    tipo = "municipal" if (tp_abrangencia or "").upper() == "M" else "geral"
    return f"{ano}-{turno}t-{tipo}"


# Chave de abrangência: ("br",), ("uf", "sp"), ("mu", "sp", "71072") e, dentro do município,
# ("zn", "sp", "71072", "1") — a zona eleitoral, que só aparece como parte do feed do município.
Abr = tuple[str, ...]


def abrangencias_da_linha(cargo: int, uf: str, municipio: str, zona: str | None = None) -> list[Abr]:
    """Abrangências em que uma linha de zona é somada: é assim que as zonas viram município, UF e Brasil.

    Sempre o município; também a UF, se o cargo é estadual ou nacional; e o Brasil, se é nacional. Com
    ``zona``, também a própria zona dentro do município (``("zn", uf, município, zona)``).
    """
    nivel = CARGOS[cargo][2]
    saida: list[Abr] = [("mu", uf, municipio)]
    if nivel in (Nivel.UF, Nivel.BRASIL):
        saida.append(("uf", uf))
    if nivel is Nivel.BRASIL:
        saida.append(("br",))
    if zona:
        saida.append(("zn", uf, municipio, zona))
    return saida


def zona_da_linha(valor: str | None) -> str | None:
    """Número da zona como texto sem zeros à esquerda (``"0001"`` → ``"1"``); None se ausente ou zero."""
    numero = _int(valor)
    return str(numero) if numero > 0 else None


def municipios_com_zonas(totais: dict[tuple[str, int, Abr], "Totais"]) -> set[tuple[str, str]]:
    """Municípios, como ``(uf, código TSE)``, que o detalhe da apuração divide em duas zonas ou mais.

    São os únicos em que o resultado por zona diz algo além do resultado do município: nos outros, a
    única zona do município tem os mesmos números que ele.
    """
    zonas: dict[tuple[str, str], set[str]] = defaultdict(set)
    for _eid, _cargo, abr in totais:
        if abr[0] == "zn":
            zonas[(abr[1], abr[2])].add(abr[3])
    return {m for m, z in zonas.items() if len(z) > 1}


# ---------------------------------------------------------------- detalhe

@dataclass
class Totais:
    """Totais do detalhe da apuração de um recorte, somados zona a zona.

    ``ultima_totalizacao`` fica com o instante mais recente entre as zonas; ``reconciliado`` marca que
    ``reconciliar`` precisou recompor algum total, o que vira aviso no feed.
    """

    aptos: int = 0
    comparecimento: int = 0
    abstencoes: int = 0
    secoes: int = 0
    votos: int = 0
    validos: int = 0
    nominais_validos: int = 0
    legenda_validos: int = 0
    brancos: int = 0
    nulos: int = 0
    nulos_simples: int = 0
    nulos_tecnicos: int = 0
    anulados: int = 0
    anulados_subjudice: int = 0
    ultima_totalizacao: datetime | None = None
    reconciliado: bool = False

    def somar(self, outro: "Totais") -> None:
        """Soma as contagens de ``outro`` a estas e fica com a mais recente das duas últimas totalizações."""
        for nome in ("aptos", "comparecimento", "abstencoes", "secoes", "votos", "validos",
                     "nominais_validos", "legenda_validos", "brancos", "nulos", "nulos_simples",
                     "nulos_tecnicos", "anulados", "anulados_subjudice"):
            setattr(self, nome, getattr(self, nome) + getattr(outro, nome))
        if outro.ultima_totalizacao and (self.ultima_totalizacao is None
                                         or outro.ultima_totalizacao > self.ultima_totalizacao):
            self.ultima_totalizacao = outro.ultima_totalizacao

    def reconciliar(self) -> None:
        """Totais zerados com parcelas positivas (1994): recompõe pelas parcelas."""
        parcelas_validos = self.nominais_validos + self.legenda_validos
        if parcelas_validos > self.validos:
            self.validos = parcelas_validos
            self.reconciliado = True
        parcelas_nulos = self.nulos_simples + self.nulos_tecnicos
        if parcelas_nulos > self.nulos:
            self.nulos = parcelas_nulos
            self.reconciliado = True
        soma = self.validos + self.brancos + self.nulos + self.anulados + self.anulados_subjudice
        if soma > self.votos:
            self.votos = soma
            self.reconciliado = True
        if self.comparecimento == 0 and self.votos:
            self.comparecimento = self.votos
            self.reconciliado = True


COLUNAS_DETALHE = ("ANO_ELEICAO", "NR_TURNO", "CD_TIPO_ELEICAO", "TP_ABRANGENCIA", "SG_UF",
                   "SG_UE", "CD_MUNICIPIO", "CD_CARGO", "QT_APTOS", "QT_COMPARECIMENTO")


def _instante_br(data: str | None, hora: str | None) -> datetime | None:
    """Data (``dd/mm/aaaa``) e hora do TSE → ``datetime`` no horário de Brasília; sem hora, meia-noite.

    Devolve ``None`` se a data faltar ou não estiver nesse formato.
    """
    data = _texto(data)
    if not data:
        return None
    try:
        return datetime.strptime(f"{data} {(_texto(hora) or '00:00:00')}", "%d/%m/%Y %H:%M:%S").replace(tzinfo=BRT)
    except ValueError:
        return None


def ler_detalhe(fluxos: Iterable[tuple[str, io.BufferedIOBase]], *, pular_presidente_nos_estados: bool,
                ) -> dict[tuple[str, int, Abr], Totais]:
    """Totais por eleição, cargo e abrangência, somados das zonas.

    Cada zona também fica com os próprios totais (abrangência ``("zn", uf, município, zona)``), que dão o
    eleitorado e o comparecimento das zonas no feed do município. ``fluxos`` é uma sequência de (nome do arquivo, fluxo binário), na ordem
    de ``entradas_csv``. Com ``pular_presidente_nos_estados``, as linhas de
    Presidente (``SG_UE`` = BR) dos arquivos por UF são puladas: vêm do
    ``_BR``.
    """
    totais: dict[tuple[str, int, Abr], Totais] = defaultdict(Totais)
    for nome, fluxo in fluxos:
        do_br = nome.upper().endswith("_BR.CSV")
        linhas = Linhas(fluxo, COLUNAS_DETALHE)
        ix = linhas.colunas
        g = {c: ix.get(c) for c in (
            "QT_ABSTENCOES", "QT_TOTAL_SECOES", "QT_VOTOS", "QT_TOTAL_VOTOS_VALIDOS",
            "QT_VOTOS_NOMINAIS_VALIDOS", "QT_TOTAL_VOTOS_LEG_VALIDOS", "QT_VOTOS_LEG_VALIDOS",
            "QT_VOTOS_BRANCOS", "QT_TOTAL_VOTOS_NULOS", "QT_VOTOS_NULOS", "QT_VOTOS_NULOS_TECNICOS",
            "QT_TOTAL_VOTOS_ANULADOS", "QT_TOTAL_VOTOS_ANUL_SUBJUD", "DT_ULTIMA_TOTALIZACAO",
            "HH_ULTIMA_TOTALIZACAO", "NR_ZONA")}

        def col(linha: list[str], nome: str, _g: dict[str, int | None] = g) -> str | None:
            i = _g.get(nome)
            return linha[i] if i is not None and i < len(linha) else None

        for linha in linhas:
            if linha[ix["CD_TIPO_ELEICAO"]].strip() != ORDINARIA:
                continue
            cargo = _int(linha[ix["CD_CARGO"]])
            if cargo not in CARGOS:
                continue
            if cargo == 1 and pular_presidente_nos_estados and not do_br:
                continue
            ano = _int(linha[ix["ANO_ELEICAO"]])
            turno = _int(linha[ix["NR_TURNO"]]) or 1
            eid = id_eleicao(ano, turno, linha[ix["TP_ABRANGENCIA"]])
            uf = linha[ix["SG_UF"]].strip().lower()
            municipio = str(_int(linha[ix["CD_MUNICIPIO"]])).zfill(5)
            legenda = max(_int(col(linha, "QT_TOTAL_VOTOS_LEG_VALIDOS")), _int(col(linha, "QT_VOTOS_LEG_VALIDOS")))
            t = Totais(
                aptos=_int(linha[ix["QT_APTOS"]]), comparecimento=_int(linha[ix["QT_COMPARECIMENTO"]]),
                abstencoes=_int(col(linha, "QT_ABSTENCOES")), secoes=_int(col(linha, "QT_TOTAL_SECOES")),
                votos=_int(col(linha, "QT_VOTOS")), validos=_int(col(linha, "QT_TOTAL_VOTOS_VALIDOS")),
                nominais_validos=_int(col(linha, "QT_VOTOS_NOMINAIS_VALIDOS")), legenda_validos=legenda,
                brancos=_int(col(linha, "QT_VOTOS_BRANCOS")), nulos=_int(col(linha, "QT_TOTAL_VOTOS_NULOS")),
                nulos_simples=_int(col(linha, "QT_VOTOS_NULOS")),
                nulos_tecnicos=_int(col(linha, "QT_VOTOS_NULOS_TECNICOS")),
                anulados=_int(col(linha, "QT_TOTAL_VOTOS_ANULADOS")),
                anulados_subjudice=_int(col(linha, "QT_TOTAL_VOTOS_ANUL_SUBJUD")),
                ultima_totalizacao=_instante_br(col(linha, "DT_ULTIMA_TOTALIZACAO"),
                                                col(linha, "HH_ULTIMA_TOTALIZACAO")),
            )
            for abr in abrangencias_da_linha(cargo, uf, municipio, zona_da_linha(col(linha, "NR_ZONA"))):
                totais[(eid, cargo, abr)].somar(t)
    for t in totais.values():
        t.reconciliar()
    return dict(totais)


# ---------------------------------------------------------------- votação

COLUNAS_VOTACAO = ("ANO_ELEICAO", "NR_TURNO", "CD_TIPO_ELEICAO", "TP_ABRANGENCIA", "SG_UF",
                   "CD_MUNICIPIO", "NM_MUNICIPIO", "CD_CARGO", "SQ_CANDIDATO", "NR_CANDIDATO",
                   "NM_URNA_CANDIDATO", "QT_VOTOS_NOMINAIS")

SITUACOES = {
    "ELEITO": "Eleito",
    "ELEITO POR QP": "Eleito por QP",
    "ELEITO POR MEDIA": "Eleito por média",
    "ELEITO POR MÉDIA": "Eleito por média",
    "MEDIA": "Eleito por média",
    "MÉDIA": "Eleito por média",
    "NAO ELEITO": "Não eleito",
    "NÃO ELEITO": "Não eleito",
    "SUPLENTE": "Suplente",
    "2º TURNO": "2º turno",
    "2O TURNO": "2º turno",
    "2° TURNO": "2º turno",
    # 1933 e 1934: etapas de apuração do Código Eleitoral de 1932 (QE e QP: quocientes eleitoral e partidário)
    "ELEITO 1º TURNO QE": "Eleito no 1º turno por QE",
    "ELEITO 1º TURNO QP": "Eleito no 1º turno por QP",
    "ELEITO 2º TURNO": "Eleito no 2º turno",
}


def situacao_publicada(texto: str | None) -> str:
    """Situação do candidato no turno (``DS_SIT_TOT_TURNO``) como o feed a mostra.

    Unifica as grafias que mudam entre anos (``MEDIA``/``MÉDIA``, ``2O TURNO``/``2º TURNO``); situação
    fora de ``SITUACOES`` sai só com a inicial maiúscula, e a ausente sai vazia.
    """
    t = (_texto(texto) or "").upper()
    return SITUACOES.get(t, t.capitalize() if t else "")


@dataclass
class _Meta:
    """Metadados de um candidato, guardados uma vez por (eleição, cargo, ``SQ_CANDIDATO``), e não por linha."""

    numero: str
    nome: str
    nome_urna: str
    partido: str | None
    agremiacao: str | None
    composicao: str | None
    federacao: str | None
    situacao: str
    destinacao: str | None


@dataclass
class AgregadorVotacao:
    """Soma os votos por candidato em cada abrangência, a partir das zonas.

    Mantém só inteiros por (eleição, cargo, abrangência, candidato) e os
    metadados do candidato uma vez; é o que permite ler o arquivo de São
    Paulo de 2018 (1,2 GB) sem carregar o arquivo na memória.
    """

    pular_presidente: bool = False
    # Municípios (uf, código TSE) com duas zonas ou mais (``municipios_com_zonas``): só neles a votação
    # também é somada por zona. Nos demais a zona repetiria o município e só ocuparia memória.
    zonas_de: set[tuple[str, str]] = field(default_factory=set)
    votos: dict[tuple[str, int, Abr], dict[str, list[int]]] = field(default_factory=lambda: defaultdict(dict))
    meta: dict[tuple[str, int, str], _Meta] = field(default_factory=dict)
    nomes_municipios: dict[tuple[str, str], str] = field(default_factory=dict)
    sem_destinacao: set[str] = field(default_factory=set)
    datas: dict[str, date] = field(default_factory=dict)
    codigos_tse: dict[tuple[str, int], int] = field(default_factory=dict)
    linhas_lidas: int = 0
    linhas_ignoradas: int = 0

    def ler(self, fluxo: io.BufferedIOBase) -> None:
        """Lê um CSV de votação e soma os votos de cada candidato em todas as abrangências da linha.

        Pula eleição não ordinária, cargo fora de ``CARGOS`` e, com ``pular_presidente``, o Presidente.
        Por candidato acumula [votos, válidos]: o voto é o maior entre nominais e válidos (2000 traz os
        nominais zerados); sem a coluna de válidos, a eleição entra em ``sem_destinacao``. Nos municípios de
        ``zonas_de``, soma também na zona da linha. Colhe também a data e o código TSE de cada eleição e o
        nome de cada município.
        """
        linhas = Linhas(fluxo, COLUNAS_VOTACAO)
        ix = linhas.colunas
        i_validos = ix.get("QT_VOTOS_NOMINAIS_VALIDOS")
        i_dest = ix.get("NM_TIPO_DESTINACAO_VOTOS")
        opc = {c: ix.get(c) for c in ("NM_CANDIDATO", "SG_PARTIDO", "NM_COLIGACAO", "DS_COMPOSICAO_COLIGACAO",
                                      "SG_FEDERACAO", "DS_SIT_TOT_TURNO", "TP_AGREMIACAO", "DT_ELEICAO",
                                      "CD_ELEICAO", "NR_ZONA")}

        def col(linha: list[str], nome: str) -> str | None:
            i = opc.get(nome)
            return linha[i] if i is not None and i < len(linha) else None

        for linha in linhas:
            self.linhas_lidas += 1
            if linha[ix["CD_TIPO_ELEICAO"]].strip() != ORDINARIA:
                self.linhas_ignoradas += 1
                continue
            cargo = _int(linha[ix["CD_CARGO"]])
            if cargo not in CARGOS or (cargo == 1 and self.pular_presidente):
                self.linhas_ignoradas += 1
                continue
            ano = _int(linha[ix["ANO_ELEICAO"]])
            turno = _int(linha[ix["NR_TURNO"]]) or 1
            eid = id_eleicao(ano, turno, linha[ix["TP_ABRANGENCIA"]])
            uf = linha[ix["SG_UF"]].strip().lower()
            municipio = str(_int(linha[ix["CD_MUNICIPIO"]])).zfill(5)
            sq = linha[ix["SQ_CANDIDATO"]].strip()
            nominais = _int(linha[ix["QT_VOTOS_NOMINAIS"]])
            if i_validos is not None:
                validos = _int(linha[i_validos])
                total = max(nominais, validos)
            else:
                validos = total = nominais
                self.sem_destinacao.add(eid)
            if eid not in self.datas:
                quando = _instante_br(col(linha, "DT_ELEICAO"), None)
                if quando:
                    self.datas[eid] = quando.date()
            if (eid, cargo) not in self.codigos_tse:
                self.codigos_tse[(eid, cargo)] = _int(col(linha, "CD_ELEICAO"))
            chave_meta = (eid, cargo, sq)
            if chave_meta not in self.meta:
                coligacao = _texto(col(linha, "NM_COLIGACAO"))
                partido = _texto(col(linha, "SG_PARTIDO"))
                isolado = coligacao is None or coligacao.upper() == "PARTIDO ISOLADO"
                self.meta[chave_meta] = _Meta(
                    numero=linha[ix["NR_CANDIDATO"]].strip(),
                    nome=(_texto(col(linha, "NM_CANDIDATO")) or "").strip(),
                    nome_urna=(_texto(linha[ix["NM_URNA_CANDIDATO"]]) or "").strip(),
                    partido=partido,
                    agremiacao=partido if isolado else coligacao,
                    composicao=_texto(col(linha, "DS_COMPOSICAO_COLIGACAO")) or partido,
                    federacao=_texto(col(linha, "SG_FEDERACAO")),
                    situacao=situacao_publicada(col(linha, "DS_SIT_TOT_TURNO")),
                    destinacao=_texto(linha[i_dest]) if i_dest is not None and i_dest < len(linha) else None,
                )
            self.nomes_municipios.setdefault((uf, municipio), (linha[ix["NM_MUNICIPIO"]] or "").strip())
            zona = zona_da_linha(col(linha, "NR_ZONA")) if (uf, municipio) in self.zonas_de else None
            for abr in abrangencias_da_linha(cargo, uf, municipio, zona):
                atual = self.votos[(eid, cargo, abr)].get(sq)
                if atual is None:
                    self.votos[(eid, cargo, abr)][sq] = [total, validos]
                else:
                    atual[0] += total
                    atual[1] += validos

    # ------------------------------------------------------------ resultados

    def chaves(self) -> list[tuple[str, int, Abr]]:
        """Chaves (eleição, cargo, abrangência) em ordem estável: dentro de eleição e cargo, Brasil, UFs,
        municípios e zonas.
        """
        return sorted(self.votos, key=lambda k: (k[0], k[1], len(k[2]), k[2]))

    def resultado(self, chave: tuple[str, int, Abr], totais: Totais | None) -> ResultadoAbrangencia:
        """Monta o ``ResultadoAbrangencia`` de uma chave, com os totais do detalhe quando os há.

        Sem detalhe, os válidos saem da soma dos candidatos, com aviso. Percentuais sobre os válidos;
        candidatos em ordem de votação, com os de voto não válido no fim; vagas = número de eleitos. A
        totalização vem como finalizada (dado definitivo), e as agremiações só nos cargos proporcionais.
        """
        eid, cargo, abr = chave
        candidatos: list[Candidato] = []
        soma_validos = 0
        for sq, (total, validos) in self.votos[chave].items():
            m = self.meta[(eid, cargo, sq)]
            soma_validos += validos
            candidatos.append(Candidato(
                numero=m.numero, sq=sq, nome=m.nome, nome_urna=m.nome_urna, partido=m.partido,
                agremiacao=m.agremiacao, composicao=m.composicao, votos=total, pct_validos=None, situacao=m.situacao, eleito=m.situacao.lower().startswith("eleito"),
                segundo_turno=m.situacao == "2º turno", destinacao=m.destinacao, sigla_federacao=m.federacao,
            ))
        avisos: list[str] = []
        if eid in self.sem_destinacao:
            avisos.append(AVISO_SEM_DESTINACAO)
        if totais is None:
            totais = Totais(validos=soma_validos, nominais_validos=soma_validos, votos=soma_validos)
            avisos.append(AVISO_SEM_DETALHE)
        elif totais.reconciliado:
            avisos.append(AVISO_TOTAIS_RECONCILIADOS)
        regra = aviso_validos_da_epoca(int(eid[:4]))
        if regra:
            avisos.append(regra)
        base = totais.validos or soma_validos
        for c in candidatos:
            c.pct_validos = round(100.0 * c.votos / base, 6) if base and c.valido else None
        candidatos.sort(key=lambda c: (not c.valido, -c.votos, c.numero))
        votos_total = totais.votos or (totais.validos + totais.brancos + totais.nulos + totais.anulados)

        def pct(parte: int, todo: int) -> float | None:
            return round(100.0 * parte / todo, 6) if todo else None

        eleitos = sum(1 for c in candidatos if c.eleito)
        tipo_abr, codigo = (abr[0], abr[-1] if abr[0] != "br" else "br")
        return ResultadoAbrangencia(
            eleicao_tse=self.codigos_tse.get((eid, cargo)) or None, cargo=cargo, vagas=eleitos or None,
            abrangencia_tipo=tipo_abr, abrangencia_codigo=codigo,
            atualizado_em=totais.ultima_totalizacao,
            totalizacao=Totalizacao(secoes=totais.secoes or None, secoes_totalizadas=totais.secoes or None,
                                    pct_secoes=100.0, finalizada=True, andamento="f"),
            comparecimento=Comparecimento(
                eleitorado=totais.aptos or None, comparecimento=totais.comparecimento or None,
                abstencao=totais.abstencoes or None,
                pct_comparecimento=pct(totais.comparecimento, totais.aptos),
                pct_abstencao=pct(totais.abstencoes, totais.aptos)),
            votos=Votos(validos=totais.validos or soma_validos, brancos=totais.brancos, nulos=totais.nulos,
                        anulados=totais.anulados + totais.anulados_subjudice, legenda=totais.legenda_validos,
                        pct_validos=pct(totais.validos, votos_total), pct_brancos=pct(totais.brancos, votos_total),
                        pct_nulos=pct(totais.nulos, votos_total)),
            candidatos=candidatos,
            agremiacoes=_agremiacoes(candidatos, totais.legenda_validos) if CARGOS[cargo][0].startswith(
                ("deputado", "vereador")) else [],
            avisos=avisos,
        )

    def limpar(self) -> None:
        """Libera votos e metadados depois de emitidos, para não segurar na memória o arquivo já lido."""
        self.votos.clear()
        self.meta.clear()


def _agremiacoes(candidatos: list[Candidato], legenda: int) -> list[Agremiacao]:
    """Votação nominal por partido (a de legenda por partido não está neste arquivo)."""
    por: dict[str, Agremiacao] = {}
    for c in candidatos:
        if not c.valido or not c.partido:
            continue
        a = por.get(c.partido)
        if a is None:
            a = por[c.partido] = Agremiacao(nome=c.partido, tipo="partido", composicao=c.composicao,
                                            votos=0, vagas=0)
        a.votos += c.votos
        if c.eleito:
            a.vagas = (a.vagas or 0) + 1
    return sorted(por.values(), key=lambda a: (-(a.vagas or 0), -a.votos, a.nome))


# ---------------------------------------------------------------- histórico

@dataclass(frozen=True)
class PontoHistorico:
    """Um ponto da evolução da totalização: instante, percentual de seções e votos acumulados por rótulo."""

    instante: datetime
    pct_secoes: float
    votos: dict[str, int]                 # rótulo do candidato → votos acumulados


def ler_historico_totalizacao(fluxo: io.BufferedIOBase, *, maximo_pontos: int = 400) -> list[PontoHistorico]:
    """``Historico_Totalizacao_*`` → série acumulada, reduzida a ``maximo_pontos``.

    As colunas por candidato são ``<RÓTULO>_QT_VOTOS_TOT_ACUMULADO``; brancos
    e nulos (``BRANCO_``, ``NULO_``) ficam de fora da série, que é de votos
    válidos. A redução preserva o primeiro e o último ponto.
    """
    texto = io.TextIOWrapper(fluxo, encoding="latin-1", newline="")
    leitor = csv.reader(texto, delimiter=";")
    cab = [c.strip() for c in next(leitor)]
    ix = {c: i for i, c in enumerate(cab)}
    sufixo = "_QT_VOTOS_TOT_ACUMULADO"
    rotulos = [c[: -len(sufixo)] for c in cab if c.endswith(sufixo)
               and not c.startswith(("BRANCO_", "NULO_"))]
    i_pct = ix.get("PE_SECOES_TOT_ACUMULADO")
    pontos: list[PontoHistorico] = []
    for linha in leitor:
        if not linha or not linha[0].strip():
            continue
        try:
            instante = datetime.strptime(linha[0].strip(), "%d/%m/%Y %H:%M:%S").replace(tzinfo=BRT)
        except ValueError:
            continue
        pct = 0.0
        if i_pct is not None:
            try:
                pct = float(linha[i_pct].strip().replace(",", ".")) * 100.0
            except ValueError:
                pct = 0.0
        votos = {r: _int(linha[ix[r + sufixo]]) for r in rotulos}
        pontos.append(PontoHistorico(instante=instante, pct_secoes=round(pct, 4), votos=votos))
    return reduzir(pontos, maximo_pontos)


def reduzir(pontos: list, maximo: int) -> list:
    """Reduz a série a ``maximo`` pontos igualmente espaçados, mantendo o primeiro e o último."""
    if len(pontos) <= maximo or maximo < 2:
        return pontos
    passo = (len(pontos) - 1) / (maximo - 1)
    return [pontos[round(i * passo)] for i in range(maximo)]


def casar_rotulo(rotulo: str, candidatos: Iterable[Candidato]) -> str | None:
    """Rótulo do histórico (``JAIR_BOLSONARO``) → número do candidato."""
    candidatos = list(candidatos)
    alvo = chave_texto(rotulo.replace("_", " "))
    for c in candidatos:
        if alvo in (chave_texto(c.nome_urna), chave_texto(c.nome)):
            return c.numero
    # O rótulo do TSE tira pontuação e às vezes encurta o nome de urna
    # ("FELIPE_DAVILA" para "FELIPE D'AVILA"): compara só letras e números.
    so_letras = "".join(ch for ch in alvo if ch.isalnum())
    for c in candidatos:
        urna = "".join(ch for ch in chave_texto(c.nome_urna) if ch.isalnum())
        if urna and (urna == so_letras or urna in so_letras or so_letras in urna):
            return c.numero
    return None


# ---------------------------------------------------------------- arquivos

def abrir_zip(caminho: Path | str) -> zipfile.ZipFile:
    """Abre um ZIP dos dados abertos para leitura."""
    return zipfile.ZipFile(caminho)


def fluxos_do_zip(zf: zipfile.ZipFile, filtro: Callable[[str], bool] | None = None
                  ) -> Iterator[tuple[str, io.BufferedIOBase]]:
    """Gera (nome, fluxo binário) dos CSVs do ZIP na ordem de ``entradas_csv``, aplicando ``filtro``.

    Lê direto do ZIP, sem extrair para o disco; cada fluxo fica aberto só enquanto é consumido.
    """
    for nome in entradas_csv(zf.namelist()):
        if filtro and not filtro(nome):
            continue
        with zf.open(nome) as fluxo:
            yield nome, fluxo
