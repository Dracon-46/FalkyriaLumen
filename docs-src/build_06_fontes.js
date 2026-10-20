const L = require("./lib");
const { h1, h2, h3, p, bullet, numbered, table, callout, code, figure, pageBreak, spacer } = L;
// Versão 1.1 (outubro de 2026): comportamentos reais observados nas fontes
// integradas na Fase 1, fontes do TSE e do IBGE da aba Eleições e situação de
// cada integração. As peculiaridades citadas têm fixture e teste próprios
// (testes/fixtures/README.md).

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

body.push(h3("Comportamento real observado (outubro de 2026)"));
body.push(p("A documentação oficial não basta para coletar o PNCP. Os pontos abaixo foram observados nas " +
  "respostas reais durante a construção dos conectores da Fase 1; cada um tem fixture e teste próprios."));
body.push(table(["Comportamento", "Como o Lumen trata"], [4600, 5000], [
  ["codigoModalidadeContratacao é obrigatório em /v1/contratacoes/*; sem ele, erro 400", "A coleta de contratações percorre as 19 modalidades do domínio oficial"],
  ["tamanhoPagina aceita no máximo 50 em contratações e 500 em contratos e atas", "O conector usa o máximo de cada recurso e recusa valor fora da faixa"],
  ["Janela de datas acima de 365 dias responde 422", "A coleta fatia por dia, o que também mantém o tamanho das páginas previsível"],
  ["Página sem registros responde 204 sem corpo, não 200 com lista vazia", "204 é tratado como fim da listagem"],
  ["Erro 422 traz status como texto (\"422\"); erro 400 traz número", "Leitura tolerante aos dois formatos"],
  ["Itens, resultados e arquivos de uma contratação ficam em outra API (/api/pncp, no caminho do órgão)", "Conector próprio (pncp_itens), separado da consulta"],
  ["usuarioNome é a plataforma de software que enviou os dados, não uma pessoa", "Guardado como plataforma; o agente que autorizou o ato fica vazio (ADR-017)"],
  ["Descrição do amparo legal ainda cita os valores originais da lei (R$ 50 mil e R$ 100 mil)", "O limite vem do código do amparo e dos parâmetros legais datados, nunca do texto"],
  ["Dados com erro de digitação (ata com vigência no ano 7203)", "Linha vai para a quarentena com o motivo; o resto do artefato segue"],
  ["valorTotalEstimado = 0 com valor homologado nulo", "Aceito com marcação de qualidade; nunca usado como valor zero"],
  ["esferaId e poderId iguais a N (não informado)", "Viram nulo, com marcação; o ente não é adivinhado"],
  ["Órgão estadual com o código IBGE da capital", "O ente é o estado, não o município"],
], { size: 17 }));
body.push(p("Limite padrão do Lumen: 60 requisições por minuto em cada recurso do PNCP, ajustável em lumen.toml."));
body.push(callout("Lacuna que afeta a política editorial", [
  "A API do PNCP não publica quem autorizou a contratação. A exigência do DOC-08 de mostrar quem praticou o " +
  "ato depende de fonte complementar (diário oficial ou portal do ente), e nenhum indício que dependa dessa " +
  "informação pode ser publicado só com o PNCP.",
], "red"));
body.push(spacer(100));

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
body.push(h3("Comportamento real observado (outubro de 2026)"));
body.push(table(["Comportamento", "Como o Lumen trata"], [4600, 5000], [
  ["Paginação ORDS por offset, com hasMore, até 5.000 itens por página", "Leitura por deslocamento até hasMore = false"],
  ["/entes lista 5.598 entes, com código IBGE, CNPJ e população", "Base do cadastro de entes e do grupo de pares"],
  ["capital vem como texto com espaços (\"1  \")", "Normalizado antes da conversão"],
  ["Estados vêm com uf = \"BR\"; a União vem com cod_ibge = 1, uf nulo e população que não é a do país", "A UF sai do código IBGE (divergência vira marcação); a população da União fica como veio, marcada, e nunca entra em grupo de pares"],
  ["/extrato_entregas diz o que cada ente entregou num exercício", "Origem da lista de ausentes (família I, RF-CF-01)"],
  ["/rreo exige o tipo do demonstrativo: RREO ou RREO Simplificado (municípios com menos de 50 mil habitantes podem optar, LRF art. 63), e cada ente publica só um. O porte não diz qual: em 2025, quase todos os pequenos de Roraima e do Amapá publicaram o completo", "O tipo vem do extrato de entregas (\"Relatório Resumido de Execução Orçamentária\" ou \"… Simplificado\", no 6º bimestre); uma consulta por ente"],
  ["A RCL fica no Anexo 03, conta RREO3ReceitaCorrenteLiquida, coluna TOTAL (ÚLTIMOS 12 MESES); a resposta do anexo tem perto de 430 linhas por ente, com valores numéricos", "Cada linha vira LinhaDemonstrativo; a RCL do exercício anterior entra nos grupos de pares (ADR-038, versão 2)"],
], { size: 17 }));
body.push(p("Limite padrão do Lumen: 50 requisições por minuto, abaixo da recomendação do Tesouro de cerca de uma " +
  "por segundo."));

