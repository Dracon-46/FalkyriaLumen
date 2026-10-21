"""Relatório de cobertura por ente e UF (critério de saída da Fase 1 no DOC-10; ADR-048).

O que o Lumen tem de cada ente do cadastro do SICONFI (estados, Distrito Federal e municípios), num arquivo só,
``cobertura.json``, publicado com os painéis:

- **PNCP:** os anos com ao menos um processo de contratação ou um contrato publicado em nome do ente, desde o
  primeiro dia guardado;
- **SICONFI:** os exercícios com o extrato de entregas coletado e se o ente tem a DCA (despesa por função), o RGF
  (despesa com pessoal) e a RCL do exercício que os grupos de pares usam (ADR-038, ADR-041 e ADR-042).

A soma vai por UF e para o Brasil, e a linha de cada ente deixa a página listar quem não tem um dado numa UF.
O que o PNCP publica sem ente identificado (órgão sem ente no cadastro) vai à parte, com a fração do total e os
``ORGAOS_SEM_ENTE`` órgãos com mais processos: fica no panorama do Brasil, fora das linhas dos entes.
Os municípios com até 20 mil habitantes vão marcados: a Lei 14.133 (art. 176) deu a eles até 1º/4/2027 para
divulgar no PNCP, e até lá podem publicar em diário oficial. Sem publicação no PNCP não quer dizer sem
contratação. A União entra à parte, só com os anos do PNCP.
"""

from __future__ import annotations

from .cadastro import Cadastro, Ente
from .comum import tipo_do_ente, uf_do_ente
from .contratacoes import Acumulador, Painel

LIMITE_ART_176 = 20_000      # habitantes: até aqui, o município tem até 1º/4/2027 para divulgar no PNCP
ORGAOS_SEM_ENTE = 20
COLUNAS = ["codigo", "ate_20_mil", "pncp", "extrato", "dca", "rgf", "rcl"]


def anos_com_publicacao(acumulador: Acumulador | None) -> list[str]:
    """Os anos (``"2024"``) com ao menos um processo ou um contrato no acumulador do ente."""
    if acumulador is None:
        return []
    return sorted({mes[:4] for mes, t in acumulador.meses.items() if t.processos or t.contratos})


def ate_20_mil(ente: Ente) -> bool:
    """Município com até ``LIMITE_ART_176`` habitantes, pela população do cadastro."""
    return (tipo_do_ente(ente.codigo) == "municipio" and ente.populacao is not None
            and ente.populacao <= LIMITE_ART_176)


def sem_ente(painel: Painel) -> dict:
    """O publicado sem ente: os totais, a fração dos processos e do valor estimado do Brasil e os órgãos sem ente
    no cadastro com mais processos (``[CNPJ, razão social, esfera, processos, valor estimado]``)."""
    t, brasil = painel.sem_ente, painel.brasil.totais
    orgaos = [(cnpj, a.totais) for cnpj, a in painel.por_orgao.items()
              if tipo_do_ente((painel.orgaos.get(cnpj) or [None, None, None])[2]) is None]
    orgaos.sort(key=lambda x: (-x[1].processos, -x[1].valor_estimado, x[0]))
    return {
        **t.para_json(),
        "fracao_processos": round(t.processos / brasil.processos, 4) if brasil.processos else None,
        "fracao_valor": round(t.valor_estimado / brasil.valor_estimado, 4) if brasil.valor_estimado else None,
        "orgaos_sem_ente": len(orgaos),
        "orgaos": [[cnpj, (painel.orgaos.get(cnpj) or [None])[0], (painel.orgaos.get(cnpj) or [None, None])[1],
                    x.processos, round(x.valor_estimado, 2)] for cnpj, x in orgaos[:ORGAOS_SEM_ENTE]],
    }


def _totais(anos_pncp: list[str], anos_extrato: list[str]) -> dict:
    """Contagens zeradas de uma UF ou do Brasil."""
    return {"entes": 0, "municipios": 0, "ate_20_mil": 0,
            "pncp": dict.fromkeys(anos_pncp, 0), "pncp_ate_20_mil": dict.fromkeys(anos_pncp, 0),
            "extrato": dict.fromkeys(anos_extrato, 0), "dca": 0, "rgf": 0, "rcl": 0}


def _somar(totais: dict, linha: list) -> None:
    """Soma a linha de um ente (na ordem de ``COLUNAS``) nas contagens."""
    codigo, pequeno, pncp, extrato, dca, rgf, rcl = linha
    totais["entes"] += 1
    totais["municipios"] += tipo_do_ente(codigo) == "municipio"
    totais["ate_20_mil"] += pequeno
    for ano in pncp:
        totais["pncp"][ano] += 1
        totais["pncp_ate_20_mil"][ano] += pequeno
    for ano in extrato:
        totais["extrato"][ano] += 1
    totais["dca"] += dca
    totais["rgf"] += rgf
    totais["rcl"] += rcl


def montar(painel: Painel, cadastro: Cadastro, coleta: dict[str, dict[str, bool]], *, dca, rgf, rcl,
           exercicios: dict[str, int | None], gerado_em: str) -> dict:
    """``cobertura.json``. ``coleta``: por ente, os exercícios do extrato e se a coleta deu certo; ``dca``, ``rgf``
    e ``rcl``: os códigos dos entes com o dado do exercício em ``exercicios`` (as chaves dos ``ler_*``)."""
    cobertura = painel.cobertura()
    anos_pncp = sorted({dia[:4] for dia in painel.dias})
    anos_extrato = sorted({ano for anos in coleta.values() for ano, ok in anos.items() if ok})
    linhas, por_uf, brasil = [], {}, _totais(anos_pncp, anos_extrato)
    for codigo, ente in sorted(cadastro.entes.items()):
        if tipo_do_ente(codigo) not in ("estado", "df", "municipio"):
            continue
        linha = [codigo, ate_20_mil(ente), anos_com_publicacao(painel.entes.get(codigo)),
                 sorted(ano for ano, ok in (coleta.get(codigo) or {}).items() if ok),
                 codigo in dca, codigo in rgf, codigo in rcl]
        linhas.append(linha)
        _somar(por_uf.setdefault(uf_do_ente(codigo), _totais(anos_pncp, anos_extrato)), linha)
        _somar(brasil, linha)
    return {
        "versao": 1, "tipo": "cobertura", "gerado_em": gerado_em,
        "pncp": {"de": cobertura["de"], "ate": cobertura["ate"], "anos": anos_pncp},
        "siconfi": {"extrato": anos_extrato, **exercicios},
        "limite_art_176": LIMITE_ART_176,
        "brasil": brasil,
        "uniao": {"pncp": anos_com_publicacao(painel.entes.get("1"))},
        "sem_ente": sem_ente(painel),
        "ufs": [{"uf": uf, **totais} for uf, totais in sorted(por_uf.items())],
        "colunas": COLUNAS, "entes": linhas,
    }
