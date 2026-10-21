const L = require("./lib");
const { h1, h2, h3, p, bullet, numbered, table, callout, code, figure, pageBreak, spacer } = L;

const body = [];
// Versão 1.1 (outubro de 2026): seção 9 com a situação de cada fase e a trilha
// paralela da aba Eleições. O plano das seções 1 a 8 fica como foi aprovado.

function fase({ num, nome, periodo, objetivo, entregaveis, saida, riscos }) {
  const out = [];
  out.push(h2(`Fase ${num} — ${nome}`));
  out.push(table(null, [1900, 7700], [
    ["Período", periodo],
    ["Objetivo", objetivo],
    ["Critério de saída", saida],
    ["Risco principal", riscos],
  ], { boldFirstCol: true }));
  out.push(h3("Entregáveis"));
  entregaveis.forEach((e) => out.push(bullet(e)));
  out.push(spacer(160));
  return out;
}

body.push(h1("1. Estratégia do plano"));
body.push(p("O plano é organizado por uma regra de priorização única: entregar cobertura nacional o mais " +
  "cedo possível, e deixar para depois o trabalho que escala mal. Isso inverte a ordem intuitiva, que " +
  "começaria por um município piloto e cresceria dali."));
body.push(p("A inversão se justifica porque as bases federais obrigatórias já concentram dados de " +
  "praticamente todos os entes. Integrar o PNCP entrega, em semanas, o que a raspagem municipal levaria " +
  "anos para alcançar. A cauda longa municipal não desaparece, mas deixa de ser o caminho crítico e " +
  "passa a ser incremento sobre um sistema que já funciona em escala nacional."));

body.push(callout("O marco que muda o projeto de natureza", [
  "Ao final da fase 2, aproximadamente cinco meses após o início, o sistema já detecta padrões sobre " +
  "dados de alcance nacional. A partir desse ponto o projeto deixa de ser promessa e passa a produzir " +
  "resultado verificável, o que muda completamente sua capacidade de atrair colaboradores, parceiros " +
  "institucionais e atenção da imprensa.",
], "green"));

body.push(callout("Situação em 6 de outubro de 2026", [
  "Fase 0 concluída (marco M1 verificado por teste). Fase 1 com o núcleo pronto: PNCP, SICONFI e IBGE " +
  "coletados, normalizados e reconstruíveis a partir da prova. Aba Eleições pronta como trilha paralela. " +
  "O detalhamento, com o que falta em cada fase, está na seção 9.",
], "blue"));

body.push(h1("2. Visão geral do cronograma"));
body.push(...figure("09_roadmap.png", "Figura 1. Cronograma de doze meses, da fundação à consolidação.", 640));

body.push(pageBreak());
body.push(h1("3. Fases detalhadas"));

body.push(...fase({
  num: 0, nome: "Fundação", periodo: "Mês 1",
  objetivo: "Estabelecer as bases técnicas e as decisões que serão difíceis de mudar depois",
  entregaveis: [
    "Monorepo criado com a estrutura de pacotes do DOC-04 e integração contínua funcionando",
    "Esquema canônico implementado com as entidades centrais do DOC-05 e primeira migração",
    "Camada bronze operacional: armazenamento de objetos com hash, versionamento e imutabilidade",
    "Verificador de vocabulário controlado implementado e integrado ao pipeline de CI",
    "ADR-001 a ADR-010 registradas no repositório",
    "Ambiente local completo executável por um único comando",
  ],
  saida: "Um artefato de teste é coletado, armazenado com hash verificável e recuperado a partir do identificador",
  riscos: "Excesso de tempo em infraestrutura; mitigado por limite rígido de um mês e escopo fechado",
}));

body.push(...fase({
  num: 1, nome: "Espinha dorsal nacional", periodo: "Meses 2 a 4",
  objetivo: "Obter cobertura nacional de contratações e dados fiscais integrando as bases federais obrigatórias",
  entregaveis: [
    "Conector PNCP cobrindo contratações, contratos, atas e amparo legal, com coleta incremental",
    "Conector SICONFI cobrindo RREO, RGF e DCA, com captura da lista de entes ausentes",
    "Conector Portal da Transparência da CGU, incluindo CEIS, CNEP e CEPIM",
    "Ingestão da base pública de CNPJ da Receita Federal com quadro societário",
    "Cadastro de entes a partir da base do IBGE, com população e classificação de porte",
    "Normalização para o esquema canônico com regras de qualidade e quarentena",
    "Cálculo inicial dos grupos de pares",
    "Painel operacional com saúde das coletas e alarme de variação de volume",
  ],
  saida: "Carga histórica de ao menos três exercícios concluída, com relatório de cobertura por ente e por UF",
  riscos: "Volume da carga histórica maior que o previsto; mitigado por coleta incremental e paralelismo por UF",
}));

