"""``lumen painel``: dias a coletar, divisão em blocos e os comandos de ponta a ponta (ADR-028)."""

from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace

import pytest

from lumen_ingestao.coleta_http import ErroColeta
from lumen_orquestracao import cli as cli_lumen
from lumen_orquestracao import etapas
from lumen_painel import cli, comum, despesa_funcao, emendas, pessoal
from lumen_painel import cnpj as base_cnpj
from lumen_painel import conformidade as conf
from lumen_painel import dia as m_dia
from lumen_painel.cadastro import Cadastro, Ente

HOJE = date(2026, 10, 14)


@pytest.fixture(autouse=True)
def ambiente(monkeypatch, tmp_path):
    monkeypatch.setenv("LUMEN_CONTATO", "c@exemplo.org")
    monkeypatch.setenv("LUMEN_DADOS", str(tmp_path / "dados"))
    monkeypatch.setenv("LUMEN_CONFIG", str(tmp_path / "nao-existe.toml"))
    monkeypatch.setattr(cli, "hoje_brasilia", lambda: HOJE)


def test_dias_pedidos_e_partes(tmp_path):
    estado = tmp_path / "e"
    comum.gravar_json(estado / "contratacoes-2026-10-12.json.gz", {}, comprimir=True)
    dias = cli.dias_pedidos(estado, de=None, ate=None, ultimos=3, hoje=HOJE)
    assert dias == [date(2026, 10, 13), date(2026, 10, 11)]                 # sem o dia já guardado, nem hoje
    assert cli.dias_pedidos(estado, de=None, ate=None, ultimos=None, hoje=HOJE, refazer=True)[1] == date(2026, 10, 12)
    assert cli.dias_pedidos(estado, de=date(2026, 10, 1), ate=date(2026, 12, 1), ultimos=None, hoje=HOJE)[0] == \
        date(2026, 10, 13)                                                  # nunca depois de ontem
    blocos = cli.partes([date(2026, 1, d) for d in range(10, 0, -1)], 3)
    assert blocos == [{"de": "2026-01-07", "ate": "2026-01-10", "dias": 4},
                      {"de": "2026-01-03", "ate": "2026-01-06", "dias": 4},
                      {"de": "2026-01-01", "ate": "2026-01-02", "dias": 2}]
    assert cli.partes([], 3) == [] and cli.partes([HOJE], 0) == []


def test_faltando(tmp_path, capsys):
    assert cli.main(["faltando", "--estado", str(tmp_path / "e"), "--de", "2026-10-01", "--partes", "2"]) == 0
    assert json.loads(capsys.readouterr().out) == [{"de": "2026-10-07", "ate": "2026-10-13", "dias": 7},
                                                   {"de": "2026-10-01", "ate": "2026-10-06", "dias": 6}]


def test_comando_contratacoes(tmp_path, monkeypatch, capsys):
    vistos = []

    def coletar_dia(cfg, dia, estado):
        vistos.append(dia)
        r = m_dia.ResultadoDia(dia, gravado=dia != date(2026, 10, 12), processos=5)
        if not r.gravado:
            r.problemas.append("falhou")
        return r

    monkeypatch.setattr(cli, "coletar_dia", coletar_dia)
    codigo = cli.main(["contratacoes", "--estado", str(tmp_path / "e"), "--ultimos", "3"])
    saida = json.loads(capsys.readouterr().out)
    assert codigo == 1 and vistos == [date(2026, 10, 13), date(2026, 10, 12), date(2026, 10, 11)]
    assert (saida["pedidos"], saida["gravados"], saida["nao_gravados"]) == (3, 2, ["2026-10-12"])
    # Prazo vencido antes de começar: nada coletado, tudo pendente
    vistos.clear()
    instantes = iter([0.0, 30.0, 61.0, 61.0])
    monkeypatch.setattr(cli, "relogio", lambda: next(instantes))
    assert cli.main(["contratacoes", "--estado", str(tmp_path / "e"), "--limite-minutos", "1"]) == 0
    assert vistos == [date(2026, 10, 13)] and len(json.loads(capsys.readouterr().out)["pendentes_no_prazo"]) == 2


