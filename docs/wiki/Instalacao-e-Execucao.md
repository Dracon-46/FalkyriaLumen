# Instalação e execução

## Pré-requisitos

| Ferramenta | Versão | Onde está exigida |
|---|---|---|
| Python | 3.11 ou superior | `requires-python = ">=3.11"` no [`pyproject.toml`](https://github.com/Dracon-46/FalkyriaLumen/blob/main/pyproject.toml); a CI testa 3.11, 3.12 e 3.13, e os fluxos de carga usam 3.12 |
| Node.js | 20.9 ou superior | `engines.node = ">=20.9.0"` em [`packages/portal/package.json`](https://github.com/Dracon-46/FalkyriaLumen/blob/main/packages/portal/package.json); a CI e o `portal-pages` usam Node 22 |
| Docker com Compose | — | Só para o ambiente local com PostgreSQL e MinIO (`make ambiente`) |
| `make` | — | Opcional: os alvos do `Makefile` são atalhos dos comandos abaixo |

Node só é necessário para o portal e para gerar os `.docx`. O núcleo em Python não tem dependências
de execução ([ADR-015](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-015.md)).

## Instalação

```bash
git clone https://github.com/Dracon-46/FalkyriaLumen.git
cd FalkyriaLumen
python -m pip install -e ".[dev,analitico]"   # pacotes, comando `lumen`, pytest, ruff e DuckDB
```

`make instalar` faz o mesmo. Para só usar a aba Eleições, `python -m pip install -e .` basta.

## Configuração

Copie [`lumen.toml.exemplo`](https://github.com/Dracon-46/FalkyriaLumen/blob/main/lumen.toml.exemplo)
para `lumen.toml` e preencha o contato em `[coleta]`. O contato vai no User-Agent de toda
requisição (RF-CO-09): sem ele, os comandos que acessam a rede recusam rodar. O `lumen.toml` está no
`.gitignore` e nunca vai para o repositório; chaves de acesso nunca ficam nele, só em variáveis de
ambiente. Todas as chaves e variáveis estão em [[Configuração e variáveis|Configuracao-e-Variaveis]].

```toml
[coleta]
contato = "seu-email@exemplo.org"

[dados]
raiz = "dados"     # bronze/ e silver/ ficam aqui
```

## Pipeline de contratações

```bash
lumen coletar pncp_contratacoes --de 2026-09-01 --modalidades 8
lumen coletar ibge_localidades --de 2026-10-05
lumen coletar siconfi_extrato --de 2026-10-05 --entes 3550308 --exercicio 2025
lumen normalizar                 # bronze → silver, idempotente
lumen bronze verificar           # reconfere o hash de toda a prova
```

- A prova fica em `<raiz>/bronze/` e a silver em `<raiz>/silver/`. As duas pastas estão fora do Git.
- `lumen normalizar` pode ser repetido: reprocessar o mesmo artefato produz os mesmos bytes.
- `lumen -v ...` mostra cada tentativa com erro, com status e URL.
- Para consultar a silver com o DuckDB, veja a macro em
  [`silver_consolidada.sql`](https://github.com/Dracon-46/FalkyriaLumen/blob/main/packages/normalizacao/sql/silver_consolidada.sql).

As fontes disponíveis em `lumen coletar` estão em [[APIs e contratos|APIs-e-Contratos]].

## Aba Eleições

Tudo num comando, retomável:

```bash
lumen eleicoes preparar --servir
```

O comando instala o mapa e o cadastro de municípios (que vêm com o Lumen), gera o portal (`npm ci` e
`npm run build`, quando faltam ou o código mudou), sobe o servidor local e abre o navegador em
`http://127.0.0.1:8080/eleicoes/` antes de a carga terminar. Cada eleição aparece assim que fica
pronta. A primeira vez baixa tudo: o sistema de resultados do TSE para a eleição corrente, as
eleições de 1933 a 1990 (só por estado, como o TSE publica), os dados abertos de 1994 a 2026 e os
locais de votação para o mapa das zonas. São vários GB e algumas horas; pode interromper e rodar de
novo, porque o que já foi feito não é refeito (registro em `<estado>/preparar.json`).

Opções úteis de `preparar`:

| Opção | Efeito |
|---|---|
| `--anos 2024,2022` | Só esses anos dos dados abertos |
| `--sem-ao-vivo` | Não coleta o sistema de resultados |
| `--sem-historico` | Não baixa os dados abertos |
| `--sem-zonas` | Não baixa os locais de votação |
| `--sem-portal` | Não gera o portal |
| `--sem-navegador` | Com `--servir`, não abre o navegador |
| `--atualizar` | Consulta a fonte e reprocessa o que mudou |
| `--refazer` | Ignora o registro do que já foi feito |
| `--apagar-zips` | Apaga os ZIPs de cada ano depois de processado (pouco disco) |
| `--nuvem`, `--limite-minutos N` | Publica no bucket e para antes do prazo; usado no GitHub Actions |

Para a carga completa, aponte `[eleicoes].saida` para um diretório fora do portal (o exemplo sugere
`dados/eleicoes/feeds`); `preparar --servir` e `lumen eleicoes servir` entregam site e feeds na mesma
porta.

Sem rede, a amostra gera feeds de exemplo a partir das fixtures (alguns estados e municípios, e
1945, 1950 e 1989, com o mapa):

```bash
python -m lumen_eleicoes --saida packages/portal/public/dados/eleicoes amostra
```

Outros comandos da aba estão em [[APIs e contratos|APIs-e-Contratos]].

### No Windows

1. Instale o Python 3.11 ou superior e, para o portal, o Node.js 20.9 ou superior.
2. Copie `lumen.toml.exemplo` para `lumen.toml` e preencha o contato em `[coleta]`.
3. Dê dois cliques em
   [`preparar.cmd`](https://github.com/Dracon-46/FalkyriaLumen/blob/main/preparar.cmd).

O script cria o ambiente Python em `.venv`, instala o Lumen e roda
`python -m lumen_eleicoes preparar --servir`. Sem o `lumen.toml`, ele avisa e para antes de qualquer
download. Sem o Node.js, os dados são carregados, mas o portal não é gerado. Opções extras vão
direto para o comando, por exemplo `preparar.cmd --anos 2024,2022` ou `preparar.cmd --sem-ao-vivo`.

## Portal em desenvolvimento

```bash
cd packages/portal
npm ci
npm run dados:amostra   # feeds de exemplo a partir das fixtures (precisa do Python do Lumen)
npm run dev             # http://localhost:3000/eleicoes/
```

Sem a amostra, a aba mostra "Nenhuma eleição foi publicada neste servidor". As áreas Contratações e
Conformidade leem os dados publicados no GitHub Pages
(`https://dracon-46.github.io/FalkyriaLumen/`), salvo se `NEXT_PUBLIC_DADOS_PAINEL` apontar para
outro lugar.

Verificação e build:

```bash
npm run verificar   # TypeScript estrito + testes (vitest)
npm run build       # gera out/, pronto para qualquer servidor de arquivos
```

Para servir o site gerado com feeds de outro diretório:
`lumen eleicoes servir --site packages/portal/out` (porta 8080). Para testar contra um bucket
publicado: `NEXT_PUBLIC_DADOS_ELEICOES=<endereço público do bucket> npm run dev` (o bucket precisa
liberar `http://localhost:3000` no CORS, quando for o R2).

Na raiz, `make portal` roda `npm ci`, `npm run verificar` e `npm run build`.

## Painéis localmente

```bash
lumen painel cadastro --estado estado/
lumen painel contratacoes --estado estado/ --ultimos 3
lumen painel conformidade --estado estado/ --ufs RS,SC
lumen painel publicar --estado estado/ --saida site/
```

## Referência de mercado (regra A-05)

Roda em modo silencioso e só grava um relatório interno em `dados/mercado/relatorio/`:

```bash
lumen coletar pncp_contratacoes --de 2026-05-04 --ate 2026-05-15 --modalidades 6,8
lumen coletar ibge_localidades --de 2026-10-09
lumen normalizar
lumen coletar pncp_itens --de 2026-05-04 --ate 2026-05-15 --objeto "combust|gasolina|diesel|etanol|glp"
lumen normalizar --fontes pncp_itens
lumen mercado anp baixar --semestres 2026-1 --series ca,glp
lumen mercado comparar --de 2026-05-04 --ate 2026-05-15
```

O varejo só funciona com a variável `LUMEN_ML_TOKEN`: sem credencial, a busca do Mercado Livre
responde 403.

## Ambiente local com banco e S3

```bash
make ambiente   # docker compose -f infra/docker-compose.yml up -d
make banco      # testes da migração contra o PostgreSQL do ambiente
```

Ver [[Banco de dados|Banco-de-Dados]].

## Documentação

```bash
make docs                       # referência do código (DOC-11) e todos os .docx em docs/
cd docs-src && npm run diagrams # PNGs a partir dos .mmd (requer mermaid-cli e Chromium)
```

## Problemas comuns

- **"defina o contato da coleta"**: falta `[coleta].contato` no `lumen.toml` ou `LUMEN_CONTATO`.
- **Malhas do IBGE com erro de certificado**: o servidor de malhas envia só o certificado final, sem
  o intermediário; `lumen eleicoes mapas` falha numa máquina sem o intermediário instalado
  ([ADR-029](https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-029.md)). As malhas
  e os contornos finos já vêm com o Lumen.
- **Publicação no Supabase recusada**: o endpoint do Supabase exige a região do projeto em
  `[publicacao].regiao` ou `LUMEN_PUBLICACAO_REGIAO`; `auto` é recusado.
