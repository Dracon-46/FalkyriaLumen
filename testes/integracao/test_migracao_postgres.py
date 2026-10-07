"""As migrações do domínio aplicadas num PostgreSQL de verdade, em ordem.

Roda só com ``LUMEN_TESTE_PG`` apontando para um servidor onde o usuário pode
criar bancos (o da CI é um serviço descartável). Cada execução cria um banco
novo, aplica todas as migrações e o apaga ao final.

O que se verifica aqui são as garantias que o banco impõe por conta própria,
independentemente da aplicação: somente-anexação, máquina de estados e
publicação condicionada a evidência e revisores distintos.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

pytestmark = pytest.mark.postgres

DSN = os.environ.get("LUMEN_TESTE_PG")
MIGRACOES = sorted((Path(__file__).resolve().parents[2] / "packages" / "canonico" / "migrations").glob("*.sql"))

if not DSN or not shutil.which("psql"):
    pytest.skip("defina LUMEN_TESTE_PG (e tenha psql) para rodar os testes de banco", allow_module_level=True)


def _psql(dsn: str, sql: str | None = None, arquivo: Path | None = None) -> subprocess.CompletedProcess:
    cmd = ["psql", dsn, "-v", "ON_ERROR_STOP=1", "-X", "-q", "-t", "-A"]
    cmd += ["-f", str(arquivo)] if arquivo else ["-c", sql]
    return subprocess.run(cmd, capture_output=True, text=True)


def _com_banco(dsn: str, banco: str) -> str:
    # DSN em formato URI ou chave=valor; acrescenta/override do dbname.
    if dsn.startswith("postgres"):
        base, _, _ = dsn.rpartition("/")
        return f"{base}/{banco}"
    return f"{dsn} dbname={banco}"


SEMENTE = """
SET search_path = lumen;
INSERT INTO fonte (id, tipo_conector, objetos, periodicidade, limite_rpm, versao_spec)
VALUES ('pncp_contratacoes', 'api', '{ProcessoContratacao}', 'diaria', 60, '1');
INSERT INTO documento_fonte (id, fonte_id, url_solicitada, url_efetiva, status_http, sha256,
  tamanho_bytes, tipo_midia, coletado_em, versao, mudou_desde_anterior, caminho_objeto)
VALUES ('reg1', 'pncp_contratacoes', 'https://pncp.gov.br/x', 'https://pncp.gov.br/x', 200,
  repeat('a', 64), 10, 'application/json', now(), 1, true, 'objetos/aa/aa/' || repeat('a', 64));
INSERT INTO ente_federativo (id, codigo_ibge, nome, esfera, uf)
VALUES ('00000000-0000-0000-0000-000000004319', '4319604', 'São Sepé', 'municipal', 'RS');
INSERT INTO regra_deteccao (codigo, versao, familia, titulo, explicacao_publica, parametros,
  severidade_base, vigente_desde)
