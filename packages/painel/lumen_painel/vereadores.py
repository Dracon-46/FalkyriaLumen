"""Os vereadores pelo SAPL do Interlegis (ADR-062): mandatos e partidos, projetos apresentados, presença nas sessões e
o voto de cada vereador nas votações nominais dos projetos, de 2017 em diante (os mandatos de 2017, 2021 e 2025).

As câmaras são as do levantamento (``camaras.py``). A API do SAPL (``/api/``) pagina de 100 em 100, em ordem
crescente de id, e não filtra por data nem por id; filtra as matérias por ano, os votos por votação e as pautas por
matéria. De cada câmara, a coleta lê:

- ``parlamentares/parlamentar``, ``mandato``, ``filiacao`` e ``partido``: os vereadores, os períodos de mandato e o
  partido em cada data; ``base/autor`` liga o autor da matéria ao vereador (o autor do tipo "Parlamentar");
- ``materia/materialegislativa?ano=AAAA``: as matérias de cada ano com os autores. As dos tipos de projeto (projetos
  de lei, de lei complementar, de decreto legislativo e de resolução e emendas à Lei Orgânica, pela descrição do
  tipo, que cada câmara cadastra do seu jeito) ficam com a ementa; as demais (requerimentos, indicações, moções) são
  só contadas por tipo. O ano corrente e o anterior são relidos a cada coleta da câmara; os outros, uma vez;
- ``sessao/sessaoplenaria`` e ``sessaoplenariapresenca``: as sessões e quem esteve nelas. A presença conta só as
  sessões com alguma presença registrada, para não pesar contra o vereador a sessão que a câmara não registrou;
- ``sessao/registrovotacao``: as votações, lidas a partir da página em que a leitura anterior parou. Ficam as dos
  projetos; de cada uma, os votos (``votoparlamentar?votacao=``) e a data, pela pauta (``ordemdia`` e
  ``expedientemateria`` da matéria). Votação sem voto por vereador (simbólica) fica registrada, sem votos, e não é
  publicada.

O estado fica num arquivo por UF (``vereadores-<UF>.json.gz``), com as câmaras do estado. Cada câmara é relida no
máximo uma vez a cada ``DIAS_ENTRE_COLETAS`` dias; a que não termina no prazo guarda o que leu e continua na próxima.
A publicação usa a dos deputados e senadores (``camara.publicar_casa``), em ``parlamentares/municipal/<IBGE>/``.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from . import camaras, tce
from .cadastro import Cadastro
from .camara import EMENTA, publicar_casa
from .comum import gravar_json, instante_utc, ler_json, sem_acento

FONTE = "Câmaras municipais, SAPL do Interlegis (sapl.<cidade>.<uf>.leg.br/api)"
ARQUIVO = "vereadores-{uf}.json.gz"
VERSAO_ESTADO = 1
PRIMEIRO_ANO = 2017
LEGISLATURAS = {2017: (2017, 2020), 2021: (2021, 2024), 2025: (2025, 2028)}
POR_PAGINA = 100
DIAS_ENTRE_COLETAS = 6
SIMULTANEOS = 8
GRAVAR_A_CADA = 300                 # segundos entre as gravações do estado durante a coleta
VOTOS = {"Sim": "S", "Não": "N", "Abstenção": "A"}
PROJETO = re.compile(r"^projeto|^(proposta de )?emenda (a )?(lei )?organica")


class _Prazo(Exception):
    """O prazo da coleta acabou no meio de uma câmara."""


def no_mandato(dia: str, legislaturas: Iterable[int]) -> bool:
    """Se o dia cai num dos mandatos municipais do vereador (de 1º de janeiro a 31 de dezembro do quarto ano)."""
    return any(f"{n}-01-01" <= dia <= f"{n + 3}-12-31" for n in legislaturas)


def e_projeto(descricao: str | None) -> bool:
    """Se o tipo de matéria é de projeto, pela descrição ("Projeto de Lei (Executivo)", "emenda a lei organica"); as
    emendas a projeto, os requerimentos e as indicações não são."""
    return bool(PROJETO.search(" ".join(sem_acento(descricao or "").lower().split())))


# ------------------------------------------------------------------------------------------ a API

class Api:
    """Os pedidos à API do SAPL de uma câmara, com o prazo da coleta."""

    def __init__(self, host: str, *, contato: str, ler_fn: Callable[[str], Any] | None = None,
                 prazo: float | None = None, relogio: Callable[[], float] = time.monotonic):
        """A câmara (``host``), o contato do User-Agent e o prazo (no relógio ``relogio``); ``ler_fn`` substitui a rede
        nos testes."""
        self.host, self.contato, self.ler_fn, self.prazo, self.relogio = host, contato, ler_fn, prazo, relogio
        self.pedidos = 0

    def obter(self, caminho: str, **filtros: Any) -> dict:
        """Uma página da API (``caminho`` como ``sessao/votoparlamentar``), em JSON."""
        if self.prazo is not None and self.relogio() >= self.prazo:
            raise _Prazo()
        url = f"https://{self.host}/api/{caminho}/?{urllib.parse.urlencode(filtros)}"
        self.pedidos += 1
        if self.ler_fn:
            return self.ler_fn(url)
        pedido = urllib.request.Request(url, headers={**tce.cabecalhos(self.contato), "Accept": "application/json"})
        with tce.abrir(pedido, tentativas=3) as r:
            return json.loads(r.read())

    def retomar(self, caminho: str, pagina: int, **filtros: Any) -> tuple[dict, int]:
        """A página em que a leitura anterior parou e o número dela. Se a página não existe mais (a câmara apagou
        linhas e o total encolheu: a API responde 404), volta à primeira."""
        try:
            return self.obter(caminho, page=pagina, page_size=POR_PAGINA, **filtros), pagina
        except urllib.error.HTTPError as erro:
            if erro.code != 404 or pagina == 1:
                raise
        return self.obter(caminho, page=1, page_size=POR_PAGINA, **filtros), 1

    def listar(self, caminho: str, *, desde: int = 0, **filtros: Any) -> tuple[list[dict], int]:
        """As linhas a partir da página da linha ``desde`` (a página em que a leitura anterior parou, relida inteira)
        e o total de linhas."""
        dados, pagina = self.retomar(caminho, desde // POR_PAGINA + 1, **filtros)
        linhas: list[dict] = []
        while True:
            linhas.extend(dados.get("results") or [])
            if not (dados.get("pagination") or {}).get("next_page"):
                return linhas, (dados.get("pagination") or {}).get("total_entries") or 0
            pagina += 1
            dados = self.obter(caminho, page=pagina, page_size=POR_PAGINA, **filtros)


# ------------------------------------------------------------------------------------------ uma câmara

def _cadastro(api: Api, c: dict) -> None:
    """Os vereadores, os mandatos, as filiações (com a sigla do partido) e os autores que são vereadores."""
    c["parlamentares"] = {str(p["id"]): (p.get("nome_parlamentar") or p.get("nome_completo") or "").strip()
                          for p in api.listar("parlamentares/parlamentar")[0]}
    mandatos: dict[str, list] = {}
    for m in api.listar("parlamentares/mandato")[0]:
        if m.get("data_inicio_mandato"):
            mandatos.setdefault(str(m["parlamentar"]), []).append([m["data_inicio_mandato"], m.get("data_fim_mandato")])
    c["mandatos"] = {p: sorted(v) for p, v in mandatos.items()}
    siglas = {p["id"]: (p.get("sigla") or "").strip() for p in api.listar("parlamentares/partido")[0]}
    filiacoes: dict[str, list] = {}
    for f in api.listar("parlamentares/filiacao")[0]:
        if f.get("data") and siglas.get(f.get("partido")):
            filiacoes.setdefault(str(f["parlamentar"]), []).append(
                [f["data"], f.get("data_desfiliacao"), siglas[f["partido"]]])
    c["filiacoes"] = {p: sorted(v) for p, v in filiacoes.items()}
    tipos = {t["content_type"] for t in api.listar("base/tipoautor")[0]
             if sem_acento(t.get("descricao") or "").strip().lower() == "parlamentar" and t.get("content_type")}
    c["autores"] = {str(a["id"]): str(a["object_id"]) for a in api.listar("base/autor")[0]
                    if a.get("content_type") in tipos and str(a.get("object_id")) in c["parlamentares"]}


def _materias(api: Api, c: dict, hoje: date) -> None:
    """As matérias de cada ano (o corrente e o anterior sempre; os outros, só se nunca lidos): os projetos com a
    ementa e os autores, e a contagem de todas por tipo e vereador."""
    tipos = {t["id"]: [(t.get("sigla") or "").strip(), e_projeto(t.get("descricao"))]
             for t in api.listar("materia/tipomaterialegislativa")[0]}
    for ano in range(PRIMEIRO_ANO, hoje.year + 1):
        if str(ano) in c["materias"] and ano < hoje.year - 1:
            continue
        projetos, contagem = {}, {}
        for m in api.listar("materia/materialegislativa", ano=ano)[0]:
            sigla, projeto = tipos.get(m.get("tipo"), ["?", False])
            autores = sorted({c["autores"][str(a)] for a in m.get("autores") or [] if str(a) in c["autores"]})
            for p in autores:
                por_tipo = contagem.setdefault(p, {})
                por_tipo[sigla] = por_tipo.get(sigla, 0) + 1
            if projeto:
                projetos[str(m["id"])] = [sigla, m.get("numero"), " ".join((m.get("ementa") or "").split())[:EMENTA],
                                          m.get("data_apresentacao") or f"{ano}-01-01", autores]
        c["materias"][str(ano)] = {"lido_em": instante_utc(), "projetos": projetos, "contagem": contagem}


def _presenca(api: Api, c: dict) -> None:
    """As sessões de 2017 em diante e a presença, a partir da página em que a leitura anterior parou."""
    c["sessoes"] = {str(s["id"]): s["data_inicio"] for s in api.listar("sessao/sessaoplenaria")[0]
                    if (s.get("data_inicio") or "") >= f"{PRIMEIRO_ANO}-01-01"}
    p = c["presencas"]
    linhas, total = api.listar("sessao/sessaoplenariapresenca", desde=p["lidas"])
    por_sessao = {s: set(v) for s, v in p["por_sessao"].items()}
    for linha in linhas:
        sessao = str(linha.get("sessao_plenaria"))
        if sessao in c["sessoes"]:
            por_sessao.setdefault(sessao, set()).add(str(linha.get("parlamentar")))
    p["por_sessao"] = {s: sorted(v) for s, v in sorted(por_sessao.items())}
    p["lidas"] = total


def _votacoes(api: Api, c: dict) -> None:
    """As votações dos projetos, a partir da página em que a leitura anterior parou: a data pela pauta, o resultado e
    os votos. O contador só anda depois que a página inteira foi lida."""
    projetos = {m for a in c["materias"].values() for m in a["projetos"]}
    resultados = {t["id"]: [t.get("nome") or "", {"A": 1, "R": 0}.get(t.get("natureza"))]
                  for t in api.listar("sessao/tiporesultadovotacao")[0]}
    pautas: dict[str, dict[str, str]] = {}
    dados, pagina = api.retomar("sessao/registrovotacao", c["registros_lidos"] // POR_PAGINA + 1)
    while True:
        for r in dados.get("results") or []:
            vid, materia = str(r["id"]), str(r.get("materia"))
            if materia not in projetos or vid in c["votacoes"]:
                continue
            votos = {str(v["parlamentar"]): VOTOS.get(v.get("voto") or "", v.get("voto") or "-")
                     for v in api.listar("sessao/votoparlamentar", votacao=vid)[0]}
            data = None
            if votos:  # a votação simbólica não é publicada: dispensa a pauta
                if materia not in pautas:
                    pautas[materia] = {
                        **{f"o{o['id']}": o.get("data_ordem")
                           for o in api.listar("sessao/ordemdia", materia=materia)[0]},
                        **{f"e{e['id']}": e.get("data_ordem")
                           for e in api.listar("sessao/expedientemateria", materia=materia)[0]}}
                data = (pautas[materia].get(f"o{r.get('ordem')}") or pautas[materia].get(f"e{r.get('expediente')}")
                        or (r.get("data_hora") or "")[:10])
            nome, aprovacao = resultados.get(r.get("tipo_resultado_votacao"), ["", None])
            c["votacoes"][vid] = [materia, data, nome, aprovacao, votos]
        pag = dados.get("pagination") or {}
        c["registros_lidos"] = (pag.get("total_entries") or 0) if not pag.get("next_page") else pagina * POR_PAGINA
        if not pag.get("next_page"):
            return
        pagina += 1
        dados = api.obter("sessao/registrovotacao", page=pagina, page_size=POR_PAGINA)


def vazia(host: str) -> dict:
    """O estado de uma câmara ainda não lida."""
    return {"host": host, "lido_em": None, "parlamentares": {}, "mandatos": {}, "filiacoes": {}, "autores": {},
            "materias": {}, "sessoes": {}, "presencas": {"lidas": 0, "por_sessao": {}}, "registros_lidos": 0,
            "votacoes": {}}


def coletar_camara(c: dict, api: Api, hoje: date) -> bool:
    """Lê uma câmara sobre o estado ``c`` (alterado no lugar). Devolve se terminou; no prazo, guarda o que leu (o
    cadastro, os anos de matérias, a presença e as votações até a última página inteira) e devolve ``False``."""
    try:
        _cadastro(api, c)
        _materias(api, c, hoje)
        _presenca(api, c)
        _votacoes(api, c)
    except _Prazo:
        return False
    c["lido_em"] = instante_utc()
    c.pop("falhou_em", None)
    c.pop("erro", None)
    return True


# ------------------------------------------------------------------------------------------ coleta

def ler_estado(estado: Path | str, uf: str) -> dict[str, dict]:
    """As câmaras de uma UF (vazio se ainda não houve coleta)."""
    caminho = Path(estado) / ARQUIVO.format(uf=uf)
    if not caminho.exists():
        return {}
    dados = ler_json(caminho)
    if dados.get("versao") != VERSAO_ESTADO:
        raise ValueError(f"{caminho}: versão {dados.get('versao')!r} do estado dos vereadores não suportada")
    return dados["camaras"]


def _gravar(estado: Path | str, uf: str, camaras_uf: dict[str, dict]) -> None:
    """Grava o arquivo das câmaras de uma UF."""
    Path(estado).mkdir(parents=True, exist_ok=True)
    gravar_json(Path(estado) / ARQUIVO.format(uf=uf), {"versao": VERSAO_ESTADO, "fonte": FONTE,
                                                       "gravado_em": instante_utc(),
                                                       "camaras": dict(sorted(camaras_uf.items()))}, comprimir=True)


def _idade(c: dict | None, hoje: date) -> int:
    """Dias desde a última coleta que terminou ou falhou (a interrompida pelo prazo não conta: continua logo)."""
    quando = max((x for x in ((c or {}).get("lido_em"), (c or {}).get("falhou_em")) if x), default=None)
    if not quando:
        return 10**6
    return (hoje - datetime.fromisoformat(quando.replace("Z", "+00:00")).date()).days


def coletar(estado: Path | str, cadastro: Cadastro, *, contato: str, hoje: date | None = None,
            ufs: list[str] | None = None, municipios: list[str] | None = None, limite_minutos: float | None = None,
            simultaneos: int = SIMULTANEOS, ler_fn: Callable[[str], Any] | None = None,
            relogio: Callable[[], float] = time.monotonic) -> dict:
    """Lê as câmaras do levantamento que passaram de ``DIAS_ENTRE_COLETAS`` dias (as nunca lidas primeiro, depois as
    mais antigas), algumas ao mesmo tempo, e grava o arquivo de cada UF. Devolve o resumo."""
    hoje = hoje or datetime.now(timezone.utc).date()
    prazo = relogio() + limite_minutos * 60 if limite_minutos else None
    hosts = {i: h for i, (h, n) in camaras.ler(estado).items() if n and i in cadastro.entes
             and (not ufs or cadastro.entes[i].uf in ufs) and (not municipios or i in municipios)}
    por_uf: dict[str, dict[str, dict]] = {}
    for i in hosts:
        uf = cadastro.entes[i].uf
        if uf not in por_uf:
            por_uf[uf] = ler_estado(estado, uf)
    fila = sorted((i for i in hosts if municipios
                   or _idade(por_uf[cadastro.entes[i].uf].get(i), hoje) >= DIAS_ENTRE_COLETAS),
                  key=lambda i: (-_idade(por_uf[cadastro.entes[i].uf].get(i), hoje), i))
    resumo: dict[str, Any] = {"camaras": len(hosts), "na_fila": len(fila), "lidas": [], "parciais": [],
                              "falhas": {}, "pedidos": 0, "interrompida": False}

    def uma(i: str) -> tuple[dict, str, int]:
        """Lê uma câmara: o estado e se foi ``lida``, ``parcial`` (o prazo acabou), ``pulada`` (acabou antes de
        começar) ou ``falha`` (com o que leu até o erro e o erro no estado)."""
        uf = cadastro.entes[i].uf
        c = json.loads(json.dumps(por_uf[uf].get(i) or vazia(hosts[i])))
        c["host"] = hosts[i]
        api = Api(hosts[i], contato=contato, ler_fn=ler_fn, prazo=prazo, relogio=relogio)
        if prazo is not None and relogio() >= prazo:
            return c, "pulada", 0
        try:
            return c, "lida" if coletar_camara(c, api, hoje) else "parcial", api.pedidos
        except Exception as erro:  # noqa: BLE001 — câmara fora do ar ou com a API quebrada: tenta de novo depois
            c["falhou_em"], c["erro"] = instante_utc(), f"{type(erro).__name__}: {erro}"[:200]
            return c, "falha", api.pedidos

    sujas: set[str] = set()
    ultima = relogio()
    with ThreadPoolExecutor(simultaneos) as grupo:
        futuros = {grupo.submit(uma, i): i for i in fila}
        for futuro in as_completed(futuros):
            i = futuros[futuro]
            uf = cadastro.entes[i].uf
            c, situacao, pedidos = futuro.result()
            if situacao == "pulada":
                resumo["interrompida"] = True
                continue
            resumo["pedidos"] += pedidos
            por_uf[uf][i] = c
            sujas.add(uf)
            if situacao == "falha":
                resumo["falhas"][i] = c["erro"]
            else:
                (resumo["lidas"] if situacao == "lida" else resumo["parciais"]).append(i)
            resumo["interrompida"] |= situacao == "parcial"
            if relogio() - ultima >= GRAVAR_A_CADA:
                for u in sorted(sujas):
                    _gravar(estado, u, por_uf[u])
                sujas, ultima = set(), relogio()
    for u in sorted(sujas):
        _gravar(estado, u, por_uf[u])
    resumo["ufs"] = sorted({cadastro.entes[i].uf for i in [*resumo["lidas"], *resumo["parciais"], *resumo["falhas"]]})
    return resumo


# ------------------------------------------------------------------------------------------ publicação

def _partido(filiacoes: list[list], dia: str) -> str:
    """A sigla do partido do vereador no dia (a filiação mais recente começada até o dia e não encerrada antes)."""
    sigla = ""
    for inicio, fim, s in filiacoes:
        if inicio <= dia and (not fim or dia <= fim):
            sigla = s
    return sigla


def montar(c: dict, uf: str) -> dict:
    """O estado de uma câmara no formato da publicação comum (``camara.publicar_casa``)."""
    hoje = instante_utc()[:10]
    projetos = {m: [a, *p] for a, ano in c["materias"].items() for m, p in ano["projetos"].items()}
    anos: dict[str, dict] = {}

    def ano_de(dia: str) -> dict:
        return anos.setdefault(dia[:4], {"votacoes": {}, "votos": {}, "partidos": {}, "sessoes": {}, "presencas": {},
                                         "autoria": {}, "contagem": {}, "ceap": {}, "fornecedores": {}})

    for vid, (materia, data, resultado, aprovacao, votos) in c["votacoes"].items():
        if not votos or not data or data < f"{PRIMEIRO_ANO}-01-01" or materia not in projetos:
            continue
        ano_m, sigla, numero, ementa, *_ = projetos[materia]
        codigos = list(votos.values())
        a = ano_de(data)
        a["votacoes"][vid] = [data, f"{sigla} {numero}/{ano_m}", ementa, resultado, aprovacao, codigos.count("S"),
                              codigos.count("N"), sum(1 for x in codigos if x not in ("S", "N")), None, materia]
        for p, voto in votos.items():
            a["votos"].setdefault(p, {})[vid] = voto
            a["partidos"].setdefault(vid, {})[p] = _partido(c["filiacoes"].get(p, []), data)
    for sessao, presentes in c["presencas"]["por_sessao"].items():
        data = c["sessoes"].get(sessao)
        if not data or not presentes:
            continue
        a = ano_de(data)
        a["sessoes"][sessao] = data
        for p in presentes:
            a["presencas"].setdefault(p, []).append(sessao)
    for materia, (ano_m, sigla, numero, ementa, apresentacao, autores) in projetos.items():
        for p in autores:
            ano_de(apresentacao)["autoria"].setdefault(p, []).append(
                [materia, sigla, str(numero or ""), ano_m, ementa, apresentacao, None])
    for ano_m, ano in c["materias"].items():
        if ano["contagem"]:
            ano_de(f"{ano_m}-01-01")["contagem"].update(ano["contagem"])
    for a in anos.values():
        a["autoria"] = {p: sorted(v, key=lambda x: (x[5], x[0])) for p, v in a["autoria"].items()}
    quem = set(c["mandatos"]) | {p for a in anos.values() for k in ("votos", "presencas", "autoria") for p in a[k]}
    vereadores = {}
    for p in quem:
        if p not in c["parlamentares"]:
            continue
        legislaturas = sorted({n for inicio, fim in c["mandatos"].get(p, [])
                               for n in LEGISLATURAS if inicio <= f"{n + 3}-12-31" and (fim or hoje) >= f"{n}-01-01"})
        if legislaturas or any(p in a[k] for a in anos.values() for k in ("votos", "autoria")):
            vereadores[p] = [c["parlamentares"][p], _partido(c["filiacoes"].get(p, []), hoje), uf, legislaturas]
    exercicio = {p: [[inicio, fim] for inicio, fim in c["mandatos"].get(p, [])] for p in vereadores}
    return {"fonte": f"{FONTE}: {c['host']}", "coletado_em": c["lido_em"], "deputados": vereadores,
            "exercicio": exercicio, "anos": dict(sorted(anos.items()))}


def publicar(estado: Path | str, cadastro: Cadastro, gravar: Callable[[str, Any], Any], *,
             gerado_em: str) -> dict | None:
    """Grava ``parlamentares/municipal/<IBGE>/`` de cada câmara com dados (como os deputados) e o índice das câmaras
    (``parlamentares/municipal/indice.json``); devolve o resumo para o índice do site."""
    arquivos = sorted(Path(estado).glob(ARQUIVO.format(uf="*")))
    if not arquivos:
        return None
    linhas = []
    for arquivo in arquivos:
        uf = arquivo.name.split("-")[1].split(".")[0]
        for ibge, c in ler_estado(estado, uf).items():
            if not c.get("lido_em") and not c.get("votacoes"):
                continue
            dados = montar(c, uf)
            if not dados["anos"] or not dados["deputados"]:
                continue
            r = publicar_casa(dados, gravar, gerado_em=gerado_em, casa=f"municipal/{ibge}", pessoa="vereador",
                              legislaturas=LEGISLATURAS, no_mandato_fn=no_mandato)
            votos = sum(len(a["votacoes"]) for a in dados["anos"].values())
            linhas.append([ibge, cadastro.nome(ibge), uf, c["host"], r["deputados"], votos, r["anos"]])
    gravar("parlamentares/municipal/indice.json", {
        "versao": 1, "tipo": "municipal-camaras", "gerado_em": gerado_em, "fonte": FONTE,
        "colunas": ["ibge", "nome", "uf", "host", "vereadores", "votacoes", "anos"],
        "camaras": sorted(linhas, key=lambda x: (x[2], x[1]))})
    return {"camaras": len(linhas), "vereadores": sum(x[4] for x in linhas)}
