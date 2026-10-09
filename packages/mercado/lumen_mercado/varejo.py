"""Ofertas do varejo online pela API oficial da loja (ADR-027, seção 2.2).

Só entra loja com API oficial, e só pelo caminho que a loja oferece a terceiros: Magazine Luiza, KaBuM,
Pichau e comparadores como o Zoom não têm API pública de preços, e extrair o site deles contraria os termos
de uso e as barreiras contra robôs — coisa que o princípio 6 do Lumen proíbe. Hoje há um adaptador, o do
Mercado Livre (``/sites/MLB/search``); Amazon (Creators API), AliExpress e Shopee (programas de afiliados)
entram pelo mesmo contrato quando houver credencial.

Preço de loja só vale como referência na data em que foi visto: a API devolve o preço de hoje. Por isso a
coleta é diária e fica no bronze, com data e hora do acesso (a Lei 14.133 exige as duas para sítios
eletrônicos, art. 23, § 1º, III), e a comparação procura as coletas em torno da data da compra.

A credencial, quando a loja exige, vem só de variável de ambiente (``LUMEN_ML_TOKEN``) e vai no cabeçalho
da requisição; o bronze guarda os cabeçalhos da resposta, nunca os do pedido.

O formato da resposta foi escrito pela documentação pública da API. A primeira coleta real precisa ser
conferida com ``lumen mercado varejo testar`` e o teste de contrato (``testes/contrato``), que avisam se o
acesso exige outro tipo de credencial ou se algum campo mudou de nome.
"""

from __future__ import annotations

import json
import os
import urllib.parse
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Iterable, Iterator

from lumen_ingestao.bronze import ArmazemBronze, ArtefatoBruto
from lumen_ingestao.cliente_http import ClienteHttp
from lumen_ingestao.portas import (
    AvaliacaoConformidade,
    CapacidadesFonte,
    Janela,
    Periodicidade,
    ReferenciaArtefato,
    RelatorioConformidade,
    ResultadoCriterio,
)

from .especificacao import Especificacao, oferta_confere
from .referencia import Evidencia, ReferenciaMercado

FONTE_ID = "varejo_mercadolivre"
BASE_ML = "https://api.mercadolibre.com"
SITE = "MLB"
LIMITE_POR_CONSULTA = 50
VARIAVEL_TOKEN = "LUMEN_ML_TOKEN"


def url_busca(consulta: str, *, base: str = BASE_ML, site: str = SITE, limite: int = LIMITE_POR_CONSULTA) -> str:
    """Endereço da busca por texto livre na API do Mercado Livre, já com o limite de resultados."""
    parametros = urllib.parse.urlencode({"q": consulta, "limit": limite})
    return f"{base.rstrip('/')}/sites/{site}/search?{parametros}"


def consulta_da_url(url: str) -> str | None:
    """O texto buscado (parâmetro ``q``) de uma URL de busca; None se não houver."""
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get("q")
    return q[0] if q else None


@dataclass(frozen=True)
class Oferta:
    """Uma oferta como a loja a mostrou: título, preço, condição, vendedor e endereço, com a hora do acesso."""

    loja: str
    id: str
    titulo: str
    preco: Decimal
    moeda: str
    condicao: str | None
    endereco: str | None
    vendedor: str | None
    loja_oficial: bool
    frete_gratis: bool
    acessado_em: datetime


def _decimal(valor) -> Decimal | None:
    """Número da API em ``Decimal`` (via texto, sem passar por ``float``); None se ausente ou inválido."""
    if valor is None or isinstance(valor, bool):
        return None
    try:
        d = Decimal(str(valor))
    except InvalidOperation:
        return None
    return d if d > 0 else None


