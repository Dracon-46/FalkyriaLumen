const L = require("./lib");
const { h1, h2, h3, p, bullet, numbered, table, callout, code, figure, pageBreak, spacer } = L;

const body = [];

// helper de caso de uso
function uc({ cod, nome, ator, objetivo, pre, gatilho, principal, alternativos, excecoes, pos, req }) {
  const out = [];
  out.push(h2(`${cod} — ${nome}`));
  out.push(table(null, [1800, 7800], [
    ["Ator principal", ator],
    ["Objetivo", objetivo],
    ["Pré-condições", pre],
    ["Gatilho", gatilho],
    ["Pós-condições", pos],
    ["Requisitos cobertos", req],
  ], { boldFirstCol: true }));
  out.push(h3("Fluxo principal"));
  principal.forEach((s) => out.push(numbered(s)));
  if (alternativos && alternativos.length) {
    out.push(h3("Fluxos alternativos"));
    alternativos.forEach((a) => out.push(bullet(a)));
  }
  if (excecoes && excecoes.length) {
    out.push(h3("Exceções"));
    excecoes.forEach((e) => out.push(bullet(e)));
  }
  return out;
}

body.push(h1("1. Atores"));
body.push(table(["Ator", "Tipo", "Descrição"], [2100, 1500, 6000], [
  ["Cidadão", "Humano", "Pessoa sem conhecimento técnico que quer entender o gasto do seu município"],
  ["Jornalista", "Humano", "Profissional que investiga padrões e precisa de evidência utilizável em apuração"],
  ["Pesquisador", "Humano", "Usa a base normalizada para análise acadêmica ou estatística"],
  ["Analista Lumen", "Humano", "Integrante da equipe que revisa indícios, calibra regras e cadastra fontes"],
  ["Órgão de controle", "Humano", "Servidor de tribunal de contas, controladoria ou ministério público"],
  ["Ente público", "Humano", "Representante do órgão analisado, exercendo direito de resposta"],
  ["Sistema agendado", "Automático", "Processo programado que dispara ciclos de coleta e detecção"],
]));

body.push(spacer(200)); // separa a figura da tabela: imagem ancorada logo apos tabela se sobrepoe no LibreOffice
body.push(...figure("08_casos_uso.png", "Figura 1. Visão geral dos casos de uso por ator.", 600));

body.push(pageBreak());
body.push(h1("2. Casos de uso detalhados"));

body.push(...uc({
  cod: "UC-01", nome: "Consultar panorama de um ente",
  ator: "Cidadão",
  objetivo: "Entender, em linguagem acessível, como um município ou estado arrecada e gasta, e se há algo sinalizado para análise",
  pre: "O ente existe no cadastro e possui ao menos um ciclo de coleta concluído",
  gatilho: "O usuário busca o nome do município ou acessa um link direto",
  pos: "O usuário visualiza o panorama e pode navegar para contratos, indícios ou conformidade",
  req: "RF-PU-01, RF-PU-05, RF-PU-10, RF-PU-12",
  principal: [
    "O usuário informa o nome do ente na busca.",
    "O sistema apresenta a lista de entes correspondentes com UF e porte.",
    "O usuário seleciona o ente desejado.",
    "O sistema exibe o panorama: despesa total por exercício, principais fornecedores, distribuição por modalidade de contratação e índice de conformidade de transparência.",
    "O sistema exibe a comparação com o grupo de pares, indicando onde o ente se posiciona.",
    "O sistema exibe a quantidade de indícios abertos por severidade, sempre rotulados como atividade para análise.",
    "O sistema exibe a data da última coleta bem-sucedida e o aviso metodológico.",
  ],
  alternativos: [
    "3a. O usuário chega por link direto e o sistema abre o panorama diretamente.",
    "5a. O ente não possui grupo de pares calculado por falta de dados demográficos ou fiscais; o sistema omite a comparação e informa o motivo.",
  ],
  excecoes: [
    "2a. Nenhum ente corresponde à busca; o sistema sugere grafias próximas.",
    "4a. O ente não possui dado coletado; o sistema exibe explicitamente que não houve publicação encontrada e remete ao caso de uso UC-07.",
  ],
}));

