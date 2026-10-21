# Contribuindo

Fonte: [DOC-09 Padrões de Código](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/DOC-09_Padroes_de_Codigo.docx).
A versão curta está em [`CONTRIBUTING.md`](https://github.com/Dracon-46/FalkyriaLumen/blob/main/CONTRIBUTING.md);
a conduta esperada, em [`CODE_OF_CONDUCT.md`](https://github.com/Dracon-46/FalkyriaLumen/blob/main/CODE_OF_CONDUCT.md);
falhas de segurança se relatam como em [`SECURITY.md`](https://github.com/Dracon-46/FalkyriaLumen/blob/main/SECURITY.md).

## Fluxo de trabalho

1. **Issue.** Use os formulários do repositório: relato de erro, proposta de melhoria ou número
   divergente da fonte oficial.
2. **Ramo.** Saia da `main`, que está sempre implantável, num ramo `tipo/descricao-curta` (ex.:
   `feat/conector-pncp`).
3. **Commits.** Conventional Commits em português, um commit por mudança lógica coesa. Tipos:
   `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `perf`; escopo é o nome do pacote
   (`feat(deteccao): …`). A mensagem responde por quê, não o quê, e cita o documento e o requisito:

   ```
   feat(deteccao): adiciona regra B-01 de fracionamento por agregacao

   Agrupa contratacoes diretas do mesmo ente e fornecedor com objeto
   similar em janela de 180 dias e compara a soma com o limite legal
   vigente na data de cada ato.

   Ref: DOC-07 familia B, RF-DE-06
   ```

4. **Antes do PR**, rode o que a CI roda: `make verificar` (vocabulário, ruff e cobertura mínima de
   80%) e, se mexeu no portal, `make portal`. Se mexeu no banco, `make ambiente` e `make banco`.
5. **Pull request** com o modelo do repositório: o que muda, por quê (ADR, se houver) e como foi
   verificado.
6. **CI verde** em todos os estágios bloqueantes (ver [[Testes|Testes]]).
7. **Revisão.** A definição de pronto é verificada na revisão, não na autoavaliação de quem
   desenvolveu. O responsável pelo repositório está em
   [`.github/CODEOWNERS`](https://github.com/Dracon-46/FalkyriaLumen/blob/main/.github/CODEOWNERS).

## Padrões de código

### Idioma

| Camada | Idioma | Por quê |
|---|---|---|
| Entidades de domínio, campos do esquema canônico, regras de detecção | Português | Termos jurídicos sem equivalente preciso (dispensa, empenho, liquidação, inexigibilidade, amparo legal) |
| Infraestrutura e utilitários | Inglês | Convenção do ecossistema, sem carga de domínio |
| Bibliotecas de terceiros | Inglês | Não se traduz o que não é nosso |

### Nomes

| Elemento | Convenção | Exemplo |
|---|---|---|
| Módulo e arquivo Python | snake_case | `processo_contratacao.py` |
| Classe | PascalCase | `ProcessoContratacao` |
| Função e variável Python | snake_case | `calcular_escore_robusto` |
| Constante | UPPER_SNAKE_CASE | `LIMITE_DISPENSA_COMPRAS` |
| Arquivo TypeScript | kebab-case | `indicio-controller.ts` |
| Função e variável TypeScript | camelCase | `buscarIndiciosPorEnte` |
| Tabela e coluna SQL | snake_case singular | `processo_contratacao`, `valor_unitario` |
| Código de regra | letra da família + sequencial | `B-01`, `D-04` |
| Especificação de fonte | `uf_ente_objeto` | `sp_campinas_contratos.yaml` |

### Regras do projeto

- **Valores legais nunca ficam no código.** Limites, percentuais e prazos vêm de
  [`parametros_legais.toml`](https://github.com/Dracon-46/FalkyriaLumen/blob/main/packages/deteccao/lumen_deteccao/parametros_legais.toml),
  consultados pela data do ato, nunca pela data atual. Parâmetro novo entra como não verificado até
  ser conferido na fonte oficial
  ([ADR-013](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-013.md)).
- **Sem dependência nova sem motivo.** O núcleo usa só a biblioteca padrão; dependência entra com a
  funcionalidade que a exige e o motivo registrado
  ([ADR-015](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-015.md)).
- **Tudo documentado.** Todo módulo, classe, função, método, componente, interface e tipo tem
  docstring (Python) ou bloco `/** */` (TypeScript); a CI recusa o que ficar sem texto
  ([ADR-023](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-023.md)).
- **Estilo Python:** `ruff` com as regras `E`, `F`, `W`, `I`, `B`, linha de até 120 caracteres.
- **Dado ausente é o normal.** Trate a ausência explicitamente e distinga erro de coleta de ausência
  de publicação pelo ente.
- **Idempotência.** Todo processamento pode ser repetido e deve dar o mesmo resultado.
- **Nunca registrar em log** documento de pessoa física sem máscara, conteúdo integral de artefato
  coletado, token ou credencial.

### Roteiro de revisão (DOC-09, seção 6)

- O texto exibido ao público está em linguagem neutra, sem inferência sobre conduta?
- Valores legais vêm de parâmetro datado, consultado pela data do ato?
- O indício carrega regra, versão, parâmetros e ao menos um documento fonte?
- A transformação preserva a linhagem até o artefato bruto?
- Dado pessoal foi minimizado e documento de pessoa física mascarado antes da camada consultável?
- A regra nova entrou em modo silencioso, e não direto em publicação?
- Há teste que falharia se a mudança fosse revertida?
- Alguma consulta nova varre partição inteira sem filtro por exercício ou ente?

### Definição de pronto

- O código atende ao requisito referenciado, e o número do requisito consta no commit.
- Há testes do caminho feliz, de ao menos um caminho de erro e, para regra, do falso positivo
  conhecido.
- A CI está verde em todos os estágios bloqueantes.
- Nenhum valor legal fixado no código.
- Textos públicos passaram pelo verificador de vocabulário.
- Decisão arquitetural relevante tem ADR.
- Mudança no esquema canônico tem migração e os dois lados da fronteira atualizados.
- Regra nova ou alterada tem a explicação pública aprovada pelo comitê de metodologia.
- Fonte nova tem fixture versionada e teste de contrato.
- Nenhum segredo, credencial ou dado pessoal real no repositório.

## Vocabulário controlado

O Lumen publica indícios, nunca conclusões. Todo texto que pode chegar ao público passa pelo
verificador
[`ferramentas/lint-vocabulario/lint_vocabulario.py`](https://github.com/Dracon-46/FalkyriaLumen/blob/main/ferramentas/lint-vocabulario/lint_vocabulario.py),
que quebra o build quando encontra termo que imputa conduta
([ADR-007](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-007.md)).

- A lista vigente, as expressões técnicas permitidas e os arquivos verificados estão em
  [`vocabulario.json`](https://github.com/Dracon-46/FalkyriaLumen/blob/main/ferramentas/lint-vocabulario/vocabulario.json).
  `python ferramentas/lint-vocabulario/lint_vocabulario.py --listar` mostra a lista com a sugestão
  de substituição de cada termo.
- A comparação ignora acento e caixa, e respeita fronteira de palavra.
- Expressões técnicas legítimas são mascaradas antes da verificação (por exemplo "desvio padrão",
  "esquema canônico", "mudança de esquema").
- Substituições usuais: "atividade para análise", "valor em análise", "preço acima da referência
  comparada", "padrão atípico identificado", "divergência em relação ao parâmetro", "distinto do
  previsto no dispositivo citado", "signatário do ato".
- O rótulo recai sobre a atividade, nunca sobre a pessoa ou a empresa. Os rótulos públicos fixos
  vivem em [`rotulos.py`](https://github.com/Dracon-46/FalkyriaLumen/blob/main/packages/canonico/lumen_canonico/rotulos.py).
- O verificador olha o modelo da explicação, não o texto renderizado com dados de terceiros
  ([ADR-014](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-014.md)).
- Exceção só para caso genuíno (texto literal de terceiro, aviso que nega a imputação), com o
  marcador `lumen:vocabulario-ok` na linha e justificativa revisada no PR.
- Para conferir arquivos fora dos alvos configurados, passe-os na linha de comando:
  `python ferramentas/lint-vocabulario/lint_vocabulario.py docs/wiki/*.md`.

## Registrar uma decisão (ADR)

Decisão arquitetural relevante exige ADR (definição de pronto). Em
[`docs/adr/`](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/README.md):

1. Copie a estrutura de uma ADR existente: título, situação, data, origem, código afetado,
   contexto, decisão, alternativas consideradas e consequências.
2. Numere em sequência (a próxima é a ADR-030) e acrescente a linha na tabela do `README.md` de
   `docs/adr/`.
3. Uma decisão tomada durante a implementação entra como **proposta** e aguarda revisão. Para
   aceitar, troque a situação para `aceita`; para rejeitar, marque `rejeitada` com o motivo.
4. Nunca apague uma ADR. Uma decisão substituída continua no diretório, marcada como tal; mudanças
   posteriores entram como adendo ou atualização datada.
5. Se a decisão muda um documento oficial, atualize a fonte em `docs-src/` e rode `make docs`.

## Versões

A versão segue o formato `MAJOR.MINOR.PATCH` e precisa ser a mesma em três lugares:

| Arquivo | Campo |
|---|---|
| [`pyproject.toml`](https://github.com/Dracon-46/FalkyriaLumen/blob/main/pyproject.toml) | `version` |
| [`packages/canonico/lumen_canonico/__init__.py`](https://github.com/Dracon-46/FalkyriaLumen/blob/main/packages/canonico/lumen_canonico/__init__.py) | `VERSAO_LUMEN` (vai no User-Agent das coletas) |
| [`packages/portal/package.json`](https://github.com/Dracon-46/FalkyriaLumen/blob/main/packages/portal/package.json) | `version` |

Cada versão tem uma seção no
[`CHANGELOG.md`](https://github.com/Dracon-46/FalkyriaLumen/blob/main/CHANGELOG.md) no formato
`## X.Y.Z — AAAA-MM-DD`, com o que mudou para quem usa e para quem desenvolve e as ADRs citadas. O
fluxo [`release.yml`](https://github.com/Dracon-46/FalkyriaLumen/blob/main/.github/workflows/release.yml)
cria a release a cada tag `vX.Y.Z`: confere que a tag bate com as três versões e usa a seção do
CHANGELOG como notas. O portal mostra o CHANGELOG na aba Novidades (`/novidades/`), lido na geração do site;
mudança só no CHANGELOG também publica o portal (`vercel.json` e `portal-pages.yml`). As mudanças que já estão
no ar e ainda não têm versão ficam em `## Não lançado`, no alto.

Versões de contrato são independentes da versão do sistema: `VERSAO_ESQUEMA_FEED` (feeds das
eleições), `VERSAO_ZONAS` (mapa das zonas), `VERSAO_PAINEL` (dados dos painéis) e a versão de cada
regra. Mudança incompatível de contrato sobe a versão dele e atualiza os dois lados no mesmo commit.

## Documentação

- Os `.docx` em `docs/` são gerados por script a partir de `docs-src/`; não edite à mão.
  `make docs` regenera tudo, inclusive o DOC-11 a partir do código.
- Esta Wiki vive em `docs/wiki/` e é publicada pelo fluxo `wiki.yml` a cada mudança na `main`.
  Edite os arquivos no repositório, não pela interface da Wiki.
- Mudança visível para quem usa entra no CHANGELOG; mudança de comando ou configuração entra no
  README e nesta Wiki.
