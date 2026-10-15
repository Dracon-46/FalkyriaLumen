/**
 * Acesso aos dados dos painéis de contratações e de conformidade (ADR-028).
 *
 * Os arquivos são gerados por `lumen painel publicar` a partir do PNCP e do
 * extrato de entregas do SICONFI e publicados no GitHub Pages do repositório.
 * A base é `NEXT_PUBLIC_DADOS_PAINEL`, fixada no build; sem ela, o endereço
 * público do Pages. Os arquivos mudam uma vez por dia: o navegador revalida
 * (`no-cache`) e recebe 304 quando nada mudou.
 */

import { normalizar } from "./busca";
import { obterJson } from "./feeds";
import { ErroFeed } from "./validacao";

/** Raiz dos dados dos painéis, sem barra final. Variável vazia vale como ausente. */
export const BASE_PAINEL = (process.env.NEXT_PUBLIC_DADOS_PAINEL || "https://dracon-46.github.io/FalkyriaLumen").replace(
  /\/$/,
  "",
);

/** Código IBGE de ente aceito nos caminhos: União (1), UF (2 dígitos) ou município (7 dígitos). */
const CODIGO = /^(1|\d{2}|\d{7})$/;
const UF = /^[A-Z]{2}$/;

/** Barra códigos fora do padrão antes do `fetch`: a URL da página vira caminho de arquivo. */
export function codigoSeguro(codigo: string): string {
  if (!CODIGO.test(codigo)) throw new ErroFeed(`código de ente inválido: ${codigo}`);
  return codigo;
}

/** Endereço de cada arquivo dos painéis; código, CNPJ e UF passam pela validação antes de virar caminho. */
export const urlsPainel = {
  indice: () => `${BASE_PAINEL}/indice.json`,
  entes: () => `${BASE_PAINEL}/entes.json`,
  contratacoesPanorama: () => `${BASE_PAINEL}/contratacoes/panorama.json`,
  contratacoesEnte: (codigo: string) => `${BASE_PAINEL}/contratacoes/ente/${codigoSeguro(codigo)}.json`,
  contratacoesOrgao: (cnpj: string) => {
    if (!/^\d{14}$/.test(cnpj)) throw new ErroFeed(`CNPJ inválido: ${cnpj}`);
    return `${BASE_PAINEL}/contratacoes/orgao/${cnpj}.json`;
  },
  conformidadePanorama: () => `${BASE_PAINEL}/conformidade/panorama.json`,
  conformidadeUf: (uf: string) => {
    if (!UF.test(uf)) throw new ErroFeed(`UF inválida: ${uf}`);
    return `${BASE_PAINEL}/conformidade/uf/${uf}.json`;
  },
  conformidadeEnte: (codigo: string) => `${BASE_PAINEL}/conformidade/ente/${codigoSeguro(codigo)}.json`,
};

// ------------------------------------------------------------------------------------------ tipos

/** Tipo de ente, como o Python grava em `ente.tipo`. */
export type TipoEnte = "uniao" | "estado" | "df" | "municipio";

/** Identificação do ente no topo de cada arquivo: código IBGE, nome, UF, tipo e população. */
export interface EnteResumo {
  codigo: string;
  nome: string;
  uf: string | null;
  tipo: TipoEnte | null;
  populacao: number | null;
}

/** Linha do cadastro para a busca. */
export interface EnteBusca {
  codigo: string;
  nome: string;
  uf: string | null;
  esfera: string | null;
  populacao: number | null;
}

/** Dias do PNCP somados no painel: o primeiro, o último, quantos e os que faltam entre eles. */
export interface Cobertura {
  de: string | null;
  ate: string | null;
  dias: number;
  faltando: string[];
}

/** Contagens e somas de um recorte: processos, valor estimado, contratos e valor global. */
export interface TotaisContratacoes {
  processos: number;
  valor_estimado: number;
  processos_sem_valor: number;
  contratos: number;
  valor_contratos: number;
}

