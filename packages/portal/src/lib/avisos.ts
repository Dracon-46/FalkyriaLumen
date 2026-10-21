/**
 * Avisos (ADR-047): o que aconteceu em cada ente e merece um olhar, reunido pelos painéis a partir de dados
 * públicos (fornecedor sancionado com contrato, valor a conferir, relatórios fiscais que não constam ou em
 * atraso, portal de transparência com nível baixo). Cada aviso traz o que aconteceu, o que observar e a fonte;
 * nenhum é conclusão sobre a conduta de alguém, e quem é citado pode contestar.
 *
 * Arquivos: `avisos/panorama.json` (contagens e os mais recentes do Brasil) e `avisos/uf-<sigla>.json` (todos
 * os do estado e dos municípios da UF) ou `avisos/uniao.json`.
 */

import { obterJson } from "./feeds";
import { BASE_PAINEL, conferir } from "./paineis";
import { CODIGO_UF } from "./busca";

/** Os tipos de aviso. */
export type TipoAviso = "fornecedor_sancionado" | "valor_a_conferir" | "lrf_nao_consta" | "lrf_atrasos" | "transparencia_baixa";

/** A contestação de um aviso (issue com o rótulo `contestacao`). */
export interface Contestacao {
  situacao: "em_analise" | "mantido" | "retificado";
  link: string | null;
  em: string;
}

/** Um aviso. */
export interface Aviso {
  id: string;
  tipo: TipoAviso;
  rotulo: string;
  data: string | null;
  ente: { codigo: string | null; nome: string; uf: string | null; tipo: string | null };
  orgao: { cnpj: string | null; nome: string | null } | null;
  titulo: string;
  detalhe: string[];
  observar: string;
  fonte: { nome: string; link: string | null; outra?: string | null };
  chave: string | null;
  valor: number | null;
  contestacao: Contestacao | null;
}

/** `avisos/uf-<sigla>.json` ou `avisos/uniao.json`. */
export interface ArquivoAvisos {
  versao: 1;
  tipo: "avisos";
  gerado_em: string;
  uf: string | null;
  avisos: Aviso[];
}

/** `avisos/panorama.json`. */
export interface PanoramaAvisos {
  versao: 1;
  tipo: "avisos-panorama";
  gerado_em: string;
  tipos: Record<TipoAviso, string>;
  total: number;
  por_tipo: Record<TipoAviso, number>;
  por_lugar: ({ lugar: string } & Record<TipoAviso, number>)[];
  contestados: number;
  ultimos: Aviso[];
}

/** Os tipos, na ordem em que aparecem nos filtros. */
export const TIPOS_AVISO: { tipo: TipoAviso; rotulo: string }[] = [
  { tipo: "fornecedor_sancionado", rotulo: "Contrato com empresa sancionada" },
  { tipo: "valor_a_conferir", rotulo: "Valor a conferir na fonte" },
  { tipo: "lrf_nao_consta", rotulo: "Relatório fiscal não consta" },
  { tipo: "lrf_atrasos", rotulo: "Relatórios fiscais em atraso" },
  { tipo: "transparencia_baixa", rotulo: "Portal de transparência com nível baixo" },
];

/** O arquivo de avisos do local: o da União, ou o da UF do estado ou do município; `null` se o código não serve. */
export function arquivoDeAvisos(codigo: string): string | null {
  if (codigo === "1") return `${BASE_PAINEL}/avisos/uniao.json`;
  const uf = CODIGO_UF[codigo.slice(0, 2)];
  return /^(\d{2}|\d{7})$/.test(codigo) && uf ? `${BASE_PAINEL}/avisos/uf-${uf}.json` : null;
}

/** O panorama do Brasil; `null` antes da primeira publicação. */
export async function carregarPanoramaAvisos(sinal?: AbortSignal): Promise<PanoramaAvisos | null> {
  const url = `${BASE_PAINEL}/avisos/panorama.json`;
  const bruto = await obterJson(url, { sinal });
  return bruto === null ? null : conferir<PanoramaAvisos>(bruto, "avisos-panorama", url);
}

/**
 * Os avisos do local. Município: os dele. Estado ou DF: os do governo e, com `comMunicipios`, também os dos
 * municípios da UF (e dos órgãos sem ente identificado que contrataram nela). União: os da União.
 */
export async function carregarAvisosDoLocal(codigo: string, comMunicipios: boolean, sinal?: AbortSignal): Promise<Aviso[] | null> {
  const url = arquivoDeAvisos(codigo);
  if (!url) return null;
  const bruto = await obterJson(url, { sinal });
  if (bruto === null) return [];
  const arq = conferir<ArquivoAvisos>(bruto, "avisos", url);
  if (codigo.length === 7) return arq.avisos.filter((a) => a.ente.codigo === codigo);
  if (codigo === "1" || comMunicipios) return arq.avisos;
  return arq.avisos.filter((a) => a.ente.codigo === codigo);
}

/** Endereço para contestar o aviso: o formulário de contestação das issues, já com o código. */
export function urlContestar(a: Pick<Aviso, "id" | "titulo">): string {
  const p = new URLSearchParams({ template: "contestacao.yml", title: `[contestação] ${a.id}`, aviso: a.id, resumo: a.titulo });
  return `https://github.com/Dracon-46/FalkyriaLumen/issues/new?${p.toString()}`;
}

/** O endereço do modal da contratação do aviso no painel, quando ele tem a chave do PNCP. */
export function urlDaContratacao(a: Pick<Aviso, "chave">): string | null {
  const m = a.chave ? /^(\d{14})-[12]-\d+\/\d{4}$/.exec(a.chave) : null;
  return m ? `/contratacoes/?orgao=${m[1]}&pub=${encodeURIComponent(a.chave!)}` : null;
}

/** Os tipos escolhidos na URL (`?tipo=a,b`); vazio é todos. */
export function lerTipos(bruto: string | null): TipoAviso[] {
  const validos = new Set(TIPOS_AVISO.map((t) => t.tipo));
  return (bruto ?? "").split(",").filter((t): t is TipoAviso => validos.has(t as TipoAviso));
}
