"""Os deputados estaduais pelas fontes próprias das Assembleias Legislativas (ADR-062, adendo 2): por enquanto, as que
usam o SPL da Ágape Consultoria, que tem uma API pública comum (``/api/publico/``), e os votos nominais de Goiás.

As Assembleias com o SAPL do Interlegis vão pela coleta dos vereadores (``vereadores.py``). As outras publicam cada
uma do seu jeito; o levantamento de 4/11/2026 achou o SPL da Ágape em quatro (``CASAS_SPL``: GO, ES, SE e BA):

- ``/api/publico/parlamentar/?pag=&qtd=``: os deputados da legislatura atual, com o partido (a API não traz as
  anteriores; por isso a coleta começa em ``PRIMEIRO_ANO``, o início da legislatura de 2023);
- ``/api/publico/proposicao/?pag=&qtd=&ano=``: as proposições do ano, com o tipo, a ementa e o autor pelo nome (e o
  gabinete). O autor é ligado ao deputado pelo nome; os documentos (CPF) e os contatos que a API traz não são
  guardados. Os projetos (o tipo começa por "projeto" ou é proposta de emenda) ficam com a ementa; os outros tipos
  são só contados;
- em Goiás, ``transparencia.al.go.leg.br/api/transparencia/votacoes.json?tipo=detalhes&ano=&todos=true``: o voto de
  cada deputado nas votações nominais do Plenário, com o partido no dia, de 2023 em diante; ``tipo=resumo`` dá o
  processo votado. O voto vem com o nome do deputado, às vezes repetido em maiúsculas: fica um por deputado.

Não há presença em nenhuma delas: o detalhe da sessão do SPL, que traria as presenças, respondeu erro em 4/11/2026.
O estado fica em ``assembleias.json.gz``; o ano fechado é relido uma vez por mês e o corrente e o anterior, uma vez
por semana (``tce.precisa_ler_por_idade``). A publicação é a dos deputados federais (``camara.publicar_casa``), em
``parlamentares/estadual/<código da UF>/``, e as linhas entram no índice das Assembleias (``vereadores.publicar``).
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

from . import tce
from .cadastro import Cadastro
from .camara import EMENTA, publicar_casa
from .comum import gravar_json, instante_utc, ler_json, sem_acento
from .vereadores import ESFERAS, e_projeto

FONTE = "Assembleias Legislativas, API pública do SPL (Ágape) e transparência da Alego"
ARQUIVO = "assembleias.json.gz"
VERSAO_ESTADO = 1
PRIMEIRO_ANO = 2023
POR_PAGINA = 500
# Código IBGE da UF → endereço do SPL e se há votos nominais pela transparência (só Goiás)
CASAS_SPL: dict[str, dict[str, Any]] = {
    "52": {"host": "alegodigital.al.go.leg.br", "votos": "https://transparencia.al.go.leg.br/api/transparencia"},
    "32": {"host": "www3.al.es.gov.br"},
    "28": {"host": "aleselegis.al.se.leg.br"},
    "29": {"host": "albalegis.nopapercloud.com.br"},
}
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


def coletar_casa(c: dict, codigo: str, *, contato: str, hoje: date,
                 ler_fn: Callable[[str], Any] | None = None) -> dict:
    """Lê uma Assembleia sobre o estado ``c`` (alterado no lugar): os deputados, as proposições e os votos dos anos
    que passaram da idade de releitura. Devolve o resumo."""
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
            detalhes = _json(f"{base}/votacoes.json?tipo=detalhes&ano={ano}&todos=true", contato=contato,
                             ler_fn=ler_fn) or []
            resumo = _json(f"{base}/votacoes.json?tipo=resumo&ano={ano}&todos=true", contato=contato,
                           ler_fn=ler_fn) or []
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
            ler_fn: Callable[[str], Any] | None = None) -> dict:
    """Lê as Assembleias de ``CASAS_SPL`` (ou as pedidas), uma por vez em paralelo, e grava ``ARQUIVO``."""
    hoje = hoje or datetime.now(timezone.utc).date()
    todas = ler_estado(estado)
    pedidas = [c for c in CASAS_SPL if not casas or c in casas]

    def uma(codigo: str) -> tuple[str, dict, dict | str]:
        """Lê uma Assembleia: o estado e o resumo, ou o erro (o estado anterior fica)."""
        c = json.loads(json.dumps(todas.get(codigo) or {"materias": {}, "votacoes": {}}))
        try:
            return codigo, c, coletar_casa(c, codigo, contato=contato, hoje=hoje, ler_fn=ler_fn)
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
        linhas.append([codigo, cadastro.nome(codigo), uf, c["host"], r["deputados"], votacoes, r["anos"], "spl"])
    return linhas
