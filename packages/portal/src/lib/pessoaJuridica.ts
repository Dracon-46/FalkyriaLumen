/**
 * Visão 360 de uma pessoa jurídica pelo CNPJ (ADR-049): o arquivo `pj/<grupo>.json.gz` traz os contratos no PNCP
 * por ente contratante e ano, as emendas parlamentares recebidas e os convênios com a União. A página junta o
 * cartão da Receita (`receita.ts`). A busca pelo nome lê `pj/busca/`, um arquivo por prefixo de palavra.
 */

import { normalizar } from "./busca";
import { obterJsonComprimido } from "./comprimido";
import { obterJson } from "./feeds";
import { BASE_PAINEL, conferir, grupoDoCnpj } from "./paineis";

/** Contratos no PNCP com o ente contratante num ano: `[ente, ano, contratos, valor]`. */
export type LinhaContratos = [string, string, number, number];
/** Emendas recebidas de um ente num ano: `[ente, ano, valor]`. */
export type LinhaEmendas = [string, string, number];
/** Contratos registrados no tribunal de contas com o ente num ano do contrato: `[ente, ano, contratos, valor]`. */
export type LinhaTce = [string, string, number, number];
/** Um convênio: `[ente, número, situação, objeto, órgão, valor, liberado, início]`. */
export type LinhaConvenio = [string, string, string, string, string, number, number, string | null];

/** O que o Lumen tem do CNPJ. */
export interface PessoaJuridica {
  cnpj: string;
  nome: string | null;
  contratos: LinhaContratos[];
  emendas: LinhaEmendas[];
  convenios: LinhaConvenio[];
  /** Contratos no tribunal de contas (ADR-050); ausente nos arquivos publicados antes dele. */
  tce?: LinhaTce[];
  /** Data do arquivo da CGU de onde vieram as emendas e os convênios (`AAAAMMDD`) e a da coleta do tribunal. */
  fontes: { emendas: string | null; convenios: string | null; tce?: string | null };
  gerado_em: string;
}

/** Arquivo `pj/<grupo>.json.gz`: as pessoas jurídicas do grupo (`grupoDoCnpj`). */
interface GrupoPessoasJuridicas {
  versao: 1;
  tipo: "pessoas-juridicas";
  gerado_em: string;
  fontes: PessoaJuridica["fontes"];
  pessoas: Record<string, Pick<PessoaJuridica, "nome" | "contratos" | "emendas" | "convenios" | "tce">>;
}

/** O CNPJ no índice; `null` quando ele não aparece em nenhuma fonte ou o arquivo não foi publicado. */
export async function carregarPessoaJuridica(cnpj: string, sinal?: AbortSignal): Promise<PessoaJuridica | null> {
  const url = `${BASE_PAINEL}/pj/${grupoDoCnpj(cnpj)}.json.gz`;
  const bruto = await obterJsonComprimido(url, sinal);
  if (bruto === null) return null;
  const grupo = conferir<GrupoPessoasJuridicas>(bruto, "pessoas-juridicas", url);
  const p = grupo.pessoas?.[cnpj];
  return p ? { cnpj, ...p, fontes: grupo.fontes, gerado_em: grupo.gerado_em } : null;
}

/** Uma soma por ente: contratos (ou zero, nas emendas), valor e os anos em que aparece. */
export interface PorEnte {
  ente: string;
  contratos: number;
  valor: number;
  anos: string[];
}

/** Soma linhas `[ente, ano, …, valor]` por ente, do maior valor ao menor. */
function somarPorEnte(linhas: { ente: string; ano: string; contratos: number; valor: number }[]): PorEnte[] {
  const m = new Map<string, PorEnte>();
  for (const l of linhas) {
    let x = m.get(l.ente);
    if (!x) m.set(l.ente, (x = { ente: l.ente, contratos: 0, valor: 0, anos: [] }));
    x.contratos += l.contratos;
    x.valor += l.valor;
    if (!x.anos.includes(l.ano)) x.anos.push(l.ano);
  }
  for (const x of m.values()) x.anos.sort();
  return [...m.values()].sort((a, b) => b.valor - a.valor || b.contratos - a.contratos || a.ente.localeCompare(b.ente));
}

