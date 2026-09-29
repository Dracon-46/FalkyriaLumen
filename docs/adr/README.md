# Registro de decisões arquiteturais

Cada decisão relevante fica registrada com contexto, alternativas e
consequências. Decisões podem ser substituídas por outras posteriores, mas
nunca apagadas: uma ADR substituída continua aqui, marcada como tal.

| ADR | Decisão | Situação |
|---|---|---|
| [001](ADR-001.md) | PNCP e SICONFI como espinha dorsal nacional | aceita |
| [002](ADR-002.md) | Camada bronze imutável como fonte de verdade | aceita |
| [003](ADR-003.md) | Python na ingestão e detecção, TypeScript na API e no portal | aceita |
| [004](ADR-004.md) | Conectores declarativos em vez de código por fonte | aceita |
| [005](ADR-005.md) | PostgreSQL para domínio e formato colunar para análise | aceita |
| [006](ADR-006.md) | Regras explicáveis em vez de aprendizado de máquina na 1.0 | aceita |
| [007](ADR-007.md) | Vocabulário controlado imposto por ferramenta | aceita |
| [008](ADR-008.md) | Revisão humana obrigatória acima do limiar de severidade | aceita |
| [009](ADR-009.md) | Dagster como orquestrador | aceita |
| [010](ADR-010.md) | Monorepo com pacotes separados | aceita |
| [011](ADR-011.md) | Conteúdo deduplicado por hash, evento de coleta nunca | **proposta** |
| [012](ADR-012.md) | Resposta HTTP de erro preservada como prova | **proposta** |
| [013](ADR-013.md) | Parâmetro legal não verificado recusado por padrão | **proposta** |
| [014](ADR-014.md) | Vocabulário verificado no modelo, não no texto renderizado | **proposta** |
| [015](ADR-015.md) | Fase 0 sem dependências externas de execução | **proposta** |

As ADRs 011 a 015 foram tomadas durante a implementação da Fase 0 e aguardam
revisão. Para aceitar, troque a situação para `aceita`. Para rejeitar, marque
`rejeitada` com o motivo — não apague o arquivo.

## Nova ADR

Copie a estrutura de qualquer uma: título, situação, data, origem, contexto,
decisão, alternativas consideradas e consequências. Numere em sequência.
