/**
 * Convênios da União com um ente (ADR-045), do arquivo `convenios/ente/<grupo>.json.gz` que os painéis
 * publicam a partir do Portal da Transparência (CGU): os convênios com início de vigência de 2001 em diante, com a
 * situação como o SIAFI a registra. Convenente pessoa física entra só na soma por ano.
 */

import { obterJsonComprimido } from "./comprimido";
import { BASE_PAINEL, conferir, grupoDoEnte } from "./paineis";

/** Um convênio: número, situação, objeto, órgão, categoria, CNPJ e nome do convenente, valores e datas. */
export type Convenio = [string, string, string, string, string, string | null, string, number, number, number,
  string, string | null, string | null];

/** Arquivo `convenios/ente/<código>.json.gz`. */
export interface ConveniosEnte {
  versao: 1;
  tipo: "convenios-ente";
  gerado_em: string;
  ente: string;
  data_arquivo: string | null;
  fonte: string | null;
  categorias: Record<string, string>;
  convenios: Convenio[];
  pessoa_fisica: Record<string, number>;
}

/** Arquivo `convenios/ente/<grupo>.json.gz`: os convênios dos entes do grupo (`grupoDoEnte`). */
export interface ConveniosGrupo extends Omit<ConveniosEnte, "tipo" | "ente" | "convenios" | "pessoa_fisica"> {
  tipo: "convenios-entes";
  entes: Record<string, Pick<ConveniosEnte, "convenios" | "pessoa_fisica">>;
}

/** Os convênios do ente; `null` quando o ente não tem convênio ou o arquivo não foi publicado. */
export async function carregarConvenios(codigo: string, sinal?: AbortSignal): Promise<ConveniosEnte | null> {
  const url = `${BASE_PAINEL}/convenios/ente/${grupoDoEnte(codigo)}.json.gz`;
  const bruto = await obterJsonComprimido(url, sinal);
  if (bruto === null) return null;
  const { entes, ...resto } = conferir<ConveniosGrupo>(bruto, "convenios-entes", url);
  const c = entes?.[codigo];
  return c ? { ...resto, tipo: "convenios-ente", ente: codigo, ...c } : null;
}

/** Um convênio do período, já com o valor e o liberado convertidos. */
export interface ConvenioNoPeriodo {
  numero: string;
  situacao: string;
  objeto: string;
  orgao: string;
  categoria: string;
  cnpj: string | null;
  convenente: string;
  valor: number;
  liberado: number;
  inicio: string;
  fim: string | null;
}

/** Os convênios iniciados nos `anos`, os totais e a contagem por situação. */
export interface ConveniosNoPeriodo {
  quantidade: number;
  valor: number;
  liberado: number;
  pessoaFisica: number;
  porSituacao: { situacao: string; quantidade: number; valor: number }[];
  lista: ConvenioNoPeriodo[];
}

/**
 * Os convênios com início de vigência nos `anos`, do maior valor ao menor, com o valor e o liberado convertidos
 * pelo ano de início (`converter` devolve `null` para o ano que não alcança: o convênio fica de fora).
 */
export function conveniosNoPeriodo(c: ConveniosEnte, anos: string[],
  converter: (valor: number, ano: string) => number | null): ConveniosNoPeriodo {
  const dentro = new Set(anos);
  const lista: ConvenioNoPeriodo[] = [];
  const situacoes = new Map<string, { quantidade: number; valor: number }>();
  for (const [numero, situacao, objeto, orgao, categoria, cnpj, convenente, valor, liberado, , inicio, fim] of c.convenios) {
    const ano = inicio.slice(0, 4);
    if (!dentro.has(ano)) continue;
    const v = converter(valor, ano);
    const l = converter(liberado, ano);
    if (v === null || l === null) continue;
    lista.push({ numero, situacao, objeto, orgao, categoria, cnpj, convenente, valor: v, liberado: l, inicio, fim });
    const s = situacoes.get(situacao) ?? { quantidade: 0, valor: 0 };
    s.quantidade += 1;
    s.valor += v;
    situacoes.set(situacao, s);
  }
  let pessoaFisica = 0;
  for (const [ano, valor] of Object.entries(c.pessoa_fisica ?? {})) {
    const v = dentro.has(ano) ? converter(valor, ano) : null;
    if (v !== null) pessoaFisica += v;
  }
  lista.sort((x, y) => y.valor - x.valor);
  return {
    quantidade: lista.length,
    valor: lista.reduce((s, x) => s + x.valor, 0),
    liberado: lista.reduce((s, x) => s + x.liberado, 0),
    pessoaFisica,
    porSituacao: [...situacoes].map(([situacao, s]) => ({ situacao, ...s })).sort((x, y) => y.quantidade - x.quantidade),
    lista,
  };
}
