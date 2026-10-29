# Fixtures do TSE

Capturadas em **05/10/2026** do sistema de divulgação de resultados
(`https://resultados.tse.jus.br/oficial/`) e do portal de dados abertos
(`https://cdn.tse.jus.br/estatistica/sead/`). Os números são os oficiais
publicados pelo TSE no momento da captura.

| Arquivo | O que é | Corte |
|---|---|---|
| `ele-c_recorte.json` | catálogo de eleições do sistema de resultados | só pleitos 2024 e 2026; consultas populares reduzidas; `dtlim` do pleito 2026 não capturado |
| `br-c0001-e006257-u.json` | Presidente, 1º turno 2026, Brasil | inteiro (soma dos votos = votos válidos) |
| `sp-c0003-e006259-u.json` | Governador SP, 1º turno 2026 | inteiro |
| `sp-c0005-e006259-u_recorte.json` | Senador SP (duas vagas) | 3 das agremiações |
| `sp-c0006-e006259-u_recorte.json` | Deputado Federal SP | 2 agremiações, 3 candidatos cada |
| `sp-c0001-e006257-u.json` | Presidente, 1º turno 2026, São Paulo (UF) | inteiro; traz o bloco `fed` (federações) que o do Brasil não traz |
| `sp61000-c0001-e006257-u.json` | Presidente num município de SP | inteiro |
| `sp71072-c0011-e000619-u.json` | Prefeito de São Paulo, 1º turno 2024 | inteiro; tem candidatura com voto anulado e "2º turno" |
| `mun-e006257-cm_recorte.json` | municípios (código TSE → IBGE) | 3 de AC, 3 do exterior, 3 de SP |
| `br-e006257-ab_recorte.json` | andamento por UF | AC, SP e exterior |
| `sp-e006257-ab_recorte.json` | andamento por município de SP | 3 municípios + a UF |
| `dados_abertos/*_inicio.csv` | primeiras linhas de três arquivos dos dados abertos | cabeçalho + 2 ou 3 linhas, Latin-1, separador `;` |

### Eleições de 1933 a 1990 (`dados_abertos_uf/`)

Linhas reais, sem nenhuma alteração (bytes Latin-1 como publicados), dos
arquivos por UF baixados em **06/10/2026** de
`https://cdn.tse.jus.br/estatistica/sead/odsele/<conjunto>/<conjunto>_<ano>.zip`
(em 1933 e 1934, `<conjunto>_<ano>_br.zip`).
Os testes montam os ZIPs com elas (`packages/eleicoes/testes/conftest.py`).
Cada recorte foi escolhido por uma particularidade da época:

| Arquivo | Linhas mantidas | Por quê |
|---|---|---|
| `votacao_candidato_uf_1933_br_recorte.txt` | cabeçalho + Acre | 1933 tem cabeçalho; dois "turnos" de apuração; situações "ELEITO 1º TURNO QE" e "ELEITO 2º TURNO"; candidatos sem número |
| `detalhe_votacao_uf_1933_br_recorte.txt` | cabeçalho + Acre | turno não registrado (`-3`), que vale para as duas etapas |
| `votacao_partido_uf_1933_br_recorte.txt` | cabeçalho + Acre | grupos de eleitores sem sigla e sem votação registrada: as agremiações saem da soma dos candidatos |
| `votacao_candidato_uf_1945_recorte.txt` | Fernando de Noronha, Iguaçu, Ponta Porã, Guaporé, Rio Branco e Presidente no Distrito Federal | territórios extintos ou renomeados; o Distrito Federal era a cidade do Rio de Janeiro |
| `detalhe_votacao_uf_1945_recorte.txt` | Presidente no Distrito Federal | os territórios não têm detalhe na fonte |
| `votacao_candidato_uf_1950_recorte.txt` | Presidente e Vice-presidente em AC, GP e RB | vice votado em separado; soma nacional de candidatos sem número |
| `detalhe_votacao_uf_1950_recorte.txt` | as mesmas UFs e cargos | |
| `votacao_candidato_uf_1962_recorte.txt` | Senador na Guanabara | UF extinta, fora do mapa atual |
| `detalhe_votacao_uf_1962_recorte.txt` | idem | |
| `votacao_candidato_uf_1986_recorte.txt` | Amapá, todas as linhas | linhas sem nome do candidato (há na fonte) |
| `detalhe_votacao_uf_1986_recorte.txt` | Amapá | votos de legenda |
| `votacao_partido_uf_1986_recorte.txt` | Amapá | coligação e partido isolado |
| `votacao_candidato_uf_1989_recorte.txt` | Presidente em AC, DF e exterior, dois turnos | número de urna; exterior (`ZZ`) |
| `detalhe_votacao_uf_1989_recorte.txt` | idem | o arquivo por partido de 1989 não existe na fonte |

