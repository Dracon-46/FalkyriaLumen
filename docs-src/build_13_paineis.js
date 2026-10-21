// DOC-13 — Painéis de contratações e de conformidade: objetivo, fontes,
// arquitetura, estado, site, regras de soma e de avaliação, portal, operação,
// verificação e próximos passos (ADR-028).
//
// Os números citados aqui (limites, colunas, contagens) são os do código em
// packages/painel e packages/portal; quem muda um lado atualiza o outro.

const path = require("path");
const { TextRun } = require("docx");
const L = require("./lib");
const { h1, h2, h3, pRuns, bulletRuns, numberedRuns, table, callout, code, figure, spacer } = L;

const body = [];

// Trechos `assim` viram fonte monoespaçada; **assim**, negrito.
function runs(texto) {
  const saida = [];
  const re = /`([^`]+)`|\*\*([^*]+)\*\*/g;
  let ultimo = 0;
  let m;
  while ((m = re.exec(texto)) !== null) {
    if (m.index > ultimo) saida.push(new TextRun({ text: texto.slice(ultimo, m.index) }));
    if (m[1]) saida.push(new TextRun({ text: m[1], font: "Consolas", size: 19 }));
    else saida.push(new TextRun({ text: m[2], bold: true }));
    ultimo = re.lastIndex;
  }
  if (ultimo < texto.length) saida.push(new TextRun({ text: texto.slice(ultimo) }));
  return saida;
}
const t = (texto) => pRuns(runs(texto));
const b = (texto) => bulletRuns(runs(texto));
let listaAtual = 0;
const novaLista = () => { listaAtual += 1; };
const n = (texto) => numberedRuns(runs(texto), 0, listaAtual);

// ============================================================ 1. Objetivo

body.push(h1("1. Objetivo e escopo"));
body.push(t("Este documento descreve as áreas **Contratações** e **Conformidade** do portal do Lumen, abertas em 14 de " +
  "outubro de 2026 (ADR-028): de onde vêm os números, como são coletados, guardados, somados, avaliados e publicados, " +
  "e como o portal os mostra. É a referência para quem mantém o código de `packages/painel` e das páginas do portal; " +
  "a referência função a função gerada do código fica no DOC-11."));
body.push(table(["Área", "Casos de uso", "O que mostra"], [1800, 2200, 5600], [
  ["Contratações", "UC-01 e UC-02", "Para o Brasil, cada ente (União, estado, DF, município) e cada órgão: processos de contratação e contratos publicados no PNCP, mês a mês e por modalidade, os órgãos que publicaram, os fornecedores pessoa jurídica de maior valor e as publicações mais recentes, com o link de cada uma no PNCP"],
  ["Conformidade", "UC-07; RF-CF-01, RF-CF-02 e RF-CF-07", "Para cada estado, o DF e cada município: se as contas anuais, o RREO e o RGF constam do extrato de entregas do Tesouro (SICONFI), em que data e contra qual prazo legal; resumos por UF e para o Brasil"],
], { size: 18 }));
body.push(spacer(80));
body.push(callout("O que estas áreas não fazem", [
  "Não publicam indício, não atribuem conduta e não ordenam entes por nenhum critério de risco (PUB-07). São fatos " +
  "publicados pela própria administração, somados e listados, com a fonte de cada um. As regras de sinalização do " +
  "DOC-07 seguem em calibração e revisão (ADR-022, ADR-027) e, quando entrarem, passam pelo fluxo de revisão do DOC-08.",
], "red"));

// ============================================================ 2. Fontes

body.push(h1("2. Fontes"));
body.push(table(["Fonte", "Recurso", "Uso", "Volume e ritmo"], [1500, 3000, 2600, 2500], [
  ["PNCP", "/v1/contratacoes/publicacao, uma consulta por modalidade (19), por dia de publicação", "Processos de contratação: órgão, ente, modalidade, objeto, valores estimado e homologado, situação", "Perto de 6 mil por dia útil; 50 por página"],
  ["PNCP", "/v1/contratos, por dia de publicação", "Contratos: órgão, ente, fornecedor, valor global, data de assinatura, instrumento", "Perto de 8 mil por dia útil; 500 por página"],
  ["SICONFI", "/entes", "Cadastro de entes: nome, UF, esfera, população, capital", "Uma requisição, todos os entes"],
  ["SICONFI", "/extrato_entregas?id_ente=…&an_referencia=…", "Entregas declaradas: instituição, entregável, exercício, período, periodicidade, situação e data", "Duas consultas por ente (exercício anterior e corrente), toda semana"],
], { size: 17 }));
body.push(spacer(80));
body.push(t("Todas as requisições se identificam com o User-Agent do Lumen e o contato do responsável (RF-CO-09) e " +
  "respeitam os limites por fonte de `lumen.toml` (60 por minuto no PNCP, 50 no SICONFI), com a redução automática " +
  "quando a fonte responde 429. A coleta reaproveita os adaptadores, a camada bronze e os normalizadores do " +
  "pipeline principal (`lumen_ingestao`, `lumen_normalizacao`): o painel não tem leitor próprio das fontes."));

// ============================================================ 3. Arquitetura

body.push(h1("3. Arquitetura"));
body.push(...figure("18_paineis_fluxo.png", "Figura 1. Da fonte ao portal: coleta no GitHub Actions, estado nos anexos de uma versão, site no GitHub Pages.", 560, 760));
body.push(t("Três decisões dão forma ao desenho (ADR-028):"));
novaLista();
body.push(n("**Estado pequeno, por dia.** A coleta de um dia passa por bronze e silver num diretório temporário e sai " +
  "como um arquivo compacto, só com as colunas que o painel usa (perto de 0,7 MB comprimido). O bronze do dia é " +
  "descartado: a prova de cada número é a página pública do PNCP, ligada em cada linha, e o dia pode ser coletado de novo."));
body.push(n("**Estado nos anexos da versão painel-estado.** O repositório é público; os anexos de uma versão não têm " +
  "custo nem limite prático de espaço e ficam fora do 1 GB do Supabase, ocupado pelas eleições."));
body.push(n("**Site refeito inteiro e servido pelo GitHub Pages.** A cada publicação, `lumen painel publicar` soma todos " +
  "os dias e avalia todas as UFs na data do dia; o diretório resultante vai para o Pages. O tráfego do portal não " +
  "consome a cota de saída do Supabase."));

// ============================================================ 4. Pacote lumen_painel

body.push(h1("4. O pacote lumen_painel, módulo a módulo"));
body.push(t("Só biblioteca padrão, como o resto do Lumen. Todas as funções têm docstring (cobrada pelo teste do DOC-11)."));

body.push(h2("4.1 comum.py"));
body.push(table(["Nome", "O que faz", "Como e por quê"], [2400, 3300, 3900], [
  ["MODALIDADES", "Nome de cada uma das 19 modalidades do PNCP pelo código", "Lido de /api/pncp/v1/modalidades em 05/10/2026, com espaços sobrando e travessões normalizados, para os nomes ficarem iguais entre si"],
  ["UFS, CODIGO_DA_UF, NOMES_UF", "Código IBGE ↔ sigla ↔ nome do estado", "Nome de reserva quando o cadastro não traz o ente"],
  ["hoje_brasilia", "Data corrente em UTC-3", "O prazo legal é dia do calendário de Brasília, e as máquinas do GitHub rodam em UTC"],
  ["tipo_do_ente, uf_do_ente", "União (1), DF (53), estado (2 dígitos) ou município (7 dígitos); a UF pelo prefixo", "Código fora desses formatos vira None e não ganha arquivo"],
  ["link_pncp", "numeroControlePNCP → página pública (/app/editais/… ou /app/contratos/…)", "O tipo 1 é contratação; o 2, contrato. É a evidência de cada linha publicada"],
  ["valor, somar", "Reais com duas casas a partir do texto da silver; soma arredondada a centavos", "Decimal evita o erro de ponto flutuante na conversão; somas arredondadas a cada passo"],
  ["ler_json, gravar_json", "JSON com ou sem gzip, gravado por troca atômica", "gzip sem data no cabeçalho: o mesmo conteúdo dá os mesmos bytes"],
  ["instante_utc", "Instante ISO em UTC, sem frações", "Carimbo de geração dos arquivos"],
], { monoCols: [0], size: 17 }));

body.push(h2("4.2 cadastro.py"));
body.push(table(["Nome", "O que faz", "Como e por quê"], [2400, 3300, 3900], [
  ["Ente", "Um ente: código, nome, UF, esfera (F, E, M, D), população, capital", "Forma compacta guardada no estado"],
  ["Cadastro.da_silver", "Monta o cadastro a partir dos ente_federativo da silver (SICONFI /entes)", "Um por código, o mais recente; só códigos que tipo_do_ente reconhece"],
  ["Cadastro.nome", "Nome do ente; sem cadastro, União, o nome do estado ou o código", "O painel nunca fica sem rótulo"],
  ["Cadastro.da_uf", "Entes da UF, com ou sem o estado", "Lista que a conformidade consulta e a tabela de municípios da UF"],
  ["para_json, de_json, ler", "Ida e volta do arquivo cadastro-entes.json.gz", "Colunas declaradas no arquivo"],
], { monoCols: [0], size: 17 }));

body.push(h2("4.3 dia.py"));
body.push(table(["Nome", "O que faz", "Como e por quê"], [2400, 3300, 3900], [
  ["resumir_dia", "Processos e contratos publicados no dia, na forma compacta", "Ente pelo órgão que publicou (Orgao.ente_codigo_ibge); contrato pelo dia de publicação no horário de Brasília; objeto cortado em 240 caracteres; pessoa física e estrangeira sem nome nem documento"],
  ["coletar_dia", "Coleta (todas as modalidades e os contratos), normaliza e grava o dia", "Bronze e silver num temporário apagado no fim; falha de página, resposta de erro ou coleta interrompida: o dia não é gravado e volta na execução seguinte"],
  ["dias_guardados, nome_do_arquivo, ler_dia", "Que dias já estão no estado; nome contratacoes-AAAA-MM-DD.json.gz; leitura com conferência da versão", "Arquivo vazio com o nome certo conta como guardado: os fluxos baixam só os nomes para saber o que falta"],
  ["ResultadoDia", "Gravado ou não, contagens e problemas", "Saída do comando e registro do fluxo"],
], { monoCols: [0], size: 17 }));

body.push(h2("4.4 contratacoes.py"));
body.push(table(["Nome", "O que faz", "Como e por quê"], [2400, 3300, 3900], [
  ["Totais", "Processos, valor estimado, processos sem valor, contratos, valor global", "Estimado ausente ou zero conta como processo sem valor (sigiloso ou não informado)"],
  ["Acumulador", "Tudo o que se soma de um recorte: meses, modalidades, órgãos, fornecedores PJ, soma anônima de pessoas físicas, recentes", "Listas de recentes com tamanho fixo (25 processos e 15 contratos; 10 e 10 por órgão, para caber na memória com dezenas de milhares de órgãos)"],
  ["somar_dias", "Lê os dias em ordem e soma por ente, por órgão, por esfera e para o Brasil", "Linha sem ente reconhecido vai só para o Brasil e para sem_ente"],
  ["ente_para_json", "Arquivo de um ente; o de um estado traz os municípios da UF", "Municípios do cadastro e os que publicaram, por nome, com zero quando não publicaram"],
  ["orgao_para_json", "Arquivo de um órgão, com o ente a que pertence", "Para quem procura uma entidade: um serviço autônomo de água e esgoto, uma fundação, uma empresa pública"],
  ["teto_do_ente", "Teto de plausibilidade de um processo ou contrato: R$ 10 bilhões ou R$ 20 mil por habitante do ente, o menor", "Acima dele, conta na quantidade e fica fora das somas, em \"valores a conferir\""],
  ["orgaos_para_busca", "Todo órgão com publicação no período: CNPJ, razão social, ente, esfera, processos e contratos", "Para a busca do portal achar uma entidade pelo nome, pela sigla ou pelo CNPJ"],
  ["panorama_para_json", "Brasil: esferas, UFs (governo do estado e municípios), meses, modalidades, 30 maiores fornecedores", "UFs em ordem alfabética; nada ordenado por risco"],
  ["Painel.cobertura", "Primeiro e último dia, quantos e os que faltam entre eles", "O portal mostra o período e os dias ainda sem coleta"],
], { monoCols: [0], size: 17 }));

body.push(h2("4.5 conformidade.py"));
body.push(table(["Nome", "O que faz", "Como e por quê"], [2400, 3300, 3900], [
  ["coletar_uf", "Extrato de entregas dos entes da UF, nos exercícios pedidos; grava conformidade-UF.json.gz", "Grava mesmo com consultas que falharam: o ente fica com a coleta marcada como malsucedida e a avaliação sai indeterminada"],
  ["coletas_por_ente", "Se o extrato de cada (ente, exercício) veio inteiro", "Lê id_ente e an_referencia da URL de cada registro do bronze; todas as páginas precisam de 200 ou 204"],
  ["estado_da_uf", "Guarda só as entregas da LRF (DCA, RREO, RGF e simplificados) e a situação da coleta", "Corta as entregas mensais da MSC, que não entram na avaliação"],
  ["Entrega", "A entrega com os campos que entregas_siconfi lê", "Instante convertido ao horário de Brasília: entrega às 22 h do último dia está no prazo"],
  ["avaliar_ente", "Obrigações do ente vencidas até a data, já avaliadas", "DCA do exercício anterior; RREO de cada bimestre encerrado; RGF de cada período encerrado na periodicidade declarada, por Poder"],
  ["_instituicao_nao_identificada", "Troca \"não consta\" por indeterminado quando o extrato tem RGF do período só de outra instituição", "O nome que o Tesouro dá à instituição varia; a dúvida é do Lumen, não do ente"],
  ["resumo", "Quantas obrigações em cada resultado e a fração entregue no prazo", "A fração conta só as determinadas; as indeterminadas aparecem à parte"],
  ["avaliar, uf_para_json, panorama_para_json", "Todas as UFs na data do dia; arquivos da UF e do Brasil", "Ordem por UF e por nome (PUB-07)"],
], { monoCols: [0], size: 17 }));

body.push(h2("4.6 site.py e cli.py"));
body.push(table(["Nome", "O que faz", "Como e por quê"], [2400, 3300, 3900], [
  ["Site", "Grava os arquivos do site num diretório limpo, sem sair da raiz", "O site é refeito inteiro; caminho que escapa da raiz é recusado"],
  ["lumen painel cadastro", "Coleta e grava o cadastro de entes", "Recusa cadastro com menos de mil entes: o anterior continua valendo"],
  ["lumen painel contratacoes", "Coleta os dias que faltam, do mais recente ao mais antigo, até o prazo", "--ultimos (padrão 3), --de/--ate, --limite-minutos, --refazer; código 1 se algum dia não foi gravado"],
  ["lumen painel faltando", "Blocos de dias seguidos que faltam, em JSON", "Matriz das execuções paralelas de paineis-carga"],
  ["lumen painel conformidade", "Coleta as UFs pedidas", "Exercícios padrão: o anterior e o corrente"],
  ["lumen painel publicar", "Monta o site inteiro a partir do estado", "--hoje fixa a data da avaliação (testes e reprocessamento)"],
], { monoCols: [0], size: 17 }));

body.push(h2("4.7 pares.py"));
body.push(table(["Nome", "O que faz", "Como e por quê"], [2400, 3300, 3900], [
  ["formar", "Grupos de pares dos entes do cadastro", "Usa lumen_canonico.pares (ADR-038): municípios por porte e região, com recuo para o porte no país abaixo de 15; estados e DF num grupo; população do SICONFI"],
  ["distribuicao", "Quartis e mediana da fração entregue no prazo", "Só entes com obrigação avaliável; quatro casas"],
  ["acrescentar", "Bloco pares no arquivo de cada ente avaliado e o arquivo de cada grupo", "Ente sem grupo leva o motivo, e a tela omite a comparação (UC-06, exceção 5a)"],
  ["pessoal_do_ente", "Bloco pessoal: o percentual da despesa com pessoal do Executivo e os limites do RGF, com os quartis do percentual no grupo (ADR-042)", "Distribuição só com 15 entes do grupo com o RGF lido"],
  ["despesa_por_habitante, distribuicoes_de_despesa, despesa_do_ente", "Bloco despesa: o total e cada função por habitante do ente, com os quartis do grupo (ADR-041)", "População do cadastro; distribuição só com 15 entes do grupo com a DCA lida e somando o total; função não executada vale zero"],
], { monoCols: [0], size: 17 }));

body.push(h2("4.8 operacao.py"));
body.push(table(["Nome", "O que faz", "Como e por quê"], [2400, 3300, 3900], [
  ["resumir_fluxos", "Uma linha por fluxo de dados acompanhado (FLUXOS): execuções, falhas, a última e a última com sucesso em 30 dias", "Lê as execuções que o paineis-site grava com gh run list; fluxo diário sem sucesso há mais de 36 h está atrasado (ADR-039)"],
  ["volume_contratacoes", "Processos por dia nos últimos 60 dias, com a referência e o alerta", "Mediana do mesmo dia da semana em 8 semanas; dia útil abaixo da metade é alerta; feriado, ponto facultativo e ponte nacionais ficam de fora"],
  ["coleta_conformidade", "Por UF: quando o extrato foi coletado e quantos entes com coleta malsucedida", "Mais de 36 h é atraso"],
  ["alertas, operacao_para_json", "operacao.json, com os alertas do mais grave ao menos e os limiares", "As UFs atrasadas viram um alerta só; limiares iniciais, marcados como não calibrados"],
], { monoCols: [0], size: 17 }));

body.push(h2("4.9 rcl.py"));
body.push(table(["Nome", "O que faz", "Como e por quê"], [2400, 3300, 3900], [
  ["tipos_pelo_extrato, ordem_de_tentativa", "O tipo de RREO de cada ente pelo extrato de entregas do 6º bimestre", "O porte não diz se o ente publica o RREO completo ou o simplificado; o extrato diz. Sem a entrega, o ente não é consultado; sem extrato, vão os dois tipos"],
  ["coletar_uf (lumen painel rcl)", "RCL dos entes pendentes da UF: RREO, Anexo 03, 6º bimestre do exercício anterior", "Bronze e silver num diretório temporário; LinhaDemonstrativo; quem não publicou volta depois de 7 dias"],
  ["ler_rcl", "A RCL de todas as UFs para a publicação", "Só o exercício mais recente entre os arquivos"],
], { monoCols: [0], size: 17 }));

body.push(h2("4.10 despesa_funcao.py"));
body.push(table(["Nome", "O que faz", "Como e por quê"], [2400, 3300, 3900], [
  ["exercicio_padrao, entregues_pelo_extrato", "O último exercício com a DCA no prazo e quem a entregou, pelo extrato", "A DCA sai até 30/4 (municípios) e 31/5 (estados): o exercício anterior a partir de maio. Quem não tem a DCA no extrato não é consultado"],
  ["coletar_uf (lumen painel despesa-funcao)", "DCA, Anexo I-E, dos entes pendentes da UF", "Lotes de 50; não começa lote novo depois de --limite-minutos (todas as UFs); o lote de uma coleta interrompida continua pendente; quem não publicou volta depois de 7 dias"],
  ["despesas_da_silver, confere", "Total e funções (NN - Nome) da despesa liquidada, sem as intraorçamentárias", "As subfunções ficam de fora; as funções somam o total (tolerância de 1%), e a DCA que não soma fica fora das distribuições"],
  ["ler_despesas", "A despesa de todas as UFs para a publicação", "Só o exercício mais recente entre os arquivos"],
], { monoCols: [0], size: 17 }));

body.push(h2("4.11 pessoal.py"));
body.push(table(["Nome", "O que faz", "Como e por quê"], [2400, 3300, 3900], [
  ["consultas_pelo_extrato", "O tipo (RGF ou simplificado) e a periodicidade do RGF do Executivo no último período, pelo extrato", "Entrega da prefeitura ou do governo; sem ela, o ente não é consultado; sem extrato, vão o RGF quadrimestral e o simplificado semestral"],
  ["coletar_uf (lumen painel pessoal)", "RGF, Anexo 1, do Poder Executivo, dos entes pendentes da UF", "Lotes de 50 por combinação; --limite-minutos para todas as UFs; ente com combinação não consultada fica pendente; quem não publicou volta depois de 7 dias"],
  ["pessoal_da_silver", "Percentual da despesa total com pessoal sobre a RCL ajustada, valores e limites declarados", "Coluna que começa com % para os percentuais e Valor para os valores; o tipo exato vem da consulta que achou o dado"],
  ["ler_pessoal", "O percentual de todas as UFs para a publicação", "Só o exercício mais recente entre os arquivos"],
], { monoCols: [0], size: 17 }));

body.push(h2("4.12 cnpj.py"));
body.push(table(["Nome", "O que faz", "Como e por quê"], [2400, 3300, 3900], [
  ["listar, mes_mais_recente, baixar", "A pasta do mês da base de CNPJ no compartilhamento da Receita e cada ZIP", "WebDAV público (token como usuário); download retomado por Range; quatro tentativas"],
  ["fornecedores_do_estado", "Os CNPJs de fornecedor dos dias do PNCP guardados", "Só eles entram (minimização, ADR-043)"],
  ["ler_empresas, ler_estabelecimentos, ler_socios, ler_simples", "As linhas dos fornecedores em cada conjunto", "Filtro pela posição fixa do CNPJ antes do CSV; sem endereço, telefone, e-mail e CPF de sócio; CPF do MEI mascarado"],
  ["coletar (lumen painel cnpj)", "Grava cnpj-fornecedores.json.gz com as tabelas usadas", "Um ZIP de cada vez, apagado depois; pula quando o estado tem o mês para todos"],
  ["publicar", "cnpj/<3 dígitos>.json.gz (comprimido, com os códigos) e cnpj/tabelas.json (os nomes)", "Lido pelo cartão do fornecedor em Contratações, que descomprime no navegador; sem compressão a base teria 402 MB no site"],
], { monoCols: [0], size: 17 }));

body.push(h2("4.13 emendas.py"));
body.push(table(["Nome", "O que faz", "Como e por quê"], [2400, 3300, 3900], [
  ["data_do_arquivo, baixar", "A data e o ZIP das emendas no Portal da Transparência", "Arquivo de dados abertos, sem chave; só baixa quando o Last-Modified muda"],
  ["categoria", "A categoria do favorecido pela natureza jurídica", "Governo municipal ou estadual, entidade, empresa, pessoa física; o agente financeiro (o banco que opera os repasses) fica sem lugar"],
  ["indice_de_lugares, APELIDOS", "O código IBGE pelo nome do município do favorecido", "Cruzamento sem acento com o cadastro; nomes antigos numa tabela de apelidos"],
  ["ler, coletar (lumen painel emendas)", "O recebido por ente, emenda, categoria e favorecido, e a descrição das emendas", "Pessoa física só na soma; CPF do MEI mascarado; o que não tem lugar fica nos totais por ano"],
  ["publicar", "emendas/ente/<grupo>.json.gz (3º a 5º dígitos do município, ou a UF)", "Comprimido e em grupos de 1 a 46 municípios, para a implantação do Pages caber no prazo; lido pelo mandato aberto em Governos municipais"],
], { monoCols: [0], size: 17 }));

body.push(h2("4.14 convenios.py"));
body.push(table(["Nome", "O que faz", "Como e por quê"], [2400, 3300, 3900], [
  ["data_do_arquivo, baixar", "A data na página de download e o ZIP dos convênios", "Arquivo de dados abertos, sem chave; só baixa quando sai um novo"],
  ["ler, coletar (lumen painel convenios)", "Os convênios por ente, pelo tipo do convenente", "Início de 2001 em diante; anulados e excluídos fora; o estado na UF; pessoa física só na soma; município pelo nome, com os apelidos"],
  ["publicar", "convenios/ente/<grupo>.json.gz (3º a 5º dígitos do município, ou a UF)", "Comprimido e em grupos, como as emendas; lido pelo mandato aberto em Governos municipais"],
], { monoCols: [0], size: 17 }));

// ============================================================ 5. Estado

body.push(h1("5. Estado guardado entre execuções"));
body.push(t("Anexos da versão `painel-estado` do repositório (pré-lançamento, não é uma versão do software). Linhas em " +
  "lista, na ordem declarada em `colunas` dentro de cada arquivo."));
body.push(table(["Arquivo", "Conteúdo", "Colunas"], [2800, 3000, 3800], [
  ["contratacoes-AAAA-MM-DD.json.gz", "Um dia do PNCP: órgãos, processos e contratos", "processos: chave, orgao, ente, uf, municipio, modalidade, valor_estimado, valor_homologado, objeto, situacao, srp. contratos: chave, orgao, ente, uf, municipio, tipo_pessoa, fornecedor_cnpj, fornecedor_nome, valor_global, data_assinatura, processo, instrumento, objeto. orgaos: razao_social, esfera, ente"],
  ["conformidade-UF.json.gz", "Entregas da LRF de cada ente da UF e a situação da coleta por exercício", "instituicao, entregavel, exercicio, periodo, periodicidade, status, entregue_em"],
  ["cadastro-entes.json.gz", "Cadastro do SICONFI", "nome, uf, esfera, populacao, capital"],
  ["rcl-UF.json.gz", "Receita corrente líquida de cada ente da UF no exercício anterior (RREO, Anexo 03), ou a data da última tentativa sem dado", "por ente: rcl, demonstrativo, coletado_em ou tentado_em"],
  ["convenios.json.gz", "Convênios da União por ente (ADR-045), com a data do arquivo da CGU", "convenios (por código IBGE: número, situação, objeto, órgão, categoria, cnpj, convenente, valor, liberado, contrapartida, início, fim, última liberação), pessoa_fisica, fora"],
  ["emendas.json.gz", "Emendas parlamentares recebidas por ente (ADR-044), com a data do arquivo da CGU", "recebido (por código IBGE: ano, emenda, categoria, cnpj, favorecido, valor), emendas (ano, tipo, autor, número, função, ação), sem_lugar"],
  ["cnpj-fornecedores.json.gz", "Base de CNPJ da Receita dos fornecedores (ADR-043): empresa, estabelecimento, Simples e sócios, com o mês e as tabelas de código usadas", "por CNPJ: empresa, estabelecimento, simples, socios; pedidos (os CNPJs procurados)"],
  ["pessoal-UF.json.gz", "Despesa com pessoal do Executivo de cada ente da UF no último período do exercício anterior (RGF, Anexo 1), ou a data da última tentativa sem dado", "por ente: percentual, dtp, rcl_ajustada, limites (alerta, prudencial, maximo), demonstrativo, periodo, periodicidade, coletado_em ou tentado_em"],
  ["despesa-funcao-UF.json.gz", "Despesa liquidada por função de cada ente da UF no último exercício com DCA (Anexo I-E), ou a data da última tentativa sem dado", "por ente: total, funcoes (código da função → valor), coletado_em ou tentado_em"],
], { monoCols: [0], size: 17 }));
body.push(spacer(80));
body.push(callout("Dados pessoais no estado", [
  "O estado é público. Contrato com pessoa física ou estrangeira guarda só o tipo de pessoa, o valor e as datas: " +
  "fornecedor_cnpj e fornecedor_nome ficam nulos. Pessoa jurídica guarda CNPJ e razão social, publicados nas bases de " +
  "origem (DOC-08, seção 5). Um teste confere que nome e documento de pessoa física não aparecem no arquivo do dia.",
], "red"));

// ============================================================ 6. Site

body.push(h1("6. Site publicado"));
body.push(t("Endereço: `https://dracon-46.github.io/FalkyriaLumen/` (variável `NEXT_PUBLIC_DADOS_PAINEL` no build do " +
  "portal; sem ela, este endereço). JSON sem compressão: o Pages comprime na entrega. Todo arquivo tem `versao` (1) e " +
  "`tipo`, conferidos pelo portal antes de usar."));
