"""Download de arquivos grandes com retomada e manifesto (ADR-021).

Os arquivos de dados abertos do TSE têm de dezenas de megabytes a vários
gigabytes (``votacao_candidato_munzona_2022.zip``: 642 MB compactado, mais de
4 GB descompactado). A camada bronze guarda o conteúdo em memória e é feita
para respostas de API; esses arquivos ficam fora dela, num diretório próprio,
e o que entra no bronze é o **manifesto**: URL, tamanho, SHA-256, cabeçalhos
de versão e instante do download. A prova continua verificável — o hash do
manifesto confere o arquivo —, sem carregar gigabytes na memória.

Como funciona
-------------
1. O download vai para ``<destino>.parcial``, com o estado em
   ``<destino>.parcial.json`` (URL, ETag, Last-Modified, bytes recebidos).
2. Se a conexão cai, a próxima tentativa pede só o que falta
   (``Range: bytes=N-``) com ``If-Range``: se o arquivo mudou no servidor
   entre as tentativas, o servidor responde 200 com o arquivo inteiro e o
   download recomeça do zero — nunca se emendam pedaços de versões diferentes.
3. No fim, o tamanho é conferido contra ``Content-Length``/``Content-Range``,
   o SHA-256 é calculado, e o arquivo é renomeado para o nome final com o
   manifesto ao lado (``<destino>.manifesto.json``), ambos por troca atômica.
4. Com ``atualizar=True`` e o arquivo já completo, a requisição é condicional
   (``If-None-Match``/``If-Modified-Since``): 304 mantém o que existe. Se veio
   versão nova e ``preservar_versoes`` está ligado, a anterior é renomeada
   com o prefixo do próprio hash em vez de apagada.

Identificação obrigatória (princípio P6): não há User-Agent padrão.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

log = logging.getLogger("lumen.eleicoes.transferencia")

BLOCO = 1024 * 1024


class ErroTransferencia(Exception):
    """O download não pôde ser concluído; o parcial fica para a próxima tentativa.

    ``status`` é o HTTP da resposta que encerrou o download (404 quando o arquivo não existe na fonte),
    ou None quando o servidor não respondeu.
    """

    def __init__(self, mensagem: str, status: int | None = None):
        """Mensagem para o operador e, quando houve resposta, o HTTP final."""
        super().__init__(mensagem)
        self.status = status


@dataclass(frozen=True)
class Manifesto:
    """Registro de um arquivo baixado: de onde veio, tamanho, SHA-256 e cabeçalhos de versão.

    Fica ao lado do arquivo (``<destino>.manifesto.json``) e é o que vai para o bronze no lugar do
    conteúdo; o hash permite reconferir o arquivo depois (``verificar``). ``retomadas`` conta quantas
    vezes o download continuou de onde tinha parado.
    """

    url: str
    arquivo: str                    # nome do arquivo, relativo ao diretório do manifesto
    tamanho: int
    sha256: str
    etag: str | None
    ultima_modificacao: str | None
    baixado_em: str                 # ISO 8601 em UTC
    retomadas: int = 0

    def para_json(self) -> str:
        """Texto JSON do manifesto, indentado e com as chaves em ordem alfabética."""
        return json.dumps(asdict(self), ensure_ascii=False, indent=2, sort_keys=True)

    @classmethod
    def de_json(cls, texto: str) -> "Manifesto":
        """Reconstrói o manifesto a partir do texto gravado por ``para_json``."""
        return cls(**json.loads(texto))


def caminho_manifesto(destino: Path) -> Path:
    """Caminho do manifesto de ``destino``: o mesmo nome com ``.manifesto.json`` acrescentado."""
    return destino.with_name(destino.name + ".manifesto.json")


def ler_manifesto(destino: Path) -> Manifesto | None:
    """Manifesto gravado ao lado de ``destino``, ou None se não houver."""
    caminho = caminho_manifesto(destino)
    if not caminho.exists():
        return None
    return Manifesto.de_json(caminho.read_text(encoding="utf-8"))


def sha256_arquivo(caminho: Path, bloco: int = BLOCO) -> str:
    """SHA-256 em hexadecimal, lido em blocos para não carregar o arquivo inteiro na memória."""
    h = hashlib.sha256()
    with open(caminho, "rb") as fh:
        while True:
            parte = fh.read(bloco)
            if not parte:
                break
            h.update(parte)
    return h.hexdigest()


def _gravar_atomico(caminho: Path, texto: str) -> None:
    """Grava texto por troca atômica (``.tmp`` e ``os.replace``): quem lê vê o arquivo antigo ou o novo,
    nunca pela metade."""
    tmp = caminho.with_name(caminho.name + ".tmp")
    tmp.write_text(texto, encoding="utf-8")
    os.replace(tmp, caminho)


def _total_do_content_range(valor: str | None) -> int | None:
    """Tamanho total do arquivo segundo o ``Content-Range``; None se ausente ou desconhecido (``*``)."""
    # "bytes 100-199/1000" → 1000; "bytes */1000" → 1000; total "*" → None
    if not valor or "/" not in valor:
        return None
    total = valor.rsplit("/", 1)[1].strip()
    return int(total) if total.isdigit() else None


def _inicio_do_content_range(valor: str | None) -> int | None:
    """Primeiro byte da faixa do ``Content-Range`` (``"bytes 100-199/1000"`` → 100); None se não der para ler."""
    if not valor:
        return None
    try:
        faixa = valor.split()[1].split("/")[0]
        return int(faixa.split("-")[0])
    except (IndexError, ValueError):
        return None


@dataclass
class _Estado:
    """Estado de um download em andamento, gravado em ``<destino>.parcial.json`` ao lado do parcial.

    Guarda a URL e os validadores (ETag, Last-Modified) da versão que está sendo baixada: a retomada pede
    só o que falta com ``If-Range`` e nunca emenda pedaços de versões diferentes.
    """

    url: str
    etag: str | None = None
    ultima_modificacao: str | None = None
    recebidos: int = 0
    retomadas: int = 0


def baixar_arquivo(
    url: str,
    destino: Path | str,
    *,
    user_agent: str,
    abridor: urllib.request.OpenerDirector | None = None,
    timeout: float = 120,
    tentativas: int = 5,
    espera_base_s: float = 5.0,
    dormir: Callable[[float], None] = time.sleep,
    atualizar: bool = False,
    preservar_versoes: bool = True,
    progresso: Callable[[int, int | None], None] | None = None,
    bloco: int = BLOCO,
) -> Manifesto:
    """Baixa ``url`` para ``destino`` e devolve o manifesto do arquivo completo."""
    if not user_agent or not user_agent.strip():
        raise ValueError("user_agent é obrigatório: a coleta precisa se identificar")
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    abridor = abridor or urllib.request.build_opener()

    existente = ler_manifesto(destino) if destino.exists() else None
    if existente and existente.url == url and not atualizar:
        return existente

    parcial = destino.with_name(destino.name + ".parcial")
    estado_arq = destino.with_name(destino.name + ".parcial.json")
    estado = _Estado(url=url)
    if parcial.exists() and estado_arq.exists():
        anterior = _Estado(**json.loads(estado_arq.read_text(encoding="utf-8")))
        if anterior.url == url:
            estado = anterior
            estado.recebidos = parcial.stat().st_size
        else:
            parcial.unlink()
    elif parcial.exists():
        parcial.unlink()  # parcial sem estado: não se sabe de que versão é

    ultimo_erro: Exception | None = None
    for tentativa in range(1, tentativas + 1):
        cab = {"User-Agent": user_agent, "Accept": "*/*"}
        if estado.recebidos:
            cab["Range"] = f"bytes={estado.recebidos}-"
            validador = estado.etag or estado.ultima_modificacao
            if validador:
                cab["If-Range"] = validador
        elif existente and existente.url == url:
            if existente.etag:
                cab["If-None-Match"] = existente.etag
            if existente.ultima_modificacao:
                cab["If-Modified-Since"] = existente.ultima_modificacao
        req = urllib.request.Request(url, headers=cab, method="GET")
        try:
            resposta = abridor.open(req, timeout=timeout)
        except urllib.error.HTTPError as erro:
            if erro.code == 304 and existente:
                erro.close()
                return existente
            if erro.code == 416 and estado.recebidos:
                # O parcial já tem o tamanho do arquivo (ou o servidor mudou):
                # recomeça do zero na próxima volta, sem gastar tentativa.
                erro.close()
                parcial.unlink(missing_ok=True)
                estado = _Estado(url=url)
                continue
            erro.close()
            if erro.code in (429, 500, 502, 503, 504) and tentativa < tentativas:
                ultimo_erro = erro
                dormir(espera_base_s * 2 ** (tentativa - 1))
                continue
            raise ErroTransferencia(f"{url}: HTTP {erro.code}", status=erro.code) from erro
        except (urllib.error.URLError, TimeoutError, OSError) as erro:
            ultimo_erro = erro
            if tentativa < tentativas:
                dormir(espera_base_s * 2 ** (tentativa - 1))
                continue
            raise ErroTransferencia(f"{url}: sem resposta ({erro})") from erro

        with resposta:
            status = resposta.status
            cabecalhos = {k.lower(): v for k, v in resposta.headers.items()}
            if status == 206:
                inicio = _inicio_do_content_range(cabecalhos.get("content-range"))
                if inicio != estado.recebidos:
                    raise ErroTransferencia(f"{url}: Content-Range inesperado {cabecalhos.get('content-range')}")
                total = _total_do_content_range(cabecalhos.get("content-range"))
                modo = "ab"
                estado.retomadas += 1
            else:
                # 200: arquivo inteiro (primeira vez, servidor sem Range, ou
                # versão nova no servidor — If-Range falhou).
                estado = _Estado(url=url, etag=cabecalhos.get("etag"),
                                 ultima_modificacao=cabecalhos.get("last-modified"),
                                 retomadas=estado.retomadas)
                comprimento = cabecalhos.get("content-length")
                total = int(comprimento) if comprimento and comprimento.isdigit() else None
                modo = "wb"
            _gravar_atomico(estado_arq, json.dumps(asdict(estado)))
            try:
                with open(parcial, modo) as fh:
                    while True:
                        parte = resposta.read(bloco)
                        if not parte:
                            break
                        fh.write(parte)
                        estado.recebidos = fh.tell()
                        if progresso:
                            progresso(estado.recebidos, total)
                    fh.flush()
                    os.fsync(fh.fileno())
            except (OSError, TimeoutError) as erro:
                ultimo_erro = erro
                estado.recebidos = parcial.stat().st_size if parcial.exists() else 0
                _gravar_atomico(estado_arq, json.dumps(asdict(estado)))
                log.info("transferencia_interrompida", extra={"url": url, "recebidos": estado.recebidos})
                if tentativa < tentativas:
                    dormir(espera_base_s * 2 ** (tentativa - 1))
                    continue
                raise ErroTransferencia(f"{url}: conexão interrompida em {estado.recebidos} bytes") from erro

        tamanho = parcial.stat().st_size
        if total is not None and tamanho != total:
            _gravar_atomico(estado_arq, json.dumps(asdict(estado)))
            ultimo_erro = ErroTransferencia(f"{url}: recebidos {tamanho} de {total} bytes")
            if tentativa < tentativas:
                continue
            raise ultimo_erro

        sha = sha256_arquivo(parcial)
        if destino.exists():
            if existente and existente.sha256 == sha:
                parcial.unlink()
                estado_arq.unlink(missing_ok=True)
                return existente
            if preservar_versoes:
                antigo_sha = existente.sha256 if existente else sha256_arquivo(destino)
                guardado = destino.with_name(f"{destino.stem}.{antigo_sha[:12]}{destino.suffix}")
                os.replace(destino, guardado)
                if existente:
                    _gravar_atomico(caminho_manifesto(guardado),
                                    Manifesto(**{**asdict(existente), "arquivo": guardado.name}).para_json())
        os.replace(parcial, destino)
        estado_arq.unlink(missing_ok=True)
        manifesto = Manifesto(
            url=url, arquivo=destino.name, tamanho=tamanho, sha256=sha, etag=estado.etag,
            ultima_modificacao=estado.ultima_modificacao,
            baixado_em=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            retomadas=estado.retomadas,
        )
        _gravar_atomico(caminho_manifesto(destino), manifesto.para_json())
        return manifesto
    raise ErroTransferencia(f"{url}: tentativas esgotadas ({ultimo_erro})")


def verificar(destino: Path | str) -> bool:
    """Reconfere o arquivo contra o próprio manifesto."""
    destino = Path(destino)
    manifesto = ler_manifesto(destino)
    if manifesto is None or not destino.exists():
        return False
    return destino.stat().st_size == manifesto.tamanho and sha256_arquivo(destino) == manifesto.sha256
