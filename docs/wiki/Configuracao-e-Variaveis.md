# Configuração e variáveis

A configuração local fica em `lumen.toml`, na raiz (ou no caminho de `LUMEN_CONFIG`). O modelo
versionado é [`lumen.toml.exemplo`](https://github.com/Dracon-46/FalkyriaLumen/blob/main/lumen.toml.exemplo).
Precedência: **variável de ambiente > arquivo > padrão**. O código que lê tudo isso está em
[`lumen_orquestracao/configuracao.py`](https://github.com/Dracon-46/FalkyriaLumen/blob/main/packages/orquestracao/lumen_orquestracao/configuracao.py)
e [`lumen_eleicoes/configuracao.py`](https://github.com/Dracon-46/FalkyriaLumen/blob/main/packages/eleicoes/lumen_eleicoes/configuracao.py).

**Segredos nunca vão para o repositório nem para o `lumen.toml`** (RNF-13). Chaves de acesso só
existem em variáveis de ambiente e nos segredos do GitHub Actions. Esta página lista nomes, nunca
valores. As únicas credenciais versionadas são as de desenvolvimento local do
`infra/docker-compose.yml`, de propósito.

## Chaves do `lumen.toml`

| Chave | Para que serve | Obrigatória | Padrão | Variável que a substitui |
|---|---|---|---|---|
| `[coleta].contato` | E-mail ou URL de contato, enviado no User-Agent de toda requisição (RF-CO-09) | Sim, para qualquer comando que acessa a rede | — | `LUMEN_CONTATO` |
| `[dados].raiz` | Diretório de `bronze/` (prova) e `silver/` | Não | `dados` | `LUMEN_DADOS` |
| `[limites_rpm].<fonte>` | Requisições por minuto de uma fonte; só aumente com evidência de que a fonte suporta | Não | PNCP 60; IBGE 30; SICONFI 50; `anp_precos_combustiveis` 10; `varejo_mercadolivre` 30; fonte sem valor, 30 | — |
| `[eleicoes].saida` | Diretório dos feeds JSON que o portal lê | Não | `packages/portal/public/dados/eleicoes` (o exemplo recomenda `dados/eleicoes/feeds` para a carga completa) | `LUMEN_ELEICOES_SAIDA` |
| `[eleicoes].arquivos` | ZIPs dos dados abertos do TSE (vários GB) | Não | `<raiz>/eleicoes/arquivos` | — |
| `[eleicoes].estado` | Estado do coletor ao vivo (cores, partes, evolução) | Não | `<raiz>/eleicoes/estado` | — |
| `[eleicoes].rpm_resultados` | Requisições por minuto ao sistema de resultados do TSE | Não | 300 | — |
| `[eleicoes].rpm_dados_abertos` | Requisições por minuto ao CKAN e à CDN de arquivos do TSE | Não | 30 | — |
| `[eleicoes].rpm_ibge` | Requisições por minuto ao IBGE | Não | 30 | — |
| `[publicacao].endpoint` | Endpoint S3 do armazenamento (R2: `https://<id da conta>.r2.cloudflarestorage.com`; Supabase: `https://<ref>.storage.supabase.co/storage/v1/s3`) | Sim, para `--nuvem` e `publicar` | — | `LUMEN_PUBLICACAO_ENDPOINT` |
| `[publicacao].bucket` | Bucket público dos feeds | Sim, para `--nuvem` e `publicar` | — | `LUMEN_PUBLICACAO_BUCKET` |
| `[publicacao].bucket_estado` | Bucket privado do estado da carga | Não | O mesmo `bucket` | `LUMEN_PUBLICACAO_BUCKET_ESTADO` |
| `[publicacao].regiao` | Região da assinatura S3 | Não no R2; sim no Supabase (ex.: `sa-east-1`) | `auto` | `LUMEN_PUBLICACAO_REGIAO` |
| `[publicacao].paralelos` | Envios simultâneos na publicação | Não | 16 | `LUMEN_PUBLICACAO_PARALELOS` |
| `[publicacao].limite_mb` | Teto do bucket público em MB; passou, a publicação para sem enviar o índice; 0 tira o teto | Não | 900 com endpoint do Supabase; 0 nos demais | `LUMEN_PUBLICACAO_LIMITE_MB` |

`paralelos` e `limite_mb` não aparecem no `lumen.toml.exemplo`, mas são lidos pela configuração.
Os limiares da regra A-05 não ficam no `lumen.toml`: estão em
[`parametros_mercado.toml`](https://github.com/Dracon-46/FalkyriaLumen/blob/main/packages/mercado/lumen_mercado/parametros_mercado.toml).
Os valores legais ficam em
[`parametros_legais.toml`](https://github.com/Dracon-46/FalkyriaLumen/blob/main/packages/deteccao/lumen_deteccao/parametros_legais.toml).

## Variáveis de ambiente

| Variável | Para que serve | Obrigatória | Padrão |
|---|---|---|---|
| `LUMEN_CONFIG` | Caminho do `lumen.toml` | Não | `lumen.toml` |
| `LUMEN_CONTATO` | Contato da coleta; substitui `[coleta].contato` | Sim, se o arquivo não tiver o contato | — |
| `LUMEN_DADOS` | Raiz dos dados; substitui `[dados].raiz` | Não | `dados` |
| `LUMEN_ELEICOES_SAIDA` | Diretório dos feeds; substitui `[eleicoes].saida` | Não | ver acima |
| `LUMEN_PUBLICACAO_ENDPOINT`, `LUMEN_PUBLICACAO_BUCKET`, `LUMEN_PUBLICACAO_BUCKET_ESTADO`, `LUMEN_PUBLICACAO_REGIAO`, `LUMEN_PUBLICACAO_PARALELOS`, `LUMEN_PUBLICACAO_LIMITE_MB` | Substituem as chaves de `[publicacao]` | Como as chaves | Como as chaves |
| `LUMEN_S3_CHAVE_ACESSO` | Chave de acesso S3 da publicação (segredo) | Sim, para `--nuvem` e `publicar` | — |
| `LUMEN_S3_CHAVE_SECRETA` | Chave secreta S3 da publicação (segredo) | Sim, para `--nuvem` e `publicar` | — |
| `LUMEN_ML_TOKEN` | Credencial da busca do Mercado Livre (regra A-05, segredo) | Só para o varejo; sem ela a busca responde 403 | — |
| `LUMEN_TESTE_PG` | DSN do PostgreSQL para os testes marcados `postgres` | Só para esses testes | — |
| `LUMEN_TESTE_CONTRATO` | `1` liga os testes de contrato contra as fontes reais | Só para esses testes | desligado |
| `LUMEN_TESTE_CONTRATO_PESADO` | `1` liga o teste de contrato que baixa o detalhe da apuração de 2022 inteiro | Só para esse teste | desligado |
| `NEXT_PUBLIC_DADOS_ELEICOES` | Base dos feeds das eleições no build do portal | Não | `/dados/eleicoes` |
| `NEXT_PUBLIC_DADOS_PAINEL` | Base dos dados dos painéis no build do portal | Não | `https://dracon-46.github.io/FalkyriaLumen` |

As variáveis `NEXT_PUBLIC_*` são fixadas no momento do `npm run build`: mudar o endereço exige gerar
o portal de novo. Na Vercel, `NEXT_PUBLIC_DADOS_ELEICOES` fica nas variáveis do projeto, com o
endereço público do bucket `lumen-eleicoes`.

## GitHub Actions: segredos

Settings → Secrets and variables → Actions → Secrets.

| Segredo | Para que serve | Usado por | Obrigatório |
|---|---|---|---|
| `LUMEN_CONTATO` | Contato da coleta (User-Agent) | `eleicoes-carga`, `eleicoes-ao-vivo`, `eleicoes-medir`, `paineis`, `paineis-carga`, `mercado-referencia` | Sim |
| `R2_ENDPOINT` | Endpoint S3 do armazenamento dos feeds (R2 ou Supabase Storage) | `eleicoes-carga`, `eleicoes-ao-vivo`, `nuvem-diagnostico` | Sim, para publicar; sem ele a carga agendada só avisa |
| `R2_CHAVE_ACESSO` | Chave de acesso S3 | os mesmos | Sim, para publicar |
| `R2_CHAVE_SECRETA` | Chave secreta S3 | os mesmos | Sim, para publicar |
| `CLOUDFLARE_API_TOKEN` | Token com permissão "Cloudflare Pages: Edit" | `portal-pages` | Só para publicar no Pages; sem ele o fluxo gera o portal e avisa |
| `CLOUDFLARE_ACCOUNT_ID` | Id da conta Cloudflare | `portal-pages` | Só para publicar no Pages |
| `LUMEN_ML_TOKEN` | Busca do varejo | `contrato` | Não; sem ele o teste do varejo fica pulado |

Os fluxos dos painéis usam também o token da própria execução (`github.token`) para os anexos da
versão `painel-estado`; não é segredo a cadastrar.

## GitHub Actions: variáveis

Settings → Secrets and variables → Actions → Variables.

| Variável | Para que serve | Obrigatória | Padrão |
|---|---|---|---|
| `R2_BUCKET_FEEDS` | Bucket público dos feeds (ex.: `lumen-eleicoes`) | Sim, para publicar | — |
| `R2_BUCKET_ESTADO` | Bucket privado do estado (ex.: `lumen-privado`) | Não | o dos feeds |
| `R2_REGIAO` | Região da assinatura S3; obrigatória com o Supabase (ex.: `sa-east-1`) | Só no Supabase | `auto` |
| `ELEICOES_SEM_HISTORICO` | `true` carrega só 2026 e o mapa das zonas, sem os dados abertos dos resultados; as entradas `anos` e `historico` da execução manual passam por cima | Não | vazio |
| `PUBLICACAO_PARALELOS` | Envios simultâneos | Não | 32 nos fluxos |
| `PUBLICACAO_LIMITE_MB` | Teto do bucket público em MB; 0 tira o teto | Não | 900 no Supabase |
| `LUMEN_URL_FEEDS` | Endereço público do bucket dos feeds; vira `NEXT_PUBLIC_DADOS_ELEICOES` no `portal-pages` e é lido pelo `nuvem-diagnostico` | Para o Pages | vazio, que vale `/dados/eleicoes` |
| `CF_PAGES_PROJETO` | Nome do projeto no Cloudflare Pages (ex.: `lumen`) | Só para publicar no Pages | — |

Mapeamento nos fluxos de eleições: `R2_ENDPOINT` → `LUMEN_PUBLICACAO_ENDPOINT`,
`R2_CHAVE_ACESSO` → `LUMEN_S3_CHAVE_ACESSO`, `R2_CHAVE_SECRETA` → `LUMEN_S3_CHAVE_SECRETA`,
`R2_BUCKET_FEEDS` → `LUMEN_PUBLICACAO_BUCKET`, `R2_BUCKET_ESTADO` → `LUMEN_PUBLICACAO_BUCKET_ESTADO`,
`R2_REGIAO` → `LUMEN_PUBLICACAO_REGIAO`. Os nomes `R2_*` ficaram os mesmos com o Supabase para não
obrigar a refazer a configuração ao trocar de serviço
([ADR-026](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-026.md), adendo).

As entradas de cada fluxo disparado à mão estão em [[Deploy e operação|Deploy-e-Operacao]].