body.push(...uc({
  cod: "UC-02", nome: "Pesquisar contratos e fornecedores",
  ator: "Jornalista",
  objetivo: "Localizar contratações que atendam a critérios combinados para sustentar uma apuração",
  pre: "Base normalizada disponível",
  gatilho: "O usuário acessa a busca avançada",
  pos: "O usuário obtém um conjunto de resultados que pode refinar, exportar ou transformar em dossiê",
  req: "RF-PU-02, RF-PU-06, RF-NO-03",
  principal: [
    "O usuário abre a busca avançada.",
    "O usuário combina filtros de ente, UF, fornecedor, objeto, faixa de valor, período, modalidade e amparo legal.",
    "O sistema executa a consulta e retorna os resultados paginados com total encontrado.",
    "O usuário ordena por valor, data ou severidade de indício associado.",
    "O usuário abre um resultado e visualiza o contrato, seus itens, aditivos e a cadeia de empenho, liquidação e pagamento.",
    "O sistema exibe, em cada resultado, o link para o documento fonte original.",
  ],
  alternativos: [
    "2a. O usuário pesquisa por CNPJ e o sistema agrega matriz e filiais, exibindo a consolidação e permitindo separar.",
    "4a. O usuário salva a consulta como filtro nomeado para reutilização.",
  ],
  excecoes: [
    "3a. A consulta excede o limite de complexidade; o sistema solicita refinamento e sugere quais filtros reduzem o custo.",
  ],
}));

body.push(...uc({
  cod: "UC-03", nome: "Visualizar um indício e sua evidência",
  ator: "Cidadão, Jornalista, Órgão de controle",
  objetivo: "Compreender por que determinada atividade foi sinalizada e verificar a evidência que a sustenta",
  pre: "Indício em estado publicado",
  gatilho: "O usuário clica em um indício a partir do panorama, da busca ou de um alerta",
  pos: "O usuário compreende a regra, os parâmetros e pode acessar o documento original",
  req: "RF-PU-03, RF-PU-04, RF-DE-03, RF-DE-04, RNF-23",
  principal: [
    "O sistema exibe o rótulo padronizado de atividade para análise, em destaque.",
    "O sistema exibe a explicação da regra em linguagem acessível, sem terminologia acusatória.",
    "O sistema exibe os parâmetros aplicados e os valores observados que levaram ao disparo.",
    "O sistema exibe a comparação com a referência utilizada, seja mediana do item, grupo de pares ou limite legal.",
    "O sistema lista os documentos fonte com link, hash SHA-256 e data de coleta.",
    "O sistema exibe o agente público signatário do ato e o amparo legal invocado, conforme publicado pela fonte.",
    "O sistema exibe o estado atual do indício e, se houver, a contestação registrada pelo ente.",
  ],
  alternativos: [
    "7a. O indício está contestado; o sistema exibe a contestação em igual destaque, lado a lado.",
    "7b. O indício foi retificado; o sistema exibe a errata e o histórico da alteração.",
  ],
  excecoes: [
    "5a. O documento fonte original saiu do ar na origem; o sistema oferece a cópia preservada na camada bruta e sinaliza que a origem está indisponível.",
  ],
}));

body.push(...uc({
  cod: "UC-04", nome: "Acompanhar um ente e receber alertas",
  ator: "Cidadão",
  objetivo: "Ser notificado quando surgirem novos indícios ou mudanças relevantes em um ente de interesse",
  pre: "Usuário identificado por e-mail validado",
  gatilho: "O usuário aciona a opção de acompanhar em um ente",
  pos: "O usuário passa a receber notificações periódicas conforme a preferência escolhida",
  req: "RF-PU-09",
  principal: [
    "O usuário aciona acompanhar no panorama do ente.",
    "O usuário informa e-mail e escolhe a periodicidade e a severidade mínima.",
    "O sistema envia mensagem de confirmação e registra o acompanhamento após a validação.",
    "A cada ciclo, o sistema agrega as novidades e envia resumo com links diretos.",
  ],
  alternativos: [
    "2a. O usuário opta por acompanhar um fornecedor em vez de um ente.",
  ],
  excecoes: [
    "3a. O e-mail não é validado em 72 horas; o sistema descarta a solicitação sem armazenar o endereço.",
  ],
}));

