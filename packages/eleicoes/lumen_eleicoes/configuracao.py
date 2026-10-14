"""Configuração da aba Eleições, lida do mesmo ``lumen.toml`` do pipeline.

Precedência igual à do resto do Lumen: variável de ambiente > arquivo >
padrão. Seção própria, toda opcional::

    [eleicoes]
    saida = "packages/portal/public/dados/eleicoes"   # feeds que o portal lê
    arquivos = "dados/eleicoes/arquivos"              # ZIPs dos dados abertos
    estado = "dados/eleicoes/estado"                  # estado do coletor ao vivo
    rpm_resultados = 300                              # sistema de resultados (CDN)
    rpm_dados_abertos = 30                            # CKAN e CDN de arquivos
    rpm_ibge = 30

O contato (``[coleta].contato`` ou ``LUMEN_CONTATO``) é obrigatório: vai no
User-Agent de toda requisição (RF-CO-09).

Publicação na nuvem (ADR-026), seção ``[publicacao]``, só para quem usa
``--nuvem``::

    [publicacao]
    endpoint = "https://<conta>.r2.cloudflarestorage.com"   # S3 compatível
    bucket = "lumen-eleicoes"          # público: feeds lidos pelo portal
    bucket_estado = "lumen-privado"    # privado: estado da carga (padrão: o mesmo bucket)
    regiao = "auto"

O Supabase Storage também serve (adendo do ADR-026): o endpoint é o S3 do
projeto (``https://<ref>.storage.supabase.co/storage/v1/s3``) e a região é a
do projeto, como aparece na página de configuração S3 do painel (ex.:
``sa-east-1``). Com ``auto``, o Supabase recusa a assinatura; por isso a
configuração recusa endpoint do Supabase sem região.

As chaves de acesso nunca ficam no arquivo: ``LUMEN_S3_CHAVE_ACESSO`` e
``LUMEN_S3_CHAVE_SECRETA``. Cada item também aceita variável de ambiente
(``LUMEN_PUBLICACAO_ENDPOINT``, ``LUMEN_PUBLICACAO_BUCKET``,
``LUMEN_PUBLICACAO_BUCKET_ESTADO``, ``LUMEN_PUBLICACAO_REGIAO``).
"""

from __future__ import annotations

import os
import tomllib
import urllib.parse
from dataclasses import dataclass
from pathlib import Path

from lumen_canonico import VERSAO_LUMEN
from lumen_ingestao.coleta_http import user_agent_lumen


class ConfiguracaoAusente(Exception):
    """Falta uma configuração obrigatória (hoje, só o contato que vai no User-Agent)."""

    pass


@dataclass
class ConfiguracaoEleicoes:
    """Configuração resolvida da aba Eleições: contato, diretórios e limites de taxa por fonte.

    ``saida`` recebe os feeds que o portal lê; ``arquivos``, os ZIPs dos dados
    abertos; ``estado``, o que o coletor ao vivo precisa para sobreviver a um
    reinício. Os ``rpm_*`` são requisições por minuto de cada fonte.
    """

    contato: str
    raiz_dados: Path
    saida: Path
    arquivos: Path
    estado: Path
    rpm_resultados: int = 300
    rpm_dados_abertos: int = 30
    rpm_ibge: int = 30

    @property
    def bronze(self) -> Path:
        """Diretório da camada bronze, compartilhado com o resto do Lumen (``<raiz_dados>/bronze``)."""
        return self.raiz_dados / "bronze"

    @property
    def user_agent(self) -> str:
        """User-Agent de toda requisição: versão do Lumen e o contato da coleta (RF-CO-09)."""
        return user_agent_lumen(VERSAO_LUMEN, self.contato)


def carregar(caminho: Path | None = None, *, exigir_contato: bool = True) -> ConfiguracaoEleicoes:
    """Lê o ``lumen.toml`` (ou ``LUMEN_CONFIG``) e monta a configuração, com variáveis de ambiente por cima.

    O arquivo é opcional; sem ele valem os padrões. ``LUMEN_CONTATO``,
    ``LUMEN_DADOS`` e ``LUMEN_ELEICOES_SAIDA`` têm precedência sobre o arquivo.
    Sem contato, levanta ``ConfiguracaoAusente`` — exceto com
    ``exigir_contato=False``, usado pelos comandos que não acessam a rede.
    """
    caminho = caminho or Path(os.environ.get("LUMEN_CONFIG", "lumen.toml"))
    dados: dict = {}
    if caminho.exists():
        with open(caminho, "rb") as fh:
            dados = tomllib.load(fh)
    contato = os.environ.get("LUMEN_CONTATO") or dados.get("coleta", {}).get("contato") or ""
    if exigir_contato and not contato:
        raise ConfiguracaoAusente(
            "defina o contato da coleta (e-mail ou URL) em lumen.toml, seção [coleta], "
            "ou na variável LUMEN_CONTATO: toda requisição precisa se identificar (RF-CO-09)")
    raiz = Path(os.environ.get("LUMEN_DADOS") or dados.get("dados", {}).get("raiz", "dados"))
    e = dados.get("eleicoes", {})
    return ConfiguracaoEleicoes(
        contato=contato,
        raiz_dados=raiz,
        saida=Path(os.environ.get("LUMEN_ELEICOES_SAIDA") or e.get("saida", "packages/portal/public/dados/eleicoes")),
        arquivos=Path(e.get("arquivos", raiz / "eleicoes" / "arquivos")),
        estado=Path(e.get("estado", raiz / "eleicoes" / "estado")),
        rpm_resultados=int(e.get("rpm_resultados", 300)),
        rpm_dados_abertos=int(e.get("rpm_dados_abertos", 30)),
        rpm_ibge=int(e.get("rpm_ibge", 30)),
    )


