"""Teste de aceitação do marco M1 (DOC-10).

Critério de saída da Fase 0, transcrito do roadmap:

    "Um artefato de teste é coletado, armazenado com hash verificável e
     recuperado a partir do identificador."

Este teste é esse critério, executável. Enquanto ele passar, o marco M1 está
cumprido. Se um dia ele falhar, a prova do projeto deixou de ser confiável e
nada construído em cima dela vale.
"""

import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from lumen_ingestao.bronze import ArmazemBronzeLocal, IntegridadeViolada, sha256_hex
from lumen_ingestao.coleta_http import baixar_http, user_agent_lumen

PUBLICACAO = (
    b'{"orgao": "Prefeitura Municipal de Exemplo", '
    b'"contrato": "045/2026", "modalidade": "dispensa", '
    b'"amparo_legal": "Lei 14.133/2021, art. 75, II", '
    b'"valor": "64900.00"}'
)


class _PortalDeTeste(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Last-Modified", "Mon, 28 Sep 2026 09:00:00 GMT")
        self.end_headers()
        self.wfile.write(PUBLICACAO)


@pytest.fixture
def portal():
    servidor = ThreadingHTTPServer(("127.0.0.1", 0), _PortalDeTeste)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{servidor.server_address[1]}/contratos/045-2026"
    servidor.shutdown()


def test_marco_m1_coleta_armazena_com_hash_e_recupera(portal, tmp_path):
    abridor = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    armazem = ArmazemBronzeLocal(tmp_path / "bronze")

    # 1. coletado
    artefato = baixar_http(
        portal,
        fonte_id="portal_teste",
        user_agent=user_agent_lumen("0.1.0", "contato@exemplo.org"),
        abridor=abridor,
    )

    # 2. armazenado com hash verificável
    registro = armazem.guardar(artefato)
    assert registro.sha256 == sha256_hex(PUBLICACAO)
    assert len(registro.sha256) == 64

    # 3. recuperado a partir do identificador, com o hash reconferido
    recuperado, conteudo = armazem.recuperar(registro.registro_id)
    assert conteudo == PUBLICACAO
    assert sha256_hex(conteudo) == recuperado.sha256

    # e a prova carrega o contexto da coleta
    assert recuperado.url_solicitada == portal
    assert recuperado.status_http == 200
    assert recuperado.cabecalhos["last-modified"] == "Mon, 28 Sep 2026 09:00:00 GMT"
    assert recuperado.coletado_em.endswith("+00:00")


def test_marco_m1_prova_adulterada_nao_e_aceita(portal, tmp_path):
    """A outra metade do critério: 'verificável' significa que a fraude no
    armazenamento é detectada, não apenas que existe um hash."""
    import os
    import stat

    abridor = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    armazem = ArmazemBronzeLocal(tmp_path / "bronze")
    registro = armazem.guardar(baixar_http(
        portal, "portal_teste",
        user_agent=user_agent_lumen("0.1.0", "contato@exemplo.org"),
        abridor=abridor,
    ))

    objeto = (tmp_path / "bronze" / "objetos" / registro.sha256[:2]
              / registro.sha256[2:4] / registro.sha256)
    os.chmod(objeto, stat.S_IRUSR | stat.S_IWUSR)
    objeto.write_bytes(PUBLICACAO.replace(b"64900.00", b"6490.00"))

    with pytest.raises(IntegridadeViolada):
        armazem.recuperar(registro.registro_id)
