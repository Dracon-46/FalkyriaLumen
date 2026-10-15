# Falkyria Lumen

Sistema de monitoramento de contratações e despesas públicas do Brasil.

O Lumen coleta, normaliza e analisa dados de contratações e despesas públicas de entes
federativos brasileiros, sinalizando atividades que merecem análise por parte de órgãos de
controle, imprensa e sociedade civil.

> **O sistema publica indícios, nunca conclusões.** Toda sinalização é rotulada como
> *atividade para análise*, acompanhada da evidência primária, da regra aplicada e de seus
> parâmetros. A determinação de que houve desvio, fraude ou crime cabe exclusivamente aos <!-- lumen:vocabulario-ok: aviso que nega a imputação -->
> órgãos de controle e ao Poder Judiciário. Essa restrição não é apenas editorial: ela é
> imposta no código, no modelo de domínio e no pipeline de publicação.

Este repositório contém a **documentação completa do projeto**, a **Fase 0** concluída (camada
de prova, máquina de estados do indício, parâmetros legais datados, vocabulário controlado), o
**núcleo da Fase 1** (coleta e normalização do PNCP, IBGE e SICONFI, conformidade da LRF) e a
**aba Eleições** do portal, com resultados oficiais do TSE ao vivo e desde 1933, e os **painéis de
Contratações e de Conformidade**, com o que cada ente publicou no PNCP e as entregas da LRF ao
Tesouro. O desenvolvimento segue o plano descrito no DOC-10.

## Ver a aba Eleições funcionando

No Windows: copie `lumen.toml.exemplo` para `lumen.toml`, preencha o contato em `[coleta]` e
dê dois cliques em **`preparar.cmd`**. Em qualquer sistema, com o Python 3.11+ e o Node.js 20.9+:

```bash
python -m pip install -e .
lumen eleicoes preparar --servir
```

O navegador abre em `http://127.0.0.1:8080/eleicoes/` antes da carga terminar, e cada eleição
aparece assim que fica pronta. Os resultados não vêm no repositório — são vários GB de arquivos
oficiais do TSE, e a prova de cada número é o SHA-256 da cópia baixada da fonte —, então a
primeira vez baixa tudo: o 1º turno de 2026 com todos os municípios, as eleições de 1933 a 1990
(só por estado, como o TSE publica) e as de 2024 a 1994 (2,3 GB, algumas horas). O mapa e o
cadastro de municípios já vêm com o Lumen. Pode interromper e rodar de novo: o que já foi feito
não é refeito. Detalhes no DOC-12, seção 9.1.

## Na nuvem, sem computador ligado

A carga, a publicação e o portal rodam em serviços gratuitos (ADR-026): a carga no GitHub
Actions, os feeds no Cloudflare R2 e o portal no Cloudflare Pages. A carga é retomável entre
execuções: o estado fica num bucket privado, e cada execução só envia o que mudou.

| Fluxo | Quando | O que faz |
|---|---|---|
| `eleicoes-carga.yml` | todo dia às 04:41 e à mão | `preparar --nuvem`: baixa, processa e publica no R2; para antes do prazo da máquina e a próxima execução continua |
| `eleicoes-ao-vivo.yml` | à mão, na noite da eleição | `ao-vivo --nuvem`: publica a cada passada |
| `portal-pages.yml` | a cada mudança do portal na main, e à mão | gera o portal apontando para o R2 e publica no Pages |

Configuração, uma vez (passo a passo com as telas no DOC-12, seção 9.5):

1. **Cloudflare:** conta gratuita; ativar o R2; criar os buckets `lumen-eleicoes` (público,
   endereço `r2.dev` habilitado) e `lumen-privado`; um token da API S3 com Object Read & Write
   só nesses dois buckets; um token com permissão *Cloudflare Pages: Edit*.
2. **CORS** no `lumen-eleicoes` (Settings → CORS Policy, aba JSON), com o endereço do Pages:

   ```json
   [
     {
       "AllowedOrigins": ["https://lumen.pages.dev"],
       "AllowedMethods": ["GET", "HEAD"],
       "MaxAgeSeconds": 3600
     }
   ]
   ```

