"""Os deputados estaduais pelas fontes próprias das Assembleias Legislativas (ADR-062, adendos 2 e 3): as que usam o
SPL da Ágape Consultoria, que tem uma API pública comum (``/api/publico/``), os votos nominais de Goiás, a API de
dados abertos da Assembleia de Minas Gerais (``CASAS_ALMG``) e os arquivos da Assembleia de São Paulo
(``CASAS_ALESP``), as duas com a verba de gabinete.

As Assembleias com o SAPL do Interlegis vão pela coleta dos vereadores (``vereadores.py``). As outras publicam cada
uma do seu jeito; o levantamento de 4/11/2026 achou o SPL da Ágape em quatro (``CASAS_SPL``: GO, ES, SE e BA):

- ``/api/publico/parlamentar/?pag=&qtd=``: os deputados da legislatura atual, com o partido (a API não traz as
  anteriores; por isso a coleta começa em ``PRIMEIRO_ANO``, o início da legislatura de 2023);
- ``/api/publico/proposicao/?pag=&qtd=&ano=``: as proposições do ano, com o tipo, a ementa e o autor pelo nome (e o
  gabinete). O autor é ligado ao deputado pelo nome; os documentos (CPF) e os contatos que a API traz não são
  guardados. Os projetos (o tipo começa por "projeto" ou é proposta de emenda) ficam com a ementa; os outros tipos
  são só contados;
- em Goiás, ``transparencia.al.go.leg.br/api/transparencia/votacoes.json?tipo=detalhes&ano=&mes=``: o voto de cada
  deputado nas votações nominais do Plenário, com o partido no dia, de 2023 em diante, um mês por pedido (o ano
  inteiro passa de 20 MB); ``tipo=resumo`` dá o processo votado. O voto vem com o nome do deputado, às vezes repetido
  em maiúsculas: fica um por deputado.

Essas quatro e a transparência da Alego não respondem fora do Brasil (tempo esgotado ou 403 para o GitHub Actions em
4/11/2026): os pedidos vão pelo intermediário em São Paulo (``tce.SO_DO_BRASIL``, ``infra/proxy-br``).

Minas Gerais (``dadosabertos.almg.gov.br/api/v2``) dá os deputados da legislatura atual (em exercício e os que
exerceram o mandato), as proposições de cada ano com os autores pelo id (``proposicoes/pesquisa/direcionada``, de 100
em 100, uma consulta por tipo: a API não pagina além de 10 mil linhas) e a verba indenizatória de cada deputado por mês, nota a nota, com o CNPJ do emitente
(``prestacao_contas/verbas_indenizatorias/deputados/<id>/<ano>/<mês>``). A verba vai no lugar da cota dos deputados
federais: por categoria, por mês e por fornecedor com CNPJ; o emitente pessoa física entra só na soma, sem o CPF. MG
não publica os votos nem a presença do Plenário.

São Paulo (``www.al.sp.gov.br/repositorioDados/``) publica arquivos inteiros, refeitos todo dia: os deputados em
exercício (``deputados/deputados.xml``), todas as proposituras desde 1990 (``processo_legislativo/proposituras.zip``,
132 MB descompactado), os autores de cada uma (``documento_autor.zip``, 145 MB; o autor é o ``IdSPL`` do deputado), as
naturezas (``naturezasSpl.xml``) e as despesas de gabinete por nota desde 2015 (``deputados/despesas_gabinetes.xml``,
172 MB, ligadas ao deputado pela matrícula). Os arquivos são lidos em fluxo, sem carregar tudo na memória; ficam as
proposituras e as despesas de ``PRIMEIRO_ANO`` em diante. A ALESP só publica votos e presença das comissões.

Não há presença em nenhuma delas: o detalhe da sessão do SPL, que traria as presenças, respondeu erro em 4/11/2026.
O estado fica em ``assembleias.json.gz``; o ano fechado é relido uma vez por mês e o corrente e o anterior, uma vez
por semana (``tce.precisa_ler_por_idade``). A publicação é a dos deputados federais (``camara.publicar_casa``), em
``parlamentares/estadual/<código da UF>/``, e as linhas entram no índice das Assembleias (``vereadores.publicar``).
"""

from __future__ import annotations

import contextlib
import json
import re
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

from lumen_canonico.documentos import cnpj_valido, mascarar_cpfs_no_texto

