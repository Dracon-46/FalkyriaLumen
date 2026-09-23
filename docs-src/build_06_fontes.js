const L = require("./lib");
const { h1, h2, h3, p, bullet, numbered, table, callout, code, figure, pageBreak, spacer } = L;

const body = [];

body.push(h1("1. Estratégia de cobertura"));
body.push(p("A pergunta central deste documento é: como cobrir mais de seis mil entes sem construir mais " +
  "de seis mil integrações. A resposta tem três movimentos, executados nessa ordem."));
body.push(numbered("Integrar as bases federais de envio obrigatório. Como a lei obriga estados e " +
  "municípios a enviarem seus dados a sistemas federais centralizados, uma única integração entrega " +
  "dados de milhares de entes. Este é o movimento que viabiliza o projeto."));
body.push(numbered("Integrar por família de plataforma. A maior parte dos municípios não desenvolve seu " +
  "portal de transparência: contrata de um número reduzido de fornecedores de software. Um conector por " +
  "família de plataforma cobre dezenas ou centenas de municípios de uma vez."));
body.push(numbered("Tratar a cauda longa com extração de documentos e mapeamento assistido. Só o que " +
  "restar depois dos dois movimentos anteriores recebe tratamento individual."));

body.push(callout("A constatação que muda a ordem de grandeza do projeto", [
  "O PNCP, criado pela Lei 14.133/2021, centraliza as contratações de todos os entes federativos e expõe " +
  "API pública. O SICONFI, do Tesouro Nacional, concentra os relatórios contábeis e fiscais de estados e " +
  "municípios, com API aberta e sem exigência de cadastro.",
  "Juntas, essas duas fontes dão alcance nacional na primeira fase do projeto. A raspagem municipal, que " +
  "a intuição colocaria como tarefa principal, é na verdade um complemento para preencher lacunas e " +
  "obter detalhe que as bases federais não trazem.",
], "green"));

body.push(pageBreak());
body.push(h1("2. Camada 1 — Fontes federais estruturadas"));

body.push(h2("2.1 PNCP — Portal Nacional de Contratações Públicas"));
body.push(table(null, [2200, 7400], [
  ["Operador", "Serpro, sob a Lei 14.133/2021"],
  ["Endpoint de consulta", "https://pncp.gov.br/api/consulta"],
  ["Documentação", "Swagger público em /api/consulta/swagger-ui/index.html"],
  ["Autenticação", "Não exigida para a API de consulta"],
  ["Formato", "JSON"],
  ["Abrangência", "Todos os entes federativos sujeitos à Nova Lei de Licitações"],
  ["Importância", "Fonte primária de contratações, contratos, atas e amparo legal"],
], { boldFirstCol: true }));

body.push(h3("Recursos relevantes"));
body.push(table(["Recurso", "Endpoint", "Uso no Lumen"], [2300, 3500, 3800], [
  ["Contratações por publicação", "/v1/contratacoes/publicacao", "Carga inicial e acompanhamento diário"],
  ["Contratações por atualização", "/v1/contratacoes/atualizacao", "Captura alterações posteriores à publicação"],
  ["Contratação específica", "/v1/orgaos/{cnpj}/compras/{ano}/{sequencial}", "Detalhamento sob demanda"],
  ["Contratos e empenhos", "/v1/contratos", "Contratos firmados e seus valores"],
  ["Contratos por atualização", "/v1/contratos/atualizacao", "Aditivos e mudanças de valor"],
  ["Atas de registro de preço", "/v1/atas", "Comparação de preços registrados entre entes"],
  ["Instrumentos de cobrança", "/v1/instrumentoscobranca/inclusao", "Notas fiscais vinculadas à execução"],
  ["Planos de contratação anual", "/v1/pca/", "Comparação entre o planejado e o executado"],
]));

body.push(callout("Por que o PNCP é a fonte mais valiosa do projeto", [
  "Além de contratos e valores, a API traz o amparo legal como campo estruturado, e não como texto " +
  "livre. Isso permite responder de forma objetiva, e em escala nacional, com que fundamento cada " +
  "contratação direta foi realizada — exatamente o dado que sustenta as regras de dispensa e " +
  "fracionamento, e o requisito de registrar por que o ato foi autorizado.",
], "blue"));

