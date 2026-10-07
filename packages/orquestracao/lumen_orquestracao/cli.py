"""Linha de comando do pipeline local.

Exemplos::

    lumen coletar pncp_contratacoes --de 2026-09-01 --modalidades 8,9
    lumen coletar pncp_contratos --de 2026-09-01 --ate 2026-09-07
    lumen coletar ibge_localidades --de 2026-10-05
    lumen coletar siconfi_extrato --de 2026-10-05 --entes 4319604,3550308 --exercicio 2025
    lumen normalizar                      # bronze inteiro → silver
    lumen bronze verificar                # reconfere o hash de toda a prova
    lumen eleicoes ...                    # aba Eleições (ver lumen_eleicoes)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from lumen_ingestao.bronze import ArmazemBronzeLocal

from . import configuracao, etapas


def _lista_int(texto: str) -> tuple[int, ...]:
    """Converte ``8,9`` em ``(8, 9)``, ignorando itens vazios; usado como ``type`` do argparse."""
    return tuple(int(x) for x in texto.split(",") if x.strip())


def _lista_str(texto: str) -> tuple[str, ...]:
    """Converte ``a, b`` em ``("a", "b")``, sem espaços nas pontas e ignorando itens vazios."""
    return tuple(x.strip() for x in texto.split(",") if x.strip())


def main(argv: list[str] | None = None) -> int:
    """Ponto de entrada do comando ``lumen``: interpreta os argumentos e despacha para a etapa pedida.

    O subcomando ``eleicoes`` é repassado inteiro ao CLI de ``lumen_eleicoes``; os demais leem a
    configuração e imprimem o resumo em JSON. O código de saída é 2 para configuração ou argumento ausente e
    1 quando a coleta tem falhas ou o bronze tem conteúdo corrompido, para que scripts e a CI percebam.
    """
    parser = argparse.ArgumentParser(prog="lumen", description="Pipeline local do Lumen")
    parser.add_argument("--config", help="caminho do lumen.toml")
    parser.add_argument("-v", "--verboso", action="store_true")
    sub = parser.add_subparsers(dest="comando", required=True)

    p = sub.add_parser("coletar", help="coleta uma fonte para o bronze")
    p.add_argument("fonte", choices=sorted(etapas.FABRICAS))
    p.add_argument("--de", required=True, help="AAAA-MM-DD")
    p.add_argument("--ate", help="AAAA-MM-DD (padrão: igual a --de)")
    p.add_argument("--modalidades", type=_lista_int, help="só PNCP contratações: códigos separados por vírgula")
    p.add_argument("--entes", type=_lista_str, help="só SICONFI extrato: códigos IBGE")
    p.add_argument("--exercicio", type=int, help="só SICONFI extrato")

    p = sub.add_parser("normalizar", help="bronze → silver (idempotente)")
    p.add_argument("--fontes", type=_lista_str)

    p = sub.add_parser("bronze", help="operações sobre a prova")
    p.add_argument("acao", choices=["verificar", "listar"])

    sub.add_parser("eleicoes", help="aba Eleições (repassa para lumen_eleicoes)", add_help=False)

    args, resto = parser.parse_known_args(argv)
    logging.basicConfig(level=logging.INFO if args.verboso else logging.WARNING,
                        format="%(asctime)s %(name)s %(message)s")

    if args.comando == "eleicoes":
        from lumen_eleicoes.cli import main as main_eleicoes
        return main_eleicoes(resto)
    if resto:
        parser.error(f"argumentos não reconhecidos: {' '.join(resto)}")

    try:
        cfg = configuracao.carregar(Path(args.config) if args.config else None)
    except configuracao.ConfiguracaoAusente as erro:
        print(f"erro: {erro}", file=sys.stderr)
        return 2

    if args.comando == "coletar":
        opcoes: dict = {}
        if args.modalidades:
            opcoes["modalidades"] = args.modalidades
        if args.fonte == "siconfi_extrato":
            if not args.entes or not args.exercicio:
                print("erro: siconfi_extrato exige --entes e --exercicio", file=sys.stderr)
                return 2
            opcoes.update(entes=args.entes, exercicio=args.exercicio)
        resumo = etapas.coletar(cfg, args.fonte, etapas.janela_de(args.de, args.ate), **opcoes)
        print(json.dumps({"fonte": args.fonte, "listados": resumo.listados,
                          "guardados": len(resumo.guardados), "conteudos_novos": resumo.conteudos_novos,
                          "respostas_de_erro": resumo.respostas_de_erro, "falhas": resumo.falhas},
                         ensure_ascii=False, indent=2))
        return 1 if resumo.falhas else 0

    if args.comando == "normalizar":
        r = etapas.normalizar(cfg, args.fontes)
        print(json.dumps(r.__dict__, ensure_ascii=False, indent=2))
        return 0

    if args.comando == "bronze":
        armazem = ArmazemBronzeLocal(cfg.bronze)
        if args.acao == "verificar":
            corrompidos = armazem.verificar_integridade()
            pendentes = armazem.verificar_consistencia()
            print(json.dumps({"corrompidos": corrompidos, "versoes_sem_registro": pendentes}, indent=2))
            return 1 if corrompidos else 0
        for r in armazem.listar_registros():
            print(f"{r.coletado_em}  {r.fonte_id:<32} {r.status_http}  v{r.versao}  {r.url_solicitada}")
        return 0
    return 0  # pragma: no cover


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
