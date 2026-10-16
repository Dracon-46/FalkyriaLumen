"""Linha de comando da área Economia e Contas Públicas.

    lumen economia coletar --estado DIR [--series ipca,selic_mes]
    lumen economia publicar --estado DIR --saida SITE

``coletar`` baixa as séries do SGS do Banco Central para ``DIR/economia-sgs.json.gz`` (o estado guardado
com o dos painéis). ``publicar`` monta ``SITE/economia/indicadores.json``, que o portal lê. O código de
saída de ``coletar`` é 1 quando alguma série falhou; as outras são gravadas mesmo assim.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import coleta, indicadores
from .catalogo import SERIES, series_por_id


def _cliente(args):
    """Cliente HTTP do SGS com o contato da configuração do Lumen no User-Agent."""
    from lumen_orquestracao import configuracao, etapas
    cfg = configuracao.carregar(Path(args.config) if args.config else None)
    return etapas.cliente(cfg, coleta.FONTE_ID)


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


def cmd_publicar(args) -> int:
    """Monta o arquivo dos indicadores a partir do estado."""
    print(json.dumps(indicadores.publicar(args.estado, args.saida), ensure_ascii=False, indent=2))
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
    p = sub.add_parser("publicar", help="monta economia/indicadores.json a partir do estado")
    p.add_argument("--estado", required=True, type=Path)
    p.add_argument("--saida", required=True, type=Path)
    args = parser.parse_args(argv)
    return cmd_coletar(args) if args.comando == "coletar" else cmd_publicar(args)