body.push(table(["Caminho", "tipo", "Conteúdo"], [3200, 2200, 4200], [
  ["indice.json", "—", "Quando foi gerado, data da avaliação, cobertura de cada painel"],
  ["entes.json", "—", "Cadastro para a busca: código, nome, UF, esfera, população"],
  ["orgaos.json", "orgaos", "Órgãos para a busca: CNPJ, razão social, ente, esfera, processos, contratos"],
  ["contratacoes/panorama.json", "contratacoes-panorama", "Brasil: totais, esferas, UFs, meses, modalidades, fornecedores, recentes"],
  ["contratacoes/ente/<grupo>.json.gz", "contratacoes-entes", "Os entes do grupo (3º a 5º dígitos do município, ou o código), cada um como contratacoes-ente; o de um estado com os municípios da UF. Comprimido"],
  ["contratacoes/orgao/<grupo>.json.gz", "contratacoes-orgaos", "Os órgãos do grupo (6º a 8º dígitos do CNPJ), cada um como contratacoes-orgao, com o ente a que pertence. Comprimido"],
  ["conformidade/panorama.json", "conformidade-panorama", "Brasil, por obrigação e por UF"],
  ["conformidade/uf/<sigla>.json", "conformidade-uf", "Entes da UF com o resumo de cada um"],
  ["conformidade/ente/<código>.json", "conformidade-ente", "Obrigações avaliadas de um ente e o grupo de pares"],
  ["operacao.json", "operacao", "Situação das coletas: fluxos, volume diário do PNCP e coleta da conformidade (ADR-039)"],
  ["conformidade/pares/<id>.json", "conformidade-pares", "Um grupo de pares: critérios, distribuição da fração no prazo e os entes que o formam, por nome"],
], { monoCols: [0, 1], size: 17 }));

