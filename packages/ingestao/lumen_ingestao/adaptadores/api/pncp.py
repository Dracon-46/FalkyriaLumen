"""Adaptadores do PNCP — Portal Nacional de Contratações Públicas.

API de consulta: ``https://pncp.gov.br/api/consulta`` (sem autenticação).
Comportamentos reais observados em 05/10/2026 e tratados aqui (ver
``testes/fixtures/pncp`` e DOC-06):

- ``codigoModalidadeContratacao`` é **obrigatório** em ``/v1/contratacoes/*``;
  sem ele a API responde 400. Por isso a coleta de contratações percorre as
  19 modalidades do domínio oficial.
- ``tamanhoPagina`` aceita no máximo **50** em contratações e **500** em
  contratos e atas.
- Janela de datas acima de **365 dias** responde 422. A coleta fatia por dia,
  o que também mantém cada página num tamanho previsível.
- Página sem registros responde **204 sem corpo**, e não 200 com lista vazia.
- Itens, resultados e arquivos de uma contratação estão em outra API,
  ``https://pncp.gov.br/api/pncp``, no caminho do órgão.

Cada página é um artefato da camada bronze. A primeira página de cada
consulta é baixada já na listagem, porque é ela que diz quantas páginas
existem; ``baixar`` devolve essa mesma cópia em vez de pedir de novo.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import date
from typing import Callable, Iterable, Iterator

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
from ._paginacao import CacheDePlanejamento, dias, montar_url, total_paginas

BASE_CONSULTA = "https://pncp.gov.br/api/consulta"
BASE_PNCP = "https://pncp.gov.br/api/pncp"

# Domínio oficial (/api/pncp/v1/modalidades), lido em 05/10/2026.
MODALIDADES_PNCP: tuple[int, ...] = tuple(range(1, 20))

DISPOSITIVO_PNCP = "Lei 14.133/2021, art. 174"


def _ymd(d: date) -> str:
    """Data no formato ``AAAAMMDD`` que a API de consulta do PNCP espera."""
    return d.strftime("%Y%m%d")


class _FontePncpBase:
    """Laço comum: listar por dia (e por modalidade), expandir páginas, baixar."""

    fonte_id: str
    objeto: str
    caminho: str
    tamanho_maximo: int

    def __init__(self, cliente: ClienteHttp, *, tamanho_pagina: int | None = None, base: str = BASE_CONSULTA):
        """Valida o tamanho de página (de 10 ao máximo do endpoint) e o ``fonte_id`` do cliente.

        Sem ``tamanho_pagina``, usa o máximo aceito pelo endpoint, o que reduz o número de requisições.
        """
        tamanho = tamanho_pagina or self.tamanho_maximo
        if not (10 <= tamanho <= self.tamanho_maximo):
            raise ValueError(f"tamanhoPagina precisa estar entre 10 e {self.tamanho_maximo} para {self.caminho}")
        if cliente.fonte_id != self.fonte_id:
            raise ValueError(f"cliente da fonte {cliente.fonte_id!r} usado em {self.fonte_id!r}")
        self.cliente = cliente
        self.tamanho_pagina = tamanho
        self.base = base
        self._cache = CacheDePlanejamento()
        self._status = Counter()
        self._sem_resposta = 0

    # ------------------------------------------------------------ porta

    def descrever_capacidades(self) -> CapacidadesFonte:
        """Um objeto canônico, periodicidade diária e coleta incremental; o limite de taxa é o do cliente."""
        return CapacidadesFonte(
            objetos=frozenset({self.objeto}),
            periodicidade=Periodicidade.DIARIA,
            suporta_incremental=True,
            limite_requisicoes_por_minuto=self.cliente.limitador.rpm,
        )

    def _consultas(self, dia: date) -> Iterator[dict]:
        """Parâmetros extras de cada consulta do dia; na base, uma única consulta sem extras."""
        yield {}

    def _parametros(self, dia: date, extra: dict, pagina: int) -> dict:
        """Parâmetros de uma página: o dia como data inicial e final, os extras, a página e o tamanho."""
        return {"dataInicial": _ymd(dia), "dataFinal": _ymd(dia), **extra,
                "pagina": pagina, "tamanhoPagina": self.tamanho_pagina}

    def listar(self, janela: Janela) -> Iterator[ReferenciaArtefato]:
        """Para cada dia e consulta, baixa a página 1 e referencia todas as páginas que ela anuncia.

        A página 1 fica no cache de planejamento e ``baixar`` a entrega sem nova requisição.
        Consultar um dia por vez mantém cada pedido longe do limite de 365 dias da API.
        """
        for dia in dias(janela):
            for extra in self._consultas(dia):
                url1 = montar_url(self.base, self.caminho, self._parametros(dia, extra, 1))
                primeira = self._obter(url1)
                self._cache.guardar(url1, primeira)
                metadados = {"dia": dia.isoformat(), **{k: str(v) for k, v in extra.items()}}
                yield ReferenciaArtefato(url=url1, objeto=self.objeto, metadados={**metadados, "pagina": "1"})
                for pagina in range(2, total_paginas(primeira) + 1):
                    yield ReferenciaArtefato(
                        url=montar_url(self.base, self.caminho, self._parametros(dia, extra, pagina)),
                        objeto=self.objeto,
                        metadados={**metadados, "pagina": str(pagina)},
                    )

    def baixar(self, ref: ReferenciaArtefato) -> ArtefatoBruto:
        """Devolve a página 1 guardada na listagem, quando é ela; senão, faz a requisição."""
        guardado = self._cache.retirar(ref.url)
        return guardado if guardado is not None else self._obter(ref.url)

    def _obter(self, url: str) -> ArtefatoBruto:
        """Requisita a URL pedindo JSON e contabiliza o status, ou a falha sem resposta.

        Essas contagens são a base de ``reportar_conformidade``.
        """
        try:
            artefato = self.cliente.obter(url, {"Accept": "application/json"})
        except ErroColeta:
            self._sem_resposta += 1
            raise
        self._status[artefato.status_http] += 1
        return artefato

    def reportar_conformidade(self) -> RelatorioConformidade:
        """Disponibilidade do próprio PNCP nas consultas desta sessão.

        Não avalia ente nenhum: diz se a fonte federal respondeu. É o que o
        avaliador de conformidade precisa para não atribuir a um ente uma
        ausência que, na verdade, foi indisponibilidade do PNCP (DOC-07,
        "cuidado essencial" da família I).
        """
        falhas = self._sem_resposta + sum(n for s, n in self._status.items() if s >= 500)
        respondidas = sum(n for s, n in self._status.items() if s < 500)
        if not respondidas and not falhas:
            avaliacao = AvaliacaoConformidade(
                criterio="pncp_respondeu_na_sessao", dispositivo_legal=DISPOSITIVO_PNCP,
                resultado=ResultadoCriterio.INDETERMINADO,
                motivo_indeterminado="nenhuma consulta feita nesta sessão")
        elif falhas:
            avaliacao = AvaliacaoConformidade(
                criterio="pncp_respondeu_na_sessao", dispositivo_legal=DISPOSITIVO_PNCP,
                resultado=ResultadoCriterio.INDETERMINADO,
                motivo_indeterminado=f"{falhas} consulta(s) sem resposta ou com erro 5xx; "
                                     "ausências desta janela não podem ser atribuídas aos entes")
        else:
            avaliacao = AvaliacaoConformidade(
                criterio="pncp_respondeu_na_sessao", dispositivo_legal=DISPOSITIVO_PNCP,
                resultado=ResultadoCriterio.CUMPRE)
        return RelatorioConformidade(fonte_id=self.fonte_id, avaliacoes=(avaliacao,))


class FontePncpContratacoes(_FontePncpBase):
    """``/v1/contratacoes/publicacao`` (carga) ou ``/v1/contratacoes/atualizacao`` (incremental)."""

    objeto = "ProcessoContratacao"
    tamanho_maximo = 50

    def __init__(self, cliente: ClienteHttp, *, modo: str = "publicacao",
                 modalidades: Iterable[int] = MODALIDADES_PNCP, **kw):
        """Escolhe endpoint e ``fonte_id`` pelo modo e fixa as modalidades a percorrer.

        O PNCP exige ``codigoModalidadeContratacao``, por isso uma lista vazia de modalidades é recusada.
        """
        if modo not in ("publicacao", "atualizacao"):
            raise ValueError("modo é 'publicacao' ou 'atualizacao'")
        self.modo = modo
        self.fonte_id = "pncp_contratacoes" if modo == "publicacao" else "pncp_contratacoes_atualizacao"
        self.caminho = f"/v1/contratacoes/{modo}"
        self.modalidades = tuple(modalidades)
        if not self.modalidades:
            raise ValueError("informe ao menos uma modalidade: o PNCP exige o parâmetro")
        super().__init__(cliente, **kw)

    def _consultas(self, dia: date) -> Iterator[dict]:
        """Uma consulta por modalidade, já que o parâmetro é obrigatório."""
        for m in self.modalidades:
            yield {"codigoModalidadeContratacao": m}


class FontePncpContratos(_FontePncpBase):
    """``/v1/contratos`` (carga) ou ``/v1/contratos/atualizacao`` (incremental)."""

    objeto = "Contrato"
    tamanho_maximo = 500

    def __init__(self, cliente: ClienteHttp, *, modo: str = "publicacao", **kw):
        """Escolhe endpoint e ``fonte_id`` pelo modo: ``publicacao`` ou ``atualizacao``."""
        if modo not in ("publicacao", "atualizacao"):
            raise ValueError("modo é 'publicacao' ou 'atualizacao'")
        self.fonte_id = "pncp_contratos" if modo == "publicacao" else "pncp_contratos_atualizacao"
        self.caminho = "/v1/contratos" if modo == "publicacao" else "/v1/contratos/atualizacao"
        super().__init__(cliente, **kw)


class FontePncpAtas(_FontePncpBase):
    """``/v1/atas`` (por vigência) ou ``/v1/atas/atualizacao`` (incremental)."""

    objeto = "AtaRegistroPreco"
    tamanho_maximo = 500

    def __init__(self, cliente: ClienteHttp, *, modo: str = "vigencia", **kw):
        """Escolhe endpoint e ``fonte_id`` pelo modo: ``vigencia`` ou ``atualizacao``."""
        if modo not in ("vigencia", "atualizacao"):
            raise ValueError("modo é 'vigencia' ou 'atualizacao'")
        self.fonte_id = "pncp_atas" if modo == "vigencia" else "pncp_atas_atualizacao"
        self.caminho = "/v1/atas" if modo == "vigencia" else "/v1/atas/atualizacao"
        super().__init__(cliente, **kw)


# ---------------------------------------------------------------- detalhe

_CHAVE_COMPRA = re.compile(r"^(?P<cnpj>[0-9A-Z]{14})-(?P<tipo>\d+)-(?P<seq>\d+)/(?P<ano>\d{4})$")


@dataclass(frozen=True)
class ChaveCompra:
    """Identifica uma contratação no PNCP: CNPJ do órgão, ano e sequencial da compra.

    Converte de e para o ``numeroControlePNCP``; os três campos compõem o caminho da
    contratação na API ``/api/pncp``.
    """

    cnpj: str
    ano: int
    sequencial: int

    @classmethod
    def de_numero_controle(cls, numero: str) -> "ChaveCompra":
        """``97229181000164-1-000406/2026`` → cnpj, 2026, 406."""
        m = _CHAVE_COMPRA.match((numero or "").strip())
        if not m or m.group("tipo") != "1":
            raise ValueError(f"numeroControlePNCP de contratação inválido: {numero!r}")
        return cls(cnpj=m.group("cnpj"), ano=int(m.group("ano")), sequencial=int(m.group("seq")))

    @property
    def numero_controle(self) -> str:
        """``numeroControlePNCP`` da contratação (tipo 1), com o sequencial em seis dígitos."""
        return f"{self.cnpj}-1-{self.sequencial:06d}/{self.ano}"


class FontePncpItens:
    """Itens e resultados das contratações informadas (API ``/api/pncp``).

    Não é uma fonte por janela de datas: os itens são buscados sob demanda,
    para as contratações já coletadas que interessam (por exemplo, as
    dispensas do período, base da família A). ``listar`` ignora a janela e
    percorre a lista recebida; o motivo fica explícito para não parecer
    esquecimento.
    """

    fonte_id = "pncp_itens"
    objeto = "ItemContratacao"

    def __init__(self, cliente: ClienteHttp, compras: Iterable[ChaveCompra], *,
                 com_resultados: bool = True, base: str = BASE_PNCP,
                 filtro_resultados: Callable[[dict], bool] | None = None):
        """Confere o ``fonte_id`` do cliente e fixa as contratações a consultar.

        ``com_resultados`` decide se os resultados dos itens que os têm também são listados;
        ``filtro_resultados``, quando dado, restringe os resultados aos itens (o dicionário da API) para os
        quais ele devolve verdadeiro. Cada resultado é uma requisição por item: buscar só os que interessam
        (os itens comparáveis da regra A-05, por exemplo) poupa a fonte e o tempo da coleta.
        """
        if cliente.fonte_id != self.fonte_id:
            raise ValueError(f"cliente da fonte {cliente.fonte_id!r} usado em {self.fonte_id!r}")
        self.cliente = cliente
        self.compras = tuple(compras)
        self.com_resultados = com_resultados
        self.base = base
        self.filtro_resultados = filtro_resultados
        self._cache = CacheDePlanejamento()

    def descrever_capacidades(self) -> CapacidadesFonte:
        """Itens e resultados, sem coleta incremental: o que se coleta é a lista de contratações recebida."""
        return CapacidadesFonte(
            objetos=frozenset({"ItemContratacao", "ResultadoItem"}),
            periodicidade=Periodicidade.DIARIA,
            suporta_incremental=False,
            limite_requisicoes_por_minuto=self.cliente.limitador.rpm,
        )

    def _url(self, c: ChaveCompra, sufixo: str) -> str:
        """URL de um recurso da contratação, sob ``/v1/orgaos/<cnpj>/compras/<ano>/<sequencial>/``."""
        return montar_url(self.base, f"/v1/orgaos/{c.cnpj}/compras/{c.ano}/{c.sequencial}/{sufixo}", {})

    def listar(self, janela: Janela) -> Iterator[ReferenciaArtefato]:
        """Baixa os itens de cada contratação e, se pedido, referencia os resultados dos itens que os têm.

        A janela é ignorada, como explica a classe. A lista de itens fica no cache de
        planejamento e é referenciada mesmo quando a resposta é de erro; os resultados só
        são procurados numa resposta 200 com JSON legível.
        """
        import json
        for c in self.compras:
            meta = {"compra": c.numero_controle}
            url_itens = self._url(c, "itens")
            itens = self.cliente.obter(url_itens, {"Accept": "application/json"})
            self._cache.guardar(url_itens, itens)
            yield ReferenciaArtefato(url=url_itens, objeto="ItemContratacao", metadados=meta)
            if not self.com_resultados or itens.status_http != 200:
                continue
            try:
                lista = json.loads(itens.conteudo.decode("utf-8-sig"))
            except (ValueError, UnicodeDecodeError):
                continue
            for item in lista if isinstance(lista, list) else []:
                if not isinstance(item, dict) or not item.get("temResultado") or item.get("numeroItem") is None:
                    continue
                if self.filtro_resultados is None or self.filtro_resultados(item):
                    yield ReferenciaArtefato(
                        url=self._url(c, f"itens/{int(item['numeroItem'])}/resultados"),
                        objeto="ResultadoItem",
                        metadados={**meta, "numero_item": str(item["numeroItem"])},
                    )

    def baixar(self, ref: ReferenciaArtefato) -> ArtefatoBruto:
        """Devolve a lista de itens guardada na listagem, quando é ela; senão, faz a requisição."""
        guardado = self._cache.retirar(ref.url)
        return guardado if guardado is not None else self.cliente.obter(ref.url, {"Accept": "application/json"})

    def reportar_conformidade(self) -> RelatorioConformidade:
        """Sempre indeterminado: a publicação de itens é avaliada pelo módulo de conformidade sobre a silver."""
        return RelatorioConformidade(fonte_id=self.fonte_id, avaliacoes=(AvaliacaoConformidade(
            criterio="itens_publicados_por_contratacao", dispositivo_legal=DISPOSITIVO_PNCP,
            resultado=ResultadoCriterio.INDETERMINADO,
            motivo_indeterminado="avaliado pelo módulo de conformidade sobre a silver, não pelo adaptador"),))
