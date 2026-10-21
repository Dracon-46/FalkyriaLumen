"""Contratos dos órgãos pernambucanos registrados no Tribunal de Contas do Estado, pela API de dados abertos (ADR-050).

O TCE-PE publica, sem chave, uma API (``sistemas.tce.pe.gov.br/DadosAbertos/<Método>!json``) que devolve até 100 mil
registros por consulta, em ISO-8859-1:

- ``Contratos?AnoContrato=AAAA``: os contratos estaduais e municipais do ano (perto de 36 mil em 2022, 31 MB), com a
  unidade gestora, o município dela, a esfera (``M`` ou ``E``), o documento do contratado (o CPF já vem mascarado
  pelo tribunal), o valor e a situação;
- ``TermoAditivo?AnoContrato=AAAA``: os aditivos dos contratos do ano, com o valor de cada termo;
- ``Municipios``: o nome e o código IBGE de cada município, para ligar o nome do contrato ao ente.

Desde 2013 (antes, poucos registros). Os municipais vão para o município; os estaduais, para o estado. A unidade
gestora com "consórcio" no nome fica sem ente. Quem não tem CNPJ válido entra na soma anônima de pessoa física (o
tribunal publica o nome, e o Lumen não guarda).

A API não tem cabeçalho barato que diga se o ano mudou: um ano fechado é relido a cada ``DIAS_ANO_FECHADO`` dias e o
corrente e o anterior, uma vez por semana (``tce.precisa_ler_por_idade``). Consulta que chega ao limite de registros
vai para os ``problemas`` da coleta, porque estaria cortada. O estado (``tce-pe.json.gz``) segue o formato comum de
``tce``.
"""

from __future__ import annotations

import json
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable

from lumen_canonico.documentos import cnpj_valido, mascarar_cpfs_no_texto

from . import tce
from .cadastro import Cadastro
from .comum import gravar_json, instante_utc, sem_acento, tipo_do_ente
from .contratacoes import teto_do_ente

TRIBUNAL = "TCE-PE"
SISTEMA = "LICON e Remessa TCE-PE"
FONTE = "Tribunal de Contas do Estado de Pernambuco, API de dados abertos (sistemas.tce.pe.gov.br/DadosAbertos)"
URL_API = "https://sistemas.tce.pe.gov.br/DadosAbertos/{metodo}!json"
ARQUIVO = "tce-pe.json.gz"
PRIMEIRO_ANO = 2013
UF = "PE"
ESTADO_PE = "26"


def consultar(metodo: str, *, contato: str, baixar_fn: Callable[..., bytes | None] = tce.baixar,
              **filtros: str) -> tuple[list[dict], bool]:
    """Os registros de um método da API e se a consulta chegou ao limite (resposta cortada)."""
    consulta = "&".join(f"{k}={v}" for k, v in filtros.items())
    url = URL_API.format(metodo=metodo) + (f"?{consulta}" if consulta else "")
    bruto = baixar_fn(url, contato=contato)
    resposta = json.loads(bruto.decode("latin-1"))["resposta"] if bruto else {}
    if resposta.get("status") not in (None, "OK"):
        raise ValueError(f"{url}: {resposta.get('status')}")
    conteudo = resposta.get("conteudo") or []
    limite = int(resposta.get("limiteResultado") or 0)
    return conteudo, bool(limite) and int(resposta.get("tamanhoResultado") or 0) >= limite


def municipios(registros: list[dict]) -> dict[str, str]:
    """O nome de cada município de Pernambuco (sem acento, maiúsculo) → código IBGE."""
    return {sem_acento(m.get("MUNICIPIO") or "").upper().strip(): m["CODIGOIBGE"]
            for m in registros if m.get("UNIDADEFEDERATIVA") == UF and tipo_do_ente(m.get("CODIGOIBGE")) == "municipio"}


def _valor(texto: str | None) -> float | None:
    """``"7200.00"`` → 7200.0; vazio ou fora do formato → ``None``."""
    try:
        return float(texto) if texto not in (None, "") else None
    except ValueError:
        return None


