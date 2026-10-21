/**
 * Relatório de cobertura por ente e UF (ADR-048): o arquivo `cobertura.json`, publicado com os painéis, diz o que o
 * Lumen tem de cada ente (os anos com publicação no PNCP e os dados do SICONFI). A situação das coletas soma por
 * UF no recorte escolhido e lista os entes sem o dado.
 */

import { CODIGO_UF } from "./busca";
import type { Opcao } from "./escolha";
import { obterJson } from "./feeds";
import { BASE_PAINEL, conferir } from "./paineis";

/**
 * Um ente, na ordem de `colunas`: código, se é município com até 20 mil habitantes, os anos com publicação no
 * PNCP, os exercícios com o extrato coletado e se tem a DCA, o RGF e a RCL do exercício.
 */
export type LinhaCobertura = [string, boolean, string[], string[], boolean, boolean, boolean];

/** Arquivo `cobertura.json`; as somas por UF e do Brasil que ele traz são refeitas aqui, no recorte da tela. */
export interface Cobertura {
  versao: 1;
  tipo: "cobertura";
  gerado_em: string;
  pncp: { de: string | null; ate: string | null; anos: string[] };
  siconfi: { extrato: string[]; dca: number | null; rgf: number | null; rcl: number | null };
  limite_art_176: number;
  uniao: { pncp: string[] };
  /** O publicado no PNCP sem ente identificado; ausente nos arquivos antigos. */
  sem_ente?: SemEnte;
  colunas: string[];
  entes: LinhaCobertura[];
}

/** O publicado sem ente: totais, frações do Brasil e os órgãos sem ente no cadastro com mais processos. */
export interface SemEnte {
  processos: number;
  valor_estimado: number;
  contratos: number;
  valor_contratos: number;
  fracao_processos: number | null;
  fracao_valor: number | null;
  orgaos_sem_ente: number;
  /** `[CNPJ, razão social, esfera, processos, valor estimado]`. */
  orgaos: [string, string | null, string | null, number, number][];
}

/** Lê e confere `cobertura.json`; `null` se ainda não foi publicado. */
export async function carregarCobertura(sinal?: AbortSignal): Promise<Cobertura | null> {
  const url = `${BASE_PAINEL}/cobertura.json`;
  const bruto = await obterJson(url, { sinal });
  return bruto === null ? null : conferir<Cobertura>(bruto, "cobertura", url);
}

/** O dado medido: publicação no PNCP ou extrato coletado num ano; a DCA, o RGF ou a RCL do exercício. */
export type Dado = { fonte: "pncp" | "extrato"; ano: string } | { fonte: "dca" | "rgf" | "rcl" };

/**
 * Que entes contar: todos; estados, DF e municípios acima de 20 mil habitantes, já obrigados a divulgar no PNCP;
 * ou os municípios com até 20 mil, que têm até 1º/4/2027 (Lei 14.133, art. 176).
 */
export type Recorte = "todos" | "acima" | "ate";

/** Se o ente tem o dado. */
export function temDado(l: LinhaCobertura, d: Dado): boolean {
  switch (d.fonte) {
    case "pncp":
      return l[2].includes(d.ano);
    case "extrato":
      return l[3].includes(d.ano);
    case "dca":
      return l[4];
    case "rgf":
      return l[5];
    case "rcl":
      return l[6];
  }
}

/** Se o ente entra no recorte. */
export function noRecorte(l: LinhaCobertura, r: Recorte): boolean {
  return r === "todos" || (r === "ate") === l[1];
}

/** Uma UF (ou o Brasil): entes do recorte, quantos têm o dado e os códigos dos que não têm. */
export interface ContagemCobertura {
  uf: string;
  entes: number;
  com: number;
  sem: string[];
}