/** Seções comuns ao panorama, a um ente e a um órgão (`_secoes` no Python). */
export interface SecoesContratacoes {
  totais: TotaisContratacoes & { orgaos: number; fornecedores: number };
  meses: (TotaisContratacoes & { mes: string })[];
  modalidades: { codigo: number | null; nome: string; processos: number; valor_estimado: number }[];
  orgaos: (TotaisContratacoes & { cnpj: string; nome: string | null })[];
  fornecedores: { cnpj: string; nome: string | null; contratos: number; valor: number }[];
  pessoas_fisicas: { contratos: number; valor: number };
  recentes: {
    data: string;
    chave: string;
    orgao: string | null;
    modalidade: string | null;
    objeto: string | null;
    valor_estimado: number | null;
    situacao: string | null;
    link: string | null;
  }[];
  contratos_recentes: {
    data: string;
    chave: string;
    orgao: string | null;
    fornecedor: string | null;
    fornecedor_cnpj: string | null;
    tipo_pessoa: string | null;
    valor: number | null;
    instrumento: string | null;
    objeto: string | null;
    link: string | null;
  }[];
}

/** Arquivo `contratacoes/ente/<código>.json`; o de um estado traz também os municípios da UF. */
export interface ContratacoesEnte extends SecoesContratacoes {
  versao: 1;
  tipo: "contratacoes-ente";
  gerado_em: string;
  cobertura: Cobertura;
  ente: EnteResumo;
  municipios?: (TotaisContratacoesSimples & { codigo: string; nome: string })[];
}

/** Arquivo `contratacoes/orgao/<CNPJ>.json`: um órgão, com o ente a que pertence (ou null sem esfera). */
export interface ContratacoesOrgao extends Omit<SecoesContratacoes, "orgaos"> {
  versao: 1;
  tipo: "contratacoes-orgao";
  gerado_em: string;
  cobertura: Cobertura;
  orgao: { cnpj: string; nome: string | null; esfera: string | null };
  ente: { codigo: string; nome: string; uf: string | null; tipo: TipoEnte | null } | null;
}

/** Totais de um município na tabela da UF. */
export interface TotaisContratacoesSimples {
  processos: number;
  valor_estimado: number;
  contratos: number;
  valor_contratos: number;
}

/** Arquivo `contratacoes/panorama.json`: o Brasil, por esfera e por UF. */
export interface ContratacoesPanorama extends SecoesContratacoes {
  versao: 1;
  tipo: "contratacoes-panorama";
  gerado_em: string;
  cobertura: Cobertura;
  esferas: (TotaisContratacoes & { esfera: string; nome: string })[];
  sem_ente: TotaisContratacoes;
  ufs: {
    uf: string;
    estado: TotaisContratacoes;
    municipios: TotaisContratacoes;
    municipios_com_publicacao: number;
    municipios_no_cadastro: number;
  }[];
  entes_com_publicacao: number;
}

/** Resultado de uma obrigação, na nomenclatura de `ResultadoCriterio`. */
export type Resultado = "cumpre" | "cumpre_parcialmente" | "nao_cumpre" | "indeterminado";

/** Quantas obrigações em cada resultado e a fração entregue no prazo. */
export interface ResumoConformidade {
  cumpre: number;
  cumpre_parcialmente: number;
  nao_cumpre: number;
  indeterminado: number;
  avaliaveis: number;
  /** Fração entregue no prazo entre as obrigações com resultado determinado; null sem nenhuma. */
  no_prazo: number | null;
}

/** Uma obrigação avaliada: rótulo, prazo, data da entrega, resultado, dispositivo e, se indeterminada, o motivo. */
export interface Obrigacao {
  exercicio: number;
  criterio: string;
  periodo: string;
  rotulo: string;
  poder: string | null;
  resultado: Resultado;
  rotulo_resultado: string;
  prazo: string | null;
  entregue_em: string | null;
  dispositivo: string;
  motivo: string | null;
}

/** Arquivo `conformidade/ente/<código>.json`. */
export interface ConformidadeEnte {
  versao: 1;
  tipo: "conformidade-ente";
  gerado_em: string;
  avaliado_em: string;
  coletado_em: string | null;
  ente: EnteResumo;
  coleta: Record<string, boolean>;
  resumo: ResumoConformidade;
  obrigacoes: Obrigacao[];
}

/** Arquivo `conformidade/uf/<sigla>.json`: os entes avaliados da UF, por nome. */
export interface ConformidadeUf {
  versao: 1;
  tipo: "conformidade-uf";
  gerado_em: string;
  avaliado_em: string;
  coletado_em: string | null;
  uf: string;
  entes: (ResumoConformidade & { codigo: string; nome: string; tipo: TipoEnte | null; populacao: number | null })[];
}

