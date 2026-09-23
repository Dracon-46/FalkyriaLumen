const L = require("./lib");
const { h1, h2, h3, p, pRuns, bullet, numbered, bold, italic, plain,
  table, callout, code, figure, pageBreak, spacer } = L;

const body = [];

body.push(h1("1. Sumário executivo"));
body.push(p("O Lumen é um sistema que coleta, normaliza e analisa dados de contratações e despesas públicas " +
  "de todos os entes federativos brasileiros, com o objetivo de sinalizar atividades que merecem análise " +
  "por parte de órgãos de controle, imprensa e sociedade civil. O sistema não acusa, não julga e não " +
  "afirma a ocorrência de ilícito: ele identifica padrões estatísticos e processuais que se afastam do " +
  "esperado, apresenta a evidência primária que sustenta cada sinalização e identifica objetivamente " +
  "quem praticou o ato administrativo e com que fundamento legal, conforme publicado pelo próprio ente."));
body.push(p("A viabilidade do projeto em escala nacional apoia-se em uma constatação técnica central: " +
  "embora o Brasil tenha 5.570 municípios, 26 estados, o Distrito Federal e a União, com portais de " +
  "transparência extremamente heterogêneos, existem hoje duas bases federais obrigatórias que já " +
  "concentram dados de praticamente todos esses entes. O Portal Nacional de Contratações Públicas " +
  "(PNCP), criado pela Lei 14.133/2021, centraliza licitações, contratos, atas e o amparo legal de cada " +
  "contratação. O SICONFI, da Secretaria do Tesouro Nacional, concentra os relatórios contábeis e " +
  "fiscais de estados e municípios. Ambos expõem APIs públicas. Isso significa que a cobertura nacional " +
  "não exige escrever 5.570 raspadores: exige integrar corretamente um pequeno número de fontes " +
  "federais e, só depois, tratar a cauda longa."));
body.push(p("O prazo alvo é de doze meses até a versão pública, distribuídos em seis fases descritas no " +
  "documento DOC-10 Roadmap."));

body.push(callout("Princípio fundador do projeto", [
  "O Lumen publica indícios, nunca conclusões. Toda sinalização é rotulada como atividade para análise " +
  "e acompanhada da evidência primária, da regra aplicada e de seus parâmetros.",
  "A determinação de que houve desvio, fraude ou crime cabe exclusivamente aos órgãos de controle e ao " +
  "Poder Judiciário. Essa restrição não é apenas uma diretriz editorial: ela é imposta no código, no " +
  "modelo de domínio e no pipeline de publicação, conforme o DOC-08 e o DOC-09.",
], "red"));

body.push(h1("2. O problema"));
body.push(p("O Brasil publica um volume enorme de dados sobre gasto público, mas publicar não é o mesmo " +
  "que tornar fiscalizável. Três barreiras separam o dado publicado do controle social efetivo."));

body.push(h2("2.1 Fragmentação"));
body.push(p("Cada esfera e cada ente publica em seu próprio formato, com sua própria nomenclatura, em " +
  "sua própria periodicidade. Um mesmo item de compra pode aparecer como material de expediente em um " +
  "município e como suprimento administrativo em outro. Sem normalização, comparar preços entre entes " +
  "é impossível, e sem comparação não existe detecção de sobrepreço."));

body.push(h2("2.2 Escala"));
body.push(p("Existem mais de 6.000 unidades publicando informação orçamentária, considerando União, " +
  "estados, municípios, câmaras legislativas, autarquias, fundações, empresas públicas e consórcios. " +
  "Nenhum ser humano ou redação consegue auditar esse volume manualmente. A fiscalização hoje é " +
  "reativa: investiga-se o que alguém denunciou, não o que os dados apontam."));

body.push(h2("2.3 Assimetria de atenção"));
body.push(p("A atenção pública concentra-se em contratos de valor elevado, que são poucos e muito " +
  "visíveis. Entretanto, uma parcela relevante das irregularidades apuradas historicamente pelos " +
  "tribunais de contas envolve valores pequenos praticados de forma repetida, precisamente porque " +
  "operam abaixo do limiar de atenção. O caso clássico é o fracionamento de despesa: dividir uma " +
  "contratação maior em várias menores para manter cada uma abaixo do limite legal de dispensa de " +
  "licitação. Um sistema que só olhe para valores grandes é cego exatamente onde o padrão é mais comum."));
