/**
 * Parlamentares (ADR-060): os deputados federais pelos arquivos de dados abertos da Câmara, publicados com os
 * painéis em `parlamentares/camara/`. O índice lista todos, com os totais; cada deputado tem o próprio arquivo, com os
 * votos nominais do Plenário, a presença nas sessões deliberativas, as proposições que apresentou e a cota
 * parlamentar, por ano; as votações (data, proposição, resultado e orientação do Governo) ficam num arquivo por ano.
 */

import { normalizar } from "./busca";
import { obterJsonComprimido } from "./comprimido";
import { obterJson } from "./feeds";
import { BASE_PAINEL, conferir } from "./paineis";

/** Uma linha do índice: `[id, nome, partido, uf, legislaturas, votos, proposições, presenças, sessões, cota]`. */
export type LinhaDeputado = [string, string, string, string, number[], number, number, number, number, number];

/** Arquivo `parlamentares/camara/indice.json`. */
export interface IndiceCamara {
  versao: 1;
  tipo: "camara-indice";
  gerado_em: string;
  fonte: string | null;
  coletado_em: string | null;
  anos: string[];
  deputados: LinhaDeputado[];
}

/** Uma proposição apresentada: `[id, tipo, número, ano, ementa, apresentação, situação]`. */
export type Proposicao = [string, string, string, string, string, string, string | null];
/** Um fornecedor da cota: `[CNPJ, nome, documentos, valor]`. */
export type FornecedorCota = [string, string | null, number, number];

/** A cota parlamentar (CEAP) de um ano. */
export interface Cota {
  categorias: Record<string, number>;
  meses: Record<string, number>;
  fornecedores: FornecedorCota[];
  /** Fornecedores pessoa física, só somados: `[documentos, valor]`. */
  pf: [number, number];
}

/** Um ano do deputado. */
export interface AnoDeputado {
  /** Voto em cada votação nominal do Plenário: S, N, A (abstenção), O (obstrução), 17 (presidente) ou "-". */
  votos: Record<string, string>;
  /** `[sessões deliberativas a que foi, sessões realizadas enquanto estava em exercício]`. */
  presenca: [number, number];
  autoria: Proposicao[];
  /** Todas as proposições que apresentou, por tipo (inclusive requerimentos e emendas). */
  contagem: Record<string, number>;
  ceap?: Cota;
}

/** Arquivo `parlamentares/camara/<id>.json.gz`. */
export interface Deputado {
  versao: 1;
  tipo: "camara-deputado";
  gerado_em: string;
  id: string;
  nome: string;
  partido: string;
  uf: string;
  legislaturas: number[];
  /** Períodos em exercício: `[início, fim ou null]`. */
  exercicio: [string, string | null][];
  anos: Record<string, AnoDeputado>;
}

/** Uma votação: `[data, proposição, ementa, descrição, aprovação (1, 0 ou null), sim, não, outros, orientação do Governo]`. */
export type Votacao = [string, string, string, string, number | null, number, number, number, string | null];

/** Arquivo `parlamentares/camara/votacoes-<ano>.json.gz`. */
interface VotacoesAno {
  versao: 1;
  tipo: "camara-votacoes";
  ano: string;
  votacoes: Record<string, Votacao>;
}

const BASE = `${BASE_PAINEL}/parlamentares/camara`;

/** O índice dos deputados; `null` quando ainda não foi publicado. */
export async function carregarIndiceCamara(sinal?: AbortSignal): Promise<IndiceCamara | null> {
  const url = `${BASE}/indice.json`;
  const bruto = await obterJson(url, { sinal });
  return bruto === null ? null : conferir<IndiceCamara>(bruto, "camara-indice", url);
}

/** O arquivo de um deputado; `null` quando ele não está no Lumen. */
export async function carregarDeputado(id: string, sinal?: AbortSignal): Promise<Deputado | null> {
  if (!/^\d+$/.test(id)) return null;
  const url = `${BASE}/${id}.json.gz`;
  const bruto = await obterJsonComprimido(url, sinal);
  return bruto === null ? null : conferir<Deputado>(bruto, "camara-deputado", url);
}

/** As votações nominais do Plenário num ano (vazio quando o arquivo não existe). */
export async function carregarVotacoes(ano: string, sinal?: AbortSignal): Promise<Record<string, Votacao>> {
  const url = `${BASE}/votacoes-${ano}.json.gz`;
  const bruto = await obterJsonComprimido(url, sinal);
  return bruto === null ? {} : conferir<VotacoesAno>(bruto, "camara-votacoes", url).votacoes;
}

/** A foto oficial do deputado no site da Câmara. */
export const fotoDoDeputado = (id: string) => `https://www.camara.leg.br/internet/deputado/bandep/${id}.jpg`;
/** A página do deputado no site da Câmara. */
export const paginaNaCamara = (id: string) => `https://www.camara.leg.br/deputados/${id}`;
/** A página da proposição no site da Câmara. */
export const proposicaoNaCamara = (id: string) =>
  `https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao=${id}`;

