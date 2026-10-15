# Fonte da documentacao

Os arquivos `.docx` em `../docs/` sao gerados por script e nao devem ser editados a mao:
qualquer alteracao manual e perdida na proxima geracao.

## Estrutura

- `lib.js` — helpers de montagem do documento (capa, titulos, tabelas, caixas de destaque,
  blocos de codigo, figuras) e a paleta. Centraliza o estilo de todos os documentos.
- `build_NN_*.js` — um script por documento. Contem o conteudo e chama `lib.buildDoc()`.
- `diagrams/*.mmd` — fontes Mermaid dos diagramas, renderizados em `../docs/diagramas/`.
- `../docs/diagramas/14_tela_aba_eleicoes.png`, `15_tela_modo_tv.png`, `16_tela_eleicao_1945.png`,
  `17_tela_mapa_aproximado.png`, `19_tela_contratacoes.png` e `20_tela_conformidade.png` — capturas de
  tela do portal (não vêm de `.mmd`): refaça-as com o portal rodando quando a interface mudar. As dos
  painéis usam dados sintéticos de teste, ditos na legenda.
- `referencia.json` — extração do código usada pelo DOC-11 (Referência Técnica). É gerado por
  `ferramentas/referencia/referencia.py`, regenerado por `make docs` antes dos `.docx` e fora do Git.

## Gerar

```bash
npm install
npm run referencia # extrai do código o conteúdo do DOC-11 (referencia.json)
npm run diagrams   # regenera os PNGs (requer Chromium para o mermaid-cli)
npm run docs       # gera os .docx em ../docs/
```

Na raiz do repositório, `make docs` faz a referência e os documentos de uma vez.

## Convencoes de estilo

- Texto corrido e titulos sempre em preto. Cor apenas em tabelas e diagramas.
- Tabelas precisam de largura dupla: `columnWidths` na tabela e `width` em cada celula,
  ambos em DXA. Percentual quebra no Google Docs.
- Sombreamento de celula usa `ShadingType.CLEAR`; `SOLID` renderiza preto.
- Figuras exigem `lineRule: AUTO` no paragrafo. Sem isso a imagem herda o espacamento de
  linha do estilo padrao e e cortada numa tira de poucos pixels de altura.
- Proporcao de diagrama entre ~0,45:1 e ~3,5:1. Fora disso a figura fica ilegivel na pagina.
- Nao usar `\n` em texto: cada paragrafo e um objeto proprio.
- Titulos ficam presos ao paragrafo seguinte (`keepNext`). Para abrir pagina nova antes de um
  titulo, use `h1(texto, { novaPagina: true })`, e nao `pageBreak()` seguido de `h1`: a quebra
  como paragrafo proprio vira pagina em branco quando o conteudo anterior termina no fim da pagina.
- Listas numeradas que devem recomecar do 1 recebem `instance` diferente
  (`numberedRuns(runs, 0, instancia)`).

## Verificacao obrigatoria

Depois de gerar, renderize e olhe antes de considerar pronto:

```bash
soffice --headless --convert-to pdf ../docs/DOC-01_Visao_e_Escopo.docx
pdftoppm -jpeg -r 80 DOC-01_Visao_e_Escopo.pdf pagina
```

O sumario aparece vazio no PDF convertido: o campo TOC so e preenchido pelo Word ao atualizar
os campos. Isso e esperado e nao e defeito.
