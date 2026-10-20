"""Testes da coleta da despesa por função (DCA, Anexo I-E) para a comparação com os pares."""

import json
from datetime import date, timedelta
from types import SimpleNamespace

from lumen_ingestao.coleta_http import ErroColeta
from lumen_normalizacao.siconfi import normalizar_demonstrativo
from lumen_normalizacao.silver import EscritorSilver
from lumen_painel import comum, despesa_funcao
from lumen_painel.cadastro import Cadastro, Ente

SAO_SEPE = "4319604"
HOJE = date(2026, 10, 20)
DCA = "Balanço Anual (DCA)"


def _cadastro():
    return Cadastro({SAO_SEPE: Ente(SAO_SEPE, "São Sepé", "RS", "M", 21551),
                     "43": Ente("43", "Rio Grande do Sul", "RS", "E", 11_000_000),
                     "4300000": Ente("4300000", "Sem entrega", "RS", "M", 5_000),
                     "4300001": Ente("4300001", "Sem extrato", "RS", "M", 8_000)})


def _conformidade():
    """Estado da conformidade de RS: São Sepé e o estado entregaram a DCA de 2025; 4300001 fica sem extrato."""
    colunas = ["instituicao", "entregavel", "exercicio", "periodo", "periodicidade", "status", "entregue_em"]
    dca = [["Prefeitura", DCA, 2025, 1, "A", "HO", "2026-04-29T10:00:00-03:00"]]
    return {"versao": 1, "uf": "RS", "colunas": colunas, "exercicios": [2025, 2026], "entes": {
        SAO_SEPE: {"coleta": {"2025": True}, "entregas": dca},
        "43": {"coleta": {"2025": True}, "entregas": dca},
        "4300000": {"coleta": {"2025": True}, "entregas": []},
        "4300001": {"coleta": {"2025": False}, "entregas": []}}}


def _dca(apoio):
    return json.loads((apoio.FIXTURES / "siconfi" / "dca_anexo_i_e_sao_sepe_2025.json").read_text(encoding="utf-8"))


def _normalizador(apoio, achados):
    """Grava na silver a DCA da fixture para cada ente em ``achados``: São Sepé como veio, os outros em dobro."""
    base = _dca(apoio)

    def normalizar(c, fontes):
        assert fontes == ["siconfi_dca"]
        escritor = EscritorSilver(c.silver, "siconfi-1")
        for ente in achados:
            fator = 1 if ente == SAO_SEPE else 2
            itens = [{**linha, "cod_ibge": int(ente), "valor": linha["valor"] * fator} for linha in base["items"]]
            r = normalizar_demonstrativo(json.dumps({"items": itens}).encode(), fonte_id="siconfi_dca",
                                         documento_fonte_id=f"doc{ente}")
            assert not r.quarentena
            escritor.gravar(f"doc{ente}", r.registros)
    return normalizar


def test_entregues_pelo_extrato_e_exercicio_padrao():
    assert despesa_funcao.entregues_pelo_extrato(_conformidade(), 2025) == {
        SAO_SEPE: True, "43": True, "4300000": False}
    assert despesa_funcao.entregues_pelo_extrato(None, 2025) == {}
    # A DCA municipal sai até 30 de abril: em abril ainda vale a do ano retrasado
    assert despesa_funcao.exercicio_padrao(HOJE) == 2025
    assert despesa_funcao.exercicio_padrao(date(2027, 4, 30)) == 2025
    assert despesa_funcao.exercicio_padrao(date(2027, 5, 1)) == 2026


