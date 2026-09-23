const L = require("./lib");
const { h1, h2, h3, p, bullet, numbered, table, callout, code, figure, pageBreak, spacer } = L;

const body = [];

function dic(entidade, descricao, campos) {
  const out = [];
  out.push(h3(entidade));
  out.push(p(descricao));
  out.push(table(["Campo", "Tipo", "Obrig.", "Descrição e origem"], [2100, 1300, 900, 5300], campos));
  out.push(spacer(140));
  return out;
}

body.push(h1("1. Princípios do modelo"));
body.push(numbered("Existe um único esquema canônico. Toda fonte converge para ele, e nenhuma " +
  "particularidade de fonte vaza para o modelo."));
body.push(numbered("Todo registro carrega proveniência. É sempre possível responder de qual artefato " +
  "bruto aquele dado veio e quando foi coletado."));
body.push(numbered("O modelo separa o fato administrativo da interpretação. Contrato, empenho e ato " +
  "autorizativo são fatos publicados. Indício é interpretação do sistema, e vive em entidades próprias."));
body.push(numbered("Campos ausentes são explicitamente nulos e nunca preenchidos por inferência. " +
  "Ausência é informação e alimenta o índice de conformidade."));
body.push(numbered("Todo campo possui classificação de sensibilidade, que governa exibição, exportação e " +
  "retenção."));

body.push(h1("2. Diagrama entidade-relacionamento"));
body.push(...figure("05_der.png", "Figura 1. Modelo canônico: entidades de fato administrativo, entidades de análise e cadeia de evidência.", 600));

body.push(h2("2.1 Os três blocos do modelo"));
body.push(table(["Bloco", "Entidades", "Natureza"], [1900, 4300, 3400], [
  ["Fato administrativo", "Ente, UnidadeGestora, ProcessoContratacao, Contrato, Aditivo, ItemContratado, Empenho, Liquidacao, Pagamento, AtoAutorizativo, AmparoLegal, AgentePublico",
    "Reflete o que o ente publicou; o Lumen não altera nem interpreta"],
  ["Contexto", "Fornecedor, Socio, Sancao, CatalogoItem, GrupoPares",
    "Enriquecimento a partir de outras bases públicas"],
  ["Análise e prova", "Indicio, RegraDeteccao, Evidencia, DocumentoFonte, Contestacao, Conformidade",
    "Produzido pelo Lumen; sempre rastreável até o fato"],
]));

body.push(callout("A entidade que atende ao requisito de quem autorizou e por quê", [
  "AtoAutorizativo é a entidade que liga um processo de contratação a um AgentePublico identificado e " +
  "a um AmparoLegal. O campo justificativa_publicada recebe, sem edição, o texto de justificativa " +
  "divulgado pelo próprio ente. O sistema nunca redige, resume ou interpreta esse texto: apenas o " +
  "preserva e o exibe ao lado do dispositivo legal invocado.",
], "blue"));

body.push(pageBreak());
body.push(h1("3. Dicionário de dados"));
body.push(p("Notação de sensibilidade usada na coluna de descrição: P indica dado público de ato " +
  "administrativo; PA indica dado de agente público no exercício da função; S indica dado sensível " +
  "sujeito a mascaramento."));

body.push(h2("3.1 Bloco de fato administrativo"));

body.push(...dic("Ente", "Unidade da federação ou órgão público analisado. Chave natural é o código IBGE para municípios e o CNPJ para os demais.", [
  ["id", "UUID", "Sim", "Identificador interno"],
  ["cnpj", "CHAR(14)", "Não", "CNPJ do ente quando publicado (P)"],
  ["codigo_ibge", "CHAR(7)", "Não", "Código IBGE para municípios e estados (P)"],
  ["nome", "TEXT", "Sim", "Nome oficial do ente (P)"],
  ["esfera", "ENUM", "Sim", "uniao, estadual, municipal, distrital"],
  ["poder", "ENUM", "Sim", "executivo, legislativo, judiciario, autonomo"],
  ["uf", "CHAR(2)", "Não", "Unidade federativa"],
  ["populacao", "INTEGER", "Não", "População estimada, base IBGE, usada no grupo de pares"],
  ["porte", "ENUM", "Não", "Faixa populacional derivada"],
  ["receita_corrente_liquida", "NUMERIC", "Não", "Origem SICONFI; usada no grupo de pares"],
  ["grupo_pares_id", "UUID", "Não", "Grupo de comparação calculado"],
]));

