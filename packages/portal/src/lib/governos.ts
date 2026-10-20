/**
 * Governos municipais na Economia (ADR-040): para um município, os mandatos de prefeito pelas eleições que o Lumen
 * publica, e o que a população (estimativas do IBGE) e as contas anuais (DCA do SICONFI) registraram em cada um.
 *
 * Tudo é lido sob demanda, no navegador, para o município escolhido:
 * - os resultados de prefeito, dos feeds da aba Eleições (`<eleição>/prefeito/mu-<código IBGE>.json`; o eleito do
 *   2º turno vem do arquivo do 2º turno);
 * - a população, do SIDRA (tabela 6579; o Censo 2022, tabela 4709, nos anos sem estimativa, 2022 e 2023);
 * - a despesa por função, da DCA (Anexo I-E, despesa liquidada), pelo endereço do próprio portal, que a Vercel
 *   repassa ao SICONFI (a API do Tesouro não aceita pedido de outro site);
 * - sob demanda, para o mandato aberto na tela, a despesa por natureza (Anexo I-D), que diz com o que foi gasto
 *   (pessoal, custeio, obras…). As aberturas e as somas estão em `lib/gastos.ts`.
 *
 * Os valores em reais são corrigidos pelo IPCA médio de cada ano, para reais do último ano com o IPCA completo.
 * Como na comparação de presidentes, os números mostram o que as fontes registraram; não dizem o que causou a
 * diferença entre um mandato e outro.
 */

import { carregarFeed, carregarIndice, obterJson } from "./feeds";
import type { Candidato, Feed, Indice } from "./tipos";
import type { Indicador } from "./economia";
import { ErroFeed } from "./validacao";
import { type Abertura, lerPorFuncao, lerPorNatureza } from "./gastos";

/** Endereço do portal que a Vercel repassa ao SICONFI (`vercel.json`). */
export const API_SICONFI = "/api/siconfi";
/** O primeiro exercício com DCA no SICONFI: o de 2013 vem vazio. */
export const PRIMEIRO_ANO_DCA = 2014;
/** A primeira eleição municipal mostrada: o mandato dela (2001–2004) é o primeiro com estimativa de população. */
export const PRIMEIRA_ELEICAO = 2000;
/** Quebras de método nas estimativas de população do IBGE (as mesmas da série do país). */
export const QUEBRAS_POPULACAO = ["2013", "2024"];

/** Um mandato de prefeito: período, quem foi eleito e em que turno. */
export interface Mandato {
  eleicao: number;
  de: number;
  ate: number;
  prefeito: string | null;
  partido: string | null;
  turno: 1 | 2 | null;
  /** Se o resultado da eleição está publicado no Lumen para o município. */
  publicado: boolean;
}

/** As despesas liquidadas de um ano, por grupo, em reais da época. */
export type Despesas = Partial<Record<IdFuncao, number>>;
/** Os grupos de despesa mostrados: o total e quatro funções. */
export type IdFuncao = "total" | "saude" | "educacao" | "assistencia" | "urbanismo";

/** As funções mostradas: a conta como a DCA (Anexo I-E) a escreve. */
export const FUNCOES: { id: IdFuncao; rotulo: string; conta: string }[] = [
  { id: "total", rotulo: "Despesa total", conta: "Despesas Exceto Intraorçamentárias" },
  { id: "saude", rotulo: "Saúde", conta: "10 - Saúde" },
  { id: "educacao", rotulo: "Educação", conta: "12 - Educação" },
  { id: "assistencia", rotulo: "Assistência social", conta: "08 - Assistência Social" },
  { id: "urbanismo", rotulo: "Urbanismo", conta: "15 - Urbanismo" },
];

// ------------------------------------------------------------------------------------------ mandatos

