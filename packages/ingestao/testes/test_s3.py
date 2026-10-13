"""Cliente S3 e camada bronze sobre objetos.

A assinatura é conferida contra o vetor oficial da AWS (exemplo "GET Object"
da documentação do Signature Version 4 para S3). O comportamento do armazém é
testado contra um servidor S3 falso que **reconfere a assinatura** de cada
requisição com os cabeçalhos efetivamente recebidos — um erro de cabeçalho
assinado e não enviado (ou o contrário) quebra o teste.
"""

import hashlib
import re
import threading
import urllib.parse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from xml.sax.saxutils import escape

import pytest

from lumen_ingestao.armazem_s3 import ArmazemBronzeObjetos
from lumen_ingestao.bronze import ArtefatoBruto, IntegridadeViolada, RegistroNaoEncontrado
from lumen_ingestao.s3 import ChaveInexistente, ChaveJaExiste, ClienteS3, ErroS3, assinar_v4

ACESSO = "AKIAIOSFODNN7EXAMPLE"
SEGREDO = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"


def test_vetor_oficial_da_aws_get_object():
    cab = assinar_v4(
        "GET", "https://examplebucket.s3.amazonaws.com/test.txt",
        {"host": "examplebucket.s3.amazonaws.com", "range": "bytes=0-9"},
        chave_acesso=ACESSO, chave_secreta=SEGREDO, regiao="us-east-1",
        instante=datetime(2013, 5, 24, tzinfo=timezone.utc),
        hash_corpo="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    )
    assert cab["authorization"] == (
        "AWS4-HMAC-SHA256 Credential=AKIAIOSFODNN7EXAMPLE/20130524/us-east-1/s3/aws4_request, "
        "SignedHeaders=host;range;x-amz-content-sha256;x-amz-date, "
        "Signature=f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41"
    )


class _S3Falso(BaseHTTPRequestHandler):
    objetos: dict = {}
    assinaturas_ruins = 0
    max_chaves = 2

    def log_message(self, *a):
        pass

    def _conferir_assinatura(self, corpo: bytes) -> bool:
        aut = self.headers.get("Authorization", "")
        m = re.match(r"AWS4-HMAC-SHA256 Credential=([^/]+)/(\d{8})/([^/]+)/s3/aws4_request, "
                     r"SignedHeaders=([^,]+), Signature=([0-9a-f]{64})$", aut)
        if not m:
            return False
        assinados = m.group(4).split(";")
        cab = {n: self.headers.get(n, "") for n in assinados if n not in ("x-amz-date", "x-amz-content-sha256")}
        instante = datetime.strptime(self.headers["x-amz-date"], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        if self.headers["x-amz-content-sha256"] != hashlib.sha256(corpo).hexdigest():
            return False
        url = f"http://{self.headers['Host']}{self.path}"
        refeito = assinar_v4(self.command, url, cab, chave_acesso=m.group(1), chave_secreta=SEGREDO,
                             regiao=m.group(3), instante=instante,
                             hash_corpo=self.headers["x-amz-content-sha256"])
        return refeito["authorization"] == aut

    def _resp(self, status, corpo=b"", tipo="application/xml"):
        self.send_response(status)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(corpo)

    def _chave(self):
        caminho = urllib.parse.urlsplit(self.path).path
        partes = urllib.parse.unquote(caminho).lstrip("/").split("/", 1)
        return partes[0], (partes[1] if len(partes) > 1 else "")

    def _tratar(self, corpo=b""):
        if not self._conferir_assinatura(corpo):
            _S3Falso.assinaturas_ruins += 1
            return self._resp(403, b"<Error><Code>SignatureDoesNotMatch</Code></Error>")
        bucket, chave = self._chave()
        if self.command == "PUT":
            if self.headers.get("If-None-Match") == "*" and chave in self.objetos:
                return self._resp(412, b"<Error><Code>PreconditionFailed</Code></Error>")
            self.objetos[chave] = corpo
            return self._resp(200)
        if chave:
            if chave not in self.objetos:
                return self._resp(404, b"<Error><Code>NoSuchKey</Code></Error>")
            return self._resp(200, self.objetos[chave], "application/octet-stream")
        q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(self.path).query))
        chaves = sorted(k for k in self.objetos if k.startswith(q.get("prefix", "")))
        inicio = int(q.get("continuation-token", "0"))
        fatia = chaves[inicio:inicio + self.max_chaves]
        truncado = inicio + self.max_chaves < len(chaves)
        xml = ['<?xml version="1.0"?><ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">']
        xml += [f"<Contents><Key>{escape(k)}</Key></Contents>" for k in fatia]
        xml.append(f"<IsTruncated>{'true' if truncado else 'false'}</IsTruncated>")
        if truncado:
            xml.append(f"<NextContinuationToken>{inicio + self.max_chaves}</NextContinuationToken>")
        xml.append("</ListBucketResult>")
        return self._resp(200, "".join(xml).encode())

    def do_PUT(self):
        n = int(self.headers.get("Content-Length", "0"))
        self._tratar(self.rfile.read(n))

    def do_GET(self):
        self._tratar()

    def do_HEAD(self):
        self._tratar()


