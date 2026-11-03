"""Os deputados federais: votos, proposições, presença e cota parlamentar, pelos arquivos de dados abertos da Câmara
(ADR-060).

A Câmara publica, sem chave, um arquivo CSV por conjunto e ano em ``dadosabertos.camara.leg.br/arquivos``:

- ``votacoes``, ``votacoesVotos``, ``votacoesProposicoes`` e ``votacoesOrientacoes``: as votações, o voto de cada
  deputado nas nominais, a proposição votada e a orientação de cada bancada. Ficam só as do Plenário com voto
  nominal (429 em 2025);
- ``eventos`` e ``eventosPresencaDeputados``: as sessões e quem esteve nelas. A presença conta as sessões
  deliberativas do Plenário encerradas (129 em 2025);
- ``proposicoes`` e ``proposicoesAutores``: as proposições apresentadas no ano e quem as assina (``proponente``).
  São listadas as de ``TIPOS_LISTADOS`` (projetos de lei, de lei complementar, de decreto legislativo, de resolução e
  propostas de emenda à Constituição); as demais, como requerimentos, são só contadas por tipo;
- ``www.camara.leg.br/cotas/Ano-AAAA.csv.zip``: as despesas da cota parlamentar (CEAP), uma por documento, com a
  categoria, o fornecedor e o valor líquido. Fornecedor com CNPJ vai pelo CNPJ (e liga à página da empresa); com CPF,
  só na soma anônima de pessoa física;
O cadastro (nome, partido e UF) vem da API (``/deputados?idLegislatura=N``), uma consulta por legislatura, e os
períodos em exercício, do histórico de cada deputado na API (``/deputados/<id>/historico``; o arquivo em lote
``deputadosHistorico`` estava parado em 2024 em 3/11/2026). A presença compara as sessões a que ele foi com as
realizadas enquanto ele estava em exercício, para não pesar contra o suplente nem o licenciado. O histórico da
legislatura encerrada é lido uma vez; o da atual, a cada coleta que lê algum ano.

Os servidores da Câmara cortam o download no meio quando há vários de uma vez, e às vezes mesmo sozinho (o
``proposicoes`` de 90 MB parou em 74 MB em 3/11/2026). Os arquivos são baixados um de cada vez, e o corte é retomado
por ``Range`` até o tamanho do cabeçalho. Um ano fechado só é relido quando o arquivo de votos muda de tamanho; o
corrente e o anterior, uma vez por semana (``tce.precisa_ler``).
"""

from __future__ import annotations

import csv
import io
import json
import shutil
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from lumen_canonico.documentos import cnpj_valido, mascarar_cpfs_no_texto

from . import tce
from .comum import gravar_json, instante_utc, ler_json

ARQUIVOS = "https://dadosabertos.camara.leg.br/arquivos/{nome}/csv/{nome}-{ano}.csv"
API_HISTORICO = "https://dadosabertos.camara.leg.br/api/v2/deputados/{id}/historico"
COTA = "https://www.camara.leg.br/cotas/Ano-{ano}.csv.zip"
API_DEPUTADOS = "https://dadosabertos.camara.leg.br/api/v2/deputados?idLegislatura={legislatura}&itens=1000"
FONTE = "Câmara dos Deputados, dados abertos (dadosabertos.camara.leg.br) e cota parlamentar (camara.leg.br/cotas)"
ARQUIVO = "camara.json.gz"
VERSAO_ESTADO = 1
PRIMEIRO_ANO = 2019                 # a 56ª legislatura, para comparar com a 57ª (2023-2027)
LEGISLATURAS = {56: (2019, 2022), 57: (2023, 2026)}
CONJUNTOS = ("votacoes", "votacoesVotos", "votacoesProposicoes", "votacoesOrientacoes", "eventos",
             "eventosPresencaDeputados", "proposicoes", "proposicoesAutores")
