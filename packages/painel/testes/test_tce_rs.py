"""Contratos dos municípios gaúchos no LicitaCon do TCE-RS (ADR-050)."""

from __future__ import annotations

import http.client
import io
import urllib.parse
import urllib.request
import zipfile
from datetime import date

import pytest

from lumen_painel import comum, tce, tce_rs
from lumen_painel.cadastro import Cadastro, Ente

ORGAOS = """﻿CD_ORGAO,NOME_ORGAO,SIGLA_ORGAO,ESFERA,SETOR_GOVERNAMENTAL,CNPJ,HOME_PAGE,NATUREZA_JURIDICA,CONTABILIDADE,\
SITUACAO_ORGAO,CD_MUNICIPIO_TCERS,NOME_MUNICIPIO,CD_MUNICIPIO_IBGE
59600,PM DE SÃO SEPÉ,PM,MUNICIPAL,EXECUTIVO,1,,PUBLICA,,1-ATIVO,1,SAO SEPE,4319604
59601,CM DE SÃO SEPÉ,CM,MUNICIPAL,LEGISLATIVO,2,,PUBLICA,,1-ATIVO,1,SAO SEPE,4319604
88135,CIS - CONSÓRCIO,CIS,MUNICIPAL,CONSÓRCIO ADMINISTRATIVO,3,,PRIVADA,,1-ATIVO,1,SAO SEPE,4319604
100,AL - ASSEMBLEIA,AL,ESTADUAL,LEGISLATIVO,4,,PUBLICA,,1-ATIVO,149,PORTO ALEGRE,4314902
"""
CONTRATOS = ("CD_ORGAO,NR_LICITACAO,ANO_LICITACAO,CD_TIPO_MODALIDADE,NR_CONTRATO,ANO_CONTRATO,TP_INSTRUMENTO,"
             "TP_DOCUMENTO,NR_DOCUMENTO,VL_CONTRATO,DS_OBJETO\n"
             "59600,1,2022,PRE,10,2022,C,J,09537392000105,1000.50,Obra\n"
             "59600,2,2022,PRD,11,2022,C,J,09537392000105,500,Material\n"
             "59601,3,2022,PRE,12,2022,C,F,05975069068,300,Aluguel\n"
             "59600,4,2022,PRE,13,2022,C,J,11111111000191,999999999999,Erro de digitação\n"
             "88135,5,2022,PRE,14,2022,C,J,22222222000122,700,Consórcio\n"
             "100,6,2022,PRE,15,2022,C,J,09537392000105,2000,Assembleia\n")
ALTERACOES = ("CD_ORGAO,NR_LICITACAO,ANO_LICITACAO,CD_TIPO_MODALIDADE,NR_CONTRATO,ANO_CONTRATO,TP_INSTRUMENTO,"
              "VL_ACRESCIMO,VL_REDUCAO\n"
              "59600,1,2022,PRE,10,2022,C,100,\n"
              "59600,1,2022,PRE,10,2022,C,,30\n")
PESSOAS = ("TP_DOCUMENTO,NR_DOCUMENTO,TP_PESSOA,NM_PESSOA\n"
           "J,09537392000105,J,EMPRESA X LTDA\n"
           "J,11111111000191,J,JOAO 123.456.789-09 MEI\n"
           "F,05975069068,F,FULANO\n")
CADASTRO = Cadastro({"4319604": Ente("4319604", "São Sepé", "RS", "M", 23_000),
                     "43": Ente("43", "Rio Grande do Sul", "RS", "E", 11_000_000)})


def _zip(**arquivos: str) -> bytes:
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as z:
        for nome, texto in arquivos.items():
            z.writestr(nome.replace("_csv", ".csv"), "﻿" + texto)
    return saida.getvalue()


ZIP_2022 = _zip(contrato_csv=CONTRATOS, alteracao_csv=ALTERACOES, pessoas_csv=PESSOAS)


def _teto(ente):
    return tce_rs.teto_do_ente(ente, CADASTRO)


def test_sem_acento():
    assert comum.sem_acento("CONSÓRCIO INTERMUNICIPAL DE SAÚDE") == "CONSORCIO INTERMUNICIPAL DE SAUDE"
    assert comum.sem_acento(None) == ""


def test_orgaos_no_ente_e_consorcio_sem_ente():
    orgaos = tce_rs.ler_orgaos(ORGAOS)
    assert [orgaos[c].ente for c in ("59600", "59601", "88135", "100")] == ["4319604", "4319604", None, "43"]