// ============================================================ 7. Regras de soma

body.push(h1("7. Regras de soma das contratações"));
body.push(b("**Ente pelo órgão que publicou.** Os números de um município são os dos órgãos municipais — prefeitura, " +
  "câmara, autarquias (como um serviço autônomo de água e esgoto), fundações e empresas públicas, que o PNCP marca com a " +
  "esfera municipal —, e não os de órgãos estaduais ou federais situados nele. Órgão sem esfera no PNCP fica só no " +
  "panorama nacional, na linha \"Não informada\"."));
body.push(b("**Data de publicação.** Processo e contrato contam no dia em que foram publicados no PNCP (o filtro das " +
  "consultas), não na data de assinatura ou de abertura."));
body.push(b("**Valores como publicados.** Valor estimado sigiloso ou zerado conta como processo sem valor. O painel não " +
  "corrige valores."));
body.push(b("**Teto de plausibilidade.** Processo ou contrato com valor acima de R$ 10 bilhões, ou de R$ 20 mil por " +
  "habitante do ente (perto de quatro anos do orçamento por habitante de um município médio), o que for menor, conta nas " +
  "quantidades, mas o valor fica fora de todas as somas (ente, órgão, mês, modalidade, esfera, UF, fornecedor) e aparece " +
  "na seção \"Valores a conferir na fonte\", com o link da publicação. Motivo: na primeira semana coletada, um único " +
  "contrato publicado com R$ 239,8 bilhões (e outro com R$ 17,7 bilhões) fazia 97% do valor de contratos do país e " +
  "punha uma empresa pequena no topo da lista de fornecedores. Não é juízo sobre o órgão nem sobre o fornecedor; o " +
  "aviso metodológico e a própria seção dizem isso. Função `teto_do_ente`; constantes `TETO_ABSOLUTO` e " +
  "`TETO_POR_HABITANTE`."));
