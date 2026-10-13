const L = require("./lib");
const { h1, h2, h3, p, bullet, numbered, table, callout, code, figure, pageBreak, spacer } = L;

const body = [];
// Versão 1.1 (outubro de 2026): avisos de revisão pendente registrados na Fase 1
// (ADR-017, ADR-022, ADR-024). Nenhuma regra foi alterada antes dessas revisões.

function regra({ cod, titulo, pergunta, metodo, parametros, dados, severidade, fp }) {
  const out = [];
  out.push(h3(`${cod} — ${titulo}`));
  out.push(table(null, [1900, 7700], [
    ["Pergunta que responde", pergunta],
    ["Método", metodo],
    ["Parâmetros iniciais", parametros],
    ["Dados necessários", dados],
    ["Severidade base", severidade],
    ["Falsos positivos conhecidos", fp],
  ], { boldFirstCol: true }));
  out.push(spacer(150));
  return out;
}

body.push(h1("1. Filosofia do motor"));
body.push(p("Uma regra de detecção não responde à pergunta se houve irregularidade. Ela responde a uma " +
  "pergunta muito mais modesta e verificável: este registro se afasta do padrão observado em registros " +
  "comparáveis, ou de um limite objetivo definido em lei. A distância entre essas duas perguntas é " +
  "exatamente o espaço onde vive a responsabilidade dos órgãos de controle, e o Lumen não o ocupa."));
body.push(p("Essa modéstia tem consequência prática direta no desenho: toda regra precisa expor a " +
  "referência contra a qual comparou. Dizer que um preço é alto sem dizer alto em relação a quê não é " +
  "detecção, é opinião. Por isso cada regra deste catálogo declara explicitamente sua linha de base."));

body.push(callout("Revisões pendentes registradas durante a Fase 1", [
  "B-01: o critério legal de aferição do limite de dispensa (Lei 14.133/2021, art. 75, § 1º) é o exercício " +
  "financeiro, a unidade gestora e o ramo de atividade, e não a janela de 180 dias por fornecedor desta " +
  "versão. A proposta de separar a regra em B-01a (aderente ao texto legal) e B-01b (padrão estatístico " +
  "complementar) aguarda revisão metodológica e jurídica (ADR-022). Nenhuma regra da família B é " +
  "implementada antes dela.",
  "Quem autorizou o ato: a API do PNCP não publica o agente (ADR-017). Regra cuja explicação pública dependa " +
  "dessa informação só pode publicar com fonte complementar (diário oficial ou portal do ente).",
  "Família K: dados eleitorais entram só como contexto factual (ADR-024). A K-01 depende da prestação de " +
  "contas de campanha do TSE, fonte ainda não integrada.",
], "amber"));
body.push(spacer(100));

body.push(h2("1.1 Anatomia de uma regra"));
body.push(table(["Componente", "Papel"], [2600, 7000], [
  ["Código e versão", "Identidade estável; alteração de parâmetro gera nova versão"],
  ["Linha de base", "A referência contra a qual se compara: mediana, grupo de pares ou limite legal"],
  ["Condição de disparo", "Expressão determinística sobre dados normalizados"],
  ["Parâmetros", "Valores calibráveis, versionados junto com a regra"],
  ["Severidade base", "Ponto de partida do cálculo de severidade final"],
  ["Explicação pública", "Texto neutro, em linguagem acessível, aprovado editorialmente"],
  ["Evidência exigida", "Quais documentos precisam existir para a regra poder publicar"],
  ["Falsos positivos conhecidos", "Situações legítimas que disparam a regra e exigem atenção do revisor"],
]));

body.push(h2("1.2 Ordem de execução"));
body.push(...figure("06_fluxo_deteccao.png", "Figura 1. Do artefato coletado ao indício publicado, com os dois pontos de descarte.", 540));

body.push(pageBreak());
body.push(h1("2. Família A — Anomalia de preço"));
body.push(p("Detecta valores unitários que destoam do praticado para o mesmo item. Depende integralmente " +
  "da normalização de itens por catálogo: sem classificar o item, não há comparação possível."));

body.push(...regra({
  cod: "A-01", titulo: "Preço unitário distante da mediana do item",
  pergunta: "Este item foi contratado por valor muito acima do que outros entes pagaram pelo mesmo item no mesmo período?",
  metodo: "Escore robusto baseado em mediana e desvio absoluto mediano (MAD), que resiste a valores extremos: " +
    "escore = 0,6745 × (valor_unitário − mediana) ÷ MAD, calculado por item de catálogo, faixa regional e trimestre.",
  parametros: "Escore mínimo de disparo: 3,5. Mínimo de 30 observações comparáveis. Valor total mínimo do item para considerar.",
  dados: "ItemContratado com catalogo_item_id preenchido; série histórica de preços",
  severidade: "Média; sobe para alta quando o escore ultrapassa 6 e o valor total é relevante",
  fp: "Item de catálogo mal classificado agrupando produtos diferentes; especificação técnica superior legítima; " +
    "compra emergencial em contexto de escassez; região com custo logístico muito superior",
}));

