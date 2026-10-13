"""Medição dos feeds contra os limites gratuitos do R2 e do Supabase (adendo do ADR-026)."""

from __future__ import annotations

import gzip
import json

import pytest

from lumen_eleicoes import cli, medicao
from lumen_eleicoes.configuracao import ConfiguracaoAusente, carregar_publicacao


def _arquivo(raiz, rel: str, conteudo: bytes) -> None:
    caminho = raiz / rel
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_bytes(conteudo)


def test_medir_grupos_visoes_e_maiores(tmp_path):
    grande = b'{"x":"' + b"a" * 5000 + b'"}'
    _arquivo(tmp_path, "indice.json", b'{"versao":1}')
    _arquivo(tmp_path, "municipios.json", b"[]")
    _arquivo(tmp_path, "geo/br-uf.json", grande)
    _arquivo(tmp_path, "2026-1t-geral/presidente/br.json", b'{"c":[' + b"1," * 300 + b"1]}")
    _arquivo(tmp_path, "2026-1t-geral/presidente/historico-br.json", b"[" + b"2," * 50 + b"2]")
    _arquivo(tmp_path, "2026-1t-geral/presidente/uf-sp.json", b"{}")
    _arquivo(tmp_path, "2026-1t-geral/presidente/uf-mg.json", bytes(range(256)) * 8)   # pouco compressível
    _arquivo(tmp_path, "2026-1t-geral/presidente/historico-uf-mg.json", b"[3]")
    _arquivo(tmp_path, "2026-1t-geral/presidente/mu-3550308.json", bytes(range(256)) * 20)  # município: fora
    _arquivo(tmp_path, "2026-1t-geral/senador/br.json", b"{}")
    _arquivo(tmp_path, "2026-1t-geral/senador/historico-uf-rj.json", b"[1]")        # evolução sem o feed
    _arquivo(tmp_path, "2026-1t-geral/senador/.br.json.1.tmp", b"{")
    _arquivo(tmp_path, "2026-1t-geral/senador/br.json.tmp", b"{")

    m = medicao.medir(tmp_path, maiores=2)

    assert m.total.arquivos == 11
    assert m.total.bytes == sum(p.stat().st_size for p in tmp_path.rglob("*")
                                if p.is_file() and not p.name.endswith(".tmp"))
    assert {g: t.arquivos for g, t in m.grupos.items()} == {"raiz": 2, "geo": 1, "2026-1t-geral": 8}
    assert [x["arquivo"] for x in m.maiores] == ["2026-1t-geral/presidente/mu-3550308.json",
                                                 "geo/br-uf.json"]
    assert m.maiores[1]["bytes_gzip"] == len(gzip.compress(grande, compresslevel=6, mtime=0))
    # Em cada visão, o par feed + evolução mais pesado é o que entra na estimativa
    br = m.visoes["2026-1t-geral"]["brasil"]
    uf = m.visoes["2026-1t-geral"]["estado"]
    assert (br["cargo"], br["abrangencia"]) == ("presidente", "br") and br["evolucao_gzip"] > 0
    assert (uf["cargo"], uf["abrangencia"]) == ("presidente", "uf-mg") and uf["evolucao_gzip"] > 0
    assert set(m.visoes["2026-1t-geral"]) == {"brasil", "estado"}
    esperado = 240 * (br["bytes_gzip"] + br["evolucao_gzip"]) + 60 * m.indice_gzip
    assert m.saida_por_visitante_hora("2026-1t-geral") == esperado
    assert m.saida_por_visitante_hora("2026-1t-geral", "estado") > esperado
    assert m.saida_por_visitante_hora("1950-geral") is None
    assert m.cabe("supabase_gratuito") == {"armazenamento": True, "arquivo": True}
    assert m.cabe("r2_gratuito") == {"armazenamento": True, "arquivo": None}

    j = m.para_json()
    assert j["visoes"]["2026-1t-geral"]["brasil"]["saida_pior_caso_por_visitante_hora"] == esperado
    assert list(j["grupos"]) == ["2026-1t-geral", "geo", "raiz"]
    json.dumps(j)  # serializável
    md = medicao.resumo_markdown(m)
    assert "`presidente/br`" in md and "`presidente/uf-mg`" in md


def test_visao_de():
    assert medicao.visao_de("br") == "brasil"
    assert medicao.visao_de("uf-sp") == "estado"
    assert medicao.visao_de("mu-3550308") is None


def test_limites_estourados(tmp_path, monkeypatch):
    _arquivo(tmp_path, "geo/br-uf.json", b"x" * 2000)
    monkeypatch.setitem(medicao.LIMITES, "supabase_gratuito",
                        {"armazenamento": 1000, "arquivo": 1500, "saida": 10**9, "saida_cache": 10**9})
    m = medicao.medir(tmp_path)
    assert m.cabe("supabase_gratuito") == {"armazenamento": False, "arquivo": False}
    assert "**não**" in medicao.resumo_markdown(m)


