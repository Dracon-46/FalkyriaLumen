"""``lumen painel``: coleta e publicação dos painéis de contratações e de conformidade (ADR-028).

Exemplos::

    lumen painel cadastro --estado estado/                          # cadastro de entes do SICONFI
    lumen painel contratacoes --estado estado/ --ultimos 3          # dias que faltam entre os 3 últimos
    lumen painel contratacoes --estado estado/ --de 2026-01-01 --ate 2026-01-31 --limite-minutos 300
    lumen painel faltando --estado estado/ --de 2026-01-01 --partes 6   # divisão para execuções paralelas
    lumen painel conformidade --estado estado/ --ufs SP,MG --exercicios 2025,2026
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
from datetime import date, timedelta
from pathlib import Path

from . import conformidade as conf
from . import contratacoes as contr
from .cadastro import Cadastro
from .comum import gravar_json, hoje_brasilia, instante_utc
from .dia import coletar_dia, dias_guardados
from .site import Site

ARQUIVO_CADASTRO = "cadastro-entes.json.gz"
INICIO_PADRAO = date(2026, 1, 1)
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
    hoje = hoje_brasilia()
    exercicios = [int(x) for x in _lista(args.exercicios)] if args.exercicios else [hoje.year - 1, hoje.year]
    resultados = []
    for uf in _lista(args.ufs):
        r = conf.coletar_uf(cfg, uf, cadastro, exercicios, Path(args.estado))
        resultados.append(r.para_json())
        print(f"{uf}: {r.consultas_ok} de {r.consultas} consulta(s) completas"
              + (f"; {'; '.join(r.problemas)}" if r.problemas else ""), file=sys.stderr, flush=True)
    _imprimir({"exercicios": exercicios, "ufs": resultados})
    return 1 if any(not r["gravado"] for r in resultados) else 0


def cmd_publicar(args) -> int:
    """Monta o site inteiro a partir do estado: índice, busca, contratações e conformidade."""
    estado = Path(args.estado)
    gerado_em = instante_utc()
    hoje = args.hoje or hoje_brasilia()
    caminho_cadastro = estado / ARQUIVO_CADASTRO
    cadastro = Cadastro.ler(caminho_cadastro) if caminho_cadastro.exists() else Cadastro({})
    site = Site(args.saida)

    painel = contr.somar_dias(estado.glob("contratacoes-*.json.gz"), cadastro)
    for codigo, acumulador in painel.entes.items():
        site.gravar(f"contratacoes/ente/{codigo}.json",
                    contr.ente_para_json(codigo, acumulador, painel, cadastro, gerado_em))
    for cnpj, acumulador in painel.por_orgao.items():
        site.gravar(f"contratacoes/orgao/{cnpj}.json",
                    contr.orgao_para_json(cnpj, acumulador, painel, cadastro, gerado_em))
    site.gravar("contratacoes/panorama.json", contr.panorama_para_json(painel, cadastro, gerado_em))
    site.gravar("orgaos.json", contr.orgaos_para_busca(painel, gerado_em))

    avaliacao = conf.avaliar(estado.glob("conformidade-*.json.gz"), cadastro, hoje=hoje, gerado_em=gerado_em)
    for codigo, arquivo in avaliacao.entes.items():
        site.gravar(f"conformidade/ente/{codigo}.json", arquivo)
    for uf in sorted({a["ente"]["uf"] for a in avaliacao.entes.values() if a["ente"]["uf"]}):
        site.gravar(f"conformidade/uf/{uf}.json", conf.uf_para_json(uf, avaliacao, gerado_em))
    site.gravar("conformidade/panorama.json", conf.panorama_para_json(avaliacao, gerado_em))

    entes = {c: [c, e.nome, e.uf, e.esfera, e.populacao] for c, e in cadastro.entes.items()}
    for codigo in set(painel.entes) | set(avaliacao.entes):
        entes.setdefault(codigo, [codigo, cadastro.nome(codigo), None, None, None])
    site.gravar("entes.json", {"versao": 1, "gerado_em": gerado_em,
                               "colunas": ["codigo", "nome", "uf", "esfera", "populacao"],
                               "entes": [entes[c] for c in sorted(entes)]})
    indice = {"versao": 1, "gerado_em": gerado_em, "avaliado_em": hoje.isoformat(),
              "cadastro": {"entes": len(cadastro), "gerado_em": cadastro.gerado_em},
              "contratacoes": {**painel.cobertura(), "entes": len(painel.entes), "orgaos": len(painel.por_orgao)},
              "conformidade": {"entes": len(avaliacao.entes), "ufs": avaliacao.coletas}}
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
    c.add_argument("--exercicios", help="padrão: o anterior e o corrente")

    c = sub.add_parser("publicar", help="monta o site dos painéis a partir do estado")
    c.add_argument("--estado", required=True)
    c.add_argument("--saida", required=True)
    c.add_argument("--hoje", type=_data, help="data da avaliação da conformidade (padrão: hoje em Brasília)")
    return p


COMANDOS = {"cadastro": cmd_cadastro, "contratacoes": cmd_contratacoes, "faltando": cmd_faltando,
            "conformidade": cmd_conformidade, "publicar": cmd_publicar}


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
