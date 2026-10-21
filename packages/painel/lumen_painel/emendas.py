"""Emendas parlamentares do Portal da Transparência (CGU), pelo arquivo de dados abertos, sem chave (ADR-044).

O Portal publica um arquivo só, refeito de tempos em tempos
(``portaldatransparencia.gov.br/download-de-dados/emendas-parlamentares/UNICO``, que redireciona para
``dadosabertos-download.cgu.gov.br/.../EmendasParlamentares.zip``; 32 MB em outubro de 2026), com três CSVs em
ISO-8859-1 separados por ``;``:

- ``EmendasParlamentares.csv``: uma linha por emenda e ação, com o autor, o tipo, a função, a ação e a
  localidade indicada. A maior parte do valor pago vem como "MÚLTIPLO" ou "Nacional", sem município;
- ``EmendasParlamentares_PorFavorecido.csv``: o que cada favorecido recebeu por mês, com a natureza jurídica e
  o município dele. É daqui que sai quanto chegou a cada lugar;
- ``EmendasParlamentares_Convenios.csv``: os convênios das emendas (fora desta versão).

O lugar do favorecido diz o destino quando ele é do próprio lugar, e não quando é um agente financeiro: o banco
que opera os repasses aparece como sociedade de economia mista em Brasília. Por isso o recebido entra por
categoria, pela natureza jurídica do favorecido:

- **governo municipal** (o município, os fundos, órgãos e autarquias municipais) e **governo estadual** (o estado,
  os fundos, órgãos e autarquias estaduais), no ente do favorecido;
- **entidade** (associação, fundação privada, organização religiosa, serviço social) e **empresa**, no município
  do favorecido, com o CNPJ e o nome;
- **pessoa física**, só a soma, sem nome nem documento (ADR-043);
- **agente financeiro** (sociedade de economia mista, empresa pública) e o resto ficam fora do lugar e só entram
  nos totais do arquivo.

O estado (``emendas.json.gz``) leva, por código IBGE do ente, o recebido por ano, emenda, categoria e favorecido,
e a descrição de cada emenda (autor, tipo, função, ação). A coleta só baixa o arquivo quando a data dele
(``Last-Modified``) muda.
"""

from __future__ import annotations

import csv
import io
import re
import shutil
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from lumen_canonico.documentos import mascarar_cpfs_no_texto
from lumen_normalizacao.transformacoes import chave_texto

from .cadastro import Cadastro
from .comum import gravar_json, instante_utc, ler_json

URL = "https://portaldatransparencia.gov.br/download-de-dados/emendas-parlamentares/UNICO"
FONTE = "Portal da Transparência (CGU), emendas parlamentares, arquivo de dados abertos"
ARQUIVO = "emendas.json.gz"
VERSAO_ESTADO = 1
COLUNAS_EMENDA = ["ano", "tipo", "autor", "numero", "funcao", "acao"]
COLUNAS_RECEBIDO = ["ano", "emenda", "categoria", "cnpj", "favorecido", "valor"]
CATEGORIAS = {"governo_municipal": "Governo municipal", "governo_estadual": "Governo estadual",
              "entidade": "Entidade sem fins lucrativos", "empresa": "Empresa", "pessoa_fisica": "Pessoa física"}
_MUNICIPAL = ("municipio", "municipal")
_ESTADUAL = ("estado ou distrito federal", "estadual")
_ENTIDADE = ("associacao privada", "fundacao privada", "organizacao religiosa", "servico social", "organizacao social")
_AGENTE = ("sociedade de economia mista", "empresa publica")
# Nomes antigos e grafias que o Portal ainda usa para o município (emendas e convênios) → o nome no cadastro
APELIDOS = {("SP", "embu"): "embu das artes", ("PA", "santa isabel do para"): "santa izabel do para",
            ("RS", "santana do livramento"): "sant'ana do livramento", ("RN", "presidente juscelino"): "serra caiada",
            ("CE", "itapage"): "itapaje", ("PA", "eldorado dos carajas"): "eldorado do carajas",
            ("PE", "iguaraci"): "iguaracy", ("MT", "poxoreo"): "poxoreu", ("TO", "fortaleza do tabocao"): "tabocao",
            ("RN", "augusto severo"): "campo grande", ("RN", "serra caiada (ex-presidente juscelino)"): "serra caiada",
            ("RN", "campo grande (ex-augusto severo)"): "campo grande", ("RN", "januario cicco"): "boa saude",
            ("RJ", "parati"): "paraty", ("RJ", "trajano de morais"): "trajano de moraes",
            ("MG", "dona eusebia"): "dona euzebia", ("MG", "brasopolis"): "brazopolis",
            ("MG", "sao thome das letras"): "sao tome das letras", ("TO", "couto de magalhaes"): "couto magalhaes",
            ("TO", "sao valerio da natividade"): "sao valerio", ("PE", "belem de sao francisco"): "belem do sao francisco",
            ("PE", "lagoa do itaenga"): "lagoa de itaenga", ("PB", "sao domingos de pombal"): "sao domingos",
            ("PB", "serido"): "sao vicente do serido"}


