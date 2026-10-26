"""Testes das transferências da União (CGU): esfera do favorecido, soma por ente, coleta gentil e publicação."""

import zipfile
from pathlib import Path

from lumen_painel import comum
from lumen_painel import transferencias as t
from lumen_painel.cadastro import Cadastro, Ente

CABECALHO = ("ANO / MÊS;TIPO TRANSFERÊNCIA;TIPO FAVORECIDO;UF;CÓDIGO MUNICÍPIO SIAFI;NOME MUNICÍPIO;NOME FUNÇÃO;"
             "NOME AÇÃO;LINGUAGEM CIDADÃ;NOME FAVORECIDO;VALOR TRANSFERIDO")


def _linha(mes, tipo, favorecido, uf, municipio, funcao, acao, cidada, nome, valor):
    return ";".join(f'"{c}"' for c in [mes, tipo, favorecido, uf, "", municipio, funcao, acao, cidada, nome, valor])


def _zip(caminho: Path, mes: str) -> Path:
    linhas = [
        _linha(mes, "Legais, Voluntárias e Específicas", "Administração Pública Municipal", "RS", "SAO SEPE", "Saúde",
               "ATENCAO", "TETO MAC", "MUNICIPIO DE SAO SEPE", "1000,50"),
        _linha(mes, "Legais, Voluntárias e Específicas", "Administração Pública", "RS", "SAO SEPE", "Saúde",
               "ATENCAO PRIMARIA", "Sem informação", "FUNDO MUNICIPAL DE SAUDE", "200,00"),
        _linha(mes, "Legais, Voluntárias e Específicas", "Administração Pública", "RS", "PORTO ALEGRE", "Saúde",
               "MAC", "TETO MAC", "FUNDO ESTADUAL DE SAUDE", "5000,00"),
        _linha(mes, "Constitucionais e Royalties", "Administração Pública Estadual ou do Distrito Federal", "RS", "",
               "Encargos especiais", "ROYALTIES", "Royalties", "ESTADO DO RS", "300,00"),
        _linha(mes, "Legais, Voluntárias e Específicas", "Entidades Sem Fins Lucrativos", "RS", "SAO SEPE", "Educação",
               "PDDE", "PDDE", "APM ESCOLA", "50,00"),
        _linha(mes, "Constitucionais e Royalties", "Entidades Empresariais Privadas", "RJ", "RIO DE JANEIRO",
               "Encargos especiais", "X", "Royalties", "PETROLEO BRASILEIRO S A", "9999,00"),
        _linha(mes, "Legais, Voluntárias e Específicas", "Administração Pública Municipal", "RJ", "PARATI", "Educação",
               "MERENDA", "Merenda Escolar", "MUNICIPIO DE PARATY", "70,00"),
        _linha(mes, "Legais, Voluntárias e Específicas", "Administração Pública Municipal", "XX", "LUGAR NENHUM",
               "Saúde", "X", "X", "?", "1,00"),
    ]
    with zipfile.ZipFile(caminho, "w") as z:
        z.writestr(f"{mes}_Transferencias.csv", ("\r\n".join([CABECALHO, *linhas]) + "\r\n").encode("latin-1"))
    return caminho


def _cadastro() -> Cadastro:
    return Cadastro({"4319604": Ente("4319604", "São Sepé", "RS", "M", 21551),
                     "43": Ente("43", "Rio Grande do Sul", "RS", "E", 11_000_000),
                     "3303807": Ente("3303807", "Paraty", "RJ", "M", 45_000)})


def test_esfera_do_favorecido():
    assert t.esfera("Administração Pública Municipal", "MUNICIPIO X") == "municipal"
    assert t.esfera("Administração Pública", "FUNDO MUNICIPAL DE SAUDE") == "municipal"
    assert t.esfera("Administração Pública", "FUNDO ESTADUAL DE SAUDE") == "estadual"
    assert t.esfera("Administração Pública", "SECRETARIA DE ESTADO DA SAUDE") == "estadual"
    assert t.esfera("Sem Informação", "SECRETARIA MUNICIPAL DE EDUCACAO") == "municipal"
    assert t.esfera("Sem Informação", "QUALQUER") is None
    assert t.esfera("Entidades Empresariais Privadas", "PETROBRAS") is None
    assert t.esfera("Entidades Sem Fins Lucrativos", "APM") == "entidade"


