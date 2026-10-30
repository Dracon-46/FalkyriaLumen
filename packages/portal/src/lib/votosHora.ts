/**
 * Os votos por hora (ADR-057): a leitura dos arquivos e as contas do painel (a hora de mais votos, quantos votaram
 * depois das 17h, até que horas metade votou, os lugares abaixo e as seções).
 *
 * Os arquivos ficam no site dos painéis, comprimidos: `votos-hora/<ano>/br.json.gz`, `uf-<sigla>.json.gz` e
 * `mu/<grupo>.json.gz`, com os municípios do grupo (o 3º e o 4º dígitos do código IBGE; `zz` para o exterior).
 */

import { obterJsonComprimido } from "./comprimido";
import { memorizar } from "./feeds";
import { BASE_PAINEL } from "./paineis";
import { validarVotosHora } from "./validacao";
import type { ArquivoVotosHora, TurnoVotosHora } from "./tipos";

/** Primeiro ano com os logs das urnas nos dados abertos do TSE. */
export const ANO_INICIAL_VOTOS_HORA = 2022;

/** A hora em que a votação termina: quem vota depois estava na fila. */
export const FIM_DA_VOTACAO = 17;

/** As horas e os votos de `[primeira hora, votos nela, ...]`. */
export function horas(porHora: number[]): { hora: number; votos: number }[] {
  const [primeira, ...votos] = porHora;
  return primeira === undefined ? [] : votos.map((v, i) => ({ hora: primeira + i, votos: v }));
}

/** A hora com mais votos (a primeira, no empate); sem votos, `null`. */
export function horaDePico(porHora: number[]): { hora: number; votos: number } | null {
  return horas(porHora).reduce<{ hora: number; votos: number } | null>(
    (melhor, h) => (h.votos > 0 && (!melhor || h.votos > melhor.votos) ? h : melhor), null);
}

/** Votos dados a partir das 17h (na fila do encerramento). */
export function depoisDoFim(porHora: number[]): number {
  return horas(porHora).filter((h) => h.hora >= FIM_DA_VOTACAO).reduce((s, h) => s + h.votos, 0);
}

/** A faixa de 10 minutos em que se chega à metade dos votos (minutos desde a meia-noite); sem faixas, `null`. */
export function metadeAte(t: TurnoVotosHora): number | null {
  const f = t.por_faixa;
  if (!f || f.inicio === null || t.votos <= 0) return null;
  let soma = 0;
  for (const [i, n] of f.contagens.entries()) {
    soma += n;
    if (soma * 2 >= t.votos) return f.inicio + (i + 1) * f.passo;
  }
  return null;
}

/** O turno a mostrar: o da eleição aberta, se o arquivo o tem; senão, o mais recente. */
export function turnoDosVotos(turnos: Record<string, unknown>, turnoEleicao: number | null | undefined): string | null {
  const chaves = Object.keys(turnos).sort();
  if (turnoEleicao && chaves.includes(String(turnoEleicao))) return String(turnoEleicao);
  return chaves.at(-1) ?? null;
}

/** Um lugar abaixo (UF, município ou zona) no turno, com a abrangência para abri-lo (a zona abre no município). */
export interface LinhaLugarVotos {
  chave: string;
  nome: string;
  abrangencia: string | null;
  turno: TurnoVotosHora;
}

/** As UFs no Brasil, os municípios na UF, as zonas no município; em ordem de nome (zona: número). */
export function lugaresDosVotos(arquivo: ArquivoVotosHora, turno: string): LinhaLugarVotos[] {
  if (arquivo.nivel === "municipio") {
    return (arquivo.zonas ?? []).flatMap((z) => {
      const t = z.turnos[turno];
      return t ? [{ chave: z.zona, nome: `Zona ${z.zona}`, abrangencia: null, turno: t }] : [];
    });
  }
  const prefixo = arquivo.nivel === "br" ? "uf-" : "mu-";
  return Object.entries(arquivo.partes ?? {})
    .flatMap(([chave, p]) => {
      const t = p.turnos[turno];
      return t ? [{ chave, nome: p.nome, abrangencia: `${prefixo}${chave}`, turno: t }] : [];
    })
    .sort((a, b) => a.nome.localeCompare(b.nome, "pt-BR"));
}

