"""Os senadores: votos nominais, presença nas votações, matérias de autoria e cota parlamentar, pelos dados abertos do
Senado Federal (ADR-060, adendo).

Fontes, sem chave:

- ``legis.senado.leg.br/dadosabertos/votacao?dataInicio=AAAA-01-01&dataFim=AAAA-12-31``: as votações do Plenário no
  ano (pela data da sessão; o parâmetro ``ano`` filtra pelo ano da matéria), cada uma com o voto de cada senador e o
  partido e a UF dele no dia. Ficam as nominais abertas (``votacaoSecreta`` = ``N``). O Senado decide muito por votação
  simbólica, sem voto por senador: em 2015, foram só 17 nominais;
- ``/senador/lista/legislatura/<n>``: os senadores de cada legislatura, e ``/senador/<código>/mandatos``: os períodos em
  exercício, para a presença;
- ``/processo?codigoParlamentarAutor=<código>``: as matérias de que o senador é autor ou coautor, de qualquer ano;
- ``senado.leg.br/transparencia/LAI/verba/despesa_ceaps_AAAA.csv``: a cota (CEAPS), uma linha por documento, com o
  nome do senador (sem código: liga pelo nome do cadastro), o tipo de despesa, o fornecedor e o valor reembolsado.

A presença, no Senado, é a presença nas votações nominais: em quantas, entre as realizadas enquanto o senador estava
em exercício, ele estava no Plenário (votou, estava presente sem votar, ``P-NRV``, ou presidia a sessão, que no Senado
não vota). Ausência, licença e missão não contam. O estado (``senado.json.gz``) tem o mesmo formato do
da Câmara, e a publicação é a mesma (``camara.publicar_casa``), em ``parlamentares/senado/``. A API não diz se o ano
mudou: o ano fechado é relido uma vez por mês e o corrente e o anterior, uma vez por semana.
"""

from __future__ import annotations

import csv
import http.client
import io
import json
import time
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from lumen_canonico.documentos import cnpj_valido, mascarar_cpfs_no_texto

from . import tce
from .camara import EMENTA, LEGISLATURAS, publicar_casa
from .comum import gravar_json, instante_utc, ler_json, sem_acento

API = "https://legis.senado.leg.br/dadosabertos"
CEAPS = "https://www.senado.leg.br/transparencia/LAI/verba/despesa_ceaps_{ano}.csv"
FONTE = "Senado Federal, dados abertos (legis.senado.leg.br/dadosabertos) e cota parlamentar (CEAPS)"
ARQUIVO = "senado.json.gz"
VERSAO_ESTADO = 1
PRIMEIRO_ANO = 2003
TIPOS_LISTADOS = frozenset({"PL", "PLP", "PEC", "PDL", "PRS", "PLS"})
VOTOS = {"Sim": "S", "Não": "N", "Abstenção": "A", "Obstrução": "O", "Presidente (art. 51 RISF)": "PR"}
PRESENTES = frozenset({"S", "N", "A", "O", "P-NRV", "PR"})


def _json(url: str, *, contato: str, ler_fn: Callable[[str], bytes] | None, tentativas: int = tce.TENTATIVAS,
          esperar: Callable[[float], None] = time.sleep) -> Any:
    """O JSON de um endereço da API (com ``Accept: application/json``). A API às vezes demora a mandar o corpo (a
    votação do ano tem 3 a 4 MB): o tempo esgotado e a conexão que cai no meio da leitura fazem pedir de novo."""
    if ler_fn:
        return json.loads(ler_fn(url))
    pedido = urllib.request.Request(url, headers={**tce.cabecalhos(contato), "Accept": "application/json"})
    for tentativa in range(tentativas):
        try:
            with tce.abrir(pedido) as r:
                return json.loads(r.read())
        except (TimeoutError, ConnectionError, http.client.IncompleteRead):
            if tentativa + 1 == tentativas:
                raise
            esperar(5 * (tentativa + 1))
    raise AssertionError("inalcançável")


def _lista(x: Any) -> list:
    """O que a API manda ora como lista, ora como um objeto só, ora como nada, sempre como lista."""
    return x if isinstance(x, list) else [x] if x else []


def _nome(texto: str | None) -> str:
    """O nome para ligar a cota ao cadastro: sem acento, maiúsculo, um espaço entre as palavras."""
    return " ".join(sem_acento(texto or "").upper().split())


# ------------------------------------------------------------------------------------------ cadastro

