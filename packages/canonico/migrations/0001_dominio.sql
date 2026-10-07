-- ===========================================================================
-- Migração 0001 — banco de domínio do Lumen (PostgreSQL 16)
--
-- O que vive aqui (ADR-005): entidades de referência, indícios, contestações,
-- conformidade e a trilha de auditoria. O fato administrativo em volume
-- (processos, contratos, itens) vive na camada silver/gold, em formato
-- colunar; aqui ficam só as tabelas transacionais e de prova.
--
-- Três garantias impostas pelo próprio banco, e não só pela aplicação:
--   1. Tabelas de prova e de auditoria são somente-anexação (RNF-15).
--   2. Um indício não chega a "publicado" sem evidência e sem o número de
--      revisores distintos exigido pela severidade (PUB-04, PUB-05, ADR-008).
--   3. Conformidade "indeterminado" exige motivo; os demais o proíbem
--      (RF-CF-07).
-- A aplicação já impõe as três em lumen_canonico.indicio e
-- lumen_ingestao.portas. Repetir no banco é defesa em profundidade: um
-- script de manutenção ou uma API nova não as contornam por descuido.
-- ===========================================================================

BEGIN;

CREATE SCHEMA IF NOT EXISTS lumen;
SET LOCAL search_path = lumen;

CREATE TABLE migracao (
    versao      text PRIMARY KEY,
    descricao   text NOT NULL,
    aplicada_em timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------- tipos

CREATE TYPE esfera AS ENUM ('uniao', 'estadual', 'municipal', 'distrital');
CREATE TYPE poder AS ENUM ('executivo', 'legislativo', 'judiciario', 'autonomo');
CREATE TYPE severidade AS ENUM ('baixa', 'media', 'alta');
CREATE TYPE estado_indicio AS ENUM (
    'detectado', 'em_revisao', 'aguardando_dado', 'descartado', 'publicado',
    'contestado', 'publicado_com_resposta', 'retificado', 'removido', 'encerrado'
);
CREATE TYPE alvo_indicio AS ENUM ('contrato', 'empenho', 'processo', 'fornecedor_no_ente', 'ente');
CREATE TYPE papel_evidencia AS ENUM ('principal', 'comparacao', 'contexto');
CREATE TYPE resultado_conformidade AS ENUM ('cumpre', 'cumpre_parcialmente', 'nao_cumpre', 'indeterminado');
CREATE TYPE origem_contestacao AS ENUM ('ente', 'fornecedor', 'terceiro');
CREATE TYPE desfecho_contestacao AS ENUM ('mantido', 'retificado', 'removido');
CREATE TYPE modo_regra AS ENUM ('silencioso', 'publicacao');

-- ---------------------------------------------------------------- somente-anexação

CREATE FUNCTION recusar_alteracao() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'tabela %.% é somente-anexação: % não é permitido',
        TG_TABLE_SCHEMA, TG_TABLE_NAME, TG_OP
        USING ERRCODE = 'insufficient_privilege';
END;
$$;

-- ---------------------------------------------------------------- fontes e prova

CREATE TABLE fonte (
    id              text PRIMARY KEY CHECK (id ~ '^[a-z0-9][a-z0-9_\-]{0,127}$'),
    tipo_conector   text NOT NULL,
    descricao       text,
    objetos         text[] NOT NULL CHECK (cardinality(objetos) > 0),
    periodicidade   text NOT NULL,
    limite_rpm      integer NOT NULL CHECK (limite_rpm > 0),
    versao_spec     text NOT NULL,
    ativa           boolean NOT NULL DEFAULT true,
    campos_legais_ausentes text[] NOT NULL DEFAULT '{}',
    criada_em       timestamptz NOT NULL DEFAULT now()
);

-- Índice do bronze: um registro por evento de coleta (ADR-011). O conteúdo
-- mora no armazenamento de objetos sob o próprio SHA-256.
CREATE TABLE documento_fonte (
    id                    text PRIMARY KEY,            -- registro_id do bronze
    fonte_id              text NOT NULL REFERENCES fonte (id),
    url_solicitada        text NOT NULL,
    url_efetiva           text NOT NULL,
    status_http           smallint NOT NULL CHECK (status_http BETWEEN 100 AND 599),
    sha256                char(64) NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    tamanho_bytes         bigint NOT NULL CHECK (tamanho_bytes >= 0),
    tipo_midia            text NOT NULL,
    cabecalhos            jsonb NOT NULL DEFAULT '{}',
    coletado_em           timestamptz NOT NULL,
    versao                integer NOT NULL CHECK (versao >= 1),
    mudou_desde_anterior  boolean NOT NULL,
    caminho_objeto        text NOT NULL,
    UNIQUE (url_solicitada, versao)
);
CREATE INDEX documento_fonte_fonte_coleta ON documento_fonte (fonte_id, coletado_em);
CREATE INDEX documento_fonte_sha ON documento_fonte (sha256);
CREATE TRIGGER documento_fonte_somente_anexacao
    BEFORE UPDATE OR DELETE ON documento_fonte
    FOR EACH ROW EXECUTE FUNCTION recusar_alteracao();
CREATE TRIGGER documento_fonte_sem_truncate
    BEFORE TRUNCATE ON documento_fonte
    FOR EACH STATEMENT EXECUTE FUNCTION recusar_alteracao();

-- ---------------------------------------------------------------- referência

CREATE TABLE grupo_pares (
    id                 uuid PRIMARY KEY,
    criterios          jsonb NOT NULL,
    faixa_populacional text,
    regiao             text,
    quantidade_entes   integer NOT NULL CHECK (quantidade_entes >= 0),
    calculado_em       timestamptz NOT NULL
);

CREATE TABLE ente_federativo (
    id                       uuid PRIMARY KEY,
    codigo_ibge              text NOT NULL UNIQUE CHECK (codigo_ibge ~ '^(1|[0-9]{2}|[0-9]{7})$'),
    nome                     text NOT NULL,
    esfera                   esfera NOT NULL,
    uf                       char(2),
    cnpj                     text,
    capital                  boolean,
    regiao                   text,
    populacao                integer CHECK (populacao IS NULL OR populacao >= 0),
    populacao_referencia     text,
    porte                    text,
    receita_corrente_liquida numeric(20, 2),
    grupo_pares_id           uuid REFERENCES grupo_pares (id),
    atualizado_em            timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE orgao (
    id               uuid PRIMARY KEY,
    cnpj             text NOT NULL UNIQUE CHECK (cnpj ~ '^[0-9A-Z]{12}[0-9]{2}$'),
    razao_social     text NOT NULL,
    esfera           esfera,
    poder            poder,
    ente_id          uuid REFERENCES ente_federativo (id),
    atualizado_em    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX orgao_ente ON orgao (ente_id);

-- ---------------------------------------------------------------- regras e indícios

CREATE TABLE regra_deteccao (
    codigo             text NOT NULL CHECK (codigo ~ '^[A-K]-[0-9]{2}$'),
    versao             integer NOT NULL CHECK (versao >= 1),
    familia            char(1) NOT NULL CHECK (familia BETWEEN 'A' AND 'K'),
    titulo             text NOT NULL,
    explicacao_publica text NOT NULL,
    parametros         jsonb NOT NULL,
    severidade_base    severidade NOT NULL,
    modo               modo_regra NOT NULL DEFAULT 'silencioso',
    ativa              boolean NOT NULL DEFAULT true,
    vigente_desde      timestamptz NOT NULL,
    PRIMARY KEY (codigo, versao),
    CHECK (left(codigo, 1) = familia)
);

CREATE TABLE indicio (
    id                    uuid PRIMARY KEY,
    regra_codigo          text NOT NULL,
    regra_versao          integer NOT NULL,
    ente_id               uuid NOT NULL REFERENCES ente_federativo (id),
    alvo_tipo             alvo_indicio NOT NULL,
    alvo_id               text NOT NULL,
    score                 numeric(6, 5) NOT NULL CHECK (score BETWEEN 0 AND 1),
    severidade            severidade NOT NULL,
    estado                estado_indicio NOT NULL DEFAULT 'detectado',
    parametros_aplicados  jsonb NOT NULL,
    valores_observados    jsonb NOT NULL CHECK (valores_observados <> '{}'::jsonb),
    explicacao            text NOT NULL,
    detectado_em          timestamptz NOT NULL DEFAULT now(),
    protocolo_contestacao text,
    FOREIGN KEY (regra_codigo, regra_versao) REFERENCES regra_deteccao (codigo, versao),
    -- mesma faixa do DOC-07, seção 13: a severidade é função do score
    CHECK (
        (severidade = 'baixa' AND score < 0.45) OR
        (severidade = 'media' AND score >= 0.45 AND score <= 0.70) OR
        (severidade = 'alta'  AND score > 0.70)
    )
);
CREATE INDEX indicio_fila ON indicio (estado, severidade, detectado_em);
CREATE INDEX indicio_ente ON indicio (ente_id);

CREATE TABLE evidencia (
    id                 uuid PRIMARY KEY,
    indicio_id         uuid NOT NULL REFERENCES indicio (id),
    documento_fonte_id text NOT NULL REFERENCES documento_fonte (id),
    papel              papel_evidencia NOT NULL,
    trecho_referencia  text,
    UNIQUE (indicio_id, documento_fonte_id, papel)
);
CREATE TRIGGER evidencia_somente_anexacao
    BEFORE UPDATE OR DELETE ON evidencia
    FOR EACH ROW EXECUTE FUNCTION recusar_alteracao();

-- Revisores distintos: a chave primária impede contar duas vezes a mesma
-- pessoa (PUB-05), qualquer que seja o caminho da escrita.
CREATE TABLE aprovacao_indicio (
    indicio_id   uuid NOT NULL REFERENCES indicio (id),
    revisor      text NOT NULL CHECK (btrim(revisor) <> '' AND revisor <> 'sistema'),
    aprovado_em  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (indicio_id, revisor)
);
CREATE TRIGGER aprovacao_somente_anexacao
    BEFORE UPDATE OR DELETE ON aprovacao_indicio
    FOR EACH ROW EXECUTE FUNCTION recusar_alteracao();

CREATE TABLE transicao_indicio (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    indicio_id    uuid NOT NULL REFERENCES indicio (id),
    de            estado_indicio NOT NULL,
    para          estado_indicio NOT NULL,
    autor         text NOT NULL CHECK (btrim(autor) <> ''),
    justificativa text NOT NULL CHECK (btrim(justificativa) <> ''),
    em            timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX transicao_indicio_por_indicio ON transicao_indicio (indicio_id, em);
CREATE TRIGGER transicao_somente_anexacao
    BEFORE UPDATE OR DELETE ON transicao_indicio
    FOR EACH ROW EXECUTE FUNCTION recusar_alteracao();

-- Mesma máquina de estados de lumen_canonico.indicio.TRANSICOES.
CREATE TABLE transicao_permitida (
    de   estado_indicio NOT NULL,
    para estado_indicio NOT NULL,
    PRIMARY KEY (de, para)
);
INSERT INTO transicao_permitida (de, para) VALUES
    ('detectado', 'em_revisao'), ('detectado', 'descartado'),
    ('em_revisao', 'publicado'), ('em_revisao', 'descartado'), ('em_revisao', 'aguardando_dado'),
    ('aguardando_dado', 'em_revisao'), ('aguardando_dado', 'descartado'),
    ('publicado', 'contestado'), ('publicado', 'encerrado'),
    ('contestado', 'publicado_com_resposta'), ('contestado', 'retificado'), ('contestado', 'removido'),
    ('publicado_com_resposta', 'encerrado'),
    ('retificado', 'publicado');

CREATE FUNCTION validar_mudanca_de_estado() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    exigidos  integer;
    aprovados integer;
    provas    integer;
BEGIN
    IF NEW.estado = OLD.estado THEN
        RETURN NEW;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM lumen.transicao_permitida WHERE de = OLD.estado AND para = NEW.estado) THEN
        RAISE EXCEPTION 'transição de indício não permitida: % -> %', OLD.estado, NEW.estado
            USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.estado = 'em_revisao' AND NEW.severidade = 'baixa' THEN
        RAISE EXCEPTION 'severidade baixa não entra na fila de revisão (DOC-07, seção 13)'
            USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.estado = 'publicado' THEN
        IF NEW.severidade = 'baixa' THEN
            RAISE EXCEPTION 'severidade baixa nunca é publicada' USING ERRCODE = 'check_violation';
        END IF;
        SELECT count(*) INTO provas FROM lumen.evidencia WHERE indicio_id = NEW.id;
        IF provas = 0 THEN
            RAISE EXCEPTION 'publicar exige ao menos um documento fonte (PUB-04)'
                USING ERRCODE = 'check_violation';
        END IF;
        exigidos := CASE NEW.severidade WHEN 'media' THEN 1 WHEN 'alta' THEN 2 END;
        SELECT count(*) INTO aprovados FROM lumen.aprovacao_indicio WHERE indicio_id = NEW.id;
        IF aprovados < exigidos THEN
            RAISE EXCEPTION 'severidade % exige % revisor(es) distinto(s); há % (PUB-05)',
                NEW.severidade, exigidos, aprovados USING ERRCODE = 'check_violation';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER indicio_mudanca_de_estado
    BEFORE UPDATE OF estado ON indicio
    FOR EACH ROW EXECUTE FUNCTION validar_mudanca_de_estado();

-- Fora o estado e o protocolo de contestação, um indício não muda depois de
-- criado: parâmetros, valores e explicação são a prova de como ele nasceu.
-- Retificar é republicar com nova versão de regra, não reescrever o antigo.
CREATE FUNCTION congelar_indicio() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF (NEW.regra_codigo, NEW.regra_versao, NEW.ente_id, NEW.alvo_tipo, NEW.alvo_id, NEW.score,
        NEW.severidade, NEW.parametros_aplicados, NEW.valores_observados, NEW.explicacao,
        NEW.detectado_em)
       IS DISTINCT FROM
       (OLD.regra_codigo, OLD.regra_versao, OLD.ente_id, OLD.alvo_tipo, OLD.alvo_id, OLD.score,
        OLD.severidade, OLD.parametros_aplicados, OLD.valores_observados, OLD.explicacao,
        OLD.detectado_em) THEN
        RAISE EXCEPTION 'conteúdo de indício é imutável; só estado e protocolo mudam'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER indicio_congelado
    BEFORE UPDATE ON indicio
    FOR EACH ROW EXECUTE FUNCTION congelar_indicio();
CREATE TRIGGER indicio_sem_delete
    BEFORE DELETE ON indicio
    FOR EACH ROW EXECUTE FUNCTION recusar_alteracao();

-- ---------------------------------------------------------------- direito de resposta

CREATE TABLE contestacao (
    id                      uuid PRIMARY KEY,
    indicio_id              uuid NOT NULL REFERENCES indicio (id),
    protocolo               text NOT NULL UNIQUE,
    origem                  origem_contestacao NOT NULL,
    vinculo_comprovado      boolean NOT NULL DEFAULT false,
    texto                   text NOT NULL,             -- como enviado, sem edição
    documentos              jsonb NOT NULL DEFAULT '[]',
    recebida_em             timestamptz NOT NULL DEFAULT now(),
    marcada_publicamente_em timestamptz,
    desfecho                desfecho_contestacao,
    desfecho_em             timestamptz,
    CHECK ((desfecho IS NULL) = (desfecho_em IS NULL))
);
CREATE INDEX contestacao_pendente ON contestacao (recebida_em) WHERE desfecho IS NULL;

-- ---------------------------------------------------------------- conformidade

CREATE TABLE conformidade (
    id                   uuid PRIMARY KEY,
    ente_id              uuid NOT NULL REFERENCES ente_federativo (id),
    criterio             text NOT NULL,
    periodo_referencia   text NOT NULL,          -- ex.: "2025", "2025-B6"
    dispositivo_legal    text NOT NULL CHECK (btrim(dispositivo_legal) <> ''),
    resultado            resultado_conformidade NOT NULL,
    motivo_indeterminado text,
    fonte_id             text REFERENCES fonte (id),
    avaliado_em          timestamptz NOT NULL DEFAULT now(),
    CHECK ((resultado = 'indeterminado') = (motivo_indeterminado IS NOT NULL AND btrim(motivo_indeterminado) <> '')),
    UNIQUE (ente_id, criterio, periodo_referencia, avaliado_em)
);
CREATE INDEX conformidade_ente ON conformidade (ente_id, criterio, periodo_referencia);

-- ---------------------------------------------------------------- auditoria

CREATE TABLE trilha_auditoria (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    em            timestamptz NOT NULL DEFAULT now(),
    autor         text NOT NULL CHECK (btrim(autor) <> ''),
    acao          text NOT NULL,
    entidade      text NOT NULL,
    entidade_id   text NOT NULL,
    justificativa text,
    dados         jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX trilha_por_entidade ON trilha_auditoria (entidade, entidade_id, em);
CREATE TRIGGER trilha_somente_anexacao
    BEFORE UPDATE OR DELETE ON trilha_auditoria
    FOR EACH ROW EXECUTE FUNCTION recusar_alteracao();
CREATE TRIGGER trilha_sem_truncate
    BEFORE TRUNCATE ON trilha_auditoria
    FOR EACH STATEMENT EXECUTE FUNCTION recusar_alteracao();

-- ---------------------------------------------------------------- papel da aplicação

-- A aplicação conecta com este papel. Ele não recebe UPDATE nem DELETE nas
-- tabelas de prova: mesmo que os gatilhos fossem removidos, o privilégio
-- continuaria faltando.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'lumen_app') THEN
        CREATE ROLE lumen_app NOLOGIN;
    END IF;
END;
$$;
GRANT USAGE ON SCHEMA lumen TO lumen_app;
GRANT SELECT ON ALL TABLES IN SCHEMA lumen TO lumen_app;
GRANT INSERT ON documento_fonte, evidencia, aprovacao_indicio, transicao_indicio,
                trilha_auditoria, indicio, contestacao, conformidade, fonte,
                ente_federativo, orgao, grupo_pares, regra_deteccao TO lumen_app;
GRANT UPDATE ON indicio, contestacao, fonte, ente_federativo, orgao, grupo_pares,
                regra_deteccao TO lumen_app;

INSERT INTO migracao (versao, descricao) VALUES ('0001', 'banco de domínio: prova, indícios, conformidade, auditoria');

COMMIT;