body.push(...dic("ProcessoContratacao", "Processo que antecede o contrato: licitação, dispensa ou inexigibilidade. Principal origem é o PNCP.", [
  ["id", "UUID", "Sim", "Identificador interno"],
  ["ente_id", "UUID", "Sim", "Ente responsável"],
  ["unidade_gestora_id", "UUID", "Não", "Unidade que conduziu o processo"],
  ["numero", "TEXT", "Sim", "Número do processo na origem (P)"],
  ["ano", "SMALLINT", "Sim", "Exercício"],
  ["modalidade", "ENUM", "Sim", "pregao, concorrencia, dispensa, inexigibilidade, concurso, leilao, dialogo"],
  ["amparo_legal_id", "UUID", "Não", "Dispositivo invocado; campo estruturado no PNCP"],
  ["objeto", "TEXT", "Sim", "Descrição do objeto conforme publicada (P)"],
  ["valor_estimado", "NUMERIC", "Não", "Valor estimado publicado"],
  ["data_publicacao", "DATE", "Sim", "Data de publicação na origem"],
  ["data_abertura_propostas", "DATE", "Não", "Usada para verificar prazos legais mínimos"],
  ["quantidade_participantes", "INTEGER", "Não", "Número de propostas; insumo de regras de concorrência"],
  ["documento_fonte_id", "UUID", "Sim", "Artefato bruto que originou o registro"],
]));

body.push(...dic("AtoAutorizativo", "Ato pelo qual um agente público autoriza a contratação ou a despesa. Atende diretamente ao requisito de registrar quem autorizou e com que fundamento.", [
  ["id", "UUID", "Sim", "Identificador interno"],
  ["processo_id", "UUID", "Não", "Processo de contratação vinculado"],
  ["contrato_id", "UUID", "Não", "Contrato vinculado, quando o ato é posterior"],
  ["tipo", "ENUM", "Sim", "autorizacao, homologacao, ratificacao, adjudicacao, ordenacao_despesa"],
  ["agente_id", "UUID", "Não", "Agente público signatário (PA)"],
  ["data", "DATE", "Sim", "Data do ato"],
  ["amparo_legal_id", "UUID", "Não", "Dispositivo legal invocado no ato"],
  ["justificativa_publicada", "TEXT", "Não", "Texto de justificativa exatamente como publicado, sem edição (P)"],
  ["documento_fonte_id", "UUID", "Sim", "Artefato bruto que originou o registro"],
]));

body.push(...dic("AgentePublico", "Agente que assinou atos administrativos. Registra-se apenas o que é publicado no exercício da função. Não há construção de perfil comportamental.", [
  ["id", "UUID", "Sim", "Identificador interno"],
  ["nome", "TEXT", "Sim", "Nome conforme publicado no ato (PA)"],
  ["cargo", "TEXT", "Não", "Cargo ou função declarada no ato (PA)"],
  ["ente_id", "UUID", "Não", "Ente ao qual o ato se vincula"],
  ["documento_mascarado", "TEXT", "Não", "CPF mascarado quando publicado pela fonte (S)"],
]));

