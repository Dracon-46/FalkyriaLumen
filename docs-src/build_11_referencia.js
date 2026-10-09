// DOC-11 Referencia Tecnica — gerada a partir do codigo (ADR-023).
//
// Entrada: referencia.json, produzido por
//   python ferramentas/referencia/referencia.py --json docs-src/referencia.json
// O texto de cada item e a docstring (Python) ou o bloco JSDoc (TypeScript)
// que esta ao lado dele no codigo. Este script so organiza e formata.

const fs = require("fs");
const path = require("path");
const { TextRun } = require("docx");
const L = require("./lib");
const { h1, h2, h3, p, pRuns, bullet, bulletRuns, table, callout, code, pageBreak, spacer, bold, mono } = L;

const ENTRADA = path.join(__dirname, "referencia.json");
if (!fs.existsSync(ENTRADA)) {
  console.error("referencia.json ausente: rode `npm run referencia` (ou `make docs` na raiz do repositório)");
  process.exit(1);
}
const dados = JSON.parse(fs.readFileSync(ENTRADA, "utf-8"));

// ---------------------------------------------------------------- texto das docstrings

// Trechos `assim` e ``assim`` viram fonte monoespaçada; **assim** vira negrito.
function runs(texto) {
  const saida = [];
  const re = /``([^`]+)``|`([^`]+)`|\*\*([^*]+)\*\*/g;
  let ultimo = 0;
  let m;
  while ((m = re.exec(texto)) !== null) {
    if (m.index > ultimo) saida.push(new TextRun({ text: texto.slice(ultimo, m.index) }));
    if (m[1] || m[2]) saida.push(new TextRun({ text: m[1] || m[2], font: "Consolas", size: 19 }));
    else saida.push(new TextRun({ text: m[3], bold: true }));
    ultimo = re.lastIndex;
  }
  if (ultimo < texto.length) saida.push(new TextRun({ text: texto.slice(ultimo) }));
  return saida.length ? saida : [new TextRun({ text: "" })];
}

const indentacao = (ln) => ln.length - ln.trimStart().length;

// Docstring (reST simples) → parágrafos: parágrafos, listas com "-", blocos
// de código após "::" ou indentados, e títulos sublinhados com "---".
function renderizar(texto) {
  const out = [];
  if (!texto || !texto.trim()) return out;
  const linhas = texto.replace(/\r/g, "").split("\n");
  let i = 0;
  let proximoECodigo = false;
  while (i < linhas.length) {
    if (!linhas[i].trim()) { i++; continue; }
    // bloco: até a próxima linha em branco
    const bloco = [];
    while (i < linhas.length && linhas[i].trim()) { bloco.push(linhas[i]); i++; }
    const base = Math.min(...bloco.map(indentacao));
    if (proximoECodigo || (base >= 4 && out.length)) {
      out.push(code(bloco.map((l) => l.slice(base))));
      out.push(spacer(60));
      proximoECodigo = false;
      continue;
    }
    // título sublinhado
    if (bloco.length >= 2 && /^[-=~]{3,}\s*$/.test(bloco[1].trim())) {
      out.push(pRuns([new TextRun({ text: bloco[0].trim(), bold: true })], { after: 60 }));
      bloco.splice(0, 2);
      if (!bloco.length) continue;
    }
    if (/^\s*[-*]\s/.test(bloco[0])) {
      // lista: cada item começa com "- "; linhas seguintes indentadas continuam o item
      let atual = null;
      const itens = [];
      for (const l of bloco) {
        if (/^\s*[-*]\s/.test(l)) { atual = l.replace(/^\s*[-*]\s/, ""); itens.push(atual); }
        else if (itens.length) itens[itens.length - 1] += " " + l.trim();
      }
      itens.forEach((it) => out.push(bulletRuns(runs(it))));
      continue;
    }
    // definição em linhas alinhadas ("``termo`` texto" ou "termo   texto",
    // com o texto começando na mesma coluna em todas as linhas — é isso que
    // separa uma tabela alinhada de prosa que por acaso começa com código —
    // e com preenchimento de espaços em pelo menos uma linha):
    // cada linha vira um item, com o termo em monoespaçado
    const definicao = /^\s*(?:``([^`]+)``\s+|(\S+)\s{2,})(\S.*)$/;
    const colunaDoTexto = (l) => { const m = l.match(definicao); return m ? l.length - m[3].length : -1; };
    if (bloco.length >= 2 && bloco.every((l) => definicao.test(l))
        && new Set(bloco.map(colunaDoTexto)).size === 1
        && bloco.some((l) => /\S\s{2,}\S/.test(l.trim()))) {
      bloco.forEach((l) => {
        const [, crase, simples, texto] = l.match(definicao);
        out.push(bulletRuns([new TextRun({ text: crase || simples, font: "Consolas", size: 19 }),
          new TextRun({ text: "  " }), ...runs(texto)]));
      });
      continue;
    }
    let corrido = bloco.map((l) => l.trim()).join(" ");
    if (corrido.endsWith("::")) {
      corrido = corrido.slice(0, -1);
      proximoECodigo = true;
    }
    out.push(pRuns(runs(corrido), { after: 80 }));
  }
  return out;
}

// ---------------------------------------------------------------- organização

const PACOTES = {
  "packages/ingestao": ["Ingestão", "Porta FonteDados, camada bronze (disco e armazenamento de objetos), cliente HTTP com política de coleta responsável e os adaptadores do PNCP, do IBGE e do SICONFI."],
  "packages/canonico": ["Esquema canônico", "Entidades de fato e de análise, identidade determinística, documentos (CNPJ e CPF), UFs, porte dos entes, rótulos públicos e a máquina de estados do indício."],
  "packages/normalizacao": ["Normalização", "Transformação do bronze em registros canônicos (silver), com regras de qualidade, quarentena e consolidação."],
  "packages/deteccao": ["Detecção", "Parâmetros legais datados e verificados; as regras do motor entram na Fase 2."],
  "packages/conformidade": ["Conformidade", "Avaliação das entregas obrigatórias ao SICONFI no prazo da LRF."],
  "packages/orquestracao": ["Orquestração", "Pipeline local e o comando `lumen`."],
  "packages/mercado": ["Referência de mercado (Python)", "Regra A-05 em modo silencioso: reconhecimento de itens comparáveis (combustível, gás de cozinha, informática), preço de revenda da ANP pela série semestral e pelas planilhas semanais (com leitor de .xlsx sem dependências), ofertas do varejo pela API oficial, comparação com a mediana por lugar e época, relatório interno e distribuição da razão para calibrar (ADR-027)."],
  "packages/eleicoes": ["Aba Eleições (Python)", "Coleta do TSE ao vivo e dos dados abertos (1933 a 2024), agregação, feeds JSON do portal, carga num comando (preparar), publicação e retomada na nuvem (R2), referências embutidas (mapa e cadastro), simulação e servidor local."],
  "packages/portal": ["Portal (TypeScript)", "Site estático em Next.js: aba Eleições, com mapa interativo, candidatos, panorama, evolução, busca e modo TV."],
  "ferramentas/lint-vocabulario": ["Vocabulário controlado", "Verificador que impede termos que imputam conduta nos textos públicos (ADR-007)."],
  "ferramentas/referencia": ["Referência técnica", "Extração deste documento a partir do código e cobrança de documentação (ADR-023)."],
};

function pacoteDe(caminho) {
  const partes = caminho.split("/");
  return `${partes[0]}/${partes[1]}`;
}

const ROTULO = {
  modulo: "módulo", classe: "classe", funcao: "função", metodo: "método", interface: "interface",
  tipo: "tipo", constante: "constante", componente: "componente",
};

const grupos = {};
for (const a of dados.arquivos) (grupos[pacoteDe(a.caminho)] ||= []).push(a);

// ---------------------------------------------------------------- documento

const body = [];
const totalItens = dados.arquivos.reduce((s, a) => s + a.itens.length, 0);
const totalLinhas = dados.arquivos.reduce((s, a) => s + a.linhas, 0);

body.push(h1("1. Como ler este documento"));
body.push(p("Esta referência descreve o código do Lumen arquivo por arquivo e, dentro de cada arquivo, cada " +
  "classe, função, método, componente, interface e tipo: o que faz, como faz quando o mecanismo não é óbvio, e " +
  "por que a escolha foi essa quando há uma razão de projeto, legal ou de segurança."));
body.push(p("O texto não foi escrito para este documento: é o que está ao lado de cada declaração no próprio " +
  "código (docstring em Python, comentário JSDoc em TypeScript). Este documento é gerado a partir dele, então " +
  "muda no mesmo commit que muda o código. O teste test_todo_o_codigo_esta_documentado recusa qualquer função " +
  "nova sem texto (ADR-023)."));
body.push(callout("Para regenerar", [
  "python ferramentas/referencia/referencia.py --json docs-src/referencia.json",
  "cd docs-src && node build_11_referencia.js",
], "blue"));
body.push(p("Convenções: nomes de código aparecem em fonte monoespaçada; a linha cinza abaixo do nome de cada " +
  "item é a assinatura como está no código. Funções auxiliares definidas dentro de outra função são parte da " +
  "que as contém e são descritas no texto dela."));

body.push(h1("2. Visão geral"));
body.push(p(`${dados.arquivos.length} arquivos de código, ${totalLinhas.toLocaleString("pt-BR")} linhas e ` +
  `${totalItens} declarações documentadas, em ${Object.keys(grupos).length} pacotes. Mais ` +
  `${dados.testes.length} arquivos de teste com ${dados.testes.reduce((s, t) => s + t.testes, 0)} testes ` +
  "declarados (apêndice A)."));
body.push(table(["Pacote", "Papel", "Arquivos", "Itens"], [2500, 5100, 1000, 1000],
  Object.keys(PACOTES).filter((k) => grupos[k]).map((k) => [
    k, PACOTES[k][1], String(grupos[k].length), String(grupos[k].reduce((s, a) => s + a.itens.length, 0)),
  ])));

let capitulo = 3;
for (const chave of Object.keys(PACOTES)) {
  const arquivos = grupos[chave];
  if (!arquivos) continue;
  body.push(pageBreak());
  body.push(h1(`${capitulo}. ${PACOTES[chave][0]} — ${chave}`));
  body.push(p(PACOTES[chave][1]));
  body.push(table(["Arquivo", "Linhas", "Itens"], [7200, 1200, 1200],
    arquivos.map((a) => [a.caminho.slice(chave.length + 1), String(a.linhas), String(a.itens.length)]),
    { monoCols: [0], size: 17 }));
  let secao = 1;
  for (const a of arquivos) {
    body.push(h2(`${capitulo}.${secao} ${a.caminho.slice(chave.length + 1)}`));
    body.push(pRuns([new TextRun({ text: `${a.caminho} · ${a.linguagem === "python" ? "Python" : "TypeScript"} · ` +
      `${a.linhas} linhas · ${a.itens.length} declarações`, size: 17 })], { after: 100 }));
    body.push(...renderizar(a.doc));
    for (const it of a.itens) {
      body.push(pRuns([bold(`${ROTULO[it.tipo] || it.tipo} `), new TextRun({ text: it.nome, font: "Consolas", size: 20, bold: true }),
        new TextRun({ text: `  (linha ${it.linha})`, size: 16 })], { after: 40 }));
      body.push(code([it.assinatura.length > 130 ? it.assinatura.slice(0, 127) + "..." : it.assinatura]));
      body.push(spacer(40));
      body.push(...renderizar(it.doc));
      body.push(spacer(80));
    }
    secao++;
  }
  capitulo++;
}

// ---------------------------------------------------------------- apêndices

body.push(pageBreak());
body.push(h1("Apêndice A. Testes"));
body.push(p("Cada arquivo de teste começa dizendo o que garante. A contagem é a de funções de teste declaradas " +
  "(testes parametrizados contam uma vez; a suíte executa mais casos que isso)."));
body.push(table(["Arquivo", "Testes", "O que garante"], [3800, 800, 5000],
  dados.testes.map((t) => [t.caminho, String(t.testes), (t.doc || "").split("\n\n")[0].replace(/\n/g, " ")]),
  { monoCols: [0], size: 16 }));

body.push(h1("Apêndice B. Configuração, dados e infraestrutura"));
body.push(table(["Arquivo", "Papel"], [3600, 6000], [
  ["pyproject.toml", "Pacote instalável (pip install -e .), comando lumen, dependências opcionais (dev, analitico), ruff e pytest (caminhos, marcadores postgres e contrato)."],
  ["Makefile", "Atalhos: instalar, testes, cobertura (80% mínimo), vocabulario, estilo, verificar, docs, ambiente, banco, contrato, portal."],
  ["lumen.toml.exemplo", "Modelo da configuração local: contato da coleta (User-Agent), raiz dos dados, limites por fonte, seções [eleicoes] e [publicacao] (endpoint e buckets do R2; as chaves só em variável de ambiente)."],
  ["infra/docker-compose.yml", "Ambiente local: PostgreSQL 16 e MinIO com Object Lock. Credenciais só de desenvolvimento."],
  [".github/workflows/ci.yml", "CI: vocabulário, testes com cobertura em Python 3.11 a 3.13, ruff, migração no PostgreSQL, portal (tipos, testes, build)."],
  [".github/workflows/contrato.yml", "Testes de contrato diários contra as fontes reais (não bloqueiam; alarmam)."],
  [".github/workflows/eleicoes-carga.yml", "Carga das eleições no GitHub Actions, diária e manual: preparar --nuvem --sem-portal --sem-bronze --apagar-zips --limite-minutos 280; retomada pelo estado no R2 (ADR-026)."],
  [".github/workflows/eleicoes-ao-vivo.yml", "Noite da eleição, disparo manual com o id: ao-vivo --nuvem, publicando a cada passada."],
  [".github/workflows/mercado-referencia.yml", "Regra A-05 com dados reais, disparo manual: contratações do PNCP na janela, itens das compras do objeto, série semestral e/ou planilhas semanais da ANP, amostras do formato no registro e relatório silencioso como artefato do fluxo."],
  [".github/workflows/portal-pages.yml", "Gera o portal com NEXT_PUBLIC_DADOS_ELEICOES apontando para o R2 e o publica no Cloudflare Pages, criando o projeto na primeira vez."],
  ["packages/canonico/migrations/0001_dominio.sql", "Esquema lumen no PostgreSQL: tabelas de prova somente-anexação, máquina de estados do indício por gatilho, aprovação por revisores distintos, papel lumen_app sem UPDATE/DELETE na prova."],
  ["packages/mercado/lumen_mercado/parametros_mercado.toml", "Limiares, janelas e amostras mínimas da regra A-05 (não calibrados) e as consultas padrão do varejo."],
  ["packages/canonico/migrations/0002_search_path.sql", "Caminho de busca vazio nas três funções de gatilho da 0001: o search_path de quem dispara o gatilho não muda o que a função enxerga (linter de segurança do Supabase)."],
  ["packages/deteccao/lumen_deteccao/parametros_legais.toml", "Parâmetros legais com vigência, fonte e data de verificação (limites de dispensa, acréscimos, prazos da LRF)."],
  ["packages/normalizacao/sql/silver_consolidada.sql", "Consolidação da silver no DuckDB: uma linha por id, a mais recente."],
  ["ferramentas/lint-vocabulario/vocabulario.json", "Lista normativa de termos proibidos, expressões técnicas permitidas, alvos e isenções."],
  ["packages/portal/package.json, package-lock.json", "Dependências do portal com versões fixas; scripts dev, build, tipos, testes, verificar, dados:amostra."],
  ["packages/portal/next.config.mjs", "Exportação estática (output: export), barra final nas rotas, imagens sem otimizador."],
  ["packages/portal/tsconfig.json, vitest.config.mts", "TypeScript estrito (noUncheckedIndexedAccess) e testes de unidade em Node."],
  ["packages/portal/src/app/globals.css", "Estilo do portal: variáveis de cor clara e escura, paleta das séries, layout responsivo, modo TV."],
  ["testes/fixtures/", "Respostas reais das fontes (PNCP, SICONFI, IBGE, TSE), com README de cada captura."],
  ["testes/fixtures/eleicoes_feed/", "Amostra de feeds gerada por lumen eleicoes amostra --sem-referencias; conferida byte a byte pelo Python e lida pelos testes do portal."],
  ["testes/fixtures/tse/dados_abertos_uf/", "Linhas reais, sem alteração, dos arquivos por UF de 1933 a 1990 (seis anos), com o motivo de cada recorte no README da pasta tse."],
  ["packages/eleicoes/lumen_eleicoes/dados/", "Malhas do IBGE (28 arquivos TopoJSON) e cadastro de municípios que vêm com o pacote; proveniência no LEIAME.md da pasta."],
  ["preparar.cmd", "Windows: confere o lumen.toml, cria o ambiente Python em .venv, instala o Lumen e roda lumen eleicoes preparar --servir."],
  ["lumen.toml (não versionado)", "Configuração local real, criada a partir do lumen.toml.exemplo; contém o contato da coleta."],
  ["docs-src/", "Fonte dos documentos .docx (este inclusive) e dos diagramas."],
], { monoCols: [0], size: 17 }));

L.buildDoc({
  codigo: "DOC-11",
  titulo: "Referência Técnica",
  subtitulo: "Arquivo por arquivo, função por função: o que faz, como faz e por quê",
  meta: { versao: "1.3", data: "9 de outubro de 2026", situacao: "Gerado a partir do código (ADR-023)",
    verificado: "outubro de 2026" },
  body,
  outFile: path.join(__dirname, "..", "docs", "DOC-11_Referencia_Tecnica.docx"),
});
