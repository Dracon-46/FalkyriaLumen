/**
 * As regras do intermediário em São Paulo (ADR-050, adendo): quem pode pedir, para onde e quanto pode voltar.
 */

import { createHash, timingSafeEqual } from "node:crypto";

/**
 * SHA-256 da chave que o GitHub Actions manda em `x-lumen-chave`. A chave fica só no segredo `LUMEN_PROXY_CHAVE` do
 * repositório; para trocá-la sem commit, a variável `LUMEN_PROXY_HASH` do projeto na Vercel tem precedência.
 */
export const HASH_DA_CHAVE = "0806acf099d324ee7f208075704a9edee3f47da071b96153cf191c372b64f437";

/** Os servidores que só respondem a endereços do Brasil e o começo do caminho aceito em cada um. */
export const DESTINOS = {
  "dados.tce.rs.gov.br": "/dados/",
  "api-dados-abertos.tce.ce.gov.br": "/",
  // A API de serviços do IBGE (releases da Economia, localidades e malhas): desde 22/10/2026, só do Brasil
  "servicodados.ibge.gov.br": "/api/",
};

/** A resposta de uma função da Vercel tem no máximo 4,5 MB; o coletor pede os arquivos grandes em partes de 4 MiB. */
export const LIMITE = 4_500_000;

/** A chave confere com o hash, em tempo constante. */
export function chaveConfere(chave, hash = process.env.LUMEN_PROXY_HASH || HASH_DA_CHAVE) {
  if (typeof chave !== "string" || !chave) return false;
  const recebida = createHash("sha256").update(chave).digest();
  const esperada = Buffer.from(hash, "hex");
  return recebida.length === esperada.length && timingSafeEqual(recebida, esperada);
}

/** O endereço pedido, se for HTTPS, num dos servidores da lista e dentro do caminho aceito; senão, `null`. */
export function destinoPermitido(texto) {
  let url;
  try {
    url = new URL(texto);
  } catch {
    return null;
  }
  const caminho = DESTINOS[url.hostname];
  if (url.protocol !== "https:" || caminho === undefined || url.port || url.username || url.password) return null;
  return url.pathname.startsWith(caminho) ? url : null;
}
