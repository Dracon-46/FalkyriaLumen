const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, Table, TableRow, TableCell,
  WidthType, ShadingType, BorderStyle, AlignmentType, LevelFormat, ImageRun,
  PageBreak, TableOfContents, Header, Footer, PageNumber, VerticalAlign, LineRuleType,
} = require("docx");

// ---------- Paleta ----------
// REGRA: texto corrido e titulos sao SEMPRE pretos.
// Cor e permitida apenas como cromia de tabela (faixa de cabecalho),
// borda e preenchimento de caixa de destaque, e nos diagramas.
const BLACK = "000000";

// Cromia (fundo de faixa, bordas) - nunca aplicada a texto corrido
const NAVY = "1F3864";
const BLUE = "2E75B6";
const RED = "C00000";
const GREEN = "548235";
const AMBER = "BF8F00";

// Preenchimentos
const LIGHT = "DCE6F1";
const GREY = "F2F2F2";
const REDBG = "FDEDED";
const GREENBG = "EAF3E3";
const AMBERBG = "FFF6E0";
const MONOBG = "F5F5F5";

const CONTENT_W = 9600; // DXA util em A4 com margens de 2cm
const DIAGRAMS = path.join(__dirname, "..", "docs", "diagramas");

// ---------- Texto ----------
const bold = (t) => new TextRun({ text: t, bold: true });
const italic = (t) => new TextRun({ text: t, italics: true });
const plain = (t) => new TextRun({ text: t });
const mono = (t) => new TextRun({ text: t, font: "Consolas", size: 18 });

// Titulos ficam presos ao paragrafo seguinte (keepNext): titulo sozinho no pe
// da pagina e erro de diagramacao. novaPagina usa pageBreakBefore no proprio
// titulo em vez de um paragrafo de quebra, que vira pagina em branco quando o
// conteudo anterior termina exatamente no fim de uma pagina.
function h1(text, opts = {}) {
  return new Paragraph({
    text, heading: HeadingLevel.HEADING_1,
    spacing: { before: 380, after: 160 },
    keepNext: true, keepLines: true, pageBreakBefore: !!opts.novaPagina,
  });
}
function h2(text) {
  return new Paragraph({
    text, heading: HeadingLevel.HEADING_2,
    spacing: { before: 280, after: 120 },
    keepNext: true, keepLines: true,
  });
}
function h3(text) {
  return new Paragraph({
    text, heading: HeadingLevel.HEADING_3,
    spacing: { before: 220, after: 100 },
    keepNext: true, keepLines: true,
  });
}
function p(text, opts = {}) {
  return new Paragraph({
    children: [new TextRun({ text, italics: !!opts.italics, bold: !!opts.bold,
      color: opts.color, size: opts.size })],
    spacing: { after: opts.after === undefined ? 120 : opts.after },
    alignment: opts.align,
  });
}
function pRuns(runs, opts = {}) {
  return new Paragraph({
    children: runs,
    spacing: { after: opts.after === undefined ? 120 : opts.after },
    alignment: opts.align,
  });
}
function bullet(text, level = 0) {
  return new Paragraph({
    children: [plain(text)],
    numbering: { reference: "bullets", level },
    spacing: { after: 70 },
  });
}
function bulletRuns(runs, level = 0) {
  return new Paragraph({
    children: runs,
    numbering: { reference: "bullets", level },
    spacing: { after: 70 },
  });
}
// instance: listas numeradas com instancias diferentes recomecam do 1; sem
// ela, todas as listas do documento continuam a mesma contagem.
function numbered(text, level = 0, instance) {
  return new Paragraph({
    children: [plain(text)],
    numbering: { reference: "steps", level, instance },
    spacing: { after: 70 },
  });
}
function numberedRuns(runs, level = 0, instance) {
  return new Paragraph({
    children: runs,
    numbering: { reference: "steps", level, instance },
    spacing: { after: 70 },
  });
}
function pageBreak() {
  return new Paragraph({ children: [new PageBreak()] });
}
function spacer(h = 120) {
  return new Paragraph({ text: "", spacing: { after: h } });
}