def test_ano_por_ente_com_teto_pessoa_fisica_e_aditivos():
    with zipfile.ZipFile(io.BytesIO(ZIP_2022)) as z:
        r = tce_rs.ler_ano(z, tce_rs.ler_orgaos(ORGAOS), _teto)
    # São Sepé: 4 contratos (o do erro de digitação conta e fica fora da soma), um com pessoa física, 2 aditivos
    assert r["entes"]["4319604"] == [4, 1800.5, 1, 1, 300.0, 2, 70.0]
    assert r["entes"]["43"] == [1, 2000.0, 0, 0, 0.0, 0, 0.0]
    assert r["sem_ente"] == [1, 700.0]                                # o consórcio
    assert r["fornecedores"]["4319604"] == {"09537392000105": [2, 1500.5], "11111111000191": [1, 0.0]}
    assert "05975069068" not in str(r)                                # o CPF não é guardado
    with zipfile.ZipFile(io.BytesIO(ZIP_2022)) as z:
        nomes = tce_rs.ler_nomes(z, {"09537392000105", "11111111000191"})
    assert nomes == {"09537392000105": "EMPRESA X LTDA", "11111111000191": "JOAO ***.456.789-** MEI"}


class _Resposta(io.BytesIO):
    def __init__(self, dados: bytes, status: int = 206):
        super().__init__(dados)
        self.status = status


def test_arquivo_remoto_le_so_as_partes_pedidas():
    pedidos = []

    def abrir(pedido):
        ini, fim = (int(x) for x in pedido.headers["Range"].split("=")[1].split("-"))
        pedidos.append((ini, fim))
        return _Resposta(ZIP_2022[ini:fim + 1])

    arquivo = tce.ArquivoRemoto("https://exemplo.org/a.zip", len(ZIP_2022), contato="c", bloco=64, abrir=abrir)
    with zipfile.ZipFile(arquivo) as z:
        assert z.read("contrato.csv").decode("utf-8-sig") == CONTRATOS
    assert pedidos and all(fim < len(ZIP_2022) for _, fim in pedidos)
    errado = tce.ArquivoRemoto("https://exemplo.org/a.zip", len(ZIP_2022), contato="c",
                               abrir=lambda p: _Resposta(ZIP_2022, status=200))
    with pytest.raises(OSError, match="parte pedida"):
        errado.read(10)


def test_arquivo_remoto_nao_pede_mais_que_o_limite_do_intermediario(monkeypatch):
    monkeypatch.setattr(tce, "BLOCO_MAXIMO", 100)
    tamanhos = []

    def abrir(pedido):
        ini, fim = (int(x) for x in pedido.headers["Range"].split("=")[1].split("-"))
        tamanhos.append(fim - ini + 1)
        return _Resposta(ZIP_2022[ini:fim + 1])

    arquivo = tce.ArquivoRemoto("https://exemplo.org/a.zip", len(ZIP_2022), contato="c", bloco=10, abrir=abrir)
    assert arquivo.read(len(ZIP_2022)) == ZIP_2022[:100]
    assert tamanhos == [100]


def test_so_os_servidores_do_brasil_vao_pelo_intermediario_e_so_com_a_configuracao():
    ambiente = {"LUMEN_PROXY_BR": "https://proxy.exemplo/api/tce", "LUMEN_PROXY_CHAVE": "k"}
    url = tce_rs.URL_ANO.format(ano=2024)
    pedido = urllib.request.Request(url, method="HEAD", headers={**tce.cabecalhos("c"), "Range": "bytes=0-9"})
    novo = tce.pelo_intermediario(pedido, ambiente)
    partes = urllib.parse.urlsplit(novo.full_url)
    assert (partes.netloc, partes.path) == ("proxy.exemplo", "/api/tce")
    assert urllib.parse.parse_qs(partes.query) == {"url": [url]}
    assert novo.get_method() == "HEAD"
    assert novo.get_header("X-lumen-chave") == "k" and novo.get_header("Range") == "bytes=0-9"
    assert novo.get_header("User-agent") == "Lumen (contato: c)"
    outro = urllib.request.Request("https://pit.tce.pr.gov.br/Arquivos/2024_PIT_TodosArquivos.zip")
    assert tce.pelo_intermediario(outro, ambiente) is outro
    assert tce.pelo_intermediario(pedido, {"LUMEN_PROXY_BR": "https://proxy.exemplo/api/tce"}) is pedido
    assert tce.pelo_intermediario(pedido, {}) is pedido


