"""Linha de comando da referência de mercado (``lumen mercado ...``, ADR-027).

Exemplos::

    lumen mercado anp baixar --semestres 2026-1,2025-2     # série semestral da ANP para o bronze
    lumen mercado anp baixar --semestres 2026-1 --series ca,glp   # combustíveis e gás de cozinha
    lumen mercado anp semanas --de 2026-09-01 --ate 2026-10-03     # planilhas semanais (o presente)
    lumen mercado anp resumo                               # o que foi lido dos arquivos da ANP
    lumen mercado varejo testar --consulta "notebook i5 8gb ssd 256gb"
    lumen mercado varejo coletar --de 2026-03-01 --ate 2026-03-31   # consultas padrão + itens da silver
    lumen mercado comparar --de 2026-03-01 --ate 2026-06-30 --saida dados/mercado/relatorio
    lumen mercado reconhecer "ÓLEO DIESEL S10" --unidade Litro

O fluxo completo, para combustível, é: ``lumen coletar pncp_contratacoes`` na janela, ``lumen coletar
ibge_localidades`` (nomes dos municípios), ``lumen normalizar``, ``lumen coletar pncp_itens --objeto
"combust|gasolina|diesel|etanol|glp|gas de cozinha"``, ``lumen normalizar --fontes pncp_itens``, ``lumen
mercado anp baixar`` (compras de semestres fechados) ou ``lumen mercado anp semanas`` (compras das últimas
semanas) e ``lumen mercado comparar``. O fluxo fica pronto em ``.github/workflows/mercado-referencia.yml``.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path
from xml.etree import ElementTree

from lumen_ingestao.bronze import ArmazemBronzeLocal
from lumen_ingestao.portas import Janela, coletar_janela
from lumen_normalizacao.silver import consolidar, ler_entidade
from lumen_orquestracao import configuracao, etapas
from lumen_orquestracao.configuracao import Configuracao

from . import anp, relatorio, varejo
from .comparacao import ParametrosMercado, comparar, itens_da_silver
from .especificacao import reconhecer


def _imprimir(dados) -> None:
    """JSON legível na saída padrão, com acentos."""
    print(json.dumps(dados, ensure_ascii=False, indent=2, default=str))


def _semestres(texto: str) -> list[tuple[int, int]]:
    """``2026-1,2025-2`` em [(2026, 1), (2025, 2)] (tipo do argparse)."""
    saida = []
    for parte in texto.split(","):
        if not parte.strip():
            continue
        ano, _, sem = parte.strip().partition("-")
        saida.append((int(ano), int(sem.lstrip("0") or "0")))
    return saida


def _series(texto: str) -> list[str]:
    """``ca,glp`` em ["ca", "glp"], recusando série desconhecida (tipo do argparse)."""
    series = [s.strip().lower() for s in texto.split(",") if s.strip()]
    desconhecidas = [s for s in series if s not in anp.SERIES]
    if desconhecidas or not series:
        raise argparse.ArgumentTypeError(f"séries válidas: {', '.join(sorted(anp.SERIES))}")
    return series


def _data(texto: str | None) -> date | None:
    """``AAAA-MM-DD`` em ``date``; None se vazio."""
    return date.fromisoformat(texto) if texto else None


def _cliente(cfg: Configuracao, fonte_id: str):
    """Cliente HTTP do pipeline (User-Agent com o contato e limite de taxa da fonte)."""
    return etapas.cliente(cfg, fonte_id)


# ------------------------------------------------------------------ ANP

_ACEITA_ANP = {"Accept": "application/zip, text/csv, application/vnd.openxmlformats-officedocument."
                        "spreadsheetml.sheet, */*"}


def _guardar_da_anp(cfg: Configuracao, urls: list[tuple[str, str]]) -> tuple[list[dict], int]:
    """Baixa cada (rótulo, url) para o bronze; devolve o que foi guardado e quantas respostas não foram 200."""
    armazem = ArmazemBronzeLocal(cfg.bronze)
    cliente = _cliente(cfg, anp.FONTE_ID)
    saida, erros = [], 0
    for rotulo, url in urls:
        artefato = cliente.obter(url, _ACEITA_ANP)
        registro = armazem.guardar(artefato)
        erros += artefato.status_http != 200
        saida.append({"arquivo": rotulo, "status": artefato.status_http, "bytes": len(artefato.conteudo),
                      "sha256": registro.sha256, "url": url})
    return saida, erros


def cmd_anp_baixar(cfg: Configuracao, args) -> int:
    """Baixa os arquivos semestrais da ANP para o bronze (prova com hash) e imprime o que guardou."""
    urls = [(f"{serie}-{ano}-{semestre}", anp.url_semestre(ano, semestre, serie))
            for serie in args.series for ano, semestre in args.semestres]
    saida, erros = _guardar_da_anp(cfg, urls)
    _imprimir(saida)
    return 1 if erros else 0


def cmd_anp_semanas(cfg: Configuracao, args) -> int:
    """Lê a página do levantamento semanal, acha as planilhas da janela e baixa cada uma para o bronze.

    A página em si não vai para o bronze: é só o índice dos arquivos, e cada planilha guardada já tem o
    próprio endereço e hash. Sem nenhuma planilha reconhecida na página, o comando falha e mostra o começo
    dos links que encontrou, para ajustar o padrão se a ANP mudar o nome dos arquivos.
    """
    pagina = _cliente(cfg, anp.FONTE_ID).obter(args.pagina, {"Accept": "text/html"})
    if pagina.status_http != 200:
        _imprimir({"pagina": args.pagina, "status": pagina.status_http})
        return 1
    html = pagina.conteudo.decode("utf-8", errors="replace")
    semanas = anp.links_semanais(html, pagina.url_efetiva or args.pagina)
    if not semanas:
        _imprimir({"pagina": args.pagina, "planilhas": 0,
                   "links_xlsx": re.findall(r"href=[\"']([^\"']+\.xlsx)", html, re.IGNORECASE)[:10]})
        return 1
    escolhidas = anp.semanas_na_janela(semanas, _data(args.de), _data(args.ate))
    if args.ultimas:
        escolhidas = escolhidas[-args.ultimas:]
    saida, erros = _guardar_da_anp(cfg, [(f"{s.inicio.isoformat()}_{s.fim.isoformat()}", s.url) for s in escolhidas])
    _imprimir({"planilhas_na_pagina": len(semanas),
               "periodo_na_pagina": [semanas[0].inicio.isoformat(), semanas[-1].fim.isoformat()],
               "baixadas": saida})
    return 1 if erros or not escolhidas else 0


def carregar_anp(armazem: ArmazemBronzeLocal, resumo: anp.ResumoLeitura | None = None) -> anp.PrecosAnp:
    """Índice de preços com todos os arquivos da ANP guardados no bronze (respostas 200).

    Arquivo que não dá para ler (formato novo, cabeçalho sem as colunas) não derruba a carga: entra em
    ``resumo.arquivos`` com o erro, e os outros seguem.
    """
    resumo = resumo if resumo is not None else anp.ResumoLeitura()
    precos = anp.PrecosAnp()
    for registro in armazem.listar_registros(anp.FONTE_ID):
        if registro.status_http != 200:
            continue
        _, conteudo = armazem.recuperar(registro.registro_id)
        antes, novas = resumo.aproveitadas, 0
        try:
            for coleta in anp.ler_bytes(conteudo, resumo):
                novas += precos.adicionar(coleta)
            erro = None
        except (ValueError, KeyError, zipfile.BadZipFile, ElementTree.ParseError) as e:
            erro = f"{type(e).__name__}: {e}"
        resumo.arquivos.append({"url": registro.url_solicitada, "lidas": resumo.aproveitadas - antes,
                                "novas": novas, "erro": erro})
    return precos


def cmd_anp_resumo(cfg: Configuracao, args) -> int:
    """Imprime o cabeçalho encontrado, os produtos, o período e os descartes da leitura dos arquivos da ANP."""
    resumo = anp.ResumoLeitura()
    precos = carregar_anp(ArmazemBronzeLocal(cfg.bronze), resumo)
    periodo = precos.periodo()
    _imprimir({"coletas": precos.total, "repetidas_entre_arquivos": precos.repetidas,
               "periodo": [d.isoformat() for d in periodo] if periodo else None,
               "municipios": len(precos.municipios()), "por_produto": precos.produtos(),
               "cabecalho": resumo.cabecalho,
               "produtos_no_arquivo": dict(sorted(resumo.produtos.items(), key=lambda kv: -kv[1])),
               "descartadas": resumo.descartadas, "arquivos": resumo.arquivos})
    return 0 if precos.total else 1


# ------------------------------------------------------------------ varejo

def _consultas_da_silver(cfg: Configuracao, de: date | None, ate: date | None) -> list[str]:
    """Consultas de varejo dos itens de informática reconhecidos nos processos publicados na janela."""
    processos = {p["id"]: p for p in etapas.processos_da_silver(cfg, de=de, ate=ate)}
    consultas = set()
    for i in consolidar(ler_entidade(cfg.silver, "item_contratacao")):
        if i["processo_id"] not in processos:
            continue
        e = reconhecer(i.get("descricao_original"), i.get("unidade_medida"))
        if e is not None and e.referencia == "varejo" and e.consulta:
            consultas.add(e.consulta)
    return sorted(consultas)


def cmd_varejo_coletar(cfg: Configuracao, args) -> int:
    """Busca no varejo as consultas padrão e as dos itens da silver, guardando cada resposta no bronze."""
    parametros = ParametrosMercado.carregar(Path(args.parametros) if args.parametros else None)
    consultas = [] if args.sem_padrao else list(parametros.consultas_padrao)
    if args.consultas:
        consultas += [c.strip() for c in args.consultas.split(",")]
    if args.de or args.ate:
        consultas += _consultas_da_silver(cfg, _data(args.de), _data(args.ate))
    fonte = varejo.FonteMercadoLivre(_cliente(cfg, varejo.FONTE_ID), consultas, base=varejo.BASE_ML)
    hoje = date.today()
    resumo = coletar_janela(fonte, Janela(hoje, hoje), ArmazemBronzeLocal(cfg.bronze))
    _imprimir({"consultas": len(fonte.consultas), "guardados": len(resumo.guardados), "falhas": resumo.falhas,
               "recusadas_pela_loja": fonte.recusadas})
    return 1 if resumo.falhas or fonte.recusadas else 0


def cmd_varejo_testar(cfg: Configuracao, args) -> int:
    """Uma busca de teste, sem guardar: status, quantas ofertas vieram, quantas conferem e os campos vistos."""
    fonte = varejo.FonteMercadoLivre(_cliente(cfg, varejo.FONTE_ID), [args.consulta], base=varejo.BASE_ML)
    ref = next(fonte.listar(Janela(date.today(), date.today())))
    artefato = fonte.baixar(ref)
    ofertas = varejo.ler_ofertas(artefato.conteudo, datetime.now(timezone.utc))
    espec = reconhecer(args.consulta, "unidade")
    comparaveis = varejo.ofertas_comparaveis(espec, ofertas) if espec else []
    try:
        corpo = json.loads(artefato.conteudo.decode("utf-8-sig"))
    except (ValueError, UnicodeDecodeError):
        corpo = None
    primeiro = (corpo or {}).get("results", [{}])[0] if isinstance(corpo, dict) and corpo.get("results") else {}
    _imprimir({"status": artefato.status_http, "com_token": bool(fonte.token), "ofertas": len(ofertas),
               "comparaveis": len(comparaveis), "especificacao": espec.produto if espec else None,
               "campos_do_primeiro_resultado": sorted(primeiro) if isinstance(primeiro, dict) else [],
               "mensagem": (corpo or {}).get("message") if isinstance(corpo, dict) else None,
               "exemplos": [{"titulo": o.titulo, "preco": str(o.preco)} for o in comparaveis[:5]]})
    return 0 if artefato.status_http == 200 else 1


# ------------------------------------------------------------------ comparação

def cmd_comparar(cfg: Configuracao, args) -> int:
    """Aplica a regra A-05 aos itens da silver e grava o relatório silencioso; imprime as contagens."""
    parametros = ParametrosMercado.carregar(Path(args.parametros) if args.parametros else None)
    armazem = ArmazemBronzeLocal(cfg.bronze)
    processos = etapas.processos_da_silver(cfg, de=_data(args.de), ate=_data(args.ate))
    itens = consolidar(ler_entidade(cfg.silver, "item_contratacao"))
    resultados = consolidar(ler_entidade(cfg.silver, "resultado_item"))
    municipios = {e["codigo_ibge"]: e["nome"] for e in consolidar(ler_entidade(cfg.silver, "ente_federativo"))
                  if e.get("codigo_ibge") and len(str(e["codigo_ibge"])) == 7}
    precos = carregar_anp(armazem)
    ofertas = varejo.OfertasVarejo.do_bronze(armazem)
    comparacoes = comparar(itens_da_silver(processos, itens, resultados), parametros, anp=precos, varejo=ofertas,
                           municipios=municipios)
    saida = Path(args.saida) if args.saida else cfg.raiz_dados / "mercado" / "relatorio"
    contagem = relatorio.escrever(comparacoes, saida, parametros)
    periodo = precos.periodo()
    _imprimir({**contagem, "processos": len(processos), "coletas_anp": precos.total,
               "periodo_anp": [d.isoformat() for d in periodo] if periodo else None,
               "consultas_varejo": len(ofertas.consultas()), "municipios_com_nome": len(municipios),
               "saida": str(saida)})
    return 0


def cmd_reconhecer(cfg: Configuracao | None, args) -> int:
    """Mostra a especificação que a regra reconhece numa descrição (ou que não reconhece nada)."""
    e = reconhecer(args.descricao, args.unidade)
    _imprimir(e.__dict__ if e else None)
    return 0 if e else 1


def main(argv: list[str] | None = None) -> int:
    """Ponto de entrada de ``lumen mercado``: lê a configuração do pipeline e despacha para o comando."""
    parser = argparse.ArgumentParser(prog="lumen mercado", description="Referência de mercado (regra A-05)")
    parser.add_argument("--config", help="caminho do lumen.toml")
    sub = parser.add_subparsers(dest="comando", required=True)

    a = sub.add_parser("anp", help="preço de bomba da ANP").add_subparsers(dest="acao", required=True)
    c = a.add_parser("baixar", help="baixa os arquivos semestrais para o bronze")
    c.add_argument("--semestres", type=_semestres, required=True, help="AAAA-S separados por vírgula")
    c.add_argument("--series", type=_series, default=["ca"], help="ca (combustíveis) e/ou glp, por vírgula")
    c = a.add_parser("semanas", help="baixa as planilhas semanais do levantamento para o bronze")
    c.add_argument("--de", help="semanas que terminam a partir desta data (AAAA-MM-DD)")
    c.add_argument("--ate", help="... e começam até esta data")
    c.add_argument("--ultimas", type=int, default=0, help="só as N semanas mais recentes da janela")
    c.add_argument("--pagina", default=anp.PAGINA_SEMANAS, help=argparse.SUPPRESS)
    a.add_parser("resumo", help="o que foi lido dos arquivos guardados")

    v = sub.add_parser("varejo", help="ofertas do varejo online").add_subparsers(dest="acao", required=True)
    c = v.add_parser("coletar", help="busca as consultas e guarda as respostas no bronze")
    c.add_argument("--consultas", help="consultas extras, separadas por vírgula")
    c.add_argument("--de", help="inclui as consultas dos itens publicados a partir desta data")
    c.add_argument("--ate", help="... até esta data")
    c.add_argument("--sem-padrao", action="store_true", help="não busca as consultas padrão")
    c.add_argument("--parametros", help="arquivo de parâmetros (padrão: o do pacote)")
    c = v.add_parser("testar", help="uma busca de teste, sem guardar")
    c.add_argument("--consulta", required=True)

    c = sub.add_parser("comparar", help="aplica a regra A-05 e grava o relatório silencioso")
    c.add_argument("--de", help="processos publicados a partir desta data (AAAA-MM-DD)")
    c.add_argument("--ate", help="... até esta data")
    c.add_argument("--saida", help="diretório do relatório (padrão: <dados>/mercado/relatorio)")
    c.add_argument("--parametros", help="arquivo de parâmetros (padrão: o do pacote)")

    c = sub.add_parser("reconhecer", help="mostra a especificação reconhecida numa descrição")
    c.add_argument("descricao")
    c.add_argument("--unidade", default=None)

    args = parser.parse_args(argv)
    if args.comando == "reconhecer":
        return cmd_reconhecer(None, args)
    try:
        cfg = configuracao.carregar(Path(args.config) if args.config else None)
    except configuracao.ConfiguracaoAusente as erro:
        print(f"erro: {erro}", file=sys.stderr)
        return 2
    comandos = {("anp", "baixar"): cmd_anp_baixar, ("anp", "semanas"): cmd_anp_semanas,
                ("anp", "resumo"): cmd_anp_resumo,
                ("varejo", "coletar"): cmd_varejo_coletar, ("varejo", "testar"): cmd_varejo_testar,
                ("comparar", None): cmd_comparar}
    return comandos[(args.comando, getattr(args, "acao", None))](cfg, args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
