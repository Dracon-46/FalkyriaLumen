"""O que a União pagou a cada pessoa jurídica, pelo arquivo mensal de recebimentos por favorecido da CGU (ADR-058).

O Portal da Transparência publica um arquivo por mês, de janeiro de 2014 em diante
(``portaldatransparencia.gov.br/download-de-dados/despesas-favorecidos/AAAAMM``, que redireciona para
``dadosabertos-download.cgu.gov.br/.../AAAAMM_Despesas.zip``; perto de 24 MB compactados e 170 MB abertos), sem chave.
O CSV, ``AAAAMM_RecebimentosRecursosPorFavorecido.csv``, tem uma linha por favorecido, unidade gestora e mês: o
código e o nome do favorecido, a UF e o município dele, o órgão superior, o órgão e a unidade que pagaram e o valor
recebido. Em setembro de 2026, foram 737 mil linhas, 174 mil CNPJs e R$ 95,9 bilhões.

Por CNPJ e ano, o recebido de cada órgão superior (ministério). O arquivo não traz pessoa física; o que não é CNPJ
(favorecido do exterior, unidade gestora pagando outra) fica só contado, em ``fora``. Entre os maiores favorecidos
estão bancos que recebem como agentes (o Banco do Brasil e a Caixa pagam benefícios e repasses) e os fundos dos
entes, que as transferências (ADR-054) já mostram pelo ente: aqui eles aparecem como a fonte publica, pelo CNPJ.

A coleta segue a das transferências: os ``RECENTES`` meses mais novos, que a CGU ainda corrige, são baixados de novo
a cada execução e ficam à parte (``recentes``); os mais antigos são somados uma vez e fixados no ano (``anos``).
Cada execução baixa no máximo ``LIMITE_MESES`` meses, do mais novo para o mais antigo, com pausa entre eles, e para
se a CGU pedir verificação humana. O nome de cada CNPJ é o mais recente, com o CPF do MEI mascarado. A publicação é
na página da empresa (``pessoas_juridicas``).
"""

from __future__ import annotations

import csv
import io
import shutil
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

from lumen_canonico.documentos import cnpj_valido, mascarar_cpfs_no_texto

from .comum import gravar_json, instante_utc, ler_json
from .transferencias import VerificacaoHumana, meses_na_pagina

PAGINA = "https://portaldatransparencia.gov.br/download-de-dados/despesas-favorecidos"
FONTE = "Portal da Transparência (CGU), recebimentos de recursos por favorecido, arquivo mensal de dados abertos"
ARQUIVO = "recebimentos.json.gz"
VERSAO_ESTADO = 1
PRIMEIRO_ANO = 2014
RECENTES = 3            # meses mais recentes, baixados de novo a cada execução
LIMITE_MESES = 12       # downloads por execução, os recentes incluídos (cada um, perto de 24 MB)
PAUSA_S = 5.0           # entre um download e o seguinte
COLUNAS = ("Código Favorecido", "Nome Favorecido", "Código Órgão Superior", "Nome Órgão Superior", "Valor Recebido")


def _cabecalhos(contato: str) -> dict[str, str]:
    """User-Agent com o contato do Lumen."""
    return {"User-Agent": f"Lumen (contato: {contato})"}


def meses_disponiveis(*, contato: str) -> list[str]:
    """Os meses publicados (``AAAAMM``), lidos da página de download, de ``PRIMEIRO_ANO`` em diante."""
    pedido = urllib.request.Request(PAGINA, headers=_cabecalhos(contato))
    with urllib.request.urlopen(pedido, timeout=120) as r:
        return [m for m in meses_na_pagina(r.read().decode("utf-8", "replace")) if int(m[:4]) >= PRIMEIRO_ANO]


