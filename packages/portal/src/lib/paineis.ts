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
import { numero, percentual } from "./formato";
import { ErroFeed } from "./validacao";

/** Raiz dos dados dos painéis, sem barra final. Variável vazia vale como ausente. */
export const BASE_PAINEL = (process.env.NEXT_PUBLIC_DADOS_PAINEL || "https://dracon-46.github.io/FalkyriaLumen").replace(
  /\/$/,
  "",
);

/** Código IBGE de ente aceito nos caminhos: União (1), UF (2 dígitos) ou município (7 dígitos). */
const CODIGO = /^(1|\d{2}|\d{7})$/;
const UF = /^[A-Z]{2}$/;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

/** Barra códigos fora do padrão antes do `fetch`: a URL da página vira caminho de arquivo. */
export function codigoSeguro(codigo: string): string {
  if (!CODIGO.test(codigo)) throw new ErroFeed(`código de ente inválido: ${codigo}`);
  return codigo;
}

/**
 * O arquivo que leva o ente nos conjuntos publicados por grupo (emendas, convênios): os 3 primeiros dígitos do
 * município e o código da UF para ela, como `comum.grupo_do_ente` no Python.
 */
export function grupoDoEnte(codigo: string): string {
  const c = codigoSeguro(codigo);
  return c.length === 7 ? c.slice(0, 3) : c;
}