body.push(h2("2.2 SICONFI — Tesouro Nacional"));
body.push(table(null, [2200, 7400], [
  ["Operador", "Secretaria do Tesouro Nacional"],
  ["Endpoint", "https://apidatalake.tesouro.gov.br/ords/siconfi/tt/"],
  ["Autenticação", "Não exigida"],
  ["Formato", "JSON, paginação padrão de 5.000 itens"],
  ["Limite de taxa", "Recomendação de aproximadamente uma requisição por segundo"],
  ["Abrangência", "Estados, Distrito Federal e municípios"],
  ["Conteúdo", "RREO bimestral, RGF, DCA anual e séries consolidadas"],
], { boldFirstCol: true }));
body.push(p("O SICONFI fornece a dimensão orçamentária e fiscal que o PNCP não cobre: receita, despesa " +
  "por função, endividamento e indicadores de gestão fiscal. É a base do cálculo de gasto per capita e " +
  "da formação dos grupos de pares."));
body.push(callout("A lacuna do SICONFI também é dado", [
  "As consolidações do Tesouro cobrem a maior parte dos municípios brasileiros, mas não todos. Os entes " +
  "ausentes em um dado exercício são, por definição, entes que não cumpriram uma obrigação legal de " +
  "envio. Essa lista de ausentes é coletada e alimenta diretamente o módulo de conformidade, e constitui " +
  "o sinal de descumprimento mais objetivo e menos contestável que o sistema produz.",
], "amber"));

body.push(h2("2.3 Portal da Transparência — CGU"));
body.push(table(null, [2200, 7400], [
  ["Operador", "Controladoria-Geral da União"],
  ["Endpoint", "https://api.portaldatransparencia.gov.br"],
  ["Autenticação", "Token gratuito, obtido por cadastro de e-mail"],
  ["Limite de taxa", "400 requisições por minuto entre 6h e 23h59; 700 entre 0h e 5h59"],
  ["Base legal de uso", "Livre utilização conforme o Decreto 8.777/2016"],
  ["Recomendação oficial", "Para volume alto, usar os arquivos de dados abertos em vez da API"],
], { boldFirstCol: true }));
body.push(table(["Conjunto", "Conteúdo", "Uso no Lumen"], [2200, 3600, 3800], [
  ["Despesas públicas", "Documentos de despesa do Executivo federal", "Cadeia de empenho, liquidação e pagamento"],
  ["Convênios", "Transferências a estados e municípios", "Rastrear destino de recurso federal"],
  ["Emendas parlamentares", "Emendas e documentos vinculados", "Vincular emenda ao executor final"],
  ["CEIS", "Empresas inidôneas e suspensas", "Regra de contratação de sancionado"],
  ["CNEP", "Empresas punidas", "Regra de contratação de sancionado"],
  ["CEPIM", "Entidades sem fins lucrativos impedidas", "Convênios com entidades impedidas"],
  ["Licitações e contratos", "Contratações do Executivo federal", "Complemento ao PNCP na esfera federal"],
  ["Notas fiscais", "Notas fiscais eletrônicas publicadas", "Confronto entre contratado e efetivamente faturado"],
]));

body.push(h2("2.4 Receita Federal — base pública de CNPJ"));
body.push(p("Distribuída como arquivos completos para download, e não como API de consulta. Traz quadro " +
  "societário, CNAE, capital social, data de abertura e situação cadastral. É a fonte que transforma um " +
  "CNPJ em contexto analisável e sustenta toda a família D do catálogo de regras."));
body.push(table(["Arquivo", "Conteúdo", "Regra que depende"], [2400, 3600, 3600], [
  ["Empresas", "Razão social, capital social, porte", "D-02 desproporção entre capital e contrato"],
  ["Estabelecimentos", "CNAE, endereço, situação, data de início", "D-01 empresa recém-constituída; D-03 CNAE incompatível"],
  ["Sócios", "Quadro societário", "D-04 sócios em comum entre concorrentes"],
]));

body.push(h2("2.5 Demais fontes federais"));
body.push(table(["Fonte", "Conteúdo", "Prioridade"], [2600, 4600, 2400], [
  ["Compras.gov.br", "Catálogos CATMAT e CATSER, painel de preços de referência", "Alta, normaliza itens"],
  ["TCU — dados abertos", "Acórdãos, processos de fiscalização, licitantes inidôneos", "Média"],
  ["TSE — dados abertos", "Candidaturas e doações eleitorais", "Média, uso com cautela metodológica"],
  ["IBGE", "População, malha territorial, indicadores municipais", "Alta, base do grupo de pares"],
  ["SIOPS e SIOPE", "Aplicação mínima em saúde e educação", "Média"],
  ["Câmara e Senado", "Dados abertos legislativos federais", "Baixa na versão 1.0"],
]));

body.push(callout("Cautela metodológica com dados eleitorais", [
  "Cruzar doação eleitoral com contratação pública produz associações de forte apelo, mas também de " +
  "alto risco de leitura equivocada: a relação pode ser inteiramente lícita e a coincidência, " +
  "estatisticamente esperada em um universo grande. Esse cruzamento só é publicado como contexto " +
  "factual anexo a um indício originado por outra regra, e nunca como indício autônomo.",
], "red"));

