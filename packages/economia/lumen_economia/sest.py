"""Estatais federais pelos dados abertos da SEST: cadastro das empresas e o Programa de Dispêndios Globais.

A Secretaria de Coordenação e Governança das Empresas Estatais (SEST, Ministério da Gestão e da Inovação)
publica, em ``gov.br/gestao/.../estatais/transparencia``, arquivos ZIP com CSV (``;``, cp1252):

- **identificação** (``sestidentificacao.zip``): as empresas federais ativas e inativas, com código SIEST,
  sigla, CNPJ, dependência do Tesouro, grupo econômico, capital aberto ou fechado e ministério supervisor;
- **PDG** (``sestpdg.zip``): o Programa de Dispêndios Globais, o orçamento anual das empresas **não
  dependentes** do Tesouro (as que se pagam com receita própria, como os Correios e a Caixa), aprovado por
  decreto, com o realizado acumulado mês a mês, por rubrica (pessoal, materiais, serviços de terceiros,
  tributos, investimentos...).

As empresas dependentes (EBSERH, Embrapa, HCPA...) não estão no PDG: a despesa delas é do Orçamento da
União e aparece no Portal da Transparência. O Lumen guarda do cadastro só dados da empresa (o arquivo
não tem dados de pessoas além do telefone e endereço institucionais, que não são lidos).
"""

from __future__ import annotations

import csv
import io
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from lumen_ingestao.cliente_http import ClienteHttp
from lumen_ingestao.coleta_http import ErroColeta
from lumen_painel.comum import gravar_json, ler_json

BASE = "https://www.gov.br/gestao/pt-br/assuntos/estatais/transparencia"
URL_IDENTIFICACAO = f"{BASE}/sestidentificacao.zip"
URL_PDG = f"{BASE}/sestpdg.zip"
URL_PAGINA = f"{BASE}/dados-abertos"
ARQUIVO_ESTADO = "economia-sest.json.gz"
VERSAO_ESTADO = 1
FONTE_ID = "sest_dados_abertos"
MESES = ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")

COLUNAS_EMPRESA = ("codigo_siest", "sigla", "nome", "dependencia", "grupo_economico", "setor",
                   "capital_aberto_fechado", "natureza_juridica", "segmento", "controle_acionario", "cnpj")
COLUNAS_PDG = ("exercicio", "codigo_siest", "empresa", "rubrica_codigo", "rubrica_nome", "aprovado",
               *(f"realiz. ate {m}" for m in MESES))


class ArquivoSestIlegivel(ValueError):
    """O arquivo da SEST não é o ZIP esperado ou o CSV não tem as colunas esperadas."""


def numero(texto: str) -> float | None:
    """Valor em reais do formato da SEST: ``1.500.002.908``, ``1.234,56``, ``-`` (zero) ou vazio (ausente)."""
    t = (texto or "").strip()
    if not t:
        return None
    if t == "-":
        return 0.0
    negativo = t.startswith("-") or (t.startswith("(") and t.endswith(")"))
    t = t.strip("-()").strip().replace(".", "").replace(",", ".")
    try:
        valor = float(t)
    except ValueError as erro:
        raise ArquivoSestIlegivel(f"valor ilegível: {texto!r}") from erro
    return -valor if negativo else valor


def membro(conteudo: bytes, sufixo: str) -> bytes:
    """O arquivo do ZIP cujo nome termina em ``sufixo`` (os ZIPs da SEST têm uma pasta dentro)."""
    try:
        z = zipfile.ZipFile(io.BytesIO(conteudo))
    except zipfile.BadZipFile as erro:
        raise ArquivoSestIlegivel(f"não é ZIP: {conteudo[:60]!r}") from erro
    nomes = [n for n in z.namelist() if n.endswith(sufixo)]
    if not nomes:
        raise ArquivoSestIlegivel(f"o ZIP não tem *{sufixo} (tem {z.namelist()})")
    return z.read(nomes[0])


