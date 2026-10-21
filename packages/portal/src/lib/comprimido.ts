/**
 * Leitura dos arquivos `.json.gz` dos painéis: os conjuntos grandes (base de CNPJ e emendas, ADR-043 e ADR-044)
 * vão comprimidos para caber no limite do GitHub Pages, e o navegador os descomprime (`DecompressionStream`).
 * Se o servidor já entregar o conteúdo descomprimido (cabeçalho `Content-Encoding`), o JSON é lido como veio.
 */

import { ErroFeed } from "./validacao";

/** O JSON de um arquivo `.json.gz`; `null` quando o arquivo não existe (404). */
export async function obterJsonComprimido(url: string, sinal?: AbortSignal): Promise<unknown> {
  let resposta: Response;
  try {
    resposta = await fetch(url, { cache: "no-cache", signal: sinal });
  } catch (erro) {
    if ((erro as Error).name === "AbortError") throw erro;
    throw new ErroFeed(`sem resposta de ${url}`);
  }
  if (resposta.status === 404) return null;
  if (!resposta.ok) throw new ErroFeed(`${url}: HTTP ${resposta.status}`);
  const bytes = new Uint8Array(await resposta.arrayBuffer());
  let texto: string;
  if (bytes[0] === 0x1f && bytes[1] === 0x8b) {
    const fluxo = new Blob([bytes]).stream().pipeThrough(new DecompressionStream("gzip"));
    texto = await new Response(fluxo).text();
  } else {
    texto = new TextDecoder().decode(bytes);
  }
  try {
    return JSON.parse(texto) as unknown;
  } catch {
    throw new ErroFeed(`${url}: conteúdo não é JSON`);
  }
}