from . import tce
from .cadastro import Cadastro
from .camara import EMENTA, baixar_inteiro, publicar_casa
from .comum import gravar_json, instante_utc, ler_json, sem_acento
from .vereadores import ESFERAS, e_projeto

FONTE = "Assembleias Legislativas, API pública do SPL (Ágape) e transparência da Alego"
ARQUIVO = "assembleias.json.gz"
VERSAO_ESTADO = 1
PRIMEIRO_ANO = 2023
POR_PAGINA = 200                    # pelo intermediário em São Paulo, a resposta tem no máximo 4,5 MB
# Código IBGE da UF → endereço do SPL e se há votos nominais pela transparência (só Goiás)
CASAS_SPL: dict[str, dict[str, Any]] = {
    "52": {"host": "alegodigital.al.go.leg.br", "votos": "https://transparencia.al.go.leg.br/api/transparencia"},
    "32": {"host": "www3.al.es.gov.br"},
    "28": {"host": "aleselegis.al.se.leg.br"},
    "29": {"host": "albalegis.nopapercloud.com.br"},
}
# Código IBGE da UF → a API de dados abertos da Assembleia de Minas
CASAS_ALMG: dict[str, dict[str, Any]] = {"31": {"host": "dadosabertos.almg.gov.br"}}
ALMG = "https://dadosabertos.almg.gov.br/api/v2"
# Código IBGE da UF → os arquivos de dados abertos da Assembleia de São Paulo
CASAS_ALESP: dict[str, dict[str, Any]] = {"35": {"host": "www.al.sp.gov.br"}}
ALESP = "https://www.al.sp.gov.br/repositorioDados"
NATUREZAS_PROJETO = frozenset({"1", "2", "3", "4", "5"})   # PL, PLC, PR, PDL e PEC
PAUSA_ALMG = 0.4                    # segundos entre os pedidos à ALMG, que responde 429 a quem pede rápido demais
TENTATIVAS_429 = 4
VOTOS = {"SIM": "S", "NAO": "N", "ABSTENCAO": "A", "OBSTRUCAO": "O"}
TITULOS = re.compile(r"^(GABINETE|GAB|DO|DA|DEP|DEPUTADO|DEPUTADA|DEPUTADOS|DEPUTADAS)$")


def chave(nome: str | None) -> str:
    """O nome para ligar autor e voto ao deputado: sem acento, maiúsculo, sem pontuação e sem "Gabinete do Deputado"
    ("Gab. Dep. João Coser" → ``JOAO COSER``)."""
    palavras = re.sub(r"[^A-Z0-9 ]", " ", sem_acento(nome or "").upper()).split()
    return " ".join(p for p in palavras if not TITULOS.match(p))


def _json(url: str, *, contato: str, ler_fn: Callable[[str], Any] | None) -> Any:
    """O JSON de um endereço (``ler_fn`` substitui a rede nos testes)."""
    if ler_fn:
        return ler_fn(url)
    pedido = urllib.request.Request(url, headers={**tce.cabecalhos(contato), "Accept": "application/json"})
    with tce.abrir(pedido) as r:
        return json.loads(r.read())


def _paginas(host: str, caminho: str, chave_lista: str, *, contato: str, ler_fn: Callable[[str], Any] | None,
             **filtros: Any) -> list[dict]:
    """Todas as linhas de uma lista paginada do SPL (``pag`` e ``qtd``; o total vem em ``total``)."""
    linhas: list[dict] = []
    pagina = 1
    while True:
        q = urllib.parse.urlencode({"pag": pagina, "qtd": POR_PAGINA, **filtros})
        dados = _json(f"https://{host}/api/publico/{caminho}/?{q}", contato=contato, ler_fn=ler_fn) or {}
        lote = dados.get(chave_lista) or []
        linhas.extend(lote)
        if not lote or len(linhas) >= int(dados.get("total") or 0):
            return linhas
        pagina += 1


# ------------------------------------------------------------------------------------------ uma Assembleia

def ler_deputados(linhas: list[dict]) -> dict[str, list]:
    """Os deputados do SPL: ``{id: [nome, nome civil, partido, situação]}``."""
    return {str(p["parlamentarID"]): [(p.get("parlamentarNome") or "").strip(),
                                      (p.get("parlamentarRazaoSocial") or "").strip(),
                                      (p.get("partidoSigla") or "").strip(), (p.get("parlamentarSituacao") or "").strip()]
            for p in linhas if p.get("parlamentarID")}


