"""Testes do painel operacional (RF-AD-05; ADR-039)."""

from datetime import date, datetime, timedelta, timezone

from lumen_painel import operacao as op
from lumen_painel.comum import uf_do_ente

AGORA = datetime(2026, 10, 19, 15, 0, tzinfo=timezone.utc)


def _execucao(nome: str, horas_atras: float, resultado: str | None, status: str = "completed") -> dict:
    instante = (AGORA - timedelta(hours=horas_atras)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"workflowName": nome, "createdAt": instante, "updatedAt": instante, "status": status,
            "conclusion": resultado or "", "event": "schedule", "url": f"https://exemplo/{nome}/{horas_atras}"}


def test_fluxo_diario_com_falha_e_atraso():
    execucoes = [_execucao("paineis", 24 * 40, "success"),     # fora da janela, mas é o último sucesso
                 _execucao("paineis", 24 * 3, "failure"), _execucao("paineis", 24 * 2, "cancelled"),
                 _execucao("paineis", 24, "timed_out")]
    f = op.resumir_fluxo("paineis", execucoes, AGORA)
    assert (f["execucoes"], f["falhas"], f["canceladas"], f["taxa_falha"]) == (3, 2, 1, 1.0)
    assert f["horas_desde_sucesso"] == 960.0 and f["atrasado"]
    assert f["ultima"]["resultado"] == "timed_out"


def test_fluxo_diario_em_dia_e_fluxo_sob_demanda_nunca_atrasado():
    ok = op.resumir_fluxo("eleicoes-carga", [_execucao("eleicoes-carga", 30, "success"),
                                             _execucao("eleicoes-carga", 6, "failure")], AGORA)
    # 30 h desde o último sucesso: dentro de 24 h mais a tolerância de 12 h
    assert not ok["atrasado"] and ok["taxa_falha"] == 0.5
    manual = op.resumir_fluxo("eleicoes-ao-vivo", [], AGORA)
    assert manual["ultima"] is None and manual["horas_desde_sucesso"] is None and not manual["atrasado"]


def test_resumir_fluxos_so_os_acompanhados_e_todos_eles():
    linhas = op.resumir_fluxos([_execucao("ci", 1, "failure"), _execucao("paineis", 2, "success")], AGORA)
    assert [f["fluxo"] for f in linhas] == list(op.FLUXOS)
    assert next(f for f in linhas if f["fluxo"] == "paineis")["execucoes"] == 1
    # Fluxo diário sem nenhuma execução é atraso
    assert next(f for f in linhas if f["fluxo"] == "contrato-de-fontes")["atrasado"]


def test_pascoa_e_dias_sem_expediente_nacional():
    assert op.pascoa(2026) == date(2026, 4, 5) and op.pascoa(2025) == date(2025, 4, 20)
    for dia in (date(2026, 2, 16), date(2026, 2, 17), date(2026, 4, 3), date(2026, 6, 4),   # móveis de 2026
                date(2026, 11, 20), date(2026, 10, 12), date(2026, 1, 1),
                date(2026, 2, 18), date(2026, 4, 2),                                       # Cinzas, Quinta Santa
                date(2026, 4, 20), date(2026, 6, 5)):                                      # pontes
        assert op.sem_expediente_nacional(dia), dia
    # A quinta antes do feriado de sexta (20/11/2026) não é ponte; dia comum, também não
    assert not op.sem_expediente_nacional(date(2026, 11, 19)) and not op.sem_expediente_nacional(date(2026, 10, 19))


