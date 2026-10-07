"""Camada silver: gravação idempotente por artefato e partição, quarentena e consolidação pela versão mais recente."""

import json

from lumen_normalizacao import pncp
from lumen_normalizacao.silver import EscritorSilver, consolidar, ler_entidade

PROV = dict(fonte_id="pncp_contratacoes", documento_fonte_id="reg0001")


def test_grava_particionado_e_idempotente(tmp_path, fixture_bytes):
    bruto = fixture_bytes("pncp/contratacoes_publicacao_dispensa_20260901_p1.json")
    r = pncp.normalizar_contratacoes(bruto, **PROV)
    escritor = EscritorSilver(tmp_path, pncp.VERSAO_NORMALIZADOR)
    arquivos = escritor.gravar("reg0001", r.registros, coletado_em="2026-10-05T11:00:00+00:00")
    assert any("processo_contratacao/exercicio=2026/uf=RS" in a.as_posix() for a in arquivos)
    antes = {a: a.read_bytes() for a in arquivos}
    # reprocessar o mesmo artefato produz exatamente os mesmos bytes
    arquivos2 = escritor.gravar("reg0001", r.registros, coletado_em="2026-10-05T11:00:00+00:00")
    assert {a: a.read_bytes() for a in arquivos2} == antes
    linhas = ler_entidade(tmp_path, "processo_contratacao")
    assert len(linhas) == 4
    assert all(linha["_versao_normalizador"] == "pncp-1" for linha in linhas)


def test_orgao_repetido_na_pagina_vira_uma_linha(tmp_path):
    def item(seq):
        return {
            "numeroControlePNCP": f"97229181000164-1-{seq:06d}/2026",
            "orgaoEntidade": {"cnpj": "97229181000164", "esferaId": "M", "poderId": "E"},
            "unidadeOrgao": {"codigoIbge": "4319604", "codigoUnidade": "1", "ufSigla": "RS"},
            "anoCompra": 2026, "sequencialCompra": seq, "objetoCompra": "x",
            "dataPublicacaoPncp": "2026-09-01T10:00:00", "modalidadeId": 8,
        }
    bruto = json.dumps({"data": [item(1), item(2)]}).encode()
    r = pncp.normalizar_contratacoes(bruto, **PROV)
    EscritorSilver(tmp_path, "t").gravar("reg0002", r.registros)
    assert len(ler_entidade(tmp_path, "orgao")) == 1
    assert len(ler_entidade(tmp_path, "processo_contratacao")) == 2


def test_quarentena_gravada_e_apagada_quando_some(tmp_path, fixture_bytes):
    r = pncp.normalizar_atas(fixture_bytes("pncp/atas_20260901_p1.json"), **PROV)
    escritor = EscritorSilver(tmp_path, "t")
    destino = escritor.gravar_quarentena("pncp_atas", "reg0003", r.quarentena)
    assert destino.exists()
    assert json.loads(destino.read_text(encoding="utf-8").splitlines()[0])["campo"] == "vigenciaFim"
    assert escritor.gravar_quarentena("pncp_atas", "reg0003", []) is None
    assert not destino.exists()


def test_nome_inseguro_e_recusado(tmp_path):
    import pytest
    with pytest.raises(ValueError):
        EscritorSilver(tmp_path, "t").gravar("../fora", [])


def test_consolidar_fica_com_a_versao_mais_recente():
    linhas = [
        {"id": "a", "atualizado_em": "2026-09-01T00:00:00-03:00", "_coletado_em": "1", "v": 1},
        {"id": "a", "atualizado_em": "2026-09-02T00:00:00-03:00", "_coletado_em": "0", "v": 2},
        {"id": "b", "atualizado_em": None, "_coletado_em": "1", "v": 3},
        {"id": "b", "atualizado_em": None, "_coletado_em": "2", "v": 4},
    ]
    assert [linha["v"] for linha in consolidar(linhas)] == [2, 4]


def test_particao_sem_ano_usa_data(tmp_path):
    from datetime import date

    from lumen_canonico.fato import AtaRegistroPreco
    ata = AtaRegistroPreco(
        id="x", chave_origem="c", processo_chave_origem=None, processo_id=None,
        orgao_cnpj="97229181000164", orgao_nome=None, unidade_codigo=None, unidade_nome=None,
        numero=None, ano=None, objeto=None, data_assinatura=date(2024, 5, 1),
        vigencia_inicio=None, vigencia_fim=None, cancelada=False, data_cancelamento=None,
        sistema_origem=None,
    )
    arquivos = EscritorSilver(tmp_path, "t").gravar("reg0004", [ata])
    assert "exercicio=2024/uf=NA" in arquivos[0].as_posix()
