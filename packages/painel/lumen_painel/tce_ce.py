"""Contratos dos municípios cearenses registrados no Tribunal de Contas do Estado, pela API do SIM (ADR-050).

O TCE-CE publica, sem chave, a API de dados abertos do SIM (``api-dados-abertos.tce.ce.gov.br/sim/<método>``), que
só responde a endereços do Brasil (no GitHub, os pedidos passam pelo intermediário em São Paulo, ``tce.abrir``). Toda
consulta pede o município (o código de três dígitos do tribunal) e o período, em ``AAAAMMDD``, e devolve até 1.000
registros por página (``$start_index``):

- ``municipios``: o código do tribunal e o código IBGE de cada município;
- ``contratos``: os contratos e os termos do município celebrados no período, com a modalidade (``OR``, o original;
  ``AA``, ``AP``, ``AR`` e ``RE``, os aditivos), o número do contrato original e o valor;
- ``contratados``: quem assinou cada contrato (pela data e pelo número), com o documento: o CNPJ, ou o CPF já cifrado
  pelo tribunal.

Desde 2003, só municípios (o SIM não traz o estado nem consórcios). O contrato com um só contratado de CNPJ válido vai
para a empresa; com contratados só pessoa física, para a soma anônima; com vários contratados de CNPJ (um instrumento
com dezenas de credenciados, por exemplo) ou nenhum registrado, só para o total do município, porque o tribunal não
diz a parte de cada um. Os aditivos são os assinados no ano, de contratos de qualquer ano, como no TCE-PR, e contam
sem valor: o valor do termo é o acréscimo em uns municípios e o valor do contrato depois do termo em outros (em
Fortaleza, em 2023, um termo que só troca o CNPJ da contratada vem com os R$ 80 milhões do contrato, e a redução vem
negativa; em Abaiara, positiva). Somá-los daria acréscimos que não houve.

Um ano pede ao menos duas consultas por município (184), e Fortaleza passa de 7 mil contratos: os municípios são lidos
``PEDIDOS_SIMULTANEOS`` de cada vez. Como no TCE-PE, a API não diz se o ano mudou, e a idade da leitura decide
(``tce.precisa_ler_por_idade``). Ano com algum município que falhou não é gravado: ficaria menor do que é. O estado
(``tce-ce.json.gz``) segue o formato comum de ``tce``.
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable

from lumen_canonico.documentos import cnpj_valido, mascarar_cpfs_no_texto

from . import tce
from .cadastro import Cadastro
from .comum import gravar_json, instante_utc
from .contratacoes import teto_do_ente

TRIBUNAL = "TCE-CE"
SISTEMA = "SIM (Sistema de Informações Municipais)"
FONTE = "Tribunal de Contas do Estado do Ceará, API de dados abertos do SIM (api-dados-abertos.tce.ce.gov.br/sim)"
URL_API = "https://api-dados-abertos.tce.ce.gov.br/sim/{metodo}"
ARQUIVO = "tce-ce.json.gz"
PRIMEIRO_ANO = 2003
POR_PAGINA = 1000
PEDIDOS_SIMULTANEOS = 4
ORIGINAL = "OR"
CNPJ = "1"


def consultar(metodo: str, *, contato: str, baixar_fn: Callable[..., bytes | None] = tce.baixar,
              **filtros: str) -> list[dict]:
    """Todos os registros de um método da API, página a página."""
    base = URL_API.format(metodo=metodo) + "?" + "&".join(f"{k}={v}" for k, v in filtros.items())
    registros: list[dict] = []
    while True:
        url = f"{base}{'&' if filtros else ''}$start_index={len(registros)}"
        bruto = baixar_fn(url, contato=contato)
        resposta = json.loads(bruto.decode("utf-8")) if bruto else {}
        if resposta.get("__errors__"):
            raise ValueError(f"{url}: {resposta['__errors__'][0].get('message', '')[:200]}")
        pagina = resposta.get("elements") or []
        registros += pagina
        if len(pagina) < POR_PAGINA:
            return registros


def municipios(registros: list[dict]) -> dict[str, str]:
    """O código do município no tribunal (``"057"``) → código IBGE; fica de fora o que não tem IBGE (o próprio
    tribunal)."""
    return {m["codigo_municipio"]: m["codigo_municipio_ibge"] for m in registros if m.get("codigo_municipio_ibge")}


def ler_municipio(codigo: str, ano: int, *, contato: str,
                  baixar_fn: Callable[..., bytes | None] = tce.baixar) -> tuple[list[dict], list[dict]]:
    """Os contratos e os contratados do município (código do tribunal) celebrados no ano."""
    filtros = {"codigo_municipio": codigo, "data_inicio": f"{ano}0101", "data_fim": f"{ano}1231"}
    return (consultar("contratos", contato=contato, baixar_fn=baixar_fn, **filtros),
            consultar("contratados", contato=contato, baixar_fn=baixar_fn, **filtros))


def _chave(registro: dict) -> tuple[str, str]:
    """O contrato pela data e pelo número, que é como o contratado se liga a ele."""
    return (registro.get("data_contrato") or "")[:10], (registro.get("numero_contrato") or "").strip()


def somar_ano(por_municipio: dict[str, tuple[list[dict], list[dict]]], teto: Callable[[str], float],
              nomes: dict[str, str]) -> dict:
    """A soma de um ano (``tce.SomaAno``), a partir dos contratos e dos contratados de cada município (código IBGE),
    com os nomes das empresas guardados em ``nomes``."""
    soma = tce.SomaAno(teto)
    for ente, (contratos, contratados) in sorted(por_municipio.items()):
        quem: dict[tuple[str, str], dict[str, str | None]] = {}
        for c in contratados:
            documento = "".join(d for d in (c.get("numero_documento_negociante") or "") if d.isdigit())
            cnpj = documento if c.get("codigo_tipo_negociante") == CNPJ and cnpj_valido(documento) else None
            chave_pessoa = cnpj or f"pf:{c.get('numero_documento_negociante')}"
            quem.setdefault(_chave(c), {})[chave_pessoa] = cnpj
            if cnpj and c.get("nome_negociante"):
                nomes[cnpj] = mascarar_cpfs_no_texto(c["nome_negociante"].strip())
        for c in contratos:
            valor = c.get("valor_total_contrato")
            modalidade = (c.get("modalide_contrato") or "").strip()
            if modalidade != ORIGINAL:
                soma.aditivo(ente, None)
                continue
            pessoas = quem.get(_chave(c), {})
            cnpjs = {v for v in pessoas.values() if v}
            if len(pessoas) == 1 and cnpjs:
                soma.contrato(ente, valor, cnpj=cnpjs.pop())
            else:
                soma.contrato(ente, valor, sem_fornecedor=bool(cnpjs) or not pessoas)
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
    codigos: dict[str, str] | None = None
    for ano in anos or range(PRIMEIRO_ANO, hoje.year + 1):
        if prazo is not None and relogio() >= prazo:
            resultado.interrompida = True
            break
        if not anos and not tce.precisa_ler_por_idade(dados["anos"].get(str(ano)), ano, hoje):
            resultado.pulados.append(ano)
            continue
        if codigos is None:
            codigos = municipios(consultar("municipios", contato=contato, baixar_fn=baixar_fn))
        por_municipio: dict[str, tuple[list[dict], list[dict]]] = {}
        falhas: list[str] = []
        with ThreadPoolExecutor(PEDIDOS_SIMULTANEOS) as grupo:
            futuros = [grupo.submit(ler_municipio, c, ano, contato=contato, baixar_fn=baixar_fn) for c in sorted(codigos)]
            for (codigo, ibge), futuro in zip(sorted(codigos.items()), futuros):
                try:
                    por_municipio[ibge] = futuro.result()
                except Exception as erro:  # noqa: BLE001 — o ano inteiro fica de fora, com o motivo
                    falhas.append(f"{codigo} ({erro})")
        if falhas:
            resultado.problemas.append(f"{ano}: {len(falhas)} município(s) não responderam: {'; '.join(falhas[:3])}")
            continue
        contratos = sum(len(c) for c, _ in por_municipio.values())
        if not contratos:
            resultado.ausentes.append(ano)
            continue
        contratados = sum(len(p) for _, p in por_municipio.values())
        nomes: dict[str, str] = {}
        dados["anos"][str(ano)] = {"tamanho": contratos, "etiqueta": f"{contratos}/{contratados}",
                                   "lido_em": instante_utc(), **somar_ano(por_municipio, teto, nomes)}
        resultado.nomes += sum(1 for c in nomes if c not in dados["nomes"])
        dados["nomes"].update(nomes)
        resultado.lidos.append(ano)
        Path(estado).mkdir(parents=True, exist_ok=True)
        gravar_json(caminho, {**dados, "coletado_em": instante_utc()}, comprimir=True)
    return resultado
