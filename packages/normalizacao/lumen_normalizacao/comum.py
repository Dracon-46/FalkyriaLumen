"""Peças comuns a todos os normalizadores: contexto de proveniência, conversão
de campo com quarentena e o laço que percorre uma lista de registros.

O laço isola cada registro: um registro com problema vai para a quarentena,
com campo, motivo e posição, e o resto do artefato segue (RF-NO-08).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Callable

from . import qualidade as q
from .qualidade import EntradaQuarentena, RegistroRejeitado, ResultadoNormalizacao
from .transformacoes import ValorIlegivel, ler_json


class Contexto:
    """Proveniência e data de referência compartilhadas pelos registros de um mesmo artefato.

    ``hoje`` é a data contra a qual se avalia a plausibilidade das datas; quando nula, as transformações
    usam a data corrente.
    """

    def __init__(self, fonte_id: str, documento_fonte_id: str, hoje: date | None):
        """Guarda a fonte, o artefato do bronze de origem e a data de referência."""
        self.fonte_id = fonte_id
        self.documento_fonte_id = documento_fonte_id
        self.hoje = hoje

    def prov(self) -> dict:
        """Campos de proveniência (``fonte_id``, ``documento_fonte_id``), prontos para expandir no registro."""
        return {"fonte_id": self.fonte_id, "documento_fonte_id": self.documento_fonte_id}


def obrigatorio(dados: dict, campo: str) -> Any:
    """Valor do campo, ou ``RegistroRejeitado`` se ele estiver ausente, nulo ou só com espaços.

    Campo obrigatório faltando manda o registro inteiro para a quarentena, em vez de criar um registro
    incompleto.
    """
    valor = dados.get(campo)
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        raise RegistroRejeitado("campo obrigatório ausente", campo)
    return valor


def converter(fn: Callable, dados: dict, campo: str, **kw) -> Any:
    """Aplica a transformação ``fn`` ao campo e traduz ``ValorIlegivel`` em ``RegistroRejeitado``.

    Assim a quarentena registra qual campo falhou e o valor recebido, e não só a mensagem de erro.
    """
    try:
        return fn(dados.get(campo), **kw)
    except ValorIlegivel as erro:
        raise RegistroRejeitado(str(erro), campo, dados.get(campo)) from erro


def nao_negativo(valor: Decimal | None, campo: str) -> Decimal | None:
    """Deixa passar o valor nulo ou não negativo; valor negativo rejeita o registro para a quarentena."""
    if valor is not None and valor < 0:
        raise RegistroRejeitado("valor negativo", campo, valor)
    return valor


def processar_lista(
    conteudo: bytes,
    ctx: Contexto,
    extrator: Callable[[dict], list],
    chave: Callable[[dict], str | None],
    *,
    paginado: bool,
    lista_em: str | None = None,
) -> ResultadoNormalizacao:
    """Percorre os registros do artefato.

    ``paginado``: resposta do PNCP com a lista em ``data``. ``lista_em``:
    nome da chave que contém a lista (o ORDS do SICONFI usa ``items``).
    Nenhum dos dois: a resposta é a própria lista, ou um objeto único.
    """
    resultado = ResultadoNormalizacao()
    if not conteudo or not conteudo.strip():
        return resultado  # 204: nada publicado nesta página
    try:
        corpo = ler_json(conteudo)
    except ValueError as erro:
        resultado.quarentena.append(EntradaQuarentena(
            fonte_id=ctx.fonte_id, documento_fonte_id=ctx.documento_fonte_id,
            chave_origem=None, posicao=None, motivo=f"JSON ilegível: {erro}",
            campo=None, valor_recebido=q.resumir_valor(conteudo[:200]),
        ))
        return resultado
    if paginado:
        lista_em = "data"
    if lista_em:
        if not isinstance(corpo, dict) or lista_em not in corpo:
            resultado.quarentena.append(EntradaQuarentena(
                fonte_id=ctx.fonte_id, documento_fonte_id=ctx.documento_fonte_id,
                chave_origem=None, posicao=None,
                motivo=f"resposta sem a lista '{lista_em}' (provável resposta de erro)",
                campo=None, valor_recebido=q.resumir_valor(corpo),
            ))
            return resultado
        itens = corpo.get(lista_em) or []
    else:
        itens = corpo if isinstance(corpo, list) else [corpo]
    for posicao, item in enumerate(itens):
        resultado.lidos += 1
        try:
            resultado.registros.extend(extrator(item))
        except RegistroRejeitado as rej:
            resultado.quarentena.append(EntradaQuarentena(
                fonte_id=ctx.fonte_id,
                documento_fonte_id=ctx.documento_fonte_id,
                chave_origem=chave(item) if isinstance(item, dict) else None,
                posicao=posicao,
                motivo=rej.motivo,
                campo=rej.campo,
                valor_recebido=q.resumir_valor(rej.valor),
            ))
    return resultado


