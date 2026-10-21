"""Visão 360 da pessoa jurídica pelo CNPJ (ADR-049)."""

from __future__ import annotations

from lumen_painel import comum, convenios, emendas
from lumen_painel import pessoas_juridicas as pj
from lumen_painel.contratacoes import Acumulador, Fornecedor, Painel

EMPRESA = "09537392000105"
FUNDO = "12231796000172"


def _painel() -> Painel:
    p = Painel()
    sao_sepe, rs = Acumulador(), Acumulador()
    f = sao_sepe.fornecedores[EMPRESA] = Fornecedor("EMPRESA X LTDA")
    f.contrato("2025-03", 100.0)
    f.contrato("2025-07", 50.0)
    f.contrato("2026-01", None)                      # a conferir: conta, não soma
    rs.fornecedores[EMPRESA] = Fornecedor("EMPRESA X LTDA")
    rs.fornecedores[EMPRESA].contrato("2026-02", 1000.0)
    p.entes = {"4319604": sao_sepe, "43": rs}
    return p


def _estados(pasta) -> None:
    comum.gravar_json(pasta / emendas.ARQUIVO, {
        "versao": emendas.VERSAO_ESTADO, "data_arquivo": "20261010",
        "colunas_recebido": ["ano", "emenda", "categoria", "cnpj", "favorecido", "valor"],
        "recebido": {"4319604": [["2022", "E1", "governo_municipal", FUNDO, "FUNDO MUNICIPAL DE SAUDE", 100.0],
                                 ["2022", "E2", "governo_municipal", FUNDO, "FUNDO MUNICIPAL DE SAUDE", 50.0],
                                 ["2023", "E3", "empresa", EMPRESA, "EMPRESA X", 30.0],
                                 ["2023", "E3", "pessoa_fisica", None, None, 5.0]]}}, comprimir=True)
    comum.gravar_json(pasta / convenios.ARQUIVO, {
        "versao": convenios.VERSAO_ESTADO, "data_arquivo": "20261009",
        "colunas": ["numero", "situacao", "objeto", "orgao", "categoria", "cnpj", "convenente", "valor", "liberado",
                    "contrapartida", "inicio", "fim", "ultima_liberacao"],
        "convenios": {"4319604": [["9", "CONCLUÍDO", "Praça " + "x" * 300, "Ministério das Cidades", "governo_municipal",
                                   FUNDO, "FUNDO", 100.0, 100.0, 0.0, "2021-03-01", "2022-03-01", None]]}},
        comprimir=True)


def test_indice_por_cnpj_com_contratos_emendas_e_convenios(tmp_path):
    _estados(tmp_path)
    gravados = {}
    resumo = pj.publicar(tmp_path, _painel(), lambda caminho, dados: gravados.__setitem__(caminho, dados),
                         gerado_em="x")
    assert resumo == {"pessoas": 2, "arquivos": 2, "com_contratos": 1, "com_emendas": 2, "com_convenios": 1}
    grupo = gravados[f"pj/{comum.grupo_do_cnpj(EMPRESA)}.json.gz"]
    assert grupo["tipo"] == "pessoas-juridicas" and grupo["fontes"] == {"emendas": "20261010", "convenios": "20261009"}
    empresa = grupo["pessoas"][EMPRESA]
    assert empresa["nome"] == "EMPRESA X LTDA"                        # o das contratações vale sobre o das emendas
    assert empresa["contratos"] == [["43", "2026", 1, 1000.0], ["4319604", "2025", 2, 150.0],
                                    ["4319604", "2026", 1, 0.0]]
    assert empresa["emendas"] == [["4319604", "2023", 30.0]] and empresa["convenios"] == []
    fundo = gravados[f"pj/{comum.grupo_do_cnpj(FUNDO)}.json.gz"]["pessoas"][FUNDO]
    assert fundo["nome"] == "FUNDO" and fundo["contratos"] == []       # sem contratos, o nome do convênio
    assert fundo["emendas"] == [["4319604", "2022", 150.0]]
    assert fundo["convenios"][0][:3] == ["4319604", "9", "CONCLUÍDO"] and len(fundo["convenios"][0][3]) == pj.OBJETO


def test_sem_estado_de_emendas_e_convenios_so_os_contratos(tmp_path):
    gravados = {}
    resumo = pj.publicar(tmp_path, _painel(), lambda caminho, dados: gravados.__setitem__(caminho, dados),
                         gerado_em="x")
    assert resumo["pessoas"] == 1 and resumo["com_emendas"] == 0
    assert list(gravados.values())[0]["fontes"] == {"emendas": None, "convenios": None}