/** Endereço de cada arquivo dos painéis; código, CNPJ e UF passam pela validação antes de virar caminho. */
export const urlsPainel = {
  indice: () => `${BASE_PAINEL}/indice.json`,
  entes: () => `${BASE_PAINEL}/entes.json`,
  orgaos: () => `${BASE_PAINEL}/orgaos.json`,
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
  conformidadePares: (id: string) => {
    if (!UUID.test(id)) throw new ErroFeed(`grupo de pares inválido: ${id}`);
    return `${BASE_PAINEL}/conformidade/pares/${id}.json`;
  },
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

/**
 * Linha do `orgaos.json` para a busca: um órgão com publicação no período, com o nome e a UF do ente a que
 * pertence (do cadastro) e as palavras e a sigla do nome já normalizadas.
 */
export interface OrgaoBusca {
  cnpj: string;
  nome: string;
  ente: string | null;
  enteNome: string | null;
  uf: string | null;
  esfera: string | null;
  publicacoes: number;
  palavras: string[];
  sigla: string;
}

/** Dias do PNCP somados no painel: o primeiro, o último, quantos e os que faltam entre eles. */
export interface Cobertura {
  de: string | null;
  ate: string | null;
  dias: number;
  faltando: string[];
}

/**
 * Contagens e somas de um recorte: processos, valor estimado, contratos e valor global. `valores_a_conferir`:
 * processos e contratos contados cujo valor passou do teto de plausibilidade e ficou fora das somas.
 */
export interface TotaisContratacoes {
  processos: number;
  valor_estimado: number;
  processos_sem_valor: number;
  contratos: number;
  valor_contratos: number;
  valores_a_conferir?: number;
}

/** Processo ou contrato com valor acima do teto de plausibilidade: fora das somas, com o link para conferir. */
export interface ValorAConferir {
  data: string;
  tipo: "processo" | "contrato";
  chave: string;
  orgao: string | null;
  fornecedor: string | null;
  fornecedor_cnpj: string | null;
  valor: number | null;
  objeto: string | null;
  link: string | null;
}

/**
 * Mês a mês de uma linha de tabela: `[mês, processos, valor estimado, contratos, valor dos contratos]` (órgãos,
 * municípios, esferas), `[mês, processos, valor estimado]` (modalidades), `[mês, contratos, valor]`
 * (fornecedores, pessoas físicas) ou `[mês, processos do estado, processos dos municípios]` (UFs). Ausente nos
 * arquivos gerados antes de existir o filtro de período.
 */
export type MesesLinha = [string, ...number[]][];

/** Seções comuns ao panorama, a um ente e a um órgão (`_secoes` no Python). */
export interface SecoesContratacoes {
  totais: TotaisContratacoes & { orgaos: number; fornecedores: number };
  meses: (TotaisContratacoes & { mes: string })[];
  modalidades: { codigo: number | null; nome: string; processos: number; valor_estimado: number; meses?: MesesLinha }[];
  orgaos: (TotaisContratacoes & { cnpj: string; nome: string | null; meses?: MesesLinha })[];
  fornecedores: { cnpj: string; nome: string | null; contratos: number; valor: number; meses?: MesesLinha }[];
  pessoas_fisicas: { contratos: number; valor: number; meses?: MesesLinha };
  recentes: {
    data: string;
    chave: string;
    orgao: string | null;
    modalidade: string | null;
    objeto: string | null;
    valor_estimado: number | null;
    situacao: string | null;
    link: string | null;
    a_conferir?: boolean;
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
    a_conferir?: boolean;
  }[];
  a_conferir?: ValorAConferir[];
}

/** Arquivo `contratacoes/ente/<código>.json`; o de um estado traz também os municípios da UF. */
export interface ContratacoesEnte extends SecoesContratacoes {
  versao: 1;
  tipo: "contratacoes-ente";
  gerado_em: string;
  cobertura: Cobertura;
  ente: EnteResumo;
  municipios?: (TotaisContratacoesSimples & { codigo: string; nome: string; meses?: MesesLinha })[];
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
  esferas: (TotaisContratacoes & { esfera: string; nome: string; meses?: MesesLinha })[];
  sem_ente: TotaisContratacoes;
  ufs: {
    uf: string;
    estado: TotaisContratacoes;
    municipios: TotaisContratacoes;
    municipios_com_publicacao: number;
    municipios_no_cadastro: number;
    meses?: MesesLinha;
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
  /** O resumo de cada exercício (`"2025"`), para o filtro de período; ausente nos arquivos antigos. */
  por_exercicio?: Record<string, ResumoConformidade>;
  obrigacoes: Obrigacao[];
  /** Grupo de pares (ADR-038); ausente nos arquivos publicados antes dele. */
  pares?: ParesConformidade;
}

/** Grupo de pares (ADR-038): descrição, célula, tamanho, ressalva e os critérios gravados. */
export interface GrupoPares {
  id: string;
  descricao: string;
  esfera: "municipal" | "estadual";
  faixa_populacional: string | null;
  regiao: string;
  entes: number;
  abaixo_do_minimo: boolean;
  /** Metade da RCL por habitante na divisão (versão 2); nula no grupo inteiro e nos arquivos anteriores. */
  faixa_rcl?: "ate_a_mediana" | "acima_da_mediana" | null;
  criterios: { minimo_entes: number; motivo?: string; receita_corrente_liquida?: string | CriterioRcl } &
    Record<string, unknown>;
}

/** Como a RCL entrou no grupo: a mediana por habitante do exercício e a metade, ou o grupo inteiro (`uso`). */
export interface CriterioRcl {
  exercicio: number | null;
  mediana_por_habitante: number;
  entes_com_rcl: number;
  faixa: "ate_a_mediana" | "acima_da_mediana" | null;
  uso?: string;
}

/** A RCL do ente: exercício, valor, por habitante e o tipo do RREO de onde veio. */
export interface RclEnte {
  exercicio: number | null;
  valor: number;
  por_habitante: number | null;
  demonstrativo: string | null;
}

/** A frase dos critérios sobre a RCL, para o cartão do grupo de pares. */
export function criterioRcl(grupo: GrupoPares): string {
  const c = grupo.criterios.receita_corrente_liquida;
  if (c === undefined) return "A receita corrente líquida ainda não entra nos critérios.";
  if (typeof c === "string") return `Receita corrente líquida (RCL) ${c}.`;
  const base = `mediana de ${moeda(c.mediana_por_habitante)} por habitante entre ${numero(c.entes_com_rcl)} entes com a RCL de ${c.exercicio} publicada`;
  if (c.faixa) return `Divididos pela receita corrente líquida (RCL) por habitante: ${base}.`;
  return `O ente não publicou a RCL de ${c.exercicio}: a comparação é com o grupo inteiro (${base}).`;
}

/** Quartis e mediana da fração entregue no prazo entre os entes do grupo com obrigação avaliável. */
export interface DistribuicaoNoPrazo {
  entes: number;
  q1: number;
  mediana: number;
  q3: number;
}

/** Uma linha da despesa por função (ADR-041): o total ou uma função, do ente e do grupo, em reais por habitante. */
export interface LinhaDespesa {
  /** "total" ou o código da função na classificação funcional ("10" é Saúde). */
  codigo: string;
  nome: string;
  /** Despesa liquidada no exercício, em reais da época. */
  valor: number;
  por_habitante: number | null;
  /** Quartis e mediana entre os entes do grupo com a DCA lida (mesmo formato da fração no prazo). */
  grupo: DistribuicaoNoPrazo | null;
}

/** A despesa por função do ente na DCA do exercício, ao lado do grupo; `funcoes` vazia sem a DCA lida. */
export interface DespesaPares {
  exercicio: number | null;
  /** Entes do grupo com a DCA lida e somando o total: a base das distribuições. */
  entes_com_dca: number;
  /** Se as funções da DCA do ente somam o total; nulo sem a DCA. */
  confere: boolean | null;
  funcoes: LinhaDespesa[];
}

/** Os limites da despesa com pessoal que o próprio RGF declara, em % da RCL ajustada (LRF, arts. 20, 22 e 59). */
export interface LimitesPessoal {
  alerta?: number;
  prudencial?: number;
  maximo?: number;
}

/** A despesa com pessoal do Executivo no RGF do último período do exercício (ADR-042), ao lado do grupo. */
export interface PessoalPares {
  exercicio: number | null;
  /** Entes do grupo com o percentual lido: a base da distribuição. */
  entes_com_rgf: number;
  /** Quartis e mediana do percentual no grupo, em pontos percentuais; nulo abaixo do mínimo de entes. */
  grupo: DistribuicaoNoPrazo | null;
  ente: {
    percentual: number;
    dtp: number | null;
    rcl_ajustada: number | null;
    limites: LimitesPessoal;
    demonstrativo: string | null;
    periodo: number | null;
    periodicidade: "Q" | "S" | null;
  } | null;
}

/** Bloco `pares` do arquivo do ente: o grupo e a distribuição, ou o motivo de o ente não ter grupo. */
export type ParesConformidade =
  | { grupo: GrupoPares; no_prazo: DistribuicaoNoPrazo | null; rcl?: RclEnte | null; despesa?: DespesaPares;
      pessoal?: PessoalPares }
  | { grupo: null; motivo: string };

/** Onde o percentual fica em relação aos limites declarados no mesmo RGF. */
export function faixaDoLimite(percentual: number, limites: LimitesPessoal): string | null {
  const { alerta, prudencial, maximo } = limites;
  if (maximo === undefined) return null;
  if (percentual > maximo) return "acima do limite máximo";
  if (prudencial !== undefined && percentual > prudencial) return "entre o limite prudencial e o máximo";
  if (alerta !== undefined && percentual > alerta) return "entre o limite de alerta e o prudencial";
  return alerta === undefined ? "abaixo do limite máximo" : "abaixo do limite de alerta";
}

/** "RGF do 3º quadrimestre de 2025" ou "do 2º semestre". */
export function periodoDoRgf(periodo: number | null, periodicidade: "Q" | "S" | null, exercicio: number): string {
  const nome = periodicidade === "S" ? "semestre" : "quadrimestre";
  return periodo ? `${periodo}º ${nome} de ${exercicio}` : `${exercicio}`;
}

/** O RGF do Executivo no SICONFI, Anexo 1 (a fonte da despesa com pessoal). */
export function urlRgfDoEnte(codigo: string, exercicio: number, pessoal: NonNullable<PessoalPares["ente"]>): string {
  const p = new URLSearchParams({
    an_exercicio: String(exercicio), in_periodicidade: pessoal.periodicidade ?? "Q",
    nr_periodo: String(pessoal.periodo ?? 3), co_tipo_demonstrativo: pessoal.demonstrativo ?? "RGF",
    no_anexo: "RGF-Anexo 01", co_poder: "E", id_ente: codigo,
  });
  return `https://apidatalake.tesouro.gov.br/ords/siconfi/tt/rgf?${p.toString().replace(/\+/g, "%20")}`;
}

/** Onde o valor fica no grupo: acima do terceiro quartil, abaixo do primeiro ou na metade central. */
export function posicaoNoGrupo(valor: number, d: DistribuicaoNoPrazo): "acima" | "abaixo" | "central" {
  if (valor > d.q3) return "acima";
  if (valor < d.q1) return "abaixo";
  return "central";
}

/** A metade central em reais: "entre R$ 5.500,00 e R$ 12.500,00". */
export function faixaCentralEmReais(d: DistribuicaoNoPrazo): string {
  return d.q1 === d.q3 ? `em ${moeda(d.q1)}` : `entre ${moeda(d.q1)} e ${moeda(d.q3)}`;
}

/** A DCA do ente no SICONFI, Anexo I-E (a fonte da despesa por função). */
export const urlDcaDoEnte = (codigo: string, exercicio: number) =>
  `https://apidatalake.tesouro.gov.br/ords/siconfi/tt/dca?an_exercicio=${exercicio}&no_anexo=${encodeURIComponent("DCA-Anexo I-E")}&id_ente=${codigo}`;

/** Um ente do grupo de pares, com a sua fração no prazo. */
export interface EntePares {
  codigo: string;
  nome: string;
  uf: string | null;
  populacao: number | null;
  rcl_por_habitante?: number | null;
  /** Despesa total da DCA por habitante (ADR-041); ausente nos arquivos anteriores. */
  despesa_por_habitante?: number | null;
  /** Despesa com pessoal do Executivo em % da RCL ajustada (ADR-042); ausente nos arquivos anteriores. */
  pessoal_percentual?: number | null;
  no_prazo: number | null;
  avaliaveis: number | null;
}

/** Arquivo `conformidade/pares/<id>.json`: o grupo, a distribuição e os entes que o formam, por nome. */
export interface ConformidadePares {
  versao: 1;
  tipo: "conformidade-pares";
  gerado_em: string;
  avaliado_em: string;
  grupo: GrupoPares;
  no_prazo: DistribuicaoNoPrazo | null;
  entes: EntePares[];
}

/**
 * A metade central do grupo em palavras: "entre 80,00% e 100,00%" (do primeiro ao terceiro quartil). `fator`
 * leva o valor a pontos percentuais: 100 para frações (o padrão), 1 para valores que já estão em %.
 */
export function faixaCentral(d: DistribuicaoNoPrazo, fator = 100): string {
  const pct = (x: number) => percentual(x * fator);
  return d.q1 === d.q3 ? `em ${pct(d.q1)}` : `entre ${pct(d.q1)} e ${pct(d.q3)}`;
}

/** Arquivo `conformidade/uf/<sigla>.json`: os entes avaliados da UF, por nome. */
export interface ConformidadeUf {
  versao: 1;
  tipo: "conformidade-uf";
  gerado_em: string;
  avaliado_em: string;
  coletado_em: string | null;
  uf: string;
  entes: (ResumoConformidade & { codigo: string; nome: string; tipo: TipoEnte | null; populacao: number | null;
                                 por_exercicio?: Record<string, ResumoConformidade> })[];
}

/** Arquivo `conformidade/panorama.json`: o Brasil, por obrigação e por UF. */
export interface ConformidadePanorama {
  versao: 1;
  tipo: "conformidade-panorama";
  gerado_em: string;
  avaliado_em: string;
  entes: number;
  brasil: ResumoConformidade;
  brasil_por_exercicio?: Record<string, ResumoConformidade>;
  criterios: (ResumoConformidade & { criterio: string; nome: string; por_exercicio?: Record<string, ResumoConformidade> })[];
  ufs: (ResumoConformidade & { uf: string; entes: number; coletado_em: string | null;
                               por_exercicio?: Record<string, ResumoConformidade> })[];
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
/** Um grupo de pares, com os entes que o formam; `null` se o arquivo não existe. */
export const carregarConformidadePares = (id: string, sinal?: AbortSignal) =>
  ler<ConformidadePares>(urlsPainel.conformidadePares(id), "conformidade-pares", sinal);

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

let cacheOrgaos: Promise<OrgaoBusca[]> | null = null;

/** Órgãos para a busca, com o cadastro de entes, baixados uma vez por visita; lista vazia sem o arquivo. */
export function carregarOrgaos(): Promise<OrgaoBusca[]> {
  if (!cacheOrgaos) {
    cacheOrgaos = Promise.all([obterJson(urlsPainel.orgaos()), carregarEntes()]).then(([bruto, entes]) =>
      lerOrgaos(bruto, entes),
    );
    cacheOrgaos.catch(() => {
      cacheOrgaos = null;
    });
  }
  return cacheOrgaos;
}

/** Palavras de ligação que não entram na sigla de um nome. */
const LIGACOES = new Set(["a", "as", "o", "os", "de", "da", "do", "das", "dos", "e", "em", "na", "no"]);

/** Sigla pelas iniciais das palavras do nome, sem as de ligação: "Serviço Autônomo de Água e Esgoto" → "saae". */
export function siglaDoNome(nome: string): string {
  return normalizar(nome)
    .split(" ")
    .filter((p) => p && !LIGACOES.has(p))
    .map((p) => p[0])
    .join("");
}

/** Converte o `orgaos.json` (linhas em lista, na ordem de `colunas`) em objetos prontos para a busca. */
export function lerOrgaos(bruto: unknown, entes: EnteBusca[]): OrgaoBusca[] {
  const o = bruto as { versao?: number; colunas?: string[]; orgaos?: unknown[][] } | null;
  if (!o || o.versao !== 1 || !Array.isArray(o.orgaos) || !Array.isArray(o.colunas)) return [];
  const c = o.colunas;
  const [ic, inome, iente, iesfera, ip, ict] = ["cnpj", "nome", "ente", "esfera", "processos", "contratos"].map(
    (n) => c.indexOf(n),
  ) as [number, number, number, number, number, number];
  const porCodigo = new Map(entes.map((e) => [e.codigo, e]));
  return o.orgaos
    .filter((l) => Array.isArray(l) && typeof l[ic] === "string" && /^\d{14}$/.test(l[ic] as string))
    .map((l) => {
      const cnpjOrgao = l[ic] as string;
      const nome = (l[inome] as string | null) || cnpjOrgao;
      const ente = (l[iente] as string | null) ?? null;
      const doEnte = ente ? porCodigo.get(ente) : undefined;
      const enteNome = doEnte?.nome ?? null;
      return {
        cnpj: cnpjOrgao,
        nome,
        ente,
        enteNome,
        uf: doEnte?.uf ?? null,
        esfera: (l[iesfera] as string | null) ?? null,
        publicacoes: ((l[ip] as number) || 0) + ((l[ict] as number) || 0),
        palavras: normalizar(`${nome} ${enteNome ?? ""}`).split(" "),
        sigla: siglaDoNome(nome),
      };
    });
}

/**
 * Até `limite` órgãos que casam com o termo. Cada palavra do termo precisa começar uma palavra do nome do órgão
 * ou do ente a que ele pertence, ou, com três letras ou mais, aparecer na sigla do nome ("saae sorocaba" acha o
 * Serviço Autônomo de Água e Esgoto de Sorocaba). Termo só de dígitos busca pelo começo do CNPJ. Quem começa com
 * o termo vem antes; empate por mais publicações e depois pelo nome.
 */
export function buscarOrgaos(termo: string, orgaos: OrgaoBusca[], limite = 8): OrgaoBusca[] {
  const t = normalizar(termo);
  if (!t) return [];
  const digitos = termo.replace(/\D/g, "");
  const soDigitos = !/[a-z]/.test(t) && digitos.length >= 4;
  const palavras = t.split(" ");
  const pontuados: { o: OrgaoBusca; p: number }[] = [];
  for (const o of orgaos) {
    let p: number;
    if (soDigitos) {
      if (!o.cnpj.startsWith(digitos)) continue;
      p = 0;
    } else {
      const casa = palavras.every(
        (w) => o.palavras.some((q) => q.startsWith(w)) || (w.length >= 3 && o.sigla.includes(w)),
      );
      if (!casa) continue;
      p = normalizar(o.nome).startsWith(t) ? 0 : 1;
    }
    pontuados.push({ o, p });
  }
  pontuados.sort((a, b) => a.p - b.p || b.o.publicacoes - a.o.publicacoes || a.o.nome.localeCompare(b.o.nome));
  return pontuados.slice(0, limite).map((x) => x.o);
}

const ESFERAS: Record<string, string> = { M: "municipal", E: "estadual", D: "distrital", F: "federal" };

/** Descrição curta do órgão: "Órgão municipal · Sorocaba (SP)", "Órgão federal" ou só "Órgão". */
export function descreverOrgao(o: Pick<OrgaoBusca, "esfera" | "ente" | "enteNome" | "uf">): string {
  const esfera = o.esfera ? ESFERAS[o.esfera] : undefined;
  const base = esfera ? `Órgão ${esfera}` : "Órgão";
  if (!o.ente || tipoDoCodigo(o.ente) === "uniao") return base;
  if (tipoDoCodigo(o.ente) === "municipio" && o.enteNome) return `${base} · ${o.enteNome}${o.uf ? ` (${o.uf})` : ""}`;
  return o.uf ? `${base} · ${o.uf}` : base;
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