/** Os anos de eleição municipal com resultado de prefeito publicado para a UF, do mais antigo ao mais novo. */
export function anosMunicipais(indice: Indice | null, uf: string): number[] {
  const anos = new Set<number>();
  for (const e of indice?.eleicoes ?? []) {
    if (e.tipo !== "municipal" || e.turno !== 1 || e.municipios === false) continue;
    const prefeito = e.cargos.find((c) => c.slug === "prefeito");
    if (prefeito && (!prefeito.ufs || prefeito.ufs.includes(uf.toLowerCase()) || prefeito.ufs.includes(uf.toUpperCase()))) {
      anos.add(e.ano);
    }
  }
  return [...anos].sort((a, b) => a - b);
}

/**
 * As eleições municipais do calendário (a cada quatro anos, desde ``PRIMEIRA_ELEICAO``) já realizadas em ``hoje``:
 * a do ano corrente só entra depois de outubro, quando o resultado sai. Os mandatos vêm daqui, e não dos resultados
 * publicados: sem o resultado, o mandato aparece assim mesmo, com os números do período.
 */
export function eleicoesMunicipais(hoje: Date): number[] {
  const anos: number[] = [];
  for (let ano = PRIMEIRA_ELEICAO; ano < hoje.getFullYear() || (ano === hoje.getFullYear() && hoje.getMonth() >= 10);
       ano += 4) anos.push(ano);
  return anos;
}

/** Os candidatos do resultado, ou nenhum (panorama, ausente). */
function candidatos(feed: Feed | null): Candidato[] {
  return feed && feed.tipo === "resultado" ? feed.candidatos : [];
}

/** O candidato marcado como eleito no resultado, se houver um. */
export function eleitoNoFeed(feed: Feed | null): Candidato | null {
  return candidatos(feed).find((c) => c.eleito) ?? null;
}

/** Se o resultado do 1º turno levou a eleição ao 2º turno. */
export function foiAoSegundoTurno(feed: Feed | null): boolean {
  return candidatos(feed).some((c) => c.segundo_turno);
}

/** O mandato que a eleição de `ano` abriu: de 1º de janeiro do ano seguinte ao fim do quarto ano. */
export function mandatoDe(ano: number, eleito: Candidato | null, turno: 1 | 2 | null, publicado: boolean): Mandato {
  return { eleicao: ano, de: ano + 1, ate: ano + 4, prefeito: eleito?.nome_urna ?? null,
           partido: eleito?.partido ?? null, turno: eleito ? turno : null, publicado };
}

/** Quem governou: "Nome (PARTIDO)", ou por que não se sabe. */
export function quemGovernou(m: Mandato): string {
  if (m.prefeito) return m.partido ? `${m.prefeito} (${m.partido})` : m.prefeito;
  return m.publicado ? "eleito não identificado no resultado do TSE" : "resultado não publicado no Lumen";
}

/** Os mandatos do calendário, com o eleito pelos resultados de prefeito publicados no Lumen. */
export async function carregarMandatos(codigo: string, uf: string, sinal?: AbortSignal,
  hoje: Date = new Date()): Promise<Mandato[]> {
  const publicados = new Set(anosMunicipais(await carregarIndice(sinal).catch(() => null), uf));
  return Promise.all(eleicoesMunicipais(hoje).map(async (ano) => {
    if (!publicados.has(ano)) return mandatoDe(ano, null, null, false);
    const primeiro = await carregarFeed(`${ano}-1t-municipal`, "prefeito", `mu-${codigo}`, sinal, { guardar: true });
    let eleito = eleitoNoFeed(primeiro);
    let turno: 1 | 2 | null = eleito ? 1 : null;
    if (!eleito && foiAoSegundoTurno(primeiro)) {
      const segundo = await carregarFeed(`${ano}-2t-municipal`, "prefeito", `mu-${codigo}`, sinal, { guardar: true });
      eleito = eleitoNoFeed(segundo);
      turno = eleito ? 2 : null;
    }
    return mandatoDe(ano, eleito, turno, primeiro !== null);
  }));
}

// ------------------------------------------------------------------------------------------ população

