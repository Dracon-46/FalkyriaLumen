# Componentes

O repositório é um monorepo com pacotes separados
([ADR-010](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-010.md)). Os pacotes
Python ficam em `packages/<nome>/lumen_<nome>/`, com os testes em `packages/<nome>/testes/`;
`pip install -e .` deixa todos importáveis e instala o comando `lumen`. A descrição função por
função está no
[DOC-11 Referência Técnica](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/DOC-11_Referencia_Tecnica.docx),
gerado das docstrings.

```
packages/
  canonico/       esquema canônico, identidade, documentos, UFs, porte, rótulos, migrações SQL
  ingestao/       porta FonteDados, bronze (disco e S3), cliente HTTP, adaptadores PNCP, IBGE, SICONFI
  normalizacao/   bronze → silver, regras de qualidade e quarentena
  deteccao/       parâmetros legais datados e verificados
  conformidade/   avaliação das entregas obrigatórias ao SICONFI (LRF)
  orquestracao/   pipeline local e o comando `lumen`
  mercado/        regra A-05 em modo silencioso: ANP, varejo, leitor de .xlsx, relatório
  eleicoes/       aba Eleições: TSE ao vivo e dados abertos, feeds, publicação, servidor local
  painel/         painéis de contratações e de conformidade
  portal/         portal Next.js: Eleições, Contratações e Conformidade
ferramentas/      verificador de vocabulário e extrator da referência técnica
testes/           fixtures reais, testes de contrato e de integração
infra/            docker compose com PostgreSQL e MinIO
docs/             documentos .docx, diagramas e ADRs
docs-src/         fonte dos documentos
```

## `packages/canonico` — `lumen_canonico`

Modelo canônico: entidades, identidade, documentos e rótulos públicos. Guarda também
`VERSAO_LUMEN`, a versão do sistema.

| Módulo | O que faz |
|---|---|
| `fato.py` | Bloco de fato administrativo do DOC-05: `EnteFederativo`, `Orgao`, `UnidadeGestora`, `AmparoLegal`, `ProcessoContratacao`, `ItemContratacao`, `ResultadoItem`, `Contrato`, `AtaRegistroPreco`, `EntregaSiconfi`, com sensibilidade declarada por campo |
| `indicio.py` | Entidade `Indicio` e a máquina de estados; publicação exige evidência, um revisor na severidade média e dois revisores distintos na alta |
| `identidade.py` | `id_canonico`: UUIDv5 a partir da chave natural; recusa chave com parte vazia |
| `documentos.py` | CNPJ (inclusive alfanumérico) e CPF: dígito verificador, raiz, máscara |
| `rotulos.py` | Todo texto fixo exibido ao público, como "Atividade para análise" e o aviso metodológico |
| `porte.py` | Porte do ente pela população (base do grupo de pares) |
| `ufs.py` | UFs: código IBGE, sigla, nome e região |
| `migrations/` | `0001_dominio.sql` e `0002_search_path.sql` (ver [[Banco de dados|Banco-de-Dados]]) |

## `packages/ingestao` — `lumen_ingestao`

Coleta das fontes públicas e preservação da prova.

| Módulo | O que faz |
|---|---|
| `portas.py` | Porta `FonteDados` (capacidades, listar, baixar, reportar conformidade), `Janela`, `coletar_janela` |
| `bronze.py` | `ArmazemBronzeLocal`: conteúdo guardado uma vez sob o SHA-256, um registro por evento de coleta, hash reconferido na leitura ([ADR-011](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-011.md)) |
| `armazem_s3.py` | `ArmazemBronzeObjetos`: a mesma bronze em armazenamento de objetos, com Object Lock |
| `s3.py` | `ClienteS3` mínimo com SigV4, escrita condicional e `Cache-Control` ([ADR-018](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-018.md)) |
| `coleta_http.py` | Coleta HTTP com User-Agent do Lumen; resposta de erro volta como artefato ([ADR-012](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-012.md)); desfaz gzip e deflate de transporte |
| `cliente_http.py` | `ClienteHttp` com `LimitadorTaxa`, `PoliticaRetentativa` e suspensão da fonte; 429 reduz a vazão pela metade |
| `adaptadores/api/pncp.py` | `FontePncpContratacoes`, `FontePncpContratos`, `FontePncpAtas` (por publicação, vigência ou atualização) e `FontePncpItens` |
| `adaptadores/api/siconfi.py` | `FonteSiconfiEntes`, `FonteSiconfiExtrato` e `FonteSiconfiDemonstrativo` (RREO, RGF, DCA) |
| `adaptadores/api/ibge.py` | `FonteIbgeLocalidades` e `FonteIbgePopulacao` |
| `adaptadores/api/_paginacao.py`, `_simples.py` | Peças comuns: dias da janela, paginação, listas fixas de URLs |

