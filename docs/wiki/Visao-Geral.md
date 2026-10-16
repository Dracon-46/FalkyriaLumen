# Visão geral

Fonte principal: [DOC-01 Visão e Escopo](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/DOC-01_Visao_e_Escopo.docx).

## Objetivo

O Lumen coleta, normaliza e analisa dados de contratações e despesas públicas de todos os entes
federativos brasileiros para sinalizar atividades que merecem análise por órgãos de controle,
imprensa e sociedade civil. Ele identifica padrões estatísticos e processuais que se afastam do
esperado, apresenta a evidência primária de cada sinalização e mostra quem praticou o ato
administrativo e com que fundamento legal, conforme publicado pelo próprio ente.

O sistema não julga e não afirma conclusões sobre conduta. A determinação sobre a conduta de
pessoas e órgãos cabe exclusivamente aos órgãos de controle e ao Poder Judiciário. Essa restrição é
imposta no código, no modelo de domínio e no pipeline de publicação (DOC-08, DOC-09,
[ADR-007](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-007.md)).

O prazo alvo é de doze meses até a versão pública, em seis fases (ver [[Roadmap|Roadmap]]).

## A ideia central

O Brasil tem 5.570 municípios, 26 estados, o Distrito Federal e a União. Cobrir todos por raspagem
individual de portais é inviável para uma equipe pequena. Duas bases federais de envio obrigatório
já concentram dados de praticamente todos esses entes:

| Base | O que traz | Acesso |
|---|---|---|
| PNCP (Lei 14.133/2021) | Contratações, contratos, atas, planos e o amparo legal de cada contratação | API pública, sem autenticação |
| SICONFI (Tesouro Nacional) | RREO, RGF e DCA de estados e municípios | API aberta, sem cadastro |

Integrar essas duas fontes entrega alcance nacional cedo; a raspagem municipal deixa de ser o
caminho crítico ([ADR-001](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-001.md)).
Os entes ausentes dessas bases são entes que não cumpriram uma obrigação legal de envio, e essa
lista alimenta o módulo de conformidade.

## O problema

Publicar não é o mesmo que tornar fiscalizável. O DOC-01 aponta três barreiras:

- **Fragmentação.** Cada esfera e cada ente publica em formato, nomenclatura e periodicidade
  próprios. Sem normalização, comparar preços entre entes é impossível.
- **Escala.** Mais de 6.000 unidades publicam informação orçamentária. Nenhuma equipe audita esse
  volume à mão; a fiscalização hoje é reativa.
- **Assimetria de atenção.** A atenção pública vai para contratos de valor alto. Padrões de valores
  pequenos e repetidos, como o fracionamento de despesa, operam abaixo desse limiar. Por isso o
  motor de detecção trata valores pequenos como cidadãos de primeira classe (família B do DOC-07),
  e a materialidade é relativizada pelo porte do ente.

## Objetivos do produto

| Código | Objetivo | Como será medido |
|---|---|---|
| OBJ-01 | Cobrir os dados de contratação de todos os entes que publicam no PNCP | Percentual de entes com ao menos uma contratação coletada nos últimos 12 meses |
| OBJ-02 | Cobrir os dados orçamentários e fiscais de estados e municípios via SICONFI | Percentual de entes com RREO e DCA coletados por exercício |
| OBJ-03 | Normalizar tudo num esquema canônico único | Percentual de registros que passam nas regras de qualidade sem intervenção manual |
| OBJ-04 | Detectar padrões de valor atípico, altos e também pequenos e repetidos | Precisão dos indícios revisados por amostragem trimestral |
| OBJ-05 | Registrar quem autorizou cada ato e com que fundamento legal | Percentual de contratações com agente e amparo legal preenchidos |
| OBJ-06 | Medir e expor o cumprimento das obrigações de transparência | Número de entes com índice de conformidade calculado e publicado |
| OBJ-07 | Garantir rastreabilidade integral da evidência | Percentual de indícios com documento fonte armazenado e hash verificável |
| OBJ-08 | Garantir direito de resposta efetivo | Tempo médio entre contestação registrada e marcação pública do indício |

