/**
 * Comparação do preço de combustível e de gás de cozinha com o preço de revenda da ANP (ADR-037; regra A-05 do
 * DOC-07, ADR-027), sob demanda no modal da contratação.
 *
 * Duas partes:
 * - **o reconhecimento do item**, cópia das regras de `lumen_mercado.especificacao.reconhecer` só para os
 *   produtos da ANP. Os casos ficam em `packages/mercado/testes/fixtures/reconhecimento_anp.json` e são lidos
 *   pelo teste do Python e pelo daqui: se uma regra mudar de um lado só, um dos testes falha. Na dúvida, o
 *   item não é reconhecido;
 * - **a referência**, do arquivo `mercado/anp/uf-<sigla>-<ano>.json` que os painéis publicam todo dia: a
 *   distribuição do preço de revenda na semana do levantamento, no município (com ao menos 5 coletas) ou na UF
 *   (ao menos 10).
 *
 * Os limiares são os de `parametros_mercado.toml` (1,20 × a mediana no combustível, 1,25 × no gás de cozinha),
 * iniciais e não calibrados. Compra pública inclui entrega, prazo de pagamento e cartão de abastecimento: a
 * distância é um ponto de partida para conferir, não uma conclusão.
 */

import { obterJson } from "./feeds";
import { BASE_PAINEL } from "./paineis";

/** Produtos como a ANP os nomeia; o diesel sem indicação é o S500. */
export type ProdutoAnp = "GASOLINA" | "GASOLINA ADITIVADA" | "ETANOL" | "DIESEL S10" | "DIESEL" | "GNV" | "GLP";

/** Nome de cada produto na tela. */
export const NOME_PRODUTO: Record<ProdutoAnp, string> = {
  GASOLINA: "gasolina comum", "GASOLINA ADITIVADA": "gasolina aditivada", ETANOL: "etanol hidratado",
  "DIESEL S10": "óleo diesel S10", DIESEL: "óleo diesel S500", GNV: "GNV", GLP: "gás de cozinha (botijão de 13 kg)",
};

/** Unidade do preço da ANP de cada produto. */
export const UNIDADE_PRODUTO = (p: ProdutoAnp) => (p === "GNV" ? "m³" : p === "GLP" ? "botijão de 13 kg" : "litro");

/** Parâmetros da A-05 (`parametros_mercado.toml`), iniciais e não calibrados. */
export const PARAMETROS_ANP = {
  limiarCombustivel: 1.2,
  limiarGas: 1.25,
  razaoMinima: 0.5,
  razaoExtrema: 3,
  razaoMaxima: 10,
  janelaDias: 7,
  minimoMunicipio: 5,
  minimoUf: 10,
} as const;

// ------------------------------------------------------------------ reconhecimento (espelho de especificacao.py)

/** Minúsculas, sem acentos e com espaços simples (`sem_acento`). */
export function semAcento(texto: string | null | undefined): string {
  return (texto ?? "").normalize("NFKD").replace(/\p{M}/gu, "").toLowerCase().replace(/\s+/g, " ").trim();
}

