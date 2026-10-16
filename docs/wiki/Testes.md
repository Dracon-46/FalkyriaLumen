# Testes

Fonte: [DOC-09 Padrões de Código](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/DOC-09_Padroes_de_Codigo.docx),
seção 3, o [`Makefile`](https://github.com/Dracon-46/FalkyriaLumen/blob/main/Makefile) e a
[CI](https://github.com/Dracon-46/FalkyriaLumen/blob/main/.github/workflows/ci.yml).

## Como rodar

Instale as dependências de desenvolvimento uma vez: `make instalar`
(`python -m pip install -e ".[dev,analitico]"`).

| Comando | O que faz | Equivalente sem `make` |
|---|---|---|
| `make testes` | Suíte completa | `python -m pytest -q` |
| `make cobertura` | Suíte com cobertura; falha abaixo de 80% | `python -m pytest -q --cov=… --cov-report=term-missing --cov-fail-under=80` |
| `make vocabulario` | Verificador de vocabulário controlado | `python ferramentas/lint-vocabulario/lint_vocabulario.py` |
| `make estilo` | Análise estática | `python -m ruff check packages ferramentas testes` |
| `make verificar` | `vocabulario`, `estilo` e `cobertura`: o que a CI verifica no Python | — |
| `make contrato` | Testes de contrato contra as fontes reais (rede) | `LUMEN_TESTE_CONTRATO=1 python -m pytest -m contrato -q` |
| `make banco` | Migrações no PostgreSQL do ambiente local (`make ambiente` antes) | `LUMEN_TESTE_PG=postgresql://lumen:<senha local>@localhost:5432/lumen python -m pytest -m postgres -q` |
| `make portal` | Instala, verifica e gera o portal | `cd packages/portal && npm ci && npm run verificar && npm run build` |
| `python ferramentas/referencia/referencia.py --verificar` | Lista o que ficou sem documentação | — |

No portal:

```bash
cd packages/portal
npm run tipos       # tsc --noEmit
npm run testes      # vitest run
npm run verificar   # os dois
npm run build       # exportação estática em out/
```

A cobertura é medida sobre `lumen_ingestao`, `lumen_canonico`, `lumen_deteccao`,
`lint_vocabulario`, `lumen_normalizacao`, `lumen_conformidade`, `lumen_orquestracao`,
`lumen_eleicoes`, `lumen_mercado`, `lumen_painel` e `referencia`. O mínimo de 80% vem do RNF-28; o
README registra 97% no Python.

### Marcadores

O pytest roda com `--strict-markers`, que recusa marcador não declarado:

| Marcador | Quando roda |
|---|---|
| `contrato` | Consome a fonte real pela rede; só com `LUMEN_TESTE_CONTRATO=1`. O teste que baixa o detalhe da apuração de 2022 inteiro exige também `LUMEN_TESTE_CONTRATO_PESADO=1` |
| `postgres` | Exige PostgreSQL acessível em `LUMEN_TESTE_PG` e o cliente `psql`; cada execução cria um banco novo, aplica as migrações em ordem e o apaga no fim |

Sem essas variáveis, os testes marcados são pulados, e a suíte roda sem rede e sem banco.

### Documentação cobrada por teste

`test_todo_o_codigo_esta_documentado` falha se qualquer módulo, classe, função, método, componente,
interface ou tipo ficar sem texto: a CI recusa função nova sem documentação
([ADR-023](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-023.md)).

## Estágios da CI

[`ci.yml`](https://github.com/Dracon-46/FalkyriaLumen/blob/main/.github/workflows/ci.yml) roda a cada
push na `main` e a cada pull request, em `ubuntu-24.04` (imagem fixa, para a troca de imagem do
GitHub não mudar versões no meio de um ciclo). Uma execução nova no mesmo ramo cancela a anterior.

| Job | O que faz | Ambiente |
|---|---|---|
| `vocabulario` | `python ferramentas/lint-vocabulario/lint_vocabulario.py`: nenhum termo que impute conduta nos textos públicos ([ADR-007](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-007.md)) | Python 3.11, 5 min |
| `testes` | Suíte completa com cobertura mínima de 80%; instala `pytest`, `pytest-cov` e `duckdb` (para o teste da macro da silver) | Python 3.11, 3.12 e 3.13, 10 min, sem parar as outras versões quando uma falha |
| `estilo` | `ruff check packages ferramentas testes` | Python 3.11, 5 min |
| `banco` | Testes marcados `postgres`: somente-anexação, publicação condicionada a evidência e revisores, conformidade | Serviço `postgres:16`, 10 min |
| `portal` | `npm ci`, `npm run verificar` (tipos e testes) e `npm run build` | Node 22, 15 min |

O DOC-09 (seção 4.2) define vocabulário, testes, análise estática e migrações como estágios
bloqueantes. Se a CI verde é exigida para o merge depende da proteção do ramo `main` nas
configurações do repositório, que não fica registrada no código. Três estágios do DOC-09 ainda não
existem na `ci.yml`: formatador e organizador de imports como verificação separada (o ruff já
confere a ordem dos imports, regra `I`), verificação de tipos no Python e o estágio de segurança
(vulnerabilidade em dependências e segredo vazado).

### Testes de contrato (diários)

[`contrato.yml`](https://github.com/Dracon-46/FalkyriaLumen/blob/main/.github/workflows/contrato.yml)
roda todo dia às 06:17 em Brasília (e à mão). Consome as fontes reais e valida só o formato (campos e tipos), não o
conteúdo. Não bloqueia: uma falha quer dizer que uma fonte mudou de formato e o normalizador precisa
de revisão antes da próxima carga (DOC-09, seção 4.2). O teste do varejo fica pulado sem o segredo
`LUMEN_ML_TOKEN`.

## Estratégia (DOC-09)

| Camada | O que cobre | Meta |
|---|---|---|
| Unitário | Domínio, cálculo de score, transformações | 80% mínimo |
| Regra | Cada regra contra casos sintéticos positivos e negativos | 100% das regras |
| Contrato de fonte | Formato esperado de cada fonte externa | Todas as fontes com API |
| Integração | Pipeline do bruto ao indício em base de teste | Fluxos principais |
| Ponta a ponta | Casos de uso críticos pelo portal | UC-03, UC-08, UC-11 |
| Vocabulário | Ausência de termo proibido | Obrigatório |

Cada regra do catálogo terá ao menos um caso que deve disparar, um que não deve e um caso de falso
positivo conhecido, documentado no DOC-07. O motor de regras é da Fase 2.

## Contagem atual (README)

| Componente | Testes |
|---|---|
| Ingestão (bronze, S3, cliente HTTP, adaptadores) | 114 |
| Esquema canônico e máquina de estados do indício | 194 |
| Parâmetros legais | 39 |
| Normalização | 116 |
| Conformidade (SICONFI) | 14 |
| Pipeline local | 8 |
| Aba Eleições (Python) | 228 |
| Painéis de contratações e conformidade | 28 |
| Vocabulário controlado e referência técnica | 66 |
| Portal (TypeScript) | 110 |

## Fixtures reais

[`testes/fixtures/`](https://github.com/Dracon-46/FalkyriaLumen/tree/main/testes/fixtures) tem
respostas reais das fontes, capturadas em 05/10/2026 e versionadas
([README das fixtures](https://github.com/Dracon-46/FalkyriaLumen/blob/main/testes/fixtures/README.md)).
Elas permitem testar coleta e normalização sem rede e documentam o formato real de cada fonte, que
diverge da documentação oficial em vários pontos. O adaptador e o normalizador usam os mesmos bytes.

| Diretório | Conteúdo |
|---|---|
| `pncp/` | Páginas de contratações (dispensa e pregão), contratos e atas; uma compra com itens, arquivos e resultados; domínios oficiais (modalidades, modos de disputa, tipos de instrumento); erros 400 e 422 |
| `siconfi/` | Amostra de entes, extrato de entregas de um ente e linhas do RREO |
| `ibge/` | Estados, amostra de municípios, população e uma malha |
| `tse/` | Recortes do sistema de resultados (catálogo, municípios, resultados, andamento), dados abertos e locais de votação |
| `eleicoes_feed/` | Amostra versionada dos feeds gerada pelo Python e lida pelos testes do portal |

Listas longas foram cortadas, nunca editadas: os registros mantidos estão exatamente como a fonte
entregou, inclusive erros de digitação e valores esquisitos. Cada peculiaridade preservada tem teste,
por exemplo: ata com vigência no ano 7203 (vai para a quarentena), `valorTotalEstimado = 0` com
homologado nulo (aceito com marcação), esfera e poder `N` (viram nulo com marcação), página vazia do
PNCP com 204 sem corpo e a descrição do amparo legal com valor desatualizado (o limite vem de
`parametros_legais`, nunca desse texto).

Para recapturar: as URLs estão nos testes de contrato
([`test_contrato_fontes.py`](https://github.com/Dracon-46/FalkyriaLumen/blob/main/testes/contrato/test_contrato_fontes.py));
mantenha o corte descrito no README das fixtures e atualize a data.

A amostra dos feeds é regenerada por `python -m lumen_eleicoes --saida <dir> amostra --sem-referencias`;
mudança no contrato exige atualizar a amostra e os dois lados no mesmo commit.
