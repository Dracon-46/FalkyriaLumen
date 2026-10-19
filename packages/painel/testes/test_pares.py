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
    assert resumo == {"versao": "porte-regiao-1", "grupos": 1, "entes_com_grupo": MINIMO_ENTES,
                      "entes_sem_grupo": 2}
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
