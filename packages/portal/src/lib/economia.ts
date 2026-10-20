/**
 * Economia e Contas Públicas (ADR-033): o arquivo `economia/indicadores.json`, publicado com os painéis, e
 * as contas que a página faz sobre ele.
 *
 * As séries vêm prontas do Python, com a documentação de cada indicador. Aqui ficam só as comparações entre
 * períodos que a pessoa escolhe: o valor no início e no fim, a variação, a média e o acumulado. As regras
 * são as do Python: período sem observação não entra na conta (ausente não é zero), e um acumulado com mês
 * faltando não é calculado.
 */

import { obterJson } from "./feeds";
import { BASE_PAINEL, conferir } from "./paineis";

/** Como o indicador se resume num período: estado num momento, ou taxa que se acumula. */
export type Agregacao = "nivel" | "variacao_mensal" | "variacao_anual";

/** Um indicador publicado: documentação do catálogo e a série. */
export interface Indicador {
  nome: string;
  nome_oficial?: string;
  grupo: string;
  unidade: string;
  periodicidade: "mensal" | "anual";
  definicao: string;
  leitura: string | null;
  limitacoes: string[];
  agregacao: Agregacao;
  fonte: string;
  fonte_primaria?: string;
  codigo_sgs?: number;
  url?: string;
  derivado_de?: string[];
  coletado_em: string | null;
  ultima_falha?: string | null;
  /** De onde veio a última coleta: o SGS, ou o espelho conferido no Ipeadata quando o SGS recusou. */
  coletado_de?: "sgs" | "ipeadata" | "sidra" | null;
  url_coleta?: string | null;
  periodo_parcial_omitido?: string | null;
  serie: [string, number][];
  ultimo: { periodo: string; valor: number } | null;
  lacunas: string[];
  /** Períodos em que o método da série muda: não se calcula variação entre um lado e o outro. */
  quebras?: string[];
  /** Releases do IBGE sobre o indicador, como a Agência de Notícias os publicou; só nos indicadores do IBGE. */
  releases?: { fonte: string; coletado_em: string | null; itens: ReleaseIbge[] };
}

/** Um release oficial do IBGE: título, data (ISO), link na Agência de Notícias e a introdução. */
export interface ReleaseIbge {
  titulo: string;
  data: string;
  link: string;
  introducao: string;
}

/** O arquivo inteiro. */
export interface FeedEconomia {
  versao: 1;
  tipo: "economia";
  gerado_em: string;
  grupos: { id: string; nome: string; indicadores: string[] }[];
  indicadores: Record<string, Indicador>;
}

/** Endereço do arquivo dos indicadores, ao lado dos painéis. */
export const urlEconomia = () => `${BASE_PAINEL}/economia/indicadores.json`;

/** Lê e confere o arquivo; `null` quando ainda não foi publicado. */
export async function carregarEconomia(sinal?: AbortSignal): Promise<FeedEconomia | null> {
  const url = urlEconomia();
  const bruto = await obterJson(url, { sinal });
  return bruto === null ? null : normalizarFeed(conferir<FeedEconomia>(bruto, "economia", url));
}

/**
 * Garante os campos que as contas usam: indicador sem `agregacao` é tratado como nível (comparado do início
 * ao fim, nunca acumulado), e sem `serie`, como série vazia. Acumular um nível daria número sem sentido.
 */
export function normalizarFeed(feed: FeedEconomia): FeedEconomia {
  for (const ind of Object.values(feed.indicadores)) {
    if (ind.agregacao !== "variacao_mensal" && ind.agregacao !== "variacao_anual") ind.agregacao = "nivel";
    if (!Array.isArray(ind.serie)) ind.serie = [];
    if (!Array.isArray(ind.limitacoes)) ind.limitacoes = [];
    if (!Array.isArray(ind.lacunas)) ind.lacunas = [];
  }
  return feed;
}

// ------------------------------------------------------------------------------------------ períodos

/** Um intervalo de meses, inclusivo nas duas pontas (`AAAA-MM`). */
export interface Periodo {
  de: string;
  ate: string;
  rotulo: string;
}