def test_meses_da_pagina():
    html = ('arquivos.push({"ano" : "2013", "mes" : "12", "dia" : ""}) arquivos.push({"ano" : "2014", "mes" : "01"})'
            ' arquivos.push({"ano" : "2026", "mes" : "09", "dia" : "", "origem" :  "Transferencias"})')
    assert t.meses_na_pagina(html) == ["201401", "202609"]


def test_soma_do_mes(tmp_path):
    soma = t.somar_mes(_zip(tmp_path / "m.zip", "202609"), t.indice_de_lugares(_cadastro()))
    sepe = soma["governo"]["4319604"]
    assert sepe["total"] == 1200.5 and sepe["por_area"] == {"Saúde": 1200.5}
    assert sepe["por_acao"] == {"TETO MAC": 1000.5, "Atencao primaria": 200.0}   # sem nome cidadão: o da ação
    assert soma["governo"]["43"]["total"] == 5300.0 and soma["governo"]["43"]["por_tipo"] == {"legais": 5000.0,
                                                                                            "constitucionais": 300.0}
    assert soma["governo"]["3303807"]["total"] == 70.0                           # Parati, pelo apelido
    assert soma["entidades"]["4319604"] == {"total": 50.0, "por_area": {"Educação": 50.0}}
    assert soma["fora"] == {"outros_favorecidos": 9999.0, "sem_lugar": 1.0}


def test_coleta_gentil_janela_e_verificacao(tmp_path):
    estado = tmp_path / "estado"
    meses = ["202605", "202606", "202607", "202608", "202609"]
    baixados, pausas = [], []

    def baixar(mes, destino, **k):
        baixados.append(mes)
        return _zip(destino, mes)

    r = t.coletar(estado, _cadastro(), contato="x", meses_fn=lambda **k: meses, baixar_fn=baixar, limite=4,
                  dormir=pausas.append)
    # Primeiro os três recentes, depois os antigos do mais novo para o mais antigo, até o limite
    assert r.baixados == ["202609", "202608", "202607", "202606"] and r.faltam == 1 and len(pausas) == 3
    dados = comum.ler_json(estado / t.ARQUIVO)
    assert sorted(dados["recentes"]) == ["202607", "202608", "202609"] and dados["fixados"] == ["202606"]
    # Na execução seguinte saiu outubro: setembro..julho seguem recentes, o antigo que faltava é fixado
    meses.append("202610")

    def bloqueado(mes, destino, **k):
        if mes == "202605":
            raise t.VerificacaoHumana("HTTP 405")
        return baixar(mes, destino)

    r = t.coletar(estado, _cadastro(), contato="x", meses_fn=lambda **k: meses, baixar_fn=bloqueado,
                  dormir=lambda s: None)
    dados = comum.ler_json(estado / t.ARQUIVO)
    assert r.verificacao == "HTTP 405" and r.faltam == 1
    assert sorted(dados["recentes"]) == ["202608", "202609", "202610"]
    assert dados["fixados"] == ["202606", "202607"]          # julho saiu da janela e foi para o ano
    assert dados["anos"]["2026"]["governo"]["4319604"]["total"] == 2401.0
    # O site soma os fixados e os recentes, por ente e ano
    saida = {}
    resumo = t.publicar(estado, lambda p, c: saida.__setitem__(p, c), gerado_em="agora")
    ente = saida[f"transferencias/ente/{comum.grupo_do_ente('4319604')}.json.gz"]["entes"]["4319604"]["2026"]
    assert ente["governo"]["total"] == 6002.5 and ente["entidades"]["total"] == 250.0
    assert resumo["meses"] == 5 and resumo["ultimo_mes"] == "202610"


def test_publicacao_junta_as_acoes_pequenas(tmp_path, monkeypatch):
    monkeypatch.setattr(t, "ACOES_POR_ANO", 1)
    estado = tmp_path / "estado"
    t.coletar(estado, _cadastro(), contato="x", meses_fn=lambda **k: ["202609"],
              baixar_fn=lambda mes, destino, **k: _zip(destino, mes), dormir=lambda s: None)
    saida = {}
    t.publicar(estado, lambda p, c: saida.__setitem__(p, c), gerado_em="agora")
    acoes = saida[f"transferencias/ente/{comum.grupo_do_ente('4319604')}.json.gz"]["entes"]["4319604"]["2026"]["governo"]["por_acao"]
    assert acoes == {"TETO MAC": 1000.5, "Outras ações": 200.0}
