/**
 * Contratos registrados nos tribunais de contas (ADR-050), do arquivo `tce/ente/<grupo>.json.gz` que os painéis
 * publicam: por ente e ano do contrato, quantos e quanto, com os aditivos, a soma anônima de pessoa física e os
 * fornecedores: o LicitaCon do TCE-RS (desde 2016), o SIM-AM do TCE-PR e a API do TCE-PE (desde 2013).
 */

import { obterJsonComprimido } from "./comprimido";
import { BASE_PAINEL, conferir, grupoDoEnte } from "./paineis";

/**
 * Um ano do ente, na ordem de `colunas`: contratos, valor somado, contratos fora da soma pelo teto de
 * plausibilidade, contratos e valor com pessoa física, aditivos e o acréscimo líquido deles.
 */
export type AnoTce = [number, number, number, number, number, number, number];

/** Os contratos de um ente no tribunal de contas. */
export interface TceEnte {
  tribunal: string;
  sistema: string;
  fonte: string;
  /** Ausente nos estados gravados antes do módulo comum dos tribunais. */
  primeiroAno: number | null;
  coletadoEm: string | null;
  anos: Record<string, AnoTce>;
  /** `[CNPJ, nome, [[ano, contratos, valor], ...]]`, do maior valor ao menor (até 100). */
  fornecedores: [string, string | null, [string, number, number][]][];
}

/** Arquivo `tce/ente/<grupo>.json.gz`. */
interface GrupoTce {
  versao: 1;
  tipo: "tce-entes";
  tribunais: Record<string, { sistema: string; fonte: string; coletado_em: string | null; primeiro_ano?: number | null }>;
  entes: Record<string, { tribunal: string; anos: Record<string, AnoTce>; fornecedores: TceEnte["fornecedores"] }>;
}

/** Os contratos do ente no tribunal de contas; `null` quando o tribunal dele ainda não está no Lumen. */
export async function carregarTce(codigo: string, sinal?: AbortSignal): Promise<TceEnte | null> {
  const url = `${BASE_PAINEL}/tce/ente/${grupoDoEnte(codigo)}.json.gz`;
  const bruto = await obterJsonComprimido(url, sinal);
  if (bruto === null) return null;
  const grupo = conferir<GrupoTce>(bruto, "tce-entes", url);
  const e = grupo.entes?.[codigo];
  const t = e ? grupo.tribunais[e.tribunal] : undefined;
  if (!e || !t) return null;
  return { tribunal: e.tribunal, sistema: t.sistema, fonte: t.fonte, primeiroAno: t.primeiro_ano ?? null,
           coletadoEm: t.coletado_em, anos: e.anos, fornecedores: e.fornecedores };
}

/** Os contratos nos anos pedidos, já convertidos (reais de um ano-base ou por habitante). */
export interface TceNoPeriodo {
  anos: string[];
  contratos: number;
  valor: number;
  foraDaSoma: number;
  pfContratos: number;
  pfValor: number;
  aditivos: number;
  aditivosValor: number;
  fornecedores: { cnpj: string; nome: string; contratos: number; valor: number }[];
}

/** Soma os `anos` do ente; o ano que a conversão não alcança fica de fora. */
export function tceNoPeriodo(t: TceEnte, anos: string[], converter: (valor: number, ano: string) => number | null): TceNoPeriodo {
  const usados: string[] = [];
  const r: TceNoPeriodo = { anos: usados, contratos: 0, valor: 0, foraDaSoma: 0, pfContratos: 0, pfValor: 0, aditivos: 0,
                            aditivosValor: 0, fornecedores: [] };
  const conv = (v: number, ano: string) => converter(v, ano) ?? 0;
  for (const ano of anos) {
    const a = t.anos[ano];
    if (!a || converter(1, ano) === null) continue;
    usados.push(ano);
    r.contratos += a[0];
    r.valor += conv(a[1], ano);
    r.foraDaSoma += a[2];
    r.pfContratos += a[3];
    r.pfValor += conv(a[4], ano);
    r.aditivos += a[5];
    r.aditivosValor += conv(a[6], ano);
  }
  const dentro = new Set(usados);
  for (const [cnpj, nome, porAno] of t.fornecedores) {
    let contratos = 0;
    let valor = 0;
    for (const [ano, n, v] of porAno) {
      if (!dentro.has(ano)) continue;
      contratos += n;
      valor += conv(v, ano);
    }
    if (contratos) r.fornecedores.push({ cnpj, nome: nome ?? cnpj, contratos, valor });
  }
  r.fornecedores.sort((x, y) => y.valor - x.valor || y.contratos - x.contratos);
  return r;
}

/** Um ano na comparação com o PNCP: contratos e valor nas duas fontes (`null` quando a fonte não tem o ano). */
export interface AnoComPncp {
  ano: string;
  pncpContratos: number | null;
  pncpValor: number | null;
  tceContratos: number | null;
  tceValor: number | null;
}

/**
 * Os anos do ente nas duas fontes, do mais recente ao mais antigo: os meses do PNCP (`AAAA-MM`, ou `AAAA` nos anos
 * publicados ano a ano) somados por ano, ao lado do tribunal. As fontes não se somam: de 2021 em diante, muitos
 * contratos estão nas duas.
 */
export function anoAAnoComPncp(t: TceEnte, meses: { mes: string; contratos: number; valor_contratos: number }[]): AnoComPncp[] {
  const pncp = new Map<string, { contratos: number; valor: number }>();
  for (const m of meses) {
    const ano = m.mes.slice(0, 4);
    const x = pncp.get(ano) ?? { contratos: 0, valor: 0 };
    x.contratos += m.contratos;
    x.valor += m.valor_contratos;
    pncp.set(ano, x);
  }
  const anos = [...new Set([...pncp.keys(), ...Object.keys(t.anos)])].sort().reverse();
  return anos.map((ano) => {
    const p = pncp.get(ano);
    const a = t.anos[ano];
    return { ano, pncpContratos: p ? p.contratos : null, pncpValor: p ? p.valor : null,
             tceContratos: a ? a[0] : null, tceValor: a ? a[1] : null };
  });
}
