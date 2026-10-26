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
import { type Forma, pontoProjetado, type Projecao } from "./topojson";

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

/** Código do exterior no feed (a "UF" ZZ do TSE) e na área que o representa no mapa do Brasil. */
export const EXTERIOR = "zz";

/**
 * Área do exterior no mapa do Brasil: um quadrado no Atlântico, ao largo do
 * Sudeste (centro em 38,5° O, 27,5° S), com lado de 6% da largura do mapa. Não
 * é geografia — os votos vêm de cidades do mundo inteiro —, e a tela diz isso
 * com o contorno tracejado e o rótulo; serve para o exterior ter cor, dica e
 * clique como as UFs.
 */
export function formaDoExterior(projecao: Projecao, largura: number): Forma {
  const [cx, cy] = pontoProjetado(projecao, -38.5, -27.5);
  const m = (largura * 0.06) / 2;
  const caixa: [number, number, number, number] = [cx - m, cy - m, cx + m, cy + m];
  const f = (v: number) => Math.round(v * 1000) / 1000;
  return {
    codigo: EXTERIOR,
    d: `M${f(caixa[0])} ${f(caixa[1])}H${f(caixa[2])}V${f(caixa[3])}H${f(caixa[0])}Z`,
    centro: [cx, cy],
    caixa,
  };
}

/**
 * Partes que nenhuma área da malha representa: o exterior (fora do mapa de
 * uma UF; no do Brasil ele tem a área de `formaDoExterior`), UFs extintas, o
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
