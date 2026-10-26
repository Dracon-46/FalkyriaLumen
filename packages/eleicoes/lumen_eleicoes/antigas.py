"""Eleições de 1933 a 1990: resultados por UF dos dados abertos do TSE.

Antes de 1994 o TSE não publica votação por município. O Portal de Dados
Abertos tem, para cada ano, três conjuntos por UF, todos em ZIP na CDN do
tribunal (``cdn.tse.jus.br/estatistica/sead/odsele``)::

    votacao_candidato_uf_AAAA.zip   votos de cada candidato em cada UF (26 colunas)
    detalhe_votacao_uf_AAAA.zip     aptos, comparecimento, brancos, nulos, legenda (22 colunas)
    votacao_partido_uf_AAAA.zip     votos nominais e de legenda por partido (17 colunas)

Em 1933 e 1934 os nomes terminam em ``_br`` (``votacao_candidato_uf_1933_br.zip``).

Formato observado em 06/10/2026 em todos os 56 arquivos (o de partido de 1989
não existe na fonte): texto Latin-1 (com dois caracteres do Windows-1252 em
toda a série, ver ``decodificar``), campos entre aspas e separados por ``;``,
um arquivo por UF ou um só para o Brasil. Só os de 1933 e 1934 têm cabeçalho;
nos demais a ordem das colunas é a do Leia-me do TSE, reproduzida em
``COLUNAS_CANDIDATO``, ``COLUNAS_DETALHE`` e ``COLUNAS_PARTIDO``. ``#NULO``
(campo em branco) equivale a ``-1``, e ``#NE`` (informação não registrada na
época) a ``-3``: os dois viram ``None``.

Particularidades da época, todas tratadas aqui e explicadas nos avisos dos feeds:

- Candidatos sem número de urna até os anos 1980 (``NUMERO_CAND = -1``): o
  candidato é identificado por um código estável derivado do nome
  (``chave_candidato``), e o feed marca ``sem_numero``.
- Cargos que não existem mais como votação própria (vice-presidente,
  vice-governador e suplente de senador, eleitos separadamente até 1960) e
  códigos com outro sentido (em 1934, o cargo 8 era vereador): o cargo leva
  slug e nível próprios (``Cargo.slug_fixo``).
- UFs extintas ou com outro território (Guanabara, Iguaçu, Ponta Porã,
  Fernando de Noronha, o Distrito Federal antes de 1960, que era a cidade do
  Rio de Janeiro): entram nos feeds com código próprio e sem código IBGE, para
  o mapa (com as fronteiras atuais) não pintar território errado. Guaporé e Rio
  Branco foram renomeados Rondônia e Roraima e usam a área atual.
- Em 1933 e 1934, os dois "turnos" publicados eram etapas de apuração da mesma
  votação proporcional (Código Eleitoral de 1932).
- Votos em branco contavam como válidos até 1997 e nulos até 1965 (Leia-me do
  TSE): os percentuais do Lumen são sempre sobre os votos dados a candidatos e
  legendas, e o feed diz isso.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
import zipfile
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Iterator

from lumen_normalizacao.transformacoes import chave_texto

from .dados_abertos import AVISO_SEM_DETALHE, CDN, NULOS, aviso_validos_da_epoca, situacao_publicada
from .feeds import (
    Abrangencia,
    EscritorFeeds,
    abrangencia_brasil,
    atribuir_cores,
    cores_dos_candidatos,
    entrada_indice,
    feed_panorama,
    feed_resultado,
    origem_json,
    parte_json,
    proporcional,
    ranking_partidos,
)
from .modelo import (
    CARGOS,
    Agremiacao,
    Candidato,
    Cargo,
    Comparecimento,
    Eleicao,
    Nivel,
    ResultadoAbrangencia,
    TipoCargo,
    Totalizacao,
    Votos,
)
from .municipios import codigo_ibge_da_uf, nome_da_uf, nome_legivel
from .transferencia import Manifesto

ANOS_ANTIGOS = (1933, 1934, 1945, 1947, 1950, 1954, 1955, 1958, 1960, 1962, 1965, 1966, 1970, 1974, 1978,
                1982, 1986, 1989, 1990)

CONJUNTO_CANDIDATO_UF = "votacao_candidato_uf"
CONJUNTO_DETALHE_UF = "detalhe_votacao_uf"
CONJUNTO_PARTIDO_UF = "votacao_partido_uf"
CONJUNTOS_UF = (CONJUNTO_CANDIDATO_UF, CONJUNTO_DETALHE_UF, CONJUNTO_PARTIDO_UF)

# Ordem das colunas do Leia-me do TSE (iguais aos cabeçalhos de 1933 e 1934).
COLUNAS_CANDIDATO = (
    "DATA_GERACAO", "HORA_GERACAO", "ANO_ELEICAO", "NUM_TURNO", "DESCRICAO_ELEICAO", "SIGLA_UF", "SIGLA_UE",
    "CODIGO_CARGO", "NUMERO_CAND", "SQ_CANDIDATO", "NOME_CANDIDATO", "NOME_URNA_CANDIDATO", "DESCRICAO_CARGO",
    "COD_SIT_CAND_SUPERIOR", "DESC_SIT_CAND_SUPERIOR", "CODIGO_SIT_CANDIDATO", "DESC_SIT_CANDIDATO",
    "CODIGO_SIT_CAND_TOT", "DESC_SIT_CAND_TOT", "NUMERO_PARTIDO", "SIGLA_PARTIDO", "NOME_PARTIDO",
    "SEQUENCIAL_LEGENDA", "NOME_COLIGACAO", "COMPOSICAO_LEGENDA", "TOTAL_VOTOS",
)
COLUNAS_DETALHE = (
    "DATA_GERACAO", "HORA_GERACAO", "ANO_ELEICAO", "NUM_TURNO", "DESCRICAO_ELEICAO", "SIGLA_UF", "SIGLA_UE",
    "CODIGO_CARGO", "DESCRICAO_CARGO", "QTD_APTOS", "QTD_COMPARECIMENTO", "QTD_ABSTENCOES", "QTD_VOTOS_NOMINAIS",
    "QTD_VOTOS_BRANCOS", "QTD_VOTOS_NULOS", "QTD_VOTOS_LEGENDA", "QTD_VOTOS_ANULADOS_APU_SEP", "QTD_SECOES_TOT",
    "QTD_SECOES_ANULADAS", "QTD_SECOES_SEM_FUNCION", "QTD_ZONAS_ELEITORAIS", "QTD_JUNTAS_APURADORAS",
)
COLUNAS_PARTIDO = (
    "DATA_GERACAO", "HORA_GERACAO", "ANO_ELEICAO", "NUM_TURNO", "DESCRICAO_ELEICAO", "SIGLA_UF", "SIGLA_UE",
    "CODIGO_CARGO", "DESCRICAO_CARGO", "TIPO_LEGENDA", "NOME_COLIGACAO", "COMPOSICAO_LEGENDA", "SIGLA_PARTIDO",
    "NUMERO_PARTIDO", "NOME_PARTIDO", "QTDE_VOTOS_NOMINAIS", "QTDE_VOTOS_LEGENDA",
)

AVISO_SO_POR_UF = (
    "Eleição anterior a 1994: o TSE publica o resultado só por UF, a partir da digitalização dos documentos "
    "oficiais de apuração, e os dados estão sujeitos a correção. Não há resultado por município."
)
AVISO_TURNOS_1932 = (
    "Em 1933 e 1934 o TSE publica a votação em dois turnos. Pelo Código Eleitoral de 1932, os dois turnos "
    "eram etapas de apuração da mesma votação proporcional, e não duas votações."
)
AVISO_MAPA_FRONTEIRAS = (
    "O mapa usa as fronteiras atuais. UFs que não existem mais, ou cujo território era outro (como o "
    "Distrito Federal antes de 1960, que era a cidade do Rio de Janeiro), aparecem só na lista."
)
AVISO_SEM_VOTACAO = "Há candidatos sem votação registrada na fonte; eles aparecem sem percentual."
AVISO_VARIOS_NOMES_1932 = (
    "No 2º turno de apuração, cada cédula podia contar para mais de um nome, e a soma dos votos dos candidatos "
    "passa do número de votantes. Os percentuais são sobre o total de votos dados a candidatos nesta etapa."
)


def aviso_soma_diferente(soma: int, nominais: int) -> str:
    """Aviso de quando os candidatos do arquivo não somam o total de votos nominais do detalhe.

    A base dos percentuais é o maior dos dois: com o total do detalhe maior, faltam candidatos no arquivo;
    com a soma maior, usar o detalhe daria percentuais somando mais de 100%.
    """
    def n(v: int) -> str:
        return f"{v:,}".replace(",", ".")
    base = "o total do detalhe" if nominais >= soma else "a soma dos candidatos"
    return (f"Os candidatos deste arquivo somam {n(soma)} votos, e o detalhe da apuração registra {n(nominais)} "
            f"votos nominais; a diferença está na fonte. Os percentuais usam {base}.")


def url_conjunto_uf(conjunto: str, ano: int) -> str:
    """URL do ZIP de um conjunto por UF na CDN do TSE; 1933 e 1934 levam o sufixo ``_br``."""
    sufixo = "_br" if ano in (1933, 1934) else ""
    return f"{CDN}/{conjunto}/{conjunto}_{ano}{sufixo}.zip"


def nome_arquivo_uf(conjunto: str, ano: int) -> str:
    """Nome do ZIP de um conjunto por UF, como gravado no diretório de arquivos."""
    return url_conjunto_uf(conjunto, ano).rsplit("/", 1)[-1]


# ---------------------------------------------------------------- UFs da época

@dataclass(frozen=True)
class UfHistorica:
    """Uma UF como aparece numa eleição antiga: código do feed, nome exibido e código IBGE da área no mapa.

    ``ibge`` é None quando a área atual não corresponde ao território da época: a UF fica fora do mapa e
    aparece só na lista.
    """

    codigo: str
    nome: str
    ibge: str | None


# Siglas (ou nomes) da fonte que não são UFs atuais: código do feed, nome, código IBGE da área no mapa.
_EXTINTAS = {
    "FERNANDO DE NORONHA": ("fn", "Território de Fernando de Noronha", None),
    "IGUACU": ("ig", "Território do Iguaçu", None),
    "PONTA PORA": ("pp", "Território de Ponta Porã", None),
    "GB": ("gb", "Guanabara", None),
    # Renomeados: o território é o mesmo da UF atual (Guaporé → Rondônia em 1956, Rio Branco → Roraima em 1962)
    "GP": ("gp", "Território do Guaporé (atual Rondônia)", "11"),
    "RB": ("rb", "Território do Rio Branco (atual Roraima)", "14"),
}


def uf_historica(sigla: str, ano: int) -> UfHistorica:
    """UF de uma linha antiga a partir de ``SIGLA_UF`` e do ano da eleição.

    O Distrito Federal anterior a 1960 era a cidade do Rio de Janeiro: entra como ``df-antigo``, sem área
    no mapa (a área atual do DF é Brasília). Sigla desconhecida vira código seguro derivado do texto.
    """
    chave = chave_texto(sigla).upper()
    if chave == "DF" and ano < 1960:
        return UfHistorica("df-antigo", "Distrito Federal (cidade do Rio de Janeiro)", None)
    if chave in _EXTINTAS:
        codigo, nome, ibge = _EXTINTAS[chave]
        return UfHistorica(codigo, nome, ibge)
    if chave == "ZZ":
        return UfHistorica("zz", nome_da_uf("zz"), None)
    ibge = codigo_ibge_da_uf(chave)
    if ibge:
        return UfHistorica(chave.lower(), nome_da_uf(chave), ibge)
    codigo = re.sub(r"[^a-z0-9]+", "-", chave_texto(sigla)).strip("-") or "uf"
    return UfHistorica(codigo, sigla.strip(), None)


def abrangencia_uf_historica(uf: UfHistorica) -> Abrangencia:
    """``Abrangencia`` de UF para uma UF da época (código, nome e IBGE da ``UfHistorica``)."""
    return Abrangencia("uf", uf.codigo, uf.nome, uf=uf.codigo, ibge=uf.ibge)


# ---------------------------------------------------------------- leitura

def _texto(valor: str | None) -> str | None:
    """Texto da célula sem espaços nas pontas; marcadores de ausência do TSE viram None."""
    if valor is None:
        return None
    v = valor.strip()
    return None if v in NULOS or v.upper() in ("#NE#", "#NULO#") else v


def _numero(valor: str | None) -> int | None:
    """Inteiro da célula; ausência (``-1``, ``-3``, ``#NULO``) e valores negativos viram None."""
    v = _texto(valor)
    if v is None:
        return None
    try:
        n = int(v)
    except ValueError:
        return None
    return n if n >= 0 else None


def linhas_tabela(texto: str, colunas: tuple[str, ...]) -> Iterator[dict[str, str]]:
    """Linhas de um arquivo antigo como dicionários pelo nome da coluna (ordem de ``colunas``).

    Pula o cabeçalho quando existe (1933 e 1934) e as linhas com número de colunas diferente do
    esperado, que não têm como ser lidas com segurança.
    """
    for linha in csv.reader(io.StringIO(texto), delimiter=";", quotechar='"'):
        if not linha or (linha[0].strip().upper() == "DATA_GERACAO"):
            continue
        if len(linha) != len(colunas):
            continue
        yield dict(zip(colunas, linha))


# O TSE declara Latin-1, mas há bytes de 0x80 a 0x9F com o sentido do Windows-1252 (em 1954, o apóstrofo
# tipográfico de "D’AVILA"). Em Latin-1 puro eles seriam caracteres de controle invisíveis.
_C1_WINDOWS = {i: bytes([i]).decode("cp1252") for i in range(0x80, 0xA0) if i not in (0x81, 0x8D, 0x8F, 0x90, 0x9D)}


def decodificar(dados: bytes) -> str:
    """Texto de um arquivo antigo: Latin-1, com a faixa 0x80–0x9F lida como Windows-1252."""
    return dados.decode("latin-1").translate(_C1_WINDOWS)


def textos_do_zip(caminho: Path | str) -> Iterator[tuple[str, str]]:
    """(nome, texto) de cada ``.txt`` ou ``.csv`` dentro do ZIP, em ordem de nome (``decodificar``)."""
    with zipfile.ZipFile(caminho) as zf:
        for nome in sorted(zf.namelist()):
            if nome.lower().endswith((".txt", ".csv")):
                yield nome, decodificar(zf.read(nome))


def chave_candidato(numero: int | None, nome: str, partido: str | None, *, nacional: bool) -> tuple[str, bool]:
    """Identificador do candidato no feed e se ele é o número de urna publicado.

    Com número de urna (a partir dos anos 1980), é o próprio número. Sem ele, um código estável derivado
    do nome — e do partido, nos cargos estaduais, para homônimos de partidos diferentes não se fundirem.
    Nos cargos nacionais, só o nome: é ele que liga as linhas do mesmo candidato nas várias UFs.
    """
    if numero:
        return str(numero), True
    base = chave_texto(nome) if nacional else f"{chave_texto(nome)}|{chave_texto(partido)}"
    return "s" + hashlib.sha1(base.encode("utf-8")).hexdigest()[:10], False


def _slug(texto: str) -> str:
    """Slug seguro para caminhos de feed: sem acento, minúsculas, hífen no lugar do resto."""
    return re.sub(r"[^a-z0-9]+", "-", chave_texto(texto)).strip("-") or "cargo"


def cargo_antigo(codigo: int, descricao: str, nacional: bool) -> Cargo:
    """``Cargo`` de uma eleição antiga a partir do código e da descrição publicados.

    Quando código e descrição batem com a tabela atual (Presidente é 1, Governador 3...), usa a tabela, e
    o cargo tem o mesmo endereço das eleições recentes. Senão, slug e nível vêm da própria descrição e da
    ``SIGLA_UE`` (``BR`` é nacional). Deputados e vereadores são proporcionais; o resto, majoritário.
    """
    desc = (descricao or "").strip()
    tipo = (TipoCargo.PROPORCIONAL if chave_texto(desc).startswith(("deputado", "vereador"))
            else TipoCargo.MAJORITARIO)
    if codigo in CARGOS and chave_texto(CARGOS[codigo][1]) == chave_texto(desc):
        return Cargo(codigo=codigo, nome=CARGOS[codigo][1], tipo=tipo, eleicao_tse=0)
    return Cargo(codigo=codigo, nome=nome_legivel(desc.upper()) if desc else f"Cargo {codigo}", tipo=tipo,
                 eleicao_tse=0, slug_fixo=_slug(desc or f"cargo-{codigo}"),
                 nivel_fixo=Nivel.BRASIL if nacional else Nivel.UF)


@dataclass
class _Cand:
    """Um candidato numa UF, como lido: identificação, partido, situação e votos (None se não registrados)."""

    chave: str
    publicado: bool
    nome: str
    nome_urna: str
    partido: str | None
    agremiacao: str | None
    composicao: str | None
    situacao: str
    votos: int | None


@dataclass
class _Det:
    """Totais do detalhe de uma UF; cada campo é None quando a fonte não o registra."""

    aptos: int | None = None
    comparecimento: int | None = None
    abstencoes: int | None = None
    nominais: int | None = None
    brancos: int | None = None
    nulos: int | None = None
    legenda: int | None = None
    anulados: int | None = None
    secoes: int | None = None


@dataclass
class _Partido:
    """Uma linha da votação por partido: rótulo do partido (ou da agremiação), tipo e votos."""

    rotulo: str
    tipo: str
    composicao: str | None
    nominais: int | None
    legenda: int | None
    eh_partido: bool


def _rotulo_partido(sigla: str | None, nome: str | None, composicao: str | None = None) -> str | None:
    """Rótulo do partido nos feeds: a sigla; sem sigla (grupos de eleitores, chapas), o nome.

    Sem os dois — em 1962 o TSE deixou sigla e nome em branco em todas as linhas —, a composição da
    legenda, quando ela é um partido só (sem "/"); composição de coligação não identifica o partido.
    """
    rotulo = _texto(sigla) or _texto(nome)
    if rotulo:
        return rotulo
    comp = _texto(composicao)
    return comp if comp and "/" not in comp else None


@dataclass
class LeituraAno:
    """Tudo o que os três arquivos de um ano antigo trazem, já organizado por eleição, cargo e UF."""

    ano: int
    cargos: dict[tuple[str, int], Cargo] = field(default_factory=dict)
    candidatos: dict[tuple[str, int, str], dict[str, _Cand]] = field(default_factory=lambda: defaultdict(dict))
    ufs: dict[str, UfHistorica] = field(default_factory=dict)
    detalhe: dict[tuple[str, int, str], _Det] = field(default_factory=dict)
    partidos: dict[tuple[str, int, str], list[_Partido]] = field(default_factory=lambda: defaultdict(list))
    turnos: set[int] = field(default_factory=set)
    linhas_lidas: int = 0
    linhas_ignoradas: int = 0
    sem_nome: int = 0

    def eid(self, turno: int) -> str:
        """Id da eleição no feed: ``<ano>-<turno>t-geral``."""
        return f"{self.ano}-{turno}t-geral"

    def ler_candidatos(self, texto: str) -> None:
        """Acrescenta as linhas de um arquivo de votação por candidato.

        Linha repetida do mesmo candidato na mesma UF soma os votos (a fonte às vezes divide a votação
        em mais de uma linha). Situação vazia de uma linha não apaga a de outra.
        """
        for linha in linhas_tabela(texto, COLUNAS_CANDIDATO):
            turno = _numero(linha["NUM_TURNO"])
            codigo = _numero(linha["CODIGO_CARGO"])
            if turno is None or codigo is None:
                self.linhas_ignoradas += 1
                continue
            self.linhas_lidas += 1
            self.turnos.add(turno)
            nacional = (linha["SIGLA_UE"] or "").strip().upper() == "BR"
            eid = self.eid(turno)
            if (eid, codigo) not in self.cargos:
                self.cargos[(eid, codigo)] = cargo_antigo(codigo, linha["DESCRICAO_CARGO"], nacional)
            uf = uf_historica(linha["SIGLA_UF"], self.ano)
            self.ufs[uf.codigo] = uf
            partido = _rotulo_partido(linha["SIGLA_PARTIDO"], linha["NOME_PARTIDO"], linha["COMPOSICAO_LEGENDA"])
            numero = _numero(linha["NUMERO_CAND"])
            nome = _texto(linha["NOME_CANDIDATO"])
            if not nome:
                # Linha com votos e sem nome (há na fonte, em 1954 e 1986): entra com o número de urna, ou
                # como "nome não registrado", sem se fundir com outra linha sem nome do mesmo partido.
                self.sem_nome += 1
                nome = f"Candidato nº {numero}" if numero else "Nome não registrado na fonte"
                if not numero:
                    nome_chave = f"{nome}|{self.sem_nome}"
                    chave, publicado = chave_candidato(None, nome_chave, partido, nacional=nacional)
                else:
                    chave, publicado = chave_candidato(numero, nome, partido, nacional=nacional)
            else:
                chave, publicado = chave_candidato(numero, nome, partido, nacional=nacional)
            votos = _numero(linha["TOTAL_VOTOS"])
            grupo = self.candidatos[(eid, codigo, uf.codigo)]
            atual = grupo.get(chave)
            situacao = situacao_publicada(_texto(linha["DESC_SIT_CAND_TOT"]))
            if atual is None:
                grupo[chave] = _Cand(chave=chave, publicado=publicado, nome=nome,
                                     nome_urna=_texto(linha["NOME_URNA_CANDIDATO"]) or nome, partido=partido,
                                     agremiacao=_texto(linha["NOME_COLIGACAO"]),
                                     composicao=_texto(linha["COMPOSICAO_LEGENDA"]), situacao=situacao, votos=votos)
            else:
                if votos is not None:
                    atual.votos = (atual.votos or 0) + votos
                if situacao and not atual.situacao:
                    atual.situacao = situacao

    def ler_detalhe(self, texto: str) -> None:
        """Acrescenta as linhas de um arquivo de detalhe. Turno não registrado (``-3``, em 1933) vale para
        os dois turnos."""
        for linha in linhas_tabela(texto, COLUNAS_DETALHE):
            codigo = _numero(linha["CODIGO_CARGO"])
            if codigo is None:
                continue
            turno = _numero(linha["NUM_TURNO"])
            uf = uf_historica(linha["SIGLA_UF"], self.ano)
            det = _Det(aptos=_numero(linha["QTD_APTOS"]), comparecimento=_numero(linha["QTD_COMPARECIMENTO"]),
                       abstencoes=_numero(linha["QTD_ABSTENCOES"]), nominais=_numero(linha["QTD_VOTOS_NOMINAIS"]),
                       brancos=_numero(linha["QTD_VOTOS_BRANCOS"]), nulos=_numero(linha["QTD_VOTOS_NULOS"]),
                       legenda=_numero(linha["QTD_VOTOS_LEGENDA"]),
                       anulados=_numero(linha["QTD_VOTOS_ANULADOS_APU_SEP"]),
                       secoes=_numero(linha["QTD_SECOES_TOT"]))
            for t in ([turno] if turno else [1, 2]):
                self.detalhe[(self.eid(t), codigo, uf.codigo)] = det

    def ler_partidos(self, texto: str) -> None:
        """Acrescenta as linhas de um arquivo de votação por partido (agremiações e votos de legenda)."""
        for linha in linhas_tabela(texto, COLUNAS_PARTIDO):
            turno, codigo = _numero(linha["NUM_TURNO"]), _numero(linha["CODIGO_CARGO"])
            if turno is None or codigo is None:
                continue
            uf = uf_historica(linha["SIGLA_UF"], self.ano)
            partido = _rotulo_partido(linha["SIGLA_PARTIDO"], linha["NOME_PARTIDO"], linha["COMPOSICAO_LEGENDA"])
            rotulo = partido or _texto(linha["NOME_COLIGACAO"]) or _texto(linha["COMPOSICAO_LEGENDA"])
            if not rotulo:
                continue
            self.partidos[(self.eid(turno), codigo, uf.codigo)].append(_Partido(
                rotulo=rotulo, tipo=(_texto(linha["TIPO_LEGENDA"]) or "").lower(),
                composicao=_texto(linha["COMPOSICAO_LEGENDA"]), nominais=_numero(linha["QTDE_VOTOS_NOMINAIS"]),
                legenda=_numero(linha["QTDE_VOTOS_LEGENDA"]), eh_partido=partido is not None))


def ler_ano(ano: int, *, candidatos: Iterable[str], detalhe: Iterable[str] = (),
            partidos: Iterable[str] = ()) -> LeituraAno:
    """Lê os textos dos três conjuntos de um ano (cada um pode vir em vários arquivos, um por UF)."""
    leitura = LeituraAno(ano)
    for t in candidatos:
        leitura.ler_candidatos(t)
    for t in detalhe:
        leitura.ler_detalhe(t)
    for t in partidos:
        leitura.ler_partidos(t)
    return leitura


# ---------------------------------------------------------------- resultados

def _pct(parte: int | None, todo: int | None) -> float | None:
    """Percentual com 6 casas, ou None sem base."""
    return round(100.0 * parte / todo, 6) if parte is not None and todo else None


def _resultado(leitura: LeituraAno, eid: str, cargo: Cargo, uf_codigo: str | None,
               cands: list[_Cand], det: _Det | None, partidos: list[_Partido]) -> ResultadoAbrangencia:
    """Monta o ``ResultadoAbrangencia`` de uma UF (ou do Brasil, com ``uf_codigo`` None).

    Base dos percentuais: o maior entre os votos nominais do detalhe e a soma dos candidatos, mais os de
    legenda; sem detalhe, a soma dos candidatos. Candidato sem votação registrada fica com 0 voto, não
    válido e sem percentual.
    """
    avisos = [AVISO_SO_POR_UF]
    if leitura.ano in (1933, 1934):
        avisos.append(AVISO_TURNOS_1932)
    regra = aviso_validos_da_epoca(leitura.ano)
    if regra:
        avisos.append(regra)
    soma = sum(c.votos for c in cands if c.votos is not None)
    legenda = det.legenda if det and det.legenda is not None else None
    if legenda is None and partidos and any(p.legenda for p in partidos if p.eh_partido):
        legenda = sum(p.legenda or 0 for p in partidos if p.eh_partido)
    nominais = det.nominais if det and det.nominais else None
    varios_nomes = leitura.ano in (1933, 1934) and eid.split("-")[1] == "2t"
    if det is None:
        avisos.append(AVISO_SEM_DETALHE)
    elif varios_nomes and nominais and soma > nominais:
        avisos.append(AVISO_VARIOS_NOMES_1932)
    elif nominais and abs(nominais - soma) > max(1, 0.005 * nominais):
        avisos.append(aviso_soma_diferente(soma, nominais))
    base = max(nominais or 0, soma) + (legenda or 0)
    if any(c.votos is None for c in cands):
        avisos.append(AVISO_SEM_VOTACAO)

    candidatos = [Candidato(
        numero=c.chave, sq=None, nome=c.nome, nome_urna=c.nome_urna, partido=c.partido, agremiacao=c.agremiacao,
        composicao=c.composicao, votos=c.votos or 0, pct_validos=_pct(c.votos, base),
        situacao=c.situacao, eleito=c.situacao.lower().startswith("eleito"), segundo_turno=c.situacao == "2º turno",
        destinacao=None if c.votos is not None else "Votação não registrada", numero_publicado=c.publicado,
    ) for c in cands]
    candidatos.sort(key=lambda c: (not c.valido, -c.votos, chave_texto(c.nome_urna)))

    votos_partido: dict[str, int] = {}
    agremiacoes: list[Agremiacao] = []
    if proporcional(cargo):
        eleitos: dict[str, int] = defaultdict(int)
        for c in candidatos:
            if c.eleito and c.partido:
                eleitos[c.partido] += 1
        for p in partidos:
            total = (p.nominais or 0) + (p.legenda or 0)
            if p.eh_partido and total:
                votos_partido[p.rotulo] = votos_partido.get(p.rotulo, 0) + total
        if votos_partido:
            agremiacoes = [Agremiacao(nome=nome, tipo="partido", composicao=None, votos=v, vagas=eleitos.get(nome, 0))
                           for nome, v in votos_partido.items()]
        else:
            soma_partido: dict[str, int] = defaultdict(int)
            for c in candidatos:
                if c.valido and c.partido:
                    soma_partido[c.partido] += c.votos
            agremiacoes = [Agremiacao(nome=nome, tipo="partido", composicao=None, votos=v, vagas=eleitos.get(nome, 0))
                           for nome, v in soma_partido.items()]
        agremiacoes.sort(key=lambda a: (-(a.vagas or 0), -a.votos, a.nome))

    brancos = det.brancos if det else None
    nulos = det.nulos if det else None
    anulados = det.anulados if det else None
    total_votos = base + (brancos or 0) + (nulos or 0) + (anulados or 0)
    aptos = det.aptos if det else None
    comparecimento = det.comparecimento if det else None
    abstencoes = det.abstencoes if det else None
    if abstencoes is None and aptos is not None and comparecimento is not None and aptos >= comparecimento:
        abstencoes = aptos - comparecimento
    eleitos_total = sum(1 for c in candidatos if c.eleito)
    return ResultadoAbrangencia(
        eleicao_tse=None, cargo=cargo.codigo, vagas=eleitos_total or None,
        abrangencia_tipo="uf" if uf_codigo else "br", abrangencia_codigo=uf_codigo or "br", atualizado_em=None,
        totalizacao=Totalizacao(secoes=det.secoes if det and det.secoes else None,
                                secoes_totalizadas=det.secoes if det and det.secoes else None,
                                pct_secoes=100.0, finalizada=True, andamento="f"),
        comparecimento=Comparecimento(eleitorado=aptos, comparecimento=comparecimento, abstencao=abstencoes,
                                      pct_comparecimento=_pct(comparecimento, aptos),
                                      pct_abstencao=_pct(abstencoes, aptos)),
        votos=Votos(validos=base or None, brancos=brancos, nulos=nulos, anulados=anulados, legenda=legenda,
                    pct_validos=_pct(base, total_votos), pct_brancos=_pct(brancos, total_votos),
                    pct_nulos=_pct(nulos, total_votos)),
        candidatos=candidatos, agremiacoes=agremiacoes, avisos=avisos, votos_partido=votos_partido,
    )


def _somar_detalhes(dets: list[_Det | None]) -> _Det | None:
    """Soma dos detalhes das UFs para o Brasil.

    Se alguma UF não tem detalhe, devolve None (e a base vira a soma dos candidatos); campo que falta em
    alguma UF fica None: total incompleto não é apresentado como total.
    """
    if not dets or any(d is None for d in dets):
        return None
    soma = _Det()
    for campo in ("aptos", "comparecimento", "abstencoes", "nominais", "brancos", "nulos", "legenda",
                  "anulados", "secoes"):
        valores = [getattr(d, campo) for d in dets]
        setattr(soma, campo, None if any(v is None for v in valores) else sum(valores))
    return soma


def _somar_candidatos(grupos: list[list[_Cand]]) -> list[_Cand]:
    """Candidatos do Brasil: soma, pela chave, dos de cada UF; situação da primeira linha que a informa."""
    por: dict[str, _Cand] = {}
    for grupo in grupos:
        for c in grupo:
            atual = por.get(c.chave)
            if atual is None:
                por[c.chave] = _Cand(**{**c.__dict__})
            else:
                if c.votos is not None:
                    atual.votos = (atual.votos or 0) + c.votos
                if c.situacao and not atual.situacao:
                    atual.situacao = c.situacao
    return list(por.values())


def nome_eleicao_antiga(ano: int, turno: int, turnos_no_ano: int) -> str:
    """Nome exibido: ``Eleições 1950``; com dois turnos no ano, ``Eleições 1989 — 1º turno``.

    1933 é a eleição da Assembleia Nacional Constituinte, como o TSE a descreve.
    """
    base = "Eleição de 1933 — Assembleia Nacional Constituinte" if ano == 1933 else f"Eleições {ano}"
    return f"{base} — {turno}º turno" if turnos_no_ano > 1 else base


@dataclass
class ResumoAntigo:
    """Contagens do processamento de um ano antigo, para o resumo da linha de comando."""

    ano: int
    eleicoes: list[str] = field(default_factory=list)
    feeds: int = 0
    linhas_lidas: int = 0
    linhas_ignoradas: int = 0


class ProcessadorAnoAntigo:
    """Transforma os três ZIPs por UF de um ano antigo nos feeds do portal (Brasil e UFs, sem municípios).

    Cargo nacional (Presidente, Vice-presidente): feed ``br`` com as UFs em ``partes`` e um feed por UF.
    Cargo estadual: um feed por UF e o panorama ``br`` (quem lidera em cada UF). O índice marca a eleição
    com ``municipios: false``.
    """

    def __init__(self, ano: int, escritor: EscritorFeeds, *, origem: Manifesto | None = None,
                 progresso: Callable[[str], None] | None = None):
        """Ano, destino dos feeds e, quando houver, o manifesto do ZIP de candidatos (origem dos números)."""
        if ano not in ANOS_ANTIGOS:
            raise ValueError(f"{ano} não é um ano com resultados só por UF ({ANOS_ANTIGOS[0]} a {ANOS_ANTIGOS[-1]})")
        self.ano = ano
        self.escritor = escritor
        self.progresso = progresso or (lambda _msg: None)
        self.origem = origem_json(
            "dados_abertos",
            url=origem.url if origem else url_conjunto_uf(CONJUNTO_CANDIDATO_UF, ano),
            sha256=origem.sha256 if origem else None,
            coletado_em=origem.baixado_em if origem else None,
        )

    def processar_zips(self, candidatos: Path | str, detalhe: Path | str | None = None,
                       partidos: Path | str | None = None) -> ResumoAntigo:
        """Lê os ZIPs (detalhe e partidos são opcionais) e grava os feeds."""
        self.progresso(f"{self.ano}: lendo os arquivos por UF")
        leitura = ler_ano(
            self.ano,
            candidatos=(t for _, t in textos_do_zip(candidatos)),
            detalhe=(t for _, t in textos_do_zip(detalhe)) if detalhe else (),
            partidos=(t for _, t in textos_do_zip(partidos)) if partidos else (),
        )
        return self.emitir(leitura)

    def emitir(self, leitura: LeituraAno) -> ResumoAntigo:
        """Grava os feeds de tudo o que a leitura organizou e atualiza o índice."""
        resumo = ResumoAntigo(ano=self.ano, linhas_lidas=leitura.linhas_lidas,
                              linhas_ignoradas=leitura.linhas_ignoradas)
        n_turnos = len(leitura.turnos)
        eleicoes: dict[str, Eleicao] = {}
        ufs_eleicao: dict[str, set[str]] = defaultdict(set)
        ufs_cargo: dict[str, dict[int, set[str]]] = defaultdict(lambda: defaultdict(set))
        for (eid, codigo), cargo in sorted(leitura.cargos.items(), key=lambda kv: (kv[0][0], kv[0][1])):
            e = eleicoes.get(eid)
            if e is None:
                turno = int(eid.split("-")[1][0])
                e = eleicoes[eid] = Eleicao(id=eid, ano=self.ano, turno=turno, tipo="geral",
                                            nome=nome_eleicao_antiga(self.ano, turno, n_turnos), data=None,
                                            ciclo=f"ele{self.ano}", pleito=None, origem="dados_abertos")
            e.cargos.append(cargo)
            ufs = sorted(u for (ei, c, u) in leitura.candidatos if ei == eid and c == codigo)
            resultados: dict[str, ResultadoAbrangencia] = {}
            for u in ufs:
                cands = list(leitura.candidatos[(eid, codigo, u)].values())
                resultados[u] = _resultado(leitura, eid, cargo, u, cands, leitura.detalhe.get((eid, codigo, u)),
                                           leitura.partidos.get((eid, codigo, u), []))
                ufs_eleicao[eid].add(u)
                ufs_cargo[eid][codigo].add(u)
            resumo.feeds += self._emitir_cargo(leitura, e, cargo, resultados)
        for eid, e in eleicoes.items():
            self.escritor.atualizar_indice(entrada_indice(
                e, origem="dados_abertos", ao_vivo=False, atualizado_em=None, ufs=ufs_eleicao[eid],
                ufs_por_cargo=ufs_cargo[eid], municipios=False))
        resumo.eleicoes = sorted(eleicoes)
        return resumo

    def _emitir_cargo(self, leitura: LeituraAno, e: Eleicao, cargo: Cargo,
                      resultados: dict[str, ResultadoAbrangencia]) -> int:
        """Grava os feeds de um cargo: um por UF e o do Brasil (resultado ou panorama). Devolve quantos."""
        por_partido = proporcional(cargo)
        nacional = cargo.nivel is Nivel.BRASIL
        gravados = 0
        cores_br: dict[str, int] = {}
        r_br: ResultadoAbrangencia | None = None
        if nacional:
            grupos = [list(leitura.candidatos[(e.id, cargo.codigo, u)].values()) for u in resultados]
            dets = [leitura.detalhe.get((e.id, cargo.codigo, u)) for u in resultados]
            r_br = _resultado(leitura, e.id, cargo, None, _somar_candidatos(grupos), _somar_detalhes(dets), [])
            cores_br = cores_dos_candidatos(r_br)
        partes: list[dict] = []
        fora_do_mapa = False
        for u, r in resultados.items():
            uf = leitura.ufs[u]
            abr = abrangencia_uf_historica(uf)
            if nacional:
                cores = cores_br
            elif por_partido:
                cores = atribuir_cores(p for p, _ in ranking_partidos(r))
            else:
                cores = cores_dos_candidatos(r)
            self.escritor.gravar(e.id, cargo.slug, abr, feed_resultado(
                eleicao=e, cargo=cargo, abr=abr, resultado=r, cores=cores, origem=self.origem))
            gravados += 1
            partes.append(parte_json(abr, r, cores, por_partido=por_partido))
            fora_do_mapa = fora_do_mapa or (uf.ibge is None and uf.codigo != "zz")
        abr_br = abrangencia_brasil()
        if nacional and r_br is not None:
            if fora_do_mapa:
                r_br.avisos.append(AVISO_MAPA_FRONTEIRAS)
            self.escritor.gravar(e.id, cargo.slug, abr_br, feed_resultado(
                eleicao=e, cargo=cargo, abr=abr_br, resultado=r_br, cores=cores_br, origem=self.origem,
                partes=partes))
        else:
            avisos = [AVISO_SO_POR_UF] + ([AVISO_MAPA_FRONTEIRAS] if fora_do_mapa else [])
            self.escritor.gravar(e.id, cargo.slug, abr_br, feed_panorama(
                eleicao=e, cargo=cargo, abr=abr_br, partes=partes, origem=self.origem, atualizado_em=None,
                avisos=avisos))
        return gravados + 1
