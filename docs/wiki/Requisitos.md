# Requisitos

Fontes: [DOC-02 Requisitos](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/DOC-02_Requisitos.docx)
e [DOC-03 Casos de Uso](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/DOC-03_Casos_de_Uso.docx).
Esta página resume os textos; a redação normativa é a dos documentos.

Cada requisito tem um código único e permanente. Códigos não são reaproveitados: um requisito
removido tem o código aposentado. O prefixo indica o módulo, o que permite rastrear o requisito até
o caso de uso (DOC-03), o componente (DOC-04) e o teste (DOC-09).

Prioridade em MoSCoW: **M** obrigatório na versão 1.0, **S** importante, **C** desejável,
**W** adiado.

| Prefixo | Módulo | Responsabilidade |
|---|---|---|
| RF-CO | Coleta | Obter dados brutos das fontes e preservá-los como prova |
| RF-NO | Normalização | Converter qualquer fonte para o esquema canônico |
| RF-EN | Enriquecimento | Agregar contexto: societário, catálogo, grupo de pares |
| RF-DE | Detecção | Executar regras e produzir indícios com evidência |
| RF-CF | Conformidade | Medir o cumprimento das obrigações de transparência |
| RF-PU | Publicação | Expor dados e indícios ao público com linguagem controlada |
| RF-DR | Direito de resposta | Receber, tratar e publicar contestações |
| RF-AD | Administração | Operar o sistema: fontes, regras, revisão, auditoria |
| RNF | Não funcional | Qualidades transversais |

## Requisitos funcionais

### Coleta (RF-CO)

| Código | Requisito | Prio. |
|---|---|---|
| RF-CO-01 | Coletar contratações, contratos, atas e planos de contratação do PNCP por data de publicação e por data de atualização global, com coleta incremental | M |
| RF-CO-02 | Coletar RREO, RGF e DCA do SICONFI para todos os entes e exercícios disponíveis | M |
| RF-CO-03 | Coletar despesas, convênios, emendas parlamentares e cadastros de sanção do Portal da Transparência da CGU | M |
| RF-CO-04 | Ingerir a base pública de CNPJ da Receita Federal, com quadro societário, CNAE e capital social | M |
| RF-CO-05 | Armazenar o artefato bruto exatamente como recebido | M |
| RF-CO-06 | Gravar todo artefato com URL de origem, SHA-256, carimbo de tempo e cabeçalhos de resposta | M |
| RF-CO-07 | Artefatos brutos imutáveis: nova coleta da mesma URL gera nova versão, nunca sobrescrita | M |
| RF-CO-08 | Respeitar limites de taxa configuráveis por fonte, com padrão conservador | M |
| RF-CO-09 | Identificar-se em todas as requisições com User-Agent próprio, com nome do projeto e contato | M |
| RF-CO-10 | Suportar conectores declarativos, definidos em especificação, sem código novo | M |
| RF-CO-11 | Extrair dados estruturados de PDF, inclusive por OCR | S |
| RF-CO-12 | Extrair dados de XLSX, XLS, CSV e tabelas HTML | M |
| RF-CO-13 | Permitir upload manual supervisionado de documentos obtidos por pedido de acesso à informação | S |
| RF-CO-14 | Registrar falha de coleta com causa classificada, distinguindo indisponibilidade temporária de ausência de publicação | M |
| RF-CO-15 | Retentar coletas falhas com espera exponencial e limite de tentativas por janela | M |
| RF-CO-16 | Não tentar contornar CAPTCHA, autenticação ou qualquer controle técnico de acesso | M |
| RF-CO-17 | Detectar mudança de esquema na fonte e alarmar sem interromper as demais fontes | S |
| RF-CO-18 | Coletar dados de doações e candidaturas do repositório de dados abertos do TSE | C |

### Normalização (RF-NO)

