"""Painel de contratações: soma os dias do PNCP guardados no estado em arquivos por ente (UC-01, UC-02).

Para cada ente com alguma publicação no período, o arquivo do ente (dentro de ``contratacoes/ente/<grupo>.json.gz``,
comprimido, com os entes do grupo; ``comum.grupo_do_ente``) traz:

- os totais (processos publicados e a soma do valor estimado; contratos e a soma do valor global);
- o mês a mês e a divisão por modalidade de contratação;
- todos os órgãos do ente que publicaram (prefeitura, câmara, secretarias, autarquias, fundações e empresas
  públicas, como um serviço autônomo de água e esgoto), cada um com o próprio arquivo
  o arquivo do órgão (dentro de ``contratacoes/orgao/<grupo>.json.gz``; ``comum.grupo_do_cnpj``), com as mesmas
  seções;
- os fornecedores pessoa jurídica com maior valor contratado e, numa linha só, a soma dos contratos com
  pessoa física ou estrangeira, sem nome nem documento (RNF-19 e RNF-20);
- os processos e contratos publicados mais recentemente, com o link de cada um no PNCP;
- no arquivo de um estado, a tabela dos municípios da UF, para navegar.

Modalidades, órgãos, fornecedores, municípios, esferas e UFs levam também o mês a mês (``meses``, em
listas ``[mês, ...]``), para o portal refazer as tabelas num período escolhido sem outro arquivo. Os
fornecedores listados são os de maior valor no período inteiro: num período menor, a ordem é refeita entre
eles, e o portal diz isso.

Com o histórico inteiro (desde agosto de 2021), o mês a mês dos anos mais antigos vira ano a ano
(``compactar_meses``): ficam mês a mês o ano corrente e o anterior; antes deles, uma linha por ano
(``"2023"``). Sem isso, o mês a mês de cada linha das tabelas passaria de 60 entradas e o site, de 1 GB. O
portal filtra por ano nesse trecho.

O ente de cada publicação é o do órgão que publicou (``dia.resumir_dia``): os números de um município são os
dos órgãos municipais, e não os de órgãos estaduais ou federais que ficam nele.

Os valores são os publicados no PNCP, sem correção: valor estimado sigiloso ou zerado conta como processo
sem valor. Um valor acima do teto de plausibilidade (``teto_do_ente``: R$ 10 bilhões, ou R$ 20 mil por
habitante do ente, o que for menor) conta o processo ou o contrato, mas fica fora das somas e das listas de
fornecedores e aparece em "valores a conferir", com o link da publicação: um único contrato de R$ 240
bilhões, como o publicado em 13/10/2026, faria sozinho mais de 90% do valor do país na semana. Não é juízo
sobre o órgão nem sobre o fornecedor; é a conferência mínima de um valor que a fonte publicou. O painel não
ordena entes por nenhum critério de risco (PUB-07) e não publica indício: só soma o que a fonte publicou.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable

from .cadastro import Cadastro
from .comum import MODALIDADES, UFS, link_pncp, somar, tipo_do_ente, uf_do_ente
from .dia import ler_dia

RECENTES = 25
CONTRATOS_RECENTES = 15
# No arquivo de cada órgão, listas menores: são dezenas de milhares de órgãos na memória ao mesmo tempo
RECENTES_ORGAO = 10
ORGAOS = 300
FORNECEDORES = 100
FORNECEDORES_ORGAO = 50
FORNECEDORES_PANORAMA = 200
A_CONFERIR = 50
# Teto de plausibilidade de um processo ou contrato: acima dele o valor fica fora das somas (ADR-028)
TETO_ABSOLUTO = 10_000_000_000.0
TETO_POR_HABITANTE = 20_000.0


def corte_mes_a_mes(ate: str | None) -> str | None:
    """O primeiro mês que fica mês a mês: janeiro do ano anterior ao do último dia coletado (``AAAA-MM``)."""
    return f"{int(ate[:4]) - 1}-01" if ate else None


def _somar_linhas(linhas: list) -> list:
    """Linhas de meses do mesmo ano somadas numa só, com o ano no lugar do mês (objetos ou listas)."""
    por_ano: dict[str, object] = {}
    for linha in linhas:
        if isinstance(linha, dict):
            ano = str(linha["mes"])[:4]
            alvo = por_ano.setdefault(ano, {"mes": ano})
            for k, v in linha.items():
                if k != "mes" and isinstance(v, (int, float)) and not isinstance(v, bool):
                    alvo[k] = alvo.get(k, 0) + v
        else:
            ano = str(linha[0])[:4]
            alvo = por_ano.setdefault(ano, [ano] + [0] * (len(linha) - 1))
            for i, v in enumerate(linha[1:], start=1):
                if i >= len(alvo):
                    alvo.append(0)
                alvo[i] += v or 0
    return [por_ano[a] for a in sorted(por_ano)]


def compactar_meses(dados, corte: str | None):
    """Troca, em toda lista ``meses`` do arquivo, os meses anteriores a ``corte`` por uma linha por ano.

    As somas não mudam: a linha do ano é a soma dos meses dele. Valores arredondados a centavos, para o número
    em ponto flutuante não crescer o arquivo à toa.
    """
    if corte is None:
        return dados
    if isinstance(dados, dict):
        saida = {}
        for k, v in dados.items():
            if k == "meses" and isinstance(v, list):
                antigos = [x for x in v if len(_chave_mes(x)) == 7 and _chave_mes(x) < corte]
                novos = [x for x in v if x not in antigos]
                saida[k] = [_arredondar(x) for x in _somar_linhas(antigos)] + novos
            else:
                saida[k] = compactar_meses(v, corte)
        return saida
    if isinstance(dados, list):
        return [compactar_meses(x, corte) for x in dados]
    return dados


def _chave_mes(linha) -> str:
    """O mês (ou o ano) de uma linha de ``meses``, em objeto ou em lista."""
    return str(linha["mes"]) if isinstance(linha, dict) else str(linha[0])


def _arredondar(linha):
    """Valores da linha somada com duas casas (as contagens já são inteiras)."""
    def r(v):
        return round(v, 2) if isinstance(v, float) else v

    return {k: r(v) for k, v in linha.items()} if isinstance(linha, dict) else [r(v) for v in linha]


def _mes(dia: str) -> str:
    """``2026-10-13`` → ``2026-10``."""
    return dia[:7]


@dataclass
class Totais:
    """Contagens e somas de um recorte: processos e valor estimado, contratos e valor global."""

    processos: int = 0
    valor_estimado: float = 0.0
    sem_valor: int = 0
    contratos: int = 0
    valor_contratos: float = 0.0
    a_conferir: int = 0

    def processo(self, estimado: float | None, conferir: bool = False) -> None:
        """Conta um processo; estimado ausente ou zero conta como processo sem valor; acima do teto
        (``conferir``), conta o processo e o valor fica fora da soma."""
        self.processos += 1
        if conferir:
            self.a_conferir += 1
            return
        if not estimado:
            self.sem_valor += 1
        self.valor_estimado = somar(self.valor_estimado, estimado)

    def contrato(self, global_: float | None, conferir: bool = False) -> None:
        """Conta um contrato e soma o valor global, salvo acima do teto (``conferir``)."""
        self.contratos += 1
        if conferir:
            self.a_conferir += 1
            return
        self.valor_contratos = somar(self.valor_contratos, global_)

    def para_json(self) -> dict:
        """Os totais com os nomes de campo dos feeds."""
        return {"processos": self.processos, "valor_estimado": self.valor_estimado,
                "processos_sem_valor": self.sem_valor, "contratos": self.contratos,
                "valor_contratos": self.valor_contratos, "valores_a_conferir": self.a_conferir}


@dataclass
class Fornecedor:
    """Um fornecedor pessoa jurídica: razão social mais recente, contratos e soma do valor global, no total e
    por mês (``[contratos, valor]``)."""

    nome: str | None = None
    contratos: int = 0
    valor: float = 0.0
    meses: dict[str, list] = field(default_factory=dict)

    def contrato(self, mes: str, valor: float | None) -> None:
        """Conta um contrato no total e no mês; ``valor`` ``None`` (a conferir ou ausente) não soma."""
        self.contratos += 1
        self.valor = somar(self.valor, valor)
        m = self.meses.setdefault(mes, [0, 0.0])
        m[0] += 1
        m[1] = somar(m[1], valor)


def meses_de_totais(meses: dict[str, Totais]) -> list[list]:
    """``{mês: Totais}`` → ``[[mês, processos, valor estimado, contratos, valor dos contratos], ...]``."""
    return [[m, x.processos, x.valor_estimado, x.contratos, x.valor_contratos] for m, x in sorted(meses.items())]


@dataclass
class Acumulador:
    """Tudo o que se soma para um ente (ou para o Brasil, no panorama)."""

    totais: Totais = field(default_factory=Totais)
    meses: dict[str, Totais] = field(default_factory=dict)
    modalidades: dict[int | None, Totais] = field(default_factory=dict)
    modalidades_mes: dict[int | None, dict[str, Totais]] = field(default_factory=dict)
    orgaos: dict[str, Totais] = field(default_factory=dict)
    orgaos_mes: dict[str, dict[str, Totais]] | None = field(default_factory=dict)
    fornecedores: dict[str, Fornecedor] = field(default_factory=dict)
    pessoas_fisicas: Totais = field(default_factory=Totais)
    pessoas_fisicas_mes: dict[str, Totais] = field(default_factory=dict)
    recentes: deque = field(default_factory=lambda: deque(maxlen=RECENTES))
    contratos_recentes: deque = field(default_factory=lambda: deque(maxlen=CONTRATOS_RECENTES))
    a_conferir: deque = field(default_factory=lambda: deque(maxlen=A_CONFERIR))

    @classmethod
    def de_orgao(cls) -> "Acumulador":
        """Acumulador de um órgão, com as listas de recentes menores (``RECENTES_ORGAO``) e sem o mês a mês
        por órgão (é o próprio órgão)."""
        return cls(recentes=deque(maxlen=RECENTES_ORGAO), contratos_recentes=deque(maxlen=RECENTES_ORGAO),
                   a_conferir=deque(maxlen=RECENTES_ORGAO), orgaos_mes=None)

    def processo(self, dia: str, linha: dict, conferir: bool = False) -> None:
        """Soma um processo (linha do arquivo do dia, já como dicionário); ``conferir``: valor acima do teto."""
        estimado = linha["valor_estimado"]
        mes = _mes(dia)
        self.totais.processo(estimado, conferir)
        self.meses.setdefault(mes, Totais()).processo(estimado, conferir)
        self.modalidades.setdefault(linha["modalidade"], Totais()).processo(estimado, conferir)
        self.modalidades_mes.setdefault(linha["modalidade"], {}).setdefault(mes, Totais()).processo(estimado, conferir)
        if linha["orgao"]:
            self.orgaos.setdefault(linha["orgao"], Totais()).processo(estimado, conferir)
            if self.orgaos_mes is not None:
                self.orgaos_mes.setdefault(linha["orgao"], {}).setdefault(mes, Totais()).processo(estimado, conferir)
        self.recentes.append((dia, linha, conferir))
        if conferir:
            self.a_conferir.append((dia, "processo", linha))

    def contrato(self, dia: str, linha: dict, conferir: bool = False) -> None:
        """Soma um contrato: no fornecedor pessoa jurídica pelo CNPJ, ou na soma anônima das demais pessoas.
        Com ``conferir`` (valor acima do teto), o contrato conta e o valor fica fora de todas as somas."""
        global_ = linha["valor_global"]
        mes = _mes(dia)
        self.totais.contrato(global_, conferir)
        self.meses.setdefault(mes, Totais()).contrato(global_, conferir)
        if linha["orgao"]:
            self.orgaos.setdefault(linha["orgao"], Totais()).contrato(global_, conferir)
            if self.orgaos_mes is not None:
                self.orgaos_mes.setdefault(linha["orgao"], {}).setdefault(mes, Totais()).contrato(global_, conferir)
        cnpj = linha["fornecedor_cnpj"]
        if cnpj:
            f = self.fornecedores.setdefault(cnpj, Fornecedor())
            f.nome = linha["fornecedor_nome"] or f.nome
            f.contrato(mes, None if conferir else global_)
        else:
            self.pessoas_fisicas.contrato(global_, conferir)
            self.pessoas_fisicas_mes.setdefault(mes, Totais()).contrato(global_, conferir)
        self.contratos_recentes.append((dia, linha, conferir))
        if conferir:
            self.a_conferir.append((dia, "contrato", linha))


def _linhas(dados: dict, tipo: str) -> Iterable[dict]:
    """As linhas de ``processos`` ou ``contratos`` do arquivo do dia, como dicionários pelas ``colunas``."""
    colunas = dados["colunas"][tipo]
    for valores in dados.get(tipo) or []:
        yield dict(zip(colunas, valores))


@dataclass
class Painel:
    """O resultado da soma de todos os dias: um acumulador por ente, o do Brasil e a cobertura."""

    entes: dict[str, Acumulador] = field(default_factory=dict)
    por_orgao: dict[str, Acumulador] = field(default_factory=dict)
    brasil: Acumulador = field(default_factory=Acumulador)
    esferas: dict[str, Totais] = field(default_factory=dict)
    esferas_mes: dict[str, dict[str, Totais]] = field(default_factory=dict)
    orgaos: dict[str, list] = field(default_factory=dict)      # CNPJ → [razão social, esfera, ente]
    dias: list[str] = field(default_factory=list)
    sem_ente: Totais = field(default_factory=Totais)
    volume: dict[str, dict[str, int]] = field(default_factory=dict)   # dia → processos e contratos publicados

    def cobertura(self) -> dict:
        """Primeiro e último dia guardados, quantos dias e os que faltam entre eles."""
        if not self.dias:
            return {"de": None, "ate": None, "dias": 0, "faltando": []}
        guardados = set(self.dias)
        inicio, fim = date.fromisoformat(self.dias[0]), date.fromisoformat(self.dias[-1])
        faltando = [(inicio + timedelta(n)).isoformat() for n in range((fim - inicio).days + 1)
                    if (inicio + timedelta(n)).isoformat() not in guardados]
        return {"de": self.dias[0], "ate": self.dias[-1], "dias": len(self.dias), "faltando": faltando}


def teto_do_ente(ente: str | None, cadastro: Cadastro | None) -> float:
    """Teto de plausibilidade de um processo ou contrato do ente: R$ 10 bilhões, ou R$ 20 mil por habitante
    (perto de quatro vezes o orçamento anual por habitante de um município médio), o que for menor. Sem
    população no cadastro (União, órgão sem ente), só o teto absoluto."""
    populacao = None
    if cadastro is not None and tipo_do_ente(ente):
        registro = cadastro.get(ente)
        populacao = registro.populacao if registro else None
    return min(TETO_ABSOLUTO, TETO_POR_HABITANTE * populacao) if populacao else TETO_ABSOLUTO


def somar_dias(arquivos: Iterable[Path], cadastro: Cadastro | None = None) -> Painel:
    """Lê os arquivos do dia em ordem de data e soma tudo por ente e para o Brasil. Com o ``cadastro``, o teto
    de plausibilidade usa a população do ente; sem ele, só o teto absoluto."""
    painel = Painel()
    tetos: dict[str | None, float] = {}
    for caminho in sorted(arquivos, key=lambda p: p.name):
        dados = ler_dia(caminho)
        dia = dados["dia"]
        painel.dias.append(dia)
        painel.volume[dia] = {tipo: len(dados.get(tipo) or []) for tipo in ("processos", "contratos")}
        for cnpj, orgao in (dados.get("orgaos") or {}).items():
            painel.orgaos[cnpj] = orgao
        for tipo, metodo, campo in (("processos", "processo", "valor_estimado"),
                                    ("contratos", "contrato", "valor_global")):
            for linha in _linhas(dados, tipo):
                ente = linha["ente"]
                if ente not in tetos:
                    tetos[ente] = teto_do_ente(ente, cadastro)
                valor = linha[campo]
                conferir = valor is not None and valor > tetos[ente]
                getattr(painel.brasil, metodo)(dia, linha, conferir)
                if linha["orgao"]:
                    acumulador = painel.por_orgao.get(linha["orgao"])
                    if acumulador is None:
                        acumulador = painel.por_orgao[linha["orgao"]] = Acumulador.de_orgao()
                    getattr(acumulador, metodo)(dia, linha, conferir)
                esfera = (painel.orgaos.get(linha["orgao"]) or [None, None])[1] or "?"
                getattr(painel.esferas.setdefault(esfera, Totais()), metodo)(valor, conferir)
                getattr(painel.esferas_mes.setdefault(esfera, {}).setdefault(_mes(dia), Totais()), metodo)(valor, conferir)
                if tipo_do_ente(ente) is None:
                    getattr(painel.sem_ente, metodo)(valor, conferir)
                    continue
                getattr(painel.entes.setdefault(ente, Acumulador()), metodo)(dia, linha, conferir)
    return painel


# ---------------------------------------------------------------------------------------------- feeds

def _nome_orgao(painel: Painel, cnpj: str | None) -> str | None:
    """Razão social do órgão pelo CNPJ, do arquivo do dia mais recente que o trouxe."""
    return (painel.orgaos.get(cnpj or "") or [None])[0]


def _secoes(a: Acumulador, painel: Painel, *, fornecedores: int = FORNECEDORES) -> dict:
    """As seções comuns ao arquivo de um ente e ao panorama."""
    return {
        "totais": {**a.totais.para_json(), "orgaos": len(a.orgaos), "fornecedores": len(a.fornecedores)},
        "meses": [{"mes": m, **t.para_json()} for m, t in sorted(a.meses.items())],
        "modalidades": [
            {"codigo": c, "nome": MODALIDADES.get(c, "Não informada") if c is not None else "Não informada",
             "processos": t.processos, "valor_estimado": t.valor_estimado,
             "meses": [[m, x.processos, x.valor_estimado] for m, x in sorted(a.modalidades_mes.get(c, {}).items())]}
            for c, t in sorted(a.modalidades.items(), key=lambda x: (-x[1].processos, x[0] or 0))],
        "orgaos": [
            {"cnpj": c, "nome": _nome_orgao(painel, c), **t.para_json(),
             "meses": meses_de_totais((a.orgaos_mes or {}).get(c, {}))}
            for c, t in sorted(a.orgaos.items(), key=lambda x: (-x[1].processos, -x[1].contratos, x[0]))[:ORGAOS]],
        "fornecedores": [
            {"cnpj": c, "nome": f.nome, "contratos": f.contratos, "valor": f.valor,
             "meses": [[m, n, v] for m, (n, v) in sorted(f.meses.items())]}
            for c, f in sorted(a.fornecedores.items(), key=lambda x: (-x[1].valor, x[0]))[:fornecedores]],
        "pessoas_fisicas": {"contratos": a.pessoas_fisicas.contratos, "valor": a.pessoas_fisicas.valor_contratos,
                            "meses": [[m, x.contratos, x.valor_contratos]
                                      for m, x in sorted(a.pessoas_fisicas_mes.items())]},
        "recentes": [
            {"data": dia, "chave": p["chave"], "orgao": _nome_orgao(painel, p["orgao"]),
             "modalidade": MODALIDADES.get(p["modalidade"]), "objeto": p["objeto"],
             "valor_estimado": p["valor_estimado"], "situacao": p["situacao"], "link": link_pncp(p["chave"]),
             "a_conferir": conferir}
            for dia, p, conferir in reversed(a.recentes)],
        "contratos_recentes": [
            {"data": dia, "chave": c["chave"], "orgao": _nome_orgao(painel, c["orgao"]),
             "fornecedor": c["fornecedor_nome"] if c["fornecedor_cnpj"] else None,
             "fornecedor_cnpj": c["fornecedor_cnpj"], "tipo_pessoa": c["tipo_pessoa"], "valor": c["valor_global"],
             "instrumento": c["instrumento"], "objeto": c["objeto"], "link": link_pncp(c["chave"]),
             "a_conferir": conferir}
            for dia, c, conferir in reversed(a.contratos_recentes)],
        "a_conferir": [
            {"data": dia, "tipo": tipo, "chave": x["chave"], "orgao": _nome_orgao(painel, x["orgao"]),
             "fornecedor": x["fornecedor_nome"] if tipo == "contrato" and x["fornecedor_cnpj"] else None,
             "fornecedor_cnpj": x["fornecedor_cnpj"] if tipo == "contrato" else None,
             "valor": x["valor_estimado"] if tipo == "processo" else x["valor_global"],
             "objeto": x["objeto"], "link": link_pncp(x["chave"])}
            for dia, tipo, x in reversed(a.a_conferir)],
    }


def ente_para_json(codigo: str, a: Acumulador, painel: Painel, cadastro: Cadastro, gerado_em: str) -> dict:
    """Um ente no arquivo do grupo dele (``contratacoes/ente/<grupo>.json.gz``); o de um estado traz a tabela dos
    municípios."""
    ente = cadastro.get(codigo)
    saida = {
        "versao": 1, "tipo": "contratacoes-ente", "gerado_em": gerado_em, "cobertura": painel.cobertura(),
        "ente": {"codigo": codigo, "nome": cadastro.nome(codigo), "uf": uf_do_ente(codigo),
                 "tipo": tipo_do_ente(codigo), "populacao": ente.populacao if ente else None},
        **_secoes(a, painel),
    }
    if tipo_do_ente(codigo) == "estado":
        saida["municipios"] = municipios_da_uf(UFS[codigo], painel, cadastro)
    return saida


def orgao_para_json(cnpj: str, a: Acumulador, painel: Painel, cadastro: Cadastro, gerado_em: str) -> dict:
    """Um órgão no arquivo do grupo dele (``contratacoes/orgao/<grupo>.json.gz``): o mesmo do ente, com o ente a que
    pertence."""
    razao, esfera, ente = (painel.orgaos.get(cnpj) or [None, None, None])[:3]
    secoes = _secoes(a, painel, fornecedores=FORNECEDORES_ORGAO)
    secoes.pop("orgaos")
    return {
        "versao": 1, "tipo": "contratacoes-orgao", "gerado_em": gerado_em, "cobertura": painel.cobertura(),
        "orgao": {"cnpj": cnpj, "nome": razao, "esfera": esfera},
        "ente": ({"codigo": ente, "nome": cadastro.nome(ente), "uf": uf_do_ente(ente), "tipo": tipo_do_ente(ente)}
                 if tipo_do_ente(ente) else None),
        **secoes,
    }


def municipios_da_uf(uf: str, painel: Painel, cadastro: Cadastro) -> list[dict]:
    """Os municípios da UF (os do cadastro e os que publicaram), em ordem de nome, com os totais de cada um."""
    codigos = {e.codigo for e in cadastro.da_uf(uf, so_municipios=True)}
    codigos |= {c for c in painel.entes if tipo_do_ente(c) == "municipio" and uf_do_ente(c) == uf}
    linhas = []
    for c in codigos:
        a = painel.entes.get(c)
        t = a.totais if a else Totais()
        linhas.append({"codigo": c, "nome": cadastro.nome(c), "processos": t.processos,
                       "valor_estimado": t.valor_estimado, "contratos": t.contratos,
                       "valor_contratos": t.valor_contratos, "meses": meses_de_totais(a.meses) if a else []})
    return sorted(linhas, key=lambda x: (x["nome"].casefold(), x["codigo"]))


def orgaos_para_busca(painel: Painel, gerado_em: str) -> dict:
    """``orgaos.json``: todo órgão com publicação no período (CNPJ, razão social, ente e contagens), para a
    busca do portal achar uma entidade pelo nome, como um serviço autônomo de água e esgoto municipal."""
    linhas = []
    for cnpj in sorted(painel.por_orgao):
        t = painel.por_orgao[cnpj].totais
        _, esfera, ente = (painel.orgaos.get(cnpj) or [None, None, None])[:3]
        linhas.append([cnpj, _nome_orgao(painel, cnpj), ente if tipo_do_ente(ente) else None, esfera,
                       t.processos, t.contratos])
    return {"versao": 1, "tipo": "orgaos", "gerado_em": gerado_em,
            "colunas": ["cnpj", "nome", "ente", "esfera", "processos", "contratos"], "orgaos": linhas}


def panorama_para_json(painel: Painel, cadastro: Cadastro, gerado_em: str) -> dict:
    """``contratacoes/panorama.json``: o Brasil, por esfera, por UF (governo do estado e municípios), meses,
    modalidades e os fornecedores pessoa jurídica de maior valor no país."""
    por_uf = {sigla: {"uf": sigla, "estado": Totais(), "municipios": Totais(), "municipios_com_publicacao": 0,
                      "meses": {}} for sigla in sorted(set(UFS.values()))}
    for codigo, a in painel.entes.items():
        tipo, uf = tipo_do_ente(codigo), uf_do_ente(codigo)
        if uf is None:
            continue
        alvo = por_uf[uf]["municipios" if tipo == "municipio" else "estado"]
        alvo.processos += a.totais.processos
        alvo.sem_valor += a.totais.sem_valor
        alvo.valor_estimado = somar(alvo.valor_estimado, a.totais.valor_estimado)
        alvo.contratos += a.totais.contratos
        alvo.valor_contratos = somar(alvo.valor_contratos, a.totais.valor_contratos)
        alvo.a_conferir += a.totais.a_conferir
        if tipo == "municipio" and (a.totais.processos or a.totais.contratos):
            por_uf[uf]["municipios_com_publicacao"] += 1
        coluna = 2 if tipo == "municipio" else 1
        for m, x in a.meses.items():
            por_uf[uf]["meses"].setdefault(m, [m, 0, 0])[coluna] += x.processos
    nomes_esfera = {"F": "União", "E": "Estados", "D": "Distrito Federal", "M": "Municípios", "?": "Não informada"}
    return {
        "versao": 1, "tipo": "contratacoes-panorama", "gerado_em": gerado_em, "cobertura": painel.cobertura(),
        **_secoes(painel.brasil, painel, fornecedores=FORNECEDORES_PANORAMA),
        "esferas": [{"esfera": e, "nome": nomes_esfera.get(e, e), **t.para_json(),
                     "meses": meses_de_totais(painel.esferas_mes.get(e, {}))}
                    for e, t in sorted(painel.esferas.items(), key=lambda x: "FEDM?".find(x[0]))],
        "sem_ente": painel.sem_ente.para_json(),
        "ufs": [{"uf": u["uf"], "estado": u["estado"].para_json(), "municipios": u["municipios"].para_json(),
                 "municipios_com_publicacao": u["municipios_com_publicacao"],
                 "municipios_no_cadastro": len(cadastro.da_uf(u["uf"], so_municipios=True)),
                 "meses": [u["meses"][m] for m in sorted(u["meses"])]}
                for u in por_uf.values()],
        "entes_com_publicacao": len(painel.entes),
    }
