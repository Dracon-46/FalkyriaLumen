"""Indício: a entidade que concentra o maior risco do projeto.

O indício é a interpretação do sistema sobre um fato administrativo (DOC-05,
princípio 3). Por isso ele vive separado do fato e carrega, sempre, a regra que
o produziu, os parâmetros, os valores observados e a evidência.

Este módulo impõe no domínio as regras de publicação do DOC-08 e a ADR-008.
Elas não dependem de disciplina de quem escreve a interface: uma transição
proibida simplesmente não acontece.

Regras impostas aqui
--------------------
- Só as transições da máquina de estados do DOC-05, seção 4, são permitidas.
- Severidade baixa nunca entra na fila de revisão nem é publicada (DOC-07).
- Publicar exige ao menos um documento de evidência (RN-02, PUB-03, PUB-04).
- Severidade média exige um revisor; severidade alta exige dois revisores
  *distintos* (PUB-05). Aprovar duas vezes com a mesma pessoa não conta.
- Toda decisão humana registra autor e justificativa (RN-04). O histórico é
  somente-anexação dentro da entidade; o repositório garante o mesmo na
  persistência.
- Marcar como contestado é automático e dispensa análise de mérito (RN-05):
  a assimetria em favor de quem contesta é deliberada (DOC-08, seção 6.2).

Por que a explicação não é verificada aqui contra o vocabulário controlado
---------------------------------------------------------------------------
A explicação de um indício é um *modelo* do projeto preenchido com *dados*.
O modelo é nosso e é verificado na integração contínua, porque vive nos
arquivos de regra. Os dados não são nossos: uma empresa pode se chamar
literalmente "Fraude Zero Ltda", e bloquear o indício por isso seria censurar
o nome publicado pelo próprio ente. Verificar o texto já renderizado misturaria
as duas coisas. A verificação correta é a do modelo, antes de interpolar.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Mapping

from . import rotulos

AUTOR_SISTEMA = "sistema"


class Estado(str, Enum):
    DETECTADO = "detectado"
    EM_REVISAO = "em_revisao"
    AGUARDANDO_DADO = "aguardando_dado"
    DESCARTADO = "descartado"
    PUBLICADO = "publicado"
    CONTESTADO = "contestado"
    PUBLICADO_COM_RESPOSTA = "publicado_com_resposta"
    RETIFICADO = "retificado"
    REMOVIDO = "removido"
    ENCERRADO = "encerrado"


class Severidade(str, Enum):
    BAIXA = "baixa"
    MEDIA = "media"
    ALTA = "alta"

    @property
    def revisores_exigidos(self) -> int:
        return {Severidade.BAIXA: 0, Severidade.MEDIA: 1, Severidade.ALTA: 2}[self]


# Limiares da versão 1 do DOC-07, seção 13. São metodológicos, não legais, e
# migram para o catálogo versionado de regras quando o motor existir.
LIMIAR_MEDIA = Decimal("0.45")
LIMIAR_ALTA = Decimal("0.70")


def classificar_severidade(score: Decimal) -> Severidade:
    """menor que 0,45 → baixa; de 0,45 a 0,70 → média; acima de 0,70 → alta."""
    score = Decimal(score)
    if not (Decimal(0) <= score <= Decimal(1)):
        raise ValueError(f"score precisa estar entre 0 e 1, recebido {score}")
    if score < LIMIAR_MEDIA:
        return Severidade.BAIXA
    if score <= LIMIAR_ALTA:
        return Severidade.MEDIA
    return Severidade.ALTA


TRANSICOES: dict[Estado, frozenset[Estado]] = {
    Estado.DETECTADO: frozenset({Estado.EM_REVISAO, Estado.DESCARTADO}),
    Estado.EM_REVISAO: frozenset({Estado.PUBLICADO, Estado.DESCARTADO, Estado.AGUARDANDO_DADO}),
    Estado.AGUARDANDO_DADO: frozenset({Estado.EM_REVISAO, Estado.DESCARTADO}),
    Estado.PUBLICADO: frozenset({Estado.CONTESTADO, Estado.ENCERRADO}),
    Estado.CONTESTADO: frozenset({Estado.PUBLICADO_COM_RESPOSTA, Estado.RETIFICADO, Estado.REMOVIDO}),
    Estado.PUBLICADO_COM_RESPOSTA: frozenset({Estado.ENCERRADO}),
    Estado.RETIFICADO: frozenset({Estado.PUBLICADO}),
    Estado.DESCARTADO: frozenset(),
    Estado.REMOVIDO: frozenset(),
    Estado.ENCERRADO: frozenset(),
}

ESTADOS_TERMINAIS = frozenset(e for e, destinos in TRANSICOES.items() if not destinos)

_ROTULOS_PUBLICOS: dict[Estado, str] = {
    Estado.PUBLICADO: rotulos.ATIVIDADE_PARA_ANALISE,
    Estado.CONTESTADO: rotulos.ROTULO_CONTESTADO,
    Estado.PUBLICADO_COM_RESPOSTA: rotulos.ROTULO_COM_RESPOSTA,
    Estado.RETIFICADO: rotulos.ROTULO_RETIFICADO,
    Estado.ENCERRADO: rotulos.ROTULO_ENCERRADO,
    Estado.REMOVIDO: rotulos.ROTULO_REMOVIDO,
}


class TransicaoInvalida(Exception):
    """A mudança de estado pedida viola a máquina de estados ou uma regra de publicação."""


@dataclass(frozen=True)
class Transicao:
    de: Estado
    para: Estado
    autor: str
    justificativa: str
    em: str  # ISO 8601 UTC


@dataclass
class Indicio:
    indicio_id: str
    regra_codigo: str
    regra_versao: int
    ente_id: str
    alvo_tipo: str
    alvo_id: str
    score: Decimal
    parametros_aplicados: Mapping[str, object]
    valores_observados: Mapping[str, object]
    explicacao: str
    evidencias: tuple[str, ...] = ()          # ids de registros da camada bronze
    detectado_em: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    estado: Estado = Estado.DETECTADO
    aprovacoes: tuple[str, ...] = ()
    protocolo_contestacao: str | None = None
    historico: tuple[Transicao, ...] = ()

    def __post_init__(self) -> None:
        self.score = Decimal(self.score)
        self.severidade  # valida o intervalo do score já na criação
        if not self.regra_codigo or self.regra_versao < 1:
            raise ValueError("indício precisa da regra e da versão que o produziram (RF-DE-02)")
        if not self.valores_observados:
            raise ValueError("indício precisa dos valores observados que o dispararam (RF-DE-03)")

    # ---------------------------------------------------------------- consulta

    @property
    def severidade(self) -> Severidade:
        return classificar_severidade(self.score)

    @property
    def terminal(self) -> bool:
        return self.estado in ESTADOS_TERMINAIS

    @property
    def rotulo_publico(self) -> str | None:
        """Rótulo exibido ao público, ou None se o indício não é público."""
        return _ROTULOS_PUBLICOS.get(self.estado)

    @property
    def visivel_ao_publico(self) -> bool:
        return self.rotulo_publico is not None

    # ---------------------------------------------------------------- mecânica

    def _transitar(self, para: Estado, autor: str, justificativa: str) -> None:
        if para not in TRANSICOES[self.estado]:
            raise TransicaoInvalida(f"{self.estado.value} → {para.value} não é permitido")
        if not autor or not autor.strip():
            raise TransicaoInvalida("toda decisão registra o autor (RN-04)")
        if not justificativa or not justificativa.strip():
            raise TransicaoInvalida("toda decisão registra a justificativa (RN-04)")
        self.historico = self.historico + (Transicao(
            de=self.estado,
            para=para,
            autor=autor.strip(),
            justificativa=justificativa.strip(),
            em=datetime.now(timezone.utc).isoformat(),
        ),)
        self.estado = para

    def anexar_evidencia(self, registro_id: str) -> None:
        if self.terminal:
            raise TransicaoInvalida("indício encerrado não recebe nova evidência")
        if registro_id not in self.evidencias:
            self.evidencias = self.evidencias + (registro_id,)

    # ---------------------------------------------------------------- fluxo

    def enviar_para_revisao(self, justificativa: str = "score acima do limiar de publicação") -> None:
        if self.severidade is Severidade.BAIXA:
            raise TransicaoInvalida(
                "severidade baixa não entra na fila de revisão: alimenta apenas "
                "estatística e priorização interna (DOC-07, seção 13)"
            )
        self._transitar(Estado.EM_REVISAO, AUTOR_SISTEMA, justificativa)

    def descartar(self, autor: str, justificativa: str) -> None:
        """Descarte com motivo registrado: realimenta a calibração da regra."""
        self._transitar(Estado.DESCARTADO, autor, justificativa)

    def aguardar_dado(self, autor: str, justificativa: str) -> None:
        self._transitar(Estado.AGUARDANDO_DADO, autor, justificativa)

    def retomar_revisao(self, justificativa: str = "nova coleta disponível") -> None:
        self._transitar(Estado.EM_REVISAO, AUTOR_SISTEMA, justificativa)

    def aprovar(self, revisor: str) -> None:
        """Registra a aprovação de um revisor. Não publica sozinho."""
        if self.estado is not Estado.EM_REVISAO:
            raise TransicaoInvalida("só é possível aprovar indício em revisão")
        revisor = (revisor or "").strip()
        if not revisor or revisor == AUTOR_SISTEMA:
            raise TransicaoInvalida("aprovação exige um revisor humano identificado")
        if revisor not in self.aprovacoes:
            self.aprovacoes = self.aprovacoes + (revisor,)

    def publicar(self, autor: str, justificativa: str) -> None:
        if self.severidade is Severidade.BAIXA:
            raise TransicaoInvalida("severidade baixa nunca é publicada (DOC-07)")
        if not self.evidencias:
            raise TransicaoInvalida(
                "sem documento fonte não há indício: publicar exige evidência (RN-02)"
            )
        exigidos = self.severidade.revisores_exigidos
        if len(self.aprovacoes) < exigidos:
            raise TransicaoInvalida(
                f"severidade {self.severidade.value} exige {exigidos} revisor(es) distinto(s); "
                f"há {len(self.aprovacoes)} (PUB-05)"
            )
        self._transitar(Estado.PUBLICADO, autor, justificativa)

    def marcar_contestado(self, protocolo: str) -> None:
        """Automático e imediato, sem análise de mérito (RN-05)."""
        if not protocolo or not protocolo.strip():
            raise TransicaoInvalida("a marcação de contestação exige o protocolo")
        self._transitar(Estado.CONTESTADO, AUTOR_SISTEMA, f"contestação registrada sob protocolo {protocolo}")
        self.protocolo_contestacao = protocolo.strip()

    def manter_com_resposta(self, autor: str, justificativa: str) -> None:
        self._transitar(Estado.PUBLICADO_COM_RESPOSTA, autor, justificativa)

    def retificar(self, autor: str, justificativa: str) -> None:
        """Erro de coleta ou cálculo do Lumen comprovado."""
        self._transitar(Estado.RETIFICADO, autor, justificativa)

    def republicar_retificado(self, autor: str, justificativa: str) -> None:
        if not self.evidencias:
            raise TransicaoInvalida("republicar exige evidência (RN-02)")
        self._transitar(Estado.PUBLICADO, autor, justificativa)

    def remover(self, autor: str, justificativa: str) -> None:
        """O dado publicado pela própria fonte estava incorreto."""
        self._transitar(Estado.REMOVIDO, autor, justificativa)

    def encerrar(self, autor: str, justificativa: str) -> None:
        """Órgão de controle concluiu a análise."""
        self._transitar(Estado.ENCERRADO, autor, justificativa)