/** Uma seção do município no turno: votos por hora e o nome do local de votação, quando o eleitorado o traz. */
export interface LinhaSecaoVotos {
  zona: string;
  secao: number;
  local: string | null;
  votos: number;
  porHora: number[];
}

/**
 * As seções do município no turno, de uma zona (ou todas, com `null`), filtradas pelo local (sem acento e caixa) ou
 * pelo número. `locais` (`"<zona>-<seção>"` → nome do local) vem do eleitorado do mesmo ano, quando carregado.
 */
export function secoesDosVotos(arquivo: ArquivoVotosHora, turno: string, zona: string | null, termo: string,
  locais?: Map<string, string>): LinhaSecaoVotos[] {
  const normal = (s: string) => s.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();
  const busca = normal(termo.trim());
  return (arquivo.secoes ?? [])
    .filter(([t, z]) => String(t) === turno && (zona === null || z === zona))
    .map(([, z, secao, ...porHora]) => {
      const ph = porHora as number[];
      return { zona: String(z), secao: Number(secao), local: locais?.get(`${z}-${secao}`) ?? null,
        votos: ph.slice(1).reduce((s, n) => s + n, 0), porHora: ph };
    })
    .filter((s) => !busca || normal(s.local ?? "").includes(busca) || String(s.secao) === busca);
}

/** O nome do local de cada seção (`"<zona>-<seção>"`), das seções e dos locais do arquivo do eleitorado. */
export function locaisDasSecoes(secoes?: [string, number, string, number][],
  locais?: Record<string, string>): Map<string, string> | undefined {
  if (!secoes || !locais) return undefined;
  return new Map(secoes.flatMap(([z, s, l]) => (locais[`${z}-${l}`] ? [[`${z}-${s}`, locais[`${z}-${l}`]!]] : [])));
}

/** A hora como rótulo: `"8h"`. */
export const rotuloHora = (h: number) => `${h}h`;

/** O arquivo do grupo do município: o 3º e o 4º dígitos do código IBGE; `zz` para as cidades do exterior. */
export function grupoDosVotos(chave: string): string {
  return /^\d{7}$/.test(chave) ? chave.slice(2, 4) : "zz";
}

/** Endereço do arquivo que leva o lugar (`br`, `uf-<sigla>` ou `mu-<chave>`, como a abrangência dos feeds). */
export function urlVotosHora(ano: number, abrangencia: string): string | null {
  const base = `${BASE_PAINEL}/votos-hora/${ano}`;
  if (abrangencia === "br") return `${base}/br.json.gz`;
  const uf = /^uf-([a-z]{2})$/.exec(abrangencia);
  if (uf) return `${base}/uf-${uf[1]}.json.gz`;
  const mu = /^mu-(\d{7}|zz-\d{5})$/.exec(abrangencia);
  return mu ? `${base}/mu/${grupoDosVotos(mu[1]!)}.json.gz` : null;
}

const cache = new Map<string, Promise<unknown>>();

/** Os votos por hora de um lugar num ano; `null` quando o ano ou o lugar não tem o arquivo. */
export async function carregarVotosHora(ano: number, abrangencia: string): Promise<ArquivoVotosHora | null> {
  const url = urlVotosHora(ano, abrangencia);
  if (!url) return null;
  const bruto = await memorizar(cache, url, () => obterJsonComprimido(url), 20);
  if (bruto === null || typeof bruto !== "object") return null;
  if (!abrangencia.startsWith("mu-")) return validarVotosHora(bruto, url);
  const grupo = bruto as { origem?: unknown; municipios?: Record<string, unknown> };
  const municipio = grupo.municipios?.[abrangencia.slice(3)];
  return municipio ? validarVotosHora({ ...(municipio as object), origem: grupo.origem ?? {} }, url) : null;
}