## `packages/normalizacao` — `lumen_normalizacao`

Transforma artefatos do bronze em registros canônicos na silver.

| Módulo | O que faz |
|---|---|
| `pncp.py` | Contratações, itens, resultados, contratos e atas; resolve o ente pelo órgão e liga o amparo legal ao parâmetro datado |
| `siconfi.py` | Cadastro de entes e extrato de entregas |
| `ibge.py` | Estados, municípios e população estimada |
| `qualidade.py` | Quarentena (`EntradaQuarentena`) e resultado da normalização |
| `transformacoes.py` | Conversões de valor: decimal, moeda brasileira, datas, instantes em horário de Brasília |
| `comum.py` | Contexto de proveniência e conversão de campo com quarentena |
| `silver.py` | `EscritorSilver` (JSON Lines particionado, troca atômica), `ler_entidade`, `consolidar` |
| `sql/silver_consolidada.sql` | Macro do DuckDB com a mesma regra de `consolidar` |

## `packages/deteccao` — `lumen_deteccao`

| Módulo | O que faz |
|---|---|
| `parametros_legais.py` | `ParametrosLegais`: consulta pela data do ato; parâmetro não verificado é recusado por padrão ([ADR-013](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-013.md)) |
| `parametros_legais.toml` | Limites de dispensa de 2021 a 2026 (obras e engenharia, compras e serviços, manutenção de veículos), fator do § 2º, acréscimos do art. 125 e prazos da LRF, com fundamento e fonte de verificação |

O motor de regras é da Fase 2. Nenhuma regra da família B será implementada antes da revisão da
[ADR-022](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-022.md).

## `packages/conformidade` — `lumen_conformidade`

| Módulo | O que faz |
|---|---|
| `entregas_siconfi.py` | `avaliar_dca`, `avaliar_rreo`, `avaliar_rgf` e `ausentes`: entregas ao SICONFI contra o prazo legal, com resultado indeterminado quando a dúvida é do Lumen |

## `packages/orquestracao` — `lumen_orquestracao`

| Módulo | O que faz |
|---|---|
| `cli.py` | Comando `lumen`: `coletar`, `normalizar`, `bronze`, e repasse para `eleicoes`, `mercado` e `painel` |
| `etapas.py` | Etapas como funções sobre diretórios (futuros ativos do Dagster): `coletar`, `coletar_itens` (itens do PNCP sob demanda), `normalizar` |
| `configuracao.py` | Leitura do `lumen.toml` e do ambiente; limites de requisição por fonte |

## `packages/mercado` — `lumen_mercado`

Regra A-05, em modo silencioso: nada é publicado
([ADR-027](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-027.md)).

| Módulo | O que faz |
|---|---|
| `especificacao.py` | Reconhece só o que é inequívoco: combustíveis, gás de cozinha (13 kg) e informática padronizada |
| `anp.py` | Série semestral e planilhas semanais de preço de revenda da ANP |
| `varejo.py` | Ofertas do Mercado Livre pela API oficial (exige `LUMEN_ML_TOKEN`) |
| `referencia.py` | Distribuição de preços por lugar e época (mediana, quartis, quantidade) |
| `comparacao.py` | Razão entre o preço pago e a mediana; `ParametrosMercado` |
| `relatorio.py` | `comparacoes.csv`, `.jsonl`, `distribuicao.json` e `resumo.md` |
| `xlsx.py` | Leitor de `.xlsx` só com a biblioteca padrão |
| `cli.py` | `lumen mercado anp`, `varejo`, `comparar`, `reconhecer` |
| `parametros_mercado.toml` | Limiares iniciais, não calibrados (1,20 combustível; 1,25 gás de cozinha; 1,50 varejo) |

## `packages/eleicoes` — `lumen_eleicoes`

Aba Eleições: resultados oficiais do TSE, ao vivo e históricos. Não depende do motor de detecção.

