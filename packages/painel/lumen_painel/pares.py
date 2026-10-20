"""Grupo de pares de cada ente na conformidade (ADR-038; UC-06).

Na publicação, depois da avaliação da conformidade, cada ente avaliado ganha o bloco ``pares``:

- **o grupo**: descrição, critérios e, abaixo do mínimo estatístico, a ressalva;
- **a distribuição** da fração entregue no prazo (``resumo.no_prazo``) entre os entes do grupo: quartis e
  mediana.

Ente sem grupo leva o motivo, e a tela omite a comparação dizendo por quê (UC-06, exceção 5a). Cada grupo tem
também o arquivo com os entes que o formam (``conformidade/pares/<id>.json``).

Com os estados da RCL (``rcl-<UF>.json.gz``), os grupos se dividem pela RCL por habitante (versão 2) e o
bloco do ente leva a RCL dele, com o exercício e o tipo do RREO de onde veio.

Com os estados da despesa por função (``despesa-funcao-<UF>.json.gz``, a DCA do exercício), o bloco leva também
``despesa``: o total e cada função por habitante do ente, ao lado dos quartis do grupo (RF-PU-05). A
distribuição só sai com ao menos ``MINIMO_ENTES`` entes do grupo com a DCA lida e somando o total; a função que
o ente não executou conta como zero.

É comparação, não sinalização. A posição de um ente no grupo é contexto, como o resto do painel (ADR-028);
indício só pelas regras do DOC-07, depois da calibração. Os grupos são formados sobre o cadastro do SICONFI,
com a população do exercício que ele informa.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Callable

from lumen_mercado.referencia import quantil

from lumen_canonico.fato import EnteFederativo, Esfera
from lumen_canonico.pares import MINIMO_ENTES, VERSAO_PARES, GrupoPares, ResultadoPares, descrever, formar_grupos

from .cadastro import Cadastro
from .comum import uf_do_ente
from .conformidade import Avaliacao
from .despesa_funcao import FUNCOES, confere

ESFERAS = {"F": Esfera.UNIAO, "E": Esfera.ESTADUAL, "M": Esfera.MUNICIPAL, "D": Esfera.DISTRITAL}
FORA_DO_CADASTRO = "o ente não está no cadastro do SICONFI"
TOTAL = "total"
NOME_DO_TOTAL = "Despesa total"


def rcl_por_habitante(cadastro: Cadastro, rcl: dict[str, dict]) -> dict[str, float]:
    """A RCL dividida pela população do cadastro, por código IBGE; ente sem população fica de fora."""
    saida = {}
    for codigo, registro in rcl.items():
        ente = cadastro.get(codigo)
        if ente and ente.populacao:
            saida[codigo] = registro["rcl"] / ente.populacao
    return saida


def despesa_por_habitante(cadastro: Cadastro, despesa: dict[str, dict]) -> dict[str, dict[str, float]]:
    """Por código IBGE, o total (``TOTAL``) e cada função da ``FUNCOES`` divididos pela população do cadastro.

    Ente sem população fica de fora; a função que o ente não executou vale zero.
    """
    saida = {}
    for codigo, registro in despesa.items():
        ente = cadastro.get(codigo)
        if ente and ente.populacao:
            funcoes = registro.get("funcoes") or {}
            saida[codigo] = {TOTAL: registro["total"] / ente.populacao,
                             **{f: funcoes.get(f, 0.0) / ente.populacao for f in FUNCOES}}
    return saida


def distribuicoes_de_despesa(membros: list[str], por_habitante: dict[str, dict[str, float]],
                             despesa: dict[str, dict]) -> tuple[int, dict[str, dict] | None]:
    """Quantos membros têm a DCA que confere e, com ao menos ``MINIMO_ENTES``, a distribuição de cada conta.

    Fica de fora a função que nenhum desses membros executou.
    """
    validos = [m for m in membros if m in por_habitante and confere(despesa[m])]
    if len(validos) < MINIMO_ENTES:
        return len(validos), None
    saida = {}
    for conta in (TOTAL, *FUNCOES):
        valores = [por_habitante[m][conta] for m in validos]
        if any(valores):
            saida[conta] = distribuicao(valores)
    return len(validos), saida


def despesa_do_ente(codigo: str, exercicio: int | None, despesa: dict[str, dict],
                    por_habitante: dict[str, dict[str, float]], entes_com_dca: int,
                    distribuicoes: dict[str, dict] | None) -> dict:
    """O bloco ``despesa`` do ente: o total e as funções com valor do ente ou do grupo, os quartis ao lado.

    Ordem: o total e as funções pela mediana do grupo, da maior para a menor (sem distribuição, pelo valor do ente).
    """
    bloco = {"exercicio": exercicio, "entes_com_dca": entes_com_dca, "confere": None, "funcoes": []}
    if codigo not in despesa:
        return bloco
    registro, proprio = despesa[codigo], por_habitante.get(codigo) or {}
    bloco["confere"] = confere(registro)
    linhas = []
    for conta in (TOTAL, *FUNCOES):
        valor = registro["total"] if conta == TOTAL else (registro.get("funcoes") or {}).get(conta, 0.0)
        grupo = (distribuicoes or {}).get(conta)
        if conta != TOTAL and not valor and not (grupo and grupo["mediana"]):
            continue
        linhas.append({"codigo": conta, "nome": NOME_DO_TOTAL if conta == TOTAL else FUNCOES[conta],
                       "valor": round(valor, 2),
                       "por_habitante": round(proprio[conta], 2) if conta in proprio else None,
                       "grupo": grupo})
    if distribuicoes:
        linhas[1:] = sorted(linhas[1:], key=lambda linha: -((linha["grupo"] or {}).get("mediana") or 0))
    else:
        linhas[1:] = sorted(linhas[1:], key=lambda linha: -linha["valor"])
    bloco["funcoes"] = linhas
    return bloco


def formar(cadastro: Cadastro, calculado_em: datetime, rcl: dict[str, dict] | None = None,
           exercicio_rcl: int | None = None) -> ResultadoPares:
    """Os grupos de pares dos entes do cadastro; com a ``rcl`` do ``exercicio_rcl``, na versão que divide por ela."""
    entes = [EnteFederativo(id=codigo, codigo_ibge=codigo, nome=e.nome, esfera=ESFERAS.get(e.esfera or ""),
                            uf=e.uf, populacao=e.populacao)
             for codigo, e in cadastro.entes.items()]
    return formar_grupos(entes, calculado_em, rcl_por_habitante(cadastro, rcl or {}), exercicio_rcl)


def distribuicao(valores: list[float]) -> dict | None:
    """Quantos valores, quartis e mediana, com quatro casas; ``None`` sem nenhum valor."""
    if not valores:
        return None
    ordenados = sorted(Decimal(str(v)) for v in valores)
    return {"entes": len(ordenados),
            **{nome: float(round(quantil(ordenados, q), 4))
               for nome, q in (("q1", "0.25"), ("mediana", "0.5"), ("q3", "0.75"))}}


def grupo_para_json(grupo: GrupoPares) -> dict:
    """O grupo como vai no arquivo do ente e no do grupo: descrição, célula, tamanho, ressalva e critérios."""
    return {"id": grupo.id, "descricao": descrever(grupo), "esfera": grupo.esfera,
            "faixa_populacional": grupo.faixa_populacional, "regiao": grupo.regiao, "faixa_rcl": grupo.faixa_rcl,
            "entes": grupo.quantidade_entes, "abaixo_do_minimo": grupo.abaixo_do_minimo, "criterios": grupo.criterios}


def acrescentar(avaliacao: Avaliacao, cadastro: Cadastro, gravar: Callable[[str, Any], Any], *,
                gerado_em: str, rcl: dict[str, dict] | None = None, exercicio_rcl: int | None = None,
                despesa: dict[str, dict] | None = None, exercicio_despesa: int | None = None) -> dict:
    """Acrescenta ``pares`` aos arquivos dos entes avaliados e grava o arquivo de cada grupo.

    ``rcl`` é a de ``rcl.ler_rcl`` e ``despesa``, a de ``despesa_funcao.ler_despesas``. Devolve o resumo para o
    ``indice.json``: versão das regras, quantos grupos, quantos entes avaliados ficaram com e sem grupo, e o
    exercício e a quantidade de RCL e de DCA usadas.
    """
    rcl, despesa = rcl or {}, despesa or {}
    resultado = formar(cadastro, datetime.fromisoformat(gerado_em.replace("Z", "+00:00")), rcl, exercicio_rcl)
    por_habitante = rcl_por_habitante(cadastro, rcl)
    despesa_hab = despesa_por_habitante(cadastro, despesa)
    despesa_grupos = {g.id: distribuicoes_de_despesa(g.membros, despesa_hab, despesa) for g in resultado.grupos}

    def rcl_do_ente(codigo: str) -> dict | None:
        if codigo not in rcl:
            return None
        return {"exercicio": exercicio_rcl, "valor": rcl[codigo]["rcl"],
                "por_habitante": round(por_habitante[codigo], 2) if codigo in por_habitante else None,
                "demonstrativo": rcl[codigo].get("demonstrativo")}

    def no_prazo(codigo: str) -> float | None:
        arquivo = avaliacao.entes.get(codigo)
        return arquivo["resumo"]["no_prazo"] if arquivo else None

    distribuicoes = {g.id: distribuicao([v for m in g.membros if (v := no_prazo(m)) is not None])
                     for g in resultado.grupos}
    com_grupo = 0
    for codigo, arquivo in avaliacao.entes.items():
        grupo = resultado.grupo(codigo)
        if grupo is None:
            arquivo["pares"] = {"grupo": None, "motivo": resultado.fora.get(codigo, FORA_DO_CADASTRO)}
            continue
        com_grupo += 1
        arquivo["pares"] = {"grupo": grupo_para_json(grupo), "no_prazo": distribuicoes[grupo.id],
                            "rcl": rcl_do_ente(codigo)}
        if despesa:
            arquivo["pares"]["despesa"] = despesa_do_ente(codigo, exercicio_despesa, despesa, despesa_hab,
                                                          *despesa_grupos[grupo.id])

    for grupo in resultado.grupos:
        entes = []
        for codigo in grupo.membros:
            ente = cadastro.get(codigo)
            resumo = (avaliacao.entes.get(codigo) or {}).get("resumo") or {}
            entes.append({"codigo": codigo, "nome": cadastro.nome(codigo), "uf": uf_do_ente(codigo),
                          "populacao": ente.populacao if ente else None,
                          "rcl_por_habitante": round(por_habitante[codigo], 2) if codigo in por_habitante else None,
                          "despesa_por_habitante": (round(despesa_hab[codigo][TOTAL], 2)
                                                    if codigo in despesa_hab else None),
                          "no_prazo": resumo.get("no_prazo"), "avaliaveis": resumo.get("avaliaveis")})
        entes.sort(key=lambda e: (e["nome"].casefold(), e["codigo"]))
        gravar(f"conformidade/pares/{grupo.id}.json", {
            "versao": 1, "tipo": "conformidade-pares", "gerado_em": gerado_em,
            "avaliado_em": avaliacao.hoje.isoformat(), "grupo": grupo_para_json(grupo),
            "no_prazo": distribuicoes[grupo.id], "entes": entes})
    return {"versao": VERSAO_PARES, "grupos": len(resultado.grupos), "entes_com_grupo": com_grupo,
            "entes_sem_grupo": len(avaliacao.entes) - com_grupo, "exercicio_rcl": exercicio_rcl,
            "entes_com_rcl": len(por_habitante), "exercicio_despesa": exercicio_despesa,
            "entes_com_despesa": len(despesa_hab)}
