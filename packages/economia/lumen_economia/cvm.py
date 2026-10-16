"""Dados abertos da CVM sobre as companhias abertas: cadastro, controle acionário (FRE) e demonstrações (DFP).

Três arquivos, todos em ``dados.cvm.gov.br``, em latin-1 e separados por ponto e vírgula:

- **cadastro** (``cad_cia_aberta.csv``): uma linha por registro da companhia, com ``CONTROLE_ACIONARIO``
  declarado pela própria companhia (``ESTATAL``, ``ESTATAL HOLDING``, ``PRIVADO``...). O campo não é
  conferido nem atualizado pela CVM a cada mudança de controle: companhias privatizadas continuam com
  ``ESTATAL`` (ADR-034). Por isso o Lumen usa o cadastro só para escolher as candidatas.
- **posição acionária do Formulário de Referência** (``fre_cia_aberta_posicao_acionaria_AAAA.csv``, dentro
  de ``fre_cia_aberta_AAAA.zip``): os acionistas com 5% ou mais e se cada um é controlador. É daqui que sai
  quem controla a companhia. O arquivo traz também pessoas físicas, com CPF; o Lumen lê só os acionistas
  diretos que são pessoa jurídica e descarta as linhas de pessoa física sem guardar nada delas (LGPD).
- **demonstrações financeiras padronizadas** (``dfp_cia_aberta_AAAA.zip``): DRE, DFC e DVA de cada
  companhia, consolidadas (``_con``) e da controladora (``_ind``), em contas com código. As contas
  "fixas" (``ST_CONTA_FIXA = S``) têm o código definido pela CVM para cada modelo de demonstração; as
  demais são abertas pela companhia, com a descrição que ela escolheu.

Os campos do cadastro com dados do responsável (nome, telefone, e-mail) nunca são lidos.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

BASE = "https://dados.cvm.gov.br/dados/CIA_ABERTA"
URL_CADASTRO = f"{BASE}/CAD/DADOS/cad_cia_aberta.csv"
CONTROLES_ESTATAIS = ("ESTATAL", "ESTATAL HOLDING")
DEMONSTRACOES = ("DRE", "DFC_MI", "DFC_MD", "DVA")
BASES = ("con", "ind")
ULTIMO = "ÚLTIMO"


def url_dfp(ano: int) -> str:
    """Endereço do ZIP das DFP do ano de referência ``ano``."""
    return f"{BASE}/DOC/DFP/DADOS/dfp_cia_aberta_{ano}.zip"


def url_fre(ano: int) -> str:
    """Endereço do ZIP dos Formulários de Referência entregues para o ano ``ano``."""
    return f"{BASE}/DOC/FRE/DADOS/fre_cia_aberta_{ano}.zip"


def membro_dfp(ano: int, demonstracao: str, base: str) -> str:
    """Nome do CSV de uma demonstração dentro do ZIP das DFP (``dfp_cia_aberta_DRE_con_2025.csv``)."""
    return f"dfp_cia_aberta_{demonstracao}_{base}_{ano}.csv"


def membro_documentos(ano: int) -> str:
    """Nome do CSV com a lista de documentos entregues (versão, data de recebimento e endereço no RAD)."""
    return f"dfp_cia_aberta_{ano}.csv"


def membro_posicao(ano: int) -> str:
    """Nome do CSV da posição acionária dentro do ZIP do FRE."""
    return f"fre_cia_aberta_posicao_acionaria_{ano}.csv"


class ArquivoCvmIlegivel(ValueError):
    """O arquivo da CVM não tem as colunas esperadas: o leiaute mudou ou a resposta não é o CSV."""


def linhas(conteudo: bytes, obrigatorias: tuple[str, ...]) -> list[dict[str, str]]:
    """As linhas do CSV da CVM como dicionários, conferindo que as colunas ``obrigatorias`` existem."""
    texto = conteudo.decode("latin-1")
    leitor = csv.DictReader(io.StringIO(texto, newline=""), delimiter=";")
    faltando = [c for c in obrigatorias if c not in (leitor.fieldnames or [])]
    if faltando:
        raise ArquivoCvmIlegivel(f"colunas ausentes: {faltando} (cabeçalho: {(leitor.fieldnames or [])[:8]})")
    return [{k: (v or "").strip() for k, v in r.items() if k is not None} for r in leitor]


# ------------------------------------------------------------------------------------------ cadastro

COLUNAS_CADASTRO = ("CNPJ_CIA", "DENOM_SOCIAL", "SIT", "CD_CVM", "SETOR_ATIV", "CATEG_REG", "SIT_EMISSOR",
                    "CONTROLE_ACIONARIO", "MUN", "UF")


@dataclass(frozen=True)
class Companhia:
    """O que o Lumen guarda do cadastro: identificação, setor e o controle declarado (sem o responsável)."""

    cnpj: str
    nome: str
    cd_cvm: str
    setor: str
    categoria: str
    situacao_emissor: str
    controle_declarado: str
    municipio: str
    uf: str

    def para_json(self) -> dict:
        """Campos para o estado."""
        return {"nome": self.nome, "cd_cvm": self.cd_cvm, "setor": self.setor, "categoria": self.categoria,
                "situacao_emissor": self.situacao_emissor, "controle_declarado": self.controle_declarado,
                "municipio": self.municipio, "uf": self.uf}


def candidatas(conteudo: bytes) -> dict[str, Companhia]:
    """Companhias com registro ativo que se declaram estatais no cadastro, uma por CNPJ."""
    saida: dict[str, Companhia] = {}
    for r in linhas(conteudo, COLUNAS_CADASTRO):
        if r["SIT"] != "ATIVO" or r["CONTROLE_ACIONARIO"] not in CONTROLES_ESTATAIS:
            continue
        saida.setdefault(r["CNPJ_CIA"], Companhia(
            cnpj=r["CNPJ_CIA"], nome=r["DENOM_SOCIAL"], cd_cvm=r["CD_CVM"], setor=r["SETOR_ATIV"],
            categoria=r["CATEG_REG"], situacao_emissor=r["SIT_EMISSOR"],
            controle_declarado=r["CONTROLE_ACIONARIO"], municipio=r["MUN"], uf=r["UF"]))
    return saida


# ------------------------------------------------------------------------------------------ controle

COLUNAS_POSICAO = ("CNPJ_Companhia", "Data_Referencia", "Versao", "ID_Documento", "Acionista",
                   "Tipo_Pessoa_Acionista", "CPF_CNPJ_Acionista", "ID_Acionista_Relacionado",
                   "Percentual_Acao_Ordinaria_Circulacao", "Percentual_Total_Acoes_Circulacao",
                   "Acionista_Controlador")


def _percentual(texto: str) -> float | None:
    """``"50.260000"`` → 50.26; vazio ou ilegível → ``None`` (ausente, não zero)."""
    try:
        return round(float(texto), 3) if texto else None
    except ValueError:
        return None


def controladores(conteudos: list[bytes], cnpjs: set[str]) -> dict[str, dict]:
    """Os controladores diretos, pessoa jurídica, declarados no FRE mais recente de cada companhia.

    Considera o documento de data de referência e versão mais recentes entre os arquivos lidos. Guarda o
    nome, o CNPJ e os percentuais de cada acionista direto (sem acionista "relacionado") marcado como
    controlador. Controladores pessoa física são só contados: nome e CPF não são guardados.
    """
    documentos: dict[str, dict[tuple[str, int], list[dict]]] = {}
    for conteudo in conteudos:
        for r in linhas(conteudo, COLUNAS_POSICAO):
            if r["CNPJ_Companhia"] not in cnpjs:
                continue
            try:
                chave = (r["Data_Referencia"], int(r["Versao"]))
            except ValueError:
                continue
            documentos.setdefault(r["CNPJ_Companhia"], {}).setdefault(chave, []).append(r)
    saida = {}
    for cnpj, por_doc in documentos.items():
        chave = max(por_doc)
        diretos = [r for r in por_doc[chave] if not r["ID_Acionista_Relacionado"] and r["Acionista_Controlador"] == "S"]
        saida[cnpj] = {
            "data_referencia": chave[0], "versao": chave[1], "id_documento": por_doc[chave][0]["ID_Documento"],
            "controladores": [{"nome": r["Acionista"], "cnpj": r["CPF_CNPJ_Acionista"],
                               "percentual_ordinarias": _percentual(r["Percentual_Acao_Ordinaria_Circulacao"]),
                               "percentual_total": _percentual(r["Percentual_Total_Acoes_Circulacao"])}
                              for r in diretos if r["Tipo_Pessoa_Acionista"] == "PJ"],
            "controladores_pessoa_fisica": sum(1 for r in diretos if r["Tipo_Pessoa_Acionista"] == "PF"),
        }
    return saida


# Raiz do CNPJ da União (Secretaria do Tesouro Nacional) e de empresas públicas federais que controlam
# companhias abertas sem ser companhias abertas (BNDES e Caixa Econômica Federal).
RAIZES_FEDERAIS = {"00.394.460": "União", "33.657.248": "BNDES (empresa pública federal)",
                   "00.360.305": "Caixa Econômica Federal (empresa pública federal)"}
# Um ente se declara pelo começo do nome ("Estado de Santa Catarina", "Governo do Distrito Federal",
# "Prefeitura do Município de São Paulo", "Secretaria de Estado ... do Distrito Federal"); uma companhia que
# tem o estado no nome ("Cia Saneamento Básico do Estado de São Paulo") não começa assim.
_ENTE = re.compile(r"^(governo|estado d|fazenda|prefeitura|munic[íi]pio|uni[ãa]o|distrito federal|secretaria"
                   r"|minist[ée]rio|tesouro)", re.I)
_DISTRITAL = re.compile(r"distrito federal", re.I)
_MUNICIPAL = re.compile(r"\b(prefeitura|munic[íi]pio)\b", re.I)
_FEDERAL = re.compile(r"^(uni[ãa]o|minist[ée]rio|tesouro)", re.I)


def esfera_do_controlador(nome: str, cnpj: str) -> str | None:
    """``federal``, ``estadual``, ``distrital`` ou ``municipal`` quando o controlador é um ente ou empresa
    pública conhecida; ``None`` quando é outra pessoa jurídica (que pode ser outra estatal, conferida à parte).

    A raiz do CNPJ decide a União, o BNDES e a Caixa. Estados, DF e municípios têm CNPJs variados (cada um
    declara o do órgão que detém as ações); para eles decide o nome, que precisa começar como nome de ente.
    """
    if cnpj[:10] in RAIZES_FEDERAIS:
        return "federal"
    nome = nome.strip()
    if not _ENTE.search(nome):
        return None
    if _DISTRITAL.search(nome):
        return "distrital"
    if _MUNICIPAL.search(nome):
        return "municipal"
    if _FEDERAL.search(nome):
        return "federal"
    return "estadual"


def classificar(controle: dict[str, dict]) -> dict[str, dict]:
    """Classifica o controle de cada companhia a partir dos controladores declarados no FRE.

    - ``publico_direto``: algum controlador é ente público ou empresa pública federal conhecida;
    - ``publico_indireto``: o controlador é outra companhia desta lista com controle público (a Cemig
      Distribuição, controlada pela Cemig); a esfera é a dela;
    - ``privado``: há controlador declarado e nenhum é público;
    - ``sem_controlador``: o FRE não declara controlador (o cadastro diz estatal, o FRE não confirma), ou
      o controlador é outra companhia desta lista sem controlador (as controladas da Copel);
    - ``sem_fre``: a companhia não entregou FRE nos anos lidos.

    A cadeia é seguida até estabilizar, então uma controlada de controlada também é reconhecida.
    """
    saida: dict[str, dict] = {}
    for cnpj, c in controle.items():
        esferas = {e for e in (esfera_do_controlador(x["nome"], x["cnpj"]) for x in c["controladores"]) if e}
        if esferas:
            saida[cnpj] = {"classe": "publico_direto", "esfera": sorted(esferas)[0], "controlada_por": None}
        elif c["controladores"] or c["controladores_pessoa_fisica"]:
            saida[cnpj] = {"classe": "privado", "esfera": None, "controlada_por": None}
        else:
            saida[cnpj] = {"classe": "sem_controlador", "esfera": None, "controlada_por": None}
    mudou = True
    while mudou:
        mudou = False
        for cnpj, c in controle.items():
            if saida[cnpj]["classe"] != "privado":
                continue
            for x in c["controladores"]:
                mae = saida.get(x["cnpj"])
                if mae and mae["classe"] in ("publico_direto", "publico_indireto"):
                    saida[cnpj] = {"classe": "publico_indireto", "esfera": mae["esfera"], "controlada_por": x["cnpj"]}
                elif mae and mae["classe"] == "sem_controlador":
                    saida[cnpj] = {"classe": "sem_controlador", "esfera": None, "controlada_por": x["cnpj"]}
                else:
                    continue
                mudou = True
                break
    return saida


# ------------------------------------------------------------------------------------------ demonstrações

COLUNAS_DFP = ("CNPJ_CIA", "DT_REFER", "VERSAO", "ESCALA_MOEDA", "ORDEM_EXERC", "DT_INI_EXERC", "DT_FIM_EXERC",
               "CD_CONTA", "DS_CONTA", "VL_CONTA", "ST_CONTA_FIXA")
COLUNAS_DOCUMENTOS = ("CNPJ_CIA", "DT_REFER", "VERSAO", "ID_DOC", "DT_RECEB", "LINK_DOC")
ESCALAS = {"MIL": Decimal(1000), "UNIDADE": Decimal(1)}


def _reais(valor: str, escala: str) -> float | None:
    """Valor da conta em reais (a CVM publica em milhares na maioria das companhias)."""
    try:
        return float(round(Decimal(valor) * ESCALAS[escala], 2))
    except (InvalidOperation, KeyError):
        return None


def contas(conteudo: bytes, cnpjs: set[str]) -> dict[str, dict]:
    """As contas do exercício de referência (``ÚLTIMO``) de cada companhia, na versão mais recente.

    Devolve ``{cnpj: {"versao", "inicio", "fim", "contas": [[código, descrição, reais, fixa], ...]}}``. O
    lucro por ação (``3.99``) fica de fora: não é valor em reais.
    """
    por_versao: dict[str, dict[int, list[dict]]] = {}
    for r in linhas(conteudo, COLUNAS_DFP):
        if r["CNPJ_CIA"] not in cnpjs or r["ORDEM_EXERC"] != ULTIMO or r["CD_CONTA"].startswith("3.99"):
            continue
        try:
            versao = int(r["VERSAO"])
        except ValueError:
            continue
        por_versao.setdefault(r["CNPJ_CIA"], {}).setdefault(versao, []).append(r)
    saida = {}
    for cnpj, versoes in por_versao.items():
        versao = max(versoes)
        rs = versoes[versao]
        saida[cnpj] = {"versao": versao, "inicio": rs[0]["DT_INI_EXERC"] or None, "fim": rs[0]["DT_FIM_EXERC"],
                       "contas": [[r["CD_CONTA"], r["DS_CONTA"], _reais(r["VL_CONTA"], r["ESCALA_MOEDA"]),
                                   r["ST_CONTA_FIXA"] == "S"] for r in rs]}
    return saida


def documentos(conteudo: bytes, cnpjs: set[str]) -> dict[str, dict]:
    """A entrega mais recente da DFP de cada companhia: versão, data de recebimento e endereço no RAD."""
    saida: dict[str, dict] = {}
    for r in linhas(conteudo, COLUNAS_DOCUMENTOS):
        if r["CNPJ_CIA"] not in cnpjs:
            continue
        try:
            versao = int(r["VERSAO"])
        except ValueError:
            continue
        if versao >= saida.get(r["CNPJ_CIA"], {}).get("versao", -1):
            saida[r["CNPJ_CIA"]] = {"versao": versao, "referencia": r["DT_REFER"], "recebido_em": r["DT_RECEB"],
                                    "id_documento": r["ID_DOC"], "link": r["LINK_DOC"]}
    return saida