def ler_ofertas(conteudo: bytes, acessado_em: datetime, *, loja: str = FONTE_ID) -> list[Oferta]:
    """Ofertas da resposta de busca (``results``); resultado sem id, título ou preço positivo fica de fora."""
    try:
        corpo = json.loads(conteudo.decode("utf-8-sig"))
    except (ValueError, UnicodeDecodeError):
        return []
    ofertas = []
    for r in (corpo.get("results") or []) if isinstance(corpo, dict) else []:
        if not isinstance(r, dict):
            continue
        preco = _decimal(r.get("price"))
        if not r.get("id") or not r.get("title") or preco is None:
            continue
        vendedor = r.get("seller") if isinstance(r.get("seller"), dict) else {}
        envio = r.get("shipping") if isinstance(r.get("shipping"), dict) else {}
        ofertas.append(Oferta(
            loja=loja, id=str(r["id"]), titulo=str(r["title"]), preco=preco,
            moeda=str(r.get("currency_id") or ""), condicao=r.get("condition"),
            endereco=r.get("permalink"), vendedor=str(vendedor["id"]) if vendedor.get("id") is not None else None,
            loja_oficial=r.get("official_store_id") is not None, frete_gratis=bool(envio.get("free_shipping")),
            acessado_em=acessado_em))
    return ofertas


def ofertas_comparaveis(especificacao: Especificacao, ofertas: Iterable[Oferta]) -> list[Oferta]:
    """Ofertas novas, em reais, cujo título confere com a especificação; uma por produto da loja (id)."""
    vistas: dict[str, Oferta] = {}
    for o in ofertas:
        if o.moeda != "BRL" or (o.condicao or "new") != "new":
            continue
        if not oferta_confere(especificacao, o.titulo):
            continue
        vistas.setdefault(o.id, o)
    return list(vistas.values())


class FonteMercadoLivre:
    """Adaptador da porta ``FonteDados`` para a busca do Mercado Livre: um artefato por consulta e por dia.

    ``consultas`` são os textos de busca (normalmente ``Especificacao.consulta`` dos itens a comparar e uma
    lista fixa de produtos comuns, para formar o histórico antes de a compra acontecer).
    """

    fonte_id = FONTE_ID

    def __init__(self, cliente: ClienteHttp, consultas: Iterable[str], *, base: str = BASE_ML,
                 token: str | None = None):
        """Confere o cliente, fixa as consultas (sem repetição) e lê o token do ambiente se não for dado."""
        if cliente.fonte_id != self.fonte_id:
            raise ValueError(f"cliente da fonte {cliente.fonte_id!r} usado em {self.fonte_id!r}")
        self.cliente = cliente
        self.consultas = tuple(dict.fromkeys(c.strip() for c in consultas if c and c.strip()))
        self.base = base
        self.token = token if token is not None else os.environ.get(VARIAVEL_TOKEN) or None
        self.respondidas = 0
        self.recusadas = 0

    def descrever_capacidades(self) -> CapacidadesFonte:
        """Ofertas de varejo, coleta diária, sem incremental; o limite de taxa é o do cliente."""
        return CapacidadesFonte(objetos=frozenset({"OfertaVarejo"}), periodicidade=Periodicidade.DIARIA,
                                suporta_incremental=False, limite_requisicoes_por_minuto=self.cliente.limitador.rpm,
                                exige_autenticacao=self.token is not None)

    def listar(self, janela: Janela) -> Iterator[ReferenciaArtefato]:
        """Uma referência por consulta. A janela não se aplica: a loja só mostra o preço de agora."""
        for consulta in self.consultas:
            yield ReferenciaArtefato(url=url_busca(consulta, base=self.base), objeto="OfertaVarejo",
                                     metadados={"consulta": consulta})

    def baixar(self, ref: ReferenciaArtefato) -> ArtefatoBruto:
        """Faz a busca, com o token no cabeçalho quando houver; 401 e 403 contam como recusa da loja."""
        cabecalhos = {"Accept": "application/json"}
        if self.token:
            cabecalhos["Authorization"] = f"Bearer {self.token}"
        artefato = self.cliente.obter(ref.url, cabecalhos)
        if artefato.status_http in (401, 403):
            self.recusadas += 1
        else:
            self.respondidas += 1
        return artefato

    def reportar_conformidade(self) -> RelatorioConformidade:
        """Disponibilidade da API nesta sessão; recusa por credencial vira indeterminado com o motivo."""
        if self.recusadas or not self.respondidas:
            motivo = (f"{self.recusadas} consulta(s) recusadas pela API (401/403): confira a credencial"
                      if self.recusadas else "nenhuma consulta feita nesta sessão")
            a = AvaliacaoConformidade(criterio=f"{FONTE_ID}_respondeu_na_sessao", dispositivo_legal="não se aplica",
                                      resultado=ResultadoCriterio.INDETERMINADO, motivo_indeterminado=motivo)
        else:
            a = AvaliacaoConformidade(criterio=f"{FONTE_ID}_respondeu_na_sessao", dispositivo_legal="não se aplica",
                                      resultado=ResultadoCriterio.CUMPRE)
        return RelatorioConformidade(fonte_id=FONTE_ID, avaliacoes=(a,))