/** O voto por extenso. */
export function votoPorExtenso(v: string): string {
  return { S: "Sim", N: "Não", A: "Abstenção", O: "Obstrução", "17": "Presidiu (art. 17)", "-": "Sem voto" }[v] ?? v;
}

/** Os deputados que casam com a busca pelo nome (começo das palavras) e com a UF e o partido escolhidos. */
export function filtrarDeputados(linhas: LinhaDeputado[], filtro: { termo?: string; uf?: string | null; partido?: string | null }) {
  const palavras = normalizar(filtro.termo ?? "").split(" ").filter(Boolean);
  return linhas.filter(([, nome, partido, uf]) => {
    if (filtro.uf && uf !== filtro.uf) return false;
    if (filtro.partido && partido !== filtro.partido) return false;
    const doNome = normalizar(nome).split(" ");
    return palavras.every((p) => doNome.some((n) => n.startsWith(p)));
  });
}

/** Os anos do deputado escolhidos: um ano, ou todos quando `ano` é null. */
function anosEscolhidos(d: Deputado, ano: string | null): AnoDeputado[] {
  return ano ? (d.anos[ano] ? [d.anos[ano]] : []) : Object.values(d.anos);
}

/** Os totais do deputado nos anos escolhidos. */
export function totaisDoDeputado(d: Deputado, ano: string | null) {
  const anos = anosEscolhidos(d, ano);
  const votos = anos.flatMap((a) => Object.values(a.votos));
  const contagem: Record<string, number> = {};
  for (const a of anos) for (const [tipo, n] of Object.entries(a.contagem)) contagem[tipo] = (contagem[tipo] ?? 0) + n;
  return {
    votos: votos.filter((v) => v !== "-").length,
    sim: votos.filter((v) => v === "S").length,
    nao: votos.filter((v) => v === "N").length,
    presentes: anos.reduce((s, a) => s + a.presenca[0], 0),
    sessoes: anos.reduce((s, a) => s + a.presenca[1], 0),
    proposicoes: anos.reduce((s, a) => s + a.autoria.length, 0),
    contagem,
    cota: anos.reduce((s, a) => s + Object.values(a.ceap?.categorias ?? {}).reduce((x, y) => x + y, 0), 0),
  };
}

/** A cota somada nos anos escolhidos: por categoria e por fornecedor (do maior valor ao menor), e a pessoa física. */
export function cotaDoDeputado(d: Deputado, ano: string | null) {
  const categorias = new Map<string, number>();
  const fornecedores = new Map<string, FornecedorCota>();
  const pf: [number, number] = [0, 0];
  for (const a of anosEscolhidos(d, ano)) {
    if (!a.ceap) continue;
    for (const [c, v] of Object.entries(a.ceap.categorias)) categorias.set(c, (categorias.get(c) ?? 0) + v);
    for (const [cnpj, nome, n, v] of a.ceap.fornecedores) {
      const f = fornecedores.get(cnpj) ?? [cnpj, nome, 0, 0];
      f[2] += n;
      f[3] += v;
      if (nome) f[1] = nome;
      fornecedores.set(cnpj, f);
    }
    pf[0] += a.ceap.pf[0];
    pf[1] += a.ceap.pf[1];
  }
  return {
    categorias: [...categorias.entries()].sort((a, b) => b[1] - a[1]),
    fornecedores: [...fornecedores.values()].sort((a, b) => b[3] - a[3] || a[0].localeCompare(b[0])),
    pf,
  };
}

/** A cota por mês de um ano, de janeiro a dezembro (os meses sem despesa ficam fora). */
export function cotaPorMes(d: Deputado, ano: string): { mes: string; valor: number }[] {
  return Object.entries(d.anos[ano]?.ceap?.meses ?? {}).map(([mes, valor]) => ({ mes, valor }))
    .sort((a, b) => a.mes.localeCompare(b.mes));
}

/** Um voto com a votação: o que a tabela mostra. */
export interface VotoComVotacao {
  id: string;
  ano: string;
  voto: string;
  votacao: Votacao | null;
  /** O voto foi igual ao que o Governo orientou (null quando não houve orientação Sim ou Não, ou não houve voto). */
  comOGoverno: boolean | null;
}

/** Os votos do deputado nos anos escolhidos, com as votações, do mais recente ao mais antigo. */
export function votosComVotacoes(d: Deputado, ano: string | null, votacoes: Record<string, Record<string, Votacao>>): VotoComVotacao[] {
  const saida: VotoComVotacao[] = [];
  for (const [a, dados] of Object.entries(d.anos)) {
    if (ano && a !== ano) continue;
    for (const [id, voto] of Object.entries(dados.votos)) {
      const v = votacoes[a]?.[id] ?? null;
      const orientacao = v?.[8] === "Sim" ? "S" : v?.[8] === "Não" ? "N" : null;
      saida.push({ id, ano: a, voto, votacao: v, comOGoverno: orientacao && (voto === "S" || voto === "N") ? voto === orientacao : null });
    }
  }
  return saida.sort((x, y) => (y.votacao?.[0] ?? "").localeCompare(x.votacao?.[0] ?? "") || y.id.localeCompare(x.id));
}
