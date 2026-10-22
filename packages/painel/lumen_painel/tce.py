"""O que os coletores dos tribunais de contas têm em comum (ADR-050): a leitura por partes, a regra de quando reler
um ano, a soma de um ano por ente e a publicação.

Cada tribunal tem o próprio módulo (``tce_rs``, ``tce_pr``, ``tce_pe``), que lê a fonte dele e grava o estado em
``tce-<sigla>.json.gz`` no mesmo formato:

- ``anos``: por ano do contrato, a ``etiqueta`` e o ``tamanho`` do que foi lido, quando foi lido e a soma do ano
  (``SomaAno.para_json``): por ente, as ``COLUNAS_ENTE``; por ente e CNPJ, ``[contratos, valor]``; e o que ficou
  sem ente (consórcios e associações, que reúnem vários municípios);
- ``nomes``: o nome de cada CNPJ, com o CPF do MEI mascarado;
- ``tribunal``, ``sistema``, ``fonte`` e ``primeiro_ano``.

A leitura por partes (``ArquivoRemoto``) é um arquivo que o ``zipfile`` abre e lê em fluxo. O ``zip_remoto`` do
``lumen_ingestao`` (ADR-032) faz parecido, mas traz o arquivo pedido inteiro para a memória e não lê ZIP64; o
``pessoas.csv`` do TCE-RS tem 200 MB.

O valor acima do teto de plausibilidade do ente (o mesmo do painel de contratações, ADR-028) conta e fica fora
da soma. Contrato com pessoa física entra só na soma anônima, sem nome nem documento (DOC-08). A publicação junta
todos os tribunais em ``tce/ente/<grupo>.json.gz``: um ente só é fiscalizado por um tribunal.

Os servidores do TCE-RS e do TCE-CE só respondem a endereços do Brasil, e o GitHub Actions roda fora. Com
``LUMEN_PROXY_BR`` e ``LUMEN_PROXY_CHAVE`` no ambiente, os pedidos a eles passam pelo intermediário em São Paulo
(``infra/proxy-br``, uma função da Vercel), que devolve a resposta do tribunal como veio (ADR-050, adendo).
"""

from __future__ import annotations

import http.client
import io
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

from .comum import grupo_do_ente, ler_json

COLUNAS_ENTE = ["contratos", "valor", "a_conferir", "pf_contratos", "pf_valor", "aditivos", "aditivos_valor"]
VERSAO_ESTADO = 1
PADRAO_ESTADO = "tce-*.json.gz"
DIAS_ENTRE_LEITURAS = 6        # o ano corrente e o anterior mudam todo dia; basta ler uma vez por semana
DIAS_ANO_FECHADO = 30          # fonte sem cabeçalho que diga se mudou: o ano fechado é relido uma vez por mês
BLOCO = 4 << 20
TENTATIVAS = 4
FORNECEDORES_PUBLICADOS = 100
BLOCO_MAXIMO = 4 << 20         # a resposta da função da Vercel tem no máximo 4,5 MB (infra/proxy-br)
SO_DO_BRASIL = {"dados.tce.rs.gov.br", "api-dados-abertos.tce.ce.gov.br"}


# ------------------------------------------------------------------------------------------ fonte

def cabecalhos(contato: str) -> dict[str, str]:
    """User-Agent com o contato, como nas outras coletas."""
    return {"User-Agent": f"Lumen (contato: {contato})"}


def pelo_intermediario(pedido: urllib.request.Request, ambiente=os.environ) -> urllib.request.Request:
    """O pedido a um servidor que só responde do Brasil, refeito para o intermediário em São Paulo quando ele está
    configurado (``LUMEN_PROXY_BR`` e ``LUMEN_PROXY_CHAVE``); os outros pedidos ficam como estão."""
    base, chave = ambiente.get("LUMEN_PROXY_BR"), ambiente.get("LUMEN_PROXY_CHAVE")
    if not base or not chave or urllib.parse.urlsplit(pedido.full_url).hostname not in SO_DO_BRASIL:
        return pedido
    url = f"{base}?{urllib.parse.urlencode({'url': pedido.full_url})}"
    return urllib.request.Request(url, method=pedido.get_method(),
                                  headers={**dict(pedido.header_items()), "X-Lumen-Chave": chave})