def categoria(tipo_favorecido: str, natureza: str) -> str | None:
    """A categoria do favorecido pela natureza jurídica; ``None`` para o que não tem lugar (agente financeiro…)."""
    if tipo_favorecido.lower().startswith("pessoa f"):
        return "pessoa_fisica"
    if tipo_favorecido != "Pessoa Jurídica":
        return None
    n = chave_texto(natureza)
    if any(a in n for a in _AGENTE):
        return None
    if n == "municipio" or "municipal" in n:
        return "governo_municipal"
    if n.startswith("estado ou distrito federal") or "estadual" in n:
        return "governo_estadual"
    if any(e in n for e in _ENTIDADE):
        return "entidade"
    if any(e in n for e in ("sociedade", "empresari", "eireli", "limitada", "cooperativa")):
        return "empresa"
    return None


def _cabecalhos(contato: str) -> dict[str, str]:
    """User-Agent com o contato do Lumen."""
    return {"User-Agent": f"Lumen (contato: {contato})"}


def data_do_arquivo(*, contato: str) -> str | None:
    """O ``Last-Modified`` do arquivo, depois do redirecionamento (``HEAD``)."""
    pedido = urllib.request.Request(URL, method="HEAD", headers=_cabecalhos(contato))
    with urllib.request.urlopen(pedido, timeout=120) as r:
        return r.headers.get("Last-Modified")


def baixar(destino: Path, *, contato: str) -> tuple[Path, str | None]:
    """Baixa o ZIP para ``destino``; devolve o caminho e o ``Last-Modified``."""
    pedido = urllib.request.Request(URL, headers=_cabecalhos(contato))
    with urllib.request.urlopen(pedido, timeout=600) as r, open(destino, "wb") as f:
        shutil.copyfileobj(r, f, 1 << 20)
        return destino, r.headers.get("Last-Modified")


def _valor(texto: str) -> float:
    """``1300000,00`` → 1300000.0; vazio vira zero."""
    try:
        return float(texto.replace(".", "").replace(",", ".")) if texto else 0.0
    except ValueError:
        return 0.0


def _linhas(z: zipfile.ZipFile, nome: str):
    """As linhas do CSV ``nome`` do ZIP como dicionários, pelo cabeçalho."""
    with z.open(nome) as f:
        yield from csv.DictReader(io.TextIOWrapper(f, encoding="latin-1", newline=""), delimiter=";")


def indice_de_lugares(cadastro: Cadastro) -> dict[tuple[str, str], str]:
    """(UF, nome do município sem acento) → código IBGE, e (UF, "") → código da UF, pelo cadastro do SICONFI."""
    saida: dict[tuple[str, str], str] = {}
    for codigo, ente in cadastro.entes.items():
        if not ente.uf:
            continue
        if len(codigo) == 7:
            saida[(ente.uf.upper(), chave_texto(ente.nome))] = codigo
        elif len(codigo) == 2:
            saida[(ente.uf.upper(), "")] = codigo
    return saida


def ler(arquivo: Path, cadastro: Cadastro) -> dict:
    """O recebido por ente (código IBGE), a descrição das emendas usadas e os totais do que ficou sem lugar."""
    lugares = indice_de_lugares(cadastro)
    recebido: dict[str, dict[tuple, list]] = {}
    sem_lugar: dict[str, float] = {}
    usadas: set[str] = set()
    with zipfile.ZipFile(arquivo) as z:
        for d in _linhas(z, "EmendasParlamentares_PorFavorecido.csv"):
            ano, valor = (d.get("Ano/Mês") or "")[:4], _valor(d.get("Valor Recebido") or "")
            cat = categoria(d.get("Tipo Favorecido") or "", d.get("Natureza Jurídica") or "")
            uf = (d.get("UF Favorecido") or "").upper()
            chave_lugar = (uf, "") if cat == "governo_estadual" else (uf, chave_texto(d.get("Município Favorecido")))
            if chave_lugar in APELIDOS:
                chave_lugar = (uf, chave_texto(APELIDOS[chave_lugar]))
            ente = lugares.get(chave_lugar) if cat else None
            if ente is None:
                sem_lugar[ano] = sem_lugar.get(ano, 0.0) + valor
                continue
            documento = re.sub(r"\D", "", d.get("Código do Favorecido") or "")
            pj = cat != "pessoa_fisica" and len(documento) == 14
            emenda = d.get("Código da Emenda") or ""
            usadas.add(emenda)
            chave = (ano, emenda, cat, documento if pj else None)
            linha = recebido.setdefault(ente, {}).setdefault(
                chave, [ano, emenda, cat, documento if pj else None,
                        mascarar_cpfs_no_texto((d.get("Favorecido") or "").strip()) if pj else None, 0.0])
            linha[5] += valor
        emendas: dict[str, list] = {}
        for d in _linhas(z, "EmendasParlamentares.csv"):
            codigo = d.get("Código da Emenda") or ""
            if codigo in usadas and codigo not in emendas:
                emendas[codigo] = [d["Ano da Emenda"], d["Tipo de Emenda"], d["Nome do Autor da Emenda"],
                                   d["Número da emenda"], d["Nome Função"], d["Nome Ação"]]
    return {
        "recebido": {e: sorted([*linha[:5], round(linha[5], 2)] for linha in linhas.values())
                     for e, linhas in sorted(recebido.items())},
        "emendas": dict(sorted(emendas.items())),
        "sem_lugar": {a: round(v, 2) for a, v in sorted(sem_lugar.items())},
    }


