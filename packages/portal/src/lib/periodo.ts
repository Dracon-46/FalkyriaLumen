/**
 * Recorte de um período (de um mês a outro) nos painéis de contratações e a paginação das listas.
 *
 * Os arquivos dos painéis trazem, além dos totais do período coletado, o mês a mês de cada tabela
 * (`meses`: `[mês, ...valores]`). Aqui as tabelas são refeitas só com os meses escolhidos: os totais saem do
 * mês a mês do ente; modalidades, órgãos, fornecedores, municípios, esferas e UFs, do mês a mês de cada linha;
 * as listas de publicações são filtradas pela data. Nada é estimado: mês fora do arquivo não entra.
 *
 * Os fornecedores do arquivo são os de maior valor no período inteiro; num período menor, a ordem é refeita
 * entre eles (um fornecedor que só aparece num mês pode não estar na lista). O portal avisa.
 */

import type {
  ContratacoesEnte,
  ContratacoesPanorama,
  SecoesContratacoes,
  TotaisContratacoes,
} from "./paineis";

/** Período de meses, inclusivo nas duas pontas (`AAAA-MM`); `null` é sem limite. */
export interface PeriodoMeses {
  de: string | null;
  ate: string | null;
}

const MES = /^\d{4}-(0[1-9]|1[0-2])$/;

/** Lê `de` e `ate` da URL, ignorando o que não é mês válido, e põe em ordem. */
export function lerPeriodo(params: { get(chave: string): string | null }): PeriodoMeses {
  const de = params.get("de");
  const ate = params.get("ate");
  const p = { de: de && MES.test(de) ? de : null, ate: ate && MES.test(ate) ? ate : null };
  return p.de && p.ate && p.de > p.ate ? { de: p.ate, ate: p.de } : p;
}

/** O período tem algum limite? */
export function temRecorte(p: PeriodoMeses): boolean {
  return p.de !== null || p.ate !== null;
}

/**
 * O mês (ou a data `AAAA-MM-DD`, ou o ano `AAAA`) cai no período? O ano, linha dos anos antigos publicados ano a
 * ano, só entra inteiro: de janeiro a dezembro dentro do período (o filtro só oferece ano inteiro para eles).
 */
export function noPeriodo(dataOuMes: string | null | undefined, p: PeriodoMeses): boolean {
  if (!dataOuMes) return !temRecorte(p);
  if (dataOuMes.length === 4) {
    return (p.de === null || `${dataOuMes}-01` >= p.de) && (p.ate === null || `${dataOuMes}-12` <= p.ate);
  }
  const mes = dataOuMes.slice(0, 7);
  return (p.de === null || mes >= p.de) && (p.ate === null || mes <= p.ate);
}

/** O ano do exercício (ou da linha) está dentro do período? Basta tocar o período (o ano 2025 em 2025-06..2026-03). */
export function anoNoPeriodo(ano: number | string, p: PeriodoMeses): boolean {
  const a = String(ano);
  return (p.de === null || a >= p.de.slice(0, 4)) && (p.ate === null || a <= p.ate.slice(0, 4));
}

/**
 * As linhas mensais somadas por ano (as já anuais ficam como estão), para o gráfico quando o período tem
 * anos publicados ano a ano: barras de ano e de mês lado a lado enganariam a escala.
 */
export function porAno<T extends { mes: string }>(meses: T[], somar: (a: T, b: T) => T): T[] {
  const anos = new Map<string, T>();
  for (const m of meses) {
    const ano = m.mes.slice(0, 4);
    const antes = anos.get(ano);
    anos.set(ano, antes ? somar(antes, { ...m, mes: ano }) : { ...m, mes: ano });
  }
  return [...anos.values()].sort((a, b) => a.mes.localeCompare(b.mes));
}

/** Linha mensal dos arquivos: `[mês, n1, n2, ...]`. */
type LinhaMes = [string, ...number[]];

/** Soma, coluna a coluna, as linhas mensais dentro do período (`colunas` valores depois do mês). */
export function somarMeses(meses: LinhaMes[] | undefined, p: PeriodoMeses, colunas: number): number[] {
  const soma = Array<number>(colunas).fill(0);
  for (const linha of meses ?? []) {
    if (!noPeriodo(linha[0], p)) continue;
    for (let i = 0; i < colunas; i++) soma[i]! += Number(linha[i + 1] ?? 0);
  }
  return soma;
}

/** Totais a partir das quatro colunas `[processos, valor estimado, contratos, valor dos contratos]`. */
function totais([processos, valor_estimado, contratos, valor_contratos]: number[]): TotaisContratacoes {
  return {
    processos: processos ?? 0,
    valor_estimado: valor_estimado ?? 0,
    processos_sem_valor: 0,
    contratos: contratos ?? 0,
    valor_contratos: valor_contratos ?? 0,
  };
}

/** Os meses do arquivo, do mais antigo ao mais recente (para as opções do filtro). */
export function mesesDoArquivo(dados: Pick<SecoesContratacoes, "meses">): string[] {
  return dados.meses.map((m) => m.mes).sort();
}

/**
 * As seções refeitas no período. Sem recorte, devolve os dados como vieram. Os totais saem do mês a mês
 * (processos sem valor e valores a conferir também); a contagem de órgãos e de fornecedores é a das linhas
 * do arquivo com movimento no período.
 */