/** Arquivo `conformidade/panorama.json`: o Brasil, por obrigação e por UF. */
export interface ConformidadePanorama {
  versao: 1;
  tipo: "conformidade-panorama";
  gerado_em: string;
  avaliado_em: string;
  entes: number;
  brasil: ResumoConformidade;
  criterios: (ResumoConformidade & { criterio: string; nome: string })[];
  ufs: (ResumoConformidade & { uf: string; entes: number; coletado_em: string | null })[];
}

// ------------------------------------------------------------------------------------------ leitura

/** Confere versão e tipo de um arquivo dos painéis; o resto do formato é o que o Python grava e testa. */
export function conferir<T>(bruto: unknown, tipo: string, url: string): T {
  const o = bruto as { versao?: unknown; tipo?: unknown } | null;
  if (!o || typeof o !== "object") throw new ErroFeed(`${url}: conteúdo inesperado`);
  if (o.versao !== 1) throw new ErroFeed(`${url}: versão ${String(o.versao)} não suportada`);
  if (o.tipo !== tipo) throw new ErroFeed(`${url}: tipo ${String(o.tipo)}, esperado ${tipo}`);
  return bruto as T;
}

/** Lê e confere um arquivo dos painéis; `null` quando ele não existe. */
async function ler<T>(url: string, tipo: string, sinal?: AbortSignal): Promise<T | null> {
  const bruto = await obterJson(url, { sinal });
  return bruto === null ? null : conferir<T>(bruto, tipo, url);
}

/** Panorama de contratações do Brasil. */
export const carregarContratacoesPanorama = (sinal?: AbortSignal) =>
  ler<ContratacoesPanorama>(urlsPainel.contratacoesPanorama(), "contratacoes-panorama", sinal);
/** Contratações de um ente pelo código IBGE; `null` sem publicação no período. */
export const carregarContratacoesEnte = (codigo: string, sinal?: AbortSignal) =>
  ler<ContratacoesEnte>(urlsPainel.contratacoesEnte(codigo), "contratacoes-ente", sinal);
/** Contratações de um órgão pelo CNPJ; `null` sem publicação no período. */
export const carregarContratacoesOrgao = (cnpj: string, sinal?: AbortSignal) =>
  ler<ContratacoesOrgao>(urlsPainel.contratacoesOrgao(cnpj), "contratacoes-orgao", sinal);
/** Panorama da conformidade no Brasil. */
export const carregarConformidadePanorama = (sinal?: AbortSignal) =>
  ler<ConformidadePanorama>(urlsPainel.conformidadePanorama(), "conformidade-panorama", sinal);
/** Conformidade dos entes de uma UF. */
export const carregarConformidadeUf = (uf: string, sinal?: AbortSignal) =>
  ler<ConformidadeUf>(urlsPainel.conformidadeUf(uf), "conformidade-uf", sinal);
/** Conformidade de um ente; `null` se ainda não avaliado. */
export const carregarConformidadeEnte = (codigo: string, sinal?: AbortSignal) =>
  ler<ConformidadeEnte>(urlsPainel.conformidadeEnte(codigo), "conformidade-ente", sinal);

let cacheEntes: Promise<EnteBusca[]> | null = null;

/** Cadastro de entes para a busca, baixado uma vez por visita; lista vazia se o arquivo não existe. */
export function carregarEntes(): Promise<EnteBusca[]> {
  if (!cacheEntes) {
    cacheEntes = obterJson(urlsPainel.entes()).then((bruto) => lerEntes(bruto));
    cacheEntes.catch(() => {
      cacheEntes = null;
    });
  }
  return cacheEntes;
}

/** Converte o `entes.json` (linhas em lista, na ordem de `colunas`) em objetos. */
export function lerEntes(bruto: unknown): EnteBusca[] {
  const o = bruto as { versao?: number; colunas?: string[]; entes?: unknown[][] } | null;
  if (!o || o.versao !== 1 || !Array.isArray(o.entes) || !Array.isArray(o.colunas)) return [];
  const colunas = o.colunas;
  const ic = colunas.indexOf("codigo");
  const inome = colunas.indexOf("nome");
  const iuf = colunas.indexOf("uf");
  const ie = colunas.indexOf("esfera");
  const ip = colunas.indexOf("populacao");
  return o.entes
    .filter((l) => Array.isArray(l) && typeof l[ic] === "string")
    .map((l) => ({
      codigo: l[ic] as string,
      nome: (l[inome] as string) ?? (l[ic] as string),
      uf: (l[iuf] as string | null) ?? null,
      esfera: (l[ie] as string | null) ?? null,
      populacao: (l[ip] as number | null) ?? null,
    }));
}

