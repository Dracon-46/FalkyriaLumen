"""Despesa da União por função, para comparar os mandatos presidenciais (ADR-033, adendo de 20/10/2026).

A fonte é o RREO da União do 6º bimestre, Anexo 2 (despesa por função e subfunção), no SICONFI (``id_ente=1``),
de 2015 em diante, o primeiro exercício que o SICONFI tem. Vale a despesa liquidada no ano, sem as
intraorçamentárias:

- **Coluna**: ``Até o Bimestre (d)`` em 2015 e ``DESPESAS LIQUIDADAS ATÉ O BIMESTRE (d)`` depois.
- **Bloco**: a partir de 2016, o anexo repete as funções num bloco das intraorçamentárias; vale o bloco cujo
  rótulo diz "Exceto" (em 2015, o rótulo vem nulo e há um bloco só).
- **Funções e subfunções**: o anexo põe funções e subfunções na mesma lista, sem marcar qual é qual. As funções
  são as 28 da classificação funcional (Portaria MOG 42/1999), e as primeiras linhas delas somam o total. Em
  2015 e em 2025 a soma confere com o total ao centavo.

Na publicação, os valores vão em bilhões de reais do último ano com o IPCA completo, corrigidos pelo IPCA médio
de cada ano. Comparar dois mandatos mostra a média anual em cada um. Mostra o que foi gasto, não o que causou a
diferença: boa parte da despesa (previdência, juros, transferências) vem de regras anteriores ao governo.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from lumen_ingestao.cliente_http import ClienteHttp
from lumen_ingestao.coleta_http import ErroColeta
from lumen_painel.comum import gravar_json

from .coleta import ARQUIVO_ESTADO, SerieIlegivel, ler_estado

FONTE_ID = "siconfi_rreo"
FONTE = "Tesouro Nacional, RREO da União (6º bimestre, Anexo 2), pelo SICONFI"
PRIMEIRO_ANO = 2015
ANOS_A_RECONFERIR = 2   # o RREO pode ser retificado: os dois últimos anos são lidos de novo a cada coleta
GRUPO = ("despesa_uniao", "Despesa da União")

# As 28 funções da classificação funcional (Portaria MOG 42/1999), como o RREO as escreve
FUNCOES_DA_CLASSIFICACAO = (
    "Legislativa", "Judiciária", "Essencial à Justiça", "Administração", "Defesa Nacional", "Segurança Pública",
    "Relações Exteriores", "Assistência Social", "Previdência Social", "Saúde", "Trabalho", "Educação", "Cultura",
    "Direitos da Cidadania", "Urbanismo", "Habitação", "Saneamento", "Gestão Ambiental", "Ciência e Tecnologia",
    "Agricultura", "Organização Agrária", "Indústria", "Comércio e Serviços", "Comunicações", "Energia",
    "Transporte", "Desporto e Lazer", "Encargos Especiais",
)
# As que vão para o portal: id, nome, função no RREO (None: o total) e o que entra nela
MOSTRADAS = (
    ("despesa_uniao_total", "Despesa total da União", None,
     "Toda a despesa liquidada no ano, sem as intraorçamentárias (pagamentos entre órgãos do próprio governo)."),
    ("despesa_uniao_previdencia", "Previdência Social", "Previdência Social",
     "Benefícios do INSS e aposentadorias e pensões dos servidores federais."),
    ("despesa_uniao_encargos", "Encargos especiais", "Encargos Especiais",
     "Juros e amortização da dívida e transferências obrigatórias a estados e municípios, entre outros."),
    ("despesa_uniao_saude", "Saúde", "Saúde", "Despesa da União com saúde, inclusive o repasse ao SUS."),
    ("despesa_uniao_educacao", "Educação", "Educação", "Despesa da União com educação, inclusive a complementação ao FUNDEB."),
    ("despesa_uniao_assistencia", "Assistência social", "Assistência Social",
     "Benefícios assistenciais (BPC) e programas de transferência de renda, entre outros."),
    ("despesa_uniao_defesa", "Defesa nacional", "Defesa Nacional", "Forças Armadas."),
)


def url_rreo_uniao(ano: int) -> str:
    """O RREO da União do 6º bimestre do ``ano``, Anexo 2, no SICONFI."""
    return ("https://apidatalake.tesouro.gov.br/ords/siconfi/tt/rreo?an_exercicio="
            f"{ano}&nr_periodo=6&co_tipo_demonstrativo=RREO&no_anexo=RREO-Anexo%2002&id_ente=1")


def ler_despesas(conteudo: bytes) -> dict[str, float]:
    """Por id de ``MOSTRADAS``, a despesa liquidada no ano, em reais da época; levanta ``SerieIlegivel``.

    Confere que as 28 funções somam o total (diferença acima de 0,1% é erro de leitura).
    """
    try:
        itens = json.loads(conteudo)["items"]
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as erro:
        raise SerieIlegivel(f"RREO da União ilegível: {conteudo[:80]!r}") from erro
    colunas = {i.get("coluna") for i in itens}
    coluna = next((c for c in colunas if c and "(d)" in c and ("LIQUIDADAS" in c.upper() or c.startswith("Até o Bimestre"))),
                  None)
    if coluna is None:
        raise SerieIlegivel(f"RREO da União sem a coluna da despesa liquidada: {sorted(map(str, colunas))[:6]}")
    linhas = [i for i in itens if i.get("coluna") == coluna
              and (i.get("rotulo") is None or "exceto" in str(i.get("rotulo")).lower())]
    funcoes: dict[str, float] = {}
    total = None
    for linha in linhas:
        conta = str(linha.get("conta") or "").strip()
        if conta.upper().startswith("DESPESAS (EXCETO INTRA") and total is None:
            total = float(linha["valor"])
        elif conta in FUNCOES_DA_CLASSIFICACAO and conta not in funcoes:
            funcoes[conta] = float(linha["valor"] or 0)
    if total is None:
        raise SerieIlegivel("RREO da União sem o total da despesa")
    if abs(sum(funcoes.values()) - total) > total * 0.001:
        raise SerieIlegivel(f"as funções somam {sum(funcoes.values()):.2f} e o total é {total:.2f}")
    return {i: (total if funcao is None else funcoes.get(funcao, 0.0)) for i, _, funcao, _ in MOSTRADAS}


def coletar(cliente: ClienteHttp, estado: Path | str, *, ano_corrente: int | None = None,
            agora: datetime | None = None) -> dict:
    """Lê os anos que faltam no estado e os ``ANOS_A_RECONFERIR`` mais recentes; o ano que falha mantém o que havia."""
    dados = ler_estado(estado)
    agora = agora or datetime.now(timezone.utc)
    ultimo = (ano_corrente or agora.year) - 1
    guardados = dados.setdefault("despesas_uniao", {})
    anos = [a for a in range(PRIMEIRO_ANO, ultimo + 1)
            if str(a) not in guardados or a > ultimo - ANOS_A_RECONFERIR]
    lidos, falhas = [], {}
    for ano in anos:
        url = url_rreo_uniao(ano)
        try:
            artefato = cliente.obter(url, {"Accept": "application/json"})
            if artefato.status_http != 200:
                raise SerieIlegivel(f"{url} respondeu {artefato.status_http}")
            valores = ler_despesas(artefato.conteudo)
        except (ErroColeta, ValueError) as erro:
            falhas[str(ano)] = f"{type(erro).__name__}: {erro}"
            continue
        guardados[str(ano)] = {"url": url, "coletado_em": agora.isoformat(timespec="seconds"), "valores": valores}
        lidos.append(ano)
    Path(estado).mkdir(parents=True, exist_ok=True)
    gravar_json(Path(estado) / ARQUIVO_ESTADO, dados, comprimir=True)
    return {"anos": lidos, "falhas": falhas}


def media_anual_do_ipca(observacoes: Iterable[tuple[str, str]]) -> dict[str, float]:
    """O IPCA médio de cada ano completo, como número-índice, das observações mensais guardadas (data ISO, %)."""
    indice, por_ano = 1.0, {}
    for data, valor in sorted(observacoes):
        indice *= 1 + float(valor) / 100
        por_ano.setdefault(data[:4], []).append(indice)
    return {ano: sum(v) / 12 for ano, v in por_ano.items() if len(v) == 12}


def indicadores(estado_dados: dict, documentar) -> dict[str, dict]:
    """Os indicadores da despesa da União para ``economia/indicadores.json``, em bilhões de reais do ano-base.

    ``documentar(id, nome, unidade, definicao, limitacoes, serie)`` monta o indicador no formato do arquivo.
    Sem IPCA para corrigir, a série sai vazia.
    """
    medias = media_anual_do_ipca((estado_dados.get("series", {}).get("433") or {}).get("observacoes") or [])
    base = max(medias) if medias else None
    guardados = estado_dados.get("despesas_uniao") or {}
    saida = {}
    for id_, nome, _, definicao in MOSTRADAS:
        serie = {}
        for ano, registro in sorted(guardados.items()):
            if base and ano in medias:
                serie[ano] = round(registro["valores"][id_] * medias[base] / medias[ano] / 1e9, 2)
        saida[id_] = documentar(
            id_, nome, f"R$ bilhões de {base}" if base else "R$ bilhões", definicao,
            [f"Despesa liquidada no ano pelo RREO da União, de {PRIMEIRO_ANO} em diante (antes, o SICONFI não tem); "
             f"corrigida pelo IPCA médio de cada ano para reais de {base}.",
             "Boa parte da despesa segue regras de antes do governo (previdência, juros, transferências "
             "obrigatórias); a comparação mostra quanto foi gasto, não o que cada governo decidiu."],
            serie, url_rreo_uniao(int(max(guardados))) if guardados else url_rreo_uniao(PRIMEIRO_ANO),
            max((r["coletado_em"] for r in guardados.values()), default=None))
    return saida