def baixar(mes: str, destino: Path, *, contato: str) -> Path:
    """Baixa o ZIP do mês para ``destino``; a página de verificação humana, no lugar do ZIP, vira erro."""
    pedido = urllib.request.Request(f"{PAGINA}/{mes}", headers=_cabecalhos(contato))
    try:
        with urllib.request.urlopen(pedido, timeout=600) as r:
            tipo = r.headers.get("Content-Type") or ""
            if "zip" not in tipo and "octet" not in tipo:
                raise VerificacaoHumana(f"{mes}: a CGU respondeu {tipo!r} no lugar do ZIP")
            with open(destino, "wb") as f:
                shutil.copyfileobj(r, f, 1 << 20)
    except urllib.error.HTTPError as erro:
        if erro.code in (403, 405, 429):
            raise VerificacaoHumana(f"{mes}: HTTP {erro.code} do servidor de arquivos da CGU") from erro
        raise
    return destino


def _valor(texto: str) -> float:
    """``48491,5300`` → 48491.53; vazio ou fora do formato vira zero."""
    try:
        return float((texto or "0").replace(".", "").replace(",", "."))
    except ValueError:
        return 0.0


def _linhas(arquivo: Path) -> Iterable[dict[str, str]]:
    """As linhas do CSV de dentro do ZIP, lidas em fluxo (ISO-8859-1, separadas por ponto e vírgula)."""
    with zipfile.ZipFile(arquivo) as z:
        nome = next(n for n in z.namelist() if n.lower().endswith(".csv"))
        with z.open(nome) as bruto:
            leitor = csv.DictReader(io.TextIOWrapper(bruto, encoding="latin-1", newline=""), delimiter=";")
            faltam = [c for c in COLUNAS if c not in (leitor.fieldnames or [])]
            if faltam:
                raise ValueError(f"{arquivo.name}: colunas ausentes no CSV da CGU: {faltam}")
            yield from leitor


def soma_vazia() -> dict[str, Any]:
    """A soma de um mês ou de um ano: por CNPJ e órgão superior, e o que ficou fora (``[linhas, valor]``)."""
    return {"cnpjs": {}, "fora": [0, 0.0]}


def somar_mes(arquivo: Path, nomes: dict[str, str], orgaos: dict[str, str], *, nomes_novos: bool) -> dict[str, Any]:
    """A soma do mês por CNPJ e órgão superior. Guarda em ``nomes`` o nome de cada CNPJ (``nomes_novos``: troca o que
    já houver, só para o mês mais recente) e em ``orgaos`` o nome de cada órgão superior."""
    soma = soma_vazia()
    for linha in _linhas(arquivo):
        valor = _valor(linha["Valor Recebido"])
        documento = (linha["Código Favorecido"] or "").strip()
        if not (len(documento) == 14 and documento.isdigit() and cnpj_valido(documento)):
            soma["fora"][0] += 1
            soma["fora"][1] += valor
            continue
        orgao = (linha["Código Órgão Superior"] or "").strip()
        orgaos.setdefault(orgao, (linha["Nome Órgão Superior"] or "").strip())
        por_orgao = soma["cnpjs"].setdefault(documento, {})
        por_orgao[orgao] = por_orgao.get(orgao, 0.0) + valor
        nome = (linha["Nome Favorecido"] or "").strip().strip("'").strip()
        if nome and (nomes_novos or documento not in nomes):
            nomes[documento] = mascarar_cpfs_no_texto(nome)
    return arredondar(soma)


def arredondar(soma: dict[str, Any]) -> dict[str, Any]:
    """Os valores em centavos."""
    return {"cnpjs": {c: {o: round(v, 2) for o, v in sorted(p.items())} for c, p in sorted(soma["cnpjs"].items())},
            "fora": [soma["fora"][0], round(soma["fora"][1], 2)]}


