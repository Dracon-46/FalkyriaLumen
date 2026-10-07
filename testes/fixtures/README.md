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
| `ibge/municipios_nivelado_amostra.json` | 2 dos 5.571 municípios |

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

## Como recapturar

As URLs estão nos testes de contrato de cada conector
(`testes/contrato/`). Ao recapturar, mantenha o corte descrito acima e
atualize a data no topo deste arquivo.