body.push(callout("A lacuna do SICONFI também é dado", [
  "As consolidações do Tesouro cobrem a maior parte dos municípios brasileiros, mas não todos. Os entes " +
  "ausentes em um dado exercício são, por definição, entes que não cumpriram uma obrigação legal de " +
  "envio. Essa lista de ausentes é coletada e alimenta diretamente o módulo de conformidade, e constitui " +
  "o sinal de descumprimento mais objetivo e menos contestável que o sistema produz.",
], "amber"));

body.push(h2("2.3 Portal da Transparência — CGU"));
body.push(table(null, [2200, 7400], [
  ["Operador", "Controladoria-Geral da União"],
  ["Endpoint da API", "https://api.portaldatransparencia.gov.br (cabeçalho chave-api-dados; 15 registros por página)"],
  ["Arquivos de dados abertos", "https://portaldatransparencia.gov.br/download-de-dados/<conjunto>/AAAAMMDD, que redireciona para dadosabertos-download.cgu.gov.br; ZIP com um CSV em ISO-8859-1, separado por ;"],
  ["Autenticação", "API: token gratuito, obtido por cadastro de e-mail. Arquivos: nenhuma"],
  ["Limite de taxa", "API: 400 requisições por minuto entre 6h e 23h59; 700 entre 0h e 5h59. Arquivos: o Lumen faz duas requisições por cadastro e por dia, com limite de 10 por minuto"],
  ["Base legal de uso", "Livre utilização conforme o Decreto 8.777/2016"],
  ["Recomendação oficial", "Para volume alto, usar os arquivos de dados abertos em vez da API"],
], { boldFirstCol: true }));
body.push(table(["Conjunto", "Conteúdo", "Uso no Lumen"], [2200, 3600, 3800], [
  ["Despesas públicas", "Documentos de despesa do Executivo federal", "Cadeia de empenho, liquidação e pagamento"],
  ["Convênios", "Transferências a estados e municípios", "Rastrear destino de recurso federal"],
  ["Emendas parlamentares", "Emendas e documentos vinculados", "Vincular emenda ao executor final"],
  ["CEIS", "Empresas inidôneas e suspensas (23.787 sanções em 15/10/2026)", "Coletado (cgu_ceis, ADR-030); regra J-01 na Fase 2"],
  ["CNEP", "Empresas punidas pela Lei 12.846/2013 (1.840)", "Coletado (cgu_cnep); regra J-01 na Fase 2"],
  ["CEPIM", "Entidades sem fins lucrativos impedidas (3.521)", "Coletado (cgu_cepim); convênios com entidades impedidas"],
  ["Licitações e contratos", "Contratações do Executivo federal", "Complemento ao PNCP na esfera federal"],
  ["Notas fiscais", "Notas fiscais eletrônicas publicadas", "Confronto entre contratado e efetivamente faturado"],
]));