def _linhas(conteudo: bytes, obrigatorias: tuple[str, ...]) -> list[dict[str, str]]:
    """Linhas do CSV (cp1252, ``;``), conferindo as colunas."""
    leitor = csv.DictReader(io.StringIO(conteudo.decode("cp1252"), newline=""), delimiter=";")
    campos = [c.strip() for c in leitor.fieldnames or []]
    leitor.fieldnames = campos
    faltando = [c for c in obrigatorias if c not in campos]
    if faltando:
        raise ArquivoSestIlegivel(f"colunas ausentes: {faltando} (cabeçalho: {campos[:8]})")
    return [{k: (v or "").strip() for k, v in r.items() if k is not None} for r in leitor]


def empresas(ativas: bytes, inativas: bytes | None = None) -> dict[str, dict]:
    """O cadastro das empresas por código SIEST, com a situação (ativa ou inativa, e desde quando)."""
    saida = {}
    for conteudo, situacao in ((ativas, "ativa"), (inativas, "inativa")):
        if conteudo is None:
            continue
        for r in _linhas(conteudo, COLUNAS_EMPRESA):
            if not r["codigo_siest"] or r["codigo_siest"] in saida:
                continue
            saida[r["codigo_siest"]] = {
                "sigla": r["sigla"], "nome": r["nome"], "cnpj": r["cnpj"] or None,
                "dependente": r["dependencia"].startswith("Dependente"), "dependencia": r["dependencia"],
                "grupo": None if r["grupo_economico"] in ("", "Sem Grupo Econômico") else r["grupo_economico"],
                "setor": r["setor"], "capital": r["capital_aberto_fechado"], "natureza": r["natureza_juridica"],
                "segmento": r["segmento"], "controle": r["controle_acionario"],
                "ministerio": r.get("ministerio_supervisor") or None, "situacao": situacao,
                "inativa_desde": r.get("data_inativacao") or None,
            }
    return saida


def pdg(conteudo: bytes) -> dict[str, dict]:
    """O PDG por empresa, exercício e rubrica: aprovado, realizado acumulado até o último mês publicado.

    Devolve ``{codigo_siest: {"empresa": sigla, "exercicios": {ano: {rubrica: [aprovado, realizado,
    último mês]}}, "rubricas": {código: nome}}}``. O realizado de cada mês é acumulado no ano, então o do
    último mês com valor é o do ano até ali. Rubrica sem nenhum mês publicado tem realizado ausente.
    """
    saida: dict[str, dict] = {}
    for r in _linhas(conteudo, COLUNAS_PDG):
        meses = [(i + 1, numero(r[f"realiz. ate {m}"])) for i, m in enumerate(MESES)]
        publicados = [(i, v) for i, v in meses if v is not None]
        ultimo = publicados[-1] if publicados else (None, None)
        e = saida.setdefault(r["codigo_siest"], {"empresa": r["empresa"], "exercicios": {}, "rubricas": {}})
        e["empresa"] = r["empresa"]
        e["rubricas"][r["rubrica_codigo"]] = r["rubrica_nome"]
        e["exercicios"].setdefault(r["exercicio"], {})[r["rubrica_codigo"]] = [numero(r["aprovado"]), ultimo[1],
                                                                              ultimo[0]]
    return saida


# ------------------------------------------------------------------------------------------ coleta

@dataclass
class ResumoColetaSest:
    """O que a coleta fez: empresas no cadastro, empresas e exercícios no PDG, falhas."""

    empresas: int = 0
    empresas_pdg: int = 0
    exercicios: list[str] = field(default_factory=list)
    falhas: dict[str, str] = field(default_factory=dict)

    def para_json(self) -> dict:
        """Resumo para imprimir na linha de comando."""
        return {"empresas": self.empresas, "empresas_pdg": self.empresas_pdg, "exercicios": self.exercicios,
                "falhas": self.falhas}


