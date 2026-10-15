"""Linha de comando do pipeline local.

Exemplos::

    lumen coletar pncp_contratacoes --de 2026-09-01 --modalidades 8,9
    lumen coletar pncp_contratos --de 2026-09-01 --ate 2026-09-07
    lumen coletar ibge_localidades --de 2026-10-05
    lumen coletar siconfi_extrato --de 2026-10-05 --entes 4319604,3550308 --exercicio 2025
    lumen coletar pncp_itens --de 2026-03-01 --ate 2026-03-31 --objeto "combust|gasolina|diesel" --so-comparaveis
    lumen normalizar                      # bronze inteiro → silver
    lumen bronze verificar                # reconfere o hash de toda a prova
    lumen eleicoes ...                    # aba Eleições (ver lumen_eleicoes)
    lumen mercado ...                     # referência de mercado fora do governo (ver lumen_mercado)
    lumen painel ...                      # painéis de contratações e conformidade (ver lumen_painel)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from lumen_ingestao.bronze import ArmazemBronzeLocal
from lumen_ingestao.coleta_http import ErroColeta

from . import configuracao, etapas

# Atributos que todo LogRecord tem; o que sobra veio em ``extra=`` e vai para a linha do log.
_CAMPOS_PADRAO = set(vars(logging.LogRecord("", 0, "", 0, "", None, None))) | {"message", "asctime"}


class FormatoComCampos(logging.Formatter):
    """Formato do log que acrescenta os campos de ``extra=`` (fonte, url, status, tentativa) à mensagem.

    Sem isso, ``tentativa_com_erro`` aparece no registro da CI sem dizer qual status a fonte respondeu.
    """

    def format(self, record: logging.LogRecord) -> str:
        """A linha padrão seguida de ``campo=valor`` para cada campo extra, em ordem alfabética."""
        linha = super().format(record)
        extras = {k: v for k, v in vars(record).items() if k not in _CAMPOS_PADRAO}
        return linha + "".join(f" {k}={v}" for k, v in sorted(extras.items()))


def _lista_int(texto: str) -> tuple[int, ...]:
    """Converte ``8,9`` em ``(8, 9)``, ignorando itens vazios; usado como ``type`` do argparse."""
    return tuple(int(x) for x in texto.split(",") if x.strip())


def _lista_str(texto: str) -> tuple[str, ...]:
    """Converte ``a, b`` em ``("a", "b")``, sem espaços nas pontas e ignorando itens vazios."""
    return tuple(x.strip() for x in texto.split(",") if x.strip())


def main(argv: list[str] | None = None) -> int:
    """Ponto de entrada do comando ``lumen``: interpreta os argumentos e despacha para a etapa pedida.

    Os subcomandos ``eleicoes``, ``mercado`` e ``painel`` são repassados inteiros aos CLIs de
    ``lumen_eleicoes``, ``lumen_mercado`` e ``lumen_painel``; ``coletar pncp_itens`` busca os itens dos
    processos da silver publicados na janela (e cujo objeto casa com ``--objeto``, quando dado). Os demais
    leem a configuração e imprimem o resumo em JSON. O código de saída é 2 para configuração ou argumento ausente e
    1 quando a coleta tem falhas ou o bronze tem conteúdo corrompido, para que scripts e a CI percebam.
    """
    parser = argparse.ArgumentParser(prog="lumen", description="Pipeline local do Lumen")
    parser.add_argument("--config", help="caminho do lumen.toml")
    parser.add_argument("-v", "--verboso", action="store_true")
    sub = parser.add_subparsers(dest="comando", required=True)

    p = sub.add_parser("coletar", help="coleta uma fonte para o bronze")
    p.add_argument("fonte", choices=sorted([*etapas.FABRICAS, "pncp_itens"]))
    p.add_argument("--de", required=True, help="AAAA-MM-DD")
    p.add_argument("--ate", help="AAAA-MM-DD (padrão: igual a --de)")
    p.add_argument("--modalidades", type=_lista_int, help="só PNCP contratações: códigos separados por vírgula")
    p.add_argument("--entes", type=_lista_str, help="só SICONFI extrato: códigos IBGE")
    p.add_argument("--exercicio", type=int, help="só SICONFI extrato")
    p.add_argument("--objeto", help="só PNCP itens: expressão procurada no objeto dos processos da silver")
    p.add_argument("--sem-resultados", action="store_true", help="só PNCP itens: não busca os resultados")
    p.add_argument("--so-comparaveis", action="store_true",
                   help="só PNCP itens: resultados só dos itens que a regra A-05 compara com o mercado")

    p = sub.add_parser("normalizar", help="bronze → silver (idempotente)")
    p.add_argument("--fontes", type=_lista_str)

    p = sub.add_parser("bronze", help="operações sobre a prova")
    p.add_argument("acao", choices=["verificar", "listar"])

    sub.add_parser("eleicoes", help="aba Eleições (repassa para lumen_eleicoes)", add_help=False)
    sub.add_parser("mercado", help="referência de mercado (repassa para lumen_mercado)", add_help=False)
    sub.add_parser("painel", help="painéis de contratações e conformidade (repassa para lumen_painel)",
                   add_help=False)

    args, resto = parser.parse_known_args(argv)
    saida_log = logging.StreamHandler()
    saida_log.setFormatter(FormatoComCampos("%(asctime)s %(name)s %(message)s"))
    logging.basicConfig(level=logging.INFO if args.verboso else logging.WARNING, handlers=[saida_log])

    if args.comando == "eleicoes":
        from lumen_eleicoes.cli import main as main_eleicoes
        return main_eleicoes(resto)
    if args.comando == "mercado":
        from lumen_mercado.cli import main as main_mercado
        return main_mercado(["--config", args.config, *resto] if args.config else resto)
    if args.comando == "painel":
        from lumen_painel.cli import main as main_painel
        return main_painel(["--config", args.config, *resto] if args.config else resto)
    if resto:
        parser.error(f"argumentos não reconhecidos: {' '.join(resto)}")

    try:
        cfg = configuracao.carregar(Path(args.config) if args.config else None)
    except configuracao.ConfiguracaoAusente as erro:
        print(f"erro: {erro}", file=sys.stderr)
        return 2

    if args.comando == "coletar" and args.fonte == "pncp_itens":
        janela = etapas.janela_de(args.de, args.ate)
        processos = etapas.processos_da_silver(cfg, de=janela.inicio, ate=janela.fim, objeto=args.objeto)
        filtro = None
        if args.so_comparaveis:
            from lumen_mercado.especificacao import reconhecer

            def filtro(item: dict) -> bool:
                """O item é um dos que a regra A-05 sabe comparar?"""
                return reconhecer(item.get("descricao"), item.get("unidadeMedida")) is not None
        resumo = etapas.coletar_itens(cfg, processos, com_resultados=not args.sem_resultados, filtro_resultados=filtro)
        print(json.dumps({"fonte": "pncp_itens", "processos": len(processos), "listados": resumo.listados,
                          "guardados": len(resumo.guardados), "conteudos_novos": resumo.conteudos_novos,
                          "respostas_de_erro": resumo.respostas_de_erro, "falhas": resumo.falhas},
                         ensure_ascii=False, indent=2))
        return 1 if resumo.falhas else 0

    if args.comando == "coletar":
        opcoes: dict = {}
        if args.modalidades:
            opcoes["modalidades"] = args.modalidades
        if args.fonte == "siconfi_extrato":
            if not args.entes or not args.exercicio:
                print("erro: siconfi_extrato exige --entes e --exercicio", file=sys.stderr)
                return 2
            opcoes.update(entes=args.entes, exercicio=args.exercicio)
        try:
            resumo = etapas.coletar(cfg, args.fonte, etapas.janela_de(args.de, args.ate), **opcoes)
        except ErroColeta as erro:
            # FonteSuspensa é um ErroColeta: a fonte falhou seguidas vezes e a coleta parou. O que já foi
            # guardado continua no bronze; o detalhe de cada tentativa sai no log com -v.
            print(json.dumps({"fonte": args.fonte, "interrompida": f"{type(erro).__name__}: {erro}"},
                             ensure_ascii=False, indent=2))
            return 1
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
