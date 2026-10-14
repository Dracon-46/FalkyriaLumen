/**
 * Acesso aos feeds da aba Eleições.
 *
 * O portal nunca fala com o TSE (princípio P6): lê os arquivos que o coletor
 * grava. A base é `/dados/eleicoes` no mesmo domínio, ou a definida em
 * `NEXT_PUBLIC_DADOS_ELEICOES` no build (CDN separada, por exemplo).
 *
 * Cache: feeds de resultado vão com `cache: "no-cache"` — o navegador
 * revalida a cada consulta e o servidor responde 304 quando nada mudou, o que
 * faz o "ao vivo" funcionar sem WebSocket. Malhas e cadastro não mudam
 * durante a noite e ficam no cache do navegador.
 */

import type { Topologia } from "./topojson";
import type { CadastroMunicipios, Feed, FeedHistorico, Indice } from "./tipos";
import { ErroFeed, validarFeed, validarHistorico, validarIndice, validarMunicipios } from "./validacao";

/**
 * Raiz dos feeds, sem barra final; fixada no build (site estático). Variável vazia vale como ausente: o
 * fluxo de publicação passa a variável do repositório mesmo quando ela não foi definida.
 */
export const BASE_DADOS = (process.env.NEXT_PUBLIC_DADOS_ELEICOES || "/dados/eleicoes").replace(/\/$/, "");

const SEGURO = /^[a-z0-9][a-z0-9-]{0,80}$/;

/**
 * Deixa passar só nomes de arquivo inofensivos (minúsculas, dígitos e hífen).
 * Os pedaços dos caminhos vêm da URL da página e do próprio feed; esta
 * barreira garante que nenhum `..` ou `/` chegue ao `fetch`.
 */
function seguro(parte: string): string {
  if (!SEGURO.test(parte)) throw new ErroFeed(`nome inválido: ${parte}`);
  return parte;
}

/**
 * Endereço de cada arquivo que o portal lê, no mesmo desenho de diretórios
 * que o coletor grava. Todo pedaço variável passa por `seguro`; `foto`
 * devolve null para caminho fora do padrão `fotos/….jpg`.
 */
export const urls = {
  indice: () => `${BASE_DADOS}/indice.json`,
  municipios: () => `${BASE_DADOS}/municipios.json`,
  feed: (eleicao: string, cargo: string, abrangencia: string) =>
    `${BASE_DADOS}/${seguro(eleicao)}/${seguro(cargo)}/${seguro(abrangencia)}.json`,
  historico: (eleicao: string, cargo: string, abrangencia: string) =>
    `${BASE_DADOS}/${seguro(eleicao)}/${seguro(cargo)}/historico-${seguro(abrangencia)}.json`,
  malhaBrasil: () => `${BASE_DADOS}/geo/br-uf.json`,
  malhaUf: (uf: string) => `${BASE_DADOS}/geo/uf-${seguro(uf)}-mu.json`,
  foto: (relativo: string) => (/^fotos\/[\w/.-]+\.jpe?g$/.test(relativo) ? `${BASE_DADOS}/${relativo}` : null),
};

/**
 * Se a resposta 400 é o "arquivo não existe" do Supabase Storage, que responde assim nos buckets públicos
 * (`{"statusCode":"404","error":"not_found"}`), em vez de 404.
 */
export async function inexistenteNoSupabase(resposta: Response): Promise<boolean> {
  if (resposta.status !== 400) return false;
  try {
    const corpo = await resposta.text();
    return /"statusCode"\s*:\s*"?404|not_found|NoSuchKey/.test(corpo);
  } catch {
    return false;
  }
}

/** JSON da URL; `null` quando o arquivo não existe (404, ou o 400 equivalente do Supabase). Outros erros viram `ErroFeed`. */
export async function obterJson(url: string, opcoes: { sinal?: AbortSignal; cache?: RequestCache } = {}) {
  let resposta: Response;
  try {
    resposta = await fetch(url, { cache: opcoes.cache ?? "no-cache", signal: opcoes.sinal });
  } catch (erro) {
    if ((erro as Error).name === "AbortError") throw erro;
    throw new ErroFeed(`sem resposta de ${url}`);
  }
  if (resposta.status === 404 || (await inexistenteNoSupabase(resposta))) return null;
  if (!resposta.ok) throw new ErroFeed(`${url}: HTTP ${resposta.status}`);
  try {
    return (await resposta.json()) as unknown;
  } catch {
    throw new ErroFeed(`${url}: conteúdo não é JSON`);
  }
}

/** Lê e confere o índice de eleições; `null` quando o servidor ainda não tem nenhuma publicada. */
export async function carregarIndice(sinal?: AbortSignal): Promise<Indice | null> {
  const bruto = await obterJson(urls.indice(), { sinal });
  return bruto === null ? null : validarIndice(bruto);
}

/** Lê e confere o feed (resultado ou panorama) de uma eleição, cargo e abrangência; `null` se não existe. */
export async function carregarFeed(eleicao: string, cargo: string, abrangencia: string,
  sinal?: AbortSignal): Promise<Feed | null> {
  const url = urls.feed(eleicao, cargo, abrangencia);
  const bruto = await obterJson(url, { sinal });
  return bruto === null ? null : validarFeed(bruto, url);
}

/** Lê e confere a evolução da apuração; `null` quando não há histórico para a combinação. */
export async function carregarHistorico(eleicao: string, cargo: string, abrangencia: string,
  sinal?: AbortSignal): Promise<FeedHistorico | null> {
  const url = urls.historico(eleicao, cargo, abrangencia);
  const bruto = await obterJson(url, { sinal });
  return bruto === null ? null : validarHistorico(bruto, url);
}

const cacheMalhas = new Map<string, Promise<Topologia | null>>();

/** Malha do IBGE; uma requisição por arquivo durante a visita. */
export function carregarMalha(url: string): Promise<Topologia | null> {
  let p = cacheMalhas.get(url);
  if (!p) {
    p = obterJson(url, { cache: "force-cache" }).then((b) => (b === null ? null : (b as Topologia)));
    p.catch(() => cacheMalhas.delete(url));
    cacheMalhas.set(url, p);
  }
  return p;
}

let cacheMunicipios: Promise<CadastroMunicipios | null> | null = null;

/**
 * Cadastro de municípios para a busca, baixado uma vez por visita. A promessa
 * fica guardada; se falhar, sai do cache para a próxima abertura tentar de novo.
 */
export function carregarMunicipios(): Promise<CadastroMunicipios | null> {
  if (!cacheMunicipios) {
    cacheMunicipios = obterJson(urls.municipios(), { cache: "force-cache" }).then((b) =>
      b === null ? null : validarMunicipios(b),
    );
    cacheMunicipios.catch(() => {
      cacheMunicipios = null;
    });
  }
  return cacheMunicipios;
}

/** Intervalo de atualização: 15 s ao vivo; sem atualização automática no histórico. */
export const INTERVALO_AO_VIVO_MS = 15_000;
