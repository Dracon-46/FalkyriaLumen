"""Adaptadores dos cadastros de sanções da CGU contra um servidor local com as fixtures reais.

O servidor imita o Portal da Transparência: a página de download declara a data, e o arquivo do dia
redireciona para o servidor de arquivos, como o Portal faz.
"""

import threading
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from lumen_ingestao.adaptadores.api.cgu import (
    DataDoArquivoAusente,
    FonteCguCeis,
    FonteCguCepim,
    FonteCguCnep,
    data_do_arquivo,
)
from lumen_ingestao.bronze import ArmazemBronzeLocal
from lumen_ingestao.cliente_http import ClienteHttp, PoliticaRetentativa
from lumen_ingestao.coleta_http import ErroColeta, user_agent_lumen
from lumen_ingestao.portas import FonteDados, Janela, ResultadoCriterio, coletar_janela

UA = user_agent_lumen("0.8.0", "contato@exemplo.org")
J = Janela(date(2026, 10, 16), date(2026, 10, 16))
FIX = Path(__file__).resolve().parents[3] / "testes" / "fixtures" / "cgu"
PAGINA = (FIX / "pagina_download_ceis.html").read_bytes()
ZIP = (FIX / "ceis_amostra.zip").read_bytes()


class _Portal(BaseHTTPRequestHandler):
    pedidos: list = []
    pagina: bytes = PAGINA
    status_pagina = 200

    def log_message(self, *a):
        pass

    def _responder(self, status, corpo=b"", tipo="text/html", extra=None):
        self.send_response(status)
        self.send_header("Content-Type", tipo)
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def do_GET(self):
        _Portal.pedidos.append((self.path, self.headers.get("Accept")))
        if self.path == "/download-de-dados/ceis":
            self._responder(_Portal.status_pagina, _Portal.pagina)
        elif self.path == "/download-de-dados/ceis/20261015":
            self._responder(302, extra={"Location": "/saida/ceis/20261015_CEIS.zip"})
        elif self.path == "/saida/ceis/20261015_CEIS.zip":
            self._responder(200, ZIP, "application/x-zip-compressed")
        else:
            self._responder(404, b"nao encontrado")


@pytest.fixture
def portal():
    _Portal.pedidos = []
    _Portal.pagina = PAGINA
    _Portal.status_pagina = 200
    s = ThreadingHTTPServer(("127.0.0.1", 0), _Portal)
    threading.Thread(target=lambda: s.serve_forever(poll_interval=0.05), daemon=True).start()
    yield f"http://127.0.0.1:{s.server_address[1]}"
    s.shutdown()


def _cliente(fonte_id, sem_proxy):
    return ClienteHttp(fonte_id, user_agent=UA, rpm=6000, abridor=sem_proxy, dormir=lambda s: None)


def test_ceis_baixa_o_zip_do_dia_declarado_na_pagina(portal, sem_proxy, tmp_path):
    fonte = FonteCguCeis(_cliente("cgu_ceis", sem_proxy), base=portal)
    assert isinstance(fonte, FonteDados)
    armazem = ArmazemBronzeLocal(tmp_path)
    resumo = coletar_janela(fonte, J, armazem)
    assert resumo.listados == 1 and len(resumo.guardados) == 1 and not resumo.falhas
    registro = next(armazem.listar_registros())
    assert registro.fonte_id == "cgu_ceis"
    assert registro.url_solicitada.endswith("/download-de-dados/ceis/20261015")
    assert registro.url_efetiva.endswith("/saida/ceis/20261015_CEIS.zip")
    _, conteudo = armazem.recuperar(registro.registro_id)
    assert conteudo == ZIP
    assert [a for _, a in _Portal.pedidos] == ["text/html", "application/zip", "application/zip"]
    relatorio = fonte.reportar_conformidade()
    assert relatorio.avaliacoes[0].resultado is ResultadoCriterio.CUMPRE
    assert relatorio.avaliacoes[0].criterio == "cgu_ceis_respondeu_na_sessao"


