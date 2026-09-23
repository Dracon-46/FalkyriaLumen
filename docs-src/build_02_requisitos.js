const L = require("./lib");
const { h1, h2, h3, p, bullet, numbered, table, callout, code, figure, pageBreak, spacer } = L;

const body = [];

body.push(h1("1. Como ler este documento"));
body.push(p("Cada requisito tem um código único e permanente. Códigos não são reaproveitados: se um " +
  "requisito for removido, seu código é aposentado. O prefixo indica o módulo, o que permite " +
  "rastrear um requisito até o caso de uso (DOC-03), o componente de arquitetura (DOC-04) e o teste " +
  "que o cobre (DOC-09)."));
body.push(table(["Prefixo", "Módulo", "Responsabilidade"], [1500, 2600, 5500], [
  ["RF-CO", "Coleta", "Obter dados brutos das fontes e preservá-los como prova"],
  ["RF-NO", "Normalização", "Converter qualquer fonte para o esquema canônico"],
  ["RF-EN", "Enriquecimento", "Agregar contexto: societário, catálogo, grupo de pares"],
  ["RF-DE", "Detecção", "Executar regras e produzir indícios com evidência"],
  ["RF-CF", "Conformidade", "Medir cumprimento das obrigações de transparência"],
  ["RF-PU", "Publicação", "Expor dados e indícios ao público com linguagem controlada"],
  ["RF-DR", "Direito de resposta", "Receber, tratar e publicar contestações"],
  ["RF-AD", "Administração", "Operar o sistema: fontes, regras, revisão, auditoria"],
  ["RNF", "Não-funcional", "Qualidades transversais do sistema"],
]));
body.push(p("A coluna Prioridade usa MoSCoW: M obrigatório para a versão 1.0, S importante, C desejável, " +
  "W adiado para versão futura."));

body.push(pageBreak());
body.push(h1("2. Requisitos funcionais"));

body.push(h2("2.1 Módulo de Coleta"));
body.push(table(["Cód.", "Requisito", "Prio."], [1100, 7600, 900], [
  ["RF-CO-01", "O sistema deve coletar contratações, contratos, atas e planos de contratação do PNCP por data de publicação e por data de atualização global, suportando coleta incremental.", "M"],
  ["RF-CO-02", "O sistema deve coletar RREO, RGF e DCA do SICONFI para todos os entes e exercícios disponíveis.", "M"],
  ["RF-CO-03", "O sistema deve coletar despesas, convênios, emendas parlamentares e cadastros de sanção do Portal da Transparência da CGU.", "M"],
  ["RF-CO-04", "O sistema deve ingerir a base pública de CNPJ da Receita Federal, incluindo quadro societário, CNAE e capital social.", "M"],
  ["RF-CO-05", "Toda coleta deve armazenar o artefato bruto exatamente como recebido, sem qualquer transformação.", "M"],
  ["RF-CO-06", "Todo artefato bruto deve ser gravado com URL de origem, hash SHA-256, carimbo de tempo e cabeçalhos de resposta.", "M"],
  ["RF-CO-07", "Artefatos brutos devem ser imutáveis. Nova coleta da mesma URL gera nova versão, nunca sobrescrita.", "M"],
  ["RF-CO-08", "O sistema deve respeitar limites de taxa configuráveis por fonte, com valor padrão conservador.", "M"],
  ["RF-CO-09", "O sistema deve identificar-se em todas as requisições com User-Agent próprio contendo nome do projeto e canal de contato.", "M"],
  ["RF-CO-10", "O sistema deve suportar conectores declarativos, definidos em arquivo de especificação, sem necessidade de novo código.", "M"],
  ["RF-CO-11", "O sistema deve extrair dados estruturados de PDF, incluindo PDF baseado em imagem, por meio de OCR.", "S"],
  ["RF-CO-12", "O sistema deve extrair dados de planilhas XLSX, XLS, CSV e de tabelas em HTML.", "M"],
  ["RF-CO-13", "O sistema deve permitir upload manual supervisionado de documentos obtidos por pedido de acesso à informação.", "S"],
  ["RF-CO-14", "Falha de coleta deve ser registrada com causa classificada, distinguindo indisponibilidade temporária de ausência de publicação.", "M"],
  ["RF-CO-15", "O sistema deve retentar coletas falhas com espera exponencial e limite máximo de tentativas por janela.", "M"],
  ["RF-CO-16", "O sistema não deve tentar contornar CAPTCHA, autenticação ou qualquer controle técnico de acesso.", "M"],
  ["RF-CO-17", "O sistema deve detectar mudança de esquema na fonte e alarmar sem interromper a coleta das demais fontes.", "S"],
  ["RF-CO-18", "O sistema deve coletar dados de doações e candidaturas do repositório de dados abertos do TSE.", "C"],
]));