| Código | Requisito | Prio. |
|---|---|---|
| RF-NO-01 | Converter todo dado coletado para o esquema canônico do DOC-05 | M |
| RF-NO-02 | Manter em cada registro normalizado a referência ao artefato bruto de origem | M |
| RF-NO-03 | Resolver a identidade de fornecedores por CNPJ raiz e filial, tratando grafias divergentes | M |
| RF-NO-04 | Resolver a identidade de entes por código IBGE e CNPJ | M |
| RF-NO-05 | Deduplicar registros presentes em mais de uma fonte, preservando a proveniência de cada ocorrência | M |
| RF-NO-06 | Normalizar valores monetários, datas e unidades de medida | M |
| RF-NO-07 | Classificar itens segundo catálogo de referência, para comparação entre entes | M |
| RF-NO-08 | Isolar em quarentena, com o motivo, registros que não passem nas regras de qualidade, sem bloquear o lote | M |
| RF-NO-09 | Aplicar classificação de sensibilidade a cada campo (DOC-08) | M |
| RF-NO-10 | Mascarar documentos de pessoa física antes de gravar em camada consultável | M |
| RF-NO-11 | Normalização idempotente: o mesmo artefato produz exatamente o mesmo resultado | M |
| RF-NO-12 | Reprocessar todo o histórico a partir da camada bruta, sem recoletar | M |

### Enriquecimento (RF-EN)

| Código | Requisito | Prio. |
|---|---|---|
| RF-EN-01 | Vincular cada fornecedor ao quadro societário, CNAE principal, capital social e data de abertura | M |
| RF-EN-02 | Calcular para cada ente um grupo de pares por porte populacional, região e receita corrente líquida | M |
| RF-EN-03 | Manter séries históricas por ente, fornecedor e item como linha de base | M |
| RF-EN-04 | Calcular medianas de preço unitário por item, região e período | M |
| RF-EN-05 | Identificar sócios em comum entre fornecedores distintos | S |
| RF-EN-06 | Vincular fornecedores a sanções vigentes no CEIS, CNEP e CEPIM | M |
| RF-EN-07 | Registrar o agente público signatário de cada ato autorizativo, quando publicado pela fonte | M |
| RF-EN-08 | Registrar o amparo legal invocado em cada contratação, quando publicado pela fonte | M |

### Detecção (RF-DE)

| Código | Requisito | Prio. |
|---|---|---|
| RF-DE-01 | Executar o catálogo de regras do DOC-07 sobre a base normalizada | M |
| RF-DE-02 | Versionar cada regra e registrar em cada indício a versão que o produziu | M |
| RF-DE-03 | Registrar em cada indício os parâmetros usados e os valores de entrada | M |
| RF-DE-04 | Referenciar em cada indício ao menos um documento fonte com hash verificável | M |
| RF-DE-05 | Detectar valores atípicos para cima, comparando o preço unitário com a mediana do mesmo item | M |
| RF-DE-06 | Detectar fracionamento de despesa por agregação de contratações de mesmo objeto e fornecedor em janela temporal | M |
| RF-DE-07 | Detectar concentração de valores imediatamente abaixo do limite legal de dispensa | M |
| RF-DE-08 | Detectar concentração de contratos num único fornecedor por ente e categoria | M |
| RF-DE-09 | Detectar contratação de fornecedor com sanção vigente na data do ato | M |
| RF-DE-10 | Detectar fornecedor constituído pouco tempo antes da contratação | S |
| RF-DE-11 | Detectar incompatibilidade entre o CNAE do fornecedor e o objeto contratado | S |
| RF-DE-12 | Aplicar teste de aderência à Lei de Benford por ente e período | S |
| RF-DE-13 | Detectar diferença relevante de gasto per capita em relação ao grupo de pares | M |
| RF-DE-14 | Detectar concentração atípica de empenhos no encerramento do exercício | S |
| RF-DE-15 | Detectar aditivos que elevem o valor do contrato acima dos percentuais previstos em lei | M |
| RF-DE-16 | Calcular score composto e severidade para cada indício | M |
| RF-DE-17 | Indícios acima do limiar de severidade entram obrigatoriamente em fila de revisão humana antes de qualquer publicação | M |
| RF-DE-18 | Simular uma regra sobre dados históricos sem publicar, para calibração | M |
| RF-DE-19 | Registrar indícios descartados com o motivo, para realimentar a calibração | M |
| RF-DE-20 | Não produzir, em nenhum campo, texto que afirme ou sugira conduta contrária à lei | M |