def ler_estado(estado: Path | str) -> dict:
    """O estado gravado, ou um estado vazio na versão atual."""
    caminho = Path(estado) / ARQUIVO_ESTADO
    if not caminho.exists() or caminho.stat().st_size == 0:
        return {"versao": VERSAO_ESTADO, "identificacao": None, "pdg": None}
    dados = ler_json(caminho)
    if dados.get("versao") != VERSAO_ESTADO:
        raise ValueError(f"{caminho}: versão {dados.get('versao')!r} do estado da SEST não suportada")
    return dados


def _baixar(cliente: ClienteHttp, url: str) -> bytes:
    """O ZIP inteiro (os da SEST têm poucos megabytes)."""
    artefato = cliente.obter(url, {"Accept": "application/zip"})
    if artefato.status_http != 200:
        raise ErroColeta(f"{url} respondeu {artefato.status_http}")
    return artefato.conteudo


def coletar(cliente: ClienteHttp, estado: Path | str, *, agora: datetime | None = None) -> ResumoColetaSest:
    """Baixa o cadastro e o PDG e grava o estado; o arquivo que falha mantém o que o estado já tinha."""
    instante = (agora or datetime.now(timezone.utc)).isoformat(timespec="seconds")
    dados = ler_estado(estado)
    resumo = ResumoColetaSest()
    try:
        z = _baixar(cliente, URL_IDENTIFICACAO)
        try:
            inativas = membro(z, "empresas-inativas.csv")
        except ArquivoSestIlegivel:
            inativas = None
        dados["identificacao"] = {"url": URL_IDENTIFICACAO, "coletado_em": instante,
                                  "empresas": empresas(membro(z, "empresas-ativas.csv"), inativas)}
    except (ErroColeta, ValueError) as erro:
        resumo.falhas["identificacao"] = f"{type(erro).__name__}: {erro}"
        if dados.get("identificacao"):
            dados["identificacao"]["ultima_falha"] = instante
    try:
        dados["pdg"] = {"url": URL_PDG, "coletado_em": instante,
                        "empresas": pdg(membro(_baixar(cliente, URL_PDG), "sest-pdg.csv"))}
    except (ErroColeta, ValueError) as erro:
        resumo.falhas["pdg"] = f"{type(erro).__name__}: {erro}"
        if dados.get("pdg"):
            dados["pdg"]["ultima_falha"] = instante
    resumo.empresas = len((dados.get("identificacao") or {}).get("empresas", {}))
    por_empresa = (dados.get("pdg") or {}).get("empresas", {})
    resumo.empresas_pdg = len(por_empresa)
    resumo.exercicios = sorted({a for e in por_empresa.values() for a in e["exercicios"]})
    dados["falhas"] = {"em": instante, "motivos": resumo.falhas} if resumo.falhas else {}
    Path(estado).mkdir(parents=True, exist_ok=True)
    gravar_json(Path(estado) / ARQUIVO_ESTADO, dados, comprimir=True)
    return resumo


# ------------------------------------------------------------------------------------------ publicação

@dataclass(frozen=True)
class Rubrica:
    """Uma linha do PDG que o portal mostra, com o código da SEST e o que ela inclui."""

    id: str
    codigo: str
    nome: str
    definicao: str


