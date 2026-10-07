"""Camada bronze sobre armazenamento de objetos compatível com S3 (ADR-002, ADR-018).

Mesmas garantias do ``ArmazemBronzeLocal``, com o layout de produção:

::

    objetos/ab/cd/<sha256>                         conteúdo, gravado uma vez
    registros/<id[:2]>/<registro_id>.json          evento de coleta (leitura em O(1))
    particoes/<fonte>/<AAAA>/<MM>/<registro_id>    marcador vazio para listar por
                                                   fonte e mês, a partição do DOC-05
    por_url/<h[:2]>/<h>/v000001.json               reserva de versão da URL

Toda escrita é condicional (``If-None-Match: *``): nada é sobrescrito, nem por
engano, nem por dois coletores ao mesmo tempo. A reserva de versão usa a
mesma condição — quem recebe 412 tenta a versão seguinte —, então o
comportamento sob concorrência é idêntico ao do backend local.

Diferença deliberada em relação ao backend local: quando o conteúdo já
existe, o local relê e reconfere o hash na gravação; aqui a existência basta
(o objeto é endereçado pelo próprio hash) e a reconferência acontece na
leitura e na auditoria periódica (``verificar_integridade``). Reler cada
objeto existente a cada coleta custaria tráfego proporcional ao bronze.
"""

from __future__ import annotations

import json
import uuid
from datetime import timezone
from typing import Iterator

from .bronze import (
    ArtefatoBruto,
    IntegridadeViolada,
    RegistroColeta,
    RegistroNaoEncontrado,
    _limpar_cabecalhos,
    sha256_hex,
)
from .s3 import ChaveInexistente, ChaveJaExiste, ClienteS3