TIPOS_LISTADOS = frozenset({"PL", "PLP", "PEC", "PDL", "PRC"})
VOTOS = {"Sim": "S", "Não": "N", "Abstenção": "A", "Obstrução": "O", "Artigo 17": "17"}
EMENTA = 300
TENTATIVAS = 6


# ------------------------------------------------------------------------------------------ fonte

def baixar_inteiro(url: str, destino: Path, *, contato: str, tentativas: int = TENTATIVAS,
                   esperar: Callable[[float], None] = time.sleep, abrir: Callable[..., Any] = urllib.request.urlopen,
                   ) -> int:
    """Baixa ``url`` em ``destino`` e devolve o tamanho. Se a conexão cair antes do ``Content-Length``, retoma de onde
    parou (``Range``), até ``tentativas`` vezes."""
    destino.unlink(missing_ok=True)
    total: int | None = None
    for tentativa in range(tentativas):
        feito = destino.stat().st_size if destino.exists() else 0
        cabecalhos = tce.cabecalhos(contato) | ({"Range": f"bytes={feito}-"} if feito else {})
        try:
            with abrir(urllib.request.Request(url, headers=cabecalhos), timeout=300) as r:
                if feito and r.status != 206:
                    destino.unlink()
                    feito = 0
                if total is None or not feito:
                    tamanho = r.headers.get("Content-Length")
                    total = (int(tamanho) + feito) if tamanho else None
                with open(destino, "ab") as f:
                    shutil.copyfileobj(r, f, 1 << 20)
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as erro:
            if isinstance(erro, urllib.error.HTTPError) and erro.code < 500:
                raise
        tamanho_atual = destino.stat().st_size if destino.exists() else 0
        if total is not None and tamanho_atual >= total:
            return tamanho_atual
        if total is None and tamanho_atual:
            return tamanho_atual
        esperar(3 * (tentativa + 1))
    raise OSError(f"{url}: download incompleto depois de {tentativas} tentativas")


def _csv(caminho: Path) -> Iterable[dict[str, str]]:
    """As linhas de um CSV da Câmara (UTF-8 com BOM, separado por ponto e vírgula)."""
    with open(caminho, encoding="utf-8-sig", newline="") as f:
        yield from csv.DictReader(f, delimiter=";")


def _csv_do_zip(caminho: Path) -> Iterable[dict[str, str]]:
    """As linhas do CSV de dentro do ZIP da cota (UTF-8 com BOM, separado por ponto e vírgula)."""
    with zipfile.ZipFile(caminho) as z:
        nome = next(n for n in z.namelist() if n.lower().endswith(".csv"))
        with z.open(nome) as bruto:
            yield from csv.DictReader(io.TextIOWrapper(bruto, encoding="utf-8-sig", newline=""), delimiter=";")


def _valor(texto: str | None) -> float:
    """``"1467.5"`` ou ``"1467,5"`` → 1467.5; vazio ou fora do formato → 0."""
    try:
        return float((texto or "0").replace(",", "."))
    except ValueError:
        return 0.0


# ------------------------------------------------------------------------------------------ cadastro

def cadastro(*, contato: str, ler_fn: Callable[[str], bytes] | None = None) -> dict[str, list]:
    """Os deputados das legislaturas de ``LEGISLATURAS``: ``{id: [nome, partido, uf, [legislaturas]]}``. O partido e a
    UF são os da legislatura mais recente."""
    ler_fn = ler_fn or (lambda url: tce.baixar(url, contato=contato) or b"")
    saida: dict[str, list] = {}
    for legislatura in sorted(LEGISLATURAS):
        for d in json.loads(ler_fn(API_DEPUTADOS.format(legislatura=legislatura)))["dados"]:
            registro = saida.setdefault(str(d["id"]), [d["nome"], d["siglaPartido"], d["siglaUf"], []])
            registro[:3] = [d["nome"], d["siglaPartido"], d["siglaUf"]]
            if legislatura not in registro[3]:          # a API repete o deputado que trocou de partido
                registro[3].append(legislatura)
    return saida


