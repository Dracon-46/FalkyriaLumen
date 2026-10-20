"""Testes da coleta da despesa com pessoal do Executivo (RGF, Anexo 1) para a Conformidade."""

import json
from datetime import date, timedelta
from types import SimpleNamespace

from lumen_ingestao.coleta_http import ErroColeta
from lumen_normalizacao.siconfi import normalizar_demonstrativo
from lumen_normalizacao.silver import EscritorSilver
from lumen_painel import comum, pessoal
from lumen_painel.cadastro import Cadastro, Ente

SAO_SEPE = "4319604"
HOJE = date(2026, 10, 20)
COMPLETO = "Relatório de Gestão Fiscal"
SIMPLIFICADO = "Relatório de Gestão Fiscal Simplificado"


def _cadastro():
    return Cadastro({SAO_SEPE: Ente(SAO_SEPE, "São Sepé", "RS", "M", 21551),
                     "43": Ente("43", "Rio Grande do Sul", "RS", "E", 11_000_000),
                     "4300000": Ente("4300000", "Só a câmara entregou", "RS", "M", 5_000),
                     "4300001": Ente("4300001", "Sem extrato", "RS", "M", 8_000)})


def _conformidade():
    """Extrato de RS: São Sepé com o simplificado semestral; o estado com o completo quadrimestral; 4300000 só com o
    RGF da câmara; 4300001 sem extrato."""
    colunas = ["instituicao", "entregavel", "exercicio", "periodo", "periodicidade", "status", "entregue_em"]
    def rgf(instituicao, tipo, periodo, periodicidade):  # noqa: E306
        return [instituicao, tipo, 2025, periodo, periodicidade, "HO", "2026-01-28T10:00:00-03:00"]
    return {"versao": 1, "uf": "RS", "colunas": colunas, "exercicios": [2025, 2026], "entes": {
        SAO_SEPE: {"coleta": {"2025": True}, "entregas": [
            rgf("Prefeitura Municipal de São Sepé - RS", SIMPLIFICADO, 1, "S"),
            rgf("Prefeitura Municipal de São Sepé - RS", SIMPLIFICADO, 2, "S"),
            rgf("Câmara de Vereadores de São Sepé - RS", SIMPLIFICADO, 2, "S")]},
        "43": {"coleta": {"2025": True}, "entregas": [rgf("Governo do Estado do Rio Grande do Sul", COMPLETO, 3, "Q")]},
        "4300000": {"coleta": {"2025": True}, "entregas": [rgf("Câmara Municipal", COMPLETO, 3, "Q")]},
        "4300001": {"coleta": {"2025": False}, "entregas": []}}}


def _normalizador(apoio, achados):
    """Grava na silver o RGF da fixture para cada ente em ``achados``: São Sepé como veio, os outros com 40%."""
    base = json.loads((apoio.FIXTURES / "siconfi" / "rgf_anexo01_sao_sepe_2025_s2.json").read_text(encoding="utf-8"))

    def normalizar(c, fontes):
        assert fontes == ["siconfi_rgf"]
        escritor = EscritorSilver(c.silver, "siconfi-1")
        for ente in set(achados):
            itens = [{**linha, "cod_ibge": int(ente)} for linha in base["items"]]
            if ente != SAO_SEPE:
                itens = [{**i, "valor": 40.0} if i["cod_conta"] == "DespesaComPessoalTotal"
                         and i["coluna"].startswith("%") else i for i in itens]
            r = normalizar_demonstrativo(json.dumps({"items": itens}).encode(), fonte_id="siconfi_rgf",
                                         documento_fonte_id=f"doc{ente}")
            assert not r.quarentena
            escritor.gravar(f"doc{ente}", r.registros)
    return normalizar


def test_consultas_pelo_extrato():
    esferas = {SAO_SEPE: "M", "43": "E", "4300000": "M", "4300001": "M"}
    assert pessoal.consultas_pelo_extrato(_conformidade(), 2025, esferas) == {
        SAO_SEPE: (pessoal.SIMPLIFICADO, "S"), "43": (pessoal.RGF, "Q"), "4300000": None}
    assert pessoal.consultas_pelo_extrato(None, 2025, esferas) == {}
    assert pessoal.exercicio_padrao(HOJE) == 2025


