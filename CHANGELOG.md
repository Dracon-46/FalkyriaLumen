# Histórico de versões

Formato: o que mudou para quem usa e para quem desenvolve, por versão. As
decisões que justificam cada mudança estão nas ADRs citadas.

## Não lançado

### Economia: taxa de desocupação (ADR-033, adendo)

- Indicador novo no grupo "Trabalho" e nos destaques: a taxa de desocupação
  da PNAD Contínua, por trimestre móvel, desde março de 2012.
  - Fonte: SGS 24369, que republica a tabela 6381 do SIDRA.
  - Espelho: Ipeadata, conferido valor a valor nos 174 meses.
  - Junto vêm os releases mensais do IBGE.

### RREO normalizado e grupos de pares com a receita corrente líquida (ADR-038, adendo)

- Normalização do RREO, do RGF e da DCA do SICONFI. Cada linha vira
  `LinhaDemonstrativo`: ente, exercício, período, demonstrativo, anexo,
  coluna, conta e valor, como o Tesouro publica.
- `lumen painel rcl`: a receita corrente líquida (RCL) do exercício anterior
  de cada ente, pelo Anexo 03 do RREO do 6º bimestre. O tipo de RREO
  (completo ou simplificado) vem do extrato de entregas, e assim sai uma
  consulta por ente. Roda no fluxo diário da conformidade, só para quem
  falta.
- Grupos de pares, versão 2 (`porte-regiao-rcl-1`): todo grupo com 30 entes
  com RCL publicada se divide na mediana da RCL por habitante. O cartão do
  ente mostra a RCL por habitante dele e como a RCL entrou no grupo, e a
  lista do grupo ganha a coluna.

### Economia: releases oficiais do IBGE ao lado dos indicadores (ADR-033, adendo)

- O IPCA, o INPC e o PIB real (e os derivados de uma série só, como o IPCA em
  12 meses) mostram os três releases mais recentes da Agência de Notícias do
  IBGE, com o título, a data e o link. Vêm da API pública de notícias do IBGE,
  na coleta diária da Economia. Falha nela não derruba a coleta das séries.
- Notícias de jornal ficam de fora, nas Contratações e na Economia. O adendo
  explica: vinculação errada por nome parecido, imputação vedada pelo DOC-08 e
  termos de uso.
- Teste de contrato novo da API de notícias do IBGE. O do SGS passa a pular,
  com o motivo, quando o Banco Central responde 5xx ou uma página no lugar do
  JSON: é acesso, não mudança de formato.

### Situação das coletas: o painel operacional (ADR-039)

- Página nova "Situação das coletas" (`/operacao/`, link no rodapé), refeita a
  cada publicação dos painéis. Mostra:
  - os alertas no topo;
  - as execuções dos fluxos de dados em 30 dias: a última, a última com
    sucesso, as falhas e o atraso dos diários;
  - o volume diário do PNCP;
  - a coleta da conformidade por UF.
- Alarme de volume: dia útil com menos da metade da mediana do mesmo dia da
  semana nas 8 semanas anteriores. Fins de semana, feriados, pontos
  facultativos e pontes nacionais ficam de fora. Simulado nos 289 dias de
  2026: nenhum alerta falso em 172 dias úteis.
- `operacao.json` no site dos painéis. O `paineis-site` grava as execuções
  com `gh run list` (permissão `actions: read`).
- Na primeira montagem com os dados reais, o painel mostrou três problemas:
  - os testes de contrato das fontes falhando (Banco Central, IBGE, TSE e ANP
    em dias diferentes);
  - a última carga por período com falha;
  - o dia 10/04/2026 do PNCP sem coleta.

### Grupos de pares (ADR-038)

- Cálculo inicial dos grupos de pares, entregável da Fase 1
  (`lumen_canonico.pares`):
  - municípios por porte (classes de tamanho do IBGE) e grande região, lida
    do código IBGE;
  - grupo regional com menos de 15 municípios recua para o porte no país, com
    o motivo nos critérios;
  - estados e DF num grupo só, e a União sem grupo.

  A receita corrente líquida entra numa próxima versão, com a normalização do
  RREO. Com o cadastro de outubro de 2026, são 33 grupos: 31 regionais, o
  nacional dos municípios acima de 500 mil habitantes e o dos estados e DF.