def _por_nome(deputados: dict[str, list]) -> dict[str, str]:
    """O id do deputado pela chave do nome parlamentar e do nome civil."""
    saida: dict[str, str] = {}
    for pid, (nome, civil, *_) in deputados.items():
        for n in (nome, civil):
            if chave(n):
                saida.setdefault(chave(n), pid)
    return saida


def ler_proposicoes(linhas: list[dict], deputados: dict[str, list], ano: int) -> dict[str, Any]:
    """As proposições de um ano: os projetos (com a ementa e os autores) e a contagem de todas por tipo e deputado."""
    nomes = _por_nome(deputados)
    projetos: dict[str, list] = {}
    contagem: dict[str, dict[str, int]] = {}
    for m in linhas:
        autor = m.get("AutorRequerenteDados") or {}
        candidatos = [autor.get("nomeRazao"), autor.get("setor")]
        candidatos += [c.get("nomeRazao") for c in (m.get("CoAutores") or []) if isinstance(c, dict)]
        autores = sorted({nomes[chave(n)] for n in candidatos if chave(n) in nomes})
        sigla = (m.get("sigla") or "?").strip()
        for p in autores:
            por_tipo = contagem.setdefault(p, {})
            por_tipo[sigla] = por_tipo.get(sigla, 0) + 1
        tipo = sem_acento(m.get("tipo") or "").lower()
        if e_projeto(m.get("tipo")) or tipo.startswith("proposta de emenda"):
            data = m.get("data") or ""
            dia = f"{data[6:10]}-{data[3:5]}-{data[0:2]}" if re.match(r"\d\d/\d\d/\d{4}", data) else f"{ano}-01-01"
            projetos[str(m["id"])] = [sigla, str(m.get("numero") or ""),
                                      " ".join((m.get("assunto") or "").split())[:EMENTA], dia, autores]
    return {"projetos": projetos, "contagem": contagem}


def _ementa(texto: str | None) -> str:
    """O assunto da votação de Goiás ("AUTOR - ...\\nASSUNTO - ..." → o assunto)."""
    m = re.search(r"ASSUNTO\s*-\s*(.+)", texto or "")
    return " ".join((m.group(1) if m else texto or "").split())[:EMENTA]


def ler_votacoes_go(detalhes: list[dict], resumo: list[dict], deputados: dict[str, list]) -> tuple[dict, int]:
    """As votações nominais de Goiás num ano: ``{pauta: [data, processo, ementa, resultado, aprovação, {id: voto},
    {id: partido}]}`` e quantos votos ficaram sem deputado no cadastro."""
    nomes = _por_nome(deputados)
    processos = {str(r.get("pauta_id")): (r.get("numero_processo_projeto") or "").strip() for r in resumo}
    votacoes: dict[str, list] = {}
    sem_deputado = 0
    for v in detalhes:
        if v.get("tipo_votacao") != "NOMINAL" or not v.get("pauta_id"):
            continue
        pid = nomes.get(chave(v.get("parlamentar")))
        if not pid:
            sem_deputado += 1
            continue
        pauta = str(v["pauta_id"])
        resultado = " ".join((v.get("resultado_votacao") or "").split())
        aprovacao = 1 if resultado.upper().startswith("APROVAD") else 0 if resultado.upper().startswith("REJEITAD") else None
        registro = votacoes.setdefault(pauta, [v.get("data_sessao") or "", processos.get(pauta) or "Votação",
                                               _ementa(v.get("ementa_projeto")), resultado, aprovacao, {}, {}])
        voto = sem_acento(v.get("tipo_voto") or "").upper()
        registro[5].setdefault(pid, VOTOS.get(voto, voto or "-"))
        registro[6].setdefault(pid, (v.get("partido_sigla") or "").strip())
    return votacoes, sem_deputado


# ------------------------------------------------------------------------------------------ Minas Gerais

