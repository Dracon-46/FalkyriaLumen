"""Portais de transparência pelo PNTP para a visão 360: coleta incremental, estado e arquivos por UF."""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from lumen_ingestao.bronze import ArtefatoBruto
from lumen_ingestao.coleta_http import ErroColeta
from lumen_painel import cli, transparencia

FIX = Path(__file__).resolve().parents[3] / "testes" / "fixtures" / "pntp"
AGORA = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)


class _Cliente:
    """Responde a página de downloads do Radar (trecho real) ou um status/erro escolhido."""

    def __init__(self, status=200, falhar=False, corpo=None):
        self.status, self.falhar, self.corpo = status, falhar, corpo

    def obter(self, url, cabecalhos=None):
        if self.falhar:
            raise ErroColeta("sem resposta")
        corpo = self.corpo if self.corpo is not None else (FIX / "downloads_trecho.html").read_bytes()
        return ArtefatoBruto(conteudo=corpo, fonte_id="pntp_avaliacoes", url_solicitada=url, url_efetiva=url,
                             status_http=self.status, tipo_midia="text/html")


class _Membro:
    def __init__(self, conteudo, marca):
        self.conteudo, self.ultima_modificacao, self.etag = conteudo, marca, None


def _baixar(marca="Tue, 10 Feb 2026 13:35:32 GMT", arquivo="avaliacoes_pntp_2025_amostra.xlsx", pedidos=None):
    def baixar(cliente, url, nome):
        if pedidos is not None:
            pedidos.append((url, nome))
        return _Membro((FIX / arquivo).read_bytes(), marca)
    return baixar


def test_coleta_grava_as_entidades_e_nao_repete_o_mesmo_arquivo(tmp_path):
    pedidos = []
    r = transparencia.coletar(_Cliente(), tmp_path, baixar=_baixar(pedidos=pedidos), agora=AGORA)
    assert r.falha is None and r.ciclo == 2025 and r.entidades > 0 and not r.mantido
    assert pedidos == [(transparencia.url_zip(2025), "pntp_2025/avaliacoes_pntp_2025.xlsx")]
    dados = transparencia.ler_estado(tmp_path)
    assert dados["colunas"] == list(transparencia.COLUNAS) and len(dados["entidades"]) == r.entidades
    r2 = transparencia.coletar(_Cliente(), tmp_path, baixar=_baixar(), agora=AGORA)
    assert r2.mantido and r2.entidades == r.entidades
    r3 = transparencia.coletar(_Cliente(), tmp_path, baixar=_baixar(marca="outra"), agora=AGORA)
    assert not r3.mantido


def test_arquivos_por_uf_agrupados_pelo_ente(tmp_path):
    transparencia.coletar(_Cliente(), tmp_path, baixar=_baixar(), agora=AGORA)
    gravados = {}
    resumo = transparencia.publicar(tmp_path, lambda nome, c: gravados.__setitem__(nome, c), gerado_em="G")
    assert resumo["ciclo"] == 2025 and resumo["arquivos"] == len(gravados) and resumo["entes"] > 0
    for nome, arquivo in gravados.items():
        assert nome.startswith("transparencia/") and arquivo["tipo"] == "transparencia" and arquivo["ciclo"] == 2025
        for codigo, entidades in arquivo["entes"].items():
            assert transparencia.arquivo_do_ente(codigo) == nome
            assert all(set(e) == set(transparencia.COLUNAS) - {"ente"} for e in entidades)
    assert transparencia.arquivo_do_ente("3550308") == "transparencia/uf-sp.json"
    assert transparencia.arquivo_do_ente("1") == "transparencia/uniao.json"
    assert transparencia.arquivo_do_ente("53") == "transparencia/uf-df.json"


def test_falhas_mantem_o_ciclo_anterior(tmp_path):
    transparencia.coletar(_Cliente(), tmp_path, baixar=_baixar(), agora=AGORA)
    antes = len(transparencia.ler_estado(tmp_path)["entidades"])
    for cliente, motivo in ((_Cliente(falhar=True), "sem resposta"), (_Cliente(status=503), "503"),
                            (_Cliente(corpo=b"<html>sem ciclos</html>"), "nenhum ciclo")):
        r = transparencia.coletar(cliente, tmp_path, baixar=_baixar(), agora=AGORA)
        assert motivo in r.falha
    dados = transparencia.ler_estado(tmp_path)
    assert len(dados["entidades"]) == antes and "nenhum ciclo" in dados["ultima_falha"]["motivo"]


def test_planilha_sem_entidades_e_falha(tmp_path):
    r = transparencia.coletar(_Cliente(), tmp_path, baixar=_baixar(arquivo="avaliacoes_pntp_2022_cabecalho.xlsx"),
                              agora=AGORA)
    assert "sem nenhuma entidade" in r.falha
    gravados = {}
    assert transparencia.publicar(tmp_path, lambda n, c: gravados.__setitem__(n, c), gerado_em="G")["arquivos"] == 0


def test_estado_de_outra_versao(tmp_path):
    from lumen_painel.comum import gravar_json
    gravar_json(tmp_path / transparencia.ARQUIVO_ESTADO, {"versao": 5}, comprimir=True)
    with pytest.raises(ValueError, match="versão 5"):
        transparencia.ler_estado(tmp_path)


def test_cli(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("LUMEN_CONTATO", "a@b.org")
    from lumen_orquestracao import etapas
    monkeypatch.setattr(etapas, "cliente", lambda cfg, fonte: _Cliente())
    monkeypatch.setattr(transparencia, "baixar_membro", _baixar())
    original = transparencia.coletar
    monkeypatch.setattr(transparencia, "coletar", lambda c, e: original(c, e, baixar=_baixar()))
    assert cli.main(["--config", str(tmp_path / "x.toml"), "transparencia", "--estado", str(tmp_path)]) == 0
    assert '"ciclo": 2025' in capsys.readouterr().out
    assert cli.main(["--config", str(tmp_path / "x.toml"), "publicar", "--estado", str(tmp_path),
                     "--saida", str(tmp_path / "site")]) == 0
    assert list((tmp_path / "site" / "transparencia").glob("uf-*.json"))
