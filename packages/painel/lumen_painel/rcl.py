"""Receita corrente líquida (RCL) de cada ente, para os grupos de pares (ADR-038, versão 2).

A RCL do exercício vem do RREO do 6º bimestre, Anexo 03: conta ``RREO3ReceitaCorrenteLiquida``, coluna
"TOTAL (ÚLTIMOS 12 MESES)". Cada ente publica um dos dois tipos de RREO, o completo ou o simplificado (municípios
com menos de 50 mil habitantes podem optar por ele, LRF art. 63), e a consulta precisa dizer qual. O tamanho do
município não diz o tipo: em 2025, quase todos os pequenos de Roraima e do Amapá publicaram o completo, e São
Sepé (RS), o simplificado. Quem diz é o extrato de entregas que a conformidade já coletou: o tipo entregue no 6º
bimestre vai numa consulta só, e o ente que não o entregou não é consultado. Sem extrato, vão os dois tipos,
o completo primeiro.

O estado é por UF (``rcl-<UF>.json.gz``), com o exercício e, por ente, a RCL e o tipo do RREO, ou só a data da
última tentativa sem dado. A coleta pega primeiro quem falta. Quem não tinha publicado é tentado de novo depois
de ``DIAS_PARA_TENTAR_DE_NOVO`` dias. Depois da primeira carga, o fluxo diário quase não consulta nada.
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from pathlib import Path

from lumen_ingestao.coleta_http import ErroColeta
from lumen_ingestao.portas import Janela
from lumen_normalizacao.silver import consolidar, ler_entidade

from .cadastro import Cadastro, Ente
from .comum import gravar_json, hoje_brasilia, instante_utc, ler_json

CONTA_RCL = "RREO3ReceitaCorrenteLiquida"
COLUNA_RCL = "TOTAL (ÚLTIMOS 12 MESES)"
ANEXO_RCL = "RREO-Anexo 03"
PERIODO_RCL = 6
RREO, SIMPLIFICADO = "RREO", "RREO Simplificado"
ENTREGAVEIS = {"Relatório Resumido de Execução Orçamentária": RREO,
               "Relatório Resumido de Execução Orçamentária Simplificado": SIMPLIFICADO}
DIAS_PARA_TENTAR_DE_NOVO = 7
VERSAO_ESTADO = 1


def nome_do_arquivo(uf: str) -> str:
    """``rcl-RS.json.gz``."""
    return f"rcl-{uf.upper()}.json.gz"


def exercicio_padrao(hoje: date) -> int:
    """O exercício anterior: o RREO do 6º bimestre sai até 30 de janeiro do ano seguinte (LRF, art. 52)."""
    return hoje.year - 1


def tipos_pelo_extrato(conformidade: dict | None, exercicio: int) -> dict[str, str | None]:
    """Por ente, o tipo de RREO entregue no 6º bimestre do ``exercicio``, pelo estado da conformidade da UF.

    ``None`` é o ente com o extrato lido e sem essa entrega; o ente cujo extrato do exercício não pôde ser lido
    fica de fora (vai com os dois tipos).
    """
    if not conformidade:
        return {}
    colunas = conformidade["colunas"]
    i_ent, i_ex, i_per = colunas.index("entregavel"), colunas.index("exercicio"), colunas.index("periodo")
    saida: dict[str, str | None] = {}
    for codigo, info in (conformidade.get("entes") or {}).items():
        if not (info.get("coleta") or {}).get(str(exercicio)):
            continue
        tipos = {ENTREGAVEIS[e[i_ent]] for e in info.get("entregas") or []
                 if e[i_ex] == exercicio and e[i_per] == PERIODO_RCL and e[i_ent] in ENTREGAVEIS}
        saida[codigo] = SIMPLIFICADO if SIMPLIFICADO in tipos else (RREO if tipos else None)
    return saida


def ordem_de_tentativa(codigo: str, tipos: dict[str, str | None]) -> tuple[str, ...]:
    """Os tipos de RREO a consultar, em ordem: o do extrato e depois o outro; nenhum se o extrato diz que o ente
    não entregou; os dois, o completo primeiro, sem extrato."""
    if codigo not in tipos:
        return (RREO, SIMPLIFICADO)
    tipo = tipos[codigo]
    return () if tipo is None else (tipo, SIMPLIFICADO if tipo == RREO else RREO)


def ler_estado(caminho: Path, exercicio: int) -> dict:
    """O estado gravado da UF; vazio se não existe ou é de outro exercício."""
    if caminho.exists():
        dados = ler_json(caminho)
        if dados.get("versao") != VERSAO_ESTADO:
            raise ValueError(f"{caminho}: versão {dados.get('versao')!r} do estado da RCL não suportada")
        if dados.get("exercicio") == exercicio:
            return dados
    return {"versao": VERSAO_ESTADO, "exercicio": exercicio, "entes": {}}


def pendentes(estado: dict, entes: list[Ente], hoje: date) -> list[Ente]:
    """Os entes sem RCL no estado: os nunca tentados e os sem dado tentados há ``DIAS_PARA_TENTAR_DE_NOVO`` dias."""
    limite = (hoje - timedelta(days=DIAS_PARA_TENTAR_DE_NOVO)).isoformat()
    saida = []
    for ente in entes:
        registro = estado["entes"].get(ente.codigo)
        if registro is None or (registro.get("rcl") is None and (registro.get("tentado_em") or "") <= limite):
            saida.append(ente)
    return saida


def rcl_da_silver(silver: Path) -> dict[str, dict]:
    """Por código IBGE, a RCL (12 meses) e o tipo do RREO, das linhas de demonstrativo da silver."""
    saida = {}
    for linha in consolidar(ler_entidade(silver, "linha_demonstrativo")):
        if linha.get("cod_conta") == CONTA_RCL and linha.get("coluna") == COLUNA_RCL and linha.get("valor") is not None:
            saida[linha["ente_codigo_ibge"]] = {"rcl": float(linha["valor"]), "demonstrativo": linha["demonstrativo"]}
    return saida


@dataclass
class ResultadoRcl:
    """O que a coleta de uma UF fez: entes pendentes, consultas feitas, RCL encontradas e problemas."""

    uf: str
    pendentes: int = 0
    consultas: int = 0
    encontradas: int = 0
    sem_dado: int = 0
    problemas: list[str] = field(default_factory=list)

    def para_json(self) -> dict:
        """Resumo para imprimir na linha de comando."""
        return {"uf": self.uf, "pendentes": self.pendentes, "consultas": self.consultas,
                "encontradas": self.encontradas, "sem_dado": self.sem_dado, "problemas": self.problemas}


def coletar_uf(cfg, uf: str, cadastro: Cadastro, estado: Path | str, exercicio: int, *, coletar=None,
               normalizar=None, temporario: Path | None = None, hoje: date | None = None) -> ResultadoRcl:
    """Coleta a RCL dos entes pendentes da UF e grava o estado; ``coletar`` e ``normalizar`` são os de
    ``lumen_orquestracao.etapas``.

    O tipo de cada ente vem do estado da conformidade da UF, no mesmo diretório (``ordem_de_tentativa``).
    Primeira passada com o primeiro tipo de cada um; segunda, com o outro, para quem ficou sem dado.
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
    resultado = ResultadoRcl(uf, pendentes=len(faltam))
    if not faltam:
        return resultado
    arquivo_conformidade = Path(estado) / f"conformidade-{uf}.json.gz"
    tipos = tipos_pelo_extrato(ler_json(arquivo_conformidade) if arquivo_conformidade.exists() else None, exercicio)
    raiz = Path(tempfile.mkdtemp(prefix=f"rcl-{uf}-", dir=temporario))
    try:
        cfg_uf = replace(cfg, raiz_dados=raiz)
        achadas: dict[str, dict] = {}
        for passada in (0, 1):
            por_tipo: dict[str, list[str]] = {}
            for ente in faltam:
                ordem = ordem_de_tentativa(ente.codigo, tipos)
                if ente.codigo not in achadas and passada < len(ordem):
                    por_tipo.setdefault(ordem[passada], []).append(ente.codigo)
            for tipo, codigos in por_tipo.items():
                resultado.consultas += len(codigos)
                try:
                    coletar(cfg_uf, "siconfi_rreo", Janela(hoje, hoje), entes=codigos, exercicio=exercicio,
                            periodo=PERIODO_RCL, tipo_demonstrativo=tipo, anexo=ANEXO_RCL)
                except ErroColeta as erro:
                    resultado.problemas.append(f"{tipo}: coleta interrompida ({type(erro).__name__}: {erro})")
            if por_tipo:
                normalizar(cfg_uf, ["siconfi_rreo"])
                achadas = rcl_da_silver(cfg_uf.silver)
        instante = instante_utc()
        for ente in faltam:
            registro = achadas.get(ente.codigo)
            if registro:
                dados["entes"][ente.codigo] = {**registro, "coletado_em": instante}
                resultado.encontradas += 1
            else:
                dados["entes"][ente.codigo] = {"rcl": None, "tentado_em": hoje.isoformat()}
                resultado.sem_dado += 1
        dados["coletado_em"] = instante
        gravar_json(caminho, dados, comprimir=True)
        return resultado
    finally:
        shutil.rmtree(raiz, ignore_errors=True)


def ler_rcl(arquivos, exercicio: int | None = None) -> tuple[int | None, dict[str, dict]]:
    """Junta os estados das UFs: o exercício (o mais recente entre os arquivos) e, por ente, a RCL e o tipo.

    Só entram os entes com RCL do exercício escolhido.
    """
    estados = [ler_json(c) for c in sorted(arquivos, key=lambda p: Path(p).name)]
    exercicios = [e.get("exercicio") for e in estados if e.get("exercicio")]
    if exercicio is None:
        exercicio = max(exercicios) if exercicios else None
    saida = {}
    for e in estados:
        if e.get("exercicio") == exercicio:
            saida.update({c: r for c, r in (e.get("entes") or {}).items() if r.get("rcl") is not None})
    return exercicio, saida
