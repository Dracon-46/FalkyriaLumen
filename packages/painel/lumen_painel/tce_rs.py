"""Contratos dos órgãos gaúchos registrados no Tribunal de Contas do Estado, pelo LicitaCon (ADR-050).

O TCE-RS publica, sem chave, um ZIP por ano de contrato (``dados/licitacon/contrato/ano/AAAA.csv.zip``) com os
contratos de todos os órgãos que fiscaliza, estaduais e municipais, desde 2016 de forma completa (antes disso, só
os que ainda vigiam quando o LicitaCon começou). Cada ZIP repete a tabela inteira de pessoas (perto de 80 MB), e
os contratos do ano são poucos MB. Por isso o ZIP é lido no servidor, por partes (``tce.ArquivoRemoto``): só o
``contrato.csv`` e o ``alteracao.csv`` de cada ano, e o ``pessoas.csv`` uma vez, para os nomes das empresas.

O órgão vira ente pela tabela de órgãos auditados (``orgaos_auditados_rs.csv``): os municipais vão para o
município (código IBGE) e os estaduais para o estado. Consórcios e associações ficam sem ente. Os aditivos
(``alteracao.csv``) são os dos contratos do ano, com o acréscimo menos a redução. O estado (``tce-rs.json.gz``)
segue o formato comum de ``tce``.
"""

from __future__ import annotations

import csv
import io
import time
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

from lumen_canonico.documentos import mascarar_cpfs_no_texto

from . import tce
from .cadastro import Cadastro
from .comum import gravar_json, instante_utc, tipo_do_ente
from .contratacoes import teto_do_ente

TRIBUNAL = "TCE-RS"
SISTEMA = "LicitaCon"
FONTE = "Tribunal de Contas do Estado do Rio Grande do Sul, dados abertos do LicitaCon (dados.tce.rs.gov.br)"
URL_ANO = "https://dados.tce.rs.gov.br/dados/licitacon/contrato/ano/{ano}.csv.zip"
URL_ORGAOS = "https://dados.tce.rs.gov.br/dados/auxiliar/orgaos_auditados_rs.csv"
ARQUIVO = "tce-rs.json.gz"
PRIMEIRO_ANO = 2016
ESTADO_RS = "43"
SETORES_SEM_ENTE = frozenset({"CONSÓRCIO ADMINISTRATIVO", "ASSOCIAÇÃO"})


@dataclass(frozen=True)
class Orgao:
    """Um órgão auditado: o ente a que pertence (``None`` para consórcio, associação e órgão sem município)."""

    ente: str | None
    nome: str


def ler_orgaos(texto: str) -> dict[str, Orgao]:
    """A tabela de órgãos auditados: municipais no município (código IBGE), estaduais no estado."""
    saida = {}
    for linha in csv.DictReader(io.StringIO(texto.lstrip("﻿"))):
        esfera, setor = linha.get("ESFERA"), (linha.get("SETOR_GOVERNAMENTAL") or "").strip()
        ente = None
        if esfera == "ESTADUAL":
            ente = ESTADO_RS
        elif esfera == "MUNICIPAL" and setor not in SETORES_SEM_ENTE:
            codigo = (linha.get("CD_MUNICIPIO_IBGE") or "").strip()
            ente = codigo if tipo_do_ente(codigo) == "municipio" else None
        saida[linha["CD_ORGAO"]] = Orgao(ente, linha.get("NOME_ORGAO") or "")
    return saida


def _valor(texto: str | None) -> float | None:
    """``"1450.04"`` → 1450.04; vazio ou fora do formato → ``None``."""
    try:
        return float(texto) if texto not in (None, "") else None
    except ValueError:
        return None


def _chave(linha: dict) -> tuple:
    """O contrato: órgão, licitação (número, ano e modalidade), contrato (número e ano) e instrumento."""
    return tuple(linha.get(c) for c in ("CD_ORGAO", "NR_LICITACAO", "ANO_LICITACAO", "CD_TIPO_MODALIDADE",
                                        "NR_CONTRATO", "ANO_CONTRATO", "TP_INSTRUMENTO"))


def _csv(z: zipfile.ZipFile, nome: str):
    """As linhas de um CSV do ZIP, como dicionários, lidas em fluxo."""
    return csv.DictReader(io.TextIOWrapper(z.open(nome), encoding="utf-8-sig", newline=""))


def _digitos(texto: str | None) -> str:
    """Só os dígitos do documento."""
    return "".join(d for d in (texto or "") if d.isdigit())