body.push(p("CEIS, CNEP e CEPIM vêm dos arquivos de dados abertos, e não da API (ADR-030). Cada arquivo é o " +
  "retrato do cadastro inteiro num dia; a página de download declara a data do mais recente, que em " +
  "16/10/2026 era 15/10 no CEIS e no CNEP e 14/10 no CEPIM. Comportamento observado em 16/10/2026: o CEIS publica o CPF inteiro das pessoas físicas " +
  "sancionadas (9.170 linhas), que o Lumen mascara na normalização; \"Sem Informação\" marca campo não " +
  "informado; há sanções com prazo determinado que terminam em 31/12/2099; sancionados estrangeiros vêm sem " +
  "tipo de pessoa e com documento de 7 a 9 dígitos; o CEPIM não tem datas nem código da sanção."));

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
  ["PNTP — Radar da Transparência (tribunais de contas e Atricon)", "Avaliação anual dos portais de transparência de 11.697 entidades (2025), com o endereço do portal; base por ciclo em ZIP, lida por Range (ADR-032)", "Em uso (pntp_avaliacoes)"],
  ["TSE — resultados", "Resultados eleitorais, ao vivo e desde 1933 (seção 2.6)", "Integrado na aba Eleições"],
  ["TSE — prestação de contas", "Candidaturas e doações eleitorais", "Média, uso com cautela metodológica"],
  ["IBGE", "População, localidades e malhas territoriais (seção 2.7)", "Alta, base do grupo de pares e do mapa"],
  ["SIOPS e SIOPE", "Aplicação mínima em saúde e educação", "Média"],
  ["Câmara e Senado", "Dados abertos legislativos federais", "Baixa na versão 1.0"],
]));

body.push(callout("Cautela metodológica com dados eleitorais", [
  "Cruzar doação eleitoral com contratação pública produz associações de forte apelo, mas também de " +
  "alto risco de leitura equivocada: a relação pode ser inteiramente lícita e a coincidência, " +
  "estatisticamente esperada em um universo grande. Esse cruzamento só é publicado como contexto " +
  "factual anexo a um indício originado por outra regra, e nunca como indício autônomo.",
], "red"));

body.push(h2("2.6 TSE — resultados eleitorais (aba Eleições)"));
body.push(p("A aba Eleições usa duas fontes do TSE, descritas em detalhe no DOC-12. Nenhuma delas alimenta o " +
  "motor de detecção (ADR-024)."));
body.push(table(["Fonte", "Endereço", "Formato e comportamento observado"], [2000, 3600, 4000], [
  ["Sistema de divulgação de resultados", "https://resultados.tse.jus.br/oficial", "JSON estático por CDN; números como texto com vírgula decimal; data e hora em campos separados, no horário de Brasília; responde 304 a If-Modified-Since. Mantém só eleições recentes."],
  ["Portal de Dados Abertos, 1994 a 2024", "dadosabertos.tse.jus.br (CKAN) e cdn.tse.jus.br (ZIPs)", "CSV Latin-1 com ;, 38, 44 ou 50 colunas conforme o ano; um arquivo por UF, um _BR (Presidente) e um _BRASIL que concatena todos e é ignorado. Diferenças de 1994, 2000 e 2002 a 2014 tratadas no DOC-12."],
  ["Portal de Dados Abertos, 1933 a 1990", "cdn.tse.jus.br/estatistica/sead/odsele (votacao_candidato_uf, detalhe_votacao_uf, votacao_partido_uf)", "Só por UF; texto Latin-1 sem cabeçalho (exceto 1933 e 1934), com bytes do Windows-1252; colunas na ordem do Leia-me (26, 22 e 17); candidatos sem número até os anos 1980; UFs extintas; o arquivo de partido de 1989 não existe. Tratado no DOC-12, seção 3.2, e no ADR-025."],
], { size: 17 }));
body.push(p("Limites padrão: 300 requisições por minuto no sistema de resultados (servido por CDN) e 30 nos " +
  "dados abertos. Os ZIPs (642 MB só a votação de 2022) são baixados com retomada e manifesto (ADR-021)."));
body.push(p("A prestação de contas de campanha — doações e despesas — é outra fonte, ainda não integrada; é " +
  "pré-requisito da regra K-01 e segue a cautela abaixo."));