body.push(pageBreak());
body.push(h1("3. Camada 2 — Estados e tribunais de contas"));
body.push(p("As 27 unidades federativas possuem portais próprios com maturidade desigual. Os tribunais " +
  "de contas estaduais, por sua vez, concentram dados dos municípios de sua jurisdição, o que os torna " +
  "atalhos valiosos: integrar um TCE pode significar cobrir centenas de municípios com detalhe superior " +
  "ao disponível nas bases federais."));
body.push(table(["Tipo de fonte", "Quantidade", "Estratégia"], [2600, 1800, 5200], [
  ["Portal estadual do Executivo", "27", "Conector declarativo quando houver dado estruturado; API quando existir"],
  ["Tribunal de Contas do Estado", "26 mais o do DF", "Prioridade alta; cobre municípios da jurisdição"],
  ["Tribunal de Contas dos Municípios", "Existente em alguns estados", "Prioridade alta onde existir"],
  ["Assembleias legislativas", "27", "Prioridade baixa na versão 1.0"],
]));
body.push(p("A ordem de ataque dentro da camada 2 é definida por um critério simples: número de " +
  "municípios cobertos por integração construída. Tribunais de contas com dados abertos consolidados " +
  "vêm primeiro; portais estaduais isolados vêm por último."));

body.push(h1("4. Camada 3 — Municípios"));
body.push(h2("4.1 Abordagem por família de plataforma"));
body.push(p("Municípios brasileiros majoritariamente contratam seus portais de transparência de " +
  "fornecedores especializados de software de gestão pública. Portais da mesma família compartilham " +
  "estrutura de URL, organização de páginas e formato de exportação. Isso permite escrever um conector " +
  "por família, e não por município."));
body.push(numbered("Levantar, para uma amostra representativa de municípios, qual plataforma cada um utiliza, " +
  "identificando-a por assinaturas técnicas da página."));
body.push(numbered("Ordenar as famílias por número de municípios atendidos."));
body.push(numbered("Construir um conector por família, começando pela de maior alcance."));
body.push(numbered("Validar o conector em amostra aleatória de municípios daquela família antes de liberar para o restante."));
body.push(callout("Premissa a validar antes de investir na camada 3", [
  "A hipótese de concentração em poucas famílias de plataforma é plausível e amplamente observada na " +
  "prática, mas o projeto não deve assumi-la sem medição. O levantamento descrito acima é a primeira " +
  "atividade da fase 4 justamente para confirmar, com dados, quantos municípios cada conector realmente " +
  "cobriria — e recalibrar o plano caso a concentração seja menor que a esperada.",
], "amber"));

body.push(h2("4.2 Cauda longa"));
body.push(table(["Situação encontrada", "Tratamento"], [3600, 6000], [
  ["Portal com exportação estruturada", "Conector declarativo padrão"],
  ["Portal só com tabelas em HTML", "Conector declarativo com seletores de tabela"],
  ["Publicação apenas em PDF com texto", "Extração estruturada de PDF"],
  ["Publicação em PDF digitalizado", "OCR seguido de extração, com marcação de confiança reduzida"],
  ["Publicação em planilhas", "Leitor de planilha com mapeamento declarativo"],
  ["Nenhuma publicação localizável", "Pedido formal de acesso à informação e registro de não conformidade"],
]));

body.push(h2("4.3 Especificação declarativa de fonte"));
body.push(p("Cadastrar uma fonte é escrever uma especificação, não código. O exemplo abaixo ilustra o " +
  "formato para um portal municipal que publica contratos em tabela HTML paginada."));