@dataclass
class ResultadoEmendas:
    """O que a coleta fez: a data do arquivo, se baixou e quantos entes e emendas."""

    data_arquivo: str | None = None
    baixado: bool = False
    entes: int = 0
    emendas: int = 0

    def para_json(self) -> dict:
        """Resumo para imprimir na linha de comando."""
        return {"data_arquivo": self.data_arquivo, "baixado": self.baixado, "entes": self.entes,
                "emendas": self.emendas}


def coletar(estado: Path | str, cadastro: Cadastro, *, contato: str, temporario: Path | None = None,
            data_fn=data_do_arquivo, baixar_fn=baixar) -> ResultadoEmendas:
    """Baixa e lê o arquivo quando a data dele mudou; grava ``ARQUIVO``."""
    caminho = Path(estado) / ARQUIVO
    anterior = ler_json(caminho) if caminho.exists() else {}
    data = data_fn(contato=contato)
    resultado = ResultadoEmendas(data_arquivo=data)
    if data and anterior.get("data_arquivo") == data:
        resultado.entes, resultado.emendas = len(anterior.get("recebido") or {}), len(anterior.get("emendas") or {})
        return resultado
    pasta = Path(tempfile.mkdtemp(prefix="emendas-", dir=temporario))
    try:
        local, data_baixada = baixar_fn(pasta / "EmendasParlamentares.zip", contato=contato)
        dados = ler(local, cadastro)
    finally:
        shutil.rmtree(pasta, ignore_errors=True)
    resultado.baixado, resultado.data_arquivo = True, data_baixada or data
    resultado.entes, resultado.emendas = len(dados["recebido"]), len(dados["emendas"])
    Path(estado).mkdir(parents=True, exist_ok=True)
    gravar_json(caminho, {"versao": VERSAO_ESTADO, "data_arquivo": resultado.data_arquivo,
                          "coletado_em": instante_utc(), "fonte": FONTE, "colunas_emenda": COLUNAS_EMENDA,
                          "colunas_recebido": COLUNAS_RECEBIDO, **dados}, comprimir=True)
    return resultado


def publicar(estado: Path | str, gravar: Callable[[str, Any], Any], *, gerado_em: str) -> dict | None:
    """Grava ``emendas/ente/<código IBGE>.json.gz`` (comprimido): o recebido pelo ente e a descrição das emendas dele."""
    caminho = Path(estado) / ARQUIVO
    if not caminho.exists():
        return None
    dados = ler_json(caminho)
    if dados.get("versao") != VERSAO_ESTADO:
        raise ValueError(f"{caminho}: versão {dados.get('versao')!r} do estado das emendas não suportada")
    emendas = dados.get("emendas") or {}
    for ente, linhas in (dados.get("recebido") or {}).items():
        codigos = sorted({linha[1] for linha in linhas})
        gravar(f"emendas/ente/{ente}.json.gz", {
            "versao": 1, "tipo": "emendas-ente", "gerado_em": gerado_em, "ente": ente,
            "data_arquivo": dados.get("data_arquivo"), "fonte": dados.get("fonte"), "categorias": CATEGORIAS,
            "colunas_recebido": dados.get("colunas_recebido"), "recebido": linhas,
            "colunas_emenda": dados.get("colunas_emenda"), "emendas": {c: emendas.get(c) for c in codigos},
        })
    return {"data_arquivo": dados.get("data_arquivo"), "entes": len(dados.get("recebido") or {}),
            "sem_lugar": dados.get("sem_lugar")}