body.push(b("**Pessoa física anônima.** Contratos com pessoa física ou estrangeira entram numa soma única, sem nome nem " +
  "documento (RNF-19, RNF-20)."));
body.push(b("**Sem dia incompleto.** Um dia com falha de coleta não entra; o portal mostra quantos dias do período ainda " +
  "não têm coleta."));

// ============================================================ 8. Conformidade

body.push(h1("8. Avaliação da conformidade"));
body.push(table(["Obrigação", "Dispositivo", "Prazo", "Quem"], [2600, 2200, 2800, 2000], [
  ["Contas anuais (DCA)", "LC 101/2000, art. 51, § 1º", "30 de abril do ano seguinte (estados: 31 de maio até 2021)", "Ente"],
  ["RREO, por bimestre", "LC 101/2000, art. 52", "30 dias após o fim do bimestre", "Ente"],
  ["RGF, por quadrimestre ou semestre", "LC 101/2000, art. 55, § 2º", "30 dias após o fim do período", "Município: prefeitura e câmara; estado e DF: Poder Executivo"],
], { size: 17 }));
body.push(spacer(80));
body.push(t("Os prazos vêm de `lumen_deteccao/parametros_legais.toml`, com a vigência de cada redação. A decisão de cada " +
  "obrigação é a de `lumen_conformidade.entregas_siconfi`, na ordem que protege o ente:"));
