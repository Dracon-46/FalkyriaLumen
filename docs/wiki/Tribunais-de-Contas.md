# Tribunais de contas

O que cada tribunal de contas publica sobre os municípios em dado aberto. Levantado em 21/10/2026, com as APIs e os
downloads testados de fato. A ordem de integração está na
[ADR-050](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-050.md). Já integrados, no fluxo diário: TCE-RS,
TCE-PR, TCE-PE e TCE-CE. Os servidores do TCE-RS e do TCE-CE só respondem a endereços do Brasil, e o fluxo chega a
eles por um intermediário em São Paulo (`infra/proxy-br`, na Vercel). Desde 28/10/2026, o TCE-RS recusa o endereço
do intermediário (403 do próprio servidor), e o RS é coletado à mão de uma máquina no Brasil até haver outro caminho.

## Resumo

- **Lote aberto, sem chave, com licitações ou contratos:** TCE-SP, TCE-RS, TCE-PR, TCE-PE, TCE-CE, TCE-RJ e
  TCE-ES.
- **Lote aberto, mas incompleto ou com obstáculo:** TCE-PB, TCE-MA, TCE-TO, TCE-AM e TCM-PA.
- **Atrás de captcha, token ou só em tela:** TCE-MG, TCM-BA, TCE-SC, TCM-GO e TCE-MT, perto de 1.850 municípios.
  Pedem pedido formal ou pela Lei de Acesso à Informação.
- **Nada aberto sobre os municípios:** os demais.

## Por tribunal

| Tribunal | Municípios | O que publica | Acesso | Desde | Observação |
|---|---|---|---|---|---|
| TCE-SP | 644 (menos a capital) | Audesp: licitações com itens, participantes (CNPJ) e propostas; ajustes (contratos e notas de empenho ligados à licitação); despesas e receitas | ZIP com CSV, sem cadastro (`transparencia.tce.sp.gov.br/sites/default/files/conjunto-dados/licitacoes-contratos/`); API de despesas (`/api/json/despesas/{mun}/{ano}/{mes}`) | Licitações e ajustes desde 2018; despesas desde 2008 | Arquivos de até 820 MB por mês, nomes de arquivo sem padrão, atualização esporádica |
| TCE-RS | 497 | LicitaCon: licitação, lote, item, licitante, proposta; contratos com aditivos e itens. SIAPC: empenhos, liquidações e pagamentos | CSV zipado por ano, sem chave (`dados.tce.rs.gov.br/dados/licitacon/contrato/ano/AAAA.csv.zip`); CKAN | Completo desde 2016; empenhos desde 2004 | **Integrado** (ADR-050). Só aceita IP do Brasil; aceita `Range`; cada ZIP repete a tabela de pessoas |
| TCE-PR | 399 | SIM-AM em XML: licitação (participantes e vencedores), contrato (aditivos, rescisão), despesa (empenho, liquidação, nota fiscal, pagamento), obra, convênio, receita e os vínculos entre eles | Zip do estado por ano (`pit.tce.pr.gov.br/Arquivos/{AAAA}_PIT_TodosArquivos.zip`, 1,3 a 1,9 GB) ou por município | 2013 | **Integrado** (contratos, ADR-050). Uso livre; geração semanal |
| TCE-PE | 184 | Contratos e aditivos (com PDF), convênios, licitações com licitantes, empenhos e pagamentos, receitas, fornecedores e sanções, obras, servidores | API sem chave (`sistemas.tce.pe.gov.br/DadosAbertos/{Metodo}!json`, até 100 mil registros); bases completas em RAR | Execução desde 2011; contratos desde 2013 | **Integrado** (contratos e aditivos, ADR-050). Atualização diária; "podem ser livremente utilizados" |
| TCE-CE | 184 | SIM inteiro: licitações, licitantes, itens, contratos e aditivos, empenhos, liquidações, pagamentos, notas fiscais, receitas, obras, folha | API REST (`api-dados-abertos.tce.ce.gov.br/sim/<método>`), GET sem credencial | Licitações desde cerca de 2003 | **Integrado** (contratos, aditivos e contratados, ADR-050). Só aceita IP do Brasil; até 1.000 registros por página; o contrato traz o id do PNCP; o CPF do contratado vem cifrado |
| TCE-RJ | 91 (menos a capital) | Licitações, licitantes, contratos (CNPJ, empenhado, liquidado e pago), compras diretas, empenhos, receitas, pessoal, obras paralisadas | API sem chave (`dados.tcerj.tc.br/api/v1/`), JSON ou CSV, paginada | 2020 | Licença ODbL |
| TCE-ES | 78 | Contratações (com nº PNCP), contratos com CNPJ, aditivos, itens, atas, obras, empenhos, despesas, receitas, pessoal | CSV no CKAN do estado (`dados.es.gov.br`, organização TCE-ES) | Contratações desde 2022 | Licença CC-BY; não cobre 2021 |
| TCE-MA | 217 | SACOP (até 2021): licitações, contratos, alterações. SINC (2022 em diante): contratações, licitantes, contratos, empenhos, pagamentos, receitas, folha | API (`tce-api.apps.tcema.tc.br`); o SACOP só por uma API interna do mural | SACOP de cerca de 2014 a 2021; SINC desde 2022 | Datas sujas (ex.: ano 9202) |
| TCE-PB | 223 | Licitações com proponentes e vencedor, despesas (empenhos com nº da licitação), receitas, folha | ZIP com CSV por ano, sem cadastro (`download.tce.pb.gov.br/dados-abertos/dados-consolidados/`) | Licitações desde 2015; despesas desde 2003 | Sem contratos nem aditivos |
| TCE-TO | 139 | SICAP-LCO: licitações, dispensas, atas, licitantes, contratação, obras; SICAP-Contábil: empenhos | CSV de licitações paginado (`app.tceto.tc.br/lo_publico/`); contábil em JSON | Licitações desde 2011 | Contratos só no detalhe de cada procedimento |
| TCE-AM | 62 | Licitações, contratos e aditivos, empenhos, receitas | Tela com exportação CSV por ente (`econtas.tce.am.gov.br`) | 2016 | O CSV não traz CNPJ; coleta exige automação da tela |
| TCM-PA | 144 | Mural de licitações (modalidade, objeto, valores) | Exportação CSV/JSON do grid (`tcmpa.tc.br/portalsc/LISTAGEM_GRID/`) | 2015 | Sem contratos nem CNPJ do vencedor; contábil com CAPTCHA |
| TCE-PI | 224 | Despesas e receitas agregadas, credores, servidores; licitações só no mural | API sem chave (`sistemas.tce.pi.gov.br/api/portaldacidadania/`) | Agregados desde 2010 | Sem histórico de licitações em lote |
| TCE-MG | 853 | SICOM: licitação, dispensa, contratos, empenho, despesas, receitas | `dadosabertos.tce.mg.gov.br`, com token depois de captcha | 2014 (segundo o tribunal) | Pede acordo com o tribunal |
| TCM-BA | 417 | Licitações, despesas, receitas, obras, pessoal | Só em tela, com reCAPTCHA; a API tem só cadastros e multas | Licitações desde 2000 | Pede acordo ou LAI |
| TCE-SC | 295 | e-Sfinge: licitações, contratos, despesas, receitas, pessoal, obras | Só painéis Qlik; API só cadastral | — | Pede acordo ou LAI |
| TCM-GO | 246 | Colare: licitações, contratos, empenhos, receitas, folha | API REST (`ws.tcm.go.gov.br/api/rest/`) com token, sem instrução pública de como obtê-lo | Provavelmente 2018 | Pede o token ao tribunal |
| TCE-MT | 142 | Radar: licitações, contratos, obras, despesa, receita, pessoal | Só painéis Qlik | Janela móvel de 6 anos | 2021 sai da janela em 2027 |
| TCE-MS | 79 | Só dados do próprio tribunal | API sem chave (`sip-barramento.tce.ms.gov.br`) | Coleta municipal só desde 2025 | Não serve para 2021–2023 |
| TCE-RN | 167 | Segundo terceiros: licitações, contratos, empenhos | API em `apidadosabertos.tce.rn.gov.br` | Não confirmado | Fora do ar (503) em 21/10/2026 |
| TCE-SE | 75 | Só editais de licitação | Tela com exportação de um relatório por vez | — | — |
| TCE-RR | 15 | SAGRES-Licitações: licitações e contratos | Só tela | — | A consulta automatizada deu erro |
| TCE-AC | 22 | LICON: licitações, contratos, dispensas | Só tela | — | Não há API |
| TCE-AL, TCE-AP, TCE-RO | 102, 16 e 52 | Nada aberto de licitações ou contratos municipais | — | — | O TCE-RO pede login |
| TCM-SP | 1 (a capital) | Empenhos do município (credor com CPF/CNPJ) | CSV estático (`iris.tcm.sp.gov.br/assets/data/empenho/EmpenhoAAAA.csv`) | 2005 | Sem licitações nem contratos |
| TCM-RJ | 1 (a capital) | Nada aberto sobre a prefeitura | — | — | — |
| TCE-BA, TCE-GO, TCE-PA, TCDF | 0 | Os municípios ficam com o TCM do estado (o DF não tem municípios) | — | — | — |