O sistema de resultados só mantém as eleições cujo prazo de divulgação
(`dtlim`) não venceu — em 05/10/2026, os ciclos 2024 e 2026. Eleições
anteriores vêm dos dados abertos: de 1994 em diante, por município
(`votacao_candidato_munzona_AAAA.zip` e afins, `lumen_eleicoes.dados_abertos`);
de 1933 a 1990, só por UF (`votacao_candidato_uf_AAAA.zip` e afins,
`lumen_eleicoes.antigas`).

Os arquivos foram gravados em JSON compacto; o TSE publica com espaços e
quebras de linha. O conteúdo é o mesmo campo a campo.

Usos além dos testes: `lumen eleicoes amostra` gera, a partir desta pasta,
os feeds de exemplo do portal (`testes/fixtures/eleicoes_feed`), e
`lumen eleicoes simular` serve estes arquivos como uma apuração em andamento.

### Locais de votação (`locais_votacao/`)

Linhas reais, sem nenhuma alteração (bytes Latin-1 como publicados), de
`https://cdn.tse.jus.br/estatistica/sead/odsele/eleitorado_locais_votacao/eleitorado_local_votacao_<ano>.zip`,
baixados em **15/10/2026**. Uma linha por seção; os testes de `zonas.py` montam
os ZIPs com elas.

| Arquivo | Linhas mantidas | Por quê |
|---|---|---|
| `eleitorado_local_votacao_2026_SP_recorte.csv` | cabeçalho; São Caetano do Sul, a primeira seção de cada um dos 31 locais (zonas 166 e 269), mais uma segunda seção de um local e uma linha do 2º turno; duas linhas de Bragança Paulista (zonas 27 e 298) | município pequeno com duas zonas; em 2026 a coordenada vem com vírgula decimal; o mesmo prédio é local das duas zonas; o 2º turno repete as seções |
| `eleitorado_local_votacao_2024_recorte.csv` | cabeçalho; duas linhas de São Caetano do Sul | até 2024 a coordenada vem com ponto decimal; local sem coordenada (`-1`) |

### Boletins de urna (`horarios/`)

Linhas reais, sem nenhuma alteração (bytes Latin-1 como publicados), dos
boletins de urna em tabela do 2º turno de 2026
(`https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2026/buweb/bweb_2t_<UF>_261020260742.zip`),
baixados em **29/10/2026**. São todas as linhas (um cargo e um número votado
por linha) das seções escolhidas; os testes de `horarios.py` as leem direto e
montam um ZIP com elas.

| Arquivo | Linhas mantidas | Por quê |
|---|---|---|
| `bweb_2t_AC_recorte.csv` | cabeçalho; as três primeiras seções de Senador Guiomard (zona 8) | a urna abre às 6h locais (8h de Brasília) e o boletim recebido vem no horário de Brasília |
| `bweb_2t_DF_recorte.csv` | cabeçalho; duas seções de Brasília (zona 17) | horário local igual ao de Brasília; Presidente e Governador na mesma seção |
