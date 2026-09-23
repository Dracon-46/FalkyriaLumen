const L = require("./lib");
const { h1, h2, h3, p, bullet, numbered, table, callout, code, figure, pageBreak, spacer } = L;

const body = [];

body.push(callout("Natureza deste documento", [
  "Este documento consolida a política interna do projeto e o entendimento que fundamenta suas escolhas " +
  "de desenho. Ele não é parecer jurídico e não substitui a orientação de advogado.",
  "Antes de a primeira publicação ir ao ar, a política aqui descrita deve ser revisada por advogado com " +
  "atuação em direito digital e responsabilidade civil, e o fluxo de direito de resposta deve ser " +
  "validado por esse profissional.",
], "red"));

body.push(h1("1. Base legal para coletar, tratar e republicar"));
body.push(p("O projeto trabalha com dados que a própria legislação determina que sejam públicos. Essa " +
  "é a diferença fundamental entre o Lumen e um sistema que obtivesse informação por meios reservados: " +
  "aqui, a publicidade é a regra imposta ao ente, e o sistema apenas a torna utilizável."));
body.push(table(["Fundamento", "O que estabelece", "Relevância para o projeto"], [2300, 3800, 3500], [
  ["Constituição Federal, art. 37", "Publicidade como princípio da administração pública",
    "Fundamento geral da publicidade dos atos administrativos"],
  ["Lei 12.527/2011", "Lei de Acesso à Informação; acesso como regra e sigilo como exceção",
    "Autoriza o acesso e estabelece o dever de transparência ativa"],
  ["Lei Complementar 131/2009", "Divulgação em tempo real da execução orçamentária e financeira",
    "Fundamenta a exigência de atualidade usada no índice de conformidade"],
  ["Lei 14.133/2021, art. 174", "Cria o PNCP para divulgação centralizada das contratações",
    "Base da obrigatoriedade de publicação que sustenta a cobertura nacional"],
  ["Decreto 8.777/2016", "Política de Dados Abertos do Executivo federal",
    "Ampara expressamente a livre utilização dos dados das APIs federais"],
  ["Lei 13.709/2018", "Lei Geral de Proteção de Dados",
    "Aplica-se aos dados pessoais presentes nas bases, mesmo públicas"],
]));

body.push(h1("2. Onde está o risco de verdade"));
body.push(p("Coletar e republicar dado público, com atribuição de fonte, é atividade de baixo risco. O " +
  "risco do projeto não está na coleta nem na republicação: está na camada de interpretação. É o " +
  "momento em que o sistema deixa de dizer este contrato custou X e passa a dizer ou sugerir algo sobre " +
  "a conduta de quem o assinou."));
body.push(table(["Situação", "Risco", "Como o Lumen o neutraliza"], [2400, 3300, 3900], [
  ["Republicar contrato público com fonte citada", "Muito baixo",
    "Atribuição de fonte, link e hash em todo registro"],
  ["Afirmar que um valor está acima da mediana", "Baixo",
    "Afirmação verificável, com a referência explicitada e reprodutível"],
  ["Afirmar ou sugerir que houve desvio ou fraude", "Alto",
    "Proibido em qualquer campo; bloqueado por verificação automática"],
  ["Rotular pessoa ou empresa como suspeita", "Alto",
    "Vocabulário controlado veda o termo; o rótulo recai sobre a atividade, nunca sobre a pessoa"],
  ["Publicar indício com dado de origem incorreto", "Alto",
    "Revisão humana confere o documento fonte antes da publicação; errata com mesmo destaque"],
  ["Ordenar entes por pontuação de risco", "Alto",
    "Não existe ranking de risco; a ordenação pública é por conformidade objetiva"],
  ["Cruzar doação eleitoral e apresentar como nexo", "Alto",
    "Família K nunca publica isoladamente e não afirma nexo causal"],
]));
body.push(p("No ordenamento brasileiro, imputar falsamente a alguém fato definido como crime, ou fato " +
  "ofensivo à reputação, atrai responsabilização penal e civil, e a jurisprudência consolidada reconhece " +
  "que pessoa jurídica também pode sofrer dano à sua reputação. É precisamente por isso que o projeto " +
  "adota como restrição de engenharia, e não apenas como recomendação editorial, a proibição de " +
  "qualquer linguagem que impute conduta ilícita."));