body.push(...dic("Contrato", "Instrumento firmado entre ente e fornecedor.", [
  ["id", "UUID", "Sim", "Identificador interno"],
  ["processo_id", "UUID", "Não", "Processo de origem"],
  ["ente_id", "UUID", "Sim", "Ente contratante"],
  ["fornecedor_id", "UUID", "Sim", "Contratado"],
  ["numero", "TEXT", "Sim", "Número do contrato na origem (P)"],
  ["objeto", "TEXT", "Sim", "Objeto conforme publicado (P)"],
  ["valor_inicial", "NUMERIC", "Sim", "Valor na assinatura"],
  ["valor_atual", "NUMERIC", "Sim", "Valor após aditivos"],
  ["data_assinatura", "DATE", "Sim", "Data de assinatura"],
  ["vigencia_inicio", "DATE", "Não", "Início da vigência"],
  ["vigencia_fim", "DATE", "Não", "Fim da vigência"],
  ["situacao", "ENUM", "Não", "vigente, encerrado, rescindido, suspenso"],
  ["documento_fonte_id", "UUID", "Sim", "Artefato bruto que originou o registro"],
]));

body.push(...dic("ItemContratado", "Item individual de um contrato. É a entidade mais volumosa do modelo e a base das regras de preço.", [
  ["id", "UUID", "Sim", "Identificador interno"],
  ["contrato_id", "UUID", "Sim", "Contrato ao qual pertence"],
  ["descricao_original", "TEXT", "Sim", "Descrição exatamente como publicada (P)"],
  ["catalogo_item_id", "UUID", "Não", "Classificação normalizada, base CATMAT ou CATSER"],
  ["quantidade", "NUMERIC", "Não", "Quantidade contratada"],
  ["unidade_medida", "TEXT", "Não", "Unidade normalizada"],
  ["valor_unitario", "NUMERIC", "Não", "Preço unitário; base das regras da família A"],
  ["valor_total", "NUMERIC", "Não", "Valor total do item"],
]));

body.push(...dic("Empenho", "Primeiro estágio da despesa. Liquidacao e Pagamento seguem estrutura análoga e encadeada.", [
  ["id", "UUID", "Sim", "Identificador interno"],
  ["ente_id", "UUID", "Sim", "Ente responsável"],
  ["contrato_id", "UUID", "Não", "Contrato vinculado, quando existir"],
  ["fornecedor_id", "UUID", "Não", "Credor"],
  ["numero", "TEXT", "Sim", "Número do empenho na origem (P)"],
  ["data", "DATE", "Sim", "Data de emissão; base das regras de sazonalidade"],
  ["valor", "NUMERIC", "Sim", "Valor empenhado; base das regras de fracionamento e Benford"],
  ["elemento_despesa", "TEXT", "Não", "Classificação orçamentária"],
  ["funcao", "TEXT", "Não", "Função de governo"],
  ["subfuncao", "TEXT", "Não", "Subfunção de governo"],
  ["modalidade_licitacao", "TEXT", "Não", "Modalidade declarada no empenho"],
  ["documento_fonte_id", "UUID", "Sim", "Artefato bruto que originou o registro"],
]));

body.push(pageBreak());
body.push(h2("3.2 Bloco de contexto"));

body.push(...dic("Fornecedor", "Pessoa jurídica ou física contratada. Enriquecido com a base pública de CNPJ da Receita Federal.", [
  ["id", "UUID", "Sim", "Identificador interno"],
  ["cnpj_cpf", "TEXT", "Sim", "Documento; CPF sempre mascarado na exibição (S quando PF)"],
  ["razao_social", "TEXT", "Sim", "Razão social (P)"],
  ["nome_fantasia", "TEXT", "Não", "Nome fantasia (P)"],
  ["data_abertura", "DATE", "Não", "Base da regra de empresa recém-constituída"],
  ["capital_social", "NUMERIC", "Não", "Base da regra de desproporção entre capital e contrato"],
  ["cnae_principal", "CHAR(7)", "Não", "Base da regra de incompatibilidade de objeto"],
  ["porte", "ENUM", "Não", "MEI, ME, EPP, demais"],
  ["situacao_cadastral", "TEXT", "Não", "Situação na Receita Federal na data da consulta"],
  ["endereco_hash", "TEXT", "Não", "Hash do endereço normalizado, para detectar coincidência sem expor o endereço"],
]));

