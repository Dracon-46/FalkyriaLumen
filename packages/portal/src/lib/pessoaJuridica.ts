/**
 * Visão 360 de uma pessoa jurídica pelo CNPJ (ADR-049): o arquivo `pj/<grupo>.json.gz` traz os contratos no PNCP
 * por ente contratante e ano, as emendas parlamentares recebidas e os convênios com a União. A página junta o
 * cartão da Receita (`receita.ts`).
 */

import { obterJsonComprimido } from "./comprimido";
import { BASE_PAINEL, conferir, grupoDoCnpj } from "./paineis";

/** Contratos no PNCP com o ente contratante num ano: `[ente, ano, contratos, valor]`. */
export type LinhaContratos = [string, string, number, number];
/** Emendas recebidas de um ente num ano: `[ente, ano, valor]`. */
export type LinhaEmendas = [string, string, number];
/** Um convênio: `[ente, número, situação, objeto, órgão, valor, liberado, início]`. */
export type LinhaConvenio = [string, string, string, string, string, number, number, string | null];

/** O que o Lumen tem do CNPJ. */
export interface PessoaJuridica {
  cnpj: string;
  nome: string | null;
  contratos: LinhaContratos[];
  emendas: LinhaEmendas[];
  convenios: LinhaConvenio[];
  /** Data do arquivo da CGU de onde vieram as emendas e os convênios (`AAAAMMDD`). */
  fontes: { emendas: string | null; convenios: string | null };
  gerado_em: string;
}

/** Arquivo `pj/<grupo>.json.gz`: as pessoas jurídicas do grupo (`grupoDoCnpj`). */
interface GrupoPessoasJuridicas {
  versao: 1;
  tipo: "pessoas-juridicas";
  gerado_em: string;
  fontes: PessoaJuridica["fontes"];
  pessoas: Record<string, Pick<PessoaJuridica, "nome" | "contratos" | "emendas" | "convenios">>;
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
  };
}

/** Só os dígitos, se forem 14; aceita o CNPJ com pontos, barra e traço. */
export function cnpjDoTexto(texto: string): string | null {
  const d = texto.replace(/\D/g, "");
  return d.length === 14 ? d : null;
}
