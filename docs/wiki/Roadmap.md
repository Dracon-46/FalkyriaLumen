# Roadmap

Fonte: [DOC-10 Roadmap](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/DOC-10_Roadmap.docx)
(versão 1.4, de 9/10/2026) e a seção "Pendente" do
[README](https://github.com/Dracon-46/FalkyriaLumen/blob/main/README.md).

## Estratégia

Entregar cobertura nacional o mais cedo possível e deixar para depois o trabalho que escala mal.
As bases federais obrigatórias (PNCP e SICONFI) entregam em semanas o que a raspagem municipal
levaria anos para alcançar; a cauda longa municipal vira incremento. Ao fim da Fase 2, perto de
cinco meses após o início, o sistema já detecta padrões sobre dados de alcance nacional.

O erro mais provável, segundo o DOC-10, é ampliar cobertura antes de consolidar qualidade. A
credibilidade do projeto vem de quantas vezes ele esteve certo quando sinalizou algo, não de quantos
entes monitora.

## Fases

| Fase | Período | Objetivo | Critério de saída | Situação |
|---|---|---|---|---|
| 0 — Fundação | Mês 1 | Bases técnicas e decisões difíceis de mudar depois | Artefato coletado, armazenado com hash e recuperado pelo identificador | **Concluída** (marco M1 verificado por teste) |
| 1 — Espinha dorsal nacional | Meses 2 a 4 | Cobertura nacional de contratações e dados fiscais | Carga histórica de ao menos três exercícios, com relatório de cobertura por ente e UF | **Núcleo pronto**; critério de saída não iniciado |
| 2 — Motor de detecção | Meses 5 a 7 | Indícios revisáveis, com evidência completa | Amostra de 100 indícios por família revisada, com falso positivo dentro do limite do DOC-07 | Não iniciada (A-05 antecipada em modo silencioso) |
| 3 — Camada estadual | Meses 8 e 9 | Profundidade estadual e tribunais de contas | Cadastro de fonte por analista, sem código, validado em ao menos cinco fontes reais | Não iniciada |
| 4 — Cauda longa municipal | Meses 9 a 11 | Lacunas municipais por família de plataforma e extração de documentos | Relatório de cobertura municipal | Não iniciada |
| 5 — Publicação | Meses 10 a 12 | Abrir ao público com todas as salvaguardas | Contestação testada de ponta a ponta e parecer jurídico externo favorável | Não iniciada |
| 6 — Consolidação | Mês 12 | Operação sustentável por equipe reduzida | Uma semana sem intervenção manual não planejada | Não iniciada |

### Entregáveis por fase

**Fase 0.** Monorepo com CI; esquema canônico e primeira migração; camada bronze com hash,
versionamento e imutabilidade; verificador de vocabulário na CI; ADR-001 a ADR-010; ambiente local
por um comando. Tudo concluído; ADRs 011 em diante registradas durante a implementação.

**Fase 1.**

| Entregável | Situação |
|---|---|
| Conector PNCP (contratações, contratos, atas, amparo legal, incremental) | Concluído, com itens e resultados |
| Conector SICONFI com lista de entes ausentes | Entes e extrato concluídos, com a avaliação da LRF; RREO, RGF e DCA com conector pronto e normalização pendente |
| Portal da Transparência (CGU), com CEIS, CNEP e CEPIM | Cadastros de sanções concluídos, pelos arquivos de dados abertos, sem chave (ADR-030); despesas, convênios e emendas pendentes |
| Base pública de CNPJ da Receita Federal | Pendente |
| Cadastro de entes do IBGE com população e porte | Concluído |
| Normalização com qualidade e quarentena | Concluída para PNCP, SICONFI e IBGE |
| Grupos de pares | Concluído (ADR-038): porte, região e RCL por habitante (versão 2), comparação na conformidade de cada ente |
| Painel operacional | Concluído (ADR-039): "Situação das coletas", com fluxos, volume diário do PNCP e coleta da conformidade |
| Parâmetros legais verificados | Concluído além do previsto: limites de dispensa de 2021 a 2026, fator do § 2º e acréscimos do art. 125 |
| Regra A-05 (antecipada da Fase 2) | Relatório silencioso; sob demanda no modal para combustível e gás de cozinha (ADR-037), limiares não calibrados |
| Regra A-01 (antecipada da Fase 2) | Sob demanda no modal da contratação, parâmetros iniciais, sem lote (ADR-036) |

**Fase 2.** Motor de regras com versionamento, parâmetros datados e linhagem; famílias B, E, I e J;
depois A e H; depois C, D, F e G; score composto e severidade; interface de revisão humana com fila e
trilha de auditoria; ambiente de calibração; todas as regras em modo silencioso.

**Fase 3.** Motor de conectores declarativos; levantamento das fontes estaduais e dos tribunais de
contas; conectores; registro de não conformidade dos entes sem publicação localizável.

**Fase 4.** Levantamento das famílias de plataforma municipal; conectores das de maior alcance;
extrator de PDF, planilha e HTML com OCR; mapeamento assistido com validação humana.

**Fase 5.** Índice de conformidade publicado por ente; portal com panorama, busca e página de
indício; API pública; exportação em CSV e Parquet e dossiê; direito de resposta completo;
metodologia publicada; revisão da política editorial por advogado externo.

**Fase 6.** Observabilidade nos três níveis; procedimentos operacionais com restauração testada;
documentação consistente com o código; avaliação da abertura do código; plano de sustentação.

### Trilhas paralelas

| Trilha | Situação |
|---|---|
| Aba Eleições ([ADR-024](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-024.md)) | Pronta: coleta ao vivo do TSE, eleições de 1933 a 2026, mapa com zonas eleitorais, carga num comando, carga e publicação na nuvem |
| Painéis de Contratações e Conformidade ([ADR-028](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-028.md)) | No ar desde 14/10/2026 |
| Contexto eleitoral nas telas de contratação (família K) | Fase 2 em diante |

## Marcos

| Marco | Quando | Significado |
|---|---|---|
| M1 | Fim do mês 1 | Prova preservada: artefato coletado, armazenado com hash e recuperado — **cumprido** |
| M2 | Fim do mês 4 | Cobertura nacional de contratações e dados fiscais |
| M3 | Fim do mês 7 | Detecção validada, com falso positivo aceitável |
| M4 | Fim do mês 9 | Tribunais de contas integrados |
| M5 | Fim do mês 11 | Cobertura municipal medida, com lacunas explicitadas |
| M6 | Fim do mês 12 | Sistema público em operação, com direito de resposta |

## Esforço estimado

Uma pessoa em dedicação parcial consistente: 16,0 pessoa-mês no total (Fase 0: 1,0; Fase 1: 3,0;
Fase 2: 3,5; Fase 3: 2,0; Fase 4: 3,0; Fase 5: 2,5; Fase 6: 1,0), compatível com doze meses porque
as fases se sobrepõem: o tempo de carga histórica e de calibração é sobretudo espera.

## Pendente

Da seção "Pendente" do README:

- **Revisar as ADRs 011 a 029**, todas propostas, tomadas durante a implementação.
- **2º turno de 2026 nos dados abertos.** O 1º turno já vem deles, com as zonas; o 2º turno é coletado
  ao vivo e passa para os dados abertos quando o TSE o acrescentar ao arquivo de 2026, que o
  `preparar` confere a cada execução.
- **Calibrar a regra A-05** sobre o relatório silencioso
  ([ADR-027](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-027.md)). Até lá, a comparação
  sob demanda do modal usa os limiares iniciais e diz isso
  ([ADR-037](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-037.md)).
- **Contas da hospedagem gratuita** ([ADR-026](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-026.md)):
  Cloudflare (R2 e Pages), segredos do GitHub e uma organização própria do projeto no Supabase para
  o núcleo. Os feeds das eleições estão no Supabase Storage desde 14/10/2026, com o histórico.
- **Revisão metodológica e jurídica da regra B-01** frente ao art. 75, § 1º, da Lei 14.133
  ([ADR-022](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-022.md)), antes da
  Fase 2. Nenhuma regra da família B é implementada antes dessa revisão.
- **Fonte para "quem autorizou o ato".** A API do PNCP não publica o agente
  ([ADR-017](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-017.md)), e o DOC-08
  exige essa informação para publicar indício.
- **Portais da transparência municipais** (ADR-028): o que não passa pelo PNCP. O cadastro dos
  portais de todos os entes vem do PNTP (ADR-032). Próximos passos: o nível do PNTP nos painéis e a
  leitura dos próprios portais, por fornecedor de sistema.
- **Economia e Contas Públicas** (ADR-033): no ar com inflação, juros, dívida, resultado fiscal,
  atividade, desocupação e rendimento (PNAD Contínua), população, despesa da União por função e a comparação
  de períodos; os governos municipais (ADR-040) e a despesa por função de cada ente ao lado do grupo de pares
  (ADR-041). Também a receita da União. Próximo: as séries fiscais do próprio ente ano a ano (RREO e RGF).
  Paginação (20 por página) e filtro de período nas Contratações já no ar.
- **Visão 360 pelo filtro de local** (ADR-035): no ar. O local escolhido no cabeçalho filtra todas as abas,
  e a contratação abre num modal com itens, vencedores, aditivos e os documentos do PNCP para baixar. Também
  no ar: o portal de transparência avaliado pelo PNTP na Conformidade. Próximos: o resultado por zona de
  2018 a 2024 (reprocessar os dados abertos desses anos) e as séries fiscais do ente (RREO e RGF).
- **Comparação de preço do item** (ADR-036, regra A-01 sob demanda): no ar no modal da contratação, para
  os itens com código do catálogo do Compras.gov.br. Próximos: calibrar a A-01 (Fase 2) e classificar os
  itens sem código, para ampliar a cobertura.
- **Preço de mercado no modal** (ADR-037, regra A-05 sob demanda): no ar para combustível e gás de cozinha,
  contra o preço de revenda da ANP publicado todo dia. Próximos: as lojas online pela API oficial (Mercado Livre,
  Amazon, Shopee, AliExpress), quando houver credencial.
- **Gastos das estatais** (ADR-034): no ar. As federais pelo PDG da SEST (aprovado e realizado por
  rubrica) e as com ações na bolsa pelas demonstrações da CVM, com o controle conferido no FRE. Próximos:
  o Orçamento de Investimento (por ação e UF), as demonstrações trimestrais (ITR) e as estaduais e
  municipais de capital fechado.
- **Regra J-01** (ADR-031): sanções da CGU × contratos do painel, em modo silencioso a cada carga;
  calibrar e revisar antes de publicar.
- **Fase 1 restante:** base de CNPJ da Receita Federal (os grupos de pares têm o cálculo inicial,
  ADR-038, com a despesa por função ao lado, ADR-041, e o painel operacional está no portal, ADR-039). Os
  cadastros de sanções da CGU já entram no pipeline; o cruzamento com as contratações é a regra J-01 da
  Fase 2.

### Definições não técnicas antes da publicação

| Decisão | Quando | Por que condiciona o desenvolvimento |
|---|---|---|
| Nome definitivo | Antes da Fase 0 (pendente) | "Lumen" é nome de trabalho e precisa de verificação de marca (INPI) e domínio |
| Natureza institucional | Antes da Fase 5 | Projeto pessoal, produto da empresa ou iniciativa sem fins lucrativos; afeta a percepção de imparcialidade |
| Abertura do código | Antes da Fase 6 | Reforça a credibilidade da metodologia, mas exige disciplina de documentação e governança |
| Apoio jurídico | Antes da Fase 5 | A revisão da política editorial por advogado é critério de saída da Fase 5 |

O domínio próprio do portal e dos feeds depende do nome definitivo.

## Critérios de replanejamento

- Cobertura nacional abaixo do esperado ao fim da Fase 1: antecipar a Fase 3 e reduzir a Fase 4.
- Falso positivo de uma família persistentemente acima do limite: adiar a família, em vez de
  publicá-la com ressalvas.
- Concentração em famílias de plataforma municipal muito menor que a esperada: reduzir a Fase 4 ao
  mapeamento assistido.
- Operação da Fase 1 exigindo mais atenção manual que o previsto: antecipar a Fase 6.