// ---------- Bloco de codigo ----------
function code(lines, opts = {}) {
  const rows = lines.map((ln) => new TableRow({
    children: [new TableCell({
      width: { size: CONTENT_W, type: WidthType.DXA },
      shading: { type: ShadingType.CLEAR, fill: opts.fill || MONOBG },
      margins: { top: 20, bottom: 20, left: 120, right: 100 },
      borders: noBorders(),
      children: [new Paragraph({ children: [mono(ln === "" ? " " : ln)], spacing: { after: 0 } })],
    })],
  }));
  return new Table({
    width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: [CONTENT_W],
    borders: {
      top: { style: BorderStyle.SINGLE, size: 4, color: "D0D0D0" },
      bottom: { style: BorderStyle.SINGLE, size: 4, color: "D0D0D0" },
      left: { style: BorderStyle.SINGLE, size: 12, color: BLUE },
      right: { style: BorderStyle.SINGLE, size: 4, color: "D0D0D0" },
      insideHorizontal: { style: BorderStyle.NONE, size: 0, color: "FFFFFF" },
      insideVertical: { style: BorderStyle.NONE, size: 0, color: "FFFFFF" },
    },
    rows,
  });
}
function noBorders() {
  const n = { style: BorderStyle.NONE, size: 0, color: "FFFFFF" };
  return { top: n, bottom: n, left: n, right: n };
}

// ---------- Callout ----------
function callout(title, lines, tone = "red") {
  // Borda e fundo carregam a cor; o titulo da caixa e texto, entao fica preto.
  const map = {
    red: { border: RED, fill: REDBG, tcolor: BLACK },
    green: { border: GREEN, fill: GREENBG, tcolor: BLACK },
    amber: { border: AMBER, fill: AMBERBG, tcolor: BLACK },
    blue: { border: BLUE, fill: LIGHT, tcolor: BLACK },
  };
  const c = map[tone] || map.red;
  const kids = [new Paragraph({
    children: [new TextRun({ text: title, bold: true, color: c.tcolor })],
    spacing: { after: 90 },
  })];
  lines.forEach((ln) => kids.push(new Paragraph({
    children: [plain(ln)], spacing: { after: 70 },
  })));
  return new Table({
    width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: [CONTENT_W],
    borders: {
      top: { style: BorderStyle.SINGLE, size: 6, color: c.border },
      bottom: { style: BorderStyle.SINGLE, size: 6, color: c.border },
      left: { style: BorderStyle.SINGLE, size: 18, color: c.border },
      right: { style: BorderStyle.SINGLE, size: 6, color: c.border },
      insideHorizontal: { style: BorderStyle.NONE, size: 0, color: "FFFFFF" },
      insideVertical: { style: BorderStyle.NONE, size: 0, color: "FFFFFF" },
    },
    // cantSplit: a caixa inteira fica numa página; partida, o título fica
    // sozinho no pé de uma página e o texto vai para a seguinte.
    rows: [new TableRow({
      cantSplit: true,
      children: [new TableCell({
        width: { size: CONTENT_W, type: WidthType.DXA },
        shading: { type: ShadingType.CLEAR, fill: c.fill },
        margins: { top: 130, bottom: 130, left: 170, right: 150 },
        children: kids,
      })],
    })],
  });
}