/** Descrição com números colados às unidades (`normalizar_titulo`). */
function normalizarTitulo(texto: string | null | undefined): string {
  let t = semAcento(texto).replace(/”/g, '"').replace(/″/g, '"').replace(/''/g, '"');
  t = t.replace(/(\d)[.,](\d)/g, "$1.$2");
  t = t.replace(/(\d)\s*(gb|tb)\b/g, "$1$2");
  t = t.replace(/(\d)\s*("|pol\.?|polegadas?)(?=\W|$)/g, "$1pol");
  return t;
}

const LITRO = new Set(["l", "lt", "lts", "ltr", "ltrs", "lit", "litro", "litros"]);
const M3 = new Set(["m3", "m³", "metro cubico", "metros cubicos"]);
const UNIDADE = new Set(["un", "und", "unid", "unidade", "unidades", "uni", "pc", "pca", "peca", "pecas"]);
const BOTIJAO = new Set(["botijao", "botijoes", "bot", "btj", "recarga", "recargas", "carga", "cargas", "p13", "p 13"]);

/** `litro`, `m3`, `unidade` ou `botijao` a partir da unidade de medida (`unidade_canonica`). */
export function unidadeCanonica(texto: string | null | undefined): string | null {
  let t = semAcento(texto).replace(/³/g, "3");
  if (!t) return null;
  t = t.replace(/[()[\].,;:/\\-]/g, " ");
  const palavras = t.split(/\s+/).filter(Boolean);
  const primeira = palavras[0] ?? "";
  if (M3.has(t) || primeira === "m3") return "m3";
  if (LITRO.has(t) || LITRO.has(primeira)) return "litro";
  if (UNIDADE.has(t) || UNIDADE.has(primeira)) return "unidade";
  if (BOTIJAO.has(t) || BOTIJAO.has(primeira)) return "botijao";
  return null;
}

const FORA_COMBUSTIVEL = new RegExp(
  "lubrificante|oleo (de |para )?motor|oleo 2 ?t|\\barla\\b|graxa|filtro|fluido|\\btaxa\\b|administra|" +
  "gerenciamento|gestao|cartao|servico|lava ?jato|troca de oleo|aditivo para|\\bgel\\b|70 ?%|70 ?inpm|" +
  "isopropil|antissept|assepsia|hospitalar|limpeza|absoluto|anidro|\\bp\\.? ?a\\.?\\b|premium|podium|" +
  "octanagem|aviacao|\\bqav\\b|querosene|maritimo|\\bbotij|\\bglp\\b|\\bgas de cozinha\\b|gas liquefeito");

/** Produto ANP de uma descrição de combustível (sem acento), ou `null` (`_combustivel`). */
function combustivel(d: string): ProdutoAnp | null {
  if (FORA_COMBUSTIVEL.test(d)) return null;
  if (/\bgnv\b|gas natural veicular/.test(d)) return "GNV";
  if (/\bgasolina\b/.test(d)) return /aditivad/.test(d) ? "GASOLINA ADITIVADA" : "GASOLINA";
  if (/\bdiesel\b|\bs ?-? ?10\b|\bs ?-? ?500\b/.test(d)) {
    if (/\bs ?-? ?10\b/.test(d)) return "DIESEL S10";
    if (/\bs ?-? ?500\b|diesel comum/.test(d)) return "DIESEL";
    return null; // "óleo diesel" sem dizer qual: S10 e S500 têm preços diferentes
  }
  if (/\betanol\b/.test(d) || (/\balcool\b/.test(d) && /combust|hidratado|veicul|automot/.test(d))) return "ETANOL";
  return null;
}

const GLP = /\bglp\b|gas liquefeito|gas de cozinha|gas de botijao|botij(ao|oes) de gas|gas butano/;
const P13 = /\bp ?-? ?13\b|\b13 ?(kg|quilos?|kilos?)\b/;
const FORA_GLP = new RegExp(
  "completo|vasilhame novo|com vasilhame|incluindo (o )?vasilhame|aquisicao de vasilhame|" +
  "botij(ao|oes) novos?\\b|regulador|mangueira|valvula|\\bp ?-? ?(2|5|8|20|45|90|190)\\b|" +
  "\\b(2|5|8|20|45|90|190) ?kg\\b|granel|empilhadeira|industrial|\\bgasolina\\b|\\bdiesel\\b|\\betanol\\b|" +
  "\\bgnv\\b|\\blocacao\\b|aluguel|instalacao|manutencao");
const VASILHAME = /\bcasco|vazio|vasilhame/;
const TROCA = /troca|devolu|permuta|substitui|retorno|recarga|reabastec/;

/** A descrição é de GLP no botijão de 13 kg, só o gás, com a troca do vazio? (`_gas_de_cozinha`) */
function gasDeCozinha(d: string): boolean {
  if (!(GLP.test(d) && P13.test(d)) || FORA_GLP.test(d)) return false;
  return !(VASILHAME.test(d) && !TROCA.test(d));
}

/**
 * O produto da ANP do item, ou `null` quando ele não é combustível nem gás de cozinha reconhecido com segurança.
 * A unidade decide antes da descrição: combustível só em litro (GNV em m³), gás só por botijão ou unidade.
 */
export function reconhecerAnp(descricao: string | null | undefined, unidadeMedida: string | null | undefined): ProdutoAnp | null {
  const d = normalizarTitulo(descricao);
  if (!d) return null;
  const unidade = unidadeCanonica(unidadeMedida);
  if (GLP.test(d)) return gasDeCozinha(d) && (unidade === "botijao" || unidade === "unidade") ? "GLP" : null;
  const produto = combustivel(d);
  if (!produto) return null;
  return unidade === (produto === "GNV" ? "m3" : "litro") ? produto : null;
}

// ------------------------------------------------------------------ referência e comparação

/** `[n, mínimo, 1º quartil, mediana, 3º quartil, máximo]` de uma semana. */
export type Estatistica = [number, number, number, number, number, number];

/** O arquivo `mercado/anp/uf-<sigla>-<ano>.json`. */
export interface ArquivoAnp {
  versao: 1;
  tipo: "anp-precos";
  uf: string;
  ano: number;
  gerado_em: string;
  fonte: string;
  pagina: string;
  semanas: [string, string, string][];  // início, fim, planilha
  produtos: Record<string, { uf: [number, ...Estatistica][]; municipios: Record<string, [number, ...Estatistica][]> }>;
}

/** A referência achada: a semana, o lugar e a distribuição. */
export interface ReferenciaAnp {
  produto: ProdutoAnp;
  escopo: "municipio" | "uf";
  inicio: string;
  fim: string;
  planilha: string;
  n: number;
  minimo: number;
  q1: number;
  mediana: number;
  q3: number;
  maximo: number;
}

/** O que a comparação diz do preço. */
export type SituacaoAnp = "acima" | "dentro" | "fora_de_escala" | "sem_referencia";

/** O resultado: a referência (se houver), a razão e a leitura. */
export interface ComparacaoAnp {
  produto: ProdutoAnp;
  preco: number;
  tipoPreco: "homologado" | "estimado";
  data: string;
  referencia: ReferenciaAnp | null;
  razao: number | null;
  limiar: number;
  conferirUnidade: boolean;
  situacao: SituacaoAnp;
  /** Por que não há referência, quando não há. */
  motivo: string | null;
}

/** Endereço do arquivo da UF no ano. */
export const urlAnp = (uf: string, ano: number) => `${BASE_PAINEL}/mercado/anp/uf-${uf.toLowerCase()}-${ano}.json`;

const dia = (iso: string) => Date.parse(`${iso}T12:00:00Z`) / 86_400_000;

/**
 * A distribuição na semana do levantamento que contém a data (ou a mais perto, até 7 dias), no município com
 * ao menos 5 coletas, senão na UF com ao menos 10.
 */
export function acharReferencia(arquivos: ArquivoAnp[], produto: ProdutoAnp, ibge: string | null, data: string): ReferenciaAnp | null {
  const alvo = dia(data);
  type Cand = { distancia: number; arq: ArquivoAnp; i: number };
  const semanas: Cand[] = arquivos.flatMap((arq) => arq.semanas.map(([ini, fim], i) => {
    const a = dia(ini);
    const b = dia(fim);
    return { distancia: alvo < a ? a - alvo : alvo > b ? alvo - b : 0, arq, i };
  })).filter((c) => c.distancia <= PARAMETROS_ANP.janelaDias).sort((x, y) => x.distancia - y.distancia);
  for (const { arq, i } of semanas) {
    const p = arq.produtos[produto];
    if (!p) continue;
    const [ini, fim, planilha] = arq.semanas[i]!;
    const linhaMu = ibge ? p.municipios[ibge]?.find((l) => l[0] === i) : undefined;
    const linhaUf = p.uf.find((l) => l[0] === i);
    const escolha = linhaMu && linhaMu[1] >= PARAMETROS_ANP.minimoMunicipio ? { l: linhaMu, escopo: "municipio" as const }
      : linhaUf && linhaUf[1] >= PARAMETROS_ANP.minimoUf ? { l: linhaUf, escopo: "uf" as const } : null;
    if (!escolha) continue;
    const [, n, minimo, q1, mediana, q3, maximo] = escolha.l;
    return { produto, escopo: escolha.escopo, inicio: ini, fim, planilha, n, minimo, q1, mediana, q3, maximo };
  }
  return null;
}

/** A leitura do preço contra a referência, pelos limiares da A-05. */
export function compararComAnp(produto: ProdutoAnp, preco: number, tipoPreco: "homologado" | "estimado", data: string,
                               referencia: ReferenciaAnp | null, motivo: string | null = null): ComparacaoAnp {
  const P = PARAMETROS_ANP;
  const limiar = produto === "GLP" ? P.limiarGas : P.limiarCombustivel;
  if (!referencia) {
    return { produto, preco, tipoPreco, data, referencia, razao: null, limiar, conferirUnidade: false,
             situacao: "sem_referencia", motivo: motivo ?? "sem coletas da ANP suficientes na semana, no município nem na UF" };
  }
  const razao = preco / referencia.mediana;
  const situacao: SituacaoAnp = razao < P.razaoMinima || razao > P.razaoMaxima ? "fora_de_escala"
    : razao >= limiar ? "acima" : "dentro";
  return { produto, preco, tipoPreco, data, referencia, razao, limiar,
           conferirUnidade: situacao === "acima" && razao >= P.razaoExtrema, situacao, motivo: null };
}

/** Lê os arquivos da UF que cobrem a data (o do ano dela e, perto da virada, o do ano vizinho) e compara. */
export async function carregarComparacaoAnp(produto: ProdutoAnp, preco: number, tipoPreco: "homologado" | "estimado",
                                            data: string, uf: string | null, ibge: string | null,
                                            sinal?: AbortSignal): Promise<ComparacaoAnp> {
  if (!uf || !/^[A-Za-z]{2}$/.test(uf)) return compararComAnp(produto, preco, tipoPreco, data, null, "a UF da unidade compradora não foi informada");
  const anos = new Set([data, desloca(data, -PARAMETROS_ANP.janelaDias), desloca(data, PARAMETROS_ANP.janelaDias)]
    .map((d) => Number(d.slice(0, 4))));
  const arquivos = (await Promise.all([...anos].map((a) => obterJson(urlAnp(uf, a), { sinal }))))
    .filter((x): x is ArquivoAnp => !!x && typeof x === "object" && (x as ArquivoAnp).tipo === "anp-precos");
  if (!arquivos.length) return compararComAnp(produto, preco, tipoPreco, data, null, "o Lumen ainda não publicou os preços da ANP dessa UF nesse período");
  return compararComAnp(produto, preco, tipoPreco, data, acharReferencia(arquivos, produto, ibge, data));
}

/** A data `dias` depois de `iso` (negativo para antes). */
function desloca(iso: string, dias: number): string {
  const d = new Date(`${iso}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + dias);
  return d.toISOString().slice(0, 10);
}
