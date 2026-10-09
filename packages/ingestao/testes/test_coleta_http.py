"""Testes da coleta HTTP contra um servidor local de verdade.

O servidor sobe em 127.0.0.1 dentro do próprio teste: é uma requisição HTTP
real, com redirecionamento, cabeçalhos e códigos de erro reais, sem depender
de rede externa.
"""

import gzip
import threading
import urllib.request
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from lumen_ingestao.coleta_http import (
    CABECALHO_CODIFICACAO_RECEBIDA,
    ConteudoGrandeDemais,
    ErroColeta,
    baixar_http,
    decodificar_corpo,
    user_agent_lumen,
)

UA = user_agent_lumen("0.1.0", "contato@exemplo.org")


class _Portal(BaseHTTPRequestHandler):
    """Simula um portal de transparência com seus comportamentos típicos."""

    user_agents_recebidos: list[str] = []

    def log_message(self, *args):  # silencia o log do servidor nos testes
        pass

    def do_GET(self):
        _Portal.user_agents_recebidos.append(self.headers.get("User-Agent", ""))
        if self.path == "/contratos":
            corpo = b'{"contratos": [{"numero": "12/2026", "valor": "48000.00"}]}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("ETag", '"v1"')
            self.send_header("Set-Cookie", "JSESSIONID=segredo")
            self.end_headers()
            self.wfile.write(corpo)
        elif self.path == "/antigo":
            self.send_response(302)
            self.send_header("Location", "/contratos")
            self.end_headers()
        elif self.path == "/grande":
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.end_headers()
            self.wfile.write(b"x" * 5000)
        elif self.path in ("/gzip", "/bomba", "/quebrado"):
            # como a API do IBGE: comprimido mesmo sem o pedido pedir
            corpo = {"/gzip": gzip.compress(b'[{"id": 12, "nome": "Acre"}]'),
                     "/bomba": gzip.compress(b"0" * 100_000),
                     "/quebrado": b"\x1f\x8b nao e gzip"}[self.path]
            self.send_response(200)
            self.send_header("Content-Type", "application/json;charset=UTF-8")
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            self.wfile.write(corpo)
        elif self.path == "/manutencao":
            self.send_response(503)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h1>Em manutencao</h1>")
        else:
            self.send_response(404)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h1>Pagina nao encontrada</h1>")


@pytest.fixture(scope="module")
def portal():
    servidor = ThreadingHTTPServer(("127.0.0.1", 0), _Portal)
    thread = threading.Thread(target=servidor.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{servidor.server_address[1]}"
    servidor.shutdown()


@pytest.fixture
def sem_proxy():
    """Garante acesso direto ao servidor local, ignorando proxy do ambiente."""
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def test_coleta_resposta_bem_sucedida(portal, sem_proxy):
    art = baixar_http(f"{portal}/contratos", "pncp", user_agent=UA, abridor=sem_proxy)
    assert art.status_http == 200
    assert art.tipo_midia == "application/json"
    assert b'"12/2026"' in art.conteudo
    assert art.coletado_em.tzinfo is not None


def test_registra_url_efetiva_apos_redirecionamento(portal, sem_proxy):
    art = baixar_http(f"{portal}/antigo", "pncp", user_agent=UA, abridor=sem_proxy)
    assert art.url_solicitada.endswith("/antigo")
    assert art.url_efetiva.endswith("/contratos")
    assert art.status_http == 200


def test_404_volta_como_artefato_e_nao_como_excecao(portal, sem_proxy):
    """Princípio P5: a ausência de publicação é um achado, com prova."""
    art = baixar_http(f"{portal}/nao-existe", "pncp", user_agent=UA, abridor=sem_proxy)
    assert art.status_http == 404
    assert b"nao encontrada" in art.conteudo


def test_503_tambem_e_preservado(portal, sem_proxy):
    """Distinguir temporário de persistente é tarefa da conformidade, não daqui."""
    art = baixar_http(f"{portal}/manutencao", "pncp", user_agent=UA, abridor=sem_proxy)
    assert art.status_http == 503


def test_envia_a_identificacao_do_projeto(portal, sem_proxy):
    _Portal.user_agents_recebidos.clear()
    baixar_http(f"{portal}/contratos", "pncp", user_agent=UA, abridor=sem_proxy)
    assert _Portal.user_agents_recebidos == [UA]
    assert "Lumen/0.1.0" in UA and "contato@exemplo.org" in UA


def test_sem_user_agent_recusa_coletar(portal, sem_proxy):
    with pytest.raises(ValueError):
        baixar_http(f"{portal}/contratos", "pncp", user_agent="  ", abridor=sem_proxy)


def test_respeita_limite_de_tamanho(portal, sem_proxy):
    with pytest.raises(ConteudoGrandeDemais):
        baixar_http(f"{portal}/grande", "pncp", user_agent=UA, limite_bytes=1000,
                    abridor=sem_proxy)


def test_sem_resposta_levanta_erro_de_coleta(sem_proxy):
    # porta 9 (discard) em localhost: conexão recusada, nada recebido
    with pytest.raises(ErroColeta):
        baixar_http("http://127.0.0.1:9/x", "pncp", user_agent=UA, timeout=3,
                    abridor=sem_proxy)


@pytest.mark.parametrize("contato", ["", "sem-arroba-nem-url", "ftp://x"])
def test_user_agent_exige_contato_valido(contato):
    with pytest.raises(ValueError):
        user_agent_lumen("0.1.0", contato)


@pytest.mark.parametrize("contato", ["a@b.org", "https://lumen.exemplo.org/contato"])
def test_user_agent_aceita_email_ou_url(contato):
    assert contato in user_agent_lumen("0.1.0", contato)


def test_desfaz_a_compressao_de_transporte(portal, sem_proxy):
    art = baixar_http(f"{portal}/gzip", "ibge_localidades", user_agent=UA, abridor=sem_proxy)
    assert art.conteudo == b'[{"id": 12, "nome": "Acre"}]'
    assert CABECALHO_CODIFICACAO_RECEBIDA in art.cabecalhos and art.cabecalhos[CABECALHO_CODIFICACAO_RECEBIDA] == "gzip"
    assert not any(k.lower() in ("content-encoding", "content-length") for k in art.cabecalhos)


def test_limite_vale_para_o_documento_descomprimido(portal, sem_proxy):
    with pytest.raises(ConteudoGrandeDemais):
        baixar_http(f"{portal}/bomba", "ibge_localidades", user_agent=UA, limite_bytes=10_000, abridor=sem_proxy)


def test_corpo_que_nao_descomprime_fica_como_veio(portal, sem_proxy):
    art = baixar_http(f"{portal}/quebrado", "ibge_localidades", user_agent=UA, abridor=sem_proxy)
    assert art.conteudo == b"\x1f\x8b nao e gzip" and art.cabecalhos.get("Content-Encoding") == "gzip"


def test_deflate_com_e_sem_cabecalho_zlib():
    texto = b'{"ok": true}'
    cru = zlib.compressobj(wbits=-zlib.MAX_WBITS)
    for corpo in (zlib.compress(texto), cru.compress(texto) + cru.flush()):
        assert decodificar_corpo(corpo, {"content-encoding": "deflate"})[0] == texto
    assert decodificar_corpo(texto, {"Content-Encoding": "br"}) == (texto, {"Content-Encoding": "br"})
    assert decodificar_corpo(b"", {"Content-Encoding": "gzip"})[0] == b""
    with pytest.raises(ConteudoGrandeDemais):
        decodificar_corpo(zlib.compress(b"0" * 5000), {"Content-Encoding": "deflate"}, limite=4999)
