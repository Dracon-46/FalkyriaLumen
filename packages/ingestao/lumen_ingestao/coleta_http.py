"""Coleta HTTP mínima, compartilhada por todos os conectores.

Duas decisões merecem nota.

**Resposta de erro também é artefato.** Um 404 ou 503 não é jogado fora: ele
volta como ``ArtefatoBruto`` com o ``status_http`` correspondente e é guardado
na camada bronze. Pelo princípio P5, um portal que não publica o que a lei
obriga é um achado — e a resposta de erro datada é a prova desse achado. Quem
decide se o erro é temporário ou persistente é o avaliador de conformidade,
olhando a sequência de coletas, não esta função.

Só falhas em que nada foi recebido (DNS, conexão recusada, tempo esgotado)
levantam ``ErroColeta``: nesse caso não existe resposta a preservar.

**Identificação obrigatória.** Não há User-Agent padrão. Todo conector precisa
declarar quem está coletando e como entrar em contato (RF-CO-09, princípio
P6). Um coletor anônimo é exatamente o tipo de tráfego que o operador de um
portal público tem razão de bloquear.

**Compressão de transporte é desfeita.** Algumas fontes (a API de serviços do
IBGE, por exemplo) respondem com ``Content-Encoding: gzip`` mesmo sem o pedido
pedir. A compressão é do transporte, não do documento: o bronze guarda o
documento descomprimido, sem o ``Content-Encoding``, e registra a codificação
recebida em ``X-Lumen-Codificacao-Recebida``. O limite de tamanho vale para o
documento descomprimido, o que barra uma resposta pequena que se expande sem
fim. Corpo que diz estar comprimido e não descomprime fica como veio, com o
cabeçalho original.

Limite de taxa por fonte, espera exponencial entre tentativas e suspensão da
fonte depois de falhas seguidas ficam em ``cliente_http.ClienteHttp``, que usa
esta função. Esta função faz uma única requisição, e faz bem.
"""

from __future__ import annotations

import urllib.error
import urllib.request
import zlib
from datetime import datetime, timezone

from .bronze import ArtefatoBruto

LIMITE_PADRAO_BYTES = 256 * 1024 * 1024  # PDFs de portal podem ser grandes
TIMEOUT_PADRAO_S = 60


class ErroColeta(Exception):
    """Nada foi recebido da fonte: não há resposta a preservar."""


class ConteudoGrandeDemais(ErroColeta):
    """A resposta excedeu o limite configurado."""


def user_agent_lumen(versao: str, contato: str) -> str:
    """Monta a identificação exigida pela política de coleta responsável."""
    eh_email = "@" in contato
    eh_url = contato.startswith(("http://", "https://"))
    if not contato or not (eh_email or eh_url):
        raise ValueError("contato precisa ser um e-mail ou uma URL de contato")
    return f"Lumen/{versao} (monitoramento de transparencia publica; +{contato})"


def _ler_limitado(resposta, limite: int) -> bytes:
    """Lê a resposta em blocos de 64 KiB e levanta ``ConteudoGrandeDemais`` ao passar de ``limite``.

    Ler em blocos interrompe o download assim que o limite é excedido, sem carregar a
    resposta inteira na memória.
    """
    partes = []
    total = 0
    while True:
        bloco = resposta.read(64 * 1024)
        if not bloco:
            break
        total += len(bloco)
        if total > limite:
            raise ConteudoGrandeDemais(f"resposta excedeu {limite} bytes")
        partes.append(bloco)
    return b"".join(partes)


CABECALHO_CODIFICACAO_RECEBIDA = "X-Lumen-Codificacao-Recebida"
_JANELAS = {"gzip": (16 + zlib.MAX_WBITS,), "x-gzip": (16 + zlib.MAX_WBITS,),
            "deflate": (zlib.MAX_WBITS, -zlib.MAX_WBITS)}   # deflate: com cabeçalho zlib ou cru


