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

Este repositório contém a **documentação completa do projeto** e o **núcleo da Fase 0**: a
camada de prova, a máquina de estados do indício, os parâmetros legais datados e o verificador
de vocabulário controlado. O desenvolvimento segue o plano descrito no DOC-10.

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

Os diagramas estão em [`docs/diagramas/`](docs/diagramas/) em PNG.

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

## Stack planejada

| Camada | Tecnologia |
|---|---|
| Orquestração | Dagster |
| Ingestão, normalização e detecção | Python |
| Camada bronze (prova) | Armazenamento de objetos com hash |
| Camadas silver e gold | Parquet + DuckDB |
| Domínio, indícios e auditoria | PostgreSQL |
| Busca textual | OpenSearch |
| API pública | Node.js + TypeScript |
| Portal | Next.js |

A justificativa de cada escolha está registrada como ADR no DOC-04.

## Regenerar a documentação

Os `.docx` são gerados por script, não editados à mão. A fonte está em `docs-src/`.

```bash
cd docs-src
npm install
npm run diagrams   # requer mermaid-cli; regenera os PNGs a partir dos .mmd
npm run docs       # gera os 10 .docx em ../docs/
```

Regra de estilo aplicada nos documentos: texto corrido e títulos sempre em preto; cor apenas
em tabelas e diagramas.

## Desenvolvimento

Requer apenas Python 3.11 ou superior. A Fase 0 não tem dependência de execução (ADR-015).

```bash
python -m pip install pytest pytest-cov

python ferramentas/lint-vocabulario/lint_vocabulario.py   # vocabulário controlado
python -m pytest                                          # suíte completa
```

Com `make`: `make verificar` roda exatamente o que a CI roda.

### Estrutura

```
packages/
  ingestao/     porta FonteDados, camada bronze (prova), coleta HTTP
  canonico/     entidade Indicio e máquina de estados, rótulos públicos
  deteccao/     parâmetros legais datados
ferramentas/
  lint-vocabulario/   verificador de vocabulário controlado (ADR-007)
docs/
  adr/          decisões arquiteturais — as 011 a 015 aguardam revisão
```

## Situação do projeto

**Fase 0 — Fundação: núcleo concluído.** O marco M1 do DOC-10 está cumprido e é verificado por
teste automatizado: um artefato é coletado, armazenado com hash verificável e recuperado a
partir do identificador — e prova adulterada é detectada (`test_marco_m1.py`).

| Componente | Garantia | Testes |
|---|---|---|
| Camada bronze | Nada sobrescrito; hash reconferido em toda leitura; alteração na fonte registrada | 33 |
| Coleta HTTP | Identificação obrigatória; resposta de erro preservada como prova | 13 |
| Porta FonteDados | Falha isolada por artefato; prova corrompida interrompe a coleta | 15 |
| Marco M1, ponta a ponta | Coleta real por HTTP, armazenamento, recuperação e detecção de adulteração | 2 |
| Máquina de estados do indício | Severidade alta só publica com dois revisores distintos e evidência | 142 |
| Parâmetros legais | Consulta pela data do ato; não verificado é recusado | 18 |
| Vocabulário controlado | Termo que imputa conduta quebra o build | 60 |

283 testes, cobertura de 97% no núcleo.

### Pendente para concluir a Fase 0

- **Revisar as ADRs 011 a 015**, tomadas durante a implementação.
- **Cadastrar os limites de dispensa de 2021 a 2025**, conferidos nos decretos de cada ano.
  Sem eles, as regras de fracionamento não disparam para atos anteriores a 2026 (ADR-013).
- **Conferir o art. 125 da Lei 14.133/2021** e marcar os limites de aditivo como verificados.
- **Esquema canônico do bloco de fato administrativo** (Contrato, Empenho, Item). Foi adiado de
  propósito: o DOC-05 foi escrito a partir da documentação do PNCP, e o esquema canônico desse
  bloco deve nascer de respostas reais da API, que costumam divergir da documentação.
- **Backend de armazenamento de objetos** para a camada bronze e ambiente local com PostgreSQL.

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
endpoints citados foram verificados em fontes oficiais em setembro de 2026 e são atualizados
periodicamente por decreto — reconfira antes de implementar.