### Conformidade de transparência (RF-CF)

| Código | Requisito | Prio. |
|---|---|---|
| RF-CF-01 | Verificar, por ente, a existência de publicação nas fontes federais obrigatórias | M |
| RF-CF-02 | Verificar a atualidade da publicação frente à periodicidade exigida em lei | M |
| RF-CF-03 | Classificar o formato de publicação quanto à legibilidade por máquina | M |
| RF-CF-04 | Verificar a presença dos campos mínimos exigidos pela Lei de Acesso à Informação | S |
| RF-CF-05 | Calcular índice de conformidade por ente, com metodologia pública e auditável | M |
| RF-CF-06 | Ausência de dado obrigatório gera indício de descumprimento, com citação do dispositivo legal | M |
| RF-CF-07 | Distinguir indisponibilidade técnica temporária de ausência persistente de publicação | M |
| RF-CF-08 | Manter histórico do índice | S |

### Publicação (RF-PU)

| Código | Requisito | Prio. |
|---|---|---|
| RF-PU-01 | Painel por ente com panorama de contratações, despesas e conformidade | M |
| RF-PU-02 | Busca por ente, fornecedor, objeto, valor, período e modalidade | M |
| RF-PU-03 | Página de indício com a regra aplicada, os parâmetros e o link para o documento fonte | M |
| RF-PU-04 | Rótulo padronizado de atividade para análise em todo indício | M |
| RF-PU-05 | Comparação entre o ente e seu grupo de pares | M |
| RF-PU-06 | Exportação em CSV e Parquet dos dados normalizados consultados | M |
| RF-PU-07 | Dossiê em PDF com o indício, a evidência e os documentos fonte | S |
| RF-PU-08 | API pública documentada, com versionamento e limite de taxa | M |
| RF-PU-09 | Acompanhar um ente e receber alerta de novos indícios | C |
| RF-PU-10 | Aviso metodológico e link para a metodologia completa em toda página pública | M |
| RF-PU-11 | Erratas e remoções com o mesmo destaque da publicação original | M |
| RF-PU-12 | Data da última coleta bem-sucedida em cada visão de dados | M |

### Direito de resposta (RF-DR)

| Código | Requisito | Prio. |
|---|---|---|
| RF-DR-01 | Canal público para ente ou fornecedor registrar contestação a um indício | M |
| RF-DR-02 | Anexar documentos comprobatórios à contestação | M |
| RF-DR-03 | Marcar publicamente o indício contestado em até 24 horas do registro | M |
| RF-DR-04 | Exibir a contestação junto ao indício original, de forma permanente | M |
| RF-DR-05 | Reexecutar a regra considerando os documentos apresentados | M |
| RF-DR-06 | Comprovado erro do sistema, retificar ou remover o indício e publicar a correção | M |
| RF-DR-07 | Registrar prazo e desfecho de cada contestação, com métricas públicas de atendimento | S |

### Administração (RF-AD)

| Código | Requisito | Prio. |
|---|---|---|
| RF-AD-01 | Cadastrar e editar fontes por especificação declarativa | M |
| RF-AD-02 | Ajustar parâmetros de uma regra e versioná-la automaticamente | M |
| RF-AD-03 | Fila de revisão priorizada por severidade e antiguidade | M |
| RF-AD-04 | Registrar toda ação de revisor em trilha de auditoria imutável, com autor, data e justificativa | M |
| RF-AD-05 | Painel operacional com saúde das coletas, atrasos e taxa de falha por fonte | M |
| RF-AD-06 | Reprocessar um período ou uma fonte sob demanda | M |
| RF-AD-07 | Acesso administrativo com autenticação de segundo fator | M |
| RF-AD-08 | Perfis distintos de revisor e administrador | S |

