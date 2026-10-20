# Fixtures de fontes reais

Amostras capturadas das APIs oficiais em **05/10/2026**, pelo navegador, e
versionadas aqui (DOC-09, seção 3.2). Elas cumprem dois papéis:

1. permitem testar coleta e normalização sem rede;
2. documentam o formato **real** de cada fonte, que diverge da documentação
   oficial em vários pontos (ver DOC-06 e ADR-017).

## Como foram reduzidas

Para caber no repositório, listas longas foram **cortadas**, nunca editadas:
os registros mantidos estão exatamente como a fonte os entregou, campo por
campo, inclusive erros de digitação e valores esquisitos. O que muda é só a
quantidade de itens em `data` ou `items`.

| Arquivo | Corte |
|---|---|
| `pncp/contratacoes_publicacao_dispensa_20260901_p1.json` | 4 dos 10 itens da página; metadados de paginação originais |
| `pncp/contratacoes_publicacao_pregao_20260901_p1.json` | 2 dos 10 itens |
| `pncp/contratos_20260901_p1.json` | 3 dos 10 itens |
| `pncp/atas_20260901_p1.json` | 2 dos 10 itens |
| `siconfi/entes_amostra.json` | 5 dos 5.598 entes; `count` ajustado para 5 |
| `siconfi/rreo_anexo02_amostra.json` | 4 linhas; `count` ajustado para 4 |
| `siconfi/rreo_anexo03_amostra.json` | 28 das 427 linhas do RREO Simplificado de 2025, 6º bimestre, Anexo 03, de São Sepé (capturado em 20/10/2026): as contas da RCL e das deduções, em todas as colunas; `count` ajustado para 28 |
| `siconfi/rreo_uniao_anexo02_2015.json`, `siconfi/rreo_uniao_anexo02_2025.json` | só as linhas da coluna da despesa liquidada do RREO da União do 6º bimestre, Anexo 2 (capturados em 20/10/2026), os dois blocos em 2025; `count` ajustado |
| `siconfi/rreo_uniao_anexo01_2015.json`, `siconfi/rreo_uniao_anexo01_2025.json` | só as linhas da coluna `Até o Bimestre (c)` (a receita realizada) do RREO da União do 6º bimestre, Anexo 1 (capturados em 20/10/2026), com os dois blocos (exceto e intraorçamentárias); `count` ajustado |
| `siconfi/dca_anexo_i_e_sao_sepe_2025.json` | DCA de 2025, Anexo I-E, de São Sepé (capturada em 20/10/2026), só as colunas "Despesas Empenhadas" e "Despesas Liquidadas" (152 das 319 linhas): funções, subfunções e totais; `count` ajustado. Sem os campos `demonstrativo` e `periodo`, como a API entrega a DCA |
| `siconfi/rgf_anexo01_sao_sepe_2025_s2.json` | RGF Simplificado do 2º semestre de 2025, Anexo 1, do Poder Executivo de São Sepé (capturado em 20/10/2026), sem as colunas mensais `<MR-1>` a `<MR-11>` (39 das 188 linhas): despesa com pessoal, RCL ajustada e limites; `count` ajustado. Sem o campo `demonstrativo` |
| `ibge/municipios_nivelado_amostra.json` | 2 dos 5.571 municípios |
| `ibge/noticias_releases_9256.json` | sem corte: a resposta inteira da API de notícias do IBGE pedida com `qtd=2` (releases do IPCA, capturada em 20/10/2026) |
| `ibge/sidra_6390_rendimento_2024_2025.json` | o cabeçalho e os 24 trimestres móveis de 2024 e 2025 dos 174 da tabela 6390, variável 5933 (capturada em 20/10/2026, com os valores a preços de jun-jul-ago 2026) |
| `ibge/sidra_6579_populacao_br.json` | sem corte: a estimativa da população do Brasil em todos os anos da tabela 6579, variável 9324 (capturada em 20/10/2026) |
| `cgu/ceis_amostra.zip` | 5 das 23.787 linhas do `20261015_CEIS.csv`, capturado em 16/10/2026, mais 1 linha fictícia de pessoa física (abaixo) |
| `cgu/cnep_amostra.zip` | 2 das 1.840 linhas do `20261015_CNEP.csv`, mais 1 linha fictícia de pessoa física |
| `cgu/cepim_amostra.zip` | 3 das 3.521 linhas do `20261014_CEPIM.csv` |
| `cgu/pagina_download_ceis.html` | só o bloco `<script>` da página de download do CEIS que declara a data do arquivo |
| `pntp/avaliacoes_pntp_2025_amostra.xlsx` | 8 das 11.697 linhas da planilha de avaliações do PNTP 2025 (capturada em 16/10/2026), regravadas numa planilha mínima com os valores como texto |
| `pntp/avaliacoes_pntp_2022_cabecalho.xlsx` | só o cabeçalho da planilha de 2022 (as linhas trazem nome e e-mail de quem preencheu) |
| `pntp/downloads_trecho.html` | só o bloco "Base de Dados" da página de downloads do Radar da Transparência |

