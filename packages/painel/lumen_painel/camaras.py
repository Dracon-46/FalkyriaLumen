"""As câmaras municipais com o SAPL do Interlegis e a API aberta (ADR-062): o cadastro que a coleta dos vereadores usa.

O SAPL (Sistema de Apoio ao Processo Legislativo) do Interlegis guarda, em cada câmara que o usa, os vereadores, os
mandatos e as filiações, as matérias com os autores, as sessões com a presença e as votações com o voto de cada um, e
tem uma API REST aberta (``/api/``). As câmaras hospedadas pelo Interlegis ficam em ``sapl.<cidade>.<uf>.leg.br``, com
o nome do município sem acento, sem espaço e sem pontuação.

O levantamento (``levantar``) testa esse endereço para cada município do cadastro, um pedido por câmara, alguns ao
mesmo tempo (são servidores diferentes), e guarda as que responderam com o número de parlamentares que a câmara tem
no SAPL. Em 3/11/2026, foram 1.192 das 5.570 (21%): 971 com matérias, 584 com ao menos 100 votos nominais (5,1 milhões
de votos somados) e 870 com presença. Câmara com o SAPL noutro endereço fica de fora até entrar à mão
(``ENDERECOS_EXTRAS``).

O levantamento testa também as Assembleias Legislativas, em ``sapl.al.<uf>.leg.br``, guardadas com o código da UF
(2 dígitos): em 4/11/2026, 9 responderam (AC, AL, AM, MT, PB, PI, RO, RR e TO).
"""

from __future__ import annotations

import json
import re
import ssl
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

from .cadastro import Cadastro
from .comum import gravar_json, instante_utc, ler_json, sem_acento

ARQUIVO = "camaras-sapl.json.gz"
VERSAO_ESTADO = 1
SIMULTANEOS = 24
# Câmaras com o SAPL fora do endereço padrão, achadas à mão: código IBGE → endereço
ENDERECOS_EXTRAS: dict[str, str] = {}


def endereco(nome: str, uf: str) -> str:
    """O endereço padrão do SAPL hospedado pelo Interlegis ("São José dos Campos", "SP" →
    ``sapl.saojosedoscampos.sp.leg.br``)."""
    return f"sapl.{re.sub(r'[^a-z0-9]', '', sem_acento(nome).lower())}.{uf.lower()}.leg.br"


def endereco_assembleia(uf: str) -> str:
    """O endereço do SAPL da Assembleia Legislativa hospedado pelo Interlegis ("AM" → ``sapl.al.am.leg.br``)."""
    return f"sapl.al.{uf.lower()}.leg.br"


def testar(host: str, *, contato: str, abrir: Callable[..., object] | None = None) -> int | None:
    """Quantos parlamentares a câmara tem no SAPL, ou ``None`` se o endereço não responde com a API."""
    url = f"https://{host}/api/parlamentares/parlamentar/?page_size=1"
    pedido = urllib.request.Request(url, headers={"User-Agent": f"Lumen (contato: {contato})"})
    try:
        abrir = abrir or (lambda p: urllib.request.urlopen(p, timeout=12, context=ssl.create_default_context()))
        with abrir(pedido) as r:  # type: ignore[attr-defined]
            total = (json.loads(r.read()).get("pagination") or {}).get("total_entries")
        return int(total) if isinstance(total, int) else None
    except Exception:  # noqa: BLE001 — endereço que não existe, sem API ou fora do ar: a câmara fica de fora
        return None


def levantar(estado: Path | str, cadastro: Cadastro, *, contato: str,
             testar_fn: Callable[..., int | None] = testar) -> dict:
    """Testa o SAPL de cada município e de cada Assembleia e grava ``ARQUIVO``: ``{código IBGE: [endereço,
    parlamentares]}``, com a data."""
    municipios = sorted(c for c in cadastro.entes if len(c) == 7)
    estados = sorted(c for c in cadastro.entes if len(c) == 2)

    def um(codigo: str) -> tuple[str, str, int | None]:
        ente = cadastro.entes[codigo]
        host = ENDERECOS_EXTRAS.get(codigo) or (endereco(ente.nome, ente.uf) if len(codigo) == 7
                                                 else endereco_assembleia(ente.uf))
        return codigo, host, testar_fn(host, contato=contato)

    with ThreadPoolExecutor(SIMULTANEOS) as grupo:
        resultados = list(grupo.map(um, municipios + estados))
    camaras = {c: [h, n] for c, h, n in resultados if n is not None}
    dados = {"versao": VERSAO_ESTADO, "levantado_em": instante_utc(), "municipios": len(municipios),
             "camaras": dict(sorted(camaras.items()))}
    Path(estado).mkdir(parents=True, exist_ok=True)
    gravar_json(Path(estado) / ARQUIVO, dados, comprimir=True)
    return {"municipios": len(municipios), "com_sapl": sum(1 for c in camaras if len(c) == 7),
            "assembleias": sum(1 for c in camaras if len(c) == 2)}


def ler(estado: Path | str) -> dict[str, list]:
    """As câmaras do último levantamento (vazio se ainda não houve)."""
    caminho = Path(estado) / ARQUIVO
    if not caminho.exists():
        return {}
    dados = ler_json(caminho)
    return dados.get("camaras") or {} if dados.get("versao") == VERSAO_ESTADO else {}