- Conformidade: a página do ente ganha o cartão "Grupo de pares", com:
  - a fração entregue no prazo ao lado da mediana e dos quartis do grupo;
  - a descrição e os critérios;
  - a ressalva quando o grupo é pequeno;
  - a lista dos entes do grupo, por nome.

  Novos arquivos `conformidade/pares/<id>.json` e bloco `pares` em
  `conformidade/ente/<código>.json`. É contexto, não avaliação: a tela não
  ordena nem classifica pela posição.

### Eleições: 2º turno ao vivo sem disparo à mão (adendo do ADR-026)

- `eleicoes-ao-vivo` agendado no dia da eleição (25/10/2026). Os agendamentos
  do GitHub chegam horas atrasados, então o fluxo agenda execuções desde as 3h
  de Brasília e espera até `AGENDA_INICIO` (16h45). Espera maior que 5h30
  termina disparando o próprio fluxo, que continua esperando.
- `lumen eleicoes ao-vivo --limite-minutos`: para ao fim da passada depois do
  prazo e sai com o código 3 se a apuração não terminou. No fluxo, 330
  minutos; com o código 3, ele dispara a continuação (até três), que segue do
  estado no bucket privado. Antes, a máquina era derrubada no prazo de 6
  horas.
- Testes: o arquivo de configuração dos testes da linha de comando grava o
  caminho com barras, e esses testes passam a rodar também no Windows.

### Eleições: carga de um ano à mão e roteiro do 2º turno

- `eleicoes-carga`: a entrada `anos` da execução manual passa a valer mesmo
  com `ELEICOES_SEM_HISTORICO=true`. Antes, sem marcar também `historico`, o
  disparo rodava sem os dados abertos e não carregava o ano pedido.
- Roteiro da noite da eleição (DOC-12 e Wiki): disparar o `eleicoes-ao-vivo`
  com a fila do grupo `eleicoes-carga` vazia, porque o grupo guarda uma só
  execução na espera e cancela a que esperava quando outra entra. Em
  16/10/2026, a carga de 2026 disparada junto com o ensaio foi cancelada assim.
  O roteiro também passa a dizer quando o coletor para sem a marca de
  finalizada do TSE (60 minutos estável com todas as seções totalizadas).
- Wiki e README: com `ELEICOES_SEM_HISTORICO=true`, a carga diária não lê os
  dados abertos de 2026; passar os dois turnos para eles pede um disparo com
  `anos` = 2026 e espaço no bucket (perto de 45 MB a mais, pelas medições de
  13 e 14/10/2026, com o bucket em 844,8 MB e o teto em 900 MB).

### Preço de mercado no modal: ANP (ADR-037)

- Os itens de combustível (gasolina comum e aditivada, etanol, diesel S10 e
  S500, GNV) e de gás de cozinha (botijão de 13 kg) ganham o botão "comparar
  com o preço de bomba (ANP)". O preço homologado (ou o estimado) é comparado
  com a distribuição do preço de revenda que a ANP pesquisa posto a posto, na
  semana da compra, no município (com 5 coletas ou mais) ou na UF. A leitura
  segue os limiares da regra A-05: 1,20× a mediana no combustível e 1,25× no
  gás, iniciais e não calibrados.
- `lumen painel anp`: as planilhas semanais da ANP no fluxo diário dos
  painéis, só as que faltam (desde 2025, até 40 por execução). Publicadas em
  `mercado/anp/uf-<sigla>-<ano>.json`, com o município pelo código IBGE.
- O portal reconhece o item com as mesmas regras do Python. Os casos ficam num
  arquivo só, lido pelos testes dos dois lados.
- Lojas online: Mercado Livre, Amazon, Shopee e AliExpress só entram pela API
  oficial, com credencial (o adaptador do Mercado Livre está pronto). Lojas
  sem API (Magazine Luiza, Havan, KaBuM) ficam de fora: extrair o site fere os
  termos de uso e o princípio 6.

### Comparação de preço do item com outros órgãos (ADR-036)

- No modal da contratação, cada item com código do catálogo do Compras.gov.br
  (CATMAT ou CATSER) tem o botão "comparar o preço com outros órgãos". O
  preço homologado (ou o estimado) é comparado com o que outros órgãos
  pagaram pelo mesmo código nos 12 meses anteriores, pela pesquisa de preços
  do Compras.gov.br. A tela mostra:
  - a mediana, os quartis, o escore robusto e a faixa, com o ponto do item;
  - as compras comparáveis;
  - as que ficaram fora da conta, e por quê (outra unidade, total lançado
    como unitário, a própria compra).