body.push(callout("Requisito derivado", [
  "O motor de detecção trata valores pequenos como cidadãos de primeira classe. A família de regras " +
  "de fracionamento e agregação temporal (família B do DOC-07) foi desenhada especificamente para " +
  "detectar padrões que só existem quando se olha o conjunto, e nunca o documento isolado.",
], "amber"));

body.push(h1("3. Objetivos"));
body.push(h2("3.1 Objetivos do produto"));
body.push(table(["Cód.", "Objetivo", "Como será medido"], [800, 4400, 4400], [
  ["OBJ-01", "Cobrir os dados de contratação de todos os entes que publicam no PNCP",
    "Percentual de entes com ao menos uma contratação coletada nos últimos 12 meses"],
  ["OBJ-02", "Cobrir os dados orçamentários e fiscais de estados e municípios via SICONFI",
    "Percentual de entes com RREO e DCA coletados por exercício"],
  ["OBJ-03", "Normalizar tudo em um esquema canônico único",
    "Percentual de registros que passam nas regras de qualidade sem intervenção manual"],
  ["OBJ-04", "Detectar padrões de valor atípico, tanto altos quanto pequenos e repetidos",
    "Precisão dos indícios revisados por amostragem trimestral"],
  ["OBJ-05", "Registrar quem autorizou cada ato e com que fundamento legal",
    "Percentual de contratações com agente e amparo legal preenchidos"],
  ["OBJ-06", "Medir e expor o cumprimento das obrigações de transparência",
    "Número de entes com índice de conformidade calculado e publicado"],
  ["OBJ-07", "Garantir rastreabilidade integral da evidência",
    "Percentual de indícios com documento fonte armazenado e hash verificável"],
  ["OBJ-08", "Garantir direito de resposta efetivo",
    "Tempo médio entre contestação registrada e marcação pública do indício"],
]));

body.push(h2("3.2 Não-objetivos"));
body.push(p("Delimitar o que o sistema não faz é tão importante quanto delimitar o que ele faz, " +
  "porque protege o projeto juridicamente e evita expansão descontrolada de escopo."));
body.push(bullet("O Lumen não afirma que houve desvio, fraude, superfaturamento ou crime, nem sugere " +
  "essas conclusões por meio de linguagem, iconografia ou rotulagem."));
body.push(bullet("O Lumen não substitui auditoria. Um indício é uma hipótese a ser verificada por quem " +
  "tem poder de requisitar documentos, ouvir agentes e aplicar sanção."));
body.push(bullet("O Lumen não produz ranking de políticos, não atribui pontuação a pessoas físicas e não " +
  "constrói perfis sobre agentes públicos além do registro objetivo dos atos que assinaram."));
body.push(bullet("O Lumen não coleta dados pessoais de cidadãos beneficiários de programas sociais para " +
  "fins de análise individual. Dados desse tipo, quando necessários, são tratados de forma agregada."));
body.push(bullet("O Lumen não burla controles técnicos de acesso. Não resolve CAPTCHA, não usa " +
  "credencial de terceiro e não acessa área restrita de nenhum portal."));
body.push(bullet("O Lumen não é, na primeira versão, um sistema de previsão. Ele descreve o que " +
  "aconteceu e o quanto isso destoa do padrão, sem prever comportamento futuro de agentes."));

body.push(pageBreak());
body.push(h1("4. Princípios inegociáveis"));
body.push(p("Os princípios a seguir têm precedência sobre qualquer requisito funcional. Em caso de " +
  "conflito entre um princípio e uma funcionalidade desejada, a funcionalidade é descartada ou " +
  "redesenhada."));

body.push(h3("P1. Evidência antes de afirmação"));
body.push(p("Nenhum indício pode ser publicado sem que exista, armazenado no sistema, o documento " +
  "primário que o sustenta, com URL de origem, hash SHA-256 e carimbo de tempo da coleta. Se a " +
  "evidência não pode ser mostrada, o indício não existe."));

