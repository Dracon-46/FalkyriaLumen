"""Pipeline dos cadastros de sanções da CGU: Portal (servidor local com a fixture real) → bronze → silver."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from lumen_ingestao.adaptadores.api.cgu import FonteCguCeis
from lumen_ingestao.cliente_http import ClienteHttp
from lumen_normalizacao.silver import consolidar, ler_entidade
from lumen_orquestracao import configuracao, etapas
from lumen_orquestracao.cli import main

FIX = Path(__file__).resolve().parents[3] / "testes" / "fixtures" / "cgu"


class _Portal(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path == "/download-de-dados/ceis":
            corpo, tipo = (FIX / "pagina_download_ceis.html").read_bytes(), "text/html"
        elif self.path == "/download-de-dados/ceis/20261015":
            corpo, tipo = (FIX / "ceis_amostra.zip").read_bytes(), "application/x-zip-compressed"
        else:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.end_headers()
        self.wfile.write(corpo)


@pytest.fixture
def portal():
    s = ThreadingHTTPServer(("127.0.0.1", 0), _Portal)
    threading.Thread(target=lambda: s.serve_forever(poll_interval=0.05), daemon=True).start()
    yield f"http://127.0.0.1:{s.server_address[1]}"
    s.shutdown()


@pytest.fixture
def local(sem_proxy, monkeypatch):
    def cliente_local(c, fonte_id):
        return ClienteHttp(fonte_id, user_agent="Lumen/teste (+contato@exemplo.org)", rpm=6000,
                           abridor=sem_proxy, dormir=lambda s: None)
    monkeypatch.setattr(etapas, "cliente", cliente_local)


def test_ceis_do_portal_ate_a_silver(tmp_path, portal, local):
    cfg = configuracao.Configuracao(contato="contato@exemplo.org", raiz_dados=tmp_path / "dados")
    resumo = etapas.coletar(cfg, "cgu_ceis", etapas.janela_de("2026-10-16"), base=portal)
    assert resumo.listados == 1 and not resumo.falhas
    r = etapas.normalizar(cfg, ["cgu_ceis"])
    assert r.por_fonte == {"cgu_ceis": 1} and r.registros == 6 and r.quarentena == 0
    sancoes = consolidar(ler_entidade(cfg.silver, "sancao"))
    assert len(sancoes) == 6
    assert {s["_versao_normalizador"] for s in sancoes} == {"cgu-1"}
    assert {s["data_referencia"] for s in sancoes} == {"2026-10-15"}
    assert "12345678909" not in json.dumps(sancoes)


def test_cli_coleta_cadastro_da_cgu_sem_data(tmp_path, portal, local, monkeypatch, capsys):
    monkeypatch.setenv("LUMEN_CONTATO", "a@b.org")
    monkeypatch.setenv("LUMEN_DADOS", str(tmp_path / "d"))
    monkeypatch.setitem(etapas.FABRICAS, "cgu_ceis", lambda c, **kw: FonteCguCeis(c, base=portal))
    assert main(["--config", str(tmp_path / "x.toml"), "coletar", "cgu_ceis"]) == 0
    assert json.loads(capsys.readouterr().out)["guardados"] == 1


def test_cli_exige_data_das_outras_fontes(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("LUMEN_CONTATO", "a@b.org")
    assert main(["--config", str(tmp_path / "x.toml"), "coletar", "pncp_contratos"]) == 2
    assert "exige --de" in capsys.readouterr().err


def test_limites_dos_cadastros_da_cgu():
    assert all(configuracao.LIMITES_PADRAO[f] == 10 for f in ("cgu_ceis", "cgu_cnep", "cgu_cepim"))
