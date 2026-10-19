/**
 * Comparação de preço de um item com o que outros órgãos pagaram pelo mesmo item de catálogo (ADR-036; regra
 * A-01 do DOC-07, aplicada sob demanda no modal da contratação).
 *
 * A referência vem da pesquisa de preços do Compras.gov.br (dados abertos), que reúne as compras feitas pelo
 * sistema federal, de órgãos federais, estaduais e municipais, com o preço unitário de cada item pelo código do
 * catálogo (CATMAT para material, CATSER para serviço). A API não libera a leitura por outro site (CORS); o
 * portal a pede pelo próprio endereço (`/api/precos/...`), que o Vercel repassa à fonte sem guardar nada.
 *
 * A conta segue o DOC-07: mediana, desvio absoluto mediano (MAD) e o escore robusto
 * `0,6745 × (preço − mediana) ÷ MAD`, com o mínimo de 30 compras comparáveis e o disparo em 3,5. Os parâmetros
 * são os iniciais, não calibrados. O resultado diz onde o preço fica entre as compras comparáveis; não é
 * conclusão sobre a compra: a especificação, a quantidade, o lugar e o prazo podem justificar a diferença.
 */

import { normalizar } from "./busca";
import { ErroFeed } from "./validacao";

/** O caminho do portal que o Vercel repassa à pesquisa de preços (`vercel.json`). */
export const API_PRECOS = "/api/precos";

/** A fonte, para o link "ver na fonte" e para a documentação. */
export const FONTE_PRECOS = "https://dadosabertos.compras.gov.br/modulo-pesquisa-preco";

/** Parâmetros da comparação (DOC-07, A-01): iniciais, não calibrados. */
export const PARAMETROS_PRECO = {
  minimoComparaveis: 30,
  escoreDisparo: 3.5,
  razaoForaDeEscala: 10,
  janelaDias: 365,
  paginas: 4,
  tamanhoPagina: 500,
} as const;

/** Uma compra da pesquisa de preços, já lida. Fornecedor pessoa física fica sem nome nem documento. */
export interface CompraComparavel {
  idCompra: string | null;
  data: string | null;
  orgao: string | null;
  municipio: string | null;
  uf: string | null;
  esfera: string | null;
  quantidade: number | null;
  unidade: string | null;
  capacidade: number | null;
  preco: number | null;
  fornecedor: { cnpj: string; nome: string | null } | null;
}

/** Onde o preço do item fica entre as compras comparáveis. */
export type SituacaoPreco = "acima" | "abaixo" | "dentro" | "poucas" | "fora_de_escala" | "sem_comparaveis";

/** O resultado da comparação, com a referência inteira para quem quiser conferir. */
export interface ComparacaoPreco {
  preco: number;
  tipoPreco: "homologado" | "estimado";
  de: string;
  ate: string;
  recebidos: number;
  comparaveis: CompraComparavel[];
  descartados: { outraUnidade: number; totalComoUnitario: number; semPreco: number; propriaCompra: number };
  unidadeMaisComum: string | null;
  n: number;
  minimo: number | null;
  q1: number | null;
  mediana: number | null;
  q3: number | null;
  maximo: number | null;
  escore: number | null;
  razao: number | null;
  /** Fração das compras comparáveis com preço menor que o do item (0 a 1). */
  acimaDe: number | null;
  situacao: SituacaoPreco;
}

/** O que a comparação precisa saber do item e da compra. */
export interface ItemParaComparar {
  catalogo: string;
  material: boolean;
  unidade: string | null;
  preco: number;
  tipoPreco: "homologado" | "estimado";
  data: string;               // AAAA-MM-DD: fim da janela
  uasg: string | null;        // para tirar a própria compra da referência
  numeroCompra: string | null;
  ano: number;
}

/** Um objeto da resposta da API, ainda sem conferir. */
type Bruto = Record<string, unknown>;
const texto = (v: unknown): string | null => (typeof v === "string" && v.trim() ? v.trim() : null);
const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);