export function recortarSecoes<T extends Omit<SecoesContratacoes, "orgaos"> & { orgaos?: SecoesContratacoes["orgaos"] }>(
  dados: T,
  p: PeriodoMeses,
): T {
  if (!temRecorte(p)) return dados;
  const meses = dados.meses.filter((m) => noPeriodo(m.mes, p));
  const soma = (campo: keyof TotaisContratacoes) => meses.reduce((s, m) => s + Number(m[campo] ?? 0), 0);
  const modalidades = dados.modalidades
    .map((m) => {
      const [processos, valor_estimado] = somarMeses(m.meses as LinhaMes[], p, 2);
      return { ...m, processos: processos!, valor_estimado: valor_estimado! };
    })
    .filter((m) => m.processos > 0)
    .sort((a, b) => b.processos - a.processos);
  const orgaos = dados.orgaos
    ?.map((o) => ({ ...o, ...totais(somarMeses(o.meses as LinhaMes[], p, 4)) }))
    .filter((o) => o.processos > 0 || o.contratos > 0)
    .sort((a, b) => b.processos - a.processos || b.contratos - a.contratos);
  const fornecedores = dados.fornecedores
    .map((f) => {
      const [contratos, valor] = somarMeses(f.meses as LinhaMes[], p, 2);
      return { ...f, contratos: contratos!, valor: valor! };
    })
    .filter((f) => f.contratos > 0)
    .sort((a, b) => b.valor - a.valor);
  const [pfContratos, pfValor] = somarMeses(dados.pessoas_fisicas.meses as LinhaMes[], p, 2);
  return {
    ...dados,
    totais: {
      ...dados.totais,
      processos: soma("processos"),
      valor_estimado: soma("valor_estimado"),
      processos_sem_valor: soma("processos_sem_valor"),
      contratos: soma("contratos"),
      valor_contratos: soma("valor_contratos"),
      valores_a_conferir: soma("valores_a_conferir"),
      orgaos: orgaos?.length ?? dados.totais.orgaos,
      fornecedores: fornecedores.length,
    },
    meses,
    modalidades,
    ...(orgaos ? { orgaos } : {}),
    fornecedores,
    pessoas_fisicas: { ...dados.pessoas_fisicas, contratos: pfContratos!, valor: pfValor! },
    recentes: dados.recentes.filter((x) => noPeriodo(x.data, p)),
    contratos_recentes: dados.contratos_recentes.filter((x) => noPeriodo(x.data, p)),
    a_conferir: dados.a_conferir?.filter((x) => noPeriodo(x.data, p)),
  };
}

/** Os municípios da UF refeitos no período (a lista toda continua, com zero onde não houve publicação). */
export function recortarMunicipios(
  municipios: NonNullable<ContratacoesEnte["municipios"]>,
  p: PeriodoMeses,
): NonNullable<ContratacoesEnte["municipios"]> {
  if (!temRecorte(p)) return municipios;
  return municipios.map((m) => {
    const t = totais(somarMeses(m.meses as LinhaMes[], p, 4));
    return { ...m, processos: t.processos, valor_estimado: t.valor_estimado, contratos: t.contratos,
             valor_contratos: t.valor_contratos };
  });
}

/** Esferas e UFs do panorama refeitas no período. */
export function recortarPanorama(dados: ContratacoesPanorama, p: PeriodoMeses): ContratacoesPanorama {
  const secoes = recortarSecoes(dados, p);
  if (!temRecorte(p)) return secoes;
  return {
    ...secoes,
    esferas: dados.esferas.map((e) => ({ ...e, ...totais(somarMeses(e.meses as LinhaMes[], p, 4)) })),
    ufs: dados.ufs.map((u) => {
      const [estado, municipios] = somarMeses(u.meses as LinhaMes[], p, 2);
      return { ...u, estado: { ...u.estado, processos: estado! }, municipios: { ...u.municipios, processos: municipios! } };
    }),
  };
}

// ------------------------------------------------------------------------------------------ paginação

/** Itens por página em todas as listas do portal. */
export const POR_PAGINA = 20;

/** Quantas páginas a lista tem (pelo menos uma). */
export function totalDePaginas(total: number, porPagina = POR_PAGINA): number {
  return Math.max(1, Math.ceil(total / porPagina));
}

/** A página `pagina` (a partir de 1, limitada ao intervalo) da lista. */
export function paginar<T>(itens: readonly T[], pagina: number, porPagina = POR_PAGINA): T[] {
  const n = Math.min(Math.max(1, Math.floor(pagina) || 1), totalDePaginas(itens.length, porPagina));
  return itens.slice((n - 1) * porPagina, n * porPagina);
}

/** Os números de página a mostrar: a primeira, a última e as vizinhas da atual, com `null` nos saltos. */
export function paginasVisiveis(atual: number, total: number): (number | null)[] {
  const saida: (number | null)[] = [];
  for (let n = 1; n <= total; n++) {
    if (n === 1 || n === total || Math.abs(n - atual) <= 1) saida.push(n);
    else if (saida[saida.length - 1] !== null) saida.push(null);
  }
  return saida;
}

/** O arquivo tem o mês a mês das tabelas? (Os gerados antes do filtro de período não têm.) */
export function temMesAMes(dados: Pick<SecoesContratacoes, "modalidades" | "fornecedores">): boolean {
  return [...dados.modalidades, ...dados.fornecedores].some((x) => Array.isArray(x.meses));
}