def abrir(pedido: urllib.request.Request, *, tentativas: int = TENTATIVAS,
          esperar: Callable[[float], None] = time.sleep):
    """``urlopen`` com novas tentativas para falha de rede e erro 5xx; 404 sobe na hora. Passa pelo intermediário
    em São Paulo quando o servidor só responde do Brasil (``pelo_intermediario``)."""
    pedido = pelo_intermediario(pedido)
    for tentativa in range(tentativas):
        try:
            return urllib.request.urlopen(pedido, timeout=120)
        except urllib.error.HTTPError as erro:
            if erro.code < 500 or tentativa + 1 == tentativas:
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if tentativa + 1 == tentativas:
                raise
        esperar(5 * (tentativa + 1))
    raise AssertionError("inalcançável")


def cabecalho(url: str, *, contato: str) -> tuple[int, str] | None:
    """Tamanho e ETag (ou Last-Modified) do arquivo; ``None`` quando ele não existe (404). Pelo intermediário, os
    originais vêm em ``X-Lumen-Tamanho`` e ``X-Lumen-Etag``."""
    try:
        with abrir(urllib.request.Request(url, method="HEAD", headers=cabecalhos(contato))) as r:
            tamanho = r.headers.get("X-Lumen-Tamanho") or r.headers["Content-Length"]
            etiqueta = r.headers.get("X-Lumen-Etag") or r.headers.get("ETag") or r.headers.get("Last-Modified") or ""
            return int(tamanho), etiqueta
    except urllib.error.HTTPError as erro:
        if erro.code == 404:
            return None
        raise


def baixar(url: str, *, contato: str, tentativas: int = TENTATIVAS,
           esperar: Callable[[float], None] = time.sleep) -> bytes | None:
    """Um arquivo inteiro; ``None`` quando ele não existe (404). A conexão que cai no meio da leitura (o TCE-PE
    fechou uma resposta de 30 MB depois de 8,7 MB, em 22/10/2026) faz baixar de novo, do começo."""
    for tentativa in range(tentativas):
        try:
            with abrir(urllib.request.Request(url, headers=cabecalhos(contato))) as r:
                return r.read()
        except urllib.error.HTTPError as erro:
            if erro.code == 404:
                return None
            raise
        except (http.client.IncompleteRead, ConnectionError, TimeoutError):
            if tentativa + 1 == tentativas:
                raise
        esperar(5 * (tentativa + 1))
    raise AssertionError("inalcançável")


class ArquivoRemoto(io.RawIOBase):
    """Um arquivo do servidor lido por partes (``Range``), em blocos guardados, para o ``zipfile`` abrir só os
    membros pedidos sem baixar o resto."""

    def __init__(self, url: str, tamanho: int, *, contato: str, bloco: int = BLOCO,
                 abrir: Callable[..., Any] = abrir):
        """``tamanho`` vem do ``cabecalho``; ``abrir`` é substituível nos testes."""
        super().__init__()
        self.url, self.tamanho, self.contato, self.bloco, self._abrir = url, tamanho, contato, bloco, abrir
        self.posicao = 0
        self._inicio = 0
        self._dados = b""
        self.pedidos = 0

    def readable(self) -> bool:
        """Lê."""
        return True

    def seekable(self) -> bool:
        """Anda para qualquer posição."""
        return True

    def tell(self) -> int:
        """A posição atual."""
        return self.posicao

    def seek(self, deslocamento: int, de: int = io.SEEK_SET) -> int:
        """Muda a posição, como ``io``."""
        base = {io.SEEK_SET: 0, io.SEEK_CUR: self.posicao, io.SEEK_END: self.tamanho}[de]
        self.posicao = max(0, base + deslocamento)
        return self.posicao

    def readinto(self, destino) -> int:
        """Copia o que puder do bloco guardado; fora dele, busca um bloco novo a partir da posição."""
        if self.posicao >= self.tamanho or len(destino) == 0:
            return 0
        if not self._inicio <= self.posicao < self._inicio + len(self._dados):
            fim = min(self.tamanho, self.posicao + max(min(len(destino), BLOCO_MAXIMO), self.bloco)) - 1
            pedido = urllib.request.Request(self.url, headers={**cabecalhos(self.contato),
                                                               "Range": f"bytes={self.posicao}-{fim}"})
            with self._abrir(pedido) as resposta:
                if resposta.status != 206:
                    raise OSError(f"{self.url}: o servidor não devolveu a parte pedida (HTTP {resposta.status})")
                self._dados = resposta.read()
            self._inicio = self.posicao
            self.pedidos += 1
        i = self.posicao - self._inicio
        n = min(len(destino), len(self._dados) - i)
        destino[:n] = self._dados[i:i + n]
        self.posicao += n
        return n


# ------------------------------------------------------------------------------------------ soma

