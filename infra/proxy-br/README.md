# Intermediário em São Paulo

Função da Vercel, na região `gru1` (São Paulo), para os servidores de dados abertos que só respondem a endereços do
Brasil: o do TCE-RS, o do TCE-CE e, desde 22/10/2026, a API de serviços do IBGE (`servicodados.ibge.gov.br`, só em
`/api/`). O GitHub Actions roda fora do Brasil, e o coletor dos tribunais de contas
(`lumen_painel.tce`) e a coleta HTTP comum (`lumen_ingestao.coleta_http`, para o IBGE) mandam os pedidos a esses
servidores por aqui. A decisão está na
[ADR-050](../../docs/adr/ADR-050.md), no adendo de 22/10/2026.

## Como funciona

```
GET  /api/tce?url=https://dados.tce.rs.gov.br/dados/...      (com x-lumen-chave e, se quiser, Range)
HEAD /api/tce?url=...
```

- Só os servidores e caminhos de `lib/regras.js`, também nos redirecionamentos; o resto recebe 403.
- Sem a chave certa em `x-lumen-chave`, 401. O código guarda só o SHA-256 da chave; a chave fica no segredo
  `LUMEN_PROXY_CHAVE` do repositório. Para trocar a chave sem commit, defina `LUMEN_PROXY_HASH` no projeto da Vercel.
- A resposta volta como o tribunal mandou (status, `Content-Range`, ETag, Last-Modified), sem cache, com o tamanho e a
  ETag originais repetidos em `x-lumen-tamanho` e `x-lumen-etag`.
- Resposta acima de 4,5 MB (o limite da função) recebe 413: o coletor pede os arquivos grandes por partes de 4 MiB.

## Implantar

Uma vez, na Vercel: **Add New → Project**, importar `Dracon-46/FalkyriaLumen`, **Root Directory** `infra/proxy-br`,
nome `lumen-proxy-br`, sem framework nem build. Depois, cada push que muda esta pasta publica de novo. No GitHub:

- variável `LUMEN_PROXY_BR` = `https://lumen-proxy-br.vercel.app/api/tce`;
- segredo `LUMEN_PROXY_CHAVE` = a chave cujo SHA-256 está em `lib/regras.js`.

## Testar

```bash
node --test infra/proxy-br/regras.test.js
```
