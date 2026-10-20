"""Testes do grupo de pares na conformidade (ADR-038)."""

from datetime import date

from lumen_canonico.pares import MINIMO_ENTES
from lumen_painel import pares
from lumen_painel.cadastro import Cadastro, Ente
from lumen_painel.conformidade import Avaliacao


def _avaliacao(no_prazo: dict[str, float | None]) -> Avaliacao:
    a = Avaliacao(date(2026, 10, 19))
    for codigo, valor in no_prazo.items():
        a.entes[codigo] = {"ente": {"codigo": codigo}, "resumo": {"no_prazo": valor, "avaliaveis": 10}}
    return a


def test_distribuicao_com_quartis_e_mediana():
    assert pares.distribuicao([]) is None
    assert pares.distribuicao([1.0, 0.5, 0.75, 0.25, 0.0]) == {"entes": 5, "q1": 0.25, "mediana": 0.5, "q3": 0.75}


def test_cada_ente_avaliado_recebe_o_grupo_e_cada_grupo_tem_arquivo():
    # 15 municípios pequenos do Nordeste formam um grupo regional; a União e um código fora do cadastro, não
    codigos = [str(2100000 + i) for i in range(MINIMO_ENTES)]
    cadastro = Cadastro({c: Ente(c, f"Município {c}", "MA", "M", 3_000) for c in codigos}
                        | {"1": Ente("1", "União", None, "F")})
    valores = {c: i / 14 for i, c in enumerate(codigos)} | {codigos[0]: None, "1": 0.5, "2999999": 1.0}
    avaliacao = _avaliacao(valores)
    gravados = {}
    resumo = pares.acrescentar(avaliacao, cadastro, lambda caminho, dados: gravados.setdefault(caminho, dados),
                               gerado_em="2026-10-19T12:00:00Z")
    assert resumo == {"versao": "porte-regiao-rcl-1", "grupos": 1, "entes_com_grupo": MINIMO_ENTES,
                      "entes_sem_grupo": 2, "exercicio_rcl": None, "entes_com_rcl": 0}
    bloco = avaliacao.entes[codigos[5]]["pares"]
    assert bloco["grupo"]["descricao"] == "Municípios até 5 mil habitantes do Nordeste"
    assert bloco["grupo"]["entes"] == MINIMO_ENTES and not bloco["grupo"]["abaixo_do_minimo"]
    # O ente sem fração avaliável fica de fora da distribuição, mas continua no grupo
    assert bloco["no_prazo"]["entes"] == MINIMO_ENTES - 1
    assert avaliacao.entes["1"]["pares"] == {"grupo": None, "motivo": "a União não tem entes comparáveis"}
    assert avaliacao.entes["2999999"]["pares"] == {"grupo": None, "motivo": pares.FORA_DO_CADASTRO}
    (caminho, arquivo), = gravados.items()
    assert caminho == f"conformidade/pares/{bloco['grupo']['id']}.json"
    assert len(arquivo["entes"]) == MINIMO_ENTES and arquivo["entes"][0]["uf"] == "MA"
    assert arquivo["entes"][0]["no_prazo"] is None and arquivo["no_prazo"] == bloco["no_prazo"]



def test_com_rcl_o_grupo_se_divide_e_o_ente_leva_a_rcl_dele():
    codigos = [str(2100000 + i) for i in range(30)]
    cadastro = Cadastro({c: Ente(c, f"Município {c}", "MA", "M", 4_000) for c in codigos})
    rcl = {c: {"rcl": 4_000.0 * (1000 + i), "demonstrativo": "RREO"} for i, c in enumerate(codigos)}
    avaliacao = _avaliacao({c: 0.5 for c in codigos})
    gravados = {}
    resumo = pares.acrescentar(avaliacao, cadastro, lambda caminho, dados: gravados.setdefault(caminho, dados),
                               gerado_em="2026-10-20T12:00:00Z", rcl=rcl, exercicio_rcl=2025)
    assert (resumo["grupos"], resumo["exercicio_rcl"], resumo["entes_com_rcl"]) == (2, 2025, 30)
    bloco = avaliacao.entes[codigos[-1]]["pares"]
    assert bloco["grupo"]["faixa_rcl"] == "acima_da_mediana" and bloco["grupo"]["entes"] == 15
    assert bloco["grupo"]["descricao"].endswith("com RCL por habitante acima da mediana do grupo")
    assert bloco["rcl"] == {"exercicio": 2025, "valor": 4_000.0 * 1029, "por_habitante": 1029.0,
                            "demonstrativo": "RREO"}
    arquivo = gravados[f"conformidade/pares/{bloco['grupo']['id']}.json"]
    assert {e["rcl_por_habitante"] for e in arquivo["entes"]} == {float(1015 + i) for i in range(15)}