def test_pasta_inexistente_e_vazia(tmp_path):
    assert medicao.medir(tmp_path / "nao-existe").total.arquivos == 0
    m = medicao.medir(tmp_path)
    assert m.total.arquivos == 0 and m.maiores == [] and m.visoes == {}
    assert "0 arquivo(s)" in medicao.resumo_markdown(m)
    assert m.cabe("supabase_gratuito") == {"armazenamento": True, "arquivo": True}


def test_legivel():
    assert medicao._legivel(None) == "—"
    assert medicao._legivel(999) == "999 B"
    assert medicao._legivel(1500) == "1,5 kB"
    assert medicao._legivel(2_500_000) == "2,5 MB"
    assert medicao._legivel(3 * medicao.GB) == "3,0 GB"
    assert medicao.grupo_de("indice.json") == "raiz"
    assert medicao.grupo_de("fotos/sp/1.jpg") == "fotos"


def test_cli_medir_sobre_a_amostra(tmp_path, capsys):
    saida = tmp_path / "f"
    assert cli.main(["--config", str(tmp_path / "x.toml"), "--saida", str(saida), "amostra"]) == 0
    capsys.readouterr()
    resumo = tmp_path / "resumo.md"
    resumo.write_text("antes\n", encoding="utf-8")
    assert cli.main(["--config", str(tmp_path / "x.toml"), "--saida", str(saida), "medir",
                     "--resumo", str(resumo), "--maiores", "3"]) == 0
    texto = capsys.readouterr().out
    j = json.loads(texto[texto.index("{"):])
    assert j["total"]["arquivos"] > 0 and len(j["maiores"]) == 3
    assert "geo" in j["grupos"] and "raiz" in j["grupos"]
    assert j["visoes"], "a amostra tem feed nacional"
    md = resumo.read_text(encoding="utf-8")
    assert md.startswith("antes\n## Tamanho dos feeds")
    assert "Saída durante a apuração" in md and "Maiores arquivos" in md
    # Sem feeds, código 1
    assert cli.main(["--config", str(tmp_path / "x.toml"), "--saida", str(tmp_path / "vazio"), "medir"]) == 1


@pytest.mark.parametrize("endpoint", ["https://abc.supabase.co/storage/v1/s3",
                                      "https://abc.storage.supabase.co/storage/v1/s3"])
def test_supabase_exige_regiao(tmp_path, monkeypatch, endpoint):
    for v in ("LUMEN_PUBLICACAO_BUCKET_ESTADO", "LUMEN_PUBLICACAO_REGIAO"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("LUMEN_PUBLICACAO_ENDPOINT", endpoint)
    monkeypatch.setenv("LUMEN_PUBLICACAO_BUCKET", "lumen-eleicoes")
    monkeypatch.setenv("LUMEN_S3_CHAVE_ACESSO", "a")
    monkeypatch.setenv("LUMEN_S3_CHAVE_SECRETA", "s")
    toml = tmp_path / "x.toml"
    with pytest.raises(ConfiguracaoAusente, match="sa-east-1"):
        carregar_publicacao(toml)
    monkeypatch.setenv("LUMEN_PUBLICACAO_REGIAO", "")        # variável vazia do GitHub: vale o padrão
    with pytest.raises(ConfiguracaoAusente, match="região do projeto"):
        carregar_publicacao(toml)
    monkeypatch.setenv("LUMEN_PUBLICACAO_REGIAO", "sa-east-1")
    pub = carregar_publicacao(toml)
    assert (pub.endpoint, pub.regiao) == (endpoint, "sa-east-1")


def test_eh_supabase():
    from lumen_eleicoes.configuracao import eh_supabase
    assert eh_supabase("https://x.supabase.co/storage/v1/s3")
    assert not eh_supabase("https://conta.r2.cloudflarestorage.com")
    assert not eh_supabase("https://supabase.co.exemplo.org/s3")
    assert not eh_supabase("")


def test_eleicao_so_com_a_visao_brasil(tmp_path):
    _arquivo(tmp_path, "1950-1t-geral/presidente/br.json", b"{}")
    m = medicao.medir(tmp_path)
    assert set(m.visoes["1950-1t-geral"]) == {"brasil"}
    assert m.saida_por_visitante_hora("1950-1t-geral", "estado") is None
    md = medicao.resumo_markdown(m)
    assert "| 1950-1t-geral | brasil |" in md and "| 1950-1t-geral | estado |" not in md