body.push(...regra({
  cod: "A-02", titulo: "Preço acima de tabela referencial oficial",
  pergunta: "O preço supera a referência publicada pelo próprio governo para aquele tipo de item?",
  metodo: "Comparação direta com tabela de referência aplicável ao objeto, com margem de tolerância percentual configurável.",
  parametros: "Tolerância inicial de 15% sobre a referência vigente na data do contrato",
  dados: "Item classificado; tabela de referência correspondente à data",
  severidade: "Alta, por se tratar de comparação com parâmetro oficial e não com estimativa estatística",
  fp: "Tabela desatualizada frente à inflação do período; item com especificação distinta da referência; " +
    "custo de instalação ou serviço embutido no preço unitário",
}));

body.push(...regra({
  cod: "A-03", titulo: "Divergência entre ata de registro de preços e contratação efetiva",
  pergunta: "O ente contratou acima do preço que ele próprio registrou em ata vigente?",
  metodo: "Confronto entre valor unitário contratado e valor registrado em ata vigente do mesmo ente para o mesmo item.",
  parametros: "Divergência mínima de 10% para disparo",
  dados: "Atas do PNCP; itens contratados classificados",
  severidade: "Alta",
  fp: "Ata vencida na data da contratação; reajuste contratual previsto e aplicado; item similar porém distinto",
}));

body.push(...regra({
  cod: "A-04", titulo: "Mesmo fornecedor, mesmo item, preços muito distintos entre entes",
  pergunta: "Um mesmo fornecedor cobra valores substancialmente diferentes de entes diferentes pelo mesmo item no mesmo período?",
  metodo: "Coeficiente de variação dos preços do par fornecedor e item entre entes, dentro de janela trimestral.",
  parametros: "Coeficiente de variação acima de 0,4 com pelo menos 3 entes distintos",
  dados: "Itens classificados; fornecedor resolvido por raiz de CNPJ",
  severidade: "Média",
  fp: "Diferença real de volume contratado; custo logístico entre regiões distantes; prazos de entrega diferentes",
}));

body.push(...regra({
  cod: "A-05", titulo: "Preço acima da referência de mercado de fora do governo",
  pergunta: "O preço unitário pago está muito acima do que o mercado cobrava, no mesmo lugar e na mesma época, por um produto inequivocamente igual?",
  metodo: "Razão entre o preço unitário homologado e a mediana de uma referência que não nasce de compra pública: o preço de revenda da ANP " +
    "no município (ou, sem amostra, na UF) até 7 dias da data do resultado, para combustíveis e para o gás de cozinha no botijão de 13 kg; " +
    "ofertas novas do varejo online, obtidas pela " +
    "API oficial da loja, cujo título contém todos os atributos da especificação, para informática padronizada. O item só entra se a " +
    "descrição e a unidade o identificam sem ambiguidade (ADR-027).",
  parametros: "Limiar de 1,20 × a mediana em combustível, 1,25 × no gás de cozinha e 1,50 × no varejo; mínimo de 5 revendas no " +
    "município, 10 na UF e 8 ofertas. Razão abaixo de 0,50 ou acima de 10,00 é \"fora de escala\" (preço simbólico, orçamento " +
    "sigiloso gravado como zero, valor total lançado como unitário ou erro de unidade) e sai da distribuição; de 3,00 a 10,00 o " +
    "item recebe a marca para conferir unidade. " +
    "Valores iniciais, não calibrados; a regra roda em modo silencioso, e o relatório traz a " +
    "distribuição da razão por categoria, tipo de preço e escopo, com a fração acima de cada limiar candidato, para a calibração",
  dados: "Itens e resultados do PNCP; série histórica e planilhas semanais de preços da ANP; ofertas do varejo guardadas no bronze com " +
    "data e hora do acesso",
  severidade: "A definir na calibração; enquanto silenciosa, não gera indício",
  fp: "Entrega no local de uso (diesel no canteiro, combustível no tanque da frota, botijão na unidade); cartão de abastecimento e prazo de pagamento; " +
    "município pequeno comparado com a mediana da UF; especificação superior à do anúncio; garantia, assistência técnica ou instalação " +
    "embutidas no preço; variação brusca de preço entre a proposta e o resultado",
}));
body.push(callout("Por que uma régua de fora do governo", [
  "A-01 a A-04 comparam o preço com o que o próprio poder público pagou ou tabelou. Quando quase todos pagam caro pelo mesmo item, " +
  "a mediana entre órgãos sobe junto e nada destoa. A-05 traz a régua do mercado, que a Lei 14.133 também aceita como parâmetro de " +
  "pesquisa de preços (art. 23, § 1º, III e V). Começa pelo combustível, cuja referência é oficial, histórica e sem ambiguidade de produto.",
], "blue"));

