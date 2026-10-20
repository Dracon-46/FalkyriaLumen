"""Despesa com pessoal do Poder Executivo em % da RCL ajustada, pelo RGF (ADR-042; LRF, arts. 19, 20, 22 e 59).

A fonte é o RGF do último período do exercício anterior (3º quadrimestre ou 2º semestre), Anexo 1, do Poder
Executivo, no SICONFI. Dele saem a despesa total com pessoal (``DespesaComPessoalTotal``), o percentual sobre a
RCL ajustada e os três limites que o próprio relatório declara: o de alerta (90% do máximo), o prudencial (95%) e
o máximo (em regra, 54% para o Executivo municipal e 49% para o estadual; 48,6% no estado com tribunal de contas
dos municípios; art. 20).

A consulta precisa do tipo (RGF ou RGF Simplificado, LRF art. 63) e da periodicidade (quadrimestral ou
semestral), e quem diz os dois é o extrato de entregas que a conformidade já coletou: o RGF do Executivo no último
período. O ente sem essa entrega não é consultado e volta depois de ``DIAS_PARA_TENTAR_DE_NOVO`` dias; sem
extrato, vão as duas combinações comuns, o RGF quadrimestral primeiro e o simplificado semestral depois.

Como a RCL e a despesa por função, o estado é por UF (``pessoal-<UF>.json.gz``), e a coleta vai em lotes até o
``limite_minutos``.
"""

from __future__ import annotations

import shutil
import tempfile
import time
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from pathlib import Path

from lumen_ingestao.coleta_http import ErroColeta
from lumen_ingestao.portas import Janela
from lumen_normalizacao.silver import consolidar, ler_entidade
from lumen_normalizacao.transformacoes import chave_texto

from .cadastro import Cadastro, Ente
from .comum import gravar_json, hoje_brasilia, instante_utc, ler_json

ANEXO = "RGF-Anexo 01"
RGF, SIMPLIFICADO = "RGF", "RGF Simplificado"
ENTREGAVEIS = {"Relatório de Gestão Fiscal": RGF, "Relatório de Gestão Fiscal Simplificado": SIMPLIFICADO}
ULTIMO_PERIODO = {"Q": 3, "S": 2}
# Sem extrato: as duas combinações comuns, nesta ordem
SEM_EXTRATO = ((RGF, "Q"), (SIMPLIFICADO, "S"))
DIAS_PARA_TENTAR_DE_NOVO = 7
TAMANHO_DO_LOTE = 50
VERSAO_ESTADO = 1
# Contas do Anexo 1: a despesa total com pessoal, a RCL ajustada e os limites
CONTA_DTP = "DespesaComPessoalTotal"
CONTA_RCL_AJUSTADA = "ReceitaCorrenteLiquidaAjustada"
LIMITES = {"alerta": "LimiteDeAlertaDespesaComPessoalTotal", "prudencial": "LimitePrudencialDespesaComPessoalTotal",
           "maximo": "LimiteMaximoDespesaComPessoalTotal"}
# O Executivo no extrato, pelo nome da instituição (sem acento e sem caixa)
EXECUTIVO = {"M": ("prefeitura",), "E": ("governo", "poder executivo"), "D": ("governo", "poder executivo")}


def nome_do_arquivo(uf: str) -> str:
    """``pessoal-RS.json.gz``."""
    return f"pessoal-{uf.upper()}.json.gz"


def exercicio_padrao(hoje: date) -> int:
    """O exercício anterior: o RGF do último período sai até 30 de janeiro do ano seguinte (LRF, art. 55, § 2º)."""
    return hoje.year - 1


def consultas_pelo_extrato(conformidade: dict | None, exercicio: int,
                           esfera_de: dict[str, str]) -> dict[str, tuple[str, str] | None]:
    """Por ente, o tipo e a periodicidade do RGF do Executivo no último período do ``exercicio``, pelo extrato.

    ``None`` é o ente com o extrato lido e sem essa entrega; o ente cujo extrato do exercício não pôde ser lido
    fica de fora (vai com ``SEM_EXTRATO``). ``esfera_de`` dá a esfera de cada código (M, E ou D).
    """
    if not conformidade:
        return {}
    colunas = conformidade["colunas"]
    i_inst, i_ent, i_ex, i_per, i_peri = (colunas.index(c) for c in
                                          ("instituicao", "entregavel", "exercicio", "periodo", "periodicidade"))
    saida: dict[str, tuple[str, str] | None] = {}
    for codigo, info in (conformidade.get("entes") or {}).items():
        if not (info.get("coleta") or {}).get(str(exercicio)):
            continue
        nomes = EXECUTIVO.get(esfera_de.get(codigo, "M"), EXECUTIVO["M"])
        achado = None
        for e in info.get("entregas") or []:
            periodicidade = (e[i_peri] or "").upper()
            if (e[i_ex] == exercicio and e[i_ent] in ENTREGAVEIS and periodicidade in ULTIMO_PERIODO
                    and e[i_per] == ULTIMO_PERIODO[periodicidade]
                    and any(n in chave_texto(e[i_inst]) for n in nomes)):
                achado = (ENTREGAVEIS[e[i_ent]], periodicidade)
        saida[codigo] = achado
    return saida