def periodos(historico: list[dict]) -> list[list]:
    """Os períodos em exercício (``[[início, fim ou None], ...]``, datas ``AAAA-MM-DD``) a partir do histórico da API:
    cada registro com ``situacao`` abre (``Exercício``) ou fecha (licença, vacância, fim de mandato…) um período; os
    sem situação (troca de nome ou de partido) não mudam nada."""
    saida: list[list] = []
    aberto: str | None = None
    for h in sorted(historico, key=lambda x: x.get("dataHora") or ""):
        situacao, dia = h.get("situacao"), (h.get("dataHora") or "")[:10]
        if not situacao:
            continue
        if situacao == "Exercício" and aberto is None:
            aberto = dia
        elif situacao != "Exercício" and aberto is not None:
            saida.append([aberto, dia])
            aberto = None
    if aberto is not None:
        saida.append([aberto, None])
    return saida


def exercicio(deputados: Iterable[str], *, contato: str, ler_fn: Callable[[str], bytes] | None = None,
              pausa: float = 0.2, dormir: Callable[[float], None] = time.sleep) -> dict[str, list[list]]:
    """Os períodos em exercício de cada deputado, um pedido à API por deputado."""
    ler_fn = ler_fn or (lambda url: tce.baixar(url, contato=contato) or b"{}")
    saida = {}
    for dep in deputados:
        saida[dep] = periodos(json.loads(ler_fn(API_HISTORICO.format(id=dep))).get("dados") or [])
        dormir(pausa)
    return saida


def em_exercicio(dia: str, periodos: list[list]) -> bool:
    """Se o deputado estava em exercício no dia (``AAAA-MM-DD``)."""
    return any(inicio <= dia and (fim is None or dia <= fim) for inicio, fim in periodos)


# ------------------------------------------------------------------------------------------ soma do ano

