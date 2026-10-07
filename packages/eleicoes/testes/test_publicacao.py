"""Publicação na nuvem (ADR-026): feeds no bucket público, estado da carga no privado, carga retomável."""

from __future__ import annotations

import json
import urllib.request
from datetime import date
from pathlib import Path

import pytest

from lumen_eleicoes import antigas, carga, cli, publicacao
from lumen_eleicoes.coletor import FONTE_ID
from lumen_eleicoes.configuracao import ConfiguracaoAusente, carregar, carregar_publicacao
from lumen_eleicoes.preparacao import OpcoesPreparacao, Preparacao
from lumen_eleicoes.publicacao import Nuvem, ResumoPublicacao
from lumen_ingestao.cliente_http import ClienteHttp
from lumen_ingestao.s3 import ClienteS3

SEM_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))
PUB, PRIV = "lumen-eleicoes", "lumen-privado"


def _cliente_s3(srv, bucket: str) -> ClienteS3:
    return ClienteS3(endpoint=srv.endpoint, bucket=bucket, chave_acesso="a", chave_secreta="s", regiao="auto",
                     abridor=SEM_PROXY)


def _nuvem(srv, saida: Path, estado: Path, avisos: list | None = None) -> Nuvem:
    return Nuvem(_cliente_s3(srv, PUB), _cliente_s3(srv, PRIV), saida, estado,
                 aviso=(avisos.append if avisos is not None else lambda m: None))


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("LUMEN_CONTATO", "c@exemplo.org")
    for v in ("LUMEN_ELEICOES_SAIDA", "LUMEN_PUBLICACAO_ENDPOINT", "LUMEN_PUBLICACAO_BUCKET",
              "LUMEN_PUBLICACAO_BUCKET_ESTADO", "LUMEN_PUBLICACAO_REGIAO", "LUMEN_S3_CHAVE_ACESSO",
              "LUMEN_S3_CHAVE_SECRETA"):
        monkeypatch.delenv(v, raising=False)
    toml = tmp_path / "lumen.toml"
    toml.write_text(f'[dados]\nraiz = "{(tmp_path / "dados").as_posix()}"\n[eleicoes]\n'
                    f'saida = "{(tmp_path / "feeds").as_posix()}"\nrpm_resultados = 60000\n'
                    'rpm_dados_abertos = 60000\n', encoding="utf-8")
    c = carregar(toml)
    c.toml = toml
    return c


# ------------------------------------------------------------------ partes

def test_tipo_e_cache_por_arquivo():
    assert publicacao.tipo_de("indice.json").startswith("application/json")
    assert publicacao.tipo_de("fotos/sp/1.jpg") == "image/jpeg"
    assert publicacao.tipo_de("x.bin") == "application/octet-stream"
    assert publicacao.cache_de("2026-1t-geral/presidente/br.json") == "no-cache"
    assert publicacao.cache_de("indice.json") == "no-cache"
    assert publicacao.cache_de("geo/br-uf.json").startswith("public, max-age=")
    assert publicacao.cache_de("municipios.json").startswith("public")


def test_arquivos_publicaveis_e_cache_de_hash(tmp_path, monkeypatch):
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "x.json").write_text("{}")
    (tmp_path / "a" / ".x.json.123.tmp").write_text("{")
    (tmp_path / "LEIAME.md").write_text("doc")
    (tmp_path / "geo").mkdir()
    (tmp_path / "geo" / "br-uf.json.tmp").write_text("{")
    cache: dict = {}
    assert list(publicacao.arquivos_publicaveis(tmp_path, cache)) == ["a/x.json"]
    chamadas = []
    original = publicacao.sha256_de
    monkeypatch.setattr(publicacao, "sha256_de", lambda p: chamadas.append(p) or original(p))
    publicacao.arquivos_publicaveis(tmp_path, cache)
    assert chamadas == []                                    # nada mudou: nenhum arquivo relido
    assert publicacao.arquivos_publicaveis(tmp_path / "nao-existe") == {}