3. **GitHub** (Settings → Secrets and variables → Actions):

   | Segredo | Valor | Variável | Valor |
   |---|---|---|---|
   | `LUMEN_CONTATO` | e-mail da coleta | `R2_BUCKET_FEEDS` | `lumen-eleicoes` |
   | `R2_ENDPOINT` | `https://<conta>.r2.cloudflarestorage.com` | `R2_BUCKET_ESTADO` | `lumen-privado` |
   | `R2_CHAVE_ACESSO` | Access Key ID | `LUMEN_URL_FEEDS` | `https://pub-….r2.dev` |
   | `R2_CHAVE_SECRETA` | Secret Access Key | `CF_PAGES_PROJETO` | `lumen` |
   | `CLOUDFLARE_API_TOKEN` | token do Pages | | |
   | `CLOUDFLARE_ACCOUNT_ID` | id da conta | | |

4. Actions → `eleicoes-carga` → *Run workflow* (a primeira carga leva duas ou três execuções);
   depois Actions → `portal-pages` → *Run workflow*.

**Sem cartão:** o Supabase Storage gratuito (1 GB, 5 GB de saída por mês) recebe os feeds com os
mesmos nomes acima: `R2_ENDPOINT` com o endereço S3 do projeto, as chaves S3 do painel, a variável
`R2_REGIAO` (a região do projeto, ex.: `sa-east-1`) e `LUMEN_URL_FEEDS` com
`https://<ref>.supabase.co/storage/v1/object/public/lumen-eleicoes`. Com os JSON comprimidos,
1933 a 2026 somam perto de 850 MB e cabem; a publicação para antes de 900 MB
(`PUBLICACAO_LIMITE_MB`). `ELEICOES_SEM_HISTORICO=true` deixa só 2026. Actions → `eleicoes-medir`
mede o tamanho dos feeds e o pior caso de saída por visitante (DOC-12, seção 9.7). É a configuração
escolhida para o 2º turno de 2026.

**Portal na Vercel, sem token:** o projeto da Vercel (plano Hobby, gratuito) importa este
repositório com *Root Directory* `packages/portal` e a variável `NEXT_PUBLIC_DADOS_ELEICOES` igual a
`LUMEN_URL_FEEDS`; `packages/portal/vercel.json` só gera de novo quando o portal muda. O fluxo
`portal-pages.yml` continua verificando o portal e só publica no Cloudflare Pages se houver token.

Nenhuma chave vai para o repositório nem para o `lumen.toml`. Com a carga já pronta num
computador, `lumen eleicoes publicar` envia ao R2 o que falta (variáveis de ambiente em
`lumen.toml.exemplo`, seção `[publicacao]`). O núcleo do Lumen (indícios, revisão,
contestação) vai para um projeto do Supabase no plano gratuito, numa organização própria do
projeto; os dados volumosos ficam em Parquet no R2.

---

## A ideia central

Cobrir os 5.570 municípios, 26 estados, o Distrito Federal e a União parece exigir milhares
de raspadores. Não exige.

Duas bases federais de envio obrigatório já concentram dados de praticamente todos os entes:

| Base | O que traz | Acesso |
|---|---|---|
| **PNCP** (Lei 14.133/2021) | Contratações, contratos, atas, planos e o **amparo legal** de cada contratação | API pública, sem autenticação |
| **SICONFI** (Tesouro Nacional) | RREO, RGF e DCA de estados e municípios | API aberta, sem cadastro |

Integrar essas duas fontes entrega alcance nacional em semanas. A raspagem municipal deixa de
ser o caminho crítico e vira incremento sobre um sistema que já funciona em escala.

E a lacuna também é dado: os entes ausentes dessas bases são, por definição, entes que
descumpriram uma obrigação legal de envio. Essa lista alimenta o módulo de conformidade.

## O que o sistema procura

O catálogo de detecção está organizado em famílias (DOC-07). Duas decisões merecem destaque:

**Valores pequenos são cidadãos de primeira classe.** A família B detecta fracionamento de
despesa — múltiplas contratações diretas que, somadas, ultrapassam o limite legal de dispensa.
Nenhuma dessas regras dispara olhando um documento isolado; todas dependem de agregar o
conjunto. É exatamente por isso que esses padrões sobrevivem à fiscalização tradicional, que
examina processos individualmente.

**A materialidade é relativizada pelo porte do ente.** Uma contratação modesta em um município
de cinco mil habitantes pode representar parcela relevante do orçamento. Sem essa
relativização, o sistema reproduziria o viés de atenção que existe para corrigir.

