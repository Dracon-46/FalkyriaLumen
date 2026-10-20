"""Despesa por função de cada ente, para a comparação com o grupo de pares (RF-PU-05; dado da regra H-01).

A fonte é a DCA do exercício, Anexo I-E (despesa por função e subfunção), no SICONFI: a coluna "Despesas
Liquidadas", sem as intraorçamentárias. As funções são as linhas ``NN - Nome``; as subfunções vêm como
``NN.NNN - Nome`` e ``FUNN - Demais Subfunções`` e ficam de fora. As funções somam a linha "Despesas Exceto
Intraorçamentárias" (até 2016, "Despesas (Exceto Intraorçamentárias)"). Em 2025, a soma confere ao centavo nas
434 DCA da região Norte, em Porto Alegre e no Rio Grande do Sul.

Como na RCL (``rcl.py``), o estado é por UF (``despesa-funcao-<UF>.json.gz``), com o exercício e, por ente, o
total e o valor de cada função, ou só a data da última tentativa sem dado. Quem diz se vale consultar é o extrato
de entregas que a conformidade já coletou: o ente sem a DCA do exercício no extrato não é consultado e volta
depois de ``DIAS_PARA_TENTAR_DE_NOVO`` dias; sem extrato, a consulta vai assim mesmo. A DCA do ano sai até 30
de abril (municípios) e 31 de maio (estados) do ano seguinte (LRF, art. 51), e a coleta passa ao exercício novo
em maio.

A primeira carga de uma UF grande pode não caber numa execução: a coleta vai em lotes e para no
``limite_minutos``; quem não foi consultado continua pendente para a execução seguinte.
"""

from __future__ import annotations

import re
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

ANEXO = "DCA-Anexo I-E"
COLUNA = "Despesas Liquidadas"
ENTREGAVEL_DCA = "Balanço Anual (DCA)"
DIAS_PARA_TENTAR_DE_NOVO = 7
TAMANHO_DO_LOTE = 50
VERSAO_ESTADO = 1
TOLERANCIA_DA_SOMA = 0.01   # funções que somam mais de 1% longe do total: a DCA do ente fica fora das distribuições

# As 28 funções da classificação funcional (Portaria MOG 42/1999), pelo código
FUNCOES = {
    "01": "Legislativa", "02": "Judiciária", "03": "Essencial à Justiça", "04": "Administração",
    "05": "Defesa Nacional", "06": "Segurança Pública", "07": "Relações Exteriores", "08": "Assistência Social",
    "09": "Previdência Social", "10": "Saúde", "11": "Trabalho", "12": "Educação", "13": "Cultura",
    "14": "Direitos da Cidadania", "15": "Urbanismo", "16": "Habitação", "17": "Saneamento",
    "18": "Gestão Ambiental", "19": "Ciência e Tecnologia", "20": "Agricultura", "21": "Organização Agrária",
    "22": "Indústria", "23": "Comércio e Serviços", "24": "Comunicações", "25": "Energia", "26": "Transporte",
    "27": "Desporto e Lazer", "28": "Encargos Especiais",
}
_FUNCAO = re.compile(r"^(\d{2}) - ")
_TOTAL = "despesas exceto intraorcamentarias"


def nome_do_arquivo(uf: str) -> str:
    """``despesa-funcao-RS.json.gz``."""
    return f"despesa-funcao-{uf.upper()}.json.gz"


def exercicio_padrao(hoje: date) -> int:
    """O último exercício com a DCA no prazo: o anterior a partir de maio, o retrasado antes (LRF, art. 51)."""
    return hoje.year - 1 if hoje.month >= 5 else hoje.year - 2


def entregues_pelo_extrato(conformidade: dict | None, exercicio: int) -> dict[str, bool]:
    """Por ente, se o extrato da conformidade da UF tem a DCA do ``exercicio``.

    O ente cujo extrato do exercício não pôde ser lido fica de fora (é consultado assim mesmo).
    """
    if not conformidade:
        return {}
    colunas = conformidade["colunas"]
    i_ent, i_ex = colunas.index("entregavel"), colunas.index("exercicio")
    saida = {}
    for codigo, info in (conformidade.get("entes") or {}).items():
        if (info.get("coleta") or {}).get(str(exercicio)):
            saida[codigo] = any(e[i_ent] == ENTREGAVEL_DCA and e[i_ex] == exercicio
                                for e in info.get("entregas") or [])
    return saida


def ler_estado(caminho: Path, exercicio: int) -> dict:
    """O estado gravado da UF; vazio se não existe ou é de outro exercício."""
    if caminho.exists():
        dados = ler_json(caminho)
        if dados.get("versao") != VERSAO_ESTADO:
            raise ValueError(f"{caminho}: versão {dados.get('versao')!r} do estado da despesa por função não suportada")
        if dados.get("exercicio") == exercicio:
            return dados
    return {"versao": VERSAO_ESTADO, "exercicio": exercicio, "entes": {}}


def pendentes(estado: dict, entes: list[Ente], hoje: date) -> list[Ente]:
    """Os entes sem a despesa no estado: os nunca tentados e os sem dado tentados há ``DIAS_PARA_TENTAR_DE_NOVO``."""
    limite = (hoje - timedelta(days=DIAS_PARA_TENTAR_DE_NOVO)).isoformat()
    saida = []
    for ente in entes:
        registro = estado["entes"].get(ente.codigo)
        if registro is None or (registro.get("total") is None and (registro.get("tentado_em") or "") <= limite):
            saida.append(ente)
    return saida