body.push(h2("2.7 IBGE — localidades, população e malhas"));
body.push(table(["Recurso", "Endereço", "Uso"], [2200, 4400, 3000], [
  ["Localidades", "servicodados.ibge.gov.br/api/v1/localidades (visão nivelado)", "Cadastro de UFs e municípios; 5.571 municípios em outubro de 2026"],
  ["População", "SIDRA, agregado 6579, variável 9324, último período", "Gasto per capita e grupo de pares"],
  ["Malhas v3", "servicodados.ibge.gov.br/api/v3/malhas, formato TopoJSON", "Mapa da aba Eleições; código IBGE em codarea"],
  ["Notícias v3 (releases)", "servicodados.ibge.gov.br/api/v3/noticias, tipo=release e idproduto", "Releases da Agência de Notícias ao lado do IPCA, do INPC e do PIB na área Economia (ADR-033, adendo de 20/10/2026); data como dd/mm/aaaa hh:mm:ss e link em http"],
], { size: 17 }));
body.push(p("Sem autenticação. Limite padrão do Lumen: 30 requisições por minuto. A API responde comprimida " +
  "(Content-Encoding: gzip) mesmo quando o pedido não pede compressão, como o teste de contrato diário mostrou em " +
  "outubro de 2026; a coleta desfaz a compressão de transporte antes de guardar no bronze e registra a codificação " +
  "recebida no cabeçalho X-Lumen-Codificacao-Recebida."));

body.push(h2("2.8 Referência de mercado de fora do governo (regra A-05)"));
body.push(p("Fontes que não são compras públicas e servem de régua para o preço que o governo pagou (ADR-027). " +
  "Nenhuma delas é usada para afirmar nada sobre um ente: a regra A-05 roda em modo silencioso até a calibração."));
body.push(table(["Fonte", "Endereço", "Formato e comportamento"], [2200, 3800, 3600], [
  ["ANP — série histórica de preços de combustíveis", "gov.br/anp/.../dados-abertos/arquivos/shpc/dsas/ca/ca-AAAA-0S.zip (até 2021, .csv; o 1º semestre de 2022 é precos-semestrais-ca.zip)", "CSV com ;, uma linha por posto, produto e semana: UF, município, revenda e CNPJ, produto, data da coleta, valor de venda com vírgula decimal. Arquivo semestral, publicado depois do fim do semestre; desde 2006. Leitura tolerante a nome de coluna, separador e codificação."],
  ["ANP — série histórica do gás de cozinha", "gov.br/anp/.../dsas/glp/glp-AAAA-0S.csv, sempre .csv, desde 2004 (2021-1 é precos-semestrais-glp2021-01.csv e 2022-1, precos-semestrais-glp-2022-01.csv)", "Mesmo formato da série de combustíveis, com o preço do botijão de 13 kg (R$ / 13 kg)."],
  ["ANP — levantamento das últimas semanas", "gov.br/anp/.../precos/levantamento-de-precos-de-combustiveis-ultimas-semanas-pesquisadas; planilhas em arquivos-lpc/AAAA/revendas_lpc_<início>_<fim>.xlsx", "Planilha .xlsx por semana (cerca de 1,8 MB e 20 mil coletas), posto a posto, com combustíveis e GLP: sete linhas de título antes do cabeçalho, CNPJ só com dígitos (às vezes sem o zero à esquerda), UF pelo nome do estado, preço como número e data como número de série do Excel, nomes de produto próprios (GASOLINA COMUM, DIESEL S500). O nome do arquivo não segue padrão fixo (2026-08-30-2026-09-5): os endereços são tirados da página, que em outubro de 2026 citava 192 semanas, de setembro de 2022 em diante. Lida sem dependências (lumen_mercado/xlsx.py)."],
  ["Mercado Livre — busca", "api.mercadolibre.com/sites/MLB/search?q=…", "JSON com results (id, title, price, currency_id, condition, permalink, seller, shipping). API oficial; sem credencial responde 403 (visto em 9/10/2026), e o token vem de LUMEN_ML_TOKEN. Só o preço de hoje: coleta diária guardada no bronze."],
  ["Notas fiscais ao consumidor (Menor Preço/PR, Preço da Hora/BA)", "menorpreco.notaparana.pr.gov.br; precodahora.ba.gov.br", "Preço de venda real por código de barras e lugar; sem API pública. Pedido de acesso pela Lei de Acesso à Informação, a fazer."],
], { size: 17 }));
body.push(p("Fora por decisão: Magazine Luiza, KaBuM, Pichau e comparadores de preço (Zoom, Buscapé) não têm API " +
  "pública de preços, e extrair o site contraria os termos de uso e as barreiras contra robôs (seção 5). " +
  "Amazon (Creators API), AliExpress e Shopee (programas de afiliados) entram quando houver credencial."));
