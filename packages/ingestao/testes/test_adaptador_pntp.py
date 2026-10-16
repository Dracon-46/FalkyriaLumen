"""Adaptador do PNTP contra um servidor local: página de downloads real e ZIP montado com a amostra real."""

import io
import re
import threading
import zipfile
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from lumen_ingestao.adaptadores.api.pntp import (
    TIPO_XLSX,
    FontePntpAvaliacoes,
    ciclos_publicados,
    membro_de_avaliacoes,
)
from lumen_ingestao.bronze import ArmazemBronzeLocal
from lumen_ingestao.cliente_http import ClienteHttp
from lumen_ingestao.coleta_http import ErroColeta, user_agent_lumen
from lumen_ingestao.portas import FonteDados, Janela, ResultadoCriterio, coletar_janela

UA = user_agent_lumen("0.8.0", "contato@exemplo.org")
J = Janela(date(2026, 10, 16), date(2026, 10, 16))
FIX = Path(__file__).resolve().parents[3] / "testes" / "fixtures" / "pntp"
PAGINA = (FIX / "downloads_trecho.html").read_bytes()
PLANILHA = (FIX / "avaliacoes_pntp_2025_amostra.xlsx").read_bytes()


def _zip(ciclo):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"pntp_{ciclo}/respostas/respostas_pntp_{ciclo}_AC.xlsx", b"x" * 5000)
        z.writestr(membro_de_avaliacoes(ciclo), PLANILHA)
    return b.getvalue()


class _Radar(BaseHTTPRequestHandler):
    status_pagina = 200

    def log_message(self, *a):
        pass

    def _enviar(self, status, corpo, extra=None):
        self.send_response(status)
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def do_GET(self):
        if self.path == "/downloads.html":
            return self._enviar(_Radar.status_pagina, PAGINA)
        m = re.fullmatch(r"/dados/dados_pntp_(\d{4})\.zip", self.path)
        if not m:
            return self._enviar(404, b"")
        corpo = _zip(int(m.group(1)))
        a, b = re.fullmatch(r"bytes=(\d*)-(\d*)", self.headers["Range"]).groups()
        inicio, fim = (len(corpo) - int(b), len(corpo) - 1) if a == "" else (int(a), min(int(b or len(corpo) - 1),
                                                                                         len(corpo) - 1))
        inicio = max(0, inicio)
        self._enviar(206, corpo[inicio:fim + 1], {"Content-Range": f"bytes {inicio}-{fim}/{len(corpo)}",
                                                  "ETag": '"e1"', "Last-Modified": "Tue, 10 Feb 2026 13:35:32 GMT"})


@pytest.fixture
def radar():
    _Radar.status_pagina = 200
    s = ThreadingHTTPServer(("127.0.0.1", 0), _Radar)
    threading.Thread(target=lambda: s.serve_forever(poll_interval=0.05), daemon=True).start()
    yield f"http://127.0.0.1:{s.server_address[1]}"
    s.shutdown()


def _fonte(base, sem_proxy, **kw):
    cliente = ClienteHttp("pntp_avaliacoes", user_agent=UA, rpm=6000, abridor=sem_proxy, dormir=lambda s: None)
    return FontePntpAvaliacoes(cliente, base=base, **kw)


def test_ciclos_publicados_na_pagina_real():
    assert ciclos_publicados(PAGINA.decode()) == [2022, 2023, 2024, 2025]


def test_coleta_a_planilha_de_cada_ciclo(radar, sem_proxy, tmp_path):
    fonte = _fonte(radar, sem_proxy, ciclos=[2025, 2024])
    assert isinstance(fonte, FonteDados)
    armazem = ArmazemBronzeLocal(tmp_path)
    resumo = coletar_janela(fonte, J, armazem)
    assert resumo.listados == 2 and len(resumo.guardados) == 2 and not resumo.falhas
    registros = sorted(armazem.listar_registros(), key=lambda r: r.url_solicitada)
    assert registros[0].url_solicitada.endswith("/dados/dados_pntp_2024.zip#pntp_2024/avaliacoes_pntp_2024.xlsx")
    assert registros[0].tipo_midia == TIPO_XLSX
    _, conteudo = armazem.recuperar(registros[1].registro_id)
    assert conteudo == PLANILHA
    assert fonte.reportar_conformidade().avaliacoes[0].resultado is ResultadoCriterio.CUMPRE


def test_sem_ciclos_pega_todos_os_publicados(radar, sem_proxy):
    refs = list(_fonte(radar, sem_proxy).listar(J))
    assert [r.metadados["ciclo"] for r in refs] == ["2022", "2023", "2024", "2025"]
    assert refs[-1].chave_origem == "2025" and refs[-1].objeto == "AvaliacaoTransparencia"


def test_cabecalhos_identificam_o_zip(radar, sem_proxy):
    fonte = _fonte(radar, sem_proxy, ciclos=[2025])
    artefato = fonte.baixar(next(fonte.listar(J)))
    assert artefato.status_http == 200 and artefato.conteudo == PLANILHA
    assert artefato.cabecalhos["X-Lumen-Zip-Membro"] == "pntp_2025/avaliacoes_pntp_2025.xlsx"
    assert artefato.cabecalhos["ETag"] == '"e1"' and artefato.cabecalhos["Last-Modified"]
    assert int(artefato.cabecalhos["X-Lumen-Zip-Tamanho"]) > len(PLANILHA)
    assert len(artefato.cabecalhos["X-Lumen-Zip-Crc32"]) == 8


def test_ciclo_sem_base_e_pagina_com_erro(radar, sem_proxy):
    with pytest.raises(ErroColeta, match="2026"):
        list(_fonte(radar, sem_proxy, ciclos=[2026]).listar(J))
    _Radar.status_pagina = 503
    fonte = _fonte(radar, sem_proxy)
    with pytest.raises(ErroColeta, match="respondeu 503"):
        list(fonte.listar(J))
    assert fonte.falhas == 1


def test_zip_sem_a_planilha_conta_falha(radar, sem_proxy):
    fonte = _fonte(radar, sem_proxy, ciclos=[2025])
    ref = next(fonte.listar(J))
    ref.metadados["membro"] = "pntp_2025/inexistente.xlsx"
    with pytest.raises(ErroColeta):
        fonte.baixar(ref)
    assert fonte.falhas == 1