body.push(...uc({
  cod: "UC-05", nome: "Exportar dossiê de evidências",
  ator: "Jornalista, Órgão de controle",
  objetivo: "Obter pacote autocontido com os indícios selecionados e todos os documentos que os sustentam",
  pre: "Ao menos um indício selecionado",
  gatilho: "O usuário aciona exportar dossiê",
  pos: "Arquivo gerado e disponibilizado para download, com manifesto de integridade",
  req: "RF-PU-06, RF-PU-07, RNF-25",
  principal: [
    "O usuário seleciona um ou mais indícios.",
    "O usuário escolhe o formato: PDF para leitura ou pacote compactado com dados e documentos.",
    "O sistema monta o dossiê com a descrição da regra, os parâmetros, os dados de entrada e os documentos fonte.",
    "O sistema inclui manifesto com hash de cada documento e a data de geração.",
    "O sistema inclui aviso metodológico e a advertência de que se trata de indício e não de conclusão.",
    "O sistema disponibiliza o arquivo para download.",
  ],
  alternativos: [
    "2a. O usuário solicita apenas os dados tabulares, em CSV ou Parquet, sem os documentos.",
  ],
  excecoes: [
    "3a. O volume excede o limite de geração síncrona; o sistema processa em segundo plano e notifica por e-mail quando pronto.",
  ],
}));

body.push(...uc({
  cod: "UC-06", nome: "Comparar ente com grupo de pares",
  ator: "Jornalista, Pesquisador",
  objetivo: "Avaliar se um padrão de gasto é atípico em relação a entes comparáveis",
  pre: "Grupo de pares calculado para o ente",
  gatilho: "O usuário aciona comparar no panorama do ente",
  pos: "O usuário visualiza a posição relativa do ente em cada indicador",
  req: "RF-EN-02, RF-PU-05, RF-DE-13",
  principal: [
    "O usuário abre a comparação a partir do panorama.",
    "O sistema exibe a composição do grupo de pares e os critérios que o definiram.",
    "O sistema exibe, por indicador, o valor do ente, a mediana do grupo e a posição percentílica.",
    "O usuário seleciona um indicador e visualiza a distribuição completa do grupo.",
    "O usuário pode ajustar os critérios do grupo e recalcular a comparação.",
  ],
  alternativos: [
    "5a. O usuário define um grupo manual selecionando entes específicos.",
  ],
  excecoes: [
    "2a. O grupo tem menos entes que o mínimo estatístico; o sistema exibe a comparação com ressalva explícita sobre a baixa confiabilidade.",
  ],
}));

body.push(...uc({
  cod: "UC-07", nome: "Consultar índice de conformidade de transparência",
  ator: "Cidadão, Órgão de controle",
  objetivo: "Verificar se um ente cumpre suas obrigações legais de publicação e em que pontos falha",
  pre: "Ciclo de avaliação de conformidade executado",
  gatilho: "O usuário acessa a seção de conformidade ou o indicador no panorama",
  pos: "O usuário compreende quais obrigações são cumpridas e quais não são",
  req: "RF-CF-01 a RF-CF-08",
  principal: [
    "O sistema exibe o índice do ente, sua composição e a data da última avaliação.",
    "O sistema detalha cada critério avaliado, o resultado e o dispositivo legal correspondente.",
    "O sistema distingue claramente ausência persistente de publicação de indisponibilidade técnica temporária.",
    "O sistema exibe a evolução histórica do índice.",
    "O sistema permite comparar o índice com o dos entes do grupo de pares.",
  ],
  alternativos: [
    "5a. O usuário consulta o ranking de conformidade por UF ou por faixa populacional.",
  ],
  excecoes: [
    "1a. O ente nunca foi avaliado; o sistema informa a situação e a data prevista para a primeira avaliação.",
  ],
}));