body.push(pageBreak());
body.push(h1("3. Vocabulário controlado"));
body.push(p("A tabela abaixo é normativa e está implementada como verificação automática. Nenhum termo " +
  "da coluna proibida pode aparecer em texto destinado ao público: interface, explicação de regra, " +
  "título de indício, nome de campo exibido, mensagem de erro, rótulo de gráfico, dossiê exportado, " +
  "resposta de API ou publicação em rede social."));
body.push(table(["Proibido", "Substituição obrigatória"], [3800, 5800], [
  ["desvio, desvio de verba", "valor em análise; atividade sinalizada para análise"],
  ["fraude, fraudulento", "padrão atípico identificado"],
  ["superfaturamento, superfaturado", "preço acima da referência comparada"],
  ["corrupção, corrupto", "não há substituição; o termo simplesmente não é utilizado"],
  ["suspeito, suspeita (como qualificação)", "atividade para análise"],
  ["irregular, irregularidade", "divergência em relação ao parâmetro legal ou estatístico"],
  ["ilegal, ilícito", "distinto do previsto no dispositivo citado"],
  ["crime, criminoso", "não há substituição; o termo simplesmente não é utilizado"],
  ["culpado, responsável por (com sentido de culpa)", "signatário do ato; agente que autorizou"],
  ["lavagem, propina, superfatura", "não há substituição; os termos não são utilizados"],
  ["esquema, organização", "conjunto de contratações relacionadas"],
  ["denúncia, denunciar", "sinalização; registro para análise"],
  ["acusado, investigado", "ente analisado; fornecedor analisado"],
]));

body.push(h2("3.1 Construções de frase aprovadas"));
body.push(p("Além do controle de termos isolados, o projeto padroniza a estrutura das frases que " +
  "descrevem um indício. O modelo canônico é: fato observado, referência comparada, distância entre " +
  "ambos e convite à verificação. Nunca inferência sobre intenção."));
body.push(code([
  "APROVADO:",
  "\"O preco unitario contratado foi de R$ 48,00. A mediana observada para",
  " este item no mesmo trimestre, entre 412 contratacoes de outros entes,",
  " foi de R$ 11,20. O valor esta 4,3 vezes acima dessa referencia.",
  " Documento fonte disponivel para verificacao.\"",
  "",
  "REPROVADO:",
  "\"Prefeitura pagou R$ 48,00 em item que custa R$ 11,20, indicando",
  " superfaturamento de mais de 300%.\"",
  "   -> imputa conduta; usa termo proibido; conclui em vez de descrever",
  "",
  "APROVADO:",
  "\"Foram identificadas 14 contratacoes diretas com o mesmo fornecedor,",
  " para objetos de descricao similar, no intervalo de 180 dias, somando",
  " R$ 218.400,00. O limite legal para dispensa por valor nesta categoria,",
  " na data dos atos, era de R$ 65.492,11. O ato foi autorizado por",
  " [nome do agente conforme publicado], com fundamento no art. 75, II.\"",
  "",
  "REPROVADO:",
  "\"Prefeito fatiou compras para fugir de licitacao.\"",
  "   -> imputa intencao e conduta ilicita; linguagem conclusiva",
]));

body.push(callout("O caso mais delicado: nomear quem autorizou", [
  "O projeto registra e exibe o nome do agente público signatário do ato, porque isso é dado público " +
  "do exercício da função e responde diretamente ao requisito de mostrar quem fez.",
  "A diferença entre informar e acusar está inteiramente na construção da frase. Dizer que o ato foi " +
  "assinado por determinada autoridade, com fundamento em determinado dispositivo, é reproduzir o que o " +
  "próprio ente publicou. Dizer que essa autoridade autorizou irregularmente é conclusão que o Lumen " +
  "não tem competência nem elementos para emitir.",
  "Por isso o nome do agente aparece sempre no campo de fato administrativo, jamais no título ou no " +
  "resumo do indício, e nunca é acompanhado de adjetivo.",
], "amber"));

