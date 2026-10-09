"""Configuração do pipeline local, lida de ``lumen.toml`` e do ambiente.

Precedência: variável de ambiente > arquivo > padrão. Nada sensível vive no
arquivo: o Lumen não usa credencial nas fontes da fase 1 (o token da CGU, que
entra depois, virá só de variável de ambiente ou cofre — RNF-13).

Exemplo de ``lumen.toml``::

    [coleta]
    contato = "contato@falkyria.com.br"   # vai no User-Agent (RF-CO-09)

    [dados]
    raiz = "dados"                        # bronze/ e silver/ ficam aqui

    [limites_rpm]                         # por fonte; o padrão é conservador
    pncp_contratacoes = 60
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from lumen_canonico import VERSAO_LUMEN  # reexportado: etapas importa daqui

__all__ = ["VERSAO_LUMEN", "Configuracao", "ConfiguracaoAusente", "carregar", "LIMITES_PADRAO"]

LIMITES_PADRAO = {
    "pncp_contratacoes": 60,
    "pncp_contratacoes_atualizacao": 60,
    "pncp_contratos": 60,
    "pncp_contratos_atualizacao": 60,
    "pncp_atas": 60,
    "pncp_atas_atualizacao": 60,
    "pncp_itens": 60,
    "ibge_localidades": 30,
    "ibge_populacao": 30,
    "siconfi_entes": 50,
    "siconfi_extrato": 50,
    "siconfi_rreo": 50,
    "siconfi_rgf": 50,
    "siconfi_dca": 50,
    "anp_precos_combustiveis": 10,
    "varejo_mercadolivre": 30,
}


@dataclass
class Configuracao:
    """Configuração resolvida do pipeline: contato da coleta, raiz dos dados e limites de requisições por minuto."""

    contato: str
    raiz_dados: Path
    limites_rpm: dict[str, int] = field(default_factory=lambda: dict(LIMITES_PADRAO))

    @property
    def bronze(self) -> Path:
        """Diretório da camada bronze, sob a raiz dos dados."""
        return self.raiz_dados / "bronze"

    @property
    def silver(self) -> Path:
        """Diretório da camada silver, sob a raiz dos dados."""
        return self.raiz_dados / "silver"

    def rpm(self, fonte_id: str) -> int:
        """Limite de requisições por minuto da fonte; 30 quando a fonte não tem limite configurado."""
        return int(self.limites_rpm.get(fonte_id, 30))


class ConfiguracaoAusente(Exception):
    """Falta configuração obrigatória: hoje, o contato que identifica a coleta no User-Agent."""
    pass


def carregar(caminho: Path | None = None) -> Configuracao:
    """Monta a ``Configuracao`` a partir do arquivo e do ambiente, com o ambiente prevalecendo.

    O arquivo é ``caminho``, ``LUMEN_CONFIG`` ou ``lumen.toml``, e pode não existir. ``LUMEN_CONTATO`` e
    ``LUMEN_DADOS`` substituem o contato e a raiz; os limites do arquivo sobrescrevem os padrões fonte a
    fonte. Sem contato, levanta ``ConfiguracaoAusente``: toda requisição precisa se identificar (RF-CO-09).
    """
    caminho = caminho or Path(os.environ.get("LUMEN_CONFIG", "lumen.toml"))
    dados: dict = {}
    if caminho.exists():
        with open(caminho, "rb") as fh:
            dados = tomllib.load(fh)
    contato = os.environ.get("LUMEN_CONTATO") or dados.get("coleta", {}).get("contato")
    if not contato:
        raise ConfiguracaoAusente(
            "defina o contato da coleta (e-mail ou URL) em lumen.toml, seção [coleta], "
            "ou na variável LUMEN_CONTATO: toda requisição precisa se identificar (RF-CO-09)"
        )
    raiz = Path(os.environ.get("LUMEN_DADOS") or dados.get("dados", {}).get("raiz", "dados"))
    limites = dict(LIMITES_PADRAO)
    limites.update({k: int(v) for k, v in dados.get("limites_rpm", {}).items()})
    return Configuracao(contato=contato, raiz_dados=raiz, limites_rpm=limites)
