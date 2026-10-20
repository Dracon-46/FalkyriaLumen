# APIs e contratos

O Lumen não tem API HTTP própria de escrita. A API pública está prevista para a Fase 3 (RF-PU-08,
UC-14). Hoje o projeto tem três tipos de interface:

1. as **fontes oficiais** que ele consome;
2. os **arquivos JSON** que ele publica e o portal lê (feeds das eleições e dados dos painéis);
3. a **linha de comando** `lumen`.

## Fontes consumidas

Todas as requisições se identificam no User-Agent com a versão do Lumen e o contato configurado
(RF-CO-09), respeitam o limite de taxa de cada fonte e preferem a API oficial (princípio P6). As
respostas são guardadas na camada bronze como prova, inclusive as de erro HTTP.

### PNCP — Portal Nacional de Contratações Públicas

Código: [`adaptadores/api/pncp.py`](https://github.com/Dracon-46/FalkyriaLumen/blob/main/packages/ingestao/lumen_ingestao/adaptadores/api/pncp.py).

| Base | Recurso | Fonte no Lumen |
|---|---|---|
| `https://pncp.gov.br/api/consulta` | `/v1/contratacoes/publicacao` | `pncp_contratacoes` |
| | `/v1/contratacoes/atualizacao` | `pncp_contratacoes_atualizacao` |
| | `/v1/contratos` | `pncp_contratos` |
| | `/v1/contratos/atualizacao` | `pncp_contratos_atualizacao` |
| | `/v1/atas` (por vigência) | `pncp_atas` |
| | `/v1/atas/atualizacao` | `pncp_atas_atualizacao` |
| `https://pncp.gov.br/api/pncp` | `/v1/orgaos/<cnpj>/compras/<ano>/<sequencial>/…` (itens e resultados da contratação) | `pncp_itens` |
| | `/v1/modalidades` (domínio oficial das modalidades) | — |

Comportamentos registrados nas fixtures e no código: `codigoModalidadeContratacao` é obrigatório em
`/v1/contratacoes/*`; página vazia responde 204 sem corpo; janela maior que 365 dias responde 422; o
PNCP limita a vazão com 429, e o cliente reduz a taxa pela metade pelo resto da sessão. Os painéis
apontam cada número para a página pública `https://pncp.gov.br/app/editais/…` ou
`https://pncp.gov.br/app/contratos/…`.

### SICONFI — Tesouro Nacional

Base `https://apidatalake.tesouro.gov.br/ords/siconfi/tt`. Código:
[`adaptadores/api/siconfi.py`](https://github.com/Dracon-46/FalkyriaLumen/blob/main/packages/ingestao/lumen_ingestao/adaptadores/api/siconfi.py).

| Recurso | Fonte no Lumen | Observação |
|---|---|---|
| `/entes` | `siconfi_entes` | Cadastro de entes |
| `/extrato_entregas` | `siconfi_extrato` | O que cada ente entregou, por exercício; base da conformidade |
| `/rreo`, `/rgf`, `/dca` | `siconfi_rreo`, `siconfi_rgf`, `siconfi_dca` | Conector pronto, normalização pendente; RGF com periodicidade `Q` ou `S` (LRF, art. 63) |

### IBGE

| Endereço | Uso |
|---|---|
| `https://servicodados.ibge.gov.br/api/v1/localidades/estados` e `/municipios` | Cadastro de UFs e municípios (`ibge_localidades`) |
| `https://servicodados.ibge.gov.br/api/v3/agregados/6579/periodos/<período>/variaveis/9324` | População estimada (`ibge_populacao`) |
| `https://servicodados.ibge.gov.br/api/v3/malhas` | Malhas do mapa da aba Eleições (`lumen eleicoes mapas`); as do Brasil por UF e das UFs por município, na qualidade mínima, já vêm com o Lumen |

### CGU — Portal da Transparência

| Endereço | Uso |
|---|---|
| `https://portaldatransparencia.gov.br/download-de-dados/ceis` (e `cnep`, `cepim`) | Página de download: declara a data do arquivo mais recente |
| `https://portaldatransparencia.gov.br/download-de-dados/ceis/AAAAMMDD` | ZIP do dia (redireciona para `dadosabertos-download.cgu.gov.br`), com um CSV em ISO-8859-1 separado por `;` (`cgu_ceis`, `cgu_cnep`, `cgu_cepim`) |

Sem chave: são os arquivos de dados abertos, e não a API, que pede `chave-api-dados`
([ADR-030](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-030.md)). Cada arquivo é o
cadastro inteiro num dia; a normalização grava `sancao` na silver, com o CPF de pessoa física mascarado e
a `data_referencia` do retrato.

### Banco Central — SGS (Economia e Contas Públicas)

| Endereço | Uso |
|---|---|
| `https://api.bcb.gov.br/dados/serie/bcdata.sgs.<código>/dados?formato=json` | Série inteira, sem chave: IPCA (433), INPC (188), Selic no mês (4390) e anualizada (4189), dívida bruta do governo geral (13762), DLSP (4513), NFSP primária (5793) e nominal (5727) em 12 meses, PIB em 12 meses (4382), variação real do PIB (7326), IBC-Br (24363), taxa de desocupação da PNAD Contínua (24369) |

O catálogo, com unidade, definição e limitações de cada série, fica em
`packages/economia/lumen_economia/catalogo.py`; o portal lê `economia/indicadores.json`, publicado com os
painéis ([ADR-033](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-033.md)).

### IBGE — SIDRA (séries da Economia que o SGS não tem conferidas)

| Endereço | Uso |
|---|---|
| `https://apisidra.ibge.gov.br/values/t/6579/n1/all/v/9324/p/all` | Estimativa anual da população do Brasil (grupo "População"), com as quebras de método de 2013 e 2024 marcadas na série |
| `https://apisidra.ibge.gov.br/values/t/6390/n1/all/v/5933/p/all` | Rendimento médio real habitual da PNAD Contínua, por trimestre móvel (`D3C` = `AAAAMM`, o último mês), sem chave; regravado inteiro a cada coleta, porque o IBGE o recalcula a cada divulgação (adendo de 20/10/2026 do ADR-033) |

### IBGE — notícias (releases ao lado dos indicadores da Economia)

| Endereço | Uso |
|---|---|
| `https://servicodados.ibge.gov.br/api/v3/noticias/?tipo=release&idproduto=<produto>&qtd=3` | Os três releases mais recentes da Agência de Notícias sobre o IPCA (9256), o INPC (9258), o PIB (9300) e a PNAD Contínua (9171), sem chave; vão em `releases` no indicador de `economia/indicadores.json` (adendo de 20/10/2026 do ADR-033) |

### CVM — dados abertos das companhias abertas (estatais com ações na bolsa)

| Endereço | Uso |
|---|---|
| `https://dados.cvm.gov.br/dados/CIA_ABERTA/CAD/DADOS/cad_cia_aberta.csv` | Cadastro (latin-1, `;`): as candidatas, que se declaram `ESTATAL` ou `ESTATAL HOLDING` e têm registro ativo |
| `https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/FRE/DADOS/fre_cia_aberta_AAAA.zip` | Formulário de Referência; o Lumen lê só `fre_cia_aberta_posicao_acionaria_AAAA.csv`, por `Range`, e só os controladores diretos pessoa jurídica |
| `https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/DFP/DADOS/dfp_cia_aberta_AAAA.zip` | Demonstrações do exercício; o Lumen lê DRE, DFC (MI ou MD) e DVA, consolidadas e individuais, e a lista de documentos, por `Range` |

Sem chave (`cvm_dados_abertos`). O controle é o do FRE, não o do cadastro, que não é atualizado depois de
privatizações ([ADR-034](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-034.md)).

### SEST — dados abertos das empresas estatais federais

| Endereço | Uso |
|---|---|
| `https://www.gov.br/gestao/pt-br/assuntos/estatais/transparencia/sestidentificacao.zip` | Cadastro das empresas ativas e inativas (cp1252, `;`): código SIEST, sigla, CNPJ, dependência do Tesouro, grupo |
| `https://www.gov.br/gestao/pt-br/assuntos/estatais/transparencia/sestpdg.zip` | Programa de Dispêndios Globais: aprovado e realizado acumulado mês a mês, por empresa, exercício e rubrica, de 2016 em diante |

Sem chave (`sest_dados_abertos`). Os dois arquivos vão para `economia-sest.json.gz` e, com os da CVM, para
`economia/estatais.json`, que o portal lê em `/economia/estatais/`.

### PNCP — modal da contratação e documentos (no navegador)

| Endereço | Uso |
|---|---|
| `https://pncp.gov.br/api/consulta/v1/orgaos/{cnpj}/compras/{ano}/{seq}` | Detalhe do processo: modalidade, fundamento legal, valores, datas, links (o caminho antigo em `/api/pncp/v1` responde 301) |
| `https://pncp.gov.br/api/pncp/v1/orgaos/{cnpj}/compras/{ano}/{seq}/itens?pagina=&tamanhoPagina=` | Itens do processo, em páginas de 50 (o portal lê até 500) |
| `https://pncp.gov.br/api/pncp/v1/orgaos/{cnpj}/compras/{ano}/{seq}/itens/{n}/resultados` | Vencedor e valor homologado do item (204 quando ainda não há) |
| `https://pncp.gov.br/api/pncp/v1/orgaos/{cnpj}/contratos/{ano}/{seq}` | Detalhe do contrato: fornecedor, valores, vigência, processo de origem |
| `https://pncp.gov.br/api/pncp/v1/orgaos/{cnpj}/contratos/{ano}/{seq}/termos` | Termos aditivos (204 quando não há) |
| `https://pncp.gov.br/api/pncp/v1/orgaos/{cnpj}/compras/{ano}/{seq}/arquivos` | Lista dos documentos de um processo (edital, aviso, termo de referência), com o link de download |
| `https://pncp.gov.br/api/pncp/v1/orgaos/{cnpj}/contratos/{ano}/{seq}/arquivos` | Lista dos documentos de um contrato |

O portal faz esses pedidos só quando a pessoa abre uma contratação. A API libera a leitura pelo navegador
(CORS), e o download é o do próprio PNCP. Fornecedor pessoa física aparece sem nome nem documento. Nada é copiado para o Lumen
([ADR-035](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-035.md)).

### Compras.gov.br — pesquisa de preços (no navegador, comparação de preço)

| Endereço | Uso |
|---|---|
| `https://dadosabertos.compras.gov.br/modulo-pesquisa-preco/1_consultarMaterial?tipo=codigoItemCatalogo&codigo=<CATMAT>&dataCompraInicio=&dataCompraFim=&pagina=&tamanhoPagina=500` | Compras de um material pelo código, com preço unitário, unidade de fornecimento e capacidade |
| `https://dadosabertos.compras.gov.br/modulo-pesquisa-preco/3_consultarServico?codigoItemCatalogo=<CATSER>&dataCompraInicio=&dataCompraFim=&pagina=&tamanhoPagina=500` | Compras de um serviço pelo código, com preço unitário e unidade de medida |

A API responde 403 a pedido com cabeçalho `Origin` de outro site. Por isso o portal chama
`/api/precos/material` e `/api/precos/servico`, que o Vercel repassa à fonte (`rewrites` no `vercel.json`).

Os governos municipais da Economia (ADR-040) leem, para o município escolhido e sob demanda: os resultados de
prefeito dos feeds da aba Eleições; a população do SIDRA (tabela 6579, nível `n6`, e a tabela 4709 para o Censo
2022), direto do navegador; e a DCA, Anexo I-E, de cada ano, por `/api/siconfi/dca`, que o Vercel repassa ao
SICONFI (`apidatalake.tesouro.gov.br/ords/siconfi/tt/dca`).
O `idCompra` de material vem como número maior que o inteiro seguro do JavaScript, e o portal usa os 17
primeiros caracteres de `idCompraItem`. O código do item vem do PNCP: `catalogo.id = 1` e
`catalogoCodigoItem`
([ADR-036](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-036.md)).

### PNTP — Radar da Transparência Pública (tribunais de contas e Atricon)

| Endereço | Uso |
|---|---|
| `https://radardatransparencia.atricon.org.br/downloads.html` | Lista as bases por ciclo |
| `https://radardatransparencia.atricon.org.br/dados/dados_pntp_AAAA.zip` | Base do ciclo (338 MB em 2025); o Lumen lê só `pntp_AAAA/avaliacoes_pntp_AAAA.xlsx`, por `Range` (`pntp_avaliacoes`) |

Uma linha por entidade avaliada (11.697 em 2025): índice e nível de transparência e endereço do portal
([ADR-032](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-032.md)). `lumen painel
transparencia` lê o ciclo mais recente todo dia e publica `transparencia/uf-<sigla>.json`, lido na página do ente em Conformidade.

### TSE

| Endereço | Uso |
|---|---|
| `https://resultados.tse.jus.br/oficial` | Sistema de divulgação de resultados: catálogo (`/comum/config/ele-c.json`), municípios, resultado por cargo e abrangência, andamento da totalização e fotos. Responde 304 a `If-Modified-Since` |
| `https://dadosabertos.tse.jus.br/api/3/action/package_show` | Portal de Dados Abertos (CKAN): pacote `resultados-<ano>` |
| `https://cdn.tse.jus.br/estatistica/sead/odsele` | ZIPs dos dados abertos (votação, detalhe da apuração, locais de votação `eleitorado_local_votacao_<ano>.zip`) |
| `https://cdn.tse.jus.br/estatistica/sead/eleicoes` | Evolução da totalização do Presidente (2018 em diante) |

Os ZIPs dos dados abertos ficam fora do bronze, com manifesto (URL, tamanho, SHA-256, ETag,
Last-Modified) registrado no bronze
([ADR-021](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-021.md)).

### ANP e varejo (regra A-05)

| Endereço | Uso |
|---|---|
| `https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/shpc/dsas` | Série semestral de preços de revenda (séries `ca` e `glp`) |
| `https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/serie-historica-de-precos-de-combustiveis` | Página da série |
| `https://www.gov.br/anp/pt-br/assuntos/precos-e-defesa-da-concorrencia/precos/levantamento-de-precos-de-combustiveis-ultimas-semanas-pesquisadas` | Página das planilhas semanais |
| `https://api.mercadolibre.com/sites/MLB/search` | Ofertas do varejo; exige `LUMEN_ML_TOKEN` |

O levantamento semanal da ANP vai para o fluxo diário dos painéis (`lumen painel anp`) e chega ao modal da
contratação como `mercado/anp/uf-<sigla>-<ano>.json`
([ADR-037](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-037.md)). Cada planilha tem
perto de 2 MB, 20 mil preços e 400 municípios.

As lojas online são outro caso:
- **Mercado Livre:** a busca responde 403 sem credencial (conferido em 19/10/2026).
- **Amazon, Shopee e AliExpress:** exigem conta de afiliado com chave.
- **Lojas sem API pública** (Magazine Luiza, Havan, KaBuM e outras): ficam de fora por decisão, porque extrair o
  site contraria os termos de uso e as barreiras contra robôs
  ([ADR-027](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-027.md), princípio 6).

## Contrato dos feeds das eleições

Definido em [`feeds.py`](https://github.com/Dracon-46/FalkyriaLumen/blob/main/packages/eleicoes/lumen_eleicoes/feeds.py)
e espelhado em [`tipos.ts`](https://github.com/Dracon-46/FalkyriaLumen/blob/main/packages/portal/src/lib/tipos.ts)
([ADR-019](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-019.md)).

### Versão

- Todo arquivo leva `versao`. A versão atual é **1** (`VERSAO_ESQUEMA_FEED` no Python,
  `VERSAO_FEED` no portal).
- O portal recusa versão desconhecida, tipo desconhecido ou campo obrigatório ausente
  ([`validacao.ts`](https://github.com/Dracon-46/FalkyriaLumen/blob/main/packages/portal/src/lib/validacao.ts)),
  em vez de exibir número errado.
- Mudança incompatível sobe a versão e atualiza os dois lados no mesmo commit. Campos opcionais e
  aditivos não mudam a versão (por exemplo `sem_numero`, `municipios: false` e as zonas em `partes`).
- O mapa das zonas tem versão própria, `VERSAO_ZONAS` = 1, igual no Python e no portal e conferida
  por teste.
- O contrato é testado dos dois lados: o Python gera a amostra versionada
  [`testes/fixtures/eleicoes_feed`](https://github.com/Dracon-46/FalkyriaLumen/tree/main/testes/fixtures/eleicoes_feed),
  conferida byte a byte, e os testes do portal leem a mesma amostra.

### Regras gerais

- Números são números (inteiros para votos, decimais com até 6 casas para percentuais), nunca texto
  com vírgula. Datas em ISO 8601 com fuso.
- Nenhum número é calculado além de somas e percentuais sobre os totais publicados; não há projeção.
- O feed não traz cor: traz `cor`, um índice de 0 a 7 (ou -1, cinza), atribuído pela ordem de
  votação no nível mais alto do cargo e fixo durante a noite. Nunca é cor de partido
  ([ADR-020](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-020.md)).
- O bloco `origem` liga cada número ao arquivo oficial: `fonte`, `url`, `sha256`, `coletado_em` e
  `registro_bronze`.

### Arquivos

| Caminho | Tipo | Conteúdo |
|---|---|---|
| `indice.json` | índice | `versao`, `gerado_em` e `eleicoes`: id, nome, ano, turno, tipo, data, `origem` (`resultados` ou `dados_abertos`), `ao_vivo`, `atualizado_em`, `cargos` (com `ufs` por cargo) e `ufs`; `municipios: false` nas eleições de 1933 a 1990 |
| `municipios.json` | cadastro | `versao` e `municipios` (UF, código TSE, código IBGE, nome, nome no TSE, capital), usado pela busca |
| `geo/br-uf.json`, `geo/uf-<sigla>-mu.json` | malha | TopoJSON do IBGE |
| `<eleição>/<cargo>/br.json` | `resultado` ou `panorama` | Brasil, com as UFs em `partes` |
| `<eleição>/<cargo>/uf-<sigla>.json` | `resultado` ou `panorama` | UF, com os municípios em `partes` |
| `<eleição>/<cargo>/mu-<chave>.json` | `resultado` | Município (a chave é o código IBGE quando há), com as zonas em `partes` quando ele tem mais de uma (só nos dados abertos) |
| `<eleição>/<cargo>/historico-<abrangência>.json` | `historico` | Evolução da totalização |
| `geo/zonas-<ano>/indice.json` | `zonas-indice` | Municípios com mais de uma zona e o número de zonas de cada um |
| `geo/zonas-<ano>/mu-<ibge>.json` | `zonas` | Zonas e locais de votação de um município |
| `fotos/…` | imagem | Fotos dos candidatos (sistema de resultados) |

### Tipo `resultado`

Campos: `versao`, `tipo: "resultado"`, `eleicao` (id, nome, ano, turno, tipo, data), `cargo` (slug,
código, nome, tipo `majoritario` ou `proporcional`, nível `br`, `uf` ou `mu`, vagas), `abrangencia`
(tipo, código, nome, UF, IBGE, TSE), `atualizado_em`, `ao_vivo`, `origem`, `totalizacao` (seções,
seções totalizadas, `pct_secoes`, `finalizada`, `matematicamente_definida`), `comparecimento`
(eleitorado, comparecimento, abstenção e percentuais), `votos` (válidos, brancos, nulos, anulados,
legenda e percentuais), `quociente_eleitoral`, `candidatos`, `candidatos_omitidos`, `agremiacoes`,
`partes` e `avisos`.

Cada candidato: `numero`, `nome_urna`, `nome`, `partido`, `agremiacao`, `composicao`, `votos`,
`pct`, `situacao`, `eleito`, `segundo_turno`, `valido`, `destinacao`, `vice`, `cor`, `foto` e, nas
eleições sem número de urna, `sem_numero: true`. Num município com centenas de candidatos a
deputado, o feed leva os mais votados e os eleitos e conta os demais em `candidatos_omitidos`; a
lista completa está no feed da UF.

Cada parte: `codigo`, `nome`, `ibge`, `lider`, `partido`, `nome_urna`, `votos`, `pct`, `margem`,
`cor`, `eleito`, `segundo_turno`, `pct_secoes`, `finalizada`, `eleitorado` e, nos proporcionais,
`bancada` ({partido: eleitos}). A parte de zona eleitoral não traz `bancada`, `eleito` nem
`segundo_turno`: quem se elege é decidido no município, na UF ou no Brasil.

### Tipo `panorama`

Usado onde não existe resultado único: cargo municipal na UF e no Brasil, cargo estadual no Brasil.
Campos: `versao`, `tipo: "panorama"`, `eleicao`, `cargo`, `abrangencia`, `atualizado_em`, `ao_vivo`,
`origem`, `totalizacao` (`partes`, `partes_finalizadas`, `pct_partes`), `partidos` (placar com
`partido`, `liderados`, `eleitos`, `votos`, `cor`, ordenado por eleitos, partes lideradas e votos),
`partes` e `avisos`.

### Tipo `historico`

Campos: `versao`, `tipo: "historico"`, `eleicao`, `cargo`, `abrangencia`, `origem`, `candidatos`
(número, nome de urna, partido, cor) e `pontos`, cada um com `t` (instante), `pct_secoes` e `votos`
({número: votos}).

### Tipos `zonas-indice` e `zonas`

- `zonas-indice`: `versao`, `tipo`, `ano`, `origem` e `municipios` ({código IBGE: número de zonas}).
- `zonas`: `versao`, `tipo`, `ano`, `municipio` (IBGE, TSE, UF, nome), `origem`, `zonas` (zona,
  locais, eleitores), `locais` (cada um `[longitude, latitude, zona, eleitores, nome]`) e
  `descartados` (`sem_coordenada`, `fora_do_municipio`).

O contorno de cada zona é calculado no portal (diagrama de Voronoi dos locais, recortado pelo
contorno do município) e apresentado como aproximação: a Justiça Eleitoral não publica os limites
das zonas ([ADR-029](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-029.md)).

### Cache

O portal relê os feeds de resultado com `cache: "no-cache"` e recebe 304 quando nada mudou; durante
a apuração, relê a cada 15 segundos. Na publicação, os feeds vão com `Cache-Control: no-cache`, e as
malhas, o cadastro e as fotos com cache de um dia. Os JSON sobem comprimidos com gzip
(`Content-Encoding: gzip`).

## Dados dos painéis

Gerados por `lumen painel publicar` e publicados no GitHub Pages
(`https://dracon-46.github.io/FalkyriaLumen/`), lidos por
[`paineis.ts`](https://github.com/Dracon-46/FalkyriaLumen/blob/main/packages/portal/src/lib/paineis.ts).
Versão do formato: `VERSAO_PAINEL` = 1
([`lumen_painel/__init__.py`](https://github.com/Dracon-46/FalkyriaLumen/blob/main/packages/painel/lumen_painel/__init__.py)).

| Caminho | Conteúdo |
|---|---|
| `indice.json` | Versão, quando foi gerado, cobertura de cada painel |
| `entes.json` | Cadastro para a busca: código, nome, UF, tipo, população |
| `orgaos.json` | Órgãos com publicação no período (CNPJ, razão social, ente, esfera, processos, contratos), para a busca |
| `contratacoes/panorama.json` | Brasil: totais, esferas, UFs, meses, modalidades, fornecedores |
| `contratacoes/ente/<código>.json` | Um ente: União (1), estado (2 dígitos), DF (53) ou município (7 dígitos) |
| `contratacoes/orgao/<CNPJ>.json` | Um órgão: prefeitura, câmara, autarquia, fundação ou empresa pública |
| `conformidade/panorama.json` | Brasil: resultados por UF e por obrigação |
| `conformidade/uf/<sigla>.json` | Entes da UF, com o resumo de cada um |
| `conformidade/ente/<código>.json` | Obrigações avaliadas de um ente e o grupo de pares (ADR-038) |
| `operacao.json` | Situação das coletas: fluxos de dados, volume diário do PNCP e coleta da conformidade (ADR-039) |
| `conformidade/pares/<id>.json` | Um grupo de pares: critérios, distribuição da fração no prazo e os entes que o formam |
| `transparencia/uf-<sigla>.json`, `transparencia/uniao.json` | Entidades avaliadas pelo PNTP, agrupadas pelo ente (ADR-035) |
| `mercado/anp/uf-<sigla>-<ano>.json` | Preço de revenda da ANP por semana e produto, na UF e em cada município (código IBGE): `[semana, n, mínimo, 1º quartil, mediana, 3º quartil, máximo]` (ADR-037) |

Processo ou contrato com valor acima de R$ 10 bilhões, ou de R$ 20 mil por habitante do ente (o que
for menor), conta nas quantidades, mas fica fora das somas e aparece em "Valores a conferir na
fonte" ([ADR-028](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-028.md),
decisão 8). Contrato com pessoa física ou estrangeira só entra numa soma anônima.

## Linha de comando

`lumen` é instalado por `pip install -e .`. Opção global: `--config <lumen.toml>` e `-v` (verboso).
`python -m lumen_eleicoes`, `python -m lumen_painel` e `python -m lumen_mercado` são equivalentes a
`lumen eleicoes`, `lumen painel` e `lumen mercado`.

### Pipeline

| Comando | O que faz |
|---|---|
| `lumen coletar <fonte> --de AAAA-MM-DD [--ate AAAA-MM-DD]` | Coleta uma fonte para o bronze. Fontes: `ibge_localidades`, `ibge_populacao`, `pncp_atas`, `pncp_atas_atualizacao`, `pncp_contratacoes`, `pncp_contratacoes_atualizacao`, `pncp_contratos`, `pncp_contratos_atualizacao`, `pncp_itens`, `siconfi_entes`, `siconfi_extrato`, `cgu_ceis`, `cgu_cnep`, `cgu_cepim` (estas três sem `--de`: a coleta pega o retrato mais recente), `pntp_avaliacoes` (sem `--de`; `--ciclos 2024,2025`) |
| `lumen deteccao j01 --estado DIR [--saida ARQ] [--resumo ARQ] [--privado]` | Regra J-01 em modo silencioso: contratos do painel × CEIS e CNEP; imprime só contagens (ADR-031) |
| `… --modalidades 6,8` | Só PNCP contratações: códigos de modalidade |
| `… --entes <IBGE> --exercicio <ano>` | Só SICONFI extrato |
| `… --objeto "<expressão>" [--sem-resultados] [--so-comparaveis]` | Só PNCP itens: itens dos processos da silver cujo objeto casa com a expressão |
| `lumen normalizar [--fontes <lista>]` | Bronze para silver, idempotente |
| `lumen bronze verificar` | Reconfere o hash de toda a prova |
| `lumen bronze listar` | Lista os registros do bronze |

### `lumen eleicoes`

Opções globais: `--config`, `--saida <diretório dos feeds>`, `-v`.

| Comando | O que faz |
|---|---|
| `preparar [--servir] [--anos] [--sem-ao-vivo] [--sem-historico] [--sem-zonas] [--sem-portal] [--sem-navegador] [--refazer] [--atualizar] [--nuvem] [--limite-minutos] [--apagar-zips] [--sem-bronze]` | Tudo num comando: mapa, portal e as eleições de 1933 a 2026; retomável |
| `publicar` | Envia ao bucket os feeds novos ou alterados |
| `catalogo` | Eleições disponíveis no sistema de resultados |
| `municipios [--eleicao]` | Grava `municipios.json` (TSE ↔ IBGE) |
| `mapas [--ufs] [--qualidade minima\|intermediaria\|maxima] [--contornos]` | Baixa as malhas do IBGE; `--contornos`, o contorno fino dos municípios com zonas |
| `zonas [--anos] [--atualizar]` | Locais de votação para o mapa das zonas (padrão: 2026 a 2018) |
| `ao-vivo --eleicao <id> [--cargos] [--ufs] [--intervalo] [--orcamento] [--uma-vez] [--parar-estavel] [--limite-minutos] [--nuvem] [--sem-bronze]` | Coleta a apuração em andamento; com `--limite-minutos`, sai com o código 3 se o prazo vencer antes do fim |
| `historico baixar --anos <lista\|todos> [--atualizar]` | Baixa os ZIPs dos dados abertos |
| `historico processar --anos <lista\|todos> [--limite-municipio]` | Gera os feeds a partir dos ZIPs |
| `simular [--eleicao] [--etapas] [--intervalo] [--ufs]` | Apuração fictícia a partir de arquivos finais |
| `amostra [--sem-referencias]` | Feeds de exemplo a partir das fixtures, sem rede |
| `servir [--site] [--host] [--porta]` | Serve o portal e os feeds localmente (padrão `http://127.0.0.1:8080`) |
| `verificar` | Confere o contrato dos feeds gravados |
| `medir [--resumo <arquivo>] [--maiores N]` | Tamanho dos feeds contra os limites gratuitos do R2 e do Supabase |

### `lumen painel`

| Comando | O que faz |
|---|---|
| `cadastro --estado <dir>` | Cadastro de entes do SICONFI |
| `contratacoes --estado <dir> [--de] [--ate] [--ultimos N] [--limite-minutos] [--refazer]` | Coleta os dias do PNCP que faltam no estado (padrão: os últimos 3 até ontem) |
| `faltando --estado <dir> [--de] [--ate] [--partes N]` | Blocos de dias que faltam, em JSON, para execuções paralelas |
| `conformidade --estado <dir> --ufs <siglas> [--exercicios]` | Extrato de entregas do SICONFI por UF (padrão: exercício anterior e corrente) |
| `transparencia --estado <dir>` | Ciclo mais recente do PNTP, só quando o arquivo muda (ADR-035) |
| `anp --estado <dir> [--maximo-semanas N]` | Planilhas semanais da ANP que faltam no estado, desde 2025, até 40 por execução (ADR-037) |
| `publicar --estado <dir> --saida <dir> [--hoje AAAA-MM-DD]` | Monta o site dos painéis a partir do estado |

### `lumen mercado`

| Comando | O que faz |
|---|---|
| `anp baixar --semestres <AAAA-S> --series ca,glp` | Série semestral da ANP para o bronze |
| `anp semanas --de --ate` | Planilhas semanais do levantamento para o bronze |
| `anp resumo` | O que foi lido dos arquivos guardados |
| `varejo coletar` / `varejo testar --consulta "<texto>"` | Ofertas do varejo pela API oficial (guardando no bronze, ou só testando) |
| `comparar [--de] [--ate] [--saida] [--parametros]` | Aplica a regra A-05 e grava o relatório silencioso |
| `reconhecer "<descrição>" [--unidade]` | Mostra a especificação reconhecida numa descrição |