def cadastro(*, contato: str, ler_fn: Callable[[str], bytes] | None = None) -> dict[str, list]:
    """Os senadores das legislaturas de ``LEGISLATURAS``: ``{código: [nome, partido, uf, [legislaturas]]}``. O partido
    fica vazio aqui; vem do voto mais recente (``partido_atual``)."""
    saida: dict[str, list] = {}
    for legislatura in sorted(LEGISLATURAS):
        dados = _json(f"{API}/senador/lista/legislatura/{legislatura}", contato=contato, ler_fn=ler_fn)
        for p in _lista(((dados.get("ListaParlamentarLegislatura") or {}).get("Parlamentares") or {}).get("Parlamentar")):
            ident = p.get("IdentificacaoParlamentar") or {}
            codigo = str(ident.get("CodigoParlamentar") or "")
            if not codigo:
                continue
            mandatos = _lista((p.get("Mandatos") or {}).get("Mandato"))
            uf = next((m.get("UfParlamentar") for m in mandatos if m.get("UfParlamentar")), "")
            registro = saida.setdefault(codigo, [ident.get("NomeParlamentar") or codigo, "", uf, []])
            registro[0], registro[2] = ident.get("NomeParlamentar") or registro[0], uf or registro[2]
            if legislatura not in registro[3]:
                registro[3].append(legislatura)
    return saida


def periodos(mandatos: dict) -> list[list]:
    """Os períodos em exercício (``[[início, fim ou None], ...]``) a partir de ``/senador/<código>/mandatos``."""
    saida = []
    parlamentar = (mandatos.get("MandatoParlamentar") or {}).get("Parlamentar") or {}
    for m in _lista((parlamentar.get("Mandatos") or {}).get("Mandato")):
        for e in _lista((m.get("Exercicios") or {}).get("Exercicio")):
            if e.get("DataInicio"):
                saida.append([e["DataInicio"][:10], (e.get("DataFim") or "")[:10] or None])
    return sorted(saida)


def exercicio(senadores: Iterable[str], *, contato: str, ler_fn: Callable[[str], bytes] | None = None,
              pausa: float = 0.2, dormir: Callable[[float], None] = time.sleep) -> dict[str, list[list]]:
    """Os períodos em exercício de cada senador, um pedido por senador."""
    saida = {}
    for codigo in senadores:
        saida[codigo] = periodos(_json(f"{API}/senador/{codigo}/mandatos", contato=contato, ler_fn=ler_fn))
        dormir(pausa)
    return saida


def autoria(senadores: Iterable[str], *, contato: str, ler_fn: Callable[[str], bytes] | None = None,
            pausa: float = 0.2, dormir: Callable[[float], None] = time.sleep) -> dict[str, list]:
    """As matérias de cada senador como autor ou coautor: ``{código: [[id, tipo, número, ano, ementa, apresentação,
    situação], ...]}``, de qualquer ano."""
    saida: dict[str, list] = {}
    for codigo in senadores:
        lista = []
        for p in _lista(_json(f"{API}/processo?codigoParlamentarAutor={codigo}", contato=contato, ler_fn=ler_fn)):
            ident = (p.get("identificacao") or "").strip()
            tipo, _, resto = ident.partition(" ")
            numero, _, ano = resto.partition("/")
            lista.append([str(p.get("codigoMateria") or p.get("id") or ""), tipo, numero, ano,
                          (p.get("ementa") or "")[:EMENTA], (p.get("dataApresentacao") or "")[:10],
                          p.get("situacaoAtual") or None])
        saida[codigo] = sorted(lista, key=lambda x: (x[5], x[0]))
        dormir(pausa)
    return saida


# ------------------------------------------------------------------------------------------ ano

def ler_votacoes(votacoes: list[dict], senadores: dict[str, list]) -> dict[str, Any]:
    """As votações nominais abertas do ano, os votos, o partido de cada um no dia e a presença (``PRESENTES``)."""
    saida: dict[str, Any] = {"votacoes": {}, "votos": {}, "partidos": {}, "sessoes": {}, "presencas": {}}
    for v in votacoes:
        if (v.get("votacaoSecreta") or "N") != "N":
            continue
        vid = str(v.get("codigoSessaoVotacao") or "")
        votos = [x for x in _lista(v.get("votos")) if str(x.get("codigoParlamentar")) in senadores]
        if not vid or not votos:
            continue
        codigos = [VOTOS.get(x.get("siglaVotoParlamentar") or "", x.get("siglaVotoParlamentar") or "-") for x in votos]
        resultado = {"A": 1, "R": 0}.get((v.get("resultadoVotacao") or "").strip())
        saida["votacoes"][vid] = [
            (v.get("dataSessao") or "")[:10], v.get("identificacao") or "", (v.get("ementa") or "")[:EMENTA],
            (v.get("descricaoVotacao") or "")[:EMENTA], resultado, codigos.count("S"), codigos.count("N"),
            sum(1 for c in codigos if c not in ("S", "N")), None, str(v.get("codigoMateria") or "") or None]
        saida["sessoes"][vid] = (v.get("dataSessao") or "")[:10]
        for x, codigo in zip(votos, codigos):
            sen = str(x["codigoParlamentar"])
            saida["votos"].setdefault(sen, {})[vid] = codigo
            saida["partidos"].setdefault(vid, {})[sen] = x.get("siglaPartidoParlamentar") or ""
            if codigo in PRESENTES:
                saida["presencas"].setdefault(sen, []).append(vid)
    return saida


