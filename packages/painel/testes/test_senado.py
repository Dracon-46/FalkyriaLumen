"""Os senadores pelos dados abertos do Senado Federal (ADR-060, adendo)."""

from __future__ import annotations

import json
from datetime import date

from lumen_painel import comum, senado

SENADORES = {"5672": ["Alan Rick", "", "AC", [57]], "5982": ["Alessandro Vieira", "", "SE", [56, 57]]}

VOTACOES = [
    {"codigoSessaoVotacao": 6918, "votacaoSecreta": "N", "dataSessao": "2025-02-19", "identificacao": "PLP 22/2025",
     "ementa": "Dispõe sobre restos a pagar.", "descricaoVotacao": "Votação nominal do substitutivo.",
     "resultadoVotacao": "A", "codigoMateria": 167182,
     "votos": [{"codigoParlamentar": 5672, "siglaPartidoParlamentar": "UNIÃO", "siglaVotoParlamentar": "Sim"},
               {"codigoParlamentar": 5982, "siglaPartidoParlamentar": "MDB", "siglaVotoParlamentar": "P-NRV"},
               {"codigoParlamentar": 1, "siglaPartidoParlamentar": "X", "siglaVotoParlamentar": "Não"}]},
    {"codigoSessaoVotacao": 6919, "votacaoSecreta": "S", "dataSessao": "2025-02-20", "votos": []},
]
CEAPS = """"ULTIMA ATUALIZACAO";"03/11/2026 02:02"
"ANO";"MES";"SENADOR";"TIPO_DESPESA";"CNPJ_CPF";"FORNECEDOR";"DOCUMENTO";"DATA";"DETALHAMENTO";"VALOR_REEMBOLSADO";"COD_DOCUMENTO"
"2025";"1";"ALAN RICK";"Aluguel de imóveis";"66.970.229/0132-26";"CLARO NXT";"1";"18/01/2025";"";"399,44";"1"
"2025";"2";"ALAN RICK";"Combustíveis";"123.456.789-09";"FULANO";"2";"18/02/2025";"";"1.000,00";"2"
"2025";"2";"FULANO DE TAL";"Combustíveis";"66.970.229/0132-26";"X";"3";"18/02/2025";"";"5,00";"3"
"2025";"3";"ALESSANDRO VIEIRA FILHO";"Combustíveis";"66.970.229/0132-26";"X";"4";"18/03/2025";"";"7,00";"4"
"""
MATERIAS = {"5672": [["1", "PL", "12", "2025", "Dá nome a uma rodovia.", "2025-03-01", "EM TRAMITAÇÃO"],
                     ["2", "RQS", "41", "2025", "Requer.", "2025-03-02", "APROVADA"],
                     ["3", "PL", "9", "2024", "Outro.", "2024-05-01", None]]}


def test_votacoes_nominais_abertas_com_partido_e_presenca():
    a = senado.ler_votacoes(VOTACOES, SENADORES)
    assert list(a["votacoes"]) == ["6918"]                            # a secreta fica de fora
    assert a["votacoes"]["6918"] == ["2025-02-19", "PLP 22/2025", "Dispõe sobre restos a pagar.",
                                     "Votação nominal do substitutivo.", 1, 1, 0, 1, None, "167182"]
    assert a["votos"] == {"5672": {"6918": "S"}, "5982": {"6918": "P-NRV"}}
    assert a["partidos"] == {"6918": {"5672": "UNIÃO", "5982": "MDB"}}
    assert a["presencas"] == {"5672": ["6918"], "5982": ["6918"]}     # presente sem registrar voto conta como presença
    assert a["sessoes"] == {"6918": "2025-02-19"}


def test_cota_pelo_nome_do_senador():
    ceap, nomes, sem = senado.ler_ceaps(CEAPS, SENADORES)
    assert ceap["5672"]["categorias"] == {"Aluguel de imóveis": 399.44, "Combustíveis": 1000.0}
    assert ceap["5672"]["fornecedores"] == {"66970229013226": [1, 399.44]} and ceap["5672"]["pf"] == [1, 1000.0]
    assert nomes["66970229013226"] in ("CLARO NXT", "X") and sem == 1
    assert ceap["5982"]["categorias"] == {"Combustíveis": 7.0}     # pelo começo do nome, quando só um senador casa
    assert "123.456.789-09" not in json.dumps(ceap)


def test_autoria_do_ano_e_periodos():
    listadas, contagem = senado.autoria_do_ano(MATERIAS, 2025)
    assert listadas == {"5672": [MATERIAS["5672"][0]]} and contagem == {"5672": {"PL": 1, "RQS": 1}}
    mandatos = {"MandatoParlamentar": {"Parlamentar": {"Mandatos": {"Mandato": [
        {"Exercicios": {"Exercicio": [{"DataInicio": "2023-02-01"}]}},
        {"Exercicios": {"Exercicio": {"DataInicio": "2015-02-01", "DataFim": "2019-01-31"}}}]}}}}
    assert senado.periodos(mandatos) == [["2015-02-01", "2019-01-31"], ["2023-02-01", None]]


def test_cadastro_e_coleta_e_publicacao(tmp_path):
    lista = {"ListaParlamentarLegislatura": {"Parlamentares": {"Parlamentar": [
        {"IdentificacaoParlamentar": {"CodigoParlamentar": "5672", "NomeParlamentar": "Alan Rick"},
         "Mandatos": {"Mandato": {"UfParlamentar": "AC"}}}]}}}
    respostas = lambda url: json.dumps(lista if "legislatura/57" in url else {} if "legislatura" in url  # noqa: E731
                                       else VOTACOES if "dataInicio=2025" in url else []).encode()
    assert senado.cadastro(contato="c", ler_fn=respostas) == {"5672": ["Alan Rick", "", "AC", [57]]}
    estado = tmp_path / "estado"
    r = senado.coletar(estado, contato="c", hoje=date(2025, 7, 1), anos=[2024, 2025], ler_fn=respostas,
                       texto_fn=lambda url: CEAPS if "2025" in url else None, cadastro_fn=lambda contato: SENADORES,
                       exercicio_fn=lambda s, contato: {x: [["2023-02-01", None]] for x in s},
                       autoria_fn=lambda s, contato: {x: MATERIAS.get(x, []) for x in s})
    assert r.lidos == [2024, 2025] and r.problemas == ["2025: 1 linha(s) da cota sem senador no cadastro"]
    gravados = {}
    assert senado.publicar(estado, lambda c, d: gravados.__setitem__(c, d), gerado_em="x") == \
        {"deputados": 2, "anos": ["2024", "2025"]}
    alan = gravados["parlamentares/senado/5672.json.gz"]
    assert alan["tipo"] == "senado-senador" and alan["partido"] == "UNIÃO"        # o partido do voto mais recente
    assert alan["anos"]["2025"]["presenca"] == [1, 1] and alan["anos"]["2024"]["autoria"][0][0] == "3"
    assert gravados["parlamentares/senado/votos-2025.json.gz"]["votos"]["6918"] == [["5672", "S", "UNIÃO"],
                                                                                   ["5982", "P-NRV", "MDB"]]
    assert gravados["parlamentares/senado/indice.json"]["tipo"] == "senado-indice"
    assert comum.ler_json(estado / senado.ARQUIVO)["autoria"]["5672"][0][0] == "1"