body.push(...fase({
  num: 2, nome: "Motor de detecção", periodo: "Meses 5 a 7",
  objetivo: "Transformar a base normalizada em indícios revisáveis, com evidência completa",
  entregaveis: [
    "Motor de regras com versionamento, parâmetros datados e registro de linhagem",
    "Famílias B, E, I e J implementadas: fracionamento, anomalias processuais, conformidade e sanções",
    "Famílias A e H implementadas após normalização de itens por catálogo",
    "Famílias C, D, F e G implementadas",
    "Cálculo de score composto e severidade conforme o DOC-07",
    "Interface de revisão humana com fila priorizada e trilha de auditoria",
    "Ambiente de calibração com simulação sobre janela histórica",
    "Todas as regras em modo silencioso, acumulando dados para calibração",
  ],
  saida: "Amostra de 100 indícios por família revisada manualmente, com taxa de falso positivo dentro do limite do DOC-07",
  riscos: "Taxa de falso positivo acima do aceitável; mitigado pelo modo silencioso, que impede publicação prematura",
}));

body.push(...fase({
  num: 3, nome: "Camada estadual", periodo: "Meses 8 e 9",
  objetivo: "Adicionar profundidade estadual e cobertura indireta de municípios via tribunais de contas",
  entregaveis: [
    "Motor de conectores declarativos concluído e documentado",
    "Levantamento das fontes estaduais e dos tribunais de contas, ordenado por municípios cobertos",
    "Conectores para os tribunais de contas com dados abertos consolidados",
    "Conectores para os portais estaduais com dado estruturado disponível",
    "Registro de não conformidade para os entes sem publicação localizável",
  ],
  saida: "Cadastro de fonte por analista, sem escrita de código, validado em ao menos cinco fontes reais",
  riscos: "Heterogeneidade maior que a prevista; mitigado por priorização pelo alcance e aceitação de cobertura parcial",
}));

body.push(...fase({
  num: 4, nome: "Cauda longa municipal", periodo: "Meses 9 a 11",
  objetivo: "Preencher lacunas municipais com conectores por família de plataforma e extração de documentos",
  entregaveis: [
    "Levantamento das famílias de plataforma de portal municipal, com medição do alcance de cada uma",
    "Conectores para as famílias de maior alcance, validados em amostra aleatória",
    "Extrator de documentos com suporte a PDF, planilha e HTML, incluindo OCR com marcação de confiança reduzida",
    "Fluxo de mapeamento assistido com validação humana obrigatória",
    "Registro sistemático de entes sem publicação localizável, alimentando o índice de conformidade",
  ],
  saida: "Relatório de cobertura municipal mostrando entes cobertos, parcialmente cobertos e sem publicação localizável",
  riscos: "Concentração em famílias de plataforma menor que o esperado; mitigado pela medição prévia, que permite recalibrar antes de investir",
}));

body.push(...fase({
  num: 5, nome: "Publicação", periodo: "Meses 10 a 12",
  objetivo: "Abrir o sistema ao público com todas as salvaguardas editoriais operando",
  entregaveis: [
    "Índice de conformidade de transparência calculado e publicado por ente",
    "Portal público com panorama por ente, busca avançada e página de indício",
    "API pública documentada e versionada, com limite de taxa",
    "Exportação em CSV e Parquet e geração de dossiê de evidências",
    "Fluxo de direito de resposta completo, incluindo publicação de errata",
    "Metodologia de todas as regras ativas publicada em linguagem acessível",
    "Revisão da política jurídica e editorial por advogado externo",
  ],
  saida: "Fluxo de contestação testado ponta a ponta e parecer jurídico externo favorável à publicação",
  riscos: "Publicação antes da calibração adequada; mitigado pelo critério de liberação por regra do DOC-07",
}));

