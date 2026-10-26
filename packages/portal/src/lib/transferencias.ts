/**
 * Transferências da União a um ente (ADR-054), do arquivo `transferencias/ente/<grupo>.json.gz` que os painéis
 * publicam a partir do Portal da Transparência (CGU): por ano, o que foi para o próprio governo (por tipo, função
 * e ação) e para as entidades sem fins lucrativos do município. Não inclui FPM e FPE, que o arquivo da CGU não
 * traz (saem nas receitas do ente).
 */

import { obterJsonComprimido } from "./comprimido";
import { BASE_PAINEL, conferir, grupoDoEnte } from "./paineis";

/** O que foi para o governo num ano: total, por tipo, por função e por ação (as maiores, o resto em "Outras ações"). */
export interface TransferidoAoGoverno {
  total: number;
  por_tipo: Record<string, number>;
  por_area: Record<string, number>;
  por_acao: Record<string, number>;
}

/** O que foi para as entidades do município num ano. */
export interface TransferidoAEntidades {
  total: number;
  por_area: Record<string, number>;
}

/** As transferências de um ente, por ano. */
export interface TransferenciasEnte {
  fonte: string | null;
  /** Os meses (`AAAAMM`) já lidos: a primeira carga se espalha por alguns dias, e um ano pode estar incompleto. */
  meses: string[];
  anos: Record<string, { governo?: TransferidoAoGoverno; entidades?: TransferidoAEntidades }>;
}

/** Arquivo `transferencias/ente/<grupo>.json.gz`: os entes do grupo (`grupoDoEnte`). */
interface TransferenciasGrupo {
  versao: 1;
  tipo: "transferencias-entes";
  gerado_em: string;
  fonte: string | null;
  meses: string[];
  entes: Record<string, TransferenciasEnte["anos"]>;
}

/** As transferências do ente; `null` quando não há (ente sem repasse ou arquivo ainda não publicado). */
export async function carregarTransferencias(codigo: string, sinal?: AbortSignal): Promise<TransferenciasEnte | null> {
  const url = `${BASE_PAINEL}/transferencias/ente/${grupoDoEnte(codigo)}.json.gz`;
  const bruto = await obterJsonComprimido(url, sinal);
  if (bruto === null) return null;
  const g = conferir<TransferenciasGrupo>(bruto, "transferencias-entes", url);
  const anos = g.entes?.[codigo];
  return anos ? { fonte: g.fonte, meses: g.meses ?? [], anos } : null;
}

/** Soma de dicionários de valores convertidos, do maior ao menor. */
function somarPorChave(partes: (Record<string, number> | undefined)[], ano: string[],
  converter: (valor: number, ano: string) => number | null): { chave: string; valor: number }[] {
  const soma = new Map<string, number>();
  partes.forEach((p, i) => {
    for (const [k, v] of Object.entries(p ?? {})) {
      const c = converter(v, ano[i]!);
      if (c !== null) soma.set(k, (soma.get(k) ?? 0) + c);
    }
  });
  return [...soma].map(([chave, valor]) => ({ chave, valor })).sort((a, b) => b.valor - a.valor);
}

/** As transferências nos `anos`, com os valores convertidos pelo ano (`converter` devolve null fora do alcance). */
export interface TransferenciasNoPeriodo {
  governo: number;
  entidades: number;
  porAno: { ano: string; governo: number | null; entidades: number | null; meses: number }[];
  porTipo: { chave: string; valor: number }[];
  porArea: { chave: string; valor: number }[];
  porAcao: { chave: string; valor: number }[];
  /** Anos do período com menos de 12 meses lidos (a carga ainda não chegou, ou o ano não acabou). */
  incompletos: string[];
}

/** Soma o período: total, ano a ano, por tipo, por função e por ação, sempre o que foi para o governo. */
export function transferenciasNoPeriodo(t: TransferenciasEnte, anos: string[],
  converter: (valor: number, ano: string) => number | null): TransferenciasNoPeriodo {
  const comDado = anos.filter((a) => t.anos[a]);
  const meses = (ano: string) => t.meses.filter((m) => m.startsWith(ano)).length;
  const porAno = anos.map((ano) => {
    const a = t.anos[ano];
    return {
      ano,
      governo: a?.governo ? converter(a.governo.total, ano) : null,
      entidades: a?.entidades ? converter(a.entidades.total, ano) : null,
      meses: meses(ano),
    };
  });
  const gov = comDado.map((a) => t.anos[a]!.governo);
  return {
    governo: porAno.reduce((s, x) => s + (x.governo ?? 0), 0),
    entidades: porAno.reduce((s, x) => s + (x.entidades ?? 0), 0),
    porAno,
    porTipo: somarPorChave(gov.map((g) => g?.por_tipo), comDado, converter),
    porArea: somarPorChave(gov.map((g) => g?.por_area), comDado, converter),
    porAcao: somarPorChave(gov.map((g) => g?.por_acao), comDado, converter),
    incompletos: anos.filter((a) => meses(a) > 0 && meses(a) < 12),
  };
}
