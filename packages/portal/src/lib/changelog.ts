/**
 * O `CHANGELOG.md` do repositório, lido na geração do site estático. Só para componente de servidor (usa `fs`):
 * o layout passa à aba os identificadores das mudanças, e a página de novidades mostra tudo.
 */

import { readFileSync } from "node:fs";
import path from "node:path";
import { lerChangelog, type VersaoNovidades } from "./novidades";

let lidas: VersaoNovidades[] | null = null;

/** As versões do CHANGELOG (o portal fica em `packages/portal`, dois níveis abaixo da raiz); vazio se não achar. */
export function novidadesDoRepositorio(): VersaoNovidades[] {
  if (lidas) return lidas;
  for (const caminho of [path.join(process.cwd(), "..", "..", "CHANGELOG.md"), path.join(process.cwd(), "CHANGELOG.md")]) {
    try {
      lidas = lerChangelog(readFileSync(caminho, "utf8"));
      return lidas;
    } catch {
      // tenta o próximo lugar
    }
  }
  lidas = [];
  return lidas;
}
