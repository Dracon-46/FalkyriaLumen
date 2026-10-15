/**
 * Seleção da tela ↔ parâmetros da URL.
 *
 * `/eleicoes/?e=2026-1t-geral&c=presidente&a=uf-sp` é um link que abre
 * exatamente o que estava na tela: dá para compartilhar o resultado de um
 * município. Parâmetros inválidos são descartados, nunca interpretados.
 */

import { CODIGO_UF } from "./busca";
import type { Selecao } from "./tipos";

const SEGURO = /^[a-z0-9][a-z0-9-]{0,80}$/;

/**
 * Seleção a partir da URL. Valor fora do formato vira null (ou "br", na
 * abrangência), e a tela escolhe o padrão em `selecao.ts`.
 */
export function lerSelecao(params: URLSearchParams): Selecao {
  const e = params.get("e");
  const c = params.get("c");
  const a = params.get("a");
  return {
    eleicao: e && SEGURO.test(e) ? e : null,
    cargo: c && SEGURO.test(c) ? c : null,
    abrangencia: a && SEGURO.test(a) && /^(br|uf-[a-z][a-z0-9-]*|mu-[a-z0-9-]+)$/.test(a) ? a : "br",
    tv: params.get("tv") === "1",
  };
}

/** Seleção → `?e=…&c=…&a=…&tv=1`, omitindo o que é padrão (Brasil, sem modo TV); "" quando nada sobra. */
export function escreverSelecao(s: Selecao): string {
  const p = new URLSearchParams();
  if (s.eleicao) p.set("e", s.eleicao);
  if (s.cargo) p.set("c", s.cargo);
  if (s.abrangencia && s.abrangencia !== "br") p.set("a", s.abrangencia);
  if (s.tv) p.set("tv", "1");
  const q = p.toString();
  return q ? `?${q}` : "";
}

/**
 * UF da abrangência, sem esperar o feed: "uf-sp" → "sp"; "mu-3550308" → "sp"
 * (os dois primeiros dígitos do código IBGE); "mu-ap-06130" (município sem
 * código IBGE) e "mu-zz-29254" (exterior) → a sigla do começo. No Brasil, null.
 */
export function ufDaAbrangencia(abrangencia: string): string | null {
  if (abrangencia.startsWith("uf-")) return abrangencia.slice(3);
  const ibge = /^mu-(\d{2})\d{5}$/.exec(abrangencia);
  if (ibge) return CODIGO_UF[ibge[1]!] ?? null;
  return /^mu-([a-z]{2})-/.exec(abrangencia)?.[1] ?? null;
}