body.push(pageBreak());
body.push(h1("3. Família B — Fracionamento e padrões de valor pequeno"));
body.push(callout("A família mais importante deste catálogo", [
  "Esta é a família que atende diretamente à preocupação com valores pequenos que escondem padrões. " +
  "Nenhuma das regras abaixo consegue disparar olhando um documento isolado: todas dependem de agregar " +
  "o conjunto. É precisamente por isso que esses padrões sobrevivem à fiscalização tradicional, que " +
  "examina processos individualmente.",
], "green"));

body.push(p("O contexto legal é objetivo. A Lei 14.133/2021 permite contratação direta por dispensa " +
  "abaixo de determinados valores, atualizados anualmente por decreto. Para 2026, o Decreto 12.807/2025 " +
  "fixou os limites em R$ 130.984,20 para obras e serviços de engenharia (art. 75, I) e R$ 65.492,11 " +
  "para demais compras e serviços (art. 75, II). Esses valores são parâmetros configuráveis do sistema, " +
  "com vigência datada, e precisam ser atualizados a cada decreto anual."));

body.push(...regra({
  cod: "B-01", titulo: "Fracionamento por agregação de objeto e fornecedor",
  pergunta: "Várias contratações diretas pequenas, somadas, correspondem a uma contratação que teria exigido licitação?",
  metodo: "Agrupar contratações diretas do mesmo ente, mesmo fornecedor e objeto similar dentro de janela móvel; " +
    "somar os valores e comparar a soma com o limite legal aplicável ao tipo de objeto.",
  parametros: "Janela de 180 dias. Similaridade de objeto acima de 0,80. Disparo quando a soma ultrapassa o limite legal vigente na data.",
  dados: "ProcessoContratacao com modalidade de dispensa; amparo legal; objeto; fornecedor resolvido",
  severidade: "Alta",
  fp: "Objetos genuinamente distintos com descrição textual parecida; contratações em unidades gestoras " +
    "autônomas do mesmo ente, cujos limites são contados separadamente; ata de registro de preços legítima",
}));
body.push(callout("B-01 em revisão (ADR-022)", [
  "A janela móvel de 180 dias por fornecedor não é o critério do art. 75, § 1º, que soma o despendido no " +
  "exercício financeiro pela unidade gestora com objetos do mesmo ramo de atividade, e o § 2º dobra os " +
  "limites para consórcios públicos e agências executivas. Esta definição fica suspensa até a revisão.",
], "amber"));
body.push(spacer(120));

body.push(...regra({
  cod: "B-02", titulo: "Concentração de valores imediatamente abaixo do limite legal",
  pergunta: "Os valores de contratação deste ente se acumulam de forma atípica logo abaixo do limite de dispensa?",
  metodo: "Análise de agrupamento na distribuição de valores. Compara-se a frequência observada na faixa " +
    "imediatamente inferior ao limite com a frequência esperada pela distribuição suavizada do próprio ente.",
  parametros: "Faixa de análise de 90% a 100% do limite. Razão observado sobre esperado acima de 2,5. Mínimo de 20 contratações no exercício.",
  dados: "Valores de contratações diretas; limites legais datados",
  severidade: "Média; alta quando a razão supera 4",
  fp: "Ente que efetivamente planeja compras para caber no limite, prática administrativamente " +
    "questionável mas não necessariamente ilícita; poucos dados gerando artefato estatístico",
}));

body.push(...regra({
  cod: "B-03", titulo: "Sequência recorrente de dispensas com o mesmo fornecedor",
  pergunta: "O mesmo fornecedor vem sendo contratado por dispensa de forma repetida e regular, como se houvesse contrato contínuo?",
  metodo: "Contagem de dispensas por par ente e fornecedor no exercício, com análise da regularidade dos intervalos " +
    "entre contratações. Regularidade alta sugere relação continuada tratada como eventos isolados.",
  parametros: "Mínimo de 6 dispensas no exercício e coeficiente de variação dos intervalos abaixo de 0,35",
  dados: "Processos de dispensa com data e fornecedor",
  severidade: "Média",
  fp: "Fornecedor único de item especializado na região; compras genuinamente eventuais que por acaso " +
    "ficaram regulares; ente pequeno com poucos fornecedores disponíveis",
}));

