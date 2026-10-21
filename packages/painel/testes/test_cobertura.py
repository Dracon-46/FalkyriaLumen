"""Relatório de cobertura por ente e UF (ADR-048)."""

from __future__ import annotations

from lumen_painel import cobertura
from lumen_painel.cadastro import Cadastro, Ente
from lumen_painel.contratacoes import Acumulador, Painel, Totais

CADASTRO = Cadastro({
    "1": Ente("1", "União", None, "F"),
    "43": Ente("43", "Rio Grande do Sul", "RS", "E", 11_000_000),
    "4314902": Ente("4314902", "Porto Alegre", "RS", "M", 1_330_000),
    "4319604": Ente("4319604", "São Sepé", "RS", "M", 23_000),
    "4300034": Ente("4300034", "Aceguá", "RS", "M", 4_800),
    "53": Ente("53", "Distrito Federal", "DF", "D", 2_800_000),
})


def _acumulador(*meses: tuple[str, int, int]) -> Acumulador:
    a = Acumulador()
    for mes, processos, contratos in meses:
        a.meses[mes] = Totais(processos=processos, contratos=contratos)
    return a


def _painel() -> Painel:
    p = Painel(dias=["2021-08-02", "2024-05-10", "2026-10-20"])
    p.entes = {"1": _acumulador(("2021-08", 3, 0)),
               "43": _acumulador(("2024-05", 1, 0), ("2026-10", 0, 2)),
               "4314902": _acumulador(("2021-08", 0, 1), ("2024-05", 5, 5)),
               "4300034": _acumulador(("2026-10", 1, 0), ("2024-05", 0, 0))}     # mês sem nada não conta
    return p


def test_anos_com_publicacao_e_municipio_ate_20_mil():
    assert cobertura.anos_com_publicacao(_painel().entes["43"]) == ["2024", "2026"]
    assert cobertura.anos_com_publicacao(None) == []
    assert [cobertura.ate_20_mil(CADASTRO.get(c)) for c in ("4300034", "4319604", "43")] == [True, False, False]
    assert not cobertura.ate_20_mil(Ente("4399999", "Sem população", "RS", "M"))


def test_arquivo_por_ente_por_uf_e_brasil():
    coleta = {"43": {"2025": True, "2026": True}, "4314902": {"2025": True, "2026": False},
              "4300034": {"2025": False}}
    r = cobertura.montar(_painel(), CADASTRO, coleta, dca={"43", "4314902"}, rgf={"4314902"}, rcl={"4300034"},
                         exercicios={"dca": 2025, "rgf": 2025, "rcl": 2025}, gerado_em="x")
    assert r["tipo"] == "cobertura" and r["colunas"] == cobertura.COLUNAS
    assert r["pncp"] == {"de": "2021-08-02", "ate": "2026-10-20", "anos": ["2021", "2024", "2026"]}
    assert r["siconfi"] == {"extrato": ["2025", "2026"], "dca": 2025, "rgf": 2025, "rcl": 2025}
    assert r["uniao"] == {"pncp": ["2021"]}                                   # a União fica fora das UFs
    linhas = {linha[0]: linha for linha in r["entes"]}
    assert set(linhas) == {"43", "4314902", "4319604", "4300034", "53"}
    assert linhas["4300034"] == ["4300034", True, ["2026"], [], False, False, True]
    assert linhas["4319604"] == ["4319604", False, [], [], False, False, False]   # sem dado também é linha
    rs = next(u for u in r["ufs"] if u["uf"] == "RS")
    assert rs == {"uf": "RS", "entes": 4, "municipios": 3, "ate_20_mil": 1,
                  "pncp": {"2021": 1, "2024": 2, "2026": 2}, "pncp_ate_20_mil": {"2021": 0, "2024": 0, "2026": 1},
                  "extrato": {"2025": 2, "2026": 1}, "dca": 2, "rgf": 1, "rcl": 1}
    assert [u["uf"] for u in r["ufs"]] == ["DF", "RS"]
    assert r["brasil"]["entes"] == 5 and r["brasil"]["pncp"]["2024"] == 2 and r["brasil"]["municipios"] == 3
