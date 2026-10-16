# Política de segurança

## Como relatar uma vulnerabilidade

Não abra issue pública para relatar uma falha de segurança.

Use o relato privado do GitHub: na aba **Security** do repositório, clique em
**Report a vulnerability** (GitHub Security Advisories). O relato fica visível só para quem mantém
o projeto até a correção.

Se o botão não aparecer, abra uma issue pedindo um canal privado, sem descrever a falha, e mencione
@Dracon-46.

Inclua no relato, quando possível:

- o componente afetado (pacote, fluxo do GitHub Actions, portal, feed publicado);
- os passos para reproduzir e o impacto esperado;
- a versão ou o commit em que a falha foi observada.

Não acesse, altere ou apague dados de terceiros para demonstrar a falha, e não faça testes que
degradem os serviços públicos de onde o Lumen coleta dados (princípio P6 do DOC-01).

## Escopo

| Dentro do escopo | Exemplos |
|---|---|
| Código deste repositório | Pacotes Python em `packages/`, portal Next.js, ferramentas, migrações SQL |
| Fluxos do GitHub Actions | `.github/workflows/*.yml`: permissões, uso de segredos, entradas dos fluxos manuais |
| Feeds e dados publicados | Feeds das eleições no bucket público, dados dos painéis no GitHub Pages, anexos da versão `painel-estado` |
| Privacidade | Exposição de documento de pessoa física ou de dado pessoal que deveria estar mascarado (RNF-19, RNF-20) |
| Integridade da prova | Qualquer forma de alterar ou apagar o que a camada bronze ou as tabelas somente-anexação deveriam proteger |

Fora do escopo: falhas nos serviços de terceiros que o Lumen usa (PNCP, SICONFI, IBGE, TSE, ANP,
GitHub, Supabase, Cloudflare, Vercel), que devem ser relatadas aos respectivos responsáveis.

Número divergente da fonte oficial não é falha de segurança: use o formulário de issue
"Dado divergente da fonte oficial".

## Segredos

Nenhum segredo vai para o repositório (RNF-13):

- chaves de acesso ficam só em variáveis de ambiente e nos segredos do GitHub Actions, nunca no
  código nem no `lumen.toml`, que está no `.gitignore`;
- as únicas credenciais versionadas são as do ambiente local de desenvolvimento em
  `infra/docker-compose.yml`, de propósito, e não valem fora da máquina local;
- logs nunca registram token, credencial, documento de pessoa física sem máscara ou conteúdo
  integral de artefato coletado.

Se encontrar um segredo real no histórico do repositório, relate pelo canal privado acima.

## Correções

As correções entram na `main` por pull request e ficam registradas no `CHANGELOG.md`.