## Documentação

| Doc | Conteúdo |
|---|---|
| [DOC-01](docs/DOC-01_Visao_e_Escopo.docx) | Visão e Escopo — por que o projeto existe, o que faz e o que nunca fará |
| [DOC-02](docs/DOC-02_Requisitos.docx) | Requisitos funcionais e não-funcionais, numerados e rastreáveis |
| [DOC-03](docs/DOC-03_Casos_de_Uso.docx) | Casos de uso com fluxos principais, alternativos e exceções |
| [DOC-04](docs/DOC-04_Arquitetura.docx) | Arquitetura, decisões registradas (ADRs) e estratégia de escala |
| [DOC-05](docs/DOC-05_Modelo_de_Dados.docx) | Esquema canônico, dicionário de dados e resolução de identidade |
| [DOC-06](docs/DOC-06_Catalogo_de_Fontes.docx) | Fontes por esfera e estratégia de cobertura nacional |
| [DOC-07](docs/DOC-07_Motor_de_Deteccao.docx) | Catálogo de regras com fórmulas, limiares e falsos positivos |
| [DOC-08](docs/DOC-08_Politica_Juridica_e_Editorial.docx) | Base legal, vocabulário controlado, LGPD e direito de resposta |
| [DOC-09](docs/DOC-09_Padroes_de_Codigo.docx) | Convenções, testes, CI/CD e definição de pronto |
| [DOC-10](docs/DOC-10_Roadmap.docx) | Fases, marcos, esforço, custos e critérios de replanejamento |
| [DOC-11](docs/DOC-11_Referencia_Tecnica.docx) | Referência técnica: arquivo por arquivo, função por função (gerada do código) |
| [DOC-12](docs/DOC-12_Eleicoes.docx) | Aba Eleições: idealização, fontes, arquitetura, operação e integração |
| [DOC-13](docs/DOC-13_Paineis.docx) | Painéis de Contratações e Conformidade: fontes, estado, regras de soma e de avaliação, operação |

Os diagramas estão em [`docs/diagramas/`](docs/diagramas/) em PNG. As decisões
arquiteturais estão em [`docs/adr/`](docs/adr/README.md); o histórico de versões, no
[CHANGELOG](CHANGELOG.md).

## Princípios inegociáveis

Têm precedência sobre qualquer requisito funcional. Em caso de conflito, a funcionalidade é
descartada ou redesenhada.

1. **Evidência antes de afirmação** — nenhum indício sem o documento primário armazenado, com
   URL de origem, hash SHA-256 e carimbo de tempo.
2. **Linguagem neutra obrigatória** — vocabulário controlado verificado automaticamente na
   integração contínua; termos que imputam conduta quebram o build.
3. **Reprodutibilidade** — qualquer indício deve poder ser reproduzido por terceiros a partir
   dos dados públicos e da especificação da regra.
4. **Simetria de correção** — erratas e remoções têm o mesmo destaque da publicação original.
5. **Ausência de dado é informação** — quando um ente não publica o que a lei obriga, isso é
   um achado, não um obstáculo.
6. **Coleta responsável** — identificação em todas as requisições, respeito a limites de taxa,
   preferência pela API oficial e nenhuma tentativa de contornar controle técnico de acesso.

## Stack

| Camada | Tecnologia | Situação |
|---|---|---|
| Ingestão, normalização e detecção | Python 3.11+, só biblioteca padrão (ADR-015) | em uso |
| Camada bronze (prova) | Disco local ou armazenamento de objetos S3 com Object Lock (ADR-018) | em uso |
| Camada silver | JSON Lines particionado, lido por DuckDB (ADR-016) | em uso |
| Domínio, indícios e auditoria | PostgreSQL 16; na nuvem, Supabase Free (ADR-026) | migração testada |
| Portal | Next.js com exportação estática (ADR-019) | aba Eleições |
| Orquestração | Dagster | Fase 2 |
| Busca textual | OpenSearch | Fase 3 |
| API pública | Node.js + TypeScript | Fase 3 |
| Hospedagem sem custo | Cloudflare R2 (feeds, estado, Parquet), Cloudflare Pages (portal), GitHub Actions (carga) — ADR-026 | fluxos prontos |