body.push(pageBreak());
body.push(...uc({
  cod: "UC-08", nome: "Revisar fila de indícios pendentes",
  ator: "Analista Lumen",
  objetivo: "Decidir se um indício detectado é bem fundamentado o suficiente para publicação",
  pre: "Existem indícios em estado de revisão; analista autenticado com segundo fator",
  gatilho: "O analista abre a fila de revisão",
  pos: "O indício é publicado ou descartado, com registro do autor e da justificativa",
  req: "RF-DE-17, RF-DE-19, RF-AD-03, RF-AD-04, RNF-12",
  principal: [
    "O analista abre a fila, ordenada por severidade e antiguidade.",
    "O analista seleciona um indício e visualiza a regra, os parâmetros, os dados de entrada e os documentos fonte.",
    "O analista verifica se o documento fonte de fato sustenta o que a regra apontou.",
    "O analista verifica se há explicação legítima evidente, como natureza do objeto ou regime especial.",
    "O analista decide entre publicar, descartar ou solicitar nova coleta.",
    "O analista registra a justificativa da decisão.",
    "O sistema aplica a decisão, grava a trilha de auditoria e atualiza o estado do indício.",
  ],
  alternativos: [
    "5a. O analista identifica falha na regra e encaminha para ajuste, conforme UC-09.",
    "5b. O analista identifica dado de origem incorreto e marca o indício para não publicação, registrando o problema da fonte.",
  ],
  excecoes: [
    "3a. O documento fonte está corrompido ou ilegível; o indício vai para o estado aguardando dado e uma nova coleta é agendada.",
  ],
}));

body.push(...uc({
  cod: "UC-09", nome: "Ajustar parâmetros de uma regra",
  ator: "Analista Lumen",
  objetivo: "Calibrar uma regra para reduzir falso positivo sem perder sensibilidade",
  pre: "Regra existente; analista com permissão de calibração",
  gatilho: "Taxa de descarte da regra acima do limite aceitável ou revisão periódica programada",
  pos: "Nova versão da regra registrada, com histórico preservado",
  req: "RF-DE-02, RF-DE-18, RF-AD-02",
  principal: [
    "O analista abre a regra e visualiza suas métricas: disparos, publicações, descartes e motivos.",
    "O analista altera parâmetros em modo de simulação.",
    "O sistema executa a regra sobre janela histórica sem publicar resultado.",
    "O sistema apresenta o comparativo entre a versão vigente e a simulada.",
    "O analista aprova a alteração e registra a motivação.",
    "O sistema cria nova versão da regra e passa a aplicá-la nos ciclos seguintes.",
  ],
  alternativos: [
    "5a. O analista descarta a simulação e a regra permanece inalterada.",
  ],
  excecoes: [
    "3a. A simulação excede o tempo máximo; o sistema reduz a janela e avisa o analista.",
  ],
}));

body.push(...uc({
  cod: "UC-10", nome: "Cadastrar nova fonte de dados",
  ator: "Analista Lumen",
  objetivo: "Adicionar um portal ou base ao sistema sem escrever código novo, quando possível",
  pre: "Analista com permissão de administração de fontes",
  gatilho: "Necessidade de cobrir um ente ainda não coberto",
  pos: "Fonte cadastrada, validada e incluída no agendamento de coleta",
  req: "RF-CO-10, RF-AD-01, RNF-27",
  principal: [
    "O analista cadastra a fonte informando ente, URL base, tipo de conector e periodicidade.",
    "O analista descreve o mapeamento dos campos da fonte para o esquema canônico.",
    "O sistema executa coleta de teste em modo isolado.",
    "O sistema apresenta uma amostra do resultado normalizado para conferência.",
    "O analista confirma o mapeamento.",
    "O sistema registra a especificação, versiona e inclui a fonte no agendamento.",
  ],
  alternativos: [
    "2a. A fonte segue padrão de plataforma já suportada; o sistema sugere o mapeamento pronto e o analista apenas confirma.",
    "2b. A fonte é documento não estruturado; o sistema propõe um mapeamento assistido que o analista valida campo a campo.",
  ],
  excecoes: [
    "3a. A coleta de teste falha por indisponibilidade; o sistema mantém a fonte em rascunho e reagenda a validação.",
    "3b. A fonte não expõe dado estruturado de nenhuma forma; o analista registra a situação e o sistema gera avaliação de conformidade negativa para o ente, conforme UC-07.",
  ],
}));

