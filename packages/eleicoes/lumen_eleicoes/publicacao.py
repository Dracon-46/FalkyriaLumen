"""Feeds e estado da carga na nuvem: Cloudflare R2, ou qualquer armazenamento compatível com S3 (ADR-026).

Com a publicação, a carga das eleições pode rodar numa máquina que começa
vazia a cada execução (GitHub Actions) e o portal lê os feeds de um endereço
público, sem nenhum computador pessoal ligado. Dois buckets:

- o **público** recebe os feeds (``indice.json``, ``<eleição>/<cargo>/…``,
  ``geo/``, ``municipios.json``), lidos pelo portal com ``Cache-Control``
  adequado a cada tipo;
- o **privado** guarda o estado da carga (``estado/preparar.json``, o estado
  do coletor ao vivo) e o manifesto do que já foi publicado
  (``publicacao.json``: caminho → SHA-256).

Cada execução: ``restaurar`` baixa o índice publicado e o estado; a carga roda
como na máquina local, pulando o que o estado diz que já foi feito;
``sincronizar`` envia só os arquivos cujo SHA-256 difere do manifesto — o
índice por último, para o portal nunca apontar para um feed que ainda não
subiu — e grava o estado. Uma execução interrompida no meio (limite de tempo
do GitHub Actions) é retomada pela seguinte sem refazer o que já subiu.

Só biblioteca padrão: o cliente é o mesmo ``ClienteS3`` da camada bronze
(``lumen_ingestao.s3``, assinatura SigV4).
"""

from __future__ import annotations

import gzip
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from lumen_ingestao.s3 import ChaveInexistente, ClienteS3

from .configuracao import ConfiguracaoEleicoes, ConfiguracaoPublicacao

MANIFESTO = "publicacao.json"
PREFIXO_ESTADO = "estado/"
INDICE = "indice.json"
LOTE_MANIFESTO = 1000
# Envios simultâneos. Um a um, o Supabase em sa-east-1 recebia pouco mais de um arquivo por segundo de
# uma máquina do GitHub (14/10/2026): uma passada do coletor, com mil feeds, levava mais de dez minutos.
PARALELOS = 16
# JSON sobe comprimido com gzip e ``Content-Encoding: gzip``: ocupa um terço no bucket. O Supabase (Cloudflare
# na frente) entrega comprimido a quem aceita gzip e descomprimido a quem não aceita (diagnóstico de
# 14/10/2026, nuvem-diagnostico.yml). No manifesto, o SHA-256 do arquivo comprimido ganha o sufixo
# ``MARCA_GZIP``: a primeira publicação depois da mudança reenvia, comprimido, o que tinha subido sem.
COMPRIMIR = (".json",)
MARCA_GZIP = ":gz"

TIPOS = {
    ".json": "application/json; charset=utf-8",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".md": "text/markdown; charset=utf-8",
}
# Feeds: o navegador revalida a cada leitura (o "ao vivo" depende disso). Malhas, cadastro e fotos mudam
# raramente e podem ficar um dia no cache de quem lê.
CACHE_FEED = "no-cache"
CACHE_REFERENCIA = "public, max-age=86400"


def tipo_de(relativo: str) -> str:
    """Tipo de mídia pelo sufixo do arquivo; desconhecido vira ``application/octet-stream``."""
    return TIPOS.get(Path(relativo).suffix.lower(), "application/octet-stream")


def cache_de(relativo: str) -> str:
    """``Cache-Control`` do arquivo publicado: longo para referências e fotos, ``no-cache`` para feeds."""
    if relativo.startswith(("geo/", "fotos/")) or relativo == "municipios.json":
        return CACHE_REFERENCIA
    return CACHE_FEED


