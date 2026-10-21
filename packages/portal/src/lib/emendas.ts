/**
 * Emendas parlamentares recebidas por um ente (ADR-044), do arquivo `emendas/ente/<código IBGE>.json.gz` que os
 * painéis publicam a partir do Portal da Transparência (CGU). O recebido é o que os favorecidos do lugar
 * receberam, por categoria (governo municipal ou estadual, entidade, empresa, pessoa física); o banco que opera
 * os repasses fica de fora, e a pessoa física entra só na soma.
 */

import { obterJsonComprimido } from "./comprimido";
import { BASE_PAINEL, codigoSeguro, conferir } from "./paineis";

/** As categorias de favorecido, pela natureza jurídica. */
export type CategoriaFavorecido = "governo_municipal" | "governo_estadual" | "entidade" | "empresa" | "pessoa_fisica";

/** Uma linha do recebido: ano, emenda, categoria, CNPJ e nome (nulos para pessoa física) e valor. */
export type LinhaRecebido = [string, string, CategoriaFavorecido, string | null, string | null, number];
/** A descrição da emenda: ano, tipo, autor, número, função e ação. */
export type DescricaoEmenda = [string, string, string, string, string, string];

/** Arquivo `emendas/ente/<código>.json`. */
export interface EmendasEnte {
  versao: 1;
  tipo: "emendas-ente";
  gerado_em: string;
  ente: string;
  data_arquivo: string | null;
  fonte: string | null;
  categorias: Record<CategoriaFavorecido, string>;
  recebido: LinhaRecebido[];
  emendas: Record<string, DescricaoEmenda | null>;
}

/** As emendas recebidas pelo ente; `null` quando o ente não recebeu ou o arquivo não foi publicado. */
export async function carregarEmendas(codigo: string, sinal?: AbortSignal): Promise<EmendasEnte | null> {
  const url = `${BASE_PAINEL}/emendas/ente/${codigoSeguro(codigo)}.json.gz`;
  const bruto = await obterJsonComprimido(url, sinal);
  return bruto === null ? null : conferir<EmendasEnte>(bruto, "emendas-ente", url);
}

/** Uma soma com o rótulo: categoria, autor ou favorecido. */
export interface Soma {
  chave: string;
  rotulo: string;
  detalhe?: string;
  valor: number;
}

/** O recebido num período, já convertido ano a ano (`converter` devolve `null` para o ano que não alcança). */
export interface RecebidoNoPeriodo {
  total: number;
  anos: string[];
  porCategoria: Soma[];
  porAutor: Soma[];
  favorecidos: (Soma & { cnpj: string; categoria: CategoriaFavorecido })[];
}

/** Soma o recebido nos `anos`, por categoria, por autor e por favorecido pessoa jurídica, do maior ao menor. */
export function recebidoNoPeriodo(e: EmendasEnte, anos: string[],
  converter: (valor: number, ano: string) => number | null): RecebidoNoPeriodo {
  const dentro = new Set(anos);
  const usados = new Set<string>();
  const categorias = new Map<string, number>();
  const autores = new Map<string, { valor: number; tipo: string }>();
  const favorecidos = new Map<string, { valor: number; nome: string; categoria: CategoriaFavorecido }>();
  let total = 0;
  for (const [ano, emenda, categoria, cnpj, nome, valor] of e.recebido) {
    if (!dentro.has(ano)) continue;
    const v = converter(valor, ano);
    if (v === null) continue;
    usados.add(ano);
    total += v;
    categorias.set(categoria, (categorias.get(categoria) ?? 0) + v);
    const descricao = e.emendas[emenda];
    const autor = descricao?.[2] ?? "Autor não informado";
    const a = autores.get(autor) ?? { valor: 0, tipo: descricao?.[1] ?? "" };
    a.valor += v;
    autores.set(autor, a);
    if (cnpj) {
      const f = favorecidos.get(cnpj) ?? { valor: 0, nome: nome ?? cnpj, categoria };
      f.valor += v;
      favorecidos.set(cnpj, f);
    }
  }
  const ordenar = <T extends { valor: number }>(xs: T[]) => xs.sort((x, y) => y.valor - x.valor);
  return {
    total,
    anos: anos.filter((a) => usados.has(a)),
    porCategoria: ordenar([...categorias].map(([chave, valor]) =>
      ({ chave, rotulo: e.categorias[chave as CategoriaFavorecido] ?? chave, valor }))),
    porAutor: ordenar([...autores].map(([autor, a]) => ({ chave: autor, rotulo: autor, detalhe: a.tipo, valor: a.valor }))),
    favorecidos: ordenar([...favorecidos].map(([cnpj, f]) =>
      ({ chave: cnpj, rotulo: f.nome, cnpj, categoria: f.categoria, detalhe: e.categorias[f.categoria], valor: f.valor }))),
  };
}
