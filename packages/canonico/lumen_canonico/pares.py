"""Grupos de pares dos entes federativos (RF-EN-02; DOC-05, ``GrupoPares``).

Um grupo de pares é o conjunto de entes contra o qual um ente é comparado: as
regras que relativizam pela materialidade (família H, E-01, E-03 e outras do
DOC-07) posicionam o ente na distribuição do seu grupo. Esta versão
(``VERSAO_PARES``) forma os grupos assim:

- **Municípios**: porte pela população (``porte.FAIXAS``) e grande região,
  lida do primeiro dígito do código IBGE (1 Norte, 2 Nordeste, 3 Sudeste,
  4 Sul, 5 Centro-Oeste, pela estrutura do próprio código). O campo
  ``regiao`` não serve: cada fonte o escreve de um jeito (o IBGE, ``S`` e
  ``N``; o SICONFI, ``SU`` e ``NO``). Grupo regional com menos de ``MINIMO_ENTES`` municípios cai para o
  grupo nacional do mesmo porte, e o motivo fica nos critérios. Grupo nacional
  que ainda fique abaixo do mínimo é formado assim mesmo, com ressalva
  (``abaixo_do_minimo``), como pede o DOC-05.
- **Estados e Distrito Federal**: um grupo só, com os 27. Por região, nenhum
  grupo chegaria ao mínimo, e as faixas de porte são as dos municípios.
- **União**: sem grupo; não há ente comparável.

- **Capacidade fiscal** (versão 2): todo grupo com ao menos ``MINIMO_PARA_DIVIDIR`` entes com receita
  corrente líquida (RCL) publicada se divide em dois, na mediana da RCL por habitante: até a mediana e acima
  dela, cada metade com ao menos ``MINIMO_ENTES``. O ente do grupo sem RCL publicada fica no grupo inteiro,
  que continua existindo para ele. O grupo dos estados (27) não chega a ser dividido.

Ente sem população ou sem região fica fora, com o motivo, e nunca é posto num
grupo por inferência (DOC-05, princípio 4).

O identificador do grupo vem da versão e da célula (esfera, porte, região e,
na divisão, a metade da RCL), e não dos membros: recalculado com outra
população ou outra RCL, o grupo mantém o id, e os critérios e a data
registram o cálculo (princípio P3).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from statistics import median

from .fato import EnteFederativo, Esfera
from .identidade import id_canonico
from .porte import FAIXAS, VERSAO_FAIXAS, classificar_porte

VERSAO_PARES = "porte-regiao-rcl-1"

# Mínimo de entes para uma comparação estatística: o da regra H-01 do DOC-07
MINIMO_ENTES = 15
# Com RCL publicada: o bastante para as duas metades terem o mínimo
MINIMO_PARA_DIVIDIR = 2 * MINIMO_ENTES

REGIOES = ("N", "NE", "SE", "S", "CO")
NACIONAL = "BR"
ATE_A_MEDIANA, ACIMA_DA_MEDIANA = "ate_a_mediana", "acima_da_mediana"


def regiao_do_codigo(codigo_ibge: str) -> str | None:
    """Grande região do município pelo primeiro dígito do código IBGE de sete dígitos; None se não for um."""
    if len(codigo_ibge) != 7 or not codigo_ibge.isdigit() or codigo_ibge[0] not in "12345":
        return None
    return REGIOES[int(codigo_ibge[0]) - 1]


@dataclass(frozen=True)
class GrupoPares:
    """Conjunto de entes comparáveis, com os critérios que o definiram (tabela ``grupo_pares``).

    ``faixa_populacional`` é nula no grupo dos estados; ``regiao`` é ``BR`` no grupo nacional; ``faixa_rcl`` é
    a metade da RCL por habitante na divisão, e nula no grupo inteiro. ``membros`` são os códigos IBGE, em
    ordem: no grupo nacional de um porte, todos os municípios do porte no país, inclusive os que têm grupo
    regional próprio (os membros são o conjunto de comparação; o grupo de cada ente está em
    ``ResultadoPares.grupo_de``).
    """

    id: str
    esfera: str
    faixa_populacional: str | None
    regiao: str
    membros: tuple[str, ...]
    criterios: dict
    calculado_em: datetime
    faixa_rcl: str | None = None

    @property
    def quantidade_entes(self) -> int:
        """Tamanho do grupo; abaixo de ``MINIMO_ENTES``, a comparação leva ressalva."""
        return len(self.membros)

    @property
    def abaixo_do_minimo(self) -> bool:
        """Se o grupo tem menos entes que o mínimo estatístico."""
        return self.quantidade_entes < MINIMO_ENTES


@dataclass
class ResultadoPares:
    """Os grupos formados, o grupo de cada ente e os entes que ficaram fora, com o motivo."""

    grupos: list[GrupoPares] = field(default_factory=list)
    grupo_de: dict[str, str] = field(default_factory=dict)
    fora: dict[str, str] = field(default_factory=dict)

    def grupo(self, codigo_ibge: str) -> GrupoPares | None:
        """O grupo do ente, ou None se ele ficou fora."""
        gid = self.grupo_de.get(codigo_ibge)
        return next((g for g in self.grupos if g.id == gid), None)


def _grupo(esfera: str, faixa: str | None, regiao: str, membros: Iterable[str], calculado_em: datetime, *,
           rcl, motivo: str | None = None, faixa_rcl: str | None = None) -> GrupoPares:
    """Monta o grupo, com o id derivado da versão e da célula e os critérios do cálculo."""
    criterios = {"versao": VERSAO_PARES, "minimo_entes": MINIMO_ENTES, "esfera": esfera,
                 "faixa_populacional": faixa, "versao_faixas": VERSAO_FAIXAS if faixa else None,
                 "regiao": regiao, "receita_corrente_liquida": rcl}
    if motivo:
        criterios["motivo"] = motivo
    return GrupoPares(
        id=id_canonico("grupo_pares", VERSAO_PARES, esfera, faixa or "-", regiao, faixa_rcl or "-"),
        esfera=esfera, faixa_populacional=faixa, regiao=regiao, membros=tuple(sorted(membros)),
        criterios=criterios, calculado_em=calculado_em, faixa_rcl=faixa_rcl)


def _formar(resultado: ResultadoPares, esfera: str, faixa: str | None, regiao: str, membros: list[str],
            atribuidos: list[str], calculado_em: datetime, rcl: dict[str, float], exercicio_rcl: int | None,
            motivo: str | None = None) -> None:
    """Forma o grupo de uma célula e atribui os ``atribuidos`` a ele ou, na divisão pela RCL, às metades."""
    com_rcl = [m for m in membros if m in rcl]
    if len(com_rcl) < MINIMO_PARA_DIVIDIR:
        uso = (f"não usada: {len(com_rcl)} ente(s) do grupo com RCL de {exercicio_rcl} publicada, menos que os "
               f"{MINIMO_PARA_DIVIDIR} para dividir" if rcl else "não usada: RCL dos entes não disponível")
        grupo = _grupo(esfera, faixa, regiao, membros, calculado_em, rcl=uso, motivo=motivo)
        resultado.grupos.append(grupo)
        resultado.grupo_de.update(dict.fromkeys(atribuidos, grupo.id))
        return
    mediana = median(rcl[m] for m in com_rcl)
    metades = {ATE_A_MEDIANA: [m for m in com_rcl if rcl[m] <= mediana],
               ACIMA_DA_MEDIANA: [m for m in com_rcl if rcl[m] > mediana]}
    base = {"exercicio": exercicio_rcl, "mediana_por_habitante": round(mediana, 2), "entes_com_rcl": len(com_rcl)}
    for chave, lista in metades.items():
        grupo = _grupo(esfera, faixa, regiao, lista, calculado_em, motivo=motivo, faixa_rcl=chave,
                       rcl={**base, "faixa": chave})
        resultado.grupos.append(grupo)
        da_metade = set(lista)
        resultado.grupo_de.update({a: grupo.id for a in atribuidos if a in da_metade})
    sem = [a for a in atribuidos if a not in rcl]
    if sem:
        inteiro = _grupo(esfera, faixa, regiao, membros, calculado_em, motivo=motivo,
                         rcl={**base, "faixa": None, "uso": "grupo inteiro, para os entes sem RCL publicada"})
        resultado.grupos.append(inteiro)
        resultado.grupo_de.update(dict.fromkeys(sem, inteiro.id))


def formar_grupos(entes: Iterable[EnteFederativo], calculado_em: datetime,
                  rcl_por_habitante: dict[str, float] | None = None,
                  exercicio_rcl: int | None = None) -> ResultadoPares:
    """Forma os grupos de pares dos entes (regras no topo do módulo).

    ``rcl_por_habitante`` é a RCL do ``exercicio_rcl`` dividida pela população, por código IBGE; sem ela, os
    grupos não se dividem. O porte é recalculado da população, e não lido do campo ``porte``, para que grupo e
    faixas venham sempre da mesma versão de ``porte.FAIXAS``.
    """
    rcl = rcl_por_habitante or {}
    resultado = ResultadoPares()
    estados: list[str] = []
    por_celula: dict[tuple[str, str], list[str]] = defaultdict(list)
    por_porte: dict[str, list[str]] = defaultdict(list)
    for ente in entes:
        codigo = ente.codigo_ibge
        if ente.esfera is Esfera.UNIAO:
            resultado.fora[codigo] = "a União não tem entes comparáveis"
        elif ente.esfera in (Esfera.ESTADUAL, Esfera.DISTRITAL):
            estados.append(codigo)
        elif ente.esfera is not Esfera.MUNICIPAL:
            resultado.fora[codigo] = "esfera desconhecida"
        elif (faixa := classificar_porte(ente.populacao)) is None:
            resultado.fora[codigo] = "população desconhecida"
        elif (regiao := regiao_do_codigo(codigo)) is None:
            resultado.fora[codigo] = "código IBGE de município inválido"
        else:
            por_celula[(faixa, regiao)].append(codigo)
            por_porte[faixa].append(codigo)

    if estados:
        _formar(resultado, "estadual", None, NACIONAL, estados, estados, calculado_em, rcl, exercicio_rcl)

    for _, faixa in FAIXAS:
        pequenas: list[str] = []
        for regiao in REGIOES:
            membros = por_celula.get((faixa, regiao))
            if not membros:
                continue
            if len(membros) >= MINIMO_ENTES:
                _formar(resultado, "municipal", faixa, regiao, membros, membros, calculado_em, rcl, exercicio_rcl)
            else:
                pequenas.extend(membros)
        if pequenas:
            _formar(resultado, "municipal", faixa, NACIONAL, por_porte[faixa], pequenas, calculado_em, rcl,
                    exercicio_rcl,
                    motivo=f"grupo regional abaixo de {MINIMO_ENTES} municípios: comparação com o porte no país")
    return resultado


ROTULOS_FAIXA = {
    "ate_5_mil": "até 5 mil habitantes",
    "5_a_10_mil": "de 5 mil a 10 mil habitantes",
    "10_a_20_mil": "de 10 mil a 20 mil habitantes",
    "20_a_50_mil": "de 20 mil a 50 mil habitantes",
    "50_a_100_mil": "de 50 mil a 100 mil habitantes",
    "100_a_500_mil": "de 100 mil a 500 mil habitantes",
    "acima_500_mil": "acima de 500 mil habitantes",
}
NOMES_REGIAO = {"N": "do Norte", "NE": "do Nordeste", "SE": "do Sudeste", "S": "do Sul", "CO": "do Centro-Oeste",
                NACIONAL: "de todo o país"}


ROTULOS_RCL = {ATE_A_MEDIANA: "com RCL por habitante até a mediana do grupo",
               ACIMA_DA_MEDIANA: "com RCL por habitante acima da mediana do grupo"}


def descrever(grupo: GrupoPares) -> str:
    """O grupo em palavras, para a tela: "Municípios de 20 mil a 50 mil habitantes do Sul, com RCL por habitante
    acima da mediana do grupo"."""
    texto = ("Estados e Distrito Federal" if grupo.esfera == "estadual" else
             f"Municípios {ROTULOS_FAIXA[grupo.faixa_populacional]} {NOMES_REGIAO[grupo.regiao]}")
    return f"{texto}, {ROTULOS_RCL[grupo.faixa_rcl]}" if grupo.faixa_rcl else texto
