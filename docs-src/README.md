# Fonte da documentacao

Os arquivos `.docx` em `../docs/` sao gerados por script e nao devem ser editados a mao:
qualquer alteracao manual e perdida na proxima geracao.

## Estrutura

- `lib.js` — helpers de montagem do documento (capa, titulos, tabelas, caixas de destaque,
  blocos de codigo, figuras) e a paleta. Centraliza o estilo de todos os documentos.
- `build_NN_*.js` — um script por documento. Contem o conteudo e chama `lib.buildDoc()`.
- `diagrams/*.mmd` — fontes Mermaid dos diagramas.

## Gerar

```bash
npm install
npm run diagrams   # regenera os PNGs (requer Chromium para o mermaid-cli)
npm run docs       # gera os .docx em ../docs/
```

## Convencoes de estilo

- Texto corrido e titulos sempre em preto. Cor apenas em tabelas e diagramas.
- Tabelas precisam de largura dupla: `columnWidths` na tabela e `width` em cada celula,
  ambos em DXA. Percentual quebra no Google Docs.
- Sombreamento de celula usa `ShadingType.CLEAR`; `SOLID` renderiza preto.
- Figuras exigem `lineRule: AUTO` no paragrafo. Sem isso a imagem herda o espacamento de
  linha do estilo padrao e e cortada numa tira de poucos pixels de altura.
- Proporcao de diagrama entre ~0,45:1 e ~3,5:1. Fora disso a figura fica ilegivel na pagina.
- Nao usar `\n` em texto: cada paragrafo e um objeto proprio.

## Verificacao obrigatoria

Depois de gerar, renderize e olhe antes de considerar pronto:

```bash
soffice --headless --convert-to pdf ../docs/DOC-01_Visao_e_Escopo.docx
pdftoppm -jpeg -r 80 DOC-01_Visao_e_Escopo.pdf pagina
```

O sumario aparece vazio no PDF convertido: o campo TOC so e preenchido pelo Word ao atualizar
os campos. Isso e esperado e nao e defeito.