def ler_ano(pasta: Path, ano: int, deputados: dict[str, list]) -> dict[str, Any]:
    """O ano a partir dos arquivos baixados em ``pasta`` (``<conjunto>.csv`` e ``cota.zip``)."""
    quem = set(deputados)
    arquivo = lambda nome: pasta / f"{nome}.csv"  # noqa: E731
    plenario = {r["id"]: r for r in _csv(arquivo("votacoes")) if r.get("siglaOrgao") == "PLEN"}
    votos: dict[str, dict[str, str]] = {}
    nominais: set[str] = set()
    for r in _csv(arquivo("votacoesVotos")):
        if r["idVotacao"] in plenario and r["deputado_id"] in quem:
            votos.setdefault(r["deputado_id"], {})[r["idVotacao"]] = VOTOS.get(r["voto"], r["voto"] or "-")
            nominais.add(r["idVotacao"])
    proposicao: dict[str, tuple[str, str]] = {}
    for r in _csv(arquivo("votacoesProposicoes")):
        if r["idVotacao"] in nominais and r["idVotacao"] not in proposicao:
            proposicao[r["idVotacao"]] = (r["proposicao_titulo"], (r["proposicao_ementa"] or "")[:EMENTA])
    governo = {r["idVotacao"]: r["orientacao"] for r in _csv(arquivo("votacoesOrientacoes"))
               if r["idVotacao"] in nominais and r["siglaBancada"] == "Governo"}
    votacoes = {}
    for vid in sorted(nominais):
        v = plenario[vid]
        titulo, ementa = proposicao.get(vid, ("", ""))
        aprovacao = {"1": 1, "0": 0}.get(v.get("aprovacao") or "")
        votacoes[vid] = [v["data"], titulo, ementa, (v.get("descricao") or "")[:EMENTA], aprovacao,
                         int(v.get("votosSim") or 0), int(v.get("votosNao") or 0), int(v.get("votosOutros") or 0),
                         governo.get(vid)]
    sessoes = {r["id"]: r["dataHoraInicio"][:10] for r in _csv(arquivo("eventos"))
               if r.get("descricaoTipo") == "Sessão Deliberativa" and "Encerrada" in (r.get("situacao") or "")}
    presencas: dict[str, list[str]] = {}
    for r in _csv(arquivo("eventosPresencaDeputados")):
        if r["idEvento"] in sessoes and r["idDeputado"] in quem:
            presencas.setdefault(r["idDeputado"], []).append(r["idEvento"])
    proposicoes = {r["id"]: r for r in _csv(arquivo("proposicoes"))}
    autoria: dict[str, list] = {}
    contagem: dict[str, dict[str, int]] = {}
    for r in _csv(arquivo("proposicoesAutores")):
        dep, p = r.get("idDeputadoAutor") or "", proposicoes.get(r["idProposicao"])
        if dep not in quem or r.get("proponente") != "1" or not p:
            continue
        sigla = p["siglaTipo"]
        por_tipo = contagem.setdefault(dep, {})
        por_tipo[sigla] = por_tipo.get(sigla, 0) + 1
        if sigla in TIPOS_LISTADOS:
            autoria.setdefault(dep, []).append([p["id"], sigla, p["numero"], p["ano"], (p["ementa"] or "")[:EMENTA],
                                                (p["dataApresentacao"] or "")[:10],
                                                p.get("ultimoStatus_descricaoSituacao") or None])
    ceap, fornecedores = ler_cota(pasta / "cota.zip", quem) if (pasta / "cota.zip").exists() else ({}, {})
    return {
        "votacoes": votacoes,
        "votos": {d: dict(sorted(v.items())) for d, v in sorted(votos.items())},
        "sessoes": dict(sorted(sessoes.items())),
        "presencas": {d: sorted(set(e)) for d, e in sorted(presencas.items())},
        "autoria": {d: sorted(a, key=lambda x: (x[5], x[0])) for d, a in sorted(autoria.items())},
        "contagem": {d: dict(sorted(c.items())) for d, c in sorted(contagem.items())},
        "ceap": ceap,
        "fornecedores": fornecedores,
    }


def ler_cota(caminho: Path, quem: set[str]) -> tuple[dict[str, dict], dict[str, str]]:
    """A cota parlamentar do ano por deputado (``categorias``, ``meses``, ``fornecedores`` por CNPJ ``[documentos,
    valor]``, ``pf`` ``[documentos, valor]``) e o nome de cada CNPJ, com o CPF do MEI mascarado."""
    ceap: dict[str, dict] = {}
    nomes: dict[str, str] = {}
    for r in _csv_do_zip(caminho):
        dep = (r.get("ideCadastro") or "").strip()
        if dep not in quem:
            continue
        valor = _valor(r.get("vlrLiquido"))
        c = ceap.setdefault(dep, {"categorias": {}, "meses": {}, "fornecedores": {}, "pf": [0, 0.0]})
        categoria = (r.get("txtDescricao") or "").strip()
        c["categorias"][categoria] = c["categorias"].get(categoria, 0.0) + valor
        mes = f"{int(r.get('numMes') or 0):02d}"
        c["meses"][mes] = c["meses"].get(mes, 0.0) + valor
        documento = "".join(x for x in (r.get("txtCNPJCPF") or "") if x.isdigit())
        if len(documento) == 14 and cnpj_valido(documento):
            f = c["fornecedores"].setdefault(documento, [0, 0.0])
            f[0] += 1
            f[1] += valor
            if r.get("txtFornecedor"):
                nomes[documento] = mascarar_cpfs_no_texto(r["txtFornecedor"].strip())
        else:
            c["pf"][0] += 1
            c["pf"][1] += valor
    r2 = lambda v: round(v, 2)  # noqa: E731
    return ({d: {"categorias": {k: r2(v) for k, v in sorted(c["categorias"].items())},
                 "meses": {k: r2(v) for k, v in sorted(c["meses"].items())},
                 "fornecedores": {k: [n, r2(v)] for k, (n, v) in sorted(c["fornecedores"].items())},
                 "pf": [c["pf"][0], r2(c["pf"][1])]} for d, c in sorted(ceap.items())},
            dict(sorted(nomes.items())))