class OfertasVarejo:
    """Ofertas guardadas no bronze, por consulta e por dia de acesso, para montar referências por período."""

    def __init__(self) -> None:
        """Índice vazio."""
        self._por_consulta: dict[str, list[Oferta]] = {}

    def adicionar(self, consulta: str, ofertas: Iterable[Oferta]) -> None:
        """Inclui as ofertas vistas numa busca."""
        self._por_consulta.setdefault(consulta, []).extend(ofertas)

    @classmethod
    def do_bronze(cls, armazem: ArmazemBronze) -> "OfertasVarejo":
        """Lê todas as buscas guardadas no bronze (respostas 200), com a hora de cada coleta."""
        indice = cls()
        for registro in armazem.listar_registros(FONTE_ID):
            if registro.status_http != 200:
                continue
            consulta = consulta_da_url(registro.url_solicitada)
            if not consulta:
                continue
            _, conteudo = armazem.recuperar(registro.registro_id)
            quando = datetime.fromisoformat(registro.coletado_em.replace("Z", "+00:00"))
            indice.adicionar(consulta, ler_ofertas(conteudo, quando))
        return indice

    def consultas(self) -> list[str]:
        """Consultas com alguma oferta guardada."""
        return sorted(self._por_consulta)

    def referencia(self, especificacao: Especificacao, quando: date, *, janela_dias: int = 7,
                   minimo_ofertas: int = 8) -> ReferenciaMercado | None:
        """Distribuição dos preços das ofertas comparáveis vistas até ``janela_dias`` antes ou depois da data.

        A mesma oferta vista em dias diferentes entra uma vez, com o preço do acesso mais próximo da data.
        Com menos de ``minimo_ofertas`` ofertas distintas, None.
        """
        if not especificacao.consulta:
            return None
        inicio = datetime.combine(quando - timedelta(days=janela_dias), datetime.min.time(), timezone.utc)
        fim = datetime.combine(quando + timedelta(days=janela_dias + 1), datetime.min.time(), timezone.utc)
        dentro = [o for o in self._por_consulta.get(especificacao.consulta, []) if inicio <= o.acessado_em < fim]
        alvo = datetime.combine(quando, datetime.min.time(), timezone.utc)
        melhor: dict[str, Oferta] = {}
        for o in ofertas_comparaveis(especificacao, sorted(dentro, key=lambda o: abs(o.acessado_em - alvo))):
            melhor.setdefault(o.id, o)
        if len(melhor) < minimo_ofertas:
            return None
        escolhidas = sorted(melhor.values(), key=lambda o: o.preco)
        datas = [o.acessado_em.date() for o in escolhidas]
        return ReferenciaMercado.de_valores(
            (o.preco for o in escolhidas), fonte=FONTE_ID, produto=especificacao.produto, escopo="brasil",
            local="BR", periodo=(min(datas), max(datas)), unidade="unidade",
            evidencias=tuple(Evidencia(descricao=o.titulo, valor=o.preco, data=o.acessado_em.isoformat(),
                                       endereco=o.endereco) for o in escolhidas))
