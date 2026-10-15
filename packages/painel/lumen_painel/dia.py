"""Um dia do PNCP, reduzido ao que o painel de contratações usa: o estado guardado entre execuções.

A coleta de um dia (todas as modalidades de contratação e os contratos publicados naquela data) passa pelo
caminho de sempre — bronze, normalização, silver — num diretório temporário, e sai daqui como um arquivo
compacto, ``contratacoes-AAAA-MM-DD.json.gz``, com uma linha por processo e por contrato e só as colunas que
o painel soma ou mostra. O bronze do dia é descartado: a prova de cada número é a própria página do PNCP,
que o painel liga (``link_pncp``), e a coleta pode ser refeita a qualquer momento.

O arquivo do dia é público (fica nos anexos de uma versão do GitHub, ADR-028). Por isso, contrato com pessoa
física ou estrangeira guarda só o tipo de pessoa, o valor e as datas: nem nome nem documento do fornecedor
(RNF-19 e RNF-20). Pessoa jurídica guarda CNPJ e razão social, que são públicos.

Um dia só é gravado quando a coleta terminou sem falha nem resposta de erro: um dia incompleto somaria menos
do que o ente publicou. Ele fica de fora e é tentado de novo na execução seguinte.
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass, field, replace
from datetime import date
from pathlib import Path

from lumen_ingestao.adaptadores.api.pncp import MODALIDADES_PNCP
from lumen_ingestao.coleta_http import ErroColeta
from lumen_ingestao.portas import Janela
from lumen_normalizacao.silver import consolidar, ler_entidade

from .comum import gravar_json, instante_utc, ler_json, valor

COLUNAS_PROCESSOS = ["chave", "orgao", "ente", "uf", "municipio", "modalidade", "valor_estimado",
                     "valor_homologado", "objeto", "situacao", "srp"]
COLUNAS_CONTRATOS = ["chave", "orgao", "ente", "uf", "municipio", "tipo_pessoa", "fornecedor_cnpj",
                     "fornecedor_nome", "valor_global", "data_assinatura", "processo", "instrumento", "objeto"]
COLUNAS_ORGAOS = ["razao_social", "esfera", "ente"]
LIMITE_OBJETO = 240
FONTES = ("pncp_contratacoes", "pncp_contratos")
ESFERAS = {"uniao": "F", "estadual": "E", "municipal": "M", "distrital": "D"}


def nome_do_arquivo(dia: date) -> str:
    """``contratacoes-2026-10-13.json.gz``."""
    return f"contratacoes-{dia.isoformat()}.json.gz"


def dias_guardados(estado: Path | str) -> set[date]:
    """As datas que já têm arquivo no diretório do estado."""
    saida = set()
    for p in Path(estado).glob("contratacoes-*.json.gz"):
        try:
            saida.add(date.fromisoformat(p.name[len("contratacoes-"):-len(".json.gz")]))
        except ValueError:
            continue
    return saida


def _texto(bruto, limite: int = LIMITE_OBJETO) -> str | None:
    """Texto sem espaços repetidos, cortado em ``limite`` caracteres (com reticências quando cortado)."""
    if not bruto:
        return None
    texto = " ".join(str(bruto).split())
    return texto if len(texto) <= limite else texto[: limite - 1].rstrip() + "…"


def resumir_dia(silver: Path | str, dia: date, *, agora: str | None = None) -> dict:
    """Processos e contratos publicados em ``dia`` na silver, na forma compacta do estado do painel.

    O ente de cada linha é o do órgão que publicou (``Orgao.ente_codigo_ibge``, resolvido pela esfera na
    normalização); órgão sem esfera informada fica com ente nulo e só entra no panorama nacional. Contrato vale
    pelo dia de publicação no PNCP (o mesmo filtro da consulta), no horário de Brasília.
    """
    iso = dia.isoformat()
    orgaos_silver = {o["cnpj"]: o for o in consolidar(ler_entidade(silver, "orgao"))}
    usados: set[str] = set()
    processos = []
    for p in consolidar(ler_entidade(silver, "processo_contratacao")):
        if p.get("data_publicacao") != iso:
            continue
        orgao = orgaos_silver.get(p.get("orgao_cnpj") or "", {})
        usados.add(p.get("orgao_cnpj"))
        processos.append([
            p.get("chave_origem"), p.get("orgao_cnpj"), orgao.get("ente_codigo_ibge"), p.get("uf"),
            p.get("municipio_codigo_ibge"), p.get("modalidade_codigo_origem"), valor(p.get("valor_estimado")),
            valor(p.get("valor_homologado")), _texto(p.get("objeto")), p.get("situacao"), p.get("srp"),
        ])
    contratos = []
    for c in consolidar(ler_entidade(silver, "contrato")):
        if str(c.get("publicado_em") or "")[:10] != iso:
            continue
        orgao = orgaos_silver.get(c.get("orgao_cnpj") or "", {})
        usados.add(c.get("orgao_cnpj"))
        tipo = c.get("fornecedor_tipo_pessoa")
        juridica = tipo == "PJ" and len(str(c.get("fornecedor_documento") or "")) == 14
        contratos.append([
            c.get("chave_origem"), c.get("orgao_cnpj"), orgao.get("ente_codigo_ibge"), c.get("uf"),
            c.get("municipio_codigo_ibge"), tipo,
            c.get("fornecedor_documento") if juridica else None,
            _texto(c.get("fornecedor_nome"), 160) if juridica else None,
            valor(c.get("valor_global")), c.get("data_assinatura"), c.get("processo_chave_origem"),
            c.get("tipo_instrumento"), _texto(c.get("objeto"), 160),
        ])
    processos.sort(key=lambda x: x[0] or "")
    contratos.sort(key=lambda x: x[0] or "")
    orgaos = {cnpj: [orgaos_silver[cnpj].get("razao_social"), ESFERAS.get(orgaos_silver[cnpj].get("esfera") or ""),
                     orgaos_silver[cnpj].get("ente_codigo_ibge")]
              for cnpj in sorted(c for c in usados if c in orgaos_silver)}
    return {
        "versao": 1, "dia": iso, "gerado_em": agora or instante_utc(),
        "fonte": "PNCP, /v1/contratacoes/publicacao (todas as modalidades) e /v1/contratos, pela data de publicação",
        "colunas": {"processos": COLUNAS_PROCESSOS, "contratos": COLUNAS_CONTRATOS, "orgaos": COLUNAS_ORGAOS},
        "orgaos": orgaos, "processos": processos, "contratos": contratos,
    }


def ler_dia(caminho: Path | str) -> dict:
    """Lê um arquivo do dia e confere a versão; as linhas continuam listas, na ordem de ``colunas``."""
    dados = ler_json(caminho)
    if dados.get("versao") != 1:
        raise ValueError(f"{caminho}: versão {dados.get('versao')!r} do arquivo do dia não suportada")
    return dados


@dataclass
class ResultadoDia:
    """O que aconteceu na coleta de um dia: gravado ou não, contagens e o motivo de não ter gravado."""

    dia: date
    gravado: bool = False
    processos: int = 0
    contratos: int = 0
    paginas: int = 0
    problemas: list[str] = field(default_factory=list)

    def para_json(self) -> dict:
        """Resumo do dia para a saída do comando."""
        return {"dia": self.dia.isoformat(), "gravado": self.gravado, "processos": self.processos,
                "contratos": self.contratos, "paginas": self.paginas, "problemas": self.problemas}


def coletar_dia(cfg, dia: date, estado: Path | str, *, coletar=None, normalizar=None,
                modalidades: tuple[int, ...] = MODALIDADES_PNCP, temporario: Path | None = None) -> ResultadoDia:
    """Coleta, normaliza e reduz um dia do PNCP; grava ``contratacoes-<dia>.json.gz`` em ``estado`` se completo.

    ``cfg`` é a ``Configuracao`` do pipeline; o bronze e a silver do dia ficam num diretório temporário,
    apagado no fim. ``coletar`` e ``normalizar`` são as funções de ``lumen_orquestracao.etapas`` (injetáveis
    nos testes).
    """
    if coletar is None or normalizar is None:
        from lumen_orquestracao import etapas
        coletar = coletar or etapas.coletar
        normalizar = normalizar or etapas.normalizar
    resultado = ResultadoDia(dia)
    raiz = Path(tempfile.mkdtemp(prefix=f"painel-{dia.isoformat()}-", dir=temporario))
    try:
        cfg_dia = replace(cfg, raiz_dados=raiz)
        janela = Janela(dia, dia)
        for fonte, opcoes in (("pncp_contratacoes", {"modalidades": tuple(modalidades)}), ("pncp_contratos", {})):
            try:
                r = coletar(cfg_dia, fonte, janela, **opcoes)
            except ErroColeta as erro:
                resultado.problemas.append(f"{fonte}: coleta interrompida ({type(erro).__name__}: {erro})")
                continue
            resultado.paginas += len(r.guardados)
            if r.falhas:
                resultado.problemas.append(f"{fonte}: {len(r.falhas)} página(s) com falha")
            if r.respostas_de_erro:
                resultado.problemas.append(f"{fonte}: {r.respostas_de_erro} resposta(s) de erro da fonte")
        if resultado.problemas:
            return resultado
        normalizar(cfg_dia, list(FONTES))
        resumo = resumir_dia(cfg_dia.silver, dia)
        resultado.processos, resultado.contratos = len(resumo["processos"]), len(resumo["contratos"])
        gravar_json(Path(estado) / nome_do_arquivo(dia), resumo, comprimir=True)
        resultado.gravado = True
        return resultado
    finally:
        shutil.rmtree(raiz, ignore_errors=True)
