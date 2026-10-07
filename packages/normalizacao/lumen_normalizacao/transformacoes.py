"""Transformações de valor usadas por todos os normalizadores.

Cada função aqui recebe o valor como a fonte entregou e devolve o tipo
canônico, ou ``None`` quando o valor está ausente. Nenhuma delas inventa
valor: ausência continua ausência (DOC-05, princípio 4). Valor presente e
ilegível levanta ``ValorIlegivel``, que o normalizador transforma em
quarentena com o campo e o motivo.
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

# Horário de Brasília sem horário de verão (extinto pelo Decreto 9.772/2019).
# Fixo, e não zoneinfo, porque no Windows o zoneinfo depende do pacote
# tzdata, e a Fase 0 não tem dependências (ADR-015). Para todo o período da
# Lei 14.133 o deslocamento é constante.
BRT = timezone(timedelta(hours=-3), "BRT")

# Datas fora desta faixa são tratadas como erro de digitação da fonte. A ata
# de Jundiaí com vigência até 7203-07-27 é o caso real que motivou o limite.
ANO_MINIMO_PLAUSIVEL = 1988
ANOS_FUTUROS_PLAUSIVEIS = 30


class ValorIlegivel(ValueError):
    """A fonte entregou um valor, mas ele não pode ser interpretado."""


def ler_json(conteudo: bytes) -> Any:
    """JSON com números decimais preservados.

    ``parse_float=Decimal`` faz ``19977.00`` virar ``Decimal('19977.00')``
    direto do texto, sem passar por ``float``. Passar por float e depois
    converter perderia exatidão em valores como 0.1 + 0.2, e a família B
    compara somas com limites legais ao centavo.
    """
    texto = conteudo.decode("utf-8-sig")
    return json.loads(texto, parse_float=Decimal)


def decimal_ou_nulo(valor: Any) -> Decimal | None:
    """Número como ``Decimal``; vazio vira None, e booleano ou texto não numérico levantam ``ValorIlegivel``.

    O booleano é recusado de propósito: em Python ``True`` é inteiro e viraria 1 sem aviso.
    """
    if valor is None or valor == "":
        return None
    if isinstance(valor, bool):
        raise ValorIlegivel(f"booleano onde se esperava número: {valor!r}")
    if isinstance(valor, Decimal):
        return valor
    if isinstance(valor, int):
        return Decimal(valor)
    if isinstance(valor, float):
        # Só chega aqui se alguém ler JSON sem ler_json; str() evita a
        # representação binária completa do float.
        return Decimal(str(valor))
    try:
        return Decimal(str(valor).strip())
    except InvalidOperation as erro:
        raise ValorIlegivel(f"não numérico: {valor!r}") from erro


def moeda_br(valor: str | None) -> Decimal | None:
    """``"R$ 1.234,56"`` → ``Decimal('1234.56')``. Para fontes em texto (HTML, PDF)."""
    if valor is None:
        return None
    texto = str(valor).strip().replace("R$", "").replace(" ", "").strip()
    if not texto:
        return None
    if re.fullmatch(r"-?\d{1,3}(\.\d{3})*(,\d+)?|-?\d+(,\d+)?", texto):
        return Decimal(texto.replace(".", "").replace(",", "."))
    raise ValorIlegivel(f"valor monetário fora do padrão brasileiro: {valor!r}")


def inteiro_ou_nulo(valor: Any) -> int | None:
    """Inteiro a partir de número ou texto; vazio vira None.

    Aceita ``12.0`` e ``"12"``, mas recusa parte fracionária diferente de zero e booleano, em vez de
    truncar ou converter em silêncio.
    """
    if valor is None or valor == "":
        return None
    if isinstance(valor, bool):
        raise ValorIlegivel(f"booleano onde se esperava inteiro: {valor!r}")
    try:
        d = Decimal(str(valor).strip())
    except InvalidOperation as erro:
        raise ValorIlegivel(f"não inteiro: {valor!r}") from erro
    if d != d.to_integral_value():
        raise ValorIlegivel(f"não inteiro: {valor!r}")
    return int(d)


def booleano_ou_nulo(valor: Any) -> bool | None:
    """Booleano a partir de ``true``/``false``, ``t``/``f``, ``s``/``n``, ``sim``/``não`` ou ``1``/``0``, sem
    distinguir caixa.

    Vazio vira None; qualquer outro texto levanta ``ValorIlegivel``.
    """
    if valor is None or valor == "":
        return None
    if isinstance(valor, bool):
        return valor
    texto = str(valor).strip().lower()
    if texto in {"true", "t", "s", "sim", "1"}:
        return True
    if texto in {"false", "f", "n", "nao", "não", "0"}:
        return False
    raise ValorIlegivel(f"não booleano: {valor!r}")


def _checar_ano(d: date, hoje: date | None) -> None:
    """Recusa data antes de ``ANO_MINIMO_PLAUSIVEL`` ou mais de ``ANOS_FUTUROS_PLAUSIVEIS`` anos depois de ``hoje``.

    Datas assim são erro de digitação da fonte (como a vigência até o ano 7203) e distorceriam qualquer
    cálculo de prazo; o registro vai para a quarentena.
    """
    referencia = hoje or date.today()
    if not (ANO_MINIMO_PLAUSIVEL <= d.year <= referencia.year + ANOS_FUTUROS_PLAUSIVEIS):
        raise ValorIlegivel(f"data fora da faixa plausível: {d.isoformat()}")


def data_ou_nula(valor: Any, *, hoje: date | None = None) -> date | None:
    """Aceita ``AAAA-MM-DD``, ``AAAA-MM-DDTHH:MM:SS`` e ``DD/MM/AAAA``."""
    if valor is None or valor == "":
        return None
    texto = str(valor).strip()
    try:
        if re.fullmatch(r"\d{2}/\d{2}/\d{4}", texto):
            d = datetime.strptime(texto, "%d/%m/%Y").date()
        else:
            d = date.fromisoformat(texto[:10])
    except ValueError as erro:
        raise ValorIlegivel(f"data ilegível: {valor!r}") from erro
    _checar_ano(d, hoje)
    return d


def instante_brt_ou_nulo(valor: Any, *, hoje: date | None = None) -> datetime | None:
    """Instante publicado sem fuso, interpretado como horário de Brasília.

    Se a fonte já mandar o fuso (``...-03:00`` ou ``Z``), ele é respeitado.
    """
    if valor is None or valor == "":
        return None
    texto = str(valor).strip().replace("Z", "+00:00")
    try:
        instante = datetime.fromisoformat(texto)
    except ValueError as erro:
        raise ValorIlegivel(f"instante ilegível: {valor!r}") from erro
    if instante.tzinfo is None:
        instante = instante.replace(tzinfo=BRT)
    _checar_ano(instante.date(), hoje)
    return instante


def texto_ou_nulo(valor: Any) -> str | None:
    """Texto como publicado. Só o vazio vira nulo; nada é reescrito."""
    if valor is None:
        return None
    texto = str(valor)
    return texto if texto.strip() else None


def chave_texto(valor: str | None) -> str:
    """Forma normalizada para comparar textos: sem acento, caixa baixa, espaço único.

    Uso exclusivo para comparação e agrupamento. Nunca é a forma armazenada
    ou exibida, que continua sendo o texto publicado.
    """
    if not valor:
        return ""
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFKD", valor) if not unicodedata.combining(c)
    )
    return re.sub(r"\s+", " ", sem_acento).strip().lower()