body.push(...fase({
  num: 6, nome: "Consolidação", periodo: "Mês 12",
  objetivo: "Tornar o sistema sustentável em operação por equipe reduzida",
  entregaveis: [
    "Observabilidade completa nos três níveis do DOC-04",
    "Procedimentos operacionais documentados, incluindo restauração testada",
    "Documentação técnica atualizada e consistente com o código entregue",
    "Avaliação da abertura do código-fonte e da metodologia",
    "Plano de sustentação: custos recorrentes, cadência de manutenção e critérios de expansão",
  ],
  saida: "Operação por uma semana sem intervenção manual não planejada",
  riscos: "Dívida técnica acumulada nas fases anteriores; mitigado por reserva explícita de capacidade nesta fase",
}));

body.push(pageBreak());
body.push(h1("4. Marcos"));
body.push(table(["Marco", "Quando", "Significado"], [1300, 1900, 6400], [
  ["M1", "Fim do mês 1", "Prova preservada: um artefato é coletado, armazenado com hash e recuperado"],
  ["M2", "Fim do mês 4", "Cobertura nacional: contratações e dados fiscais de alcance nacional na base"],
  ["M3", "Fim do mês 7", "Detecção validada: regras calibradas com taxa de falso positivo aceitável"],
  ["M4", "Fim do mês 9", "Profundidade estadual: tribunais de contas integrados"],
  ["M5", "Fim do mês 11", "Cobertura municipal medida e documentada, com lacunas explicitadas"],
  ["M6", "Fim do mês 12", "Sistema público em operação com direito de resposta funcionando"],
]));

body.push(h1("5. Esforço estimado"));
body.push(p("A estimativa considera uma pessoa em dedicação parcial consistente, que é o cenário " +
  "realista para o início. Está expressa em pessoa-mês para permitir recálculo caso a equipe cresça."));
body.push(table(["Fase", "Esforço estimado", "Observação"], [2200, 2400, 5000], [
  ["Fase 0", "1,0 pessoa-mês", "Escopo fechado; não deve exceder"],
  ["Fase 1", "3,0 pessoa-mês", "Maior retorno por esforço de todo o projeto"],
  ["Fase 2", "3,5 pessoa-mês", "Inclui o tempo de calibração, que não é comprimível"],
  ["Fase 3", "2,0 pessoa-mês", "Depende da qualidade das fontes estaduais"],
  ["Fase 4", "3,0 pessoa-mês", "Maior incerteza do plano"],
  ["Fase 5", "2,5 pessoa-mês", "Inclui portal e API"],
  ["Fase 6", "1,0 pessoa-mês", "Reserva para dívida técnica"],
  ["Total", "16,0 pessoa-mês", "Compatível com doze meses considerando sobreposição entre fases"],
]));
body.push(callout("Sobre a sobreposição entre fases", [
  "O cronograma mostra fases sobrepostas porque o tempo de calibração da fase 2 e o tempo de coleta " +
  "histórica da fase 1 são majoritariamente de espera, não de trabalho ativo. Enquanto uma carga roda " +
  "ou uma regra acumula dados em modo silencioso, o desenvolvimento avança na fase seguinte.",
], "blue"));

body.push(h1("6. Custos recorrentes estimados"));
body.push(p("Valores de referência para dimensionamento, em ordem de grandeza. Devem ser revistos com " +
  "números reais ao fim da fase 1, quando o volume efetivo de coleta será conhecido."));
body.push(table(["Item", "Fase 1", "Regime pleno", "Observação"], [2600, 2200, 2200, 2600], [
  ["Armazenamento de objetos", "Baixo", "Cresce continuamente", "Camada bronze nunca é apagada"],
  ["Armazenamento analítico", "Baixo", "Moderado", "Compressão colunar reduz muito o custo"],
  ["Banco de domínio", "Baixo", "Baixo a moderado", "Volume pequeno comparado à camada analítica"],
  ["Processamento", "Moderado na carga histórica", "Baixo em regime", "Sob demanda, liberado ao fim do ciclo"],
  ["Índice de busca", "Não aplicável", "Moderado", "Componente mais caro em regime; entra na fase 5"],
  ["Portal e API", "Não aplicável", "Baixo", "Tráfego previsível e cacheável"],
  ["Domínio e certificados", "Baixo", "Baixo", "Custo fixo pequeno"],
]));
body.push(p("A principal alavanca de custo é a política de ciclo de vida do armazenamento de objetos: " +
  "artefatos antigos migram para classes de acesso menos frequente sem perda de disponibilidade para " +
  "auditoria, o que mantém o custo da prova sob controle mesmo com crescimento permanente."));
