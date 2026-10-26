/**
 * Feeds publicados antes do ADR-052 (sem o campo `paleta`) lidos na regra de
 * cores atual: o PL azul e o PT vermelho já na leitura, sem esperar a carga
 * refazer os arquivos. Feed com `paleta` atual passa sem mudança.
 */

import { corDaRegraAtual, PALETA_DOS_FEEDS } from "./cores";
import type { Feed, FeedHistorico, Parte } from "./tipos";

/** O feed (resultado, panorama ou evolução) com as cores na regra atual. */
export function naRegraAtual<F extends Feed | FeedHistorico>(feed: F): F {
  if ((feed.paleta ?? 1) >= PALETA_DOS_FEEDS) return feed;
  if (feed.tipo === "historico") {
    return { ...feed, candidatos: feed.candidatos.map((c) => ({ ...c, cor: corDaRegraAtual(c.cor, c.partido) })) };
  }
  // O líder de uma parte é o número de um candidato do próprio feed ou, nos proporcionais e panoramas, a sigla
  const partidoDoNumero = new Map(feed.tipo === "resultado" ? feed.candidatos.map((c) => [c.numero, c.partido]) : []);
  const parte = (p: Parte): Parte => ({
    ...p,
    cor: corDaRegraAtual(p.cor, p.partido ?? partidoDoNumero.get(p.lider ?? "") ?? p.lider),
  });
  if (feed.tipo === "resultado") {
    return {
      ...feed,
      candidatos: feed.candidatos.map((c) => ({ ...c, cor: corDaRegraAtual(c.cor, c.partido) })),
      partes: feed.partes.map(parte),
    };
  }
  return {
    ...feed,
    partidos: feed.partidos.map((p) => ({ ...p, cor: corDaRegraAtual(p.cor, p.partido) })),
    partes: feed.partes.map(parte),
  };
}