VALUES ('B-01', 1, 'B', 'Soma de contratações diretas', 'Explicação neutra.', '{}', 'alta', now());
"""


@pytest.fixture(scope="module")
def banco():
    nome = "lumen_teste_" + uuid.uuid4().hex[:10]
    r = _psql(DSN, f"CREATE DATABASE {nome}")
    assert r.returncode == 0, r.stderr
    dsn = _com_banco(DSN, nome)
    for migracao in MIGRACOES:
        r = _psql(dsn, arquivo=migracao)
        assert r.returncode == 0, f"{migracao.name}: {r.stderr}"
    r = _psql(dsn, SEMENTE)
    assert r.returncode == 0, r.stderr
    yield dsn
    _psql(DSN, f"DROP DATABASE IF EXISTS {nome} WITH (FORCE)")


def ok(dsn, sql):
    r = _psql(dsn, sql)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def falha(dsn, sql, trecho):
    r = _psql(dsn, sql)
    assert r.returncode != 0, f"deveria falhar: {sql}"
    assert trecho in r.stderr, r.stderr




def _indicio(dsn, iid, score, severidade):
    ok(dsn, f"""SET search_path = lumen;
      INSERT INTO indicio (id, regra_codigo, regra_versao, ente_id, alvo_tipo, alvo_id, score,
        severidade, parametros_aplicados, valores_observados, explicacao)
      VALUES ('{iid}', 'B-01', 1, '00000000-0000-0000-0000-000000004319', 'fornecedor_no_ente',
        'f1', {score}, '{severidade}', '{{}}', '{{"soma": "75000.00"}}', 'texto');""")


def test_migracoes_registradas(banco):
    versoes = ok(banco, "SELECT string_agg(versao, ',' ORDER BY versao) FROM lumen.migracao")
    assert versoes == ",".join(m.name.split("_")[0] for m in MIGRACOES)


def test_funcoes_de_gatilho_com_caminho_de_busca_fixo(banco):
    # 0002: o search_path de quem dispara o gatilho não muda o que a função enxerga
    sem_caminho = ok(banco, """SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
      WHERE n.nspname = 'lumen' AND p.prorettype = 'trigger'::regtype
        AND NOT coalesce(p.proconfig @> ARRAY['search_path=""'], false)""")
    assert sem_caminho == "0"


def test_prova_e_somente_anexacao(banco):
    falha(banco, "UPDATE lumen.documento_fonte SET status_http = 404", "somente-anexação")
    falha(banco, "DELETE FROM lumen.documento_fonte", "somente-anexação")
    falha(banco, "TRUNCATE lumen.documento_fonte CASCADE", "somente-anexação")


def test_trilha_de_auditoria_e_somente_anexacao(banco):
    ok(banco, "INSERT INTO lumen.trilha_auditoria (autor, acao, entidade, entidade_id) VALUES ('ana', 'x', 'indicio', '1')")
    falha(banco, "UPDATE lumen.trilha_auditoria SET autor = 'outra'", "somente-anexação")
    falha(banco, "DELETE FROM lumen.trilha_auditoria", "somente-anexação")


def test_severidade_precisa_corresponder_ao_score(banco):
    falha(banco, """SET search_path = lumen; INSERT INTO indicio (id, regra_codigo, regra_versao,
      ente_id, alvo_tipo, alvo_id, score, severidade, parametros_aplicados, valores_observados,
      explicacao) VALUES (gen_random_uuid(), 'B-01', 1, '00000000-0000-0000-0000-000000004319',
      'ente', 'e', 0.90, 'media', '{}', '{"a":1}', 't')""", "check")


def test_alta_so_publica_com_evidencia_e_dois_revisores_distintos(banco):
    iid = "11111111-1111-1111-1111-111111111111"
    _indicio(banco, iid, "0.85", "alta")
    falha(banco, f"UPDATE lumen.indicio SET estado = 'publicado' WHERE id = '{iid}'", "transição")
    ok(banco, f"UPDATE lumen.indicio SET estado = 'em_revisao' WHERE id = '{iid}'")
    falha(banco, f"UPDATE lumen.indicio SET estado = 'publicado' WHERE id = '{iid}'", "documento fonte")
    ok(banco, f"""INSERT INTO lumen.evidencia (id, indicio_id, documento_fonte_id, papel)
                  VALUES (gen_random_uuid(), '{iid}', 'reg1', 'principal')""")
    ok(banco, f"INSERT INTO lumen.aprovacao_indicio (indicio_id, revisor) VALUES ('{iid}', 'ana')")
    falha(banco, f"INSERT INTO lumen.aprovacao_indicio (indicio_id, revisor) VALUES ('{iid}', 'ana')", "duplicate")
    falha(banco, f"UPDATE lumen.indicio SET estado = 'publicado' WHERE id = '{iid}'", "2 revisor")
    falha(banco, f"INSERT INTO lumen.aprovacao_indicio (indicio_id, revisor) VALUES ('{iid}', 'sistema')", "check")
    ok(banco, f"INSERT INTO lumen.aprovacao_indicio (indicio_id, revisor) VALUES ('{iid}', 'bruno')")
    ok(banco, f"UPDATE lumen.indicio SET estado = 'publicado' WHERE id = '{iid}'")
    assert ok(banco, f"SELECT estado FROM lumen.indicio WHERE id = '{iid}'") == "publicado"


def test_baixa_nao_entra_em_revisao(banco):
    iid = "22222222-2222-2222-2222-222222222222"
    _indicio(banco, iid, "0.30", "baixa")
    falha(banco, f"UPDATE lumen.indicio SET estado = 'em_revisao' WHERE id = '{iid}'", "baixa")
    ok(banco, f"UPDATE lumen.indicio SET estado = 'descartado' WHERE id = '{iid}'")


def test_conteudo_do_indicio_e_imutavel(banco):
    iid = "33333333-3333-3333-3333-333333333333"
    _indicio(banco, iid, "0.50", "media")
    falha(banco, f"UPDATE lumen.indicio SET explicacao = 'outro' WHERE id = '{iid}'", "imutável")
    falha(banco, f"DELETE FROM lumen.indicio WHERE id = '{iid}'", "somente-anexação")
    ok(banco, f"UPDATE lumen.indicio SET protocolo_contestacao = 'P-1' WHERE id = '{iid}'")


def test_conformidade_indeterminada_exige_motivo(banco):
    base = """INSERT INTO lumen.conformidade (id, ente_id, criterio, periodo_referencia,
      dispositivo_legal, resultado, motivo_indeterminado) VALUES (gen_random_uuid(),
      '00000000-0000-0000-0000-000000004319', 'dca_enviada', '2025', 'LC 101/2000, art. 51', """
    falha(banco, base + "'indeterminado', NULL)", "check")
    falha(banco, base + "'cumpre', 'sobrou motivo')", "check")
    ok(banco, base + "'indeterminado', 'fonte indisponível na janela')")
    ok(banco, base + "'cumpre', NULL)")
    falha(banco, base.replace("'LC 101/2000, art. 51'", "' '") + "'cumpre', NULL)", "check")


def test_papel_da_aplicacao_nao_altera_prova(banco):
    r = ok(banco, """SELECT has_table_privilege('lumen_app', 'lumen.documento_fonte', 'UPDATE')::text
                     || has_table_privilege('lumen_app', 'lumen.trilha_auditoria', 'DELETE')::text
                     || has_table_privilege('lumen_app', 'lumen.documento_fonte', 'INSERT')::text""")
    assert r == "falsefalsetrue"