body.push(p("Limites padrão: 10 requisições por minuto na ANP (arquivos grandes, poucas requisições) e 30 no " +
  "varejo."));

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
  ["Limite da fonte (429)", "Resposta 429 reduz a vazão da fonte pela metade pelo resto da sessão e espera ao menos 30 s antes de repetir; só conta como falha quando a última tentativa também recebe 429. O PNCP respondeu 429 a 60 requisições por minuto a partir do GitHub Actions em outubro de 2026"],
  ["Compressão de transporte", "Resposta com Content-Encoding gzip ou deflate é descomprimida antes do bronze, com o limite de tamanho aplicado ao documento descomprimido (a API do IBGE comprime mesmo sem pedido)"],
  ["Respeito a robots", "Observância das diretrizes publicadas pelo domínio"],
  ["Sem contorno de controle", "Nenhuma tentativa de resolver CAPTCHA, burlar autenticação ou acessar área restrita"],
  ["Cache agressivo", "Artefato já coletado e inalterado não é rebaixado novamente"],
  ["Requisição condicional", "If-Modified-Since onde a fonte aceita: o que não mudou volta 304, sem corpo (TSE)"],
  ["Arquivo grande retomável", "Range e If-Range: queda de conexão continua de onde parou, sem rebaixar gigabytes (ADR-021)"],
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

body.push(h1("7. Situação da integração (outubro de 2026)"));
body.push(table(["Fonte", "Situação", "Observação"], [3000, 2400, 4200], [
  ["PNCP — contratações, contratos e atas (publicação e atualização)", "Integrado", "Coleta, bronze e normalização para a silver no pipeline padrão"],
  ["PNCP — itens e resultados", "Integrado sob demanda", "lumen coletar pncp_itens --objeto busca os itens só dos processos da silver que interessam (regra A-05)"],
  ["SICONFI — entes e extrato de entregas", "Integrado", "Base do cadastro e da conformidade (família I)"],
  ["SICONFI — RREO, RGF e DCA", "Conector e normalização prontos (LinhaDemonstrativo)", "RCL de todos os entes coletada todo dia, só a que falta (Anexo 03 do RREO); demais anexos sob demanda"],
  ["IBGE — localidades e população", "Integrado", "Cadastro de entes, população aplicada aos municípios"],
  ["IBGE — malhas", "Integrado (aba Eleições)", "Mapa"],
  ["TSE — resultados e dados abertos", "Integrado (aba Eleições)", "DOC-12"],
  ["Portal da Transparência (CGU)", "CEIS, CNEP e CEPIM em uso", "Pelos arquivos de dados abertos, sem chave (ADR-030); despesas, convênios e emendas pendentes"],
  ["Receita Federal — CNPJ", "Pendente", "Arquivos completos; base da família D"],
  ["TSE — prestação de contas", "Pendente", "Pré-requisito da K-01; revisão editorial antes de qualquer uso"],
  ["ANP — preços de combustíveis e GLP", "Integrado (regra A-05)", "Série semestral (ca e glp) e planilhas semanais; formato real conferido na primeira execução do fluxo mercado-referencia (9/10/2026), sem linha descartada"],
  ["Mercado Livre — busca", "Conector pronto, a validar", "Formato e acesso conferidos pela primeira coleta real e pelo teste de contrato"],
  ["Notas fiscais ao consumidor (estados)", "Pendente", "Pedido pela Lei de Acesso à Informação"],
  ["Compras.gov.br, estados, tribunais de contas, municípios", "Planejado", "Fases 2 a 4, conforme a seção 6"],
], { size: 17 }));

body.push(h1("8. Registro de fontes"));
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
  meta: { versao: "1.6", data: "20 de outubro de 2026",
    situacao: "Atualizado com o comportamento real das fontes da Fase 1, as da aba Eleições e as de referência de mercado (seção 2.8)",
    verificado: "outubro de 2026" },
  body,
  outFile: "../docs/DOC-06_Catalogo_de_Fontes.docx",
});
