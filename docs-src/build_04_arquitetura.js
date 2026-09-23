const L = require("./lib");
const { h1, h2, h3, p, bullet, numbered, table, callout, code, figure, pageBreak, spacer } = L;

const body = [];

function adr({ num, titulo, contexto, decisao, alternativas, consequencias }) {
  const out = [];
  out.push(h3(`ADR-${num} — ${titulo}`));
  out.push(table(null, [1800, 7800], [
    ["Contexto", contexto],
    ["Decisão", decisao],
    ["Alternativas", alternativas],
    ["Consequências", consequencias],
  ], { boldFirstCol: true }));
  out.push(spacer(140));
  return out;
}

body.push(h1("1. Direcionadores arquiteturais"));
body.push(p("A arquitetura do Lumen responde a cinco forças que, juntas, eliminam a maior parte das " +
  "soluções óbvias. Entendê-las é pré-requisito para avaliar qualquer decisão registrada neste documento."));
body.push(table(["Direcionador", "Consequência arquitetural"], [3200, 6400], [
  ["A prova importa mais que o dado",
    "O artefato bruto é a fonte de verdade e nunca é sobrescrito; tudo mais é derivado e descartável"],
  ["Heterogeneidade extrema das fontes",
    "A ingestão é isolada por portas e adaptadores; o núcleo nunca conhece o formato de origem"],
  ["Escala nacional com equipe mínima",
    "Conectores declarativos e integração das bases federais obrigatórias antes da cauda longa"],
  ["Volume analítico alto, escrita pontual",
    "Camada analítica colunar separada do banco transacional de domínio"],
  ["Risco jurídico na publicação",
    "Restrição de linguagem imposta no modelo de domínio e verificada automaticamente na integração contínua"],
]));

body.push(h1("2. Visão de contexto e containers"));
body.push(...figure("02_c4_containers.png", "Figura 1. Visão de containers: ingestão, armazenamento, processamento e entrega.", 620));

body.push(h2("2.1 Responsabilidade de cada container"));
body.push(table(["Container", "Responsabilidade", "Tecnologia"], [2300, 4700, 2600], [
  ["Orquestrador", "Agendar, retentar, versionar e observar execuções", "Dagster"],
  ["Trabalhadores de coleta", "Executar conectores e preservar artefatos brutos", "Python"],
  ["Registro de fontes", "Guardar a especificação declarativa de cada fonte", "YAML versionado em Git"],
  ["Armazenamento de objetos", "Camada bronze imutável com hash e carimbo de tempo", "S3 ou MinIO"],
  ["Lakehouse analítico", "Camadas silver e gold em formato colunar particionado", "Parquet + DuckDB"],
  ["Banco de domínio", "Entidades, indícios, contestações e trilha de auditoria", "PostgreSQL"],
  ["Índice de busca", "Busca textual em objetos de contratação e editais", "OpenSearch"],
  ["Normalizador", "Converter qualquer fonte ao esquema canônico", "Python"],
  ["Enriquecedor", "Societário, catálogo de itens, grupo de pares", "Python"],
  ["Motor de detecção", "Executar regras versionadas e gerar indícios", "Python + SQL analítico"],
  ["Avaliador de conformidade", "Medir cumprimento das obrigações legais de publicação", "Python"],
  ["API pública", "Servir dados e indícios com contrato estável", "Node.js + TypeScript"],
  ["Portal web", "Interface pública de consulta e visualização", "Next.js"],
]));

body.push(pageBreak());
body.push(h1("3. Estilo arquitetural"));

body.push(h2("3.1 Portas e adaptadores na ingestão"));
body.push(p("A ingestão é o ponto de maior variabilidade do sistema: cada uma das milhares de fontes " +
  "possui formato, protocolo e qualidade próprios. Para impedir que essa variabilidade contamine o " +
  "restante, toda fonte é acessada por meio de uma única porta, e cada família de fonte é um adaptador " +
  "que a implementa. O núcleo de domínio não sabe se um contrato veio de uma API REST, de uma planilha " +
  "ou de um PDF digitalizado."));
body.push(...figure("04_conectores.png", "Figura 2. Porta FonteDados e seus adaptadores, com o alcance de cobertura de cada um.", 620));