def _descomprimir(conteudo: bytes, janela: int, limite: int) -> bytes:
    """Descomprime com a janela dada, levantando ``ConteudoGrandeDemais`` se passar de ``limite``."""
    d = zlib.decompressobj(janela)
    saida = d.decompress(conteudo, limite + 1)
    if len(saida) > limite or d.unconsumed_tail:
        raise ConteudoGrandeDemais(f"resposta descomprimida excedeu {limite} bytes")
    saida += d.flush()
    if len(saida) > limite:
        raise ConteudoGrandeDemais(f"resposta descomprimida excedeu {limite} bytes")
    return saida


def decodificar_corpo(conteudo: bytes, cabecalhos: dict[str, str],
                      limite: int = LIMITE_PADRAO_BYTES) -> tuple[bytes, dict[str, str]]:
    """Desfaz ``Content-Encoding`` gzip ou deflate; devolve o corpo e os cabeçalhos ajustados.

    Sem codificação (ou com uma desconhecida, ou com um corpo que não descomprime), devolve
    tudo como veio.
    """
    chave = next((k for k in cabecalhos if k.lower() == "content-encoding"), None)
    codificacao = (cabecalhos.get(chave) or "").strip().lower() if chave else ""
    if codificacao not in _JANELAS or not conteudo:
        return conteudo, cabecalhos
    for janela in _JANELAS[codificacao]:
        try:
            corpo = _descomprimir(conteudo, janela, limite)
        except zlib.error:
            continue
        ajustados = {k: v for k, v in cabecalhos.items() if k.lower() not in ("content-encoding", "content-length")}
        ajustados[CABECALHO_CODIFICACAO_RECEBIDA] = codificacao
        return corpo, ajustados
    return conteudo, cabecalhos


def baixar_http(
    url: str,
    fonte_id: str,
    *,
    user_agent: str,
    timeout: float = TIMEOUT_PADRAO_S,
    limite_bytes: int = LIMITE_PADRAO_BYTES,
    abridor: urllib.request.OpenerDirector | None = None,
    cabecalhos: dict[str, str] | None = None,
) -> ArtefatoBruto:
    """Faz uma requisição GET e devolve o que a fonte respondeu (sem a compressão de transporte).

    ``cabecalhos`` acrescenta cabeçalhos à requisição (``Accept``,
    ``If-None-Match``, ``Range``). Não pode substituir o ``User-Agent``: a
    identificação é obrigatória e única.
    """
    if not user_agent or not user_agent.strip():
        raise ValueError("user_agent é obrigatório: a coleta precisa se identificar")
    extras = dict(cabecalhos or {})
    if any(k.lower() == "user-agent" for k in extras):
        raise ValueError("o User-Agent vem de user_agent; não o sobrescreva por cabecalhos")

    requisicao = urllib.request.Request(
        url,
        headers={"User-Agent": user_agent, "Accept": "*/*", **extras},
        method="GET",
    )
    abridor = abridor or urllib.request.build_opener()
    coletado_em = datetime.now(timezone.utc)

    try:
        resposta = abridor.open(requisicao, timeout=timeout)
    except urllib.error.HTTPError as erro:
        # HTTPError é também uma resposta completa: tem status, cabeçalhos e
        # corpo. É prova de que a fonte respondeu com erro nesta data.
        resposta = erro
    except (urllib.error.URLError, TimeoutError, OSError) as erro:
        raise ErroColeta(f"nenhuma resposta de {url}: {erro}") from erro

    try:
        conteudo = _ler_limitado(resposta, limite_bytes)
        cabecalhos = {k: v for k, v in resposta.headers.items()}
        conteudo, cabecalhos = decodificar_corpo(conteudo, cabecalhos, limite_bytes)
        status = getattr(resposta, "status", None) or resposta.getcode()
        url_efetiva = resposta.geturl() or url
        tipo_midia = resposta.headers.get_content_type() if resposta.headers else "application/octet-stream"
    finally:
        resposta.close()

    return ArtefatoBruto(
        conteudo=conteudo,
        fonte_id=fonte_id,
        url_solicitada=url,
        url_efetiva=url_efetiva,
        status_http=int(status),
        tipo_midia=tipo_midia,
        cabecalhos=cabecalhos,
        coletado_em=coletado_em,
    )