def ler_estado(caminho: Path, exercicio: int) -> dict:
    """O estado gravado da UF; vazio se não existe ou é de outro exercício."""
    if caminho.exists():
        dados = ler_json(caminho)
        if dados.get("versao") != VERSAO_ESTADO:
            raise ValueError(f"{caminho}: versão {dados.get('versao')!r} do estado da despesa com pessoal não suportada")
        if dados.get("exercicio") == exercicio:
            return dados
    return {"versao": VERSAO_ESTADO, "exercicio": exercicio, "entes": {}}


def pendentes(estado: dict, entes: list[Ente], hoje: date) -> list[Ente]:
    """Os entes sem o percentual no estado: os nunca tentados e os sem dado tentados há ``DIAS_PARA_TENTAR_DE_NOVO``."""
    limite = (hoje - timedelta(days=DIAS_PARA_TENTAR_DE_NOVO)).isoformat()
    saida = []
    for ente in entes:
        registro = estado["entes"].get(ente.codigo)
        if registro is None or (registro.get("percentual") is None and (registro.get("tentado_em") or "") <= limite):
            saida.append(ente)
    return saida


def pessoal_da_silver(silver: Path) -> dict[str, dict]:
    """Por código IBGE, o percentual da despesa total com pessoal sobre a RCL ajustada, os valores e os limites.

    A coluna do percentual é a que começa com "%"; a dos valores, "Valor". Ente sem o percentual fica de fora.
    """
    por_ente: dict[str, dict] = {}
    for linha in consolidar(ler_entidade(silver, "linha_demonstrativo")):
        if linha.get("anexo") != ANEXO or linha.get("valor") is None:
            continue
        registro = por_ente.setdefault(linha["ente_codigo_ibge"], {
            "percentual": None, "dtp": None, "rcl_ajustada": None, "limites": {},
            "demonstrativo": linha.get("demonstrativo"), "periodo": linha.get("periodo"),
            "periodicidade": linha.get("periodicidade")})
        conta, valor = linha.get("cod_conta"), float(linha["valor"])
        percentual = str(linha.get("coluna") or "").startswith("%")
        if conta == CONTA_DTP:
            registro["percentual" if percentual else "dtp"] = valor
        elif conta == CONTA_RCL_AJUSTADA and not percentual:
            registro["rcl_ajustada"] = valor
        elif percentual:
            for nome, codigo in LIMITES.items():
                if conta == codigo:
                    registro["limites"][nome] = valor
    return {c: r for c, r in por_ente.items() if r["percentual"] is not None}


@dataclass
class ResultadoPessoal:
    """O que a coleta de uma UF fez: pendentes, consultas, percentuais encontrados, sem dado e os que ficaram."""

    uf: str
    pendentes: int = 0
    consultas: int = 0
    encontradas: int = 0
    sem_dado: int = 0
    para_depois: int = 0
    problemas: list[str] = field(default_factory=list)

    def para_json(self) -> dict:
        """Resumo para imprimir na linha de comando."""
        return {"uf": self.uf, "pendentes": self.pendentes, "consultas": self.consultas,
                "encontradas": self.encontradas, "sem_dado": self.sem_dado, "para_depois": self.para_depois,
                "problemas": self.problemas}


