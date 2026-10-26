/**
 * Modos de cor do mapa da aba Eleições: quem lidera (a cor cheia), a força
 * da vitória (a cor de quem lidera, mais forte quanto maior o percentual), o
 * que mudou do 1º para o 2º turno e a abstenção.
 *
 * A identidade continua sendo a cor de quem lidera (ADR-020, ADR-052); a
 * força só mistura essa cor com a da superfície, em faixas fixas, para a
 * leitura não depender de distinguir tons parecidos de cores diferentes.
 */

import { varCor, varCorMapa } from "./cores";
import type { Feed, Parte } from "./tipos";

/** O que a cor de cada área mostra. */
export type ModoCor = "vencedor" | "intensidade" | "mudanca" | "abstencao";

/** Os modos, na ordem do seletor, com o texto curto e a explicação. */
export const MODOS_COR: { id: ModoCor; rotulo: string; descricao: string }[] = [
  { id: "vencedor", rotulo: "Vencedor", descricao: "Quem lidera em cada área" },
  { id: "intensidade", rotulo: "% de votos", descricao: "A cor de quem lidera, mais forte quanto maior o percentual" },
  { id: "mudanca", rotulo: "Mudança", descricao: "Quem cresceu mais do 1º para o 2º turno" },
  { id: "abstencao", rotulo: "Abstenção", descricao: "Quem não foi votar" },
];

/** Uma faixa da escala: até que valor vale e a força da cor (1 = cheia). */
export interface Faixa {
  ate: number;
  forca: number;
  rotulo: string;
}

/** Percentual dos válidos de quem lidera. */
export const FAIXAS_PCT: Faixa[] = [
  { ate: 45, forca: 0.3, rotulo: "até 45%" },
  { ate: 50, forca: 0.45, rotulo: "45–50%" },
  { ate: 55, forca: 0.6, rotulo: "50–55%" },
  { ate: 60, forca: 0.74, rotulo: "55–60%" },
  { ate: 70, forca: 0.87, rotulo: "60–70%" },
  { ate: Infinity, forca: 1, rotulo: "70% ou mais" },
];

/** Diferença, em pontos percentuais, entre o crescimento de um finalista e o do outro. */
export const FAIXAS_MUDANCA: Faixa[] = [
  { ate: 2, forca: 0.3, rotulo: "até 2 p.p." },
  { ate: 5, forca: 0.5, rotulo: "2–5 p.p." },
  { ate: 10, forca: 0.75, rotulo: "5–10 p.p." },
  { ate: Infinity, forca: 1, rotulo: "10 p.p. ou mais" },
];

/** Abstenção sobre o eleitorado. */
export const FAIXAS_ABSTENCAO: Faixa[] = [
  { ate: 15, forca: 0.2, rotulo: "até 15%" },
  { ate: 20, forca: 0.38, rotulo: "15–20%" },
  { ate: 25, forca: 0.56, rotulo: "20–25%" },
  { ate: 30, forca: 0.74, rotulo: "25–30%" },
  { ate: Infinity, forca: 0.92, rotulo: "30% ou mais" },
];

/** A força da faixa em que o valor cai. */
export function forcaNa(faixas: Faixa[], valor: number): number {
  return (faixas.find((f) => valor < f.ate) ?? faixas[faixas.length - 1]!).forca;
}

/** A cor misturada com a superfície na força dada (1 devolve a própria cor). */
export function misturar(cor: string, forca: number): string {
  return forca >= 1 ? cor : `color-mix(in srgb, ${cor} ${Math.round(forca * 100)}%, var(--superficie))`;
}

/** Os dois finalistas comparados no modo Mudança: o primeiro e o segundo do feed do 2º turno. */
export interface Finalista {
  numero: string;
  nome: string;
  cor: number;
}

/** O que o modo Mudança precisa além da parte: as do 1º turno, pelo código, e os dois finalistas. */
export interface ContextoMudanca {
  primeiro: Map<string, Parte>;
  a: Finalista;
  b: Finalista;
}