body.push(p("Na Fase 1, a ADR-026 leva esses itens a custo zero com planos gratuitos (seção 9.5). O primeiro " +
  "gasto previsto é o domínio próprio; o seguinte, armazenamento de objetos além de 10 GB."));

body.push(pageBreak());
body.push(h1("7. Decisões que precisam ser tomadas antes de começar"));
body.push(p("Quatro definições não são técnicas e não podem ser adiadas indefinidamente, porque " +
  "condicionam escolhas das primeiras fases."));
body.push(table(["Decisão", "Quando", "Por que condiciona o desenvolvimento"], [2400, 1700, 5500], [
  ["Nome definitivo do projeto", "Antes da fase 0",
    "Decidido em 21/10/2026: o nome fica Lumen (ADR-043). O domínio próprio continua pendente, como decisão de custo"],
  ["Natureza institucional", "Antes da fase 5",
    "Projeto pessoal, produto da empresa ou iniciativa sem fins lucrativos; afeta percepção de imparcialidade e a estratégia de sustentação"],
  ["Abertura do código", "Antes da fase 6",
    "Código aberto reforça a credibilidade da metodologia e atrai colaboração, mas exige disciplina adicional de documentação e governança"],
  ["Apoio jurídico", "Antes da fase 5",
    "A revisão da política editorial por advogado é critério de saída da fase 5 e precisa estar contratada com antecedência"],
]));

body.push(h1("8. Critérios de replanejamento"));
body.push(p("O plano prevê explicitamente as condições em que deve ser revisto, para que o replanejamento " +
  "seja decisão consciente e não deriva silenciosa."));
body.push(bullet("Se a cobertura nacional ao fim da fase 1 ficar abaixo do esperado, a fase 3 é " +
  "antecipada e a fase 4 é reduzida, porque a profundidade passa a valer mais que a extensão."));
body.push(bullet("Se a taxa de falso positivo de uma família inteira ficar persistentemente acima do " +
  "limite, essa família é adiada em vez de publicada com ressalvas."));
body.push(bullet("Se a concentração em famílias de plataforma municipal for muito menor que a esperada, a " +
  "fase 4 é reduzida ao mapeamento assistido e o foco migra para a qualidade do que já está coberto."));
body.push(bullet("Se a operação da fase 1 consumir mais atenção manual que o previsto, a fase 6 é " +
  "antecipada, porque um sistema instável não sustenta publicação pública."));

body.push(callout("O erro mais provável neste plano", [
  "A tentação recorrente será ampliar cobertura antes de consolidar qualidade: adicionar mais fontes é " +
  "visivelmente produtivo, enquanto calibrar regra e reduzir falso positivo é trabalho invisível.",
  "Mas a credibilidade do projeto não decorre de quantos entes ele monitora, e sim de quantas vezes " +
  "ele esteve certo quando sinalizou algo. Um sistema que cobre todo o Brasil e erra com frequência é " +
  "pior que um que cobre metade e acerta — porque o primeiro perde a confiança que é seu único ativo.",
], "amber"));


// ============================================================ 9. Situação
body.push(h1("9. Situação em 20 de outubro de 2026", { novaPagina: true }));
body.push(p("As seções anteriores são o plano. Esta seção registra onde o projeto está, entregável por " +
  "entregável, para que o replanejamento da seção 8 parta de fatos e não de impressão."));

body.push(h2("9.1 Fase 0 — Fundação: concluída"));
body.push(table(["Entregável", "Situação"], [5200, 4400], [
  ["Monorepo e integração contínua", "Concluído: vocabulário, testes em Python 3.11 a 3.13 com cobertura mínima de 80%, ruff, migração no PostgreSQL e portal"],
  ["Esquema canônico e primeira migração", "Concluído: entidades do DOC-05 (seção 8) e migração 0001 testada no PostgreSQL 16"],
  ["Camada bronze", "Concluído: disco local e armazenamento de objetos S3 com Object Lock (ADR-018)"],
  ["Verificador de vocabulário no CI", "Concluído; cobre também o código da aba Eleições e os textos do portal"],
  ["ADR-001 a ADR-010", "Concluído; ADR-011 a ADR-026 registradas durante a implementação, todas como propostas"],
  ["Ambiente local por um comando", "Concluído: make ambiente (PostgreSQL e MinIO)"],
  ["Critério de saída (M1)", "Cumprido e verificado por teste: artefato coletado, guardado com hash e recuperado pelo identificador"],
], { size: 17 }));