- Pela regra A-01 do DOC-07 (30 compras ou mais, escore 3,5, parâmetros
  iniciais), o item recebe a leitura "preço acima da referência comparada",
  com a ressalva de que não é conclusão. Com menos compras, os números são só
  contexto.
- O portal pede os preços pelo próprio endereço (`/api/precos/...`), que o
  Vercel repassa à fonte (`rewrites` no `vercel.json`): a API não aceita
  pedido de outro site.

### Visão 360 pelo filtro de local, modal da contratação e tudo diário (ADR-035)

- **Filtro de local** no cabeçalho, em todas as páginas: escolhido um estado,
  o DF ou um município (ou ao entrar num deles em qualquer aba), cada aba
  abre já nele. Eleições abre no mapa, Contratações e Conformidade no ente e
  as Estatais nas que ele controla. O ✕ volta para o Brasil, e o local fica
  guardado no navegador.
- **Modal da contratação**: clicar no objeto de um processo ou contrato abre
  tudo o que o PNCP publica dele: modalidade, fundamento legal, valores,
  datas, itens com o preço unitário e o vencedor, termos aditivos, documentos
  e o processo de origem do contrato. A página atrás passa a mostrar o órgão.
  Clicar num fornecedor filtra a página por ele.
- **Conformidade**: a página do ente mostra os portais de transparência
  avaliados pelo PNTP (nível, índice e link de cada entidade).
- **Documentos para baixar**: cada processo e contrato do PNCP tem o botão
  "documentos", que lista os arquivos publicados (edital, termo de
  referência, contrato, aditivos) com o link de download do próprio PNCP.
- `lumen painel transparencia`: o ciclo mais recente do PNTP no fluxo diário
  (só a planilha de dentro do ZIP, e só quando muda), publicado por UF.
- **Zonas eleitorais**: o mapa das zonas não era publicado, porque a carga
  sem o histórico também tirava os locais de votação. Agora roda em toda
  carga (perto de 2 MB por ano).
- **Economia**: quando o firewall do Banco Central recusa a coleta (aconteceu
  em 18/10/2026), a série é pedida de novo e, se continuar recusada, vem da
  cópia conferida no Ipeadata (IPCA, INPC, Selic no mês, NFSP e PIB real). O
  estado é gravado mesmo com falha.
- **Conformidade todo dia**, e não só às segundas.
- Tabelas sem rolagem interna: as linhas são paginadas de 20 em 20.

### Empresas estatais (ADR-034)

- Página nova **Empresas estatais**, dentro de Economia: quanto gastam e
  investem as estatais, que não publicam no PNCP (Lei 13.303/2016). Na aba
  das federais, o Programa de Dispêndios Globais da SEST, com aprovado e
  realizado por rubrica (pessoal, serviços de terceiros, materiais,
  tributos, investimentos) de 2016 a 2025: os Correios, por exemplo,
  realizaram R$ 26,7 bilhões em 2025, R$ 15,2 bilhões com pessoal. Na aba das
  companhias com ações na bolsa, as demonstrações entregues à CVM (receita,
  pessoal, impostos, compras de terceiros, investimento em ativos, lucro),
  com o controle conferido no Formulário de Referência e o link do documento.
- O controle não vem do campo do cadastro da CVM, que continua dizendo
  "estatal" depois de privatizações (Sabesp, Copel, Eletrobras): vem dos
  controladores declarados no FRE. Pessoas físicas do FRE e do cadastro não
  são lidas.
- `lumen economia estatais` coleta CVM e SEST todo dia no fluxo `paineis`.
  Nenhum total soma empresas: a controladora já inclui as controladas.

### Paginação, filtro de período e escolhas com busca no portal

- Toda lista ou tabela com mais de 20 itens mostra 20 por página:
  fornecedores, órgãos, municípios, valores a conferir, publicações
  recentes, UFs, entes da conformidade, obrigações, candidatos, partidos,
  zonas e a tabela das séries econômicas.
- Contratações ganha o filtro de período (do mês tal ao mês tal, com os
  atalhos "último mês", "últimos 3 meses" e por ano), na URL: totais,
  gráficos, modalidades, órgãos, fornecedores, municípios, esferas e UFs são
  refeitos com os meses escolhidos. Os arquivos dos painéis trazem o mês a
  mês de cada tabela; os fornecedores listados passam de 20 para 100 por
  ente (200 no Brasil, 50 por órgão).