body.push(...dic("Sancao", "Registro de sanção administrativa vigente, obtido dos cadastros federais.", [
  ["id", "UUID", "Sim", "Identificador interno"],
  ["fornecedor_id", "UUID", "Sim", "Sancionado"],
  ["cadastro", "ENUM", "Sim", "CEIS, CNEP, CEPIM"],
  ["tipo", "TEXT", "Sim", "Tipo de sanção conforme o cadastro (P)"],
  ["orgao_sancionador", "TEXT", "Não", "Órgão que aplicou (P)"],
  ["data_inicio", "DATE", "Sim", "Início da vigência; essencial para avaliar a data do contrato"],
  ["data_fim", "DATE", "Não", "Fim da vigência"],
]));

body.push(...dic("GrupoPares", "Conjunto de entes comparáveis, recalculado periodicamente.", [
  ["id", "UUID", "Sim", "Identificador interno"],
  ["criterios", "JSONB", "Sim", "Critérios que definiram o grupo, para reprodutibilidade"],
  ["faixa_populacional", "TEXT", "Não", "Faixa usada"],
  ["regiao", "TEXT", "Não", "Região usada"],
  ["quantidade_entes", "INTEGER", "Sim", "Tamanho do grupo; abaixo do mínimo estatístico gera ressalva"],
  ["calculado_em", "TIMESTAMP", "Sim", "Data do cálculo"],
]));

body.push(h2("3.3 Bloco de análise e prova"));

body.push(...dic("DocumentoFonte", "Artefato bruto preservado na camada bronze. É a prova que sustenta qualquer afirmação do sistema.", [
  ["id", "UUID", "Sim", "Identificador interno"],
  ["url_origem", "TEXT", "Sim", "URL efetiva após redirecionamentos"],
  ["caminho_objeto", "TEXT", "Sim", "Localização no armazenamento de objetos"],
  ["sha256", "CHAR(64)", "Sim", "Hash do conteúdo; reconferido a cada leitura"],
  ["formato", "TEXT", "Sim", "Tipo de mídia recebido"],
  ["tamanho_bytes", "BIGINT", "Sim", "Tamanho do artefato"],
  ["coletado_em", "TIMESTAMP", "Sim", "Momento exato da coleta"],
  ["cabecalhos", "JSONB", "Não", "Cabeçalhos de resposta relevantes"],
  ["fonte_id", "UUID", "Sim", "Fonte cadastrada que originou a coleta"],
  ["versao", "INTEGER", "Sim", "Versão da coleta desta URL; nunca sobrescreve a anterior"],
]));

body.push(...dic("RegraDeteccao", "Definição versionada de uma regra do catálogo do DOC-07.", [
  ["codigo", "TEXT", "Sim", "Código estável, por exemplo B-01"],
  ["versao", "INTEGER", "Sim", "Versão; alterações de parâmetro geram nova versão"],
  ["familia", "CHAR(1)", "Sim", "Família do catálogo, de A a K"],
  ["titulo", "TEXT", "Sim", "Título em linguagem neutra"],
  ["explicacao_publica", "TEXT", "Sim", "Explicação acessível exibida ao cidadão"],
  ["parametros", "JSONB", "Sim", "Parâmetros vigentes desta versão"],
  ["severidade_base", "ENUM", "Sim", "baixa, media, alta"],
  ["ativa", "BOOLEAN", "Sim", "Se participa dos ciclos de detecção"],
  ["vigente_desde", "TIMESTAMP", "Sim", "Início de vigência da versão"],
]));