def test_comando_cadastro(tmp_path, monkeypatch, capsys, apoio):
    def coletar(cfg, fonte, janela, **kw):
        assert fonte == "siconfi_entes"
        return SimpleNamespace(falhas=[], respostas_de_erro=0)

    monkeypatch.setattr(etapas, "coletar", coletar)
    monkeypatch.setattr(etapas, "normalizar", lambda cfg, fontes: apoio.silver_siconfi(cfg.silver))
    # A amostra tem só 5 entes: o comando recusa um cadastro tão pequeno
    assert cli.main(["cadastro", "--estado", str(tmp_path / "e")]) == 1
    assert "só 5" in capsys.readouterr().err
    monkeypatch.setattr(Cadastro, "__len__", lambda self: 5570)
    assert cli.main(["cadastro", "--estado", str(tmp_path / "e")]) == 0
    capsys.readouterr()
    assert Cadastro.ler(tmp_path / "e" / cli.ARQUIVO_CADASTRO).get("4319604").nome == "São Sepé"
    monkeypatch.setattr(etapas, "coletar", lambda *a, **k: SimpleNamespace(falhas=[("u", "x")], respostas_de_erro=0))
    assert cli.main(["cadastro", "--estado", str(tmp_path / "e")]) == 1
    assert "falha" in capsys.readouterr().err


def test_comando_conformidade(tmp_path, monkeypatch, capsys):
    comum.gravar_json(tmp_path / "e" / cli.ARQUIVO_CADASTRO,
                      Cadastro({"43": Ente("43", "Rio Grande do Sul", "RS", "E")}).para_json(), comprimir=True)
    pedidos = []

    def coletar_uf(cfg, uf, cadastro, exercicios, estado):
        pedidos.append((uf, exercicios))
        return conf.ResultadoUf(uf, entes=1, consultas=2, consultas_ok=2, gravado=uf == "RS")

    monkeypatch.setattr(conf, "coletar_uf", coletar_uf)
    assert cli.main(["conformidade", "--estado", str(tmp_path / "e"), "--ufs", "rs, ap"]) == 1
    assert pedidos == [("RS", [2025, 2026]), ("AP", [2025, 2026])]
    assert json.loads(capsys.readouterr().out)["exercicios"] == [2025, 2026]
    assert cli.main(["conformidade", "--estado", str(tmp_path / "e"), "--ufs", "RS", "--exercicios", "2024"]) == 0
    assert pedidos[-1] == ("RS", [2024])


def test_comando_despesa_funcao_divide_o_prazo_entre_as_ufs(tmp_path, monkeypatch, capsys):
    comum.gravar_json(tmp_path / "e" / cli.ARQUIVO_CADASTRO,
                      Cadastro({"43": Ente("43", "Rio Grande do Sul", "RS", "E")}).para_json(), comprimir=True)
    pedidos = []
    instantes = iter([0, 0, 600])        # início; antes de RS; antes de AP (10 minutos depois)

    def coletar_uf(cfg, uf, cadastro, estado, exercicio, *, limite_minutos, relogio):
        pedidos.append((uf, exercicio, limite_minutos))
        return despesa_funcao.ResultadoDespesa(uf, pendentes=3, consultas=2, encontradas=2, para_depois=1,
                                               problemas=["coleta interrompida"] if uf == "AP" else [])

    monkeypatch.setattr(despesa_funcao, "coletar_uf", coletar_uf)
    monkeypatch.setattr(cli, "relogio", lambda: next(instantes))
    assert cli.main(["despesa-funcao", "--estado", str(tmp_path / "e"), "--ufs", "RS,AP",
                     "--limite-minutos", "30"]) == 1
    assert pedidos == [("RS", 2025, 30.0), ("AP", 2025, 20.0)]
    assert json.loads(capsys.readouterr().out)["ufs"][0]["para_depois"] == 1


def test_comando_pessoal(tmp_path, monkeypatch, capsys):
    comum.gravar_json(tmp_path / "e" / cli.ARQUIVO_CADASTRO,
                      Cadastro({"43": Ente("43", "Rio Grande do Sul", "RS", "E")}).para_json(), comprimir=True)
    pedidos = []

    def coletar_uf(cfg, uf, cadastro, estado, exercicio, *, limite_minutos, relogio):
        pedidos.append((uf, exercicio, limite_minutos))
        return pessoal.ResultadoPessoal(uf, pendentes=1, consultas=1, encontradas=1)

    monkeypatch.setattr(pessoal, "coletar_uf", coletar_uf)
    assert cli.main(["pessoal", "--estado", str(tmp_path / "e"), "--ufs", "RS", "--exercicio", "2024"]) == 0
    assert pedidos == [("RS", 2024, None)]
    assert json.loads(capsys.readouterr().out)["ufs"][0]["encontradas"] == 1


