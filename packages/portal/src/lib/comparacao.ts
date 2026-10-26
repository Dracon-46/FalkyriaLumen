/**
 * Comparação do 2º turno com o 1º, na mesma abrangência: quanto cada
 * finalista ganhou e de onde vieram, na conta líquida, os votos a mais.
 *
 * O ganho somado dos finalistas é exatamente os votos que os demais
 * candidatos tiveram no 1º turno mais a variação dos votos válidos; e a
 * variação dos válidos é a do comparecimento menos a dos brancos, dos nulos e
 * dos anulados. O voto é secreto: a conta diz quanto mudou, não quem mudou de
 * candidato (eleitor do 1º colocado pode ter ido para o 2º e vice-versa).
 */

import type { EleicaoIndice, FeedResultado, Indice } from "./tipos";

/** A eleição do 1º turno que corresponde a um 2º turno (mesmo ano e tipo) e tem o cargo; null se não há. */
export function primeiroTurnoDe(indice: Indice, eleicao: EleicaoIndice, cargo: string): EleicaoIndice | null {
  if (eleicao.turno !== 2) return null;
  return (
    indice.eleicoes.find(
      (e) => e.turno === 1 && e.ano === eleicao.ano && e.tipo === eleicao.tipo && e.cargos.some((c) => c.slug === cargo),
    ) ?? null
  );
}

/** Um finalista: votos e percentual dos válidos nos dois turnos. */
export interface LinhaComparacao {
  numero: string;
  nome: string;
  partido: string | null;
  cor: number;
  votos1: number;
  votos2: number;
  pct1: number | null;
  pct2: number | null;
}

/** Variação de um total entre os turnos; null quando falta o número em algum deles. */
export interface Variacao {
  turno1: number | null;
  turno2: number | null;
  diferenca: number | null;
}

/** O que a tela de comparação mostra. */
export interface Comparacao {
  finalistas: LinhaComparacao[];
  /** Votos válidos que, no 1º turno, foram para os candidatos que não estão no 2º. */
  demais: number | null;
  /** Ganho somado dos finalistas do 1º para o 2º turno. */
  ganho: number;
  validos: Variacao;
  comparecimento: Variacao;
  abstencao: Variacao;
  brancos: Variacao;
  nulos: Variacao;
  anulados: Variacao;
}

/** Diferença entre os turnos, se os dois números existem. */
function variacao(turno1: number | null, turno2: number | null): Variacao {
  return { turno1, turno2, diferenca: turno1 !== null && turno2 !== null ? turno2 - turno1 : null };
}

/** Compara os dois turnos de um cargo na mesma abrangência. */
export function compararTurnos(primeiro: FeedResultado, segundo: FeedResultado): Comparacao {
  const no1 = new Map(primeiro.candidatos.map((c) => [c.numero, c] as const));
  const finalistas = segundo.candidatos
    .filter((c) => c.valido)
    .map((c) => {
      const antes = no1.get(c.numero);
      return {
        numero: c.numero,
        nome: c.nome_urna,
        partido: c.partido,
        cor: c.cor,
        votos1: antes?.votos ?? 0,
        votos2: c.votos,
        pct1: antes?.pct ?? null,
        pct2: c.pct,
      };
    });
  const v1 = primeiro.votos;
  const v2 = segundo.votos;
  const somaFinalistas1 = finalistas.reduce((s, f) => s + f.votos1, 0);
  return {
    finalistas,
    demais: v1.validos !== null ? v1.validos - somaFinalistas1 : null,
    ganho: finalistas.reduce((s, f) => s + f.votos2 - f.votos1, 0),
    validos: variacao(v1.validos, v2.validos),
    comparecimento: variacao(primeiro.comparecimento.comparecimento, segundo.comparecimento.comparecimento),
    abstencao: variacao(primeiro.comparecimento.abstencao, segundo.comparecimento.abstencao),
    brancos: variacao(v1.brancos, v2.brancos),
    nulos: variacao(v1.nulos, v2.nulos),
    anulados: variacao(v1.anulados, v2.anulados),
  };
}
