"""Testes da camada bronze.

A camada bronze é a prova jurídica do projeto. Os testes mais importantes
aqui não são os do caminho feliz, e sim os que garantem que prova alterada
nunca é devolvida em silêncio e que nada é sobrescrito.
"""

import json
import os
import stat
from datetime import datetime, timezone
from pathlib import Path

import pytest

from lumen_ingestao.bronze import (
    ArmazemBronze,
    ArmazemBronzeLocal,
    ArtefatoBruto,
    IntegridadeViolada,
    RegistroColeta,
    RegistroNaoEncontrado,
    sha256_hex,
    validar_fonte_id,
)

URL = "https://transparencia.exemplo.gov.br/contratos?ano=2026"


def artefato(conteudo: bytes = b'{"contrato": 1}', url: str = URL, **extra) -> ArtefatoBruto:
    base = dict(
        conteudo=conteudo,
        fonte_id="pncp",
        url_solicitada=url,
        url_efetiva=url,
        status_http=200,
        tipo_midia="application/json",
        cabecalhos={"Content-Type": "application/json", "Date": "Mon, 28 Sep 2026 10:00:00 GMT"},
        coletado_em=datetime(2026, 9, 28, 10, 0, tzinfo=timezone.utc),
    )
    base.update(extra)
    return ArtefatoBruto(**base)


@pytest.fixture
def armazem(tmp_path) -> ArmazemBronzeLocal:
    return ArmazemBronzeLocal(tmp_path / "bronze")


def _tornar_gravavel(caminho: Path) -> None:
    os.chmod(caminho, stat.S_IRUSR | stat.S_IWUSR)


# --------------------------------------------------------------------------
# Caminho feliz
# --------------------------------------------------------------------------

def test_implementa_a_porta(armazem):
    assert isinstance(armazem, ArmazemBronze)


def test_guardar_e_recuperar_devolve_bytes_identicos(armazem):
    original = artefato(b"conteudo exatamente como publicado \x00\xff")
    registro = armazem.guardar(original)

    recuperado_registro, conteudo = armazem.recuperar(registro.registro_id)

    assert conteudo == original.conteudo
    assert recuperado_registro == registro
    assert registro.sha256 == sha256_hex(original.conteudo)
    assert registro.tamanho_bytes == len(original.conteudo)


def test_registro_preserva_metadados_da_coleta(armazem):
    registro = armazem.guardar(artefato(
        url_efetiva="https://transparencia.exemplo.gov.br/v2/contratos?ano=2026",
        status_http=200,
    ))
    assert registro.url_solicitada == URL
    assert registro.url_efetiva.endswith("/v2/contratos?ano=2026")
    assert registro.fonte_id == "pncp"
    assert registro.tipo_midia == "application/json"
    assert registro.coletado_em == "2026-09-28T10:00:00+00:00"
    assert registro.cabecalhos["date"] == "Mon, 28 Sep 2026 10:00:00 GMT"


def test_resposta_de_erro_e_guardada_como_prova(armazem):
    """Princípio P5: o 404 datado é a prova de que a publicação não existia."""
    registro = armazem.guardar(artefato(b"<h1>Not Found</h1>", status_http=404,
                                        tipo_midia="text/html"))
    recuperado, conteudo = armazem.recuperar(registro.registro_id)
    assert recuperado.status_http == 404
    assert conteudo == b"<h1>Not Found</h1>"


# --------------------------------------------------------------------------
# Versionamento e deduplicação
# --------------------------------------------------------------------------

def test_primeira_coleta_e_versao_1(armazem):
    registro = armazem.guardar(artefato())
    assert registro.versao == 1
    assert registro.mudou_desde_anterior is True


def test_mesmo_conteudo_gera_novo_registro_mas_um_so_objeto(armazem, tmp_path):
    """O conteúdo é deduplicado; o fato de ter sido coletado de novo, não."""
    r1 = armazem.guardar(artefato(b"mesmo"))
    r2 = armazem.guardar(artefato(b"mesmo"))

    assert r1.registro_id != r2.registro_id
    assert (r1.versao, r2.versao) == (1, 2)
    assert r2.mudou_desde_anterior is False
    assert r1.sha256 == r2.sha256

    objetos = [p for p in (tmp_path / "bronze" / "objetos").rglob("*") if p.is_file()]
    assert len(objetos) == 1


def test_conteudo_alterado_na_fonte_fica_registrado(armazem):
    """Um portal que altera contrato já publicado deixa rastro."""
    r1 = armazem.guardar(artefato(b'{"valor": 10000}'))
    r2 = armazem.guardar(artefato(b'{"valor": 95000}'))

    assert r2.versao == 2
    assert r2.mudou_desde_anterior is True
    assert r1.sha256 != r2.sha256

    # a versão anterior continua recuperável: nada foi sobrescrito
    _, antigo = armazem.recuperar(r1.registro_id)
    assert antigo == b'{"valor": 10000}'


def test_historico_ordenado_da_mais_antiga_para_a_mais_recente(armazem):
    for i in range(4):
        armazem.guardar(artefato(f"versao {i}".encode()))
    historico = armazem.historico(URL)
    assert [r.versao for r in historico] == [1, 2, 3, 4]


def test_urls_diferentes_tem_versionamento_independente(armazem):
    a = armazem.guardar(artefato(url="https://a.gov.br/x"))
    b = armazem.guardar(artefato(url="https://b.gov.br/x"))
    assert a.versao == b.versao == 1


def test_historico_de_url_nunca_coletada_e_vazio(armazem):
    assert armazem.historico("https://nunca.gov.br") == []


