/**
 * Com o que o município gastou (ADR-040, adendo de 20/10/2026): a despesa liquidada de cada ano, sem as
 * intraorçamentárias, aberta de dois jeitos, e as somas de um período (um mandato).
 *
 * - **Por área**: a DCA, Anexo I-E, com as funções (`10 - Saúde`) e as subfunções (`10.301 - Atenção Básica`,
 *   `FU10 - Demais Subfunções`).
 * - **Por tipo de gasto**: a DCA, Anexo I-D, com os grupos de natureza (pessoal, juros, outras despesas correntes,
 *   investimentos, inversões, amortização) e os elementos (material de consumo, serviços de terceiros, obras…). Só
 *   entram as linhas `DO…` (as `DI…` são as intraorçamentárias). As modalidades somam o total do Anexo I-E ao
 *   centavo (São Sepé, 2015 e 2024).
 *
 * As somas recebem uma conversão por ano (reais de outro ano, por habitante); ano que a conversão não alcança fica
 * de fora do período, e a tela diz quantos anos entraram.
 */

import { ErroFeed } from "./validacao";

/** Uma abertura de um ano: o total e o valor de cada código, com o nome e o pai (o código do nível de cima). */
export interface Abertura {
  total: number;
  /** Nível 1 (função "10" ou grupo "3.1") e nível 2 ("10.301", "FU10"; "3.3|39"). */
  valores: Record<string, number>;
  nomes: Record<string, string>;
  /** O código de nível 1 de cada código de nível 2. */
  pai: Record<string, string>;
}

/** Uma linha das somas: o código, o nome, o total no período, o valor de cada ano e as linhas de baixo. */
export interface LinhaGasto {
  codigo: string;
  nome: string;
  total: number;
  porAno: Record<string, number>;
  filhos: LinhaGasto[];
}

/** As somas de um período: o total, os anos que entraram e as linhas, da maior para a menor. */
export interface SomaGastos {
  total: number;
  anos: string[];
  linhas: LinhaGasto[];
}

/** Os nomes dos grupos de natureza como a tela os mostra (o Anexo I-D os escreve com a classificação na frente). */
export const GRUPOS_NATUREZA: Record<string, string> = {
  "3.1": "Pessoal e encargos sociais",
  "3.2": "Juros e encargos da dívida",
  "3.3": "Outras despesas correntes (custeio)",
  "4.4": "Investimentos",
  "4.5": "Inversões financeiras",
  "4.6": "Amortização da dívida",
  "9.9": "Reserva de contingência",
};

/** Uma linha da resposta do SICONFI, só com os campos lidos. */
type Item = { coluna?: string; conta?: string; cod_conta?: string; valor?: number | null };

/** As linhas da despesa liquidada de uma resposta do SICONFI; `null` se o ano não foi entregue. */
function liquidadas(bruto: unknown): Item[] | null {
  const itens = (bruto as { items?: Item[] } | null)?.items;
  if (!Array.isArray(itens)) throw new ErroFeed("resposta do SICONFI sem items");
  if (itens.length === 0) return null;
  return itens.filter((i) => i.coluna === "Despesas Liquidadas" && typeof i.valor === "number");
}

/** O nome sem a classificação da frente: "3.3.90.39.00 - Outros Serviços…" → "Outros Serviços…". */
function semCodigo(conta: string): string {
  const i = conta.indexOf(" - ");
  return (i >= 0 ? conta.slice(i + 3) : conta).trim();
}

/** A conta sem parênteses e espaços repetidos (até 2016 a DCA escrevia "Despesas (Exceto Intraorçamentárias)"). */
function semParenteses(conta: string): string {
  return conta.replace(/[()]/g, "").replace(/\s+/g, " ").trim();
}

/** A abertura por área (DCA, Anexo I-E): funções e subfunções; `null` se o ano não foi entregue. */
export function lerPorFuncao(bruto: unknown): Abertura | null {
  const linhas = liquidadas(bruto);
  if (!linhas) return null;
  const a: Abertura = { total: 0, valores: {}, nomes: {}, pai: {} };
  let total: number | null = null;
  for (const l of linhas) {
    const conta = (l.conta ?? "").trim();
    const valor = l.valor as number;
    let m: RegExpExecArray | null;
    if (semParenteses(conta) === "Despesas Exceto Intraorçamentárias") total ??= valor;
    else if ((m = /^(\d{2}) - (.+)$/.exec(conta))) {
      a.valores[m[1]!] = valor;
      a.nomes[m[1]!] = m[2]!.trim();
    } else if ((m = /^(\d{2})\.(\d{3}) - (.+)$/.exec(conta))) {
      const codigo = `${m[1]}.${m[2]}`;
      a.valores[codigo] = valor;
      a.nomes[codigo] = m[3]!.trim();
      a.pai[codigo] = m[1]!;
    } else if ((m = /^FU(\d{2}) - /.exec(conta))) {
      const codigo = `FU${m[1]}`;
      a.valores[codigo] = valor;
      a.nomes[codigo] = "Demais subfunções";
      a.pai[codigo] = m[1]!;
    }
  }
  a.total = total ?? Object.entries(a.valores).filter(([c]) => !(c in a.pai)).reduce((s, [, v]) => s + v, 0);
  return a;
}