body.push(...regra({
  cod: "B-04", titulo: "Múltiplas contratações do mesmo objeto na mesma data",
  pergunta: "O ente emitiu, no mesmo dia, várias contratações diretas do mesmo objeto que somadas superariam o limite?",
  metodo: "Agrupamento por ente, data e objeto similar, com soma dos valores confrontada ao limite legal.",
  parametros: "Mesma data; similaridade de objeto acima de 0,85; soma acima do limite",
  dados: "Processos de contratação com data e objeto",
  severidade: "Alta, por ser padrão de difícil justificativa operacional",
  fp: "Empenhos distintos de um mesmo processo licitatório regular; fontes de recurso diferentes exigindo " +
    "documentos separados por exigência contábil",
}));

body.push(pageBreak());
body.push(h1("4. Família C — Concentração de fornecedores"));

body.push(...regra({
  cod: "C-01", titulo: "Concentração de mercado elevada por categoria",
  pergunta: "As contratações de determinada categoria neste ente se concentram excessivamente em poucos fornecedores?",
  metodo: "Índice de Herfindahl-Hirschman calculado sobre a participação em valor de cada fornecedor, " +
    "por ente e categoria: HHI = soma dos quadrados das participações percentuais.",
  parametros: "HHI acima de 2.500 com no mínimo 10 contratações e valor total relevante na categoria",
  dados: "Contratos por ente, categoria e fornecedor",
  severidade: "Baixa isoladamente; média quando combinada com regras das famílias D ou E",
  fp: "Mercado naturalmente concentrado; município pequeno com poucos fornecedores locais; " +
    "categoria com barreira técnica legítima de entrada",
}));

body.push(...regra({
  cod: "C-02", titulo: "Fornecedor dominante no ente",
  pergunta: "Um único fornecedor concentra parcela desproporcional do valor contratado pelo ente?",
  metodo: "Participação percentual do fornecedor no valor total contratado pelo ente no exercício, " +
    "comparada à participação típica do maior fornecedor nos entes do grupo de pares.",
  parametros: "Participação acima de 30% e acima do percentil 95 do grupo de pares",
  dados: "Contratos agregados por ente e fornecedor; grupo de pares",
  severidade: "Média",
  fp: "Contrato único de grande vulto, como obra ou concessão, distorcendo o percentual; " +
    "terceirização ampla de serviço contínuo concentrada em um prestador",
}));

body.push(...regra({
  cod: "C-03", titulo: "Dependência do fornecedor em relação ao ente",
  pergunta: "Este fornecedor tem praticamente um único cliente público, que é justamente este ente?",
  metodo: "Participação do ente na receita pública total identificada do fornecedor, considerando todas as fontes coletadas.",
  parametros: "Acima de 90% da receita pública identificada, com valor absoluto mínimo e ao menos 12 meses de histórico",
  dados: "Contratos do fornecedor em todos os entes cobertos",
  severidade: "Média",
  fp: "Cobertura incompleta do Lumen produzindo dependência aparente; empresa genuinamente local e " +
    "pequena; fornecedor recém-entrante ainda sem diversificação",
}));

body.push(h1("5. Família D — Perfil societário do fornecedor"));
body.push(p("Esta família depende da base pública de CNPJ da Receita Federal e produz os indícios de " +
  "maior sensibilidade do sistema, porque tocam pessoas jurídicas identificadas. Por isso, todas as " +
  "regras da família D exigem revisão humana antes de qualquer publicação, independentemente do score."));

body.push(...regra({
  cod: "D-01", titulo: "Fornecedor constituído pouco antes da contratação",
  pergunta: "A empresa foi aberta em prazo muito curto antes de ser contratada?",
  metodo: "Diferença entre a data de abertura do estabelecimento e a data de assinatura do contrato.",
  parametros: "Menos de 90 dias, com valor de contrato acima de patamar mínimo configurável",
  dados: "Fornecedor com data_abertura; contrato com data de assinatura",
  severidade: "Média",
  fp: "Empresa nova legítima disputando e vencendo regularmente; reorganização societária que gerou novo " +
    "CNPJ para operação preexistente; filial recém-aberta de empresa antiga",
}));

body.push(...regra({
  cod: "D-02", titulo: "Capital social desproporcional ao valor contratado",
  pergunta: "O capital social declarado é muito pequeno frente ao porte do contrato assumido?",
  metodo: "Razão entre valor do contrato e capital social do fornecedor.",
  parametros: "Razão acima de 50, com valor de contrato acima de patamar mínimo",
  dados: "Fornecedor com capital_social; valor do contrato",
  severidade: "Baixa isoladamente; média quando combinada com D-01",
  fp: "Capital social desatualizado no registro, situação extremamente comum; setores de serviço com " +
    "baixa necessidade de capital; empresa com patrimônio real muito superior ao capital registrado",
}));