def test_volume_abaixo_do_esperado_e_dia_nao_coletado():
    hoje = date(2026, 10, 19)
    volume = {}
    for n in range(1, 130):
        dia = hoje - timedelta(days=n)
        volume[dia.isoformat()] = {"processos": 1000 if dia.weekday() < 5 else 50, "contratos": 300}
    volume["2026-10-14"]["processos"] = 100        # quarta-feira: um décimo do normal
    volume["2026-10-12"]["processos"] = 30         # feriado: não é alerta
    del volume["2026-10-16"]                       # sexta-feira não coletada
    dias = {d["dia"]: d for d in op.volume_contratacoes(volume, hoje)["dias"]}
    assert len(dias) == op.DIAS_SERIE and max(dias) == "2026-10-18"
    assert dias["2026-10-14"]["alerta"] == "volume abaixo do esperado" and dias["2026-10-14"]["referencia"] == 1000
    assert dias["2026-10-12"]["alerta"] is None and not dias["2026-10-12"]["util"]
    assert dias["2026-10-16"]["alerta"] == "dia não coletado" and dias["2026-10-16"]["processos"] is None
    assert dias["2026-10-18"]["referencia"] is None and dias["2026-10-18"]["alerta"] is None   # domingo


def test_coleta_da_conformidade_por_uf():
    entes = {"4319604": {"coleta": {"2025": True, "2026": False}}, "4300000": {"coleta": {"2025": True}},
             "3550308": {"coleta": {"2026": True}}}
    linhas = op.coleta_conformidade({"RS": "2026-10-19T09:00:00Z", "SP": "2026-10-15T09:00:00Z"}, entes, AGORA,
                                    uf_do_ente)
    rs, sp = linhas
    assert (rs["uf"], rs["entes"], rs["coleta_malsucedida"], rs["horas_desde_coleta"], rs["atrasada"]) == (
        "RS", 2, 1, 6.0, False)
    assert sp["atrasada"] and sp["horas_desde_coleta"] == 102.0


def test_arquivo_com_alertas_do_mais_grave_ao_menos():
    hoje = date(2026, 10, 19)
    volume = {(hoje - timedelta(days=n)).isoformat(): {"processos": 1000, "contratos": 1} for n in range(1, 130)}
    volume["2026-10-14"]["processos"] = 10
    arquivo = op.operacao_para_json(
        execucoes=[_execucao("paineis", 3, "failure")], volume=volume, faltando=["2026-04-10"],
        coletas={"SP": "2026-10-10T00:00:00Z"},
        entes={}, uf_do_ente=uf_do_ente, agora=AGORA, hoje=hoje, gerado_em="2026-10-19T15:00:00Z")
    assert arquivo["tipo"] == "operacao" and arquivo["parametros"]["calibrados"] is False
    tipos = [a["tipo"] for a in arquivo["alertas"]]
    assert tipos == sorted(tipos, key=["fluxo", "volume", "conformidade"].index)
    textos = " | ".join(a["texto"] for a in arquivo["alertas"])
    assert "a última execução falhou" in textos and "PNCP em 14/10/2026: 10 processos" in textos
    assert "Conformidade: extrato de todas as UFs coletado há mais de 36 h (o mais antigo, há 9 dias)" in textos
    assert "PNCP: 1 dia(s) sem coleta antes dos últimos 30 dias (10/04/2026)" in textos
    assert arquivo["contratacoes"]["faltando"] == ["2026-04-10"]
    # Fora do GitHub Actions, sem o arquivo das execuções
    sem = op.operacao_para_json(execucoes=None, volume={}, faltando=[], coletas={}, entes={}, uf_do_ente=uf_do_ente,
                                agora=AGORA, hoje=hoje, gerado_em="x")
    assert sem["fluxos"] is None


def test_conformidade_atrasada_vira_um_alerta_so():
    linhas = [{"uf": uf, "horas_desde_coleta": h, "atrasada": h is None or h > 36} for uf, h in
              (("AC", 100.4), ("AL", 30.0), ("SP", None), ("RS", 40.2))]
    (alerta,) = op.alertas([], {"dias": []}, linhas)
    assert alerta["texto"] == ("Conformidade: extrato de AC, SP, RS coletado há mais de 36 h (o mais antigo, há 4 dias);"
                               " 1 UF(s) nunca coletada(s)")
    assert op.alertas([], {"dias": []}, [linhas[1]]) == []