## Requisitos não funcionais

### Desempenho e escala

| Código | Requisito | Meta |
|---|---|---|
| RNF-01 | Tempo de resposta da busca pública no percentil 95 | Até 2 segundos |
| RNF-02 | Tempo de resposta da API pública no percentil 95 | Até 800 ms |
| RNF-03 | Volume na camada analítica sem redesenho | 10 bilhões de linhas |
| RNF-04 | Janela do ciclo completo de detecção | Até 12 horas |
| RNF-05 | Defasagem entre publicação na fonte e disponibilidade no Lumen | Até 72 horas para fontes com API |
| RNF-06 | Reprocessamento integral do histórico | Até 7 dias corridos |

### Confiabilidade e operação

| Código | Requisito | Meta |
|---|---|---|
| RNF-07 | Disponibilidade do portal público e da API | 99,0% mensal |
| RNF-08 | Perda de artefato bruto já coletado | Zero, com replicação |
| RNF-09 | Falha numa fonte não interrompe as demais | Isolamento por fonte |
| RNF-10 | Recuperação da camada analítica a partir da camada bruta | Sempre possível |
| RNF-11 | Tempo para detectar falha sistemática de coleta | Até 6 horas |

### Segurança

| Código | Requisito |
|---|---|
| RNF-12 | Acesso administrativo com segundo fator e sessão com expiração |
| RNF-13 | Credenciais de API de terceiros em cofre de segredos, nunca no repositório |
| RNF-14 | Todo tráfego externo com TLS 1.2 ou superior |
| RNF-15 | Trilha de auditoria somente-anexação, sem alteração ou exclusão pela aplicação |
| RNF-16 | Backups cifrados em repouso e testados por restauração periódica |
| RNF-17 | Registrar e limitar tentativas de acesso administrativo malsucedidas |

### Privacidade e conformidade legal

| Código | Requisito |
|---|---|
| RNF-18 | Classificação de sensibilidade em todo campo do esquema canônico |
| RNF-19 | Dados pessoais de cidadãos que não são agentes públicos nunca expostos em nível individual |
| RNF-20 | Documentos de pessoa física mascarados em qualquer exibição ou exportação |
| RNF-21 | Procedimento documentado de atendimento a solicitação de titular de dados |
| RNF-22 | Base legal do tratamento documentada e vinculada a cada categoria de dado |

### Auditabilidade e reprodutibilidade

| Código | Requisito |
|---|---|
| RNF-23 | Indício publicado reproduzível por terceiro a partir dos dados públicos e da especificação da regra |
| RNF-24 | Metodologia de cada regra publicada em linguagem acessível no portal |
| RNF-25 | Linhagem registrada em toda transformação, do indício ao artefato bruto |
| RNF-26 | Versão da regra e versão do esquema registradas explicitamente em cada execução |

### Manutenibilidade e custo

| Código | Requisito |
|---|---|
| RNF-27 | Adicionar fonte de padrão já suportado sem alterar o núcleo |
| RNF-28 | Cobertura de testes no núcleo de domínio e no motor de regras: mínimo de 80% |
| RNF-29 | Custo mensal de infraestrutura na Fase 1 compatível com equipe reduzida |
| RNF-30 | Execução integral em ambiente local para desenvolvimento e teste |
| RNF-31 | Nenhum componente proprietário sem alternativa aberta equivalente como dependência crítica |

## Rastreabilidade