A justificativa de cada escolha está registrada como ADR (DOC-04 e `docs/adr/`).

## Regenerar a documentação

Os `.docx` são gerados por script, não editados à mão. A fonte está em `docs-src/`.

```bash
make docs          # extrai a referência do código (DOC-11) e gera todos os .docx em docs/

cd docs-src
npm run diagrams   # requer mermaid-cli; regenera os PNGs a partir dos .mmd
```

Regra de estilo aplicada nos documentos: texto corrido e títulos sempre em preto; cor apenas
em tabelas e diagramas.

## Desenvolvimento

Requer Python 3.11 ou superior; o portal requer Node 20.9 ou superior.

```bash
python -m pip install -e ".[dev,analitico]"   # pacotes, comando `lumen` e DuckDB (opcional)

python ferramentas/lint-vocabulario/lint_vocabulario.py   # vocabulário controlado
python ferramentas/referencia/referencia.py --verificar   # tudo documentado (DOC-11)
python -m pytest                                          # suíte completa
make portal                                               # tipos, testes e build do portal
```

Com `make`: `make verificar` roda o que a CI roda no Python; `make ambiente` sobe PostgreSQL e
MinIO (`infra/docker-compose.yml`); `make banco` testa a migração no PostgreSQL.

Configuração local: copie `lumen.toml.exemplo` para `lumen.toml` e preencha o contato (vai no
User-Agent de toda requisição).

### Pipeline de contratações (Fase 1)

```bash
lumen coletar pncp_contratacoes --de 2026-09-01 --modalidades 8
lumen coletar ibge_localidades --de 2026-10-05
lumen coletar siconfi_extrato --de 2026-10-05 --entes 3550308 --exercicio 2025
lumen normalizar                 # bronze → silver, idempotente
lumen bronze verificar           # reconfere o hash de toda a prova
```

### Aba Eleições

```bash
lumen eleicoes preparar --servir                       # tudo num comando, retomável
lumen eleicoes preparar --nuvem --limite-minutos 280   # a mesma carga publicando no R2 (ADR-026)
lumen eleicoes publicar                                # envia ao bucket os feeds que mudaram
lumen eleicoes medir                                   # tamanho dos feeds contra os limites gratuitos
lumen eleicoes municipios                              # cadastro TSE ↔ IBGE corrente (um já vem com o Lumen)
lumen eleicoes mapas                                   # malhas do IBGE correntes (idem)
lumen eleicoes zonas --anos 2026,2024                  # locais de votação: mapa das zonas eleitorais (ADR-029)
lumen eleicoes historico baixar --anos 2022,1950       # dados abertos, 1933 a 2024 (ou --anos todos)
lumen eleicoes historico processar --anos 2022,1950
lumen eleicoes ao-vivo --eleicao 2026-1t-geral         # noite da apuração
lumen eleicoes simular                                 # apuração fictícia para testar a tela
lumen eleicoes servir                                  # portal + feeds em http://127.0.0.1:8080
```

Sem rede, `python -m lumen_eleicoes --saida packages/portal/public/dados/eleicoes amostra` gera
feeds de exemplo com resultados oficiais de alguns estados e municípios (e de 1945, 1950 e 1989),
com o mapa. Detalhes no DOC-12.

### Referência de mercado (regra A-05, em modo silencioso)

Compara o preço pago com uma régua de fora do governo (ADR-027): o preço de revenda
da ANP para combustíveis e gás de cozinha (GLP P13) e ofertas do varejo, pela API
oficial da loja, para informática padronizada. Nada é publicado: o resultado é um
relatório interno até a calibração.

```bash
lumen coletar pncp_contratacoes --de 2026-05-04 --ate 2026-05-15 --modalidades 6,8
lumen coletar ibge_localidades --de 2026-10-09        # nomes dos municípios
lumen normalizar
lumen coletar pncp_itens --de 2026-05-04 --ate 2026-05-15 --objeto "combust|gasolina|diesel|etanol|glp"
lumen normalizar --fontes pncp_itens
lumen mercado anp baixar --semestres 2026-1 --series ca,glp   # série histórica da ANP
lumen mercado anp semanas --de 2026-09-01 --ate 2026-10-03    # ou as planilhas semanais (desde 2022-09)
lumen mercado comparar --de 2026-05-04 --ate 2026-05-15
lumen mercado varejo testar --consulta "notebook i5 8gb ssd 256gb"
lumen mercado reconhecer "ÓLEO DIESEL S10" --unidade Litro
```

