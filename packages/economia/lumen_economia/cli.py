"""Linha de comando da área Economia e Contas Públicas.

    lumen economia coletar --estado DIR [--series ipca,selic_mes]
    lumen economia estatais --estado DIR [--anos 2021-2025]
    lumen economia publicar --estado DIR --saida SITE

``coletar`` baixa as séries do SGS do Banco Central para ``DIR/economia-sgs.json.gz`` (o estado guardado
com o dos painéis). ``estatais`` lê o cadastro, o controle (FRE) e as demonstrações (DFP) das estatais com
ações na bolsa nos dados abertos da CVM para ``DIR/economia-cvm.json.gz`` (ADR-034). ``publicar`` monta
``SITE/economia/indicadores.json`` e, se houver o estado das estatais, ``SITE/economia/estatais.json``. As
estatais federais de capital fechado vêm dos dados abertos da SEST, no mesmo comando (``economia-sest.json.gz``). O
código de saída de ``coletar`` e de ``estatais`` é 1 quando algo falhou; o resto é gravado mesmo assim.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import coleta, estatais, indicadores, sest
from .catalogo import SERIES, series_por_id


def _cliente(args, fonte: str = coleta.FONTE_ID):
    """Cliente HTTP da fonte com o contato da configuração do Lumen no User-Agent."""
    from lumen_orquestracao import configuracao, etapas
    cfg = configuracao.carregar(Path(args.config) if args.config else None)
    return etapas.cliente(cfg, fonte)


def _anos(texto: str) -> list[int]:
    """``2021-2025`` ou ``2023,2025`` → lista de anos."""
    if "-" in texto:
        de, ate = (int(x) for x in texto.split("-", 1))
        return list(range(de, ate + 1))
    return [int(x) for x in texto.split(",") if x.strip()]


def cmd_coletar(args) -> int:
    """Baixa as séries pedidas (ou todas) e imprime o resumo."""
    pedidas = SERIES
    if args.series:
        por_id = series_por_id()
        desconhecidas = [i for i in args.series if i not in por_id]
        if desconhecidas:
            print(f"erro: séries desconhecidas: {desconhecidas}. Conhecidas: {sorted(por_id)}", file=sys.stderr)
            return 2
        pedidas = tuple(por_id[i] for i in args.series)
    resumo = coleta.coletar(_cliente(args), args.estado, pedidas)
    print(json.dumps(resumo.para_json(), ensure_ascii=False, indent=2))
    return 1 if resumo.falhas else 0


def cmd_estatais(args) -> int:
    """Lê cadastro, FRE e DFP da CVM para o estado das estatais e imprime o resumo."""
    resumo = estatais.coletar(_cliente(args, estatais.FONTE_ID), args.estado, args.anos,
                              baixar=estatais.baixar_membro)
    federais = sest.coletar(_cliente(args, sest.FONTE_ID), args.estado)
    print(json.dumps({"cvm": resumo.para_json(), "sest": federais.para_json()}, ensure_ascii=False, indent=2))
    return 1 if resumo.falhas or federais.falhas else 0


def cmd_publicar(args) -> int:
    """Monta o arquivo dos indicadores e, se houver o estado das estatais, o das estatais."""
    saida = {"indicadores": indicadores.publicar(args.estado, args.saida)}
    if any((Path(args.estado) / a).exists() for a in (estatais.ARQUIVO_ESTADO, sest.ARQUIVO_ESTADO)):
        saida["estatais"] = estatais.publicar(args.estado, args.saida)
    print(json.dumps(saida, ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    """Ponto de entrada de ``lumen economia`` e de ``python -m lumen_economia``."""
    parser = argparse.ArgumentParser(prog="lumen economia", description="Economia e Contas Públicas")
    parser.add_argument("--config", help="caminho do lumen.toml")
    sub = parser.add_subparsers(dest="comando", required=True)
    p = sub.add_parser("coletar", help="baixa as séries do SGS do Banco Central para o estado")
    p.add_argument("--estado", required=True, type=Path)
    p.add_argument("--series", type=lambda t: [x.strip() for x in t.split(",") if x.strip()],
                   help="identificadores do catálogo, separados por vírgula (padrão: todas)")
    p = sub.add_parser("estatais", help="lê as estatais com ações na bolsa nos dados abertos da CVM")
    p.add_argument("--estado", required=True, type=Path)
    p.add_argument("--anos", type=_anos, help="exercícios das DFP, como 2021-2025 (padrão: os cinco últimos)")
    p = sub.add_parser("publicar", help="monta economia/indicadores.json (e estatais.json) a partir do estado")
    p.add_argument("--estado", required=True, type=Path)
    p.add_argument("--saida", required=True, type=Path)
    args = parser.parse_args(argv)
    return {"coletar": cmd_coletar, "estatais": cmd_estatais, "publicar": cmd_publicar}[args.comando](args)
