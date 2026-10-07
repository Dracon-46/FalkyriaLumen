# Portal do Lumen

Site estático em Next.js (exportação estática, sem servidor Node em
produção). Hoje tem a aba **Eleições**; Contratações e Conformidade entram nas
próximas fases do roteiro (DOC-10).

## Para ver o site com todos os dados

Na raiz do repositório, `lumen eleicoes preparar --servir` (no Windows, dois
cliques em `preparar.cmd`): instala o mapa, gera este portal, carrega as
eleições de 1933 a 2026 e abre o navegador. Ver o README da raiz.

## Desenvolvimento

Requer Node 20.9 ou superior.

```bash
cd packages/portal
npm ci
npm run dados:amostra   # feeds de exemplo a partir das fixtures (precisa do Python do Lumen)
npm run dev             # http://localhost:3000/eleicoes/
```

Sem a amostra, a aba mostra "Nenhuma eleição foi publicada neste servidor".
A amostra já traz o mapa e o cadastro de municípios que vêm com o Lumen
(`packages/eleicoes/lumen_eleicoes/dados`), além de três eleições anteriores a
1994 (1945, 1950 e 1989), publicadas só por UF.

## Verificação e build

```bash
npm run verificar   # TypeScript estrito + testes (vitest)
npm run build       # gera out/, pronto para qualquer servidor de arquivos
```

Para servir o site gerado junto com feeds de outro diretório:
`lumen eleicoes servir --site packages/portal/out` (porta 8080).

## Organização

```
src/app/                    páginas (layout, início, eleições, áreas em construção)
src/componentes/            cabeçalho e rodapé
src/componentes/eleicoes/   painel, mapa, candidatos, panorama, evolução, busca, faixas
src/lib/                    tipos do contrato, validação, acesso aos feeds, TopoJSON,
                            formato pt-BR, cores, busca, URL, regras de navegação,
                            zoom do mapa (zoom.ts) e área do mapa ↔ parte do feed (areas.ts)
src/lib/__testes__/         testes de unidade; leem a amostra gerada pelo Python
```

Regras que valem para todo o código daqui:

- O portal **nunca** chama o TSE nem o IBGE: lê só os feeds (princípio P6).
- Todo texto em `src/` passa pelo verificador de vocabulário controlado
  (`ferramentas/lint-vocabulario`), como o resto do texto público do Lumen.
- Cor identifica candidato pela ordem de votação, nunca o partido (ADR-020).
- Feed com versão desconhecida é recusado (`src/lib/validacao.ts`).
- Eleição com `municipios: false` no índice (1933 a 1990) não tem mapa por
  município: na UF, a tela mostra o resultado do estado e uma nota; a busca
  por município leva ao estado. UFs da época sem área no mapa atual
  (Guanabara, o Distrito Federal antes de 1960, territórios extintos, o
  exterior) aparecem como botões abaixo do mapa.
- O mapa aproxima pelos botões + e −, por Ctrl (⌘) + rolagem, pela pinça no
  trackpad e por dois dedos na tela de toque; aproximado, arrasta. A rolagem
  simples continua rolando a página.

Configuração de build: `NEXT_PUBLIC_DADOS_ELEICOES` muda a base dos feeds
(padrão `/dados/eleicoes`), para quando os dados ficam numa CDN separada.

## Publicação

O fluxo `.github/workflows/portal-pages.yml` gera este portal com
`NEXT_PUBLIC_DADOS_ELEICOES` apontando para o bucket público do Cloudflare R2
(variável `LUMEN_URL_FEEDS` do repositório) e publica `out/` no Cloudflare
Pages a cada mudança em `packages/portal` na main (ADR-026). O bucket precisa
liberar leitura (CORS, GET e HEAD) para o endereço do Pages; o passo a passo
está no README da raiz e no DOC-12, seção 9.5. Para testar localmente contra o
bucket:

```bash
NEXT_PUBLIC_DADOS_ELEICOES=https://pub-xxxx.r2.dev npm run dev
```

(com `http://localhost:3000` na regra de CORS do bucket).