# --------------------------------------------------------------------------
# Integridade: prova alterada nunca é devolvida em silêncio
# --------------------------------------------------------------------------

def test_leitura_detecta_conteudo_adulterado(armazem, tmp_path):
    registro = armazem.guardar(artefato(b"original"))
    caminho = tmp_path / "bronze" / "objetos" / registro.sha256[:2] / registro.sha256[2:4] / registro.sha256
    _tornar_gravavel(caminho)
    caminho.write_bytes(b"adulterado")

    with pytest.raises(IntegridadeViolada):
        armazem.recuperar(registro.registro_id)


def test_leitura_detecta_objeto_desaparecido(armazem, tmp_path):
    registro = armazem.guardar(artefato(b"vai sumir"))
    caminho = tmp_path / "bronze" / "objetos" / registro.sha256[:2] / registro.sha256[2:4] / registro.sha256
    _tornar_gravavel(caminho)
    caminho.unlink()

    with pytest.raises(IntegridadeViolada):
        armazem.recuperar(registro.registro_id)


def test_nova_gravacao_nao_conserta_objeto_corrompido_em_silencio(armazem, tmp_path):
    """Corrupção de prova é incidente. Esconder o incidente seria pior."""
    registro = armazem.guardar(artefato(b"conteudo"))
    caminho = tmp_path / "bronze" / "objetos" / registro.sha256[:2] / registro.sha256[2:4] / registro.sha256
    _tornar_gravavel(caminho)
    caminho.write_bytes(b"corrompido")

    with pytest.raises(IntegridadeViolada):
        armazem.guardar(artefato(b"conteudo"))


def test_verificar_integridade_lista_os_corrompidos(armazem, tmp_path):
    bom = armazem.guardar(artefato(b"integro", url="https://a.gov.br"))
    ruim = armazem.guardar(artefato(b"sera corrompido", url="https://b.gov.br"))
    caminho = tmp_path / "bronze" / "objetos" / ruim.sha256[:2] / ruim.sha256[2:4] / ruim.sha256
    _tornar_gravavel(caminho)
    caminho.write_bytes(b"x")

    assert armazem.verificar_integridade() == [ruim.sha256]
    assert bom.sha256 not in armazem.verificar_integridade()


def test_objeto_gravado_fica_somente_leitura(armazem, tmp_path):
    registro = armazem.guardar(artefato())
    caminho = tmp_path / "bronze" / "objetos" / registro.sha256[:2] / registro.sha256[2:4] / registro.sha256
    assert not (caminho.stat().st_mode & stat.S_IWUSR)


# --------------------------------------------------------------------------
# Imutabilidade dos registros
# --------------------------------------------------------------------------

def test_registro_nunca_e_sobrescrito(armazem, tmp_path, monkeypatch):
    """Mesmo forçando colisão de id, a gravação falha em vez de sobrescrever."""
    import lumen_ingestao.bronze as bronze

    class IdFixo:
        hex = "a" * 32

    monkeypatch.setattr(bronze.uuid, "uuid4", lambda: IdFixo())
    armazem.guardar(artefato(b"primeiro", url="https://a.gov.br"))
    with pytest.raises(FileExistsError):
        armazem.guardar(artefato(b"segundo", url="https://b.gov.br"))

    registro, conteudo = armazem.recuperar("a" * 32)
    assert conteudo == b"primeiro"


def test_versao_reservada_sem_registro_e_reportada_e_ignorada(armazem, tmp_path):
    """Queda entre a reserva de versão e a escrita do registro."""
    armazem.guardar(artefato(b"ok"))
    dir_url = next((tmp_path / "bronze" / "por_url").glob("*/*"))
    (dir_url / "v000002.json").write_text(json.dumps(
        {"registro_id": "inexistente", "sha256": "0" * 64, "url": URL}))

    assert len(armazem.historico(URL)) == 1
    assert armazem.verificar_consistencia() == [f"{URL} v000002"]


def test_recuperar_id_inexistente(armazem):
    with pytest.raises(RegistroNaoEncontrado):
        armazem.recuperar("0" * 32)


def test_registro_serializa_e_desserializa(armazem):
    registro = armazem.guardar(artefato())
    assert RegistroColeta.de_json(registro.para_json()) == registro


# --------------------------------------------------------------------------
# Segurança
# --------------------------------------------------------------------------

def test_cabecalhos_com_credencial_sao_descartados(armazem):
    registro = armazem.guardar(artefato(cabecalhos={
        "Set-Cookie": "sessao=segredo",
        "Authorization": "Bearer xyz",
        "ETag": '"abc"',
        "Last-Modified": "Mon, 01 Sep 2026 00:00:00 GMT",
    }))
    assert "set-cookie" not in registro.cabecalhos
    assert "authorization" not in registro.cabecalhos
    assert registro.cabecalhos["etag"] == '"abc"'
    assert "last-modified" in registro.cabecalhos


@pytest.mark.parametrize("fonte_id", ["../../etc", "a/b", "", "PNCP", "-x", "a b", "x" * 200])
def test_fonte_id_perigoso_e_recusado(fonte_id):
    with pytest.raises(ValueError):
        validar_fonte_id(fonte_id)


@pytest.mark.parametrize("fonte_id", ["pncp", "siconfi", "sp_campinas_contratos", "tce-sp", "cgu2"])
def test_fonte_id_valido(fonte_id):
    assert validar_fonte_id(fonte_id) == fonte_id


def test_artefato_exige_fuso_horario():
    with pytest.raises(ValueError):
        artefato(coletado_em=datetime(2026, 9, 28, 10, 0))
