"""Base para fontes cuja listagem é uma lista fixa de URLs (cadastros, extratos)."""

from __future__ import annotations

import json
from typing import Iterator

from ...bronze import ArtefatoBruto
from ...cliente_http import ClienteHttp
from ...coleta_http import ErroColeta
from ...portas import (
    AvaliacaoConformidade,
    CapacidadesFonte,
    Janela,
    Periodicidade,
    ReferenciaArtefato,
    RelatorioConformidade,
    ResultadoCriterio,
)
from ._paginacao import CacheDePlanejamento, montar_url


class FonteListaFixa:
    """Base de fonte cuja listagem é uma lista fixa de consultas, uma URL por consulta.

    A subclasse define ``fonte_id``, ``objetos``, ``periodicidade``, ``dispositivo`` e
    ``_consultas``. A base conta as consultas respondidas e as que falharam, que é o
    que ``reportar_conformidade`` relata.
    """

    fonte_id: str
    objetos: frozenset[str]
    periodicidade: Periodicidade = Periodicidade.MENSAL
    dispositivo: str = ""

    def __init__(self, cliente: ClienteHttp, base: str):
        """Confere que o cliente é desta fonte e começa com os contadores zerados."""
        if cliente.fonte_id != self.fonte_id:
            raise ValueError(f"cliente da fonte {cliente.fonte_id!r} usado em {self.fonte_id!r}")
        self.cliente = cliente
        self.base = base
        self._cache = CacheDePlanejamento()
        self.respondidas = 0
        self.falhas = 0

    def descrever_capacidades(self) -> CapacidadesFonte:
        """Capacidades a partir dos atributos da classe, sem coleta incremental; o limite de taxa é o do cliente."""
        return CapacidadesFonte(objetos=self.objetos, periodicidade=self.periodicidade,
                                suporta_incremental=False,
                                limite_requisicoes_por_minuto=self.cliente.limitador.rpm)

    def _consultas(self, janela: Janela) -> Iterator[tuple[str, str, dict, dict]]:
        """(objeto, caminho, parâmetros, metadados) de cada artefato."""
        raise NotImplementedError

    def _url(self, caminho: str, parametros: dict) -> str:
        """Monta a URL da consulta sobre a ``base`` configurada."""
        return montar_url(self.base, caminho, parametros)

    def listar(self, janela: Janela) -> Iterator[ReferenciaArtefato]:
        """Uma referência por consulta de ``_consultas``, sem nenhuma requisição na listagem."""
        for objeto, caminho, parametros, meta in self._consultas(janela):
            yield ReferenciaArtefato(url=self._url(caminho, parametros), objeto=objeto,
                                     metadados={k: str(v) for k, v in meta.items()})

    def _obter(self, url: str) -> ArtefatoBruto:
        """Requisita a URL pedindo JSON e conta o resultado para ``reportar_conformidade``.

        Falha sem resposta e erro 5xx contam como falha da fonte; qualquer outra
        resposta, inclusive 4xx, conta como respondida.
        """
        try:
            a = self.cliente.obter(url, {"Accept": "application/json"})
        except ErroColeta:
            self.falhas += 1
            raise
        if a.status_http >= 500:
            self.falhas += 1
        else:
            self.respondidas += 1
        return a

    def baixar(self, ref: ReferenciaArtefato) -> ArtefatoBruto:
        """Devolve a página já baixada na listagem, se houver; senão, faz a requisição."""
        guardado = self._cache.retirar(ref.url)
        return guardado if guardado is not None else self._obter(ref.url)

    def reportar_conformidade(self) -> RelatorioConformidade:
        """Disponibilidade da própria fonte nas consultas desta sessão; não avalia ente nenhum.

        Com alguma falha, ou sem nenhuma consulta respondida, o resultado é indeterminado
        e traz o motivo; só sem falhas e com resposta é ``CUMPRE``.
        """
        if self.falhas or not self.respondidas:
            motivo = (f"{self.falhas} consulta(s) sem resposta ou com erro 5xx" if self.falhas
                      else "nenhuma consulta feita nesta sessão")
            a = AvaliacaoConformidade(criterio=f"{self.fonte_id}_respondeu_na_sessao",
                                      dispositivo_legal=self.dispositivo,
                                      resultado=ResultadoCriterio.INDETERMINADO,
                                      motivo_indeterminado=motivo)
        else:
            a = AvaliacaoConformidade(criterio=f"{self.fonte_id}_respondeu_na_sessao",
                                      dispositivo_legal=self.dispositivo,
                                      resultado=ResultadoCriterio.CUMPRE)
        return RelatorioConformidade(fonte_id=self.fonte_id, avaliacoes=(a,))


class FontePaginadaPorDeslocamento(FonteListaFixa):
    """APIs ORDS (SICONFI): ``limit``/``offset`` e o indicador ``hasMore``."""

    limite = 5000

    def listar(self, janela: Janela) -> Iterator[ReferenciaArtefato]:
        """Baixa as páginas de cada consulta em sequência enquanto a resposta indicar ``hasMore``.

        O deslocamento avança pela quantidade de itens recebida, ou por ``limite`` quando
        não dá para contá-los. Cada página fica no cache de planejamento, e ``baixar`` a
        devolve sem nova requisição.
        """
        for objeto, caminho, parametros, meta in self._consultas(janela):
            deslocamento = 0
            while True:
                params = {**parametros, "offset": deslocamento} if deslocamento else dict(parametros)
                url = self._url(caminho, params)
                artefato = self._obter(url)
                self._cache.guardar(url, artefato)
                yield ReferenciaArtefato(url=url, objeto=objeto,
                                         metadados={**{k: str(v) for k, v in meta.items()},
                                                    "offset": str(deslocamento)})
                if not _tem_mais(artefato):
                    break
                deslocamento += _quantidade(artefato) or self.limite


def _corpo(artefato: ArtefatoBruto) -> dict | None:
    """Corpo JSON de uma resposta 200 quando é um objeto; ``None`` em qualquer outro caso."""
    if artefato.status_http != 200:
        return None
    try:
        c = json.loads(artefato.conteudo.decode("utf-8-sig"))
    except (ValueError, UnicodeDecodeError):
        return None
    return c if isinstance(c, dict) else None


def _tem_mais(artefato: ArtefatoBruto) -> bool:
    """Indica se a página ORDS anuncia mais itens (``hasMore``)."""
    c = _corpo(artefato)
    return bool(c and c.get("hasMore"))


def _quantidade(artefato: ArtefatoBruto) -> int:
    """Quantos itens a página ORDS trouxe em ``items``; 0 se o corpo não for legível."""
    c = _corpo(artefato)
    return len(c.get("items") or []) if c else 0
