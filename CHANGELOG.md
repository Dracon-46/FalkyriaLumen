# Histórico de versões

Formato: o que mudou para quem usa e para quem desenvolve, por versão. As
decisões que justificam cada mudança estão nas ADRs citadas.

## 0.6.0 — 2026-10-09

### Preço comparado com o mercado de fora do governo (regra A-05, ADR-027)

- Pacote novo, `lumen_mercado`, com a regra A-05 em **modo silencioso**: para
  cada item de compra pública reconhecido, a razão entre o preço homologado e a
  mediana de uma referência de mercado no mesmo lugar e na mesma época. Nada é
  publicado nem vira indício; o resultado é um relatório interno (`.jsonl`,
  `.csv` e `resumo.md`) para calibração.
- Combustível contra a série histórica de preços da ANP (posto a posto, por
  semana e município, desde 2006): `lumen mercado anp baixar|resumo`. Município
  sem amostra recua para a UF, marcado no relatório.
- O presente também: `lumen mercado anp semanas --de --ate` acha na página do
  levantamento as planilhas semanais (`revendas_lpc_*.xlsx`) e baixa as da
  janela; a planilha é lida sem dependências (`lumen_mercado/xlsx.py`). A mesma
  coleta lida no arquivo semanal e no semestral conta uma vez só, e arquivo
  ilegível fica registrado no resumo sem parar a carga.
- Gás de cozinha (GLP no botijão de 13 kg) contra o preço de revenda da ANP,
  com limiar próprio (1,25, não calibrado); `anp baixar --series ca,glp`.
  Vasilhame, botijão completo, outros tamanhos, granel e preço por quilo ficam
  de fora.
- Distribuição da razão para calibrar (`distribuicao.json` e tabela no
  resumo): quantis por categoria, tipo de preço e escopo da referência, e a
  fração dos itens acima de cada limiar candidato (1,10 a 2,00).
- Informática padronizada (notebook, monitor, impressora) contra ofertas do
  varejo pela API oficial do Mercado Livre, com coleta diária guardada no
  bronze e data e hora do acesso (art. 23, § 1º, III, da Lei 14.133):
  `lumen mercado varejo coletar|testar`. O formato e o acesso real ainda
  precisam ser conferidos pela primeira coleta e pelo teste de contrato.
- Reconhecimento conservador dos itens (`lumen mercado reconhecer`): unidade
  coerente, atributos que definem o preço, exclusão de acessórios, serviços,
  lubrificante, álcool 70%, cartão de abastecimento e gestão de frota.
- Leitura da ANP mais estrita: UF pela sigla ou pelo nome do estado, unidade de
  medida conferida com o produto (GLP por 45 kg não entra como P13), milésimo de
  real arredondado em vez de truncado.
- Itens do PNCP sob demanda: `lumen coletar pncp_itens --objeto` busca os itens
  e resultados só dos processos da silver cujo objeto interessa, e a
  normalização acha o processo pela URL do item.
- Lojas sem API pública (Magazine Luiza, KaBuM, Pichau, comparadores de preço)
  ficam de fora por decisão.
- Fluxo `mercado-referencia.yml` (manual) roda a regra com dados reais, com a
  série semestral, as planilhas semanais ou as duas, e guarda o relatório como
  artefato privado; testes de contrato da busca do varejo, das séries ca e glp
  e da página semanal da ANP.
- Fluxos do GitHub Actions em `ubuntu-24.04` e nas versões das ações que rodam
  em Node 24 (checkout v5, setup-python v6, setup-node v5, upload-artifact v6);
  cobertura do `lumen_mercado` no CI; token opcional do varejo no teste de
  contrato.
- Documentação: ADR-027, DOC-07 1.2 (A-05), DOC-06 1.3 (seção 2.8), DOC-10 1.4,
  DOC-11 1.3, README.

### Correções

- A coleta HTTP desfaz a compressão de transporte (`Content-Encoding` gzip ou
  deflate) antes de guardar no bronze. A API do IBGE responde comprimida mesmo
  sem pedir, e o teste de contrato diário falhou por isso; sem a correção, a
  carga de municípios e das malhas guardaria bytes comprimidos. O limite de
  tamanho vale para o documento descomprimido, e a codificação recebida fica
  em `X-Lumen-Codificacao-Recebida`.
- Primeira execução de `mercado-referencia.yml` com dados reais: o arquivo
  semestral de combustíveis e as planilhas semanais foram lidos sem nenhuma linha
  descartada. Ajustes a partir dela: a série de GLP é sempre `.csv`, com dois
  semestres de nome próprio; o CNPJ da planilha semanal recupera os zeros à
  esquerda (para a mesma coleta contar uma vez só); a planilha de teste segue o
  leiaute real. A busca do Mercado Livre responde 403 sem credencial, e o teste
  de contrato do varejo fica pulado até o segredo `LUMEN_ML_TOKEN` existir.
- O teste de contrato da série da ANP lê a página da série em vez de pedir o
  arquivo com `HEAD`, que o gov.br recusa com 403.
- Resposta 429 (excesso de requisições) passa a ser tratada como pedido para ir
  mais devagar: a vazão da fonte cai pela metade pelo resto da sessão, a espera
  antes de repetir é de pelo menos 30 s, e o 429 só conta para o recuo quando a
  última tentativa também o recebe. A segunda execução do `mercado-referencia`
  mostrou que o PNCP respondia 429 na oitava página seguida a 60 requisições
  por minuto, e cinco 429 seguidos suspendiam a fonte.
- Teste de contrato do TSE: o arquivo do 2º turno de 2026 já está publicado,
  com votos zerados e sem a destinação do voto (`dvt`), que só aparece depois
  que a totalização começa; o teste passou a exigir o campo só nesse caso.
- `eleicoes-carga` agendado, sem os segredos do bucket, só avisa em vez de
  falhar todo dia; disparado à mão, continua falhando com o motivo.
- `lumen coletar pncp_itens --so-comparaveis` busca os resultados só dos itens
  que a regra A-05 reconhece; cada resultado é uma requisição por item, e o
  PNCP limita a vazão. O fluxo `mercado-referencia` usa a opção e tem prazo de
  4 horas.
- O cliente S3 aceita endpoint com caminho (o S3 do Supabase Storage fica em
  `/storage/v1/s3`), mantendo o prefixo antes do bucket.
- `lumen coletar` interrompida por fonte suspensa diz que parou, em JSON, e sai
  com 1, sem rastro de exceção; com `-v`, o log de cada tentativa traz o status,
  a URL e o número da tentativa. O fluxo `mercado-referencia` coleta o PNCP com
  `-v`, porque a primeira execução parou com o PNCP em recuo depois de cinco
  respostas de erro.
- Portal: endereço dos feeds vazio (variável `LUMEN_URL_FEEDS` não definida no
  repositório) volta a valer `/dados/eleicoes`, em vez de gerar um site com os
  feeds na raiz. O fluxo `portal-pages` testa o portal sem a variável, gera com
  ela, e, sem o token do Cloudflare ou o nome do projeto, avisa que não publicou
  em vez de falhar.

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

### Correções no mesmo dia

- Migração 0002: caminho de busca vazio nas três funções de gatilho do
  domínio (`recusar_alteracao`, `validar_mudanca_de_estado`,
  `congelar_indicio`), apontado pelo linter de segurança do Supabase. O teste
  de banco aplica todas as migrações em ordem e confere o caminho fixo.
- `test_preparar_parado_pelo_usuario` deixou de consultar o endereço real do
  TSE (na CI, a coleta ao vivo começava antes da parada e o teste falhava).

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
