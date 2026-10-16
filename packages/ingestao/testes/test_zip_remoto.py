"""Leitura de um arquivo de dentro de um ZIP remoto por ``Range``, contra um servidor local."""

import io
import re
import struct
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from lumen_ingestao import zip_remoto
from lumen_ingestao.cliente_http import ClienteHttp
from lumen_ingestao.coleta_http import user_agent_lumen
from lumen_ingestao.zip_remoto import ErroZipRemoto, baixar_membro, descomprimir, entradas, ler_diretorio

UA = user_agent_lumen("0.8.0", "contato@exemplo.org")
CONTEUDO = "linha de teste com acentuação: São Sepé\n".encode() * 300


def _zip(*, armazenado=False, muitos=0, comentario=b""):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("grande/enchimento.bin", bytes(range(256)) * 400, zipfile.ZIP_STORED)
        for i in range(muitos):
            z.writestr(f"respostas/{'x' * 120}_{i:05d}.txt", "", zipfile.ZIP_STORED)
        z.writestr("pntp_2025/avaliacoes.xlsx", CONTEUDO, zipfile.ZIP_STORED if armazenado else zipfile.ZIP_DEFLATED)
        z.comment = comentario
    return b.getvalue()


class _Servidor(BaseHTTPRequestHandler):
    corpo = b""
    aceita_range = True
    faixas: list = []

    def log_message(self, *a):
        pass

    def do_GET(self):
        corpo = _Servidor.corpo
        faixa = self.headers.get("Range")
        if not faixa or not _Servidor.aceita_range:
            self.send_response(200)
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            self.wfile.write(corpo)
            return
        _Servidor.faixas.append(faixa)
        m = re.fullmatch(r"bytes=(\d*)-(\d*)", faixa)
        if m.group(1) == "":
            inicio, fim = max(0, len(corpo) - int(m.group(2))), len(corpo) - 1
        else:
            inicio = int(m.group(1))
            fim = min(int(m.group(2)) if m.group(2) else len(corpo) - 1, len(corpo) - 1)
        parte = corpo[inicio:fim + 1]
        self.send_response(206)
        self.send_header("Content-Range", f"bytes {inicio}-{fim}/{len(corpo)}")
        self.send_header("Content-Length", str(len(parte)))
        self.send_header("ETag", '"abc"')
        self.send_header("Last-Modified", "Tue, 10 Feb 2026 13:35:32 GMT")
        self.end_headers()
        self.wfile.write(parte)


@pytest.fixture
def srv():
    _Servidor.aceita_range = True
    _Servidor.faixas = []
    s = ThreadingHTTPServer(("127.0.0.1", 0), _Servidor)
    threading.Thread(target=lambda: s.serve_forever(poll_interval=0.05), daemon=True).start()
    yield f"http://127.0.0.1:{s.server_address[1]}/dados.zip"
    s.shutdown()


def _cliente(sem_proxy):
    return ClienteHttp("pntp_avaliacoes", user_agent=UA, rpm=6000, abridor=sem_proxy, dormir=lambda s: None)


@pytest.mark.parametrize("armazenado", [False, True])
def test_baixa_so_o_arquivo_pedido(srv, sem_proxy, armazenado):
    _Servidor.corpo = _zip(armazenado=armazenado, comentario=b"comentario do zip")
    m = baixar_membro(_cliente(sem_proxy), srv, "pntp_2025/avaliacoes.xlsx")
    assert m.conteudo == CONTEUDO
    assert m.tamanho_do_zip == len(_Servidor.corpo) and m.etag == '"abc"' and m.ultima_modificacao
    assert m.entrada.metodo == (0 if armazenado else 8)
    assert len(_Servidor.faixas) == 2   # o fim (com o diretório central) e o arquivo; o enchimento não vem


def test_diretorio_central_fora_do_fim_lido_pede_mais_uma_faixa(srv, sem_proxy):
    _Servidor.corpo = _zip(muitos=600)  # diretório central maior que os 64 KB do fim
    m = baixar_membro(_cliente(sem_proxy), srv, "pntp_2025/avaliacoes.xlsx")
    assert m.conteudo == CONTEUDO and len(_Servidor.faixas) == 3


def test_arquivo_inexistente_e_servidor_sem_range(srv, sem_proxy):
    _Servidor.corpo = _zip()
    with pytest.raises(ErroZipRemoto, match="não tem"):
        baixar_membro(_cliente(sem_proxy), srv, "outro.xlsx")
    _Servidor.aceita_range = False
    with pytest.raises(ErroZipRemoto, match="esperado 206"):
        baixar_membro(_cliente(sem_proxy), srv, "pntp_2025/avaliacoes.xlsx")


def test_cabecalho_local_ausente(srv, sem_proxy, monkeypatch):
    _Servidor.corpo = _zip()
    original = zip_remoto.entradas
    monkeypatch.setattr(zip_remoto, "entradas", lambda d: [
        zip_remoto.EntradaZip(e.nome, e.metodo, e.crc32, e.tamanho_comprimido, e.tamanho, e.deslocamento + 7)
        for e in original(d)])
    with pytest.raises(ErroZipRemoto, match="cabeçalho local"):
        baixar_membro(_cliente(sem_proxy), srv, "pntp_2025/avaliacoes.xlsx")


def test_descomprimir_confere_crc_e_metodo():
    e = zip_remoto.EntradaZip("a", 0, 0, 3, 3, 0)
    with pytest.raises(ErroZipRemoto, match="CRC-32"):
        descomprimir(e, b"abc")
    with pytest.raises(ErroZipRemoto, match="método"):
        descomprimir(zip_remoto.EntradaZip("a", 12, 0, 3, 3, 0), b"abc")


def test_fim_do_zip_invalido_ou_zip64():
    with pytest.raises(ErroZipRemoto, match="fim do ZIP"):
        ler_diretorio(b"isto nao e zip")
    zip64 = b"PK\x05\x06" + struct.pack("<HHHHIIH", 0, 0, 0xFFFF, 0xFFFF, 0, 0xFFFFFFFF, 0)
    with pytest.raises(ErroZipRemoto, match="ZIP64"):
        ler_diretorio(zip64)


def test_entradas_le_nomes_utf8():
    corpo = _zip()
    _, tamanho, deslocamento = ler_diretorio(corpo[-65558:])
    nomes = [e.nome for e in entradas(corpo[deslocamento:deslocamento + tamanho])]
    assert nomes == ["grande/enchimento.bin", "pntp_2025/avaliacoes.xlsx"]