| Módulo | O que faz |
|---|---|
| `tse.py` | URLs e leitura do sistema de divulgação de resultados (`resultados.tse.jus.br/oficial`) |
| `coletor.py` | `ColetorAoVivo`: requisições condicionais, andamento por UF e município, fila municipal com orçamento por passada |
| `dados_abertos.py` | Pacotes do Portal de Dados Abertos do TSE (CKAN e CDN), leitura por nome de coluna, votação por zona |
| `historico.py`, `carga.py` | Do ZIP dos dados abertos aos feeds; baixar e processar um ano |
| `antigas.py` | Eleições de 1933 a 1990, só por UF |
| `feeds.py` | Contrato dos feeds JSON (ver [[APIs e contratos|APIs-e-Contratos]]) |
| `modelo.py` | Modelo dos resultados, comum às duas fontes do TSE |
| `municipios.py`, `referencias.py`, `dados/` | Cadastro TSE ↔ IBGE e malhas do IBGE embutidos, com proveniência em `dados/LEIAME.md` |
| `geo.py` | Malhas do IBGE (API v3) e contornos finos dos municípios com mais de uma zona |
| `eleitorado.py` | Perfil do eleitorado, comparecimento por perfil e seções, do Brasil à seção, para o site dos painéis ([ADR-055](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-055.md)) |
| `votos_hora.py` | Votos por hora de cada seção, pelos logs das urnas lidos por pedaços (HTTP `Range`) dos arquivos transmitidos, para o site dos painéis ([ADR-057](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-057.md)) |
| `horarios.py` | Horários das urnas (abertura, encerramento, emissão e recebimento do boletim) de cada seção, do boletim de urna, para o site dos painéis ([ADR-056](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-056.md)) |
| `zonas.py` | Locais de votação de 2018 a 2026 para o mapa das zonas ([ADR-029](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-029.md)) |
| `transferencia.py` | Download de arquivos grandes com retomada e manifesto ([ADR-021](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-021.md)) |
| `preparacao.py` | `lumen eleicoes preparar`: a carga inteira num comando, retomável |
| `publicacao.py` | `Nuvem`: publicação no bucket S3 só do que mudou, gzip, manifesto por grupo, teto de tamanho |
| `configuracao.py` | Seções `[eleicoes]` e `[publicacao]` do `lumen.toml` |
| `verificacao.py`, `medicao.py` | Conferência dos feeds gravados e medição contra os limites gratuitos |
| `servidor.py`, `simulacao.py` | Servidor local (portal e feeds na mesma porta) e apuração fictícia para testar a tela |
| `cli.py` | `lumen eleicoes ...` |

## `packages/painel` — `lumen_painel`

Painéis de contratações e de conformidade fiscal, com fatos publicados e sem indício
([ADR-028](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-028.md)).

| Módulo | O que faz |
|---|---|
| `dia.py` | Um dia do PNCP reduzido ao que o painel usa; o dia só é gravado quando a coleta termina sem falha |
| `contratacoes.py` | Soma os dias por ente, órgão, esfera e UF; teto de plausibilidade dos valores; pessoa física só em soma anônima |
| `conformidade.py` | Extrato de entregas por UF e avaliação de cada ente na data do dia |
| `cadastro.py` | Cadastro dos entes do SICONFI: nome, UF, esfera, população, capital |
| `avisos.py` | Os avisos de cada local (J-01, valor a conferir, LRF, PNTP), com código estável, e as contestações lidas das issues ([ADR-047](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-047.md)) |
| `pares.py`, `rcl.py`, `despesa_funcao.py`, `pessoal.py` | Grupos de pares e o que se compara neles: RCL, despesa por função (DCA) e despesa com pessoal (RGF) ([ADR-038](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-038.md), [ADR-041](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-041.md) e [ADR-042](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-042.md)) |
| `operacao.py`, `cobertura.py` | Situação das coletas ([ADR-039](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-039.md)) e cobertura por ente e UF ([ADR-048](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-048.md)) |
| `cnpj.py`, `emendas.py`, `convenios.py` | Base de CNPJ da Receita dos fornecedores, emendas parlamentares e convênios da União pelos arquivos de dados abertos ([ADR-043](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-043.md), [ADR-044](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-044.md) e [ADR-045](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-045.md)) |
| `pessoas_juridicas.py` | Índice por CNPJ: contratos, emendas, convênios e contratos no tribunal de contas de cada empresa ou entidade ([ADR-049](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-049.md)) |
| `tce.py`, `tce_rs.py`, `tce_pr.py`, `tce_pe.py`, `tce_ce.py` | Contratos nos tribunais de contas: o comum (leitura por partes, quando reler, soma do ano, publicação), o LicitaCon do TCE-RS, o SIM-AM do TCE-PR, a API do TCE-PE e a do SIM do TCE-CE ([ADR-050](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-050.md)) |
| `mercado.py`, `transparencia.py` | Preços da ANP ([ADR-037](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-037.md)) e avaliação dos portais pelo PNTP ([ADR-035](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-035.md)) |
| `site.py` | Diretório publicado no GitHub Pages |
| `comum.py` | JSON em disco, códigos dos entes, modalidades do PNCP, links e valores |
| `cli.py` | `lumen painel cadastro`, `contratacoes`, `faltando`, `conformidade`, `publicar` |

## `packages/portal` — portal Next.js

