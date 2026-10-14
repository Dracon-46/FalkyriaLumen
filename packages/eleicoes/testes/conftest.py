"""Fixtures da aba Eleições compartilhadas entre os módulos de teste."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from lumen_eleicoes import antigas

FIX_UF = Path(__file__).resolve().parents[3] / "testes" / "fixtures" / "tse" / "dados_abertos_uf"


def _zips_do_ano(pasta: Path, ano: int) -> list[Path | None]:
    """ZIPs dos três conjuntos por UF do ano, montados das fixtures com os nomes da fonte (None se não há
    recorte do conjunto)."""
    caminhos: list[Path | None] = []
    sufixo = "_br" if ano in (1933, 1934) else ""
    for conjunto in antigas.CONJUNTOS_UF:
        recorte = FIX_UF / f"{conjunto}_{ano}{sufixo}_recorte.txt"
        if not recorte.exists():
            caminhos.append(None)
            continue
        destino = pasta / antigas.nome_arquivo_uf(conjunto, ano)
        destino.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(destino, "w") as zf:
            zf.writestr(f"{conjunto.upper()}_{ano}/{conjunto.upper()}_{ano}.txt", recorte.read_bytes())
        caminhos.append(destino)
    return caminhos


@pytest.fixture
def zips_antigos():
    """Função ``(pasta, ano) -> [candidato, detalhe, partido]`` que monta os ZIPs antigos das fixtures."""
    return _zips_do_ano


class _S3Memoria:
    """Servidor S3 mínimo em memória (estilo caminho): PUT, GET, HEAD e ListObjectsV2.

    Guarda, por bucket e chave, o corpo e os cabeçalhos recebidos (``content-type``, ``cache-control``),
    para os testes conferirem o que a publicação mandou. Não confere assinatura: isso é coberto pelos
    testes do cliente (``packages/ingestao/testes/test_s3.py``).
    """

    def __init__(self):
        import threading
        import urllib.parse
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from xml.sax.saxutils import escape

        self.objetos: dict[tuple[str, str], tuple[bytes, dict[str, str]]] = {}
        self.puts: list[tuple[str, str]] = []
        objetos, puts = self.objetos, self.puts

        class T(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _partes(self):
                u = urllib.parse.urlsplit(self.path)
                bucket, _, chave = urllib.parse.unquote(u.path).lstrip("/").partition("/")
                return bucket, chave, dict(urllib.parse.parse_qsl(u.query))

            def _resp(self, status, corpo=b"", cab=None):
                self.send_response(status)
                for k, v in (cab or {}).items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(corpo)))
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(corpo)

            def do_PUT(self):
                bucket, chave, _ = self._partes()
                corpo = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                if self.headers.get("If-None-Match") == "*" and (bucket, chave) in objetos:
                    return self._resp(412)
                objetos[(bucket, chave)] = (corpo, {k.lower(): v for k, v in self.headers.items()})
                puts.append((bucket, chave))
                self._resp(200)

            def do_GET(self):
                bucket, chave, q = self._partes()
                if not chave and q.get("list-type") == "2":
                    prefixo = q.get("prefix", "")
                    chaves = sorted(c for b, c in objetos if b == bucket and c.startswith(prefixo))
                    itens = "".join(f"<Contents><Key>{escape(c)}</Key></Contents>" for c in chaves)
                    xml = (f'<?xml version="1.0"?><ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
                           f"{itens}<IsTruncated>false</IsTruncated></ListBucketResult>").encode()
                    return self._resp(200, xml)
                if (bucket, chave) not in objetos:
                    return self._resp(404, b"<Error><Code>NoSuchKey</Code></Error>")
                corpo, cab = objetos[(bucket, chave)]
                self._resp(200, corpo, {"Content-Type": cab.get("content-type", "")})

            def do_HEAD(self):
                bucket, chave, _ = self._partes()
                self._resp(200 if (bucket, chave) in objetos else 404)

        class Servidor(ThreadingHTTPServer):
            request_queue_size = 64   # a publicação envia vários arquivos ao mesmo tempo

        self.http = Servidor(("127.0.0.1", 0), T)
        self.endpoint = f"http://127.0.0.1:{self.http.server_address[1]}"
        threading.Thread(target=self.http.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()

    def corpo(self, bucket: str, chave: str) -> bytes:
        """Conteúdo guardado de uma chave."""
        return self.objetos[(bucket, chave)][0]

    def chaves(self, bucket: str) -> list[str]:
        """Chaves de um bucket, em ordem."""
        return sorted(c for b, c in self.objetos if b == bucket)

    def parar(self):
        self.http.shutdown()
        self.http.server_close()


@pytest.fixture
def s3_memoria():
    """Servidor S3 em memória para os testes de publicação na nuvem."""
    srv = _S3Memoria()
    yield srv
    srv.parar()