# ------------------------------------------------------------------------------------------ coleta

def coletar(estado: Path | str, *, contato: str, hoje: date | None = None, anos: list[int] | None = None,
            limite_minutos: float | None = None, temporario: Path | None = None,
            baixar_fn: Callable[..., int] = baixar_inteiro, cabecalho_fn: Callable[..., Any] = tce.cabecalho,
            cadastro_fn: Callable[..., dict] = cadastro, exercicio_fn: Callable[..., dict] = exercicio,
            relogio: Callable[[], float] = time.monotonic,
            ) -> tce.ResultadoTce:
    """Lê os anos que mudaram (ou os pedidos), um de cada vez, e grava ``ARQUIVO`` depois de cada um."""
    hoje = hoje or datetime.now(timezone.utc).date()
    caminho = Path(estado) / ARQUIVO
    dados = ler_json(caminho) if caminho.exists() else {}
    if dados and dados.get("versao") != VERSAO_ESTADO:
        raise ValueError(f"{caminho}: versão {dados.get('versao')!r} do estado da Câmara não suportada")
    resultado = tce.ResultadoTce("Câmara dos Deputados")
    prazo = relogio() + limite_minutos * 60 if limite_minutos else None
    pasta = Path(tempfile.mkdtemp(prefix="camara-", dir=temporario))
    try:
        deputados = cadastro_fn(contato=contato)
        estado_novo = {"versao": VERSAO_ESTADO, "fonte": FONTE, "deputados": deputados,
                       "exercicio": dict(dados.get("exercicio") or {}), "anos": dict(dados.get("anos") or {})}
        atual = max(LEGISLATURAS)

        def gravar() -> None:
            Path(estado).mkdir(parents=True, exist_ok=True)
            gravar_json(caminho, {**estado_novo, "coletado_em": instante_utc()}, comprimir=True)

        for ano in anos or range(PRIMEIRO_ANO, hoje.year + 1):
            if prazo is not None and relogio() >= prazo:
                resultado.interrompida = True
                break
            sinal = cabecalho_fn(ARQUIVOS.format(nome="votacoesVotos", ano=ano), contato=contato)
            if sinal is None:
                resultado.ausentes.append(ano)
                continue
            tamanho, etiqueta = sinal
            if not anos and not tce.precisa_ler(estado_novo["anos"].get(str(ano)), tamanho, etiqueta, ano, hoje):
                resultado.pulados.append(ano)
                continue
            for nome in CONJUNTOS:
                baixar_fn(ARQUIVOS.format(nome=nome, ano=ano), pasta / f"{nome}.csv", contato=contato)
            try:
                baixar_fn(COTA.format(ano=ano), pasta / "cota.zip", contato=contato)
            except urllib.error.HTTPError as erro:
                if erro.code != 404:
                    raise
                (pasta / "cota.zip").unlink(missing_ok=True)
                resultado.problemas.append(f"{ano}: sem o arquivo da cota parlamentar")
            faltam = [d for d, r in deputados.items() if atual in r[3] or d not in estado_novo["exercicio"]]
            if not resultado.lidos and faltam:
                estado_novo["exercicio"].update(exercicio_fn(faltam, contato=contato))
            estado_novo["anos"][str(ano)] = {"tamanho": tamanho, "etiqueta": etiqueta, "lido_em": instante_utc(),
                                             **ler_ano(pasta, ano, deputados)}
            resultado.lidos.append(ano)
            gravar()
        if not resultado.lidos:
            gravar()
    finally:
        shutil.rmtree(pasta, ignore_errors=True)
    return resultado