- As caixas de seleção (eleição, indicador, mandato, mês) viram caixas de
  escolha com busca: dá para abrir a lista e escolher ou escrever parte do
  nome ou do ano. A busca de estado ou município das eleições aceita a
  digitação direto no campo.

### Economia e Contas Públicas (ADR-033)

- Aba nova **Economia** no portal: inflação (IPCA, INPC), juros (Selic, juro
  real), dívida (bruta do governo geral, líquida do setor público), resultado
  fiscal (primário, nominal, juros) e atividade (PIB, IBC-Br). Cada número
  traz a fonte, o código da série, o período de referência, a data da coleta,
  a definição, como ler o sinal e as limitações.
- Comparação de dois períodos (mandatos presidenciais ou qualquer intervalo
  de meses) para todos os indicadores, com a consulta na URL e o aviso de que
  a comparação não atribui causa.
- `lumen economia coletar` e `publicar`: séries do SGS do Banco Central,
  coletadas todo dia pelo fluxo `paineis` e publicadas com os painéis. O IPCA
  acumulado calculado confere com o do IBGE.
- Busca de órgãos do painel de Contratações com o exemplo "Correios" (a
  Petrobras não publica no PNCP: as estatais seguem a Lei 13.303/2016).
- Abas do cabeçalho roláveis no celular.

### Sanções cruzadas com os contratos: regra J-01 em modo silencioso (ADR-031)

- `lumen deteccao j01` cruza os contratos guardados pelo painel com o CEIS e o
  CNEP: mesmo CNPJ, sanção que impede contratar, vigente na assinatura e com
  alcance sobre o contratante pela abrangência publicada (todas as esferas;
  mesma esfera, UF e município; mesmo órgão). Em 16/10/2026: 6.364
  coincidências para análise, de 661 fornecedores, em 1,64 milhão de
  contratos.
- O fluxo `deteccao-sancoes` roda sozinho depois de cada carga do painel. Nada
  é publicado: o resumo da execução só tem contagens, e o relatório completo
  vai para o bucket privado.

### Portais de transparência de todos os entes: PNTP (ADR-032)

- `lumen coletar pntp_avaliacoes` traz as avaliações do Programa Nacional de
  Transparência Pública (tribunais de contas e Atricon): 11.697 entidades em
  2025, com o índice, o nível e o endereço do portal. Lê só a planilha de
  avaliações de dentro do ZIP de 338 MB, por `Range` (`zip_remoto`).
- Entidade nova `avaliacao_transparencia` na silver, ciclos de 2023 em diante.

### Coleta ao vivo para quando a totalização se estabiliza

- O ensaio com o 1º turno de 2026 mostrou que os deputados de Rondônia ficaram
  com 100% das seções totalizadas sem a marca de finalizada do TSE, e o
  coletor rodaria até o prazo da máquina. Agora ele para depois de 60 minutos
  sem mudança com todas as seções totalizadas (`--parar-estavel`) e diz quais
  resultados ficaram sem a marca.

### Sanções da CGU: CEIS, CNEP e CEPIM (ADR-030)

- `lumen coletar cgu_ceis` (e `cgu_cnep`, `cgu_cepim`) baixa para o bronze o
  retrato mais recente de cada cadastro de sanções do Portal da Transparência,
  pelos arquivos de dados abertos: sem chave de API e sem `--de`, com a data
  lida na página de download.
- `lumen normalizar` grava a entidade nova `sancao` na silver: um registro por
  sanção, com a `data_referencia` do retrato, a categoria, as datas, a
  abrangência, o órgão sancionador e a fundamentação legal, como publicados.
  O CPF de pessoa física (o CEIS publica 9.170 inteiros) sai mascarado, e o
  `fornecedor_id` é o mesmo do PNCP, pronto para a regra J-01 da Fase 2.
- Os 29.148 registros dos arquivos de 14 e 15/10/2026 passaram sem nenhuma
  quarentena; "Sem Informação" vira nulo, e o fim de sanção em 31/12/2099
  fica como publicado, com a marcação `data_fim_distante`.
- Teste de contrato diário das colunas dos três cadastros; DOC-05 1.2,
  DOC-06 1.4 e DOC-10 1.5.

### Documentação e organização do repositório