def test_configuracao_da_publicacao(tmp_path, monkeypatch):
    for v in ("LUMEN_PUBLICACAO_ENDPOINT", "LUMEN_PUBLICACAO_BUCKET", "LUMEN_PUBLICACAO_BUCKET_ESTADO",
              "LUMEN_PUBLICACAO_REGIAO", "LUMEN_S3_CHAVE_ACESSO", "LUMEN_S3_CHAVE_SECRETA"):
        monkeypatch.delenv(v, raising=False)
    toml = tmp_path / "lumen.toml"
    toml.write_text('[publicacao]\nendpoint = "https://conta.r2.cloudflarestorage.com/"\nbucket = "pub"\n',
                    encoding="utf-8")
    with pytest.raises(ConfiguracaoAusente, match="LUMEN_S3_CHAVE_ACESSO"):
        carregar_publicacao(toml)
    monkeypatch.setenv("LUMEN_S3_CHAVE_ACESSO", "a")
    monkeypatch.setenv("LUMEN_S3_CHAVE_SECRETA", "s")
    pub = carregar_publicacao(toml)
    assert (pub.endpoint, pub.bucket, pub.bucket_estado, pub.regiao) == (
        "https://conta.r2.cloudflarestorage.com", "pub", "pub", "auto")
    monkeypatch.setenv("LUMEN_PUBLICACAO_BUCKET_ESTADO", "priv")
    monkeypatch.setenv("LUMEN_PUBLICACAO_BUCKET", "outro")
    pub = carregar_publicacao(toml)
    assert (pub.bucket, pub.bucket_estado) == ("outro", "priv")


# ------------------------------------------------------------------ Nuvem

def test_publica_so_o_que_mudou_com_o_indice_por_ultimo(tmp_path, s3_memoria):
    saida, estado = tmp_path / "feeds", tmp_path / "estado"
    (saida / "2026-1t-geral" / "presidente").mkdir(parents=True)
    (saida / "2026-1t-geral" / "presidente" / "br.json").write_text('{"v":1}')
    (saida / "geo").mkdir()
    (saida / "geo" / "br-uf.json").write_text("{}")
    (saida / "indice.json").write_text('{"versao":1,"eleicoes":[]}')
    estado.mkdir()
    (estado / "preparar.json").write_text('{"anos":{}}')
    nuvem = _nuvem(s3_memoria, saida, estado)
    r = nuvem.sincronizar()
    assert (r.enviados, r.iguais) == (3, 0)
    feeds_enviados = [c for b, c in s3_memoria.puts if b == PUB]
    assert feeds_enviados[-1] == "indice.json"
    _, cab = s3_memoria.objetos[(PUB, "geo/br-uf.json")]
    assert cab["cache-control"].startswith("public") and cab["content-type"].startswith("application/json")
    assert s3_memoria.objetos[(PUB, "indice.json")][1]["cache-control"] == "no-cache"
    manifesto = json.loads(s3_memoria.corpo(PRIV, "publicacao.json"))["arquivos"]
    assert set(manifesto) == {"indice.json", "geo/br-uf.json", "2026-1t-geral/presidente/br.json"}
    assert s3_memoria.chaves(PRIV) == ["estado/preparar.json", "publicacao.json"]

    # Nada mudou: nada sobe. Um feed mudou: só ele (o manifesto é lido do bucket, numa Nuvem nova).
    s3_memoria.puts.clear()
    assert _nuvem(s3_memoria, saida, estado).publicar().enviados == 0
    (saida / "2026-1t-geral" / "presidente" / "br.json").write_text('{"v":2}')
    avisos = []
    r = _nuvem(s3_memoria, saida, estado, avisos).publicar()
    assert (r.enviados, r.iguais) == (1, 2)
    assert s3_memoria.corpo(PUB, "2026-1t-geral/presidente/br.json") == b'{"v":2}'
    assert "1 arquivo(s) publicado(s)" in avisos[0]


def test_manifesto_regravado_em_lotes(tmp_path, s3_memoria, monkeypatch):
    monkeypatch.setattr(publicacao, "LOTE_MANIFESTO", 2)
    saida = tmp_path / "feeds"
    saida.mkdir()
    for i in range(5):
        (saida / f"f{i}.json").write_text(str(i))
    _nuvem(s3_memoria, saida, tmp_path / "estado").publicar()
    assert sum(1 for b, c in s3_memoria.puts if c == "publicacao.json") == 3   # 2, 4 e o fim


