# Feeds da aba Eleições

Este diretório é preenchido pelo coletor do Lumen; nada aqui é editado à mão
nem versionado (exceto este arquivo). O portal lê os arquivos por HTTP em
`/dados/eleicoes/...`. É o destino padrão, bom para `npm run dev` com a
amostra; para a carga completa, o `lumen.toml` aponta os feeds para fora do
portal (`[eleicoes] saida = "dados/eleicoes/feeds"`), e `preparar --servir`
ou `servir` entregam site e feeds pela mesma porta.

| Para ter | Rode, na raiz do repositório |
|---|---|
| tudo: mapa, eleições de 1933 a 2026 e o portal no navegador | `lumen eleicoes preparar --servir` (no Windows, dois cliques em `preparar.cmd`) |
| uma amostra para desenvolver o portal, sem rede | `python -m lumen_eleicoes --saida packages/portal/public/dados/eleicoes amostra` |
| o cadastro de municípios e as malhas do mapa | já vêm com o Lumen (`preparar` e `amostra` instalam); `lumen eleicoes municipios` e `lumen eleicoes mapas` baixam a versão corrente das fontes |
| eleições passadas, ano a ano | `lumen eleicoes historico baixar --anos 2022,1950` e depois `historico processar --anos 2022,1950` |
| a apuração ao vivo | `lumen eleicoes ao-vivo --eleicao 2026-1t-geral` |
| uma apuração simulada (números intermediários fictícios) | `lumen eleicoes simular` |

O contrato dos arquivos (campos, versões, regras) está em
`packages/eleicoes/lumen_eleicoes/feeds.py`, no ADR-019 e no DOC-12.