body.push(h2("9.2 Fase 1 — Espinha dorsal nacional: núcleo pronto"));
body.push(table(["Entregável", "Situação"], [5200, 4400], [
  ["Conector PNCP (contratações, contratos, atas, amparo legal, incremental)", "Concluído, com coleta por publicação e por atualização; itens e resultados com conector e normalizador prontos"],
  ["Conector SICONFI com lista de entes ausentes", "Entes e extrato de entregas concluídos, com a avaliação da LRF; RREO, RGF e DCA com conector e normalização prontos (LinhaDemonstrativo), e a RCL, a despesa por função e a despesa com pessoal de todos os entes coletadas para os grupos de pares (ADR-038, ADR-041 e ADR-042)"],
  ["Portal da Transparência (CGU), com CEIS, CNEP e CEPIM", "Cadastros de sanções concluídos: coleta diária pelos arquivos de dados abertos, sem chave, e normalização com CPF mascarado (ADR-030); emendas parlamentares pelo arquivo de dados abertos, sem chave (ADR-044); convênios e despesas pendentes, pelo mesmo caminho"],
  ["Base pública de CNPJ da Receita Federal", "Concluído para os fornecedores dos contratos (ADR-043): cadastro, Simples e quadro societário, semanal, no fornecedor de Contratações"],
  ["Cadastro de entes do IBGE com população e porte", "Concluído"],
  ["Normalização com qualidade e quarentena", "Concluída para PNCP, SICONFI e IBGE; silver idempotente, reconstruível do bronze"],
  ["Grupos de pares", "Concluído (ADR-038): municípios por porte e região, com recuo para o porte no país abaixo de 15 entes; estados e DF num grupo; versão 2 com a receita corrente líquida por habitante (todo grupo com 30 entes com RCL publicada se divide na mediana). Comparação publicada na conformidade de cada ente"],
  ["Painel operacional", "Concluído (ADR-039): página pública \"Situação das coletas\" com as execuções dos fluxos, o volume diário do PNCP contra o usual (alarme de queda, sem falso positivo em 172 dias úteis de 2026) e a coleta da conformidade; limiares iniciais"],
  ["Cadastro dos portais de transparência (ADR-028)", "Concluído pelo PNTP (ADR-032): 11.697 entidades com endereço do portal e nível de transparência; leitura dos portais pendente"],
  ["Regra J-01: contratação de sancionado (antecipada da Fase 2)", "Em modo silencioso (ADR-031), a cada carga do painel; calibração e revisão pendentes"],
  ["Parâmetros legais verificados", "Concluído além do previsto: limites de dispensa de 2021 a 2026, fator do § 2º e acréscimos do art. 125, conferidos no Planalto"],
  ["Itens e resultados do PNCP no pipeline", "Concluído: coleta sob demanda dos processos da silver por objeto (lumen coletar pncp_itens)"],
  ["Regra A-05: preço comparado com o mercado de fora do governo (antecipada da Fase 2)", "Em modo silencioso (ADR-027): combustível contra a série da ANP; informática contra o varejo pela API oficial, a validar; limiares não calibrados"],
  ["Critério de saída (três exercícios e relatório de cobertura)", "Não iniciado. A hospedagem está decidida (ADR-026); faltam o projeto no Supabase e levar a coleta de contratações para a nuvem"],
], { size: 17 }));
body.push(spacer(80));
body.push(callout("Antes da Fase 2", [
  "Revisar as ADRs 011 a 026. Resolver a divergência da regra B-01 com o art. 75, § 1º, da Lei 14.133 " +
  "(ADR-022): nenhuma regra da família B deve ser implementada antes dessa revisão metodológica e jurídica.",
  "Definir a fonte de \"quem autorizou o ato\": a API do PNCP não publica o agente (ADR-017), e o DOC-08 " +
  "exige essa informação para publicar indício.",
], "amber"));

body.push(h2("9.3 Trilha paralela: aba Eleições"));
body.push(p("A aba Eleições não estava no plano original. Entrou como trilha paralela porque não disputa o " +
  "caminho crítico: usa só a camada bronze, a identificação da coleta e o cadastro de entes, e não depende do " +
  "motor de detecção (ADR-024). O detalhamento está no DOC-12."));
