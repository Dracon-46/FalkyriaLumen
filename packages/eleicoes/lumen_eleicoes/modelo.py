"""Modelo dos resultados eleitorais, comum às duas fontes do TSE."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum


class TipoCargo(str, Enum):
    """Forma de eleição do cargo: majoritário (vence o mais votado) ou proporcional (vagas divididas entre
    partidos pelo quociente eleitoral)."""

    MAJORITARIO = "majoritario"
    PROPORCIONAL = "proporcional"


class Nivel(str, Enum):
    """Menor abrangência em que o cargo é disputado."""

    BRASIL = "br"
    UF = "uf"
    MUNICIPIO = "mu"


# Cargos do TSE: código → (slug, nome, nível). Os códigos são os do sistema de
# resultados e dos dados abertos (CD_CARGO), iguais nas duas fontes.
CARGOS: dict[int, tuple[str, str, Nivel]] = {
    1: ("presidente", "Presidente", Nivel.BRASIL),
    3: ("governador", "Governador", Nivel.UF),
    5: ("senador", "Senador", Nivel.UF),
    6: ("deputado-federal", "Deputado Federal", Nivel.UF),
    7: ("deputado-estadual", "Deputado Estadual", Nivel.UF),
    8: ("deputado-distrital", "Deputado Distrital", Nivel.UF),
    11: ("prefeito", "Prefeito", Nivel.MUNICIPIO),
    13: ("vereador", "Vereador", Nivel.MUNICIPIO),
    25: ("conselheiro-distrital", "Conselheiro Distrital", Nivel.MUNICIPIO),
}


def slug_do_cargo(codigo: int) -> str:
    """Slug do cargo nos caminhos dos feeds; código fora de ``CARGOS`` vira ``cargo-<código>``."""
    return CARGOS[codigo][0] if codigo in CARGOS else f"cargo-{codigo}"


@dataclass(frozen=True)
class Cargo:
    """Cargo em disputa numa eleição: código do TSE (``CD_CARGO``), nome e tipo.

    Slug e nível derivam do código pela tabela ``CARGOS``; ``vagas`` só é preenchido quando a fonte informa.

    ``slug_fixo`` e ``nivel_fixo`` existem para as eleições de 1933 a 1990, em que o mesmo código
    nomeava outro cargo (em 1934, o 8 era vereador, e não deputado distrital) e havia cargos que
    deixaram de existir como votação própria (vice-presidente, vice-governador, suplente de senador).
    Quando preenchidos, valem no lugar do que a tabela ``CARGOS`` diria.
    """

    codigo: int
    nome: str
    tipo: TipoCargo
    eleicao_tse: int                 # código da "eleição" do TSE que contém o cargo
    vagas: int | None = None
    slug_fixo: str | None = None
    nivel_fixo: Nivel | None = None

    @property
    def slug(self) -> str:
        """Slug do cargo nos caminhos dos feeds: o fixo, quando há; senão o da tabela (``slug_do_cargo``)."""
        return self.slug_fixo or slug_do_cargo(self.codigo)

    @property
    def nivel(self) -> Nivel:
        """Nível em que o cargo é disputado: o fixo, quando há; senão o da tabela, e municipal fora dela."""
        if self.nivel_fixo is not None:
            return self.nivel_fixo
        return CARGOS[self.codigo][2] if self.codigo in CARGOS else Nivel.MUNICIPIO


@dataclass
class Eleicao:
    """O que o eleitor reconhece como "a eleição": um pleito num turno.

    O TSE divide um mesmo dia de votação em várias "eleições" (federal com
    presidente, estadual com governador, senado e deputados). Para a aba
    elas são uma só, agrupadas pelo pleito e pelo turno.
    """

    id: str                          # ex.: "2026-1t-geral"
    ano: int
    turno: int
    tipo: str                        # geral, municipal, suplementar, consulta
    nome: str
    data: date | None
    ciclo: str                       # ex.: "ele2026"
    pleito: str | None
    origem: str                      # "resultados" ou "dados_abertos"
    cargos: list[Cargo] = field(default_factory=list)
    abrangencias: list[str] = field(default_factory=list)  # UFs com eleição (municipal/suplementar)

    def cargo(self, slug_ou_codigo: str | int) -> Cargo:
        """Cargo da eleição pelo slug ou pelo código (inteiro ou texto); ``KeyError`` se não existir."""
        for c in self.cargos:
            if c.slug == slug_ou_codigo or c.codigo == slug_ou_codigo or str(c.codigo) == str(slug_ou_codigo):
                return c
        raise KeyError(f"cargo {slug_ou_codigo!r} não existe em {self.id}")


@dataclass
class Candidato:
    """Candidato num resultado: identificação, partido e agremiação, votos e situação publicada.

    ``numero`` é o número de urna e ``sq`` o sequencial do TSE, que dá nome ao arquivo da foto.
    ``eleito`` e ``segundo_turno`` derivam de ``situacao``.
    """

    numero: str
    sq: str | None
    nome: str
    nome_urna: str
    partido: str | None
    agremiacao: str | None
    composicao: str | None
    votos: int
    pct_validos: float | None
    situacao: str                    # como o TSE publica: "Eleito", "2º turno", "Não eleito", ""
    eleito: bool
    segundo_turno: bool
    destinacao: str | None           # "Válido", "Anulado", "Anulado sub judice"...; None quando a fonte não informa
    vice: str | None = None
    sigla_federacao: str | None = None
    # Falso quando o candidato não tinha número de urna (eleições até os anos 1980): o ``numero``
    # é então só um identificador estável gerado pelo Lumen, que a tela não exibe.
    numero_publicado: bool = True

    @property
    def valido(self) -> bool:
        """Voto conta como válido. Sem destinação informada (dados abertos
        anteriores a 2016), a fonte não distingue: conta como válido e o feed
        registra o aviso."""
        return self.destinacao is None or self.destinacao.lower().startswith("válido")


@dataclass
class Agremiacao:
    """Partido isolado, coligação ou federação pela qual os candidatos concorrem, com os votos somados e as
    vagas, quando a fonte informa."""

    nome: str
    tipo: str                        # isolado, coligação, federação
    composicao: str | None
    votos: int
    vagas: int | None


@dataclass
class Totalizacao:
    """Progresso da totalização numa abrangência: seções totalizadas sobre o total e se ela terminou.

    ``matematicamente_definida`` reproduz o sinal ``md`` do TSE (o resultado não muda mais, mesmo com
    seções por totalizar); fica None quando a fonte não o publica.
    """

    secoes: int | None
    secoes_totalizadas: int | None
    pct_secoes: float | None
    finalizada: bool
    andamento: str | None            # "f" finalizada, "p" parcial, "n" não iniciada (siglas do TSE)
    matematicamente_definida: bool | None = None


@dataclass
class Comparecimento:
    """Eleitorado, comparecimento e abstenção de uma abrangência, em números absolutos e percentuais.

    ``eleitorado_secoes_nao_instaladas`` são os eleitores das seções que não funcionaram: contam no eleitorado,
    mas nem no comparecimento nem na abstenção (o sistema de resultados publica; os dados abertos, não).
    """

    eleitorado: int | None
    comparecimento: int | None
    abstencao: int | None
    pct_comparecimento: float | None
    pct_abstencao: float | None
    eleitorado_secoes_nao_instaladas: int | None = None


@dataclass
class Votos:
    """Votos válidos, brancos, nulos e anulados de uma abrangência, com os percentuais.

    ``legenda`` são os votos dados só ao partido, nos cargos proporcionais. ``nulos`` é o total de nulos, e
    ``nulos_tecnicos`` a parte dele que o TSE separa como nulo técnico, quando a fonte publica.
    """

    validos: int | None
    brancos: int | None
    nulos: int | None
    anulados: int | None
    legenda: int | None = None
    pct_validos: float | None = None
    pct_brancos: float | None = None
    pct_nulos: float | None = None
    nulos_tecnicos: int | None = None


@dataclass
class ResultadoAbrangencia:
    """Resultado de um cargo numa abrangência (Brasil, UF, exterior ou município), seja qual for a fonte.

    É o formato comum em que ``tse.ler_resultado`` e o agregador dos dados abertos entregam o que leram,
    e de onde os feeds são montados.
    """

    eleicao_tse: int | None
    cargo: int
    vagas: int | None
    abrangencia_tipo: str            # br, uf, zz (exterior), mu
    abrangencia_codigo: str          # "br", "sp", código TSE do município
    atualizado_em: datetime | None
    totalizacao: Totalizacao
    comparecimento: Comparecimento
    votos: Votos
    candidatos: list[Candidato]
    agremiacoes: list[Agremiacao] = field(default_factory=list)
    quociente_eleitoral: int | None = None
    avisos: list[str] = field(default_factory=list)
    # Votação de cada partido (nominal + legenda), quando a fonte publica.
    # O sistema de resultados publica (``par.tvtn``); os dados abertos de
    # votação nominal não trazem a legenda por partido.
    votos_partido: dict[str, int] = field(default_factory=dict)

    @property
    def lider(self) -> Candidato | None:
        """Mais votado entre os votos válidos; sem nenhum válido, o primeiro da lista."""
        validos = [c for c in self.candidatos if c.valido]
        return validos[0] if validos else (self.candidatos[0] if self.candidatos else None)

    @property
    def segundo(self) -> Candidato | None:
        """Segundo mais votado entre os votos válidos; None se não houver."""
        validos = [c for c in self.candidatos if c.valido]
        return validos[1] if len(validos) > 1 else None


@dataclass(frozen=True)
class MunicipioTse:
    """Município como o TSE o cadastra (``mun-e<eleição>-cm.json``): códigos TSE e IBGE, nome como
    publicado (em maiúsculas), se é capital e as zonas eleitorais."""

    uf: str                          # minúsculas, como o TSE ("sp", "zz")
    codigo_tse: str
    codigo_ibge: str | None          # vazio no exterior
    nome: str
    capital: bool
    zonas: tuple[str, ...]


@dataclass(frozen=True)
class AndamentoAbrangencia:
    """Linha dos arquivos ``-ab``: em que pé está a totalização de cada lugar."""

    tipo: str                        # uf ou mun
    codigo: str
    andamento: str | None
    atualizado_em: datetime | None
    pct_secoes: float | None
    secoes_totalizadas: int | None
    secoes: int | None
