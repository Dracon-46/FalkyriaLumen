"""Normalização dos cadastros de sanções da CGU (CEIS, CNEP, CEPIM) com as amostras reais."""

import io
import json
import zipfile
from datetime import date
from decimal import Decimal

import pytest

from lumen_canonico.fato import CadastroSancao, Esfera, Sancao, TipoPessoa
from lumen_canonico.identidade import id_canonico
from lumen_normalizacao import cgu
from lumen_normalizacao.cgu import (
    DATA_FIM_DISTANTE,
    abrir_arquivo,
    data_do_nome,
    decodificar,
    normalizar_sancoes,
)
from lumen_normalizacao.qualidade import DOCUMENTO_FORNECEDOR_INVALIDO, ESFERA_NAO_INFORMADA

HOJE = date(2026, 10, 16)


def _norm(conteudo, fonte_id="cgu_ceis"):
    return normalizar_sancoes(conteudo, fonte_id=fonte_id, documento_fonte_id="reg1", hoje=HOJE)


def _por_chave(resultado):
    return {r.chave_origem: r for r in resultado.registros}


def _zip(nome, csv_texto, codificacao="latin-1"):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(nome, csv_texto.encode(codificacao))
    return buf.getvalue()


CABECALHO_CEIS = ";".join(f'"{c}"' for c in cgu.COLUNAS_SANCAO)


def _linha_ceis(**troca):
    base = dict.fromkeys(cgu.COLUNAS_SANCAO, "")
    base.update({"CADASTRO": "CEIS", "CÓDIGO DA SANÇÃO": "1", "TIPO DE PESSOA": "J",
                 "CPF OU CNPJ DO SANCIONADO": "14310577000104", "NOME DO SANCIONADO": "EMPRESA",
                 "DATA INÍCIO SANÇÃO": "01/02/2024", "ESFERA ÓRGÃO SANCIONADOR": "FEDERAL"})
    base.update(troca)
    return ";".join(f'"{base[c]}"' for c in cgu.COLUNAS_SANCAO)


def _csv_ceis(*linhas):
    return "\r\n".join([CABECALHO_CEIS, *linhas]) + "\r\n"


# ------------------------------------------------------------------ amostras reais

def test_ceis_real(fixture_bytes):
    r = _norm(fixture_bytes("cgu/ceis_amostra.zip"))
    assert (r.lidos, len(r.registros), len(r.quarentena)) == (6, 6, 0)
    assert all(isinstance(s, Sancao) and s.cadastro is CadastroSancao.CEIS for s in r.registros)
    assert {s.data_referencia for s in r.registros} == {date(2026, 10, 15)}
    s = _por_chave(r)
    coesa = s["367110"]
    assert coesa.documento == "14310577000104" and coesa.tipo_pessoa is TipoPessoa.JURIDICA
    assert coesa.fornecedor_id == id_canonico("fornecedor", "14310577000104")  # o mesmo id do PNCP
    assert coesa.data_fim == date(2099, 9, 19) and DATA_FIM_DISTANTE in coesa.marcacoes_qualidade
    assert coesa.esfera_orgao_sancionador is Esfera.ESTADUAL
    assert coesa.id == id_canonico("sancao", "CEIS", "367110")
    assert s["70548"].data_fim is None  # inidoneidade sem prazo determinado
    assert ESFERA_NAO_INFORMADA in s["348982"].marcacoes_qualidade
    assert s["348982"].esfera_orgao_sancionador is None


def test_cpf_do_ceis_sai_mascarado_e_nao_gera_id_reversivel(fixture_bytes):
    r = _norm(fixture_bytes("cgu/ceis_amostra.zip"))
    pf = _por_chave(r)["900000001"]
    assert pf.tipo_pessoa is TipoPessoa.FISICA
    assert pf.documento == "***.456.789-**"
    assert pf.fornecedor_id == id_canonico("fornecedor_pf", "***.456.789-**", "PESSOA FISICA FICTICIA DE TESTE")
    assert pf.razao_social_receita is None
    linhas = json.dumps([x.para_dict() for x in r.registros], ensure_ascii=False)
    assert "12345678909" not in linhas and "123.456.789-09" not in linhas


def test_estrangeiro_sem_tipo_e_documento_curto_fica_sem_documento(fixture_bytes):
    davati = _por_chave(_norm(fixture_bytes("cgu/ceis_amostra.zip")))["298939"]
    assert davati.tipo_pessoa is None and davati.documento is None and davati.fornecedor_id is None
    assert DOCUMENTO_FORNECEDOR_INVALIDO in davati.marcacoes_qualidade
    assert davati.nome == "Davati Medical Supply LLC"
    assert davati.razao_social_receita is None


def test_cnep_real_com_multa(fixture_bytes):
    r = _norm(fixture_bytes("cgu/cnep_amostra.zip"), "cgu_cnep")
    assert (len(r.registros), len(r.quarentena)) == (3, 0)
    multa = _por_chave(r)["106565"]
    assert multa.cadastro is CadastroSancao.CNEP
    assert multa.valor_multa == Decimal("710.57")
    assert multa.abrangencia == "No órgão sancionador"
    assert multa.esfera_orgao_sancionador is Esfera.MUNICIPAL and multa.uf_orgao_sancionador == "RS"
    assert _por_chave(r)["900000002"].documento == "***.456.789-**"


