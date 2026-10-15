# Referências embutidas da aba Eleições

Arquivos que vêm com o pacote para o mapa e a busca funcionarem sem nenhum
download. `lumen eleicoes preparar` e `lumen eleicoes amostra` copiam tudo
para o diretório dos feeds (`referencias.instalar`), sem sobrescrever o que
já estiver lá.

Nada aqui é editado à mão. Para atualizar, rode `lumen eleicoes municipios`
e `lumen eleicoes mapas` (gravam a versão corrente das fontes no diretório
dos feeds), confira o resultado e copie os arquivos para cá, atualizando
esta tabela.

| Arquivo | Conteúdo | Fonte | Obtido em |
|---|---|---|---|
| `municipios.json` | 5.757 municípios: 5.571 no Brasil, com código IBGE, e 186 cidades do exterior (UF `zz`) | Cadastro de municípios da eleição geral de 2026 no sistema de resultados do TSE, com os nomes da API de localidades do IBGE | 06/10/2026 |
| `geo/br-uf.json` | Brasil, uma geometria por UF | API de malhas v3 do IBGE, qualidade `minima`, TopoJSON | 06/10/2026 |
| `geo/uf-<sigla>-mu.json` | Cada UF, uma geometria por município (27 arquivos, 5.570 municípios) | API de malhas v3 do IBGE, qualidade `minima`, TopoJSON | 06/10/2026 |
| `geo/mu/<código IBGE>.json` | Contorno de cada um dos 191 municípios com mais de uma zona eleitoral em algum ano de 2018 a 2026 (1,5 MB), para o mapa das zonas (ADR-029) | API de malhas v3 do IBGE, qualidade `maxima`, TopoJSON | 15/10/2026 |

## Endereços

- Cadastro do TSE: `https://resultados.tse.jus.br/oficial/ele2026/6257/config/mun-e006257-cm.json`
  (gerado pelo TSE em 02/10/2026 às 18:30:22; SHA-256 do publicado
  `dd8dcad73361a481b5110098ec812c1bda3f7acc12774fe6b0cf0be10ed2132b`).
- Nomes do IBGE: `https://servicodados.ibge.gov.br/api/v1/localidades/municipios`
  (5.571 municípios).
- Malha do Brasil: `https://servicodados.ibge.gov.br/api/v3/malhas/paises/BR?formato=application/json&intrarregiao=UF&qualidade=minima`
- Malha de cada UF: `https://servicodados.ibge.gov.br/api/v3/malhas/estados/<código IBGE da UF>?formato=application/json&intrarregiao=municipio&qualidade=minima`
- Contorno de um município: `https://servicodados.ibge.gov.br/api/v3/malhas/municipios/<código IBGE>?formato=application/json&qualidade=maxima`
  (`geo.baixar_contornos`; a lista é a dos índices `geo/zonas-<ano>/indice.json` de 2018 a 2026).
  O servidor envia só o certificado final, sem o intermediário (Sectigo Public Server Authentication
  CA DV R36); o download de 15/10/2026 completou a cadeia com o intermediário publicado no crt.sh
  (SHA-256 `8C:54:C3:34:B6:6B:A4:E4:26:77:2A:F4:A3:F9:13:6C:19:A1:AE:C7:29:FD:B2:8C:53:5C:07:A5:A4:EF:22:E0`),
  conferido até a raiz Sectigo Public Server Authentication Root R46.

As malhas são os bytes publicados pelo IBGE, sem alteração, conferidos por
`geo.validar_topojson`. O cadastro é gravado por
`CadastroMunicipios.de_tse(...).gravar(...)` a partir dos dois arquivos acima.

## Limitação conhecida

Boa Esperança do Norte (MT, IBGE 5101837), instalado em 2025, está no
cadastro do TSE e na lista do IBGE, mas ainda não na malha de municípios do
IBGE. Os resultados dele aparecem na lista e na busca; no mapa de Mato
Grosso a área continua dentro da dos municípios de que foi desmembrado.