O relatório fica em `dados/mercado/relatorio/` (`comparacoes.csv`, `.jsonl`,
`distribuicao.json` com a razão por grupo para calibrar e `resumo.md`). Na nuvem, o fluxo `mercado-referencia.yml` faz o mesmo e guarda o
relatório como artefato da execução; a entrada `janelas` junta várias janelas curtas numa execução, para
calibrar com amostras maiores. O varejo só funciona com o segredo
`LUMEN_ML_TOKEN` (sem credencial, a busca do Mercado Livre responde 403). Lojas sem API pública (Magazine Luiza, KaBuM,
Pichau, comparadores) ficam de fora por decisão: ver a ADR-027.

### Painéis de contratações e conformidade

Fatos publicados, sem indício (ADR-028, DOC-13): o que cada ente e cada órgão publicou no PNCP
(processos, contratos, órgãos, fornecedores pessoa jurídica, com o link de cada publicação) e se
as contas anuais, o RREO e o RGF constam do extrato do Tesouro, contra o prazo da LRF.

```bash
lumen painel cadastro --estado estado/                      # cadastro de entes do SICONFI
lumen painel contratacoes --estado estado/ --ultimos 3      # dias do PNCP que faltam
lumen painel conformidade --estado estado/ --ufs RS,SC      # extrato de entregas por UF
lumen painel publicar --estado estado/ --saida site/        # o site inteiro, a partir do estado
```

Na nuvem: `paineis.yml` (todo dia; a conformidade às segundas), `paineis-carga.yml` (meses
anteriores, em máquinas paralelas) e `paineis-site.yml` (publica no GitHub Pages). O estado fica
nos anexos da versão `painel-estado`; o portal lê de `https://dracon-46.github.io/FalkyriaLumen/`.

### Estrutura

```
packages/
  ingestao/       porta FonteDados, camada bronze (disco e S3), cliente HTTP, adaptadores PNCP, IBGE, SICONFI
  canonico/       esquema canônico (fatos e indício), identidade, documentos, UFs, porte, migração SQL
  normalizacao/   bronze → silver: PNCP, IBGE, SICONFI, regras de qualidade e quarentena
  deteccao/       parâmetros legais datados e verificados
  conformidade/   avaliação das entregas obrigatórias ao SICONFI (LRF)
  orquestracao/   pipeline local e o comando `lumen`
  mercado/        regra A-05: itens comparáveis, preço da ANP (semestral e semanal), varejo por API oficial,
                  leitor de .xlsx sem dependências, relatório e distribuição para calibrar
  eleicoes/       aba Eleições: coletor do TSE, dados abertos (1933 a 2024), feeds, preparar,
                  mapa e cadastro embutidos, simulação, servidor local
  painel/         painéis de contratações (PNCP por ente e órgão) e conformidade (entregas da LRF)
  portal/         portal Next.js: Eleições, Contratações e Conformidade
ferramentas/
  lint-vocabulario/   verificador de vocabulário controlado (ADR-007)
  referencia/         extrai a referência técnica e cobra documentação de tudo (ADR-023)
testes/
  fixtures/       respostas reais das fontes, capturadas e documentadas
  contrato/       testes do esquema da fonte contra as fontes reais (diários, não bloqueiam)
  integracao/     migração no PostgreSQL
infra/            docker compose com PostgreSQL e MinIO
docs/             documentos (.docx), diagramas e ADRs
docs-src/         fonte dos documentos
```

## Situação do projeto

**Fase 0 — Fundação: concluída.** Marco M1 cumprido e verificado por teste (`test_marco_m1.py`).
Os limites de dispensa de 2021 a 2026, o fator de consórcios e agências executivas e os
acréscimos do art. 125 foram conferidos no texto oficial e cadastrados; a migração do domínio
roda no PostgreSQL; o backend de objetos (S3/MinIO) da camada bronze está implementado.

**Fase 1 — Espinha dorsal nacional: núcleo pronto.** Adaptadores do PNCP (contratações,
contratos, atas, itens e resultados), do IBGE (localidades e população) e do SICONFI (entes e
extrato de entregas); normalização com quarentena; silver idempotente reconstruível do bronze;
avaliação das entregas da LRF com lista de ausentes; pipeline local e testes de contrato
diários.