body.push(h3("P2. Linguagem neutra obrigatória"));
body.push(p("Todo texto voltado ao público usa vocabulário controlado. Termos que imputam ilícito são " +
  "proibidos em qualquer campo exibível. Essa regra é verificada automaticamente na integração " +
  "contínua e quebra o build quando violada."));

body.push(h3("P3. Reprodutibilidade"));
body.push(p("Qualquer indício deve poder ser reproduzido por terceiros a partir dos dados públicos e da " +
  "especificação da regra. A regra, sua versão, seus parâmetros e os dados de entrada ficam registrados " +
  "junto ao indício."));

body.push(h3("P4. Simetria de correção"));
body.push(p("Correções e remoções recebem o mesmo destaque e o mesmo canal que a publicação original. " +
  "Um erro do sistema corrigido em silêncio é um erro cometido duas vezes."));

body.push(h3("P5. Ausência de dado é informação"));
body.push(p("Quando um ente não publica o que a lei obriga, isso não é tratado como falha de coleta, mas " +
  "registrado como indício de descumprimento de transparência, com a base legal correspondente. A " +
  "opacidade é um achado, não um obstáculo."));

body.push(h3("P6. Coleta responsável"));
body.push(p("O sistema se identifica em todas as requisições, respeita limites de taxa publicados, " +
  "prefere sempre a API oficial ao raspador e jamais degrada a disponibilidade de um serviço público " +
  "para terceiros."));

body.push(h1("5. Escopo"));
body.push(...figure("01_c4_contexto.png", "Figura 1. Diagrama de contexto: atores e fontes externas do Lumen."));

body.push(h2("5.1 Escopo por esfera e fase"));
body.push(p("A cobertura é construída em camadas, do mais estruturado para o menos estruturado. Essa " +
  "ordem não é arbitrária: as fontes federais obrigatórias entregam cobertura nacional desde a primeira " +
  "fase, o que permite começar a detectar padrões muito antes de o trabalho de cauda longa terminar."));
body.push(table(["Camada", "Alcance", "Natureza da fonte", "Fase"], [1800, 3200, 3000, 1600], [
  ["Federal obrigatória", "Todos os entes que cumprem a lei", "API estruturada (PNCP, SICONFI)", "Fase 1"],
  ["Federal complementar", "União e transferências a estados e municípios", "API (CGU, Compras.gov, RFB, TSE)", "Fase 1"],
  ["Estadual", "27 unidades federativas e seus tribunais de contas", "API, CSV ou HTML", "Fase 3"],
  ["Municipal por plataforma", "Centenas de municípios por conector", "Famílias de portal comerciais", "Fase 4"],
  ["Municipal cauda longa", "Municípios restantes", "PDF, XLS, HTML avulso, pedido LAI", "Fase 4"],
]));

body.push(h2("5.2 Objetos de análise no escopo"));
body.push(bullet("Processos de contratação: licitações, dispensas, inexigibilidades, com modalidade e amparo legal."));
body.push(bullet("Contratos, seus aditivos, prorrogações e reajustes."));
body.push(bullet("Itens contratados com quantidade, preço unitário e classificação de catálogo."));
body.push(bullet("Cadeia da despesa: empenho, liquidação e pagamento."));
body.push(bullet("Atas de registro de preço e planos anuais de contratação."));
body.push(bullet("Convênios, transferências voluntárias e emendas parlamentares."));
body.push(bullet("Atos autorizativos e os agentes públicos que os assinaram, no exercício da função."));
body.push(bullet("Fornecedores, seu quadro societário, CNAE, capital social e data de abertura."));
body.push(bullet("Sanções administrativas vigentes (CEIS, CNEP, CEPIM) e decisões de tribunais de contas."));
body.push(bullet("Indicadores de cumprimento das obrigações de transparência de cada ente."));

body.push(h2("5.3 Fora de escopo na versão 1.0"));
body.push(bullet("Folha de pagamento individualizada de servidores, exceto quando já publicada de forma " +
  "agregada e usada para indicadores do próprio ente."));
body.push(bullet("Dados de beneficiários de programas sociais em nível individual."));
body.push(bullet("Obras físicas com verificação em campo, imagens de satélite ou medição de execução."));
body.push(bullet("Análise de conteúdo de processos judiciais."));
body.push(bullet("Previsão de risco futuro por aprendizado de máquina supervisionado."));