class SomaAno:
    """A soma de um ano: por ente (``COLUNAS_ENTE``), por ente e CNPJ e o que ficou sem ente. ``teto(ente)`` é o
    valor acima do qual o contrato conta e fica fora da soma."""

    def __init__(self, teto: Callable[[str], float]):
        """Começa vazia."""
        self._teto = teto
        self._tetos: dict[str, float] = {}
        self.entes: dict[str, list] = {}
        self.fornecedores: dict[str, dict[str, list]] = {}
        self.sem_ente = [0, 0.0]

    def _linha(self, ente: str) -> list:
        """A linha do ente (``COLUNAS_ENTE``), criada zerada na primeira vez."""
        return self.entes.setdefault(ente, [0, 0.0, 0, 0, 0.0, 0, 0.0])

    def contrato(self, ente: str | None, valor: float | None, *, cnpj: str | None = None) -> None:
        """Um contrato do ente: com ``cnpj``, na empresa; sem ele, na soma anônima de pessoa física. Sem ente, vai
        para ``sem_ente``."""
        if ente is None:
            self.sem_ente[0] += 1
            self.sem_ente[1] += valor or 0.0
            return
        if ente not in self._tetos:
            self._tetos[ente] = self._teto(ente)
        conferir = valor is not None and valor > self._tetos[ente]
        soma = 0.0 if conferir or valor is None else valor
        x = self._linha(ente)
        x[0] += 1
        x[1] += soma
        x[2] += conferir
        if cnpj:
            f = self.fornecedores.setdefault(ente, {}).setdefault(cnpj, [0, 0.0])
            f[0] += 1
            f[1] += soma
        else:
            x[3] += 1
            x[4] += soma

    def aditivo(self, ente: str | None, valor: float) -> None:
        """Um aditivo do ente, com o acréscimo líquido (negativo quando reduz)."""
        if ente is None:
            return
        x = self._linha(ente)
        x[5] += 1
        x[6] += valor

    def para_json(self) -> dict:
        """A soma como vai no estado, em ordem e com os valores em centavos."""
        r = lambda v: round(v, 2)  # noqa: E731
        return {
            "entes": {e: [x[0], r(x[1]), x[2], x[3], r(x[4]), x[5], r(x[6])] for e, x in sorted(self.entes.items())},
            "fornecedores": {e: {c: [n, r(v)] for c, (n, v) in sorted(fs.items())}
                             for e, fs in sorted(self.fornecedores.items())},
            "sem_ente": [self.sem_ente[0], r(self.sem_ente[1])],
        }


# ------------------------------------------------------------------------------------------ coleta

@dataclass
class ResultadoTce:
    """O que a coleta de um tribunal fez: os anos lidos, os pulados (sem mudança) e os que não existem."""

    tribunal: str
    lidos: list[int] = field(default_factory=list)
    pulados: list[int] = field(default_factory=list)
    ausentes: list[int] = field(default_factory=list)
    nomes: int = 0
    interrompida: bool = False
    problemas: list[str] = field(default_factory=list)

    def para_json(self) -> dict:
        """Resumo para imprimir na linha de comando."""
        return {"tribunal": self.tribunal, "lidos": self.lidos, "pulados": self.pulados, "ausentes": self.ausentes,
                "nomes": self.nomes, "interrompida": self.interrompida, "problemas": self.problemas}


def precisa_ler(guardado: dict | None, tamanho: int, etiqueta: str, ano: int, hoje: date) -> bool:
    """O ano tem de ser lido de novo? Nunca lido: sim. Fechado (antes do ano anterior): só se o tamanho mudou,
    porque os tribunais refazem os arquivos sem mudar o conteúdo. Corrente ou anterior: quando mudou e a última
    leitura tem ``DIAS_ENTRE_LEITURAS`` dias ou mais."""
    if not guardado:
        return True
    if ano < hoje.year - 1:
        return guardado.get("tamanho") != tamanho
    if guardado.get("etiqueta") == etiqueta:
        return False
    lido = datetime.fromisoformat(guardado["lido_em"].replace("Z", "+00:00")).date()
    return (hoje - lido).days >= DIAS_ENTRE_LEITURAS


def precisa_ler_por_idade(guardado: dict | None, ano: int, hoje: date) -> bool:
    """Para a fonte sem cabeçalho de mudança (uma API): nunca lido, sim; fechado, quando a leitura tem
    ``DIAS_ANO_FECHADO`` dias ou mais; corrente ou anterior, ``DIAS_ENTRE_LEITURAS``."""
    if not guardado:
        return True
    lido = datetime.fromisoformat(guardado["lido_em"].replace("Z", "+00:00")).date()
    return (hoje - lido).days >= (DIAS_ANO_FECHADO if ano < hoje.year - 1 else DIAS_ENTRE_LEITURAS)