## Público

| Parte interessada | O que espera | Como o sistema atende |
|---|---|---|
| Cidadão | Entender como o dinheiro do seu município é gasto | Painel por ente em linguagem simples, com comparação entre municípios semelhantes |
| Jornalista de dados | Encontrar pautas e sustentar a apuração | Busca avançada, exportação e dossiê de evidências com documentos originais |
| Órgão de controle | Priorizar onde alocar capacidade de auditoria | API, fila de indícios por severidade e exportação estruturada |
| Pesquisador | Base histórica normalizada e reprodutível | Exportação em Parquet e CSV com dicionário de dados versionado |
| Ente público analisado | Corrigir informação incorreta a seu respeito | Canal de contestação com prazo definido e resposta publicada junto ao indício |
| Equipe do projeto | Operar com previsibilidade e sem risco jurídico | Vocabulário controlado, revisão humana obrigatória e trilha de auditoria |

## Escopo

### Dentro do escopo

A cobertura é construída em camadas, do mais estruturado para o menos estruturado:

| Camada | Alcance | Natureza da fonte | Fase |
|---|---|---|---|
| Federal obrigatória | Todos os entes que cumprem a lei | API estruturada (PNCP, SICONFI) | Fase 1 |
| Federal complementar | União e transferências a estados e municípios | API (CGU, Compras.gov, RFB, TSE) | Fase 1 |
| Estadual | 27 unidades federativas e seus tribunais de contas | API, CSV ou HTML | Fase 3 |
| Municipal por plataforma | Centenas de municípios por conector | Famílias de portal comerciais | Fase 4 |
| Municipal cauda longa | Municípios restantes | PDF, XLS, HTML avulso, pedido LAI | Fase 4 |

Objetos de análise: processos de contratação (licitações, dispensas, inexigibilidades, com
modalidade e amparo legal); contratos, aditivos, prorrogações e reajustes; itens com quantidade,
preço unitário e classificação de catálogo; a cadeia da despesa (empenho, liquidação e pagamento);
atas de registro de preço e planos anuais de contratação; convênios, transferências voluntárias e
emendas parlamentares; atos autorizativos e os agentes que os assinaram, no exercício da função;
fornecedores (quadro societário, CNAE, capital social, data de abertura); sanções administrativas
vigentes (CEIS, CNEP, CEPIM) e decisões de tribunais de contas; indicadores de cumprimento das
obrigações de transparência.

Além do plano original, o repositório tem duas áreas que não geram indício:

- **Aba Eleições**: resultados oficiais do TSE, ao vivo e de 1933 a 2026, como trilha paralela que
  não disputa o caminho crítico ([ADR-024](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-024.md)).
- **Painéis de Contratações e de Conformidade**: o que cada ente e cada órgão publicou no PNCP e as
  entregas da LRF ao Tesouro contra o prazo legal, sem indício e sem ordenação por risco
  ([ADR-028](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-028.md)).

### Fora do escopo da versão 1.0

- Folha de pagamento individualizada de servidores, exceto quando já publicada de forma agregada e
  usada para indicadores do próprio ente.
- Dados de beneficiários de programas sociais em nível individual.
- Obras físicas com verificação em campo, imagens de satélite ou medição de execução.
- Análise de conteúdo de processos judiciais.
- Previsão de risco futuro por aprendizado de máquina supervisionado.

### Não objetivos

- O Lumen não afirma nem sugere conclusões sobre conduta, por linguagem, iconografia ou rotulagem.
- O Lumen não substitui auditoria. Um indício é uma hipótese a ser verificada por quem pode
  requisitar documentos, ouvir agentes e aplicar sanção.
- O Lumen não produz ranking de políticos, não atribui pontuação a pessoas físicas e não constrói
  perfis de agentes públicos além do registro objetivo dos atos que assinaram.
- O Lumen não coleta dados pessoais de beneficiários de programas sociais para análise individual.
- O Lumen não contorna controles técnicos de acesso: não resolve CAPTCHA, não usa credencial de
  terceiro e não acessa área restrita de nenhum portal.