// ---------- Tabelas ----------
function headerCell(text, width) {
  return new TableCell({
    width: { size: width, type: WidthType.DXA },
    shading: { type: ShadingType.CLEAR, fill: NAVY },
    margins: { top: 80, bottom: 80, left: 110, right: 110 },
    verticalAlign: VerticalAlign.CENTER,
    children: [new Paragraph({
      // Faixa de cabecalho da tabela: cromia do componente, nao texto corrido
      children: [new TextRun({ text, bold: true, color: "FFFFFF", size: 19 })],
      spacing: { after: 0 },
    })],
  });
}
function bodyCell(text, width, opts = {}) {
  const runs = Array.isArray(text)
    ? text
    : [new TextRun({ text: String(text), bold: !!opts.bold, size: opts.size || 19,
        color: opts.color, font: opts.monoFont ? "Consolas" : undefined })];
  return new TableCell({
    width: { size: width, type: WidthType.DXA },
    shading: { type: ShadingType.CLEAR, fill: opts.fill || "FFFFFF" },
    margins: { top: 70, bottom: 70, left: 110, right: 110 },
    verticalAlign: VerticalAlign.CENTER,
    children: [new Paragraph({ children: runs, spacing: { after: 0 } })],
  });
}
function table(headers, widths, rows, opts = {}) {
  const total = widths.reduce((a, b) => a + b, 0);
  const trs = [];
  if (headers && headers.length) {
    trs.push(new TableRow({
      tableHeader: true,
      children: headers.map((hh, i) => headerCell(hh, widths[i])),
    }));
  }
  rows.forEach((r, ri) => {
    const fill = opts.zebra === false ? "FFFFFF" : (ri % 2 === 1 ? GREY : "FFFFFF");
    trs.push(new TableRow({
      cantSplit: true, // linha de tabela não se divide entre páginas
      children: r.map((cell, i) => bodyCell(cell, widths[i], {
        fill, bold: opts.boldFirstCol && i === 0, size: opts.size,
        monoFont: opts.monoCols && opts.monoCols.includes(i),
      })),
    }));
  });
  return new Table({
    width: { size: total, type: WidthType.DXA },
    columnWidths: widths,
    borders: {
      top: { style: BorderStyle.SINGLE, size: 4, color: "BFBFBF" },
      bottom: { style: BorderStyle.SINGLE, size: 4, color: "BFBFBF" },
      left: { style: BorderStyle.SINGLE, size: 4, color: "BFBFBF" },
      right: { style: BorderStyle.SINGLE, size: 4, color: "BFBFBF" },
      insideHorizontal: { style: BorderStyle.SINGLE, size: 2, color: "D9D9D9" },
      insideVertical: { style: BorderStyle.SINGLE, size: 2, color: "D9D9D9" },
    },
    rows: trs,
  });
}

// ---------- Imagens ----------
function pngSize(file) {
  const b = fs.readFileSync(file);
  return { w: b.readUInt32BE(16), h: b.readUInt32BE(20) };
}
// maxH evita que diagramas altos estourem a altura util da pagina A4 (~880px)
function figure(fileName, caption, maxW = 620, maxH = 860) {
  const full = path.join(DIAGRAMS, fileName);
  const { w, h } = pngSize(full);
  const scale = Math.min(1, maxW / w, maxH / h);
  const out = [
    new Paragraph({
      children: [new ImageRun({
        type: "png",
        data: fs.readFileSync(full),
        transformation: { width: Math.round(w * scale), height: Math.round(h * scale) },
      })],
      alignment: AlignmentType.CENTER,
      // lineRule AUTO e obrigatorio: sem ele a imagem herda line:276 do estilo
      // padrao e o renderizador corta a figura numa tira de ~20px de altura.
      spacing: { before: 140, after: 70, line: 240, lineRule: LineRuleType.AUTO },
    }),
  ];
  if (caption) {
    out.push(new Paragraph({
      children: [new TextRun({ text: caption, italics: true, size: 17, color: BLACK })],
      alignment: AlignmentType.CENTER,
      spacing: { after: 200 },
    }));
  }
  return out;
}

// ---------- Capa ----------
function cover(codigo, titulo, subtitulo, meta = {}) {
  return [
    new Paragraph({
      children: [new TextRun({ text: "PROJETO LUMEN", bold: true, size: 26, color: BLACK,
        characterSpacing: 60 })],
      spacing: { before: 900, after: 60 },
    }),
    new Paragraph({
      children: [new TextRun({ text: "Monitoramento de contratações e despesas públicas do Brasil",
        size: 20, color: BLACK })],
      spacing: { after: 400 },
    }),
    new Paragraph({
      children: [new TextRun({ text: codigo, bold: true, size: 22, color: BLACK })],
      spacing: { after: 80 },
    }),
    new Paragraph({
      children: [new TextRun({ text: titulo, bold: true, size: 48, color: BLACK })],
      spacing: { after: 140 },
    }),
    new Paragraph({
      children: [new TextRun({ text: subtitulo, size: 24, color: BLACK, italics: true })],
      spacing: { after: 700 },
      border: { bottom: { style: BorderStyle.SINGLE, size: 8, color: BLACK, space: 14 } },
    }),
    table(null, [2400, 7200], [
      ["Projeto", "Lumen (nome de trabalho, sujeito a verificação de disponibilidade)"],
      ["Responsável", "Gaspare"],
      ["Versão", meta.versao || "1.0"],
      ["Data", meta.data || "18 de setembro de 2026"],
      ["Situação", meta.situacao || "Documento base para início de desenvolvimento"],
    ], { boldFirstCol: true, zebra: true }),
    spacer(300),
    p("Este documento integra o pacote de documentação do Projeto Lumen. Valores legais, " +
      "limites e endpoints citados foram verificados em fontes oficiais em " + (meta.verificado || "setembro de 2026") + " e " +
      "devem ser reconferidos antes da implementação, pois são atualizados periodicamente por decreto.",
      { italics: true, size: 18, color: BLACK }),
  ];
}