body.push(code([
  "fonte: sp_exemplo_municipio_contratos",
  "ente:",
  "  codigo_ibge: \"3500000\"",
  "  esfera: municipal",
  "conector: declarativo_html",
  "objeto_canonico: Contrato",
  "periodicidade: diaria",
  "",
  "acesso:",
  "  url_base: \"https://transparencia.exemplo.sp.gov.br/contratos\"",
  "  paginacao:",
  "    tipo: parametro_query",
  "    parametro: \"pagina\"",
  "    inicio: 1",
  "  limite_taxa:",
  "    requisicoes_por_minuto: 20      # conservador por padrao",
  "",
  "extracao:",
  "  seletor_linhas: \"table#contratos tbody tr\"",
  "  campos:",
  "    numero:            { seletor: \"td:nth-child(1)\" }",
  "    fornecedor_cnpj:   { seletor: \"td:nth-child(2)\", transformar: [somente_digitos] }",
  "    objeto:            { seletor: \"td:nth-child(3)\" }",
  "    valor_inicial:     { seletor: \"td:nth-child(4)\", transformar: [moeda_br] }",
  "    data_assinatura:   { seletor: \"td:nth-child(5)\", transformar: [data_br] }",
  "    documento_detalhe: { seletor: \"td:nth-child(6) a\", atributo: \"href\" }",
  "",
  "qualidade:",
  "  obrigatorios: [numero, objeto, valor_inicial, data_assinatura]",
  "  validacoes:",
  "    - campo: fornecedor_cnpj",
  "      regra: cnpj_valido",
  "      ao_falhar: quarentena",
  "",
  "conformidade:",
  "  # o que a lei exige e esta fonte NAO oferece",
  "  campos_ausentes: [amparo_legal, agente_autorizador]",
  "  dispositivo: \"Lei 14.133/2021, art. 174\"",
]));
body.push(p("O bloco de conformidade merece atenção: ele declara, no próprio cadastro da fonte, quais " +
  "informações legalmente exigidas aquele portal não publica. Essa declaração vira insumo automático do " +
  "índice de conformidade do ente, sem trabalho adicional."));

body.push(pageBreak());
body.push(h1("5. Política de coleta responsável"));
body.push(p("O Lumen depende da boa saúde dos serviços públicos que consulta. Degradar um portal de " +
  "transparência para coletar dados seria contraditório com o propósito do projeto."));
body.push(table(["Regra", "Detalhamento"], [2600, 7000], [
  ["Identificação", "User-Agent próprio com nome do projeto, versão e endereço de contato em toda requisição"],
  ["Preferência por API", "Raspagem só quando não existir API ou exportação estruturada"],
  ["Vazão conservadora", "Padrão baixo por fonte; aumento só com evidência de que a fonte suporta"],
  ["Janela preferencial", "Coletas volumosas em horário de menor uso quando a fonte publicar essa informação"],
  ["Coleta incremental", "Uso de endpoints por data de atualização em vez de varredura completa recorrente"],
  ["Recuo em erro", "Espera exponencial e suspensão temporária da fonte após falhas sucessivas"],
  ["Respeito a robots", "Observância das diretrizes publicadas pelo domínio"],
  ["Sem contorno de controle", "Nenhuma tentativa de resolver CAPTCHA, burlar autenticação ou acessar área restrita"],
  ["Cache agressivo", "Artefato já coletado e inalterado não é rebaixado novamente"],
]));

body.push(h1("6. Matriz de cobertura esperada por fase"));
body.push(table(["Fase", "Fontes integradas", "Cobertura resultante"], [1300, 4300, 4000], [
  ["Fase 1", "PNCP, SICONFI, CGU, Receita Federal, IBGE",
    "Contratações e dados fiscais de alcance nacional, limitados ao que os entes efetivamente enviam"],
  ["Fase 2", "Compras.gov (catálogos e preços de referência)",
    "Normalização de itens e linha de base de preço, habilitando as regras de sobrepreço"],
  ["Fase 3", "27 estados e tribunais de contas",
    "Detalhamento estadual e cobertura indireta de municípios via jurisdição dos tribunais"],
  ["Fase 4", "Famílias de plataforma municipal e cauda longa",
    "Preenchimento de lacunas e detalhe local não disponível nas bases federais"],
  ["Fase 5", "Consolidação e reavaliação",
    "Índice de conformidade publicado para todos os entes cadastrados"],
]));

body.push(h1("7. Registro de fontes"));
body.push(p("Toda fonte cadastrada mantém os metadados abaixo, que alimentam o painel operacional e a " +
  "avaliação de conformidade."));
body.push(table(["Metadado", "Finalidade"], [2800, 6800], [
  ["Identificador e ente vinculado", "Associar dados coletados ao ente correto"],
  ["Tipo de conector", "Determinar o adaptador que executa a coleta"],
  ["Objetos canônicos fornecidos", "Saber o que esperar da fonte e o que falta"],
  ["Periodicidade e janela", "Agendamento e detecção de atraso"],
  ["Limite de taxa acordado", "Controle de vazão"],
  ["Última coleta bem-sucedida", "Exibição pública da atualidade do dado"],
  ["Histórico de falhas", "Distinguir instabilidade pontual de descontinuidade"],
  ["Campos legalmente exigidos ausentes", "Alimentar o índice de conformidade"],
  ["Versão da especificação", "Reprodutibilidade das coletas passadas"],
]));

L.buildDoc({
  codigo: "DOC-06",
  titulo: "Catálogo de Fontes",
  subtitulo: "Fontes por esfera, estratégia de cobertura nacional e coleta responsável",
  body,
  outFile: "../docs/DOC-06_Catalogo_de_Fontes.docx",
});