@dataclass
class ConfiguracaoPublicacao:
    """Onde publicar os feeds e guardar o estado da carga: um armazenamento compatível com S3 (R2 ou Supabase).

    ``bucket`` é o público, lido pelo portal; ``bucket_estado``, o privado, com o registro do que a carga
    já fez — sem ele, uma máquina que começa vazia a cada execução (GitHub Actions) refaria tudo.
    """

    endpoint: str
    bucket: str
    chave_acesso: str
    chave_secreta: str
    bucket_estado: str
    regiao: str = "auto"
    paralelos: int = 16
    limite_bytes: int | None = None


# Limite padrão do bucket público no Supabase gratuito (1 GB por organização, somando os dois buckets): deixa
# perto de 100 MB para o estado da carga no bucket privado. ``LUMEN_PUBLICACAO_LIMITE_MB`` = 0 tira o limite.
LIMITE_SUPABASE_MB = 900


def carregar_publicacao(caminho: Path | None = None) -> ConfiguracaoPublicacao:
    """Lê ``[publicacao]`` do ``lumen.toml`` com as variáveis de ambiente por cima.

    Levanta ``ConfiguracaoAusente`` dizendo o que falta: endpoint, bucket ou as chaves, que só vêm de
    variável de ambiente para nunca irem parar no arquivo (e no Git).
    """
    caminho = caminho or Path(os.environ.get("LUMEN_CONFIG", "lumen.toml"))
    dados: dict = {}
    if caminho.exists():
        with open(caminho, "rb") as fh:
            dados = tomllib.load(fh)
    p = dados.get("publicacao", {})

    def valor(chave: str, env: str, padrao: str = "") -> str:
        return os.environ.get(env) or str(p.get(chave, padrao) or "")

    endpoint = valor("endpoint", "LUMEN_PUBLICACAO_ENDPOINT").rstrip("/")
    bucket = valor("bucket", "LUMEN_PUBLICACAO_BUCKET")
    acesso = os.environ.get("LUMEN_S3_CHAVE_ACESSO", "")
    segredo = os.environ.get("LUMEN_S3_CHAVE_SECRETA", "")
    faltando = [nome for nome, v in (("endpoint", endpoint), ("bucket", bucket),
                                     ("LUMEN_S3_CHAVE_ACESSO", acesso), ("LUMEN_S3_CHAVE_SECRETA", segredo)) if not v]
    if faltando:
        raise ConfiguracaoAusente(
            "publicação na nuvem sem " + ", ".join(faltando) + ": defina [publicacao] no lumen.toml (endpoint e "
            "bucket) e as chaves nas variáveis LUMEN_S3_CHAVE_ACESSO e LUMEN_S3_CHAVE_SECRETA")
    regiao = valor("regiao", "LUMEN_PUBLICACAO_REGIAO", "auto")
    if eh_supabase(endpoint) and regiao == "auto":
        raise ConfiguracaoAusente(
            "o S3 do Supabase assina com a região do projeto, não com \"auto\": defina [publicacao].regiao "
            "ou LUMEN_PUBLICACAO_REGIAO com a região mostrada na configuração S3 do painel (ex.: sa-east-1)")
    paralelos = _inteiro(valor("paralelos", "LUMEN_PUBLICACAO_PARALELOS", "16"), "paralelos")
    limite_mb = _inteiro(valor("limite_mb", "LUMEN_PUBLICACAO_LIMITE_MB",
                               str(LIMITE_SUPABASE_MB) if eh_supabase(endpoint) else "0"), "limite_mb")
    return ConfiguracaoPublicacao(
        endpoint=endpoint, bucket=bucket, chave_acesso=acesso, chave_secreta=segredo,
        bucket_estado=valor("bucket_estado", "LUMEN_PUBLICACAO_BUCKET_ESTADO") or bucket,
        regiao=regiao, paralelos=max(1, paralelos), limite_bytes=limite_mb * 1_000_000 if limite_mb > 0 else None,
    )


def _inteiro(texto: str, nome: str) -> int:
    """Número inteiro de uma opção da publicação; texto que não é número vira ``ConfiguracaoAusente``."""
    try:
        return int(texto.strip())
    except ValueError:
        raise ConfiguracaoAusente(f"[publicacao].{nome} precisa ser um número inteiro, não {texto!r}") from None


def eh_supabase(endpoint: str) -> bool:
    """Se o endpoint é o S3 de um projeto do Supabase (``<ref>.supabase.co`` ou ``<ref>.storage.supabase.co``)."""
    host = urllib.parse.urlsplit(endpoint).hostname or ""
    return host == "supabase.co" or host.endswith(".supabase.co")
