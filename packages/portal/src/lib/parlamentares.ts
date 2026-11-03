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

/** Os números de um ano ou período: `[votos, proposições, presenças, sessões, cota]`. */
export type Numeros = [number, number, number, number, number];

/**
 * Uma linha do índice: `[id, nome, partido, uf, legislaturas, votos, proposições, presenças, sessões, cota, por ano]`;
 * `por ano` falta nos índices publicados antes do filtro de período.
 */
export type LinhaDeputado = [string, string, string, string, number[], number, number, number, number, number,
  Record<string, Numeros>?];

/** Arquivo `parlamentares/camara/indice.json`. */
export interface IndiceCamara {
  versao: 1;
  tipo: `${Casa}-indice`;
  gerado_em: string;
  fonte: string | null;
  coletado_em: string | null;
  anos: string[];
  /** O primeiro e o último ano de cada legislatura (`{"57": [2023, 2026]}`). */
  legislaturas?: Record<string, [number, number]>;
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
  tipo: `${Casa}-${"deputado" | "senador"}`;
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

/**
 * Uma votação: `[data, proposição, ementa, descrição, aprovação (1, 0 ou null), sim, não, outros, orientação do
 * Governo, id da proposição]`; o id falta nos arquivos publicados antes da página da votação.
 */
export type Votacao = [string, string, string, string, number | null, number, number, number, string | null, (string | null)?];

/** O voto de um deputado numa votação: `[id do deputado, voto, partido no dia do voto]`. */
export type VotoNaVotacao = [string, string, string];

/** Arquivo `parlamentares/camara/votos-<ano>.json.gz`: quem votou em cada votação nominal do ano. */
interface VotosAno {
  versao: 1;
  tipo: `${Casa}-votos`;
  ano: string;
  votos: Record<string, VotoNaVotacao[]>;
}

/** Arquivo `parlamentares/camara/votacoes-<ano>.json.gz`. */
interface VotacoesAno {
  versao: 1;
  tipo: `${Casa}-votacoes`;
  ano: string;
  votacoes: Record<string, Votacao>;
}

/** A casa legislativa: a Câmara dos Deputados ou o Senado Federal. */
export type Casa = "camara" | "senado";

/** A pasta da casa no site dos painéis. */
const base = (casa: Casa) => `${BASE_PAINEL}/parlamentares/${casa}`;

/** O nome da casa e de quem tem mandato nela, para os textos das páginas. */
export const CASAS: Record<Casa, { nome: string; pessoa: string; pessoas: string; rota: string }> = {
  camara: { nome: "Câmara dos Deputados", pessoa: "Deputado(a) federal", pessoas: "Deputados federais", rota: "deputado" },
  senado: { nome: "Senado Federal", pessoa: "Senador(a)", pessoas: "Senadores", rota: "senador" },
};

/** A casa pelo parâmetro da URL (`?casa=senado`); qualquer outro valor é a Câmara. */
export const casaDaUrl = (valor: string | null): Casa => (valor === "senado" ? "senado" : "camara");

/** O índice dos parlamentares da casa; `null` quando ainda não foi publicado. */
export async function carregarIndiceCamara(sinal?: AbortSignal, casa: Casa = "camara"): Promise<IndiceCamara | null> {
  const url = `${base(casa)}/indice.json`;
  const bruto = await obterJson(url, { sinal });
  return bruto === null ? null : conferir<IndiceCamara>(bruto, `${casa}-indice`, url);
}

/** O arquivo de um deputado; `null` quando ele não está no Lumen. */
export async function carregarDeputado(id: string, sinal?: AbortSignal, casa: Casa = "camara"): Promise<Deputado | null> {
  if (!/^\d+$/.test(id)) return null;
  const url = `${base(casa)}/${id}.json.gz`;
  const bruto = await obterJsonComprimido(url, sinal);
  return bruto === null ? null : conferir<Deputado>(bruto, `${casa}-${casa === "senado" ? "senador" : "deputado"}`, url);
}

/** As votações nominais do Plenário num ano (vazio quando o arquivo não existe). */
export async function carregarVotacoes(ano: string, sinal?: AbortSignal, casa: Casa = "camara"): Promise<Record<string, Votacao>> {
  const url = `${base(casa)}/votacoes-${ano}.json.gz`;
  const bruto = await obterJsonComprimido(url, sinal);
  return bruto === null ? {} : conferir<VotacoesAno>(bruto, `${casa}-votacoes`, url).votacoes;
}

/** Os votos de cada votação nominal do ano (vazio quando o arquivo não existe). */
export async function carregarVotosDoAno(ano: string, sinal?: AbortSignal, casa: Casa = "camara"): Promise<Record<string, VotoNaVotacao[]>> {
  const url = `${base(casa)}/votos-${ano}.json.gz`;
  const bruto = await obterJsonComprimido(url, sinal);
  return bruto === null ? {} : conferir<VotosAno>(bruto, `${casa}-votos`, url).votos;
}

/** O placar de um partido numa votação. */
export interface PlacarPartido {
  partido: string;
  sim: number;
  nao: number;
  abstencao: number;
  obstrucao: number;
  outros: number;
  total: number;
}

/** O placar de cada partido numa votação, do partido com mais votos ao com menos. */
export function placarPorPartido(votos: VotoNaVotacao[]): PlacarPartido[] {
  const m = new Map<string, PlacarPartido>();
  for (const [, voto, partido] of votos) {
    const p = m.get(partido) ?? { partido, sim: 0, nao: 0, abstencao: 0, obstrucao: 0, outros: 0, total: 0 };
    if (voto === "S") p.sim++;
    else if (voto === "N") p.nao++;
    else if (voto === "A") p.abstencao++;
    else if (voto === "O") p.obstrucao++;
    else p.outros++;
    p.total++;
    m.set(partido, p);
  }
  return [...m.values()].sort((a, b) => b.total - a.total || a.partido.localeCompare(b.partido));
}

/** O tipo da proposição pelo título ("PEC 45/2019" → "PEC"); sem título, "Outras". */
export function tipoDaProposicao(titulo: string): string {
  return /^([A-Z]{2,5})\b/.exec(titulo.trim())?.[1] ?? "Outras";
}

/** A página da votação no Lumen. */
export const urlDaVotacao = (ano: string, id: string, casa: Casa = "camara") =>
  `/parlamentares/votacoes/?${casa === "senado" ? "casa=senado&" : ""}ano=${ano}&id=${encodeURIComponent(id)}`;

/** A página do parlamentar no Lumen. */
export const urlDoParlamentar = (id: string, casa: Casa = "camara", ano?: string | null) =>
  `/parlamentares/${CASAS[casa].rota}/?id=${id}${ano ? `&ano=${ano}` : ""}`;

/** A foto oficial do parlamentar no site da casa. */
export const fotoDoDeputado = (id: string, casa: Casa = "camara") => casa === "senado"
  ? `https://www.senado.leg.br/senadores/img/fotos-oficiais/senador${id}.jpg`
  : `https://www.camara.leg.br/internet/deputado/bandep/${id}.jpg`;
/** A página do parlamentar no site da casa. */
export const paginaNaCamara = (id: string, casa: Casa = "camara") => casa === "senado"
  ? `https://www25.senado.leg.br/web/senadores/senador/-/perfil/${id}`
  : `https://www.camara.leg.br/deputados/${id}`;
/** A página da proposição (ou matéria, no Senado) no site da casa. */
export const proposicaoNaCamara = (id: string, casa: Casa = "camara") => casa === "senado"
  ? `https://www25.senado.leg.br/web/atividade/materias/-/materia/${id}`
  : `https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao=${id}`;

/** Os votos de fato: sim, não, abstenção, obstrução e o do presidente da sessão na Câmara (art. 17). */
const VOTOS_DE_FATO = new Set(["S", "N", "A", "O", "17"]);

/** O voto por extenso. */
export function votoPorExtenso(v: string): string {
  return { S: "Sim", N: "Não", A: "Abstenção", O: "Obstrução", "17": "Presidiu (art. 17)", "-": "Sem voto",
           "P-NRV": "Presente, não votou", AP: "Ausente (art. 13)", LS: "Licença saúde", LP: "Licença particular",
           MIS: "Em missão", NCom: "Não compareceu", PR: "Presidiu a sessão (art. 51)", NA: "Não votou" }[v] ?? v;
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

/** Os números do deputado nos anos pedidos (todos quando `anos` é null), somados. */
export function numerosNoPeriodo(linha: LinhaDeputado, anos: string[] | null): Numeros {
  const porAno = linha[10];
  if (!anos || !porAno) return [linha[5], linha[6], linha[7], linha[8], linha[9]];
  const soma: Numeros = [0, 0, 0, 0, 0];
  for (const ano of anos) porAno[ano]?.forEach((v, i) => (soma[i] = (soma[i] ?? 0) + v));
  return soma;
}

/** Se o deputado tem algo nos anos pedidos: voto, proposição, sessão em exercício ou cota. */
export function apareceNoPeriodo(linha: LinhaDeputado, anos: string[] | null): boolean {
  return !anos || !linha[10] || anos.some((a) => linha[10]?.[a] !== undefined);
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
    votos: votos.filter((v) => VOTOS_DE_FATO.has(v)).length,
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
