# Ambiente local

Fora do ambiente local, `infra/proxy-br` é o intermediário em São Paulo (Vercel) e `infra/runner-br`, o runner
próprio no Brasil para o TCE-RS (ADR-050).

```bash
docker compose -f infra/docker-compose.yml up -d
```

| Serviço | Endereço | Uso |
|---|---|---|
| PostgreSQL 16 | `localhost:5432`, usuário `lumen`, senha `lumen-dev-local` | banco de domínio; a migração `0001_dominio.sql` roda na primeira subida |
| MinIO (S3) | `http://localhost:9000` | camada bronze, bucket `lumen-bronze` com Object Lock |
| Console MinIO | `http://localhost:9001` | inspeção visual dos objetos |

As credenciais são de desenvolvimento e ficam no repositório de propósito.
Fora da máquina local elas vêm de cofre de segredos (RNF-13).

## Usar o bronze no MinIO

```python
from lumen_ingestao.s3 import ClienteS3
from lumen_ingestao.armazem_s3 import ArmazemBronzeObjetos

s3 = ClienteS3(endpoint="http://localhost:9000", bucket="lumen-bronze",
               chave_acesso="lumen", chave_secreta="lumen-dev-local")
armazem = ArmazemBronzeObjetos(s3, retencao_dias=3650)
```

Sem Docker, o pipeline funciona igual com o backend local
(`ArmazemBronzeLocal`), que é o padrão do comando `lumen`.

## Testes contra o banco

```bash
LUMEN_TESTE_PG="postgresql://lumen:lumen-dev-local@localhost:5432/lumen" python -m pytest -m postgres
```

## Zerar tudo

```bash
docker compose -f infra/docker-compose.yml down -v
```

Isso apaga os volumes, inclusive a prova coletada. Só faça em
desenvolvimento.