def test_referencia_traz_cadastro_e_data_do_arquivo(portal, sem_proxy):
    ref = next(FonteCguCeis(_cliente("cgu_ceis", sem_proxy), base=portal).listar(J))
    assert ref.objeto == "Sancao"
    assert ref.chave_origem == "CEIS-20261015"
    assert ref.metadados == {"cadastro": "CEIS", "data_arquivo": "2026-10-15"}


def test_pagina_sem_data_interrompe_a_coleta(portal, sem_proxy, tmp_path):
    _Portal.pagina = b"<html>manutencao</html>"
    fonte = FonteCguCeis(_cliente("cgu_ceis", sem_proxy), base=portal)
    with pytest.raises(DataDoArquivoAusente):
        coletar_janela(fonte, J, ArmazemBronzeLocal(tmp_path))


def test_pagina_com_erro_interrompe_a_coleta_e_conta_falha(portal, sem_proxy, tmp_path):
    _Portal.status_pagina = 404
    fonte = FonteCguCeis(_cliente("cgu_ceis", sem_proxy), base=portal)
    with pytest.raises(ErroColeta, match="respondeu 404"):
        coletar_janela(fonte, J, ArmazemBronzeLocal(tmp_path))
    assert fonte.respondidas == 1 and fonte.falhas == 0


def test_cliente_de_outra_fonte_e_recusado(sem_proxy):
    with pytest.raises(ValueError, match="cgu_ceis"):
        FonteCguCnep(_cliente("cgu_ceis", sem_proxy))


@pytest.mark.parametrize("classe,fonte_id,cadastro", [(FonteCguCeis, "cgu_ceis", "ceis"),
                                                       (FonteCguCnep, "cgu_cnep", "cnep"),
                                                       (FonteCguCepim, "cgu_cepim", "cepim")])
def test_tres_cadastros_diarios_sem_autenticacao(classe, fonte_id, cadastro, sem_proxy):
    fonte = classe(_cliente(fonte_id, sem_proxy))
    assert fonte.cadastro == cadastro
    capacidades = fonte.descrever_capacidades()
    assert capacidades.objetos == frozenset({"Sancao"})
    assert capacidades.periodicidade.value == "diaria"
    assert not capacidades.exige_autenticacao


def test_data_do_arquivo_escolhe_a_mais_recente_do_cadastro():
    html = ('arquivos.push({"ano" : "2026", "mes" : "10", "dia" : "14", "origem" :  "CEIS"});'
            'arquivos.push({"ano" : "2026", "mes" : "10", "dia" : "15", "origem" :  "CEIS"});'
            'arquivos.push({"ano" : "2026", "mes" : "10", "dia" : "16", "origem" :  "CNEP"});')
    assert data_do_arquivo(html, "ceis") == date(2026, 10, 15)
    assert data_do_arquivo(html, "CNEP") == date(2026, 10, 16)
    with pytest.raises(DataDoArquivoAusente):
        data_do_arquivo(html, "cepim")


def test_portal_fora_do_ar_conta_falha_e_conformidade_fica_indeterminada(portal, sem_proxy, tmp_path):
    _Portal.status_pagina = 503
    fonte = FonteCguCeis(_cliente("cgu_ceis", sem_proxy), base=portal)
    with pytest.raises(ErroColeta, match="respondeu 503"):
        coletar_janela(fonte, J, ArmazemBronzeLocal(tmp_path))
    assert fonte.falhas == 1
    assert fonte.reportar_conformidade().avaliacoes[0].resultado is ResultadoCriterio.INDETERMINADO


def test_sem_resposta_nenhuma_conta_falha(sem_proxy):
    cliente = ClienteHttp("cgu_ceis", user_agent=UA, rpm=6000, abridor=sem_proxy, dormir=lambda s: None,
                          politica=PoliticaRetentativa(max_tentativas=1))
    fonte = FonteCguCeis(cliente, base="http://127.0.0.1:9")
    with pytest.raises(ErroColeta):
        next(fonte.listar(J))
    assert fonte.falhas == 1