body.push(...regra({
  cod: "D-03", titulo: "Atividade econômica incompatível com o objeto",
  pergunta: "O CNAE do fornecedor guarda relação com aquilo que ele foi contratado para fornecer?",
  metodo: "Mapeamento entre categoria do objeto contratado e conjunto de CNAEs compatíveis, considerando " +
    "atividade principal e secundárias do estabelecimento.",
  parametros: "Nenhuma compatibilidade encontrada entre o objeto e os CNAEs registrados",
  dados: "Fornecedor com CNAE; objeto classificado",
  severidade: "Média",
  fp: "CNAE desatualizado; empresa com atuação ampla legítima não refletida no cadastro; " +
    "classificação imprecisa do objeto pelo próprio sistema",
}));

body.push(...regra({
  cod: "D-04", titulo: "Sócios em comum entre participantes do mesmo processo",
  pergunta: "Empresas que disputaram a mesma licitação compartilham sócios?",
  metodo: "Interseção do quadro societário entre fornecedores participantes de um mesmo processo.",
  parametros: "Ao menos um sócio em comum entre dois ou mais participantes",
  dados: "Quadro societário da Receita Federal; lista de participantes do processo",
  severidade: "Alta",
  fp: "Homonímia de sócios sem verificação por documento; participação societária minoritária e " +
    "irrelevante; grupo econômico formalmente declarado e admitido no edital",
}));

body.push(...regra({
  cod: "D-05", titulo: "Endereço coincidente entre participantes do mesmo processo",
  pergunta: "Empresas concorrentes no mesmo processo estão registradas no mesmo endereço?",
  metodo: "Comparação de hash do endereço normalizado entre participantes, sem expor o endereço.",
  parametros: "Coincidência exata do endereço normalizado entre dois ou mais participantes",
  dados: "Estabelecimentos da Receita Federal; participantes do processo",
  severidade: "Média",
  fp: "Endereços de escritórios compartilhados e coworking, causa muito frequente; prédios comerciais " +
    "com muitas empresas onde a normalização não distingue a unidade; empresas familiares no mesmo imóvel",
}));

body.push(pageBreak());
body.push(h1("6. Família E — Anomalias processuais"));

body.push(...regra({
  cod: "E-01", titulo: "Uso de contratação direta acima do padrão do grupo de pares",
  pergunta: "Este ente recorre a dispensa e inexigibilidade muito mais que entes semelhantes?",
  metodo: "Percentual do valor contratado por dispensa ou inexigibilidade sobre o total, comparado à " +
    "distribuição do grupo de pares.",
  parametros: "Acima do percentil 90 do grupo, com mínimo de contratações no exercício",
  dados: "Processos por modalidade; grupo de pares",
  severidade: "Média",
  fp: "Situação emergencial declarada e legítima, como calamidade; ente com perfil de compra atípico " +
    "por natureza da atividade; grupo de pares mal formado",
}));

body.push(...regra({
  cod: "E-02", titulo: "Aditivos acima do limite legal de acréscimo",
  pergunta: "Os aditivos elevaram o valor do contrato além do que a lei permite acrescer?",
  metodo: "Soma dos acréscimos sobre o valor inicial, confrontada com o percentual legal aplicável ao tipo de objeto.",
  parametros: "Percentuais conforme o art. 125 da Lei 14.133/2021, parametrizados por tipo de objeto e datados",
  dados: "Contrato com valor inicial; aditivos com valores e datas",
  severidade: "Alta, por comparar com limite objetivo de lei",
  fp: "Reajuste contratual e repactuação, que não constituem acréscimo de objeto e não entram no limite; " +
    "valor inicial registrado incorretamente na fonte; contratos sob regime legal anterior",
}));

body.push(...regra({
  cod: "E-03", titulo: "Prazo entre publicação e abertura inferior ao mínimo legal",
  pergunta: "O prazo concedido para apresentação de propostas respeitou o mínimo previsto para a modalidade?",
  metodo: "Diferença em dias úteis entre publicação do edital e abertura das propostas, comparada ao mínimo da modalidade.",
  parametros: "Prazos mínimos por modalidade conforme a legislação vigente, com calendário de dias úteis",
  dados: "Processo com data de publicação e data de abertura",
  severidade: "Alta",
  fp: "Republicação de edital com contagem reiniciada; datas registradas incorretamente na fonte; " +
    "contagem em dias corridos versus úteis conforme o dispositivo aplicável",
}));