body.push(pageBreak());
body.push(h1("6. Público e partes interessadas"));
body.push(table(["Parte interessada", "O que espera do sistema", "Como o sistema atende"], [2400, 3600, 3600], [
  ["Cidadão", "Entender como o dinheiro do seu município é gasto",
    "Painel por ente com linguagem simples e comparação com municípios semelhantes"],
  ["Jornalista de dados", "Encontrar pautas e sustentar a apuração",
    "Busca avançada, exportação e dossiê de evidências com documentos originais"],
  ["Órgão de controle", "Priorizar onde alocar capacidade de auditoria",
    "API, fila de indícios por severidade e exportação estruturada"],
  ["Pesquisador", "Base histórica normalizada e reprodutível",
    "Exportação em Parquet e CSV com dicionário de dados versionado"],
  ["Ente público analisado", "Corrigir informação incorreta a seu respeito",
    "Canal de contestação com prazo definido e resposta publicada junto ao indício"],
  ["Equipe do projeto", "Operar com previsibilidade e sem risco jurídico",
    "Vocabulário controlado, revisão humana obrigatória e trilha de auditoria"],
]));

body.push(h1("7. Premissas e restrições"));
body.push(h2("7.1 Premissas"));
body.push(numbered("Os dados tratados são públicos por força da Lei 12.527/2011 (Lei de Acesso à " +
  "Informação), da Lei Complementar 131/2009 e do art. 174 da Lei 14.133/2021, e sua reutilização é " +
  "amparada pelo Decreto 8.777/2016, que instituiu a Política de Dados Abertos do Executivo federal."));
body.push(numbered("As APIs federais citadas permanecerão disponíveis e gratuitas. Caso alguma seja " +
  "descontinuada, o modelo de conectores permite substituir a fonte sem alterar o núcleo do sistema."));
body.push(numbered("A qualidade do dado de origem é variável e frequentemente ruim. O sistema deve " +
  "tratar dado incompleto como situação normal de operação, não como exceção."));
body.push(numbered("O projeto será conduzido inicialmente por uma equipe muito pequena, o que torna a " +
  "automação e a padronização mais importantes do que a sofisticação de cada componente."));

body.push(h2("7.2 Restrições"));
body.push(table(["Tipo", "Restrição", "Implicação no desenho"], [1700, 3900, 4000], [
  ["Legal", "Vedado imputar ilícito a pessoa física ou jurídica",
    "Vocabulário controlado aplicado por lint e testes automatizados"],
  ["Legal", "LGPD aplica-se a dados pessoais mesmo em bases públicas",
    "Classificação de dados e minimização no estágio de normalização"],
  ["Técnica", "Limites de taxa das APIs oficiais",
    "Fila com controle de vazão por fonte e coleta incremental por data de atualização"],
  ["Técnica", "Volume na casa de bilhões de linhas ao longo dos anos",
    "Camada analítica colunar particionada, e não banco transacional único"],
  ["Operacional", "Equipe reduzida",
    "Conectores declarativos em vez de código por ente; revisão humana só no que é publicado"],
  ["Financeira", "Orçamento de infraestrutura limitado",
    "Armazenamento em objetos e processamento sob demanda em vez de cluster permanente"],
]));

body.push(h1("8. Riscos do projeto"));
body.push(table(["Cód.", "Risco", "Prob.", "Impacto", "Mitigação"], [700, 3200, 900, 900, 3900], [
  ["R-01", "Ação judicial por parte de ente ou fornecedor citado", "Média", "Alto",
    "Vocabulário controlado, revisão humana, evidência primária armazenada e direito de resposta imediato"],
  ["R-02", "Falso positivo publicado com repercussão", "Média", "Alto",
    "Limiar de publicação alto, revisão obrigatória acima de severidade média e errata com mesmo destaque"],
  ["R-03", "Fonte oficial muda formato sem aviso", "Alta", "Médio",
    "Testes de contrato por fonte, alarme de variação de esquema e camada bronze que permite reprocessar"],
  ["R-04", "Bloqueio de IP por coleta agressiva", "Média", "Médio",
    "Vazão conservadora, identificação no User-Agent e preferência por API oficial"],
  ["R-05", "Cauda longa municipal consumir todo o tempo do projeto", "Alta", "Médio",
    "Cobertura nacional entregue na fase 1 via PNCP e SICONFI; cauda longa tratada como incremento"],
  ["R-06", "Custo de armazenamento crescer acima do previsto", "Média", "Médio",
    "Compressão colunar, particionamento por ano e política de ciclo de vida no armazenamento de objetos"],
  ["R-07", "Exposição indevida de dado pessoal", "Baixa", "Alto",
    "Classificação de dados, mascaramento de documentos e revisão de privacidade antes de cada publicação nova"],
  ["R-08", "Projeto ser percebido como perseguição política", "Média", "Alto",
    "Critérios idênticos para todos os entes, metodologia pública e ausência de recorte partidário"],
]));