def _almg(caminho: str, *, contato: str, ler_fn: Callable[[str], Any] | None,
          esperar: Callable[[float], None] = time.sleep, **filtros: Any) -> Any:
    """Um pedido à API da ALMG, em JSON, com uma pausa antes (``PAUSA_ALMG``): a API responde 429 a quem pede rápido
    demais, e então o pedido espera e é feito de novo, até ``TENTATIVAS_429`` vezes."""
    q = urllib.parse.urlencode({**filtros, "formato": "json"})
    for tentativa in range(TENTATIVAS_429):
        if not ler_fn:
            esperar(PAUSA_ALMG)
        try:
            return _json(f"{ALMG}/{caminho}?{q}", contato=contato, ler_fn=ler_fn)
        except urllib.error.HTTPError as erro:
            if erro.code != 429 or tentativa + 1 == TENTATIVAS_429:
                raise
            esperar(60 * (tentativa + 1))
    raise AssertionError("inalcançável")


def ler_proposicoes_almg(linhas: list[dict], deputados: dict[str, list], ano: int) -> dict[str, Any]:
    """As proposições de um ano em Minas: os projetos (id ``SIGLA-número-ano``) com a ementa e os autores e a contagem
    de todas por tipo. O autor que não está no cadastro (deixou a Assembleia) entra nele, com o nome e o partido."""
    projetos: dict[str, list] = {}
    contagem: dict[str, dict[str, int]] = {}
    for m in linhas:
        autores = []
        for a in m.get("autoresEstruturados") or []:
            if not a.get("id"):
                continue
            pid = str(a["id"])
            if pid not in deputados:
                nome = re.sub(r"^Deputad[oa]\s+", "", (a.get("nome") or "").strip())
                deputados[pid] = [nome, nome, (a.get("partido") or "").strip(), "Fora de exercício"]
            autores.append(pid)
        autores = sorted(set(autores))
        sigla = (m.get("siglaTipoProjeto") or "?").strip()
        for pid in autores:
            por_tipo = contagem.setdefault(pid, {})
            por_tipo[sigla] = por_tipo.get(sigla, 0) + 1
        tipo = sem_acento(m.get("tipoProjeto") or "").lower()
        if e_projeto(m.get("tipoProjeto")) or tipo.startswith("proposta de emenda"):
            projetos[f"{sigla}-{m.get('numero')}-{ano}"] = [
                sigla, str(m.get("numero") or ""), " ".join((m.get("assunto") or "").split())[:EMENTA],
                m.get("dataPublicacao") or f"{ano}-01-01", autores]
    return {"projetos": projetos, "contagem": contagem}


def ler_verba_almg(notas_por_deputado: dict[str, list[dict]]) -> tuple[dict[str, dict], dict[str, str]]:
    """A verba indenizatória de um ano por deputado, como a cota dos federais (categorias, meses, fornecedores com
    CNPJ e a pessoa física só somada), e os nomes dos CNPJs. ``notas_por_deputado``: as linhas da API (uma por
    categoria e mês, com as notas em ``listaDetalheVerba``)."""
    verba: dict[str, dict] = {}
    nomes: dict[str, str] = {}
    for pid, linhas in notas_por_deputado.items():
        for linha in linhas:
            for n in linha.get("listaDetalheVerba") or []:
                valor = float(n.get("valorReembolsado") or 0)
                c = verba.setdefault(pid, {"categorias": {}, "meses": {}, "fornecedores": {}, "pf": [0, 0.0]})
                categoria = (n.get("descTipoDespesa") or linha.get("descTipoDespesa") or "").strip()
                c["categorias"][categoria] = c["categorias"].get(categoria, 0.0) + valor
                mes = ((n.get("dataReferencia") or {}).get("$") or "")[5:7] or "00"
                c["meses"][mes] = c["meses"].get(mes, 0.0) + valor
                documento = "".join(x for x in (n.get("cpfCnpj") or "") if x.isdigit())
                if len(documento) == 14 and cnpj_valido(documento):
                    f = c["fornecedores"].setdefault(documento, [0, 0.0])
                    f[0] += 1
                    f[1] += valor
                    if n.get("nomeEmitente"):
                        nomes[documento] = mascarar_cpfs_no_texto(n["nomeEmitente"].strip())
                else:
                    c["pf"][0] += 1
                    c["pf"][1] += valor
    r2 = lambda v: round(v, 2)  # noqa: E731
    return ({p: {"categorias": {k: r2(v) for k, v in sorted(c["categorias"].items())},
                 "meses": {k: r2(v) for k, v in sorted(c["meses"].items())},
                 "fornecedores": {k: [n, r2(v)] for k, (n, v) in sorted(c["fornecedores"].items())},
                 "pf": [c["pf"][0], r2(c["pf"][1])]} for p, c in sorted(verba.items())},
            dict(sorted(nomes.items())))


