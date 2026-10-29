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
| [016](ADR-016.md) | Camada silver em JSON Lines particionado na Fase 1 | **proposta** |
| [017](ADR-017.md) | Modelo de fatos da Fase 1 a partir das respostas reais das fontes | **proposta** |
| [018](ADR-018.md) | Cliente S3 próprio, só com a biblioteca padrão | **proposta** |
| [019](ADR-019.md) | Aba Eleições: coletor único, feeds JSON versionados e portal estático | **proposta** |
| [020](ADR-020.md) | Cor identifica o candidato pela ordem de votação, nunca o partido | **proposta**, substituída em parte pela 052 |
| [021](ADR-021.md) | Arquivos grandes fora do bronze, com manifesto e download retomável | **proposta** |
| [022](ADR-022.md) | Revisão da regra B-01 frente ao art. 75, § 1º, da Lei 14.133 | **proposta (revisão jurídica)** |
| [023](ADR-023.md) | Referência técnica gerada do código e cobrada por teste | **proposta** |
| [024](ADR-024.md) | Eleições é dado oficial, não indício: fronteira e integração futura | **proposta** |
| [025](ADR-025.md) | Eleições de 1933 a 1990, referências embutidas e carga num comando | **proposta** |
| [026](ADR-026.md) | Hospedagem gratuita: Supabase Free, Cloudflare R2 e Pages, carga no GitHub Actions | **proposta** |
| [027](ADR-027.md) | Referência de mercado de fora do governo: regra A-05 em modo silencioso | **proposta** |
| [028](ADR-028.md) | Painéis de contratações e de conformidade: fatos publicados, sem indício | **proposta** |
| [029](ADR-029.md) | Zonas eleitorais no mapa do município: resultado por zona e contorno aproximado | **proposta** |
| [030](ADR-030.md) | Sanções da CGU (CEIS, CNEP e CEPIM) pelos arquivos de dados abertos, em retrato diário e com CPF mascarado | **proposta** |
| [031](ADR-031.md) | Regra J-01 em modo silencioso: contratos do painel cruzados com o CEIS e o CNEP a cada carga | **proposta** |
| [032](ADR-032.md) | Cadastro nacional dos portais de transparência pelo PNTP, lido por partes de dentro do ZIP | **proposta** |
| [033](ADR-033.md) | Economia e Contas Públicas: séries oficiais do SGS, catálogo documentado e comparação de períodos sem atribuição de causa | **proposta** |
| [034](ADR-034.md) | Empresas estatais: controle conferido no FRE, demonstrações da CVM e dispêndios da SEST, sem somar empresas | **proposta** |
| [035](ADR-035.md) | Visão 360 por filtro de local, modal da contratação, documentos do PNCP pela própria fonte e atualização diária de todas as áreas | **proposta** |
| [036](ADR-036.md) | Comparação de preço do item com outros órgãos, sob demanda no modal (regra A-01) | **proposta** |
| [037](ADR-037.md) | Preço de mercado no modal: ANP publicada todo dia e A-05 sob demanda; lojas online só por API oficial | **proposta** |
| [038](ADR-038.md) | Grupos de pares por porte e região, com recuo para o porte no país e a RCL para uma próxima versão | **proposta** |
| [039](ADR-039.md) | Painel operacional: execuções dos fluxos, volume diário do PNCP e coleta da conformidade, numa página pública | **proposta** |
| [040](ADR-040.md) | Governos municipais na Economia: mandatos de prefeito, população e despesa, lidos sob demanda | **proposta** |
| [041](ADR-041.md) | Despesa por função dos entes, por habitante, ao lado do grupo de pares | **proposta** |
| [042](ADR-042.md) | Despesa com pessoal do Executivo em % da RCL, com os limites do próprio RGF, ao lado do grupo | **proposta** |
| [043](ADR-043.md) | Nome "Lumen", sócios da base de CNPJ e CPF mascarado em nomes e textos | **proposta** |
| [044](ADR-044.md) | Emendas parlamentares recebidas por município e UF, pelo arquivo de dados abertos da CGU | **proposta** |
| [045](ADR-045.md) | Convênios da União com estados, municípios e entidades, pelo arquivo de dados abertos da CGU | **proposta** |
| [046](ADR-046.md) | Histórico desde 2021 nos painéis e filtro de período em todas as abas | **proposta** |
| [047](ADR-047.md) | Avisos públicos: o que aconteceu e o que observar, sem revisão humana prévia | **proposta** |
| [048](ADR-048.md) | Relatório de cobertura por ente e UF | **proposta** |
| [049](ADR-049.md) | Visão 360 da empresa ou entidade pelo CNPJ | **proposta** |
| [050](ADR-050.md) | Tribunais de contas: o levantamento, a ordem de integração e o TCE-RS primeiro | **proposta** |
| [051](ADR-051.md) | As tabelas do portal em CSV | **proposta** |
| [052](ADR-052.md) | PL azul e PT vermelho, em todas as eleições | **proposta** |
| [053](ADR-053.md) | Conferência seção a seção: a votação por seção contra o total divulgado | **proposta** |
| [054](ADR-054.md) | Transferências da União a estados, municípios e entidades, pelo arquivo mensal da CGU | **proposta** |
| [055](ADR-055.md) | Eleitorado do Brasil à seção, com perfil e comparecimento por perfil, publicado no site dos painéis | **proposta** |

As ADRs 011 a 015 foram tomadas durante a implementação da Fase 0, e as 016 a
033 durante a Fase 1 e a criação da aba Eleições; todas aguardam revisão. Para aceitar, troque a situação para `aceita`. Para rejeitar, marque
`rejeitada` com o motivo — não apague o arquivo.

## Nova ADR

Copie a estrutura de qualquer uma: título, situação, data, origem, contexto,
decisão, alternativas consideradas e consequências. Numere em sequência.