/** Percentual de um candidato (ou partido) na parte: o de `pcts` ou, se ele lidera, o `pct`. */
export function pctNaParte(p: Parte, numero: string): number | null {
  const v = p.pcts?.[numero];
  if (v !== undefined && v !== null) return v;
  return p.lider === numero ? (p.pct ?? null) : null;
}

/**
 * Quanto o finalista `a` cresceu a mais que o `b` do 1º para o 2º turno na
 * parte, em pontos percentuais dos válidos (negativo: o `b` cresceu mais).
 * No 2º turno, com dois candidatos, o percentual de um é o resto do outro.
 * Null quando falta o percentual de algum deles em algum turno.
 */
export function mudancaNaParte(dois: Parte, um: Parte | undefined, ctx: ContextoMudanca): number | null {
  if (!um) return null;
  const a2d = pctNaParte(dois, ctx.a.numero);
  const b2d = pctNaParte(dois, ctx.b.numero);
  const a2 = a2d ?? (b2d !== null ? 100 - b2d : null);
  const b2 = b2d ?? (a2d !== null ? 100 - a2d : null);
  const a1 = pctNaParte(um, ctx.a.numero);
  const b1 = pctNaParte(um, ctx.b.numero);
  if (a2 === null || b2 === null || a1 === null || b1 === null) return null;
  return a2 - a1 - (b2 - b1);
}

/** Sem dado para a área no modo: o mesmo cinza claro da área sem líder. */
const SEM_DADO = "var(--mapa-sem-lider)";

/** A cor da área no modo escolhido. */
export function corDaParte(modo: ModoCor, p: Parte | undefined, ctx: ContextoMudanca | null): string {
  if (!p) return SEM_DADO;
  if (modo === "abstencao") {
    return p.pct_abstencao == null ? SEM_DADO : misturar("var(--texto)", forcaNa(FAIXAS_ABSTENCAO, p.pct_abstencao));
  }
  if (modo === "mudanca") {
    const d = ctx ? mudancaNaParte(p, ctx.primeiro.get(p.codigo), ctx) : null;
    if (d === null || !ctx) return SEM_DADO;
    return misturar(varCor((d >= 0 ? ctx.a : ctx.b).cor), forcaNa(FAIXAS_MUDANCA, Math.abs(d)));
  }
  if (!p.lider) return SEM_DADO;
  if (modo === "intensidade" && p.pct != null) return misturar(varCorMapa(p.cor), forcaNa(FAIXAS_PCT, p.pct));
  return varCorMapa(p.cor);
}

/** Se o modo tem dado para pintar estas partes (o seletor desabilita o que não tem). */
export function modoDisponivel(modo: ModoCor, partes: Parte[], ctx: ContextoMudanca | null): boolean {
  if (modo === "abstencao") return partes.some((p) => p.pct_abstencao != null);
  if (modo === "mudanca") return !!ctx && partes.some((p) => mudancaNaParte(p, ctx.primeiro.get(p.codigo), ctx) !== null);
  return true;
}

/**
 * Partes de UF (o mapa do Brasil por estado) com `pcts` e `pct_abstencao` tirados dos feeds das próprias UFs,
 * que trazem todos os candidatos e o comparecimento: assim Mudança e Abstenção funcionam por estado também
 * nos feeds gravados antes de as partes terem esses campos. A parte que já os tem fica como está.
 */
export function completarComFeedsDasUfs(partes: Parte[], feeds: Feed[]): Parte[] {
  const porUf = new Map(feeds.map((f) => [f.abrangencia.codigo, f] as const));
  return partes.map((p) => {
    const f = porUf.get(p.codigo);
    if (!f || f.tipo !== "resultado") return p;
    const mais = f.candidatos.filter((c) => c.valido && c.votos > 0).slice(0, 4);
    return {
      ...p,
      pcts: p.pcts ?? Object.fromEntries(mais.map((c) => [c.numero, c.pct])),
      pct_abstencao: p.pct_abstencao ?? f.comparecimento.pct_abstencao,
    };
  });
}