def _coletar_almg(c: dict, *, contato: str, hoje: date, ler_fn: Callable[[str], Any] | None) -> dict:
    """Minas Gerais: os deputados, as proposições e a verba dos anos que passaram da idade de releitura."""
    c["host"] = CASAS_ALMG["31"]["host"]
    deputados = dict(c.get("deputados") or {})
    for caminho, chave_lista in (("deputados/em_exercicio", "list"), ("deputados/que_exerceram_mandato", "listaDeputado")):
        for d in (_almg(caminho, contato=contato, ler_fn=ler_fn) or {}).get(chave_lista) or []:
            nome = (d.get("nome") or "").strip()
            deputados[str(d["id"])] = [nome, nome, (d.get("partido") or "").strip(),
                                       "Em exercício" if caminho.endswith("exercicio") else "Exerceu o mandato"]
    c["deputados"] = deputados
    tipos = sorted({(x.get("sigla") or "").strip() for x in (_almg("proposicoes/tipos", contato=contato,
                                                                   ler_fn=ler_fn) or {}).get("list") or []
                    if x.get("pesquisaDirigida") == "S" and x.get("sigla")})
    lidos: list[str] = []
    for ano in range(PRIMEIRO_ANO, hoje.year + 1):
        if tce.precisa_ler_por_idade(c["materias"].get(str(ano)), ano, hoje):
            # A API não pagina além de 10 mil linhas por consulta (2025 teve 14.225 proposições): uma por tipo
            linhas: list[dict] = []
            for sigla in tipos:
                do_tipo: list[dict] = []
                pagina = 1
                while True:
                    r = (_almg("proposicoes/pesquisa/direcionada", contato=contato, ler_fn=ler_fn, tp=100, p=pagina,
                               ano=ano, tipo=sigla) or {}).get("resultado") or {}
                    lote = r.get("listaItem") or []
                    do_tipo.extend(lote)
                    if not lote or len(do_tipo) >= int(r.get("noOcorrencias") or 0):
                        break
                    pagina += 1
                linhas.extend(do_tipo)
            c["materias"][str(ano)] = {"lido_em": instante_utc(), **ler_proposicoes_almg(linhas, deputados, ano)}
            lidos.append(f"proposicoes-{ano}")
        if tce.precisa_ler_por_idade(c["verbas"].get(str(ano)), ano, hoje):
            meses = range(1, (hoje.month if ano == hoje.year else 12) + 1)
            notas = {pid: [linha for mes in meses for linha in
                           (_almg(f"prestacao_contas/verbas_indenizatorias/deputados/{pid}/{ano}/{mes}",
                                  contato=contato, ler_fn=ler_fn) or {}).get("list") or []]
                     for pid in sorted(deputados)}
            verba, nomes = ler_verba_almg(notas)
            c["verbas"][str(ano)] = {"lido_em": instante_utc(), "verba": verba, "fornecedores": nomes}
            lidos.append(f"verba-{ano}")
    c["lido_em"] = instante_utc()
    return {"lidos": lidos, "problemas": []}


# ------------------------------------------------------------------------------------------ São Paulo

def _elementos(arquivo: Any, tag: str) -> Any:
    """Os elementos ``tag`` de um XML, um de cada vez (``iterparse``), cada um com os filhos num dicionário."""
    for _, el in ET.iterparse(arquivo):
        if el.tag == tag:
            yield {f.tag: (f.text or "").strip() for f in el}
            el.clear()