/** Os contratos por ente contratante. */
export function contratosPorEnte(p: PessoaJuridica): PorEnte[] {
  return somarPorEnte(p.contratos.map(([ente, ano, contratos, valor]) => ({ ente, ano, contratos, valor })));
}

/** Os contratos registrados no tribunal de contas, por ente. */
export function tcePorEnte(p: PessoaJuridica): PorEnte[] {
  return somarPorEnte((p.tce ?? []).map(([ente, ano, contratos, valor]) => ({ ente, ano, contratos, valor })));
}

/** As emendas recebidas por ente. */
export function emendasPorEnte(p: PessoaJuridica): PorEnte[] {
  return somarPorEnte(p.emendas.map(([ente, ano, valor]) => ({ ente, ano, contratos: 0, valor })));
}

/** Contratos e valor por ano, em ordem. */
export function contratosPorAno(p: PessoaJuridica): { ano: string; contratos: number; valor: number }[] {
  const m = new Map<string, { ano: string; contratos: number; valor: number }>();
  for (const [, ano, contratos, valor] of p.contratos) {
    const x = m.get(ano) ?? { ano, contratos: 0, valor: 0 };
    x.contratos += contratos;
    x.valor += valor;
    m.set(ano, x);
  }
  return [...m.values()].sort((a, b) => a.ano.localeCompare(b.ano));
}

/** Os totais do topo da página. */
export function totaisDaPessoa(p: PessoaJuridica) {
  return {
    contratos: p.contratos.reduce((s, l) => s + l[2], 0),
    valorContratos: p.contratos.reduce((s, l) => s + l[3], 0),
    entesContratantes: new Set(p.contratos.map((l) => l[0])).size,
    emendas: p.emendas.reduce((s, l) => s + l[2], 0),
    convenios: p.convenios.length,
    valorConvenios: p.convenios.reduce((s, l) => s + l[5], 0),
    liberado: p.convenios.reduce((s, l) => s + l[6], 0),
    contratosTce: (p.tce ?? []).reduce((s, l) => s + l[2], 0),
    valorTce: (p.tce ?? []).reduce((s, l) => s + l[3], 0),
  };
}

// ------------------------------------------------------------------------------------------ busca pelo nome

/** Palavras comuns demais para separar uma empresa da outra, como `PALAVRAS_FORA` no Python. */
const PALAVRAS_FORA = new Set(["ltda", "eireli", "epp", "cia", "dos", "das", "del", "para", "com"]);

/** Um nome achado: o CNPJ, o nome e o peso (contratos, emendas e convênios somados). */
export interface AchadoPj {
  cnpj: string;
  nome: string | null;
  peso: number;
}

/** `pj/busca/indice.json`: os prefixos de duas letras divididos em três e quantos nomes tem cada arquivo. */
interface IndiceBusca {
  versao: 1;
  tipo: "pj-busca-indice";
  divididos: string[];
  arquivos: Record<string, number>;
}

/** As palavras que a busca usa: três letras ou mais, normalizadas, fora as comuns demais. */
export function palavrasDaBusca(texto: string): string[] {
  return normalizar(texto).split(" ").filter((p) => p.length >= 3 && !PALAVRAS_FORA.has(p));
}

/** O arquivo de uma palavra: as duas primeiras letras, ou as três quando o de duas foi dividido. */
export function prefixoDaPalavra(palavra: string, divididos: readonly string[]): string {
  return divididos.includes(palavra.slice(0, 2)) ? palavra.slice(0, 3) : palavra.slice(0, 2);
}

/** Se cada palavra procurada começa alguma palavra do nome. */
export function casaComONome(nome: string | null, procuradas: string[]): boolean {
  const doNome = palavrasDaBusca(nome ?? "");
  return procuradas.every((p) => doNome.some((n) => n.startsWith(p)));
}

