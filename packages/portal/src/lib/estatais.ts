/**
 * Empresas estatais (ADR-034): o arquivo `economia/estatais.json`, publicado com os painéis, e as contas da
 * página sobre ele.
 *
 * Duas fontes, lado a lado e nunca somadas:
 * - as estatais com ações na bolsa, pelas demonstrações entregues à CVM (DFP): receita, custos, pessoal,
 *   impostos, compras de terceiros, investimentos; o controle conferido no Formulário de Referência;
 * - as estatais federais, pelo Programa de Dispêndios Globais da SEST: o orçamento aprovado e o realizado de
 *   cada rubrica (pessoal, materiais, serviços, tributos, investimentos), das não dependentes do Tesouro.
 */

import { normalizar } from "./busca";
import { obterJson } from "./feeds";
import { BASE_PAINEL, conferir } from "./paineis";

/** Um valor tirado das demonstrações: a conta, a descrição publicada e o valor em reais. */
export interface ValorConta {
  conta: string | null;
  descricao: string;
  valor: number | null;
  linhas?: [string, string, number][];
}

/** Classe do controle, conferida no FRE. */
export type ClasseControle = "publico_direto" | "publico_indireto" | "privado" | "sem_controlador" | "sem_fre";

/** Uma companhia aberta que se declara estatal no cadastro da CVM. */
export interface CompanhiaCvm {
  cnpj: string;
  nome: string;
  cd_cvm: string;
  setor: string;
  categoria: string;
  uf: string;
  municipio: string;
  controle_declarado: string;
  controle: {
    classe: ClasseControle;
    esfera: "federal" | "estadual" | "distrital" | "municipal" | null;
    controlada_por: string | null;
    controlada_por_nome: string | null;
    controladores: { nome: string; cnpj: string; percentual_ordinarias: number | null; percentual_total: number | null }[] | null;
    data_referencia: string | null;
  };
  modelo: "empresa" | "banco" | "seguradora" | "outro" | null;
  exercicios: Record<string, {
    documento: { link: string; versao: number; recebido_em: string } | null;
    bases: Record<string, string>;
    fim: string | null;
    valores: Record<string, ValorConta | null>;
  }>;
}

/** Uma rubrica do PDG num exercício: aprovado, realizado acumulado e até que mês. */
export interface ValorPdg {
  aprovado: number | null;
  realizado: number | null;
  ate_mes: number | null;
}

/** Uma empresa estatal federal do cadastro da SEST, com o PDG por exercício (vazio nas dependentes). */
export interface EmpresaSest {
  codigo_siest: string;
  sigla: string;
  nome: string;
  cnpj: string | null;
  dependente: boolean | null;
  grupo: string | null;
  setor: string | null;
  capital: string | null;
  natureza: string | null;
  ministerio: string | null;
  situacao: "ativa" | "inativa" | null;
  inativa_desde: string | null;
  na_cvm?: boolean;
  exercicios: Record<string, Record<string, ValorPdg | null>>;
}

/** O arquivo inteiro. */
export interface FeedEstatais {
  versao: 1;
  tipo: "estatais";
  gerado_em: string;
  urls: { cadastro: string; controle: string[]; dfp: Record<string, string> };
  coletado_em: { cadastro: string | null; controle: string | null; dfp: Record<string, string | null> };
  indicadores: { id: string; nome: string; demonstracao: string; definicao: string; saida: boolean }[];
  companhias: CompanhiaCvm[];
  federais: {
    fonte: string;
    urls: { pagina: string; identificacao: string; pdg: string };
    coletado_em: { identificacao: string | null; pdg: string | null };
    rubricas: { id: string; codigo: string; nome: string; definicao: string }[];
    empresas: EmpresaSest[];
  } | null;
}

/** Endereço do arquivo, ao lado dos painéis. */
export const urlEstatais = () => `${BASE_PAINEL}/economia/estatais.json`;