novaLista();
body.push(n("Coleta do extrato malsucedida, ou prazo sem parâmetro conferido: **indeterminado**."));
body.push(n("Há entrega: vale a data mais antiga das versões originais (as retificadas só na falta delas). Até o prazo: " +
  "**entregue no prazo**. Depois: **entregue após o prazo**, salvo quando só existe a versão retificada, caso em que o " +
  "atraso não pode ser afirmado: indeterminado."));
body.push(n("Sem entrega e prazo vencido: **não consta no extrato**. Sem nenhum RGF no exercício, a periodicidade " +
  "escolhida pelo ente (art. 63) não é conhecida: indeterminado."));
body.push(n("RGF do período só de outra instituição: indeterminado (instituição não identificada pelo nome)."));
body.push(spacer(60));
body.push(t("Cada resultado sai com o ícone e o texto, nunca só com a cor:"));
body.push(table(["Resultado", "Texto publicado", "Ícone", "Cor (claro / escuro)"], [2200, 2800, 1000, 3600], [
  ["cumpre", "Entregue no prazo", "✓", "#0A7A33 / #5FD08A"],
  ["cumpre_parcialmente", "Entregue após o prazo", "!", "#9A6500 / #E6B04A"],
  ["nao_cumpre", "Não consta no extrato", "×", "#B42318 / #FF8A7A"],
  ["indeterminado", "Indeterminado (com o motivo)", "?", "#5E5D58 / #B5B4AB"],
], { monoCols: [0, 3], size: 17 }));
body.push(spacer(60));
body.push(t("Contraste das quatro cores sobre a superfície do portal: de 4,8:1 a 6,4:1 no tema claro e de 7,6:1 a 9,0:1 " +
  "no escuro (WCAG AA pede 4,5:1 para texto)."));
