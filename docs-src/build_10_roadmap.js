const L = require("./lib");
const { h1, h2, h3, p, bullet, numbered, table, callout, code, figure, pageBreak, spacer } = L;

const body = [];

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

body.push(pageBreak());
body.push(h1("7. Decisões que precisam ser tomadas antes de começar"));
body.push(p("Quatro definições não são técnicas e não podem ser adiadas indefinidamente, porque " +
  "condicionam escolhas das primeiras fases."));
body.push(table(["Decisão", "Quando", "Por que condiciona o desenvolvimento"], [2400, 1700, 5500], [
  ["Nome definitivo do projeto", "Antes da fase 0",
    "Lumen é nome de trabalho e precisa passar pela mesma verificação de disponibilidade de marca e domínio já feita para a marca da empresa"],
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

L.buildDoc({
  codigo: "DOC-10",
  titulo: "Roadmap",
  subtitulo: "Fases, marcos, esforço, custos e critérios de replanejamento",
  body,
  outFile: "../docs/DOC-10_Roadmap.docx",
});
