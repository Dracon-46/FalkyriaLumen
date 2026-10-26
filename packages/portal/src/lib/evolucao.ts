/**
 * Contas do gráfico de evolução da apuração: as séries de cada candidato, a
 * vantagem entre os dois primeiros e a escala vertical. Ficam fora do
 * componente para serem testadas sem desenhar nada.
 */

import type { FeedHistorico } from "./tipos";

/** A linha de um candidato: x = % de seções totalizadas, y = % dos votos no ponto. */
export interface SerieEvolucao {
  numero: string;
  rotulo: string;
  cor: number;
  pontos: { x: number; y: number }[];
}

/** O que o gráfico desenha: as séries, e para cada ponto o % de seções e o instante. */
export interface Evolucao {
  series: SerieEvolucao[];
  xs: number[];
  instantes: (string | null)[];
}

/**
 * Séries das `quantas` maiores votações no último ponto. Leituras sem seção
 * totalizada ou sem voto apurado ficam de fora: no começo da noite elas
 * dariam 0% a todos e puxariam as linhas até o chão.
 */
export function seriesDaEvolucao(historico: FeedHistorico, quantas: number): Evolucao {
  const pontos = historico.pontos
    .map((p) => ({ p, total: Object.values(p.votos).reduce((s, v) => s + v, 0) }))
    .filter(({ p, total }) => p.pct_secoes != null && total > 0);
  const ultimo = pontos[pontos.length - 1]?.p;
  const ordem = [...historico.candidatos]
    .sort((a, b) => (ultimo?.votos[b.numero] ?? 0) - (ultimo?.votos[a.numero] ?? 0))
    .slice(0, quantas);
  const series = ordem.map((c) => ({
    numero: c.numero,
    rotulo: c.nome_urna,
    cor: c.cor,
    pontos: pontos.map(({ p, total }) => ({ x: p.pct_secoes ?? 0, y: (100 * (p.votos[c.numero] ?? 0)) / total })),
  }));
  return { series, xs: pontos.map(({ p }) => p.pct_secoes ?? 0), instantes: pontos.map(({ p }) => p.t) };
}

/** Diferença, em pontos percentuais, do primeiro para o segundo colocado no fim, ponto a ponto (negativa quando o segundo estava à frente). */
export function vantagem(series: SerieEvolucao[]): { x: number; y: number }[] {
  const [a, b] = series;
  if (!a || !b) return [];
  return a.pontos.map((p, i) => ({ x: p.x, y: p.y - (b.pontos[i]?.y ?? 0) }));
}

/**
 * Pontos que decidem a escala vertical: a partir de 2% das seções. No começo
 * da apuração, com poucas urnas, o percentual oscila muito (um candidato com
 * 58% e o outro com 42% em 0,3% das seções) e achataria o resto da noite; o
 * gráfico recorta esse trecho na borda, e a dica continua com o valor exato.
 */
export function pontosDaEscala<T extends { x: number }>(pontos: T[]): T[] {
  const depois = pontos.filter((p) => p.x >= 2);
  return depois.length >= 2 ? depois : pontos;
}

const PASSOS = [0.5, 1, 2, 5, 10, 20, 25];

/**
 * Escala vertical justa para os valores: de um múltiplo do passo abaixo do
 * menor a um acima do maior, com no máximo seis divisões. Com `zero`, o zero
 * entra na faixa (a linha da vantagem precisa dele); os percentuais ficam
 * entre 0 e 100.
 */
export function escalaVertical(valores: number[], { zero = false } = {}): { min: number; max: number; marcas: number[] } {
  let min = Math.min(...valores, ...(zero ? [0] : []));
  let max = Math.max(...valores, ...(zero ? [0] : []));
  if (!Number.isFinite(min) || !Number.isFinite(max)) return { min: 0, max: 100, marcas: [0, 25, 50, 75, 100] };
  if (max - min < 1) {
    min -= 0.5;
    max += 0.5;
  }
  const passo = PASSOS.find((p) => (Math.ceil(max / p) - Math.floor(min / p)) <= 6) ?? 25;
  let baixo = Math.floor(min / passo) * passo;
  let alto = Math.ceil(max / passo) * passo;
  if (!zero) {
    baixo = Math.max(0, baixo);
    alto = Math.min(100, alto);
  }
  const marcas: number[] = [];
  for (let v = baixo; v <= alto + passo / 1000; v += passo) marcas.push(Math.round(v * 1000) / 1000);
  return { min: baixo, max: alto, marcas };
}
