"""Testes da coleta da receita corrente líquida (RREO, Anexo 03) para os grupos de pares."""

import json
from datetime import date, timedelta
from types import SimpleNamespace

from lumen_ingestao.coleta_http import ErroColeta
from lumen_normalizacao.siconfi import normalizar_demonstrativo
from lumen_normalizacao.silver import EscritorSilver
from lumen_painel import comum, rcl
from lumen_painel.cadastro import Cadastro, Ente

SAO_SEPE = "4319604"
HOJE = date(2026, 10, 20)
RREO_COMPLETO = "Relatório Resumido de Execução Orçamentária"
SIMPLIFICADO = "Relatório Resumido de Execução Orçamentária Simplificado"


def _cadastro():
    return Cadastro({SAO_SEPE: Ente(SAO_SEPE, "São Sepé", "RS", "M", 21551),
                     "43": Ente("43", "Rio Grande do Sul", "RS", "E", 11_000_000),
                     "4300000": Ente("4300000", "Sem entrega", "RS", "M", 5_000),
                     "4300001": Ente("4300001", "Sem extrato", "RS", "M", 8_000)})


def _conformidade():
    """Estado da conformidade de RS: o extrato diz o tipo entregue no 6º bimestre; 4300001 fica sem extrato."""
    colunas = ["instituicao", "entregavel", "exercicio", "periodo", "periodicidade", "status", "entregue_em"]
    entrega = lambda tipo: [["Prefeitura", tipo, 2025, 6, "B", "HO", "2026-01-28T10:00:00-03:00"]]  # noqa: E731
    return {"versao": 1, "uf": "RS", "colunas": colunas, "exercicios": [2025, 2026], "entes": {
        SAO_SEPE: {"coleta": {"2025": True}, "entregas": entrega(SIMPLIFICADO)},
        "43": {"coleta": {"2025": True}, "entregas": entrega(RREO_COMPLETO)},
        "4300000": {"coleta": {"2025": True}, "entregas": []},
        "4300001": {"coleta": {"2025": False}, "entregas": []}}}


def test_tipo_pelo_extrato_e_ordem_de_tentativa():
    tipos = rcl.tipos_pelo_extrato(_conformidade(), 2025)
    assert tipos == {SAO_SEPE: rcl.SIMPLIFICADO, "43": rcl.RREO, "4300000": None}
    assert rcl.ordem_de_tentativa(SAO_SEPE, tipos) == (rcl.SIMPLIFICADO, rcl.RREO)
    assert rcl.ordem_de_tentativa("4300000", tipos) == ()
    assert rcl.ordem_de_tentativa("4300001", tipos) == (rcl.RREO, rcl.SIMPLIFICADO)
    assert rcl.tipos_pelo_extrato(None, 2025) == {} and rcl.exercicio_padrao(HOJE) == 2025


def test_coletar_uf_consulta_o_tipo_certo_e_guarda_o_estado(tmp_path, apoio, cfg):
    estado = tmp_path / "estado"
    comum.gravar_json(estado / "conformidade-RS.json.gz", _conformidade(), comprimir=True)
    publica = {SAO_SEPE: rcl.SIMPLIFICADO, "43": rcl.RREO, "4300001": rcl.SIMPLIFICADO}
    base = json.loads((apoio.FIXTURES / "siconfi" / "rreo_anexo03_amostra.json").read_text(encoding="utf-8"))
    chamadas, achados = [], []

    def coletar(c, fonte, janela, **kw):
        assert (fonte, kw["periodo"], kw["anexo"], kw["exercicio"]) == ("siconfi_rreo", 6, "RREO-Anexo 03", 2025)
        chamadas.append((kw["tipo_demonstrativo"], list(kw["entes"])))
        achados.extend(e for e in kw["entes"] if publica.get(e) == kw["tipo_demonstrativo"])
        return SimpleNamespace(falhas=[])

    def normalizar(c, fontes):
        escritor = EscritorSilver(c.silver, "siconfi-1")
        for ente in achados:
            # São Sepé com os valores da fixture; os outros, com o dobro
            fator = 1 if ente == SAO_SEPE else 2
            itens = [{**linha, "cod_ibge": int(ente), "demonstrativo": publica[ente],
                      "valor": linha["valor"] * fator} for linha in base["items"]]
            r = normalizar_demonstrativo(json.dumps({"items": itens}).encode(), fonte_id="siconfi_rreo",
                                         documento_fonte_id=f"doc{ente}")
            escritor.gravar(f"doc{ente}", r.registros)

    r = rcl.coletar_uf(cfg, "rs", _cadastro(), estado, 2025, coletar=coletar, normalizar=normalizar,
                       temporario=tmp_path, hoje=HOJE)
    assert (r.pendentes, r.consultas, r.encontradas, r.sem_dado, r.problemas) == (4, 4, 3, 1, [])
    # 1ª passada: o tipo do extrato (e o completo para quem não tem extrato); 2ª: o outro, só para quem faltou
    assert sorted(chamadas[:2]) == [(rcl.RREO, ["43", "4300001"]), (rcl.SIMPLIFICADO, [SAO_SEPE])]
    assert chamadas[2:] == [(rcl.SIMPLIFICADO, ["4300001"])]
    gravado = comum.ler_json(estado / "rcl-RS.json.gz")
    assert gravado["exercicio"] == 2025 and gravado["entes"]["4300000"] == {"rcl": None, "tentado_em": "2026-10-20"}
    assert gravado["entes"][SAO_SEPE]["rcl"] == 127898463.53
    assert gravado["entes"][SAO_SEPE]["demonstrativo"] == rcl.SIMPLIFICADO
    assert not list(tmp_path.glob("rcl-RS-*"))
    # De novo no mesmo dia: nada pendente. Uma semana depois, o sem entrega volta, mas não é consultado
    assert rcl.coletar_uf(cfg, "RS", _cadastro(), estado, 2025, coletar=coletar, normalizar=normalizar,
                          hoje=HOJE).pendentes == 0
    chamadas.clear()
    depois = rcl.coletar_uf(cfg, "RS", _cadastro(), estado, 2025, coletar=coletar, normalizar=normalizar,
                            hoje=HOJE + timedelta(days=rcl.DIAS_PARA_TENTAR_DE_NOVO + 1))
    assert (depois.pendentes, depois.consultas, chamadas) == (1, 0, [])
    exercicio, entes = rcl.ler_rcl(estado.glob("rcl-*.json.gz"))
    assert exercicio == 2025 and set(entes) == {SAO_SEPE, "43", "4300001"}


def test_coleta_interrompida_vai_nos_problemas(tmp_path, cfg):
    def coletar(c, fonte, janela, **kw):
        raise ErroColeta("SICONFI fora do ar")

    r = rcl.coletar_uf(cfg, "RS", _cadastro(), tmp_path, 2025, coletar=coletar, normalizar=lambda c, f: None,
                       hoje=HOJE)
    assert r.problemas and "coleta interrompida" in r.problemas[0] and r.sem_dado == 4


def test_estado_de_outro_exercicio_recomeça(tmp_path):
    comum.gravar_json(tmp_path / "rcl-RS.json.gz", {"versao": 1, "exercicio": 2024, "entes": {"43": {"rcl": 1.0}}},
                      comprimir=True)
    assert rcl.ler_estado(tmp_path / "rcl-RS.json.gz", 2025)["entes"] == {}
    assert rcl.ler_rcl([tmp_path / "rcl-RS.json.gz"]) == (2024, {"43": {"rcl": 1.0}})