def ler_ceaps(texto: str, senadores: dict[str, list]) -> tuple[dict[str, dict], dict[str, str], int]:
    """A cota do ano por senador (como na Câmara: categorias, meses, fornecedores por CNPJ e pessoa física só somada),
    os nomes dos CNPJs e quantas linhas ficaram sem senador no cadastro."""
    por_nome = {_nome(r[0]): codigo for codigo, r in senadores.items()}

    def achar(nome: str) -> str | None:
        """O senador pelo nome; sem o nome exato, o único do cadastro cujo nome é o começo do nome da cota ("WEVERTON
        ROCHA" na cota, "Weverton" no cadastro)."""
        if nome in por_nome:
            return por_nome[nome]
        candidatos = {c for n, c in por_nome.items() if nome.startswith(n + " ")}
        return candidatos.pop() if len(candidatos) == 1 else None
    linhas = texto.splitlines()
    inicio = next((i for i, linha in enumerate(linhas) if linha.startswith('"ANO"')), 0)
    ceap: dict[str, dict] = {}
    nomes: dict[str, str] = {}
    sem_senador = 0
    for r in csv.DictReader(io.StringIO("\n".join(linhas[inicio:])), delimiter=";"):
        codigo = achar(_nome(r.get("SENADOR")))
        if not codigo:
            sem_senador += 1
            continue
        try:
            valor = float((r.get("VALOR_REEMBOLSADO") or "0").replace(".", "").replace(",", "."))
        except ValueError:
            valor = 0.0
        c = ceap.setdefault(codigo, {"categorias": {}, "meses": {}, "fornecedores": {}, "pf": [0, 0.0]})
        categoria = (r.get("TIPO_DESPESA") or "").strip()
        c["categorias"][categoria] = c["categorias"].get(categoria, 0.0) + valor
        mes = f"{int(r.get('MES') or 0):02d}"
        c["meses"][mes] = c["meses"].get(mes, 0.0) + valor
        documento = "".join(x for x in (r.get("CNPJ_CPF") or "") if x.isdigit())
        if len(documento) == 14 and cnpj_valido(documento):
            f = c["fornecedores"].setdefault(documento, [0, 0.0])
            f[0] += 1
            f[1] += valor
            if r.get("FORNECEDOR"):
                nomes[documento] = mascarar_cpfs_no_texto(r["FORNECEDOR"].strip())
        else:
            c["pf"][0] += 1
            c["pf"][1] += valor
    r2 = lambda v: round(v, 2)  # noqa: E731
    return ({s: {"categorias": {k: r2(v) for k, v in sorted(c["categorias"].items())},
                 "meses": {k: r2(v) for k, v in sorted(c["meses"].items())},
                 "fornecedores": {k: [n, r2(v)] for k, (n, v) in sorted(c["fornecedores"].items())},
                 "pf": [c["pf"][0], r2(c["pf"][1])]} for s, c in sorted(ceap.items())},
            dict(sorted(nomes.items())), sem_senador)


def autoria_do_ano(autorias: dict[str, list], ano: int) -> tuple[dict[str, list], dict[str, dict[str, int]]]:
    """As matérias apresentadas no ano: as listadas (``TIPOS_LISTADOS``) e a contagem de todas por tipo."""
    listadas: dict[str, list] = {}
    contagem: dict[str, dict[str, int]] = {}
    for sen, materias in autorias.items():
        for m in materias:
            if not m[5].startswith(str(ano)):
                continue
            por_tipo = contagem.setdefault(sen, {})
            por_tipo[m[1]] = por_tipo.get(m[1], 0) + 1
            if m[1] in TIPOS_LISTADOS:
                listadas.setdefault(sen, []).append(m)
    return listadas, {s: dict(sorted(c.items())) for s, c in contagem.items()}


# ------------------------------------------------------------------------------------------ coleta

