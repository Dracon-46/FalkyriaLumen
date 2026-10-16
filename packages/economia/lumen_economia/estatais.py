"""Empresas estatais com ações na bolsa: quem as controla e quanto gastam, pelas demonstrações entregues à CVM.

As estatais não contratam pela Lei 14.133 e não publicam no PNCP (Lei 13.303/2016). As que são companhias
abertas entregam à CVM, todo ano, as demonstrações financeiras padronizadas (DFP), com receita, custos,
despesas, o valor adicionado distribuído (pessoal, impostos, juros) e o caixa aplicado em investimentos.

A coleta (``coletar``) lê o cadastro da CVM, escolhe as companhias que se declaram estatais, confere quem
as controla no Formulário de Referência e guarda as contas das DFP no estado ``economia-cvm.json.gz``, com
o dos painéis. A publicação (``montar``/``publicar``) gera ``economia/estatais.json``, que o portal lê, com
as estatais federais de capital fechado da SEST (``sest.py``) ao lado.

Regras (ADR-034):

- o controle vem do FRE, não do campo do cadastro, que a companhia declara e não atualiza;
- nenhum total soma companhias: a controladora consolida as controladas (o Banco do Brasil consolida a BB
  Seguridade), e somar contaria duas vezes;
- cada indicador vem de uma conta identificada pela descrição oficial do modelo da CVM, porque o código
  muda conforme o modelo (empresa, banco ou seguradora); quando a conta não é achada, o valor fica
  ausente, e não zero;
- os valores são os publicados, em reais correntes, com o sinal da demonstração.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

from lumen_ingestao.cliente_http import ClienteHttp
from lumen_ingestao.coleta_http import ErroColeta
from lumen_ingestao.zip_remoto import baixar_membro
from lumen_painel.comum import gravar_json, ler_json

from . import cvm, sest

ARQUIVO_ESTADO = "economia-cvm.json.gz"
ARQUIVO_FEED = "economia/estatais.json"
VERSAO_ESTADO = 1
VERSAO_FEED = 1
FONTE_ID = "cvm_dados_abertos"
ANOS_PADRAO = 5

BaixarMembro = Callable[[ClienteHttp, str, str], object]


# ------------------------------------------------------------------------------------------ coleta

@dataclass
class ResumoColetaEstatais:
    """O que a coleta fez: candidatas, controle conferido, anos das DFP lidos ou mantidos e as falhas."""

    candidatas: int = 0
    com_controle: int = 0
    anos_lidos: dict[str, int] = field(default_factory=dict)      # ano → companhias com contas
    anos_mantidos: list[str] = field(default_factory=list)        # arquivo sem mudança desde a última coleta
    falhas: dict[str, str] = field(default_factory=dict)

    def para_json(self) -> dict:
        """Resumo para imprimir na linha de comando."""
        return {"candidatas": self.candidatas, "com_controle": self.com_controle, "anos_lidos": self.anos_lidos,
                "anos_mantidos": self.anos_mantidos, "falhas": self.falhas}


def ler_estado(estado: Path | str) -> dict:
    """O estado gravado, ou um estado vazio na versão atual."""
    caminho = Path(estado) / ARQUIVO_ESTADO
    if not caminho.exists() or caminho.stat().st_size == 0:
        return {"versao": VERSAO_ESTADO, "cadastro": None, "controle": None, "dfp": {}}
    dados = ler_json(caminho)
    if dados.get("versao") != VERSAO_ESTADO:
        raise ValueError(f"{caminho}: versão {dados.get('versao')!r} do estado das estatais não suportada")
    return dados


def anos_padrao(agora: datetime) -> list[int]:
    """Os últimos ``ANOS_PADRAO`` exercícios encerrados (em 2026, de 2021 a 2025)."""
    return list(range(agora.year - ANOS_PADRAO, agora.year))


def ultima_modificacao(cliente: ClienteHttp, url: str) -> str | None:
    """``Last-Modified`` do arquivo, pedindo só o último byte (o arquivo inteiro não é baixado)."""
    artefato = cliente.obter(url, {"Range": "bytes=-1"})
    if artefato.status_http not in (200, 206):
        raise ErroColeta(f"{url} respondeu {artefato.status_http}")
    return {k.lower(): v for k, v in artefato.cabecalhos.items()}.get("last-modified")


def _membro(baixar: BaixarMembro, cliente: ClienteHttp, url: str, nome: str) -> bytes | None:
    """Conteúdo de um CSV de dentro do ZIP, ou ``None`` se o ZIP não o tem (DFC pelo método direto, por exemplo)."""
    try:
        return baixar(cliente, url, nome).conteudo
    except ErroColeta as erro:
        if "não tem" in str(erro):
            return None
        raise


def _coletar_dfp(cliente: ClienteHttp, baixar: BaixarMembro, ano: int, cnpjs: set[str]) -> dict:
    """As contas e os documentos de um ano das DFP, só das companhias pedidas.

    Para cada companhia e demonstração, fica a base consolidada quando existe; senão, a da controladora.
    Da DFC, fica o método indireto quando existe; senão, o direto.
    """
    url = cvm.url_dfp(ano)
    lidas: dict[str, dict[str, dict]] = {}       # "DRE_con" → cnpj → contas
    for demonstracao in cvm.DEMONSTRACOES:
        for base in cvm.BASES:
            conteudo = _membro(baixar, cliente, url, cvm.membro_dfp(ano, demonstracao, base))
            lidas[f"{demonstracao}_{base}"] = cvm.contas(conteudo, cnpjs) if conteudo is not None else {}
    docs_bytes = _membro(baixar, cliente, url, cvm.membro_documentos(ano))
    docs = cvm.documentos(docs_bytes, cnpjs) if docs_bytes is not None else {}
    companhias: dict[str, dict] = {}
    for cnpj in cnpjs:
        escolhidas: dict[str, dict] = {}
        for tipo, opcoes in (("DRE", ("DRE",)), ("DFC", ("DFC_MI", "DFC_MD")), ("DVA", ("DVA",))):
            for demonstracao in opcoes:
                achou = next(((demonstracao, base) for base in cvm.BASES if cnpj in lidas[f"{demonstracao}_{base}"]), None)
                if achou:
                    escolhidas[tipo] = {"demonstracao": achou[0], "base": achou[1],
                                        **lidas[f"{achou[0]}_{achou[1]}"][cnpj]}
                    break
        if escolhidas:
            companhias[cnpj] = {"documento": docs.get(cnpj), "demonstracoes": escolhidas}
    return {"url": url, "companhias": companhias}


def coletar(cliente: ClienteHttp, estado: Path | str, anos: Iterable[int] | None = None, *,
            baixar: BaixarMembro = baixar_membro, agora: datetime | None = None) -> ResumoColetaEstatais:
    """Lê cadastro, FRE e DFP e grava o estado; o que falha mantém o que o estado já tinha.

    Um ano das DFP cujo ZIP não mudou desde a última coleta (mesmo ``Last-Modified``) não é baixado de novo,
    a não ser que as candidatas tenham mudado.
    """
    agora = agora or datetime.now(timezone.utc)
    instante = agora.isoformat(timespec="seconds")
    dados = ler_estado(estado)
    dados.setdefault("falhas", {})
    resumo = ResumoColetaEstatais()
    try:
        artefato = cliente.obter(cvm.URL_CADASTRO, {"Accept": "text/csv"})
        if artefato.status_http != 200:
            raise ErroColeta(f"cadastro respondeu {artefato.status_http}")
        companhias = cvm.candidatas(artefato.conteudo)
        if not companhias:
            raise cvm.ArquivoCvmIlegivel("nenhuma companhia estatal ativa no cadastro")
        dados["cadastro"] = {"url": cvm.URL_CADASTRO, "coletado_em": instante,
                             "companhias": {c: v.para_json() for c, v in sorted(companhias.items())}}
    except (ErroColeta, ValueError) as erro:
        resumo.falhas["cadastro"] = f"{type(erro).__name__}: {erro}"
    if not dados.get("cadastro"):
        _gravar(estado, dados, resumo, instante)
        return resumo
    cnpjs = set(dados["cadastro"]["companhias"])
    resumo.candidatas = len(cnpjs)

    try:
        conteudos, urls = [], []
        for ano in (agora.year - 1, agora.year):
            conteudo = _membro(baixar, cliente, cvm.url_fre(ano), cvm.membro_posicao(ano))
            if conteudo is not None:
                conteudos.append(conteudo)
                urls.append(cvm.url_fre(ano))
        controle = cvm.controladores(conteudos, cnpjs)
        dados["controle"] = {"urls": urls, "coletado_em": instante, "companhias": controle}
    except (ErroColeta, ValueError) as erro:
        resumo.falhas["controle"] = f"{type(erro).__name__}: {erro}"
    resumo.com_controle = len((dados.get("controle") or {}).get("companhias", {}))

    for ano in anos if anos is not None else anos_padrao(agora):
        chave = str(ano)
        anterior = dados["dfp"].get(chave) or {}
        try:
            modificado = ultima_modificacao(cliente, cvm.url_dfp(ano))
            if (modificado and anterior.get("ultima_modificacao") == modificado
                    and set(anterior.get("cnpjs", [])) == cnpjs):
                resumo.anos_mantidos.append(chave)
                continue
            lido = _coletar_dfp(cliente, baixar, ano, cnpjs)
        except (ErroColeta, ValueError) as erro:
            resumo.falhas[f"dfp_{ano}"] = f"{type(erro).__name__}: {erro}"
            if anterior:
                dados["dfp"][chave] = {**anterior, "ultima_falha": instante}
            continue
        dados["dfp"][chave] = {**lido, "ultima_modificacao": modificado, "coletado_em": instante,
                               "cnpjs": sorted(cnpjs)}
        resumo.anos_lidos[chave] = len(lido["companhias"])
    _gravar(estado, dados, resumo, instante)
    return resumo


def _gravar(estado: Path | str, dados: dict, resumo: ResumoColetaEstatais, instante: str) -> None:
    """Grava o estado com as falhas desta coleta."""
    dados["falhas"] = {"em": instante, "motivos": resumo.falhas} if resumo.falhas else {}
    Path(estado).mkdir(parents=True, exist_ok=True)
    gravar_json(Path(estado) / ARQUIVO_ESTADO, dados, comprimir=True)


# ------------------------------------------------------------------------------------------ indicadores

@dataclass(frozen=True)
class Indicador:
    """Um número tirado das demonstrações: de qual demonstração, como achar a conta e como ler o sinal."""

    id: str
    nome: str
    demonstracao: str           # DRE, DFC ou DVA
    definicao: str
    saida: bool                 # a demonstração publica como negativo o que é gasto (custo, compra)


INDICADORES: tuple[Indicador, ...] = (
    Indicador("receita", "Receita", "DRE",
              "Primeira linha da DRE: receita de venda de bens e serviços (empresas), de intermediação "
              "financeira (bancos) ou das operações de seguro, conforme o modelo da companhia.", False),
    Indicador("custos", "Custos", "DRE",
              "Segunda linha da DRE: custo dos bens e serviços vendidos (empresas), despesas de intermediação "
              "financeira (bancos) ou da atividade seguradora.", True),
    Indicador("despesas_operacionais", "Despesas e receitas operacionais", "DRE",
              "Saldo das despesas operacionais (vendas, administrativas, outras) e das outras receitas "
              "operacionais. Negativo é despesa líquida.", False),
    Indicador("resultado", "Lucro ou prejuízo", "DRE",
              "Lucro (positivo) ou prejuízo (negativo) do exercício, incluindo a parte dos sócios não "
              "controladores no consolidado.", False),
    Indicador("insumos", "Compras de terceiros", "DVA",
              "Insumos adquiridos de terceiros na DVA: materiais, energia, serviços de terceiros e outros "
              "custos com fornecedores.", True),
    Indicador("pessoal", "Pessoal", "DVA",
              "Valor adicionado distribuído ao pessoal: remuneração direta, benefícios e FGTS.", False),
    Indicador("impostos", "Impostos, taxas e contribuições", "DVA",
              "Valor adicionado distribuído ao governo (federal, estadual e municipal). Pode ser negativo "
              "quando há créditos tributários, como nos bancos.", False),
    Indicador("capitais_terceiros", "Juros e aluguéis", "DVA",
              "Remuneração de capitais de terceiros na DVA: juros, aluguéis e outras.", False),
    Indicador("capitais_proprios", "Remuneração dos acionistas", "DVA",
              "Remuneração de capitais próprios: juros sobre o capital próprio, dividendos e lucros retidos "
              "(ou prejuízo).", False),
    Indicador("caixa_investimentos", "Caixa das atividades de investimento", "DFC",
              "Saldo do caixa das atividades de investimento na DFC: compras de ativos, aplicações, vendas "
              "de ativos e dividendos recebidos. Negativo é caixa aplicado.", False),
    Indicador("aquisicoes_ativos", "Compras de imobilizado e intangível", "DFC",
              "Soma das saídas de caixa que a própria companhia descreveu como imobilizado ou intangível na "
              "atividade de investimento (sem as vendas e baixas). Não é conta padronizada: a lista das linhas "
              "somadas vai junto. A infraestrutura de concessões lançada como ativo de contrato ou ativo "
              "financeiro fica de fora.", True),
)

_DISTRIBUICAO = re.compile(r"^Distribui[çc][ãa]o do Valor Adicionado", re.I)
_DVA_FILHOS = {"pessoal": re.compile(r"^Pessoal", re.I),
               "impostos": re.compile(r"^Impostos", re.I),
               "capitais_terceiros": re.compile(r"^Remunera[çc][ãa]o d[eo]s? Capita(l|is) de Terceiros", re.I),
               "capitais_proprios": re.compile(r"^Remunera[çc][ãa]o d[eo]s? Capita(l|is) Pr[óo]prios?", re.I)}
_INSUMOS = re.compile(r"^Insumos Adquiridos de Terceiros", re.I)
_RESULTADO = re.compile(r"^Lucro.*(Per[íi]odo|Exerc[íi]cio)", re.I)
_INVESTIMENTO = re.compile(r"^Caixa L[íi]quido (das )?Atividades de Investimento", re.I)
_ATIVO_FIXO = re.compile(r"(imobilizad|intang)", re.I)
_VENDA = re.compile(r"(venda|aliena|baixa|recebiment|resgate|redu[çc])", re.I)


def nivel(codigo: str) -> int:
    """Profundidade da conta: ``3.04`` é 2, ``3.04.05.01`` é 4."""
    return codigo.count(".") + 1


def modelo(dre: list[list]) -> str:
    """Modelo da DRE pela descrição da primeira linha: ``empresa``, ``banco``, ``seguradora`` ou ``outro``."""
    primeira = next((ds for cd, ds, *_ in dre if cd == "3.01"), "")
    if primeira.startswith("Receita de Venda"):
        return "empresa"
    if "Intermedia" in primeira:
        return "banco"
    if "Segura" in primeira or "Previd" in primeira:
        return "seguradora"
    return "outro"


def _conta(contas_: list[list], codigo: str) -> dict | None:
    """A conta de código ``codigo``, como ``{"conta", "descricao", "valor"}``."""
    for cd, ds, valor, _ in contas_:
        if cd == codigo:
            return {"conta": cd, "descricao": ds, "valor": valor}
    return None


def _por_descricao(contas_: list[list], padrao: re.Pattern, *, nivel_: int | None = None,
                   prefixo: str = "", ultima: bool = False) -> dict | None:
    """A primeira (ou a última) conta cuja descrição casa com ``padrao``, no nível e sob o prefixo pedidos."""
    achadas = [{"conta": cd, "descricao": ds, "valor": v} for cd, ds, v, _ in contas_
               if padrao.search(ds) and (nivel_ is None or nivel(cd) == nivel_) and cd.startswith(prefixo)]
    if not achadas:
        return None
    return achadas[-1] if ultima else achadas[0]


def _aquisicoes(dfc: list[list], investimento: dict | None) -> dict | None:
    """Linhas da atividade de investimento que a companhia descreveu como compra de imobilizado ou
    intangível, somadas, sem contar duas vezes uma linha e a que está dentro dela."""
    if not investimento:
        return None
    raiz = investimento["conta"] + "."
    casadas = [(cd, ds, v) for cd, ds, v, _ in dfc
               if cd.startswith(raiz) and v is not None and v < 0 and _ATIVO_FIXO.search(ds)
               and not _VENDA.search(ds)]
    linhas_ = [x for x in casadas if not any(x[0].startswith(o[0] + ".") for o in casadas if o is not x)]
    if not linhas_:
        return None
    return {"conta": None, "descricao": "; ".join(ds for _, ds, _ in linhas_),
            "valor": round(sum(v for *_, v in linhas_), 2), "linhas": [list(x) for x in linhas_]}


def extrair(demonstracoes: dict[str, dict]) -> tuple[str, dict[str, dict | None]]:
    """O modelo da companhia e cada indicador do catálogo (``None`` quando a conta não foi achada)."""
    dre = (demonstracoes.get("DRE") or {}).get("contas", [])
    dva = (demonstracoes.get("DVA") or {}).get("contas", [])
    dfc = (demonstracoes.get("DFC") or {}).get("contas", [])
    saida: dict[str, dict | None] = {
        "receita": _conta(dre, "3.01"),
        "custos": _conta(dre, "3.02"),
        "despesas_operacionais": _conta(dre, "3.04"),
        "resultado": _por_descricao(dre, _RESULTADO, nivel_=2, ultima=True),
        "insumos": _por_descricao(dva, _INSUMOS, nivel_=2),
    }
    distribuicao = _por_descricao(dva, _DISTRIBUICAO, nivel_=2)
    for chave, padrao in _DVA_FILHOS.items():
        saida[chave] = (_por_descricao(dva, padrao, nivel_=3, prefixo=distribuicao["conta"] + ".")
                        if distribuicao else None)
    saida["caixa_investimentos"] = _por_descricao(dfc, _INVESTIMENTO, nivel_=2)
    saida["aquisicoes_ativos"] = _aquisicoes(dfc, saida["caixa_investimentos"])
    return modelo(dre), saida


def _bases(demonstracoes: dict[str, dict]) -> dict[str, str]:
    """De onde saiu cada demonstração: ``DRE`` → ``consolidado`` ou ``individual`` (e o método da DFC)."""
    nomes = {"con": "consolidado", "ind": "individual"}
    saida = {}
    for tipo, d in demonstracoes.items():
        texto = nomes.get(d.get("base"), d.get("base"))
        if tipo == "DFC":
            texto += ", método " + ("indireto" if d.get("demonstracao") == "DFC_MI" else "direto")
        saida[tipo] = texto
    return saida


def montar(dados: dict, *, sest_dados: dict | None = None, agora: datetime | None = None) -> dict:
    """O arquivo ``economia/estatais.json`` a partir dos estados da CVM e (se houver) da SEST."""
    cadastro = (dados.get("cadastro") or {}).get("companhias", {})
    controle = (dados.get("controle") or {}).get("companhias", {})
    classes = cvm.classificar(controle)
    nomes = {c: v["nome"] for c, v in cadastro.items()}
    companhias = []
    for cnpj, cad in cadastro.items():
        classe = classes.get(cnpj, {"classe": "sem_fre", "esfera": None, "controlada_por": None})
        exercicios = {}
        modelos = set()
        for ano, lido in sorted((dados.get("dfp") or {}).items()):
            c = lido.get("companhias", {}).get(cnpj)
            if not c:
                continue
            modelo_, valores = extrair(c["demonstracoes"])
            modelos.add(modelo_)
            exercicios[ano] = {"documento": c.get("documento"), "bases": _bases(c["demonstracoes"]),
                               "fim": (c["demonstracoes"].get("DRE") or {}).get("fim"), "valores": valores}
        mae = classe["controlada_por"]
        companhias.append({
            "cnpj": cnpj, **{k: cad[k] for k in ("nome", "cd_cvm", "setor", "categoria", "uf", "municipio",
                                                  "controle_declarado")},
            "controle": {**classe, "controlada_por_nome": nomes.get(mae) if mae else None,
                         **{k: (controle.get(cnpj) or {}).get(k) for k in
                            ("controladores", "data_referencia", "versao", "id_documento")}},
            "modelo": sorted(modelos)[-1] if modelos else None,
            "exercicios": exercicios,
        })
    companhias.sort(key=lambda c: (c["controle"]["classe"] not in ("publico_direto", "publico_indireto"),
                                   -(((c["exercicios"].get(max(c["exercicios"], default=""), {}) or {})
                                      .get("valores", {}).get("receita") or {}).get("valor") or 0)))
    return {
        "versao": VERSAO_FEED, "tipo": "estatais",
        "gerado_em": (agora or datetime.now(timezone.utc)).isoformat(timespec="seconds"),
        "fonte": "CVM, dados abertos das companhias abertas (cadastro, FRE e DFP)",
        "urls": {"cadastro": cvm.URL_CADASTRO, "controle": (dados.get("controle") or {}).get("urls", []),
                 "dfp": {a: v.get("url") for a, v in sorted((dados.get("dfp") or {}).items())}},
        "coletado_em": {"cadastro": (dados.get("cadastro") or {}).get("coletado_em"),
                        "controle": (dados.get("controle") or {}).get("coletado_em"),
                        "dfp": {a: v.get("coletado_em") for a, v in sorted((dados.get("dfp") or {}).items())}},
        "falhas": dados.get("falhas") or {},
        "indicadores": [{"id": i.id, "nome": i.nome, "demonstracao": i.demonstracao, "definicao": i.definicao,
                         "saida": i.saida} for i in INDICADORES],
        "companhias": companhias,
        "federais": _federais(sest_dados, {c["cnpj"] for c in companhias}) if sest_dados else None,
    }


def _federais(sest_dados: dict, cnpjs_cvm: set[str]) -> dict:
    """A parte da SEST, marcando as empresas que também estão na lista da CVM (para o portal ligar as duas)."""
    federais = sest.montar(sest_dados)
    for e in federais["empresas"]:
        e["na_cvm"] = e["cnpj"] in cnpjs_cvm
    return federais


def publicar(estado: Path | str, saida: Path | str, *, agora: datetime | None = None) -> dict:
    """Grava ``economia/estatais.json`` em ``saida`` e devolve um resumo por classe de controle."""
    sest_dados = sest.ler_estado(estado) if (Path(estado) / sest.ARQUIVO_ESTADO).exists() else None
    feed = montar(ler_estado(estado), sest_dados=sest_dados, agora=agora)
    gravar_json(Path(saida) / ARQUIVO_FEED, feed)
    classes: dict[str, int] = {}
    for c in feed["companhias"]:
        classes[c["controle"]["classe"]] = classes.get(c["controle"]["classe"], 0) + 1
    federais = feed["federais"]["empresas"] if feed["federais"] else []
    return {"arquivo": str(Path(saida) / ARQUIVO_FEED), "companhias": len(feed["companhias"]), "controle": classes,
            "federais_sest": len(federais), "federais_com_pdg": sum(1 for e in federais if e["exercicios"])}