body.push(p("O contrato da porta é deliberadamente pequeno. Quatro operações bastam para todos os casos:"));
body.push(code([
  "class FonteDados(Protocol):",
  "    \"\"\"Porta unica de acesso a qualquer fonte de dado publico.\"\"\"",
  "",
  "    def descrever_capacidades(self) -> CapacidadesFonte:",
  "        \"\"\"Que objetos essa fonte fornece, com que granularidade",
  "        e periodicidade. Consultado pelo orquestrador para montar o plano.\"\"\"",
  "",
  "    def listar(self, janela: Janela) -> Iterator[ReferenciaArtefato]:",
  "        \"\"\"Enumera o que existe na janela, sem baixar conteudo.",
  "        Permite planejar volume antes de consumir cota da fonte.\"\"\"",
  "",
  "    def baixar(self, ref: ReferenciaArtefato) -> ArtefatoBruto:",
  "        \"\"\"Obtem o conteudo exatamente como publicado.",
  "        Retorna bytes, midia, cabecalhos e URL efetiva apos redirecionamentos.\"\"\"",
  "",
  "    def reportar_conformidade(self) -> RelatorioConformidade:",
  "        \"\"\"O que a fonte deveria publicar e nao publica.",
  "        E por aqui que a ausencia de dado vira achado, e nao erro.\"\"\"",
]));
body.push(callout("Por que reportar_conformidade fica na porta, e não fora dela", [
  "Quem sabe distinguir uma indisponibilidade temporária de uma ausência persistente de publicação é o " +
  "adaptador, porque só ele conhece o comportamento normal daquela fonte. Colocar essa responsabilidade " +
  "no núcleo obrigaria o núcleo a conhecer particularidades de cada portal, que é exatamente o que a " +
  "porta existe para evitar.",
], "blue"));

body.push(h2("3.2 Camadas de dados no padrão medallion"));
body.push(p("Os dados percorrem três camadas com propósitos distintos e garantias distintas. A separação " +
  "resolve o conflito entre preservar a prova e ter um modelo consultável e limpo."));
body.push(...figure("03_pipeline_medallion.png", "Figura 3. Camadas bronze, silver e gold, e os dois caminhos de volta que sustentam a auditabilidade.", 620));
body.push(table(["Camada", "Garantia", "O que pode ser feito"], [1500, 3800, 4300], [
  ["Bronze", "Imutável, nunca alterada nem apagada",
    "Somente escrita por coleta e leitura por reprocessamento; é a prova jurídica"],
  ["Silver", "Reconstruível integralmente a partir do bronze",
    "Pode ser apagada e regerada a qualquer momento sem perda de informação"],
  ["Gold", "Derivada e descartável",
    "Recalculada a cada mudança de regra, parâmetro ou linha de base"],
]));
body.push(p("A consequência prática mais importante: mudar uma regra de detecção nunca exige nova coleta. " +
  "Recalcula-se a camada gold sobre a silver existente. E corrigir um erro de normalização não exige " +
  "pedir nada de novo às fontes, porque o bronze permanece intacto. Em um projeto que depende de " +
  "milhares de servidores públicos de terceiros, essa propriedade vale mais do que qualquer otimização."));

body.push(pageBreak());
body.push(h1("4. Decisões arquiteturais registradas"));
body.push(p("Cada decisão relevante fica registrada com contexto, alternativas consideradas e " +
  "consequências aceitas. Decisões podem ser substituídas por outras posteriores, mas nunca apagadas."));

body.push(...adr({
  num: "001", titulo: "Usar PNCP e SICONFI como espinha dorsal, antes de qualquer raspagem municipal",
  contexto: "Cobrir 5.570 municípios por raspagem individual é inviável para uma equipe pequena e produziria milhares de integrações frágeis.",
  decisao: "Integrar primeiro as bases federais de envio obrigatório que já concentram dados de praticamente todos os entes, e só então tratar a cauda longa.",
  alternativas: "Começar pelos portais municipais; começar por um estado piloto; comprar base de terceiro.",
  consequencias: "Cobertura nacional já na fase 1, com poucas integrações. Em contrapartida, o sistema herda as lacunas das bases federais, o que é tratado pelo módulo de conformidade como achado e não como falha.",
}));