body.push(...regra({
  cod: "E-04", titulo: "Participante único recorrente em processos competitivos",
  pergunta: "Processos que deveriam ser competitivos vêm recebendo uma única proposta de forma sistemática?",
  metodo: "Proporção de processos competitivos do ente com apenas um participante, comparada ao grupo de pares.",
  parametros: "Acima de 50% dos processos e acima do percentil 90 do grupo",
  dados: "Processos com quantidade de participantes",
  severidade: "Média",
  fp: "Mercado local restrito em municípios pequenos e remotos; objeto altamente especializado; " +
    "campo de participantes não preenchido pela fonte e interpretado como um",
}));

body.push(h1("7. Família F — Análise forense de dígitos"));

body.push(...regra({
  cod: "F-01", titulo: "Desvio da distribuição esperada do primeiro dígito",
  pergunta: "O conjunto de valores deste ente se distribui de forma compatível com o que se observa em dados financeiros naturais?",
  metodo: "Teste de aderência à Lei de Benford sobre o primeiro dígito significativo, com estatística " +
    "qui-quadrado e desvio absoluto médio. Aplicado a conjuntos de valores por ente e exercício.",
  parametros: "Mínimo de 500 valores no conjunto; desvio absoluto médio acima do limiar de aderência marginal",
  dados: "Valores de empenho e de contrato agregados por ente e exercício",
  severidade: "Baixa; nunca publicada isoladamente",
  fp: "Conjuntos com limite inferior ou superior de valor, que violam a premissa do teste; " +
    "poucos valores repetidos dominando o conjunto; contratos de valor padronizado por tabela",
}));
body.push(callout("Restrição específica desta regra", [
  "A Lei de Benford descreve conjuntos, não transações. Um desvio de aderência não diz nada sobre " +
  "nenhum contrato individual, e apresentá-lo como se dissesse seria um erro metodológico grave. " +
  "No Lumen, F-01 nunca gera indício publicável por si só: ela apenas eleva a prioridade do ente na fila " +
  "de análise interna, para que outras regras sejam examinadas com atenção naquele conjunto.",
], "red"));

body.push(pageBreak());
body.push(h1("8. Família G — Padrões temporais"));

body.push(...regra({
  cod: "G-01", titulo: "Concentração atípica de empenhos no encerramento do exercício",
  pergunta: "O ente concentra empenhos nos últimos dias do ano muito acima do que é usual entre seus pares?",
  metodo: "Proporção do valor empenhado nos últimos 15 dias do exercício sobre o total anual, comparada ao grupo de pares.",
  parametros: "Acima do percentil 90 do grupo de pares",
  dados: "Empenhos com data e valor; grupo de pares",
  severidade: "Baixa a média",
  fp: "Prática orçamentária generalizada e conhecida no setor público brasileiro, o que torna o " +
    "indicador pouco discriminante isoladamente; liberação tardia de recurso federal fora do controle do ente",
}));

body.push(...regra({
  cod: "G-02", titulo: "Inversão na cadeia da despesa",
  pergunta: "Houve pagamento registrado antes da liquidação correspondente?",
  metodo: "Comparação de datas na cadeia empenho, liquidação e pagamento do mesmo documento.",
  parametros: "Data de pagamento anterior à data de liquidação",
  dados: "Cadeia da despesa completa com datas",
  severidade: "Média",
  fp: "Erro de registro na fonte, que é a causa mais frequente; adiantamento legalmente previsto; " +
    "datas de competência versus datas de caixa registradas de forma inconsistente",
}));

body.push(h1("9. Família H — Comparação com o grupo de pares"));

body.push(...regra({
  cod: "H-01", titulo: "Gasto per capita atípico por função",
  pergunta: "Quanto este ente gasta por habitante em determinada função, comparado a entes semelhantes?",
  metodo: "Despesa por função dividida pela população, posicionada na distribuição do grupo de pares por escore robusto.",
  parametros: "Escore robusto acima de 3,0; grupo com no mínimo 15 entes",
  dados: "Despesa por função do SICONFI; população do IBGE; grupo de pares",
  severidade: "Baixa a média",
  fp: "Ente que sedia equipamento regional atendendo população de municípios vizinhos, causa muito " +
    "comum em saúde e educação; classificação funcional divergente entre entes; população desatualizada",
}));

body.push(...regra({
  cod: "H-02", titulo: "Variação abrupta na série histórica do próprio ente",
  pergunta: "O gasto do ente nesta rubrica mudou de patamar de forma abrupta em relação à sua própria história?",
  metodo: "Comparação do valor do período com a mediana dos períodos anteriores do próprio ente, por escore robusto.",
  parametros: "Escore acima de 3,5; mínimo de 8 períodos históricos",
  dados: "Série histórica de despesa por ente e rubrica",
  severidade: "Baixa a média",
  fp: "Mudança real e legítima de política pública; obra pontual de grande vulto; " +
    "reclassificação contábil entre rubricas; efeito inflacionário em série longa não deflacionada",
}));