def test_cepim_real_sem_datas(fixture_bytes):
    r = _norm(fixture_bytes("cgu/cepim_amostra.zip"), "cgu_cepim")
    assert (len(r.registros), len(r.quarentena)) == (3, 0)
    e = r.registros[0]
    assert e.cadastro is CadastroSancao.CEPIM and e.data_referencia == date(2026, 10, 14)
    assert e.data_inicio is None and e.data_fim is None
    assert e.numero_convenio and e.chave_origem == f"{e.documento}/{e.numero_convenio}"
    assert e.id == id_canonico("sancao", "CEPIM", e.documento, e.numero_convenio)
    assert e.esfera_orgao_sancionador is Esfera.UNIAO and e.orgao_sancionador


def test_serializacao_vai_para_a_silver(fixture_bytes):
    d = _norm(fixture_bytes("cgu/cnep_amostra.zip"), "cgu_cnep").registros[0].para_dict()
    assert d["_entidade"] == "sancao" and d["cadastro"] == "CNEP" and d["valor_multa"] == "710.57"
    assert d["fonte_id"] == "cgu_cnep" and d["documento_fonte_id"] == "reg1"


# ------------------------------------------------------------------ casos de borda

def test_sem_informacao_vira_nulo():
    r = _norm(_zip("20261015_CEIS.csv", _csv_ceis(_linha_ceis(**{
        "ABRAGÊNCIA DA SANÇÃO": "Sem Informação", "PUBLICAÇÃO": "Sem Informação",
        "RAZÃO SOCIAL - CADASTRO RECEITA": "SEM INFORMACAO"}))))
    s = r.registros[0]
    assert s.abrangencia is None and s.meio_publicacao is None and s.razao_social_receita is None


def test_sem_inicio_da_sancao_vai_para_a_quarentena():
    r = _norm(_zip("20261015_CEIS.csv", _csv_ceis(_linha_ceis(), _linha_ceis(**{
        "CÓDIGO DA SANÇÃO": "2", "DATA INÍCIO SANÇÃO": ""}))))
    assert len(r.registros) == 1
    q = r.quarentena[0]
    assert (q.campo, q.chave_origem, q.posicao) == ("DATA INÍCIO SANÇÃO", "2", 1)


def test_data_ilegivel_vai_para_a_quarentena():
    r = _norm(_zip("20261015_CEIS.csv", _csv_ceis(_linha_ceis(**{"DATA FINAL SANÇÃO": "31/02/2027"}))))
    assert not r.registros and r.quarentena[0].campo == "DATA FINAL SANÇÃO"


def test_linha_de_outro_cadastro_e_cadastro_desconhecido_sao_rejeitados():
    r = _norm(_zip("20261015_CEIS.csv", _csv_ceis(_linha_ceis(CADASTRO="CNEP"), _linha_ceis(CADASTRO="XYZ"))))
    assert not r.registros
    assert [q.motivo for q in r.quarentena] == ["cadastro da linha diverge do arquivo", "cadastro desconhecido"]


def test_cpf_sem_tipo_de_pessoa_tambem_sai_mascarado():
    r = _norm(_zip("20261015_CEIS.csv", _csv_ceis(_linha_ceis(**{
        "TIPO DE PESSOA": "", "CPF OU CNPJ DO SANCIONADO": "12345678909", "NOME DO SANCIONADO": "FULANO"}))))
    s = r.registros[0]
    assert s.documento == "***.456.789-**" and s.tipo_pessoa is None


def test_cabecalho_sem_coluna_vai_inteiro_para_a_quarentena():
    r = _norm(_zip("20261015_CEIS.csv", '"CADASTRO";"CÓDIGO DA SANÇÃO"\r\n"CEIS";"1"\r\n'))
    assert not r.registros and len(r.quarentena) == 1
    assert "formato da fonte mudou" in r.quarentena[0].motivo


def test_cepim_com_cnpj_invalido_e_rejeitado():
    csv_texto = ('"CNPJ ENTIDADE";"NOME ENTIDADE";"NÚMERO CONVÊNIO";"ÓRGÃO CONCEDENTE";"MOTIVO DO IMPEDIMENTO"\r\n'
                 '"11111111111111";"ENTIDADE";"1";"Ministério";"MOTIVO"\r\n')
    r = _norm(_zip("20261014_CEPIM.csv", csv_texto), "cgu_cepim")
    assert not r.registros and r.quarentena[0].campo == "CNPJ ENTIDADE"


def test_csv_fora_do_zip_e_sem_data_no_nome_marca_a_referencia():
    r = _norm(_csv_ceis(_linha_ceis()).encode("latin-1"))
    s = r.registros[0]
    assert s.data_referencia is None and cgu.DATA_REFERENCIA_AUSENTE in s.marcacoes_qualidade


def test_artefato_vazio_e_zip_estranho():
    assert not _norm(b"").registros
    r = _norm(_zip("leia-me.txt", "nada"))
    assert not r.registros and "arquivo ilegível" in r.quarentena[0].motivo


@pytest.mark.parametrize("conteudo,esperado", [
    ("Órgão".encode("utf-8"), "Órgão"),
    ("Órgão – “x”".encode("cp1252"), "Órgão – “x”"),
    (b"\xd3rg\xe3o \x81", "Órgão \x81"),
])
def test_decodificar(conteudo, esperado):
    assert decodificar(conteudo) == esperado


def test_data_do_nome_e_abrir_arquivo():
    assert data_do_nome("20261015_CEIS.csv") == date(2026, 10, 15)
    assert data_do_nome("20261399_CEIS.csv") is None
    assert data_do_nome(None) is None
    assert abrir_arquivo(b"a;b") == (None, b"a;b")
    duplo = io.BytesIO()
    with zipfile.ZipFile(duplo, "w") as z:
        z.writestr("a.csv", "x")
        z.writestr("b.csv", "y")
    with pytest.raises(ValueError, match="2 arquivos CSV"):
        abrir_arquivo(duplo.getvalue())