body.push(table(["Item", "Situação"], [5200, 4400], [
  ["Coleta ao vivo do sistema de resultados do TSE", "Concluída e ensaiada em apuração simulada"],
  ["Eleições passadas pelos dados abertos (1994 a 2024, por município)", "Processamento concluído e testado nos três layouts"],
  ["Eleições de 1933 a 1990 (só por UF, como o TSE publica)", "Concluído: os 19 anos lidos e verificados com os dados reais completos (ADR-025)"],
  ["Carga completa num comando (lumen eleicoes preparar; preparar.cmd no Windows)", "Concluído; retomável. A carga numa máquina leva horas na primeira vez"],
  ["Carga, publicação e portal na nuvem, sem custo (ADR-026)", "Em produção desde 14/10/2026: feeds no Supabase Storage, carga diária e retomável no GitHub Actions, portal na Vercel"],
  ["Portal estático: mapa interativo, candidatos, panorama, evolução, busca, modo TV", "Concluído; mapa e cadastro de municípios vêm com o Lumen"],
  ["Domínio próprio para o portal e os feeds", "Pendente: o nome está decidido (Lumen, ADR-043); falta registrar o domínio, que tem custo"],
  ["Ensaio em infraestrutura real antes do 2º turno de 2026", "Feito com o 1º turno (16 e 17/10/2026), que achou a parada sem a marca de finalizada do TSE, já corrigida. O 2º turno está agendado no eleicoes-ao-vivo (adendo do ADR-026)"],
  ["Contexto eleitoral nas telas de contratação (família K)", "Fase 2 em diante"],
], { size: 17 }));

body.push(h2("9.4 Efeito no cronograma"));
body.push(p("Os entregáveis pendentes da Fase 1 (CGU, Receita, grupos de pares e painel) são os de menor " +
  "risco técnico: fontes com documentação estável ou arquivos completos. O risco de prazo estava no critério " +
  "de saída, que exige infraestrutura para a carga histórica. A ADR-026 resolve a hospedagem sem custo; o que " +
  "resta é trabalho técnico (levar a coleta de contratações para o GitHub Actions, como a das eleições) e " +
  "criar as contas. A decisão não técnica que sobra é o domínio: o nome ficou Lumen (ADR-043), e falta registrá-lo."));

body.push(h2("9.5 Hospedagem sem custo (ADR-026)"));
body.push(p("Nenhum banco gratuito comporta o Lumen inteiro: só as eleições por município passam de 500 MB em " +
  "linhas de banco, e a base de CNPJ da Receita tem dezenas de GB. Por isso cada tipo de dado vai para o " +
  "serviço gratuito que lhe serve. Limites verificados em 7 de outubro de 2026."));
body.push(table(["Serviço", "O que guarda ou executa", "Limite gratuito", "Sinal para a primeira despesa"], [1900, 3200, 2400, 2100], [
  ["Cloudflare R2", "Feeds das eleições (bucket público), estado das cargas (privado); depois, Parquet das contratações e a prova com trava de bucket", "10 GB-mês, 1 milhão de escritas e 10 milhões de leituras por mês; saída grátis", "Passar de 10 GB: US$ 0,015 por GB-mês"],
  ["Cloudflare Pages", "Portal estático (os feeds ficam no R2)", "Até 20.000 arquivos por site e 25 MiB por arquivo", "Domínio próprio (registro pago à parte)"],
  ["GitHub Actions", "Cargas agendadas e retomáveis", "2.000 minutos por mês em repositório privado; 6 horas por execução", "Cargas diárias longas de várias fontes"],
  ["Supabase Free", "Núcleo transacional: entes, fontes, indícios, evidências, revisão e contestação (migração 0001)", "500 MB de banco; pausa após 1 semana sem uso", "Passar de 500 MB: plano Pro"],
], { size: 16 }));
body.push(spacer(80));
body.push(p("O projeto do Supabase fica numa organização própria do Lumen, nunca na de uma empresa que o " +
  "mantenedor atende. Os dados volumosos e só de leitura ficam em Parquet no R2, consultados com DuckDB; entra " +
  "no banco o que uma revisão de indício precisa consultar com transação."));

L.buildDoc({
  codigo: "DOC-10",
  titulo: "Roadmap",
  subtitulo: "Fases, marcos, esforço, custos e critérios de replanejamento",
  meta: { versao: "2.1", data: "21 de outubro de 2026",
    situacao: "Plano aprovado, com a situação de cada fase em outubro de 2026 (seção 9)",
    verificado: "outubro de 2026" },
  body,
  outFile: "../docs/DOC-10_Roadmap.docx",
});