body.push(pageBreak());
body.push(h1("4. Regras de publicação"));
body.push(table(["Cód.", "Regra"], [1100, 8500], [
  ["PUB-01", "Todo indício exibe o rótulo padronizado de atividade para análise, em posição de destaque e antes de qualquer outro conteúdo."]  ,
  ["PUB-02", "Todo indício exibe a regra aplicada, sua versão, seus parâmetros e a referência comparada."],
  ["PUB-03", "Todo indício exibe pelo menos um documento fonte com link, hash e data de coleta."],
  ["PUB-04", "Nenhum indício é publicado sem que o documento fonte esteja armazenado e íntegro."],
  ["PUB-05", "Indícios de severidade alta exigem aprovação de dois analistas distintos."],
  ["PUB-06", "O nome de agente público aparece apenas como signatário do ato, sem adjetivação."],
  ["PUB-07", "Não existe ranking público de entes por pontuação de risco; a ordenação pública é por conformidade objetiva."],
  ["PUB-08", "Toda página pública exibe o aviso metodológico e o link para a metodologia completa."],
  ["PUB-09", "Erratas e remoções são publicadas no mesmo canal, no mesmo formato e com o mesmo destaque da publicação original."],
  ["PUB-10", "Comunicação em redes sociais segue exatamente o mesmo vocabulário controlado, sem exceção para linguagem informal."],
  ["PUB-11", "Nenhum indício é publicado enquanto houver contestação pendente de análise que alegue erro de dado."],
  ["PUB-12", "Critérios de detecção e publicação são idênticos para todos os entes, sem distinção de porte, região ou vinculação política."],
]));

body.push(h1("5. Proteção de dados pessoais"));
body.push(h2("5.1 Classificação adotada"));
body.push(table(["Categoria", "Exemplos", "Tratamento"], [2300, 3500, 3800], [
  ["Ato administrativo", "Número de contrato, objeto, valor, data, modalidade",
    "Publicação integral; não são dados pessoais"],
  ["Pessoa jurídica", "CNPJ, razão social, CNAE, capital social, quadro societário",
    "Publicação conforme divulgado nas bases públicas de origem"],
  ["Agente público na função", "Nome e cargo do signatário do ato",
    "Publicação restrita ao vínculo com o ato, sem adjetivação e sem perfil"],
  ["Documento de pessoa física", "CPF em qualquer contexto",
    "Mascarado em exibição, exportação, dossiê e resposta de API"],
  ["Cidadão beneficiário", "Beneficiários de programas sociais",
    "Fora de escopo; tratamento apenas agregado, nunca individual"],
  ["Dado sensível", "Qualquer dado do art. 5º, II da LGPD",
    "Não coletado; descartado na normalização caso apareça em fonte"],
]));

body.push(h2("5.2 Princípios operacionais"));
body.push(bullet("Minimização: campos que não alimentam nenhuma regra ativa nem visualização pública não " +
  "são promovidos da camada bruta para a camada consultável."));
body.push(bullet("Finalidade declarada: o tratamento se destina a controle social do gasto público, e essa " +
  "finalidade é declarada publicamente."));
body.push(bullet("Mascaramento na origem: a máscara de documentos é aplicada no estágio de normalização, " +
  "e não na exibição, de modo que o dado sem máscara não circula pelas camadas consultáveis."));
body.push(bullet("Canal de titular: existe procedimento documentado para receber e responder solicitações " +
  "de titulares de dados, com prazo definido."));
body.push(bullet("Registro de tratamento: cada categoria de dado tem sua base legal documentada e vinculada."));

body.push(pageBreak());
body.push(h1("6. Direito de resposta"));
body.push(p("O direito de resposta não é concessão do projeto: é parte da sua arquitetura e do seu " +
  "controle de qualidade. Um ente que contesta um indício frequentemente traz informação que o sistema " +
  "não tinha, e essa informação melhora as regras."));
body.push(...figure("10_direito_resposta.png", "Figura 1. Fluxo de contestação, da manifestação ao desfecho publicado.", 600));

