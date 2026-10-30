"""O que a União pagou a cada pessoa jurídica, pelo arquivo mensal da CGU (ADR-058)."""

import zipfile
from pathlib import Path

import pytest

from lumen_painel import comum
from lumen_painel import pessoas_juridicas as pj
from lumen_painel import recebimentos as r
from lumen_painel.contratacoes import Painel

EMPRESA = "09537392000105"
BANCO = "00000000000191"
CABECALHO = ('"Código Favorecido";"Nome Favorecido";"Sigla UF";"Nome Município";"Código Órgão Superior";'
             '"Nome Órgão Superior";"Código Órgão";"Nome Órgão";"Código Unidade Gestora";"Nome Unidade Gestora";'
             '"Ano e mês do lançamento";"Valor Recebido"')


def _linha(codigo, nome, orgao, nome_orgao, mes, valor):
    return ";".join(f'"{c}"' for c in [codigo, nome, "RS", "SAO SEPE", orgao, nome_orgao, orgao, nome_orgao, "1",
                                       "UG", mes, valor])


def _zip(caminho: Path, mes: str, nome_empresa="EMPRESA X 123.456.789-09") -> Path:
    m = f"{mes[4:]}/{mes[:4]}"
    linhas = [
        _linha(EMPRESA, f"'' {nome_empresa}", "36000", "Ministério da Saúde", m, "1000,50"),
        _linha(EMPRESA, nome_empresa, "26000", "Ministério da Educação", m, "200"),
        _linha(EMPRESA, nome_empresa, "36000", "Ministério da Saúde", m, "99,50"),
        _linha(BANCO, "BANCO DO BRASIL SA", "25000", "Ministério da Fazenda", m, "1.000.000,00"),
        _linha("EX1540453", "EMPRESA DO EXTERIOR", "26000", "Ministério da Educação", m, "10,00"),
        _linha("160126", "BATALHAO", "52000", "Ministério da Defesa", m, "5,00"),
    ]
    with zipfile.ZipFile(caminho, "w") as z:
        z.writestr(f"{mes}_RecebimentosRecursosPorFavorecido.csv",
                   "\n".join([CABECALHO, *linhas]).encode("latin-1"))
    return caminho


def test_soma_do_mes_por_cnpj_e_orgao(tmp_path):
    nomes, orgaos = {}, {}
    soma = r.somar_mes(_zip(tmp_path / "a.zip", "202609"), nomes, orgaos, nomes_novos=True)
    assert soma["cnpjs"][EMPRESA] == {"26000": 200.0, "36000": 1100.0}
    assert soma["cnpjs"][BANCO] == {"25000": 1_000_000.0}
    assert soma["fora"] == [2, 15.0]                                 # exterior e unidade gestora
    assert nomes[EMPRESA] == "EMPRESA X ***.456.789-**"              # sem as aspas da fonte e com o CPF mascarado
    assert orgaos["36000"] == "Ministério da Saúde"


def test_coluna_que_falta_e_erro(tmp_path):
    caminho = tmp_path / "b.zip"
    with zipfile.ZipFile(caminho, "w") as z:
        z.writestr("x.csv", '"Código Favorecido";"Valor Recebido"\n"1";"2"'.encode("latin-1"))
    with pytest.raises(ValueError, match="colunas ausentes"):
        r.somar_mes(caminho, {}, {}, nomes_novos=False)


def test_coleta_janela_nome_mais_recente_e_verificacao(tmp_path):
    estado = tmp_path / "estado"
    meses = ["202605", "202606", "202607", "202608", "202609"]
    baixados, pausas = [], []

    def baixar(mes, destino, **k):
        baixados.append(mes)
        return _zip(destino, mes, nome_empresa="EMPRESA X NOVA" if mes == "202609" else "EMPRESA X VELHA")

    res = r.coletar(estado, contato="x", meses_fn=lambda **k: meses, baixar_fn=baixar, limite=4,
                    dormir=pausas.append)
    assert res.baixados == ["202609", "202608", "202607", "202606"] and res.faltam == 1 and len(pausas) == 3
    dados = comum.ler_json(estado / r.ARQUIVO)
    assert sorted(dados["recentes"]) == ["202607", "202608", "202609"] and dados["fixados"] == ["202606"]
    assert dados["nomes"][EMPRESA] == "EMPRESA X NOVA"               # o do mês mais novo, não o dos outros recentes
    meses.append("202610")

    def bloqueado(mes, destino, **k):
        if mes == "202605":
            raise r.VerificacaoHumana("HTTP 405")
        return baixar(mes, destino)

    res = r.coletar(estado, contato="x", meses_fn=lambda **k: meses, baixar_fn=bloqueado, dormir=lambda s: None)
    dados = comum.ler_json(estado / r.ARQUIVO)
    assert res.verificacao == "HTTP 405" and res.faltam == 1
    assert dados["fixados"] == ["202606", "202607"]                  # julho saiu da janela e foi para o ano
    assert dados["anos"]["2026"]["cnpjs"][EMPRESA]["36000"] == 2200.0
    ano = r.por_ano(dados)["2026"]
    assert ano["cnpjs"][EMPRESA] == {"26000": 1000.0, "36000": 5500.0}    # cinco meses, fixados e recentes
    assert ano["fora"] == [10, 75.0]


def test_pagina_da_empresa_com_o_recebido_da_uniao(tmp_path):
    nomes, orgaos = {}, {}
    soma = r.somar_mes(_zip(tmp_path / "a.zip", "202609"), nomes, orgaos, nomes_novos=True)
    comum.gravar_json(tmp_path / r.ARQUIVO, {
        "versao": r.VERSAO_ESTADO, "coletado_em": "2026-10-30T00:00:00Z", "fixados": [], "anos": {"2025": soma},
        "recentes": {"202609": soma}, "nomes": nomes, "orgaos": orgaos}, comprimir=True)
    gravados = {}
    resumo = pj.publicar(tmp_path, Painel(), lambda caminho, dados: gravados.__setitem__(caminho, dados), gerado_em="x")
    assert resumo["com_uniao"] == 2 and resumo["pessoas"] == 2
    arquivo = gravados[f"pj/{comum.grupo_do_cnpj(EMPRESA)}.json.gz"]
    empresa = arquivo["pessoas"][EMPRESA]
    assert empresa["nome"] == "EMPRESA X ***.456.789-**"
    assert empresa["uniao"] == [["2025", "26000", 200.0], ["2025", "36000", 1100.0],
                                ["2026", "26000", 200.0], ["2026", "36000", 1100.0]]
    assert arquivo["orgaos_uniao"]["26000"] == "Ministério da Educação"
    assert arquivo["fontes"]["uniao"] == "2026-10-30T00:00:00Z" and arquivo["colunas"]["uniao"] == ["ano", "orgao", "valor"]
    busca = [p for f, d in gravados.items() if f.startswith("pj/busca/em") for p in d["pessoas"]]
    assert [EMPRESA, "EMPRESA X ***.456.789-**", 2600.0] in busca      # o recebido entra no peso da busca
