# Histórico de versões

Formato: o que mudou para quem usa e para quem desenvolve, por versão. As
decisões que justificam cada mudança estão nas ADRs citadas.

## 0.5.0 — 2026-10-07

### Na nuvem, sem custo e sem computador ligado (ADR-026)

- Hospedagem decidida com planos gratuitos: feeds e estado das cargas no
  Cloudflare R2, portal no Cloudflare Pages, carga no GitHub Actions e, para
  o núcleo transacional (migração 0001), o Supabase gratuito numa organização
  própria do projeto. Dados volumosos e só de leitura em Parquet no R2.
- `lumen eleicoes publicar`: envia ao bucket público só os feeds cujo SHA-256
  mudou (manifesto `publicacao.json` no bucket privado), o índice por último,
  com `Cache-Control: no-cache` nos feeds e cache de um dia nas malhas, no
  cadastro e nas fotos (`publicacao.py`).
- `preparar --nuvem`: restaura o índice publicado e o estado antes de
  começar e publica depois de cada ano e de cada passada do sistema de
  resultados; a carga continua numa máquina que começa vazia. Falha na
  restauração interrompe antes de carregar; falha na publicação vira erro no
  resumo e é reenviada na próxima sincronização.
- `preparar --limite-minutos` (para sozinha antes do prazo da máquina; a
  próxima execução continua) e `--apagar-zips` (apaga os ZIPs de cada ano
  depois de processado). O resumo ganha `publicados_na_nuvem` e
  `prazo_atingido`.
- `ao-vivo --nuvem`: publica a cada passada que gravou feeds.
- Seção `[publicacao]` no `lumen.toml` (endpoint e buckets); as chaves só em
  variáveis de ambiente (`LUMEN_S3_CHAVE_ACESSO`, `LUMEN_S3_CHAVE_SECRETA`).
- Fluxos do GitHub Actions: `eleicoes-carga.yml` (diário e manual),
  `eleicoes-ao-vivo.yml` (noite da eleição) e `portal-pages.yml` (portal no
  Pages, criando o projeto na primeira vez).
- `ClienteS3.gravar` aceita `cache` (cabeçalho `Cache-Control`).
- Testes contra um servidor S3 em memória: publicação só do que mudou,
  retomada em outra máquina, prazo, falhas de restauração e de publicação.
- Documentação: ADR-026, DOC-12 1.2 (seções 9.5 e 9.6, passo a passo da
  configuração), DOC-10 1.3 (seção 9.5), DOC-04 (seção 9), README.

## 0.4.0 — 2026-10-06

### Aba Eleições: todas as eleições, pronta num comando (ADR-025)

- Eleições de 1933 a 1990, só por UF, como o TSE publica: 19 anos, 23 eleições
  contando os turnos, lidas por inteiro dos três conjuntos por UF dos dados
  abertos (`antigas.py`). Candidatos sem número de urna (o feed marca
  `sem_numero`), cargos da época (vice-presidente, vice-governador e suplente
  de senador votados em separado; vereador em 1934), UFs extintas ou com
  outro território com código próprio e fora do mapa atual (Guanabara, o
  Distrito Federal antes de 1960, territórios), Guaporé e Rio Branco na área
  de Rondônia e Roraima. Avisos da regra de voto válido da época (também em
  1994 e 1996) e de divergências da fonte; percentuais nunca somam mais de
  100%. Os 1.670 feeds passam em `verificar`.
- `lumen eleicoes preparar [--servir]`: mapa e cadastro, portal, servidor e
  navegador, o 1º turno de 2026 pelo sistema de resultados com todos os
  municípios, e os dados abertos de 1933 a 1990 e de 2024 a 1994. Retomável
  (`<estado>/preparar.json`), segue depois de erro num ano. `preparar.cmd`
  faz o mesmo no Windows com dois cliques.
- Malhas do IBGE e cadastro de municípios TSE ↔ IBGE embutidos no pacote
  (`lumen_eleicoes/dados`, com proveniência), instalados por `preparar` e
  `amostra`. O mapa e a busca funcionam sem download prévio.
- Mapa interativo: botões + e −, Ctrl/⌘ + rolagem, pinça, arrasto, dois
  dedos na tela de toque e teclas +, − e 0; a rolagem simples continua
  rolando a página. Partes sem área no mapa atual viram botões abaixo dele.
- Seletor de eleições em dois grupos (por município; 1933 a 1990, só por
  estado); várias ressalvas da fonte numa faixa só; a busca por município,
  numa eleição só por UF, leva ao estado.
- `historico baixar|processar` aceitam de 1933 a 2024 e `--anos todos`; 404
  em conjunto opcional e ZIP opcional corrompido viram aviso.
- `verificar` cobra as UFs de cada cargo quando o índice as traz.
- No Windows, a gravação de um feed que o servidor local está enviando ao
  navegador espera e tenta de novo, em vez de falhar (`substituir_arquivo`).