body.push(h2("6.1 Compromissos de prazo"));
body.push(table(["Etapa", "Prazo máximo", "Responsável"], [3400, 2400, 3800], [
  ["Marcação pública do indício como contestado", "24 horas do registro", "Automático"],
  ["Confirmação de recebimento com protocolo", "24 horas", "Automático"],
  ["Análise da contestação e desfecho", "15 dias corridos", "Analista Lumen"],
  ["Publicação de errata quando houver erro do sistema", "48 horas da constatação", "Analista Lumen"],
  ["Remoção quando o dado de origem estava incorreto", "48 horas da constatação", "Analista Lumen"],
]));

body.push(h2("6.2 Desfechos possíveis"));
body.push(table(["Desfecho", "Quando se aplica", "Efeito público"], [1800, 4200, 3600], [
  ["Mantido", "A contestação não afasta o que foi observado",
    "Indício permanece com a contestação exibida ao lado, em igual destaque"],
  ["Retificado", "Houve erro de coleta ou de cálculo do Lumen",
    "Indício corrigido e errata publicada com o mesmo destaque"],
  ["Removido", "O dado publicado pela própria fonte estava incorreto",
    "Indício removido e nota explicando a origem do erro"],
]));
body.push(callout("Assimetria deliberada", [
  "O projeto adota postura assimétrica em favor de quem contesta. A marcação pública de contestação é " +
  "automática e imediata, sem análise prévia de mérito, enquanto a manutenção do indício exige análise " +
  "completa. Publicar rápido e corrigir devagar seria incompatível com os princípios do projeto.",
], "blue"));

body.push(h1("7. Governança editorial"));
body.push(table(["Instância", "Composição", "Competência"], [2200, 3400, 4000], [
  ["Revisão de primeira linha", "Analista de plantão",
    "Aprovar ou descartar indício de severidade média"],
  ["Revisão de segunda linha", "Dois analistas distintos",
    "Aprovar indício de severidade alta; nenhum aprova sozinho"],
  ["Comitê de metodologia", "Responsável técnico e revisores seniores",
    "Aprovar regra nova, mudança de limiar e texto de explicação pública"],
  ["Consulta jurídica", "Advogado externo",
    "Avaliar caso limite, contestação com ameaça de medida judicial e revisão anual da política"],
]));

body.push(h2("7.1 Situações que exigem escalonamento obrigatório"));
body.push(bullet("Contestação acompanhada de notificação extrajudicial ou ameaça de medida judicial."));
body.push(bullet("Indício que envolva agente público em exercício de mandato eletivo em período eleitoral."));
body.push(bullet("Pedido de remoção de conteúdo por qualquer via."));
body.push(bullet("Solicitação de titular de dados relativa a informação publicada."));
body.push(bullet("Cobertura jornalística que atribua ao Lumen conclusão que ele não emitiu, hipótese em que " +
  "cabe pedido público de retificação por parte do próprio projeto."));

body.push(callout("O risco reputacional invertido", [
  "Um risco frequentemente esquecido é o de terceiros atribuírem ao Lumen conclusões que ele nunca " +
  "emitiu. Uma manchete afirmando que o sistema apontou desvio em determinado município compromete a " +
  "credibilidade do projeto tanto quanto um erro próprio.",
  "Por isso o material de imprensa do projeto sempre inclui a formulação padronizada do que um indício " +
  "significa e do que ele não significa, e a equipe solicita retificação quando a atribuição incorreta " +
  "é relevante.",
], "amber"));

body.push(h1("8. Revisão periódica"));
body.push(numbered("A lista de vocabulário controlado é revista a cada seis meses e sempre que um caso " +
  "concreto revelar termo não previsto."));
body.push(numbered("A política inteira é revista anualmente com apoio jurídico externo."));
body.push(numbered("Métricas de contestação, taxa de manutenção, retificação e remoção são publicadas " +
  "trimestralmente, como forma de prestação de contas do próprio projeto."));
body.push(numbered("Toda alteração desta política é versionada, com registro do motivo e da data de vigência."));

L.buildDoc({
  codigo: "DOC-08",
  titulo: "Política Jurídica e Editorial",
  subtitulo: "Base legal, vocabulário controlado, proteção de dados e direito de resposta",
  body,
  outFile: "../docs/DOC-08_Politica_Juridica_e_Editorial.docx",
});