/** As compras da resposta da API (`resultado`), sem conferir mais que o tipo de cada campo. */
export function lerCompras(bruto: unknown): CompraComparavel[] {
  const lista = bruto && typeof bruto === "object" ? (bruto as Bruto).resultado : null;
  if (!Array.isArray(lista)) return [];
  return lista.filter((x): x is Bruto => !!x && typeof x === "object").map((x) => {
    const ni = texto(x.niFornecedor);
    // idCompra de material vem como número maior que o inteiro seguro do JavaScript: o do item (texto) o traz inteiro
    const id = texto(x.idCompra) ?? texto(x.idCompraItem)?.slice(0, 17) ?? null;
    const capacidade = num(x.capacidadeUnidadeFornecimento);
    return {
      idCompra: id,
      data: texto(x.dataResultado) ?? texto(x.dataCompra),
      orgao: texto(x.nomeOrgao) ?? texto(x.nomeUasg),
      municipio: texto(x.municipio),
      uf: texto(x.estado),
      esfera: texto(x.esfera),
      quantidade: num(x.quantidade),
      unidade: texto(x.nomeUnidadeFornecimento) ?? texto(x.nomeUnidadeMedida) ?? texto(x.siglaUnidadeFornecimento)
        ?? texto(x.siglaUnidadeMedida),
      capacidade: capacidade && capacidade > 0 ? capacidade : null,
      preco: num(x.precoUnitario),
      fornecedor: ni && ni.replace(/\D/g, "").length === 14 ? { cnpj: ni.replace(/\D/g, ""), nome: texto(x.nomeFornecedor) } : null,
    };
  });
}

const SIGLAS: Record<string, string> = { un: "unidade", und: "unidade", unid: "unidade", m2: "metro quadrado",
  m3: "metro cubico", m: "metro", l: "litro", kg: "quilograma", h: "hora", cx: "caixa", pct: "pacote", sv: "servico" };

/** A unidade normalizada, com as siglas mais comuns por extenso ("UN" → "unidade"). */
function unidadeNormal(u: string | null): string {
  const n = normalizar(u ?? "");
  return SIGLAS[n] ?? n;
}

/** A unidade da compra é a do item? Mesmo nome (ou o nome do item começa por ela) e, se houver, a mesma capacidade. */
export function mesmaUnidade(unidadeItem: string | null, c: Pick<CompraComparavel, "unidade" | "capacidade">): boolean {
  const a = unidadeNormal(unidadeItem);
  const b = unidadeNormal(c.unidade);
  if (!a || !b) return false;
  if (a !== b && !a.startsWith(`${b} `)) return false;
  if (c.capacidade === null) return true;
  const numeros = (unidadeItem ?? "").match(/\d+(?:[.,]\d+)?/g)?.map((x) => Number(x.replace(",", "."))) ?? [];
  return numeros.some((x) => Math.abs(x - c.capacidade!) < 1e-9);
}

/** Unidade que se divide (metro, litro, quilo, hora, mês): quantidade 1 nela costuma ser o total lançado como unitário. */
const FRACIONAVEL = /\b(metro|metros|quadrado|cubico|quilometro|km|litro|litros|ml|quilo|quilograma|quilogramas|grama|gramas|tonelada|toneladas|hora|horas|dia|dias|diaria|diarias|mes|meses)\b/;

/** A compra é a própria compra do item? Pelo número no sistema federal: UASG, modalidade, número (5 dígitos) e ano. */
function daPropriaCompra(c: CompraComparavel, item: ItemParaComparar): boolean {
  if (!c.idCompra || !item.uasg || !item.numeroCompra) return false;
  const numero = item.numeroCompra.split("/")[0]!.replace(/\D/g, "");
  if (!numero) return false;
  return c.idCompra.startsWith(item.uasg) && c.idCompra.endsWith(`${numero.padStart(5, "0").slice(-5)}${item.ano}`);
}

/** Quantil por interpolação linear (o tipo 7, o mesmo das planilhas). `ordenados` em ordem crescente. */
function quantil(ordenados: number[], q: number): number {
  const pos = (ordenados.length - 1) * q;
  const base = Math.floor(pos);
  const resto = pos - base;
  const prox = ordenados[base + 1];
  return prox === undefined ? ordenados[base]! : ordenados[base]! + resto * (prox - ordenados[base]!);
}

/**
 * Escore robusto do DOC-07: `0,6745 × (x − mediana) ÷ MAD`. Quando mais da metade dos preços é igual (MAD zero),
 * usa o desvio absoluto médio (`(x − mediana) ÷ (1,2533 × média |x − mediana|)`), como é usual nesse caso;
 * `null` se todos os preços são iguais.
 */
export function escoreRobusto(x: number, ordenados: number[]): number | null {
  const med = quantil(ordenados, 0.5);
  const desvios = ordenados.map((v) => Math.abs(v - med)).sort((a, b) => a - b);
  const mad = quantil(desvios, 0.5);
  if (mad > 0) return (0.6745 * (x - med)) / mad;
  const medio = desvios.reduce((s, v) => s + v, 0) / desvios.length;
  return medio > 0 ? (x - med) / (1.253314 * medio) : null;
}