# ------------------------------------------------------------------------------------------ publicação

def publicar(estado: Path | str, gravar: Callable[[str, Any], Any], *, gerado_em: str) -> dict | None:
    """Grava ``parlamentares/camara/<id>.json.gz`` (um por deputado), ``parlamentares/camara/votacoes-<ano>.json.gz``
    e ``parlamentares/camara/indice.json``; devolve o resumo para o índice dos painéis."""
    caminho = Path(estado) / ARQUIVO
    if not caminho.exists():
        return None
    dados = ler_json(caminho)
    if dados.get("versao") != VERSAO_ESTADO:
        raise ValueError(f"{caminho}: versão {dados.get('versao')!r} do estado da Câmara não suportada")
    deputados, periodos = dados["deputados"], dados.get("exercicio") or {}
    pessoas: dict[str, dict] = {}
    for ano, a in sorted(dados["anos"].items()):
        gravar(f"parlamentares/camara/votacoes-{ano}.json.gz", {
            "versao": 1, "tipo": "camara-votacoes", "gerado_em": gerado_em, "ano": ano,
            "colunas": ["data", "proposicao", "ementa", "descricao", "aprovacao", "sim", "nao", "outros", "governo"],
            "votacoes": a["votacoes"]})
        for dep in deputados:
            sessoes = [e for e, dia in a["sessoes"].items() if em_exercicio(dia, periodos.get(dep, []))]
            presente = len(set(a["presencas"].get(dep, [])) & set(sessoes))
            ceap = a["ceap"].get(dep)
            registro = {"votos": a["votos"].get(dep, {}), "presenca": [presente, len(sessoes)],
                        "autoria": a["autoria"].get(dep, []), "contagem": a["contagem"].get(dep, {})}
            if ceap:
                registro["ceap"] = {**ceap, "fornecedores": sorted(
                    ([c, a["fornecedores"].get(c), n, v] for c, (n, v) in ceap["fornecedores"].items()),
                    key=lambda x: (-x[3], x[0]))}
            if registro["votos"] or registro["autoria"] or presente or ceap or sessoes:
                pessoas.setdefault(dep, {})[ano] = registro
    indice = []
    for dep, anos in sorted(pessoas.items(), key=lambda x: deputados[x[0]][0]):
        nome, partido, uf, legislaturas = deputados[dep]
        gravar(f"parlamentares/camara/{dep}.json.gz", {
            "versao": 1, "tipo": "camara-deputado", "gerado_em": gerado_em, "id": dep, "nome": nome,
            "partido": partido, "uf": uf, "legislaturas": legislaturas, "exercicio": periodos.get(dep, []),
            "colunas_autoria": ["id", "tipo", "numero", "ano", "ementa", "apresentacao", "situacao"],
            "colunas_fornecedor": ["cnpj", "nome", "documentos", "valor"], "anos": anos})
        votos = sum(1 for a in anos.values() for v in a["votos"].values() if v not in ("-", ""))
        presente = sum(a["presenca"][0] for a in anos.values())
        sessoes = sum(a["presenca"][1] for a in anos.values())
        indice.append([dep, nome, partido, uf, legislaturas, votos,
                       sum(len(a["autoria"]) for a in anos.values()), presente, sessoes,
                       round(sum(sum(a.get("ceap", {}).get("categorias", {}).values()) for a in anos.values()), 2)])
    gravar("parlamentares/camara/indice.json", {
        "versao": 1, "tipo": "camara-indice", "gerado_em": gerado_em, "fonte": dados.get("fonte"),
        "coletado_em": dados.get("coletado_em"), "anos": sorted(dados["anos"]),
        "colunas": ["id", "nome", "partido", "uf", "legislaturas", "votos", "proposicoes", "presencas", "sessoes",
                    "ceap"], "deputados": indice})
    return {"deputados": len(indice), "anos": sorted(dados["anos"])}