def test_cabecalho_usa_o_tamanho_e_a_etag_originais_que_o_intermediario_repassa(monkeypatch):
    class Cabecalho(io.BytesIO):
        status = 200
        headers = {"Content-Length": "0", "X-Lumen-Tamanho": "129763680", "X-Lumen-Etag": '"e1"', "ETag": '"outra"'}

    monkeypatch.setattr(tce, "abrir", lambda pedido: Cabecalho())
    assert tce.cabecalho(tce_rs.URL_ANO.format(ano=2024), contato="c") == (129763680, '"e1"')


def test_baixar_de_novo_quando_a_conexao_cai_no_meio_da_leitura(monkeypatch):
    class Cortada(io.BytesIO):
        def read(self, *_):
            raise http.client.IncompleteRead(b"meio")

    respostas = iter([Cortada(), _Resposta(b"inteiro", status=200)])
    monkeypatch.setattr(tce, "abrir", lambda pedido: next(respostas))
    esperas = []
    assert tce.baixar("https://exemplo.org/a.json", contato="c", esperar=esperas.append) == b"inteiro"
    assert esperas == [5]
    monkeypatch.setattr(tce, "abrir", lambda pedido: Cortada())
    with pytest.raises(http.client.IncompleteRead):
        tce.baixar("https://exemplo.org/a.json", contato="c", esperar=lambda segundos: None)


def test_quando_ler_de_novo():
    hoje = date(2026, 10, 21)
    lido = {"tamanho": 10, "etiqueta": "a", "lido_em": "2026-10-19T00:00:00Z"}
    assert tce.precisa_ler(None, 10, "a", 2020, hoje)
    assert not tce.precisa_ler(lido, 10, "b", 2020, hoje)             # ano fechado: o tamanho não mudou
    assert tce.precisa_ler(lido, 11, "b", 2020, hoje)
    assert not tce.precisa_ler(lido, 10, "a", 2026, hoje)             # ano corrente sem mudança
    assert not tce.precisa_ler(lido, 10, "b", 2026, hoje)             # mudou, mas foi lido há 2 dias
    assert tce.precisa_ler(lido, 10, "b", 2025, date(2026, 10, 26))


def test_coleta_grava_os_anos_lidos_e_os_nomes_e_publica(tmp_path):
    cabecalhos = {tce_rs.URL_ANO.format(ano=2022): (len(ZIP_2022), "e1")}
    abertos = []

    def remoto(url, tamanho, *, contato):
        abertos.append(url)
        return io.BytesIO(ZIP_2022)

    r = tce_rs.coletar(tmp_path, CADASTRO, contato="c", hoje=date(2023, 3, 1),
                       cabecalho_fn=lambda url, contato: cabecalhos.get(url),
                       texto_fn=lambda url, contato: ORGAOS, remoto_fn=remoto)
    assert r.para_json()["lidos"] == [2022] and r.ausentes == [2016, 2017, 2018, 2019, 2020, 2021, 2023]
    assert r.nomes == 2 and len(abertos) == 2                        # o ano e, no fim, a tabela de pessoas
    estado = comum.ler_json(tmp_path / tce_rs.ARQUIVO)
    assert estado["anos"]["2022"]["entes"]["4319604"][0] == 4 and estado["nomes"]["09537392000105"] == "EMPRESA X LTDA"
    # Na segunda vez, nada mudou: pula o ano e não relê os nomes
    r2 = tce_rs.coletar(tmp_path, CADASTRO, contato="c", hoje=date(2023, 3, 2),
                        cabecalho_fn=lambda url, contato: cabecalhos.get(url),
                        texto_fn=lambda url, contato: ORGAOS, remoto_fn=remoto)
    assert r2.pulados == [2022] and r2.lidos == [] and len(abertos) == 2

    gravados = {}
    resumo = tce.publicar(tmp_path, lambda caminho, dados: gravados.__setitem__(caminho, dados), gerado_em="x")
    assert resumo["tribunais"]["TCE-RS"]["entes"] == 2
    assert resumo["tribunais"]["TCE-RS"]["sem_ente"] == {"2022": [1, 700.0]}
    grupo = gravados[f"tce/ente/{comum.grupo_do_ente('4319604')}.json.gz"]
    sepe = grupo["entes"]["4319604"]
    assert grupo["tipo"] == "tce-entes" and sepe["tribunal"] == "TCE-RS" and sepe["anos"]["2022"][0] == 4
    assert sepe["fornecedores"][0] == ["09537392000105", "EMPRESA X LTDA", [["2022", 2, 1500.5]]]
    assert grupo["tribunais"]["TCE-RS"]["primeiro_ano"] == 2016
    assert tce.publicar(tmp_path / "vazio", lambda *a: None, gerado_em="x") is None