/**
 * Mandatos presidenciais, para atalho na comparação. São só intervalos de datas: o que muda num período
 * não é atribuído a quem governava (ADR-033). Dilma Rousseff foi afastada em 12/05/2016 e o impeachment
 * concluído em 31/08/2016; o corte é por mês.
 */
export const MANDATOS: Periodo[] = [
  { de: "1995-01", ate: "1998-12", rotulo: "1995–1998 · Fernando Henrique Cardoso" },
  { de: "1999-01", ate: "2002-12", rotulo: "1999–2002 · Fernando Henrique Cardoso" },
  { de: "2003-01", ate: "2006-12", rotulo: "2003–2006 · Luiz Inácio Lula da Silva" },
  { de: "2007-01", ate: "2010-12", rotulo: "2007–2010 · Luiz Inácio Lula da Silva" },
  { de: "2011-01", ate: "2014-12", rotulo: "2011–2014 · Dilma Rousseff" },
  { de: "2015-01", ate: "2016-08", rotulo: "2015–ago/2016 · Dilma Rousseff" },
  { de: "2016-09", ate: "2018-12", rotulo: "set/2016–2018 · Michel Temer" },
  { de: "2019-01", ate: "2022-12", rotulo: "2019–2022 · Jair Bolsonaro" },
  { de: "2023-01", ate: "2026-12", rotulo: "2023–2026 · Luiz Inácio Lula da Silva (em curso)" },
];

const MES = /^\d{4}-(0[1-9]|1[0-2])$/;

/** O mês é `AAAA-MM` válido? */
export function mesValido(m: string | null | undefined): m is string {
  return typeof m === "string" && MES.test(m);
}

/** Mês da série (`AAAA-MM`, ou `AAAA` na anual) cai no período? Na série anual, vale o ano inteiro dentro. */
function dentro(periodo: string, p: Pick<Periodo, "de" | "ate">): boolean {
  if (periodo.length === 4) return periodo >= p.de.slice(0, 4) && periodo <= p.ate.slice(0, 4);
  return periodo >= p.de && periodo <= p.ate;
}

/** Os pontos da série dentro do período. */
export function recortar(ind: Pick<Indicador, "serie">, p: Pick<Periodo, "de" | "ate">): [string, number][] {
  return ind.serie.filter(([k]) => dentro(k, p));
}

/** Resumo de um indicador num período: o que a tabela de comparação mostra. */
export interface Resumo {
  inicio: { periodo: string; valor: number } | null;  // o último valor antes do período (o estado ao começar)
  fim: { periodo: string; valor: number } | null;
  variacao: number | null;   // fim - início (pontos, na unidade do indicador) ou % (reais e índices)
  variacaoEmPercentual: boolean;
  media: number | null;
  acumulado: number | null;  // só nas taxas: produto de (1 + taxa) no período, menos 1, em %
  observacoes: number;
  esperadas: number;         // quantas observações o período teria sem lacunas, até o último publicado
  ateEfetivo: string;        // o fim do período, ou o último mês publicado, se for antes
  quebra?: string | null;    // quebra de método entre o início e o fim: a variação fica sem cálculo
}

/** Unidade em que a variação é diferença de pontos (as percentuais) e não variação percentual. */
function emPontos(unidade: string): boolean {
  return unidade.startsWith("%");
}

/** Quantos meses (ou anos, na série anual) o período tem, contando as duas pontas. */
export function tamanho(p: Pick<Periodo, "de" | "ate">, periodicidade: "mensal" | "anual"): number {
  const [a1, m1] = p.de.split("-").map(Number) as [number, number];
  const [a2, m2] = p.ate.split("-").map(Number) as [number, number];
  if (periodicidade === "anual") return Math.max(0, a2 - a1 + 1);
  return Math.max(0, (a2 - a1) * 12 + (m2 - m1) + 1);
}

/**
 * Resume o indicador no período. O início de um nível é o último valor **antes** do período (a dívida ao
 * começar 2019 é a de dezembro de 2018); o fim, o último dentro dele. Nas taxas, o acumulado só existe se
 * não faltar nenhum mês (ou ano) do período, até o último publicado.
 */