Site estático (exportação estática, sem servidor Node em produção). Ver o
[README do portal](https://github.com/Dracon-46/FalkyriaLumen/blob/main/packages/portal/README.md).

| Caminho | O que tem |
|---|---|
| `src/app/` | Páginas: início, `/eleicoes/`, `/contratacoes/`, `/conformidade/`, `/economia/`, `/avisos/`, `/operacao/`, `/pessoa-juridica/`, `/novidades/` (o CHANGELOG, com o aviso das mudanças desde a última visita) e a página de não encontrado |
| `src/componentes/eleicoes/` | `PainelEleicoes`, `Mapa`, `ListaCandidatos`, `Panorama`, `GraficoEvolucao`, `TabelaZonas`, `Totais`, `Busca`, `Faixas` |
| `src/componentes/avisos/` | `PainelAvisos`: panorama do Brasil, avisos do local, filtros de tipo e período, link de contestação |
| `src/componentes/paineis/` | `PainelContratacoes`, `PainelConformidade`, `PainelOperacao` (com `CoberturaEntes`), `PainelPessoaJuridica` e peças comuns (aviso metodológico, busca, gráfico por mês, cartão da Receita) |
| `src/lib/tipos.ts`, `validacao.ts` | Tipos do contrato dos feeds e conferência na chegada: versão desconhecida é recusada |
| `src/lib/feeds.ts`, `paineis.ts` | Acesso aos feeds das eleições e aos dados dos painéis |
| `src/lib/topojson.ts`, `areas.ts`, `zoom.ts`, `voronoi.ts`, `zonas.ts` | Mapa: TopoJSON para SVG sem biblioteca, ligação área ↔ parte, aproximação, Voronoi das zonas |
| `src/componentes/BaixarCsv.tsx`, `src/lib/csv.ts` | O link "baixar CSV" das tabelas: todas as linhas, valores inteiros, `;` e vírgula decimal ([ADR-051](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-051.md)) |
| `src/lib/cores.ts`, `formato.ts`, `busca.ts`, `estado-url.ts`, `selecao.ts` | Paleta ([ADR-020](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-020.md)), formato pt-BR, busca, seleção na URL e regras de navegação |
| `src/lib/__testes__/` | Testes de unidade (vitest), que leem a amostra gerada pelo Python |

## `ferramentas/`

| Ferramenta | O que faz |
|---|---|
| [`lint-vocabulario/`](https://github.com/Dracon-46/FalkyriaLumen/tree/main/ferramentas/lint-vocabulario) | Verificador de vocabulário controlado ([ADR-007](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-007.md)); a lista e os alvos estão em `vocabulario.json` |
| [`referencia/`](https://github.com/Dracon-46/FalkyriaLumen/tree/main/ferramentas/referencia) | Extrai a referência técnica do código (Python e TypeScript) para o DOC-11 e falha se algo ficar sem documentação ([ADR-023](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-023.md)) |

## `testes/`

| Diretório | O que tem |
|---|---|
| `fixtures/` | Respostas reais das fontes (PNCP, SICONFI, IBGE, TSE) e a amostra versionada dos feeds (`eleicoes_feed`) |
| `contrato/` | Testes do formato das fontes reais (campos e tipos), diários e não bloqueantes |
| `integracao/` | Migrações no PostgreSQL |

Ver [[Testes|Testes]].

## `infra/`

[`docker-compose.yml`](https://github.com/Dracon-46/FalkyriaLumen/blob/main/infra/docker-compose.yml)
com PostgreSQL 16, MinIO e a criação do bucket `lumen-bronze` com Object Lock. Ver
[README de infra](https://github.com/Dracon-46/FalkyriaLumen/blob/main/infra/README.md).

## `docs-src/`

Fonte dos documentos `.docx`: `lib.js` (estilo comum), um `build_NN_*.js` por documento,
`diagrams/*.mmd` (Mermaid) e `referencia.json` (gerado, fora do Git). `make docs` extrai a referência
e gera todos os `.docx`; `npm run diagrams` regenera os PNG. Ver o
[README de docs-src](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs-src/README.md).

## Raiz

| Arquivo | Para quê |
|---|---|
| `pyproject.toml` | Pacote `falkyria-lumen`, versão, extras `dev` e `analitico`, comando `lumen`, configuração do ruff e do pytest |
| `Makefile` | Atalhos: `instalar`, `testes`, `cobertura`, `vocabulario`, `estilo`, `verificar`, `docs`, `ambiente`, `banco`, `contrato`, `portal` |
| `lumen.toml.exemplo` | Modelo da configuração local (o `lumen.toml` real não vai para o Git) |
| `preparar.cmd` | Aba Eleições pronta com dois cliques no Windows |
| `conftest.py` | Configuração comum da suíte e acesso às fixtures |