| Objetivo | Requisitos principais | Casos de uso |
|---|---|---|
| OBJ-01 | RF-CO-01, RF-CO-05 a RF-CO-09, RF-NO-01 | UC-12 |
| OBJ-02 | RF-CO-02, RF-NO-01, RF-NO-04 | UC-12 |
| OBJ-03 | RF-NO-01 a RF-NO-12 | UC-12 |
| OBJ-04 | RF-DE-05 a RF-DE-16 | UC-03, UC-13 |
| OBJ-05 | RF-EN-07, RF-EN-08, RF-CO-01 | UC-01, UC-03 |
| OBJ-06 | RF-CF-01 a RF-CF-08 | UC-07 |
| OBJ-07 | RF-CO-05, RF-CO-06, RF-DE-04, RNF-23, RNF-25 | UC-03, UC-05 |
| OBJ-08 | RF-DR-01 a RF-DR-07 | UC-11 |

## O que o código já cobre

Situação descrita no DOC-10 (seção 9), no README e nas ADRs:

- **Coleta:** PNCP (contratações por publicação e por atualização, contratos, atas, itens e
  resultados), IBGE (localidades e população) e SICONFI (entes, extrato de entregas; RREO, RGF e DCA
  com conector pronto e normalização pendente). Bronze com SHA-256, URL, instante e cabeçalhos;
  nada sobrescrito; respostas de erro HTTP guardadas como prova
  ([ADR-012](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-012.md)); limite de
  taxa, retentativa com recuo e User-Agent com contato. Cadastros de sanções da CGU (CEIS, CNEP e
  CEPIM, RF-CO-03 em parte) coletados pelos arquivos de dados abertos; base de CNPJ pendente.
- **Normalização:** esquema canônico do bloco de fatos, quarentena, silver idempotente e
  reconstruível do bronze, sensibilidade por campo e CPF mascarado
  ([ADR-016](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-016.md),
  [ADR-017](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-017.md)).
- **Detecção:** parâmetros legais datados e verificados
  ([ADR-013](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-013.md)) e máquina de
  estados do indício. O motor de regras é da Fase 2; a regra A-05 roda em modo silencioso, sem
  publicar ([ADR-027](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-027.md)).
- **Conformidade:** avaliação das entregas de DCA, RREO e RGF contra o prazo da LRF, com resultado
  indeterminado quando a dúvida é do Lumen (RF-CF-01, RF-CF-02, RF-CF-07).
- **Publicação:** painéis de Contratações e de Conformidade com fatos publicados, sem indício
  ([ADR-028](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-028.md)), e aba Eleições.

## Casos de uso (DOC-03)

Atores: cidadão, jornalista, pesquisador, analista Lumen (revisa indícios, calibra regras, cadastra
fontes), órgão de controle, ente público (direito de resposta) e sistema agendado.

