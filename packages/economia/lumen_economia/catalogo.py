"""Catálogo dos indicadores da área Economia e Contas Públicas.

Cada série tem o código no SGS do Banco Central e o nome oficial, conferido no catálogo de dados abertos do
BC (``dadosabertos.bcb.gov.br``) ou, para as séries que o IBGE produz e o BC replica, na tabela do SIDRA de
onde vêm. Os derivados são contas sobre as séries, com a conta escrita em ``definicao``.

Regras que valem para todos (ADR-033):

- **Ausente não é zero.** Mês sem observação fica fora da série; um acumulado que precisa de 12 meses só
  existe quando os 12 estão lá.
- **Unidade e conceito explícitos.** Dívida bruta do governo geral e dívida líquida do setor público são
  medidas diferentes; percentual do PIB, percentual ao mês e reais correntes não se misturam.
- **O sinal da NFSP.** Na necessidade de financiamento do setor público, valor positivo é déficit e valor
  negativo é superávit.

``agregacao`` diz como o indicador se resume num período escolhido no portal: ``variacao_mensal`` (taxa do
mês, que se acumula: IPCA, INPC, Selic do mês), ``variacao_anual`` (taxa do ano, que também se acumula: PIB
real) e ``nivel`` (um estado num momento, comparado do início ao fim do período: dívida, resultado em 12
meses, índices).

**Espelho.** O SGS fica atrás de um firewall que às vezes recusa as requisições vindas de servidores em nuvem
(em 18/10/2026 recusou as 11 séries no fluxo diário). Para as séries que o Ipeadata (Ipea) republica com os
mesmos valores, ``espelho`` é o código lá: a coleta usa o espelho só quando o SGS falha, e diz que usou. Cada
espelho foi conferido valor a valor contra o SGS (2024 e 2025; o PIB real, de 2015 a 2025, com as duas casas
do SGS) em 19/10/2026; os que divergem (o Ipeadata guarda outra revisão do PIB mensal e do IBC-Br, e não
tem a dívida bruta nem a líquida total) ficam sem espelho.
"""

from __future__ import annotations

from dataclasses import dataclass, field

FONTE_SGS = "Banco Central do Brasil, Sistema Gerenciador de Séries Temporais (SGS)"
FONTE_IPEADATA = "Ipeadata (Ipea), que republica a série do Banco Central ou do IBGE"


def url_sgs(codigo: int) -> str:
    """Endereço público da série no SGS, em JSON (o mesmo que a coleta usa)."""
    return f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados?formato=json"


def url_ipeadata(codigo: str) -> str:
    """Endereço da série no Ipeadata (OData), em JSON."""
    return f"http://www.ipeadata.gov.br/api/odata4/ValoresSerie(SERCODIGO='{codigo}')"


@dataclass(frozen=True)
class Serie:
    """Uma série coletada do SGS e como ela aparece no portal."""

    id: str
    codigo: int
    nome: str                       # curto, para o portal
    nome_oficial: str               # como a fonte chama a série
    grupo: str
    unidade: str                    # "% ao mês", "% do PIB", "R$ milhões correntes", "índice"
    periodicidade: str              # "mensal" ou "anual"
    definicao: str
    fonte_primaria: str = FONTE_SGS
    leitura: str | None = None      # como ler o sinal ou o valor, quando não é óbvio
    limitacoes: tuple[str, ...] = field(default_factory=tuple)
    parcial_no_mes_corrente: bool = False   # o SGS publica o mês em curso acumulado até o dia
    agregacao: str = "nivel"                # nivel, variacao_mensal ou variacao_anual
    espelho: str | None = None              # código no Ipeadata, usado só quando o SGS falha
    espelho_casas: int | None = None        # casas decimais do SGS, quando o espelho publica mais


@dataclass(frozen=True)
class Derivado:
    """Um indicador calculado a partir das séries, com a conta descrita."""

    id: str
    nome: str
    grupo: str
    unidade: str
    periodicidade: str
    definicao: str
    usa: tuple[str, ...]
    leitura: str | None = None
    limitacoes: tuple[str, ...] = field(default_factory=tuple)
    agregacao: str = "nivel"


GRUPOS = (
    ("inflacao", "Inflação e poder de compra"),
    ("juros", "Juros"),
    ("divida", "Dívida pública"),
    ("fiscal", "Resultado fiscal"),
    ("atividade", "Atividade econômica"),
)

