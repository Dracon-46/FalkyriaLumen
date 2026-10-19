/**
 * Documentos de um processo ou contrato no PNCP (edital, aviso, termo de referência, contrato, aditivos), para
 * baixar direto da fonte.
 *
 * A API pública do PNCP lista os arquivos de cada publicação (`/orgaos/{cnpj}/compras/{ano}/{seq}/arquivos` e
 * `/orgaos/{cnpj}/contratos/{ano}/{seq}/arquivos`) e libera a leitura pelo navegador (CORS). O portal pede a
 * lista só quando a pessoa abre os documentos de uma publicação; nada é copiado para o Lumen.
 */

import { obterJson } from "./feeds";

/** Raiz da API pública de consulta do PNCP. */
export const API_PNCP = "https://pncp.gov.br/api/pncp/v1";

/** Uma publicação do PNCP pela chave dos painéis (`<CNPJ>-1-<seq>/<ano>` é processo; `-2-`, contrato). */
export interface PublicacaoPncp {
  tipo: "compra" | "contrato";
  cnpj: string;
  ano: number;
  sequencial: number;
}

/** Um documento publicado: título (nome do arquivo), tipo, data e o endereço de download na fonte. */
export interface DocumentoPncp {
  titulo: string;
  tipo: string | null;
  publicado_em: string | null;
  url: string;
}

const CHAVE = /^(\d{14})-([12])-(\d+)\/(\d{4})$/;

/** A publicação da chave dos painéis, ou `null` quando a chave não tem esse formato. */
export function lerChave(chave: string): PublicacaoPncp | null {
  const m = CHAVE.exec(chave);
  if (!m) return null;
  return { tipo: m[2] === "1" ? "compra" : "contrato", cnpj: m[1]!, ano: Number(m[4]), sequencial: Number(m[3]) };
}

/** Endereço da lista de arquivos da publicação na API do PNCP. */
export function urlArquivos(p: PublicacaoPncp): string {
  const recurso = p.tipo === "compra" ? "compras" : "contratos";
  return `${API_PNCP}/orgaos/${p.cnpj}/${recurso}/${p.ano}/${p.sequencial}/arquivos`;
}

/** Lê a resposta da API: só documentos ativos com endereço; tipo e data quando a fonte informa. */
export function lerArquivos(bruto: unknown): DocumentoPncp[] {
  if (!Array.isArray(bruto)) return [];
  const saida: DocumentoPncp[] = [];
  for (const item of bruto) {
    if (!item || typeof item !== "object") continue;
    const x = item as Record<string, unknown>;
    const url = typeof x.url === "string" ? x.url : typeof x.uri === "string" ? x.uri : null;
    if (!url || !/^https:\/\/pncp\.gov\.br\//.test(url) || x.statusAtivo === false) continue;
    saida.push({
      titulo: typeof x.titulo === "string" && x.titulo ? x.titulo : "documento",
      tipo: typeof x.tipoDocumentoNome === "string" ? x.tipoDocumentoNome : null,
      publicado_em: typeof x.dataPublicacaoPncp === "string" ? x.dataPublicacaoPncp : null,
      url,
    });
  }
  return saida;
}

/** Os documentos da publicação; lista vazia quando não há nenhum (404 também é "nenhum"). */
export async function carregarDocumentos(chave: string, sinal?: AbortSignal): Promise<DocumentoPncp[]> {
  const p = lerChave(chave);
  if (!p) return [];
  const bruto = await obterJson(urlArquivos(p), { sinal });
  return bruto === null ? [] : lerArquivos(bruto);
}