- O Lumen não é, na primeira versão, um sistema de previsão.

## Princípios inegociáveis

Têm precedência sobre qualquer requisito funcional. Em caso de conflito, a funcionalidade é
descartada ou redesenhada.

1. **P1. Evidência antes de afirmação.** Nenhum indício é publicado sem o documento primário
   armazenado, com URL de origem, hash SHA-256 e carimbo de tempo da coleta.
2. **P2. Linguagem neutra obrigatória.** Todo texto voltado ao público usa vocabulário controlado,
   verificado na integração contínua; termos que imputam conduta quebram o build.
3. **P3. Reprodutibilidade.** Qualquer indício pode ser reproduzido por terceiros a partir dos dados
   públicos e da especificação da regra; regra, versão, parâmetros e dados de entrada ficam
   registrados junto ao indício.
4. **P4. Simetria de correção.** Erratas e remoções têm o mesmo destaque e o mesmo canal da
   publicação original.
5. **P5. Ausência de dado é informação.** Quando um ente não publica o que a lei obriga, isso é
   registrado como achado de transparência, com a base legal, e não como falha de coleta.
6. **P6. Coleta responsável.** O sistema se identifica em todas as requisições, respeita limites de
   taxa, prefere a API oficial e nunca degrada a disponibilidade de um serviço público.

## Premissas e restrições

Os dados tratados são públicos por força da Lei 12.527/2011 (Lei de Acesso à Informação), da Lei
Complementar 131/2009 e do art. 174 da Lei 14.133/2021, e sua reutilização é amparada pelo Decreto
8.777/2016. A qualidade do dado de origem é variável; dado incompleto é situação normal de operação.
O projeto é conduzido por uma equipe muito pequena, o que torna automação e padronização mais
importantes que a sofisticação de cada componente.

| Tipo | Restrição | Implicação no desenho |
|---|---|---|
| Legal | Vedado imputar conduta a pessoa física ou jurídica | Vocabulário controlado aplicado por lint e testes |
| Legal | LGPD vale para dados pessoais mesmo em bases públicas | Classificação de dados e minimização na normalização |
| Técnica | Limites de taxa das APIs oficiais | Controle de vazão por fonte e coleta incremental |
| Técnica | Volume na casa de bilhões de linhas ao longo dos anos | Camada analítica colunar particionada |
| Operacional | Equipe reduzida | Conectores declarativos; revisão humana só no que é publicado |
| Financeira | Orçamento de infraestrutura limitado | Armazenamento em objetos e processamento sob demanda; na Fase 1, planos gratuitos ([ADR-026](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-026.md)) |

## Riscos principais

| Código | Risco | Mitigação |
|---|---|---|
| R-01 | Ação judicial por ente ou fornecedor citado | Vocabulário controlado, revisão humana, evidência armazenada e direito de resposta imediato |
| R-02 | Falso positivo publicado com repercussão | Limiar de publicação alto, revisão obrigatória acima de severidade média e errata com o mesmo destaque |
| R-03 | Fonte oficial muda de formato sem aviso | Testes de contrato por fonte, alarme de variação e camada bronze que permite reprocessar |
| R-04 | Bloqueio de IP por coleta agressiva | Vazão conservadora, identificação no User-Agent e preferência por API oficial |
| R-05 | Cauda longa municipal consumir o tempo do projeto | Cobertura nacional na Fase 1 via PNCP e SICONFI |
| R-06 | Custo de armazenamento acima do previsto | Compressão colunar, particionamento por ano e ciclo de vida no armazenamento de objetos |
| R-07 | Exposição indevida de dado pessoal | Classificação de dados, mascaramento de documentos e revisão de privacidade |
| R-08 | Percepção de perseguição política | Critérios idênticos para todos os entes, metodologia pública e nenhum recorte partidário |

Veja também: [[Requisitos|Requisitos]], [[Arquitetura|Arquitetura]], [[Glossário|Glossario]].
