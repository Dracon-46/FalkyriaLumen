// Testes do intermediário em São Paulo: node --test infra/proxy-br/regras.test.js
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { afterEach, test } from "node:test";
import { GET, HEAD } from "./api/tce.js";
import { chaveConfere, destinoPermitido } from "./lib/regras.js";

const CHAVE = "chave-de-teste";
process.env.LUMEN_PROXY_HASH = createHash("sha256").update(CHAVE).digest("hex");
const original = globalThis.fetch;
afterEach(() => {
  globalThis.fetch = original;
});

/** Um pedido ao intermediário, como o coletor faz. */
function pedido(url, cabecalhos = { "x-lumen-chave": CHAVE }) {
  return new Request(`https://proxy.exemplo/api/tce?url=${encodeURIComponent(url)}`, { headers: cabecalhos });
}

test("só a chave certa passa", () => {
  assert.equal(chaveConfere(CHAVE), true);
  assert.equal(chaveConfere("outra"), false);
  assert.equal(chaveConfere(""), false);
  assert.equal(chaveConfere(null), false);
});

test("só os servidores da lista, por HTTPS, sem porta nem usuário e no caminho aceito", () => {
  assert.ok(destinoPermitido("https://dados.tce.rs.gov.br/dados/licitacon/contrato/ano/2024.csv.zip"));
  assert.ok(destinoPermitido("https://api-dados-abertos.tce.ce.gov.br/sim/contratos?ano=2024"));
  assert.ok(destinoPermitido("https://servicodados.ibge.gov.br/api/v3/noticias/?tipo=release&idproduto=9256&qtd=3"));
  for (const ruim of [
    "http://dados.tce.rs.gov.br/dados/x.csv",
    "https://dados.tce.rs.gov.br/admin",
    "https://dados.tce.rs.gov.br.exemplo.com/dados/x.csv",
    "https://dados.tce.rs.gov.br:8443/dados/x.csv",
    "https://eu@dados.tce.rs.gov.br/dados/x.csv",
    "https://exemplo.com/dados/x.csv",
    "https://servicodados.ibge.gov.br/outra/coisa",
    "não é endereço",
  ]) {
    assert.equal(destinoPermitido(ruim), null, ruim);
  }
});

test("recusa sem chave ou fora da lista, antes de pedir ao tribunal", async () => {
  globalThis.fetch = () => assert.fail("não devia pedir");
  assert.equal((await GET(pedido("https://dados.tce.rs.gov.br/dados/a.zip", {}))).status, 401);
  assert.equal((await GET(pedido("https://exemplo.com/dados/a.zip"))).status, 403);
});

test("repassa Range e devolve a parte, o tamanho e a ETag originais", async () => {
  const vistos = [];
  globalThis.fetch = async (url, opcoes) => {
    vistos.push([String(url), opcoes.method, opcoes.headers.range, opcoes.headers["accept-encoding"]]);
    return new Response("abc", { status: 206, headers: { "content-range": "bytes 0-2/100", "content-length": "3",
                                                         etag: '"e1"' } });
  };
  const r = await GET(pedido("https://dados.tce.rs.gov.br/dados/a.zip", { "x-lumen-chave": CHAVE, range: "bytes=0-2" }));
  assert.equal(r.status, 206);
  assert.equal(await r.text(), "abc");
  assert.equal(r.headers.get("content-range"), "bytes 0-2/100");
  assert.equal(r.headers.get("x-lumen-etag"), '"e1"');
  assert.equal(r.headers.get("cache-control"), "no-store");
  assert.deepEqual(vistos, [["https://dados.tce.rs.gov.br/dados/a.zip", "GET", "bytes=0-2", "identity"]]);

  globalThis.fetch = async () => new Response(null, { status: 200, headers: { "content-length": "129763680" } });
  const h = await HEAD(pedido("https://dados.tce.rs.gov.br/dados/a.zip"));
  assert.equal(h.status, 200);
  assert.equal(h.headers.get("x-lumen-tamanho"), "129763680");
});

test("segue redirecionamento só dentro da lista e recusa resposta grande demais", async () => {
  globalThis.fetch = async () => new Response(null, { status: 302, headers: { location: "https://exemplo.com/x" } });
  assert.equal((await GET(pedido("https://dados.tce.rs.gov.br/dados/a.zip"))).status, 502);

  globalThis.fetch = async () => new Response("x", { status: 200, headers: { "content-length": "130000000" } });
  assert.equal((await GET(pedido("https://dados.tce.rs.gov.br/dados/a.zip"))).status, 413);

  globalThis.fetch = async () => {
    throw new DOMException("tempo esgotado", "TimeoutError");
  };
  assert.equal((await GET(pedido("https://dados.tce.rs.gov.br/dados/a.zip"))).status, 504);
});
