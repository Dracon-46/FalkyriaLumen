"""Tudo o que o Lumen tem de uma pessoa jurídica, pelo CNPJ: a visão 360 da empresa ou entidade (ADR-049).

As contratações, as emendas e os convênios são publicados por ente (quem contrata ou recebe). Aqui, o mesmo dado
é virado para o CNPJ, em ``pj/<grupo>.json.gz`` (comprimido; o grupo é ``comum.grupo_do_cnpj``):

- **contratos:** os contratos publicados no PNCP com ela como fornecedora, por ente contratante e ano
  (``[ente, ano, contratos, valor]``), da mesma soma do painel de contratações;
- **emendas:** o recebido de emendas parlamentares como favorecida, por ente e ano (``[ente, ano, valor]``,
  ADR-044);
- **convenios:** os convênios com a União como convenente (ADR-045), com o objeto cortado em ``OBJETO``
  caracteres.

O nome é o mais recente das contratações e, sem elas, o dos convênios ou das emendas; as fontes já chegam com o
CPF do MEI mascarado (ADR-043). A página do portal junta o cartão da Receita (``cnpj/``). Pessoa física não
entra: o índice é por CNPJ.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from . import convenios, emendas
from .comum import grupo_do_cnpj, ler_json
from .contratacoes import Painel

OBJETO = 160
COLUNAS_CONVENIO = ["ente", "numero", "situacao", "objeto", "orgao", "valor", "liberado", "inicio"]


def _registro(indice: dict[str, dict], cnpj: str) -> dict:
    """O registro do CNPJ no índice, criado vazio na primeira vez."""
    return indice.setdefault(cnpj, {"nome": None, "contratos": {}, "emendas": {}, "convenios": []})


def de_contratacoes(indice: dict[str, dict], painel: Painel) -> None:
    """Os contratos de cada fornecedor pessoa jurídica, por ente contratante e ano."""
    for ente, acumulador in painel.entes.items():
        for cnpj, f in acumulador.fornecedores.items():
            r = _registro(indice, cnpj)
            r["nome"] = r["nome"] or f.nome
            for mes, (n, valor) in f.meses.items():
                x = r["contratos"].setdefault((ente, mes[:4]), [0, 0.0])
                x[0] += n
                x[1] += valor


def de_emendas(indice: dict[str, dict], dados: dict) -> None:
    """O recebido de emendas por favorecido pessoa jurídica, por ente e ano (o estado de ``emendas``)."""
    colunas = dados.get("colunas_recebido") or []
    i_ano, i_cnpj, i_nome, i_valor = (colunas.index(c) for c in ("ano", "cnpj", "favorecido", "valor"))
    for ente, linhas in (dados.get("recebido") or {}).items():
        for linha in linhas:
            cnpj = linha[i_cnpj]
            if not cnpj:
                continue
            r = _registro(indice, cnpj)
            r["nome"] = r["nome"] or linha[i_nome]
            chave = (ente, linha[i_ano])
            r["emendas"][chave] = r["emendas"].get(chave, 0.0) + linha[i_valor]


def de_convenios(indice: dict[str, dict], dados: dict) -> None:
    """Os convênios por convenente pessoa jurídica (o estado de ``convenios``)."""
    colunas = dados.get("colunas") or []
    i = {c: colunas.index(c) for c in ("numero", "situacao", "objeto", "orgao", "cnpj", "convenente", "valor",
                                       "liberado", "inicio")}
    for ente, linhas in (dados.get("convenios") or {}).items():
        for linha in linhas:
            cnpj = linha[i["cnpj"]]
            if not cnpj:
                continue
            r = _registro(indice, cnpj)
            r["nome"] = r["nome"] or linha[i["convenente"]]
            r["convenios"].append([ente, linha[i["numero"]], linha[i["situacao"]], (linha[i["objeto"]] or "")[:OBJETO],
                                   linha[i["orgao"]], linha[i["valor"]], linha[i["liberado"]], linha[i["inicio"]]])


def _estado(estado: Path, modulo) -> dict | None:
    """O estado de ``emendas`` ou ``convenios``, se existe e está na versão conhecida."""
    caminho = estado / modulo.ARQUIVO
    if not caminho.exists():
        return None
    dados = ler_json(caminho)
    return dados if dados.get("versao") == modulo.VERSAO_ESTADO else None


def para_json(registro: dict) -> dict:
    """O registro de um CNPJ como vai no arquivo: listas ordenadas, valores em centavos."""
    return {
        "nome": registro["nome"],
        "contratos": [[ente, ano, n, round(v, 2)] for (ente, ano), (n, v) in sorted(registro["contratos"].items())],
        "emendas": [[ente, ano, round(v, 2)] for (ente, ano), v in sorted(registro["emendas"].items())],
        "convenios": sorted(registro["convenios"], key=lambda c: (c[7] or "", c[0], c[1])),
    }


def publicar(estado: Path | str, painel: Painel, gravar: Callable[[str, Any], Any], *, gerado_em: str) -> dict:
    """Grava ``pj/<grupo>.json.gz`` com as pessoas jurídicas do grupo e devolve o resumo para o índice."""
    estado = Path(estado)
    indice: dict[str, dict] = {}
    de_contratacoes(indice, painel)                 # o nome: o primeiro que aparecer, nesta ordem
    dados_convenios = _estado(estado, convenios)
    if dados_convenios:
        de_convenios(indice, dados_convenios)
    dados_emendas = _estado(estado, emendas)
    if dados_emendas:
        de_emendas(indice, dados_emendas)
    grupos: dict[str, dict[str, dict]] = {}
    for cnpj, registro in indice.items():
        grupos.setdefault(grupo_do_cnpj(cnpj), {})[cnpj] = para_json(registro)
    for grupo, pessoas in sorted(grupos.items()):
        gravar(f"pj/{grupo}.json.gz", {
            "versao": 1, "tipo": "pessoas-juridicas", "gerado_em": gerado_em,
            "colunas": {"contratos": ["ente", "ano", "contratos", "valor"], "emendas": ["ente", "ano", "valor"],
                        "convenios": COLUNAS_CONVENIO},
            "fontes": {"emendas": (dados_emendas or {}).get("data_arquivo"),
                       "convenios": (dados_convenios or {}).get("data_arquivo")},
            "pessoas": dict(sorted(pessoas.items())),
        })
    return {"pessoas": len(indice), "arquivos": len(grupos),
            "com_contratos": sum(1 for r in indice.values() if r["contratos"]),
            "com_emendas": sum(1 for r in indice.values() if r["emendas"]),
            "com_convenios": sum(1 for r in indice.values() if r["convenios"])}
