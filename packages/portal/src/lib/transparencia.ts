/**
 * Portais de transparência avaliados pelo PNTP (ADR-032, ADR-035): o arquivo `transparencia/uf-<sigla>.json`
 * (ou `uniao.json`) que os painéis publicam, com as entidades de cada ente (prefeitura, câmara, poderes,
 * consórcios, estatais), o nível, o índice e o endereço do portal. A página do ente em Conformidade os mostra.
 */

import { CODIGO_UF } from "./busca";
import { obterJson } from "./feeds";
import { BASE_PAINEL, codigoSeguro, conferir } from "./paineis";

/** Uma entidade do ente avaliada pelo PNTP (prefeitura, câmara, poderes, consórcios, estatais). */
export interface EntidadeTransparencia {
  codigo_entidade: string;
  entidade: string;
  poder: string | null;
  esfera: string | null;
  avaliada: boolean;
  indice: number | null;
  essenciais: number | null;
  nivel: string | null;
  nivel_anterior: string | null;
  link: string | null;
  data_envio: string | null;
}

/** Arquivo `transparencia/uf-<sigla>.json` (ou `uniao.json`): as entidades de cada ente da UF. */
export interface FeedTransparencia {
  versao: 1;
  tipo: "transparencia";
  gerado_em: string;
  ciclo: number;
  fonte: string;
  url: string | null;
  coletado_em: string | null;
  entes: Record<string, EntidadeTransparencia[]>;
}

/** Em que arquivo está o ente (o mesmo do Python, `transparencia.arquivo_do_ente`). */
export function arquivoTransparencia(codigo: string): string | null {
  if (codigo === "1") return "transparencia/uniao.json";
  const uf = CODIGO_UF[codigo.slice(0, 2)];
  return uf ? `transparencia/uf-${uf}.json` : null;
}

/** As entidades do ente avaliadas no ciclo mais recente do PNTP, ou `null` se o arquivo não foi publicado. */
export async function carregarTransparencia(codigo: string, sinal?: AbortSignal):
  Promise<{ feed: FeedTransparencia; entidades: EntidadeTransparencia[] } | null> {
  const arquivo = arquivoTransparencia(codigoSeguro(codigo));
  if (!arquivo) return null;
  const url = `${BASE_PAINEL}/${arquivo}`;
  const bruto = await obterJson(url, { sinal });
  if (bruto === null) return null;
  const feed = conferir<FeedTransparencia>(bruto, "transparencia", url);
  return { feed, entidades: feed.entes[codigo] ?? [] };
}
