"""Política de coleta responsável: vazão, retentativa, Retry-After e recuo."""

import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from lumen_ingestao.cliente_http import (
    ClienteHttp,
    FonteSuspensa,
    LimitadorTaxa,
    PoliticaRetentativa,
    interpretar_retry_after,
)
from lumen_ingestao.coleta_http import ErroColeta, baixar_http, user_agent_lumen

UA = user_agent_lumen("0.2.0", "contato@exemplo.org")


class Relogio:
    """Relógio falso: dormir avança o tempo, sem esperar de verdade."""

    def __init__(self):
        self.t = 1000.0
        self.dormidas = []

    def __call__(self):
        return self.t

    def dormir(self, s):
        self.dormidas.append(round(s, 3))
        self.t += s


# ------------------------------------------------------------------ limitador

def test_limitador_espaca_as_requisicoes_no_rpm():
    r = Relogio()
    lim = LimitadorTaxa(rpm=60, relogio=r, dormir=r.dormir)
    esperas = [lim.aguardar() for _ in range(4)]
    assert esperas[0] == 0.0
    assert esperas[1:] == pytest.approx([1.0, 1.0, 1.0])


def test_limitador_nao_espera_quando_o_tempo_ja_passou():
    r = Relogio()
    lim = LimitadorTaxa(rpm=30, relogio=r, dormir=r.dormir)
    lim.aguardar()
    r.t += 10
    assert lim.aguardar() == 0.0


@pytest.mark.parametrize("rpm,rajada", [(0, 1), (10, 0)])
def test_limitador_invalido(rpm, rajada):
    with pytest.raises(ValueError):
        LimitadorTaxa(rpm=rpm, rajada=rajada)


def test_espera_exponencial_com_teto():
    p = PoliticaRetentativa(espera_base_s=2, espera_teto_s=10)
    assert p.espera(1, 0.5) == 2.0
    assert p.espera(2, 0.5) == 4.0
    assert p.espera(3, 0.0) == 4.0     # 8 × 0,5
    assert p.espera(10, 1.0) == 10.0   # teto
    with pytest.raises(ValueError):
        PoliticaRetentativa(max_tentativas=0)


def test_retry_after():
    agora = datetime(2026, 10, 5, 12, 0, 0, tzinfo=timezone.utc)
    assert interpretar_retry_after("30") == 30.0
    assert interpretar_retry_after("Mon, 05 Oct 2026 12:00:20 GMT", agora) == 20.0
    assert interpretar_retry_after("Mon, 05 Oct 2026 11:00:00 GMT", agora) == 0.0
    assert interpretar_retry_after("lixo") is None
    assert interpretar_retry_after(None) is None


# ------------------------------------------------------------------ servidor

class _Instavel(BaseHTTPRequestHandler):
    contagem: dict = {}

    def log_message(self, *a):
        pass

    def do_GET(self):
        n = _Instavel.contagem.get(self.path, 0) + 1
        _Instavel.contagem[self.path] = n
        self.cabecalhos_recebidos = dict(self.headers)
        if self.path.startswith("/oscila") and n < 3:
            self.send_response(503)
            self.send_header("Retry-After", "7")
            self.end_headers()
            self.wfile.write(b"ocupado")
            return
        if self.path.startswith("/sempre503"):
            self.send_response(503)
            self.end_headers()
            return
        if self.path.startswith("/eco"):
            corpo = (self.headers.get("If-None-Match") or "").encode()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(corpo)
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok": true}')


@pytest.fixture
def servidor():
    _Instavel.contagem = {}
    s = ThreadingHTTPServer(("127.0.0.1", 0), _Instavel)
    threading.Thread(target=lambda: s.serve_forever(poll_interval=0.05), daemon=True).start()
    yield f"http://127.0.0.1:{s.server_address[1]}"
    s.shutdown()


def _cliente(sem_proxy, **kw):
    r = Relogio()
    c = ClienteHttp("fonte_teste", user_agent=UA, rpm=600, abridor=sem_proxy,
                    relogio=r, dormir=r.dormir, sorteio=lambda: 0.5, timeout=5, **kw)
    return c, r


def test_retenta_503_respeitando_retry_after(servidor, sem_proxy):
    c, r = _cliente(sem_proxy)
    art = c.obter(f"{servidor}/oscila")
    assert art.status_http == 200
    assert c.requisicoes == 3
    assert r.dormidas.count(7.0) == 2  # Retry-After da fonte manda
    assert c.falhas_seguidas == 0


def test_503_persistente_devolve_o_erro_como_artefato(servidor, sem_proxy):
    """ADR-012: a resposta de erro final é prova, não exceção."""
    c, _ = _cliente(sem_proxy, politica=PoliticaRetentativa(max_tentativas=3, falhas_para_suspender=99))
    art = c.obter(f"{servidor}/sempre503")
    assert art.status_http == 503
    assert c.requisicoes == 3


def test_recuo_suspende_a_fonte_depois_de_falhas_seguidas(servidor, sem_proxy):
    c, r = _cliente(sem_proxy, politica=PoliticaRetentativa(max_tentativas=2, falhas_para_suspender=3,
                                                             suspensao_s=600))
    c.obter(f"{servidor}/sempre503")          # 2 falhas
    art = c.obter(f"{servidor}/sempre503")    # 3ª falha suspende e devolve o erro
    assert art.status_http == 503 and c.suspensa
    feitas = c.requisicoes
    with pytest.raises(FonteSuspensa):
        c.obter(f"{servidor}/ok")
    assert c.requisicoes == feitas            # suspensa não toca a rede
    r.t += 601
    assert c.obter(f"{servidor}/ok").status_http == 200
    assert not c.suspensa and c.falhas_seguidas == 0


def test_sem_resposta_retenta_e_depois_levanta(sem_proxy):
    c, r = _cliente(sem_proxy, politica=PoliticaRetentativa(max_tentativas=2, falhas_para_suspender=99))
    with pytest.raises(ErroColeta):
        c.obter("http://127.0.0.1:9/nada")
    assert c.requisicoes == 2 and len(r.dormidas) >= 1


def test_cabecalhos_extras_chegam_mas_nao_trocam_o_user_agent(servidor, sem_proxy):
    art = baixar_http(f"{servidor}/eco", "fonte_teste", user_agent=UA, abridor=sem_proxy,
                      cabecalhos={"If-None-Match": '"v9"'})
    assert art.conteudo == b'"v9"'
    with pytest.raises(ValueError, match="User-Agent"):
        baixar_http(f"{servidor}/eco", "fonte_teste", user_agent=UA, abridor=sem_proxy,
                    cabecalhos={"user-agent": "outro"})