body.push(h2("8.1 Comparação com o grupo de pares (ADR-038)"));
body.push(t("A página do ente mostra a fração dele entregue no prazo ao lado da mediana e dos quartis da mesma fração " +
  "entre os entes do seu grupo de pares, com a descrição do grupo e os critérios. Grupo regional com menos de 15 " +
  "municípios recua para o porte no país, e a tela diz isso; grupo abaixo de 15 leva a ressalva. Com o cadastro de " +
  "outubro de 2026, são 33 grupos para os 5.597 entes avaliados: 31 regionais, o nacional dos municípios acima de 500 " +
  "mil habitantes e o dos estados e DF. A posição no grupo é contexto: não ordena, não classifica e não vira indício."));
body.push(t("Com a DCA do último exercício (ADR-041), o mesmo cartão mostra a despesa por função: o total gasto em cada " +
  "função e a fatia do total, e, no filtro \"por habitante, com o grupo\", o valor por habitante do " +
  "ente, a mediana e a metade central do grupo (do 1º ao 3º quartil) e de que lado dela o ente fica. Aparecem o total e " +
  "as sete funções de maior mediana no grupo, e o resto fica em \"ver todas\". A tela lista as causas comuns de " +
  "diferença (equipamento regional que atende vizinhos, classificação por função que varia, população desatualizada, " +
  "DCA como foi entregue) e liga para a DCA do ente no SICONFI. Sem escore e sem destaque: a marcação é a regra H-01, " +
  "da Fase 2."));
