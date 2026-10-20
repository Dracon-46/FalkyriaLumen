"""Os indicadores publicados: as séries do estado, os derivados e o arquivo que o portal lê.

O portal lê ``economia/indicadores.json``, publicado com os painéis no GitHub Pages. Cada indicador leva a
série inteira (mês ``AAAA-MM`` ou ano ``AAAA`` e valor), o último valor, a data da coleta, a fonte e a
documentação do catálogo. As comparações entre períodos (variação, média, acumulado) são feitas no
portal sobre estas séries, com as mesmas regras: sem dado, sem conta.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from lumen_painel.comum import gravar_json

from .catalogo import DERIVADOS, FONTE_SGS, FONTE_SIDRA, GRUPOS, SERIES, Derivado, Serie
from .coleta import ler_estado

VERSAO_FEED = 1
ARQUIVO_FEED = "economia/indicadores.json"


def chave(data_iso: str, periodicidade: str) -> str:
    """Chave do período na série: ``AAAA-MM`` na mensal, ``AAAA`` na anual."""
    return data_iso[:4] if periodicidade == "anual" else data_iso[:7]


def mes_anterior(mes: str) -> str:
    """``2025-01`` → ``2024-12``."""
    ano, m = int(mes[:4]), int(mes[5:7])
    return f"{ano - 1}-12" if m == 1 else f"{ano}-{m - 1:02d}"


def serie_do_estado(observacoes: Iterable[tuple[str, str]], periodicidade: str) -> dict[str, float]:
    """Valores por período, a partir das observações do estado (a última do período, se houver mais de uma)."""
    return {chave(d, periodicidade): float(v) for d, v in observacoes}


def acumulado(variacoes: dict[str, float], meses: int) -> dict[str, float]:
    """Variação acumulada em ``meses`` meses seguidos, em %, só onde os ``meses`` estão todos na série."""
    saida = {}
    for mes in variacoes:
        fator, atual = 1.0, mes
        for _ in range(meses):
            if atual not in variacoes:
                break
            fator *= 1 + variacoes[atual] / 100
            atual = mes_anterior(atual)
        else:
            saida[mes] = round((fator - 1) * 100, 2)
    return saida


def no_ano(variacoes: dict[str, float]) -> dict[str, float]:
    """Variação acumulada de janeiro até o mês, em %, só onde todos os meses do ano até ele estão na série."""
    return {mes: v for mes, v in ((m, acumulado(variacoes, int(m[5:7])).get(m)) for m in variacoes)
            if v is not None}


def juro_real(selic: dict[str, float], inflacao: dict[str, float]) -> dict[str, float]:
    """(1 + Selic) / (1 + inflação) - 1, em %, nos períodos em que há as duas."""
    return {k: round(((1 + selic[k] / 100) / (1 + inflacao[k] / 100) - 1) * 100, 2)
            for k in selic if k in inflacao}


def diferenca(a: dict[str, float], b: dict[str, float]) -> dict[str, float]:
    """``a - b`` nos períodos em que há os dois, com duas casas."""
    return {k: round(a[k] - b[k], 2) for k in a if k in b}


def lacunas(serie: dict[str, float], periodicidade: str) -> list[str]:
    """Períodos sem observação entre o primeiro e o último da série (ausentes, e não zero)."""
    if not serie:
        return []
    chaves = sorted(serie)
    faltando, atual = [], chaves[-1]
    if periodicidade == "anual":
        return [str(a) for a in range(int(chaves[0]), int(chaves[-1])) if str(a) not in serie]
    while atual > chaves[0]:
        atual = mes_anterior(atual)
        if atual not in serie:
            faltando.append(atual)
    return sorted(faltando)


def _documentacao(item: Serie | Derivado) -> dict:
    """Os campos de documentação comuns a séries e derivados."""
    return {"nome": item.nome, "grupo": item.grupo, "unidade": item.unidade, "periodicidade": item.periodicidade,
            "definicao": item.definicao, "leitura": item.leitura, "limitacoes": list(item.limitacoes),
            "agregacao": item.agregacao}


def _publicado(doc: dict, serie: dict[str, float]) -> dict:
    """Acrescenta a série, o último valor e as lacunas à documentação do indicador."""
    pontos = sorted(serie.items())
    return {**doc, "serie": [[k, v] for k, v in pontos],
            "ultimo": {"periodo": pontos[-1][0], "valor": pontos[-1][1]} if pontos else None,
            "lacunas": lacunas(serie, doc["periodicidade"])}


def montar(estado_dados: dict, *, agora: datetime | None = None) -> dict:
    """O arquivo ``economia/indicadores.json`` a partir do estado da coleta."""
    valores: dict[str, dict[str, float]] = {}
    coletas: dict[str, str | None] = {}
    indicadores: dict[str, dict] = {}
    for s in SERIES:
        guardado = estado_dados.get("series", {}).get(s.chave, {})
        valores[s.id] = serie_do_estado(guardado.get("observacoes", []), s.periodicidade)
        coletas[s.id] = guardado.get("coletado_em")
        parcial = None
        if s.parcial_no_mes_corrente and coletas[s.id]:
            parcial = coletas[s.id][:7]
            valores[s.id].pop(parcial, None)
        doc = {**_documentacao(s), "nome_oficial": s.nome_oficial, "fonte": FONTE_SGS if s.codigo else FONTE_SIDRA,
               "fonte_primaria": s.fonte_primaria, "codigo_sgs": s.codigo, "url": s.url,
               "coletado_em": coletas[s.id], "ultima_falha": guardado.get("ultima_falha"),
               "periodo_parcial_omitido": parcial,
               "coletado_de": guardado.get("fonte_coleta", "sgs") if guardado.get("observacoes") else None,
               "url_coleta": guardado.get("url_coleta"), "quebras": list(s.quebras)}
        if s.ibge_produto:
            # Releases do IBGE sobre o indicador, como a Agência de Notícias os publicou (ADR-033, adendo)
            releases = estado_dados.get("releases", {}).get(str(s.ibge_produto)) or {}
            doc["releases"] = {"fonte": "IBGE, Agência de Notícias", "coletado_em": releases.get("coletado_em"),
                               "itens": releases.get("itens", [])}
        indicadores[s.id] = _publicado(doc, valores[s.id])
    contas = {
        "ipca_12m": lambda: acumulado(valores["ipca"], 12),
        "ipca_ano": lambda: no_ano(valores["ipca"]),
        "inpc_12m": lambda: acumulado(valores["inpc"], 12),
        "selic_12m": lambda: acumulado(valores["selic_mes"], 12),
        "juro_real_12m": lambda: juro_real(acumulado(valores["selic_mes"], 12), acumulado(valores["ipca"], 12)),
        "juros_nominais_12m": lambda: diferenca(valores["nominal_12m"], valores["primario_12m"]),
    }
    for d in DERIVADOS:
        coletado = [coletas[u] for u in d.usa]
        doc = {**_documentacao(d), "derivado_de": list(d.usa), "fonte": FONTE_SGS,
               "coletado_em": min(coletado) if all(coletado) else None}
        if len(d.usa) == 1 and "releases" in indicadores[d.usa[0]]:
            # Conta sobre uma série só (IPCA em 12 meses, no ano): os releases do IBGE são os dela
            doc["releases"] = indicadores[d.usa[0]]["releases"]
        indicadores[d.id] = _publicado(doc, contas[d.id]())
    grupos = [{"id": g, "nome": nome, "indicadores": [i for i, v in indicadores.items() if v["grupo"] == g]}
              for g, nome in GRUPOS]
    return {"versao": VERSAO_FEED, "tipo": "economia",
            "gerado_em": (agora or datetime.now(timezone.utc)).isoformat(timespec="seconds"),
            "grupos": grupos, "indicadores": indicadores}


def publicar(estado: Path | str, saida: Path | str, *, agora: datetime | None = None) -> dict:
    """Grava ``economia/indicadores.json`` em ``saida`` e devolve um resumo (indicadores e último período)."""
    feed = montar(ler_estado(estado), agora=agora)
    gravar_json(Path(saida) / ARQUIVO_FEED, feed)
    return {"arquivo": str(Path(saida) / ARQUIVO_FEED),
            "indicadores": {k: (v["ultimo"] or {}).get("periodo") for k, v in feed["indicadores"].items()}}
