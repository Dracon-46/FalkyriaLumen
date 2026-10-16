"""Coleta das séries do SGS para o estado da área Economia (``economia-sgs.json.gz``).

Uma requisição por série, com a série inteira (as séries do catálogo são mensais ou anuais; o SGS limita a
dez anos por consulta só as diárias). O estado guarda os valores como a fonte os publicou (texto, com o
ponto decimal), a URL e a hora da coleta de cada série. Uma série que falha na coleta mantém o que o estado
já tinha e registra a falha: o portal mostra o dado anterior com a data em que foi coletado, sem fingir que
é de hoje.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from lumen_ingestao.cliente_http import ClienteHttp
from lumen_ingestao.coleta_http import ErroColeta
from lumen_painel.comum import gravar_json, ler_json

from .catalogo import SERIES, Serie, url_sgs

ARQUIVO_ESTADO = "economia-sgs.json.gz"
VERSAO_ESTADO = 1
FONTE_ID = "bcb_sgs"
_DATA = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")


class SerieIlegivel(ErroColeta):
    """O SGS respondeu, mas não com a lista de observações (página de erro, JSON inesperado)."""


def ler_resposta(conteudo: bytes) -> list[tuple[str, str]]:
    """Observações da resposta do SGS como (``AAAA-MM-DD``, valor em texto), em ordem de data.

    O SGS publica ``[{"data": "01/01/2025", "valor": "0.16"}]``. Valor vazio é ausência e fica fora (não vira
    zero). Resposta que não é essa lista levanta ``SerieIlegivel``.
    """
    try:
        dados = json.loads(conteudo.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as erro:
        raise SerieIlegivel(f"resposta não é JSON: {conteudo[:80]!r}") from erro
    if not isinstance(dados, list):
        raise SerieIlegivel(f"resposta não é uma lista: {str(dados)[:80]}")
    saida = []
    for item in dados:
        m = _DATA.match(str(item.get("data", "")).strip()) if isinstance(item, dict) else None
        valor = str(item.get("valor", "")).strip() if isinstance(item, dict) else ""
        if not m:
            raise SerieIlegivel(f"observação sem data no formato DD/MM/AAAA: {str(item)[:80]}")
        if not valor:
            continue
        float(valor)  # confere que é número; ValueError sobe como erro de coleta logo abaixo
        saida.append((f"{m.group(3)}-{m.group(2)}-{m.group(1)}", valor))
    return sorted(saida)


@dataclass
class ResumoColetaEconomia:
    """O que a coleta fez: séries atualizadas e as que falharam, com o motivo."""

    atualizadas: dict[str, int] = field(default_factory=dict)   # id → observações
    falhas: dict[str, str] = field(default_factory=dict)        # id → motivo

    def para_json(self) -> dict:
        """Resumo para imprimir na linha de comando."""
        return {"atualizadas": self.atualizadas, "falhas": self.falhas}


def ler_estado(estado: Path | str) -> dict:
    """O estado gravado, ou um estado vazio na versão atual."""
    caminho = Path(estado) / ARQUIVO_ESTADO
    if not caminho.exists() or caminho.stat().st_size == 0:
        return {"versao": VERSAO_ESTADO, "series": {}}
    dados = ler_json(caminho)
    if dados.get("versao") != VERSAO_ESTADO:
        raise ValueError(f"{caminho}: versão {dados.get('versao')!r} do estado da economia não suportada")
    return dados


def coletar(cliente: ClienteHttp, estado: Path | str, series: Iterable[Serie] = SERIES, *,
            agora: datetime | None = None) -> ResumoColetaEconomia:
    """Baixa cada série do SGS e grava o estado; a série que falha mantém o que já havia."""
    dados = ler_estado(estado)
    resumo = ResumoColetaEconomia()
    instante = (agora or datetime.now(timezone.utc)).isoformat(timespec="seconds")
    for s in series:
        url = url_sgs(s.codigo)
        anterior = dados["series"].get(str(s.codigo), {})
        try:
            artefato = cliente.obter(url, {"Accept": "application/json"})
            if artefato.status_http != 200:
                raise SerieIlegivel(f"SGS respondeu {artefato.status_http}")
            observacoes = ler_resposta(artefato.conteudo)
            if not observacoes:
                raise SerieIlegivel("série sem nenhuma observação")
        except (ErroColeta, ValueError) as erro:
            resumo.falhas[s.id] = f"{type(erro).__name__}: {erro}"
            dados["series"][str(s.codigo)] = {**anterior, "url": url, "ultima_falha": instante,
                                               "motivo_da_falha": resumo.falhas[s.id]}
            continue
        dados["series"][str(s.codigo)] = {"url": url, "coletado_em": instante, "observacoes": observacoes}
        resumo.atualizadas[s.id] = len(observacoes)
    Path(estado).mkdir(parents=True, exist_ok=True)
    gravar_json(Path(estado) / ARQUIVO_ESTADO, dados, comprimir=True)
    return resumo
