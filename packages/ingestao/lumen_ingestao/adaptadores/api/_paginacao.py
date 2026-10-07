"""Peças comuns aos adaptadores de API: dias da janela, cache da página 1, URLs."""

from __future__ import annotations

import json
import urllib.parse
from datetime import date, timedelta
from typing import Iterator, Mapping

from ...bronze import ArtefatoBruto
from ...portas import Janela


def dias(janela: Janela) -> Iterator[date]:
    """Cada data da janela, de ``inicio`` a ``fim``, inclusive."""
    d = janela.inicio
    while d <= janela.fim:
        yield d
        d += timedelta(days=1)


def montar_url(base: str, caminho: str, parametros: Mapping[str, object]) -> str:
    """Junta base, caminho e consulta numa URL, omitindo os parâmetros ``None``."""
    # Ordem fixa dos parâmetros: a mesma consulta gera sempre a mesma URL, e o
    # índice de versões do bronze (por URL) reconhece a recoleta.
    consulta = urllib.parse.urlencode([(k, str(v)) for k, v in parametros.items() if v is not None])
    return f"{base.rstrip('/')}/{caminho.lstrip('/')}" + (f"?{consulta}" if consulta else "")


def total_paginas(artefato: ArtefatoBruto, campo: str = "totalPaginas") -> int:
    """Quantas páginas a resposta anuncia. 204 e erro valem como uma página só.

    Uma resposta de erro é guardada como prova mas não se expande: não há
    como saber quantas páginas existiriam.
    """
    if artefato.status_http != 200 or not artefato.conteudo.strip():
        return 1
    try:
        corpo = json.loads(artefato.conteudo.decode("utf-8-sig"))
    except (ValueError, UnicodeDecodeError):
        return 1
    if isinstance(corpo, dict):
        try:
            return max(1, int(corpo.get(campo) or 1))
        except (TypeError, ValueError):
            return 1
    return 1


class CacheDePlanejamento:
    """Guarda as páginas já baixadas para planejar a listagem.

    Para saber quantas páginas uma consulta tem, é preciso baixar a primeira.
    Baixá-la de novo em ``baixar`` gastaria cota da fonte à toa (princípio P6).
    A listagem guarda o artefato aqui e ``baixar`` o devolve, uma única vez.
    """

    def __init__(self) -> None:
        """Começa sem nenhuma página guardada."""
        self._por_url: dict[str, ArtefatoBruto] = {}

    def guardar(self, url: str, artefato: ArtefatoBruto) -> None:
        """Guarda a página já baixada, indexada pela URL."""
        self._por_url[url] = artefato

    def retirar(self, url: str) -> ArtefatoBruto | None:
        """Devolve e remove a página da URL, ou ``None``: cada página guardada é entregue uma vez só."""
        return self._por_url.pop(url, None)

    def __len__(self) -> int:
        """Quantidade de páginas guardadas e ainda não retiradas."""
        return len(self._por_url)