const NATUREZA = /^DO(\d)\.(\d)\.(\d\d)\.(\d\d)\.00\.00$/;

/**
 * A abertura por tipo de gasto (DCA, Anexo I-D): grupos de natureza e elementos, sem as intraorçamentárias;
 * `null` se o ano não foi entregue.
 *
 * O grupo soma as modalidades (`DO3.3.90.00…`, `DO3.3.50.00…`). Dentro de cada modalidade, os elementos
 * (`DO3.3.90.39…`) somam-se por código entre as modalidades; a modalidade sem elementos entra com o próprio nome
 * (as transferências a instituições privadas, por exemplo), e o que os elementos não cobrem fica em "Demais".
 */
export function lerPorNatureza(bruto: unknown): Abertura | null {
  const linhas = liquidadas(bruto);
  if (!linhas) return null;
  const a: Abertura = { total: 0, valores: {}, nomes: {}, pai: {} };
  const modalidades: { grupo: string; mm: string; nome: string; valor: number }[] = [];
  const elementos = new Map<string, { grupo: string; ee: string; nome: string; valor: number }[]>();
  for (const l of linhas) {
    const m = NATUREZA.exec(l.cod_conta ?? "");
    if (!m) continue;
    const [, cat, grp, mm, ee] = m as unknown as [string, string, string, string, string];
    const grupo = `${cat}.${grp}`;
    const valor = l.valor as number;
    if (grp === "0") continue;                                  // categoria (3.0, 4.0): soma dos grupos
    if (mm !== "00" && ee === "00") modalidades.push({ grupo, mm, nome: semCodigo(l.conta ?? ""), valor });
    else if (mm !== "00") {
      const chave = `${grupo}.${mm}`;
      elementos.set(chave, [...(elementos.get(chave) ?? []), { grupo, ee, nome: semCodigo(l.conta ?? ""), valor }]);
    }
  }
  const somar = (codigo: string, nome: string, pai: string | null, valor: number) => {
    a.valores[codigo] = (a.valores[codigo] ?? 0) + valor;
    a.nomes[codigo] ??= nome;
    if (pai) a.pai[codigo] = pai;
  };
  for (const mod of modalidades) {
    somar(mod.grupo, GRUPOS_NATUREZA[mod.grupo] ?? mod.grupo, null, mod.valor);
    a.total += mod.valor;
    const filhos = elementos.get(`${mod.grupo}.${mod.mm}`) ?? [];
    for (const e of filhos) somar(`${mod.grupo}|${e.ee}`, e.nome, mod.grupo, e.valor);
    const resto = mod.valor - filhos.reduce((s, e) => s + e.valor, 0);
    if (filhos.length === 0) somar(`${mod.grupo}|m${mod.mm}`, mod.nome, mod.grupo, mod.valor);
    else if (Math.abs(resto) > 0.5) somar(`${mod.grupo}|demais`, "Demais (sem elemento informado)", mod.grupo, resto);
  }
  return a;
}

/**
 * Soma as aberturas dos `anos` com a `converter` de cada ano (o valor da época vira o valor mostrado). O ano sem
 * abertura, ou que a conversão não alcança, fica de fora. As linhas vêm da maior para a menor, sem as zeradas.
 */
export function somarAberturas(anos: string[], porAno: Map<string, Abertura | null | undefined>,
  converter: (valor: number, ano: string) => number | null): SomaGastos {
  const usados: string[] = [];
  const valores = new Map<string, Record<string, number>>();
  const nomes: Record<string, string> = {};
  const pai: Record<string, string> = {};
  let total = 0;
  for (const ano of anos) {
    const a = porAno.get(ano);
    const t = a ? converter(a.total, ano) : null;
    if (!a || t === null) continue;
    usados.push(ano);
    total += t;
    for (const [codigo, v] of Object.entries(a.valores)) {
      const c = converter(v, ano) ?? 0;
      valores.set(codigo, { ...(valores.get(codigo) ?? {}), [ano]: c });
      nomes[codigo] ??= a.nomes[codigo] ?? codigo;
      if (a.pai[codigo]) pai[codigo] = a.pai[codigo]!;
    }
  }
  const linha = (codigo: string): LinhaGasto => {
    const porAnoLinha = valores.get(codigo) ?? {};
    return { codigo, nome: nomes[codigo] ?? codigo, total: Object.values(porAnoLinha).reduce((s, v) => s + v, 0),
             porAno: porAnoLinha, filhos: [] };
  };
  const ordenar = (ls: LinhaGasto[]) => ls.filter((l) => Math.abs(l.total) >= 0.005).sort((x, y) => y.total - x.total);
  const topo = new Map<string, LinhaGasto>();
  for (const codigo of valores.keys()) if (!pai[codigo]) topo.set(codigo, linha(codigo));
  for (const codigo of valores.keys()) {
    const p = pai[codigo];
    if (p && topo.has(p)) topo.get(p)!.filhos.push(linha(codigo));
  }
  const linhas = ordenar([...topo.values()]);
  for (const l of linhas) l.filhos = ordenar(l.filhos);
  return { total, anos: usados, linhas };
}