body.push(...adr({
  num: "002", titulo: "Camada bronze imutável como fonte de verdade",
  contexto: "Um indício só se sustenta se a evidência que o originou puder ser exibida exatamente como estava publicada na data da coleta. Portais reescrevem e removem páginas com frequência.",
  decisao: "Todo artefato é armazenado sem transformação, com hash SHA-256, URL efetiva, carimbo de tempo e cabeçalhos. Nova coleta gera nova versão; nada é sobrescrito.",
  alternativas: "Guardar apenas o dado normalizado; guardar apenas a URL e recoletar quando necessário.",
  consequencias: "Custo de armazenamento maior e crescente. Em troca, o projeto sobrevive à remoção de conteúdo na origem e a qualquer contestação sobre o que estava publicado.",
}));

body.push(...adr({
  num: "003", titulo: "Python na ingestão e detecção, TypeScript na API e no portal",
  contexto: "O ecossistema de coleta, extração de documentos e análise estatística é dominado por Python. A equipe já domina Node com arquitetura limpa para construção de API.",
  decisao: "Separar por responsabilidade: Python do conector até o indício; TypeScript do indício até o usuário. O contato entre os dois mundos é o banco de domínio e o lakehouse, nunca chamadas diretas.",
  alternativas: "Tudo em Python; tudo em TypeScript.",
  consequencias: "Duas cadeias de ferramentas para manter. Em troca, cada camada usa o ecossistema onde é mais produtiva, e a fronteira entre elas é um contrato de dados explícito e testável.",
}));

body.push(...adr({
  num: "004", titulo: "Conectores declarativos em vez de código por fonte",
  contexto: "Escrever e manter uma classe por município produziria milhares de arquivos praticamente idênticos e impossíveis de manter.",
  decisao: "Uma especificação declarativa por fonte, interpretada por um motor genérico. Código novo só para fontes genuinamente exóticas.",
  alternativas: "Uma classe por fonte; um único raspador genérico sem configuração.",
  consequencias: "Cadastrar fonte deixa de ser tarefa de programador e passa a ser tarefa de analista. O motor genérico fica mais complexo e precisa de cobertura de teste alta.",
}));

body.push(...adr({
  num: "005", titulo: "PostgreSQL para domínio e formato colunar para análise",
  contexto: "O domínio tem escritas transacionais e relacionamentos ricos; a análise varre bilhões de linhas históricas. Um único banco atenderia mal aos dois perfis.",
  decisao: "PostgreSQL para entidades, indícios, contestações e auditoria. Parquet particionado consultado por motor colunar para as camadas silver e gold.",
  alternativas: "Somente PostgreSQL; somente lakehouse; data warehouse gerenciado.",
  consequencias: "É preciso manter consistência entre os dois mundos. Em troca, consulta analítica não degrada a operação, e o custo de armazenamento analítico cai por ordens de grandeza.",
}));

body.push(...adr({
  num: "006", titulo: "Regras explicáveis em vez de aprendizado de máquina na versão 1.0",
  contexto: "Um indício precisa ser explicado em linguagem simples a um cidadão e reproduzido por um terceiro. Um modelo estatístico opaco não satisfaz nenhuma das duas exigências e amplia o risco jurídico.",
  decisao: "A versão 1.0 usa apenas regras determinísticas e estatística clássica, com parâmetros explícitos e versionados.",
  alternativas: "Detecção de anomalia por aprendizado não supervisionado desde o início.",
  consequencias: "Menor capacidade de descobrir padrões não antecipados. Em troca, cada indício é explicável, auditável e defensável. Métodos mais sofisticados ficam para versões futuras, e somente como priorização interna da fila, nunca como base de publicação.",
}));

body.push(...adr({
  num: "007", titulo: "Vocabulário controlado imposto por ferramenta, não por disciplina",
  contexto: "A proibição de imputar ilícito é a restrição mais crítica do projeto. Depender de revisão humana para garanti-la é frágil: basta um texto de erro, um rótulo ou um comentário escaparem.",
  decisao: "Uma lista de termos proibidos é verificada automaticamente em todo texto destinado ao público, e a verificação roda na integração contínua quebrando o build quando violada.",
  alternativas: "Diretriz documentada; revisão editorial manual.",
  consequencias: "Algum atrito no desenvolvimento e necessidade de manter a lista. Em troca, a garantia deixa de depender de memória individual e passa a ser propriedade verificável do sistema.",
}));

