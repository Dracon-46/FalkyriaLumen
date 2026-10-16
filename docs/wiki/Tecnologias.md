# Tecnologias

Cada escolha tem o motivo registrado numa ADR. A regra geral vem da
[ADR-015](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-015.md): dependência nova
entra junto com a funcionalidade que a exige, com o motivo registrado, porque cada uma é superfície
de ataque e custo de manutenção a mais.

## Linguagens

| Linguagem | Onde | Por quê |
|---|---|---|
| Python 3.11 ou superior | Ingestão, normalização, detecção, conformidade, eleições, painéis, mercado, ferramentas | O ecossistema de coleta, extração de documentos e análise estatística é dominado por Python ([ADR-003](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-003.md)) |
| TypeScript | Portal (e, na Fase 3, a API pública) | A equipe domina Node com arquitetura limpa; do indício até o usuário é TypeScript ([ADR-003](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-003.md)) |
| SQL (PostgreSQL 16 e DuckDB) | Migrações do domínio e macro da silver consolidada | Garantias impostas pelo próprio banco; consulta analítica sobre a silver ([ADR-005](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-005.md), [ADR-016](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-016.md)) |
| JavaScript (Node) | Geração dos `.docx` em `docs-src/` | Biblioteca `docx` e `mermaid-cli` para os diagramas |

O código de domínio é escrito em português (entidades, campos, regras); infraestrutura e
utilitários podem usar inglês (DOC-09, seção 1.1).

## Python