// ------------------------------------------------------------------------------------------ busca

/** Tipo do ente pelo código: União (1), DF (53), estado (2 dígitos) ou município (7 dígitos). */
export function tipoDoCodigo(codigo: string): TipoEnte | null {
  if (codigo === "1") return "uniao";
  if (codigo === "53") return "df";
  if (/^\d{2}$/.test(codigo)) return "estado";
  if (/^\d{7}$/.test(codigo)) return "municipio";
  return null;
}

/**
 * Até `limite` entes cujo nome casa com o termo (sem acento e sem caixa), ou a sigla da UF: União e estados
 * primeiro, depois municípios; quem começa com o termo antes de quem só o contém; empate pelo maior.
 */
export function buscarEntes(termo: string, entes: EnteBusca[], limite = 12): EnteBusca[] {
  const t = normalizar(termo);
  if (!t) return [];
  const pontuados: { e: EnteBusca; p: number }[] = [];
  for (const e of entes) {
    const nome = normalizar(e.nome);
    const sigla = (e.uf ?? "").toLowerCase();
    const tipo = tipoDoCodigo(e.codigo);
    let p: number;
    if (nome.startsWith(t)) p = 0;
    else if (nome.includes(t)) p = 2;
    else if (tipo !== "municipio" && sigla === t) p = 0;
    else continue;
    if (tipo !== "municipio") p -= 1;
    pontuados.push({ e, p });
  }
  pontuados.sort((a, b) => a.p - b.p || (b.e.populacao ?? 0) - (a.e.populacao ?? 0) || a.e.nome.localeCompare(b.e.nome));
  return pontuados.slice(0, limite).map((x) => x.e);
}

/** Descrição curta do ente: "União", "Estado", "Distrito Federal" ou "Município · SP". */
export function descreverEnte(e: { codigo: string; uf: string | null }): string {
  const tipo = tipoDoCodigo(e.codigo);
  if (tipo === "uniao") return "União";
  if (tipo === "estado") return "Estado";
  if (tipo === "df") return "Distrito Federal";
  return e.uf ? `Município · ${e.uf}` : "Município";
}

// ------------------------------------------------------------------------------------------ formato

const reais = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 2 });
const reaisCompacto = new Intl.NumberFormat("pt-BR", { notation: "compact", maximumFractionDigits: 1 });

/** 1234.5 → "R$ 1.234,50"; ausente → "—". */
export function moeda(valor: number | null | undefined): string {
  return valor === null || valor === undefined ? "—" : reais.format(valor);
}

/** 1500000 → "R$ 1,5 mi"; ausente → "—". */
export function moedaCompacta(valor: number | null | undefined): string {
  if (valor === null || valor === undefined) return "—";
  return `R$ ${reaisCompacto.format(valor)}`;
}

/** "2026-03" → "mar/2026". */
export function mesCurto(mes: string): string {
  const nomes = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
  const [a, m] = mes.split("-");
  const i = Number(m) - 1;
  return i >= 0 && i < 12 ? `${nomes[i]}/${a}` : mes;
}

/** "2026-10-13" → "13/10/2026"; ISO com hora → só a data, no horário de Brasília. */
export function dataCurta(iso: string | null | undefined): string {
  if (!iso) return "—";
  if (/^\d{4}-\d{2}-\d{2}$/.test(iso)) {
    const [a, m, d] = iso.split("-");
    return `${d}/${m}/${a}`;
  }
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? "—"
    : new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric", timeZone: "America/Sao_Paulo" }).format(d);
}

/** Topo "redondo" do eixo de um gráfico: 1, 2 ou 5 vezes uma potência de 10, no maior valor ou acima. */
export function topoDoEixo(maximo: number): number {
  if (!(maximo > 0)) return 1;
  const potencia = 10 ** Math.floor(Math.log10(maximo));
  for (const m of [1, 2, 5]) if (m * potencia >= maximo) return m * potencia;
  return 10 * potencia;
}

/** CNPJ com máscara: 07854402000100 → 07.854.402/0001-00. */
export function cnpj(texto: string | null | undefined): string {
  if (!texto || !/^\d{14}$/.test(texto)) return texto ?? "—";
  return `${texto.slice(0, 2)}.${texto.slice(2, 5)}.${texto.slice(5, 8)}/${texto.slice(8, 12)}-${texto.slice(12)}`;
}