def coletar(estado: Path | str, *, contato: str, hoje: date | None = None, anos: list[int] | None = None,
            limite_minutos: float | None = None, ler_fn: Callable[[str], bytes] | None = None,
            texto_fn: Callable[[str], str | None] | None = None, cadastro_fn: Callable[..., dict] = cadastro,
            exercicio_fn: Callable[..., dict] = exercicio, autoria_fn: Callable[..., dict] = autoria,
            relogio: Callable[[], float] = time.monotonic) -> tce.ResultadoTce:
    """Lê os anos que passaram da idade de releitura (ou os pedidos) e grava ``ARQUIVO`` depois de cada um."""
    hoje = hoje or datetime.now(timezone.utc).date()
    caminho = Path(estado) / ARQUIVO
    dados = ler_json(caminho) if caminho.exists() else {}
    if dados and dados.get("versao") != VERSAO_ESTADO:
        raise ValueError(f"{caminho}: versão {dados.get('versao')!r} do estado do Senado não suportada")
    texto_fn = texto_fn or (lambda url: (tce.baixar(url, contato=contato) or b"").decode("latin-1") or None)
    resultado = tce.ResultadoTce("Senado Federal")
    prazo = relogio() + limite_minutos * 60 if limite_minutos else None
    senadores = cadastro_fn(contato=contato)
    atual = max(LEGISLATURAS)
    estado_novo = {"versao": VERSAO_ESTADO, "fonte": FONTE, "deputados": senadores,
                   "exercicio": dict(dados.get("exercicio") or {}), "autoria": dict(dados.get("autoria") or {}),
                   "anos": dict(dados.get("anos") or {})}

    def gravar() -> None:
        Path(estado).mkdir(parents=True, exist_ok=True)
        gravar_json(caminho, {**estado_novo, "coletado_em": instante_utc()}, comprimir=True)

    for ano in anos or range(PRIMEIRO_ANO, hoje.year + 1):
        if prazo is not None and relogio() >= prazo:
            resultado.interrompida = True
            break
        if not anos and not tce.precisa_ler_por_idade(estado_novo["anos"].get(str(ano)), ano, hoje):
            resultado.pulados.append(ano)
            continue
        if not resultado.lidos:
            faltam = [s for s, r in senadores.items() if atual in r[3] or s not in estado_novo["exercicio"]]
            estado_novo["exercicio"].update(exercicio_fn(faltam, contato=contato))
            estado_novo["autoria"].update(autoria_fn(faltam, contato=contato))
        votacoes = _lista(_json(f"{API}/votacao?dataInicio={ano}-01-01&dataFim={ano}-12-31", contato=contato,
                                ler_fn=ler_fn))
        a = ler_votacoes(votacoes, senadores)
        texto = texto_fn(CEAPS.format(ano=ano))
        ceap, fornecedores, sem_senador = ler_ceaps(texto, senadores) if texto else ({}, {}, 0)
        if sem_senador:
            resultado.problemas.append(f"{ano}: {sem_senador} linha(s) da cota sem senador no cadastro")
        listadas, contagem = autoria_do_ano(estado_novo["autoria"], ano)
        if not a["votacoes"] and not ceap and not listadas:
            resultado.ausentes.append(ano)
            continue
        estado_novo["anos"][str(ano)] = {"lido_em": instante_utc(), **a, "autoria": listadas, "contagem": contagem,
                                         "ceap": ceap, "fornecedores": fornecedores}
        resultado.lidos.append(ano)
        gravar()
    if not resultado.lidos:
        gravar()
    return resultado


def partido_atual(dados: dict) -> dict[str, list]:
    """O cadastro com o partido do voto mais recente de cada senador (a lista por legislatura não traz o partido)."""
    senadores = {s: list(r) for s, r in dados["deputados"].items()}
    for _, a in sorted(dados["anos"].items()):
        for _vid, partidos in sorted(a.get("partidos", {}).items(), key=lambda x: a["votacoes"].get(x[0], [""])[0]):
            for sen, partido in partidos.items():
                if sen in senadores and partido:
                    senadores[sen][1] = partido
    return senadores


def publicar(estado: Path | str, gravar: Callable[[str, Any], Any], *, gerado_em: str) -> dict | None:
    """Grava ``parlamentares/senado/`` como a Câmara (``camara.publicar_casa``); devolve o resumo para o índice."""
    caminho = Path(estado) / ARQUIVO
    if not caminho.exists():
        return None
    dados = ler_json(caminho)
    if dados.get("versao") != VERSAO_ESTADO:
        raise ValueError(f"{caminho}: versão {dados.get('versao')!r} do estado do Senado não suportada")
    return publicar_casa({**dados, "deputados": partido_atual(dados)}, gravar, gerado_em=gerado_em, casa="senado",
                         pessoa="senador")