- Wiki do projeto em `docs/wiki/` (visão geral, requisitos, arquitetura,
  tecnologias, componentes, instalação, configuração e variáveis, APIs e
  contratos, banco de dados, testes, deploy e operação, roadmap, glossário),
  publicada na Wiki do GitHub pelo fluxo `wiki.yml` a cada mudança na `main`.
- `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, modelo de PR,
  formulários de issue (erro, melhoria, dado divergente da fonte), `CODEOWNERS`
  e Dependabot mensal (GitHub Actions, portal, docs-src e Python).
- Rótulos e marcos versionados em `.github/organizacao.json` (fluxo
  `organizacao.yml`); release do GitHub a cada tag `vX.Y.Z`, com as notas
  desta página e as versões conferidas (`release.yml`).
- O verificador de vocabulário passa a conferir a Wiki, os textos da raiz e os
  modelos de issue e de PR.
- README: guia das páginas da Wiki; hospedagem em uso (Supabase Storage e
  Vercel); portal com as três abas.

## 0.8.0 — 2026-10-15

### Zonas eleitorais no mapa do município (ADR-029)

- Escolher um município no mapa abre o município: o mapa da UF voa até ele,
  apaga os vizinhos (que continuam clicáveis: abrir outro voa até ele) e, nos
  190 municípios com mais de uma zona eleitoral, mostra as zonas com a cor de
  quem lidera em cada uma, os locais de votação como pontos e o número de cada
  zona. Dica por zona (quem lidera, percentual, vantagem, eleitores, locais) e
  por local de votação (nome, zona, eleitores).
- O contorno das zonas é aproximado e a tela diz isso: a Justiça Eleitoral não
  publica os limites das zonas; cada zona é a área mais perto dos seus locais
  de votação (dados abertos do TSE, do mesmo ano da eleição, de 2018 em
  diante), recortada pelo contorno do município.
- Tabela "Por zona eleitoral", ligada ao mapa: o cursor numa linha destaca a
  zona, o clique fixa o destaque. Ao vivo, o TSE não publica por zona: a tabela
  mostra o eleitorado e os locais, e o mapa, as zonas sem cor de resultado.
- Feeds de município (dados abertos, 1994 em diante): as zonas em `partes`
  quando o município tem mais de uma, com as cores do próprio feed e sem
  `bancada` nos cargos proporcionais. Contrato na versão 1.
- `lumen eleicoes zonas` e etapa nova do `preparar`: locais de votação de 2018
  a 2026 em `geo/zonas-<ano>/` (índice e um arquivo por município). O
  `preparar` refaz uma vez os anos de 1994 a 2024 processados pela versão
  anterior (`VERSAO_PROCESSAMENTO`), para os feeds ganharem as zonas; a
  publicação só envia o que mudou. `--sem-zonas` pula a etapa.
- Contornos dos 191 municípios com mais de uma zona na qualidade `maxima` do
  IBGE, embutidos em `lumen_eleicoes/dados/geo/mu/` (1,5 MB) e instalados em
  `geo/mu/`; `geo.baixar_contornos` os baixa de novo.
- `lumen eleicoes verificar` confere os arquivos das zonas e não trata mais as
  malhas de `geo/` como feeds.
- `lumen eleicoes mapas --contornos` baixa o contorno fino de cada município
  dos índices das zonas; o resumo de `zonas` lista os que ficaram sem ele.
- O mapa das zonas é gravado de novo quando o cálculo muda (`REVISAO_ZONAS`) ou
  os contornos embutidos mudam; o arquivo de um município que deixou de ter
  mais de uma zona é apagado. A zona não traz `eleito` nem `segundo_turno`
  (quem se elege é decidido no município, na UF ou no Brasil).
- O arquivo das zonas tem versão própria (`VERSAO_ZONAS`, a mesma no Python e no
  portal, conferida por teste), independente da dos feeds.

### 2026 nos dados abertos, com o 2º turno ao vivo

- O 1º turno de 2026 passa a vir dos dados abertos do TSE (publicados em
  15/10/2026), com o resultado por zona. 2026 é o ano em aberto
  (`ANO_EM_ABERTO`): o `preparar` confere a fonte a cada execução e reprocessa
  quando o TSE acrescentar o 2º turno.
- A coleta ao vivo decide por eleição: o 1º turno, já processado, sai dela; o
  2º turno de 25/10/2026 continua ao vivo, no `preparar` e no `ao-vivo`.
- Os feeds dos dados abertos ficam com as fotos que a coleta ao vivo da mesma
  eleição já publicou (`carga.fotos_da_coleta`).

### Navegação mais fluida na aba Eleições

- A tela anterior fica, esmaecida, enquanto o feed novo chega (no lugar de
  "Carregando…"); na primeira leitura, um esqueleto no formato da tela.
- O feed da UF de um município é pedido junto com o dele (a UF sai do código
  IBGE na URL), e o mapa não some durante a troca.
- Feeds de eleições encerradas guardados em memória durante a visita, e o
  cursor parado numa área do mapa pré-carrega o que o clique vai abrir.
- Aproximação animada (botões, tecla 0, "Ver tudo", "Município") e voo até o
  município; sem animação para quem pede menos movimento ao sistema.
- Mapa mais leve: camada das áreas memorizada, um ouvinte só para o cursor (no
  máximo uma atualização da dica por quadro), apagamento dos vizinhos numa
  opacidade só, do grupo. Num navegador sem GPU, o voo até a capital paulista
  passou de 4 quadros travados para 32 quadros de 16 ms.
- Esc no município solta a zona escolhida e, de novo, volta para a UF.
- Cache dos feeds descarta o usado há mais tempo (e não o mais antigo), e uma
  falha atrasada não apaga a leitura que a substituiu.
- Acessibilidade (auditoria axe-core, WCAG 2 AA): o cinza do texto secundário
  passa a ter contraste de 4,5:1 ou mais em todos os fundos claros, e a página
  das eleições tem de novo o seu título de nível 1 para leitores de tela (fora
  do modo TV ele ficava escondido de todos). Nenhuma violação nas páginas do
  Brasil, da UF e do município, nos temas claro e escuro.
- Documentação: ADR-029.

## 0.7.1 — 2026-10-15

### Busca de órgãos no painel de Contratações (ADR-028)

- A busca de Contratações acha também os órgãos que publicaram no PNCP, e não
  só a União, os estados e os municípios: prefeituras, câmaras, autarquias,
  fundações e empresas públicas. Casa pelo nome, pela sigla formada pelas
  iniciais ("SAAE Sorocaba" acha o Serviço Autônomo de Água e Esgoto de
  Sorocaba), pelo município do órgão ou pelo começo do CNPJ, e leva à página
  do órgão.
- `lumen painel publicar` grava `orgaos.json` (CNPJ, razão social, ente,
  esfera, processos e contratos de cada órgão com publicação no período); o
  portal só baixa o arquivo quando a busca de Contratações é aberta.
- Teto de plausibilidade dos valores: processo ou contrato com valor acima
  de R$ 10 bilhões, ou de R$ 20 mil por habitante do ente, conta nas
  quantidades, mas fica fora das somas e da lista de fornecedores e aparece
  em "Valores a conferir na fonte", com o link do PNCP. Na primeira semana
  coletada, um contrato publicado com R$ 239,8 bilhões fazia sozinho perto de
  90% do valor de contratos do país.
- Documentação: ADR-028 (decisão 8), DOC-13 1.1, DOC-11 regerado.

## 0.7.0 — 2026-10-14

### Painéis de Contratações e de Conformidade (ADR-028, DOC-13)

- As abas Contratações e Conformidade do portal deixam de ser "em breve". Mostram
  fatos publicados, sem indício e sem ordenação por risco (PUB-07), com o aviso
  metodológico em cada página (PUB-08).
- Pacote novo, `lumen_painel` (`lumen painel …`):
  - `contratacoes`: coleta um dia do PNCP por vez (as 19 modalidades e os
    contratos, pela data de publicação), com bronze e silver temporários, e
    guarda só o resumo compacto do dia; um dia com falha não é gravado e volta
    na execução seguinte;
  - `conformidade`: o extrato de entregas do SICONFI de cada ente da UF, no
    exercício anterior e no corrente, com a situação da coleta de cada um;
  - `cadastro`: nomes, UF, esfera e população dos entes, do SICONFI;
  - `publicar`: soma os dias por ente, por órgão, por esfera e por UF, avalia
    as obrigações da LRF na data do dia e grava o site inteiro;
  - `faltando`: divide os dias que faltam em blocos para máquinas paralelas.
- Contratações por ente (União, estado, DF, município) e por órgão: o número
  de um município é o dos órgãos municipais, inclusive autarquias, fundações e
  empresas públicas (como um serviço autônomo de água e esgoto), cada um com
  página própria. Contratos com pessoa física ou estrangeira só entram numa
  soma anônima: nome e documento não ficam nem no estado guardado.
- Conformidade: contas anuais, RREO por bimestre e RGF por período e por
  Poder, contra os prazos de `parametros_legais`; coleta que falhou, prazo não
  vencido e instituição não identificada dão indeterminado. Entregas
  comparadas ao prazo no horário de Brasília.
- Estado nos anexos da versão `painel-estado` do repositório (sem custo, fora
  do 1 GB do Supabase); site no GitHub Pages
  (`https://dracon-46.github.io/FalkyriaLumen/`). Fluxos `paineis.yml`
  (diário; conformidade às segundas), `paineis-carga.yml` (meses anteriores) e
  `paineis-site.yml`.
