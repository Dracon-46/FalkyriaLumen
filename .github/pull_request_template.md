## O que muda

<!-- Uma ou duas frases sobre a mudança, do ponto de vista de quem usa ou de quem desenvolve. -->

## Por quê

<!-- O motivo. Cite a issue, o documento e o requisito (ex.: DOC-07 família B, RF-DE-06) e a ADR,
se a mudança envolve decisão arquitetural (nova ou existente). -->

- Issue:
- Documento e requisito:
- ADR:

## Como foi verificado

- [ ] Testes: `make testes` (ou `python -m pytest`) passa, com teste novo que falharia se a mudança fosse revertida
- [ ] Cobertura: `make cobertura` acima de 80%
- [ ] Vocabulário controlado: `make vocabulario` sem violação (e, para arquivos fora dos alvos, `python ferramentas/lint-vocabulario/lint_vocabulario.py <arquivos>`)
- [ ] Estilo: `make estilo` (ruff) sem apontamentos
- [ ] Documentação do código: `python ferramentas/referencia/referencia.py --verificar` sem pendências
- [ ] Portal, se mudou: `npm run verificar` e `npm run build` em `packages/portal`
- [ ] Banco, se mudou: migração nova em `packages/canonico/migrations` e `make banco`
- [ ] Contrato dos feeds, se mudou: Python, portal e `testes/fixtures/eleicoes_feed` atualizados juntos
- [ ] Nenhum valor legal fixado no código; nenhum segredo, credencial ou dado pessoal real
- [ ] Documentação: README, Wiki (`docs/wiki/`), DOC (`docs-src/`, `make docs`) e `CHANGELOG.md`, quando aplicável

## Observações para a revisão

<!-- Riscos, limitações conhecidas, o que ficou de fora e por quê. -->
