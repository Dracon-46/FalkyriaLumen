"""Camada bronze: a prova.

Tudo o que o Lumen afirma precisa poder ser mostrado exatamente como estava
publicado na data da coleta (DOC-01, princípio P1; ADR-002). Portais de
transparência reescrevem e removem páginas o tempo todo. Se a prova não
estiver guardada aqui, íntegra e datada, o indício não se sustenta.

Garantias desta camada
----------------------
1. **Nada é sobrescrito.** Nova coleta da mesma URL gera nova versão; a
   anterior continua intacta (RF-CO-07).
2. **Conteúdo endereçado por hash.** O arquivo é guardado sob o próprio
   SHA-256. Conteúdo idêntico é armazenado uma vez só, mas cada *evento* de
   coleta gera seu próprio registro. Isso separa duas coisas que importam de
   forma diferente:

   - o conteúdo (quantos bytes guardamos) — deduplicado, economiza espaço;
   - o fato de ter sido coletado em tal data — nunca deduplicado, porque
     "a página continuava publicada, sem alteração, em 12/03" é evidência.

3. **Hash reconferido em toda leitura.** Prova corrompida nunca é devolvida
   em silêncio: a leitura levanta ``IntegridadeViolada``.
4. **Alteração na fonte vira dado.** Cada registro diz se o conteúdo mudou em
   relação à versão anterior da mesma URL. Um portal que altera um contrato
   já publicado deixa rastro — e isso, por si só, pode interessar à análise.

Layout do backend local
-----------------------
::

    <raiz>/
      objetos/ab/cd/<sha256>                    conteúdo, somente leitura
      registros/<id[:2]>/<registro_id>.json     um arquivo por evento de coleta
      por_url/<h[:2]>/<h>/v000001.json          índice de versões da URL

O DOC-05 particiona o bronze por fonte, ano e mês. Esse particionamento é o do
backend de armazenamento de objetos, onde listar por prefixo é a operação
barata. No backend local o que importa é recuperar um registro pelo id em
tempo constante, então os registros ficam por id e a listagem por fonte e
período faz varredura — aceitável em desenvolvimento, e é por isso que este
backend não é o de produção.

Consistência em caso de queda
-----------------------------
A ordem de escrita é: conteúdo, reserva de versão, registro. Cada passo usa
criação exclusiva ou troca atômica de arquivo, então nenhum passo deixa
arquivo pela metade. Uma queda entre a reserva e o registro deixa uma versão
reservada sem registro: ``verificar_consistencia`` a reporta e ``historico``
a ignora. Um conteúdo sem registro é inofensivo — é só um objeto órfão.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tempfile
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Mapping, Protocol, runtime_checkable

# Cabeçalhos que podem carregar credencial ou sessão. São descartados antes de
# gravar: a prova precisa de Date, Last-Modified, ETag e Content-Type, não de
# cookies de sessão de portal nenhum.
CABECALHOS_SENSIVEIS = frozenset({
    "set-cookie",
    "cookie",
    "authorization",
    "proxy-authorization",
})

_FONTE_ID_VALIDO = re.compile(r"^[a-z0-9][a-z0-9_\-]{0,127}$")


class ErroBronze(Exception):
    """Erro na camada bronze."""


class IntegridadeViolada(ErroBronze):
    """O conteúdo guardado não corresponde mais ao hash registrado.

    É um incidente, não um erro comum: significa que a prova foi alterada ou
    corrompida no armazenamento. Nunca deve ser tratado em silêncio.
    """


class RegistroNaoEncontrado(ErroBronze, KeyError):
    """Não existe registro de coleta com o identificador pedido."""


def sha256_hex(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()


def _agora_utc() -> datetime:
    return datetime.now(timezone.utc)


def _limpar_cabecalhos(cabecalhos: Mapping[str, str]) -> dict[str, str]:
    return {
        k.lower(): v
        for k, v in cabecalhos.items()
        if k.lower() not in CABECALHOS_SENSIVEIS
    }


def validar_fonte_id(fonte_id: str) -> str:
    """O id da fonte vira componente de caminho: precisa ser inofensivo.

    Sem esta validação, um id como ``../../etc`` escreveria fora da raiz.
    """
    if not _FONTE_ID_VALIDO.match(fonte_id):
        raise ValueError(
            f"fonte_id inválido: {fonte_id!r}. Use apenas letras minúsculas, "
            "dígitos, '_' e '-', começando por letra ou dígito."
        )
    return fonte_id


@dataclass(frozen=True)
class ArtefatoBruto:
    """Exatamente o que a fonte entregou, sem nenhuma transformação."""

    conteudo: bytes
    fonte_id: str
    url_solicitada: str
    url_efetiva: str
    status_http: int
    tipo_midia: str
    cabecalhos: Mapping[str, str] = field(default_factory=dict)
    coletado_em: datetime = field(default_factory=_agora_utc)

    def __post_init__(self) -> None:
        validar_fonte_id(self.fonte_id)
        if self.coletado_em.tzinfo is None:
            raise ValueError("coletado_em precisa ter fuso horário; use UTC")
        if not self.url_solicitada:
            raise ValueError("url_solicitada é obrigatória")

    @property
    def sha256(self) -> str:
        return sha256_hex(self.conteudo)


@dataclass(frozen=True)
class RegistroColeta:
    """Um evento de coleta. Imutável e somente-anexação.

    ``status_http`` fica registrado porque, pelo princípio P5, a ausência de
    dado é informação: um portal que devolve 404 para o que a lei manda
    publicar é um achado, e a resposta 404 datada é a prova desse achado.
    """

    registro_id: str
    fonte_id: str
    url_solicitada: str
    url_efetiva: str
    status_http: int
    sha256: str
    tamanho_bytes: int
    tipo_midia: str
    cabecalhos: dict[str, str]
    coletado_em: str          # ISO 8601 em UTC
    versao: int               # 1 na primeira coleta desta URL
    mudou_desde_anterior: bool

    def para_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True, indent=2)

    @classmethod
    def de_json(cls, texto: str) -> "RegistroColeta":
        return cls(**json.loads(texto))


@runtime_checkable
class ArmazemBronze(Protocol):
    """Porta de armazenamento da prova. Backends: local agora, objetos depois."""

    def guardar(self, artefato: ArtefatoBruto) -> RegistroColeta: ...
    def recuperar(self, registro_id: str) -> tuple[RegistroColeta, bytes]: ...
    def historico(self, url_solicitada: str) -> list[RegistroColeta]: ...


class ArmazemBronzeLocal:
    """Backend em sistema de arquivos, para desenvolvimento e testes."""

    def __init__(self, raiz: Path | str):
        self.raiz = Path(raiz)
        self._objetos = self.raiz / "objetos"
        self._registros = self.raiz / "registros"
        self._por_url = self.raiz / "por_url"
        for d in (self._objetos, self._registros, self._por_url):
            d.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ caminhos

    def _caminho_objeto(self, sha: str) -> Path:
        return self._objetos / sha[:2] / sha[2:4] / sha

    def _caminho_registro(self, registro_id: str) -> Path:
        return self._registros / registro_id[:2] / f"{registro_id}.json"

    def _dir_url(self, url: str) -> Path:
        h = sha256_hex(url.encode("utf-8"))
        return self._por_url / h[:2] / h

    # ------------------------------------------------------------------ escrita

    def _gravar_objeto(self, sha: str, conteudo: bytes) -> bool:
        """Grava o conteúdo sob o próprio hash. Devolve True se era novo."""
        destino = self._caminho_objeto(sha)
        if destino.exists():
            # Já existe: confere antes de confiar. Se o objeto guardado estiver
            # corrompido, isso é um incidente — não vamos "consertar" em
            # silêncio e esconder que a prova foi alterada.
            if sha256_hex(destino.read_bytes()) != sha:
                raise IntegridadeViolada(
                    f"objeto {sha} existe mas seu conteúdo não bate com o hash"
                )
            return False

        destino.parent.mkdir(parents=True, exist_ok=True)
        # Escreve em temporário no mesmo diretório e troca atomicamente:
        # quem ler nunca vê arquivo pela metade.
        fd, tmp = tempfile.mkstemp(dir=destino.parent, prefix=".tmp-")
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(conteudo)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, destino)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        # Somente leitura: não impede um administrador de alterar, mas impede
        # acidente. A garantia real é a reconferência do hash na leitura.
        os.chmod(destino, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        return True

    def _reservar_versao(self, url: str, registro_id: str, sha: str) -> tuple[int, bool]:
        """Reserva a próxima versão da URL por criação exclusiva de arquivo.

        Criação exclusiva é atômica e portável (inclusive no Windows), então
        dois processos coletando a mesma URL ao mesmo tempo nunca recebem a
        mesma versão: o segundo recebe erro e tenta a seguinte.
        """
        diretorio = self._dir_url(url)
        diretorio.mkdir(parents=True, exist_ok=True)
        while True:
            existentes = sorted(diretorio.glob("v*.json"))
            anterior_sha = None
            if existentes:
                anterior = json.loads(existentes[-1].read_text(encoding="utf-8"))
                anterior_sha = anterior["sha256"]
                proxima = int(existentes[-1].stem[1:]) + 1
            else:
                proxima = 1
            try:
                with open(diretorio / f"v{proxima:06d}.json", "x", encoding="utf-8") as fh:
                    json.dump({"registro_id": registro_id, "sha256": sha, "url": url}, fh)
            except FileExistsError:
                continue  # outro processo reservou esta versão; tenta a próxima
            mudou = anterior_sha is None or anterior_sha != sha
            return proxima, mudou

    def guardar(self, artefato: ArtefatoBruto) -> RegistroColeta:
        sha = artefato.sha256
        self._gravar_objeto(sha, artefato.conteudo)

        registro_id = uuid.uuid4().hex
        versao, mudou = self._reservar_versao(artefato.url_solicitada, registro_id, sha)

        registro = RegistroColeta(
            registro_id=registro_id,
            fonte_id=artefato.fonte_id,
            url_solicitada=artefato.url_solicitada,
            url_efetiva=artefato.url_efetiva,
            status_http=artefato.status_http,
            sha256=sha,
            tamanho_bytes=len(artefato.conteudo),
            tipo_midia=artefato.tipo_midia,
            cabecalhos=_limpar_cabecalhos(artefato.cabecalhos),
            coletado_em=artefato.coletado_em.astimezone(timezone.utc).isoformat(),
            versao=versao,
            mudou_desde_anterior=mudou,
        )

        caminho = self._caminho_registro(registro_id)
        caminho.parent.mkdir(parents=True, exist_ok=True)
        # "x": se por qualquer motivo já existir registro com este id, falha
        # em vez de sobrescrever. Registro é somente-anexação.
        with open(caminho, "x", encoding="utf-8") as fh:
            fh.write(registro.para_json())
        return registro

    # ------------------------------------------------------------------ leitura

    def obter_registro(self, registro_id: str) -> RegistroColeta:
        caminho = self._caminho_registro(registro_id)
        if not caminho.exists():
            raise RegistroNaoEncontrado(registro_id)
        return RegistroColeta.de_json(caminho.read_text(encoding="utf-8"))

    def recuperar(self, registro_id: str) -> tuple[RegistroColeta, bytes]:
        """Devolve o registro e o conteúdo, com o hash reconferido."""
        registro = self.obter_registro(registro_id)
        caminho = self._caminho_objeto(registro.sha256)
        if not caminho.exists():
            raise IntegridadeViolada(
                f"registro {registro_id} aponta para objeto inexistente {registro.sha256}"
            )
        conteudo = caminho.read_bytes()
        encontrado = sha256_hex(conteudo)
        if encontrado != registro.sha256:
            raise IntegridadeViolada(
                f"registro {registro_id}: hash esperado {registro.sha256}, "
                f"encontrado {encontrado}"
            )
        return registro, conteudo

    def historico(self, url_solicitada: str) -> list[RegistroColeta]:
        """Todas as coletas da URL, da mais antiga para a mais recente."""
        diretorio = self._dir_url(url_solicitada)
        if not diretorio.exists():
            return []
        registros = []
        for entrada in sorted(diretorio.glob("v*.json")):
            reserva = json.loads(entrada.read_text(encoding="utf-8"))
            try:
                registros.append(self.obter_registro(reserva["registro_id"]))
            except RegistroNaoEncontrado:
                continue  # versão reservada sem registro: coleta interrompida
        return registros

    def listar_registros(self, fonte_id: str | None = None) -> Iterator[RegistroColeta]:
        for caminho in sorted(self._registros.glob("*/*.json")):
            registro = RegistroColeta.de_json(caminho.read_text(encoding="utf-8"))
            if fonte_id is None or registro.fonte_id == fonte_id:
                yield registro

    # ------------------------------------------------------------------ auditoria

    def verificar_integridade(self) -> list[str]:
        """Reconfere o hash de todos os objetos. Devolve os hashes corrompidos.

        Deve rodar periodicamente (RNF-08): corrupção silenciosa de prova é o
        pior modo de falha possível para este projeto.
        """
        corrompidos = []
        for caminho in self._objetos.glob("*/*/*"):
            if caminho.name.startswith(".tmp-") or not caminho.is_file():
                continue
            if sha256_hex(caminho.read_bytes()) != caminho.name:
                corrompidos.append(caminho.name)
        return sorted(corrompidos)

    def verificar_consistencia(self) -> list[str]:
        """Versões reservadas cujo registro não existe (coletas interrompidas)."""
        pendentes = []
        for entrada in self._por_url.glob("*/*/v*.json"):
            reserva = json.loads(entrada.read_text(encoding="utf-8"))
            if not self._caminho_registro(reserva["registro_id"]).exists():
                pendentes.append(f"{reserva['url']} {entrada.stem}")
        return sorted(pendentes)