- Portal: busca de União, estado ou município; páginas do Brasil, do ente e
  do órgão; gráficos por mês com tabela; selos de resultado com ícone e texto;
  obrigações empilhadas no celular.
- `eleicoes-carga`: entrada `historico` na execução manual, que inclui 1933 a
  2024 mesmo com `ELEICOES_SEM_HISTORICO=true`. A primeira carga com o
  histórico (14/10/2026) publicou 342 mil arquivos em 3h17, a perto de 50 por
  segundo: as 56 eleições de 1933 a 2026 somam 844 MB no Supabase.
- Publicação das eleições: o manifesto e o estado também tentam de novo uma
  falha passageira, e os 520 a 524 do Cloudflare (na frente do Supabase) contam
  como passageiros; um 520 ao gravar o estado tinha marcado a carga como falha.
- Documentação: ADR-028, DOC-13 1.0, DOC-11 e DOC-12 regerados, README.

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
  e da página semanal da ANP. A entrada `janelas` junta várias janelas curtas
  numa execução: a distribuição sai do conjunto, com amostras maiores para
  calibrar.
- Fluxos do GitHub Actions em `ubuntu-24.04` e nas versões das ações que rodam
  em Node 24 (checkout v5, setup-python v6, setup-node v5, upload-artifact v6);
  cobertura do `lumen_mercado` no CI; token opcional do varejo no teste de
  contrato.
