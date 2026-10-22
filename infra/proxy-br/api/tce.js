/**
 * Intermediário em São Paulo para os servidores de dados abertos que só respondem a endereços do Brasil (ADR-050,
 * adendo): o do TCE-RS e o do TCE-CE. Roda como função da Vercel na região gru1. O coletor no GitHub Actions pede
 * `?url=<endereço original>` com a chave em `x-lumen-chave` e recebe a resposta do tribunal como veio, com `Range`.
 * Só GET e HEAD, só os servidores da lista (também nos redirecionamentos), sem cache. O tamanho e a ETag originais
 * vão também em `x-lumen-tamanho` e `x-lumen-etag`, que a plataforma não reescreve.
 */

import { chaveConfere, destinoPermitido, LIMITE } from "../lib/regras.js";

/** Cabeçalhos da resposta do tribunal que voltam ao coletor. */
const REPASSADOS = ["content-type", "content-range", "accept-ranges", "etag", "last-modified"];
/** Redirecionamentos seguidos, cada um conferido contra a lista. */
const SALTOS = 3;
/** Espera pelo tribunal, abaixo do limite de 60 s da função. */
const ESPERA_MS = 50_000;

/** Resposta de texto curta, para os erros do próprio intermediário. */
function texto(status, mensagem) {
  return new Response(`${mensagem}\n`, {
    status,
    headers: { "content-type": "text/plain; charset=utf-8", "cache-control": "no-store" },
  });
}

/** Confere a chave e o destino, pede ao tribunal e devolve a resposta dele. */
async function repassar(request, metodo) {
  if (!chaveConfere(request.headers.get("x-lumen-chave"))) return texto(401, "chave ausente ou errada");
  let destino = destinoPermitido(new URL(request.url).searchParams.get("url") ?? "");
  if (!destino) return texto(403, "destino fora da lista");
  const cabecalhos = { "user-agent": request.headers.get("user-agent") ?? "Lumen", "accept-encoding": "identity" };
  const range = request.headers.get("range");
  if (range) cabecalhos.range = range;
  let resposta;
  try {
    for (let salto = 0; ; salto++) {
      resposta = await fetch(destino, { method: metodo, headers: cabecalhos, redirect: "manual",
                                        signal: AbortSignal.timeout(ESPERA_MS) });
      const local = resposta.headers.get("location");
      if (resposta.status < 300 || resposta.status >= 400 || !local) break;
      const proximo = destinoPermitido(new URL(local, destino).toString());
      if (!proximo || salto >= SALTOS) return texto(502, "redirecionamento para fora da lista");
      destino = proximo;
    }
  } catch (erro) {
    return texto(504, `o tribunal não respondeu (${erro.name})`);
  }
  const saida = new Headers({ "cache-control": "no-store" });
  for (const nome of REPASSADOS) {
    const valor = resposta.headers.get(nome);
    if (valor) saida.set(nome, valor);
  }
  const tamanho = resposta.headers.get("content-length");
  if (tamanho) saida.set("x-lumen-tamanho", tamanho);
  if (resposta.headers.get("etag")) saida.set("x-lumen-etag", resposta.headers.get("etag"));
  if (metodo === "HEAD") return new Response(null, { status: resposta.status, headers: saida });
  if (Number(tamanho) > LIMITE) {
    await resposta.body?.cancel();
    return texto(413, "resposta grande demais para a função: peça por partes, com Range");
  }
  return new Response(resposta.body, { status: resposta.status, headers: saida });
}

/** GET: o arquivo, ou a parte dele pedida em `Range`. */
export function GET(request) {
  return repassar(request, "GET");
}

/** HEAD: só os cabeçalhos, para o coletor saber o tamanho e a ETag do arquivo. */
export function HEAD(request) {
  return repassar(request, "HEAD");
}
