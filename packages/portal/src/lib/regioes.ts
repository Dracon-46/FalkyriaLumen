/**
 * Regiões do Brasil (as cinco do IBGE) para o filtro da aba Eleições: quais
 * UFs entram em cada uma e o resultado somado das UFs de uma região.
 *
 * A soma só vale para cargo disputado no Brasil inteiro (Presidente), em que
 * todas as UFs têm os mesmos candidatos: os votos de cada um, o comparecimento
 * e o destino dos votos são somados; os percentuais saem das somas.
 */

import { CODIGO_UF } from "./busca";
import type { Candidato, FeedResultado, Parte } from "./tipos";

/** Identificador de uma região no filtro. */
export type Regiao = "norte" | "nordeste" | "centro-oeste" | "sudeste" | "sul";

/** As regiões, na ordem do seletor, com o nome e as siglas das UFs. */
export const REGIOES: { id: Regiao; nome: string; ufs: readonly string[] }[] = [
  { id: "norte", nome: "Norte", ufs: ["ac", "am", "ap", "pa", "ro", "rr", "to"] },
  { id: "nordeste", nome: "Nordeste", ufs: ["al", "ba", "ce", "ma", "pb", "pe", "pi", "rn", "se"] },
  { id: "centro-oeste", nome: "Centro-Oeste", ufs: ["df", "go", "ms", "mt"] },
  { id: "sudeste", nome: "Sudeste", ufs: ["es", "mg", "rj", "sp"] },
  { id: "sul", nome: "Sul", ufs: ["pr", "rs", "sc"] },
];

/** As UFs da região, ou null sem região (o Brasil inteiro). */
export function ufsDaRegiao(regiao: Regiao | null): readonly string[] | null {
  return regiao ? (REGIOES.find((r) => r.id === regiao)?.ufs ?? null) : null;
}

/**
 * A UF de uma parte do mapa do Brasil: a sigla, quando a parte é uma UF, ou a dos dois primeiros dígitos do
 * código IBGE, quando é um município. Null para o exterior e para o que não é de UF atual.
 */
export function ufDaParte(p: Parte): string | null {
  if (/^[a-z]{2}$/.test(p.codigo)) return p.codigo;
  const ibge = p.ibge ?? (/^\d{7}$/.test(p.codigo) ? p.codigo : null);
  return ibge ? (CODIGO_UF[ibge.slice(0, 2)] ?? null) : null;
}

/** Soma de números que podem faltar: null só quando falta em todos. */
function somar(valores: (number | null | undefined)[]): number | null {
  const presentes = valores.filter((v): v is number => typeof v === "number");
  return presentes.length ? presentes.reduce((s, v) => s + v, 0) : null;
}

/** Percentual com a precisão dos feeds (seis casas); null sem base. */
function pct(parte: number | null, total: number | null): number | null {
  return parte !== null && total ? Math.round((1e8 * parte) / total) / 1e6 : null;
}

/**
 * O resultado de uma região como um feed de resultado: os feeds das UFs dela somados, com o cabeçalho e os
 * candidatos do feed do Brasil (`base`, que traz a cor, o partido e o vice de cada um) e as UFs como partes.
 * Null se falta o feed de alguma UF: a soma ficaria menor que a região sem avisar.
 */
export function resultadoDaRegiao(base: FeedResultado, nome: string, ufs: FeedResultado[], esperadas: number,
  partes: Parte[]): FeedResultado | null {
  if (ufs.length < esperadas) return null;
  const votosDe = new Map<string, number>();
  for (const f of ufs) {
    for (const c of f.candidatos) votosDe.set(c.numero, (votosDe.get(c.numero) ?? 0) + c.votos);
  }
  const validos = somar(ufs.map((f) => f.votos.validos));
  const comparecimento = somar(ufs.map((f) => f.comparecimento.comparecimento));
  const eleitorado = somar(ufs.map((f) => f.comparecimento.eleitorado));
  const abstencao = somar(ufs.map((f) => f.comparecimento.abstencao));
  const brancos = somar(ufs.map((f) => f.votos.brancos));
  const nulos = somar(ufs.map((f) => f.votos.nulos));
  const candidatos: Candidato[] = base.candidatos
    .map((c) => {
      const votos = votosDe.get(c.numero) ?? 0;
      // Eleito e 2º turno são decididos no Brasil: na região, só os votos
      return { ...c, votos, pct: c.valido ? pct(votos, validos) : null, eleito: false, segundo_turno: false, situacao: "" };
    })
    .sort((a, b) => b.votos - a.votos);
  const secoes = somar(ufs.map((f) => f.totalizacao.secoes));
  const totalizadas = somar(ufs.map((f) => f.totalizacao.secoes_totalizadas));
  return {
    ...base,
    abrangencia: { ...base.abrangencia, nome },
    totalizacao: {
      ...base.totalizacao,
      secoes,
      secoes_totalizadas: totalizadas,
      pct_secoes: pct(totalizadas, secoes),
      finalizada: ufs.every((f) => f.totalizacao.finalizada),
    },
    comparecimento: {
      eleitorado,
      comparecimento,
      abstencao,
      pct_comparecimento: pct(comparecimento, eleitorado),
      pct_abstencao: pct(abstencao, eleitorado),
      eleitorado_secoes_nao_instaladas: somar(ufs.map((f) => f.comparecimento.eleitorado_secoes_nao_instaladas)),
    },
    votos: {
      validos,
      brancos,
      nulos,
      nulos_tecnicos: somar(ufs.map((f) => f.votos.nulos_tecnicos)),
      anulados: somar(ufs.map((f) => f.votos.anulados)),
      legenda: somar(ufs.map((f) => f.votos.legenda)),
      pct_validos: pct(validos, comparecimento),
      pct_brancos: pct(brancos, comparecimento),
      pct_nulos: pct(nulos, comparecimento),
    },
    candidatos,
    partes,
  };
}