/** Consulta do SIDRA: estimativa anual da população do município (tabela 6579, variável 9324). */
export const urlPopulacao = (codigo: string) =>
  `https://apisidra.ibge.gov.br/values/t/6579/n6/${codigo}/v/9324/p/all`;
/** Consulta do SIDRA: população residente do Censo 2022 (tabela 4709, variável 93). */
export const urlCenso2022 = (codigo: string) => `https://apisidra.ibge.gov.br/values/t/4709/n6/${codigo}/v/93/p/2022`;

/** `[ano, valor]` de uma consulta anual do SIDRA; a primeira linha é o cabeçalho e valor não numérico fica de fora. */
export function lerSidraAnual(bruto: unknown): [string, number][] {
  if (!Array.isArray(bruto)) throw new ErroFeed("resposta do SIDRA não é uma lista");
  const saida: [string, number][] = [];
  for (const linha of bruto.slice(1) as { D3C?: string; V?: string }[]) {
    const ano = String(linha.D3C ?? "");
    const valor = Number(linha.V);
    if (/^\d{4}$/.test(ano) && linha.V !== "" && Number.isFinite(valor)) saida.push([ano, valor]);
  }
  return saida;
}

/** A população de cada ano para a conta por habitante: a estimativa e, em 2022 e 2023, o Censo 2022. */
export function populacaoPorAno(estimativas: [string, number][], censo2022: number | null): Map<string, number> {
  const mapa = new Map(estimativas);
  if (censo2022 !== null) for (const ano of ["2022", "2023"]) if (!mapa.has(ano)) mapa.set(ano, censo2022);
  return mapa;
}

// ------------------------------------------------------------------------------------------ despesas

/** Consulta da DCA de um ano pelo endereço do portal (a Vercel repassa ao SICONFI): Anexo I-E (por função) ou I-D. */
export const urlDca = (codigo: string, ano: number, anexo: "I-E" | "I-D" = "I-E") =>
  `${API_SICONFI}/dca/?an_exercicio=${ano}&no_anexo=${encodeURIComponent(`DCA-Anexo ${anexo}`)}&id_ente=${codigo}`;

/** A mesma consulta direto no SICONFI, para o link da fonte. */
export const urlDcaNaFonte = (codigo: string, ano: number, anexo: "I-E" | "I-D" = "I-E") =>
  `https://apidatalake.tesouro.gov.br/ords/siconfi/tt${urlDca(codigo, ano, anexo).slice(API_SICONFI.length)}`
    .replace("/dca/?", "/dca?");

/** As despesas das funções de `FUNCOES` tiradas da abertura por área do ano. */
export function despesasDe(contas: Abertura): Despesas {
  const saida: Despesas = { total: contas.total };
  for (const f of FUNCOES) {
    const codigo = /^(\d{2}) - /.exec(f.conta)?.[1];
    if (codigo && contas.valores[codigo] !== undefined) saida[f.id] = contas.valores[codigo];
  }
  return saida;
}

/** As despesas liquidadas das funções de `FUNCOES` numa resposta da DCA; `null` se o ano não foi entregue. */
export function lerDca(bruto: unknown): Despesas | null {
  const contas = lerPorFuncao(bruto);
  return contas ? despesasDe(contas) : null;
}

/** Esperas antes de cada nova tentativa de consulta ao SICONFI, em milissegundos. */
export const ESPERAS_SICONFI = [1000, 3000];

/**
 * Consulta ao SICONFI pelo portal com novas tentativas: a API do Tesouro recusa pedidos demais ao mesmo tempo, e a
 * página faz perto de 20 de uma vez. Só a falha da consulta se repete; o cancelamento, não.
 */
export async function obterDoSiconfi(url: string, sinal?: AbortSignal, esperas = ESPERAS_SICONFI): Promise<unknown> {
  for (let tentativa = 0; ; tentativa++) {
    try {
      return await obterJson(url, { sinal, cache: "force-cache" });
    } catch (erro) {
      if ((erro as Error).name === "AbortError" || tentativa >= esperas.length) throw erro;
      await new Promise((ok) => setTimeout(ok, esperas[tentativa]));
      if (sinal?.aborted) throw new DOMException("cancelada", "AbortError");
    }
  }
}