body.push(h2("2.2 Módulo de Normalização"));
body.push(table(["Cód.", "Requisito", "Prio."], [1100, 7600, 900], [
  ["RF-NO-01", "O sistema deve converter todo dado coletado para o esquema canônico definido no DOC-05.", "M"],
  ["RF-NO-02", "Cada registro normalizado deve manter referência ao artefato bruto que o originou.", "M"],
  ["RF-NO-03", "O sistema deve resolver identidade de fornecedores por CNPJ raiz e filial, tratando grafias divergentes de razão social.", "M"],
  ["RF-NO-04", "O sistema deve resolver identidade de entes por código IBGE e CNPJ, tratando variações de nome.", "M"],
  ["RF-NO-05", "O sistema deve deduplicar registros que apareçam em mais de uma fonte, preservando a proveniência de cada ocorrência.", "M"],
  ["RF-NO-06", "O sistema deve normalizar valores monetários, datas e unidades de medida para formatos únicos.", "M"],
  ["RF-NO-07", "O sistema deve classificar itens contratados segundo catálogo de referência, permitindo comparação entre entes.", "M"],
  ["RF-NO-08", "Registros que não passem nas regras de qualidade devem ser isolados em quarentena, com o motivo, sem bloquear o lote.", "M"],
  ["RF-NO-09", "O sistema deve aplicar classificação de sensibilidade a cada campo, conforme política do DOC-08.", "M"],
  ["RF-NO-10", "O sistema deve mascarar documentos de pessoa física antes de qualquer gravação em camada consultável.", "M"],
  ["RF-NO-11", "A normalização deve ser idempotente: reprocessar o mesmo artefato produz exatamente o mesmo resultado.", "M"],
  ["RF-NO-12", "O sistema deve permitir reprocessar todo o histórico a partir da camada bruta, sem recoletar das fontes.", "M"],
]));

body.push(h2("2.3 Módulo de Enriquecimento"));
body.push(table(["Cód.", "Requisito", "Prio."], [1100, 7600, 900], [
  ["RF-EN-01", "O sistema deve vincular cada fornecedor ao seu quadro societário, CNAE principal, capital social e data de abertura.", "M"],
  ["RF-EN-02", "O sistema deve calcular, para cada ente, um grupo de pares com base em porte populacional, região e receita corrente líquida.", "M"],
  ["RF-EN-03", "O sistema deve manter séries históricas por ente, fornecedor e item para servir de linha de base.", "M"],
  ["RF-EN-04", "O sistema deve calcular medianas de preço unitário por item, região e período.", "M"],
  ["RF-EN-05", "O sistema deve identificar sócios em comum entre fornecedores distintos.", "S"],
  ["RF-EN-06", "O sistema deve vincular fornecedores a sanções vigentes nos cadastros CEIS, CNEP e CEPIM.", "M"],
  ["RF-EN-07", "O sistema deve registrar o agente público signatário de cada ato autorizativo, quando publicado pela fonte.", "M"],
  ["RF-EN-08", "O sistema deve registrar o amparo legal invocado em cada contratação, quando publicado pela fonte.", "M"],
]));