- Amostra de desenvolvimento com 1945, 1950 e 1989; `amostra
  --sem-referencias` para regenerar a amostra versionada.
- Documentação: DOC-12 1.1, DOC-06 1.2, DOC-10 1.2, DOC-11 1.1, ADR-025.

## 0.3.0 — 2026-10-05

### Fase 0 concluída

- Limites de dispensa de 2021 a 2026 (art. 75, I e II, e § 7º da Lei 14.133),
  fator do § 2º para consórcios e agências executivas e acréscimos do art. 125
  (25% e 50%) conferidos no texto oficial e cadastrados como verificados.
  Prazos da LRF (art. 51, 52, 55 e 63) cadastrados com a mudança da LC
  178/2021 a partir de 2022. Teste de cobertura contínua da vigência (ADR-013,
  atualização).
- Migração do domínio (`0001_dominio.sql`) testada em PostgreSQL 16:
  tabelas de prova somente-anexação, máquina de estados do indício com
  revisores distintos, papel da aplicação sem UPDATE/DELETE na prova.
- Camada bronze em armazenamento de objetos: cliente S3 próprio com escrita
  condicional e Object Lock (ADR-018); ambiente local com PostgreSQL e MinIO
  (`infra/docker-compose.yml`).

### Fase 1 — núcleo

- Esquema canônico do bloco de fatos (ente, órgão, unidade gestora, amparo
  legal, processo, item, resultado, contrato, ata, entrega SICONFI), com
  identidade determinística e sensibilidade por campo (ADR-017).
- Adaptadores: PNCP (contratações por publicação e por atualização, contratos,
  atas, itens e resultados), IBGE (localidades e população), SICONFI (entes e
  extrato de entregas). Cliente HTTP com limite de taxa, retentativa e recuo.
- Normalização com regras de qualidade e quarentena; silver em JSON Lines
  particionado, idempotente e reconstruível do bronze (ADR-016).
- Conformidade: avaliação das entregas de DCA, RREO e RGF no prazo legal, com
  resultado indeterminado quando a dúvida é do Lumen; lista de ausentes.
- Comando `lumen` (coletar, normalizar, bronze, eleicoes) e testes de contrato
  diários contra as fontes reais.

### Aba Eleições (nova)

- Coletor ao vivo do sistema de divulgação de resultados do TSE: requisições
  condicionais, andamento por UF e município, fila municipal com orçamento por
  passada, prova na camada bronze, evolução da totalização (ADR-019).
- Eleições passadas desde 1994 pelos dados abertos do TSE: download retomável
  com manifesto (ADR-021), leitura por nome de coluna (layouts de 38, 44 e 50
  colunas), agregação de zonas em município, UF e Brasil, reconciliação dos
  totais de 1994.
- Feeds JSON com contrato versionado; panoramas por partido para cargos vistos
  acima do nível em que são disputados; malhas do IBGE; cadastro TSE ↔ IBGE.
- Portal Next.js estático: mapa (TopoJSON decodificado sem biblioteca), lista
  de candidatos, totais, evolução, busca (Ctrl+K), modo TV, atualização a cada
  15 s ao vivo. Cores por posição, nunca por partido, validadas para
  daltonismo (ADR-020).
- Simulação de apuração e amostra de desenvolvimento a partir de arquivos
  oficiais reais.

### Documentação

- DOC-11 Referência Técnica, gerada do código; todo módulo, classe, função e
  componente documentado, cobrado por teste (ADR-023).
- DOC-12 Eleições, com diagramas da arquitetura, da passada ao vivo e do
  processamento histórico, e o roteiro da noite da eleição.
- DOC-05 (seção 8: bloco de fatos implementado, identidade, quarentena, silver
  e banco de domínio), DOC-06 (comportamento real das fontes, TSE e IBGE,
  situação de cada integração), DOC-07 (revisões pendentes da B-01, do agente
  autorizador e da família K) e DOC-10 (situação de cada fase) na versão 1.1.
  ADRs 016 a 024.
- Proposta de revisão da regra B-01 frente ao art. 75, § 1º (ADR-022).
- Geração dos documentos: títulos presos ao parágrafo seguinte, quebra de
  página sem página em branco, linhas de tabela que não se dividem e capa com
  acentuação; `make docs` gera a referência antes dos `.docx`.

### Silver

- Macro do DuckDB `packages/normalizacao/sql/silver_consolidada.sql` (uma
  linha por id, a mais recente), conferida contra `silver.consolidar` por
  teste; o CI instala o DuckDB para rodá-lo.
- `lumen.toml.exemplo` com a seção `[eleicoes]` comentada.

## 0.2.0 — 2026-09-29

Fase 0: camada bronze imutável com hash, coleta HTTP identificada, porta
FonteDados, máquina de estados do indício, parâmetros legais datados,
verificador de vocabulário controlado, marco M1 verificado por teste.