SERIES: tuple[Serie, ...] = (
    Serie("ipca", 433, "IPCA no mês", "IPCA — variação mensal", "inflacao", "% no mês", "mensal",
          "Variação dos preços ao consumidor das famílias com renda de 1 a 40 salários mínimos, nas regiões "
          "metropolitanas e capitais pesquisadas. É o índice da meta de inflação.",
          fonte_primaria="IBGE, Sistema Nacional de Índices de Preços ao Consumidor (SIDRA, tabela 1737, "
                         "variável 63), replicado no SGS do Banco Central",
          leitura="Inflação menor não é queda de preços: com variação positiva, os preços sobem, só que mais "
                  "devagar. Queda generalizada de preços é deflação (variação negativa).",
          agregacao="variacao_mensal", espelho="PRECOS12_IPCAG12"),
    Serie("inpc", 188, "INPC no mês", "INPC — variação mensal", "inflacao", "% no mês", "mensal",
          "Variação dos preços ao consumidor das famílias com renda de 1 a 5 salários mínimos. É o índice "
          "usado na correção do salário mínimo e de benefícios.",
          fonte_primaria="IBGE, Sistema Nacional de Índices de Preços ao Consumidor (SIDRA, tabela 1736, "
                         "variável 44), replicado no SGS do Banco Central",
          agregacao="variacao_mensal", espelho="PRECOS12_INPCBR12"),
    Serie("selic_mes", 4390, "Selic no mês", "Taxa de juros - Selic acumulada no mês", "juros", "% no mês",
          "mensal", "Taxa média dos financiamentos diários com títulos públicos federais no Selic, acumulada no "
                    "mês. É a taxa que a meta do Copom orienta.",
          limitacoes=("O mês em curso fica de fora até fechar: o SGS o publica acumulado só até o dia.",),
          parcial_no_mes_corrente=True, agregacao="variacao_mensal", espelho="BM12_TJOVER12"),
    Serie("selic_anualizada", 4189, "Selic anualizada", "Taxa de juros - Selic acumulada no mês anualizada base "
          "252", "juros", "% ao ano", "mensal",
          "A Selic do mês expressa ao ano (252 dias úteis), para comparar com a meta e com outras taxas anuais.",
          limitacoes=("O mês em curso fica de fora até fechar.",), parcial_no_mes_corrente=True),
    Serie("divida_bruta", 13762, "Dívida bruta do governo geral",
          "Dívida bruta do governo geral (% PIB) - Metodologia utilizada a partir de 2008", "divida", "% do PIB",
          "mensal",
          "Dívida do governo federal, dos governos estaduais e municipais e do INSS com o setor privado, o "
          "setor público financeiro, o Banco Central e o resto do mundo, em proporção do PIB dos últimos 12 meses.",
          limitacoes=("Série iniciada em dezembro de 2006 com a metodologia de 2008; a anterior (código 4537) "
                      "não é comparável.", "Não inclui o Banco Central nem as empresas estatais.")),
    Serie("divida_liquida", 4513, "Dívida líquida do setor público",
          "Dívida Líquida do Setor Público (% PIB) - Total - Setor público consolidado", "divida", "% do PIB",
          "mensal",
          "Dívida do setor público consolidado (governos, Banco Central e estatais, exceto Petrobras e Eletrobras) "
          "descontados os seus ativos financeiros, como as reservas internacionais, em proporção do PIB.",
          leitura="Pode cair quando o real se desvaloriza, porque as reservas em dólar valem mais em reais.",
          limitacoes=("Não é a mesma medida da dívida bruta: as duas não se somam nem se comparam diretamente.",)),
    Serie("primario_12m", 5793, "Resultado primário (12 meses)",
          "NFSP sem desvalorização cambial (% PIB) - Fluxo acumulado em 12 meses - Resultado primário - Total - "
          "Setor público consolidado", "fiscal", "% do PIB", "mensal",
          "Receitas menos despesas do setor público consolidado, sem os juros, acumuladas em 12 meses, em "
          "proporção do PIB. Apurado pelo Banco Central pela variação da dívida (abaixo da linha).",
          leitura="É a necessidade de financiamento: positivo é déficit primário; negativo, superávit.",
          limitacoes=("A apuração abaixo da linha do Banco Central pode diferir do resultado do Tesouro (acima da "
                      "linha) por discrepância estatística.",),
          espelho="BM12_NFSPPYS12"),
    Serie("nominal_12m", 5727, "Resultado nominal (12 meses)",
          "NFSP sem desvalorização cambial (% PIB) - Fluxo acumulado em 12 meses - Resultado nominal - Total - "
          "Setor público consolidado", "fiscal", "% do PIB", "mensal",
          "O resultado primário mais os juros nominais apropriados da dívida, acumulados em 12 meses, em "
          "proporção do PIB.",
          leitura="Positivo é déficit nominal: quanto o setor público precisou financiar, juros incluídos.",
          espelho="BM12_NFSPNYS12"),
    Serie("pib_12m", 4382, "PIB em 12 meses", "PIB acumulado dos últimos 12 meses - Valores correntes",
          "atividade", "R$ milhões correntes", "mensal",
          "Produto Interno Bruto acumulado nos 12 meses até o mês, em reais da época. É o denominador das séries "
          "em % do PIB.",
          fonte_primaria="IBGE, Contas Nacionais Trimestrais, com a estimativa mensal do Banco Central (SGS)",
          limitacoes=("Valores correntes: a variação inclui a inflação. Para o crescimento real, use a variação "
                      "real anual.", "Os meses mais recentes são estimativa e mudam com as revisões do IBGE.")),
    Serie("pib_real", 7326, "PIB: variação real no ano", "Produto Interno Bruto - taxa de variação real no ano",
          "atividade", "% no ano", "anual",
          "Crescimento do PIB em volume (descontada a variação de preços) em relação ao ano anterior.",
          fonte_primaria="IBGE, Contas Nacionais, replicado no SGS do Banco Central",
          limitacoes=("O IBGE revisa os anos recentes; o valor de um ano pode mudar depois de publicado.",),
          agregacao="variacao_anual", espelho="SCN10_PIBG10", espelho_casas=2),
    Serie("ibc_br", 24363, "IBC-Br", "Índice de Atividade Econômica do Banco Central (IBC-Br)", "atividade",
          "índice (2002 = 100)", "mensal",
          "Indicador mensal da atividade econômica, calculado pelo Banco Central como antecedente do PIB.",
          limitacoes=("Série sem ajuste sazonal: compare o mesmo mês de anos diferentes, não meses vizinhos.",)),
)