/** A despesa por natureza de um ano (Anexo I-D), pelo endereço do portal; `null` se o ano não foi entregue. */
export function carregarNatureza(codigo: string, ano: number, sinal?: AbortSignal): Promise<Abertura | null> {
  return obterDoSiconfi(urlDca(codigo, ano, "I-D"), sinal).then(lerPorNatureza);
}

// ------------------------------------------------------------------------------------------ inflação

/**
 * O IPCA médio de cada ano, como número-índice (o primeiro mês da série vale 1), a partir da série mensal da
 * Economia. Só entram os anos com os 12 meses.
 */
export function ipcaMedioAnual(ipca: Pick<Indicador, "serie">): Map<string, number> {
  const porAno = new Map<string, number[]>();
  let indice = 1;
  for (const [mes, taxa] of [...ipca.serie].sort(([a], [b]) => a.localeCompare(b))) {
    indice *= 1 + taxa / 100;
    const ano = mes.slice(0, 4);
    porAno.set(ano, [...(porAno.get(ano) ?? []), indice]);
  }
  const saida = new Map<string, number>();
  for (const [ano, valores] of porAno) {
    if (valores.length === 12) saida.set(ano, valores.reduce((s, v) => s + v, 0) / 12);
  }
  return saida;
}

/** O ano-base da correção: o último com o IPCA completo. */
export function anoBase(medias: Map<string, number>): string | null {
  return [...medias.keys()].sort().at(-1) ?? null;
}

/** `valor` do `ano` em reais do `base`, pelo IPCA médio; `null` sem IPCA de um dos dois anos. */
export function emReaisDe(valor: number, ano: string, base: string, medias: Map<string, number>): number | null {
  const de = medias.get(ano);
  const para = medias.get(base);
  return de && para ? valor * (para / de) : null;
}

// ------------------------------------------------------------------------------------------ mandato a mandato

/** Um ano do município: população usada, despesas da época e corrigidas, e por habitante. */
export interface AnoMunicipal {
  ano: string;
  populacao: number | null;
  despesas: Despesas | null;
  reais: Despesas;
  porHabitante: Despesas;
}

/** O resumo de um mandato: a população no começo e no fim e a média anual de cada despesa, corrigida. */
export interface ResumoMandato {
  mandato: Mandato;
  populacaoInicio: [string, number] | null;
  populacaoFim: [string, number] | null;
  variacaoPopulacao: number | null;
  quebraPopulacao: string | null;
  anosComContas: number;
  mediaReal: Despesas;
  mediaPorHabitante: Despesas;
}

/** Os anos do município, com a despesa corrigida para reais do `base` e dividida pela população do ano. */
export function anosMunicipaisComDespesa(anos: string[], populacao: Map<string, number>,
  despesas: Map<string, Despesas | null>, medias: Map<string, number>, base: string | null): AnoMunicipal[] {
  return anos.map((ano) => {
    const d = despesas.get(ano) ?? null;
    const pop = populacao.get(ano) ?? null;
    const reais: Despesas = {};
    const porHabitante: Despesas = {};
    for (const f of FUNCOES) {
      const v = d?.[f.id];
      if (v === undefined || base === null) continue;
      const real = emReaisDe(v, ano, base, medias);
      if (real === null) continue;
      reais[f.id] = real;
      if (pop) porHabitante[f.id] = real / pop;
    }
    return { ano, populacao: pop, despesas: d, reais, porHabitante };
  });
}

/** A média das despesas dos anos com contas, por função. */
function media(anos: AnoMunicipal[], chave: "reais" | "porHabitante"): Despesas {
  const saida: Despesas = {};
  for (const f of FUNCOES) {
    const valores = anos.map((a) => a[chave][f.id]).filter((v): v is number => v !== undefined);
    if (valores.length) saida[f.id] = valores.reduce((s, v) => s + v, 0) / valores.length;
  }
  return saida;
}

