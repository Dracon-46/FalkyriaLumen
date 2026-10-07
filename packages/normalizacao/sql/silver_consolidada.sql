-- Visão consolidada da silver no DuckDB — ADR-016.
--
-- A silver guarda todas as ocorrências de um registro, cada uma com a sua
-- proveniência (RF-NO-05): o mesmo contrato chega pela coleta por publicação e
-- pela coleta por atualização, ou em duas coletas do mesmo dia. Esta macro
-- devolve uma linha por id: a de atualizado_em mais recente; no empate (ou com
-- os dois nulos), a da coleta mais recente (_coletado_em); persistindo o
-- empate, a do arquivo de nome maior, que é a última lida pela versão em
-- Python.
--
-- É a mesma regra de lumen_normalizacao.silver.consolidar(), que existe para
-- testes e para quem não tem o DuckDB instalado. O teste
-- packages/normalizacao/testes/test_silver_sql.py confere as duas lado a lado
-- (roda quando o pacote duckdb está instalado: pip install -e ".[analitico]").
--
-- Uso:
--   duckdb -c ".read packages/normalizacao/sql/silver_consolidada.sql" \
--          -c "SELECT * FROM silver_consolidada('dados/silver', 'contratacao') LIMIT 10"
--
-- Parâmetros:
--   raiz      diretório raiz da silver (o mesmo de EscritorSilver)
--   entidade  nome da entidade canônica (contratacao, contrato, ata_registro_preco, ...)
--
-- As colunas exercicio e uf vêm do particionamento Hive do caminho
-- (entidade/exercicio=AAAA/uf=XX/arquivo.jsonl); o arquivo de origem fica em
-- _arquivo_silver, para rastrear cada linha até o artefato do bronze.

CREATE OR REPLACE MACRO silver_consolidada(raiz, entidade) AS TABLE
    WITH linhas AS (
        SELECT *
        FROM read_json_auto(
            raiz || '/' || entidade || '/exercicio=*/uf=*/*.jsonl',
            format = 'newline_delimited',
            hive_partitioning = true,
            union_by_name = true,
            filename = true
        )
        -- Nem toda entidade tem atualizado_em (órgão, item, ata...) e uma
        -- coleta sem instante não grava _coletado_em. A relação vazia abaixo
        -- garante as duas colunas, nulas quando o arquivo não as traz, para
        -- que a mesma macro sirva a qualquer entidade.
        UNION ALL BY NAME
        SELECT NULL AS atualizado_em, NULL AS _coletado_em WHERE false
    ),
    ordenadas AS (
        SELECT
            *,
            row_number() OVER (
                PARTITION BY id
                ORDER BY
                    CAST(atualizado_em AS VARCHAR) DESC NULLS LAST,
                    CAST(_coletado_em AS VARCHAR) DESC NULLS LAST,
                    filename DESC
            ) AS _posicao
        FROM linhas
    )
    SELECT * EXCLUDE (filename, _posicao), filename AS _arquivo_silver
    FROM ordenadas
    WHERE _posicao = 1
    ORDER BY id;