def test_coletar_uf_le_o_percentual_e_os_limites(tmp_path, apoio, cfg):
    estado = tmp_path / "estado"
    comum.gravar_json(estado / "conformidade-RS.json.gz", _conformidade(), comprimir=True)
    chamadas, achados = [], []
    publica = {SAO_SEPE: (pessoal.SIMPLIFICADO, "S"), "43": (pessoal.RGF, "Q"),
               "4300001": (pessoal.SIMPLIFICADO, "S")}

    def coletar(c, fonte, janela, **kw):
        assert (fonte, kw["anexo"], kw["poder"], kw["exercicio"]) == ("siconfi_rgf", "RGF-Anexo 01", "E", 2025)
        assert kw["periodo"] == pessoal.ULTIMO_PERIODO[kw["periodicidade_rgf"]]
        combinacao = (kw["tipo_demonstrativo"], kw["periodicidade_rgf"])
        chamadas.append((combinacao, sorted(kw["entes"])))
        achados.extend(e for e in kw["entes"] if publica.get(e) == combinacao)
        return SimpleNamespace(falhas=[])

    r = pessoal.coletar_uf(cfg, "rs", _cadastro(), estado, 2025, coletar=coletar,
                           normalizar=_normalizador(apoio, achados), temporario=tmp_path, hoje=HOJE)
    assert (r.pendentes, r.encontradas, r.sem_dado, r.para_depois, r.problemas) == (4, 3, 1, 0, [])
    # 1ª passada: a combinação do extrato (o sem extrato vai com o RGF quadrimestral); 2ª: o simplificado semestral
    assert sorted(chamadas[:2]) == [((pessoal.RGF, "Q"), ["43", "4300001"]), ((pessoal.SIMPLIFICADO, "S"), [SAO_SEPE])]
    assert chamadas[2:] == [((pessoal.SIMPLIFICADO, "S"), ["4300001"])]
    gravado = comum.ler_json(estado / "pessoal-RS.json.gz")
    sepe = gravado["entes"][SAO_SEPE]
    assert (sepe["percentual"], sepe["dtp"], sepe["rcl_ajustada"]) == (48.33, 60635260.4, 125449743.27)
    assert sepe["limites"] == {"alerta": 48.6, "prudencial": 51.3, "maximo": 54.0}
    assert (sepe["demonstrativo"], sepe["periodicidade"], sepe["periodo"]) == (pessoal.SIMPLIFICADO, "S", 2)
    assert gravado["entes"]["4300001"]["demonstrativo"] == pessoal.SIMPLIFICADO
    assert gravado["entes"]["4300000"] == {"percentual": None, "tentado_em": "2026-10-20"}
    assert not list(tmp_path.glob("pessoal-RS-*"))
    # De novo no mesmo dia: nada pendente; uma semana depois, só o que não tinha entregado volta
    assert pessoal.coletar_uf(cfg, "RS", _cadastro(), estado, 2025, coletar=coletar,
                              normalizar=_normalizador(apoio, []), hoje=HOJE).pendentes == 0
    depois = pessoal.coletar_uf(cfg, "RS", _cadastro(), estado, 2025, coletar=coletar,
                                normalizar=_normalizador(apoio, []),
                                hoje=HOJE + timedelta(days=pessoal.DIAS_PARA_TENTAR_DE_NOVO + 1))
    assert (depois.pendentes, depois.consultas) == (1, 0)
    exercicio, entes = pessoal.ler_pessoal(estado.glob("pessoal-*.json.gz"))
    assert exercicio == 2025 and set(entes) == {SAO_SEPE, "43", "4300001"}


def test_prazo_e_coleta_interrompida_deixam_pendente(tmp_path, apoio, cfg, monkeypatch):
    monkeypatch.setattr(pessoal, "TAMANHO_DO_LOTE", 1)
    instantes = iter([0, 0, 120])           # início, antes do 1º lote, antes do 2º (2 minutos depois)

    def coletar(c, fonte, janela, **kw):
        return SimpleNamespace(falhas=[])

    r = pessoal.coletar_uf(cfg, "RS", _cadastro(), tmp_path, 2025, coletar=coletar,
                           normalizar=_normalizador(apoio, []), hoje=HOJE, limite_minutos=1,
                           relogio=lambda: next(instantes))
    # Sem extrato, cada ente tem duas combinações: o prazo para no 2º lote, e nenhum fica marcado como sem dado
    assert (r.consultas, r.encontradas, r.sem_dado, r.para_depois) == (1, 0, 0, 4)

    def falha(c, fonte, janela, **kw):
        raise ErroColeta("SICONFI fora do ar")

    r = pessoal.coletar_uf(cfg, "RS", _cadastro(), tmp_path, 2025, coletar=falha, normalizar=lambda c, f: None,
                           hoje=HOJE)
    assert r.problemas and (r.sem_dado, r.para_depois) == (0, 4)
    assert comum.ler_json(tmp_path / "pessoal-RS.json.gz")["entes"] == {}
    comum.gravar_json(tmp_path / "pessoal-RS.json.gz", {"versao": 1, "exercicio": 2024, "entes": {}}, comprimir=True)
    assert pessoal.ler_estado(tmp_path / "pessoal-RS.json.gz", 2025)["exercicio"] == 2025