- Documentação: ADR-027, DOC-07 1.2 (A-05), DOC-06 1.3 (seção 2.8), DOC-10 1.4,
  DOC-11 1.3, README.

### Eleições sem cartão: Supabase Storage no lugar do R2 (adendo do ADR-026)

- A publicação das eleições funciona também com o Supabase Storage, que fala o
  protocolo S3 e não pede meio de pagamento. Com os JSON comprimidos, 1933 a
  2026 cabem no 1 GB gratuito (perto de 850 MB). Os nomes dos segredos e das
  variáveis no GitHub não mudam.
- Variável `R2_REGIAO` nos fluxos `eleicoes-carga` e `eleicoes-ao-vivo` (região
  da assinatura S3; o R2 usa `auto`). A configuração recusa endpoint do
  Supabase sem a região do projeto, que o Supabase exige na assinatura.
- Variável `ELEICOES_SEM_HISTORICO`: com `true`, a carga diária não baixa os
  dados abertos de 1933 a 2024.
- `lumen eleicoes medir`: tamanho dos feeds gravados (total, por grupo, com
  gzip, maiores arquivos), se cabem no R2 e no Supabase gratuitos e o pior caso
  de saída por visitante e hora de apuração, que no Supabase gratuito tem cota
  de 5 GB por mês.
- Fluxo `eleicoes-medir.yml` (manual): gera os feeds de 2026 numa máquina do
  GitHub, sem publicar, e mede. Primeira medição: o 1º turno de 2026 completo
  tem 17.653 arquivos e 112,9 MB (35,4 MB com gzip); no pior caso, um
  visitante consome cerca de 1 MB por hora na visão Brasil e 9 MB na de um
  estado grande. A medição passou a estimar também a visão do estado mais
  pesado, que chega a dez vezes a nacional.
- O Supabase responde 400 (com `not_found` ou `NoSuchKey` no corpo), e não 404,
  a arquivo inexistente em parte das rotas: o cliente S3 e o portal tratam essa
  resposta como "não existe". Sem isso, a primeira carga, com o bucket vazio,
  não começaria, e o portal mostraria erro em vez de "ainda não publicado".
