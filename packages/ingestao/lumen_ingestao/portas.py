"""Porta FonteDados: o único ponto de contato com qualquer fonte externa.

DOC-04, seção 3.1. Cada uma das milhares de fontes do projeto tem formato,
protocolo e qualidade próprios. Para que essa variabilidade não contamine o
resto do sistema, toda fonte é acessada por esta porta, e cada família de
fonte é um adaptador que a implementa. O núcleo nunca sabe se um contrato
veio de uma API REST, de uma planilha ou de um PDF digitalizado.

O contrato é deliberadamente pequeno: quatro operações bastam para todos os
casos. Em particular, ``reportar_conformidade`` fica na porta porque só o
adaptador sabe distinguir uma indisponibilidade passageira de uma ausência
persistente de publicação — ele é quem conhece o comportamento normal daquela
fonte.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from typing import Iterator, Mapping, Protocol, runtime_checkable

from .bronze import (
    ArmazemBronze,
    ArtefatoBruto,
    IntegridadeViolada,
    RegistroColeta,
    validar_fonte_id,
)


class Periodicidade(str, Enum):
    """Frequência com que a fonte publica dados novos, declarada em ``CapacidadesFonte``."""

    TEMPO_REAL = "tempo_real"
    DIARIA = "diaria"
    SEMANAL = "semanal"
    MENSAL = "mensal"
    BIMESTRAL = "bimestral"
    ANUAL = "anual"


@dataclass(frozen=True)
class Janela:
    """Intervalo de datas a coletar, com as duas pontas inclusivas."""

    inicio: date
    fim: date

    def __post_init__(self) -> None:
        """Recusa janela invertida (``fim`` antes de ``inicio``)."""
        if self.fim < self.inicio:
            raise ValueError(f"janela invertida: {self.inicio} a {self.fim}")

    @property
    def dias(self) -> int:
        """Quantidade de dias da janela, contando as duas pontas."""
        return (self.fim - self.inicio).days + 1


@dataclass(frozen=True)
class CapacidadesFonte:
    """O que a fonte oferece. O orquestrador monta o plano a partir disto."""

    objetos: frozenset[str]
    periodicidade: Periodicidade
    suporta_incremental: bool
    limite_requisicoes_por_minuto: int
    exige_autenticacao: bool = False

    def __post_init__(self) -> None:
        """Exige ao menos um objeto canônico e um limite de taxa positivo.

        Sem limite declarado não há como coletar a fonte de forma responsável (princípio P6).
        """
        if not self.objetos:
            raise ValueError("uma fonte precisa declarar ao menos um objeto canônico")
        if self.limite_requisicoes_por_minuto < 1:
            raise ValueError("limite de taxa precisa ser positivo (princípio P6)")


@dataclass(frozen=True)
class ReferenciaArtefato:
    """O que existe na fonte, antes de baixar. Permite planejar o volume."""

    url: str
    objeto: str
    chave_origem: str | None = None
    metadados: Mapping[str, str] = field(default_factory=dict)


class ResultadoCriterio(str, Enum):
    """Resultado da avaliação de um critério de conformidade.

    ``INDETERMINADO`` é para quando não foi possível avaliar, e sempre vem com o
    motivo (ver ``AvaliacaoConformidade``).
    """

    CUMPRE = "cumpre"
    CUMPRE_PARCIALMENTE = "cumpre_parcialmente"
    NAO_CUMPRE = "nao_cumpre"
    INDETERMINADO = "indeterminado"


@dataclass(frozen=True)
class AvaliacaoConformidade:
    """Avaliação de um critério de conformidade, amarrada ao dispositivo legal que o fundamenta."""

    criterio: str
    dispositivo_legal: str
    resultado: ResultadoCriterio
    motivo_indeterminado: str | None = None

    def __post_init__(self) -> None:
        """Exige o dispositivo legal, e o motivo quando, e só quando, o resultado é indeterminado.

        Sem dispositivo a obrigação avaliada fica sem base (RF-CF-06); sem motivo, um
        "indeterminado" poderia atribuir ao ente uma falha que foi da fonte ou do próprio
        sistema (RF-CF-07).
        """
        if not self.dispositivo_legal.strip():
            raise ValueError("toda obrigação avaliada precisa citar o dispositivo legal (RF-CF-06)")
        indeterminado = self.resultado is ResultadoCriterio.INDETERMINADO
        if indeterminado and not (self.motivo_indeterminado or "").strip():
            # RF-CF-07: sem motivo, "indeterminado" viraria uma forma disfarçada
            # de atribuir falha ao ente quando o problema pode ser nosso.
            raise ValueError("resultado indeterminado exige o motivo")
        if not indeterminado and self.motivo_indeterminado:
            raise ValueError("motivo_indeterminado só se aplica ao resultado indeterminado")


@dataclass(frozen=True)
class RelatorioConformidade:
    """Avaliações que o adaptador reporta sobre a fonte, com o instante da avaliação em UTC."""

    fonte_id: str
    avaliacoes: tuple[AvaliacaoConformidade, ...]
    avaliado_em: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@runtime_checkable
class FonteDados(Protocol):
    """Porta única de acesso a qualquer fonte de dado público."""

    fonte_id: str

    def descrever_capacidades(self) -> CapacidadesFonte:
        """Declara os objetos, a periodicidade e o limite de taxa da fonte."""

    def listar(self, janela: Janela) -> Iterator[ReferenciaArtefato]:
        """Enumera o que a fonte oferece na janela, para planejar o volume antes de baixar."""

    def baixar(self, ref: ReferenciaArtefato) -> ArtefatoBruto:
        """Baixa o artefato referenciado, exatamente como a fonte o entregou."""

    def reportar_conformidade(self) -> RelatorioConformidade:
        """Relata o que o adaptador observou sobre a fonte.

        É o adaptador quem distingue indisponibilidade passageira de ausência
        persistente de publicação (ver o módulo).
        """


# --------------------------------------------------------------------------
# O laço que todo conector executa
# --------------------------------------------------------------------------

@dataclass
class ResumoColeta:
    """Resultado de ``coletar_janela``: quantos artefatos foram listados, os registros guardados e as falhas."""

    fonte_id: str
    janela: Janela
    listados: int = 0
    guardados: list[RegistroColeta] = field(default_factory=list)
    falhas: list[tuple[str, str]] = field(default_factory=list)  # (url, erro)

    @property
    def conteudos_novos(self) -> int:
        """Registros cujo conteúdo é inédito para a URL: primeira coleta ou mudança desde a anterior."""
        return sum(1 for r in self.guardados if r.mudou_desde_anterior)

    @property
    def respostas_de_erro(self) -> int:
        """Respostas 4xx/5xx preservadas como prova (princípio P5)."""
        return sum(1 for r in self.guardados if r.status_http >= 400)


def coletar_janela(fonte: FonteDados, janela: Janela, armazem: ArmazemBronze) -> ResumoColeta:
    """Lista, baixa e preserva tudo o que a fonte oferece na janela.

    Uma falha em um artefato é registrada e não interrompe os demais (RNF-09,
    em escala de artefato). Uma falha ao listar é propagada: sem a listagem
    não se sabe o que deveria ter sido coletado, e fingir sucesso esconderia
    exatamente o modo de falha mais perigoso do sistema — a fonte que responde
    "tudo certo" com zero registros (DOC-04, seção 8).
    """
    validar_fonte_id(fonte.fonte_id)
    resumo = ResumoColeta(fonte_id=fonte.fonte_id, janela=janela)
    for ref in fonte.listar(janela):
        resumo.listados += 1
        try:
            artefato = fonte.baixar(ref)
            if artefato.fonte_id != fonte.fonte_id:
                raise ValueError(
                    f"adaptador devolveu fonte_id {artefato.fonte_id!r}, esperado {fonte.fonte_id!r}"
                )
            resumo.guardados.append(armazem.guardar(artefato))
        except IntegridadeViolada:
            # Prova corrompida não é falha de um artefato: é incidente no
            # armazenamento inteiro. Continuar gravando evidência num
            # armazém possivelmente comprometido seria pior que parar.
            raise
        except Exception as erro:  # isolamento deliberado por artefato
            resumo.falhas.append((ref.url, f"{type(erro).__name__}: {erro}"))
    return resumo