body.push(...uc({
  cod: "UC-11", nome: "Registrar contestação e direito de resposta",
  ator: "Ente público ou fornecedor",
  objetivo: "Contestar um indício que considera equivocado e ter a resposta publicada",
  pre: "Indício em estado publicado",
  gatilho: "O representante aciona contestar na página do indício",
  pos: "Contestação registrada, indício marcado como contestado e tarefa de análise aberta",
  req: "RF-DR-01 a RF-DR-07",
  principal: [
    "O representante aciona contestar e identifica-se informando vínculo com o ente ou fornecedor.",
    "O representante descreve a contestação e anexa documentos comprobatórios.",
    "O sistema registra a contestação vinculada ao indício e gera protocolo.",
    "O sistema marca publicamente o indício como contestado no prazo máximo de 24 horas.",
    "O sistema abre tarefa de análise para a equipe.",
    "O analista reexecuta a regra considerando os documentos apresentados.",
    "O sistema publica o desfecho: manutenção com a resposta anexada, retificação ou remoção.",
  ],
  alternativos: [
    "7a. Confirmado erro de coleta ou cálculo do Lumen, o sistema publica errata com o mesmo destaque da publicação original.",
    "7b. Confirmado que o dado publicado pela própria fonte estava incorreto, o indício é removido e a nota de remoção explica a origem do erro.",
  ],
  excecoes: [
    "1a. O solicitante não comprova vínculo; a contestação é registrada como manifestação de terceiro e recebe tratamento distinto, sem marcar o indício.",
  ],
}));

body.push(...uc({
  cod: "UC-12", nome: "Executar ciclo de coleta",
  ator: "Sistema agendado",
  objetivo: "Obter dados novos ou atualizados de todas as fontes ativas, preservando a prova",
  pre: "Fontes ativas cadastradas e agendadas",
  gatilho: "Agendamento periódico ou disparo manual de reprocessamento",
  pos: "Artefatos brutos preservados e registros normalizados disponíveis na camada analítica",
  req: "RF-CO-01 a RF-CO-17, RF-NO-01 a RF-NO-12, RNF-09",
  principal: [
    "O orquestrador seleciona as fontes cuja janela de coleta está vencida.",
    "Para cada fonte, o sistema determina o ponto de retomada com base na última coleta bem-sucedida.",
    "O trabalhador executa a coleta respeitando o limite de taxa da fonte.",
    "O sistema grava cada artefato bruto com URL, hash, carimbo de tempo e cabeçalhos.",
    "O normalizador converte os artefatos para o esquema canônico.",
    "O sistema aplica as regras de qualidade e envia para quarentena o que não passar.",
    "O enriquecedor agrega dados societários, catálogo e grupo de pares.",
    "O sistema atualiza o painel operacional com o resultado do ciclo.",
  ],
  alternativos: [
    "2a. É um reprocessamento integral; o sistema lê da camada bruta e pula a etapa de coleta externa.",
  ],
  excecoes: [
    "3a. A fonte retorna erro temporário; o sistema retenta com espera exponencial dentro do limite configurado.",
    "3b. A fonte permanece indisponível após todas as tentativas; o sistema registra a falha, alarma e prossegue com as demais fontes.",
    "5a. O esquema da fonte mudou; o sistema preserva o bruto, interrompe a normalização apenas daquela fonte e alarma para intervenção.",
  ],
}));