/** Compara o preço do item com as compras recebidas: filtra as comparáveis e calcula a posição dele. */
export function compararPreco(item: ItemParaComparar, compras: CompraComparavel[], de: string): ComparacaoPreco {
  const descartados = { outraUnidade: 0, totalComoUnitario: 0, semPreco: 0, propriaCompra: 0 };
  const unidades = new Map<string, number>();
  const comparaveis: CompraComparavel[] = [];
  for (const c of compras) {
    if (c.preco === null || c.preco <= 0) { descartados.semPreco++; continue; }
    if (daPropriaCompra(c, item)) { descartados.propriaCompra++; continue; }
    if (!mesmaUnidade(item.unidade, c)) {
      descartados.outraUnidade++;
      const u = `${c.unidade ?? "sem unidade"}${c.capacidade ? ` ${c.capacidade}` : ""}`;
      unidades.set(u, (unidades.get(u) ?? 0) + 1);
      continue;
    }
    if ((c.quantidade ?? 0) <= 1 && FRACIONAVEL.test(unidadeNormal(c.unidade))) { descartados.totalComoUnitario++; continue; }
    comparaveis.push(c);
  }
  comparaveis.sort((a, b) => (b.data ?? "").localeCompare(a.data ?? ""));
  const precos = comparaveis.map((c) => c.preco!).sort((a, b) => a - b);
  const n = precos.length;
  const mediana = n ? quantil(precos, 0.5) : null;
  const razao = mediana ? item.preco / mediana : null;
  const escore = n ? escoreRobusto(item.preco, precos) : null;
  const P = PARAMETROS_PRECO;
  const situacao: SituacaoPreco = n === 0 ? "sem_comparaveis"
    : razao !== null && (razao > P.razaoForaDeEscala || razao < 1 / P.razaoForaDeEscala) ? "fora_de_escala"
    : n < P.minimoComparaveis ? "poucas"
    : escore !== null && escore >= P.escoreDisparo ? "acima"
    : escore !== null && escore <= -P.escoreDisparo ? "abaixo"
    : "dentro";
  return {
    preco: item.preco, tipoPreco: item.tipoPreco, de, ate: item.data, recebidos: compras.length, comparaveis, descartados,
    unidadeMaisComum: [...unidades.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] ?? null,
    n, minimo: n ? precos[0]! : null, q1: n ? quantil(precos, 0.25) : null, mediana, q3: n ? quantil(precos, 0.75) : null,
    maximo: n ? precos[n - 1]! : null, escore, razao,
    acimaDe: n ? precos.filter((p) => p < item.preco).length / n : null,
    situacao,
  };
}

/** A data `dias` antes de `iso` (AAAA-MM-DD). */
function diasAntes(iso: string, dias: number): string {
  const d = new Date(`${iso}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() - dias);
  return d.toISOString().slice(0, 10);
}

/** O endereço de uma página da pesquisa de preços, pelo caminho do portal. */
export function urlPrecos(item: Pick<ItemParaComparar, "catalogo" | "material">, de: string, ate: string, pagina: number): string {
  const codigo = item.material ? `tipo=codigoItemCatalogo&codigo=${item.catalogo}` : `codigoItemCatalogo=${item.catalogo}`;
  return `${API_PRECOS}/${item.material ? "material" : "servico"}?pagina=${pagina}&tamanhoPagina=${PARAMETROS_PRECO.tamanhoPagina}` +
    `&${codigo}&dataCompraInicio=${de}&dataCompraFim=${ate}`;
}

/** GET na pesquisa de preços. */
async function pedir(url: string, sinal?: AbortSignal): Promise<Bruto> {
  let r: Response;
  try {
    r = await fetch(url, { signal: sinal, headers: { Accept: "application/json" } });
  } catch (erro) {
    if ((erro as Error).name === "AbortError") throw erro;
    throw new ErroFeed("a pesquisa de preços do Compras.gov.br não respondeu");
  }
  if (!r.ok) throw new ErroFeed(`a pesquisa de preços respondeu ${r.status}`);
  const corpo = await r.json().catch(() => null);
  if (!corpo || typeof corpo !== "object") throw new ErroFeed("a pesquisa de preços respondeu algo que não é JSON");
  return corpo as Bruto;
}

/** Pede as compras do código nos 12 meses até a data do item (até 4 páginas de 500) e compara. */
export async function carregarComparacao(item: ItemParaComparar, sinal?: AbortSignal): Promise<ComparacaoPreco> {
  const de = diasAntes(item.data, PARAMETROS_PRECO.janelaDias);
  const primeira = await pedir(urlPrecos(item, de, item.data, 1), sinal);
  const total = Math.min(num(primeira.totalPaginas) ?? 1, PARAMETROS_PRECO.paginas);
  const outras = await Promise.all(
    Array.from({ length: Math.max(total - 1, 0) }, (_, i) => pedir(urlPrecos(item, de, item.data, i + 2), sinal)));
  const compras = [primeira, ...outras].flatMap(lerCompras);
  return compararPreco(item, compras, de);
}