def despesas_da_silver(silver: Path) -> dict[str, dict]:
    """Por código IBGE, o total e as funções (código → valor) da despesa liquidada, das linhas da silver.

    Se o ente tiver linhas de mais de uma instituição, vale a de maior total.
    """
    por_instituicao: dict[tuple[str, str], dict] = {}
    for linha in consolidar(ler_entidade(silver, "linha_demonstrativo")):
        if linha.get("coluna") != COLUNA or linha.get("anexo") != ANEXO or linha.get("valor") is None:
            continue
        registro = por_instituicao.setdefault((linha["ente_codigo_ibge"], linha.get("instituicao") or ""),
                                              {"total": None, "funcoes": {}})
        conta = str(linha.get("conta") or "")
        funcao = _FUNCAO.match(conta)
        if funcao:
            registro["funcoes"].setdefault(funcao.group(1), float(linha["valor"]))
        elif chave_texto(re.sub(r"[()]", "", conta)) == _TOTAL and registro["total"] is None:
            registro["total"] = float(linha["valor"])
    saida: dict[str, dict] = {}
    for (codigo, _), registro in sorted(por_instituicao.items()):
        if registro["total"] is None:
            continue
        if codigo not in saida or registro["total"] > saida[codigo]["total"]:
            saida[codigo] = registro
    return saida


def confere(registro: dict) -> bool:
    """Se as funções do ente somam o total, com ``TOLERANCIA_DA_SOMA``."""
    total = registro.get("total")
    if not total:
        return False
    return abs(sum(registro.get("funcoes", {}).values()) - total) <= abs(total) * TOLERANCIA_DA_SOMA


@dataclass
class ResultadoDespesa:
    """O que a coleta de uma UF fez: pendentes, consultas, DCA encontradas, entes sem dado e os que ficaram."""

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
               limite_minutos: float | None = None, relogio=time.monotonic) -> ResultadoDespesa:
    """Coleta a DCA (Anexo I-E) dos entes pendentes da UF e grava o estado; ``coletar`` e ``normalizar`` são os de
    ``lumen_orquestracao.etapas``.

    Vai em lotes de ``TAMANHO_DO_LOTE``; passado o ``limite_minutos``, não começa outro lote, e os entes que
    não foram consultados continuam pendentes.
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
    resultado = ResultadoDespesa(uf, pendentes=len(faltam))
    if not faltam:
        return resultado
    arquivo_conformidade = Path(estado) / f"conformidade-{uf}.json.gz"
    entregues = entregues_pelo_extrato(ler_json(arquivo_conformidade) if arquivo_conformidade.exists() else None,
                                       exercicio)
    consultar = [e.codigo for e in faltam if entregues.get(e.codigo, True)]
    nao_entregaram = [e.codigo for e in faltam if not entregues.get(e.codigo, True)]
    inicio = relogio()
    consultados: list[str] = []
    interrompidos: set[str] = set()   # o lote da coleta interrompida: quem ficou sem dado continua pendente
    raiz = Path(tempfile.mkdtemp(prefix=f"despesa-funcao-{uf}-", dir=temporario))
    try:
        cfg_uf = replace(cfg, raiz_dados=raiz)
        for i in range(0, len(consultar), TAMANHO_DO_LOTE):
            if limite_minutos is not None and relogio() - inicio > limite_minutos * 60:
                break
            lote = consultar[i:i + TAMANHO_DO_LOTE]
            resultado.consultas += len(lote)
            consultados.extend(lote)
            try:
                coletar(cfg_uf, "siconfi_dca", Janela(hoje, hoje), entes=lote, exercicio=exercicio, anexo=ANEXO)
            except ErroColeta as erro:
                resultado.problemas.append(f"coleta interrompida ({type(erro).__name__}: {erro})")
                interrompidos = set(lote)
                break
        achadas = {}
        if consultados:
            normalizar(cfg_uf, ["siconfi_dca"])
            achadas = despesas_da_silver(cfg_uf.silver)
        instante = instante_utc()
        for codigo in consultados + nao_entregaram:
            if codigo in achadas:
                dados["entes"][codigo] = {**achadas[codigo], "coletado_em": instante}
                resultado.encontradas += 1
            elif codigo in interrompidos:
                resultado.para_depois += 1
            else:
                dados["entes"][codigo] = {"total": None, "tentado_em": hoje.isoformat()}
                resultado.sem_dado += 1
        resultado.para_depois += len(consultar) - len(consultados)
        dados["coletado_em"] = instante
        gravar_json(caminho, dados, comprimir=True)
        return resultado
    finally:
        shutil.rmtree(raiz, ignore_errors=True)


def ler_despesas(arquivos, exercicio: int | None = None) -> tuple[int | None, dict[str, dict]]:
    """Junta os estados das UFs: o exercício (o mais recente entre os arquivos) e, por ente, o total e as funções.

    Só entram os entes com a DCA do exercício escolhido.
    """
    estados = [ler_json(c) for c in sorted(arquivos, key=lambda p: Path(p).name)]
    if exercicio is None:
        exercicios = [e.get("exercicio") for e in estados if e.get("exercicio")]
        exercicio = max(exercicios) if exercicios else None
    saida = {}
    for e in estados:
        if e.get("exercicio") == exercicio:
            saida.update({c: r for c, r in (e.get("entes") or {}).items() if r.get("total") is not None})
    return exercicio, saida