/** As UFs, na ordem das siglas, e o Brasil (sem a lista dos que não têm o dado). */
export function contarPorUf(c: Cobertura, d: Dado, r: Recorte): { brasil: ContagemCobertura; ufs: ContagemCobertura[] } {
  const brasil: ContagemCobertura = { uf: "Brasil", entes: 0, com: 0, sem: [] };
  const ufs = new Map<string, ContagemCobertura>();
  for (const l of c.entes) {
    if (!noRecorte(l, r)) continue;
    const sigla = (CODIGO_UF[l[0].slice(0, 2)] ?? "?").toUpperCase();
    let u = ufs.get(sigla);
    if (!u) ufs.set(sigla, (u = { uf: sigla, entes: 0, com: 0, sem: [] }));
    const tem = temDado(l, d);
    u.entes++;
    brasil.entes++;
    if (tem) {
      u.com++;
      brasil.com++;
    } else {
      u.sem.push(l[0]);
    }
  }
  return { brasil, ufs: [...ufs.values()].sort((a, b) => a.uf.localeCompare(b.uf)) };
}

/** Os entes do recorte com publicação no PNCP, ano a ano. */
export function pncpPorAno(c: Cobertura, r: Recorte): { ano: string; com: number; entes: number }[] {
  const doRecorte = c.entes.filter((l) => noRecorte(l, r));
  return c.pncp.anos.map((ano) => ({ ano, com: doRecorte.filter((l) => l[2].includes(ano)).length, entes: doRecorte.length }));
}

/** O dado como valor da caixa de escolha (`pncp:2025`, `dca`…) e de volta. */
export function valorDoDado(d: Dado): string {
  return "ano" in d ? `${d.fonte}:${d.ano}` : d.fonte;
}

/** O dado de um valor da caixa de escolha; `null` se não é um dos oferecidos. */
export function dadoDoValor(valor: string, c: Cobertura): Dado | null {
  const [fonte, ano = ""] = valor.split(":");
  if (fonte === "pncp" && c.pncp.anos.includes(ano)) return { fonte, ano };
  if (fonte === "extrato" && c.siconfi.extrato.includes(ano)) return { fonte, ano };
  if ((fonte === "dca" || fonte === "rgf" || fonte === "rcl") && !ano && c.siconfi[fonte] !== null) return { fonte };
  return null;
}

/** Rótulo do dado na tela. */
export function rotuloDoDado(d: Dado, c: Cobertura): string {
  switch (d.fonte) {
    case "pncp":
      return `Publicação no PNCP em ${d.ano}`;
    case "extrato":
      return `Extrato de entregas de ${d.ano} coletado`;
    case "dca":
      return `DCA de ${c.siconfi.dca} (despesa por função)`;
    case "rgf":
      return `RGF de ${c.siconfi.rgf} (despesa com pessoal)`;
    case "rcl":
      return `RCL de ${c.siconfi.rcl} (RREO)`;
  }
}

/** As opções da caixa: os anos do PNCP (o mais recente primeiro), os do extrato e os exercícios do SICONFI. */
export function opcoesDeDado(c: Cobertura): Opcao[] {
  const dados: Dado[] = [
    ...[...c.pncp.anos].reverse().map((ano) => ({ fonte: "pncp" as const, ano })),
    ...[...c.siconfi.extrato].reverse().map((ano) => ({ fonte: "extrato" as const, ano })),
    ...(["dca", "rgf", "rcl"] as const).filter((f) => c.siconfi[f] !== null).map((fonte) => ({ fonte })),
  ];
  return dados.map((d) => ({ valor: valorDoDado(d), rotulo: rotuloDoDado(d, c), grupo: d.fonte === "pncp" ? "PNCP" : "SICONFI" }));
}

/** O dado de partida: o PNCP no último ano inteiro coberto (o anterior ao do último dia), ou no único ano. */
export function dadoPadrao(c: Cobertura): Dado | null {
  const anos = c.pncp.anos;
  const ultimo = anos[anos.length - 1];
  if (ultimo === undefined) return null;
  const anterior = c.pncp.ate ? String(Number(c.pncp.ate.slice(0, 4)) - 1) : null;
  return { fonte: "pncp", ano: anterior && anos.includes(anterior) ? anterior : ultimo };
}
