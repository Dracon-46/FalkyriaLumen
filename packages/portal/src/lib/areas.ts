/**
 * Ligação entre as áreas da malha do IBGE e as partes do feed.
 *
 * Na malha, cada área tem o `codarea` do IBGE (2 dígitos na UF, 7 no
 * município). No feed, a parte tem o código da abrangência (a sigla da UF, ou
 * o código IBGE do município) e, quando há área correspondente no mapa atual,
 * o `ibge`. Nas eleições antigas, a sigla pode ser de uma UF que não existe
 * mais: o Território do Guaporé ("gp") declara o `ibge` de Rondônia e pinta
 * a área dela; a Guanabara ("gb") não declara nenhum e fica fora do mapa.
 */

import { CODIGO_UF } from "./busca";
import type { Parte } from "./tipos";

/** O que cada área do mapa é: UF (mapa do Brasil) ou município (mapa de uma UF). */
export type NivelMapa = "uf" | "mu";

/** Índice das partes pelo código e pelo código IBGE. */
export function indexarPartes(partes: Parte[]): Map<string, Parte> {
  const m = new Map<string, Parte>();
  for (const p of partes) {
    m.set(p.codigo, p);
    if (p.ibge) m.set(p.ibge, p);
  }
  return m;
}

/** Código da parte que corresponde à área no feed atual: a sigla da UF no mapa do Brasil, o próprio código no da UF. */
export function chaveDaArea(codarea: string, nivel: NivelMapa): string {
  return nivel === "uf" ? (CODIGO_UF[codarea] ?? codarea) : codarea;
}

/** A parte que pinta a área: pela sigla atual da UF ou, se não houver, pelo código IBGE declarado pela parte. */
export function parteDaArea(porCodigo: Map<string, Parte>, codarea: string, nivel: NivelMapa): Parte | undefined {
  return porCodigo.get(chaveDaArea(codarea, nivel)) ?? porCodigo.get(codarea);
}

/**
 * Partes que nenhuma área da malha representa: o exterior, UFs extintas, o
 * Distrito Federal anterior a 1960 (a cidade do Rio de Janeiro) e municípios
 * que o IBGE ainda não tem na malha. Elas aparecem fora do mapa.
 */
export function partesSemArea(partes: Parte[], codareas: string[], nivel: NivelMapa): Parte[] {
  const porCodigo = indexarPartes(partes);
  const representadas = new Set<string>();
  for (const codarea of codareas) {
    const p = parteDaArea(porCodigo, codarea, nivel);
    if (p) representadas.add(p.codigo);
  }
  return partes.filter((p) => !representadas.has(p.codigo));
}