def ente_do_contrato(registro: dict, por_nome: dict[str, str]) -> str | None:
    """O ente do contrato: o estado para a esfera estadual; o município (pelo nome) para a municipal; nenhum para
    consórcio ou município que não se acha."""
    if "CONSORCIO" in sem_acento(registro.get("UnidadeGestora") or "").upper():
        return None
    esfera = (registro.get("Esfera") or "").strip()
    if esfera == "E":
        return ESTADO_PE
    if esfera == "M":
        return por_nome.get(sem_acento(registro.get("Municipio") or "").upper().strip())
    return None


def somar_ano(contratos: list[dict], aditivos: list[dict], por_nome: dict[str, str], teto: Callable[[str], float],
              nomes: dict[str, str]) -> dict:
    """A soma de um ano (``tce.SomaAno``), com os nomes das empresas guardados em ``nomes``."""
    soma = tce.SomaAno(teto)
    ente_por_contrato: dict[str, str | None] = {}
    for c in contratos:
        ente = ente_do_contrato(c, por_nome)
        ente_por_contrato[str(c.get("CodigoContrato"))] = ente
        documento = "".join(d for d in (c.get("CPF_CNPJ") or "") if d.isdigit())
        cnpj = documento if c.get("TipoDocumento") == "CNPJ" and cnpj_valido(documento) else None
        soma.contrato(ente, _valor(c.get("Valor")), cnpj=cnpj)
        if cnpj and c.get("RazaoSocial"):
            nomes[cnpj] = mascarar_cpfs_no_texto(c["RazaoSocial"].strip())
    for a in aditivos:
        codigo = str(a.get("CodigoContrato"))
        ente = ente_por_contrato[codigo] if codigo in ente_por_contrato else ente_do_contrato(a, por_nome)
        soma.aditivo(ente, _valor(a.get("ValorTermoAditivo")) or 0.0)
    return soma.para_json()


def coletar(estado: Path | str, cadastro: Cadastro, *, contato: str, hoje: date | None = None,
            anos: list[int] | None = None, limite_minutos: float | None = None,
            baixar_fn: Callable[..., bytes | None] = tce.baixar,
            relogio: Callable[[], float] = time.monotonic) -> tce.ResultadoTce:
    """Lê os anos que passaram da idade de releitura (ou os pedidos) e grava ``ARQUIVO`` depois de cada um."""
    hoje = hoje or datetime.now(timezone.utc).date()
    caminho = Path(estado) / ARQUIVO
    dados = tce.ler_estado(caminho, tribunal=TRIBUNAL, sistema=SISTEMA, fonte=FONTE, primeiro_ano=PRIMEIRO_ANO)
    teto = lambda ente: teto_do_ente(ente, cadastro)  # noqa: E731
    resultado = tce.ResultadoTce(TRIBUNAL)
    prazo = relogio() + limite_minutos * 60 if limite_minutos else None
    por_nome: dict[str, str] | None = None
    for ano in anos or range(PRIMEIRO_ANO, hoje.year + 1):
        if prazo is not None and relogio() >= prazo:
            resultado.interrompida = True
            break
        if not anos and not tce.precisa_ler_por_idade(dados["anos"].get(str(ano)), ano, hoje):
            resultado.pulados.append(ano)
            continue
        if por_nome is None:
            por_nome = municipios(consultar("Municipios", contato=contato, baixar_fn=baixar_fn)[0])
        contratos, cortada = consultar("Contratos", contato=contato, baixar_fn=baixar_fn, AnoContrato=str(ano))
        aditivos, cortada_ad = consultar("TermoAditivo", contato=contato, baixar_fn=baixar_fn, AnoContrato=str(ano))
        if cortada or cortada_ad:
            resultado.problemas.append(f"{ano}: a consulta chegou ao limite de registros da API e veio cortada")
            continue
        if not contratos:
            resultado.ausentes.append(ano)
            continue
        nomes: dict[str, str] = {}
        dados["anos"][str(ano)] = {"tamanho": len(contratos), "etiqueta": f"{len(contratos)}/{len(aditivos)}",
                                   "lido_em": instante_utc(), **somar_ano(contratos, aditivos, por_nome, teto, nomes)}
        resultado.nomes += sum(1 for c in nomes if c not in dados["nomes"])
        dados["nomes"].update(nomes)
        resultado.lidos.append(ano)
        Path(estado).mkdir(parents=True, exist_ok=True)
        gravar_json(caminho, {**dados, "coletado_em": instante_utc()}, comprimir=True)
    return resultado