def juntar(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """A soma de duas somas, sem mudar as duas."""
    cnpjs = {c: dict(p) for c, p in a["cnpjs"].items()}
    for c, p in b["cnpjs"].items():
        destino = cnpjs.setdefault(c, {})
        for o, v in p.items():
            destino[o] = round(destino.get(o, 0.0) + v, 2)
    return {"cnpjs": cnpjs, "fora": [a["fora"][0] + b["fora"][0], round(a["fora"][1] + b["fora"][1], 2)]}


def por_ano(dados: dict) -> dict[str, dict[str, Any]]:
    """Os anos do estado com os meses recentes somados: ``{ano: soma}``."""
    anos = dict(dados.get("anos") or {})
    for mes, soma in (dados.get("recentes") or {}).items():
        anos[mes[:4]] = juntar(anos.get(mes[:4]) or soma_vazia(), soma)
    return anos


def ler_estado(caminho: Path) -> dict | None:
    """O estado, se existe e está na versão conhecida."""
    if not caminho.exists():
        return None
    dados = ler_json(caminho)
    return dados if dados.get("versao") == VERSAO_ESTADO else None


@dataclass
class ResultadoRecebimentos:
    """O que a coleta fez: os meses publicados, os baixados, os que faltam e se a CGU pediu verificação."""

    meses: int = 0
    baixados: list[str] = field(default_factory=list)
    faltam: int = 0
    verificacao: str | None = None

    def para_json(self) -> dict:
        """Resumo para imprimir na linha de comando."""
        return {"meses": self.meses, "baixados": self.baixados, "faltam": self.faltam,
                "verificacao_humana": self.verificacao}


def coletar(estado: Path | str, *, contato: str, temporario: Path | None = None, anos: list[int] | None = None,
            limite: int = LIMITE_MESES, pausa: float = PAUSA_S, meses_fn=meses_disponiveis, baixar_fn=baixar,
            dormir: Callable[[float], None] = time.sleep) -> ResultadoRecebimentos:
    """Baixa os meses recentes e os que faltam (até ``limite``) e grava ``ARQUIVO`` depois de cada um.

    O mês que sai da janela dos ``RECENTES`` é fixado no ano dele. Os antigos que faltam vêm do mais novo para o
    mais antigo. Com a verificação humana da CGU, para e devolve o que conseguiu. ``anos`` limita a coleta.
    """
    caminho = Path(estado) / ARQUIVO
    dados = ler_estado(caminho) or {}
    fixados: set[str] = set(dados.get("fixados") or [])
    anos_fixos: dict[str, Any] = dict(dados.get("anos") or {})
    recentes: dict[str, Any] = dict(dados.get("recentes") or {})
    nomes: dict[str, str] = dict(dados.get("nomes") or {})
    orgaos: dict[str, str] = dict(dados.get("orgaos") or {})
    meses = [m for m in meses_fn(contato=contato) if not anos or int(m[:4]) in anos]
    janela = meses[-RECENTES:]
    for mes in sorted(set(recentes) - set(janela)):
        if mes not in fixados:
            anos_fixos[mes[:4]] = juntar(anos_fixos.get(mes[:4]) or soma_vazia(), recentes[mes])
            fixados.add(mes)
        del recentes[mes]
    antigos = [m for m in reversed(meses) if m not in janela and m not in fixados]
    fila = [*reversed(janela), *antigos][:limite]
    resultado = ResultadoRecebimentos(meses=len(meses))

    def gravar() -> None:
        Path(estado).mkdir(parents=True, exist_ok=True)
        gravar_json(caminho, {"versao": VERSAO_ESTADO, "coletado_em": instante_utc(), "fonte": FONTE,
                              "fixados": sorted(fixados), "anos": dict(sorted(anos_fixos.items())),
                              "recentes": dict(sorted(recentes.items())), "orgaos": dict(sorted(orgaos.items())),
                              "nomes": dict(sorted(nomes.items()))}, comprimir=True)

    pasta = Path(tempfile.mkdtemp(prefix="recebimentos-", dir=temporario))
    try:
        for i, mes in enumerate(fila):
            if i:
                dormir(pausa)
            try:
                arquivo = baixar_fn(mes, pasta / f"{mes}_Despesas.zip", contato=contato)
            except VerificacaoHumana as erro:
                resultado.verificacao = str(erro)
                break
            soma = somar_mes(arquivo, nomes, orgaos, nomes_novos=mes == meses[-1])
            arquivo.unlink(missing_ok=True)
            if mes in janela:
                recentes[mes] = soma
            else:
                anos_fixos[mes[:4]] = juntar(anos_fixos.get(mes[:4]) or soma_vazia(), soma)
                fixados.add(mes)
            resultado.baixados.append(mes)
            gravar()
    finally:
        shutil.rmtree(pasta, ignore_errors=True)
    if not caminho.exists():
        gravar()
    resultado.faltam = len([m for m in meses if m not in janela and m not in fixados])
    return resultado
