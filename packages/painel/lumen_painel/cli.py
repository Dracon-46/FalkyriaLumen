"""``lumen painel``: coleta e publicação dos painéis de contratações e de conformidade (ADR-028).

Exemplos::

    lumen painel cadastro --estado estado/                          # cadastro de entes do SICONFI
    lumen painel contratacoes --estado estado/ --ultimos 3          # dias que faltam entre os 3 últimos
    lumen painel contratacoes --estado estado/ --de 2026-01-01 --ate 2026-01-31 --limite-minutos 300
    lumen painel faltando --estado estado/ --de 2026-01-01 --partes 6   # divisão para execuções paralelas
    lumen painel conformidade --estado estado/ --ufs SP,MG --exercicios 2025,2026
    lumen painel rcl --estado estado/ --ufs SP,MG                  # RCL do exercício anterior, para os pares
    lumen painel despesa-funcao --estado estado/ --ufs SP,MG --limite-minutos 30   # DCA por função, pares
    lumen painel pessoal --estado estado/ --ufs SP,MG --limite-minutos 20          # RGF: pessoal em % da RCL
    lumen painel cnpj --estado estado/                              # base de CNPJ da Receita, dos fornecedores
    lumen painel emendas --estado estado/                           # emendas parlamentares (CGU), por ente
    lumen painel convenios --estado estado/                         # convênios da União (CGU), por ente
    lumen painel transparencia --estado estado/                     # portais de transparência (PNTP)
    lumen painel anp --estado estado/                               # preço de revenda da ANP por semana
    lumen painel publicar --estado estado/ --saida site/            # o site inteiro, a partir do estado

O estado é um diretório com ``cadastro-entes.json.gz``, um ``contratacoes-<dia>.json.gz`` por dia coletado e
um ``conformidade-<UF>.json.gz`` por UF. No GitHub Actions, ele fica nos anexos de uma versão do repositório
(``painel-estado``) entre uma execução e outra.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from . import cnpj as base_cnpj
from . import conformidade as conf
from . import contratacoes as contr
from . import convenios, despesa_funcao, emendas, mercado, operacao, pares, pessoal, rcl, transparencia
from .cadastro import Cadastro
from .comum import gravar_json, hoje_brasilia, instante_utc, ler_json, uf_do_ente
from .dia import coletar_dia, dias_guardados, mascarar_dia
from .site import Site

ARQUIVO_CADASTRO = "cadastro-entes.json.gz"
# Execuções dos fluxos de dados, gravadas pelo paineis-site com gh run list (painel operacional, ADR-039)
ARQUIVO_EXECUCOES = "execucoes.json"
# O PNCP começou a receber publicações em agosto de 2021 (as primeiras dispensas, de 1º a 10/8/2021)
INICIO_PADRAO = date(2021, 8, 1)
relogio = time.monotonic          # o prazo de --limite-minutos (substituível nos testes)


def _data(texto: str) -> date:
    """``AAAA-MM-DD`` → ``date``, como ``type`` do argparse."""
    return date.fromisoformat(texto)


def _lista(texto: str) -> list[str]:
    """``SP, mg`` → ``["SP", "MG"]``."""
    return [x.strip().upper() for x in texto.split(",") if x.strip()]


def _imprimir(dados) -> None:
    """JSON legível na saída padrão."""
    print(json.dumps(dados, ensure_ascii=False, indent=2))


def _configuracao(args):
    """A configuração do pipeline (contato da coleta e limites de requisições)."""
    from lumen_orquestracao import configuracao
    return configuracao.carregar(Path(args.config) if args.config else None)


def dias_pedidos(estado: Path, *, de: date | None, ate: date | None, ultimos: int | None, hoje: date,
                 refazer: bool = False) -> list[date]:
    """Os dias a coletar, do mais recente para o mais antigo, sem os que já estão no estado.

    Sem ``de``, o intervalo é dos ``ultimos`` dias (padrão 3) até ontem; o dia corrente nunca entra, porque
    ainda está recebendo publicações.
    """
    fim = min(ate or hoje - timedelta(days=1), hoje - timedelta(days=1))
    inicio = de or fim - timedelta(days=(ultimos or 3) - 1)
    guardados = set() if refazer else dias_guardados(estado)
    return [fim - timedelta(n) for n in range((fim - inicio).days + 1) if fim - timedelta(n) not in guardados]


def partes(dias: list[date], n: int) -> list[dict]:
    """Divide os dias (já do mais recente ao mais antigo) em até ``n`` blocos de dias seguidos, para execuções
    paralelas; cada bloco vira ``{"de": …, "ate": …, "dias": …}``."""
    if not dias or n < 1:
        return []
    tamanho = -(-len(dias) // n)
    blocos = [dias[i:i + tamanho] for i in range(0, len(dias), tamanho)]
    return [{"de": min(b).isoformat(), "ate": max(b).isoformat(), "dias": len(b)} for b in blocos]


# ------------------------------------------------------------------------------------------- comandos

def cmd_cadastro(args) -> int:
    """Coleta o cadastro de entes do SICONFI (uma requisição), normaliza e grava ``cadastro-entes.json.gz``."""
    import shutil
    import tempfile
    from dataclasses import replace

    from lumen_ingestao.portas import Janela
    from lumen_orquestracao import etapas

    cfg = _configuracao(args)
    raiz = Path(tempfile.mkdtemp(prefix="painel-cadastro-"))
    try:
        cfg_c = replace(cfg, raiz_dados=raiz)
        hoje = hoje_brasilia()
        r = etapas.coletar(cfg_c, "siconfi_entes", Janela(hoje, hoje))
        if r.falhas or r.respostas_de_erro:
            print(f"erro: cadastro do SICONFI com {len(r.falhas)} falha(s) e {r.respostas_de_erro} resposta(s) "
                  "de erro; o cadastro anterior continua valendo", file=sys.stderr)
            return 1
        etapas.normalizar(cfg_c, ["siconfi_entes"])
        cadastro = Cadastro.da_silver(cfg_c.silver)
    finally:
        shutil.rmtree(raiz, ignore_errors=True)
    if len(cadastro) < 1000:
        print(f"erro: o cadastro veio com só {len(cadastro)} ente(s); o anterior continua valendo", file=sys.stderr)
        return 1
    gravar_json(Path(args.estado) / ARQUIVO_CADASTRO, cadastro.para_json(), comprimir=True)
    _imprimir({"entes": len(cadastro), "arquivo": str(Path(args.estado) / ARQUIVO_CADASTRO)})
    return 0


def cmd_contratacoes(args) -> int:
    """Coleta os dias pedidos que faltam no estado, do mais recente ao mais antigo, até o prazo."""
    cfg = _configuracao(args)
    estado = Path(args.estado)
    estado.mkdir(parents=True, exist_ok=True)
    dias = dias_pedidos(estado, de=args.de, ate=args.ate, ultimos=args.ultimos, hoje=hoje_brasilia(),
                        refazer=args.refazer)
    fim = relogio() + args.limite_minutos * 60 if args.limite_minutos else None
    resultados, pendentes = [], []
    for dia in dias:
        if fim is not None and relogio() >= fim:
            pendentes.append(dia.isoformat())
            continue
        r = coletar_dia(cfg, dia, estado)
        resultados.append(r.para_json())
        print(f"{dia}: {'gravado' if r.gravado else 'não gravado'} — {r.processos} processo(s), "
              f"{r.contratos} contrato(s), {r.paginas} página(s)" + (f"; {'; '.join(r.problemas)}" if r.problemas
                                                                       else ""), file=sys.stderr, flush=True)
    _imprimir({"pedidos": len(dias), "gravados": sum(1 for r in resultados if r["gravado"]),
               "nao_gravados": [r["dia"] for r in resultados if not r["gravado"]], "pendentes_no_prazo": pendentes,
               "dias": resultados})
    return 1 if any(not r["gravado"] for r in resultados) else 0


def cmd_faltando(args) -> int:
    """Imprime, em JSON, os blocos de dias que faltam no estado (matriz das execuções paralelas)."""
    dias = dias_pedidos(Path(args.estado), de=args.de, ate=args.ate, ultimos=None, hoje=hoje_brasilia())
    print(json.dumps(partes(dias, args.partes)))
    return 0


def cmd_conformidade(args) -> int:
    """Coleta o extrato de entregas de cada UF pedida e grava o estado de cada uma."""
    cfg = _configuracao(args)
    cadastro = Cadastro.ler(Path(args.estado) / ARQUIVO_CADASTRO)
    exercicios = [int(x) for x in _lista(args.exercicios)] if args.exercicios else None
    resultados = []
    for uf in _lista(args.ufs):
        r = conf.coletar_uf(cfg, uf, cadastro, exercicios, Path(args.estado), maximo_anteriores=args.maximo_anteriores)
        resultados.append(r.para_json())
        print(f"{uf}: {r.consultas_ok} de {r.consultas} consulta(s) completas"
              + (f"; {'; '.join(r.problemas)}" if r.problemas else ""), file=sys.stderr, flush=True)
    _imprimir({"ufs": resultados})
    return 1 if any(not r["gravado"] for r in resultados) else 0


def cmd_rcl(args) -> int:
    """Coleta a RCL dos entes pendentes de cada UF pedida (RREO, Anexo 03) e grava o estado de cada uma.

    Ente que ainda não publicou não é falha: fica para a próxima tentativa. O código é 1 só quando uma coleta
    foi interrompida.
    """
    cfg = _configuracao(args)
    cadastro = Cadastro.ler(Path(args.estado) / ARQUIVO_CADASTRO)
    exercicio = args.exercicio or rcl.exercicio_padrao(hoje_brasilia())
    resultados = []
    for uf in _lista(args.ufs):
        r = rcl.coletar_uf(cfg, uf, cadastro, Path(args.estado), exercicio)
        resultados.append(r.para_json())
        print(f"{uf}: {r.encontradas} RCL de {r.pendentes} pendente(s), {r.consultas} consulta(s)"
              + (f"; {'; '.join(r.problemas)}" if r.problemas else ""), file=sys.stderr, flush=True)
    _imprimir({"exercicio": exercicio, "ufs": resultados})
    return 1 if any(r["problemas"] for r in resultados) else 0


def cmd_despesa_funcao(args) -> int:
    """Coleta a despesa por função (DCA, Anexo I-E) dos entes pendentes de cada UF pedida e grava o estado.

    O ``--limite-minutos`` vale para todas as UFs juntas: passado o tempo, os entes que faltam ficam para a
    execução seguinte. O código é 1 só quando uma coleta foi interrompida.
    """
    cfg = _configuracao(args)
    cadastro = Cadastro.ler(Path(args.estado) / ARQUIVO_CADASTRO)
    exercicio = args.exercicio or despesa_funcao.exercicio_padrao(hoje_brasilia())
    inicio, resultados = relogio(), []
    for uf in _lista(args.ufs):
        restante = None if args.limite_minutos is None else max(0.0, args.limite_minutos - (relogio() - inicio) / 60)
        r = despesa_funcao.coletar_uf(cfg, uf, cadastro, Path(args.estado), exercicio, limite_minutos=restante,
                                      relogio=relogio)
        resultados.append(r.para_json())
        print(f"{uf}: {r.encontradas} DCA de {r.pendentes} pendente(s), {r.consultas} consulta(s)"
              + (f", {r.para_depois} para a próxima execução" if r.para_depois else "")
              + (f"; {'; '.join(r.problemas)}" if r.problemas else ""), file=sys.stderr, flush=True)
    _imprimir({"exercicio": exercicio, "ufs": resultados})
    return 1 if any(r["problemas"] for r in resultados) else 0


def cmd_pessoal(args) -> int:
    """Coleta a despesa com pessoal do Executivo (RGF, Anexo 1) dos entes pendentes de cada UF pedida.

    Como em ``despesa-funcao``, o ``--limite-minutos`` vale para todas as UFs juntas. O código é 1 só quando uma
    coleta foi interrompida.
    """
    cfg = _configuracao(args)
    cadastro = Cadastro.ler(Path(args.estado) / ARQUIVO_CADASTRO)
    exercicio = args.exercicio or pessoal.exercicio_padrao(hoje_brasilia())
    inicio, resultados = relogio(), []
    for uf in _lista(args.ufs):
        restante = None if args.limite_minutos is None else max(0.0, args.limite_minutos - (relogio() - inicio) / 60)
        r = pessoal.coletar_uf(cfg, uf, cadastro, Path(args.estado), exercicio, limite_minutos=restante,
                               relogio=relogio)
        resultados.append(r.para_json())
        print(f"{uf}: {r.encontradas} RGF de {r.pendentes} pendente(s), {r.consultas} consulta(s)"
              + (f", {r.para_depois} para a próxima execução" if r.para_depois else "")
              + (f"; {'; '.join(r.problemas)}" if r.problemas else ""), file=sys.stderr, flush=True)
    _imprimir({"exercicio": exercicio, "ufs": resultados})
    return 1 if any(r["problemas"] for r in resultados) else 0


def cmd_cnpj(args) -> int:
    """Lê a base pública de CNPJ da Receita para os fornecedores do estado e grava ``cnpj-fornecedores.json.gz``.

    Pula quando o estado já tem a base do mês para todos os fornecedores (ADR-043).
    """
    cfg = _configuracao(args)
    r = base_cnpj.coletar(Path(args.estado), contato=cfg.contato, mes=args.mes)
    _imprimir(r.para_json())
    return 0


def cmd_emendas(args) -> int:
    """Lê o arquivo de emendas parlamentares da CGU quando ele muda e grava ``emendas.json.gz`` (ADR-044)."""
    cfg = _configuracao(args)
    cadastro = Cadastro.ler(Path(args.estado) / ARQUIVO_CADASTRO)
    _imprimir(emendas.coletar(Path(args.estado), cadastro, contato=cfg.contato).para_json())
    return 0


def cmd_convenios(args) -> int:
    """Lê o arquivo de convênios da CGU quando sai um novo e grava ``convenios.json.gz`` (ADR-045)."""
    cfg = _configuracao(args)
    cadastro = Cadastro.ler(Path(args.estado) / ARQUIVO_CADASTRO)
    _imprimir(convenios.coletar(Path(args.estado), cadastro, contato=cfg.contato).para_json())
    return 0


def cmd_mascarar(args) -> int:
    """Reescreve os arquivos do dia gravados antes da máscara de CPF (ADR-043) e lista os que mudaram."""
    alterados = []
    for caminho in sorted(Path(args.estado).glob("contratacoes-*.json.gz")):
        if caminho.stat().st_size == 0:
            continue
        dados = ler_json(caminho)
        if mascarar_dia(dados):
            gravar_json(caminho, dados, comprimir=True)
            alterados.append(caminho.name)
    _imprimir({"alterados": alterados})
    return 0


def cmd_transparencia(args) -> int:
    """Lê o ciclo mais recente do PNTP para ``transparencia-pntp.json.gz``; o código é 1 quando falhou."""
    from lumen_orquestracao import etapas
    resumo = transparencia.coletar(etapas.cliente(_configuracao(args), transparencia.FONTE_ID), args.estado)
    _imprimir(resumo.para_json())
    return 1 if resumo.falha else 0


def cmd_anp(args) -> int:
    """Lê as planilhas semanais da ANP que faltam em ``anp-semanas.json.gz``; o código é 1 quando algo falhou."""
    from lumen_orquestracao import etapas
    resumo = mercado.coletar(etapas.cliente(_configuracao(args), mercado.FONTE_ID), args.estado,
                             maximo=args.maximo_semanas)
    _imprimir(resumo.para_json())
    return 1 if resumo.falha or resumo.falhas else 0


def cmd_publicar(args) -> int:
    """Monta o site inteiro a partir do estado: índice, busca, contratações e conformidade."""
    estado = Path(args.estado)
    gerado_em = instante_utc()
    hoje = args.hoje or hoje_brasilia()
    caminho_cadastro = estado / ARQUIVO_CADASTRO
    cadastro = Cadastro.ler(caminho_cadastro) if caminho_cadastro.exists() else Cadastro({})
    site = Site(args.saida)

    painel = contr.somar_dias(estado.glob("contratacoes-*.json.gz"), cadastro)
    corte = contr.corte_mes_a_mes(painel.cobertura()["ate"])
    for codigo, acumulador in painel.entes.items():
        site.gravar(f"contratacoes/ente/{codigo}.json", contr.compactar_meses(
            contr.ente_para_json(codigo, acumulador, painel, cadastro, gerado_em), corte))
    for cnpj, acumulador in painel.por_orgao.items():
        site.gravar(f"contratacoes/orgao/{cnpj}.json", contr.compactar_meses(
            contr.orgao_para_json(cnpj, acumulador, painel, cadastro, gerado_em), corte))
    site.gravar("contratacoes/panorama.json",
                contr.compactar_meses(contr.panorama_para_json(painel, cadastro, gerado_em), corte))
    site.gravar("orgaos.json", contr.orgaos_para_busca(painel, gerado_em))

    avaliacao = conf.avaliar(estado.glob("conformidade-*.json.gz"), cadastro, hoje=hoje, gerado_em=gerado_em)
    exercicio_rcl, rcl_entes = rcl.ler_rcl(estado.glob("rcl-*.json.gz"))
    exercicio_despesa, despesa_entes = despesa_funcao.ler_despesas(estado.glob("despesa-funcao-*.json.gz"))
    exercicio_pessoal, pessoal_entes = pessoal.ler_pessoal(estado.glob("pessoal-*.json.gz"))
    grupos = pares.acrescentar(avaliacao, cadastro, site.gravar, gerado_em=gerado_em, rcl=rcl_entes,
                               exercicio_rcl=exercicio_rcl, despesa=despesa_entes,
                               exercicio_despesa=exercicio_despesa, pessoal=pessoal_entes,
                               exercicio_pessoal=exercicio_pessoal)
    for codigo, arquivo in avaliacao.entes.items():
        site.gravar(f"conformidade/ente/{codigo}.json", arquivo)
    for uf in sorted({a["ente"]["uf"] for a in avaliacao.entes.values() if a["ente"]["uf"]}):
        site.gravar(f"conformidade/uf/{uf}.json", conf.uf_para_json(uf, avaliacao, gerado_em))
    site.gravar("conformidade/panorama.json", conf.panorama_para_json(avaliacao, gerado_em))

    caminho_execucoes = estado / ARQUIVO_EXECUCOES
    situacao = operacao.operacao_para_json(
        execucoes=ler_json(caminho_execucoes) if caminho_execucoes.exists() else None, volume=painel.volume,
        faltando=painel.cobertura()["faltando"],
        coletas=avaliacao.coletas, entes=avaliacao.entes, uf_do_ente=uf_do_ente,
        agora=datetime.fromisoformat(gerado_em.replace("Z", "+00:00")), hoje=hoje, gerado_em=gerado_em)
    site.gravar("operacao.json", situacao)

    pntp = transparencia.publicar(estado, site.gravar, gerado_em=gerado_em)
    precos_anp = mercado.publicar(estado, cadastro, site.gravar, gerado_em=gerado_em)
    receita = base_cnpj.publicar(estado, site.gravar, gerado_em=gerado_em)
    recebido_de_emendas = emendas.publicar(estado, site.gravar, gerado_em=gerado_em)
    convenios_dos_entes = convenios.publicar(estado, site.gravar, gerado_em=gerado_em)

    entes = {c: [c, e.nome, e.uf, e.esfera, e.populacao] for c, e in cadastro.entes.items()}
    for codigo in set(painel.entes) | set(avaliacao.entes):
        entes.setdefault(codigo, [codigo, cadastro.nome(codigo), None, None, None])
    site.gravar("entes.json", {"versao": 1, "gerado_em": gerado_em,
                               "colunas": ["codigo", "nome", "uf", "esfera", "populacao"],
                               "entes": [entes[c] for c in sorted(entes)]})
    indice = {"versao": 1, "gerado_em": gerado_em, "avaliado_em": hoje.isoformat(),
              "cadastro": {"entes": len(cadastro), "gerado_em": cadastro.gerado_em},
              "contratacoes": {**painel.cobertura(), "entes": len(painel.entes), "orgaos": len(painel.por_orgao)},
              "conformidade": {"entes": len(avaliacao.entes), "ufs": avaliacao.coletas, "pares": grupos},
              "transparencia": pntp, "anp": precos_anp, "cnpj": receita, "emendas": recebido_de_emendas, "convenios": convenios_dos_entes, "operacao": {"alertas": len(situacao["alertas"])}}
    site.gravar("indice.json", indice)
    site.finalizar()
    _imprimir({"arquivos": site.arquivos, **{k: v for k, v in indice.items() if k != "versao"},
               "contratacoes": {**indice["contratacoes"], "faltando": len(indice["contratacoes"]["faltando"])}})
    return 0


def construir_parser() -> argparse.ArgumentParser:
    """Os subcomandos e as opções de cada um."""
    p = argparse.ArgumentParser(prog="lumen painel", description="Painéis de contratações e de conformidade")
    p.add_argument("--config", help="caminho do lumen.toml")
    sub = p.add_subparsers(dest="comando", required=True)

    c = sub.add_parser("cadastro", help="cadastro de entes do SICONFI")
    c.add_argument("--estado", required=True, help="diretório do estado dos painéis")

    c = sub.add_parser("contratacoes", help="coleta os dias do PNCP que faltam no estado")
    c.add_argument("--estado", required=True)
    c.add_argument("--de", type=_data, help="primeiro dia (AAAA-MM-DD)")
    c.add_argument("--ate", type=_data, help="último dia (padrão: ontem)")
    c.add_argument("--ultimos", type=int, help="sem --de: quantos dias até ontem (padrão 3)")
    c.add_argument("--limite-minutos", type=float, help="não começa dia novo depois deste tempo")
    c.add_argument("--refazer", action="store_true", help="coleta de novo os dias que já estão no estado")

    c = sub.add_parser("faltando", help="blocos de dias que faltam, em JSON, para execuções paralelas")
    c.add_argument("--estado", required=True)
    c.add_argument("--de", type=_data, default=INICIO_PADRAO)
    c.add_argument("--ate", type=_data)
    c.add_argument("--partes", type=int, default=6)

    c = sub.add_parser("conformidade", help="coleta o extrato de entregas do SICONFI por UF")
    c.add_argument("--estado", required=True)
    c.add_argument("--ufs", required=True, help="siglas separadas por vírgula")
    c.add_argument("--exercicios", help="só estes; padrão: o anterior, o corrente e os encerrados que faltam desde 2021")
    c.add_argument("--maximo-anteriores", type=int, default=conf.MAXIMO_ANTERIORES,
                   help="exercícios encerrados coletados por execução, além do anterior e do corrente")

    c = sub.add_parser("rcl", help="receita corrente líquida dos entes por UF (RREO, Anexo 03), para os pares")
    c.add_argument("--estado", required=True)
    c.add_argument("--ufs", required=True, help="siglas separadas por vírgula")
    c.add_argument("--exercicio", type=int, help="padrão: o anterior")

    c = sub.add_parser("despesa-funcao", help="despesa por função dos entes por UF (DCA, Anexo I-E), para os pares")
    c.add_argument("--estado", required=True)
    c.add_argument("--ufs", required=True, help="siglas separadas por vírgula")
    c.add_argument("--exercicio", type=int, help="padrão: o último com a DCA no prazo (o anterior, a partir de maio)")
    c.add_argument("--limite-minutos", type=float, help="não começa lote novo depois deste tempo (todas as UFs)")

    c = sub.add_parser("pessoal", help="despesa com pessoal do Executivo em %% da RCL por UF (RGF, Anexo 1)")
    c.add_argument("--estado", required=True)
    c.add_argument("--ufs", required=True, help="siglas separadas por vírgula")
    c.add_argument("--exercicio", type=int, help="padrão: o anterior")
    c.add_argument("--limite-minutos", type=float, help="não começa lote novo depois deste tempo (todas as UFs)")

    c = sub.add_parser("cnpj", help="base de CNPJ da Receita (cadastro e sócios) dos fornecedores do estado")
    c.add_argument("--estado", required=True)
    c.add_argument("--mes", help="pasta AAAA-MM da Receita (padrão: a mais recente)")

    c = sub.add_parser("emendas", help="emendas parlamentares da CGU recebidas por município e UF")
    c.add_argument("--estado", required=True)

    c = sub.add_parser("convenios", help="convênios da União com estados, municípios e entidades (CGU), por ente")
    c.add_argument("--estado", required=True)

    c = sub.add_parser("mascarar", help="mascara o CPF nos textos dos arquivos do dia já gravados (uma vez)")
    c.add_argument("--estado", required=True)

    c = sub.add_parser("transparencia", help="portais de transparência dos entes pelo PNTP")
    c.add_argument("--estado", required=True)

    c = sub.add_parser("anp", help="preço de revenda da ANP por semana, produto e lugar")
    c.add_argument("--estado", required=True)
    c.add_argument("--maximo-semanas", type=int, default=mercado.MAXIMO_SEMANAS,
                   help="planilhas baixadas por execução, no máximo (as mais recentes primeiro)")

    c = sub.add_parser("publicar", help="monta o site dos painéis a partir do estado")
    c.add_argument("--estado", required=True)
    c.add_argument("--saida", required=True)
    c.add_argument("--hoje", type=_data, help="data da avaliação da conformidade (padrão: hoje em Brasília)")
    return p


COMANDOS = {"cadastro": cmd_cadastro, "contratacoes": cmd_contratacoes, "faltando": cmd_faltando,
            "conformidade": cmd_conformidade, "rcl": cmd_rcl, "despesa-funcao": cmd_despesa_funcao, "pessoal": cmd_pessoal,
            "mascarar": cmd_mascarar, "cnpj": cmd_cnpj, "emendas": cmd_emendas, "convenios": cmd_convenios,
            "transparencia": cmd_transparencia, "anp": cmd_anp,
            "publicar": cmd_publicar}


def main(argv: list[str] | None = None) -> int:
    """Ponto de entrada de ``lumen painel``; falta de configuração (contato da coleta) vira código 2."""
    args = construir_parser().parse_args(argv)
    try:
        return COMANDOS[args.comando](args)
    except Exception as erro:
        from lumen_orquestracao.configuracao import ConfiguracaoAusente
        if isinstance(erro, ConfiguracaoAusente):
            print(f"erro: {erro}", file=sys.stderr)
            return 2
        raise