O pacote `falkyria-lumen` ([`pyproject.toml`](https://github.com/Dracon-46/FalkyriaLumen/blob/main/pyproject.toml))
não tem dependências de execução: tudo usa a biblioteca padrão, inclusive `tomllib` para a
configuração, `urllib` para HTTP e S3 e a leitura de `.xlsx`.

| Dependência | Grupo | Para quê |
|---|---|---|
| `pytest>=8`, `pytest-cov>=5` | `dev` | Suíte de testes e cobertura mínima de 80% |
| `ruff>=0.6` | `dev` | Análise estática (`E`, `F`, `W`, `I`, `B`; linha de 120 caracteres) |
| `duckdb>=1.1` | `analitico` (opcional) | Consulta analítica da silver; o pipeline grava sem ele ([ADR-016](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-016.md)) |

Escolhas feitas para não depender de bibliotecas externas:

- **Cliente S3 próprio** em `urllib`, com assinatura AWS Signature Version 4, escrita condicional
  (`If-None-Match: *`) e Object Lock em modo COMPLIANCE, em vez do `boto3`
  ([ADR-018](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-018.md)). A camada
  bronze é a que guarda a prova, e é onde menos superfície de ataque se quer.
- **Silver em JSON Lines** em vez de Parquet com `pyarrow`, até haver volume que justifique a
  dependência ([ADR-016](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-016.md)).
- **Leitor de `.xlsx`** só com a biblioteca padrão, para as planilhas semanais da ANP
  ([`xlsx.py`](https://github.com/Dracon-46/FalkyriaLumen/blob/main/packages/mercado/lumen_mercado/xlsx.py)).
- **TopoJSON decodificado sem biblioteca** no portal (CHANGELOG 0.3.0).

## Portal

[`packages/portal/package.json`](https://github.com/Dracon-46/FalkyriaLumen/blob/main/packages/portal/package.json):

| Pacote | Versão | Uso |
|---|---|---|
| `next` | 16.3.8 | Site com exportação estática (`output: "export"`), sem servidor Node em produção |
| `react`, `react-dom` | 19.3.0 | Interface |
| `typescript` | 5.9.3 | Tipos estritos (`npm run tipos`) |
| `vitest` | 5.0.3 | Testes de unidade (`npm run testes`) |
| `@types/node` | 22.20.5 | Tipos do Node |

O portal exige Node 20.9 ou superior (`engines`); a CI usa Node 22. Ele é estático porque, na noite
da apuração, o custo de servir arquivos é o de qualquer CDN, e não há servidor a operar no pico
([ADR-019](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-019.md)).

## Armazenamento e banco

| Tecnologia | Papel | Situação | ADR |
|---|---|---|---|
| Disco local | Bronze e silver no desenvolvimento (`ArmazemBronzeLocal`) | em uso | [ADR-002](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-002.md) |
| S3 compatível (MinIO, Cloudflare R2, Supabase Storage) | Bronze com Object Lock; feeds e estado das cargas das eleições | em uso | [ADR-018](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-018.md), [ADR-026](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-026.md) |
| JSON Lines particionado + DuckDB | Camada silver | em uso | [ADR-016](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-016.md) |
| PostgreSQL 16 | Banco de domínio (indícios, revisão, contestação, auditoria) | migração testada na CI | [ADR-005](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-005.md) |
| Parquet | Silver e gold compactadas; dados volumosos no R2 | planejado | [ADR-005](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-005.md), [ADR-026](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-026.md) |
| Dagster | Orquestrador centrado em ativos de dados | Fase 2 | [ADR-009](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-009.md) |
| OpenSearch | Busca textual | Fase 3 | DOC-04 |
| Node.js + TypeScript | API pública | Fase 3 | [ADR-003](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-003.md) |

O Supabase Storage não oferece Object Lock; por isso serve para os feeds, que são refeitos a partir
das fontes, mas não para a prova, que exige o R2 com trava de bucket
([ADR-026](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-026.md), adendo).

## Hospedagem

A condição da Fase 1 é custo zero e nenhum computador pessoal ligado
([ADR-026](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-026.md)). Cada tipo de
dado vai para o serviço gratuito que lhe serve:

| Serviço | O que roda ou guarda | Por quê |
|---|---|---|
| GitHub Actions | CI, cargas das eleições, coleta dos painéis, referência de mercado, testes de contrato | Cargas agendadas e retomáveis; repositório público desde 14/10/2026, então os minutos não são cobrados |
| Supabase Storage | Feeds das eleições (bucket `lumen-eleicoes`, público) e estado da carga (`lumen-privado`) | Gratuito sem meio de pagamento; configuração escolhida para o 2º turno de 2026 |
| Cloudflare R2 | Alternativa para feeds e estado; destino previsto da prova (com trava) e do Parquet | Saída grátis e Object Lock; a assinatura pede meio de pagamento mesmo no plano gratuito |
| Vercel (plano Hobby) | Portal, em uso desde 14/10/2026 | Gera o site a partir do repositório sem token guardado no GitHub |
| Cloudflare Pages | Portal, alternativa (`portal-pages.yml`) | Site estático publicado pelo fluxo com token |
| GitHub Pages | Site JSON dos painéis (`https://dracon-46.github.io/FalkyriaLumen/`) | Sem custo e fora da cota de saída do Supabase, reservada à noite da eleição ([ADR-028](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-028.md)) |
| Anexos da versão `painel-estado` | Estado dos painéis (um arquivo por dia do PNCP e por UF) | Sem custo e fora do 1 GB do Supabase ([ADR-028](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-028.md)) |
| Supabase (banco gratuito) | Núcleo transacional (migração 0001), numa organização própria do projeto | Planejado; cabe em 500 MB por muito tempo |

Os nomes dos segredos e variáveis (`R2_*`) valem para qualquer armazenamento compatível com S3:
trocar de Supabase para R2 é trocar os valores e gerar o portal de novo com o endereço novo.

## Ambiente local

[`infra/docker-compose.yml`](https://github.com/Dracon-46/FalkyriaLumen/blob/main/infra/docker-compose.yml)
sobe `postgres:16` (com as migrações aplicadas na primeira subida) e MinIO com o bucket
`lumen-bronze` com Object Lock e versionamento. Ver [[Banco de dados|Banco-de-Dados]].

## Documentação

`docs-src/` gera os `.docx` com a biblioteca `docx` (^9.7.2) e os diagramas com
`@mermaid-js/mermaid-cli` (^11.0.0). O DOC-11 é extraído do código por
[`ferramentas/referencia/referencia.py`](https://github.com/Dracon-46/FalkyriaLumen/blob/main/ferramentas/referencia/referencia.py)
([ADR-023](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-023.md)).