**Aba Eleições: pronta para uso.** Coleta ao vivo do sistema de resultados do TSE, eleições
passadas desde 1933 pelos dados abertos (por município de 1994 em diante; antes, por estado),
mapa interativo por estado e município, busca, modo TV, simulação de apuração e carga completa
num comando (`lumen eleicoes preparar`, ou `preparar.cmd` no Windows). Escolher um município no
mapa abre o município e, nos 190 com mais de uma zona eleitoral, mostra as zonas, com quem lidera
em cada uma e uma tabela ligada ao mapa; o contorno das zonas é aproximado pelos locais de votação,
e a tela diz isso (ADR-029).

**Painéis de Contratações e Conformidade: no ar desde 14/10/2026.** Para o Brasil, cada ente e
cada órgão (inclusive autarquias e empresas públicas municipais), o que foi publicado no PNCP; para
cada estado e município, as entregas da LRF ao Tesouro contra o prazo legal. Sem indício e sem
ordenação por risco (ADR-028).

| Componente | Testes |
|---|---|
| Ingestão (bronze, S3, cliente HTTP, adaptadores) | 114 |
| Esquema canônico e máquina de estados do indício | 194 |
| Parâmetros legais | 39 |
| Normalização | 116 |
| Conformidade (SICONFI) | 14 |
| Pipeline local | 8 |
| Aba Eleições (Python, inclusive a publicação na nuvem e as zonas) | 225 |
| Painéis de contratações e conformidade | 28 |
| Vocabulário controlado e referência técnica | 66 |
| Portal (TypeScript) | 107 |

Cobertura de 97% no Python. Todo módulo, classe e função tem documentação (verificado por teste).

### Pendente

- **Revisar as ADRs 011 a 029** (todas propostas, tomadas durante a implementação).
- **Resultado por zona de 2026**: os dados abertos de votação de 2026 (453 MB) saíram em
  15/10/2026; com 2026 em `ANOS_GERAIS`, o 1º turno passa a vir deles, com as zonas (ADR-029).
- **Calibrar a regra A-05** sobre o relatório silencioso antes de qualquer publicação (ADR-027).
- **Contas da hospedagem gratuita** (ADR-026): Cloudflare (R2 e Pages), segredos do GitHub e
  uma organização própria do projeto no Supabase para o núcleo (DOC-12, seção 9.5). Feeds das
  eleições no Supabase Storage desde 14/10/2026, com o histórico (seção 9.7).
- **Revisão metodológica e jurídica da regra B-01** frente ao art. 75, § 1º, da Lei 14.133
  (ADR-022), antes da Fase 2.
- **Fonte para "quem autorizou o ato"**: a API do PNCP não publica o agente (ADR-017).
- **Portais da transparência municipais** (ADR-028): o que não passa pelo PNCP — estatais da
  Lei 13.303 que não publicam lá e o que o município só publica no próprio portal. Cadastro do
  portal de cada município, conformidade de transparência (RF-CF-01, 03, 04) e leitura por
  fornecedor de sistema.
- Fase 1 restante: Portal da Transparência (CGU, com CEIS/CNEP/CEPIM), base de CNPJ da Receita
  Federal, grupos de pares e painel operacional (DOC-10).

### Definições pendentes antes da publicação, conforme DOC-10

- **Nome definitivo** — "Lumen" é nome de trabalho e precisa de verificação de disponibilidade
  de marca (INPI) e domínio, como foi feito para a marca Falkyria.
- **Natureza institucional** — projeto pessoal, produto da empresa ou iniciativa sem fins
  lucrativos; afeta a percepção de imparcialidade.
- **Abertura do código** — reforça a credibilidade da metodologia, mas exige disciplina
  adicional de documentação e governança.
- **Apoio jurídico** — a revisão da política editorial por advogado é critério de saída da
  Fase 5 e precisa ser contratada com antecedência.

## Aviso

A documentação deste repositório consolida a política interna do projeto e o entendimento que
fundamenta suas escolhas de desenho. Não constitui parecer jurídico. Valores legais, limites e
endpoints citados foram verificados em fontes oficiais entre setembro e outubro de 2026 e são atualizados
periodicamente por decreto — reconfira antes de implementar.