def ler_alesp(deputados_xml: Any, naturezas_xml: Any, proposituras_xml: Any, autores_xml: Any, despesas_xml: Any,
              *, primeiro_ano: int = PRIMEIRO_ANO) -> dict[str, Any]:
    """Os arquivos da ALESP (abertos, em XML) no estado da Assembleia: os deputados (``{IdSPL: [nome, nome, partido,
    situação]}``), as proposituras por ano (projetos e contagem) e a verba de gabinete por ano."""
    deputados: dict[str, list] = {}
    por_matricula: dict[str, str] = {}
    for d in _elementos(deputados_xml, "Deputado"):
        if d.get("IdSPL"):
            deputados[d["IdSPL"]] = [d.get("NomeParlamentar", ""), d.get("NomeParlamentar", ""), d.get("Partido", ""),
                                     d.get("Situacao", "")]
            if d.get("Matricula"):
                por_matricula[d["Matricula"]] = d["IdSPL"]
    # A raiz do arquivo de naturezas também se chama "natureza": fica só o elemento com o id
    siglas = {n["idNatureza"]: n.get("sgNatureza") or n["idNatureza"] for n in _elementos(naturezas_xml, "natureza")
              if n.get("idNatureza")}
    documentos: dict[str, list] = {}
    for m in _elementos(proposituras_xml, "propositura"):
        dia = (m.get("DtPublicacao") or "")[:10]
        if dia >= f"{primeiro_ano}-01-01":
            documentos[m["IdDocumento"]] = [m.get("IdNatureza", ""), m.get("NroLegislativo", ""),
                                            m.get("AnoLegislativo", ""), " ".join(m.get("Ementa", "").split())[:EMENTA],
                                            dia]
    autores: dict[str, set] = {}
    for a in _elementos(autores_xml, "DocumentoAutor"):
        if a.get("IdDocumento") in documentos and a.get("IdAutor") in deputados:
            autores.setdefault(a["IdDocumento"], set()).add(a["IdAutor"])
    materias: dict[str, dict] = {}
    for doc, (natureza, numero, _, ementa, dia) in documentos.items():
        ano = materias.setdefault(dia[:4], {"projetos": {}, "contagem": {}})
        sigla = " ".join(siglas.get(natureza, natureza).split())
        quem = sorted(autores.get(doc, ()))
        for pid in quem:
            por_tipo = ano["contagem"].setdefault(pid, {})
            por_tipo[sigla] = por_tipo.get(sigla, 0) + 1
        if natureza in NATUREZAS_PROJETO:
            ano["projetos"][doc] = [sigla, numero, ementa, dia, quem]
    notas: dict[str, dict[str, list]] = {}
    for n in _elementos(despesas_xml, "despesa"):
        pid = por_matricula.get(n.get("Matricula", ""))
        if not pid or int(n.get("Ano") or 0) < primeiro_ano:
            continue
        notas.setdefault(n["Ano"], {}).setdefault(pid, []).append({"listaDetalheVerba": [{
            "valorReembolsado": n.get("Valor"), "dataReferencia": {"$": f"{n['Ano']}-{int(n.get('Mes') or 0):02d}-01"},
            "cpfCnpj": n.get("CNPJ"), "nomeEmitente": n.get("Fornecedor"), "descTipoDespesa": n.get("Tipo")}]})
    verbas = {}
    for ano, por_deputado in notas.items():
        verba, nomes = ler_verba_almg(por_deputado)
        verbas[ano] = {"verba": verba, "fornecedores": nomes}
    return {"deputados": deputados, "materias": materias, "verbas": verbas}


def _coletar_alesp(c: dict, *, contato: str, abrir_fn: Callable[[str], Any] | None) -> dict:
    """São Paulo: baixa os cinco arquivos (os ZIPs, para uma pasta temporária) e lê tudo de novo."""
    c["host"] = CASAS_ALESP["35"]["host"]
    with tempfile.TemporaryDirectory() as pasta, contextlib.ExitStack() as abertos:
        def abrir(caminho: str) -> Any:
            """O arquivo XML de ``caminho`` (um ``.zip`` com um XML dentro, ou o XML), aberto para leitura e fechado
            antes de a pasta temporária ser apagada."""
            if abrir_fn:
                return abrir_fn(caminho)
            destino = Path(pasta) / caminho.replace("/", "_")
            baixar_inteiro(f"{ALESP}/{caminho}", destino, contato=contato)
            if caminho.endswith(".zip"):
                z = abertos.enter_context(zipfile.ZipFile(destino))
                return abertos.enter_context(z.open(z.infolist()[0]))
            return abertos.enter_context(open(destino, "rb"))
        lido = ler_alesp(abrir("deputados/deputados.xml"), abrir("processo_legislativo/naturezasSpl.xml"),
                         abrir("processo_legislativo/proposituras.zip"),
                         abrir("processo_legislativo/documento_autor.zip"), abrir("deputados/despesas_gabinetes.xml"))
    agora = instante_utc()
    c["deputados"] = lido["deputados"]
    c["materias"] = {a: {"lido_em": agora, **m} for a, m in lido["materias"].items()}
    c["verbas"] = {a: {"lido_em": agora, **v} for a, v in lido["verbas"].items()}
    c["lido_em"] = agora
    return {"lidos": sorted(lido["materias"]), "problemas": []}


