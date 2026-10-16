# Glossário

Termos do domínio e do projeto. As definições de domínio seguem o glossário do DOC-01 (seção 9);
as técnicas, o DOC-04, o DOC-05 e as ADRs.

## Domínio

| Termo | Definição no projeto |
|---|---|
| **Amparo legal** | Dispositivo da lei invocado para justificar a forma de contratação; no PNCP vem como campo estruturado. O Lumen usa o código do amparo para escolher o parâmetro legal datado, nunca o valor escrito na descrição |
| **Ato autorizativo** | Documento pelo qual um agente público autoriza uma contratação ou despesa |
| **Agente público** | Quem assinou atos administrativos; o Lumen registra só o que é publicado no exercício da função |
| **CATMAT / CATSER** | Catálogos federais de materiais e serviços, usados para normalizar itens entre entes |
| **CEIS / CNEP / CEPIM** | Cadastros federais de empresas e entidades sancionadas ou impedidas |
| **DCA** | Declaração de Contas Anuais, enviada ao SICONFI; prazo no art. 51 da LC 101/2000 |
| **Dispensa de licitação** | Contratação direta permitida por lei em hipóteses específicas, inclusive por valor |
| **Empenho, liquidação, pagamento** | Os três estágios da despesa pública |
| **Ente** | Unidade da federação ou órgão público analisado: União, estado, Distrito Federal ou município, identificado pelo código IBGE |
| **Esfera** | União, estadual, municipal ou distrital |
| **Fracionamento** | Divisão de uma despesa em parcelas menores, de modo que cada uma fique abaixo de um limite legal |
| **Grupo de pares** | Conjunto de entes comparáveis por porte, região e capacidade fiscal |
| **IBGE** | Instituto Brasileiro de Geografia e Estatística: cadastro de UFs e municípios, população estimada e malhas do mapa |
| **Inexigibilidade** | Modalidade de contratação direta prevista em lei; com a dispensa, forma o grupo das contratações diretas no modelo (`eh_contratacao_direta`, DOC-09) |
| **LRF** | Lei de Responsabilidade Fiscal (LC 101/2000): fixa os prazos de RREO, RGF e contas anuais avaliados no painel de Conformidade |
| **Modalidade** | Forma da contratação: pregão, concorrência, dispensa, inexigibilidade, concurso, leilão e diálogo (DOC-05) |
| **Órgão** | Quem publicou no PNCP, identificado pelo CNPJ: prefeitura, câmara, autarquia, fundação, empresa pública |
| **PNCP** | Portal Nacional de Contratações Públicas, criado pela Lei 14.133/2021: licitações, contratos, atas e amparo legal |
| **Porte** | Faixa populacional do ente, base do grupo de pares |
| **RREO** | Relatório Resumido de Execução Orçamentária (nome do entregável no extrato do SICONFI), por bimestre; prazo no art. 52 da LC 101/2000 |
| **RGF** | Relatório de Gestão Fiscal, quadrimestral ou semestral (LRF, art. 63), avaliado por Poder; prazo no art. 55, § 2º, da LC 101/2000 |
| **SICONFI** | Sistema de Informações Contábeis e Fiscais do Setor Público Brasileiro, do Tesouro Nacional |
| **TSE** | Tribunal Superior Eleitoral: sistema de divulgação de resultados (ao vivo) e Portal de Dados Abertos |
| **ANP** | Publica a pesquisa semanal de preço de revenda dos combustíveis e do gás de cozinha, posto a posto; é a régua da regra A-05 |
| **Unidade gestora** | Unidade do órgão que conduz o processo; no PNCP, identificada pelo CNPJ do órgão e pelo código da unidade |

## Indícios e publicação

| Termo | Definição no projeto |
|---|---|
| **Indício** | Sinalização produzida por uma regra, sempre acompanhada de evidência e nunca de conclusão |
| **Atividade para análise** | Rótulo padronizado de todo indício exibido ao público |
| **Regra** | Especificação versionada do DOC-07 que produz indícios; código com a letra da família e um sequencial (ex.: `B-01`) |
| **Família** | Grupo de regras do catálogo, de A a K (ex.: A, preço; B, fracionamento; I, conformidade; K, contexto eleitoral) |
| **Score e severidade** | Score composto entre 0 e 1; severidade baixa, média ou alta conforme a faixa do score |
| **Revisão humana** | Severidade média exige um revisor; alta, dois revisores distintos. Severidade baixa nunca é publicada |
| **Modo silencioso** | A regra roda e grava resultado interno para calibração, sem publicar nada (ex.: A-05) |
| **Calibração** | Medição da taxa de falso positivo de uma regra sobre dados históricos antes de publicar |
| **Contestação** | Manifestação formal de ente ou fornecedor sobre um indício publicado; marca o indício como contestado em até 24 horas |
| **Errata** | Correção publicada com o mesmo destaque da publicação original (princípio P4) |
| **Trilha de evidência** | Regra, parâmetros, dados de entrada e documentos que sustentam um indício |
| **Trilha de auditoria** | Registro somente-anexação de toda decisão humana, com autor, data e justificativa |
| **Conformidade** | Avaliação do cumprimento das obrigações legais de publicação por um ente: cumpre, cumpre parcialmente, não cumpre ou indeterminado |
| **Indeterminado** | Resultado de conformidade quando a dúvida é do Lumen (coleta que falhou, prazo não vencido, instituição não identificada); exige motivo |
| **Parâmetro legal datado** | Valor legal (limite, percentual, prazo) com vigência, fundamento e verificação, consultado pela data do ato |
| **Vocabulário controlado** | Lista de termos proibidos em texto público, verificada na CI ([ADR-007](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-007.md)) |
| **Teto de plausibilidade** | Nos painéis, valor acima de R$ 10 bilhões ou de R$ 20 mil por habitante do ente fica fora das somas e vai para "Valores a conferir na fonte" |
| **Referência de mercado** | Distribuição de preços de fora do governo (ANP, varejo) usada pela regra A-05; a régua é a mediana |