body.push(...uc({
  cod: "UC-13", nome: "Executar ciclo de detecção",
  ator: "Sistema agendado",
  objetivo: "Aplicar o catálogo de regras sobre a base atualizada e produzir indícios",
  pre: "Ciclo de coleta concluído e camada analítica atualizada",
  gatilho: "Agendamento posterior ao ciclo de coleta",
  pos: "Indícios criados nos estados detectado ou em revisão, com trilha de evidência completa",
  req: "RF-DE-01 a RF-DE-19, RNF-04",
  principal: [
    "O orquestrador carrega o catálogo de regras ativas com suas versões vigentes.",
    "O sistema executa cada regra sobre o recorte de dados aplicável.",
    "Para cada disparo, o sistema monta a trilha de evidência com regra, versão, parâmetros e dados de entrada.",
    "O sistema vincula os documentos fonte correspondentes.",
    "O sistema calcula o score composto e a severidade.",
    "Indícios abaixo do limiar são descartados com registro do motivo.",
    "Indícios acima do limiar entram na fila de revisão humana.",
    "O sistema atualiza as métricas por regra para acompanhamento de calibração.",
  ],
  alternativos: [
    "2a. Execução em modo simulação, disparada pelo UC-09; nenhum indício é persistido como publicável.",
  ],
  excecoes: [
    "2a. Uma regra falha na execução; o sistema registra o erro, isola aquela regra e conclui o ciclo com as demais.",
    "5a. Dados insuficientes para calcular a referência estatística; a regra não dispara e o motivo é registrado.",
  ],
}));

body.push(...uc({
  cod: "UC-14", nome: "Consumir API pública",
  ator: "Jornalista, Pesquisador, Órgão de controle",
  objetivo: "Integrar os dados do Lumen a sistemas próprios de forma programática",
  pre: "Chave de acesso emitida quando aplicável",
  gatilho: "Requisição HTTP à API",
  pos: "Resposta entregue dentro dos limites de taxa, com metadados de proveniência",
  req: "RF-PU-08, RNF-02",
  principal: [
    "O consumidor consulta a documentação e obtém chave de acesso, quando exigida.",
    "O consumidor envia requisição a um recurso versionado.",
    "O sistema valida a chave e o limite de taxa.",
    "O sistema retorna os dados com paginação, data da última coleta e identificação da versão do esquema.",
    "Recursos de indício retornam também a regra, a versão e as referências de documento fonte.",
  ],
  alternativos: [
    "2a. Consulta a recurso público sem necessidade de chave, sujeita a limite de taxa mais restrito.",
  ],
  excecoes: [
    "3a. Limite de taxa excedido; o sistema responde com código apropriado e indica o tempo de espera.",
    "4a. Consulta muito ampla; o sistema orienta o uso das exportações em massa em vez da API de consulta.",
  ],
}));

body.push(pageBreak());
body.push(h1("3. Regras de negócio transversais"));
body.push(p("As regras abaixo valem para todos os casos de uso e não se repetem em cada um."));
body.push(table(["Cód.", "Regra de negócio"], [1100, 8500], [
  ["RN-01", "Nenhum texto exibido ao público pode afirmar ou sugerir a ocorrência de ilícito; aplica-se o vocabulário controlado do DOC-08."],
  ["RN-02", "Nenhum indício é publicado sem documento fonte armazenado e com hash verificável."],
  ["RN-03", "Indício com severidade alta exige revisão humana antes da publicação, sem exceção."],
  ["RN-04", "Toda decisão humana sobre um indício é registrada em trilha de auditoria somente-anexação."],
  ["RN-05", "Contestação registrada por representante identificado marca o indício como contestado em até 24 horas."],
  ["RN-06", "Errata e remoção são publicadas no mesmo canal e com o mesmo destaque da publicação original."],
  ["RN-07", "Ausência de publicação obrigatória por parte do ente gera avaliação de conformidade, não erro de sistema."],
  ["RN-08", "Documentos de pessoa física são mascarados em qualquer exibição, exportação ou dossiê."],
  ["RN-09", "Critérios de detecção são idênticos para todos os entes, sem exceção por porte, região ou vinculação política."],
  ["RN-10", "Toda visualização de dado informa a data da última coleta bem-sucedida da fonte correspondente."],
]));

L.buildDoc({
  codigo: "DOC-03",
  titulo: "Casos de Uso",
  subtitulo: "Atores, fluxos principais, alternativos e exceções",
  body,
  outFile: "../docs/DOC-03_Casos_de_Uso.docx",
});