def ler_estado(caminho: Path, *, tribunal: str, sistema: str, fonte: str, primeiro_ano: int) -> dict:
    """O estado de um tribunal, ou um vazio; versão desconhecida é erro."""
    dados = ler_json(caminho) if caminho.exists() else {}
    if dados and dados.get("versao") != VERSAO_ESTADO:
        raise ValueError(f"{caminho}: versão {dados.get('versao')!r} do estado do {tribunal} não suportada")
    return {"versao": VERSAO_ESTADO, "tribunal": tribunal, "sistema": sistema, "fonte": fonte,
            "primeiro_ano": primeiro_ano, "colunas_ente": COLUNAS_ENTE, "anos": dados.get("anos") or {},
            "nomes": dados.get("nomes") or {}}


# ------------------------------------------------------------------------------------------ publicação

def estados(estado: Path | str) -> list[dict]:
    """Os estados de todos os tribunais coletados (``tce-*.json.gz``), em ordem de nome."""
    saida = []
    for caminho in sorted(Path(estado).glob(PADRAO_ESTADO)):
        dados = ler_json(caminho)
        if dados.get("versao") != VERSAO_ESTADO:
            raise ValueError(f"{caminho}: versão {dados.get('versao')!r} do estado do tribunal não suportada")
        saida.append(dados)
    return saida


def entes_do_estado(dados: dict) -> dict[str, dict]:
    """Por ente: os anos (``COLUNAS_ENTE``) e os fornecedores do maior valor ao menor, cada um com os anos
    (``[CNPJ, nome, [[ano, contratos, valor], ...]]``), até ``FORNECEDORES_PUBLICADOS``."""
    nomes = dados.get("nomes") or {}
    saida: dict[str, dict] = {}
    for ano, a in sorted((dados.get("anos") or {}).items()):
        for ente, linha in a["entes"].items():
            saida.setdefault(ente, {"anos": {}, "_f": {}})["anos"][ano] = linha
        for ente, fs in a["fornecedores"].items():
            por_cnpj = saida.setdefault(ente, {"anos": {}, "_f": {}})["_f"]
            for cnpj, (n, v) in fs.items():
                por_cnpj.setdefault(cnpj, []).append([ano, n, v])
    for registro in saida.values():
        f = registro.pop("_f")
        ordem = sorted(f.items(), key=lambda x: (-sum(v for _, _, v in x[1]), x[0]))[:FORNECEDORES_PUBLICADOS]
        registro["fornecedores"] = [[cnpj, nomes.get(cnpj), anos] for cnpj, anos in ordem]
    return saida


def publicar(estado: Path | str, gravar: Callable[[str, Any], Any], *, gerado_em: str) -> dict | None:
    """Grava ``tce/ente/<grupo>.json.gz`` (comprimido, ``comum.grupo_do_ente``) com os contratos de cada ente
    registrados no tribunal de contas dele, e devolve o resumo de cada tribunal para o índice."""
    todos = estados(estado)
    if not todos:
        return None
    tribunais, grupos, resumo = {}, {}, {}
    for dados in todos:
        sigla = dados["tribunal"]
        tribunais[sigla] = {"sistema": dados.get("sistema"), "fonte": dados.get("fonte"),
                            "coletado_em": dados.get("coletado_em"), "primeiro_ano": dados.get("primeiro_ano")}
        por_ente = entes_do_estado(dados)
        for ente, registro in por_ente.items():
            grupos.setdefault(grupo_do_ente(ente), {})[ente] = {"tribunal": sigla, **registro}
        anos = dados.get("anos") or {}
        resumo[sigla] = {"anos": sorted(anos), "entes": len(por_ente),
                         "sem_ente": {a: x["sem_ente"] for a, x in sorted(anos.items())}}
    for grupo, entes in sorted(grupos.items()):
        gravar(f"tce/ente/{grupo}.json.gz", {
            "versao": 1, "tipo": "tce-entes", "gerado_em": gerado_em, "tribunais": tribunais,
            "colunas": COLUNAS_ENTE, "colunas_fornecedor": ["cnpj", "nome", "anos"], "entes": dict(sorted(entes.items())),
        })
    return {"arquivos": len(grupos), "tribunais": resumo}