def coletar_casa(c: dict, codigo: str, *, contato: str, hoje: date,
                 ler_fn: Callable[[str], Any] | None = None, abrir_fn: Callable[[str], Any] | None = None) -> dict:
    """Lê uma Assembleia sobre o estado ``c`` (alterado no lugar): os deputados, as proposições, os votos e a verba
    dos anos que passaram da idade de releitura. Devolve o resumo."""
    c.setdefault("materias", {})
    c.setdefault("votacoes", {})
    c.setdefault("verbas", {})
    if codigo in CASAS_ALMG:
        return _coletar_almg(c, contato=contato, hoje=hoje, ler_fn=ler_fn)
    if codigo in CASAS_ALESP:
        return _coletar_alesp(c, contato=contato, abrir_fn=abrir_fn)
    config = CASAS_SPL[codigo]
    host = config["host"]
    c["host"] = host
    c["deputados"] = ler_deputados(_paginas(host, "parlamentar", "parlamentares", contato=contato, ler_fn=ler_fn))
    lidos, problemas = [], []
    for ano in range(PRIMEIRO_ANO, hoje.year + 1):
        if tce.precisa_ler_por_idade(c["materias"].get(str(ano)), ano, hoje):
            linhas = _paginas(host, "proposicao", "Data", contato=contato, ler_fn=ler_fn, ano=ano)
            c["materias"][str(ano)] = {"lido_em": instante_utc(), **ler_proposicoes(linhas, c["deputados"], ano)}
            lidos.append(f"proposicoes-{ano}")
        if config.get("votos") and tce.precisa_ler_por_idade(c["votacoes"].get(str(ano)), ano, hoje):
            base = config["votos"]
            meses = range(1, (hoje.month if ano == hoje.year else 12) + 1)
            detalhes = [v for mes in meses for v in _json(f"{base}/votacoes.json?tipo=detalhes&ano={ano}&mes={mes}",
                                                          contato=contato, ler_fn=ler_fn) or []]
            resumo = [v for mes in meses for v in _json(f"{base}/votacoes.json?tipo=resumo&ano={ano}&mes={mes}",
                                                        contato=contato, ler_fn=ler_fn) or []]
            votacoes, sem_deputado = ler_votacoes_go(detalhes, resumo, c["deputados"])
            c["votacoes"][str(ano)] = {"lido_em": instante_utc(), "votacoes": votacoes}
            lidos.append(f"votos-{ano}")
            if sem_deputado:
                problemas.append(f"{ano}: {sem_deputado} voto(s) sem deputado no cadastro")
    c["lido_em"] = instante_utc()
    return {"lidos": lidos, "problemas": problemas}


# ------------------------------------------------------------------------------------------ coleta

def ler_estado(estado: Path | str) -> dict[str, dict]:
    """As Assembleias já lidas (vazio se ainda não houve coleta)."""
    caminho = Path(estado) / ARQUIVO
    if not caminho.exists():
        return {}
    dados = ler_json(caminho)
    if dados.get("versao") != VERSAO_ESTADO:
        raise ValueError(f"{caminho}: versão {dados.get('versao')!r} do estado das Assembleias não suportada")
    return dados["casas"]


def coletar(estado: Path | str, *, contato: str, hoje: date | None = None, casas: list[str] | None = None,
            ler_fn: Callable[[str], Any] | None = None, abrir_fn: Callable[[str], Any] | None = None) -> dict:
    """Lê as Assembleias de ``CASAS_SPL`` (ou as pedidas), uma por vez em paralelo, e grava ``ARQUIVO``."""
    hoje = hoje or datetime.now(timezone.utc).date()
    todas = ler_estado(estado)
    pedidas = [c for c in [*CASAS_SPL, *CASAS_ALMG, *CASAS_ALESP] if not casas or c in casas]

    def uma(codigo: str) -> tuple[str, dict, dict | str]:
        """Lê uma Assembleia: o estado e o resumo, ou o erro (o estado anterior fica)."""
        c = json.loads(json.dumps(todas.get(codigo) or {"materias": {}, "votacoes": {}, "verbas": {}}))
        try:
            return codigo, c, coletar_casa(c, codigo, contato=contato, hoje=hoje, ler_fn=ler_fn, abrir_fn=abrir_fn)
        except Exception as erro:  # noqa: BLE001 — Assembleia fora do ar: fica a leitura anterior
            return codigo, c, f"{type(erro).__name__}: {erro}"[:200]

    resumo: dict[str, Any] = {}
    with ThreadPoolExecutor(len(pedidas) or 1) as grupo:
        for codigo, c, r in grupo.map(uma, pedidas):
            if isinstance(r, str):
                resumo[codigo] = {"erro": r}
            else:
                todas[codigo] = c
                resumo[codigo] = r
    Path(estado).mkdir(parents=True, exist_ok=True)
    gravar_json(Path(estado) / ARQUIVO, {"versao": VERSAO_ESTADO, "fonte": FONTE, "gravado_em": instante_utc(),
                                         "casas": dict(sorted(todas.items()))}, comprimir=True)
    return resumo


