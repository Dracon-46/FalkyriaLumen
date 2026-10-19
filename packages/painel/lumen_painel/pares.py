"""Grupo de pares de cada ente na conformidade (ADR-038; UC-06).

Na publicação, depois da avaliação da conformidade, cada ente avaliado ganha o bloco ``pares``:

- **o grupo**: descrição, critérios e, abaixo do mínimo estatístico, a ressalva;
- **a distribuição** da fração entregue no prazo (``resumo.no_prazo``) entre os entes do grupo: quartis e
  mediana.

Ente sem grupo leva o motivo, e a tela omite a comparação dizendo por quê (UC-06, exceção 5a). Cada grupo tem
também o arquivo com os entes que o formam (``conformidade/pares/<id>.json``).

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
from lumen_canonico.pares import VERSAO_PARES, GrupoPares, ResultadoPares, descrever, formar_grupos

from .cadastro import Cadastro
from .comum import uf_do_ente
from .conformidade import Avaliacao

ESFERAS = {"F": Esfera.UNIAO, "E": Esfera.ESTADUAL, "M": Esfera.MUNICIPAL, "D": Esfera.DISTRITAL}
FORA_DO_CADASTRO = "o ente não está no cadastro do SICONFI"


def formar(cadastro: Cadastro, calculado_em: datetime) -> ResultadoPares:
    """Os grupos de pares dos entes do cadastro."""
    entes = [EnteFederativo(id=codigo, codigo_ibge=codigo, nome=e.nome, esfera=ESFERAS.get(e.esfera or ""),
                            uf=e.uf, populacao=e.populacao)
             for codigo, e in cadastro.entes.items()]
    return formar_grupos(entes, calculado_em)


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
            "faixa_populacional": grupo.faixa_populacional, "regiao": grupo.regiao, "entes": grupo.quantidade_entes,
            "abaixo_do_minimo": grupo.abaixo_do_minimo, "criterios": grupo.criterios}


def acrescentar(avaliacao: Avaliacao, cadastro: Cadastro, gravar: Callable[[str, Any], Any], *,
                gerado_em: str) -> dict:
    """Acrescenta ``pares`` aos arquivos dos entes avaliados e grava o arquivo de cada grupo.

    Devolve o resumo para o ``indice.json``: versão das regras, quantos grupos e quantos entes avaliados ficaram
    com e sem grupo.
    """
    resultado = formar(cadastro, datetime.fromisoformat(gerado_em.replace("Z", "+00:00")))

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
        arquivo["pares"] = {"grupo": grupo_para_json(grupo), "no_prazo": distribuicoes[grupo.id]}

    for grupo in resultado.grupos:
        entes = []
        for codigo in grupo.membros:
            ente = cadastro.get(codigo)
            resumo = (avaliacao.entes.get(codigo) or {}).get("resumo") or {}
            entes.append({"codigo": codigo, "nome": cadastro.nome(codigo), "uf": uf_do_ente(codigo),
                          "populacao": ente.populacao if ente else None,
                          "no_prazo": resumo.get("no_prazo"), "avaliaveis": resumo.get("avaliaveis")})
        entes.sort(key=lambda e: (e["nome"].casefold(), e["codigo"]))
        gravar(f"conformidade/pares/{grupo.id}.json", {
            "versao": 1, "tipo": "conformidade-pares", "gerado_em": gerado_em,
            "avaliado_em": avaliacao.hoje.isoformat(), "grupo": grupo_para_json(grupo),
            "no_prazo": distribuicoes[grupo.id], "entes": entes})
    return {"versao": VERSAO_PARES, "grupos": len(resultado.grupos), "entes_com_grupo": com_grupo,
            "entes_sem_grupo": len(avaliacao.entes) - com_grupo}