body.push(...dic("Indicio", "Sinalização produzida por uma regra. Nunca contém conclusão sobre licitude.", [
  ["id", "UUID", "Sim", "Identificador interno"],
  ["regra_codigo", "TEXT", "Sim", "Regra que produziu"],
  ["regra_versao", "INTEGER", "Sim", "Versão exata da regra na execução"],
  ["ente_id", "UUID", "Sim", "Ente relacionado"],
  ["alvo_tipo", "ENUM", "Sim", "contrato, empenho, processo, fornecedor_no_ente, ente"],
  ["alvo_id", "UUID", "Sim", "Identificador do objeto analisado"],
  ["score", "NUMERIC", "Sim", "Score composto normalizado entre 0 e 1"],
  ["severidade", "ENUM", "Sim", "baixa, media, alta"],
  ["estado", "ENUM", "Sim", "Conforme a máquina de estados da seção 4"],
  ["parametros_aplicados", "JSONB", "Sim", "Parâmetros efetivamente usados nesta execução"],
  ["valores_observados", "JSONB", "Sim", "Valores que dispararam a regra e a referência comparada"],
  ["explicacao", "TEXT", "Sim", "Texto neutro gerado a partir de modelo aprovado"],
  ["detectado_em", "TIMESTAMP", "Sim", "Momento da detecção"],
  ["revisado_por", "TEXT", "Não", "Analista responsável pela decisão"],
  ["justificativa_decisao", "TEXT", "Não", "Motivo registrado da publicação ou do descarte"],
]));

body.push(...dic("Evidencia", "Vínculo entre um indício e os documentos que o sustentam. Um indício sem evidência não pode ser publicado.", [
  ["id", "UUID", "Sim", "Identificador interno"],
  ["indicio_id", "UUID", "Sim", "Indício sustentado"],
  ["documento_fonte_id", "UUID", "Sim", "Documento que sustenta"],
  ["papel", "ENUM", "Sim", "principal, comparacao, contexto"],
  ["trecho_referencia", "TEXT", "Não", "Localização do trecho relevante dentro do documento"],
]));

body.push(...dic("Contestacao", "Manifestação formal de ente ou fornecedor sobre um indício publicado.", [
  ["id", "UUID", "Sim", "Identificador interno"],
  ["indicio_id", "UUID", "Sim", "Indício contestado"],
  ["protocolo", "TEXT", "Sim", "Protocolo público da contestação"],
  ["origem", "ENUM", "Sim", "ente, fornecedor, terceiro"],
  ["vinculo_comprovado", "BOOLEAN", "Sim", "Se o solicitante comprovou vínculo"],
  ["texto", "TEXT", "Sim", "Manifestação como enviada, sem edição"],
  ["documentos", "JSONB", "Não", "Anexos apresentados"],
  ["recebida_em", "TIMESTAMP", "Sim", "Data de recebimento"],
  ["marcada_publicamente_em", "TIMESTAMP", "Não", "Quando o indício passou a exibir a marcação"],
  ["desfecho", "ENUM", "Não", "mantido, retificado, removido"],
]));

body.push(...dic("Conformidade", "Avaliação do cumprimento das obrigações legais de publicação por um ente.", [
  ["id", "UUID", "Sim", "Identificador interno"],
  ["ente_id", "UUID", "Sim", "Ente avaliado"],
  ["criterio", "TEXT", "Sim", "Critério avaliado"],
  ["dispositivo_legal", "TEXT", "Sim", "Dispositivo que fundamenta a obrigação"],
  ["resultado", "ENUM", "Sim", "cumpre, cumpre_parcialmente, nao_cumpre, indeterminado"],
  ["motivo_indeterminado", "TEXT", "Não", "Usado quando houve indisponibilidade técnica"],
  ["avaliado_em", "TIMESTAMP", "Sim", "Data da avaliação"],
]));

