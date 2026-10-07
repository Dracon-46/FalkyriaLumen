"""Download de arquivos grandes: retomada, validação e manifesto, contra um servidor local."""

from __future__ import annotations

import email.message
import hashlib
import io
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from lumen_eleicoes import transferencia as t

UA = "Lumen/teste (+contato@exemplo.org)"


class Servidor:
    """Serve ``conteudo`` com ETag, Range/If-Range e falhas programáveis."""

    def __init__(self, conteudo: bytes):
        self.conteudo = conteudo
        self.etag = '"v1"'
        self.cortar_em: int | None = None       # fecha a conexão depois de N bytes (uma vez)
        self.ignorar_range = False
        self.falhas_503 = 0
        self.pedidos: list[dict] = []
        servidor = self

        class Tratador(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                servidor.pedidos.append(dict(self.headers))
                if servidor.falhas_503:
                    servidor.falhas_503 -= 1
                    self.send_response(503)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                if self.headers.get("If-None-Match") == servidor.etag:
                    self.send_response(304)
                    self.end_headers()
                    return
                corpo = servidor.conteudo
                faixa = self.headers.get("Range")
                if_range = self.headers.get("If-Range")
                if faixa and not servidor.ignorar_range and (if_range is None or if_range == servidor.etag):
                    inicio = int(faixa.split("=")[1].split("-")[0])
                    if inicio >= len(corpo):
                        self.send_response(416)
                        self.send_header("Content-Range", f"bytes */{len(corpo)}")
                        self.end_headers()
                        return
                    parte = corpo[inicio:]
                    self.send_response(206)
                    self.send_header("Content-Range", f"bytes {inicio}-{len(corpo) - 1}/{len(corpo)}")
                    self.send_header("Content-Length", str(len(parte)))
                else:
                    parte = corpo
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(parte)))
                self.send_header("ETag", servidor.etag)
                self.send_header("Last-Modified", "Mon, 05 Oct 2026 10:00:00 GMT")
                self.end_headers()
                if servidor.cortar_em is not None and servidor.cortar_em < len(parte):
                    self.wfile.write(parte[: servidor.cortar_em])
                    self.wfile.flush()
                    servidor.cortar_em = None
                    self.close_connection = True
                    return
                self.wfile.write(parte)

        self.http = ThreadingHTTPServer(("127.0.0.1", 0), Tratador)
        self.url = f"http://127.0.0.1:{self.http.server_address[1]}/arquivo.zip"
        self.thread = threading.Thread(target=self.http.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        self.thread.start()

    def parar(self):
        self.http.shutdown()
        self.http.server_close()


@pytest.fixture
def conteudo():
    return bytes(range(256)) * 400   # 102.400 bytes


@pytest.fixture
def servidor(conteudo):
    s = Servidor(conteudo)
    yield s
    s.parar()


@pytest.fixture
def abridor():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def baixar(servidor, destino, abridor, **kw):
    return t.baixar_arquivo(servidor.url, destino, user_agent=UA, abridor=abridor, dormir=lambda s: None,
                            bloco=4096, **kw)


def test_download_completo_com_manifesto(servidor, conteudo, tmp_path, abridor):
    destino = tmp_path / "a" / "arquivo.zip"
    m = baixar(servidor, destino, abridor)
    assert destino.read_bytes() == conteudo
    assert m.sha256 == hashlib.sha256(conteudo).hexdigest()
    assert (m.tamanho, m.etag, m.arquivo, m.retomadas) == (len(conteudo), '"v1"', "arquivo.zip", 0)
    assert t.ler_manifesto(destino) == m
    assert t.verificar(destino)
    assert servidor.pedidos[0]["User-Agent"] == UA
    assert not destino.with_name("arquivo.zip.parcial").exists()


def test_arquivo_ja_baixado_nao_vai_a_rede(servidor, tmp_path, abridor):
    destino = tmp_path / "arquivo.zip"
    baixar(servidor, destino, abridor)
    baixar(servidor, destino, abridor)
    assert len(servidor.pedidos) == 1


def test_atualizar_usa_requisicao_condicional(servidor, tmp_path, abridor):
    destino = tmp_path / "arquivo.zip"
    primeiro = baixar(servidor, destino, abridor)
    segundo = baixar(servidor, destino, abridor, atualizar=True)
    assert segundo == primeiro
    assert servidor.pedidos[-1]["If-None-Match"] == '"v1"'


def test_versao_nova_preserva_a_anterior(servidor, conteudo, tmp_path, abridor):
    destino = tmp_path / "arquivo.zip"
    antigo = baixar(servidor, destino, abridor)
    servidor.conteudo = conteudo[::-1]
    servidor.etag = '"v2"'
    novo = baixar(servidor, destino, abridor, atualizar=True)
    assert novo.sha256 != antigo.sha256
    assert destino.read_bytes() == conteudo[::-1]
    guardado = tmp_path / f"arquivo.{antigo.sha256[:12]}.zip"
    assert guardado.read_bytes() == conteudo
    assert t.ler_manifesto(guardado).sha256 == antigo.sha256


def test_versao_nova_sem_preservar(servidor, conteudo, tmp_path, abridor):
    destino = tmp_path / "arquivo.zip"
    baixar(servidor, destino, abridor)
    servidor.conteudo, servidor.etag = conteudo[:1000], '"v2"'
    baixar(servidor, destino, abridor, atualizar=True, preservar_versoes=False)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["arquivo.zip", "arquivo.zip.manifesto.json"]


def test_conexao_cortada_retoma_de_onde_parou(servidor, conteudo, tmp_path, abridor):
    servidor.cortar_em = 30_000
    destino = tmp_path / "arquivo.zip"
    m = baixar(servidor, destino, abridor)
    assert destino.read_bytes() == conteudo
    assert m.retomadas == 1
    assert servidor.pedidos[1]["Range"] == "bytes=30000-"
    assert servidor.pedidos[1]["If-Range"] == '"v1"'


def test_parcial_de_execucao_anterior_e_retomado(servidor, conteudo, tmp_path, abridor):
    servidor.cortar_em = 50_000
    destino = tmp_path / "arquivo.zip"
    with pytest.raises(t.ErroTransferencia):
        baixar(servidor, destino, abridor, tentativas=1)
    assert destino.with_name("arquivo.zip.parcial").stat().st_size == 50_000
    m = baixar(servidor, destino, abridor)
    assert destino.read_bytes() == conteudo and m.retomadas == 1


def test_arquivo_mudou_no_meio_recomeca_do_zero(servidor, conteudo, tmp_path, abridor):
    servidor.cortar_em = 10_000
    destino = tmp_path / "arquivo.zip"
    with pytest.raises(t.ErroTransferencia):
        baixar(servidor, destino, abridor, tentativas=1)
    servidor.conteudo, servidor.etag = conteudo[::-1], '"v2"'   # If-Range não confere: 200 inteiro
    baixar(servidor, destino, abridor)
    assert destino.read_bytes() == conteudo[::-1]


def test_servidor_sem_range_recomeca(servidor, conteudo, tmp_path, abridor):
    servidor.cortar_em = 10_000
    servidor.ignorar_range = True
    destino = tmp_path / "arquivo.zip"
    baixar(servidor, destino, abridor)
    assert destino.read_bytes() == conteudo


def test_parcial_completo_recebe_416_e_recomeca(servidor, conteudo, tmp_path, abridor):
    destino = tmp_path / "arquivo.zip"
    parcial = destino.with_name("arquivo.zip.parcial")
    parcial.write_bytes(conteudo)
    destino.with_name("arquivo.zip.parcial.json").write_text(
        '{"url": "%s", "etag": "\\"v1\\"", "ultima_modificacao": null, "recebidos": 0, "retomadas": 0}'
        % servidor.url)
    baixar(servidor, destino, abridor)
    assert destino.read_bytes() == conteudo


def test_parcial_sem_estado_e_descartado(servidor, conteudo, tmp_path, abridor):
    destino = tmp_path / "arquivo.zip"
    destino.with_name("arquivo.zip.parcial").write_bytes(b"lixo")
    baixar(servidor, destino, abridor)
    assert destino.read_bytes() == conteudo


def test_503_passageiro_e_retentado(servidor, conteudo, tmp_path, abridor):
    servidor.falhas_503 = 2
    destino = tmp_path / "arquivo.zip"
    baixar(servidor, destino, abridor)
    assert destino.read_bytes() == conteudo


def test_503_persistente_falha(servidor, tmp_path, abridor):
    servidor.falhas_503 = 10
    with pytest.raises(t.ErroTransferencia):
        baixar(servidor, tmp_path / "x.zip", abridor, tentativas=3)


def test_404_falha_na_hora(tmp_path):
    abridor = urllib.request.build_opener(urllib.request.ProxyHandler({}), _Responde404())
    with pytest.raises(t.ErroTransferencia, match="HTTP 404"):
        t.baixar_arquivo("http://127.0.0.1:9/nao-existe.zip", tmp_path / "y.zip", user_agent=UA,
                         abridor=abridor, dormir=lambda s: None)


class _Responde404(urllib.request.BaseHandler):
    handler_order = 100

    def http_open(self, req):
        return urllib.request.addinfourl(io.BytesIO(b""), email.message.Message(), req.full_url, 404)

    def http_response(self, req, resposta):
        raise urllib.error.HTTPError(req.full_url, 404, "Not Found", resposta.headers, io.BytesIO(b""))


def test_sem_resposta_falha_depois_das_tentativas(tmp_path, abridor):
    with pytest.raises(t.ErroTransferencia):
        t.baixar_arquivo("http://127.0.0.1:9/x.zip", tmp_path / "x.zip", user_agent=UA, abridor=abridor,
                         tentativas=2, dormir=lambda s: None, timeout=1)


def test_progresso_e_identificacao(servidor, conteudo, tmp_path, abridor):
    vistos = []
    baixar(servidor, tmp_path / "p.zip", abridor, progresso=lambda r, total: vistos.append((r, total)))
    assert vistos[-1] == (len(conteudo), len(conteudo))
    with pytest.raises(ValueError):
        t.baixar_arquivo(servidor.url, tmp_path / "q.zip", user_agent=" ")


def test_verificar_detecta_adulteracao(servidor, tmp_path, abridor):
    destino = tmp_path / "arquivo.zip"
    baixar(servidor, destino, abridor)
    dados = bytearray(destino.read_bytes())
    dados[10] ^= 0xFF
    destino.write_bytes(bytes(dados))
    assert not t.verificar(destino)
    assert not t.verificar(tmp_path / "inexistente.zip")


def test_content_range_auxiliares():
    assert t._total_do_content_range("bytes 0-9/100") == 100
    assert t._total_do_content_range("bytes */100") == 100
    assert t._total_do_content_range("bytes 0-9/*") is None
    assert t._total_do_content_range(None) is None
    assert t._inicio_do_content_range("bytes 30-99/100") == 30
    assert t._inicio_do_content_range("lixo") is None
