"""Servidor local do portal: o site estático e os feeds, numa porta só.

Para uso em máquina própria (``lumen eleicoes servir``) e nos testes de
ponta a ponta. Em produção, o mesmo diretório vai para qualquer servidor de
arquivos estáticos ou CDN; nada aqui é necessário.

- ``/dados/eleicoes/...`` vem do diretório dos feeds, com
  ``Cache-Control: no-cache`` (o navegador revalida a cada consulta, e é
  isso que faz o "ao vivo" funcionar sem WebSocket).
- O resto vem do site exportado (``packages/portal/out``); arquivos com hash
  no nome (``/_next/static``) levam cache longo.
- Caminhos são resolvidos dentro do diretório servido: ``..`` não sai dele.
"""

from __future__ import annotations

import posixpath
import threading
import urllib.parse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PREFIXO_FEEDS = "/dados/eleicoes/"


class _Tratador(SimpleHTTPRequestHandler):
    """Tratador HTTP que serve o site e os feeds, cada um do seu diretório, com tipos e cache próprios."""

    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, ".json": "application/json; charset=utf-8",
                      ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
                      ".svg": "image/svg+xml", ".webmanifest": "application/manifest+json"}

    def __init__(self, *args, site: Path, feeds: Path, **kwargs):
        """Guarda os dois diretórios; o do site é o diretório padrão do ``SimpleHTTPRequestHandler``."""
        self.site = site
        self.feeds = feeds
        super().__init__(*args, directory=str(site), **kwargs)

    def log_message(self, *a):  # silencioso; o CLI mostra o endereço
        """Descarta o log por requisição do ``http.server``."""
        pass

    def translate_path(self, path: str) -> str:
        """Converte o caminho da URL em arquivo local, dentro do diretório dos feeds ou do site.

        Depois de normalizar o caminho, os segmentos ``.`` e ``..`` são descartados, de modo que nenhuma URL
        resolve para fora do diretório servido; a conferência contra os diretórios-pai do alvo é uma segunda
        barreira. Caminho sem extensão que não existe é servido como ``.html``, como nas rotas do site
        exportado.
        """
        caminho = urllib.parse.unquote(urllib.parse.urlsplit(path).path)
        if caminho.startswith(PREFIXO_FEEDS):
            base, resto = self.feeds, caminho[len(PREFIXO_FEEDS):]
        else:
            base, resto = self.site, caminho.lstrip("/")
        partes = [p for p in posixpath.normpath("/" + resto).split("/") if p and p not in (".", "..")]
        alvo = base.joinpath(*partes) if partes else base
        if base not in (alvo, *alvo.parents):  # pragma: no cover - normpath já impede
            return str(base / "__fora__")
        if not alvo.exists() and alvo.suffix == "" and alvo.with_suffix(".html").exists():
            return str(alvo.with_suffix(".html"))
        return str(alvo)

    def end_headers(self) -> None:
        """Acrescenta os cabeçalhos de cache e o ``nosniff`` antes de encerrar os cabeçalhos da resposta.

        Feeds levam ``no-cache`` (o navegador revalida a cada consulta, o que mantém o "ao vivo"); arquivos
        de ``/_next/static`` têm hash no nome e levam cache longo e imutável.
        """
        caminho = urllib.parse.urlsplit(self.path).path
        if caminho.startswith(PREFIXO_FEEDS):
            self.send_header("Cache-Control", "no-cache")
        elif caminho.startswith("/_next/static/"):
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()


class ServidorPortal:
    """Servidor HTTP do portal, para o CLI e os testes de ponta a ponta.

    Funciona como gerenciador de contexto (``with``), atendendo numa thread à parte. Com ``porta=0`` o
    sistema escolhe uma porta livre, e ``endereco`` traz a porta efetiva.
    """

    def __init__(self, site: Path | str, feeds: Path | str, *, host: str = "127.0.0.1", porta: int = 8080):
        """Resolve os diretórios e abre o socket já na construção; o atendimento só começa com ``iniciar`` ou
        ``servir_para_sempre``."""
        self.site = Path(site).resolve()
        self.feeds = Path(feeds).resolve()
        self.http = ThreadingHTTPServer((host, porta), partial(_Tratador, site=self.site, feeds=self.feeds))
        self.endereco = f"http://{host}:{self.http.server_address[1]}"
        self._thread: threading.Thread | None = None

    def servir_para_sempre(self) -> None:  # pragma: no cover - laço do CLI
        """Atende na thread atual até ser interrompido (uso do CLI)."""
        self.http.serve_forever()

    def iniciar(self) -> "ServidorPortal":
        """Atende numa thread daemon e devolve o próprio servidor.

        O intervalo de verificação curto (50 ms) faz ``parar`` responder logo.
        """
        self._thread = threading.Thread(target=self.http.serve_forever, kwargs={"poll_interval": 0.05},
                                        daemon=True)
        self._thread.start()
        return self

    def parar(self) -> None:
        """Encerra o laço de atendimento e fecha o socket."""
        self.http.shutdown()
        self.http.server_close()

    def __enter__(self) -> "ServidorPortal":
        """Inicia o servidor ao entrar no bloco ``with``."""
        return self.iniciar()

    def __exit__(self, *exc) -> None:
        """Para o servidor ao sair do bloco ``with``, com ou sem exceção."""
        self.parar()