/** A variação de `b` para `a` em %, ou `null` sem base. */
export function variacao(a: number, b: number): number | null {
  return b ? (a / b - 1) * 100 : null;
}

/** As receitas de um ano (DCA, Anexo I-C) em grupos, e as deduções da receita (a retenção para o FUNDEB e outras). */
export interface ReceitasAno extends Abertura {
  deducoes: number;
}

/** Os grupos de receita, na ordem da tela. */
export const GRUPOS_RECEITA: Record<string, string> = {
  impostos: "Impostos, taxas e contribuições de melhoria (próprios)",
  contribuicoes: "Contribuições (previdência própria, iluminação pública)",
  uniao: "Transferências da União (FPM, SUS, FNDE…)",
  estado: "Transferências do estado (ICMS, IPVA…)",
  fundeb: "FUNDEB",
  outras_transferencias: "Outras transferências correntes",
  outras_correntes: "Outras receitas correntes (patrimonial, serviços…)",
  capital: "Receitas de capital (operações de crédito, transferências de capital…)",
};

/**
 * As receitas realizadas de um ano em grupos (DCA, Anexo I-C, "Receitas Brutas Realizadas"), sem as
 * intraorçamentárias; `null` se o ano não foi entregue.
 *
 * O ementário da receita mudou em 2018, e o formato do código diz qual vale: até 2017, `RO1.7.2.1.00.00.00` é a
 * transferência da União, `1.7.2.2` a do estado e `1.7.2.4` (multigovernamentais) o FUNDEB; de 2018 em diante,
 * `RO1.7.1.0.00.0.0`, `1.7.2` e `1.7.5`. Os grupos somam as receitas correntes (1) e de capital (2), ao centavo
 * (São Sepé, 2015, 2017, 2018 e 2024). As deduções (a retenção para o FUNDEB e outras) ficam à parte.
 */
export function lerReceitas(bruto: unknown): ReceitasAno | null {
  const itens = (bruto as { items?: Item[] } | null)?.items;
  if (!Array.isArray(itens)) throw new ErroFeed("resposta do SICONFI sem items");
  if (itens.length === 0) return null;
  const realizadas = itens.filter((i) => i.coluna === "Receitas Brutas Realizadas" && typeof i.valor === "number");
  const novo = realizadas.some((i) => /^RO\d\.\d\.\d\.\d\.\d\d\.\d\.\d$/.test(i.cod_conta ?? ""));
  const codigo = (prefixo: string) => {
    const partes = prefixo.split(".");
    return `RO${[...partes, ...Array(4 - partes.length).fill("0")].join(".")}.${novo ? "00.0.0" : "00.00.00"}`;
  };
  const valor = (prefixo: string) => realizadas.find((i) => i.cod_conta === codigo(prefixo))?.valor ?? 0;
  const correntes = valor("1");
  const capital = valor("2");
  const transferencias = valor("1.7");
  const uniao = valor(novo ? "1.7.1" : "1.7.2.1");
  const estado = valor(novo ? "1.7.2" : "1.7.2.2");
  const fundeb = valor(novo ? "1.7.5" : "1.7.2.4");
  const impostos = valor("1.1");
  const contribuicoes = valor("1.2");
  const valores: Record<string, number> = {
    impostos, contribuicoes, uniao, estado, fundeb, outras_transferencias: transferencias - uniao - estado - fundeb,
    outras_correntes: correntes - impostos - contribuicoes - transferencias, capital,
  };
  const deducoes = itens.filter((i) => /Dedu/.test(i.coluna ?? "") && typeof i.valor === "number"
    && (i.cod_conta === codigo("1") || i.cod_conta === codigo("2"))).reduce((s, i) => s + (i.valor as number), 0);
  return { total: correntes + capital, valores, nomes: { ...GRUPOS_RECEITA }, pai: {}, deducoes };
}
