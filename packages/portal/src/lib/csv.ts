/**
 * As tabelas do portal em CSV (ADR-051): o que a tabela mostra, com todas as linhas (não só a página da tela) e os
 * valores inteiros (não os compactos, como "1,2 mi"). Separador ";" e vírgula decimal, que as planilhas em português
 * abrem sem configurar; UTF-8 com BOM, para os acentos. O arquivo é montado no navegador, na hora do clique, a
 * partir dos mesmos dados da tela: não há outro arquivo publicado nem outro recorte.
 */

/** Uma célula: texto, número ou vazio. */
export type Celula = string | number | null | undefined;

/** Começos que uma planilha lê como fórmula: o texto da fonte não pode virar fórmula ao abrir. */
const FORMULA = /^[=+\-@\t\r]/;

/** Número com vírgula decimal, sem separador de milhar e com no máximo duas casas; texto entre aspas quando precisa. */
export function celulaCsv(c: Celula): string {
  if (c === null || c === undefined) return "";
  if (typeof c === "number") {
    if (!Number.isFinite(c)) return "";
    return String(Number.isInteger(c) ? c : Math.round(c * 100) / 100).replace(".", ",");
  }
  const texto = FORMULA.test(c) ? `'${c}` : c;
  return /[;"\r\n]/.test(texto) || texto !== texto.trim() ? `"${texto.replace(/"/g, '""')}"` : texto;
}

/** O CSV inteiro: a linha das colunas e as linhas, com quebra `\r\n`. */
export function paraCsv(colunas: string[], linhas: Celula[][]): string {
  return [colunas, ...linhas].map((l) => l.map(celulaCsv).join(";")).join("\r\n") + "\r\n";
}

/** "lumen-contratacoes-4314902-fornecedores.csv": minúsculas, sem acento, partes vazias de fora. */
export function nomeDoArquivo(...partes: (string | null | undefined)[]): string {
  const limpo = partes
    .filter((p): p is string => !!p)
    .map((p) => p.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, "-"))
    .map((p) => p.replace(/^-+|-+$/g, ""))
    .filter(Boolean);
  return `${["lumen", ...limpo].join("-")}.csv`;
}

/** Entrega o arquivo ao navegador para salvar. */
export function baixarCsv(nome: string, colunas: string[], linhas: Celula[][]): void {
  const blob = new Blob([`﻿${paraCsv(colunas, linhas)}`], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = nome;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