# ------------------------------------------------------------------------------------------ publicação

def montar(c: dict, uf: str) -> dict:
    """O estado de uma Assembleia no formato da publicação comum (``camara.publicar_casa``)."""
    anos: dict[str, dict] = {}

    def ano_de(ano: str) -> dict:
        return anos.setdefault(ano, {"votacoes": {}, "votos": {}, "partidos": {}, "sessoes": {}, "presencas": {},
                                     "autoria": {}, "contagem": {}, "ceap": {}, "fornecedores": {}})

    for ano, a in c["materias"].items():
        for mid, (sigla, numero, ementa, dia, autores) in a["projetos"].items():
            for p in autores:
                ano_de(dia[:4])["autoria"].setdefault(p, []).append([mid, sigla, numero, ano, ementa, dia, None])
        if a["contagem"]:
            ano_de(ano)["contagem"].update(a["contagem"])
    for ano, a in c["votacoes"].items():
        for pauta, (dia, processo, ementa, resultado, aprovacao, votos, partidos) in a["votacoes"].items():
            if not votos:
                continue
            codigos = list(votos.values())
            destino = ano_de((dia or ano)[:4])
            destino["votacoes"][pauta] = [dia, processo, ementa, resultado, aprovacao, codigos.count("S"),
                                          codigos.count("N"), sum(1 for x in codigos if x not in ("S", "N")), None,
                                          None]
            for p, voto in votos.items():
                destino["votos"].setdefault(p, {})[pauta] = voto
                destino["partidos"].setdefault(pauta, {})[p] = partidos.get(p, "")
    for ano, a in (c.get("verbas") or {}).items():
        if a["verba"]:
            ano_de(ano)["ceap"].update(a["verba"])
            ano_de(ano)["fornecedores"].update(a["fornecedores"])
    for a in anos.values():
        a["autoria"] = {p: sorted(v, key=lambda x: (x[5], x[0])) for p, v in a["autoria"].items()}
    deputados = {p: [nome, partido, uf, [PRIMEIRO_ANO]] for p, (nome, _, partido, _) in c["deputados"].items()}
    return {"fonte": f"{FONTE}: {c['host']}", "coletado_em": c.get("lido_em"), "deputados": deputados,
            "exercicio": {}, "anos": dict(sorted(anos.items()))}


def publicar(estado: Path | str, cadastro: Cadastro, gravar: Callable[[str, Any], Any], *,
             gerado_em: str) -> list[list]:
    """Grava ``parlamentares/estadual/<código>/`` de cada Assembleia lida e devolve as linhas do índice das
    Assembleias (``[código, estado, UF, endereço, deputados, votações, anos, sistema]``)."""
    legislaturas, no_mandato_fn, _, pessoa = ESFERAS["estadual"]
    linhas = []
    for codigo, c in sorted(ler_estado(estado).items()):
        uf = cadastro.entes[codigo].uf if codigo in cadastro.entes else ""
        dados = montar(c, uf)
        if not dados["anos"] or not dados["deputados"]:
            continue
        r = publicar_casa(dados, gravar, gerado_em=gerado_em, casa=f"estadual/{codigo}", pessoa=pessoa,
                          legislaturas=legislaturas, no_mandato_fn=no_mandato_fn)
        votacoes = sum(len(a["votacoes"]) for a in dados["anos"].values())
        linhas.append([codigo, cadastro.nome(codigo), uf, c["host"], r["deputados"], votacoes, r["anos"],
                       "almg" if codigo in CASAS_ALMG else "alesp" if codigo in CASAS_ALESP else "spl"])
    return linhas