DERIVADOS: tuple[Derivado, ...] = (
    Derivado("ipca_12m", "IPCA em 12 meses", "inflacao", "% em 12 meses", "mensal",
             "Variação acumulada nos 12 meses até o mês: produto de (1 + variação mensal) nos 12 meses, menos 1.",
             ("ipca",), leitura="É a medida comparada com a meta de inflação."),
    Derivado("ipca_ano", "IPCA no ano", "inflacao", "% no ano", "mensal",
             "Variação acumulada de janeiro até o mês, no mesmo ano.", ("ipca",)),
    Derivado("inpc_12m", "INPC em 12 meses", "inflacao", "% em 12 meses", "mensal",
             "Variação acumulada nos 12 meses até o mês, como no IPCA.", ("inpc",)),
    Derivado("selic_12m", "Selic em 12 meses", "juros", "% em 12 meses", "mensal",
             "Selic acumulada nos 12 meses até o mês: produto de (1 + taxa do mês) nos 12 meses, menos 1.",
             ("selic_mes",)),
    Derivado("juro_real_12m", "Juro real (ex post, 12 meses)", "juros", "% em 12 meses", "mensal",
             "Selic acumulada em 12 meses descontado o IPCA dos mesmos 12 meses: (1 + Selic) / (1 + IPCA) - 1.",
             ("selic_mes", "ipca"),
             leitura="É o juro real que de fato ocorreu (ex post), e não o esperado pelo mercado (ex ante).",
             limitacoes=("Usa a Selic, não o custo médio da dívida pública.",)),
    Derivado("juros_nominais_12m", "Juros nominais da dívida (12 meses)", "fiscal", "% do PIB", "mensal",
             "Resultado nominal menos resultado primário, nos mesmos 12 meses: na NFSP, o nominal é o primário "
             "mais os juros nominais.", ("nominal_12m", "primario_12m"),
             leitura="Positivo é o custo dos juros apropriados no período, em proporção do PIB."),
)


def series_por_id() -> dict[str, Serie]:
    """As séries do catálogo pelo identificador."""
    return {s.id: s for s in SERIES}