body.push(pageBreak());
body.push(h1("4. Ciclo de vida do indício"));
body.push(p("O estado de um indício é controlado por máquina de estados explícita. Transições não " +
  "previstas são rejeitadas pelo domínio, o que impede, por exemplo, que um indício seja publicado sem " +
  "passar pela revisão quando a severidade exige."));
body.push(...figure("07_estados_indicio.png", "Figura 2. Máquina de estados do indício, da detecção ao encerramento.", 560));

body.push(h1("5. Identidade e resolução de entidades"));
body.push(p("Resolver identidade é um dos pontos mais delicados do modelo. Grafias divergentes, CNPJ " +
  "ausente e mudanças de razão social são a norma, não a exceção."));
body.push(table(["Entidade", "Chave preferencial", "Estratégia quando a chave falta"], [1900, 2700, 5000], [
  ["Ente", "Código IBGE, depois CNPJ",
    "Comparação de nome normalizado restrita à mesma UF, com revisão manual em caso de ambiguidade"],
  ["Fornecedor", "CNPJ completo",
    "Agrupamento por raiz de CNPJ mantendo filiais distinguíveis; pessoa física por documento mascarado"],
  ["Contrato", "Ente mais número mais exercício",
    "Comparação adicional por objeto, fornecedor e valor quando o número não é publicado"],
  ["Item", "Classificação de catálogo",
    "Similaridade textual sobre descrição normalizada, com faixa de confiança registrada no próprio registro"],
  ["Agente público", "Nome mais ente mais período",
    "Sem unificação automática entre entes distintos; homônimos permanecem separados por decisão de projeto"],
]));
body.push(callout("Decisão deliberada sobre agentes públicos", [
  "O sistema não unifica automaticamente o mesmo nome entre entes diferentes. Unificar homônimos sem " +
  "documento identificador criaria associações incorretas entre pessoas distintas, com potencial de " +
  "dano reputacional. O custo aceito é a fragmentação do histórico de um mesmo agente entre entes.",
], "amber"));

body.push(h1("6. Qualidade de dados"));
body.push(p("As regras de qualidade rodam na transição de bronze para silver. Registros reprovados vão " +
  "para quarentena com o motivo, sem interromper o lote, e são revisados periodicamente."));
body.push(table(["Dimensão", "Verificação", "Ação na falha"], [1900, 4400, 3300], [
  ["Completude", "Campos obrigatórios do esquema canônico presentes", "Quarentena com o campo faltante registrado"],
  ["Validade", "CNPJ com dígito verificador válido, datas coerentes, valores não negativos", "Quarentena com o teste que falhou"],
  ["Consistência", "Valor total do contrato compatível com a soma dos itens", "Aceita com marcação de inconsistência; não bloqueia"],
  ["Temporalidade", "Data do ato dentro do exercício declarado", "Quarentena para conferência manual"],
  ["Unicidade", "Ausência de duplicata pela chave de identidade", "Deduplicação com preservação da proveniência de cada ocorrência"],
  ["Referência", "Chaves estrangeiras resolvidas", "Registro mantido com vínculo pendente e nova tentativa no ciclo seguinte"],
]));

body.push(h1("7. Particionamento e retenção"));
body.push(table(["Camada", "Particionamento", "Retenção"], [1800, 4400, 3400], [
  ["Bronze", "Por fonte, ano e mês de coleta", "Permanente; é a prova"],
  ["Silver", "Por exercício e unidade federativa", "Regerável; retida enquanto útil"],
  ["Gold", "Por exercício e tipo de agregado", "Recalculada a cada mudança de regra ou linha de base"],
  ["Domínio", "Sem particionamento na fase inicial", "Permanente, com backup testado"],
  ["Auditoria", "Por mês", "Permanente e somente-anexação"],
]));

L.buildDoc({
  codigo: "DOC-05",
  titulo: "Modelo de Dados",
  subtitulo: "Esquema canônico, dicionário de dados e resolução de identidade",
  body,
  outFile: "../docs/DOC-05_Modelo_de_Dados.docx",
});
