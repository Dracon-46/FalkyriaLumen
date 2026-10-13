"""Relatório interno da regra A-05 em modo silencioso: JSON Lines, CSV, distribuição e um resumo em Markdown.

Nada aqui é publicação. O relatório existe para calibrar a regra (quantos itens passariam do limiar, em
quais categorias, com qual distância) e para que uma pessoa possa olhar os casos de maior distância com a
referência completa ao lado. A distribuição da razão (``distribuicao.json``) separa categoria, tipo de
preço (homologado ou estimado) e escopo da referência (município ou UF), porque a calibração precisa medir
cada grupo à parte: o preço estimado e a referência da UF têm outra distância esperada. A linguagem segue a do DOC-08 mesmo assim, porque relatório interno vira
captura de tela: "preço acima da referência comparada", nunca adjetivo sobre conduta.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import Iterable

from .comparacao import ACIMA, FORA_DE_ESCALA, NAO_COMPARAVEL, Comparacao, ParametrosMercado
from .referencia import quantil

# Limiares candidatos: para cada um, a fração dos itens com referência que ficaria acima dele.
LIMIARES_SENSIBILIDADE = ("1.10", "1.20", "1.25", "1.30", "1.50", "2.00")
AMOSTRA_PEQUENA = 20

COLUNAS_CSV = [
    "situacao", "razao", "limiar", "tipo_preco", "categoria", "produto", "uf", "municipio", "data_referencia",
    "preco_unitario", "quantidade", "valor_total", "ref_fonte", "ref_escopo", "ref_quantidade", "ref_minimo",
    "ref_mediana", "ref_p75", "ref_maximo", "ref_periodo", "descricao", "unidade_medida", "orgao_cnpj",
    "processo", "fornecedor", "marcacoes", "item_id", "regra", "modo",
]


def _linha_csv(c: Comparacao) -> dict:
    """Uma comparação achatada para o CSV, com a referência em colunas próprias."""
    d = c.para_dict()
    ref = d.pop("referencia") or {}
    d.update({f"ref_{k}": v for k, v in ref.items() if k in ("fonte", "escopo", "quantidade", "minimo",
                                                              "mediana", "p75", "maximo")})
    d["ref_periodo"] = " a ".join(ref.get("periodo", []))
    d["marcacoes"] = ";".join(d.get("marcacoes") or [])
    return {k: d.get(k) for k in COLUNAS_CSV}


def _real(valor: Decimal | None) -> str:
    """Valor em reais no formato brasileiro (``R$ 1.234,56``), ou travessão."""
    if valor is None:
        return "—"
    inteiro, _, centavos = f"{valor:,.2f}".partition(".")
    return f"R$ {inteiro.replace(',', '.')},{centavos}"


def _q(razoes: list[Decimal], fracao: str) -> str:
    """Quantil de razões já ordenadas, com três casas."""
    return str(quantil(razoes, fracao).quantize(Decimal("0.001")))


def distribuicao(comparacoes: Iterable[Comparacao]) -> list[dict]:
    """Distribuição da razão por (categoria, tipo de preço, escopo da referência), com a sensibilidade ao limiar.

    Para cada grupo: quantidade, quantis (10, 25, 50, 75 e 90%) e máximo da razão, e, para cada limiar de
    ``LIMIARES_SENSIBILIDADE``, quantos itens e que fração ficariam acima dele. Só entram itens com referência;
    os fora de escala (preço simbólico ou erro de unidade) ficam de fora, porque deslocariam os quantis de baixo.
    """
    grupos: dict[tuple[str, str, str], list[Decimal]] = {}
    for c in comparacoes:
        if c.razao is None or c.especificacao is None or c.referencia is None:
            continue
        if getattr(c, "situacao", None) == FORA_DE_ESCALA:
            continue
        grupos.setdefault((c.especificacao.categoria, c.tipo_preco, c.referencia.escopo), []).append(c.razao)
    saida = []
    for (categoria, tipo, escopo), razoes in sorted(grupos.items()):
        razoes.sort()
        n = len(razoes)
        acima = {}
        for limiar in LIMIARES_SENSIBILIDADE:
            k = sum(1 for r in razoes if r >= Decimal(limiar))
            acima[limiar] = {"itens": k, "fracao": str((Decimal(k) / n).quantize(Decimal("0.001")))}
        saida.append({"categoria": categoria, "tipo_preco": tipo, "escopo": escopo, "itens": n,
                      "amostra_pequena": n < AMOSTRA_PEQUENA, "p10": _q(razoes, "0.10"),
                      "p25": _q(razoes, "0.25"), "mediana": _q(razoes, "0.5"), "p75": _q(razoes, "0.75"),
                      "p90": _q(razoes, "0.90"), "maximo": str(razoes[-1]),
                      "acima_de": acima})
    return saida


def _percentual(fracao: str) -> str:
    """``0.125`` em ``12,5%``."""
    return f"{Decimal(fracao) * 100:.1f}%".replace(".", ",")


def resumo_markdown(comparacoes: list[Comparacao], parametros: ParametrosMercado, *, limite: int = 25) -> str:
    """Resumo para leitura humana: contagens, parâmetros e os itens de maior distância acima da referência."""
    por_situacao = Counter(c.situacao for c in comparacoes)
    comparaveis = [c for c in comparacoes if c.situacao != NAO_COMPARAVEL]
    por_categoria = Counter((c.especificacao.categoria, c.situacao) for c in comparaveis)
    linhas = [
        "# Regra A-05 — preço comparado com o mercado (modo silencioso)",
        "",
        "Relatório interno de calibração. Nada aqui foi publicado. Preço acima da referência comparada é "
        "atividade para análise: entrega no local, prazo de pagamento, quantidade e especificação podem "
        "explicar a distância.",
        "",
        f"- Itens lidos: {len(comparacoes)}",
        f"- Reconhecidos como comparáveis: {len(comparaveis)}",
        f"- Com referência de mercado: {por_situacao[ACIMA] + por_situacao['dentro_da_referencia']}",
        f"- Acima do limiar: {por_situacao[ACIMA]}",
        f"- Sem referência na época e no lugar: {por_situacao['sem_referencia']}",
        f"- Fora de escala (abaixo de {parametros.razao_minima_plausivel}× ou acima de "
        f"{parametros.razao_maxima_plausivel}× a mediana: preço simbólico, valor total lançado como unitário ou "
        f"erro de unidade; fora da distribuição): {por_situacao[FORA_DE_ESCALA]}",
        f"- Limiar: combustível {parametros.combustivel_limiar}×, gás de cozinha "
        f"{parametros.gas_de_cozinha_limiar}× e varejo {parametros.varejo_limiar}× a mediana "
        f"({'calibrado' if parametros.calibrado else 'ainda não calibrado'})",
        "",
        "| Categoria | Situação | Itens |",
        "|---|---|---|",
    ]
    for (categoria, situacao), n in sorted(por_categoria.items()):
        linhas.append(f"| {categoria} | {situacao} | {n} |")
    grupos = distribuicao(comparacoes)
    linhas += ["", "## Distribuição da razão (para calibrar)", "",
               "Razão = preço unitário ÷ mediana da referência. As colunas \"≥\" dizem que fração do grupo "
               f"ficaria acima de cada limiar candidato. Grupo com menos de {AMOSTRA_PEQUENA} itens é marcado "
               "com \\*: a amostra ainda não sustenta um limiar.", ""]
    if not grupos:
        linhas.append("Nenhum item com referência.")
    else:
        linhas += ["| Categoria | Preço | Referência | Itens | p25 | Mediana | p75 | p90 | ≥1,2 | ≥1,5 | ≥2,0 |",
                   "|---|---|---|---|---|---|---|---|---|---|---|"]
        for g in grupos:
            marca = "\\*" if g["amostra_pequena"] else ""
            linhas.append(
                f"| {g['categoria']} | {g['tipo_preco']} | {g['escopo']} | {g['itens']}{marca} | {g['p25']} | "
                f"{g['mediana']} | {g['p75']} | {g['p90']} | {_percentual(g['acima_de']['1.20']['fracao'])} | "
                f"{_percentual(g['acima_de']['1.50']['fracao'])} | {_percentual(g['acima_de']['2.00']['fracao'])} |")
    destaques = sorted(
        (c for c in comparacoes if c.situacao == ACIMA and c.tipo_preco == "homologado"
         and (c.valor_total or Decimal(0)) >= parametros.valor_total_minimo_destaque),
        key=lambda c: (c.razao or Decimal(0)), reverse=True)[:limite]
    linhas += ["", f"## Maiores distâncias (preço homologado, valor total a partir de "
                   f"{_real(parametros.valor_total_minimo_destaque)})", ""]
    linhas += _tabela_destaques(destaques, "Pago")
    estimados = sorted(
        (c for c in comparacoes if c.situacao == ACIMA and c.tipo_preco == "estimado"
         and (c.valor_total or Decimal(0)) >= parametros.valor_total_minimo_destaque),
        key=lambda c: (c.razao or Decimal(0)), reverse=True)[:limite]
    linhas += ["", "## Maiores distâncias no preço estimado (pesquisa de preços da compra, antes do resultado)", "",
               "Outro fato, separado do homologado: a estimativa acima do mercado pode vir de orçamentos altos na "
               "pesquisa de preços, e o preço contratado ainda pode sair menor.", ""]
    linhas += _tabela_destaques(estimados, "Estimado")
    return "\n".join(linhas) + "\n"


def _tabela_destaques(comparacoes: list[Comparacao], rotulo_preco: str) -> list[str]:
    """Linhas de uma tabela Markdown de itens acima da referência, ou "Nenhum item."."""
    if not comparacoes:
        return ["Nenhum item."]
    linhas = [f"| Razão | Produto | Local | Data | {rotulo_preco} | Mediana (n) | Máximo | Valor total | Marcas | "
              "Processo |", "|---|---|---|---|---|---|---|---|---|---|"]
    for c in comparacoes:
        ref = c.referencia
        local = f"{c.municipio or c.municipio_codigo_ibge or '?'}/{c.uf or '?'}"
        marcas = ", ".join(m for m in c.marcacoes if m != "preco_estimado") or "—"
        linhas.append(
            f"| {c.razao}× | {c.especificacao.produto} | {local} | {c.data_referencia.isoformat()} | "
            f"{_real(c.preco_unitario)} | {_real(ref.mediana)} ({ref.quantidade}, {ref.escopo}) | "
            f"{_real(ref.maximo)} | {_real(c.valor_total)} | {marcas} | {c.processo} |")
    return linhas


def escrever(comparacoes: Iterable[Comparacao], destino: Path | str, parametros: ParametrosMercado) -> dict:
    """Grava ``comparacoes.jsonl``, ``comparacoes.csv``, ``distribuicao.json`` e ``resumo.md`` no destino.

    Devolve as contagens por situação e a distribuição da razão por grupo.
    """
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)
    lista = list(comparacoes)
    with open(destino / "comparacoes.jsonl", "w", encoding="utf-8") as fh:
        for c in lista:
            fh.write(json.dumps(c.para_dict(), ensure_ascii=False, sort_keys=True) + "\n")
    with open(destino / "comparacoes.csv", "w", encoding="utf-8-sig", newline="") as fh:
        escritor = csv.DictWriter(fh, fieldnames=COLUNAS_CSV, delimiter=";")
        escritor.writeheader()
        for c in lista:
            if c.situacao != NAO_COMPARAVEL:
                escritor.writerow(_linha_csv(c))
    grupos = distribuicao(lista)
    (destino / "distribuicao.json").write_text(json.dumps(grupos, ensure_ascii=False, indent=2) + "\n",
                                               encoding="utf-8")
    (destino / "resumo.md").write_text(resumo_markdown(lista, parametros), encoding="utf-8")
    contagem = Counter(c.situacao for c in lista)
    return {"itens": len(lista), **{k: contagem[k] for k in sorted(contagem)}, "distribuicao": grupos}