## TCE-SP: o que falta decidir antes de integrar

Examinado em 21/10/2026 com o semestre 2022-1 (`ajustes-2022-1o-semestre_0.zip`, 19 MB comprimido, um CSV de 225 MB
em UTF-8 separado por `;`):
- **Linhas:** 464 mil. São 418 mil notas de empenho e 47 mil linhas de contrato, de 22 mil contratos distintos (um
  contrato chega a 694 linhas, uma por item). Os outros tribunais integrados contam contratos; as compras só por nota
  de empenho precisam de decisão à parte.
- **Esfera:** o CSV não diz se a entidade é estadual ou municipal. Os órgãos do estado aparecem com o município onde
  ficam: "São Paulo" para secretarias, USP, Sabesp e Metrô (a Prefeitura da capital é do TCM-SP), e também em outras
  cidades, como hospitais estaduais. É preciso uma lista de entidades por esfera, da API do tribunal ou pelo CNPJ.
- **Ano:** os arquivos são por semestre de registro (anuais até 2020) e trazem contratos de anos anteriores (2021 no
  semestre 2022-1). Os repetidos entre arquivos saem pelo código do ajuste.
- **Valores:** há erros de digitação grandes (R$ 89,9 bilhões num contrato de Franca); o teto de plausibilidade os
  tira da soma, como nos outros.

## O que eles têm além do PNCP

- **2021 a 2023 completos**, quando o PNCP ainda era parcial, e séries mais antigas: CE desde 2003, PR desde 2013,
  RS desde 2016, SP desde 2018.
- **Licitantes e propostas que não venceram:** SP, RS, PB, PE, TO, MA.
- **Aditivos:** RS, PR, PE, CE, ES, MA, AM.
- **Ligação com empenho, pagamento e nota fiscal:** PR, CE, SP, PB, TO.
- **Obras e medições:** CE, PR, PE, ES, TO.
- **Chave para cruzar com o PNCP:** CE (`numero_id_contrato_pncp`), ES (nº PNCP) e RJ (indicação da Lei 14.133).
