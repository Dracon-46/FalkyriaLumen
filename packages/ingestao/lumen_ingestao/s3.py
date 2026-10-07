"""Cliente S3 mínimo, só com a biblioteca padrão (ADR-015, ADR-018).

Fala o protocolo S3 com assinatura AWS Signature Version 4, o que serve ao
MinIO do ambiente local e a qualquer armazenamento compatível em produção. Só
implementa o que a camada bronze usa: gravar sem sobrescrever, ler, verificar
existência e listar por prefixo.

Por que não boto3: a camada bronze é a parte que guarda a prova, e é a parte
em que menos superfície de ataque se quer (ADR-015). O protocolo usado aqui é
pequeno, estável há uma década e coberto pelo vetor de teste oficial da AWS
(``test_s3.py``).

Gravação sem sobrescrever
-------------------------
``PUT`` com ``If-None-Match: *`` é a escrita condicional do S3: se a chave já
existe, a resposta é 412 e nada muda. É a mesma garantia que o backend local
obtém com criação exclusiva de arquivo, e é ela que permite reservar versões
de URL sem corrida entre coletores. Suportada pela AWS desde 2024 e pelo
MinIO.

Retenção (WORM)
---------------
Com o bucket criado com Object Lock, ``retencao_dias`` grava cada objeto em
modo COMPLIANCE: nem o administrador apaga antes do prazo. É a versão
"de verdade" do somente-leitura que o backend local só imita com chmod.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterator

SHA256_VAZIO = hashlib.sha256(b"").hexdigest()


class ErroS3(Exception):
    """Resposta de erro do armazenamento de objetos; o status HTTP fica em ``status``."""

    def __init__(self, status: int, mensagem: str):
        """Guarda o status e monta a mensagem no formato ``S3 <status>: <mensagem>``."""
        super().__init__(f"S3 {status}: {mensagem}")
        self.status = status


class ChaveJaExiste(ErroS3):
    """412 em PUT condicional: a chave já existia e não foi tocada."""


class ChaveInexistente(ErroS3):
    """404 na leitura: a chave pedida não existe no bucket."""


def _hmac(chave: bytes, msg: str) -> bytes:
    """HMAC-SHA256 de ``msg``: o passo repetido na derivação da chave de assinatura SigV4."""
    return hmac.new(chave, msg.encode("utf-8"), hashlib.sha256).digest()


def _codificar_caminho(caminho: str) -> str:
    """Codifica o caminho segmento a segmento, como o S3 exige na URL e na requisição canônica."""
    # S3 codifica cada segmento; a barra separa segmentos e não é codificada.
    return "/".join(urllib.parse.quote(p, safe="-_.~") for p in caminho.split("/"))


def assinar_v4(
    metodo: str,
    url: str,
    cabecalhos: dict[str, str],
    *,
    chave_acesso: str,
    chave_secreta: str,
    regiao: str,
    instante: datetime,
    hash_corpo: str,
    servico: str = "s3",
) -> dict[str, str]:
    """Devolve os cabeçalhos com ``Authorization`` (SigV4) acrescentado.

    ``cabecalhos`` precisa conter ``host``. ``x-amz-date`` e
    ``x-amz-content-sha256`` são acrescentados aqui.
    """
    partes = urllib.parse.urlsplit(url)
    amz_data = instante.strftime("%Y%m%dT%H%M%SZ")
    dia = instante.strftime("%Y%m%d")
    todos = {k.lower(): str(v).strip() for k, v in cabecalhos.items()}
    todos["x-amz-date"] = amz_data
    todos["x-amz-content-sha256"] = hash_corpo
    nomes = sorted(todos)
    canonicos = "".join(f"{n}:{' '.join(todos[n].split())}\n" for n in nomes)
    assinados = ";".join(nomes)
    consulta = urllib.parse.parse_qsl(partes.query, keep_blank_values=True)
    consulta_canonica = "&".join(
        f"{urllib.parse.quote(k, safe='-_.~')}={urllib.parse.quote(v, safe='-_.~')}"
        for k, v in sorted(consulta)
    )
    requisicao = "\n".join([
        metodo.upper(),
        _codificar_caminho(urllib.parse.unquote(partes.path or "/")),
        consulta_canonica,
        canonicos,
        assinados,
        hash_corpo,
    ])
    escopo = f"{dia}/{regiao}/{servico}/aws4_request"
    texto = "\n".join([
        "AWS4-HMAC-SHA256", amz_data, escopo,
        hashlib.sha256(requisicao.encode("utf-8")).hexdigest(),
    ])
    k = _hmac(("AWS4" + chave_secreta).encode("utf-8"), dia)
    k = _hmac(k, regiao)
    k = _hmac(k, servico)
    k = _hmac(k, "aws4_request")
    assinatura = hmac.new(k, texto.encode("utf-8"), hashlib.sha256).hexdigest()
    todos["authorization"] = (
        f"AWS4-HMAC-SHA256 Credential={chave_acesso}/{escopo}, "
        f"SignedHeaders={assinados}, Signature={assinatura}"
    )
    return todos


@dataclass
class ClienteS3:
    """Cliente S3 com as operações que a camada bronze usa: gravar, ler, verificar existência e listar.

    Toda requisição é assinada com SigV4. ``estilo_caminho`` escolhe entre ``endpoint/bucket/chave``
    (MinIO, ambiente local) e ``bucket.endpoint/chave`` (AWS virtual-hosted). ``abridor`` permite
    substituir o transporte, por exemplo nos testes.
    """

    endpoint: str              # ex.: http://localhost:9000
    bucket: str
    chave_acesso: str
    chave_secreta: str
    regiao: str = "us-east-1"
    estilo_caminho: bool = True  # MinIO e ambientes locais; False para AWS virtual-hosted
    timeout: float = 60
    abridor: urllib.request.OpenerDirector | None = None

    def _url(self, chave: str = "", consulta: dict[str, str] | None = None) -> str:
        """Monta a URL da chave no estilo configurado, com caminho codificado e consulta em ordem fixa."""
        base = urllib.parse.urlsplit(self.endpoint)
        if self.estilo_caminho:
            host = base.netloc
            caminho = f"/{self.bucket}" + (f"/{chave}" if chave else "")
        else:
            host = f"{self.bucket}.{base.netloc}"
            caminho = f"/{chave}"
        q = urllib.parse.urlencode(sorted((consulta or {}).items()))
        return urllib.parse.urlunsplit((base.scheme, host, _codificar_caminho(caminho), q, ""))

    def _enviar(self, metodo: str, url: str, corpo: bytes = b"",
                extras: dict[str, str] | None = None) -> tuple[int, dict[str, str], bytes]:
        """Assina e envia a requisição; devolve status, cabeçalhos em minúsculas e corpo.

        Erro HTTP não levanta exceção aqui: volta como status, e cada operação decide o
        que ele significa (412 na gravação, 404 na leitura). O ``host`` entra na
        assinatura, mas sai dos cabeçalhos enviados, porque o urllib o preenche sozinho.
        """
        partes = urllib.parse.urlsplit(url)
        cab = {"host": partes.netloc, **(extras or {})}
        assinados = assinar_v4(metodo, url, cab, chave_acesso=self.chave_acesso,
                               chave_secreta=self.chave_secreta, regiao=self.regiao,
                               instante=datetime.now(timezone.utc),
                               hash_corpo=hashlib.sha256(corpo).hexdigest())
        assinados.pop("host")
        req = urllib.request.Request(url, data=corpo if metodo in ("PUT", "POST") else None,
                                     headers=assinados, method=metodo)
        abridor = self.abridor or urllib.request.build_opener()
        try:
            with abridor.open(req, timeout=self.timeout) as r:
                return r.status, {k.lower(): v for k, v in r.headers.items()}, r.read()
        except urllib.error.HTTPError as e:
            return e.code, {k.lower(): v for k, v in (e.headers or {}).items()}, e.read() or b""

    # ------------------------------------------------------------------ operações

    def gravar(self, chave: str, corpo: bytes, *, sem_sobrescrever: bool = True,
               tipo: str = "application/octet-stream", retencao_dias: int | None = None,
               cache: str | None = None) -> None:
        """Grava o objeto; por padrão, só se a chave ainda não existir (``If-None-Match: *``).

        412 levanta ``ChaveJaExiste`` sem que nada tenha mudado; outro erro levanta ``ErroS3``.
        Envia ``Content-MD5``, exigido pelo Object Lock, e, com ``retencao_dias``, grava em
        modo COMPLIANCE até a data calculada a partir de agora. ``cache`` vira o ``Cache-Control``
        que o armazenamento devolve a quem lê o objeto (feeds publicados, ADR-026).
        """
        extras = {
            "content-type": tipo,
            "content-length": str(len(corpo)),
            "content-md5": base64.b64encode(hashlib.md5(corpo).digest()).decode(),  # noqa: S324 - integridade em trânsito, exigida pelo Object Lock
        }
        if sem_sobrescrever:
            extras["if-none-match"] = "*"
        if cache:
            extras["cache-control"] = cache
        if retencao_dias:
            ate = datetime.now(timezone.utc) + timedelta(days=retencao_dias)
            extras["x-amz-object-lock-mode"] = "COMPLIANCE"
            extras["x-amz-object-lock-retain-until-date"] = ate.strftime("%Y-%m-%dT%H:%M:%SZ")
        status, _, resposta = self._enviar("PUT", self._url(chave), corpo, extras)
        if status == 412:
            raise ChaveJaExiste(status, chave)
        if status >= 300:
            raise ErroS3(status, resposta[:300].decode("utf-8", "replace"))

    def ler(self, chave: str) -> bytes:
        """Lê o conteúdo da chave; 404 levanta ``ChaveInexistente`` e outro erro, ``ErroS3``."""
        status, _, corpo = self._enviar("GET", self._url(chave))
        if status == 404:
            raise ChaveInexistente(status, chave)
        if status >= 300:
            raise ErroS3(status, corpo[:300].decode("utf-8", "replace"))
        return corpo

    def existe(self, chave: str) -> bool:
        """Verifica a existência da chave com ``HEAD``, sem baixar o conteúdo."""
        status, _, _ = self._enviar("HEAD", self._url(chave))
        if status == 404:
            return False
        if status >= 300:
            raise ErroS3(status, chave)
        return True

    def listar(self, prefixo: str) -> Iterator[str]:
        """Chaves sob o prefixo, em ordem lexicográfica (ListObjectsV2, paginado)."""
        token = None
        while True:
            q = {"list-type": "2", "prefix": prefixo}
            if token:
                q["continuation-token"] = token
            status, _, corpo = self._enviar("GET", self._url("", q))
            if status >= 300:
                raise ErroS3(status, corpo[:300].decode("utf-8", "replace"))
            raiz = ET.fromstring(corpo)
            ns = raiz.tag[: raiz.tag.index("}") + 1] if raiz.tag.startswith("{") else ""
            for item in raiz.findall(f"{ns}Contents"):
                yield item.findtext(f"{ns}Key")
            if raiz.findtext(f"{ns}IsTruncated") == "true":
                token = raiz.findtext(f"{ns}NextContinuationToken")
            else:
                return