body.push(h1("10. Família I — Conformidade de transparência"));
body.push(p("Esta família não analisa gasto: analisa o cumprimento do dever legal de publicar. Suas " +
  "regras são as mais objetivas e as menos contestáveis do catálogo, porque comparam o que foi publicado " +
  "com o que a lei determina que fosse publicado."));

body.push(...regra({
  cod: "I-01", titulo: "Ausência de envio obrigatório a sistema federal",
  pergunta: "O ente deixou de enviar declaração ou relatório cuja remessa é legalmente obrigatória?",
  metodo: "Confronto entre a lista de entes existentes e a lista de entes presentes na base federal para o período.",
  parametros: "Ausência do ente na base para período já encerrado e vencido",
  dados: "Cadastro de entes do IBGE; base federal correspondente",
  severidade: "Alta",
  fp: "Ente extinto ou incorporado; envio realizado fora do prazo e ainda não refletido na consolidação; " +
    "identificador do ente divergente entre bases",
}));

body.push(...regra({
  cod: "I-02", titulo: "Desatualização da publicação obrigatória",
  pergunta: "A informação publicada está dentro da periodicidade exigida pela legislação?",
  metodo: "Diferença entre a data do dado mais recente publicado e a data limite legal para aquela periodicidade.",
  parametros: "Atraso superior ao prazo legal aplicável, com tolerância operacional configurável",
  dados: "Data do registro mais recente por ente e tipo de informação",
  severidade: "Média",
  fp: "Indisponibilidade técnica temporária do portal; falha do próprio conector do Lumen, que precisa " +
    "ser descartada antes de atribuir o atraso ao ente",
}));

body.push(...regra({
  cod: "I-03", titulo: "Publicação em formato não legível por máquina",
  pergunta: "O ente publica em formato que permite reutilização, ou apenas em formato que dificulta a análise?",
  metodo: "Classificação do formato predominante de publicação por tipo de informação.",
  parametros: "Predominância de documento digitalizado sem camada de texto ou de formato não estruturado",
  dados: "Metadados de formato dos artefatos coletados",
  severidade: "Baixa",
  fp: "Portal que oferece exportação estruturada em local não descoberto pelo conector, hipótese que " +
    "precisa ser verificada manualmente antes de qualquer registro",
}));

body.push(callout("Cuidado essencial nesta família", [
  "Antes de registrar qualquer não conformidade, é obrigatório descartar a hipótese de falha do próprio " +
  "Lumen. Um conector quebrado produz exatamente o mesmo sintoma de um ente que parou de publicar. " +
  "Por isso o estado indeterminado existe no modelo: quando não é possível distinguir as duas " +
  "situações, o sistema registra indeterminado e não atribui falha ao ente.",
], "red"));

body.push(pageBreak());
body.push(h1("11. Família J — Sanções vigentes"));

body.push(...regra({
  cod: "J-01", titulo: "Contratação de fornecedor com sanção vigente na data do ato",
  pergunta: "Na data da contratação, o fornecedor constava em cadastro de sanção que o impedia de contratar?",
  metodo: "Interseção temporal entre a vigência da sanção e a data de assinatura do contrato, considerando " +
    "a abrangência da sanção e o ente contratante.",
  parametros: "Sanção vigente na data do ato, com abrangência aplicável ao ente",
  dados: "CEIS, CNEP e CEPIM com datas de vigência; contratos com data de assinatura",
  severidade: "Alta",
  fp: "Sanção com abrangência restrita a outro ente ou esfera, o que é determinante e precisa ser " +
    "verificado; sanção suspensa por decisão judicial; inclusão retroativa no cadastro após a contratação",
}));

body.push(h1("12. Família K — Contexto factual, sem publicação autônoma"));
body.push(p("Regras desta família nunca geram indício publicável. Elas apenas anexam contexto verificável " +
  "a um indício já originado por outra regra, para que quem for analisar disponha de informação adicional."));
body.push(table(["Cód.", "Contexto anexado", "Restrição"], [900, 4700, 4000], [
  ["K-01", "Fornecedor consta como doador eleitoral em pleito relacionado ao ente",
    "Nunca publicado isoladamente; exibido apenas como dado factual anexo, sem qualquer sugestão de nexo causal"],
  ["K-02", "Fornecedor foi objeto de acórdão de tribunal de contas",
    "Exibido com referência ao acórdão e ao seu desfecho, sem interpretação do Lumen"],
  ["K-03", "Ente apresenta conjunto com baixa aderência a Benford no período",
    "Uso exclusivamente interno, para priorização da fila de análise"],
]));

