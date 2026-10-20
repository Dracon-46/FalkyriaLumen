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
                      "entes_sem_grupo": 2, "exercicio_rcl": None, "entes_com_rcl": 0,
                      "exercicio_despesa": None, "entes_com_despesa": 0, "exercicio_pessoal": None,
                      "entes_com_pessoal": 0}
    assert "despesa" not in avaliacao.entes[codigos[5]]["pares"]
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


def test_despesa_por_funcao_por_habitante_ao_lado_dos_quartis_do_grupo():
    # 16 municípios de 1.000 habitantes: saúde de 1.000 a 16.000 reais por habitante, educação fixa em 500
    codigos = [str(2100000 + i) for i in range(16)]
    cadastro = Cadastro({c: Ente(c, f"Município {c}", "MA", "M", 1_000) for c in codigos})
    despesa = {c: {"total": 1_000.0 * (1000 * (i + 1) + 500), "funcoes": {"10": 1_000.0 * 1000 * (i + 1),
                                                                          "12": 500_000.0}}
               for i, c in enumerate(codigos)}
    despesa[codigos[0]]["funcoes"]["01"] = 70_000.0           # só ele tem a Legislativa, e a soma não bate
    avaliacao = _avaliacao({c: 0.5 for c in codigos})
    gravados = {}
    resumo = pares.acrescentar(avaliacao, cadastro, lambda caminho, dados: gravados.setdefault(caminho, dados),
                               gerado_em="2026-10-20T12:00:00Z", despesa=despesa, exercicio_despesa=2025)
    assert (resumo["exercicio_despesa"], resumo["entes_com_despesa"]) == (2025, 16)
    ultimo = avaliacao.entes[codigos[-1]]["pares"]["despesa"]
    # O que não confere fica fora da distribuição: 15 entes, o mínimo
    assert (ultimo["exercicio"], ultimo["entes_com_dca"], ultimo["confere"]) == (2025, 15, True)
    total, saude, educacao = ultimo["funcoes"]
    assert (total["codigo"], total["nome"], total["por_habitante"]) == ("total", "Despesa total", 16_500.0)
    assert (saude["codigo"], saude["nome"], saude["por_habitante"]) == ("10", "Saúde", 16_000.0)
    assert saude["grupo"] == {"entes": 15, "q1": 5_500.0, "mediana": 9_000.0, "q3": 12_500.0}
    assert educacao["grupo"]["mediana"] == 500.0
    # A Legislativa: só o primeiro a executou, e ele não entra na distribuição; aparece só no bloco dele
    primeiro = avaliacao.entes[codigos[0]]["pares"]["despesa"]
    assert primeiro["confere"] is False
    assert [f["codigo"] for f in primeiro["funcoes"]] == ["total", "10", "12", "01"]
    assert primeiro["funcoes"][-1]["grupo"] is None
    arquivo = gravados[f"conformidade/pares/{avaliacao.entes[codigos[0]]['pares']['grupo']['id']}.json"]
    assert {e["despesa_por_habitante"] for e in arquivo["entes"]} == {1000.0 * (i + 1) + 500 for i in range(16)}


def test_despesa_sem_entes_suficientes_no_grupo_sai_sem_distribuicao():
    codigos = [str(2100000 + i) for i in range(15)]
    cadastro = Cadastro({c: Ente(c, f"Município {c}", "MA", "M", 1_000) for c in codigos})
    despesa = {c: {"total": 2_000.0, "funcoes": {"10": 2_000.0}} for c in codigos[:14]}
    avaliacao = _avaliacao({c: 0.5 for c in codigos})
    pares.acrescentar(avaliacao, cadastro, lambda caminho, dados: None, gerado_em="2026-10-20T12:00:00Z",
                      despesa=despesa, exercicio_despesa=2025)
    sem_dca = avaliacao.entes[codigos[-1]]["pares"]["despesa"]
    assert sem_dca == {"exercicio": 2025, "entes_com_dca": 14, "confere": None, "funcoes": []}
    com_dca = avaliacao.entes[codigos[0]]["pares"]["despesa"]
    assert [(f["codigo"], f["por_habitante"], f["grupo"]) for f in com_dca["funcoes"]] == [
        ("total", 2.0, None), ("10", 2.0, None)]


def test_despesa_com_pessoal_do_ente_e_do_grupo():
    codigos = [str(2100000 + i) for i in range(16)]
    cadastro = Cadastro({c: Ente(c, f"Município {c}", "MA", "M", 1_000) for c in codigos})
    limites = {"alerta": 48.6, "prudencial": 51.3, "maximo": 54.0}
    pessoal = {c: {"percentual": 40.0 + i, "dtp": 1.0, "rcl_ajustada": 2.0, "limites": limites,
                   "demonstrativo": "RGF Simplificado", "periodo": 2, "periodicidade": "S"}
               for i, c in enumerate(codigos[:15])}
    avaliacao = _avaliacao({c: 0.5 for c in codigos})
    gravados = {}
    resumo = pares.acrescentar(avaliacao, cadastro, lambda caminho, dados: gravados.setdefault(caminho, dados),
                               gerado_em="2026-10-20T12:00:00Z", pessoal=pessoal, exercicio_pessoal=2025)
    assert (resumo["exercicio_pessoal"], resumo["entes_com_pessoal"]) == (2025, 15)
    bloco = avaliacao.entes[codigos[14]]["pares"]["pessoal"]
    assert (bloco["exercicio"], bloco["entes_com_rgf"]) == (2025, 15)
    assert bloco["grupo"] == {"entes": 15, "q1": 43.5, "mediana": 47.0, "q3": 50.5}
    assert bloco["ente"]["percentual"] == 54.0 and bloco["ente"]["limites"]["maximo"] == 54.0
    # O ente sem RGF lido leva a distribuição do grupo, sem os próprios números
    assert avaliacao.entes[codigos[15]]["pares"]["pessoal"]["ente"] is None
    arquivo = gravados[f"conformidade/pares/{avaliacao.entes[codigos[0]]['pares']['grupo']['id']}.json"]
    assert {e["codigo"]: e["pessoal_percentual"] for e in arquivo["entes"]}[codigos[15]] is None
    assert "despesa" not in avaliacao.entes[codigos[0]]["pares"]
