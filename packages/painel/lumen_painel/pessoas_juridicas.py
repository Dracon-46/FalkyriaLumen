"""Tudo o que o Lumen tem de uma pessoa jurídica, pelo CNPJ: a visão 360 da empresa ou entidade (ADR-049).

As contratações, as emendas e os convênios são publicados por ente (quem contrata ou recebe). Aqui, o mesmo dado
é virado para o CNPJ, em ``pj/<grupo>.json.gz`` (comprimido; o grupo é ``comum.grupo_do_cnpj``):

- **contratos:** os contratos publicados no PNCP com ela como fornecedora, por ente contratante e ano
  (``[ente, ano, contratos, valor]``), da mesma soma do painel de contratações;
- **emendas:** o recebido de emendas parlamentares como favorecida, por ente e ano (``[ente, ano, valor]``,
  ADR-044);
- **convenios:** os convênios com a União como convenente (ADR-045), com o objeto cortado em ``OBJETO``
  caracteres;
- **tce:** os contratos registrados nos tribunais de contas (TCE-RS, TCE-PR e TCE-PE, ADR-050), por ente e ano do
  contrato (``[ente, ano, contratos, valor]``).

O nome é o mais recente das contratações e, sem elas, o dos convênios, das emendas ou do tribunal de contas; as fontes já chegam com o
CPF do MEI mascarado (ADR-043). A página do portal junta o cartão da Receita (``cnpj/``). Pessoa física não
entra: o índice é por CNPJ.

A busca pelo nome lê ``pj/busca/<prefixo>.json.gz``: cada palavra do nome com três letras ou mais (fora as de
``PALAVRAS_FORA``) põe o CNPJ no arquivo das duas primeiras letras dela, com o nome e o peso (a soma dos contratos,
das emendas e dos convênios), do maior peso ao menor. O arquivo de duas letras com mais de ``LIMITE_BUSCA`` nomes
("co", de comércio e construções) se divide pelas três primeiras. ``pj/busca/indice.json`` diz quais se dividiram
e quantos nomes tem cada arquivo, para o portal ler o menor entre as palavras procuradas. A normalização é a mesma
do portal (``busca.ts``).
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any, Callable

from . import convenios, emendas, tce
from .comum import grupo_do_cnpj, ler_json
from .contratacoes import Painel

OBJETO = 160
COLUNAS_CONVENIO = ["ente", "numero", "situacao", "objeto", "orgao", "valor", "liberado", "inicio"]
# Palavras comuns demais nos nomes para separar uma empresa da outra (a busca as ignora)
PALAVRAS_FORA = frozenset({"ltda", "eireli", "epp", "cia", "dos", "das", "del", "para", "com"})
LIMITE_BUSCA = 10_000


def normalizar(texto: str) -> str:
    """Sem acento, minúsculas, só letras, dígitos e espaço único, como ``normalizar`` do portal."""
    sem_marca = "".join(c for c in unicodedata.normalize("NFD", texto) if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", sem_marca.lower())).strip()


def palavras_da_busca(nome: str | None) -> list[str]:
    """As palavras do nome que a busca usa: três letras ou mais, fora as de ``PALAVRAS_FORA``."""
    return [p for p in normalizar(nome or "").split(" ") if len(p) >= 3 and p not in PALAVRAS_FORA]


def _registro(indice: dict[str, dict], cnpj: str) -> dict:
    """O registro do CNPJ no índice, criado vazio na primeira vez."""
    return indice.setdefault(cnpj, {"nome": None, "contratos": {}, "emendas": {}, "convenios": [], "tce": {}})


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


def montar_busca(indice: dict[str, dict]) -> tuple[dict[str, list], list[str]]:
    """Os arquivos da busca pelo nome (``{prefixo: [[CNPJ, nome, peso], ...]}``, do maior peso ao menor) e os
    prefixos de duas letras divididos pelas três primeiras, por passarem de ``LIMITE_BUSCA`` nomes."""
    busca: dict[str, list] = {}
    for cnpj, registro in indice.items():
        peso = round(sum(v for _, v in registro["contratos"].values()) + sum(registro["emendas"].values())
                     + sum(c[5] for c in registro["convenios"]) + sum(v for _, v in registro["tce"].values()), 2)
        palavras = palavras_da_busca(registro["nome"])
        for prefixo in sorted({p[:2] for p in palavras}):
            busca.setdefault(prefixo, []).append((cnpj, registro["nome"], peso, palavras))
    divididos = sorted(p for p, pessoas in busca.items() if len(pessoas) > LIMITE_BUSCA)
    for curto in divididos:
        for pessoa in busca.pop(curto):
            for prefixo in sorted({p[:3] for p in pessoa[3] if p.startswith(curto)}):
                busca.setdefault(prefixo, []).append(pessoa)
    return ({prefixo: [list(p[:3]) for p in sorted(pessoas, key=lambda x: (-x[2], x[0]))]
             for prefixo, pessoas in busca.items()}, divididos)


def de_tce(indice: dict[str, dict], dados: dict) -> None:
    """Os contratos de cada empresa registrados num tribunal de contas, por ente e ano (um estado de ``tce``)."""
    nomes = dados.get("nomes") or {}
    for ano, a in (dados.get("anos") or {}).items():
        for ente, fornecedores in a["fornecedores"].items():
            for cnpj, (n, valor) in fornecedores.items():
                r = _registro(indice, cnpj)
                r["nome"] = r["nome"] or nomes.get(cnpj)
                r["tce"][(ente, ano)] = [n, valor]


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
        "tce": [[ente, ano, n, round(v, 2)] for (ente, ano), (n, v) in sorted(registro["tce"].items())],
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
    estados_tce = tce.estados(estado)
    for dados_tce in estados_tce:
        de_tce(indice, dados_tce)
    grupos: dict[str, dict[str, dict]] = {}
    for cnpj, registro in indice.items():
        grupos.setdefault(grupo_do_cnpj(cnpj), {})[cnpj] = para_json(registro)
    busca, divididos = montar_busca(indice)
    for prefixo, pessoas in sorted(busca.items()):
        gravar(f"pj/busca/{prefixo}.json.gz", {
            "versao": 1, "tipo": "pj-busca", "gerado_em": gerado_em, "prefixo": prefixo,
            "colunas": ["cnpj", "nome", "peso"], "pessoas": pessoas,
        })
    gravar("pj/busca/indice.json", {"versao": 1, "tipo": "pj-busca-indice", "gerado_em": gerado_em,
                                    "divididos": divididos, "arquivos": {p: len(v) for p, v in sorted(busca.items())}})
    for grupo, pessoas in sorted(grupos.items()):
        gravar(f"pj/{grupo}.json.gz", {
            "versao": 1, "tipo": "pessoas-juridicas", "gerado_em": gerado_em,
            "colunas": {"contratos": ["ente", "ano", "contratos", "valor"], "emendas": ["ente", "ano", "valor"],
                        "convenios": COLUNAS_CONVENIO, "tce": ["ente", "ano", "contratos", "valor"]},
            "fontes": {"emendas": (dados_emendas or {}).get("data_arquivo"),
                       "convenios": (dados_convenios or {}).get("data_arquivo"),
                       "tce": {d["tribunal"]: d.get("coletado_em") for d in estados_tce} or None},
            "pessoas": dict(sorted(pessoas.items())),
        })
    return {"pessoas": len(indice), "arquivos": len(grupos), "arquivos_busca": len(busca),
            "com_contratos": sum(1 for r in indice.values() if r["contratos"]),
            "com_emendas": sum(1 for r in indice.values() if r["emendas"]),
            "com_convenios": sum(1 for r in indice.values() if r["convenios"]),
            "com_tce": sum(1 for r in indice.values() if r["tce"])}
