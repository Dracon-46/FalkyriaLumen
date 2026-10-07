"""Porte do ente pela população — base do grupo de pares (RF-EN-02).

As faixas são as classes de tamanho da população que o IBGE usa nas suas
pesquisas municipais (MUNIC e afins). São um parâmetro **metodológico**, não
legal: por isso não estão em ``parametros_legais.toml``, mas são versionadas
aqui, e a versão vai junto de todo grupo de pares calculado
(``GrupoPares.criterios``), para que um indício antigo continue reproduzível
depois de uma mudança de faixas (princípio P3).
"""

from __future__ import annotations

VERSAO_FAIXAS = "ibge-classes-tamanho-1"

# (limite superior inclusivo, rótulo). A última faixa não tem limite.
FAIXAS: tuple[tuple[int | None, str], ...] = (
    (5_000, "ate_5_mil"),
    (10_000, "5_a_10_mil"),
    (20_000, "10_a_20_mil"),
    (50_000, "20_a_50_mil"),
    (100_000, "50_a_100_mil"),
    (500_000, "100_a_500_mil"),
    (None, "acima_500_mil"),
)


def classificar_porte(populacao: int | None) -> str | None:
    """Rótulo da faixa, ou None quando a população é desconhecida.

    População desconhecida não vira "pequeno": vira nulo, e o ente fica fora
    dos grupos de pares até a população ser conhecida (DOC-05, princípio 4).
    """
    if populacao is None:
        return None
    if populacao < 0:
        raise ValueError("população negativa")
    for limite, rotulo in FAIXAS:
        if limite is None or populacao <= limite:
            return rotulo
    raise AssertionError("inalcançável")  # pragma: no cover
