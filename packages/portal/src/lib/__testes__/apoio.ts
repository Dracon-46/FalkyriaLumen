import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, resolve } from "node:path";

/** Raiz do repositório (packages/portal/src/lib/__testes__ → ../../../../..). */
export const RAIZ = resolve(__dirname, "../../../../..");
export const AMOSTRA = join(RAIZ, "testes/fixtures/eleicoes_feed");
export const FIX_IBGE = join(RAIZ, "testes/fixtures/ibge");

export function lerJson(caminho: string): unknown {
  return JSON.parse(readFileSync(caminho, "utf-8"));
}

export function arquivosJson(raiz: string): string[] {
  const saida: string[] = [];
  const andar = (dir: string) => {
    for (const nome of readdirSync(dir)) {
      const p = join(dir, nome);
      if (statSync(p).isDirectory()) andar(p);
      else if (nome.endsWith(".json")) saida.push(relative(raiz, p));
    }
  };
  andar(raiz);
  return saida.sort();
}