/** Lê e confere o arquivo; `null` quando ainda não foi publicado. */
export async function carregarEstatais(sinal?: AbortSignal): Promise<FeedEstatais | null> {
  const url = urlEstatais();
  const bruto = await obterJson(url, { sinal });
  return bruto === null ? null : conferir<FeedEstatais>(bruto, "estatais", url);
}

/** Rótulo da classe de controle. */
export const ROTULO_CONTROLE: Record<ClasseControle, string> = {
  publico_direto: "Controle público direto",
  publico_indireto: "Controle público indireto",
  sem_controlador: "Sem controlador declarado",
  privado: "Controle privado declarado",
  sem_fre: "Sem Formulário de Referência",
};

/** A companhia tem controle público conferido no FRE (direto ou por outra estatal)? */
export function controlePublico(c: CompanhiaCvm): boolean {
  return c.controle.classe === "publico_direto" || c.controle.classe === "publico_indireto";
}

/** Os exercícios que aparecem em alguma empresa da lista, do mais recente ao mais antigo. */
export function exerciciosDe(lista: { exercicios: Record<string, unknown> }[]): string[] {
  return [...new Set(lista.flatMap((x) => Object.keys(x.exercicios)))].sort().reverse();
}

/** O texto em que a busca procura: nome, sigla, CNPJ, grupo, setor, controlador. */
function textoBusca(x: CompanhiaCvm | EmpresaSest): string {
  if ("codigo_siest" in x) return normalizar(`${x.sigla} ${x.nome} ${x.cnpj ?? ""} ${x.grupo ?? ""} ${x.setor ?? ""} ${x.ministerio ?? ""}`);
  return normalizar(`${x.nome} ${x.cnpj} ${x.setor} ${x.uf} ${x.controle.controladores?.map((c) => c.nome).join(" ") ?? ""}`);
}

/** Filtra pelo termo (todas as palavras, sem acento) e por um predicado. */
export function filtrar<T extends CompanhiaCvm | EmpresaSest>(lista: T[], termo: string, aceita: (x: T) => boolean = () => true): T[] {
  const palavras = normalizar(termo).split(" ").filter(Boolean);
  return lista.filter((x) => aceita(x) && palavras.every((p) => textoBusca(x).includes(p)));
}

/** O realizado de uma rubrica do PDG no exercício, ou `null`. */
export function realizado(e: EmpresaSest, ano: string, rubrica: string): number | null {
  return e.exercicios[ano]?.[rubrica]?.realizado ?? null;
}

/** Quanto do aprovado foi realizado, em %; `null` sem os dois ou com aprovado zero. */
export function execucao(v: ValorPdg | null | undefined): number | null {
  if (!v || v.aprovado === null || v.realizado === null || v.aprovado === 0) return null;
  return (v.realizado / v.aprovado) * 100;
}

/** O valor de um indicador da companhia no exercício, como publicado (com o sinal da demonstração). */
export function valorCvm(c: CompanhiaCvm, ano: string, indicador: string): number | null {
  return c.exercicios[ano]?.valores[indicador]?.valor ?? null;
}

/** Um gasto publicado como negativo (custo, compra) mostrado como valor positivo de saída. */
export function comoGasto(valor: number | null, saida: boolean): number | null {
  if (valor === null) return null;
  return saida ? -valor : valor;
}

/** Ordena pela coluna (valores ausentes por último) e, no empate, pelo nome. */
export function ordenarPor<T>(lista: T[], valor: (x: T) => number | null, nome: (x: T) => string): T[] {
  return [...lista].sort((a, b) => {
    const va = valor(a);
    const vb = valor(b);
    if (va === null && vb === null) return nome(a).localeCompare(nome(b), "pt-BR");
    if (va === null) return 1;
    if (vb === null) return -1;
    return vb - va || nome(a).localeCompare(nome(b), "pt-BR");
  });
}

/** "dez" do mês 12, para "realizado até dez". */
export function mesAbreviado(n: number | null): string {
  return n ? ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"][n - 1] ?? "" : "";
}
