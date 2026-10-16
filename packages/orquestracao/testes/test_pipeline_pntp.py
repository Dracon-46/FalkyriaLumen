"""Pipeline do PNTP: Radar da Transparência (servidor local) → bronze → silver, com o ciclo lido da URL."""

import io
import json
import re
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from lumen_ingestao.adaptadores.api.pntp import FontePntpAvaliacoes, membro_de_avaliacoes
from lumen_ingestao.cliente_http import ClienteHttp
from lumen_normalizacao.silver import consolidar, ler_entidade
from lumen_orquestracao import configuracao, etapas
from lumen_orquestracao.cli import main

FIX = Path(__file__).resolve().parents[3] / "testes" / "fixtures" / "pntp"


class _Radar(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path == "/downloads.html":
            corpo, status, extra = (FIX / "downloads_trecho.html").read_bytes(), 200, {}
        else:
            ciclo = int(re.search(r"(\d{4})", self.path).group(1))
            b = io.BytesIO()
            with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
                nome = "avaliacoes_pntp_2025_amostra.xlsx" if ciclo != 2022 else "avaliacoes_pntp_2022_cabecalho.xlsx"
                z.writestr(membro_de_avaliacoes(ciclo), (FIX / nome).read_bytes())
            inteiro = b.getvalue()
            a, f = re.fullmatch(r"bytes=(\d*)-(\d*)", self.headers["Range"]).groups()
            inicio = max(0, len(inteiro) - int(f)) if a == "" else int(a)
            fim = len(inteiro) - 1 if a == "" or not f else min(int(f), len(inteiro) - 1)
            corpo, status = inteiro[inicio:fim + 1], 206
            extra = {"Content-Range": f"bytes {inicio}-{fim}/{len(inteiro)}"}
        self.send_response(status)
        for k, v in extra.items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)


@pytest.fixture
def radar(sem_proxy, monkeypatch):
    s = ThreadingHTTPServer(("127.0.0.1", 0), _Radar)
    threading.Thread(target=lambda: s.serve_forever(poll_interval=0.05), daemon=True).start()
    base = f"http://127.0.0.1:{s.server_address[1]}"

    def cliente_local(c, fonte_id):
        return ClienteHttp(fonte_id, user_agent="Lumen/teste (+contato@exemplo.org)", rpm=6000,
                           abridor=sem_proxy, dormir=lambda s: None)
    monkeypatch.setattr(etapas, "cliente", cliente_local)
    monkeypatch.setitem(etapas.FABRICAS, "pntp_avaliacoes", lambda c, **kw: FontePntpAvaliacoes(c, base=base, **kw))
    yield base
    s.shutdown()


def test_avaliacoes_do_radar_ate_a_silver(tmp_path, radar):
    cfg = configuracao.Configuracao(contato="contato@exemplo.org", raiz_dados=tmp_path / "dados")
    resumo = etapas.coletar(cfg, "pntp_avaliacoes", etapas.janela_de("2026-10-16"), ciclos=[2022, 2025])
    assert resumo.listados == 2 and not resumo.falhas
    r = etapas.normalizar(cfg, ["pntp_avaliacoes"])
    assert r.registros == 8 and r.quarentena == 1      # 2022: outro layout, inteiro na quarentena
    avaliacoes = consolidar(ler_entidade(cfg.silver, "avaliacao_transparencia"))
    assert {a["ciclo"] for a in avaliacoes} == {2025} and {a["_versao_normalizador"] for a in avaliacoes} == {"pntp-1"}
    assert (cfg.silver / "avaliacao_transparencia" / "exercicio=2025").is_dir()


def test_cli_coleta_ciclos_sem_data(tmp_path, radar, monkeypatch, capsys):
    monkeypatch.setenv("LUMEN_CONTATO", "a@b.org")
    monkeypatch.setenv("LUMEN_DADOS", str(tmp_path / "d"))
    assert main(["--config", str(tmp_path / "x.toml"), "coletar", "pntp_avaliacoes", "--ciclos", "2025"]) == 0
    assert json.loads(capsys.readouterr().out)["guardados"] == 1


def test_url_sem_ciclo_nao_tem_normalizador():
    from lumen_ingestao.bronze import RegistroColeta
    registro = RegistroColeta.__new__(RegistroColeta)
    object.__setattr__(registro, "fonte_id", "pntp_avaliacoes")
    object.__setattr__(registro, "url_solicitada", "https://exemplo.org/outra.zip#x.xlsx")
    object.__setattr__(registro, "registro_id", "r1")
    assert etapas._normalizador_de(registro) is None