@pytest.fixture
def s3(sem_proxy):
    _S3Falso.objetos = {}
    _S3Falso.assinaturas_ruins = 0
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _S3Falso)
    threading.Thread(target=lambda: srv.serve_forever(poll_interval=0.05), daemon=True).start()
    yield ClienteS3(endpoint=f"http://127.0.0.1:{srv.server_address[1]}", bucket="lumen-bronze",
                    chave_acesso=ACESSO, chave_secreta=SEGREDO, abridor=sem_proxy)
    srv.shutdown()
    assert _S3Falso.assinaturas_ruins == 0


def test_operacoes_basicas(s3):
    s3.gravar("a/b c.txt", b"oi")
    assert s3.ler("a/b c.txt") == b"oi"
    assert s3.existe("a/b c.txt") and not s3.existe("nada")
    with pytest.raises(ChaveJaExiste):
        s3.gravar("a/b c.txt", b"outro")
    assert s3.ler("a/b c.txt") == b"oi"
    with pytest.raises(ChaveInexistente):
        s3.ler("nada")
    for i in range(5):
        s3.gravar(f"lista/{i}", b"")
    assert list(s3.listar("lista/")) == [f"lista/{i}" for i in range(5)]  # 3 páginas de 2


def test_erro_de_autenticacao_vira_excecao(s3):
    s3.chave_secreta = "errada"
    with pytest.raises(ErroS3) as e:
        s3.gravar("x", b"1")
    assert e.value.status == 403
    _S3Falso.assinaturas_ruins = 0


def _art(conteudo=b'{"v": 1}', url="https://pncp.gov.br/api/consulta/v1/contratos?pagina=1"):
    return ArtefatoBruto(conteudo=conteudo, fonte_id="pncp_contratos", url_solicitada=url,
                         url_efetiva=url, status_http=200, tipo_midia="application/json",
                         cabecalhos={"Set-Cookie": "segredo", "ETag": '"1"'},
                         coletado_em=datetime(2026, 10, 5, 12, tzinfo=timezone.utc))


def test_armazem_guarda_versiona_e_recupera(s3):
    armazem = ArmazemBronzeObjetos(s3, prefixo="lumen")
    r1 = armazem.guardar(_art())
    r2 = armazem.guardar(_art())
    r3 = armazem.guardar(_art(b'{"v": 2}'))
    assert (r1.versao, r2.versao, r3.versao) == (1, 2, 3)
    assert (r1.mudou_desde_anterior, r2.mudou_desde_anterior, r3.mudou_desde_anterior) == (True, False, True)
    assert "set-cookie" not in r1.cabecalhos and r1.cabecalhos["etag"] == '"1"'
    registro, conteudo = armazem.recuperar(r3.registro_id)
    assert conteudo == b'{"v": 2}' and registro.sha256 == r3.sha256
    assert [r.versao for r in armazem.historico(r1.url_solicitada)] == [1, 2, 3]
    # conteúdo idêntico é guardado uma vez só
    assert sum(1 for k in _S3Falso.objetos if k.startswith("lumen/objetos/")) == 2
    # listagem pela partição do DOC-05 (fonte/ano/mês) e completa
    assert len(list(armazem.listar_registros("pncp_contratos", 2026, 10))) == 3
    assert len(list(armazem.listar_registros("pncp_contratos", 2026, 9))) == 0
    assert len(list(armazem.listar_registros())) == 3
    assert armazem.verificar_integridade() == []


def test_armazem_detecta_prova_adulterada(s3):
    armazem = ArmazemBronzeObjetos(s3)
    r = armazem.guardar(_art())
    chave = next(k for k in _S3Falso.objetos if k.startswith("objetos/"))
    _S3Falso.objetos[chave] = b"adulterado"
    with pytest.raises(IntegridadeViolada):
        armazem.recuperar(r.registro_id)
    assert armazem.verificar_integridade() == [r.sha256]
    del _S3Falso.objetos[chave]
    with pytest.raises(IntegridadeViolada, match="inexistente"):
        armazem.recuperar(r.registro_id)
    with pytest.raises(RegistroNaoEncontrado):
        armazem.obter_registro("0" * 32)


def test_retencao_envia_object_lock(s3):
    armazem = ArmazemBronzeObjetos(s3, retencao_dias=3650)
    armazem.guardar(_art())  # o servidor falso aceita; o que se verifica é a assinatura dos cabeçalhos extras


def test_estilo_virtual_hosted():
    c = ClienteS3(endpoint="https://s3.sa-east-1.amazonaws.com", bucket="b", chave_acesso="a",
                  chave_secreta="s", estilo_caminho=False)
    assert c._url("x/y") == "https://b.s3.sa-east-1.amazonaws.com/x/y"
    assert ClienteS3(endpoint="http://localhost:9000", bucket="b", chave_acesso="a",
                     chave_secreta="s")._url("x") == "http://localhost:9000/b/x"


def test_endpoint_com_caminho():
    """Endpoints S3 que vivem num caminho (o do Supabase Storage) mantêm o prefixo antes do bucket."""
    c = ClienteS3(endpoint="https://ref.supabase.co/storage/v1/s3/", bucket="feeds", chave_acesso="a",
                  chave_secreta="s", regiao="sa-east-1")
    assert c._url("2026/indice.json") == "https://ref.supabase.co/storage/v1/s3/feeds/2026/indice.json"
    assert c._url("", {"prefix": "2026/", "list-type": "2"}) == (
        "https://ref.supabase.co/storage/v1/s3/feeds?list-type=2&prefix=2026%2F")
