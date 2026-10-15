"""Painel de contratações: soma os dias do PNCP guardados no estado em arquivos por ente (UC-01, UC-02).

Para cada ente com alguma publicação no período, o arquivo ``contratacoes/ente/<código>.json`` traz:

- os totais (processos publicados e a soma do valor estimado; contratos e a soma do valor global);
- o mês a mês e a divisão por modalidade de contratação;
- todos os órgãos do ente que publicaram (prefeitura, câmara, secretarias, autarquias, fundações e empresas
  públicas, como um serviço autônomo de água e esgoto), cada um com o próprio arquivo
  ``contratacoes/orgao/<CNPJ>.json``, com as mesmas seções;
- os fornecedores pessoa jurídica com maior valor contratado e, numa linha só, a soma dos contratos com
  pessoa física ou estrangeira, sem nome nem documento (RNF-19 e RNF-20);
- os processos e contratos publicados mais recentemente, com o link de cada um no PNCP;
- no arquivo de um estado, a tabela dos municípios da UF, para navegar.

O ente de cada publicação é o do órgão que publicou (``dia.resumir_dia``): os números de um município são os
dos órgãos municipais, e não os de órgãos estaduais ou federais que ficam nele.

Os valores são os publicados no PNCP, sem correção: valor estimado sigiloso ou zerado conta como processo
sem valor, e um valor digitado errado pelo órgão entra na soma como veio. O painel não ordena entes por
nenhum critério de risco (PUB-07) e não publica indício: só soma o que a fonte publicou.
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
FORNECEDORES = 20
FORNECEDORES_PANORAMA = 30


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

    def processo(self, estimado: float | None) -> None:
        """Conta um processo; estimado ausente ou zero conta como processo sem valor."""
        self.processos += 1
        if not estimado:
            self.sem_valor += 1
        self.valor_estimado = somar(self.valor_estimado, estimado)

    def contrato(self, global_: float | None) -> None:
        """Conta um contrato e soma o valor global."""
        self.contratos += 1
        self.valor_contratos = somar(self.valor_contratos, global_)

    def para_json(self) -> dict:
        """Os totais com os nomes de campo dos feeds."""
        return {"processos": self.processos, "valor_estimado": self.valor_estimado,
                "processos_sem_valor": self.sem_valor, "contratos": self.contratos,
                "valor_contratos": self.valor_contratos}


@dataclass
class Fornecedor:
    """Um fornecedor pessoa jurídica: razão social mais recente, contratos e soma do valor global."""

    nome: str | None = None
    contratos: int = 0
    valor: float = 0.0


@dataclass
class Acumulador:
    """Tudo o que se soma para um ente (ou para o Brasil, no panorama)."""

    totais: Totais = field(default_factory=Totais)
    meses: dict[str, Totais] = field(default_factory=dict)
    modalidades: dict[int | None, Totais] = field(default_factory=dict)
    orgaos: dict[str, Totais] = field(default_factory=dict)
    fornecedores: dict[str, Fornecedor] = field(default_factory=dict)
    pessoas_fisicas: Totais = field(default_factory=Totais)
    recentes: deque = field(default_factory=lambda: deque(maxlen=RECENTES))
    contratos_recentes: deque = field(default_factory=lambda: deque(maxlen=CONTRATOS_RECENTES))

    @classmethod
    def de_orgao(cls) -> "Acumulador":
        """Acumulador de um órgão, com as listas de recentes menores (``RECENTES_ORGAO``)."""
        return cls(recentes=deque(maxlen=RECENTES_ORGAO), contratos_recentes=deque(maxlen=RECENTES_ORGAO))

    def processo(self, dia: str, linha: dict) -> None:
        """Soma um processo (linha do arquivo do dia, já como dicionário)."""
        estimado = linha["valor_estimado"]
        self.totais.processo(estimado)
        self.meses.setdefault(_mes(dia), Totais()).processo(estimado)
        self.modalidades.setdefault(linha["modalidade"], Totais()).processo(estimado)
        if linha["orgao"]:
            self.orgaos.setdefault(linha["orgao"], Totais()).processo(estimado)
        self.recentes.append((dia, linha))

    def contrato(self, dia: str, linha: dict) -> None:
        """Soma um contrato: no fornecedor pessoa jurídica pelo CNPJ, ou na soma anônima das demais pessoas."""
        global_ = linha["valor_global"]
        self.totais.contrato(global_)
        self.meses.setdefault(_mes(dia), Totais()).contrato(global_)
        if linha["orgao"]:
            self.orgaos.setdefault(linha["orgao"], Totais()).contrato(global_)
        cnpj = linha["fornecedor_cnpj"]
        if cnpj:
            f = self.fornecedores.setdefault(cnpj, Fornecedor())
            f.nome = linha["fornecedor_nome"] or f.nome
            f.contratos += 1
            f.valor = somar(f.valor, global_)
        else:
            self.pessoas_fisicas.contrato(global_)
        self.contratos_recentes.append((dia, linha))


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
    orgaos: dict[str, list] = field(default_factory=dict)      # CNPJ → [razão social, esfera, ente]
    dias: list[str] = field(default_factory=list)
    sem_ente: Totais = field(default_factory=Totais)

    def cobertura(self) -> dict:
        """Primeiro e último dia guardados, quantos dias e os que faltam entre eles."""
        if not self.dias:
            return {"de": None, "ate": None, "dias": 0, "faltando": []}
        guardados = set(self.dias)
        inicio, fim = date.fromisoformat(self.dias[0]), date.fromisoformat(self.dias[-1])
        faltando = [(inicio + timedelta(n)).isoformat() for n in range((fim - inicio).days + 1)
                    if (inicio + timedelta(n)).isoformat() not in guardados]
        return {"de": self.dias[0], "ate": self.dias[-1], "dias": len(self.dias), "faltando": faltando}


def somar_dias(arquivos: Iterable[Path]) -> Painel:
    """Lê os arquivos do dia em ordem de data e soma tudo por ente e para o Brasil."""
    painel = Painel()
    for caminho in sorted(arquivos, key=lambda p: p.name):
        dados = ler_dia(caminho)
        dia = dados["dia"]
        painel.dias.append(dia)
        for cnpj, orgao in (dados.get("orgaos") or {}).items():
            painel.orgaos[cnpj] = orgao
        for tipo, metodo in (("processos", "processo"), ("contratos", "contrato")):
            for linha in _linhas(dados, tipo):
                getattr(painel.brasil, metodo)(dia, linha)
                if linha["orgao"]:
                    acumulador = painel.por_orgao.get(linha["orgao"])
                    if acumulador is None:
                        acumulador = painel.por_orgao[linha["orgao"]] = Acumulador.de_orgao()
                    getattr(acumulador, metodo)(dia, linha)
                esfera = (painel.orgaos.get(linha["orgao"]) or [None, None])[1] or "?"
                totais = painel.esferas.setdefault(esfera, Totais())
                ente = linha["ente"]
                if tipo == "processos":
                    totais.processo(linha["valor_estimado"])
                else:
                    totais.contrato(linha["valor_global"])
                if tipo_do_ente(ente) is None:
                    getattr(painel.sem_ente, "processo" if tipo == "processos" else "contrato")(
                        linha["valor_estimado"] if tipo == "processos" else linha["valor_global"])
                    continue
                getattr(painel.entes.setdefault(ente, Acumulador()), metodo)(dia, linha)
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
             "processos": t.processos, "valor_estimado": t.valor_estimado}
            for c, t in sorted(a.modalidades.items(), key=lambda x: (-x[1].processos, x[0] or 0))],
        "orgaos": [
            {"cnpj": c, "nome": _nome_orgao(painel, c), **t.para_json()}
            for c, t in sorted(a.orgaos.items(), key=lambda x: (-x[1].processos, -x[1].contratos, x[0]))[:ORGAOS]],
        "fornecedores": [
            {"cnpj": c, "nome": f.nome, "contratos": f.contratos, "valor": f.valor}
            for c, f in sorted(a.fornecedores.items(), key=lambda x: (-x[1].valor, x[0]))[:fornecedores]],
        "pessoas_fisicas": {"contratos": a.pessoas_fisicas.contratos, "valor": a.pessoas_fisicas.valor_contratos},
        "recentes": [
            {"data": dia, "chave": p["chave"], "orgao": _nome_orgao(painel, p["orgao"]),
             "modalidade": MODALIDADES.get(p["modalidade"]), "objeto": p["objeto"],
             "valor_estimado": p["valor_estimado"], "situacao": p["situacao"], "link": link_pncp(p["chave"])}
            for dia, p in reversed(a.recentes)],
        "contratos_recentes": [
            {"data": dia, "chave": c["chave"], "orgao": _nome_orgao(painel, c["orgao"]),
             "fornecedor": c["fornecedor_nome"] if c["fornecedor_cnpj"] else None,
             "fornecedor_cnpj": c["fornecedor_cnpj"], "tipo_pessoa": c["tipo_pessoa"], "valor": c["valor_global"],
             "instrumento": c["instrumento"], "objeto": c["objeto"], "link": link_pncp(c["chave"])}
            for dia, c in reversed(a.contratos_recentes)],
    }


def ente_para_json(codigo: str, a: Acumulador, painel: Painel, cadastro: Cadastro, gerado_em: str) -> dict:
    """O arquivo ``contratacoes/ente/<código>.json`` de um ente; o de um estado traz a tabela dos municípios."""
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
    """O arquivo ``contratacoes/orgao/<CNPJ>.json`` de um órgão: o mesmo do ente, com o ente a que pertence."""
    razao, esfera, ente = (painel.orgaos.get(cnpj) or [None, None, None])[:3]
    secoes = _secoes(a, painel)
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
        t = painel.entes[c].totais if c in painel.entes else Totais()
        linhas.append({"codigo": c, "nome": cadastro.nome(c), "processos": t.processos,
                       "valor_estimado": t.valor_estimado, "contratos": t.contratos,
                       "valor_contratos": t.valor_contratos})
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
    por_uf = {sigla: {"uf": sigla, "estado": Totais(), "municipios": Totais(), "municipios_com_publicacao": 0}
              for sigla in sorted(set(UFS.values()))}
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
        if tipo == "municipio" and (a.totais.processos or a.totais.contratos):
            por_uf[uf]["municipios_com_publicacao"] += 1
    nomes_esfera = {"F": "União", "E": "Estados", "D": "Distrito Federal", "M": "Municípios", "?": "Não informada"}
    return {
        "versao": 1, "tipo": "contratacoes-panorama", "gerado_em": gerado_em, "cobertura": painel.cobertura(),
        **_secoes(painel.brasil, painel, fornecedores=FORNECEDORES_PANORAMA),
        "esferas": [{"esfera": e, "nome": nomes_esfera.get(e, e), **t.para_json()}
                    for e, t in sorted(painel.esferas.items(), key=lambda x: "FEDM?".find(x[0]))],
        "sem_ente": painel.sem_ente.para_json(),
        "ufs": [{"uf": u["uf"], "estado": u["estado"].para_json(), "municipios": u["municipios"].para_json(),
                 "municipios_com_publicacao": u["municipios_com_publicacao"],
                 "municipios_no_cadastro": len(cadastro.da_uf(u["uf"], so_municipios=True))}
                for u in por_uf.values()],
        "entes_com_publicacao": len(painel.entes),
    }
