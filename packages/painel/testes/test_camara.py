"""Os deputados federais pelos arquivos de dados abertos da Câmara (ADR-060)."""

from __future__ import annotations

import io
import json
import urllib.error
import zipfile
from datetime import date
from pathlib import Path

import pytest

from lumen_painel import camara, comum

DEPUTADOS = {"1": ["Fulana", "PL", "MT", [57]], "2": ["Beltrano", "PT", "SP", [56, 57]]}


def _csv(caminho: Path, colunas: list[str], linhas: list[list]) -> None:
    texto = "\n".join(";".join(f'"{c}"' for c in linha) for linha in [colunas, *linhas])
    caminho.write_text("﻿" + texto, encoding="utf-8")


def _pasta(pasta: Path) -> Path:
    pasta.mkdir(parents=True, exist_ok=True)
    _csv(pasta / "votacoes.csv", ["id", "data", "siglaOrgao", "aprovacao", "votosSim", "votosNao", "votosOutros",
                                  "descricao"],
         [["10-1", "2025-03-01", "PLEN", "1", "300", "100", "2", "Aprovado o projeto."],
          ["10-2", "2025-03-02", "CCJC", "1", "30", "10", "0", "Aprovado o parecer."],
          ["10-3", "2025-04-01", "PLEN", "", "0", "0", "0", "Sem votos nominais."]])
    _csv(pasta / "votacoesVotos.csv", ["idVotacao", "voto", "deputado_id"],
         [["10-1", "Sim", "1"], ["10-1", "Não", "2"], ["10-1", "Sim", "99"], ["10-2", "Sim", "1"]])
    _csv(pasta / "votacoesProposicoes.csv", ["idVotacao", "proposicao_titulo", "proposicao_ementa"],
         [["10-1", "PL 759/2015", "Cria a Zona Franca de Rosário."], ["10-1", "PL 1/2016", "Outro."]])
    _csv(pasta / "votacoesOrientacoes.csv", ["idVotacao", "siglaBancada", "orientacao"],
         [["10-1", "Governo", "Sim"], ["10-1", "Oposição", "Não"]])
    _csv(pasta / "eventos.csv", ["id", "dataHoraInicio", "descricaoTipo", "situacao"],
         [["E1", "2025-02-10T14:00", "Sessão Deliberativa", "Encerrada"],
          ["E2", "2025-06-10T14:00", "Sessão Deliberativa", "Encerrada"],
          ["E3", "2025-06-11T14:00", "Sessão Deliberativa", "Cancelada"],
          ["E4", "2025-06-12T14:00", "Reunião Deliberativa", "Encerrada"]])
    _csv(pasta / "eventosPresencaDeputados.csv", ["idEvento", "idDeputado"],
         [["E1", "1"], ["E2", "1"], ["E2", "2"], ["E4", "2"]])
    _csv(pasta / "proposicoes.csv", ["id", "siglaTipo", "numero", "ano", "ementa", "dataApresentacao",
                                     "ultimoStatus_descricaoSituacao"],
         [["P1", "PL", "12", "2025", "Dá nome a uma ponte.", "2025-05-01T10:00", "Aguardando Parecer"],
          ["P2", "REQ", "7", "2025", "Requer informação.", "2025-05-02T10:00", ""]])
    _csv(pasta / "proposicoesAutores.csv", ["idProposicao", "idDeputadoAutor", "proponente"],
         [["P1", "1", "1"], ["P1", "2", "0"], ["P2", "1", "1"], ["P2", "", "1"]])
    cota = ["ideCadastro", "txtDescricao", "txtFornecedor", "txtCNPJCPF", "vlrLiquido", "numMes"]
    linhas = [["1", "TELEFONIA", "EMPRESA X 123.456.789-09", "09.537.392/0001-05", "100.5", "3"],
              ["1", "TELEFONIA", "EMPRESA X", "09537392000105", "50", "4"],
              ["1", "COMBUSTÍVEIS", "FULANO TAXISTA", "123.456.789-09", "30", "4"],
              ["", "TELEFONIA", "LIDERANÇA", "09537392000105", "1000", "4"]]
    texto = "\n".join(";".join(f'"{c}"' for c in linha) for linha in [cota, *linhas])
    with zipfile.ZipFile(pasta / "cota.zip", "w") as z:
        z.writestr("Ano-2025.csv", ("﻿" + texto).encode("utf-8"))
    return pasta