// ---------- Documento ----------
function buildDoc({ codigo, titulo, subtitulo, body, outFile, toc = true, meta = {} }) {
  const children = [...cover(codigo, titulo, subtitulo, meta), pageBreak()];
  if (toc) {
    children.push(h1("Sumário"));
    // O campo TOC do Word so e preenchido quando os campos sao atualizados.
    children.push(p("Para preencher o sumário, selecione todo o documento (Ctrl+A) e atualize os " +
      "campos (F9). No Word, também é possível clicar com o botão direito sobre o sumário e escolher " +
      "Atualizar campo.", { italics: true, size: 18, color: BLACK }));
    children.push(new TableOfContents("Sumário", {
      hyperlink: true, headingStyleRange: "1-3",
    }));
    children.push(pageBreak());
  }
  children.push(...body);

  const doc = new Document({
    creator: "Projeto Lumen",
    title: `${codigo} - ${titulo}`,
    description: subtitulo,
    styles: {
      default: {
        document: { run: { font: "Calibri", size: 21 }, paragraph: { spacing: { line: 276 } } },
        heading1: {
          run: { font: "Calibri Light", size: 34, bold: true, color: BLACK },
          paragraph: { spacing: { before: 380, after: 160 } },
        },
        heading2: {
          run: { font: "Calibri Light", size: 27, bold: true, color: BLACK },
          paragraph: { spacing: { before: 280, after: 120 } },
        },
        heading3: {
          run: { font: "Calibri", size: 23, bold: true, color: BLACK },
          paragraph: { spacing: { before: 220, after: 100 } },
        },
      },
    },
    numbering: {
      config: [
        {
          reference: "bullets",
          levels: [
            { level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
              style: { paragraph: { indent: { left: 420, hanging: 250 } } } },
            { level: 1, format: LevelFormat.BULLET, text: "◦", alignment: AlignmentType.LEFT,
              style: { paragraph: { indent: { left: 840, hanging: 250 } } } },
            { level: 2, format: LevelFormat.BULLET, text: "▪", alignment: AlignmentType.LEFT,
              style: { paragraph: { indent: { left: 1260, hanging: 250 } } } },
          ],
        },
        {
          reference: "steps",
          levels: [
            { level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
              style: { paragraph: { indent: { left: 440, hanging: 280 } } } },
            { level: 1, format: LevelFormat.LOWER_LETTER, text: "%2)", alignment: AlignmentType.LEFT,
              style: { paragraph: { indent: { left: 880, hanging: 280 } } } },
          ],
        },
      ],
    },
    sections: [{
      properties: { page: { margin: { top: 1140, bottom: 1140, left: 1134, right: 1134 } } },
      headers: {
        default: new Header({
          children: [new Paragraph({
            children: [new TextRun({ text: `Projeto Lumen  |  ${codigo} ${titulo}`, size: 16, color: BLACK })],
            border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: "D9D9D9", space: 6 } },
          })],
        }),
      },
      footers: {
        default: new Footer({
          children: [new Paragraph({
            alignment: AlignmentType.RIGHT,
            children: [new TextRun({ text: "Pagina ", size: 16, color: BLACK }),
              new TextRun({ children: [PageNumber.CURRENT], size: 16, color: BLACK }),
              new TextRun({ text: " de ", size: 16, color: BLACK }),
              new TextRun({ children: [PageNumber.TOTAL_PAGES], size: 16, color: BLACK })],
          })],
        }),
      },
      children,
    }],
  });

  return Packer.toBuffer(doc).then((buf) => {
    fs.mkdirSync(path.dirname(outFile), { recursive: true });
    fs.writeFileSync(outFile, buf);
    console.log("gerado:", outFile, (buf.length / 1024).toFixed(0) + "KB");
  });
}

module.exports = {
  h1, h2, h3, p, pRuns, bullet, bulletRuns, numbered, numberedRuns,
  bold, italic, plain, mono, table, callout, code, figure, pageBreak, spacer,
  buildDoc, CONTENT_W, NAVY, BLUE, RED, GREEN, AMBER, LIGHT, GREY,
};
