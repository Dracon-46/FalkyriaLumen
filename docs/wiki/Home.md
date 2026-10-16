# Falkyria Lumen

O Lumen é um sistema de monitoramento de contratações e despesas públicas do Brasil. Ele coleta,
normaliza e analisa dados de contratações e despesas dos entes federativos, a partir de duas bases
federais de envio obrigatório (PNCP e SICONFI), e sinaliza atividades que merecem análise por
órgãos de controle, imprensa e sociedade civil. O sistema publica indícios, nunca conclusões: toda
sinalização é rotulada como atividade para análise e acompanhada da evidência primária, da regra
aplicada e dos parâmetros. Hoje o repositório tem a Fase 0 concluída, o núcleo da Fase 1 (coleta e
normalização do PNCP, IBGE e SICONFI, conformidade da LRF), a aba Eleições do portal, com
resultados oficiais do TSE de 1933 a 2026, e os painéis de Contratações e de Conformidade, com
fatos publicados e sem indício.

"Lumen" é nome de trabalho, sujeito a verificação de disponibilidade (DOC-01). A versão atual é a
0.8.0 ([CHANGELOG](https://github.com/Dracon-46/FalkyriaLumen/blob/main/CHANGELOG.md)).

## Páginas desta Wiki

| Página | Conteúdo |
|---|---|
| [[Visão geral|Visao-Geral]] | Objetivo, problema, público, escopo e princípios inegociáveis |
| [[Requisitos|Requisitos]] | Requisitos funcionais e não funcionais (RF-..., RNF-...) e casos de uso |
| [[Arquitetura|Arquitetura]] | Componentes, camadas bronze e silver, fluxo dos dados e decisões (ADRs) |
| [[Tecnologias|Tecnologias]] | Linguagens, bibliotecas e serviços de hospedagem, com o porquê de cada um |
| [[Componentes|Componentes]] | Organização do repositório: cada pacote, ferramentas, testes e infraestrutura |
| [[Instalação e execução|Instalacao-e-Execucao]] | Pré-requisitos, instalação, pipeline, aba Eleições, portal e Windows |
| [[Configuração e variáveis|Configuracao-e-Variaveis]] | Chaves do `lumen.toml`, variáveis de ambiente, segredos e variáveis do GitHub Actions |
| [[APIs e contratos|APIs-e-Contratos]] | Fontes consumidas, contrato dos feeds JSON e comandos `lumen` |
| [[Banco de dados|Banco-de-Dados]] | Modelo de dados, migrações, garantias do banco e PostgreSQL local |
| [[Testes|Testes]] | Como rodar a suíte, estágios da CI e fixtures reais |
| [[Deploy e operação|Deploy-e-Operacao]] | Publicação do portal e dos feeds, cargas no GitHub Actions, noite da eleição, limites e reversão |
| [[Contribuindo|Contribuindo]] | Fluxo de trabalho, padrões de código, vocabulário controlado, ADRs e versões |
| [[Roadmap|Roadmap]] | Fases do DOC-10 e o que está pendente |
| [[Glossário|Glossario]] | Termos do domínio e do projeto |

## Documentos oficiais

Os documentos `.docx` são a documentação normativa do projeto. Ficam em
[`docs/`](https://github.com/Dracon-46/FalkyriaLumen/tree/main/docs) e são gerados por script a
partir de [`docs-src/`](https://github.com/Dracon-46/FalkyriaLumen/tree/main/docs-src) (`make docs`);
não se editam à mão.

| Doc | Conteúdo |
|---|---|
| [DOC-01](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/DOC-01_Visao_e_Escopo.docx) | Visão e Escopo |
| [DOC-02](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/DOC-02_Requisitos.docx) | Requisitos funcionais e não funcionais |
| [DOC-03](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/DOC-03_Casos_de_Uso.docx) | Casos de uso |
| [DOC-04](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/DOC-04_Arquitetura.docx) | Arquitetura, ADRs e estratégia de escala |
| [DOC-05](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/DOC-05_Modelo_de_Dados.docx) | Modelo de dados e resolução de identidade |
| [DOC-06](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/DOC-06_Catalogo_de_Fontes.docx) | Catálogo de fontes |
| [DOC-07](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/DOC-07_Motor_de_Deteccao.docx) | Motor de detecção: regras, fórmulas, limiares e falsos positivos |
| [DOC-08](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/DOC-08_Politica_Juridica_e_Editorial.docx) | Política jurídica e editorial, vocabulário controlado, LGPD e direito de resposta |
| [DOC-09](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/DOC-09_Padroes_de_Codigo.docx) | Padrões de código, testes, CI/CD e definição de pronto |
| [DOC-10](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/DOC-10_Roadmap.docx) | Roadmap: fases, marcos, esforço e custos |
| [DOC-11](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/DOC-11_Referencia_Tecnica.docx) | Referência técnica, gerada do código |
| [DOC-12](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/DOC-12_Eleicoes.docx) | Aba Eleições: fontes, arquitetura e operação |
| [DOC-13](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/DOC-13_Paineis.docx) | Painéis de Contratações e de Conformidade |

Os diagramas estão em
[`docs/diagramas/`](https://github.com/Dracon-46/FalkyriaLumen/tree/main/docs/diagramas), em PNG.

## Decisões arquiteturais (ADRs)

As ADRs ficam em [`docs/adr/`](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/README.md).
As ADRs 001 a 010 estão aceitas; as 011 a 029 foram tomadas durante a implementação e estão como
propostas, aguardando revisão. Uma ADR nunca é apagada: quando substituída ou rejeitada, fica no
diretório com a situação marcada.

## Sobre esta Wiki

As páginas vivem no repositório, em
[`docs/wiki/`](https://github.com/Dracon-46/FalkyriaLumen/tree/main/docs/wiki), e passam por revisão
no PR como qualquer outro texto. O fluxo
[`wiki.yml`](https://github.com/Dracon-46/FalkyriaLumen/blob/main/.github/workflows/wiki.yml) as copia
para a Wiki a cada mudança na `main`; editar pela interface do GitHub não adianta, porque a próxima
publicação sobrescreve. Em caso de diferença entre esta Wiki e os documentos oficiais, valem os
documentos oficiais e as ADRs.