let indiceBusca: Promise<IndiceBusca | null> | null = null;
const arquivosBusca = new Map<string, Promise<[string, string | null, number][]>>();

/** O índice da busca, lido uma vez por visita; `null` quando ainda não foi publicado. */
function lerIndiceBusca(): Promise<IndiceBusca | null> {
  if (!indiceBusca) {
    const url = `${BASE_PAINEL}/pj/busca/indice.json`;
    indiceBusca = obterJson(url).then((b) => (b === null ? null : conferir<IndiceBusca>(b, "pj-busca-indice", url)));
    indiceBusca.catch(() => (indiceBusca = null));
  }
  return indiceBusca;
}

/** Os nomes de um prefixo (`[CNPJ, nome, peso]`), lidos uma vez por visita; lista vazia sem o arquivo. */
function lerArquivoBusca(prefixo: string): Promise<[string, string | null, number][]> {
  let arquivo = arquivosBusca.get(prefixo);
  if (!arquivo) {
    const url = `${BASE_PAINEL}/pj/busca/${prefixo}.json.gz`;
    arquivo = obterJsonComprimido(url).then((b) =>
      b === null ? [] : conferir<{ pessoas: [string, string | null, number][] }>(b, "pj-busca", url).pessoas);
    arquivo.catch(() => arquivosBusca.delete(prefixo));
    arquivosBusca.set(prefixo, arquivo);
  }
  return arquivo;
}

/**
 * Os nomes com todas as palavras procuradas (pelo começo de cada palavra), do maior peso ao menor. Lê só o
 * arquivo da palavra com menos nomes; `null` quando a busca ainda não foi publicada.
 */
export async function buscarPessoasJuridicas(termo: string, limite = 20): Promise<AchadoPj[] | null> {
  const procuradas = palavrasDaBusca(termo);
  if (procuradas.length === 0) return [];
  const indice = await lerIndiceBusca();
  if (!indice) return null;
  const prefixos = procuradas.map((p) => prefixoDaPalavra(p, indice.divididos));
  const menor = prefixos.reduce((a, b) => ((indice.arquivos[a] ?? 0) <= (indice.arquivos[b] ?? 0) ? a : b));
  if (!indice.arquivos[menor]) return [];
  const achados: AchadoPj[] = [];
  for (const [cnpj, nome, peso] of await lerArquivoBusca(menor)) {
    if (casaComONome(nome, procuradas)) achados.push({ cnpj, nome, peso });
    if (achados.length >= limite) break;
  }
  return achados;
}

/** Só os dígitos, se forem 14; aceita o CNPJ com pontos, barra e traço. */
export function cnpjDoTexto(texto: string): string | null {
  const d = texto.replace(/\D/g, "");
  return d.length === 14 ? d : null;
}

// ------------------------------------------------------------------------------------------ período

/** Os anos que aparecem em alguma fonte do CNPJ (contratos, emendas, tribunal e início dos convênios), em ordem. */
export function anosDaPessoa(p: PessoaJuridica): string[] {
  const anos = new Set<string>();
  for (const l of p.contratos) anos.add(l[1]);
  for (const l of p.emendas) anos.add(l[1]);
  for (const l of p.tce ?? []) anos.add(l[1]);
  for (const c of p.convenios) if (c[7]) anos.add(c[7].slice(0, 4));
  return [...anos].sort();
}

/** O CNPJ só com os anos de `de` a `ate` (inclusive; `null` deixa a ponta aberta); convênio pelo ano de início. */
export function recortarPessoa(p: PessoaJuridica, de: string | null, ate: string | null): PessoaJuridica {
  if (!de && !ate) return p;
  const dentro = (ano: string | null | undefined) => !!ano && (!de || ano >= de) && (!ate || ano <= ate);
  return {
    ...p,
    contratos: p.contratos.filter((l) => dentro(l[1])),
    emendas: p.emendas.filter((l) => dentro(l[1])),
    tce: p.tce?.filter((l) => dentro(l[1])),
    convenios: p.convenios.filter((c) => dentro(c[7]?.slice(0, 4))),
  };
}