body.push(h2("2.4 Módulo de Detecção"));
body.push(table(["Cód.", "Requisito", "Prio."], [1100, 7600, 900], [
  ["RF-DE-01", "O sistema deve executar o catálogo de regras definido no DOC-07 sobre a base normalizada.", "M"],
  ["RF-DE-02", "Cada regra deve ser versionada, e cada indício deve registrar a versão da regra que o produziu.", "M"],
  ["RF-DE-03", "Cada indício deve registrar os parâmetros usados e os valores de entrada que levaram ao disparo.", "M"],
  ["RF-DE-04", "Cada indício deve referenciar ao menos um documento fonte com hash verificável.", "M"],
  ["RF-DE-05", "O sistema deve detectar valores atípicos para cima, comparando preço unitário com a mediana do mesmo item.", "M"],
  ["RF-DE-06", "O sistema deve detectar fracionamento de despesa por agregação de contratações de mesmo objeto e fornecedor em janela temporal.", "M"],
  ["RF-DE-07", "O sistema deve detectar concentração anômala de valores imediatamente abaixo de limite legal de dispensa.", "M"],
  ["RF-DE-08", "O sistema deve detectar concentração de contratos em um único fornecedor por ente e categoria.", "M"],
  ["RF-DE-09", "O sistema deve detectar contratação de fornecedor com sanção vigente na data do ato.", "M"],
  ["RF-DE-10", "O sistema deve detectar fornecedor constituído em prazo muito curto antes da contratação.", "S"],
  ["RF-DE-11", "O sistema deve detectar incompatibilidade entre CNAE do fornecedor e objeto contratado.", "S"],
  ["RF-DE-12", "O sistema deve aplicar teste de aderência à Lei de Benford sobre conjuntos de valores por ente e período.", "S"],
  ["RF-DE-13", "O sistema deve detectar desvio relevante de gasto per capita em relação ao grupo de pares.", "M"],
  ["RF-DE-14", "O sistema deve detectar concentração atípica de empenhos no encerramento do exercício.", "S"],
  ["RF-DE-15", "O sistema deve detectar aditivos que elevem o valor do contrato acima dos percentuais previstos em lei.", "M"],
  ["RF-DE-16", "O sistema deve calcular um score composto e uma severidade para cada indício.", "M"],
  ["RF-DE-17", "Indícios com severidade acima do limiar configurado devem entrar obrigatoriamente em fila de revisão humana antes de qualquer publicação.", "M"],
  ["RF-DE-18", "O sistema deve permitir simular uma regra sobre dados históricos sem publicar resultado, para calibração.", "M"],
  ["RF-DE-19", "O sistema deve registrar indícios descartados com o motivo, para realimentar a calibração das regras.", "M"],
  ["RF-DE-20", "O sistema não deve produzir, em nenhum campo, texto que afirme ou sugira a ocorrência de ilícito.", "M"],
]));

body.push(h2("2.5 Módulo de Conformidade de Transparência"));
body.push(table(["Cód.", "Requisito", "Prio."], [1100, 7600, 900], [
  ["RF-CF-01", "O sistema deve verificar, por ente, a existência de publicação nas fontes federais obrigatórias.", "M"],
  ["RF-CF-02", "O sistema deve verificar a atualidade da publicação em relação à periodicidade exigida pela legislação.", "M"],
  ["RF-CF-03", "O sistema deve classificar o formato de publicação quanto à legibilidade por máquina.", "M"],
  ["RF-CF-04", "O sistema deve verificar a presença dos campos mínimos exigidos pela Lei de Acesso à Informação.", "S"],
  ["RF-CF-05", "O sistema deve calcular um índice de conformidade por ente, com metodologia pública e auditável.", "M"],
  ["RF-CF-06", "A ausência de dado obrigatório deve gerar indício de descumprimento, com citação do dispositivo legal.", "M"],
  ["RF-CF-07", "O índice deve distinguir explicitamente indisponibilidade técnica temporária de ausência persistente de publicação.", "M"],
  ["RF-CF-08", "O sistema deve manter histórico do índice, permitindo observar evolução ou deterioração ao longo do tempo.", "S"],
]));

body.push(h2("2.6 Módulo de Publicação"));
body.push(table(["Cód.", "Requisito", "Prio."], [1100, 7600, 900], [
  ["RF-PU-01", "O sistema deve oferecer painel por ente com panorama de contratações, despesas e conformidade.", "M"],
  ["RF-PU-02", "O sistema deve oferecer busca por ente, fornecedor, objeto, valor, período e modalidade.", "M"],
  ["RF-PU-03", "Toda página de indício deve exibir a regra aplicada, os parâmetros e o link para o documento fonte.", "M"],
  ["RF-PU-04", "Todo indício deve ser exibido com rótulo padronizado de atividade para análise.", "M"],
  ["RF-PU-05", "O sistema deve exibir comparação entre o ente e seu grupo de pares.", "M"],
  ["RF-PU-06", "O sistema deve permitir exportação em CSV e Parquet dos dados normalizados consultados.", "M"],
  ["RF-PU-07", "O sistema deve gerar dossiê em PDF com o indício, sua evidência e os documentos fonte.", "S"],
  ["RF-PU-08", "O sistema deve oferecer API pública documentada, com versionamento e limite de taxa.", "M"],
  ["RF-PU-09", "O sistema deve permitir que o usuário acompanhe um ente e receba alerta de novos indícios.", "C"],
  ["RF-PU-10", "Toda página pública deve exibir aviso metodológico e link para a metodologia completa.", "M"],
  ["RF-PU-11", "O sistema deve publicar erratas e remoções com o mesmo destaque da publicação original.", "M"],
  ["RF-PU-12", "O sistema deve exibir a data da última coleta bem-sucedida em cada visão de dados.", "M"],
]));