def ler_ano(z: zipfile.ZipFile, orgaos: dict[str, Orgao], teto: Callable[[str], float]) -> dict:
    """Os contratos de um ano (``tce.SomaAno``). ``teto(ente)`` é o valor acima do qual o contrato conta e não
    soma; o contrato com pessoa física (``TP_DOCUMENTO`` F) só entra na soma anônima."""
    soma = tce.SomaAno(teto)
    if "alteracao.csv" in z.namelist():
        aditivos: dict[tuple, list] = {}
        for a in _csv(z, "alteracao.csv"):
            aditivos.setdefault(_chave(a), []).append(
                (_valor(a.get("VL_ACRESCIMO")) or 0.0) - (_valor(a.get("VL_REDUCAO")) or 0.0))
    else:
        aditivos = {}
    for c in _csv(z, "contrato.csv"):
        orgao = orgaos.get(c.get("CD_ORGAO") or "")
        ente = orgao.ente if orgao else None
        documento = _digitos(c.get("NR_DOCUMENTO"))
        cnpj = documento if c.get("TP_DOCUMENTO") == "J" and len(documento) == 14 else None
        soma.contrato(ente, _valor(c.get("VL_CONTRATO")), cnpj=cnpj)
        for valor in aditivos.get(_chave(c), []):
            soma.aditivo(ente, valor)
    return soma.para_json()


def ler_nomes(z: zipfile.ZipFile, cnpjs: set[str]) -> dict[str, str]:
    """O nome de cada CNPJ pedido, da tabela de pessoas do LicitaCon, com o CPF do MEI mascarado."""
    nomes = {}
    for p in _csv(z, "pessoas.csv"):
        if p.get("TP_DOCUMENTO") != "J":
            continue
        documento = _digitos(p.get("NR_DOCUMENTO"))
        if documento in cnpjs and p.get("NM_PESSOA"):
            nomes[documento] = mascarar_cpfs_no_texto(p["NM_PESSOA"].strip())
    return nomes


def coletar(estado: Path | str, cadastro: Cadastro, *, contato: str, hoje: date | None = None,
            anos: list[int] | None = None, limite_minutos: float | None = None,
            cabecalho_fn: Callable[..., tuple[int, str] | None] = tce.cabecalho,
            texto_fn: Callable[[str, str], str] | None = None,
            remoto_fn: Callable[..., Any] = tce.ArquivoRemoto,
            relogio: Callable[[], float] = time.monotonic) -> tce.ResultadoTce:
    """Lê os anos que mudaram e grava ``ARQUIVO`` depois de cada um; no fim, os nomes dos CNPJs novos."""
    hoje = hoje or datetime.now(timezone.utc).date()
    caminho = Path(estado) / ARQUIVO
    dados = tce.ler_estado(caminho, tribunal=TRIBUNAL, sistema=SISTEMA, fonte=FONTE, primeiro_ano=PRIMEIRO_ANO)
    texto_fn = texto_fn or (lambda url, contato: tce.baixar(url, contato=contato).decode("utf-8-sig"))
    orgaos = ler_orgaos(texto_fn(URL_ORGAOS, contato))
    teto = lambda ente: teto_do_ente(ente, cadastro)  # noqa: E731
    resultado = tce.ResultadoTce(TRIBUNAL)
    prazo = relogio() + limite_minutos * 60 if limite_minutos else None
    ultimo_zip = None
    for ano in anos or range(PRIMEIRO_ANO, hoje.year + 1):
        if prazo is not None and relogio() >= prazo:
            resultado.interrompida = True
            break
        url = URL_ANO.format(ano=ano)
        info = cabecalho_fn(url, contato=contato)
        if info is None:
            resultado.ausentes.append(ano)
            continue
        tamanho, etiqueta = info
        ultimo_zip = (url, tamanho)
        if not tce.precisa_ler(dados["anos"].get(str(ano)), tamanho, etiqueta, ano, hoje):
            resultado.pulados.append(ano)
            continue
        with zipfile.ZipFile(remoto_fn(url, tamanho, contato=contato)) as z:
            dados["anos"][str(ano)] = {"tamanho": tamanho, "etiqueta": etiqueta, "lido_em": instante_utc(),
                                       **ler_ano(z, orgaos, teto)}
        resultado.lidos.append(ano)
        Path(estado).mkdir(parents=True, exist_ok=True)
        gravar_json(caminho, {**dados, "coletado_em": instante_utc()}, comprimir=True)
    faltam = {c for a in dados["anos"].values() for fs in a["fornecedores"].values() for c in fs} - set(dados["nomes"])
    if faltam and ultimo_zip and not resultado.interrompida:
        with zipfile.ZipFile(remoto_fn(*ultimo_zip, contato=contato)) as z:
            novos = ler_nomes(z, faltam)
        dados["nomes"].update(novos)
        resultado.nomes = len(novos)
        gravar_json(caminho, {**dados, "coletado_em": instante_utc()}, comprimir=True)
    return resultado