/**
 * O resumo de cada mandato. A população de início é a do primeiro ano do mandato com estimativa (ou a última antes
 * dele) e a de fim, a do último ano com estimativa no mandato; entre uma quebra de método e outra, a variação fica
 * sem cálculo, como na comparação de presidentes.
 */
export function resumirMandatos(mandatos: Mandato[], estimativas: [string, number][],
  anos: AnoMunicipal[]): ResumoMandato[] {
  return mandatos.map((m) => {
    const dentro = estimativas.filter(([a]) => Number(a) >= m.de && Number(a) <= m.ate);
    const antes = estimativas.filter(([a]) => Number(a) < m.de);
    const inicio = dentro[0] ?? antes.at(-1) ?? null;
    const fim = dentro.at(-1) ?? null;
    const quebra = inicio && fim ? QUEBRAS_POPULACAO.find((q) => inicio[0] < q && q <= fim[0]) ?? null : null;
    const variacao = inicio && fim && inicio[0] !== fim[0] && !quebra ? (fim[1] / inicio[1] - 1) * 100 : null;
    const doMandato = anos.filter((a) => Number(a.ano) >= m.de && Number(a.ano) <= m.ate && a.despesas);
    return { mandato: m, populacaoInicio: inicio, populacaoFim: fim, variacaoPopulacao: variacao,
             quebraPopulacao: quebra, anosComContas: doMandato.length, mediaReal: media(doMandato, "reais"),
             mediaPorHabitante: media(doMandato, "porHabitante") };
  });
}

// ------------------------------------------------------------------------------------------ leitura

/** Tudo o que a página precisa de um município, lido das três fontes. */
export interface DadosMunicipio {
  mandatos: Mandato[];
  estimativas: [string, number][];
  censo2022: number | null;
  despesas: Map<string, Despesas | null>;
  /** A abertura por área de cada ano (Anexo I-E), de onde saem as `despesas`. */
  contas: Map<string, Abertura | null>;
  falhas: string[];
}

/** Lê os mandatos, a população e as contas anuais de 2014 até `ultimoAno`; falha de uma fonte vai em `falhas`. */
export async function carregarMunicipio(codigo: string, uf: string, ultimoAno: number,
  sinal?: AbortSignal): Promise<DadosMunicipio> {
  const falhas: string[] = [];
  const guardar = <T>(nome: string, p: Promise<T>, padrao: T): Promise<T> =>
    p.catch((e: Error) => {
      if (e.name === "AbortError") throw e;
      falhas.push(nome);
      return padrao;
    });
  const anos = Array.from({ length: Math.max(0, ultimoAno - PRIMEIRO_ANO_DCA + 1) }, (_, i) => PRIMEIRO_ANO_DCA + i);
  const [mandatos, estimativas, censo, contas] = await Promise.all([
    guardar("resultados das eleições", carregarMandatos(codigo, uf, sinal), [] as Mandato[]),
    guardar("estimativas de população do IBGE",
            obterJson(urlPopulacao(codigo), { sinal, cache: "force-cache" }).then(lerSidraAnual), []),
    guardar("Censo 2022", obterJson(urlCenso2022(codigo), { sinal, cache: "force-cache" })
      .then((b) => lerSidraAnual(b)[0]?.[1] ?? null), null),
    Promise.all(anos.map((ano) => guardar(`contas anuais de ${ano}`,
      obterDoSiconfi(urlDca(codigo, ano), sinal).then(lerPorFuncao), null)
      .then((d) => [String(ano), d] as const))),
  ]);
  return { mandatos, estimativas, censo2022: censo, contas: new Map(contas),
           despesas: new Map(contas.map(([ano, c]) => [ano, c ? despesasDe(c) : null])), falhas };
}
