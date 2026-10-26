/**
 * Cores dos feeds lidas sempre na regra atual (ADR-052), seja qual for o
 * arquivo: o PL azul e o PT vermelho já na leitura.
 *
 * Feed sem o campo `paleta` (gravado antes do ADR-052) passa inteiro pela
 * regra de transição (`corDaRegraAtual`). Feed com `paleta` atual pode ainda
 * trazer partes de uma leitura anterior (a coleta regrava o feed da UF antes
 * de baixar de novo cada município, 26/10/2026): nele, só PL e PT são
 * conferidos pelo partido, e o resto fica como está.
 */

import { CORES_DOS_PARTIDOS, corDaRegraAtual, PALETA_DOS_FEEDS } from "./cores";
import type { Feed, FeedHistorico, Parte } from "./tipos";

/** O feed (resultado, panorama ou evolução) com as cores na regra atual. */
export function naRegraAtual<F extends Feed | FeedHistorico>(feed: F): F {
  const antigo = (feed.paleta ?? 1) < PALETA_DOS_FEEDS;
  // No feed antigo, toda cor muda; no atual, só a de PL e PT é conferida
  const cor = (atual: number, partido: string | null | undefined) =>
    antigo ? corDaRegraAtual(atual, partido) : (partido ? CORES_DOS_PARTIDOS[partido] : undefined) ?? atual;
  if (feed.tipo === "historico") {
    return { ...feed, candidatos: feed.candidatos.map((c) => ({ ...c, cor: cor(c.cor, c.partido) })) };
  }
  // O líder de uma parte é o número de um candidato do próprio feed ou, nos proporcionais e panoramas, a sigla
  const partidoDoNumero = new Map(feed.tipo === "resultado" ? feed.candidatos.map((c) => [c.numero, c.partido]) : []);
  const parte = (p: Parte): Parte => ({
    ...p,
    cor: p.lider ? cor(p.cor, p.partido ?? partidoDoNumero.get(p.lider) ?? p.lider) : p.cor,
  });
  if (feed.tipo === "resultado") {
    return {
      ...feed,
      candidatos: feed.candidatos.map((c) => ({ ...c, cor: cor(c.cor, c.partido) })),
      partes: feed.partes.map(parte),
    };
  }
  return {
    ...feed,
    partidos: feed.partidos.map((p) => ({ ...p, cor: cor(p.cor, p.partido) })),
    partes: feed.partes.map(parte),
  };
}
