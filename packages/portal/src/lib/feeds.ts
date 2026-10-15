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
 * durante a noite e ficam no cache do navegador. Os feeds de uma eleição
 * encerrada também ficam guardados em memória durante a visita (`guardar`):
 * voltar a um estado ou a um município já visto não espera a rede, e a
 * pré-carga (`preCarregarFeed`, ao passar o cursor no mapa) deixa o clique
 * instantâneo.
 */

import type { Topologia } from "./topojson";
import type { ArquivoZonas, CadastroMunicipios, Feed, FeedHistorico, Indice, IndiceZonas } from "./tipos";
import {
  ErroFeed,
  validarFeed,
  validarHistorico,
  validarIndice,
  validarIndiceZonas,
  validarMunicipios,
  validarZonas,
} from "./validacao";

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
  /** Contorno fino (qualidade `maxima`) de um município com mais de uma zona eleitoral. */
  contorno: (ibge: string) => `${BASE_DADOS}/geo/mu/${seguro(ibge)}.json`,
  zonasIndice: (ano: number) => `${BASE_DADOS}/geo/zonas-${seguro(String(ano))}/indice.json`,
  zonas: (ano: number, ibge: string) => `${BASE_DADOS}/geo/zonas-${seguro(String(ano))}/mu-${seguro(ibge)}.json`,
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

/**
 * Guarda a promessa da `chave` enquanto a visita durar (até `limite` itens, saindo os mais antigos); se
 * ela falhar, sai do cache para a próxima tentativa. Várias telas pedindo o mesmo arquivo fazem uma
 * requisição só.
 */
function memorizar<T>(cache: Map<string, Promise<T>>, chave: string, criar: () => Promise<T>, limite = Infinity): Promise<T> {
  const guardada = cache.get(chave);
  if (guardada) return guardada;
  const nova = criar();
  nova.catch(() => cache.delete(chave));
  cache.set(chave, nova);
  while (cache.size > limite) cache.delete(cache.keys().next().value as string);
  return nova;
}

const cacheFeeds = new Map<string, Promise<Feed | null>>();
/** Feeds guardados em memória: um estado com centenas de municípios cabe com folga. */
const LIMITE_CACHE_FEEDS = 400;

/**
 * Lê e confere o feed (resultado ou panorama) de uma eleição, cargo e abrangência; `null` se não existe.
 * Com `guardar` (eleição encerrada: os números não mudam mais), a resposta fica em memória e o `sinal` não
 * cancela a leitura, que serve a quem pedir depois.
 */
export async function carregarFeed(eleicao: string, cargo: string, abrangencia: string,
  sinal?: AbortSignal, opcoes: { guardar?: boolean } = {}): Promise<Feed | null> {
  const url = urls.feed(eleicao, cargo, abrangencia);
  const ler = async () => {
    const bruto = await obterJson(url, { sinal: opcoes.guardar ? undefined : sinal });
    return bruto === null ? null : validarFeed(bruto, url);
  };
  return opcoes.guardar ? memorizar(cacheFeeds, url, ler, LIMITE_CACHE_FEEDS) : ler();
}

/** Pré-carga de um feed de eleição encerrada (cursor sobre a área do mapa): erro aqui não aparece na tela. */
export function preCarregarFeed(eleicao: string, cargo: string, abrangencia: string): void {
  carregarFeed(eleicao, cargo, abrangencia, undefined, { guardar: true }).catch(() => undefined);
}

/** Lê e confere a evolução da apuração; `null` quando não há histórico para a combinação. */
export async function carregarHistorico(eleicao: string, cargo: string, abrangencia: string,
  sinal?: AbortSignal): Promise<FeedHistorico | null> {
  const url = urls.historico(eleicao, cargo, abrangencia);
  const bruto = await obterJson(url, { sinal });
  return bruto === null ? null : validarHistorico(bruto, url);
}

const cacheMalhas = new Map<string, Promise<Topologia | null>>();

/** Malha do IBGE (a da UF, ou o contorno fino de um município); uma requisição por arquivo durante a visita. */
export function carregarMalha(url: string): Promise<Topologia | null> {
  return memorizar(cacheMalhas, url, () =>
    obterJson(url, { cache: "force-cache" }).then((b) => (b === null ? null : (b as Topologia))),
  );
}

const cacheIndiceZonas = new Map<string, Promise<IndiceZonas | null>>();
const cacheZonas = new Map<string, Promise<ArquivoZonas | null>>();

/** Índice das zonas de um ano (municípios com mais de uma zona); `null` quando o ano não tem mapa das zonas. */
export function carregarIndiceZonas(ano: number): Promise<IndiceZonas | null> {
  const url = urls.zonasIndice(ano);
  return memorizar(cacheIndiceZonas, url, () =>
    obterJson(url, { cache: "force-cache" }).then((b) => (b === null ? null : validarIndiceZonas(b, url))),
  );
}

/** Zonas e locais de votação de um município num ano; `null` quando o arquivo não existe. */
export function carregarZonas(ano: number, ibge: string): Promise<ArquivoZonas | null> {
  const url = urls.zonas(ano, ibge);
  return memorizar(cacheZonas, url, () =>
    obterJson(url, { cache: "force-cache" }).then((b) => (b === null ? null : validarZonas(b, url))),
    40,
  );
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
