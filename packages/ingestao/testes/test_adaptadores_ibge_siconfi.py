"""Adaptadores do IBGE e do SICONFI contra servidores locais que respondem com as fixtures reais."""

import json
import threading
import urllib.parse
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from lumen_ingestao.adaptadores.api.ibge import FonteIbgeLocalidades, FonteIbgePopulacao
from lumen_ingestao.adaptadores.api.siconfi import (
    FonteSiconfiDemonstrativo,
    FonteSiconfiEntes,
    FonteSiconfiExtrato,
)
from lumen_ingestao.bronze import ArmazemBronzeLocal
from lumen_ingestao.cliente_http import ClienteHttp
from lumen_ingestao.coleta_http import user_agent_lumen
from lumen_ingestao.portas import FonteDados, Janela, ResultadoCriterio, coletar_janela

UA = user_agent_lumen("0.2.0", "contato@exemplo.org")
J = Janela(date(2026, 10, 5), date(2026, 10, 5))


class _Falso(BaseHTTPRequestHandler):
    pedidos: list = []

    def log_message(self, *a):
        pass

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = dict(urllib.parse.parse_qsl(u.query))
        _Falso.pedidos.append((u.path, q))
        if "/falha" in u.path:
            self.send_response(503)
            self.end_headers()
            return
        if u.path.endswith("/entes"):
            # duas páginas: a primeira anuncia hasMore
            off = int(q.get("offset", 0))
            corpo = {"items": [{"cod_ibge": 1 + off}], "hasMore": off == 0, "limit": 1, "offset": off}
        else:
            corpo = {"items": [], "hasMore": False} if "siconfi" in u.path else []
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(corpo).encode())


@pytest.fixture
def srv():
    _Falso.pedidos = []
    s = ThreadingHTTPServer(("127.0.0.1", 0), _Falso)
    threading.Thread(target=lambda: s.serve_forever(poll_interval=0.05), daemon=True).start()
    yield f"http://127.0.0.1:{s.server_address[1]}"
    s.shutdown()


def _c(fid, sem_proxy):
    return ClienteHttp(fid, user_agent=UA, rpm=6000, abridor=sem_proxy, dormir=lambda s: None)


def test_ibge_localidades(srv, sem_proxy, tmp_path):
    f = FonteIbgeLocalidades(_c("ibge_localidades", sem_proxy), base=f"{srv}/api")
    assert isinstance(f, FonteDados)
    r = coletar_janela(f, J, ArmazemBronzeLocal(tmp_path))
    assert r.listados == 2
    caminhos = [p for p, _ in _Falso.pedidos]
    assert "/api/v1/localidades/municipios" in caminhos
    assert dict(_Falso.pedidos[1][1]) == {"view": "nivelado"}
    assert f.reportar_conformidade().avaliacoes[0].resultado is ResultadoCriterio.CUMPRE


def test_ibge_populacao(srv, sem_proxy, tmp_path):
    f = FonteIbgePopulacao(_c("ibge_populacao", sem_proxy), periodo="2026", base=f"{srv}/api")
    coletar_janela(f, J, ArmazemBronzeLocal(tmp_path))
    assert _Falso.pedidos[0][0] == "/api/v3/agregados/6579/periodos/2026/variaveis/9324"
    assert {q["localidades"] for _, q in _Falso.pedidos} == {"N3[all]", "N6[all]"}
    with pytest.raises(ValueError):
        FonteIbgePopulacao(_c("ibge_populacao", sem_proxy), periodo="26")


def test_siconfi_entes_segue_has_more(srv, sem_proxy, tmp_path):
    f = FonteSiconfiEntes(_c("siconfi_entes", sem_proxy), base=f"{srv}/siconfi")
    r = coletar_janela(f, J, ArmazemBronzeLocal(tmp_path))
    assert r.listados == 2
    assert [q.get("offset") for _, q in _Falso.pedidos] == [None, "1"]


def test_siconfi_extrato_por_ente(srv, sem_proxy, tmp_path):
    f = FonteSiconfiExtrato(_c("siconfi_extrato", sem_proxy), ["4319604", 3550308], 2025, base=f"{srv}/siconfi")
    r = coletar_janela(f, J, ArmazemBronzeLocal(tmp_path))
    assert r.listados == 2
    assert _Falso.pedidos[0][1] == {"id_ente": "4319604", "an_referencia": "2025"}
    with pytest.raises(ValueError):
        FonteSiconfiExtrato(_c("siconfi_extrato", sem_proxy), [], 2025)


def test_siconfi_demonstrativos(srv, sem_proxy, tmp_path):
    rreo = FonteSiconfiDemonstrativo(_c("siconfi_rreo", sem_proxy), "rreo", ["4319604"], 2025, periodo=6,
                                     tipo_demonstrativo="RREO Simplificado", anexo="RREO-Anexo 02",
                                     base=f"{srv}/siconfi")
    coletar_janela(rreo, J, ArmazemBronzeLocal(tmp_path))
    assert _Falso.pedidos[-1][1] == {"an_exercicio": "2025", "nr_periodo": "6",
                                     "co_tipo_demonstrativo": "RREO Simplificado",
                                     "no_anexo": "RREO-Anexo 02", "id_ente": "4319604"}
    rgf = FonteSiconfiDemonstrativo(_c("siconfi_rgf", sem_proxy), "rgf", ["43"], 2025, periodo=1,
                                    periodicidade_rgf="S", base=f"{srv}/siconfi")
    coletar_janela(rgf, J, ArmazemBronzeLocal(tmp_path))
    assert _Falso.pedidos[-1][1]["in_periodicidade"] == "S"
    dca = FonteSiconfiDemonstrativo(_c("siconfi_dca", sem_proxy), "dca", ["43"], 2025, base=f"{srv}/siconfi")
    coletar_janela(dca, J, ArmazemBronzeLocal(tmp_path))
    assert _Falso.pedidos[-1][0] == "/siconfi/dca"
    for kw in ({"recurso": "x"}, {"recurso": "rreo"}, {"recurso": "rgf", "periodo": 1, "periodicidade_rgf": "M"}):
        recurso = kw.pop("recurso")
        with pytest.raises(ValueError):
            FonteSiconfiDemonstrativo(_c(f"siconfi_{recurso}", sem_proxy), recurso, ["1"], 2025, **kw)


def test_sessao_sem_consulta_e_com_falha(srv, sem_proxy):
    f = FonteSiconfiEntes(_c("siconfi_entes", sem_proxy), base=f"{srv}/siconfi")
    assert f.reportar_conformidade().avaliacoes[0].resultado is ResultadoCriterio.INDETERMINADO
    f.base = f"{srv}/x/falha"
    f.cliente.politica = type(f.cliente.politica)(max_tentativas=1, falhas_para_suspender=99)
    list(f.listar(J))
    a = f.reportar_conformidade().avaliacoes[0]
    assert a.resultado is ResultadoCriterio.INDETERMINADO and "5xx" in a.motivo_indeterminado


def test_cliente_de_outra_fonte(sem_proxy):
    with pytest.raises(ValueError):
        FonteSiconfiEntes(_c("ibge_localidades", sem_proxy))