body.push(t("Com o RGF do último período (ADR-042), o cartão mostra também a despesa total com pessoal do Poder Executivo " +
  "em % da RCL ajustada, os limites de alerta, prudencial e máximo que o próprio relatório declara (LRF, arts. 20, 22 e " +
  "59) e de que lado deles o percentual fica, ao lado da mediana e da metade central do grupo. São os números do ente: a " +
  "verificação do cumprimento cabe ao tribunal de contas, e a tela diz isso."));

// ============================================================ 9. Portal

body.push(h1("9. Portal"));
body.push(table(["Arquivo", "Papel"], [4200, 5400], [
  ["src/lib/paineis.ts", "Endereços (com validação de código, CNPJ e UF antes de virar caminho), tipos dos arquivos, leitura com conferência de versão e tipo, busca de entes e de órgãos (nome, sigla pelas iniciais, município do órgão ou CNPJ), formatos de reais, meses, datas e CNPJ"],
  ["src/componentes/paineis/Comuns.tsx", "Busca de ente e, em Contratações, de órgão (combobox com setas, Enter e Esc; \"SAAE Sorocaba\" acha o serviço autônomo de água e esgoto pela sigla e pelo município), aviso metodológico (PUB-08), número em destaque, gráfico de barras por mês com tabela recolhida, selo de resultado"],
  ["src/componentes/paineis/PainelContratacoes.tsx", "Brasil, ente (?ente=) e órgão (?orgao=); tabelas de modalidades, fornecedores, órgãos, UFs e municípios; publicações recentes com link do PNCP"],
  ["src/componentes/paineis/PainelConformidade.tsx", "Brasil, UF (?uf=) e ente (?ente=); obrigações por exercício, que viram blocos no celular"],
  ["src/componentes/paineis/GrupoPares.tsx", "Grupo de pares do ente: descrição, ressalvas, a fração do ente ao lado da mediana e dos quartis do grupo, e a lista dos entes do grupo, sob demanda e por nome"],
  ["src/componentes/paineis/DespesaComPessoal.tsx", "Despesa com pessoal do Executivo em % da RCL ajustada, os limites do RGF e a mediana do grupo, com o link do RGF (ADR-042)"],
  ["src/componentes/paineis/DespesaPorFuncao.tsx", "Despesa por função do ente: o total gasto e a fatia de cada função (padrão) ou, no filtro, por habitante ao lado da mediana e da metade central do grupo, com as ressalvas e o link da DCA (ADR-041)"],
  ["src/componentes/paineis/EmpresaReceita.tsx, src/lib/receita.ts", "Cartão \"Na Receita Federal\" do fornecedor filtrado em Contratações: cadastro, Simples e quadro societário (ADR-043)"],
  ["src/componentes/economia/EmendasMandato.tsx, src/lib/emendas.ts, src/lib/comprimido.ts", "Emendas parlamentares recebidas no mandato aberto de Governos municipais, por categoria, autor e favorecido, e a leitura dos arquivos .json.gz no navegador (ADR-044)"],
  ["src/componentes/economia/ConveniosMandato.tsx, src/lib/convenios.ts", "Convênios da União iniciados no mandato aberto de Governos municipais, com a situação no SIAFI e a lista (ADR-045)"],
  ["src/componentes/Ligacoes.tsx", "Faixa \"Este município nas outras abas\": Contratações, Conformidade, Governos municipais e Eleições do mesmo ente (visão 360, ADR-035 e ADR-040)"],
  ["src/app/contratacoes/page.tsx, src/app/conformidade/page.tsx", "Páginas estáticas que envolvem os painéis em Suspense (leem a URL no navegador)"],
  ["src/app/operacao/page.tsx, src/componentes/paineis/PainelOperacao.tsx, src/lib/operacao.ts", "Situação das coletas (/operacao/, link no rodapé): alertas, fluxos, volume diário do PNCP e coleta da conformidade (ADR-039)"],
], { monoCols: [0], size: 17 }));
body.push(...figure("19_tela_contratacoes.png", "Figura 2. Contratações de um município, com dados sintéticos de teste: totais, gráficos por mês, modalidades, fornecedores e órgãos (inclusive a autarquia de água e esgoto).", 600, 640));
body.push(...figure("20_tela_conformidade.png", "Figura 3. Conformidade de um município: resumo e obrigações por exercício (extrato real de 2025 de São Sepé, RS; 2026 sintético).", 600, 560));
body.push(b("**Gráfico.** Uma série por gráfico (processos por mês; valor dos contratos por mês), barras finas com a ponta " +
  "arredondada, grade discreta em três linhas, rótulo do valor ao passar o mouse ou com o foco do teclado, e a mesma " +
  "série em tabela, recolhida."));
body.push(b("**Ausência.** Ente sem arquivo de contratações: \"nenhuma contratação encontrada no PNCP no período já " +
  "coletado\", com o link para a conformidade do ente (UC-01, exceção 4a). Ente ainda não avaliado na conformidade: a " +
  "próxima coleta semanal."));