| Caso | Ator principal | Resumo |
|---|---|---|
| UC-01 Consultar panorama de um ente | Cidadão | Busca o ente e vê despesa por exercício, principais fornecedores, modalidades, índice de conformidade, comparação com pares, indícios por severidade (sempre como atividade para análise), data da última coleta e aviso metodológico. Sem dado coletado, a tela diz que não houve publicação encontrada e remete ao UC-07 |
| UC-02 Pesquisar contratos e fornecedores | Jornalista | Busca avançada com filtros combinados (ente, UF, fornecedor, objeto, valor, período, modalidade, amparo legal), resultados paginados, detalhe do contrato com itens, aditivos e cadeia da despesa, sempre com link para o documento fonte; por CNPJ, agrega matriz e filiais |
| UC-03 Visualizar um indício e sua evidência | Cidadão, jornalista, órgão de controle | Rótulo de atividade para análise, explicação da regra em linguagem acessível, parâmetros, valores observados, referência comparada, documentos com hash e data de coleta, agente signatário e amparo legal, estado e contestação lado a lado. Se a origem saiu do ar, oferece a cópia da camada bruta |
| UC-04 Acompanhar um ente e receber alertas | Cidadão | Acompanhamento por e-mail validado, com periodicidade e severidade mínima; e-mail não validado em 72 horas é descartado sem armazenar |
| UC-05 Exportar dossiê de evidências | Jornalista, órgão de controle | Pacote com regra, parâmetros, dados de entrada, documentos, manifesto com hash e aviso metodológico, em PDF ou pacote compactado |
| UC-06 Comparar ente com grupo de pares | Jornalista, pesquisador | Composição e critérios do grupo, valor do ente, mediana e posição percentílica por indicador; grupo pequeno recebe ressalva explícita |
| UC-07 Consultar índice de conformidade | Cidadão, órgão de controle | Índice, critérios com dispositivo legal, distinção entre ausência persistente e indisponibilidade temporária, evolução histórica |
| UC-08 Revisar fila de indícios pendentes | Analista Lumen | Fila por severidade e antiguidade; o analista confere a evidência, decide publicar, descartar ou pedir nova coleta e registra a justificativa na trilha de auditoria |
| UC-09 Ajustar parâmetros de uma regra | Analista Lumen | Simulação sobre janela histórica, comparação entre versão vigente e simulada, nova versão registrada com histórico preservado |
| UC-10 Cadastrar nova fonte de dados | Analista Lumen | Cadastro declarativo, coleta de teste isolada, conferência da amostra normalizada e inclusão no agendamento |
| UC-11 Registrar contestação e direito de resposta | Ente público ou fornecedor | Contestação com documentos, protocolo, marcação pública em até 24 horas, reexecução da regra e desfecho publicado: manutenção com resposta, retificação ou remoção |
| UC-12 Executar ciclo de coleta | Sistema agendado | Retomada pela última coleta, coleta com limite de taxa, gravação no bronze, normalização, quarentena, enriquecimento; falha numa fonte não para as demais |
| UC-13 Executar ciclo de detecção | Sistema agendado | Regras ativas com versões vigentes, trilha de evidência por disparo, score e severidade, descarte com motivo abaixo do limiar e fila de revisão acima dele |
| UC-14 Consumir API pública | Jornalista, pesquisador, órgão de controle | Recursos versionados com paginação, data da última coleta e versão do esquema, com limite de taxa |

## Regras de negócio transversais

| Código | Regra |
|---|---|
| RN-01 | Nenhum texto exibido ao público afirma ou sugere conclusão sobre conduta; vale o vocabulário controlado do DOC-08 |
| RN-02 | Nenhum indício é publicado sem documento fonte armazenado e com hash verificável |
| RN-03 | Indício de severidade alta exige revisão humana antes da publicação, sem exceção |
| RN-04 | Toda decisão humana sobre um indício vai para trilha de auditoria somente-anexação |
| RN-05 | Contestação de representante identificado marca o indício como contestado em até 24 horas |
| RN-06 | Errata e remoção saem no mesmo canal e com o mesmo destaque da publicação original |
| RN-07 | Ausência de publicação obrigatória gera avaliação de conformidade, não erro de sistema |
| RN-08 | Documentos de pessoa física são mascarados em qualquer exibição, exportação ou dossiê |
| RN-09 | Critérios de detecção idênticos para todos os entes, sem exceção por porte, região ou vinculação política |
| RN-10 | Toda visualização informa a data da última coleta bem-sucedida da fonte |

## Critérios de aceitação da versão 1.0

- Todos os requisitos M implementados e cobertos por teste automatizado.
- Amostra aleatória de 100 indícios publicados revisada à mão, com taxa de falso positivo confirmado
  abaixo do limite do DOC-07.
- Todo indício da amostra com documento fonte recuperável e hash conferido.
- Verificador de vocabulário na integração contínua, sem nenhuma violação na base.
- Fluxo de direito de resposta testado de ponta a ponta, inclusive a errata.
- Metodologia de todas as regras ativas publicada.
- Plano de resposta a incidente de privacidade documentado, com teste de mesa realizado.
- Procedimento de restauração testado para a camada bruta e para o banco de domínio.