def test_coletar_uf_le_as_funcoes_e_guarda_o_estado(tmp_path, apoio, cfg):
    estado = tmp_path / "estado"
    comum.gravar_json(estado / "conformidade-RS.json.gz", _conformidade(), comprimir=True)
    chamadas, achados = [], []

    def coletar(c, fonte, janela, **kw):
        assert (fonte, kw["anexo"], kw["exercicio"]) == ("siconfi_dca", "DCA-Anexo I-E", 2025)
        chamadas.append(list(kw["entes"]))
        achados.extend(e for e in kw["entes"] if e != "4300001")   # o sem extrato não publicou
        return SimpleNamespace(falhas=[])

    r = despesa_funcao.coletar_uf(cfg, "rs", _cadastro(), estado, 2025, coletar=coletar,
                                  normalizar=_normalizador(apoio, achados), temporario=tmp_path, hoje=HOJE)
    # O sem entrega no extrato não é consultado; o sem extrato é
    assert (r.pendentes, r.consultas, r.encontradas, r.sem_dado, r.para_depois, r.problemas) == (4, 3, 2, 2, 0, [])
    assert set(chamadas[0]) == {"43", SAO_SEPE, "4300001"}
    gravado = comum.ler_json(estado / "despesa-funcao-RS.json.gz")
    assert gravado["entes"]["4300000"] == {"total": None, "tentado_em": "2026-10-20"}
    sepe = gravado["entes"][SAO_SEPE]
    # As 19 funções liquidadas de 2025 somam o total ao centavo; as subfunções e a coluna do empenho ficam de fora
    assert sepe["total"] == 138913815.96 and len(sepe["funcoes"]) == 19
    assert sepe["funcoes"]["10"] == 32108759.99 and sepe["funcoes"]["12"] == 36030202.95
    assert despesa_funcao.confere(sepe) and gravado["entes"]["43"]["total"] == 2 * 138913815.96
    assert not list(tmp_path.glob("despesa-funcao-RS-*"))
    # De novo no mesmo dia: nada pendente; uma semana depois, os dois sem dado voltam
    assert despesa_funcao.coletar_uf(cfg, "RS", _cadastro(), estado, 2025, coletar=coletar,
                                     normalizar=_normalizador(apoio, []), hoje=HOJE).pendentes == 0
    depois = despesa_funcao.coletar_uf(cfg, "RS", _cadastro(), estado, 2025, coletar=coletar,
                                       normalizar=_normalizador(apoio, []),
                                       hoje=HOJE + timedelta(days=despesa_funcao.DIAS_PARA_TENTAR_DE_NOVO + 1))
    assert (depois.pendentes, depois.consultas) == (2, 1)
    exercicio, entes = despesa_funcao.ler_despesas(estado.glob("despesa-funcao-*.json.gz"))
    assert exercicio == 2025 and set(entes) == {SAO_SEPE, "43"}


def test_prazo_deixa_os_lotes_seguintes_para_depois(tmp_path, apoio, cfg, monkeypatch):
    monkeypatch.setattr(despesa_funcao, "TAMANHO_DO_LOTE", 1)
    instantes = iter([0, 0, 120])          # início, antes do 1º lote, antes do 2º (2 minutos depois)
    achados = []

    def coletar(c, fonte, janela, **kw):
        achados.extend(kw["entes"])
        return SimpleNamespace(falhas=[])

    r = despesa_funcao.coletar_uf(cfg, "RS", _cadastro(), tmp_path, 2025, coletar=coletar,
                                  normalizar=_normalizador(apoio, achados), hoje=HOJE, limite_minutos=1,
                                  relogio=lambda: next(instantes))
    # Sem extrato, todos seriam consultados; o prazo para depois do primeiro lote
    assert (r.consultas, r.encontradas, r.para_depois) == (1, 1, 3)
    assert len(comum.ler_json(tmp_path / "despesa-funcao-RS.json.gz")["entes"]) == 1


def test_coleta_interrompida_deixa_o_lote_pendente(tmp_path, cfg):
    def coletar(c, fonte, janela, **kw):
        raise ErroColeta("SICONFI fora do ar")

    r = despesa_funcao.coletar_uf(cfg, "RS", _cadastro(), tmp_path, 2025, coletar=coletar,
                                  normalizar=lambda c, f: None, hoje=HOJE)
    assert r.problemas and "coleta interrompida" in r.problemas[0]
    assert (r.sem_dado, r.para_depois) == (0, 4)
    assert comum.ler_json(tmp_path / "despesa-funcao-RS.json.gz")["entes"] == {}


def test_funcoes_que_nao_somam_o_total_nao_conferem(tmp_path):
    assert despesa_funcao.confere({"total": 100.0, "funcoes": {"10": 60.0, "12": 39.5}})
    assert not despesa_funcao.confere({"total": 100.0, "funcoes": {"10": 60.0}})
    assert not despesa_funcao.confere({"total": None, "funcoes": {}})
    comum.gravar_json(tmp_path / "despesa-funcao-RS.json.gz",
                      {"versao": 1, "exercicio": 2024, "entes": {"43": {"total": 1.0, "funcoes": {}}}}, comprimir=True)
    assert despesa_funcao.ler_estado(tmp_path / "despesa-funcao-RS.json.gz", 2025)["entes"] == {}
