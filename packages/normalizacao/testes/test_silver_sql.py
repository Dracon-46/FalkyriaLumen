"""A macro ``sql/silver_consolidada.sql`` (DuckDB) escolhe as mesmas linhas que ``silver.consolidar``.

Roda só quando o pacote ``duckdb`` está instalado (dependência opcional
``analitico``); sem ele, o teste é pulado e a regra continua coberta pela
versão em Python em ``test_silver.py``.
"""

import dataclasses
from pathlib import Path

import pytest

from lumen_normalizacao import pncp
from lumen_normalizacao.silver import EscritorSilver, consolidar, ler_entidade

duckdb = pytest.importorskip("duckdb")

SQL = Path(__file__).resolve().parents[1] / "sql" / "silver_consolidada.sql"
PROV = dict(fonte_id="pncp_contratacoes", documento_fonte_id="reg0001")


def _escolhidas(raiz: Path, entidade: str) -> dict[str, tuple]:
    """id -> (coletado_em, atualizado_em) escolhidos pela macro no DuckDB."""
    con = duckdb.connect()
    con.execute(SQL.read_text(encoding="utf-8"))
    consulta = ("SELECT CAST(id AS VARCHAR), CAST(_coletado_em AS VARCHAR), _arquivo_silver "
                "FROM silver_consolidada(?, ?)")
    return {i: (c, Path(a).name) for i, c, a in con.execute(consulta, [raiz.as_posix(), entidade]).fetchall()}


def _escolhidas_python(raiz: Path, entidade: str, arquivos: dict[str, str]) -> dict[str, tuple]:
    """Mesmo formato de ``_escolhidas``, a partir de ``consolidar``."""
    return {linha["id"]: (linha["_coletado_em"], arquivos[linha["_coletado_em"]])
            for linha in consolidar(ler_entidade(raiz, entidade))}


def test_macro_e_python_concordam(tmp_path, fixture_bytes):
    bruto = fixture_bytes("pncp/contratacoes_publicacao_dispensa_20260901_p1.json")
    r = pncp.normalizar_contratacoes(bruto, **PROV)
    escritor = EscritorSilver(tmp_path, pncp.VERSAO_NORMALIZADOR)
    # Três artefatos com os mesmos registros: o segundo é uma coleta mais
    # recente; no terceiro, mais antigo, um processo foi atualizado depois e
    # tem de vencer mesmo vindo de uma coleta anterior.
    escritor.gravar("reg0001", r.registros, coletado_em="2026-10-01T10:00:00+00:00")
    escritor.gravar("reg0002", r.registros, coletado_em="2026-10-02T10:00:00+00:00")
    processos = [x for x in r.registros if x.ENTIDADE == "processo_contratacao"]
    assert processos[0].atualizado_em is not None
    alterado = dataclasses.replace(processos[0], atualizado_em=processos[0].atualizado_em.replace(year=2027))
    escritor.gravar("reg0000", [alterado], coletado_em="2026-09-30T10:00:00+00:00")
    arquivos = {
        "2026-10-01T10:00:00+00:00": "reg0001.jsonl",
        "2026-10-02T10:00:00+00:00": "reg0002.jsonl",
        "2026-09-30T10:00:00+00:00": "reg0000.jsonl",
    }

    # entidade com atualizado_em
    sql = _escolhidas(tmp_path, "processo_contratacao")
    assert {k: v[1] for k, v in sql.items()} == {k: v[1] for k, v in _escolhidas_python(
        tmp_path, "processo_contratacao", arquivos).items()}
    assert sql[alterado.id][1] == "reg0000.jsonl"
    assert sum(1 for _, arquivo in sql.values() if arquivo == "reg0002.jsonl") == len(processos) - 1
    # entidade sem atualizado_em: vale a coleta mais recente
    orgaos = _escolhidas(tmp_path, "orgao")
    assert orgaos and all(arquivo == "reg0002.jsonl" for _, arquivo in orgaos.values())


def test_macro_sem_coletado_em_desempata_pelo_arquivo(tmp_path, fixture_bytes):
    bruto = fixture_bytes("pncp/contratacoes_publicacao_dispensa_20260901_p1.json")
    r = pncp.normalizar_contratacoes(bruto, **PROV)
    escritor = EscritorSilver(tmp_path, "t")
    escritor.gravar("reg0001", r.registros)
    escritor.gravar("reg0002", r.registros)
    sql = _escolhidas(tmp_path, "orgao")
    python = {linha["id"]: Path("reg0002.jsonl").name for linha in consolidar(ler_entidade(tmp_path, "orgao"))}
    assert {k: v[1] for k, v in sql.items()} == python
