"""Pipeline ponta a ponta: PNCP (servidor local com fixtures reais) → bronze → silver.

É o marco M2 em miniatura: coleta incremental de uma fonte federal, prova
preservada com hash, normalização para o esquema canônico e visão
consolidada, tudo reconstruível a partir do bronze.
"""

import json
import shutil
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from lumen_ingestao.bronze import ArmazemBronzeLocal
from lumen_ingestao.cliente_http import ClienteHttp
from lumen_normalizacao.silver import consolidar, ler_entidade
from lumen_orquestracao import configuracao, etapas
from lumen_orquestracao.cli import main

FIX = Path(__file__).resolve().parents[3] / "testes" / "fixtures" / "pncp"


class _Pncp(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(self.path).query))
        if q.get("codigoModalidadeContratacao") != "8":
            self.send_response(204)
            self.end_headers()
            return
        corpo = json.loads((FIX / "contratacoes_publicacao_dispensa_20260901_p1.json").read_text(encoding="utf-8"))
        corpo["totalPaginas"] = 1
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(corpo, ensure_ascii=False).encode())


@pytest.fixture
def srv():
    s = ThreadingHTTPServer(("127.0.0.1", 0), _Pncp)
    threading.Thread(target=lambda: s.serve_forever(poll_interval=0.05), daemon=True).start()
    yield f"http://127.0.0.1:{s.server_address[1]}"
    s.shutdown()


@pytest.fixture
def cfg(tmp_path):
    return configuracao.Configuracao(contato="contato@exemplo.org", raiz_dados=tmp_path / "dados")


def test_coleta_normaliza_e_reconstroi(cfg, srv, sem_proxy, monkeypatch):
    def cliente_local(c, fonte_id):
        return ClienteHttp(fonte_id, user_agent="Lumen/teste (+contato@exemplo.org)", rpm=6000,
                           abridor=sem_proxy, dormir=lambda s: None)
    monkeypatch.setattr(etapas, "cliente", cliente_local)
    resumo = etapas.coletar(cfg, "pncp_contratacoes", etapas.janela_de("2026-09-01"),
                            modalidades=(6, 8), base=f"{srv}/consulta")
    assert resumo.listados == 2 and not resumo.falhas

    r = etapas.normalizar(cfg)
    assert r.artefatos == 2 and r.quarentena == 0
    processos = consolidar(ler_entidade(cfg.silver, "processo_contratacao"))
    assert len(processos) == 4

    # recoleta do mesmo dia: o bronze ganha novos eventos de coleta, o conteúdo
    # não muda, e a visão consolidada continua com 4 processos
    etapas.coletar(cfg, "pncp_contratacoes", etapas.janela_de("2026-09-01"),
                   modalidades=(8,), base=f"{srv}/consulta")
    etapas.normalizar(cfg)
    assert len(ler_entidade(cfg.silver, "processo_contratacao")) == 8       # duas ocorrências de cada
    assert len(consolidar(ler_entidade(cfg.silver, "processo_contratacao"))) == 4
    eventos = list(ArmazemBronzeLocal(cfg.bronze).listar_registros())
    assert sorted(e.mudou_desde_anterior for e in eventos if e.status_http == 200) == [False, True]

    # RF-NO-12: apagar a silver e reconstruir a partir do bronze dá o mesmo resultado
    antes = consolidar(ler_entidade(cfg.silver, "processo_contratacao"))
    shutil.rmtree(cfg.silver)
    etapas.normalizar(cfg)
    assert consolidar(ler_entidade(cfg.silver, "processo_contratacao")) == antes


def test_fonte_desconhecida(cfg):
    with pytest.raises(KeyError):
        etapas.coletar(cfg, "inexistente", etapas.janela_de("2026-09-01"))


def test_configuracao_exige_contato(tmp_path, monkeypatch):
    monkeypatch.delenv("LUMEN_CONTATO", raising=False)
    with pytest.raises(configuracao.ConfiguracaoAusente):
        configuracao.carregar(tmp_path / "nao_existe.toml")
    arquivo = tmp_path / "lumen.toml"
    arquivo.write_text('[coleta]\ncontato = "a@b.org"\n[dados]\nraiz = "x"\n[limites_rpm]\npncp_contratos = 10\n',
                       encoding="utf-8")
    c = configuracao.carregar(arquivo)
    assert c.contato == "a@b.org" and c.rpm("pncp_contratos") == 10 and c.rpm("outra") == 30
    assert c.bronze.as_posix().endswith("x/bronze")
    monkeypatch.setenv("LUMEN_CONTATO", "env@b.org")
    assert configuracao.carregar(arquivo).contato == "env@b.org"


def test_cli_bronze_e_normalizar(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("LUMEN_CONTATO", "a@b.org")
    monkeypatch.setenv("LUMEN_DADOS", str(tmp_path / "d"))
    assert main(["--config", str(tmp_path / "x.toml"), "bronze", "verificar"]) == 0
    assert '"corrompidos": []' in capsys.readouterr().out
    assert main(["--config", str(tmp_path / "x.toml"), "normalizar"]) == 0
    assert main(["--config", str(tmp_path / "x.toml"), "bronze", "listar"]) == 0


def test_cli_sem_contato(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("LUMEN_CONTATO", raising=False)
    assert main(["--config", str(tmp_path / "x.toml"), "normalizar"]) == 2
    assert "contato" in capsys.readouterr().err


def test_cli_extrato_exige_entes(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("LUMEN_CONTATO", "a@b.org")
    assert main(["--config", str(tmp_path / "x.toml"), "coletar", "siconfi_extrato", "--de", "2026-10-05"]) == 2


def test_cli_repassa_eleicoes(capsys):
    """`lumen eleicoes ...` vai inteiro para o CLI da aba Eleições."""
    amostra = Path(__file__).resolve().parents[3] / "testes" / "fixtures" / "eleicoes_feed"
    assert main(["eleicoes", "--saida", str(amostra), "verificar"]) == 0
    assert "0 problema(s)" in capsys.readouterr().out


def test_cli_recusa_argumento_desconhecido(tmp_path, monkeypatch):
    monkeypatch.setenv("LUMEN_CONTATO", "c@exemplo.org")
    with pytest.raises(SystemExit):
        main(["--config", str(tmp_path / "x.toml"), "normalizar", "--nao-existe"])