RUBRICAS: tuple[Rubrica, ...] = (
    Rubrica("total_usos", "2300000000", "Total dos dispêndios",
            "Total dos usos do PDG: despesas correntes e de capital (investimentos, amortização de dívidas, "
            "inversões financeiras). Nos bancos inclui a concessão de crédito e as aplicações, por isso chega a "
            "trilhões: para comparar o custo da empresa, use pessoal, materiais e serviços."),
    Rubrica("pessoal", "2201000000", "Pessoal", "Despesas de pessoal e encargos dos empregados."),
    Rubrica("dirigentes", "2202000000", "Dirigentes", "Remuneração e encargos da diretoria."),
    Rubrica("conselhos", "2203000000", "Conselhos e comitês", "Remuneração dos conselhos e comitês estatutários."),
    Rubrica("materiais", "2204000000", "Materiais e produtos", "Compras de materiais e produtos."),
    Rubrica("servicos", "2205000000", "Serviços de terceiros", "Contratação de serviços de terceiros."),
    Rubrica("tributos", "2206000000", "Tributos", "Tributos e encargos parafiscais pagos."),
    Rubrica("financeiras", "2207000000", "Despesas financeiras", "Juros e outros encargos financeiros."),
    Rubrica("outras_correntes", "2290000000", "Outras despesas correntes",
            "Despesas correntes não classificadas nas rubricas anteriores."),
    Rubrica("investimentos", "2107000000", "Investimentos",
            "Investimentos no ativo imobilizado, intangível e benfeitorias. É o realizado do Orçamento de "
            "Investimento visto pelo PDG: não somar com o OI."),
    Rubrica("receitas_correntes", "1200000000", "Receitas correntes",
            "Receitas correntes da empresa (vendas, serviços, receitas financeiras)."),
    Rubrica("aportes_tesouro", "1100010100", "Aportes do Tesouro",
            "Aportes de capital do Tesouro Nacional. Também aparecem no Orçamento da União: não somar."),
    Rubrica("subsidios_tesouro", "1102000000", "Subsídios do Tesouro",
            "Subsídios do Tesouro Nacional. Também aparecem no Orçamento da União: não somar."),
)


def montar(dados: dict) -> dict:
    """A parte das estatais federais da SEST no arquivo ``economia/estatais.json``."""
    cadastro = (dados.get("identificacao") or {}).get("empresas", {})
    por_empresa = (dados.get("pdg") or {}).get("empresas", {})
    lista = []
    for codigo in sorted(set(cadastro) | set(por_empresa)):
        cad = cadastro.get(codigo, {})
        p = por_empresa.get(codigo, {"exercicios": {}})
        exercicios = {}
        for ano, rubricas in sorted(p["exercicios"].items()):
            valores = {}
            for r in RUBRICAS:
                linha = rubricas.get(r.codigo)
                valores[r.id] = None if linha is None else {"aprovado": linha[0], "realizado": linha[1],
                                                             "ate_mes": linha[2]}
            exercicios[ano] = valores
        lista.append({"codigo_siest": codigo, "sigla": cad.get("sigla") or p.get("empresa"),
                      "nome": cad.get("nome") or p.get("empresa"), "cnpj": cad.get("cnpj"),
                      "dependente": cad.get("dependente"), "grupo": cad.get("grupo"), "setor": cad.get("setor"),
                      "capital": cad.get("capital"), "natureza": cad.get("natureza"),
                      "ministerio": cad.get("ministerio"), "situacao": cad.get("situacao"),
                      "inativa_desde": cad.get("inativa_desde"), "exercicios": exercicios})

    def ordem(e):
        ultimo = max(e["exercicios"], default=None)
        total = ((e["exercicios"].get(ultimo) or {}).get("total_usos") or {}) if ultimo else {}
        return (e["situacao"] != "ativa", -(total.get("realizado") or 0), e["sigla"] or "")
    lista.sort(key=ordem)
    return {"fonte": "SEST/MGI, dados abertos das empresas estatais federais (identificação e PDG)",
            "urls": {"pagina": URL_PAGINA, "identificacao": URL_IDENTIFICACAO, "pdg": URL_PDG},
            "coletado_em": {"identificacao": (dados.get("identificacao") or {}).get("coletado_em"),
                            "pdg": (dados.get("pdg") or {}).get("coletado_em")},
            "falhas": dados.get("falhas") or {},
            "rubricas": [{"id": r.id, "codigo": r.codigo, "nome": r.nome, "definicao": r.definicao} for r in RUBRICAS],
            "empresas": lista}
