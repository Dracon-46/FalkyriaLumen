"""Referência de mercado: a distribuição de preços que serve de régua para um item (ADR-027, seção 4).

Uma referência guarda a distribuição inteira (mínimo, quartis, mediana, máximo e quantidade), não só a
média: quem analisar precisa ver se o preço pago está um pouco acima do terceiro quartil ou acima do maior
preço encontrado, e com quantas observações. A régua da regra A-05 é a mediana, que um preço fora da curva
não desloca.

Quantis pelo método linear (o mesmo do ``numpy.percentile`` padrão e do ``quantile_cont`` do DuckDB), em
``Decimal`` para não passar dinheiro por ``float``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Iterable

CENTAVO_MILESIMO = Decimal("0.001")


def quantil(valores: list[Decimal], q: Decimal | str) -> Decimal:
    """Quantil ``q`` (entre 0 e 1) de valores já ordenados, por interpolação linear entre vizinhos."""
    if not valores:
        raise ValueError("quantil de lista vazia")
    q = Decimal(q)
    if not Decimal(0) <= q <= Decimal(1):
        raise ValueError(f"quantil fora de [0, 1]: {q}")
    posicao = q * (len(valores) - 1)
    baixo = int(posicao)
    alto = min(baixo + 1, len(valores) - 1)
    fracao = posicao - baixo
    return valores[baixo] + (valores[alto] - valores[baixo]) * fracao


@dataclass(frozen=True)
class Evidencia:
    """Uma observação de mercado que entrou na referência, para quem quiser conferir.

    Na ANP é o posto (CNPJ da revenda e data da coleta); no varejo é a oferta, com o endereço e a data e hora
    do acesso, como pede a Lei 14.133 para sítios eletrônicos (art. 23, § 1º, III).
    """

    descricao: str
    valor: Decimal
    data: str
    endereco: str | None = None


@dataclass(frozen=True)
class ReferenciaMercado:
    """Distribuição de preços de mercado de um produto, num lugar e num período.

    ``escopo`` diz de onde vieram as observações (``municipio``, ``uf`` ou ``brasil``); ``periodo`` é o
    intervalo das datas de coleta usadas; ``fonte`` é ``anp`` ou o identificador da loja.
    """

    fonte: str
    produto: str
    escopo: str
    local: str
    periodo: tuple[date, date]
    unidade: str
    quantidade: int
    minimo: Decimal
    p25: Decimal
    mediana: Decimal
    p75: Decimal
    maximo: Decimal
    evidencias: tuple[Evidencia, ...] = field(default=())

    @classmethod
    def de_valores(cls, valores: Iterable[Decimal], *, fonte: str, produto: str, escopo: str, local: str,
                   periodo: tuple[date, date], unidade: str,
                   evidencias: Iterable[Evidencia] = ()) -> "ReferenciaMercado":
        """Monta a referência a partir dos valores observados (ao menos um), arredondando a milésimos."""
        ordenados = sorted(Decimal(v) for v in valores)
        if not ordenados:
            raise ValueError("referência de mercado sem nenhuma observação")

        def r(v: Decimal) -> Decimal:
            return v.quantize(CENTAVO_MILESIMO, rounding=ROUND_HALF_EVEN)
        return cls(fonte=fonte, produto=produto, escopo=escopo, local=local, periodo=periodo, unidade=unidade,
                   quantidade=len(ordenados), minimo=r(ordenados[0]), p25=r(quantil(ordenados, "0.25")),
                   mediana=r(quantil(ordenados, "0.5")), p75=r(quantil(ordenados, "0.75")),
                   maximo=r(ordenados[-1]), evidencias=tuple(evidencias))

    def para_dict(self) -> dict:
        """Forma serializável (valores em texto, datas em ISO 8601), sem as evidências."""
        return {
            "fonte": self.fonte, "produto": self.produto, "escopo": self.escopo, "local": self.local,
            "periodo": [self.periodo[0].isoformat(), self.periodo[1].isoformat()], "unidade": self.unidade,
            "quantidade": self.quantidade, "minimo": str(self.minimo), "p25": str(self.p25),
            "mediana": str(self.mediana), "p75": str(self.p75), "maximo": str(self.maximo),
        }
