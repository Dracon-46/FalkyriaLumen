/**
 * Os horários das urnas (ADR-056): a leitura dos arquivos e as contas do painel (as barras dos histogramas, os
 * lugares abaixo e as seções filtradas).
 *
 * Os arquivos ficam no site dos painéis, comprimidos, como os do eleitorado (ADR-055): `horarios/<ano>/br.json.gz`,
 * `uf-<sigla>.json.gz` e `mu/<grupo>.json.gz`, com os municípios do grupo.
 */

import { obterJsonComprimido } from "./comprimido";
import { grupoDoMunicipio } from "./eleitorado";
import { memorizar } from "./feeds";
import { BASE_PAINEL } from "./paineis";
import { validarHorarios } from "./validacao";
import type { ArquivoHorarios, HistogramaHorarios, ResumoHorarios } from "./tipos";

/** Primeiro ano com os horários publicados pelo Lumen (o boletim de urna em tabela começa em 2018). */
export const ANO_INICIAL_HORARIOS = 2018;

/** Encerrar depois disso é sinal de fila na hora de fechar (a votação termina às 17h). */
export const FILA = "17h30";

/** Minutos desde a meia-noite do dia da eleição → `"17:42"`; no dia seguinte, `"+1 00:10"`; ausente → `"—"`. */
export function hhmm(minutos: number | null | undefined): string {
  if (minutos === null || minutos === undefined) return "—";
  const dias = Math.floor(minutos / 1440);
  const resto = minutos - dias * 1440;
  const texto = `${String(Math.floor(resto / 60)).padStart(2, "0")}:${String(resto % 60).padStart(2, "0")}`;
  return dias ? `+${dias} ${texto}` : texto;
}

/** As barras de um histograma, uma por faixa (`"17:00"`), sem as faixas vazias do fim. */
export function barrasDoHistograma(h: HistogramaHorarios): { rotulo: string; valor: number }[] {
  let fim = h.contagens.length;
  while (fim > 1 && h.contagens[fim - 1] === 0) fim--;
  return h.contagens.slice(0, fim).map((valor, i) => ({ rotulo: hhmm(h.inicio + i * h.passo), valor }));
}

/** O turno a mostrar: o da eleição aberta, se o arquivo o tem; senão, o mais recente. */
export function turnoDosHorarios(turnos: Record<string, unknown>, turnoEleicao: number | null | undefined): string | null {
  const chaves = Object.keys(turnos).sort();
  if (turnoEleicao && chaves.includes(String(turnoEleicao))) return String(turnoEleicao);
  return chaves.at(-1) ?? null;
}

/** Uma linha dos lugares abaixo: o resumo do turno, com a abrangência para abrir o lugar (a zona abre no município). */
export interface LinhaLugarHorarios {
  chave: string;
  nome: string;
  abrangencia: string | null;
  resumo: ResumoHorarios;
}

/** As UFs no Brasil, os municípios na UF, as zonas no município, com o turno; em ordem de nome (zona: número). */
export function lugaresDosHorarios(arquivo: ArquivoHorarios, turno: string): LinhaLugarHorarios[] {
  if (arquivo.nivel === "municipio") {
    return (arquivo.zonas ?? []).flatMap((z) => {
      const resumo = z.turnos[turno];
      return resumo ? [{ chave: z.zona, nome: `Zona ${z.zona}`, abrangencia: null, resumo }] : [];
    });
  }
  const prefixo = arquivo.nivel === "br" ? "uf-" : "mu-";
  return Object.entries(arquivo.partes ?? {})
    .flatMap(([chave, p]) => {
      const resumo = p.turnos[turno];
      return resumo ? [{ chave, nome: p.nome, abrangencia: `${prefixo}${chave}`, resumo }] : [];
    })
    .sort((a, b) => a.nome.localeCompare(b.nome, "pt-BR"));
}

/** Uma seção do município num turno, com o nome do local de votação quando o eleitorado o traz. */
export interface LinhaSecaoHorarios {
  zona: string;
  secao: number;
  local: string;
  aptos: number;
  comparecimento: number;
  tipo: string;
  abertura: string | null;
  encerramento: string | null;
  emissao: string | null;
  recebido: string | null;
}

/**
 * As seções do município no turno, de uma zona (ou todas, com `null`), filtradas pelo local (sem acento e caixa)
 * ou pelo número. `locais` (`"<zona>-<local>"` → nome) vem do eleitorado do mesmo ano, quando carregado.
 */
export function secoesDosHorarios(arquivo: ArquivoHorarios, turno: string, zona: string | null, termo: string,
  locais?: Record<string, string>): LinhaSecaoHorarios[] {
  const normal = (s: string) => s.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();
  const busca = normal(termo.trim());
  return (arquivo.secoes ?? [])
    .filter(([t, z]) => String(t) === turno && (zona === null || z === zona))
    .map(([, z, secao, local, aptos, comparecimento, tipo, abertura, encerramento, emissao, recebido]) => ({
      zona: z, secao, aptos, comparecimento, tipo, abertura, encerramento, emissao, recebido,
      local: locais?.[`${z}-${local}`] ?? `Local ${local}`,
    }))
    .filter((s) => !busca || normal(s.local).includes(busca) || String(s.secao) === busca);
}

/** Endereço do arquivo que leva o lugar (`br`, `uf-<sigla>` ou `mu-<chave>`, como a abrangência dos feeds). */
export function urlHorarios(ano: number, abrangencia: string): string | null {
  const base = `${BASE_PAINEL}/horarios/${ano}`;
  if (abrangencia === "br") return `${base}/br.json.gz`;
  const uf = /^uf-([a-z]{2})$/.exec(abrangencia);
  if (uf) return `${base}/uf-${uf[1]}.json.gz`;
  const mu = /^mu-(\d{7}|zz-\d{5})$/.exec(abrangencia);
  return mu ? `${base}/mu/${grupoDoMunicipio(mu[1]!)}.json.gz` : null;
}

const cache = new Map<string, Promise<unknown>>();

/**
 * Os horários de um lugar num ano; `null` quando o ano ou o lugar não tem o arquivo (antes de 2018, ou ainda não
 * publicado). No município, o arquivo do grupo é lido uma vez e serve aos outros municípios dele.
 */
export async function carregarHorarios(ano: number, abrangencia: string): Promise<ArquivoHorarios | null> {
  const url = urlHorarios(ano, abrangencia);
  if (!url) return null;
  const bruto = await memorizar(cache, url, () => obterJsonComprimido(url), 40);
  if (bruto === null || typeof bruto !== "object") return null;
  if (!abrangencia.startsWith("mu-")) return validarHorarios(bruto, url);
  const grupo = bruto as { origem?: unknown; municipios?: Record<string, unknown> };
  const municipio = grupo.municipios?.[abrangencia.slice(3)];
  return municipio ? validarHorarios({ ...(municipio as object), origem: grupo.origem ?? {} }, url) : null;
}