class ArmazemBronzeObjetos:
    """Backend de produção da camada bronze, sobre armazenamento de objetos compatível com S3.

    Implementa a porta ``ArmazemBronze`` com o layout e as garantias descritos no módulo.
    """

    def __init__(self, cliente: ClienteS3, *, prefixo: str = "", retencao_dias: int | None = None):
        """Guarda o cliente, o prefixo comum a todas as chaves (normalizado para terminar em ``/``) e a retenção.

        ``retencao_dias`` é repassado a cada gravação para o Object Lock; ``None`` grava sem retenção.
        """
        self.s3 = cliente
        self.prefixo = prefixo.strip("/") + "/" if prefixo.strip("/") else ""
        self.retencao_dias = retencao_dias

    # ------------------------------------------------------------ chaves

    def _k(self, chave: str) -> str:
        """Acrescenta o prefixo configurado à chave."""
        return self.prefixo + chave

    def _chave_objeto(self, sha: str) -> str:
        """Chave do conteúdo: ``objetos/ab/cd/<sha256>``."""
        return self._k(f"objetos/{sha[:2]}/{sha[2:4]}/{sha}")

    def _chave_registro(self, registro_id: str) -> str:
        """Chave do registro, ``registros/<id[:2]>/<registro_id>.json``: lida pelo id, sem listagem."""
        return self._k(f"registros/{registro_id[:2]}/{registro_id}.json")

    def _prefixo_url(self, url: str) -> str:
        """Prefixo das reservas de versão da URL, nomeado pelo SHA-256 da própria URL."""
        h = sha256_hex(url.encode("utf-8"))
        return self._k(f"por_url/{h[:2]}/{h}/")

    # ------------------------------------------------------------ escrita

    def _gravar_objeto(self, sha: str, conteudo: bytes) -> None:
        """Grava o conteúdo sob o próprio hash, se ainda não existir.

        A existência basta, porque a chave é o hash do conteúdo (ver o módulo). Se outro
        coletor gravar o mesmo conteúdo entre a verificação e a escrita, o 412 é ignorado.
        """
        chave = self._chave_objeto(sha)
        if self.s3.existe(chave):
            return
        try:
            self.s3.gravar(chave, conteudo, retencao_dias=self.retencao_dias)
        except ChaveJaExiste:
            pass  # outro coletor gravou o mesmo conteúdo no intervalo: é o mesmo hash

    def _reservar_versao(self, url: str, registro_id: str, sha: str) -> tuple[int, bool]:
        """Reserva a próxima versão da URL por gravação condicional e diz se o conteúdo mudou.

        Lê a última reserva para obter o hash anterior e tenta gravar a versão seguinte;
        se outro coletor a reservou antes (412), lista de novo e tenta a próxima. É o
        equivalente da criação exclusiva de arquivo do backend local.
        """
        prefixo = self._prefixo_url(url)
        while True:
            existentes = sorted(self.s3.listar(prefixo))
            anterior_sha = None
            if existentes:
                anterior = json.loads(self.s3.ler(existentes[-1]))
                anterior_sha = anterior["sha256"]
                proxima = int(existentes[-1].rsplit("/v", 1)[1].split(".")[0]) + 1
            else:
                proxima = 1
            corpo = json.dumps({"registro_id": registro_id, "sha256": sha, "url": url}).encode()
            try:
                self.s3.gravar(f"{prefixo}v{proxima:06d}.json", corpo, tipo="application/json",
                               retencao_dias=self.retencao_dias)
            except ChaveJaExiste:
                continue
            return proxima, (anterior_sha is None or anterior_sha != sha)

    def guardar(self, artefato: ArtefatoBruto) -> RegistroColeta:
        """Grava conteúdo, reserva de versão, registro e marcador de partição, nessa ordem.

        O marcador vazio em ``particoes/<fonte>/<AAAA>/<MM>/`` permite listar por fonte e
        mês sem varrer os registros. Os cabeçalhos sensíveis são descartados e
        ``coletado_em`` é gravado em UTC.
        """
        sha = artefato.sha256
        self._gravar_objeto(sha, artefato.conteudo)
        registro_id = uuid.uuid4().hex
        versao, mudou = self._reservar_versao(artefato.url_solicitada, registro_id, sha)
        coletado = artefato.coletado_em.astimezone(timezone.utc)
        registro = RegistroColeta(
            registro_id=registro_id, fonte_id=artefato.fonte_id,
            url_solicitada=artefato.url_solicitada, url_efetiva=artefato.url_efetiva,
            status_http=artefato.status_http, sha256=sha, tamanho_bytes=len(artefato.conteudo),
            tipo_midia=artefato.tipo_midia, cabecalhos=_limpar_cabecalhos(artefato.cabecalhos),
            coletado_em=coletado.isoformat(), versao=versao, mudou_desde_anterior=mudou,
        )
        self.s3.gravar(self._chave_registro(registro_id), registro.para_json().encode("utf-8"),
                       tipo="application/json", retencao_dias=self.retencao_dias)
        self.s3.gravar(self._k(f"particoes/{artefato.fonte_id}/{coletado:%Y}/{coletado:%m}/{registro_id}"),
                       b"", retencao_dias=self.retencao_dias)
        return registro

    # ------------------------------------------------------------ leitura

    def obter_registro(self, registro_id: str) -> RegistroColeta:
        """Lê só o registro pelo id; chave inexistente vira ``RegistroNaoEncontrado``."""
        try:
            return RegistroColeta.de_json(self.s3.ler(self._chave_registro(registro_id)).decode("utf-8"))
        except ChaveInexistente as erro:
            raise RegistroNaoEncontrado(registro_id) from erro

    def recuperar(self, registro_id: str) -> tuple[RegistroColeta, bytes]:
        """Devolve o registro e o conteúdo, com o hash reconferido na leitura.

        Objeto ausente ou com hash diferente do registrado levanta ``IntegridadeViolada``.
        """
        registro = self.obter_registro(registro_id)
        try:
            conteudo = self.s3.ler(self._chave_objeto(registro.sha256))
        except ChaveInexistente as erro:
            raise IntegridadeViolada(
                f"registro {registro_id} aponta para objeto inexistente {registro.sha256}") from erro
        encontrado = sha256_hex(conteudo)
        if encontrado != registro.sha256:
            raise IntegridadeViolada(
                f"registro {registro_id}: hash esperado {registro.sha256}, encontrado {encontrado}")
        return registro, conteudo

    def historico(self, url_solicitada: str) -> list[RegistroColeta]:
        """Todas as coletas da URL, da mais antiga para a mais recente; ignora reservas sem registro."""
        registros = []
        for chave in sorted(self.s3.listar(self._prefixo_url(url_solicitada))):
            reserva = json.loads(self.s3.ler(chave))
            try:
                registros.append(self.obter_registro(reserva["registro_id"]))
            except RegistroNaoEncontrado:
                continue
        return registros

    def listar_registros(self, fonte_id: str | None = None, ano: int | None = None,
                         mes: int | None = None) -> Iterator[RegistroColeta]:
        """Por partição quando a fonte é dada (barato); varredura completa sem ela."""
        if fonte_id:
            prefixo = f"particoes/{fonte_id}/"
            if ano:
                prefixo += f"{ano:04d}/" + (f"{mes:02d}/" if mes else "")
            for chave in self.s3.listar(self._k(prefixo)):
                yield self.obter_registro(chave.rsplit("/", 1)[1])
            return
        for chave in self.s3.listar(self._k("registros/")):
            yield RegistroColeta.de_json(self.s3.ler(chave).decode("utf-8"))

    def verificar_integridade(self) -> list[str]:
        """Relê todos os objetos e devolve, ordenados, os hashes cujo conteúdo não bate.

        É a auditoria periódica que compensa não reconferir o hash na gravação (ver o
        módulo); custa ler o bronze inteiro.
        """
        corrompidos = []
        for chave in self.s3.listar(self._k("objetos/")):
            sha = chave.rsplit("/", 1)[1]
            if sha256_hex(self.s3.ler(chave)) != sha:
                corrompidos.append(sha)
        return sorted(corrompidos)
