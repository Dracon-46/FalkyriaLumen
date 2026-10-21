"""Linha de comando das regras de detecção.

    lumen deteccao j01 --estado DIR [--silver DIR] [--saida ARQ] [--resumo ARQ] [--privado]

``j01`` cruza os contratos do painel (``contratacoes-AAAA-MM-DD.json.gz`` em ``--estado``) com as sanções da
silver (``lumen coletar cgu_ceis`` e ``cgu_cnep``, depois ``lumen normalizar``). Imprime só as contagens.
O relatório completo, com as coincidências, vai para ``--saida``: no fluxo ``deteccao-sancoes``, o
``deteccao-j01.json.gz`` do estado dos painéis, de onde saem os avisos do portal (ADR-047). Com ``--privado``,
vai também para o bucket privado da publicação (``deteccao/j01/ultimo.json.gz``, trocado a cada execução).
``--resumo`` acrescenta o resumo, só com contagens, a um arquivo Markdown (o resumo da execução no GitHub).
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path

from . import j01

CHAVE_PRIVADA = "deteccao/j01/ultimo.json.gz"


def _silver(args) -> Path:
    """A silver pedida, ou a da configuração do Lumen (``LUMEN_DADOS``/``lumen.toml``)."""
    if args.silver:
        return Path(args.silver)
    from lumen_orquestracao import configuracao
    return configuracao.carregar(Path(args.config) if args.config else None).silver


def _enviar_ao_privado(corpo: bytes, chave: str, config: str | None) -> str:
    """Grava o relatório no bucket privado da publicação e devolve a chave usada."""
    from lumen_eleicoes.configuracao import carregar_publicacao
    from lumen_ingestao.s3 import ClienteS3
    pub = carregar_publicacao(Path(config) if config else None)
    cliente = ClienteS3(endpoint=pub.endpoint, bucket=pub.bucket_estado, chave_acesso=pub.chave_acesso,
                        chave_secreta=pub.chave_secreta, regiao=pub.regiao, estilo_caminho=True)
    cliente.gravar(chave, corpo, sem_sobrescrever=False, tipo="application/json", codificacao="gzip")
    return f"{pub.bucket_estado}/{chave}"


def cmd_j01(args) -> int:
    """Cruza contratos e sanções, imprime as contagens e grava o relatório onde foi pedido."""
    from lumen_normalizacao.silver import consolidar, ler_entidade
    sancoes = consolidar(ler_entidade(_silver(args), "sancao"))
    if not sancoes:
        print("erro: a silver não tem sanções; rode `lumen coletar cgu_ceis`, `cgu_cnep` e `lumen normalizar`",
              file=sys.stderr)
        return 2
    relatorio = j01.cruzar(j01.ler_dias(args.estado), sancoes, j01.Municipios.do_cadastro())
    if not relatorio.dias:
        print(f"erro: {args.estado} não tem arquivos contratacoes-*.json.gz", file=sys.stderr)
        return 2
    completo = relatorio.para_json()
    corpo = gzip.compress(json.dumps(completo, ensure_ascii=False).encode("utf-8"), mtime=0)
    destinos = []
    if args.saida:
        Path(args.saida).parent.mkdir(parents=True, exist_ok=True)
        Path(args.saida).write_bytes(corpo)
        destinos.append(str(args.saida))
    if args.privado:
        destinos.append(_enviar_ao_privado(corpo, CHAVE_PRIVADA, args.config))
    if args.resumo:
        with open(args.resumo, "a", encoding="utf-8") as fh:
            fh.write(relatorio.resumo_markdown())
    contagens = {k: v for k, v in completo.items() if k != "coincidencias"}
    contagens["coincidencias"] = len(completo["coincidencias"])
    contagens["relatorio"] = destinos
    print(json.dumps(contagens, ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    """Ponto de entrada de ``lumen deteccao`` e de ``python -m lumen_deteccao``."""
    parser = argparse.ArgumentParser(prog="lumen deteccao", description="Regras de detecção")
    parser.add_argument("--config", help="caminho do lumen.toml")
    sub = parser.add_subparsers(dest="comando", required=True)
    p = sub.add_parser("j01", help="contratos com fornecedor que constava num cadastro de sanções da CGU")
    p.add_argument("--estado", required=True, help="diretório com os contratacoes-AAAA-MM-DD.json.gz do painel")
    p.add_argument("--silver", help="silver com as sanções (padrão: a da configuração)")
    p.add_argument("--saida", help="arquivo local do relatório completo (.json.gz)")
    p.add_argument("--resumo", help="arquivo Markdown onde acrescentar o resumo só com contagens")
    p.add_argument("--privado", action="store_true", help="grava o relatório completo no bucket privado")
    args = parser.parse_args(argv)
    return cmd_j01(args)