body.push(b("**Celular.** Sem rolagem horizontal em 390 px de largura (conferido com Playwright): colunas secundárias " +
  "escondidas e obrigações empilhadas."));

// ============================================================ 10. Operação

body.push(h1("10. Operação"));
body.push(table(["Fluxo", "Quando", "O que faz"], [2400, 2400, 4800], [
  ["paineis.yml", "Todo dia às 05:17 (Brasília); às segundas, também 05:47; à mão", "Dias que faltam entre os últimos 5; cadastro de entes; às segundas (ou com a entrada conformidade), o extrato de todas as UFs em 5 máquinas; publica"],
  ["paineis-carga.yml", "À mão", "Meses anteriores: divide os dias que faltam desde \"de\" em \"partes\" blocos (padrão 12) e coleta no máximo 4 ao mesmo tempo; publica"],
  ["paineis-site.yml", "Chamado pelos dois acima; à mão", "Baixa o estado, grava as execuções dos fluxos (gh run list, permissão actions: read), monta o site e publica no GitHub Pages"],
], { monoCols: [0], size: 17 }));
body.push(h3("Configuração, uma vez"));
novaLista();
body.push(n("Settings → Pages → Build and deployment → Source: **GitHub Actions** (feito em 14/10/2026)."));
body.push(n("Segredo `LUMEN_CONTATO` (já usado pelas eleições). Nada mais: os anexos usam o token da própria execução."));
body.push(n("Actions → `paineis-carga` → Run workflow, com \"de\" em 2026-01-01; repetir até não faltar dia. Depois, " +
  "Actions → `paineis` → Run workflow com conformidade marcada, para a primeira coleta do SICONFI."));
body.push(h3("Comandos locais"));
body.push(code([
  "lumen painel cadastro --estado estado/",
  "lumen painel contratacoes --estado estado/ --ultimos 3",
  "lumen painel contratacoes --estado estado/ --de 2026-09-01 --ate 2026-09-30 --limite-minutos 300",
  "lumen painel faltando --estado estado/ --de 2026-01-01 --partes 12",
  "lumen painel conformidade --estado estado/ --ufs RS,SC --exercicios 2025,2026",
  "lumen painel publicar --estado estado/ --saida site/ --hoje 2026-10-14",
]));
body.push(h3("Limites"));
body.push(b("Até mil anexos por versão: perto de três anos de dias. Antes disso, juntar os dias de meses fechados num " +
  "arquivo por mês."));
body.push(b("GitHub Pages: 1 GB por site e 100 GB de tráfego por mês (limites flexíveis); o site dos painéis fica na casa " +
  "das centenas de MB com dezenas de milhares de órgãos."));
body.push(b("Uma máquina do GitHub coleta perto de 8 minutos por dia do PNCP; um bloco de 24 dias cabe nas 5 horas de " +
  "--limite-minutos."));

// ============================================================ 11. Verificação

body.push(h1("11. Verificação"));
body.push(table(["Conjunto", "Quantidade", "O que cobre"], [3000, 1400, 5200], [
  ["packages/painel/testes", "30", "Dia compacto com as respostas reais do PNCP (01/09/2026), pessoa física sem identificação, dia incompleto não gravado (falha, resposta de erro, coleta interrompida), soma por ente, órgão, esfera e UF, cobertura e dias faltando, avaliação da conformidade com o extrato real de São Sepé (RS), instituição não identificada, obrigações só até a data, coleta por UF, comandos e publicação de ponta a ponta"],
  ["packages/portal (vitest)", "10 novos", "Busca de entes e de órgãos (sigla, município, CNPJ), leitura do entes.json e do orgaos.json, validação de caminhos, conferência de versão e tipo, formatos e topo do eixo do gráfico"],
], { size: 17 }));
body.push(spacer(80));
body.push(t("Conferência visual em navegador real (Playwright) com dados sintéticos: Brasil, município, órgão, estado, " +
  "ente sem dados, conformidade do Brasil, da UF e do ente, celular (390 px) e a busca; sem erro no console além do 404 " +
  "esperado do ente sem dados, e sem rolagem horizontal."));

// ============================================================ 12. Próximos passos

body.push(h1("12. Próximos passos e riscos"));
body.push(table(["Item", "Por quê", "Quando"], [3400, 4600, 1600], [
  ["Portais da transparência municipais", "Estatais da Lei 13.303 e o que o município só publica no próprio portal ficam fora do PNCP. Três etapas: cadastro do endereço do portal de cada município; conformidade de transparência do portal (RF-CF-01, RF-CF-03, RF-CF-04); leitura por fornecedor de sistema, dos que atendem mais municípios para os que atendem menos", "Próxima fase"],
  ["Atualização dos processos", "O valor homologado chega depois da publicação; a consulta /v1/contratacoes/atualizacao traria os resultados", "Próxima versão"],
  ["Juntar dias em meses", "Limite de mil anexos por versão", "Antes de 2029"],
  ["Valor digitado errado", "Valores acima do teto já ficam fora das somas (seção 7); erro menor que o teto (um contrato de R$ 50 mil digitado como R$ 50 milhões numa capital) ainda entra. Comparar com o valor estimado do processo do mesmo contrato é o próximo passo", "Revisão do DOC-07"],
  ["Indícios", "Quando as regras forem calibradas e revisadas, os painéis ganham a camada de sinalização, com o fluxo do DOC-08", "Fase 2"],
], { size: 17 }));

L.buildDoc({
  codigo: "DOC-13",
  titulo: "Painéis de Contratações e Conformidade",
  subtitulo: "O que cada ente publicou no PNCP e as entregas da LRF ao Tesouro, com a fonte de cada número",
  meta: { versao: "2.0", data: "21 de outubro de 2026", situacao: "Proposta — acompanha o ADR-028, o ADR-038, o ADR-039, o ADR-041 e o ADR-042",
    verificado: "outubro de 2026" },
  body,
  outFile: path.join(__dirname, "..", "docs", "DOC-13_Paineis.docx"),
});
