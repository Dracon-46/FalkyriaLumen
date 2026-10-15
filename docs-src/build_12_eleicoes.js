// DOC-12 — Aba Eleições: idealização, fontes, arquitetura, contrato dos
// feeds, operação na noite da apuração, verificação e integração com o Lumen.
//
// Os números citados aqui (padrões, limites, contagens) são os do código em
// packages/eleicoes e packages/portal; quem muda um lado atualiza o outro.

const path = require("path");
const fs = require("fs");
const {
  Paragraph, TextRun, Table, TableRow, TableCell, WidthType, ShadingType, BorderStyle, VerticalAlign,
} = require("docx");
const L = require("./lib");
const { h1, h2, h3, p, pRuns, bullet, bulletRuns, numberedRuns, table, callout, code, figure, pageBreak, spacer } = L;

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

// Texto preto ou branco sobre a amostra, pelo que tiver mais contraste (WCAG).
function tintaSobre(hex) {
  const canal = (i) => {
    const c = parseInt(hex.slice(1 + 2 * i, 3 + 2 * i), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  const lum = 0.2126 * canal(0) + 0.7152 * canal(1) + 0.0722 * canal(2);
  return (lum + 0.05) / 0.05 >= 1.05 / (lum + 0.05) ? "000000" : "FFFFFF";
}

// Tabela da paleta: a única cor fora de diagrama é a da própria amostra.
function tabelaPaleta(linhas) {
  const larguras = [1100, 1500, 1500, 5500];
  const borda = { style: BorderStyle.SINGLE, size: 2, color: "D9D9D9" };
  const celula = (conteudo, largura, opts = {}) => new TableCell({
    width: { size: largura, type: WidthType.DXA },
    shading: { type: ShadingType.CLEAR, fill: opts.fill || "FFFFFF" },
    margins: { top: 60, bottom: 60, left: 110, right: 110 },
    verticalAlign: VerticalAlign.CENTER,
    children: [new Paragraph({
      children: [new TextRun({ text: conteudo, size: 19, bold: !!opts.bold, color: opts.cor,
        font: opts.mono ? "Consolas" : undefined })],
      spacing: { after: 0 },
    })],
  });
  const cab = new TableRow({
    tableHeader: true,
    children: ["Posição", "Fundo claro", "Fundo escuro", "Uso"].map((h, i) =>
      celula(h, larguras[i], { fill: L.NAVY, bold: true, cor: "FFFFFF" })),
  });
  const corpo = linhas.map(([pos, clara, escura, uso]) => new TableRow({
    children: [
      celula(pos, larguras[0], { bold: true }),
      celula(clara, larguras[1], { fill: clara.slice(1), cor: tintaSobre(clara), mono: true }),
      celula(escura, larguras[2], { fill: escura.slice(1), cor: tintaSobre(escura), mono: true }),
      celula(uso, larguras[3]),
    ],
  }));
  return new Table({
    width: { size: larguras.reduce((a, c) => a + c, 0), type: WidthType.DXA },
    columnWidths: larguras,
    borders: { top: borda, bottom: borda, left: borda, right: borda, insideHorizontal: borda, insideVertical: borda },
    rows: [cab, ...corpo],
  });
}

// Paleta lida do próprio portal, para o documento não divergir do código.
function lerPaleta(nome) {
  const fonte = fs.readFileSync(path.join(__dirname, "..", "packages", "portal", "src", "lib", "cores.ts"), "utf8");
  const bloco = fonte.match(new RegExp(`export const ${nome} = \\[([\\s\\S]*?)\\] as const`));
  if (!bloco) throw new Error(`paleta ${nome} não encontrada em cores.ts`);
  return [...bloco[1].matchAll(/"(#[0-9a-fA-F]{6})"/g)].map((m) => m[1].toUpperCase());
}
const CLARA = lerPaleta("PALETA_CLARA");
const ESCURA = lerPaleta("PALETA_ESCURA");

// ============================================================ 1. Idealização

body.push(h1("1. Idealização"));
body.push(t("A aba Eleições é a área do Lumen para consultar resultados de eleições brasileiras — municipais, " +
  "estaduais e federais —, tanto a apuração em andamento quanto as eleições passadas desde 1933 (por município " +
  "de 1994 em diante; antes disso, por UF, que é como o TSE publica). Fica dentro " +
  "do portal do Lumen como mais uma aba, ao lado de Contratações e Conformidade, com código, marca e dados " +
  "próprios: tudo vem direto do Tribunal Superior Eleitoral (TSE) e do IBGE, sem intermediário."));
body.push(t("A ideia nasceu da observação de portais de apuração que se tornaram referência por um motivo simples: " +
  "mostram o resultado oficial num mapa e numa lista legível, atualizados sozinhos, sem exigir que a pessoa " +
  "entenda o sistema do tribunal. O Lumen adota o mesmo formato de leitura — mapa, candidatos, comparecimento, " +
  "evolução da apuração — e acrescenta o que é próprio do projeto: cada número aponta para o arquivo oficial de " +
  "onde saiu, com o hash da cópia guardada."));

body.push(h2("1.1 Princípios"));
body.push(table(["Princípio", "O que significa na prática"], [2700, 6900], [
  ["Dado oficial, sem projeção", "Só somas e percentuais sobre os totais publicados pelo TSE. Nenhuma projeção, tendência, pesquisa ou estimativa (ADR-019, item 5)."],
  ["Rastreável", "Todo feed carrega a origem: fonte, URL do arquivo original, instante da coleta e SHA-256 da cópia guardada na camada bronze. A tela mostra os três."],
  ["Coleta responsável", "Um coletor só, identificado no User-Agent, com limite de taxa e requisição condicional. Milhões de visitas não viram milhões de consultas ao TSE (princípio P6)."],
  ["Neutro", "A cor identifica a posição na votação, não o partido (ADR-020). Nenhum texto qualifica candidato ou partido."],
  ["Acessível", "Paleta validada para os três tipos de daltonismo; identidade nunca só pela cor (nome na legenda, na dica e na tabela); tabela sempre ao lado do mapa."],
  ["Barato de servir", "O portal é estático. Na noite de maior demanda, o custo é o de servir arquivos por CDN, não o de manter um servidor de aplicação."],
], { boldFirstCol: true }));

body.push(spacer(120));
body.push(callout("O que a aba não faz", [
  "Não gera indício, score nem severidade, e não cruza resultado eleitoral com contratações (ADR-024).",
  "Não projeta resultado, não mostra pesquisa e não comenta candidato, partido ou apuração.",
  "Não substitui o TSE: em caso de divergência, vale o arquivo oficial, cujo endereço está em cada tela.",
], "amber"));

body.push(h2("1.2 Como a aba se apresenta"));
body.push(t("A tela principal tem três controles no topo — eleição, busca (Ctrl+K) e modo TV — e uma faixa de " +
  "cargos. Abaixo, o mapa da abrangência escolhida (Brasil, UF ou município), a lista de candidatos, o quadro de " +
  "comparecimento e votos e o gráfico de evolução da apuração. Clicar numa UF desce para ela; clicar num " +
  "município, idem. O estado da tela vai para a URL, então qualquer recorte pode ser compartilhado por link."));
body.push(...figure("14_tela_aba_eleicoes.png",
  "Figura 1. Aba Eleições no computador: Presidente, Brasil (amostra de desenvolvimento com dados oficiais).", 600, 640));
body.push(...figure("15_tela_modo_tv.png",
  "Figura 2. Modo TV (?tv=1): fundo escuro, letras grandes, sem controles, para telão ou transmissão.", 600, 360));
body.push(t("O mapa é interativo: os botões + e − (e as teclas +, − e 0), Ctrl ou ⌘ + rolagem e a pinça do " +
  "trackpad aproximam em torno do cursor; aproximado, ele é arrastado com o mouse ou com um dedo, e dois dedos " +
  "aproximam na tela de toque. A rolagem simples continua rolando a página — o mapa não prende quem só quer " +
  "descer a tela — e mostra um lembrete do atalho."));
body.push(...figure("17_tela_mapa_aproximado.png",
  "Figura 3. Mapa aproximado no Nordeste (Presidente, 1950), com a dica da área sob o cursor.", 420, 420));

// ============================================================ 2. Escopo

body.push(h1("2. Escopo", { novaPagina: true }));
body.push(table(["Eleição", "Anos", "Cargos", "Onde é disputado", "Origem dos dados"], [1500, 1500, 2700, 1700, 2200], [
  ["Geral", "1994 a 2022 (passadas); 2026 (ao vivo)", "Presidente", "Brasil", "Dados abertos; sistema de resultados"],
  ["Geral", "idem", "Governador, Senador, Deputado Federal, Deputado Estadual, Deputado Distrital", "UF", "idem"],
  ["Municipal", "1996 a 2024", "Prefeito, Vereador", "Município", "Dados abertos; sistema de resultados quando a eleição é recente"],
  ["Geral, anterior a 1994", "1933 a 1990 (19 anos, 23 eleições contando os turnos)", "Os da época: Presidente e Vice-presidente (votados em separado até 1960), Governador e Vice-governador, Senador e Suplente de Senador, Deputado Federal e Estadual, Deputado (1933, Constituinte), Vereador (1934, Distrito Federal)", "UF (não há resultado por município)", "Dados abertos, conjuntos por UF"],
], { size: 18 }));
body.push(spacer(80));
body.push(t("Cada eleição aparece por turno (`2022-1t-geral`, `2022-2t-geral`, `2024-1t-municipal`…). Para cada " +
  "cargo há três níveis de leitura: Brasil, UF e município. Quando o cargo não tem resultado único num nível — " +
  "Prefeito na UF, Governador no Brasil —, o arquivo daquele nível é um **panorama**: quem lidera cada parte e " +
  "o placar por partido, em vez da lista de candidatos."));
body.push(t("As eleições de 1933 a 1990 entram no mesmo seletor, num grupo próprio (“1933 a 1990: só por " +
  "estado”). Nelas o mapa é o do Brasil por UF; ao descer para uma UF, a tela mostra o resultado do estado e uma " +
  "nota no lugar do mapa de municípios, e a busca por município leva ao estado dele (seção 3.2)."));
body.push(t("Eleições suplementares e consultas aparecem no catálogo do TSE, mas não estão cobertas pelos testes " +
  "nem pelo processamento de dados abertos; ficam na seção 12 como próximo passo."));

// ============================================================ 3. Fontes

body.push(h1("3. Fontes de dados"));
body.push(t("Três fontes, todas públicas e oficiais. Os formatos abaixo foram observados nos arquivos reais em " +
  "outubro de 2026 e estão guardados em `testes/fixtures/tse` e `testes/fixtures/ibge`, com README de cada captura. " +
  "Os testes de contrato (seção 10.3) alarmam quando algum deles muda."));

body.push(h2("3.1 Sistema de divulgação de resultados do TSE"));
body.push(t("É o sistema que alimenta a apuração ao vivo: arquivos JSON estáticos servidos por CDN em " +
  "`https://resultados.tse.jus.br/oficial`, regravados pelo tribunal conforme as seções são totalizadas. Mantém " +
  "a eleição em andamento e as recentes; as antigas saem do ar, e por isso as passadas vêm dos dados abertos."));
body.push(table(["Arquivo", "Caminho (a partir de /oficial)", "Uso"], [1700, 4800, 3100], [
  ["Catálogo", "comum/config/ele-c.json", "Eleições disponíveis, ciclo, códigos internos e cargos de cada uma"],
  ["Municípios", "{ciclo}/{ele}/config/mun-e{ele:06d}-cm.json", "Cadastro TSE dos municípios da eleição, com código IBGE e capital"],
  ["Resultado", "{ciclo}/{ele}/dados/{uf}/{uf}[{mun}]-c{cargo:04d}-e{ele:06d}-u.json", "Candidatos, votos, totais e situação numa abrangência"],
  ["Andamento", "{ciclo}/{ele}/dados/{uf}/{uf}-e{ele:06d}-ab.json", "Seções totalizadas de cada UF (no br) ou de cada município (na UF)"],
  ["Foto", "{ciclo}/{ele}/fotos/{uf}/{sq}.jpeg", "Foto do candidato pelo sequencial do TSE"],
], { monoCols: [1], size: 17 }));
body.push(spacer(80));
body.push(t("Particularidades tratadas em `tse.py`: números com vírgula decimal e ponto de milhar, como texto; " +
  "data e hora em campos separados (`dt`, `ht`), no horário de Brasília; UF do exterior com a sigla `zz`. " +
  "O servidor responde `304 Not Modified` a `If-Modified-Since`, e é isso que torna barata uma passada em que " +
  "pouco mudou. O arquivo de resultado traz a votação total de cada partido (`par.tvtn`), usada para ordenar os " +
  "partidos nos proporcionais mesmo quando a lista de candidatos de um município é limitada."));

body.push(h2("3.2 Portal de Dados Abertos do TSE"));
body.push(t("As eleições passadas vêm do Portal de Dados Abertos (CKAN): o pacote `resultados-AAAA` lista arquivos " +
  "ZIP hospedados na CDN do tribunal (`cdn.tse.jus.br/estatistica/sead/odsele`). Três conjuntos interessam:"));
body.push(table(["Conjunto", "Conteúdo", "Tamanho de referência"], [3600, 4000, 2000], [
  ["votacao_candidato_munzona_AAAA.zip", "Votos de cada candidato em cada zona de cada município", "2022: 642 MB compactado, mais de 4 GB descompactado"],
  ["detalhe_votacao_munzona_AAAA.zip", "Por zona: aptos, comparecimento, abstenção, brancos, nulos, válidos, legenda", "Pequeno perto do anterior"],
  ["Historico_Totalizacao_Presidente_BR_{T}T_AAAA.zip", "Evolução da totalização do Presidente, de 2018 em diante", "Pequeno"],
], { monoCols: [0], size: 17 }));
body.push(spacer(80));
body.push(t("Formato comum: CSV com cabeçalho, separador `;`, aspas duplas, codificação Latin-1; valores ausentes " +
  "como `#NULO#`, `#NULO`, `#NE` ou códigos `-1` e `-3`. O número de colunas varia por ano (38, 44 ou 50), e por " +
  "isso a leitura é sempre pelo nome da coluna, nunca pela posição. Cada ZIP traz um CSV por UF, um `_BR.csv` " +
  "com o Presidente em todos os municípios e no exterior, e um `_BRASIL.csv` que é a concatenação de todos."));
body.push(callout("Regra que evita contar votos duas vezes", [
  "O `_BRASIL.csv` é ignorado sempre que há arquivos por UF. As linhas de Presidente são lidas só do `_BR.csv`, " +
  "e os arquivos por UF as pulam. Sem essa regra, o Presidente sairia com o dobro (ou o triplo) dos votos.",
], "red"));
body.push(spacer(100));
body.push(h3("Diferenças entre anos que mudam o resultado"));
body.push(table(["Ano(s)", "O que a fonte faz", "O que o Lumen faz"], [1500, 4300, 3800], [
  ["1994", "Totais do detalhe parcialmente zerados (válidos = 0 com votos nominais > 0)", "Reconcilia os totais pelas parcelas e publica o aviso “Totais do detalhe da apuração incompletos na fonte; reconciliados pelas parcelas.”"],
  ["2000", "QT_VOTOS_NOMINAIS zerado; o voto está em QT_VOTOS_NOMINAIS_VALIDOS", "A votação do candidato é o maior dos dois campos"],
  ["2002 a 2014", "Sem QT_VOTOS_NOMINAIS_VALIDOS nem NM_TIPO_DESTINACAO_VOTOS", "Não distingue válido de anulado por candidatura indeferida; publica o aviso de que votos de candidaturas indeferidas podem aparecer somados aos válidos"],
  ["Qualquer", "Recorte sem linha no detalhe", "Válidos pela soma dos candidatos, com aviso"],
  ["2018 em diante", "Publica o histórico da totalização do Presidente", "Gera o gráfico de evolução das eleições passadas (historico-br.json)"],
], { size: 17 }));
body.push(spacer(80));
body.push(t("Os avisos aparecem na tela antes dos números (faixa amarela; havendo mais de um, numa lista dentro da " +
  "mesma faixa), nunca escondidos em nota de rodapé."));

body.push(h3("Eleições de 1933 a 1990"));
body.push(t("O pacote `resultados-AAAA` existe desde 1933, mas até 1990 em outro formato: não há votação por " +
  "município nem por zona, só por UF, em três conjuntos com endereço fixo na mesma CDN (em 1933 e 1934 o nome " +
  "termina em `_br`). Os 56 arquivos foram baixados e lidos por inteiro em 6 de outubro de 2026; o de partido de " +
  "1989 não existe na fonte."));
body.push(table(["Conjunto", "Conteúdo", "Colunas"], [3300, 4800, 1500], [
  ["votacao_candidato_uf_AAAA.zip", "Votos de cada candidato em cada UF, situação, partido, legenda", "26"],
  ["detalhe_votacao_uf_AAAA.zip", "Aptos, comparecimento, abstenção, nominais, brancos, nulos, legenda, seções", "22"],
  ["votacao_partido_uf_AAAA.zip", "Votos nominais e de legenda por partido ou coligação", "17"],
], { monoCols: [0], size: 17 }));
body.push(spacer(80));
body.push(t("Texto Latin-1 (com dois caracteres do Windows-1252 em toda a série, como o apóstrofo de “D’AVILA” em " +
  "1954), separador `;`, aspas, um arquivo por UF (ou um só para o país) dentro do ZIP. Só 1933 e 1934 têm cabeçalho; nos demais, a " +
  "ordem das colunas é a do Leia-me do TSE, reproduzida em `antigas.py`. `#NULO` (campo em branco) vale `-1` e " +
  "`#NE` (não registrado na época) vale `-3`; os dois viram ausência, nunca zero."));
body.push(table(["Particularidade da fonte", "O que o Lumen faz"], [4300, 5300], [
  ["Candidato sem número de urna até os anos 1980 (NUMERO_CAND = -1)", "Código estável derivado do nome (e do partido, nos cargos estaduais), que liga as linhas do mesmo candidato entre UFs; o feed marca `sem_numero` e o portal não exibe o código"],
  ["Linhas com votos e sem nome (1 em 1954, 22 em 1986)", "Entram como “Candidato nº N”, ou “Nome não registrado na fonte” quando também não há número, sem se fundir com outra linha"],
  ["Vice-presidente, vice-governador e suplente de senador votados em separado; em 1934 o código 8 era vereador; em 1933 o cargo era “Deputado”", "O cargo leva slug e nível próprios (`Cargo.slug_fixo`), em vez de ser confundido com o cargo atual de mesmo código"],
  ["1933 e 1934: dois “turnos” que eram etapas de apuração da mesma votação (Código Eleitoral de 1932); detalhe de 1933 sem turno (-3)", "Uma eleição por etapa, com aviso; o detalhe sem turno vale para as duas. Na 2ª etapa a soma dos candidatos passa do número de votantes (cada cédula contava para vários nomes), e os percentuais são sobre essa soma, com aviso"],
  ["1962: sigla e nome do partido em branco em todas as linhas", "O partido vem da composição da legenda quando ela é um partido só; composição de coligação não identifica partido"],
  ["Soma dos candidatos diferente do total nominal do detalhe (104 dos 1.586 resultados por UF e cargo; 75 com diferença acima de 0,5%)", "Base dos percentuais = o maior dos dois, e nenhum conjunto passa de 100%; diferença acima de 0,5% vira aviso dizendo qual total foi usado"],
  ["Brancos válidos até 1997; nulos até 1965", "Percentuais sempre sobre candidatos e legendas, com aviso da regra da época (também em 1994 e 1996, que vêm do formato novo)"],
], { size: 17 }));
body.push(spacer(80));
body.push(t("UFs da época. O mapa usa as fronteiras atuais; pintar uma UF antiga sobre um território que não era o " +
  "dela seria mostrar fato errado. Por isso cada UF da fonte vira um código do feed, e só as que correspondem a " +
  "uma área atual declaram o código IBGE:"));
body.push(table(["Na fonte", "No feed", "No mapa"], [3000, 3600, 3000], [
  ["DF antes de 1960 (a cidade do Rio de Janeiro)", "df-antigo — “Distrito Federal (cidade do Rio de Janeiro)”", "Botão abaixo do mapa"],
  ["GB (Guanabara, 1960 a 1975)", "gb", "Botão abaixo do mapa"],
  ["Fernando de Noronha, Iguaçu, Ponta Porã (territórios federais da época)", "fn, ig, pp", "Botão abaixo do mapa"],
  ["GP (Território do Guaporé) e RB (Território do Rio Branco)", "gp e rb, com o IBGE de Rondônia (11) e Roraima (14)", "Área de Rondônia e de Roraima: mesmo território, só o nome mudou"],
  ["ZZ (exterior, a partir de 1989)", "zz", "Botão abaixo do mapa, como nas eleições recentes"],
  ["Sigla atual (SP, MG…)", "a sigla, com o código IBGE", "Área da UF"],
], { size: 17 }));
body.push(...figure("16_tela_eleicao_1945.png",
  "Figura 4. Presidente, 1945: as quatro faixas de aviso numa só, o mapa por UF e, abaixo dele, as UFs da época sem área no mapa atual.",
  560, 700));

body.push(h2("3.3 IBGE"));
body.push(t("O mapa usa as malhas territoriais da API v3 do IBGE em TopoJSON (`formato=application/json`): uma " +
  "malha do Brasil por UF e uma por UF com os municípios, em qualidade `minima` por padrão (o portal desenha em " +
  "poucas centenas de pixels). Cada geometria traz o código IBGE em `codarea`. A API de localidades fornece os " +
  "nomes oficiais dos municípios, com acentos e caixa corretos — o TSE publica em maiúsculas sem padronização."));
body.push(t("A ligação TSE ↔ IBGE vem do próprio cadastro do TSE (`mun-e…-cm.json` traz os dois códigos) e fica " +
  "em `municipios.json`. Município sem código IBGE (exterior) usa a chave `zz-<código TSE>`."));
body.push(t("Malhas e cadastro vêm com o Lumen: as 28 malhas em qualidade `minima` (1,4 MB) e o cadastro da eleição " +
  "geral de 2026 com os nomes do IBGE (5.757 municípios, 186 deles no exterior) ficam em " +
  "`packages/eleicoes/lumen_eleicoes/dados`, com a proveniência (endereços, data e SHA-256) no `LEIAME.md` da " +
  "pasta. `preparar` e `amostra` os copiam para o diretório dos feeds sem sobrescrever o que já estiver lá; " +
  "`mapas` e `municipios` continuam baixando a versão corrente das fontes. Limitação conhecida: Boa Esperança do " +
  "Norte (MT), instalado em 2025, já está no cadastro mas ainda não na malha do IBGE; aparece na tabela e na busca."));

body.push(h2("3.4 Conferências feitas contra os arquivos reais"));
body.push(table(["Conferência", "Resultado"], [5600, 4000], [
  ["Soma dos votos do Presidente em SP, 1º turno de 2026 (fixture real do sistema de resultados)", "24.882.948 votos, igual ao total do arquivo"],
  ["Eleitorado apto do Brasil em 2022, somado dos dados abertos (teste de contrato pesado)", "156.454.011, igual ao publicado pelo TSE"],
  ["Malha do Acre com municípios (fixture real do IBGE)", "22 geometrias, uma por município"],
], { size: 18 }));

// ============================================================ 4. Arquitetura

body.push(h1("4. Arquitetura", { novaPagina: true }));
body.push(t("Dois pacotes: `packages/eleicoes` (Python, só biblioteca padrão, como o resto do Lumen — ADR-015) faz " +
  "toda a conversa com as fontes e grava os feeds; `packages/portal` (Next.js com exportação estática) só lê os " +
  "feeds. Não há banco de dados nem servidor de aplicação no caminho da noite da eleição."));
body.push(...figure("11_eleicoes_arquitetura.png",
  "Figura 5. Fontes oficiais, comandos do lumen eleicoes, camada bronze, feeds e portal estático.", 560, 500));

body.push(h2("4.1 Módulos"));
body.push(table(["Módulo", "Responsabilidade"], [2600, 7000], [
  ["modelo.py", "Tipos do domínio: Eleicao, Cargo, Candidato, ResultadoAbrangencia, MunicipioTse, AndamentoAbrangencia; tabela CARGOS (código TSE → slug, nome, nível)."],
  ["tse.py", "URLs e leitores do sistema de resultados (catálogo, municípios, resultado, andamento), conversão de números e datas, detecção de quem mudou."],
  ["coletor.py", "Coleta ao vivo: plano, passadas, fila de municípios, estado persistido, regravação dos feeds e do índice."],
  ["dados_abertos.py", "CKAN, ZIPs, leitura dos CSV pelo nome da coluna, agregação zona → município → UF → Brasil, regras por ano, histórico do Presidente."],
  ["historico.py", "Processamento de um ano inteiro dos dados abertos em feeds, um CSV por vez."],
  ["antigas.py", "Eleições de 1933 a 1990: leitura dos três conjuntos por UF, UFs da época, cargos da época, candidatos sem número, avisos e feeds (sem municípios)."],
  ["carga.py", "Baixar e processar um ano, escolhendo o formato pelo ano; usado por historico e por preparar."],
  ["preparacao.py", "O comando preparar: referências, portal, servidor, sistema de resultados e dados abertos, com registro do que já foi feito."],
  ["referencias.py e dados/", "Malhas do IBGE e cadastro de municípios que vêm com o pacote, e a cópia deles para o diretório dos feeds."],
  ["transferencia.py", "Download retomável (Range e If-Range), verificação de tamanho, SHA-256, manifesto e preservação de versões (ADR-021)."],
  ["feeds.py", "Contrato dos feeds: montagem de cada tipo de arquivo, cores, panoramas, índice e gravação atômica."],
  ["municipios.py", "Cadastro TSE ↔ IBGE, nomes legíveis, gravação de municipios.json."],
  ["geo.py", "Download e validação das malhas do IBGE."],
  ["simulacao.py", "Servidor que imita o sistema de resultados avançando por etapas; geração da amostra de desenvolvimento."],
  ["servidor.py", "Servidor local do portal exportado e dos feeds, com os mesmos cabeçalhos de cache da produção."],
  ["verificacao.py", "Conferência do contrato dos feeds gravados."],
  ["configuracao.py, cli.py", "Leitura do lumen.toml e variáveis de ambiente; comando lumen eleicoes."],
], { monoCols: [0], size: 17 }));
body.push(spacer(80));
body.push(t("A descrição função por função está no DOC-11 (Referência Técnica), gerado a partir do código."));

body.push(h2("4.2 Por que feeds estáticos"));
body.push(t("A alternativa óbvia — o navegador consultar o TSE — foi descartada por três motivos: multiplicaria a " +
  "carga sobre o tribunal na noite de maior demanda, deixaria o portal refém do CORS e da estabilidade de um " +
  "sistema de terceiros e não guardaria prova do que foi exibido. Uma API própria com banco resolveria os três, " +
  "mas acrescentaria um servidor para operar exatamente quando ele seria mais exigido. Arquivo estático com " +
  "`Cache-Control: no-cache` e resposta 304 escala sem esforço: a apuração muda em minutos, e o portal relê o " +
  "feed a cada 15 segundos (ADR-019)."));

// ============================================================ 5. Coleta ao vivo

body.push(h1("5. Coleta ao vivo", { novaPagina: true }));
body.push(t("O comando `lumen eleicoes ao-vivo --eleicao <id>` roda em passadas. Cada passada pergunta ao TSE o que " +
  "mudou, baixa só isso e regrava só os feeds afetados."));
body.push(...figure("12_eleicoes_passada.png", "Figura 6. Uma passada do coletor ao vivo.", 480, 820));

body.push(h2("5.1 O plano da noite"));
body.push(t("O plano (`plano_padrao`) decide o que coletar:"));
body.push(b("**Cargos:** todos os da eleição, ou só os passados em `--cargos`."));
body.push(b("**UFs:** nas eleições gerais, as 27 e o exterior (`zz`); nas municipais, as que o catálogo lista, " +
  "ou todas exceto o DF, que não tem municípios."));
body.push(b("**Municípios:** cargos majoritários sempre descem ao município; proporcionais estaduais só com " +
  "`--municipios-proporcionais` (um arquivo por município por cargo, com centenas de candidatos); Vereador é " +
  "sempre por município, porque não existe outro nível."));
body.push(b("**Fotos:** dos cargos majoritários nacionais e estaduais; as dos municipais só com " +
  "`--fotos-municipais` (dezenas de milhares de imagens)."));
body.push(b("**Orçamento:** até 600 arquivos de município por passada (`--orcamento`), os nunca baixados primeiro."));

body.push(h2("5.2 Quanto tempo leva para tudo ficar em dia"));
body.push(t("Brasil e UFs são lidos em toda passada e nunca esperam pelos municípios. Os municípios entram numa " +
  "fila. Na pior hora da noite, quando quase todos mudam a cada passada, a conta é esta (eleição geral, três " +
  "cargos majoritários):"));
body.push(table(["Grandeza", "Valor"], [6000, 3600], [
  ["Arquivos de município (cerca de 5.570 municípios × Presidente, Governador e Senador)", "cerca de 16.700"],
  ["Limite padrão do sistema de resultados (rpm_resultados)", "300 por minuto"],
  ["Tempo para percorrer todos uma vez", "cerca de 56 minutos"],
], { size: 18 }));
body.push(spacer(80));
body.push(t("Ou seja: com o limite padrão, a tela de um município pode ficar até perto de uma hora atrás da tela " +
  "da UF no pico da apuração. É uma escolha consciente (coleta responsável primeiro); se o TSE indicar que a CDN " +
  "suporta mais, basta subir `rpm_resultados`. Com fila pendente, o intervalo entre passadas cai para no máximo " +
  "5 segundos, para o limite de taxa — e não a espera — ser o gargalo."));

body.push(h2("5.3 Cores fixas durante a noite"));
body.push(t("A cor de cada candidato é atribuída na primeira leitura, pela ordem de votação no nível mais alto do " +
  "cargo, e não muda mais (`atribuir_cores`). Se um candidato ultrapassa outro, as cores não trocam — a troca " +
  "faria o mapa parecer mudar mais do que mudou. As cores ficam no estado do coletor e sobrevivem a reinício."));

body.push(h2("5.4 Reinício e falhas"));
body.push(b("**Estado persistido** em `[eleicoes].estado`: cores, partes (para remontar o mapa da UF sem baixar " +
  "todos os municípios de novo), pontos da evolução (até 2.000 por abrangência; acima disso saem os mais antigos, menos o primeiro) e fotos " +
  "já baixadas."));
body.push(b("**Falha de uma requisição** (rede, 5xx, 429) não derruba a passada: é contada no resumo e a próxima " +
  "passada tenta de novo. 404 é registrado como ausente (UF sem o cargo, por exemplo)."));
body.push(b("**Parada** (Ctrl+C ou sinal): a passada em curso termina, o índice é regravado com `ao_vivo = false` " +
  "e o estado é salvo. O portal deixa de exibir “ao vivo” mesmo que a apuração continue — ninguém vê um número " +
  "parado como se fosse atual."));
body.push(b("**Fim natural:** quando a totalização termina e a fila esvazia, o coletor faz a última passada e sai."));

body.push(h2("5.5 Prova"));
body.push(t("Cada resposta 200 do TSE vai para a camada bronze do Lumen (fonte `tse_resultados`), com SHA-256, URL, " +
  "instante e cabeçalhos — a mesma camada imutável das contratações. O feed carrega o hash e o identificador " +
  "dessa cópia, e a tela os mostra no rodapé. `--sem-bronze` desliga a gravação (útil só em teste)."));

// ============================================================ 6. Eleições passadas

body.push(h1("6. Eleições passadas"));
body.push(t("Dois passos por ano, separados de propósito: baixar (rede, demorado, retomável) e processar (local, " +
  "repetível sem rede)."));
body.push(code([
  "lumen eleicoes historico baixar --anos 2024,2022,1950",
  "lumen eleicoes historico processar --anos 2024,2022,1950",
]));
body.push(t("`--anos todos` vale os 35 anos com eleição ordinária nos dados abertos, de 2024 a 1933. O formato é " +
  "escolhido pelo ano (`carga.py`): de 1994 em diante, por município (seções 6.1 e 6.2); de 1933 a 1990, por UF " +
  "(seção 6.3). Só a votação por candidato é obrigatória: detalhe, votação por partido e histórico da " +
  "totalização ausentes na fonte (404) viram aviso, e um ZIP opcional corrompido é ignorado com aviso, sem " +
  "derrubar o ano. Para fazer tudo de uma vez, há `preparar` (seção 9.1)."));
body.push(spacer(60));

body.push(h2("6.1 Baixar"));
body.push(t("Os endereços vêm do pacote CKAN do ano; se o CKAN falhar, o comando monta os endereços conhecidos da " +
  "CDN. O download grava em `<nome>.parcial` e, se a conexão cair, retoma com `Range` e `If-Range` — se o arquivo " +
  "mudou no servidor entre as tentativas, recomeça do zero em vez de emendar versões diferentes. No fim, confere " +
  "o tamanho, calcula o SHA-256 e grava o manifesto (`<nome>.manifesto.json`), que entra na camada bronze. Versão " +
  "nova no servidor não apaga a anterior: ela é renomeada com o prefixo do próprio hash (ADR-021)."));
body.push(t("`--atualizar` consulta o servidor mesmo para arquivos já baixados (requisição condicional)."));

body.push(h2("6.2 Processar"));
body.push(...figure("13_eleicoes_historico.png", "Figura 7. Processamento de um ano dos dados abertos (1994 em diante).", 520, 560));
body.push(t("O detalhe (pequeno) é lido inteiro primeiro. O arquivo de votação (grande) é lido um CSV por vez, de " +
  "dentro do ZIP, sem descompactar no disco: primeiro o `_BR` (Presidente), depois cada UF. Cada CSV vira os " +
  "feeds do que contém antes de o próximo ser aberto, e a memória fica proporcional à maior UF, não ao Brasil."));
body.push(table(["Cargo", "Arquivos gerados por eleição (ano e turno)"], [2600, 7000], [
  ["Nacional (Presidente)", "br, uf-* e mu-*; historico-br de 2018 em diante"],
  ["Estadual", "uf-* e mu-*; panorama br (quem lidera em cada UF)"],
  ["Municipal", "mu-*; panoramas uf-* e br (quem lidera em cada município, placar por partido)"],
], { boldFirstCol: true, size: 18 }));
body.push(spacer(80));
body.push(t("O arquivo de município de cargo com muitos candidatos (Vereador, deputados) leva os 50 mais votados e " +
  "todos os eleitos (`--limite-municipio`); os demais são contados em `candidatos_omitidos`, e a lista completa " +
  "fica no arquivo da UF quando o cargo é estadual."));

body.push(h2("6.3 Eleições de 1933 a 1990"));
body.push(t("Os três ZIPs do ano são pequenos (de 10 KB a 640 KB) e lidos inteiros (`antigas.LeituraAno`), " +
  "organizados por eleição (ano e turno), cargo e UF. Linha repetida do mesmo candidato na mesma UF soma os " +
  "votos. Depois, `ProcessadorAnoAntigo` grava:"));
body.push(table(["Cargo", "Arquivos gerados"], [2600, 7000], [
  ["Nacional (Presidente, Vice-presidente)", "uf-* e br, com as UFs em partes; os candidatos do Brasil são a soma das UFs pelo código do candidato, e a cor de cada um é a mesma em todas as UFs"],
  ["Estadual (os demais)", "uf-* e o panorama br (quem lidera em cada UF)"],
], { boldFirstCol: true, size: 18 }));
body.push(spacer(80));
body.push(t("O índice marca a eleição com `municipios: false`. Os totais do Brasil só somam os do detalhe quando " +
  "todas as UFs o têm; senão, a base é a soma dos candidatos, com aviso — total incompleto não é apresentado " +
  "como total. Os 19 anos geram 1.670 feeds em cerca de 5 segundos, e todos passam em `verificar`."));

// ============================================================ 7. Contrato dos feeds

body.push(h1("7. Contrato dos feeds (versão 1)", { novaPagina: true }));
body.push(t("Tudo o que o portal mostra sai destes arquivos. O contrato está em `feeds.py` (Python, quem grava) e " +
  "`src/lib/tipos.ts` (TypeScript, quem lê); o ADR-019 registra a decisão."));
body.push(table(["Caminho (a partir do diretório dos feeds)", "Conteúdo"], [4400, 5200], [
  ["indice.json", "Eleições publicadas, cargos com dados e UFs de cada cargo; é o primeiro arquivo lido"],
  ["municipios.json", "Cadastro TSE ↔ IBGE (vem com o pacote), baixado pelo portal só quando a busca abre"],
  ["geo/br-uf.json, geo/uf-<sigla>-mu.json", "Malhas do IBGE em TopoJSON (vêm com o pacote)"],
  ["<eleição>/<cargo>/br.json", "Resultado (ou panorama) no Brasil, com as UFs em partes"],
  ["<eleição>/<cargo>/uf-<sigla>.json", "Resultado (ou panorama) na UF, com os municípios em partes; nas eleições de 1933 a 1990, a “sigla” pode ser um código da época (df-antigo, gb, fn, ig, pp, gp, rb)"],
  ["<eleição>/<cargo>/mu-<chave>.json", "Resultado no município; chave = código IBGE, ou zz-<código TSE> no exterior"],
  ["<eleição>/<cargo>/historico-<abr>.json", "Pontos da evolução da totalização"],
  ["fotos/…", "Fotos dos candidatos, copiadas do sistema de resultados"],
], { monoCols: [0], size: 17 }));

body.push(h2("7.1 Tipos de arquivo"));
body.push(table(["tipo", "Quando", "Campos principais"], [1500, 3300, 4800], [
  ["resultado", "Abrangência em que o cargo tem resultado único", "totalizacao, comparecimento, votos, candidatos (com cor, situação, vice), agremiacoes, quociente_eleitoral, partes, avisos, origem"],
  ["panorama", "Cargo visto acima do nível em que é disputado", "partidos (liderados, eleitos, votos, cor), partes (líder de cada uma; bancada nos proporcionais), totalizacao por partes"],
  ["historico", "Evolução da totalização", "candidatos (número, nome, partido, cor) e pontos (instante, % de seções, votos por número)"],
], { monoCols: [0], size: 17 }));

body.push(h2("7.2 Regras do contrato"));
body.push(b("**`versao` em todo arquivo.** Mudança incompatível sobe `VERSAO_ESQUEMA_FEED` no Python e `VERSAO_FEED` " +
  "no portal, no mesmo commit. O portal recusa versão desconhecida em vez de exibir número errado."));
body.push(b("**Números são números:** inteiros para votos, decimais com até 6 casas para percentuais; nunca texto " +
  "com vírgula. Datas em ISO 8601 com fuso."));
body.push(b("**Cor é índice,** de 0 a 7, ou -1 (cinza). A paleta é do portal (seção 8.1)."));
body.push(b("**Origem sempre presente:** fonte, URL, SHA-256, instante da coleta e registro no bronze; `simulacao` " +
  "e `amostra` marcam o que não é apuração real."));
body.push(b("**Gravação atômica:** cada arquivo é escrito ao lado e renomeado por cima, então o portal nunca lê um " +
  "JSON pela metade. No Windows, o arquivo que o servidor local está enviando não pode ser trocado naquele " +
  "instante; a gravação espera alguns milissegundos e tenta de novo (`feeds.substituir_arquivo`)."));
body.push(b("**Campos opcionais e aditivos** não mudam a versão: o portal ignora o que não conhece, e o ausente tem " +
  "valor padrão. Assim entraram `sem_numero` no candidato (o `numero` é só um código do feed e não é exibido) e " +
  "`municipios: false` na eleição do índice (publicada só por UF, sem mapa nem busca por município)."));

body.push(h2("7.3 Como o contrato é protegido"));
body.push(t("O Python gera uma amostra versionada (`testes/fixtures/eleicoes_feed`, 40 arquivos, com 1945, 1950 e " +
  "1989 entre as eleições) a partir das fixtures reais do TSE; um teste confere a amostra byte a byte contra uma " +
  "nova geração. Os testes do portal " +
  "(`validacao.test.ts`) leem a mesma amostra com o validador de produção. Mudou um lado sem o outro, um dos " +
  "dois testes falha. Depois de uma mudança intencional, a amostra é regenerada com:"));
body.push(code(["python -m lumen_eleicoes --saida testes/fixtures/eleicoes_feed amostra --sem-referencias"]));
body.push(t("`--sem-referencias` deixa de fora o mapa e o cadastro, que não fazem parte do contrato conferido."));

// ============================================================ 8. Regras de exibição

body.push(h1("8. Regras de exibição"));

body.push(h2("8.1 Paleta"));
body.push(t("Paleta categórica de oito posições em ordem fixa, com versão própria para o fundo escuro (modo TV e " +
  "tema escuro), validada para deuteranopia, protanopia e tritanopia (ADR-020). Os valores abaixo são lidos de " +
  "`src/lib/cores.ts` na geração deste documento."));
body.push(tabelaPaleta(CLARA.map((c, i) => [String(i), c, ESCURA[i] || "", i < 3
  ? "Lista, legenda, gráfico e mapa"
  : "Lista, legenda e gráfico; no mapa, aparece como “Outros”"])));
body.push(spacer(80));
body.push(t("No mapa (coroplético: todas as áreas lado a lado) só as três primeiras posições passam na validação de " +
  "todos os pares; da quarta em diante, a área aparece como “Outros”, e o nome continua na dica, na lista e na " +
  "tabela. Nos panoramas e nos cargos proporcionais, a cor é do partido, pela ordem do placar (eleitos, depois " +
  "partes lideradas, depois votos) — de novo pela posição, nunca pela cor tradicional do partido."));

body.push(h2("8.2 Leitura da tela"));
body.push(table(["Elemento", "Regra"], [2600, 7000], [
  ["Lista de candidatos", "Ordem do feed (mais votado primeiro); percentual dos válidos; vice ou 1º suplente; selo de eleito ou 2º turno como o TSE publica."],
  ["Mapa", "Pinta quem lidera cada parte; dica com líder, percentual, margem e seções totalizadas; contorno em destaque na área sob o cursor; clique desce de nível (o clique que termina um arrasto não desce). Aproxima até 16 vezes (seção 1.2). Partes sem área no mapa atual viram botões abaixo dele (no Brasil) ou uma nota (na UF)."],
  ["Eleições de 1933 a 1990", "Grupo próprio no seletor; sem mapa de municípios nem evolução da apuração; número de urna oculto quando não existia; a busca por município leva ao estado."],
  ["Panorama", "Placar por partido com eleitos e partes lideradas; nos proporcionais, a bancada de cada partido na parte."],
  ["Evolução", "Eixo horizontal em % de seções totalizadas (não o relógio): mostra como a vantagem mudou conforme as urnas chegaram. Um só eixo vertical, em % dos válidos; quatro séries."],
  ["Faixas", "Simulação, amostra e ressalvas da fonte aparecem antes dos números."],
  ["Rodapé", "Fonte, link para o arquivo original e SHA-256 da cópia guardada."],
  ["Atualização", "Ao vivo, o portal relê o feed a cada 15 s com no-cache; o servidor responde 304 quando nada mudou. Eleição passada não se atualiza sozinha."],
  ["URL", "?e=<eleição>&c=<cargo>&a=<abrangência>&tv=1 — todo recorte é um link."],
  ["Busca", "Ctrl+K: UFs e municípios pelo nome, sem acento e sem caixa."],
  ["Celular", "Lista de candidatos antes do mapa; cabeçalho compacto."],
  ["Modo TV", "Fundo escuro, tipografia grande, seis candidatos, sem controles."],
], { boldFirstCol: true, size: 17 }));

// ============================================================ 9. Operação

body.push(h1("9. Operação"));

body.push(h2("9.1 Deixar pronto num comando"));
body.push(t("Os resultados não vão para o repositório: são vários GB de arquivos oficiais, corrigidos pelo TSE de " +
  "tempos em tempos, e a prova de cada número é o SHA-256 da cópia baixada da fonte (ADR-021 e ADR-025). O que " +
  "vem no repositório é o código, o mapa e o cadastro de municípios. Um comando busca e processa o resto:"));
body.push(code(["lumen eleicoes preparar --servir"]));
body.push(t("No Windows, dois cliques em `preparar.cmd`, na raiz do repositório: ele confere o `lumen.toml`, cria o " +
  "ambiente Python em `.venv`, instala o Lumen e roda o mesmo comando. As etapas, em ordem:"));
novaLista();
body.push(n("Mapa e cadastro de municípios no diretório dos feeds (`referencias.instalar`)."));
body.push(n("Portal: `npm ci` (se faltam as dependências) e `npm run build`, quando `out/` não existe ou o código " +
  "do portal é mais novo que ele. Sem Node.js, a etapa vira erro no resumo e as demais seguem."));
body.push(n("Com `--servir`: o servidor local sobe e o navegador abre antes da carga; cada eleição aparece no " +
  "portal assim que fica pronta. Porta ocupada: o sistema escolhe outra, e o endereço é impresso."));
body.push(n("Sistema de resultados: as eleições ordinárias que já aconteceram e ainda não estão nos dados abertos " +
  "(em outubro de 2026, o 1º turno de 2026), com todos os municípios, até a totalização terminar; se ela ainda " +
  "não terminou, para quando uma passada não traz nada novo e indica o `ao-vivo`. Eleição com data futura (o 2º " +
  "turno) fica para a noite da apuração."));
body.push(n("Dados abertos de 1933 a 1990 (cerca de 18 MB, poucos minutos)."));
body.push(n("Dados abertos de 2024 a 1994, do mais recente para o mais antigo: 2,3 GB de ZIPs e algumas horas na " +
  "primeira vez."));
body.push(t("É retomável: `<estado>/preparar.json` registra cada ano processado com o SHA-256 dos ZIPs de entrada, e " +
  "rodar de novo pula o que já está pronto. `--atualizar` consulta a fonte e só reprocessa o ano cujos arquivos " +
  "mudaram; `--refazer` ignora o registro. Erro num ano não interrompe os outros: o resumo final (em JSON) lista " +
  "o que falhou, e o comando devolve 1. Ctrl+C para ao fim da etapa em curso."));
body.push(table(["Opção", "Efeito"], [3400, 6200], [
  ["--servir [--porta 8080] [--sem-navegador]", "Sobe o portal antes da carga e abre o navegador"],
  ["--anos 2024,2022 | todos", "Restringe os anos dos dados abertos (padrão: todos)"],
  ["--sem-ao-vivo / --sem-historico / --sem-portal", "Pula a etapa correspondente"],
  ["--atualizar / --refazer", "Reprocessa o que mudou na fonte / tudo"],
  ["--municipios-proporcionais", "Na eleição do sistema de resultados, também os deputados por município"],
  ["--limite-municipio 50", "Candidatos por município nos cargos proporcionais"],
  ["--nuvem", "Restaura o estado do R2 antes e publica os feeds depois de cada ano e de cada passada (seção 9.5)"],
  ["--limite-minutos 280", "Não começa nada novo depois desse tempo; o ano em curso termina e a próxima execução continua"],
  ["--apagar-zips", "Apaga os ZIPs de cada ano depois de processado (máquina com pouco disco)"],
], { monoCols: [0], size: 17 }));

body.push(h2("9.2 Configuração"));
body.push(t("Seção `[eleicoes]` do mesmo `lumen.toml` do pipeline (modelo em `lumen.toml.exemplo`). Variável de " +
  "ambiente tem precedência sobre o arquivo, que tem precedência sobre o padrão."));
body.push(table(["Chave", "Padrão", "Para quê"], [2600, 3600, 3400], [
  ["[coleta].contato / LUMEN_CONTATO", "obrigatório", "Vai no User-Agent de toda requisição (RF-CO-09)"],
  ["[dados].raiz / LUMEN_DADOS", "dados", "Raiz da camada bronze, compartilhada com o Lumen"],
  ["saida / LUMEN_ELEICOES_SAIDA", "packages/portal/public/dados/eleicoes", "Diretório dos feeds. O padrão serve ao npm run dev com a amostra; para a carga completa, use \"dados/eleicoes/feeds\" (fora do portal), como no lumen.toml.exemplo"],
  ["arquivos", "<raiz>/eleicoes/arquivos", "ZIPs dos dados abertos e manifestos"],
  ["estado", "<raiz>/eleicoes/estado", "Estado do coletor ao vivo"],
  ["rpm_resultados", "300", "Sistema de resultados (CDN)"],
  ["rpm_dados_abertos", "30", "CKAN e CDN de arquivos"],
  ["rpm_ibge", "30", "Malhas e localidades"],
  ["NEXT_PUBLIC_DADOS_ELEICOES (build do portal)", "/dados/eleicoes", "Endereço dos feeds quando servidos de outro domínio"],
], { monoCols: [0], size: 17 }));
body.push(spacer(80));
body.push(t("A publicação na nuvem tem seção própria, `[publicacao]`, lida só por `--nuvem` e `publicar`. As chaves " +
  "de acesso nunca ficam no arquivo: só em variável de ambiente (no GitHub Actions, segredos do repositório)."));
body.push(table(["Chave", "Padrão", "Para quê"], [3400, 1800, 4400], [
  ["endpoint / LUMEN_PUBLICACAO_ENDPOINT", "obrigatório", "Endereço S3 do R2 (https://<id da conta>.r2.cloudflarestorage.com) ou do Supabase (https://<ref>.storage.supabase.co/storage/v1/s3, seção 9.7)"],
  ["bucket / LUMEN_PUBLICACAO_BUCKET", "obrigatório", "Bucket público dos feeds, lido pelo portal"],
  ["bucket_estado / LUMEN_PUBLICACAO_BUCKET_ESTADO", "o mesmo bucket", "Bucket privado do estado da carga e do manifesto da publicação"],
  ["regiao / LUMEN_PUBLICACAO_REGIAO", "auto", "Região da assinatura: o R2 usa auto; o Supabase, a região do projeto (ex.: sa-east-1), e a configuração recusa endpoint do Supabase sem ela"],
  ["paralelos / LUMEN_PUBLICACAO_PARALELOS", "16", "Envios simultâneos ao bucket público (no GitHub Actions, 32)"],
  ["limite_mb / LUMEN_PUBLICACAO_LIMITE_MB", "900 no Supabase; sem limite no R2", "Teto do bucket público, em MB: a publicação para entre dois lotes quando o total passa dele (0 tira o teto)"],
  ["LUMEN_S3_CHAVE_ACESSO e LUMEN_S3_CHAVE_SECRETA", "obrigatório", "Token da API S3 do R2, com leitura e escrita só nos dois buckets; no Supabase, as chaves S3 do projeto"],
], { monoCols: [0], size: 17 }));

body.push(h2("9.3 Comandos"));
body.push(table(["Comando", "O que faz"], [4400, 5200], [
  ["lumen eleicoes preparar [--servir]", "Tudo num comando, retomável (seção 9.1)"],
  ["lumen eleicoes preparar --nuvem", "A mesma carga numa máquina vazia, publicando no R2 (seção 9.5)"],
  ["lumen eleicoes publicar", "Envia ao bucket os feeds novos ou alterados e grava o estado; imprime enviados, iguais e bytes"],
  ["lumen eleicoes medir [--resumo arquivo]", "Tamanho dos feeds gravados: total, por grupo, maiores arquivos, se cabem no R2 e no Supabase gratuitos e o pior caso de saída por visitante e hora de apuração (seção 9.7); JSON na saída, Markdown no arquivo"],
  ["lumen eleicoes catalogo", "Lista as eleições do sistema de resultados e os anos dos dados abertos"],
  ["lumen eleicoes municipios [--eleicao <id>]", "Grava municipios.json (TSE ↔ IBGE)"],
  ["lumen eleicoes mapas [--ufs] [--qualidade]", "Baixa as malhas do IBGE"],
  ["lumen eleicoes ao-vivo --eleicao <id> [--nuvem]", "Coleta a apuração em andamento (seção 5); com --nuvem, publica a cada passada"],
  ["lumen eleicoes historico baixar --anos", "Baixa os ZIPs dos dados abertos (1933 a 2024)"],
  ["lumen eleicoes historico processar --anos", "Gera os feeds das eleições passadas"],
  ["lumen eleicoes simular", "Apuração fictícia a partir de arquivos finais reais"],
  ["lumen eleicoes amostra [--sem-referencias]", "Feeds de exemplo a partir das fixtures, sem rede, com o mapa e o cadastro"],
  ["lumen eleicoes servir [--porta 8080]", "Serve o portal exportado e os feeds localmente"],
  ["lumen eleicoes verificar", "Confere o contrato dos feeds gravados"],
], { monoCols: [0], size: 17 }));
body.push(spacer(80));
body.push(t("`python -m lumen_eleicoes` é equivalente a `lumen eleicoes`. Opções globais: `--config`, `--saida`, `-v`."));

body.push(h2("9.4 Roteiro da noite da eleição"));
body.push(h3("Na semana anterior"));
novaLista();
body.push(n("Conferir o id da eleição no catálogo: `lumen eleicoes catalogo`."));
body.push(n("Atualizar o cadastro e as malhas para a eleição: `lumen eleicoes municipios --eleicao <id>` e " +
  "`lumen eleicoes mapas` (os que vêm com o pacote podem estar um ciclo atrás)."));
body.push(n("Ensaiar com a simulação: `lumen eleicoes simular` e abrir o portal com `lumen eleicoes servir`. A tela " +
  "mostra a faixa de simulação; conferir avanço, troca de líder, mapa e gráfico."));
body.push(n("Rodar os testes de contrato (`LUMEN_TESTE_CONTRATO=1 pytest -m contrato`) para saber se o TSE mudou " +
  "algum formato desde a última eleição."));
body.push(n("Publicar o portal apontando `NEXT_PUBLIC_DADOS_ELEICOES` para os feeds. Na nuvem, o fluxo " +
  "`portal-pages.yml` faz isso, e `publicar` já grava `Cache-Control: no-cache` nos feeds (seção 9.5)."));
body.push(h3("No dia"));
novaLista();
body.push(n("Apagar os feeds e o estado da simulação do diretório de produção."));
body.push(n("Iniciar o coletor antes da divulgação dos primeiros resultados. Na nuvem: Actions → `eleicoes-ao-vivo` " +
  "→ Run workflow, com o id da eleição. Numa máquina:"));
body.push(code(["lumen eleicoes ao-vivo --eleicao 2026-1t-geral --intervalo 30 --nuvem"]));
body.push(n("Acompanhar o resumo de cada passada (requisições, baixados, 304, ausentes, feeds, fila, erros). Fila " +
  "crescendo sem parar indica limite de taxa baixo para o volume; erros repetidos indicam problema na fonte."));
body.push(n("Se for preciso reiniciar, basta rodar o mesmo comando: o estado preserva cores e evolução. Na nuvem, " +
  "a máquina tem prazo de 6 horas; se a totalização não terminou, dispare o fluxo de novo, e o estado " +
  "guardado no bucket privado continua a série."));
body.push(h3("Depois"));
novaLista();
body.push(n("O coletor termina sozinho quando a totalização acaba. O índice fica com `ao_vivo = false`."));
body.push(n("Quando os dados abertos do ano saírem, reprocessar pelo histórico; o feed passa a ter origem " +
  "`dados_abertos`, que é a base definitiva."));

body.push(h2("9.5 Na nuvem, sem computador ligado (ADR-026)"));
body.push(t("Nada disso precisa do computador de quem opera o Lumen. A carga, a publicação e o portal rodam em " +
  "serviços gratuitos, e o computador pessoal fica para desenvolvimento e uso local (`preparar --servir`)."));
body.push(table(["Parte", "Onde roda", "Como"], [2200, 3000, 4400], [
  ["Carga diária e retomada", "GitHub Actions: eleicoes-carga.yml", "Todo dia às 04:41 (Brasília) e quando disparada à mão: preparar --nuvem --sem-portal --sem-bronze --apagar-zips --limite-minutos 280"],
  ["Noite da eleição", "GitHub Actions: eleicoes-ao-vivo.yml", "À mão, com o id da eleição; publica a cada passada que gravou feeds"],
  ["Feeds", "Cloudflare R2, bucket público", "Cache-Control: no-cache nos feeds; um dia nas malhas, no cadastro e nas fotos"],
  ["Estado da carga", "Cloudflare R2 ou Supabase, bucket privado", "estado/preparar.json, estado do coletor ao vivo e o manifesto da publicação, um arquivo por grupo (publicacao/<grupo>.json) e o total de cada grupo (publicacao/_totais.json)"],
  ["Portal", "Vercel (Hobby) ou Cloudflare Pages: portal-pages.yml", "Vercel: importa o repositório com Root Directory packages/portal e gera a cada mudança do portal (vercel.json), sem token no GitHub. Pages: a cada mudança em packages/portal na main, ou à mão; cria o projeto na primeira vez"],
], { size: 17 }));

body.push(h3("Como a carga continua de uma execução para outra"));
body.push(t("A máquina do GitHub começa vazia a cada execução e tem prazo de 6 horas. O que a carga já fez fica no " +
  "bucket privado (`publicacao.Nuvem`):"));
novaLista();
body.push(n("`restaurar`: traz do bucket privado tudo o que está em `estado/` e, do público, o `indice.json` (se ainda " +
  "não existe na máquina). Se a restauração falhar, a carga não começa: sem o estado ela refaria tudo e " +
  "sobrescreveria o índice publicado."));
body.push(n("A carga roda como numa máquina local e pula o que o estado registra como pronto."));
body.push(n("Depois de cada ano e de cada passada do sistema de resultados que gravou feeds, `sincronizar` envia só " +
  "os arquivos cuja assinatura (os 24 primeiros dígitos do SHA-256) difere do manifesto, 16 de cada vez (32 no " +
  "GitHub Actions), os JSON comprimidos com gzip (`Content-Encoding: gzip`, um quinto do espaço), o índice por " +
  "último, depois de todos (o portal nunca aponta para um feed que ainda não subiu), e grava o estado. O " +
  "manifesto é regravado a cada 1.000 envios: uma interrupção no meio não obriga a reenviar o que já subiu."));
body.push(n("O manifesto é dividido por grupo: uma parte por eleição (`publicacao/2022-1t-geral.json`), uma para " +
  "`geo` e uma para os arquivos da raiz, comprimidas. Cada parte só é lida quando a carga tem arquivo daquele " +
  "grupo para enviar; com o histórico inteiro (perto de 450 mil arquivos), um manifesto único passaria do limite " +
  "de 50 MB por arquivo do Supabase e seria regravado inteiro a cada lote. `publicacao/_totais.json` guarda os " +
  "bytes de cada grupo no bucket público."));
body.push(n("Falha passageira de um envio (408, 429, 5xx, rede ou tempo esgotado) é tentada de novo depois de 2 e " +
  "de 8 segundos; outra falha, ou a terceira seguida, vira erro do lote."));
body.push(n("Antes de cada lote, se o total no bucket público passou de `limite_mb` (900 MB no Supabase), a " +
  "publicação para com erro, sem enviar o índice: o bucket não passa do plano gratuito por um ano a mais."));
body.push(n("Vencido `--limite-minutos`, nada novo começa; o ano em curso termina, o estado sobe e o resumo marca " +
  "`prazo_atingido`. A publicação tem 50 minutos de folga depois do prazo; passou dela, para entre dois lotes, " +
  "não grava o estado e deixa o resto para a execução seguinte, que gera o ano de novo e envia só o que faltou."));
body.push(t("Falha ao publicar não interrompe a carga: vira erro no resumo, e a próxima sincronização reenvia o que " +
  "faltou, porque o manifesto só registra o que subiu. `--apagar-zips` apaga os ZIPs de cada ano depois de " +
  "processado, para caber no disco da máquina; a prova de cada número continua sendo o SHA-256 do ZIP, registrado " +
  "na origem de todo feed (ADR-021)."));

body.push(h3("Configuração, uma vez"));
novaLista();
body.push(n("**Cloudflare.** Criar uma conta gratuita e, em Storage & databases → R2, concluir a assinatura do R2. " +
  "A tela de assinatura aparece mesmo no plano gratuito e pode pedir um meio de pagamento; o uso dentro dos " +
  "limites da seção 9.6 não é cobrado. Sem cartão, a alternativa para o 2º turno de 2026 é a da seção 9.7."));
body.push(n("Criar dois buckets na classe Standard (o plano gratuito não vale para Infrequent Access): `lumen-eleicoes`, " +
  "para os feeds, e `lumen-privado`, para o estado."));
body.push(n("No `lumen-eleicoes`, Settings → Public access: habilitar o endereço `r2.dev` e anotar o endereço " +
  "`https://pub-….r2.dev`. Ele tem limite de requisições e serve para começar; o portal público deve ler os " +
  "feeds de um domínio próprio ligado ao bucket (Custom Domains)."));
body.push(n("No `lumen-eleicoes`, Settings → CORS Policy → Add CORS policy, aba JSON. Trocar `lumen` pelo nome do " +
  "projeto no Pages; acrescentar o domínio próprio quando houver e, para testar o portal local contra o bucket, " +
  "`http://localhost:3000`:"));
body.push(code([
  "[",
  "  {",
  "    \"AllowedOrigins\": [\"https://lumen.pages.dev\"],",
  "    \"AllowedMethods\": [\"GET\", \"HEAD\"],",
  "    \"MaxAgeSeconds\": 3600",
  "  }",
  "]",
]));
body.push(n("Em R2 → API Tokens → Manage, criar um token com a permissão Object Read & Write, restrito aos dois " +
  "buckets. Copiar o Access Key ID e o Secret Access Key (o segundo aparece uma vez só). O endpoint é " +
  "`https://<id da conta>.r2.cloudflarestorage.com`."));
body.push(n("Em My Profile → API Tokens → Create Token, um token personalizado com Account → Cloudflare Pages → " +
  "Edit. Anotar o id da conta (Account ID, no painel). O projeto do Pages não precisa ser criado à mão."));
body.push(n("**GitHub.** Em Settings → Secrets and variables → Actions, os segredos e as variáveis da tabela abaixo."));
body.push(n("Actions → `eleicoes-carga` → Run workflow. A primeira carga leva duas ou três execuções: quando uma " +
  "termina com \"prazo atingido\", dispare de novo (ou espere a execução diária). Depois, Actions → " +
  "`portal-pages` → Run workflow; o portal fica em `https://<projeto>.pages.dev`."));
body.push(table(["Nome no GitHub", "Tipo", "Valor"], [3000, 1400, 5200], [
  ["LUMEN_CONTATO", "segredo", "E-mail do responsável pela coleta (vai no User-Agent, RF-CO-09)"],
  ["R2_ENDPOINT", "segredo", "https://<id da conta>.r2.cloudflarestorage.com"],
  ["R2_CHAVE_ACESSO", "segredo", "Access Key ID do token do R2"],
  ["R2_CHAVE_SECRETA", "segredo", "Secret Access Key do token do R2"],
  ["CLOUDFLARE_API_TOKEN", "segredo", "Token com Cloudflare Pages: Edit (passo 6)"],
  ["CLOUDFLARE_ACCOUNT_ID", "segredo", "Id da conta Cloudflare"],
  ["R2_BUCKET_FEEDS", "variável", "lumen-eleicoes"],
  ["R2_BUCKET_ESTADO", "variável", "lumen-privado"],
  ["LUMEN_URL_FEEDS", "variável", "https://pub-….r2.dev, ou o domínio próprio do bucket"],
  ["CF_PAGES_PROJETO", "variável", "lumen"],
], { monoCols: [0], size: 17 }));
body.push(spacer(80));
body.push(callout("Credenciais", [
  "Nenhuma chave vai para o repositório, para o lumen.toml ou para o código: só segredos do GitHub e variáveis " +
  "de ambiente. Se uma chave vazar, revogue o token no Cloudflare, crie outro e atualize o segredo; nada mais " +
  "muda.",
], "red"));

body.push(h3("Sem o GitHub Actions"));
body.push(t("A mesma carga roda em qualquer máquina com as variáveis de ambiente da publicação: " +
  "`lumen eleicoes preparar --nuvem`. Quem já tem a carga pronta no computador só publica: `lumen eleicoes " +
  "publicar` envia o que ainda não está no bucket. É também o caminho se as fontes do TSE recusarem conexões das " +
  "máquinas do GitHub, que ficam fora do Brasil."));

body.push(h2("9.6 Limites do plano gratuito"));
body.push(t("Verificados em 7 de outubro de 2026 (ADR-026). Os números de uso são estimativas da carga completa."));
body.push(table(["Limite", "Uso esperado", "Se passar"], [3300, 3300, 3000], [
  ["R2: 10 GB-mês armazenados", "Feeds de todas as eleições: 2 a 3 GB", "US$ 0,015 por GB-mês adicional"],
  ["R2: 1 milhão de escritas por mês", "Primeira carga: algumas centenas de milhares de envios; depois, só o que muda", "Cobrança por milhão adicional. Reprocessar todos os anos (--refazer) no mês da primeira carga pode passar"],
  ["R2: 10 milhões de leituras por mês", "Poucos arquivos por tela; a noite de eleição muito acessada é o caso a acompanhar", "Cobrança por milhão adicional"],
  ["R2: tráfego de saída", "Grátis, sem limite", "—"],
  ["Endereço r2.dev", "Limite de requisições, para desenvolvimento", "Domínio próprio ligado ao bucket"],
  ["GitHub Actions: 2.000 minutos por mês (repositório privado; público não conta)", "Primeira carga: duas ou três execuções de até 6 horas (até cerca de 1.000 minutos); depois, poucos minutos por dia", "Os fluxos param até o mês seguinte; o estado preserva o que foi feito"],
  ["GitHub Actions: 6 horas por execução", "--limite-minutos 280 deixa folga para terminar o ano em curso", "A máquina é encerrada; o que já subiu fica, e o ano em curso é refeito"],
  ["GitHub (repositório público): agendamento desligado após 60 dias sem atividade", "—", "Reativar o fluxo em Actions"],
], { size: 17 }));

body.push(h2("9.7 Alternativa sem cartão: Supabase Storage (adendo do ADR-026)"));
body.push(t("O R2 pede um meio de pagamento na assinatura, mesmo no plano gratuito. Sem ele, os feeds cabem no " +
  "armazenamento gratuito do Supabase, que fala o mesmo protocolo S3: o código é o mesmo, muda só a " +
  "configuração. Com os JSON comprimidos com gzip, as eleições de 1933 a 2026 somam perto de 850 MB e cabem no " +
  "1 GB gratuito (medição de 14/10/2026, abaixo)."));
body.push(table(["", "Cloudflare R2", "Supabase Storage gratuito"], [2400, 3600, 3600], [
  ["Armazenamento", "10 GB-mês", "1 GB, 50 MB por arquivo"],
  ["Saída (quem lê os feeds)", "Grátis, sem limite", "5 GB sem cache e 5 GB com cache por mês, somados a todo o uso da organização; passou, o projeto pode ser restringido até o mês seguinte"],
  ["Meio de pagamento", "Pedido na assinatura", "Não"],
  ["Eleições", "Todas, de 1933 a 2026", "Todas, de 1933 a 2026, com o JSON comprimido (perto de 850 MB); pouca folga para o que vier depois"],
  ["CORS", "Política no bucket (seção 9.5)", "Nada a configurar: o Supabase responde a qualquer origem nos buckets públicos (conferido em 14/10/2026)"],
  ["Arquivo inexistente", "404", "400 com not_found no corpo; o cliente S3 e o portal tratam como 404"],
  ["Pausa", "Não há", "Projeto gratuito pausa após uma semana sem uso; a carga diária o mantém ativo"],
  ["Endereço público dos feeds", "https://pub-….r2.dev ou domínio próprio", "https://<ref>.supabase.co/storage/v1/object/public/<bucket>"],
], { boldFirstCol: true, size: 17 }));
body.push(spacer(80));
body.push(t("A saída é o ponto a medir antes de escolher. Durante a apuração, o portal relê o feed nacional e a " +
  "evolução a cada 15 segundos e o índice a cada minuto. O fluxo `eleicoes-medir.yml` gera os feeds de 2026 numa " +
  "máquina do GitHub, sem publicar nada, e roda `lumen eleicoes medir`: o resumo da execução traz o tamanho total, " +
  "se cabe em 1 GB, o maior arquivo e o pior caso de saída por visitante e por hora (o feed mudando entre duas " +
  "leituras). Dividir 5 GB por esse número dá quantas horas-visitante a cota comporta; quando o feed não muda, " +
  "o navegador recebe só uma resposta 304, e o consumo real fica abaixo do pior caso."));
body.push(t("A primeira medição (13 de outubro de 2026, 1h06 de execução) deu o tamanho do 1º turno de 2026 completo:"));
body.push(table(["Medida", "Valor"], [4800, 4800], [
  ["Arquivos", "17.653 (17.127 feeds do 1º turno, 496 fotos, 28 malhas, índice e cadastro)"],
  ["Tamanho", "112,9 MB (35,4 MB com gzip): 11% do 1 GB gratuito"],
  ["Maior arquivo", "municipios.json, 615 kB (125 kB com gzip), abaixo do limite de 50 MB"],
  ["Visão Brasil, pior caso", "Feed de presidente de 3,3 kB com gzip: cerca de 1 MB por visitante e hora, perto de 5.000 horas-visitante na cota"],
  ["Visão de um estado grande, pior caso", "Feed de presidente em MG de 34 kB com gzip: cerca de 9 MB por visitante e hora, perto de 550 horas-visitante"],
], { boldFirstCol: true, size: 17 }));
body.push(spacer(80));
body.push(t("Recomendação para o 2º turno de 2026: o Supabase, gratuito sem meio de pagamento, que ao fim da cota para " +
  "de servir em vez de cobrar. O R2 fica para quando o portal for divulgado. " +
  "`lumen eleicoes medir` passou a estimar também a visão do estado mais pesado."));
body.push(t("A medição por anos (14 de outubro de 2026, oito execuções de 1 a 4 minutos, com `so_2026` desmarcado) " +
  "deu o tamanho do histórico, sem contar as malhas e o cadastro, que são os mesmos de 2026:"));
body.push(table(["Anos", "Arquivos", "Com gzip", "Execução"], [2600, 2000, 2000, 3000], [
  ["2026 (1º turno, 13/10)", "17.653", "35,4 MB", "1h06 (sistema de resultados)"],
  ["2024", "11.233", "28,6 MB", "41 s"],
  ["2022", "36.677", "83,9 MB", "4 min"],
  ["2018 e 2020", "48.144", "115,4 MB", "3 min"],
  ["2014 e 2016", "46.927", "110,5 MB", "3 min"],
  ["2010 e 2012", "46.174", "102,0 MB", "1 min"],
  ["2004, 2006 e 2008", "58.649", "129,3 MB", "4 min"],
  ["1994 a 2002", "112.612", "236,9 MB", "3 min"],
  ["1933 a 1990", "1.670", "5,3 MB", "1 min"],
  ["Total", "perto de 380 mil", "perto de 850 MB", ""],
], { boldFirstCol: true, size: 17 }));
body.push(spacer(80));
body.push(t("Sem compressão seriam perto de 4 GB. Com 85% do plano ocupado, a publicação tem um teto " +
  "(`LUMEN_PUBLICACAO_LIMITE_MB`, 900 MB por padrão no Supabase, seção 9.5) e para antes de passar dele. A " +
  "conferência dos feeds (`lumen eleicoes verificar`) apontou 630 municípios em que a soma dos votos dos " +
  "candidatos passa dos votos válidos do arquivo de detalhe (493 em 1998, quase todos de senador; 133 em 2000; 4 " +
  "em 2024): é divergência entre dois arquivos do próprio TSE, publicada como está, com a fonte de cada número."));
body.push(h3("Configuração, uma vez"));
novaLista();
body.push(n("Num projeto do Supabase da conta do mantenedor (nunca na organização de uma empresa que ele atende), " +
  "em Storage → Settings, habilitar a conexão S3 e anotar o endpoint e a região (ex.: `sa-east-1`)."));
body.push(n("Em Storage, criar o bucket `lumen-eleicoes` com Public bucket ligado e o bucket `lumen-privado` " +
  "desligado."));
body.push(n("Em Storage → Settings → S3 Access Keys, criar um par de chaves. A chave dá acesso a todos os " +
  "buckets do projeto e ignora as políticas de linha: só em segredo do GitHub."));
body.push(n("No GitHub, os mesmos nomes da seção 9.5, com os valores do Supabase:"));
body.push(table(["Nome no GitHub", "Tipo", "Valor no Supabase"], [3000, 1400, 5200], [
  ["R2_ENDPOINT", "segredo", "https://<ref>.storage.supabase.co/storage/v1/s3"],
  ["R2_CHAVE_ACESSO", "segredo", "Access key ID do par criado no passo 3"],
  ["R2_CHAVE_SECRETA", "segredo", "Secret access key do mesmo par"],
  ["R2_REGIAO", "variável", "A região do projeto (ex.: sa-east-1); obrigatória no Supabase"],
  ["R2_BUCKET_FEEDS", "variável", "lumen-eleicoes"],
  ["R2_BUCKET_ESTADO", "variável", "lumen-privado"],
  ["ELEICOES_SEM_HISTORICO", "variável", "false (ou ausente): a carga inclui os dados abertos de 1933 a 2024; true deixa só 2026, e a entrada historico da execução manual passa por cima"],
  ["PUBLICACAO_LIMITE_MB", "variável", "Opcional: teto do bucket público em MB (900 se ausente)"],
  ["LUMEN_URL_FEEDS", "variável", "https://<ref>.supabase.co/storage/v1/object/public/lumen-eleicoes"],
], { monoCols: [0], size: 17 }));
body.push(spacer(80));
body.push(n("Portal na Vercel (plano Hobby): Add New → Project → importar o repositório, Root Directory " +
  "`packages/portal`, variável `NEXT_PUBLIC_DADOS_ELEICOES` com o mesmo valor de `LUMEN_URL_FEEDS`. O " +
  "`vercel.json` do portal faz a Vercel gerar o site só quando `packages/portal` muda. Sem token no GitHub."));
body.push(n("Actions → `eleicoes-carga` → Run workflow (publica 2026 e, em duas ou três execuções, o histórico). Na " +
  "noite do 2º turno, `eleicoes-ao-vivo` com `2026-2t-geral`, como na seção 9.4."));
body.push(n("Durante a apuração, acompanhar a saída em Organization → Usage do Supabase. Se a cota se aproximar " +
  "do fim, a saída é passar os feeds para o R2: os mesmos segredos com os valores do R2 e um novo " +
  "`portal-pages` com o endereço do R2."));
body.push(callout("O que o Supabase não faz", [
  "O armazenamento do Supabase não tem trava contra apagar e sobrescrever (Object Lock). Serve para os feeds, que " +
  "são refeitos a partir das fontes; não serve para a prova (bronze), que continua exigindo o R2 com trava " +
  "(ADR-018 e ADR-026).",
], "red"));

// ============================================================ 10. Verificação

body.push(h1("10. Verificação"));
body.push(h2("10.1 Testes automatizados"));
body.push(table(["Conjunto", "Quantidade", "O que cobre"], [3000, 1400, 5200], [
  ["packages/eleicoes/testes", "203", "Leitores do TSE com arquivos reais, dados abertos com CSV sintético nos cabeçalhos reais dos três layouts, eleições de 1933 a 1990 com linhas reais recortadas de seis anos, download retomável, coletor contra servidor local, feeds (amostra byte a byte), cadastro, malhas e referências embutidas, servidor, preparar de ponta a ponta (com retomada e erro num ano), publicação na nuvem contra um S3 em memória (só o que mudou, índice por último, manifesto por grupo lido só quando preciso, teto do bucket, prazo entre lotes, novas tentativas, retomada em outra máquina, falhas de restauração e de publicação), configuração (inclusive a região exigida pelo Supabase), medição dos feeds contra os limites gratuitos e CLI"],
  ["packages/portal (vitest)", "84", "Leitura dos feeds (404 e o 400 de inexistente do Supabase), decodificador TopoJSON, validação dos feeds lendo a amostra do Python (inclusive as eleições antigas), formatação, cores, busca, estado na URL, grupos do seletor, área do mapa ↔ parte e as contas do zoom"],
  ["Suíte Python inteira", "862", "Eleições e o resto do Lumen; cobertura mínima de 80% exigida no CI (97% na data deste documento)"],
], { size: 17 }));
body.push(spacer(80));
body.push(t("Além dos testes: verificação de tipos do portal (`tsc`), build da exportação estática, ruff, o verificador " +
  "de vocabulário (que inclui o código de `lumen_eleicoes` e os textos do portal) e a cobrança de documentação " +
  "(ADR-023). Tudo roda no CI a cada push."));

body.push(h2("10.2 Verificação visual"));
body.push(t("As telas desta versão foram conferidas em navegador real (Playwright) nos recortes Brasil, UF, " +
  "panorama, município, celular, modo TV, busca e dica do mapa, e numa apuração simulada do início ao fim (20% → " +
  "100% das seções, com troca de líder). Na versão 1.1, também: aproximar pelos botões e por Ctrl + rolagem, " +
  "arrastar sem abrir a área sob o cursor, voltar ao mapa inteiro, o lembrete da rolagem simples, as 23 eleições " +
  "de 1933 a 1990 com os dados reais completos (territórios fora do mapa, Guaporé na área de Rondônia, UF sem " +
  "mapa de municípios, seletor em grupos), celular sem rolagem horizontal e nenhum erro no console. A " +
  "conferência visual ainda é manual: automatizá-la com capturas de referência no CI é um próximo passo (seção 12)."));

body.push(h2("10.3 Testes de contrato"));
body.push(t("Diários, contra as fontes reais (`.github/workflows/contrato.yml`); não bloqueiam, alarmam. Para a aba " +
  "Eleições: o catálogo e o arquivo de resultado do TSE mantêm os campos lidos; os cabeçalhos dos CSV dos dados " +
  "abertos continuam os esperados (lidos só o início do ZIP, com `Range`); a malha do IBGE continua TopoJSON. Um " +
  "teste pesado, ligado com `LUMEN_TESTE_CONTRATO_PESADO=1`, baixa o detalhe de 2022 e confere o eleitorado apto."));

// ============================================================ 11. Integração

body.push(h1("11. Integração com o Lumen"));
body.push(t("A aba Eleições mostra dado oficial; o resto do Lumen sinaliza atividades para análise em contratações. " +
  "Misturar os dois sem regra sugeriria relação entre resultado eleitoral e contratação, exatamente o tipo de " +
  "associação que o DOC-08 proíbe sem evidência. Por isso (ADR-024):"));
body.push(table(["Compartilha com o Lumen", "Não compartilha"], [4800, 4800], [
  ["Camada bronze (prova) e identificação da coleta", "Motor de detecção: lumen_eleicoes não depende de lumen_deteccao"],
  ["Cadastro de entes do IBGE (código IBGE ↔ município TSE)", "Score, severidade e indício: a aba não gera nenhum"],
  ["Vocabulário controlado e política editorial", "Telas: a aba não exibe contratações, e as telas de contratação não exibem votos"],
  ["Portal, cabeçalho e rodapé", ""],
], { size: 18 }));
body.push(spacer(100));
body.push(h3("Integração prevista (Fase 2 em diante)"));
body.push(b("**Contexto factual na família K do DOC-07:** ao exibir um indício sobre um ente, mostrar quem foi eleito " +
  "ali e em qual pleito, como dado oficial com fonte. A ligação ente ↔ município TSE já existe (`municipios.json`)."));
body.push(b("**Regra K-01** (fornecedor que consta como doador eleitoral em pleito relacionado ao ente): exige a fonte " +
  "de prestação de contas de campanha do TSE, que ainda não está integrada, um conector próprio e revisão editorial " +
  "antes de qualquer uso. Nunca é publicada isoladamente e nunca sugere nexo causal."));
body.push(spacer(80));
body.push(callout("Cuidado editorial", [
  "Coincidência entre doação de campanha e contratação é contexto, não conclusão. Qualquer tela que aproxime os " +
  "dois dados segue o DOC-08: linguagem de atividade para análise, fonte de cada fato, direito de resposta e " +
  "revisão por pessoas distintas antes da publicação.",
], "red"));

// ============================================================ 12. Próximos passos e riscos

body.push(h1("12. Próximos passos e riscos", { novaPagina: true }));
body.push(h2("12.1 Próximos passos"));
body.push(table(["Item", "Por quê", "Quando"], [3600, 4300, 1700], [
  ["Acompanhar o espaço e a saída do Supabase", "O histórico inteiro ocupa perto de 85% do 1 GB gratuito (seção 9.7); a saída tem cota mensal", "Na carga do histórico e na noite de 25/10/2026"],
  ["Feeds municipais mais enxutos", "Os nomes dos candidatos se repetem em cada arquivo de município; um cadastro por UF e cargo liberaria boa parte do espaço", "Se o espaço apertar"],
  ["Domínio próprio para o portal e os feeds", "O endereço r2.dev tem limite de requisições (seção 9.6)", "Antes da divulgação pública"],
  ["Malhas históricas para as UFs da época", "Guanabara, o Distrito Federal antigo e os territórios aparecem só como botões; a API de malhas do IBGE não tem as fronteiras antigas", "Quando houver fonte oficial"],
  ["Ensaio geral com a simulação em infraestrutura real (CDN)", "Medir a latência entre a gravação do feed e a tela", "Antes do 2º turno de 2026 e de cada pleito"],
  ["Eleições suplementares e consultas", "Aparecem no catálogo, mas não estão nos testes", "Após a carga histórica"],
  ["Capturas de tela de referência no CI", "Hoje a conferência visual é manual (seção 10.2)", "Fase 1"],
  ["Política de retenção dos ZIPs", "Ocupam espaço fora do armazenamento de objetos (ADR-021)", "Junto com a política do bronze"],
  ["Contexto eleitoral nas telas de contratação (família K)", "ADR-024", "Fase 2"],
  ["Prestação de contas de campanha (conector)", "Pré-requisito da K-01", "Fase 3 ou depois, com revisão editorial"],
], { size: 17 }));

body.push(h2("12.2 Riscos"));
body.push(table(["Risco", "Efeito", "Mitigação"], [2900, 3200, 3500], [
  ["TSE muda o formato dos arquivos antes da eleição", "Coletor deixa de ler ou lê errado", "Testes de contrato diários; leitura sempre pelo nome do campo; ensaio na semana anterior"],
  ["Limite de taxa insuficiente no pico", "Telas de município atrasadas (até ~56 min a 300 rpm)", "Brasil e UFs nunca esperam; subir rpm_resultados com indicação do TSE"],
  ["Coletor parado no meio da noite", "Tela parada como se fosse atual", "Índice volta para ao_vivo = false ao parar; reinício preserva estado"],
  ["Dado aberto com totais inconsistentes (como 1994)", "Percentuais errados", "Reconciliação pelas parcelas, com aviso visível"],
  ["Dados de 1933 a 1990 digitalizados de documentos da época, sujeitos a correção", "Somas que não fecham, nomes ausentes, partido em branco", "Leitura tolerante e explícita (seção 3.2), base que nunca passa de 100%, avisos em todo feed antigo, verificar sobre os 1.670 feeds"],
  ["Primeira carga longa (2,3 GB, horas)", "Quem roda acha que travou", "Andamento impresso por arquivo e por ano; portal no ar desde o início com --servir; retomada sem refazer nada"],
  ["Fontes do TSE recusarem conexões das máquinas do GitHub (fora do Brasil)", "Carga na nuvem não avança", "A primeira execução confirma; alternativa: preparar --nuvem ou publicar a partir de uma máquina no Brasil (seção 9.5)"],
  ["Passar de um limite gratuito (R2 ou Actions)", "Cobrança pequena ou fluxo parado até o mês seguinte", "Uso esperado abaixo dos limites (seção 9.6); só o que muda é reenviado; acompanhar o painel do R2 na noite da eleição"],
  ["Bucket do Supabase no teto de 900 MB (seção 9.7)", "A publicação para e o índice não sobe: eleições novas não aparecem no portal", "Erro no resumo da carga; feeds municipais mais enxutos ou passar para o R2"],
  ["Cota de saída do Supabase gratuito esgotada na noite da eleição (seção 9.7)", "Feeds restringidos até o mês seguinte", "Medir antes com eleicoes-medir.yml; acompanhar o uso durante a apuração; passar para o R2 trocando segredos e o endereço do portal"],
  ["Chave do R2 vazada", "Escrita indevida nos feeds publicados", "Token restrito aos dois buckets, guardado só em segredos do GitHub; revogar e trocar"],
  ["Leitura indevida do mapa como mensagem partidária", "Dano à neutralidade do projeto", "Cor por posição, nunca por partido; tabela sempre ao lado"],
  ["Aproximação indevida entre eleição e contratação", "Dano editorial e jurídico", "ADR-024; família K só como contexto; revisão editorial"],
], { size: 17 }));

// ============================================================ Apêndice

body.push(h1("Apêndice A. Glossário"));
body.push(table(["Termo", "Significado"], [2400, 7200], [
  ["Abrangência", "Recorte geográfico de um resultado: Brasil, UF ou município."],
  ["Andamento", "Arquivo -ab do TSE com as seções totalizadas de cada parte; decide o que baixar."],
  ["Bronze", "Camada imutável do Lumen que guarda cada resposta original com hash (DOC-04)."],
  ["Feed", "Arquivo JSON do contrato da seção 7, lido pelo portal."],
  ["Panorama", "Cargo visto acima do nível em que é disputado: líder de cada parte e placar por partido."],
  ["Parte", "Abrangência filha dentro de um feed (UF no Brasil, município na UF), usada pelo mapa."],
  ["Passada", "Um ciclo do coletor ao vivo: andamento, resultados, fila, feeds e estado."],
  ["Seção / zona", "Unidade de votação e agrupamento territorial do TSE; os dados abertos vêm por zona."],
  ["Totalização", "Contagem oficial dos votos das seções; o percentual de seções totalizadas mede o avanço."],
  ["UF da época", "UF como aparece numa eleição anterior a 1994, inclusive as que não existem mais; tem código próprio no feed e só declara o código IBGE quando o território é o atual."],
], { boldFirstCol: true, size: 18 }));

L.buildDoc({
  codigo: "DOC-12",
  titulo: "Aba Eleições",
  subtitulo: "Consulta de eleições municipais, estaduais e federais, ao vivo e passadas desde 1933, com dados oficiais do TSE",
  meta: { versao: "1.4", data: "14 de outubro de 2026", situacao: "Proposta — acompanha o ADR-019 a ADR-026",
    verificado: "outubro de 2026" },
  body,
  outFile: path.join(__dirname, "..", "docs", "DOC-12_Eleicoes.docx"),
});