- Os JSON sobem comprimidos com gzip (`Content-Encoding: gzip`) e ocupam um
  terço no bucket. O diagnóstico `nuvem-diagnostico.yml` confirmou que o
  Supabase entrega o arquivo comprimido a quem aceita gzip e descomprimido a
  quem não aceita. O manifesto marca o que subiu comprimido: a primeira
  publicação depois da mudança reenvia, comprimido, o que tinha subido sem.
  `lumen eleicoes medir` compara o tamanho comprimido com o limite do plano.
- Repositório público desde 14/10/2026: os minutos do GitHub Actions deixam de
  contar, e o histórico das eleições e a coleta de contratações cabem nos
  fluxos. `eleicoes-medir` mede anos dos dados abertos sem 2026, em execuções
  paralelas.
- A publicação envia 16 arquivos ao mesmo tempo (o índice continua por último,
  depois de todos). Na primeira carga real no Supabase, um a um, subia pouco
  mais de um arquivo por segundo: cada passada do coletor, com mil feeds, levava
  mais de dez minutos, lento demais para a noite da apuração. Uma falha no meio
  guarda no manifesto o que subiu e segura o índice.
- Portal na Vercel (plano Hobby, gratuito) como alternativa ao Cloudflare Pages,
  sem token no GitHub: `packages/portal/vercel.json` gera de novo só quando o
  portal muda.
- Medição por anos (14/10/2026): o histórico de 1933 a 2024 soma perto de 362
  mil arquivos e 812 MB com gzip (3,9 GB sem). Com 2026, perto de 850 MB: a
  carga passa a incluir o histórico também no Supabase.
- Manifesto da publicação dividido por grupo (`publicacao/<grupo>.json`,
  comprimido, com a assinatura e o tamanho de cada arquivo) e lido só quando a
  carga tem arquivo do grupo para enviar; um manifesto único do histórico
  passaria de 50 MB, o limite por arquivo do Supabase. A assinatura encurta
  para 24 dígitos do SHA-256 e o manifesto antigo deixa de ser lido: 2026 sobe
  de novo uma vez, comprimido.
- Teto do bucket público (`LUMEN_PUBLICACAO_LIMITE_MB`, 900 MB por padrão no
  Supabase): a publicação para antes de passar dele, sem enviar o índice.
- A publicação tem 50 minutos de folga depois de `--limite-minutos` e então
  para entre dois lotes, sem gravar o estado, em vez de ser derrubada pelo
  prazo da máquina; falha passageira de envio (408, 429, 5xx, rede) é tentada
  de novo; envios simultâneos configuráveis (`LUMEN_PUBLICACAO_PARALELOS`, 32
  no GitHub Actions).
- O coletor ao vivo não para mais quando uma publicação falha: a passada
  seguinte publica de novo.
- Documentação: adendo do ADR-026 (com as medições e a recomendação para 25/10),
  DOC-12 1.4 (seções 9.5 e 9.7), DOC-11, README.

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
- Amostras para calibrar a A-05 (série semestral 2026-1, preço homologado com
  referência na UF), com a entrada `janelas` juntando sete janelas de janeiro a
  junho: combustível com 324 itens, mediana 0,989 e 3,1% a partir de 1,20; gás
  de cozinha com 86 itens, mediana 1,053 e cauda longa (4,7% a partir de 2,00),
  em que os maiores casos sugerem outro produto (cilindro de 45 kg, botijão
  com vasilhame). Observação, não calibração: os limiares continuam os
  iniciais (ADR-027, DOC-07 1.3).
- Segunda comparação (compras de junho contra a série semestral): 33
  homologados de combustível com referência na UF, mediana 1,03. Razão acima de
  10,00 também vira "fora de escala": é o valor total da compra lançado como
  preço unitário (quantidade 1).
- Primeira comparação de ponta a ponta com dados reais (compras de 22 e 23/9
  contra a planilha semanal da ANP): 473 itens, 130 comparáveis, 104 com
  referência. A partir dela: preço zero (orçamento sigiloso) conta como sem
  preço; razão abaixo de 0,50 vira "fora de escala" (preço simbólico ou erro de
  unidade) e sai da distribuição; razão a partir de 3,00 ganha a marca para
  conferir unidade; o resumo ganha a tabela dos estimados acima do limiar, à
  parte dos homologados. Janela padrão do fluxo: dois dias.
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
