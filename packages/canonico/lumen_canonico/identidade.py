"""Identificadores determinísticos do esquema canônico.

A normalização precisa ser idempotente (RF-NO-11): reprocessar o mesmo
artefato bruto produz exatamente o mesmo resultado, inclusive os
identificadores. Um ``uuid4`` gerado na normalização quebraria isso — o mesmo
contrato ganharia um id novo a cada reprocessamento, e todo indício que o
referenciasse ficaria órfão.

Por isso o id de qualquer registro de fato é um UUID versão 5, derivado de um
espaço de nomes fixo do projeto e da chave natural do registro. A mesma chave
gera sempre o mesmo id, em qualquer máquina, em qualquer ano.

O espaço de nomes abaixo é permanente. Trocá-lo invalida todos os ids já
emitidos: não troque.
"""

from __future__ import annotations

import uuid

NAMESPACE_LUMEN = uuid.UUID("6f1d3a52-6b0e-5c1e-9a57-4c756d656e00")


def _normalizar_parte(parte: object) -> str:
    """Converte uma parte da chave natural em texto sem espaços nas pontas.

    Parte nula ou vazia é recusada com ``ValueError``: uma chave incompleta daria o mesmo id a registros
    diferentes.
    """
    if parte is None:
        raise ValueError("chave natural não pode ter parte nula: o id deixaria de ser único")
    texto = str(parte).strip()
    if not texto:
        raise ValueError("chave natural não pode ter parte vazia")
    return texto


def id_canonico(entidade: str, *chave_natural: object) -> str:
    """UUID v5 em texto, a partir do nome da entidade e da chave natural.

    O nome da entidade entra na derivação para que duas entidades com a mesma
    chave natural (um processo e o contrato que herdou o mesmo número, por
    exemplo) nunca colidam.
    """
    if not chave_natural:
        raise ValueError("informe ao menos uma parte da chave natural")
    partes = [_normalizar_parte(entidade)] + [_normalizar_parte(p) for p in chave_natural]
    return str(uuid.uuid5(NAMESPACE_LUMEN, "\x1f".join(partes)))