def coletar_uf(cfg, uf: str, cadastro: Cadastro, estado: Path | str, exercicio: int, *, coletar=None,
               normalizar=None, temporario: Path | None = None, hoje: date | None = None,
               limite_minutos: float | None = None, relogio=time.monotonic) -> ResultadoPessoal:
    """Coleta o RGF (Anexo 1, Executivo) dos entes pendentes da UF e grava o estado; ``coletar`` e
    ``normalizar`` são os de ``lumen_orquestracao.etapas``.

    Primeira passada com a combinação do extrato (ou a primeira de ``SEM_EXTRATO``); segunda, só para quem ficou
    sem extrato e sem dado, com a outra. Cada passada vai em lotes de ``TAMANHO_DO_LOTE`` por combinação;
    passado o ``limite_minutos``, não começa outro lote, e quem não foi consultado continua pendente.
    """
    if coletar is None or normalizar is None:
        from lumen_orquestracao import etapas
        coletar = coletar or etapas.coletar
        normalizar = normalizar or etapas.normalizar
    hoje = hoje or hoje_brasilia()
    uf = uf.upper()
    caminho = Path(estado) / nome_do_arquivo(uf)
    dados = ler_estado(caminho, exercicio)
    faltam = pendentes(dados, list(cadastro.da_uf(uf)), hoje)
    resultado = ResultadoPessoal(uf, pendentes=len(faltam))
    if not faltam:
        return resultado
    arquivo_conformidade = Path(estado) / f"conformidade-{uf}.json.gz"
    pelo_extrato = consultas_pelo_extrato(
        ler_json(arquivo_conformidade) if arquivo_conformidade.exists() else None, exercicio,
        {e.codigo: e.esfera or "M" for e in faltam})
    ordem = {e.codigo: ((pelo_extrato[e.codigo],) if pelo_extrato.get(e.codigo) else ())
             if e.codigo in pelo_extrato else SEM_EXTRATO for e in faltam}
    inicio = relogio()
    tentativas: dict[str, int] = {}     # combinações já consultadas por ente
    interrompidos: set[str] = set()     # o lote da coleta interrompida: continua pendente
    achadas: dict[str, dict] = {}
    raiz = Path(tempfile.mkdtemp(prefix=f"pessoal-{uf}-", dir=temporario))
    try:
        cfg_uf = replace(cfg, raiz_dados=raiz)
        parar = False
        for passada in (0, 1):
            por_combinacao: dict[tuple[str, str], list[str]] = {}
            for codigo, combinacoes in ordem.items():
                if codigo not in achadas and passada < len(combinacoes):
                    por_combinacao.setdefault(combinacoes[passada], []).append(codigo)
            for (tipo, periodicidade), codigos in sorted(por_combinacao.items()):
                for i in range(0, len(codigos), TAMANHO_DO_LOTE):
                    if limite_minutos is not None and relogio() - inicio > limite_minutos * 60:
                        parar = True
                        break
                    lote = codigos[i:i + TAMANHO_DO_LOTE]
                    resultado.consultas += len(lote)
                    for codigo in lote:
                        tentativas[codigo] = tentativas.get(codigo, 0) + 1
                    try:
                        coletar(cfg_uf, "siconfi_rgf", Janela(hoje, hoje), entes=lote, exercicio=exercicio,
                                periodo=ULTIMO_PERIODO[periodicidade], tipo_demonstrativo=tipo, anexo=ANEXO,
                                poder="E", periodicidade_rgf=periodicidade)
                    except ErroColeta as erro:
                        resultado.problemas.append(f"coleta interrompida ({type(erro).__name__}: {erro})")
                        interrompidos.update(lote)
                        parar = True
                        break
                if parar:
                    break
            if tentativas:
                normalizar(cfg_uf, ["siconfi_rgf"])
                achadas = pessoal_da_silver(cfg_uf.silver)
            if parar:
                break
        instante = instante_utc()
        for codigo, combinacoes in sorted(ordem.items()):
            if codigo in achadas:
                # O RGF não diz se é o simplificado: vale a combinação da consulta que o achou (a última feita)
                tipo, periodicidade = combinacoes[tentativas[codigo] - 1]
                dados["entes"][codigo] = {**achadas[codigo], "demonstrativo": tipo, "periodicidade": periodicidade,
                                          "coletado_em": instante}
                resultado.encontradas += 1
            elif codigo in interrompidos or tentativas.get(codigo, 0) < len(combinacoes):
                resultado.para_depois += 1      # nem todas as combinações foram consultadas
            else:
                dados["entes"][codigo] = {"percentual": None, "tentado_em": hoje.isoformat()}
                resultado.sem_dado += 1
        dados["coletado_em"] = instante
        gravar_json(caminho, dados, comprimir=True)
        return resultado
    finally:
        shutil.rmtree(raiz, ignore_errors=True)


def ler_pessoal(arquivos, exercicio: int | None = None) -> tuple[int | None, dict[str, dict]]:
    """Junta os estados das UFs: o exercício (o mais recente entre os arquivos) e, por ente, o percentual.

    Só entram os entes com o percentual do exercício escolhido.
    """
    estados = [ler_json(c) for c in sorted(arquivos, key=lambda p: Path(p).name)]
    if exercicio is None:
        exercicios = [e.get("exercicio") for e in estados if e.get("exercicio")]
        exercicio = max(exercicios) if exercicios else None
    saida = {}
    for e in estados:
        if e.get("exercicio") == exercicio:
            saida.update({c: r for c, r in (e.get("entes") or {}).items() if r.get("percentual") is not None})
    return exercicio, saida