def sha256_de(caminho: Path) -> str:
    """SHA-256 do conteúdo do arquivo, em hexadecimal."""
    h = hashlib.sha256()
    with open(caminho, "rb") as fh:
        for bloco in iter(lambda: fh.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def comprimir(relativo: str) -> bool:
    """Se o arquivo sobe comprimido com gzip (os JSON; imagens já são comprimidas)."""
    return Path(relativo).suffix.lower() in COMPRIMIR


def assinatura(relativo: str, sha: str) -> str:
    """Como o arquivo fica no manifesto: o SHA-256 do conteúdo, com ``MARCA_GZIP`` quando sobe comprimido."""
    return sha + MARCA_GZIP if comprimir(relativo) else sha


def descomprimir_se_gzip(conteudo: bytes) -> bytes:
    """Conteúdo lido do bucket, descomprimido se veio com a assinatura do gzip (``1f 8b``)."""
    return gzip.decompress(conteudo) if conteudo[:2] == b"\x1f\x8b" else conteudo


def arquivos_publicaveis(raiz: Path, cache: dict[str, tuple[int, int, str]] | None = None) -> dict[str, str]:
    """{caminho relativo com "/": SHA-256} de tudo o que vai para o bucket público.

    Ficam de fora os temporários da gravação atômica (``.*.tmp``, ``*.tmp``), arquivos ocultos e os
    ``LEIAME.md`` de explicação de diretório. Com ``cache`` ({caminho: (mtime_ns, tamanho, sha)}), o
    SHA-256 só é recalculado para arquivo com data ou tamanho diferente — na apuração ao vivo, a cada
    passada, só os feeds regravados são lidos de novo.
    """
    saida: dict[str, str] = {}
    if not raiz.exists():
        return saida
    for p in sorted(raiz.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(raiz).as_posix()
        nome = p.name
        if nome.startswith(".") or nome.endswith(".tmp") or nome == "LEIAME.md":
            continue
        st = p.stat()
        anterior = cache.get(rel) if cache is not None else None
        if anterior and anterior[0] == st.st_mtime_ns and anterior[1] == st.st_size:
            saida[rel] = anterior[2]
            continue
        saida[rel] = sha256_de(p)
        if cache is not None:
            cache[rel] = (st.st_mtime_ns, st.st_size, saida[rel])
    return saida


@dataclass
class ResumoPublicacao:
    """Contagem de uma publicação: arquivos enviados, já iguais no bucket e bytes enviados."""

    enviados: int = 0
    iguais: int = 0
    bytes: int = 0


class Nuvem:
    """Ponte entre os diretórios locais da carga (feeds e estado) e os dois buckets."""

    def __init__(self, feeds: ClienteS3, estado: ClienteS3, saida: Path, dir_estado: Path, *,
                 aviso: Callable[[str], None] | None = None, paralelos: int = PARALELOS):
        """Clientes dos buckets público (``feeds``) e privado (``estado``), os diretórios locais e quantos
        arquivos sobem ao mesmo tempo."""
        self.feeds = feeds
        self.estado = estado
        self.saida = Path(saida)
        self.dir_estado = Path(dir_estado)
        self.aviso = aviso or (lambda msg: print(msg, flush=True))
        self.paralelos = max(1, paralelos)
        self._manifesto: dict[str, str] | None = None
        self._hashes: dict[str, tuple[int, int, str]] = {}

    @classmethod
    def de_configuracao(cls, pub: ConfiguracaoPublicacao, cfg: ConfiguracaoEleicoes, *,
                        aviso: Callable[[str], None] | None = None) -> "Nuvem":
        """Monta os dois clientes S3 (estilo caminho, que o R2 aceita) a partir da configuração."""
        def cliente(bucket: str) -> ClienteS3:
            return ClienteS3(endpoint=pub.endpoint, bucket=bucket, chave_acesso=pub.chave_acesso,
                             chave_secreta=pub.chave_secreta, regiao=pub.regiao, estilo_caminho=True)
        return cls(cliente(pub.bucket), cliente(pub.bucket_estado), cfg.saida, cfg.estado, aviso=aviso)

    # ------------------------------------------------------------ manifesto

    def manifesto(self) -> dict[str, str]:
        """O que já está publicado ({caminho: SHA-256}), lido uma vez do bucket privado."""
        if self._manifesto is None:
            try:
                self._manifesto = dict(json.loads(self.estado.ler(MANIFESTO)).get("arquivos") or {})
            except ChaveInexistente:
                self._manifesto = {}
        return self._manifesto

    def _gravar_manifesto(self) -> None:
        """Grava o manifesto no bucket privado (sobrescrevendo o anterior)."""
        corpo = json.dumps({"versao": 1, "arquivos": self.manifesto()}, sort_keys=True,
                           separators=(",", ":")).encode("utf-8")
        self.estado.gravar(MANIFESTO, corpo, sem_sobrescrever=False, tipo="application/json")

    # ------------------------------------------------------------ operações

    def restaurar(self) -> int:
        """Baixa o índice publicado (se não há um local) e o estado da carga; devolve quantos arquivos vieram.

        O índice local, quando existe, vence: é a máquina em que a carga está rodando que sabe o que gerou.
        """
        vieram = 0
        indice = self.saida / INDICE
        if not indice.exists():
            try:
                conteudo = self.feeds.ler(INDICE)
            except ChaveInexistente:
                conteudo = None
            if conteudo is not None:
                indice.parent.mkdir(parents=True, exist_ok=True)
                indice.write_bytes(descomprimir_se_gzip(conteudo))
                vieram += 1
        for chave in self.estado.listar(PREFIXO_ESTADO):
            rel = chave[len(PREFIXO_ESTADO):]
            if not rel or ".." in Path(rel).parts:
                continue
            destino = self.dir_estado / rel
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_bytes(self.estado.ler(chave))
            vieram += 1
        self.manifesto()
        self.aviso(f"nuvem: {vieram} arquivo(s) restaurado(s) (índice e estado da carga)")
        return vieram

    def publicar(self) -> ResumoPublicacao:
        """Envia ao bucket público os arquivos novos ou alterados, ``paralelos`` de cada vez; o índice por último.

        O índice só sobe depois de todos os outros terem subido, para o portal nunca apontar para um feed que
        ainda não está lá. O manifesto registra só o que subiu e é regravado a cada ``LOTE_MANIFESTO``
        envios e no fim, também quando um envio falha: uma interrupção perde no máximo um lote, que a
        próxima publicação reenvia. A primeira falha de um lote é levantada depois que o lote termina.
        """
        resumo = ResumoPublicacao()
        publicado = self.manifesto()
        locais = {rel: assinatura(rel, h) for rel, h in arquivos_publicaveis(self.saida, self._hashes).items()}
        mudaram = sorted(rel for rel, h in locais.items() if publicado.get(rel) != h)
        resumo.iguais = len(locais) - len(mudaram)
        antes = [rel for rel in mudaram if rel != INDICE]
        lotes = [antes[i:i + LOTE_MANIFESTO] for i in range(0, len(antes), LOTE_MANIFESTO)]
        if INDICE in mudaram:
            lotes.append([INDICE])
        for lote in lotes:
            falha: Exception | None = None
            with ThreadPoolExecutor(max_workers=min(self.paralelos, len(lote))) as ex:
                futuros = {ex.submit(self._enviar, rel): rel for rel in lote}
                for futuro in as_completed(futuros):
                    rel = futuros[futuro]
                    try:
                        tamanho = futuro.result()
                    except Exception as erro:  # noqa: BLE001 - o lote termina; a falha sobe depois
                        falha = falha or erro
                        continue
                    publicado[rel] = locais[rel]
                    resumo.enviados += 1
                    resumo.bytes += tamanho
            self._gravar_manifesto()
            if falha is not None:
                raise falha
        self.aviso(f"nuvem: {resumo.enviados} arquivo(s) publicado(s) ({resumo.bytes / 1e6:,.1f} MB), "
                   f"{resumo.iguais} já iguais")
        return resumo

    def _enviar(self, rel: str) -> int:
        """Envia um arquivo da saída ao bucket público com o tipo e o cache dele (JSON comprimido com gzip);
        devolve quantos bytes subiram."""
        corpo = (self.saida / rel).read_bytes()
        codificacao = None
        if comprimir(rel):
            corpo, codificacao = gzip.compress(corpo, compresslevel=6, mtime=0), "gzip"
        self.feeds.gravar(rel, corpo, sem_sobrescrever=False, tipo=tipo_de(rel), cache=cache_de(rel),
                          codificacao=codificacao)
        return len(corpo)

    def salvar_estado(self) -> int:
        """Envia ao bucket privado os arquivos do diretório de estado; devolve quantos."""
        n = 0
        if self.dir_estado.exists():
            for p in sorted(self.dir_estado.rglob("*")):
                if p.is_file() and not p.name.endswith(".tmp"):
                    rel = p.relative_to(self.dir_estado).as_posix()
                    self.estado.gravar(PREFIXO_ESTADO + rel, p.read_bytes(), sem_sobrescrever=False,
                                       tipo=tipo_de(rel))
                    n += 1
        return n

    def sincronizar(self) -> ResumoPublicacao:
        """Publica os feeds e grava o estado: o ponto de salvamento depois de cada etapa da carga."""
        resumo = self.publicar()
        self.salvar_estado()
        return resumo
