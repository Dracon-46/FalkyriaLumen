"""Regras de qualidade da transição bronze → silver (DOC-05, seção 6).

Duas saídas possíveis para um registro com problema, e a escolha entre elas é
o que este módulo padroniza:

- **Quarentena**: o registro não segue para a silver. Acontece quando falta
  campo obrigatório, quando um valor é ilegível ou quando a data é
  implausível. O motivo fica registrado, com o campo e o valor recebido, e o
  lote continua (RF-NO-08).
- **Marcação**: o registro segue, com uma etiqueta de qualidade. Acontece
  quando o dado é utilizável mas tem uma ressalva conhecida — esfera "não se
  aplica", valor estimado zerado, CPF que não pôde ser mascarado. As regras de
  detecção leem as marcações para reduzir a confiança do dado
  (``confianca_dado`` do DOC-07, seção 13).

Os códigos de marcação são estáveis: viram filtro em consulta e insumo de
métrica, então não se renomeia um código existente.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


class RegistroRejeitado(Exception):
    """Levantada dentro do normalizador para mandar o registro à quarentena."""

    def __init__(self, motivo: str, campo: str | None = None, valor: Any = None):
        """Guarda o motivo, o campo e o valor recebido que a quarentena vai registrar."""
        super().__init__(motivo)
        self.motivo = motivo
        self.campo = campo
        self.valor = valor


@dataclass(frozen=True)
class EntradaQuarentena:
    """Registro que não seguiu para a silver, com o motivo e o lugar onde estava.

    Identifica a fonte, o artefato, a chave e a posição do registro, o campo e o valor recebido (truncado
    por ``resumir_valor``): o bastante para localizar o problema no bronze sem copiar o registro.
    """

    fonte_id: str
    documento_fonte_id: str
    chave_origem: str | None
    posicao: int | None          # índice do registro dentro do artefato
    motivo: str
    campo: str | None
    valor_recebido: str | None   # truncado: a quarentena não é cópia do bronze

    def para_dict(self) -> dict[str, Any]:
        """Dicionário da entrada, na forma gravada no arquivo de quarentena."""
        return asdict(self)


# Códigos de marcação — estáveis
ESFERA_NAO_INFORMADA = "esfera_nao_informada"
PODER_NAO_INFORMADO = "poder_nao_informado"
ENTE_NAO_RESOLVIDO = "ente_nao_resolvido"
VALOR_ESTIMADO_ZERO = "valor_estimado_zero"
VALOR_HOMOLOGADO_AUSENTE = "valor_homologado_ausente"
DOCUMENTO_FORNECEDOR_INVALIDO = "documento_fornecedor_invalido"
MODALIDADE_DESCONHECIDA = "modalidade_desconhecida"
CNPJ_ORGAO_INVALIDO = "cnpj_orgao_invalido"
VALOR_TOTAL_DIVERGE_ITENS = "valor_total_diverge_itens"
CODIGO_IBGE_AUSENTE = "codigo_ibge_ausente"


def resumir_valor(valor: Any, limite: int = 200) -> str | None:
    """Texto do valor truncado em ``limite`` caracteres (com reticências no fim), ou None.

    A quarentena aponta o problema, não guarda cópia do dado: o registro completo continua no bronze.
    """
    if valor is None:
        return None
    texto = str(valor)
    return texto if len(texto) <= limite else texto[: limite - 1] + "…"


@dataclass
class ResultadoNormalizacao:
    """O que um artefato bruto produziu: registros canônicos e quarentena."""

    registros: list = field(default_factory=list)
    quarentena: list[EntradaQuarentena] = field(default_factory=list)
    lidos: int = 0

    @property
    def aceitos(self) -> int:
        """Registros lidos que não foram para a quarentena."""
        return self.lidos - len(self.quarentena)

    def juntar(self, outro: "ResultadoNormalizacao") -> None:
        """Acumula neste resultado os registros, a quarentena e a contagem de leitura de outro."""
        self.registros.extend(outro.registros)
        self.quarentena.extend(outro.quarentena)
        self.lidos += outro.lidos
