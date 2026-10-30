# Como contribuir

Obrigado pelo interesse no Falkyria Lumen. O guia completo está na Wiki, na página
[Contribuindo](https://github.com/Dracon-46/FalkyriaLumen/wiki/Contribuindo), com base no
[DOC-09 Padrões de Código](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/DOC-09_Padroes_de_Codigo.docx).
Este arquivo é a versão curta.

## Licença das contribuições

O Lumen é software proprietário da Falkyria ([LICENSE](LICENSE)): o código está público só para
consulta. Pull request de fora só é aceito com um acordo por escrito com a Falkyria que ceda a ela os
direitos sobre o código contribuído. Sem esse acordo, use as issues: erro, melhoria e dado divergente
da fonte oficial são bem-vindos.

## Antes de tudo

O Lumen publica indícios, nunca conclusões. Todo texto que pode chegar ao público (portal, rótulos,
avisos dos feeds, relatórios, documentação) usa vocabulário controlado, verificado na integração
contínua. Termos que imputam conduta a pessoas ou órgãos quebram o build
([ADR-007](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-007.md)). A lista está em
[`ferramentas/lint-vocabulario/vocabulario.json`](https://github.com/Dracon-46/FalkyriaLumen/blob/main/ferramentas/lint-vocabulario/vocabulario.json).

## Fluxo

1. Abra uma issue com um dos formulários: erro, melhoria ou dado divergente da fonte oficial.
2. Crie um ramo a partir da `main`: `tipo/descricao-curta` (ex.: `fix/painel-conformidade`).
3. Faça commits no padrão Conventional Commits em português (`feat`, `fix`, `refactor`, `test`,
   `docs`, `chore`, `perf`), com o pacote como escopo e a referência ao documento e ao requisito.
   A mensagem explica por quê.
4. Rode localmente o que a CI roda:

   ```bash
   python -m pip install -e ".[dev,analitico]"
   make verificar      # vocabulário, ruff e testes com cobertura mínima de 80%
   make portal         # se mexeu em packages/portal
   ```

5. Abra o pull request com o modelo do repositório e espere a CI verde e a revisão.

## Regras que a revisão confere

- Nenhum valor legal fixado no código: use os parâmetros datados de
  `packages/deteccao/lumen_deteccao/parametros_legais.toml`, consultados pela data do ato.
- Toda função, classe e módulo documentado (docstring ou `/** */`); a CI recusa o que ficar sem texto.
- Testes do caminho feliz e de ao menos um caminho de erro.
- Dependência nova só com o motivo registrado
  ([ADR-015](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-015.md)).
- Decisão arquitetural relevante tem ADR em `docs/adr/` (numerada em sequência, nunca apagada).
- Mudança no contrato dos feeds atualiza o Python, o portal e a amostra no mesmo commit.
- Nenhum segredo, credencial ou dado pessoal real no repositório.
- Mudança visível para quem usa entra no `CHANGELOG.md`.

## Versões

A versão é a mesma em `pyproject.toml`, `packages/canonico/lumen_canonico/__init__.py`
(`VERSAO_LUMEN`) e `packages/portal/package.json`, com uma seção no `CHANGELOG.md`.

## Documentação

Os `.docx` em `docs/` são gerados a partir de `docs-src/` (`make docs`); não edite à mão. As páginas
da Wiki vivem em `docs/wiki/` e são publicadas a cada mudança na `main`.

## Conduta e segurança

Siga o [Código de Conduta](CODE_OF_CONDUCT.md). Falhas de segurança não vão em issue pública: veja
[SECURITY.md](SECURITY.md).