body.push(...adr({
  num: "008", titulo: "Revisão humana obrigatória acima do limiar de severidade",
  contexto: "Publicação automática de indício sobre pessoa jurídica identificável concentra o maior risco do projeto.",
  decisao: "Nenhum indício de severidade alta é publicado sem aprovação humana registrada, com autor e justificativa em trilha somente-anexação.",
  alternativas: "Publicação automática com limiar alto; revisão por amostragem.",
  consequencias: "Cria dependência de capacidade humana e limita o volume publicável. Essa limitação é aceita deliberadamente: o gargalo protege o projeto.",
}));

body.push(...adr({
  num: "009", titulo: "Dagster como orquestrador, com os dados como cidadãos de primeira classe",
  contexto: "O pipeline tem milhares de execuções parciais, dependências entre fontes e necessidade de reprocessar recortes específicos sem refazer tudo.",
  decisao: "Adotar orquestrador centrado em ativos de dados, e não em tarefas, o que torna o reprocesso seletivo e a linhagem propriedades nativas.",
  alternativas: "Airflow; Prefect; agendamento por cron com scripts.",
  consequencias: "Curva de aprendizado inicial maior que a de um agendador simples. Em troca, linhagem, materialização parcial e reprocesso seletivo vêm prontos, que são exatamente as operações mais frequentes deste projeto.",
}));

body.push(...adr({
  num: "010", titulo: "Monorepo com pacotes separados",
  contexto: "Equipe pequena, forte acoplamento conceitual entre o esquema canônico, as regras e a API que os expõe.",
  decisao: "Um único repositório com pacotes independentes e versionamento conjunto do esquema canônico.",
  alternativas: "Repositórios separados por serviço.",
  consequencias: "Mudanças no esquema canônico são atômicas e não geram dessincronização entre serviços. O repositório cresce e exige boa configuração de integração contínua seletiva por caminho alterado.",
}));

body.push(pageBreak());
body.push(h1("5. Estrutura do repositório"));
body.push(code([
  "lumen/",
  "├── packages/",
  "│   ├── canonico/              # esquema canonico: unica fonte de verdade do modelo",
  "│   │   ├── schemas/           # definicoes versionadas (contrato entre Python e TS)",
  "│   │   └── migrations/",
  "│   ├── ingestao/              # Python - portas e adaptadores de coleta",
  "│   │   ├── portas/            # protocolo FonteDados e tipos de dominio",
  "│   │   ├── adaptadores/",
  "│   │   │   ├── api/           # pncp.py, siconfi.py, cgu.py, rfb.py, tse.py",
  "│   │   │   ├── plataforma/    # familias de portal municipal",
  "│   │   │   ├── declarativo/   # motor que interpreta as specs YAML",
  "│   │   │   └── documento/     # extracao de PDF, XLSX, HTML, OCR",
  "│   │   └── fontes/            # specs YAML, uma por fonte cadastrada",
  "│   ├── normalizacao/          # Python - bruto para canonico + qualidade",
  "│   ├── enriquecimento/        # Python - societario, catalogo, grupo de pares",
  "│   ├── deteccao/              # Python - motor e catalogo de regras",
  "│   │   ├── motor/",
  "│   │   ├── regras/            # uma regra por arquivo, versionada",
  "│   │   └── calibracao/        # simulacao sobre janela historica",
  "│   ├── conformidade/          # Python - indice de transparencia",
  "│   ├── api/                   # TypeScript - API publica (arquitetura limpa)",
  "│   │   ├── dominio/",
  "│   │   ├── aplicacao/",
  "│   │   ├── infra/",
  "│   │   └── http/",
  "│   └── portal/                # Next.js - interface publica",
  "├── orquestracao/              # definicoes Dagster: ativos, jobs, agendas",
  "├── infra/                     # Terraform e Docker Compose",
  "├── ferramentas/",
  "│   └── lint-vocabulario/      # verificador de vocabulario controlado (ADR-007)",
  "├── docs/                      # DOC-01 a DOC-10 e ADRs",
  "└── testes/",
  "    ├── fixtures/              # amostras reais de cada fonte, versionadas",
  "    ├── contrato/              # testes de contrato por fonte externa",
  "    └── regras/                # casos sinteticos por regra de deteccao",
]));

body.push(h1("6. Volumetria e escalabilidade"));
body.push(p("As estimativas abaixo orientam o dimensionamento inicial. São ordens de grandeza, não " +
  "previsões precisas, e devem ser revistas ao final da fase 1 com números reais de coleta."));
