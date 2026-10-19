/**
 * Visão 360 de um ente (ADR-035): tudo o que o Lumen publica sobre a União, um estado, o DF ou um município, num
 * lugar só. Aqui ficam as escolhas da página (que eleições mostrar, que estatais o ente controla, em que
 * arquivo está o portal de transparência dele); os números vêm dos arquivos de cada área, sem cópia.
 */

import { CODIGO_UF, normalizar } from "./busca";
import { obterJson } from "./feeds";
import type { CompanhiaCvm, FeedEstatais } from "./estatais";
import { BASE_PAINEL, codigoSeguro, conferir, type TipoEnte } from "./paineis";
import type { EleicaoIndice, Indice } from "./tipos";

/** Uma entidade do ente avaliada pelo PNTP (prefeitura, câmara, poderes, consórcios, estatais). */
export interface EntidadeTransparencia {
  codigo_entidade: string;
  entidade: string;
  poder: string | null;
  esfera: string | null;
  avaliada: boolean;
  indice: number | null;
  essenciais: number | null;
  nivel: string | null;
  nivel_anterior: string | null;
  link: string | null;
  data_envio: string | null;
}

/** Arquivo `transparencia/uf-<sigla>.json` (ou `uniao.json`): as entidades de cada ente da UF. */
export interface FeedTransparencia {
  versao: 1;
  tipo: "transparencia";
  gerado_em: string;
  ciclo: number;
  fonte: string;
  url: string | null;
  coletado_em: string | null;
  entes: Record<string, EntidadeTransparencia[]>;
}

/** Em que arquivo está o ente (o mesmo do Python, `transparencia.arquivo_do_ente`). */
export function arquivoTransparencia(codigo: string): string | null {
  if (codigo === "1") return "transparencia/uniao.json";
  const uf = CODIGO_UF[codigo.slice(0, 2)];
  return uf ? `transparencia/uf-${uf}.json` : null;
}

/** As entidades do ente avaliadas no ciclo mais recente do PNTP, ou `null` se o arquivo não foi publicado. */
export async function carregarTransparencia(codigo: string, sinal?: AbortSignal):
  Promise<{ feed: FeedTransparencia; entidades: EntidadeTransparencia[] } | null> {
  const arquivo = arquivoTransparencia(codigoSeguro(codigo));
  if (!arquivo) return null;
  const url = `${BASE_PAINEL}/${arquivo}`;
  const bruto = await obterJson(url, { sinal });
  if (bruto === null) return null;
  const feed = conferir<FeedTransparencia>(bruto, "transparencia", url);
  return { feed, entidades: feed.entes[codigo] ?? [] };
}

// ------------------------------------------------------------------------------------------ eleições

/** Um resultado a mostrar na página do ente: a eleição, o cargo e a abrangência do feed. */
export interface ResultadoDoEnte {
  eleicao: EleicaoIndice;
  cargo: string;
  nomeCargo: string;
  abrangencia: string;
}

/** A abrangência dos feeds de eleição para o ente: `br`, `uf-sp` ou `mu-3550308`; `null` para código estranho. */
export function abrangenciaDoEnte(codigo: string, tipo: TipoEnte | null): string | null {
  if (tipo === "uniao") return "br";
  if (tipo === "estado" || tipo === "df") return CODIGO_UF[codigo] ? `uf-${CODIGO_UF[codigo]}` : null;
  if (tipo === "municipio") return `mu-${codigo}`;
  return null;
}

/**
 * As eleições que a página mostra: no município, a última de prefeito e a última de presidente (com o
 * resultado no município); no estado e no DF, a última de governador e a de presidente na UF; na União, a de
 * presidente. Do índice publicado, a mais recente com o cargo (o 2º turno, quando houve, vem antes do 1º).
 */
export function eleicoesDoEnte(indice: Indice, codigo: string, tipo: TipoEnte | null): ResultadoDoEnte[] {
  const abrangencia = abrangenciaDoEnte(codigo, tipo);
  if (!abrangencia) return [];
  const cargos = tipo === "municipio" ? ["prefeito", "presidente"] : tipo === "uniao" ? ["presidente"]
    : ["governador", "presidente"];
  const ordenadas = [...indice.eleicoes]
    .filter((e) => !e.simulacao && !e.amostra && e.municipios !== false && e.tipo !== "suplementar")
    .sort((a, b) => (b.data ?? "").localeCompare(a.data ?? "") || b.turno - a.turno);
  const saida: ResultadoDoEnte[] = [];
  for (const cargo of cargos) {
    const eleicao = ordenadas.find((e) => e.cargos.some((c) => c.slug === cargo));
    const c = eleicao?.cargos.find((x) => x.slug === cargo);
    if (eleicao && c) saida.push({ eleicao, cargo, nomeCargo: c.nome, abrangencia });
  }
  return saida;
}

// ------------------------------------------------------------------------------------------ estatais

/**
 * As companhias abertas com controle público conferido que o ente controla, pela esfera do controlador e
 * pelo lugar da sede: na União, as federais; num estado, as estaduais com sede na UF; no DF, as distritais;
 * num município, as municipais com sede nele. É aproximação: a sede não prova o controlador, e a página diz isso.
 */
export function estataisDoEnte(feed: FeedEstatais, nome: string, uf: string | null, tipo: TipoEnte | null): CompanhiaCvm[] {
  const esfera = tipo === "uniao" ? "federal" : tipo === "estado" ? "estadual" : tipo === "df" ? "distrital"
    : tipo === "municipio" ? "municipal" : null;
  if (!esfera) return [];
  return feed.companhias.filter((c) => {
    if (c.controle.esfera !== esfera) return false;
    if (tipo === "uniao") return true;
    if ((c.uf || "").toUpperCase() !== (uf || "").toUpperCase()) return false;
    return tipo !== "municipio" || normalizar(c.municipio || "") === normalizar(nome);
  });
}

/** Quantas estatais federais de capital fechado a SEST lista (só para a União). */
export function federaisDaSest(feed: FeedEstatais): number {
  return (feed.federais?.empresas ?? []).filter((e) => e.situacao === "ativa").length;
}

/** Endereço da página do ente no portal. */
export function urlDoEnte(codigo: string): string {
  return `/ente/?codigo=${encodeURIComponent(codigo)}`;
}