## Dados e arquitetura

| Termo | Definição no projeto |
|---|---|
| **Artefato bruto** | O conteúdo exatamente como a fonte entregou, com URL, hash SHA-256, instante e cabeçalhos |
| **Bronze** | Camada da prova: artefatos brutos imutáveis, nunca alterados nem apagados; o conteúdo é guardado uma vez sob o próprio SHA-256 e cada coleta gera um registro |
| **Silver** | Camada dos registros no esquema canônico, em JSON Lines particionado; reconstruível do bronze |
| **Gold** | Camada derivada (agregados, indícios), recalculada a cada mudança de regra; ainda não implementada |
| **Prova** | O que sustenta qualquer afirmação do sistema: o artefato bruto e o seu hash |
| **Esquema canônico** | Modelo de dados único para o qual toda fonte é convertida |
| **Conector / adaptador** | Componente que sabe obter dados de uma fonte e entregá-los pela porta `FonteDados` |
| **FonteDados** | A porta única de acesso a qualquer fonte: descrever capacidades, listar, baixar e reportar conformidade |
| **Quarentena** | Onde vai a linha que não pode virar registro canônico, com o motivo, sem bloquear o lote |
| **Marcação de qualidade** | Ressalva que acompanha um registro aproveitável até a tela (ex.: `valor_estimado_zero`) |
| **Identidade determinística** | Id UUIDv5 calculado da chave natural: o mesmo dado tem sempre o mesmo id |
| **`numeroControlePNCP`** | Identificador do PNCP para processos, contratos e atas; chave natural no Lumen |
| **Somente-anexação** | Tabela que aceita inserção, mas recusa alteração e remoção (prova e auditoria) |
| **Object Lock** | Trava de bucket S3 que impede apagar ou sobrescrever um objeto durante a retenção |
| **Manifesto** | Arquivo pequeno com URL, tamanho, SHA-256, ETag e data de um arquivo grande; vai para o bronze no lugar do arquivo |
| **ADR** | Registro de decisão arquitetural, em `docs/adr/` |

## Eleições

| Termo | Definição no projeto |
|---|---|
| **Feed** | Arquivo JSON com contrato versionado que o portal lê; o portal nunca chama o TSE |
| **Índice** | `indice.json`: as eleições publicadas e os seus cargos; é o primeiro arquivo que a aba lê |
| **Abrangência** | Recorte de um feed: Brasil (`br`), UF (`uf-<sigla>`) ou município (`mu-<chave>`) |
| **Partes** | As abrangências filhas de um feed (UFs no Brasil, municípios na UF, zonas no município), que pintam o mapa |
| **Resultado** | Feed com candidatos, votos, comparecimento e totalização de um cargo numa abrangência |
| **Panorama** | Feed de um cargo visto de cima, onde não há resultado único (prefeitos na UF, governadores no Brasil): o líder de cada parte e o placar por partido |
| **Histórico** | Feed com a evolução da totalização, ponto a ponto, para o gráfico |
| **Totalização** | Andamento da apuração: seções totalizadas sobre o total |
| **Sistema de resultados** | `resultados.tse.jus.br/oficial`, de onde vem a apuração ao vivo |
| **Dados abertos** | Arquivos ZIP do Portal de Dados Abertos do TSE, de 1933 em diante |
| **Zona eleitoral** | Divisão da Justiça Eleitoral dentro de um município; 190 municípios têm duas ou mais em 2026 |
| **Local de votação** | Endereço onde ficam as seções; o TSE publica as coordenadas, e o Lumen aproxima o contorno das zonas pelo diagrama de Voronoi desses locais |
| **Contorno aproximado** | O desenho das zonas no mapa: a Justiça Eleitoral não publica os limites, e a tela diz isso |
| **Malha** | Geometria do IBGE em TopoJSON, usada no mapa |
| **UF histórica** | UF extinta ou de outro território (Guanabara, Distrito Federal antes de 1960, territórios), com código próprio e sem área no mapa atual |
| **Ano em aberto** | Ano cujos dados abertos ainda podem ganhar arquivos (2026); o `preparar` confere a fonte a cada execução |
| **Índice de cor** | Número de 0 a 7 que o feed atribui a cada candidato pela ordem de votação; nunca a cor do partido |

## Painéis e operação

| Termo | Definição no projeto |
|---|---|
| **Painel** | Área do portal com fatos publicados, sem indício: Contratações (PNCP) e Conformidade (entregas da LRF) |
| **Estado dos painéis** | Arquivos compactos por dia do PNCP e por UF, guardados nos anexos da versão `painel-estado` |
| **Estado da carga** | O que a carga das eleições já fez, no bucket privado; permite continuar numa máquina que começa vazia |
| **Publicação** | Envio ao bucket público só dos arquivos que mudaram, com o índice por último |
| **Carga retomável** | Carga que para antes do prazo e continua na execução seguinte sem refazer o que já foi feito |