body.push(pageBreak());
body.push(h1("9. Glossário"));
body.push(table(["Termo", "Definição no contexto do projeto"], [2600, 7000], [
  ["Amparo legal", "Dispositivo da lei invocado para justificar a forma de contratação; no PNCP vem como campo estruturado"],
  ["Ato autorizativo", "Documento pelo qual um agente público autoriza uma contratação ou despesa"],
  ["CATMAT / CATSER", "Catálogos federais de materiais e serviços, usados para normalizar itens entre entes"],
  ["CEIS / CNEP / CEPIM", "Cadastros federais de empresas e entidades sancionadas ou impedidas"],
  ["Conector", "Componente que sabe obter dados de uma fonte específica e entregar no formato canônico"],
  ["DCA", "Declaração de Contas Anuais enviada ao SICONFI"],
  ["Dispensa de licitação", "Contratação direta permitida por lei em hipóteses específicas, inclusive por valor"],
  ["Ente", "Unidade da federação ou órgão público analisado"],
  ["Esquema canônico", "Modelo de dados único para o qual toda fonte é convertida"],
  ["Fracionamento", "Divisão de uma despesa em parcelas menores, de modo que cada uma fique abaixo de um limite legal"],
  ["Grupo de pares", "Conjunto de entes comparáveis por porte, região e capacidade fiscal"],
  ["Indício", "Sinalização produzida por uma regra, sempre acompanhada de evidência e nunca de conclusão"],
  ["PNCP", "Portal Nacional de Contratações Públicas, criado pela Lei 14.133/2021"],
  ["RREO / RGF", "Relatórios fiscais periódicos obrigatórios enviados ao SICONFI"],
  ["SICONFI", "Sistema de Informações Contábeis e Fiscais do Setor Público Brasileiro"],
  ["Trilha de evidência", "Conjunto regra, parâmetros, dados de entrada e documentos que sustentam um indício"],
]));

body.push(h1("10. Documentos relacionados"));
body.push(table(["Código", "Documento", "Conteúdo"], [1400, 3400, 4800], [
  ["DOC-01", "Visão e Escopo", "Este documento"],
  ["DOC-02", "Requisitos", "Requisitos funcionais e não-funcionais numerados e rastreáveis"],
  ["DOC-03", "Casos de Uso", "Atores e fluxos detalhados de cada caso de uso"],
  ["DOC-04", "Arquitetura", "Estilo arquitetural, containers, decisões registradas e stack"],
  ["DOC-05", "Modelo de Dados", "Entidades do esquema canônico e dicionário de dados"],
  ["DOC-06", "Catálogo de Fontes", "Fontes por esfera e estratégia de ingestão multiformato"],
  ["DOC-07", "Motor de Detecção", "Catálogo de regras com fórmulas, limiares e falsos positivos"],
  ["DOC-08", "Política Jurídica e Editorial", "Base legal, LGPD, vocabulário e direito de resposta"],
  ["DOC-09", "Padrões de Código", "Convenções, testes, CI/CD e definição de pronto"],
  ["DOC-10", "Roadmap", "Fases, marcos, esforço e custos estimados"],
]));

L.buildDoc({
  codigo: "DOC-01",
  titulo: "Visão e Escopo",
  subtitulo: "Por que o projeto existe, o que ele faz, o que ele nunca fará",
  body,
  outFile: "../docs/DOC-01_Visao_e_Escopo.docx",
});