Nos ZIPs da CGU, as linhas mantidas são os bytes originais do CSV (ISO-8859-1,
`;`, fim de linha CRLF), e o ZIP foi refeito com elas. **Exceção ao "nunca
editadas":** o CEIS e o CNEP publicam o CPF inteiro e o nome de pessoas
físicas sancionadas, e dado pessoal real não entra no repositório (DOC-08,
seção 5). A linha de pessoa física de cada amostra parte de uma linha real,
com CPF, nomes, número do processo e código da sanção trocados por valores
fictícios (CPF `123.456.789-09`, nome `PESSOA FISICA FICTICIA DE TESTE`,
códigos `900000001` e `900000002`) e as observações apagadas.

Os demais arquivos estão inteiros.

## Peculiaridades reais preservadas de propósito

Cada uma delas tem teste que garante o tratamento correto:

- **PNCP, ata com vigência no ano 7203** (`atas_20260901_p1.json`, Jundiaí).
  Erro de digitação na fonte. Vai para a quarentena por temporalidade.
- **PNCP, `valorTotalEstimado = 0` com homologado nulo** (FUNCATE). Aceito
  com marcação de qualidade, nunca usado como valor zero.
- **PNCP, `esferaId` e `poderId` iguais a `N`** (CAIXA, FUNCATE, município
  de São Sepé com poder `N`). Viram nulo, com marcação.
- **PNCP, órgão estadual com código IBGE da capital** (Estado do Ceará em
  Fortaleza). O ente é o estado, não o município.
- **PNCP, empresa individual com nome de pessoa como razão social**
  (Xique-Xique). É CNPJ, dado público; não é tratado como CPF.
- **PNCP, descrição do amparo legal com valor desatualizado** ("inferiores a
  R$ 50.000,00"). O limite vem de `parametros_legais`, nunca desse texto.
- **PNCP, página vazia responde 204 sem corpo**, não 200 com lista vazia.
- **PNCP, erro 422 com `status` em texto** (`"422"`), e erro 400 com número.
- **SICONFI, `capital` com espaços** (`"1  "`) e **estado com `uf = "BR"`**.
- **SICONFI, União com `cod_ibge = 1`** e população claramente inválida.
- **CGU, sanção "com prazo determinado" que termina em 31/12/2099 ou
  19/09/2099** (COESA, no CEIS). Mantida como publicada, com a marcação
  `data_fim_distante`, em vez de ir para a quarentena.
- **CGU, sancionado estrangeiro sem tipo de pessoa e com documento de 9
  dígitos** (Davati Medical Supply LLC). O documento não segue; o nome, sim.
- **CGU, "Sem Informação" e "SEM INFORMACAO"** em abrangência, meio de
  publicação e razão social. Viram nulo.
- **CGU, esfera do órgão sancionador vazia** (DCS, no CEIS). Nula, com
  marcação.
- **CGU, o CEPIM não tem datas nem código da sanção.** A chave é CNPJ mais
  convênio.
- **PNTP, "% das Essenciais" igual a 6,6 numa escala de 0 a 1** (Prefeitura
  de Piedade dos Gerais, 2025). O número vira nulo com
  `fracao_fora_da_faixa`; a entidade continua no cadastro.
- **PNTP, entidade "Não Avaliado"** (Prefeitura de Abaíra, 2025): índice 0 e
  traços na planilha. Fica no cadastro, sem índice.
- **PNTP, nível "Inexistente" com índice 0** (consórcio do Vale Europeu): é
  avaliação de verdade, e o zero fica.

## Como recapturar

As URLs estão nos testes de contrato de cada conector
(`testes/contrato/`). Ao recapturar, mantenha o corte descrito acima e
atualize a data no topo deste arquivo.
