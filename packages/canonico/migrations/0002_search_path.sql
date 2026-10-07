-- ===========================================================================
-- Migração 0002 — caminho de busca fixo nas funções de gatilho (PostgreSQL 16)
--
-- As três funções da 0001 resolvem nomes pelo search_path de quem dispara o
-- gatilho. Uma sessão que ponha à frente um esquema com uma tabela ou um
-- operador de mesmo nome mudaria o que a função enxerga. Com o caminho vazio,
-- elas só veem o pg_catalog e o que está qualificado com "lumen." (as consultas
-- de validar_mudanca_de_estado já são qualificadas).
--
-- Aponta o linter de segurança do Supabase (function_search_path_mutable),
-- onde o banco de domínio roda no plano gratuito (ADR-026).
-- ===========================================================================

BEGIN;

ALTER FUNCTION lumen.recusar_alteracao() SET search_path = '';
ALTER FUNCTION lumen.validar_mudanca_de_estado() SET search_path = '';
ALTER FUNCTION lumen.congelar_indicio() SET search_path = '';

INSERT INTO lumen.migracao (versao, descricao) VALUES ('0002', 'caminho de busca fixo nas funções de gatilho');

COMMIT;