def test_ano_com_votos_presenca_autoria_e_cota(tmp_path):
    a = camara.ler_ano(_pasta(tmp_path / "ano"), 2025, DEPUTADOS)
    assert list(a["votacoes"]) == ["10-1"]                           # só o Plenário com voto nominal
    assert a["votacoes"]["10-1"] == ["2025-03-01", "PL 759/2015", "Cria a Zona Franca de Rosário.",
                                     "Aprovado o projeto.", 1, 300, 100, 2, "Sim"]
    assert a["votos"] == {"1": {"10-1": "S"}, "2": {"10-1": "N"}}    # o 99 não está no cadastro
    assert a["sessoes"] == {"E1": "2025-02-10", "E2": "2025-06-10"}  # cancelada e de comissão ficam de fora
    assert a["presencas"] == {"1": ["E1", "E2"], "2": ["E2"]}
    assert a["autoria"] == {"1": [["P1", "PL", "12", "2025", "Dá nome a uma ponte.", "2025-05-01",
                                   "Aguardando Parecer"]]}           # o REQ só conta; coautor não proponente fora
    assert a["contagem"] == {"1": {"PL": 1, "REQ": 1}}
    c = a["ceap"]["1"]
    assert c["categorias"] == {"COMBUSTÍVEIS": 30.0, "TELEFONIA": 150.5} and c["meses"] == {"03": 100.5, "04": 80.0}
    assert c["fornecedores"] == {"09537392000105": [2, 150.5]} and c["pf"] == [1, 30.0]
    assert a["fornecedores"] == {"09537392000105": "EMPRESA X"}
    assert "123.456.789-09" not in json.dumps(a) and "TAXISTA" not in json.dumps(a)


def test_periodos_em_exercicio():
    historico = [{"dataHora": "2023-02-01T00:00", "situacao": None},
                 {"dataHora": "2023-02-01T12:05", "situacao": "Exercício"},
                 {"dataHora": "2024-03-01T10:00", "situacao": None},                      # troca de partido
                 {"dataHora": "2024-06-01T00:00", "situacao": "Licença"},
                 {"dataHora": "2024-10-01T00:00", "situacao": "Exercício"}]
    p = camara.periodos(historico)
    assert p == [["2023-02-01", "2024-06-01"], ["2024-10-01", None]]
    assert camara.em_exercicio("2024-05-31", p) and not camara.em_exercicio("2024-07-01", p)
    assert camara.em_exercicio("2026-01-01", p)
    assert camara.no_mandato("2023-01-31", [56]) and not camara.no_mandato("2023-02-01", [56])
    assert camara.no_mandato("2027-01-31", [57]) and not camara.no_mandato("2019-01-31", [56, 57])


class _Resposta(io.BytesIO):
    def __init__(self, dados: bytes, status: int, tamanho: int):
        super().__init__(dados)
        self.status, self.headers = status, {"Content-Length": str(tamanho)}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_baixar_retoma_o_que_caiu_no_meio(tmp_path):
    conteudo = b"0123456789" * 10
    pedidos = []

    def abrir(pedido, timeout):
        faixa = pedido.headers.get("Range")
        pedidos.append(faixa)
        if not faixa:
            return _Resposta(conteudo[:40], 200, len(conteudo))           # corta em 40 de 100
        inicio = int(faixa.split("=")[1].rstrip("-"))
        return _Resposta(conteudo[inicio:], 206, len(conteudo) - inicio)

    destino = tmp_path / "a.csv"
    assert camara.baixar_inteiro("https://x/a.csv", destino, contato="c", abrir=abrir, esperar=lambda s: None) == 100
    assert destino.read_bytes() == conteudo and pedidos == [None, "bytes=40-"]