def test_restaurar_traz_indice_e_estado(tmp_path, s3_memoria):
    pub, priv = _cliente_s3(s3_memoria, PUB), _cliente_s3(s3_memoria, PRIV)
    pub.gravar("indice.json", b'{"versao":1,"eleicoes":[{"id":"1950-1t-geral"}]}', sem_sobrescrever=False)
    priv.gravar("estado/preparar.json", b'{"anos":{"1950":{}}}', sem_sobrescrever=False)
    priv.gravar("estado/coleta-2026-1t-geral.json", b"{}", sem_sobrescrever=False)
    priv.gravar("estado/../fora.json", b"{}", sem_sobrescrever=False)
    saida, estado = tmp_path / "feeds", tmp_path / "estado"
    avisos = []
    assert _nuvem(s3_memoria, saida, estado, avisos).restaurar() == 3
    assert json.loads((saida / "indice.json").read_text())["eleicoes"][0]["id"] == "1950-1t-geral"
    assert (estado / "coleta-2026-1t-geral.json").exists() and not (tmp_path / "fora.json").exists()
    # Índice local vence o publicado
    (saida / "indice.json").write_text('{"local":true}')
    _nuvem(s3_memoria, saida, estado).restaurar()
    assert json.loads((saida / "indice.json").read_text()) == {"local": True}


def test_restaurar_com_bucket_vazio(tmp_path, s3_memoria):
    assert _nuvem(s3_memoria, tmp_path / "feeds", tmp_path / "estado").restaurar() == 0
    assert _nuvem(s3_memoria, tmp_path / "feeds", tmp_path / "estado").salvar_estado() == 0


# ------------------------------------------------------------------ carga na nuvem, de ponta a ponta

def _cliente_http(fonte: str) -> ClienteHttp:
    return ClienteHttp(fonte, user_agent="Lumen/t (+c@exemplo.org)", rpm=60000, abridor=SEM_PROXY,
                       dormir=lambda s: None)