body.push(table(["Dimensão", "Estimativa", "Implicação"], [2600, 2600, 4400], [
  ["Entes monitorados", "~6.000", "Cabe em memória; não é o fator de escala"],
  ["Contratações por ano", "Ordem de milhões", "Volume tratável em formato colunar particionado por ano e UF"],
  ["Itens contratados por ano", "Ordem de dezenas de milhões", "Principal tabela analítica; exige particionamento e compressão"],
  ["Empenhos por ano", "Ordem de dezenas de milhões", "Particionar por exercício e esfera"],
  ["Artefatos brutos por ano", "Ordem de milhões de objetos", "Armazenamento de objetos com política de classe de acesso por idade"],
  ["Histórico alvo", "10 anos", "Camada analítica projetada para a casa de bilhões de linhas"],
]));
body.push(h3("Estratégia de crescimento"));
body.push(bullet("Particionamento por exercício e unidade federativa em todas as tabelas analíticas grandes, " +
  "de modo que consultas por ente ou por ano leiam uma fração mínima do total."));
body.push(bullet("Compressão colunar com ordenação por ente e data, o que melhora simultaneamente o custo " +
  "de armazenamento e o desempenho dos filtros mais frequentes."));
body.push(bullet("Processamento sob demanda em vez de cluster permanente: o pipeline sobe capacidade para " +
  "o ciclo e a libera ao fim, o que se ajusta ao perfil de carga concentrada e ao orçamento restrito."));
body.push(bullet("Se o motor colunar embarcado deixar de atender ao crescimento do histórico, a substituição " +
  "por um banco colunar distribuído não afeta as camadas acima, porque o formato de armazenamento é aberto."));

body.push(pageBreak());
body.push(h1("7. Segurança"));
body.push(table(["Domínio", "Controle"], [2400, 7200], [
  ["Autenticação administrativa", "Segundo fator obrigatório, sessão com expiração curta e registro de tentativas malsucedidas"],
  ["Autorização", "Perfis separados de revisor e administrador; permissão de calibração distinta da de revisão"],
  ["Segredos", "Cofre de segredos; nenhuma credencial em repositório, imagem ou variável de build"],
  ["Transporte", "TLS 1.2 ou superior em todo tráfego externo"],
  ["Repouso", "Cifragem no armazenamento de objetos e nos backups"],
  ["Trilha de auditoria", "Somente-anexação, sem permissão de alteração ou exclusão pela aplicação"],
  ["Superfície pública", "API com limite de taxa por chave e por endereço; portal sem escrita anônima exceto contestação"],
  ["Dependências", "Verificação automática de vulnerabilidade e fixação de versões"],
  ["Integridade da prova", "Hash registrado no momento da coleta e reconferido a cada leitura do artefato"],
]));

body.push(h1("8. Observabilidade"));
body.push(p("O sistema é observado em três níveis, porque falhas silenciosas de coleta são o modo de " +
  "falha mais perigoso: o pipeline continua verde enquanto a cobertura real despenca."));
body.push(table(["Nível", "O que é medido", "Alarme"], [2000, 4400, 3200], [
  ["Infraestrutura", "CPU, memória, fila, latência de armazenamento", "Limiares padrão"],
  ["Pipeline", "Execuções por fonte, taxa de falha, atraso em relação à janela, volume coletado", "Queda de volume acima de desvio esperado para a fonte"],
  ["Produto", "Cobertura por ente, indícios por regra, taxa de descarte na revisão, tempo de contestação", "Cobertura em queda ou taxa de descarte de uma regra acima do limite"],
]));
body.push(callout("Alarme mais importante do sistema", [
  "A métrica que mais merece atenção não é erro, é ausência: uma fonte que passa a retornar sucesso com " +
  "zero registros. Tecnicamente tudo funciona, e a cobertura desaparece em silêncio. Por isso o alarme " +
  "de variação de volume por fonte é tratado como crítico, no mesmo nível de uma falha de coleta.",
], "amber"));

L.buildDoc({
  codigo: "DOC-04",
  titulo: "Arquitetura",
  subtitulo: "Estilo, containers, decisões registradas e estratégia de escala",
  body,
  outFile: "../docs/DOC-04_Arquitetura.docx",
});