export function resumir(ind: Indicador, p: Pick<Periodo, "de" | "ate">): Resumo {
  const pontos = recortar(ind, p);
  const antes = ind.serie.filter(([k]) => (k.length === 4 ? k < p.de.slice(0, 4) : k < p.de));
  const ultimoAntes = antes[antes.length - 1];
  const fimPonto = pontos[pontos.length - 1];
  const fim = fimPonto ? { periodo: fimPonto[0], valor: fimPonto[1] } : null;
  const valores = pontos.map(([, v]) => v);
  const media = valores.length ? valores.reduce((s, v) => s + v, 0) / valores.length : null;
  const ultimo = ind.ultimo?.periodo;
  const ultimoMes = ultimo ? (ultimo.length === 4 ? `${ultimo}-12` : ultimo) : null;
  const ateEfetivo = ultimoMes && ultimoMes < p.ate ? ultimoMes : p.ate;
  const esperadas = tamanho({ de: p.de, ate: ateEfetivo }, ind.periodicidade);
  if (ind.agregacao === "nivel") {
    const primeiro = pontos[0];
    const inicio = ultimoAntes
      ? { periodo: ultimoAntes[0], valor: ultimoAntes[1] }
      : primeiro
        ? { periodo: primeiro[0], valor: primeiro[1] }
        : null;
    const pontosEmPontos = emPontos(ind.unidade);
    const quebra = inicio && fim
      ? (ind.quebras ?? []).find((q) => inicio.periodo < q && q <= fim.periodo) ?? null
      : null;
    let variacao: number | null = null;
    if (inicio && fim && inicio.periodo !== fim.periodo && !quebra) {
      variacao = pontosEmPontos ? fim.valor - inicio.valor : inicio.valor ? (fim.valor / inicio.valor - 1) * 100 : null;
    }
    return { inicio, fim, variacao, variacaoEmPercentual: !pontosEmPontos, media, acumulado: null,
             observacoes: pontos.length, esperadas, ateEfetivo, quebra };
  }
  const completo = pontos.length > 0 && pontos.length === esperadas;
  const acumulado = completo ? (valores.reduce((f, v) => f * (1 + v / 100), 1) - 1) * 100 : null;
  return { inicio: null, fim, variacao: null, variacaoEmPercentual: false, media, acumulado,
           observacoes: pontos.length, esperadas, ateEfetivo };
}

// ------------------------------------------------------------------------------------------ formato

const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];

/** `2025-03` → "mar/2025"; `2025` → "2025". */
export function periodoCurto(periodo: string): string {
  if (periodo.length === 4) return periodo;
  return `${MESES[Number(periodo.slice(5, 7)) - 1]}/${periodo.slice(0, 4)}`;
}

/** Valor do indicador na unidade dele, em português ("4,58%", "82,87% do PIB", "R$ 13,40 tri"). */
export function valorNaUnidade(valor: number | null | undefined, unidade: string): string {
  if (valor === null || valor === undefined || !Number.isFinite(valor)) return "—";
  if (unidade.startsWith("R$ milhões")) {
    const reais = valor * 1e6;
    if (Math.abs(reais) >= 1e12) return `R$ ${(reais / 1e12).toLocaleString("pt-BR", { maximumFractionDigits: 2 })} tri`;
    return `R$ ${(reais / 1e9).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} bi`;
  }
  if (unidade === "pessoas") {
    return `${(valor / 1e6).toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 })} milhões`;
  }
  const n = valor.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  if (unidade.startsWith("R$")) return `R$ ${n}`;
  if (unidade === "% do PIB") return `${n}% do PIB`;
  if (unidade.startsWith("%")) return `${n}%`;
  return n;
}

/** Variação de um resumo de nível: "+3,12 p.p." nas unidades percentuais, "+4,5%" nas demais. */
export function variacaoTexto(r: Resumo): string {
  if (r.variacao === null) return "—";
  const sinal = r.variacao > 0 ? "+" : r.variacao < 0 ? "−" : "";
  const n = Math.abs(r.variacao).toLocaleString("pt-BR", { minimumFractionDigits: r.variacaoEmPercentual ? 1 : 2,
                                                         maximumFractionDigits: r.variacaoEmPercentual ? 1 : 2 });
  return r.variacaoEmPercentual ? `${sinal}${n}%` : `${sinal}${n} p.p.`;
}