body.push(h2("2.7 Módulo de Direito de Resposta"));
body.push(table(["Cód.", "Requisito", "Prio."], [1100, 7600, 900], [
  ["RF-DR-01", "O sistema deve oferecer canal público para que ente ou fornecedor registre contestação a um indício.", "M"],
  ["RF-DR-02", "A contestação deve permitir anexar documentos comprobatórios.", "M"],
  ["RF-DR-03", "O indício contestado deve ser marcado publicamente como contestado em até 24 horas do registro.", "M"],
  ["RF-DR-04", "A contestação deve ser exibida junto ao indício original, de forma permanente.", "M"],
  ["RF-DR-05", "O sistema deve permitir reexecutar a regra considerando os documentos apresentados na contestação.", "M"],
  ["RF-DR-06", "Comprovado erro do sistema, o indício deve ser retificado ou removido e a correção publicada.", "M"],
  ["RF-DR-07", "O sistema deve registrar prazo e desfecho de cada contestação, com métricas públicas de atendimento.", "S"],
]));

body.push(h2("2.8 Módulo de Administração"));
body.push(table(["Cód.", "Requisito", "Prio."], [1100, 7600, 900], [
  ["RF-AD-01", "O sistema deve permitir cadastrar e editar fontes de dados por especificação declarativa.", "M"],
  ["RF-AD-02", "O sistema deve permitir ajustar parâmetros de uma regra e versioná-la automaticamente.", "M"],
  ["RF-AD-03", "O sistema deve oferecer fila de revisão priorizada por severidade e antiguidade.", "M"],
  ["RF-AD-04", "Toda ação de revisor deve ser registrada em trilha de auditoria imutável, com autor, data e justificativa.", "M"],
  ["RF-AD-05", "O sistema deve exibir painel operacional com saúde das coletas, atrasos e taxa de falha por fonte.", "M"],
  ["RF-AD-06", "O sistema deve permitir reprocessar um período ou uma fonte específica sob demanda.", "M"],
  ["RF-AD-07", "O acesso administrativo deve exigir autenticação com segundo fator.", "M"],
  ["RF-AD-08", "O sistema deve suportar perfis distintos de revisor e administrador, com permissões separadas.", "S"],
]));

body.push(pageBreak());
body.push(h1("3. Requisitos não-funcionais"));

body.push(h2("3.1 Desempenho e escala"));
body.push(table(["Cód.", "Requisito", "Meta"], [1100, 6100, 2400], [
  ["RNF-01", "Tempo de resposta da busca pública no percentil 95", "Até 2 segundos"],
  ["RNF-02", "Tempo de resposta da API pública no percentil 95", "Até 800 ms"],
  ["RNF-03", "Volume suportado na camada analítica sem redesenho", "10 bilhões de linhas"],
  ["RNF-04", "Janela de execução do ciclo completo de detecção", "Até 12 horas"],
  ["RNF-05", "Defasagem entre publicação na fonte e disponibilidade no Lumen", "Até 72 horas para fontes com API"],
  ["RNF-06", "Capacidade de reprocessamento integral do histórico", "Até 7 dias corridos"],
]));

body.push(h2("3.2 Confiabilidade e operação"));
body.push(table(["Cód.", "Requisito", "Meta"], [1100, 6100, 2400], [
  ["RNF-07", "Disponibilidade do portal público e da API", "99,0% mensal"],
  ["RNF-08", "Perda de artefato bruto já coletado", "Zero, com replicação"],
  ["RNF-09", "Falha em uma fonte não pode interromper as demais", "Isolamento por fonte"],
  ["RNF-10", "Recuperação da camada analítica a partir da camada bruta", "Sempre possível"],
  ["RNF-11", "Tempo para detectar falha sistemática de coleta", "Até 6 horas"],
]));

body.push(h2("3.3 Segurança"));
body.push(table(["Cód.", "Requisito"], [1100, 8500], [
  ["RNF-12", "Todo acesso administrativo deve usar autenticação com segundo fator e sessão com expiração."],
  ["RNF-13", "Credenciais de API de terceiros devem ser armazenadas em cofre de segredos, nunca no repositório."],
  ["RNF-14", "Todo tráfego externo deve usar TLS 1.2 ou superior."],
  ["RNF-15", "A trilha de auditoria deve ser somente-anexação, sem permissão de alteração ou exclusão pela aplicação."],
  ["RNF-16", "Backups devem ser cifrados em repouso e testados por restauração periódica."],
  ["RNF-17", "O sistema deve registrar e limitar tentativas de acesso administrativo malsucedidas."],
]));