@pytest.fixture
def cdn_1950(tmp_path, monkeypatch, zips_antigos):
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    rotas = {}
    for ano in (1950, 1989):
        for conjunto, caminho in zip(antigas.CONJUNTOS_UF, zips_antigos(tmp_path / "cdn", ano)):
            if caminho is not None:
                rotas[f"/{conjunto}/{caminho.name}"] = caminho.read_bytes()

    class T(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            corpo = rotas.get(self.path)
            self.send_response(200 if corpo else 404)
            self.send_header("Content-Length", str(len(corpo or b"")))
            self.end_headers()
            self.wfile.write(corpo or b"")
    http = ThreadingHTTPServer(("127.0.0.1", 0), T)
    threading.Thread(target=http.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
    monkeypatch.setattr(antigas, "CDN", f"http://127.0.0.1:{http.server_address[1]}")
    yield
    http.shutdown()
    http.server_close()


def _preparacao(cfg, s3, raiz: Path, anos, **kw) -> tuple[Preparacao, list[str]]:
    extra = kw.pop("extra", {})
    cfg.saida = raiz / "feeds"
    cfg.estado = raiz / "estado"
    cfg.arquivos = raiz / "arquivos"
    linhas: list[str] = []
    op = OpcoesPreparacao(anos=anos, ao_vivo=False, portal=False, bronze=False, **kw)
    prep = Preparacao(cfg, op, cliente_resultados=_cliente_http(FONTE_ID),
                      cliente_dados=_cliente_http(carga.FONTE_DADOS_ABERTOS), saida=linhas.append,
                      hoje=date(2026, 10, 7), dormir=lambda s: None,
                      nuvem=_nuvem(s3, raiz / "feeds", raiz / "estado"), **extra)
    return prep, linhas


def test_carga_na_nuvem_retomada_em_outra_maquina(cfg, s3_memoria, cdn_1950, tmp_path):
    # 1ª máquina: processa 1950, publica e guarda o estado; apaga os ZIPs ao terminar o ano
    prep, _ = _preparacao(cfg, s3_memoria, tmp_path / "m1", [1950], apagar_arquivos=True)
    r = prep.executar()
    assert r.erros == [] and r.publicados > 0
    assert not (tmp_path / "m1" / "arquivos" / "1950").exists()
    assert "1950-1t-geral/presidente/br.json" in s3_memoria.chaves(PUB)
    assert "estado/preparar.json" in s3_memoria.chaves(PRIV)

    # 2ª máquina, vazia: restaura, pula 1950 e processa 1989; o índice publicado fica com os dois anos
    antes = len(s3_memoria.puts)
    prep2, _ = _preparacao(cfg, s3_memoria, tmp_path / "m2", [1989, 1950])
    r2 = prep2.executar()
    assert {a["ano"]: a["situacao"] for a in r2.anos} == {1950: "já processado", 1989: "processado"}
    indice = json.loads(s3_memoria.corpo(PUB, "indice.json"))
    assert {"1950-1t-geral", "1989-1t-geral", "1989-2t-geral"} <= {e["id"] for e in indice["eleicoes"]}
    # Só o que a 2ª máquina gerou subiu: nada de 1950 de novo, e o mapa e o cadastro já estavam iguais
    subiram = [c for b, c in s3_memoria.puts[antes:] if b == PUB]
    assert subiram and all(c.startswith("1989-") or c == "indice.json" for c in subiram)


def test_carga_para_no_prazo(cfg, s3_memoria, cdn_1950, tmp_path):
    # Relógio: criação, início do bloco de 1933 a 1990, 1950 dentro do prazo; em 1989 o prazo já venceu
    instantes = iter([0.0, 0.0, 0.0] + [10_000.0] * 100)
    prep, linhas = _preparacao(cfg, s3_memoria, tmp_path / "m", [1989, 1950], limite_minutos=1,
                               extra={"relogio": lambda: next(instantes)})
    r = prep.executar()
    assert r.prazo_atingido and [a["ano"] for a in r.anos] == [1950]
    assert any("prazo atingido" in linha for linha in linhas)


def test_falha_ao_restaurar_nao_carrega_nada(cfg, tmp_path):
    class Quebrada:
        def restaurar(self):
            raise OSError("sem rede")
    cfg.saida, cfg.estado = tmp_path / "f", tmp_path / "e"
    linhas = []
    prep = Preparacao(cfg, OpcoesPreparacao(portal=False, bronze=False), cliente_resultados=_cliente_http(FONTE_ID),
                      cliente_dados=_cliente_http(carga.FONTE_DADOS_ABERTOS), saida=linhas.append, nuvem=Quebrada())
    r = prep.executar()
    assert r.erros == ["restauração da nuvem: sem rede"] and r.anos == []


def test_falha_ao_publicar_vira_erro_do_resumo(cfg, tmp_path):
    class Quebrada:
        def sincronizar(self):
            raise OSError("R2 fora do ar")
    cfg.saida, cfg.estado = tmp_path / "f", tmp_path / "e"
    prep = Preparacao(cfg, OpcoesPreparacao(portal=False, bronze=False), saida=lambda m: None,
                      cliente_resultados=_cliente_http(FONTE_ID), cliente_dados=_cliente_http(carga.FONTE_DADOS_ABERTOS))
    prep.nuvem = Quebrada()
    prep.sincronizar()
    assert prep.resumo.erros == ["publicação na nuvem: R2 fora do ar"]


# ------------------------------------------------------------------ CLI

def test_cli_publicar_e_falta_de_configuracao(cfg, s3_memoria, monkeypatch, capsys):
    assert cli.main(["--config", str(cfg.toml), "publicar"]) == 2
    assert "LUMEN_S3_CHAVE_ACESSO" in capsys.readouterr().err
    assert cli.main(["--config", str(cfg.toml), "preparar", "--nuvem"]) == 2
    capsys.readouterr()
    monkeypatch.setenv("LUMEN_PUBLICACAO_ENDPOINT", s3_memoria.endpoint)
    monkeypatch.setenv("LUMEN_PUBLICACAO_BUCKET", PUB)
    monkeypatch.setenv("LUMEN_PUBLICACAO_BUCKET_ESTADO", PRIV)
    monkeypatch.setenv("LUMEN_S3_CHAVE_ACESSO", "a")
    monkeypatch.setenv("LUMEN_S3_CHAVE_SECRETA", "s")
    # O cliente S3 do CLI usa o abridor padrão; nos testes, sem o proxy do ambiente
    monkeypatch.setattr(publicacao, "ClienteS3",
                        lambda **kw: ClienteS3(**{**kw, "abridor": SEM_PROXY}))
    cfg.saida.mkdir(parents=True)
    (cfg.saida / "indice.json").write_text('{"versao":1,"eleicoes":[]}')
    assert cli.main(["--config", str(cfg.toml), "publicar"]) == 0
    texto = capsys.readouterr().out
    assert json.loads(texto[texto.index("{"):]) == {"enviados": 1, "iguais": 0, "bytes": 26}
    assert s3_memoria.chaves(PUB) == ["indice.json"]


def test_resumo_publicacao_padrao():
    assert ResumoPublicacao() == ResumoPublicacao(0, 0, 0)
