# Deploy e operação

Fontes: [ADR-026](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-026.md) (com o
adendo), [ADR-028](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-028.md), o README
da raiz, o [README do portal](https://github.com/Dracon-46/FalkyriaLumen/blob/main/packages/portal/README.md)
e os fluxos em [`.github/workflows/`](https://github.com/Dracon-46/FalkyriaLumen/tree/main/.github/workflows).
O passo a passo com as telas de configuração está no DOC-12, seções 9.5 a 9.7.

Tudo roda em planos gratuitos, sem computador pessoal ligado. O repositório é público desde
14/10/2026, o que tira o limite de minutos do GitHub Actions.

## Visão geral

| O quê | Onde | Como chega lá |
|---|---|---|
| Portal (site estático) | Vercel, plano Hobby (em uso desde 14/10/2026); Cloudflare Pages como alternativa | Vercel: importa o repositório e gera a cada mudança em `packages/portal`. Pages: fluxo `portal-pages` |
| Feeds das eleições | Supabase Storage, bucket público `lumen-eleicoes` (configuração escolhida para o 2º turno de 2026); Cloudflare R2 como alternativa | Fluxos `eleicoes-carga` e `eleicoes-ao-vivo` |
| Estado da carga das eleições | Bucket privado `lumen-privado` | Os mesmos fluxos |
| Dados dos painéis | GitHub Pages (`https://dracon-46.github.io/FalkyriaLumen/`) | Fluxo `paineis-site` |
| Estado dos painéis | Anexos da versão `painel-estado` do repositório | Fluxos `paineis` e `paineis-carga` |
| Núcleo transacional | Supabase gratuito, organização própria do projeto | Pendente |

## Portal

### Vercel (em uso)

O projeto da Vercel importa este repositório com *Root Directory* `packages/portal` e a variável
`NEXT_PUBLIC_DADOS_ELEICOES` igual ao endereço público do bucket dos feeds
(`https://<ref>.supabase.co/storage/v1/object/public/lumen-eleicoes`). O
[`vercel.json`](https://github.com/Dracon-46/FalkyriaLumen/blob/main/packages/portal/vercel.json)
roda `npm ci` e `npm run build` e cancela a geração quando o portal não mudou
(`git diff --quiet HEAD^ HEAD -- .`). Os `rewrites` repassam `/api/siconfi/dca` (governos municipais, ADR-040), `/api/precos/material` e `/api/precos/servico`
à pesquisa de preços do Compras.gov.br, que não aceita pedido de outro site (ADR-036). Cada um vale com e sem
a barra final, porque o `trailingSlash` do portal faz o Vercel redirecionar para a barra antes do `rewrite`; no Cloudflare Pages
esse caminho não existe, e a comparação de preço diz que não respondeu. Nenhum token fica no GitHub. O plano Hobby é para uso não
comercial.

### Cloudflare Pages (alternativa)

[`portal-pages.yml`](https://github.com/Dracon-46/FalkyriaLumen/blob/main/.github/workflows/portal-pages.yml)
roda a cada mudança em `packages/portal/**` na `main` e à mão: verifica o portal (tipos e testes),
gera com `NEXT_PUBLIC_DADOS_ELEICOES` = `LUMEN_URL_FEEDS` e publica `out/` com `wrangler` (cria o
projeto na primeira vez). Sem o segredo `CLOUDFLARE_API_TOKEN` ou a variável `CF_PAGES_PROJETO`, gera
o portal e avisa que não publicou, sem falhar. Com o R2, o bucket dos feeds precisa liberar leitura
(CORS, `GET` e `HEAD`) para o endereço do Pages:

```json
[
  {
    "AllowedOrigins": ["https://lumen.pages.dev"],
    "AllowedMethods": ["GET", "HEAD"],
    "MaxAgeSeconds": 3600
  }
]
```

O bucket público do Supabase responde à leitura de qualquer origem, sem CORS a configurar.

## Feeds das eleições

### Supabase Storage (em uso)

Sem meio de pagamento. Os segredos e variáveis têm os mesmos nomes do R2: `R2_ENDPOINT` com o
endereço S3 do projeto (`https://<ref>.storage.supabase.co/storage/v1/s3`), as chaves S3 do painel
do Supabase, `R2_REGIAO` com a região do projeto (ex.: `sa-east-1`, obrigatória) e
`LUMEN_URL_FEEDS` com `https://<ref>.supabase.co/storage/v1/object/public/lumen-eleicoes`.
Configurado em 14/10/2026: projeto `lumen`, região `sa-east-1`, buckets `lumen-eleicoes` (público)
e `lumen-privado`.

### Cloudflare R2 (alternativa)

1. Conta gratuita; ativar o R2; criar `lumen-eleicoes` (público, endereço `r2.dev` habilitado) e
   `lumen-privado`.
2. Token da API S3 com Object Read & Write só nesses dois buckets; token com permissão
   *Cloudflare Pages: Edit*.
3. CORS no `lumen-eleicoes` com o endereço do Pages (acima).
4. Segredos e variáveis do GitHub (ver [[Configuração e variáveis|Configuracao-e-Variaveis]]).

Passar do Supabase para o R2 é trocar os valores dos segredos e variáveis e gerar o portal de novo
com o endereço novo.

### Como a publicação funciona

`lumen eleicoes publicar` e `preparar --nuvem` enviam só os arquivos cuja assinatura mudou, com
manifesto por grupo (`publicacao/<grupo>.json`, comprimido) e totais em `publicacao/_totais.json`.
O índice sobe por último, depois de todos. Os JSON sobem comprimidos com gzip. Antes de cada lote,
se o total publicado passou de `LUMEN_PUBLICACAO_LIMITE_MB` (900 MB por padrão no Supabase), a
publicação para com erro e o índice não sobe. Falha passageira de envio (408, 429, 5xx, rede, e 520 a
524 do Cloudflare na frente do Supabase) é tentada de novo. Com uma carga pronta num computador,
`lumen eleicoes publicar` envia o que falta.

## Fluxos do GitHub Actions

| Fluxo | Quando | O que faz | Segredos e variáveis |
|---|---|---|---|
| [`ci.yml`](https://github.com/Dracon-46/FalkyriaLumen/blob/main/.github/workflows/ci.yml) | Push na `main` e PR | Vocabulário, testes, ruff, banco e portal (ver [[Testes|Testes]]) | — |
| [`contrato.yml`](https://github.com/Dracon-46/FalkyriaLumen/blob/main/.github/workflows/contrato.yml) | Todo dia, 06:17 em Brasília, e à mão | Formato das fontes reais (campos e tipos); não bloqueia, alarma | `LUMEN_ML_TOKEN` (opcional) |
| [`eleicoes-carga.yml`](https://github.com/Dracon-46/FalkyriaLumen/blob/main/.github/workflows/eleicoes-carga.yml) | Todo dia, 04:41 em Brasília, e à mão | `preparar --nuvem --sem-portal --sem-bronze --apagar-zips --limite-minutos 280`: baixa, processa e publica; para antes do prazo e a próxima execução continua | `LUMEN_CONTATO`, `R2_*`, `ELEICOES_SEM_HISTORICO`, `PUBLICACAO_*` |
| [`eleicoes-ao-vivo.yml`](https://github.com/Dracon-46/FalkyriaLumen/blob/main/.github/workflows/eleicoes-ao-vivo.yml) | Agendado no dia da eleição (25/10/2026) e à mão | Espera até `AGENDA_INICIO`; `ao-vivo --eleicao <id> --intervalo <s> --nuvem --sem-bronze --limite-minutos 330`: publica a cada passada e, com a apuração em andamento no prazo, dispara a continuação | Os mesmos da carga |
| [`eleicoes-medir.yml`](https://github.com/Dracon-46/FalkyriaLumen/blob/main/.github/workflows/eleicoes-medir.yml) | À mão | Gera os feeds sem publicar e mede total, grupos, maiores arquivos e o pior caso de saída por visitante; resultado no resumo e num artefato de sete dias | `LUMEN_CONTATO` |
| [`nuvem-diagnostico.yml`](https://github.com/Dracon-46/FalkyriaLumen/blob/main/.github/workflows/nuvem-diagnostico.yml) | À mão | Grava dois objetos em `_diagnostico/` (um comum e um com gzip) e lê pelo endereço público, para saber se o armazenamento devolve o `Content-Encoding` | `R2_*`, `LUMEN_URL_FEEDS` |
| [`portal-pages.yml`](https://github.com/Dracon-46/FalkyriaLumen/blob/main/.github/workflows/portal-pages.yml) | Mudança no portal na `main`, e à mão | Verifica, gera e publica no Cloudflare Pages | `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `LUMEN_URL_FEEDS`, `CF_PAGES_PROJETO` |
| [`paineis.yml`](https://github.com/Dracon-46/FalkyriaLumen/blob/main/.github/workflows/paineis.yml) | Todo dia, 05:17 em Brasília, e à mão | Dias do PNCP que faltam entre os últimos cinco, cadastro de entes do SICONFI, séries da Economia (SGS, com o Ipeadata quando o BC recusa), estatais (CVM e SEST), portais de transparência (PNTP), extrato de entregas em cinco grupos de UFs e publicação do site | `LUMEN_CONTATO` |
| [`paineis-carga.yml`](https://github.com/Dracon-46/FalkyriaLumen/blob/main/.github/workflows/paineis-carga.yml) | À mão | Meses anteriores do PNCP em blocos de dias, no máximo quatro máquinas ao mesmo tempo; publica no fim | `LUMEN_CONTATO` |
| [`paineis-site.yml`](https://github.com/Dracon-46/FalkyriaLumen/blob/main/.github/workflows/paineis-site.yml) | Chamado pelos dois acima, e à mão | Baixa o estado, roda `lumen painel publicar` e publica no GitHub Pages | — |
| [`mercado-referencia.yml`](https://github.com/Dracon-46/FalkyriaLumen/blob/main/.github/workflows/mercado-referencia.yml) | À mão | Regra A-05 com dados reais, em modo silencioso: PNCP, itens, ANP e o relatório como artefato de sete dias | `LUMEN_CONTATO` |

Repositório: [`wiki.yml`](https://github.com/Dracon-46/FalkyriaLumen/blob/main/.github/workflows/wiki.yml)
copia `docs/wiki/` para a Wiki,
[`release.yml`](https://github.com/Dracon-46/FalkyriaLumen/blob/main/.github/workflows/release.yml)
cria a release de cada tag de versão e
[`organizacao.yml`](https://github.com/Dracon-46/FalkyriaLumen/blob/main/.github/workflows/organizacao.yml)
aplica rótulos e marcos de `.github/organizacao.json`.

### Entradas dos fluxos manuais

| Fluxo | Entrada | Padrão | Efeito |
|---|---|---|---|
| `eleicoes-carga` | `anos` | vazio (todos) | Anos dos dados abertos, separados por vírgula; preenchida, vale mesmo com `ELEICOES_SEM_HISTORICO=true` |
| | `sem_ao_vivo` | falso | Pula o sistema de resultados |
| | `historico` | falso | Inclui 1933 a 2026 mesmo com `ELEICOES_SEM_HISTORICO=true` |
| `eleicoes-ao-vivo` | `eleicao` | obrigatória | Id do catálogo do TSE (ex.: `2026-2t-geral`) |
| | `intervalo` | 30 | Segundos entre passadas |
| | `agendada` | falso | Espera `AGENDA_INICIO`, como a execução agendada (uso do próprio fluxo) |
| | `continuacao` | 0 | Continuações já feitas depois do prazo da máquina (uso do próprio fluxo; até 3) |
| `eleicoes-medir` | `so_2026` | verdadeiro | Só 2026, sem os dados abertos |
| | `anos` | 2022 | Com `so_2026` desmarcado, anos a medir |
| | `limite_minutos` | 300 | Para a coleta e mede o que houver |
| `paineis` | `ultimos` | 5 | Quantos dias até ontem conferir |
| | `conformidade` | falso | Coleta também a conformidade |
| `paineis-carga` | `de`, `ate`, `partes` | 2026-01-01, ontem, 12 | Período e número de blocos |
| `mercado-referencia` | `de`, `ate`, `fonte_anp`, `semestres`, `series`, `objeto`, `janelas` | ver o arquivo | Janela de compras, fonte da ANP e várias janelas numa execução |

`eleicoes-carga` e a coleta do `eleicoes-ao-vivo` compartilham o grupo de concorrência `eleicoes-carga`
(a espera agendada do `eleicoes-ao-vivo` tem grupo próprio): uma espera a outra terminar, porque as duas disputariam o índice publicado. O grupo guarda uma só
execução na espera: se outra entra na fila (a agendada, por exemplo), a que esperava é cancelada
sem rodar. Foi o que aconteceu em 16/10/2026 com a carga de 2026 disparada junto com o ensaio do
`eleicoes-ao-vivo`. Dispare uma de cada vez, com a fila do grupo vazia.

### Primeira configuração das eleições

1. Configurar o armazenamento (Supabase ou R2) e os segredos e variáveis.
2. Actions → `eleicoes-carga` → *Run workflow*. A primeira carga de todos os anos leva algumas horas,
   em duas ou três execuções (2,3 GB de arquivos do TSE). A primeira carga com o histórico, em
   14/10/2026, publicou 342 mil arquivos em 3h17.
3. Gerar o portal apontando para o bucket (Vercel, ou Actions → `portal-pages`).

Sem os segredos do bucket, a execução agendada só avisa; a disparada à mão falha, para mostrar o
motivo.

### Painéis

Na conformidade, depois do extrato de entregas, cada máquina coleta a receita corrente líquida (RREO, Anexo 03,
6º bimestre do exercício anterior) dos entes que ainda não a têm, para os grupos de pares (`rcl-<UF>.json.gz`,
ADR-038). O tipo de RREO de cada ente vem do extrato, e assim sai uma consulta por ente; a primeira carga leva
perto de 25 minutos por máquina, e as seguintes quase nenhuma.

Por fim, a mesma máquina coleta a despesa por função (DCA, Anexo I-E, do último exercício) dos entes que
entregaram a DCA e ainda não a têm (`despesa-funcao-<UF>.json.gz`, ADR-041). São perto de 1,3 segundo por ente,
e o passo para de começar lote novo depois de 30 minutos (`--limite-minutos 30`). A primeira carga de um grupo
grande leva duas execuções, e quem não foi consultado fica para a seguinte.

A situação das coletas fica no portal, em `/operacao/` (link no rodapé; ADR-039): a última execução e
a última com sucesso de cada fluxo de dados, o volume diário do PNCP contra o usual e a coleta da
conformidade por UF, com os alertas no topo. O `paineis-site` grava as execuções com `gh run list` antes de
publicar, e por isso ele e os fluxos que o chamam têm a permissão `actions: read`.

O estado fica nos anexos da versão `painel-estado`, criada pelo fluxo na primeira execução. Um dia
só é gravado quando a coleta terminou sem falha nem resposta de erro; um dia com falha volta na
execução seguinte. A primeira carga, de janeiro de 2026 em diante, leva várias execuções de
`paineis-carga` (perto de 8 minutos por dia coletado). O GitHub Pages foi configurado em 14/10/2026
(Settings → Pages → Source: GitHub Actions).

## Noite da eleição

Roteiro a partir dos fluxos, do código e das ADRs; o roteiro oficial está no DOC-12.

**Antes**

1. Confirmar que a carga diária (`eleicoes-carga`) está passando e o portal está no ar, lendo do
   bucket certo.
2. Medir com `eleicoes-medir` o tamanho dos feeds e o pior caso de saída por visitante. No Supabase
   gratuito, a saída tem cota de 5 GB sem cache e 5 GB com cache por mês, somados a tudo o que a
   organização usa. A medição de 13/10/2026 deu cerca de 1 MB por visitante e hora na visão Brasil
   e cerca de 9 MB na visão de um estado grande.
3. Ensaiar a tela com `lumen eleicoes simular` (apuração fictícia a partir de arquivos finais).
4. Conferir o id da eleição com `lumen eleicoes catalogo` (ex.: `2026-2t-geral`).

**Durante**

1. O `eleicoes-ao-vivo` começa sozinho: tem agendamentos horas antes, porque o GitHub atrasa os
   agendamentos (de 4 a 7 horas e meia em outubro de 2026), e espera até `AGENDA_INICIO` (16h45 de
   Brasília em 25/10/2026). Espera maior que 5h30 termina disparando o próprio fluxo, que continua
   esperando. De manhã, confira em Actions que há uma execução esperando. À mão: Actions →
   `eleicoes-ao-vivo` → *Run workflow*, com o id da eleição e o intervalo (padrão 30 s), com nada do
   grupo `eleicoes-carga` rodando ou na fila: a carga diária em andamento atrasa o início, e outra
   execução que entre na fila cancela a que espera.
2. O coletor consulta o TSE com requisições condicionais, regrava só os feeds que mudaram e publica
   a cada passada. Uma publicação que falha não para o coletor: sai no registro e a passada seguinte
   publica de novo.
3. O portal relê os feeds a cada 15 segundos (`Cache-Control: no-cache`, 304 quando nada mudou).
4. A execução para quando a totalização termina, ou quando todas as seções estão totalizadas e
   nada muda há 60 minutos, mesmo sem a marca de finalizada do TSE (no 1º turno de 2026, os
   deputados de Rondônia ficaram assim, e o ensaio de 16/10/2026 rodou até ser cancelado). Aos 330
   minutos, com a apuração em andamento, o coletor para ao fim da passada e o fluxo dispara a
   continuação (até três), que segue do estado guardado.

**Depois**

- A carga diária segue. Quando o TSE acrescentar o turno aos dados abertos do ano, o `preparar`
  confere a fonte a cada execução e reprocessa (2026 é o ano em aberto,
  [ADR-029](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-029.md)).
- Com `ELEICOES_SEM_HISTORICO=true`, a configuração da nuvem desde 14/10/2026, a carga diária não
  lê os dados abertos, nem os do ano em aberto: dispare `eleicoes-carga` com `anos` = 2026. Antes,
  confira o espaço. O 1º turno de 2026 coletado ao vivo ocupa 32 MB (medição de 13/10/2026); o de
  2022 pelos dados abertos ocupou 74,5 MB, e o 2º turno mais 9,4 MB (medições de 14/10/2026). Com o
  bucket em 844,8 MB em 19/10/2026, a troca passa perto do teto de 900 MB do Supabase gratuito.

Localmente, o equivalente é `lumen eleicoes ao-vivo --eleicao <id> --nuvem`.

## Limites do plano gratuito

Verificados em 7/10/2026 (ADR-026; DOC-10, seção 9.5) e no adendo da ADR-026.

| Serviço | Limite | Sinal para a primeira despesa |
|---|---|---|
| Supabase Storage | 1 GB de arquivos (50 MB por arquivo); 5 GB de saída sem cache e 5 GB com cache por mês; passou, os projetos podem ser restringidos até o mês seguinte; pausa após 1 semana sem uso | Feeds de 1933 a 2026 somam perto de 850 MB com gzip (85% do 1 GB); a publicação para antes de 900 MB |
| Supabase (banco) | 500 MB de banco por projeto; 2 projetos ativos | Passar de 500 MB: plano Pro |
| Cloudflare R2 | 10 GB-mês, 1 milhão de escritas e 10 milhões de leituras por mês; saída grátis; o endereço `r2.dev` tem limite de requisições e é para desenvolvimento | Passar de 10 GB: US$ 0,015 por GB-mês |
| Cloudflare Pages | Até 20.000 arquivos por site e 25 MiB por arquivo | Domínio próprio, pago à parte |
| GitHub Actions | 6 horas por execução; 2.000 minutos por mês só em repositório privado | O repositório é público desde 14/10/2026 |
| Versão `painel-estado` | Até mil anexos: perto de três anos de dias | Antes disso, juntar os dias de meses fechados num arquivo por mês |
| Vercel Hobby | Uso não comercial | — |

A carga diária mantém o projeto do Supabase ativo, porque lê e grava no bucket todo dia.

## Como reverter

- **Código e portal:** reverta o commit por PR. Na Vercel, o push na `main` que muda
  `packages/portal` gera o site de novo; no Cloudflare Pages, o `portal-pages` roda na mudança ou à
  mão.
- **Feeds das eleições:** são refeitos a partir das fontes oficiais. `lumen eleicoes preparar
  --refazer` ignora o registro do que já foi feito, e a publicação só envia o que mudou, com o índice
  por último. Se uma carga passar do teto, o índice publicado anterior continua valendo.
- **Trocar de armazenamento:** troque os valores dos segredos e variáveis `R2_*` e gere o portal de
  novo com o endereço novo.
- **Painéis:** o site é refeito inteiro a cada publicação a partir do estado; rode `paineis-site` à
  mão para refazê-lo. Para coletar de novo um dia já guardado, use `lumen painel contratacoes
  --refazer` com o período.
- **Banco:** as tabelas de prova não aceitam alteração nem remoção, de propósito. Correções entram
  como novos registros (nova versão de regra, nova transição de estado), nunca reescrevendo os
  antigos.
- **Decisões:** uma ADR nunca é apagada; marque-a como rejeitada ou substituída.