body.push(h2("3.4 Privacidade e conformidade legal"));
body.push(table(["Cód.", "Requisito"], [1100, 8500], [
  ["RNF-18", "Todo campo do esquema canônico deve ter classificação de sensibilidade atribuída."],
  ["RNF-19", "Dados pessoais de cidadãos não agentes públicos não podem ser expostos em nível individual."],
  ["RNF-20", "Documentos de pessoa física devem ser mascarados em qualquer exibição ou exportação."],
  ["RNF-21", "Deve existir procedimento documentado de atendimento a solicitação de titular de dados."],
  ["RNF-22", "A base legal do tratamento deve estar documentada e vinculada a cada categoria de dado."],
]));

body.push(h2("3.5 Auditabilidade e reprodutibilidade"));
body.push(table(["Cód.", "Requisito"], [1100, 8500], [
  ["RNF-23", "Qualquer indício publicado deve ser reproduzível por terceiro a partir dos dados públicos e da especificação da regra."],
  ["RNF-24", "A metodologia de cada regra deve ser publicada em linguagem acessível junto ao portal."],
  ["RNF-25", "Toda transformação de dado deve registrar linhagem, permitindo rastrear do indício ao artefato bruto."],
  ["RNF-26", "Versões de regra e de esquema devem ser explicitamente registradas em cada execução."],
]));

body.push(h2("3.6 Manutenibilidade e custo"));
body.push(table(["Cód.", "Requisito"], [1100, 8500], [
  ["RNF-27", "Adicionar uma fonte que siga padrão já suportado não deve exigir alteração no núcleo do sistema."],
  ["RNF-28", "Cobertura de testes automatizados no núcleo de domínio e no motor de regras: mínimo de 80%."],
  ["RNF-29", "O custo mensal de infraestrutura na fase 1 deve permanecer compatível com operação de equipe reduzida."],
  ["RNF-30", "O sistema deve poder ser executado integralmente em ambiente local para desenvolvimento e teste."],
  ["RNF-31", "Nenhum componente proprietário sem alternativa aberta equivalente pode ser dependência crítica."],
]));

body.push(pageBreak());
body.push(h1("4. Matriz de rastreabilidade"));
body.push(p("A matriz vincula objetivos do produto (DOC-01) a requisitos e casos de uso (DOC-03). Ela é " +
  "mantida atualizada a cada mudança de escopo e serve de base para o planejamento de testes."));
body.push(table(["Objetivo", "Requisitos principais", "Casos de uso"], [1300, 5300, 3000], [
  ["OBJ-01", "RF-CO-01, RF-CO-05 a RF-CO-09, RF-NO-01", "UC-12"],
  ["OBJ-02", "RF-CO-02, RF-NO-01, RF-NO-04", "UC-12"],
  ["OBJ-03", "RF-NO-01 a RF-NO-12", "UC-12"],
  ["OBJ-04", "RF-DE-05 a RF-DE-15, RF-DE-16", "UC-03, UC-13"],
  ["OBJ-05", "RF-EN-07, RF-EN-08, RF-CO-01", "UC-01, UC-03"],
  ["OBJ-06", "RF-CF-01 a RF-CF-08", "UC-07"],
  ["OBJ-07", "RF-CO-05, RF-CO-06, RF-DE-04, RNF-23, RNF-25", "UC-03, UC-05"],
  ["OBJ-08", "RF-DR-01 a RF-DR-07", "UC-11"],
]));

body.push(h1("5. Critérios de aceitação da versão 1.0"));
body.push(p("A versão 1.0 só é considerada pronta quando todos os critérios abaixo forem verificados e " +
  "documentados. Nenhum critério é dispensável por pressão de prazo."));
body.push(numbered("Todos os requisitos de prioridade M estão implementados e cobertos por teste automatizado."));
body.push(numbered("Uma amostra aleatória de 100 indícios publicados foi revisada manualmente e a taxa de " +
  "falso positivo confirmado ficou abaixo do limite definido no DOC-07."));
body.push(numbered("Todo indício da amostra possui documento fonte recuperável e com hash conferido."));
body.push(numbered("O verificador de vocabulário controlado executa na integração contínua e nenhuma " +
  "violação está presente na base."));
body.push(numbered("O fluxo de direito de resposta foi testado ponta a ponta, incluindo publicação de errata."));
body.push(numbered("A metodologia de todas as regras ativas está publicada e acessível ao público."));
body.push(numbered("O plano de resposta a incidente de privacidade está documentado e um teste de mesa foi realizado."));
body.push(numbered("Existe procedimento de restauração testado para a camada bruta e para o banco de domínio."));

L.buildDoc({
  codigo: "DOC-02",
  titulo: "Requisitos",
  subtitulo: "Requisitos funcionais e não-funcionais, numerados e rastreáveis",
  body,
  outFile: "../docs/DOC-02_Requisitos.docx",
});