def test_baixar_desiste_depois_das_tentativas(tmp_path):
    abrir = lambda pedido, timeout: _Resposta(b"", 200, 100)  # noqa: E731
    with pytest.raises(OSError, match="incompleto"):
        camara.baixar_inteiro("https://x/a.csv", tmp_path / "a.csv", contato="c", abrir=abrir, tentativas=2,
                              esperar=lambda s: None)


def test_coleta_e_publicacao(tmp_path):
    origem = _pasta(tmp_path / "origem")

    def baixar(url, destino, *, contato):
        if "cotas" in url:
            if "2024" in url:
                raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
            nome = "cota.zip"
        else:
            nome = url.rsplit("/", 1)[-1].rsplit("-", 1)[0] + ".csv"
        destino.write_bytes((origem / nome).read_bytes())
        return destino.stat().st_size

    exercicio = {"1": [["2025-01-01", "2025-05-31"]], "2": [["2019-02-01", None]]}
    estado = tmp_path / "estado"
    r = camara.coletar(estado, contato="c", hoje=date(2025, 7, 1), anos=[2024, 2025], baixar_fn=baixar,
                       cabecalho_fn=lambda url, contato: (10, "e"), cadastro_fn=lambda contato: DEPUTADOS,
                       exercicio_fn=lambda deps, contato: {d: exercicio[d] for d in deps})
    assert r.lidos == [2024, 2025] and r.problemas == ["2024: sem o arquivo da cota parlamentar"]
    gravados = {}
    resumo = camara.publicar(estado, lambda c, d: gravados.__setitem__(c, d), gerado_em="x")
    assert resumo == {"deputados": 2, "anos": ["2024", "2025"]}
    fulana = gravados["parlamentares/camara/1.json.gz"]
    assert fulana["anos"]["2025"]["presenca"] == [1, 1]          # só a sessão de fevereiro, quando estava em exercício
    assert fulana["anos"]["2025"]["ceap"]["fornecedores"] == [["09537392000105", "EMPRESA X", 2, 150.5]]
    assert "ceap" not in fulana["anos"]["2024"]
    assert gravados["parlamentares/camara/2.json.gz"]["anos"]["2025"]["presenca"] == [1, 2]
    indice = gravados["parlamentares/camara/indice.json"]
    assert [d[:4] for d in indice["deputados"]] == [["2", "Beltrano", "PT", "SP"], ["1", "Fulana", "PL", "MT"]]
    assert indice["deputados"][1][5:10] == [2, 2, 2, 2, 180.5]     # votos, proposições, presenças, sessões, cota
    assert indice["deputados"][1][10] == {"2024": [1, 1, 1, 1, 0], "2025": [1, 1, 1, 1, 180.5]}
    assert indice["legislaturas"]["57"] == [2023, 2026]
    assert gravados["parlamentares/camara/votacoes-2025.json.gz"]["votacoes"]["10-1"][1] == "PL 759/2015"
    # Sem anos pedidos, o tamanho decide: 2025 é o corrente e foi lido agora, e não volta
    r2 = camara.coletar(estado, contato="c", hoje=date(2025, 7, 2), baixar_fn=baixar,
                        cabecalho_fn=lambda url, contato: (10, "e"), cadastro_fn=lambda contato: DEPUTADOS,
                        exercicio_fn=lambda deps, contato: {d: exercicio[d] for d in deps})
    assert 2025 in r2.pulados and comum.ler_json(estado / camara.ARQUIVO)["exercicio"]["1"] == exercicio["1"]


def test_cadastro_sem_legislatura_repetida():
    respostas = {56: [{"id": 2, "nome": "Beltrano", "siglaPartido": "PSB", "siglaUf": "SP"}],
                 57: [{"id": 2, "nome": "Beltrano", "siglaPartido": "PSB", "siglaUf": "SP"},
                      {"id": 2, "nome": "Beltrano", "siglaPartido": "PT", "siglaUf": "SP"}]}
    ler = lambda url: json.dumps({"dados": respostas[int(url.split("idLegislatura=")[1].split("&")[0])]}).encode()  # noqa: E731
    assert camara.cadastro(contato="c", ler_fn=ler) == {"2": ["Beltrano", "PT", "SP", [56, 57]]}