def test_publicar_de_ponta_a_ponta(tmp_path, apoio, capsys):
    estado, site = tmp_path / "e", tmp_path / "site"
    s_pncp = apoio.silver_pncp(tmp_path / "sp")
    s_sic = apoio.silver_siconfi(tmp_path / "ss")
    comum.gravar_json(estado / "contratacoes-2026-09-01.json.gz", m_dia.resumir_dia(s_pncp, date(2026, 9, 1)),
                      comprimir=True)
    comum.gravar_json(estado / cli.ARQUIVO_CADASTRO, Cadastro.da_silver(s_sic).para_json(), comprimir=True)
    comum.gravar_json(estado / "conformidade-RS.json.gz",
                      conf.estado_da_uf("RS", ["4319604"], [2025], s_sic, {("4319604", 2025): True}), comprimir=True)
    comum.gravar_json(estado / "despesa-funcao-RS.json.gz", {"versao": 1, "exercicio": 2025, "entes": {
        "4319604": {"total": 1000.0, "funcoes": {"10": 600.0, "12": 400.0}, "coletado_em": "2026-10-14T12:00:00Z"}}},
        comprimir=True)
    comum.gravar_json(estado / base_cnpj.ARQUIVO, base_cnpj.montar(
        {"97229181000164"}, {"97229181": {"razao_social": "MUNICIPIO DE SAO SEPE", "natureza": "1244",
                                          "capital_social": 0.0, "porte": "05"}}, {}, {}, {},
        {"natureza": {"1244": "Município"}}, "2026-10"), comprimir=True)
    comum.gravar_json(estado / emendas.ARQUIVO, {
        "versao": 1, "data_arquivo": "Sat, 10 Oct 2026 02:57:21 GMT", "fonte": "CGU",
        "colunas_recebido": emendas.COLUNAS_RECEBIDO, "colunas_emenda": emendas.COLUNAS_EMENDA,
        "recebido": {"4319604": [["2025", "E1", "governo_municipal", "12231796000172", "FUNDO", 10.0]]},
        "emendas": {"E1": ["2025", "Emenda Individual", "DEPUTADA A", "0001", "Saúde", "ATENCAO BASICA"]},
        "sem_lugar": {}}, comprimir=True)
    comum.gravar_json(estado / "pessoal-RS.json.gz", {"versao": 1, "exercicio": 2025, "entes": {
        "4319604": {"percentual": 48.33, "dtp": 1.0, "rcl_ajustada": 2.0, "limites": {"maximo": 54.0},
                    "demonstrativo": "RGF Simplificado", "periodo": 2, "periodicidade": "S"}}}, comprimir=True)
    comum.gravar_json(estado / cli.ARQUIVO_EXECUCOES, [
        {"workflowName": "paineis", "createdAt": "2026-10-13T12:00:00Z", "updatedAt": "2026-10-13T12:30:00Z",
         "status": "completed", "conclusion": "success", "event": "schedule", "url": "https://exemplo/1"}])
    assert cli.main(["publicar", "--estado", str(estado), "--saida", str(site), "--hoje", "2026-10-14"]) == 0
    resumo = json.loads(capsys.readouterr().out)
    assert resumo["contratacoes"]["dias"] == 1 and resumo["conformidade"]["entes"] == 1
    arquivos = {p.relative_to(site).as_posix() for p in site.rglob("*") if p.is_file()}
    assert {"indice.json", "entes.json", "index.html", ".nojekyll", "contratacoes/panorama.json",
            "contratacoes/ente/4319604.json", "conformidade/panorama.json", "conformidade/uf/RS.json",
            "conformidade/ente/4319604.json", "contratacoes/orgao/97229181000164.json", "orgaos.json"} <= arquivos
    assert "97229181000164" in {linha[0] for linha in comum.ler_json(site / "orgaos.json")["orgaos"]}
    entes = comum.ler_json(site / "entes.json")
    linhas = {e[0]: e for e in entes["entes"]}
    assert linhas["4319604"][1] == "São Sepé" and linhas["4202008"][1] == "4202008"   # fora do cadastro de amostra
    indice = comum.ler_json(site / "indice.json")
    assert indice["avaliado_em"] == "2026-10-14" and indice["conformidade"]["ufs"]["RS"]
    # Grupo de pares (ADR-038): na amostra, São Sepé é o único município de 20 a 50 mil habitantes do Sul e
    # recua para o porte no país, com a ressalva de grupo abaixo do mínimo
    pares = comum.ler_json(site / "conformidade" / "ente" / "4319604.json")["pares"]
    assert pares["grupo"]["regiao"] == "BR" and pares["grupo"]["abaixo_do_minimo"]
    assert pares["grupo"]["descricao"] == "Municípios de 20 mil a 50 mil habitantes de todo o país"
    assert pares["no_prazo"]["entes"] == 1
    grupo = comum.ler_json(site / "conformidade" / "pares" / f"{pares['grupo']['id']}.json")
    assert [e["codigo"] for e in grupo["entes"]] == ["4319604"] and grupo["tipo"] == "conformidade-pares"
    assert indice["conformidade"]["pares"]["entes_com_grupo"] == 1
    # Despesa por função (ADR-041): o ente leva os próprios valores; o grupo de 1 não tem distribuição
    assert [f["codigo"] for f in pares["despesa"]["funcoes"]] == ["total", "10", "12"]
    assert pares["despesa"]["exercicio"] == 2025 and pares["despesa"]["funcoes"][0]["grupo"] is None
    assert indice["conformidade"]["pares"]["entes_com_despesa"] == 1
    # Despesa com pessoal (ADR-042): o percentual do ente, sem a distribuição do grupo de 1
    assert pares["pessoal"]["ente"]["percentual"] == 48.33 and pares["pessoal"]["grupo"] is None
    assert indice["conformidade"]["pares"]["entes_com_pessoal"] == 1
    # Base de CNPJ (ADR-043) e emendas (ADR-044)
    assert indice["cnpj"]["empresas"] == 1 and "cnpj/972.json.gz" in arquivos and "cnpj/tabelas.json" in arquivos
    assert indice["emendas"]["entes"] == 1 and "emendas/ente/431.json.gz" in arquivos
    # Painel operacional (ADR-039): as execuções gravadas pelo fluxo e o volume do dia coletado
    situacao = comum.ler_json(site / "operacao.json")
    assert next(f for f in situacao["fluxos"] if f["fluxo"] == "paineis")["ultimo_sucesso"] == "2026-10-13T12:30:00Z"
    assert {d["dia"]: d["processos"] for d in situacao["contratacoes"]["dias"]}["2026-09-01"] is not None
    assert indice["operacao"]["alertas"] == len(situacao["alertas"])
    # Sem cadastro e sem estado: site vazio, mas válido
    assert cli.main(["publicar", "--estado", str(tmp_path / "vazio"), "--saida", str(tmp_path / "s2")]) == 0
    assert comum.ler_json(tmp_path / "s2" / "contratacoes" / "panorama.json")["totais"]["processos"] == 0


def test_lumen_painel_pelo_comando_lumen(tmp_path, capsys):
    assert cli_lumen.main(["painel", "faltando", "--estado", str(tmp_path), "--de", "2026-10-13"]) == 0
    assert json.loads(capsys.readouterr().out) == [{"de": "2026-10-13", "ate": "2026-10-13", "dias": 1}]
    toml = tmp_path / "lumen.toml"
    toml.write_text("[coleta]\ncontato = \"x@exemplo.org\"\n", encoding="utf-8")
    assert cli_lumen.main(["--config", str(toml), "painel", "faltando", "--estado", str(tmp_path),
                           "--de", "2026-10-13"]) == 0


def test_falta_de_contato_vira_codigo_2(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("LUMEN_CONTATO")
    assert cli.main(["contratacoes", "--estado", str(tmp_path)]) == 2
    assert "contato" in capsys.readouterr().err

    def quebra(args):
        raise ErroColeta("outra falha")
    monkeypatch.setitem(cli.COMANDOS, "faltando", quebra)
    with pytest.raises(ErroColeta):
        cli.main(["faltando", "--estado", str(tmp_path)])
