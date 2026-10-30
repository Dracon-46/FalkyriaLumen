# Runner no Brasil

Um runner próprio do GitHub Actions num servidor no Brasil, só para o job do TCE-RS do fluxo `tce`. Desde 28/10/2026,
o servidor do TCE-RS recusa os endereços da Vercel (403 do próprio tribunal), e o intermediário em São Paulo
(`infra/proxy-br`) deixou de servir para ele. Do Brasil fora da Vercel/AWS, ele responde: em 30/10/2026, um servidor
comum em São Paulo (AS268581) recebeu 200. A decisão está na [ADR-050](../../docs/adr/ADR-050.md), no adendo de
30/10/2026.

## Como o fluxo usa

- Com a variável `LUMEN_RUNNER_BR` do repositório definida (qualquer valor, por exemplo `1`), o job do RS roda em
  `runs-on: [self-hosted, lumen-br]`, direto, sem o intermediário. Os jobs do PR, de PE e do CE continuam nas
  máquinas do GitHub.
- Sem a variável, nada muda: o job do RS roda no GitHub, pelo intermediário, e falha com 403.
- Se o runner estiver desligado quando o fluxo rodar, o job do RS espera na fila (até 24 horas) e os outros seguem.

## O servidor

Ubuntu 24.04, x64 ou arm64, com 1 GB de memória e 10 GB de disco bastam: o job baixa o estado do release, lê uns 5 MB por ano
do tribunal e sobe o estado de volta, uma vez por dia, em poucos minutos.

- **Oracle Cloud, nível gratuito, região São Paulo (`sa-saopaulo-1`):** sem custo (VM.Standard.E2.1.Micro ou
  A1.Flex). Pede cartão para criar a conta, sem cobrança. A faixa de IP é da Oracle, não da AWS; confirme o acesso
  ao tribunal antes de instalar o runner (abaixo).
- **VPS brasileira** (Hostinger, Locaweb, Magalu Cloud, entre outras): perto de R$ 20 a R$ 40 por mês, IP de
  provedor brasileiro.

Antes de tudo, do próprio servidor:

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://dados.tce.rs.gov.br/dados/auxiliar/orgaos_auditados_rs.csv
```

Tem de voltar `200`. Com `403`, o tribunal também bloqueia aquele provedor: escolha outro.

## Instalação

1. No servidor (Ubuntu 24.04, que o `actions/setup-python` conhece), um usuário só para o runner, sem `sudo`, e o
   `gh`, que o job usa para baixar e subir o estado:
   ```bash
   sudo useradd -m -s /bin/bash runner
   sudo apt-get update && sudo apt-get install -y git curl
   curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
     | sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg
   echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] \
   https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list
   sudo apt-get update && sudo apt-get install -y gh
   ```
2. No GitHub, em Settings → Actions → Runners → New self-hosted runner, escolha Linux e a arquitetura do servidor e
   siga os comandos de download que a página mostra, como o usuário `runner`. No `./config.sh`, use:
   ```bash
   ./config.sh --url https://github.com/Dracon-46/FalkyriaLumen --token <token da página> \
               --name lumen-br --labels lumen-br --unattended
   ```
3. Como serviço, para voltar sozinho depois de reiniciar:
   ```bash
   sudo ./svc.sh install runner && sudo ./svc.sh start
   ```
4. No repositório, em Settings → Secrets and variables → Actions → Variables, crie `LUMEN_RUNNER_BR` = `1`.
5. Dispare o fluxo `tce` à mão e confira o job do RS.

## Segurança

O repositório é público, e um pull request de fora pode trazer um fluxo que peça `self-hosted`.

- Em Settings → Actions → General, em "Fork pull request workflows from outside collaborators", deixe "Require
  approval for all outside collaborators". Nenhum fluxo de PR roda no servidor sem a sua aprovação.
- O servidor serve só para isso: nada de chaves, senhas ou outros serviços nele. O job usa o `GITHUB_TOKEN` da
  execução, que expira no fim dela.
- Para tirar o runner: `sudo ./svc.sh stop && sudo ./svc.sh uninstall && ./config.sh remove --token <token>` e apague
  a variável `LUMEN_RUNNER_BR`.