body.push(h1("13. Score composto e severidade"));
body.push(p("Cada disparo gera um score normalizado entre 0 e 1, que combina a intensidade do desvio com " +
  "a confiabilidade dos dados e a materialidade financeira. A fórmula é deliberadamente simples e " +
  "auditável, e seus pesos são parâmetros versionados."));
body.push(code([
  "score = w_int * intensidade",
  "      + w_conf * confianca_dado",
  "      + w_mat * materialidade",
  "      + w_corr * corroboracao",
  "",
  "onde, todos normalizados no intervalo [0, 1]:",
  "",
  "  intensidade    = quanto o valor observado se afasta da linha de base",
  "                   (escore robusto truncado, ou razao sobre o limite legal)",
  "",
  "  confianca_dado = qualidade da evidencia disponivel",
  "                   (fonte estruturada e completa = 1,0;",
  "                    extracao de PDF com OCR = 0,5;",
  "                    campos criticos ausentes reduz proporcionalmente)",
  "",
  "  materialidade  = relevancia financeira do valor envolvido,",
  "                   relativizada pelo porte do ente",
  "                   (um valor pequeno pode ser material em municipio pequeno)",
  "",
  "  corroboracao   = quantas regras independentes apontam o mesmo alvo",
  "                   (satura em 3 regras para nao inflar o score)",
  "",
  "pesos iniciais: w_int = 0,40  w_conf = 0,25  w_mat = 0,20  w_corr = 0,15",
]));
body.push(table(["Severidade", "Faixa de score", "Tratamento"], [1800, 2600, 5200], [
  ["Baixa", "menor que 0,45", "Não publicada; alimenta estatísticas e priorização interna"],
  ["Média", "de 0,45 a 0,70", "Entra na fila de revisão humana; publicável após aprovação"],
  ["Alta", "acima de 0,70", "Revisão humana obrigatória por dois analistas antes da publicação"],
]));
body.push(p("A materialidade merece destaque porque implementa diretamente a preocupação com valores " +
  "pequenos: ela é relativizada pelo porte do ente. Uma contratação de valor modesto em um município de " +
  "cinco mil habitantes pode representar parcela relevante do orçamento e receber materialidade alta, " +
  "enquanto o mesmo valor absoluto em uma capital receberia materialidade baixa. Sem essa relativização, " +
  "o sistema reproduziria exatamente o viés de atenção que ele existe para corrigir."));

body.push(h1("14. Calibração e controle de qualidade"));
body.push(numbered("Toda regra nova entra em modo silencioso: executa e registra, mas não publica."));
body.push(numbered("Após acumular volume suficiente, uma amostra aleatória é revisada manualmente para estimar a taxa de falso positivo."));
body.push(numbered("A regra só é liberada para publicação quando a taxa estimada de falso positivo fica abaixo do limite definido para sua severidade."));
body.push(numbered("Regras publicadas têm suas métricas acompanhadas continuamente; taxa de descarte na revisão acima do limite dispara revisão de calibração."));
body.push(numbered("Toda alteração de parâmetro gera nova versão e é simulada sobre janela histórica antes de entrar em vigor."));
body.push(table(["Severidade", "Taxa máxima aceitável de falso positivo", "Amostra mínima para liberação"], [2000, 4400, 3200], [
  ["Baixa", "30%", "50 casos revisados"],
  ["Média", "15%", "80 casos revisados"],
  ["Alta", "5%", "120 casos revisados"],
]));

body.push(callout("O falso positivo mais perigoso não é o estatístico", [
  "A maior fonte de erro deste tipo de sistema não é a regra mal calibrada: é o dado de origem incorreto. " +
  "Um valor digitado com casas decimais erradas por um servidor produz um indício de sobrepreço " +
  "perfeitamente calculado e completamente equivocado. Por isso a revisão humana verifica primeiro se o " +
  "documento fonte de fato contém o que a regra leu, antes de avaliar o mérito do desvio apontado.",
], "amber"));

L.buildDoc({
  codigo: "DOC-07",
  titulo: "Motor de Detecção",
  subtitulo: "Catálogo de regras, fórmulas, limiares e tratamento de falso positivo",
  meta: { versao: "1.2", data: "9 de outubro de 2026",
    situacao: "Catálogo da versão 1.0 com as revisões pendentes da Fase 1 e a regra A-05 (ADR-027)",
    verificado: "outubro de 2026" },
  body,
  outFile: "../docs/DOC-07_Motor_de_Deteccao.docx",
});
