"""Contratos dos municípios gaúchos registrados no Tribunal de Contas do Estado, pelo LicitaCon (ADR-050).

O TCE-RS publica, sem chave, um ZIP por ano de contrato (``dados/licitacon/contrato/ano/AAAA.csv.zip``) com os
contratos de todos os órgãos que fiscaliza, estaduais e municipais, desde 2016 de forma completa (antes disso, só
os que ainda vigiam quando o LicitaCon começou). Cada ZIP repete a tabela inteira de pessoas (perto de 80 MB), e
os contratos do ano são poucos MB. Por isso o ZIP é lido no servidor, por partes (``Range``): só o ``contrato.csv``
e o ``alteracao.csv`` de cada ano, e o ``pessoas.csv`` uma vez, para os nomes das empresas.

O órgão vira ente pela tabela de órgãos auditados (``orgaos_auditados_rs.csv``): os municipais vão para o
município (código IBGE) e os estaduais para o estado. Consórcios e associações ficam sem ente, como no PNCP,
porque reúnem vários municípios.

Por ente e ano do contrato, o estado guarda (``COLUNAS_ENTE``): quantos contratos, o valor somado, quantos
ficaram fora da soma pelo teto de plausibilidade (o mesmo do painel de contratações, ADR-028), a soma anônima
dos contratos com pessoa física (o CPF nunca é guardado, DOC-08), quantos aditivos e o acréscimo líquido deles.
Por ente, ano e CNPJ, os contratos e o valor de cada empresa; os nomes vêm à parte, com o CPF do MEI
mascarado. A publicação grava ``tce/ente/<grupo>.json.gz``, com o tribunal de cada ente; quando entrar outro
tribunal, o arquivo do grupo passa a juntar os dois (um ente só é fiscalizado por um tribunal).
"""

from __future__ import annotations

import csv
import io
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

from lumen_canonico.documentos import mascarar_cpfs_no_texto

from .cadastro import Cadastro
from .comum import gravar_json, grupo_do_ente, instante_utc, ler_json, tipo_do_ente
from .contratacoes import teto_do_ente

TRIBUNAL = "TCE-RS"
SISTEMA = "LicitaCon"
FONTE = "Tribunal de Contas do Estado do Rio Grande do Sul, dados abertos do LicitaCon (dados.tce.rs.gov.br)"
URL_ANO = "https://dados.tce.rs.gov.br/dados/licitacon/contrato/ano/{ano}.csv.zip"
URL_ORGAOS = "https://dados.tce.rs.gov.br/dados/auxiliar/orgaos_auditados_rs.csv"
ARQUIVO = "tce-rs.json.gz"
VERSAO_ESTADO = 1
PRIMEIRO_ANO = 2016
ESTADO_RS = "43"
SETORES_SEM_ENTE = frozenset({"CONSÓRCIO ADMINISTRATIVO", "ASSOCIAÇÃO"})
COLUNAS_ENTE = ["contratos", "valor", "a_conferir", "pf_contratos", "pf_valor", "aditivos", "aditivos_valor"]
DIAS_ENTRE_LEITURAS = 6        # o ano corrente e o anterior mudam todo dia; basta ler uma vez por semana
BLOCO = 4 << 20
TENTATIVAS = 4
FORNECEDORES_PUBLICADOS = 100


# ------------------------------------------------------------------------------------------ fonte

def _cabecalhos(contato: str) -> dict[str, str]:
    """User-Agent com o contato, como nas outras coletas."""
    return {"User-Agent": f"Lumen (contato: {contato})"}


def _abrir(pedido: urllib.request.Request, *, tentativas: int = TENTATIVAS,
           esperar: Callable[[float], None] = time.sleep):
    """``urlopen`` com novas tentativas para falha de rede e erro 5xx; 404 sobe na hora."""
    for tentativa in range(tentativas):
        try:
            return urllib.request.urlopen(pedido, timeout=120)
        except urllib.error.HTTPError as erro:
            if erro.code < 500 or tentativa + 1 == tentativas:
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if tentativa + 1 == tentativas:
                raise
        esperar(5 * (tentativa + 1))
    raise AssertionError("inalcançável")


def cabecalho(url: str, *, contato: str) -> tuple[int, str] | None:
    """Tamanho e ETag (ou Last-Modified) do arquivo; ``None`` quando ele não existe (404)."""
    try:
        with _abrir(urllib.request.Request(url, method="HEAD", headers=_cabecalhos(contato))) as r:
            return int(r.headers["Content-Length"]), r.headers.get("ETag") or r.headers.get("Last-Modified") or ""
    except urllib.error.HTTPError as erro:
        if erro.code == 404:
            return None
        raise


class ArquivoRemoto(io.RawIOBase):
    """Um arquivo do servidor lido por partes (``Range``), em blocos guardados, para o ``zipfile`` abrir só os
    membros pedidos sem baixar o resto."""

    def __init__(self, url: str, tamanho: int, *, contato: str, bloco: int = BLOCO,
                 abrir: Callable[..., Any] = _abrir):
        """``tamanho`` vem do ``cabecalho``; ``abrir`` é substituível nos testes."""
        super().__init__()
        self.url, self.tamanho, self.contato, self.bloco, self._abrir = url, tamanho, contato, bloco, abrir
        self.posicao = 0
        self._inicio = 0
        self._dados = b""
        self.pedidos = 0

    def readable(self) -> bool:
        """Lê."""
        return True

    def seekable(self) -> bool:
        """Anda para qualquer posição."""
        return True

    def tell(self) -> int:
        """A posição atual."""
        return self.posicao

    def seek(self, deslocamento: int, de: int = io.SEEK_SET) -> int:
        """Muda a posição, como ``io``."""
        base = {io.SEEK_SET: 0, io.SEEK_CUR: self.posicao, io.SEEK_END: self.tamanho}[de]
        self.posicao = max(0, base + deslocamento)
        return self.posicao

    def readinto(self, destino) -> int:
        """Copia o que puder do bloco guardado; fora dele, busca um bloco novo a partir da posição."""
        if self.posicao >= self.tamanho or len(destino) == 0:
            return 0
        if not self._inicio <= self.posicao < self._inicio + len(self._dados):
            fim = min(self.tamanho, self.posicao + max(len(destino), self.bloco)) - 1
            pedido = urllib.request.Request(self.url, headers={**_cabecalhos(self.contato),
                                                               "Range": f"bytes={self.posicao}-{fim}"})
            with self._abrir(pedido) as resposta:
                if resposta.status != 206:
                    raise OSError(f"{self.url}: o servidor não devolveu a parte pedida (HTTP {resposta.status})")
                self._dados = resposta.read()
            self._inicio = self.posicao
            self.pedidos += 1
        i = self.posicao - self._inicio
        n = min(len(destino), len(self._dados) - i)
        destino[:n] = self._dados[i:i + n]
        self.posicao += n
        return n


# ------------------------------------------------------------------------------------------ leitura

@dataclass(frozen=True)
class Orgao:
    """Um órgão auditado: o ente a que pertence (``None`` para consórcio, associação e órgão sem município)."""

    ente: str | None
    nome: str


def ler_orgaos(texto: str) -> dict[str, Orgao]:
    """A tabela de órgãos auditados: municipais no município (código IBGE), estaduais no estado."""
    saida = {}
    for linha in csv.DictReader(io.StringIO(texto.lstrip("﻿"))):
        esfera, setor = linha.get("ESFERA"), (linha.get("SETOR_GOVERNAMENTAL") or "").strip()
        ente = None
        if esfera == "ESTADUAL":
            ente = ESTADO_RS
        elif esfera == "MUNICIPAL" and setor not in SETORES_SEM_ENTE:
            codigo = (linha.get("CD_MUNICIPIO_IBGE") or "").strip()
            ente = codigo if tipo_do_ente(codigo) == "municipio" else None
        saida[linha["CD_ORGAO"]] = Orgao(ente, linha.get("NOME_ORGAO") or "")
    return saida


def _valor(texto: str | None) -> float | None:
    """``"1450.04"`` → 1450.04; vazio ou fora do formato → ``None``."""
    try:
        return float(texto) if texto not in (None, "") else None
    except ValueError:
        return None


def _chave(linha: dict) -> tuple:
    """O contrato: órgão, licitação (número, ano e modalidade), contrato (número e ano) e instrumento."""
    return tuple(linha.get(c) for c in ("CD_ORGAO", "NR_LICITACAO", "ANO_LICITACAO", "CD_TIPO_MODALIDADE",
                                        "NR_CONTRATO", "ANO_CONTRATO", "TP_INSTRUMENTO"))


def _csv(z: zipfile.ZipFile, nome: str):
    """As linhas de um CSV do ZIP, como dicionários, lidas em fluxo."""
    return csv.DictReader(io.TextIOWrapper(z.open(nome), encoding="utf-8-sig", newline=""))


def ler_ano(z: zipfile.ZipFile, orgaos: dict[str, Orgao], teto: Callable[[str], float]) -> dict:
    """Os contratos de um ano: por ente (``COLUNAS_ENTE``), por ente e CNPJ (``[contratos, valor]``) e o que
    ficou sem ente (``[contratos, valor]``). ``teto(ente)`` é o valor acima do qual o contrato conta e não soma."""
    aditivos: dict[tuple, list] = {}
    if "alteracao.csv" in z.namelist():
        for a in _csv(z, "alteracao.csv"):
            x = aditivos.setdefault(_chave(a), [0, 0.0])
            x[0] += 1
            x[1] += (_valor(a.get("VL_ACRESCIMO")) or 0.0) - (_valor(a.get("VL_REDUCAO")) or 0.0)
    entes: dict[str, list] = {}
    fornecedores: dict[str, dict[str, list]] = {}
    sem_ente = [0, 0.0]
    tetos: dict[str, float] = {}
    for c in _csv(z, "contrato.csv"):
        orgao = orgaos.get(c.get("CD_ORGAO") or "")
        ente = orgao.ente if orgao else None
        valor = _valor(c.get("VL_CONTRATO"))
        if ente is None:
            sem_ente[0] += 1
            sem_ente[1] += valor or 0.0
            continue
        if ente not in tetos:
            tetos[ente] = teto(ente)
        conferir = valor is not None and valor > tetos[ente]
        soma = 0.0 if conferir or valor is None else valor
        x = entes.setdefault(ente, [0, 0.0, 0, 0, 0.0, 0, 0.0])
        x[0] += 1
        x[1] += soma
        x[2] += conferir
        aditivo = aditivos.get(_chave(c))
        if aditivo:
            x[5] += aditivo[0]
            x[6] += aditivo[1]
        documento = "".join(d for d in (c.get("NR_DOCUMENTO") or "") if d.isdigit())
        tipo = c.get("TP_DOCUMENTO")
        if tipo == "J" and len(documento) == 14:
            f = fornecedores.setdefault(ente, {}).setdefault(documento, [0, 0.0])
            f[0] += 1
            f[1] += soma
        elif tipo == "F":
            x[3] += 1
            x[4] += soma
    arredondar = lambda v: round(v, 2)  # noqa: E731
    return {
        "entes": {e: [x[0], arredondar(x[1]), x[2], x[3], arredondar(x[4]), x[5], arredondar(x[6])]
                  for e, x in sorted(entes.items())},
        "fornecedores": {e: {c: [n, arredondar(v)] for c, (n, v) in sorted(fs.items())}
                         for e, fs in sorted(fornecedores.items())},
        "sem_ente": [sem_ente[0], arredondar(sem_ente[1])],
    }


def ler_nomes(z: zipfile.ZipFile, cnpjs: set[str]) -> dict[str, str]:
    """O nome de cada CNPJ pedido, da tabela de pessoas do LicitaCon, com o CPF do MEI mascarado."""
    nomes = {}
    for p in _csv(z, "pessoas.csv"):
        if p.get("TP_DOCUMENTO") != "J":
            continue
        documento = "".join(d for d in (p.get("NR_DOCUMENTO") or "") if d.isdigit())
        if documento in cnpjs and p.get("NM_PESSOA"):
            nomes[documento] = mascarar_cpfs_no_texto(p["NM_PESSOA"].strip())
    return nomes


# ------------------------------------------------------------------------------------------ coleta

@dataclass
class ResultadoTce:
    """O que a coleta fez: os anos lidos, os pulados (sem mudança) e os que não existem."""

    lidos: list[int] = field(default_factory=list)
    pulados: list[int] = field(default_factory=list)
    ausentes: list[int] = field(default_factory=list)
    nomes: int = 0
    interrompida: bool = False

    def para_json(self) -> dict:
        """Resumo para imprimir na linha de comando."""
        return {"tribunal": TRIBUNAL, "lidos": self.lidos, "pulados": self.pulados, "ausentes": self.ausentes,
                "nomes": self.nomes, "interrompida": self.interrompida}


def precisa_ler(guardado: dict | None, tamanho: int, etiqueta: str, ano: int, hoje: date) -> bool:
    """O ano tem de ser lido de novo? Nunca lido: sim. Fechado (antes do ano anterior): só se o tamanho mudou,
    porque o tribunal refaz os arquivos toda semana sem mudar o conteúdo. Corrente ou anterior: quando mudou e a
    última leitura tem ``DIAS_ENTRE_LEITURAS`` dias ou mais."""
    if not guardado:
        return True
    if ano < hoje.year - 1:
        return guardado.get("tamanho") != tamanho
    if guardado.get("etiqueta") == etiqueta:
        return False
    lido = datetime.fromisoformat(guardado["lido_em"].replace("Z", "+00:00")).date()
    return (hoje - lido).days >= DIAS_ENTRE_LEITURAS


def coletar(estado: Path | str, cadastro: Cadastro, *, contato: str, hoje: date | None = None,
            anos: list[int] | None = None, limite_minutos: float | None = None,
            cabecalho_fn: Callable[..., tuple[int, str] | None] = cabecalho,
            texto_fn: Callable[[str, str], str] | None = None,
            remoto_fn: Callable[..., Any] = ArquivoRemoto,
            relogio: Callable[[], float] = time.monotonic) -> ResultadoTce:
    """Lê os anos que mudaram e grava ``ARQUIVO`` depois de cada um; no fim, os nomes dos CNPJs novos."""
    hoje = hoje or datetime.now(timezone.utc).date()
    caminho = Path(estado) / ARQUIVO
    dados = ler_json(caminho) if caminho.exists() else {}
    if dados and dados.get("versao") != VERSAO_ESTADO:
        raise ValueError(f"{caminho}: versão {dados.get('versao')!r} do estado do TCE-RS não suportada")
    dados = {"versao": VERSAO_ESTADO, "fonte": FONTE, "tribunal": TRIBUNAL, "sistema": SISTEMA,
             "colunas_ente": COLUNAS_ENTE, "anos": dados.get("anos") or {}, "nomes": dados.get("nomes") or {}}
    texto_fn = texto_fn or _baixar_texto
    orgaos = ler_orgaos(texto_fn(URL_ORGAOS, contato))
    teto = lambda ente: teto_do_ente(ente, cadastro)  # noqa: E731
    resultado = ResultadoTce()
    prazo = relogio() + limite_minutos * 60 if limite_minutos else None
    ultimo_zip = None
    for ano in anos or range(PRIMEIRO_ANO, hoje.year + 1):
        if prazo is not None and relogio() >= prazo:
            resultado.interrompida = True
            break
        url = URL_ANO.format(ano=ano)
        info = cabecalho_fn(url, contato=contato)
        if info is None:
            resultado.ausentes.append(ano)
            continue
        tamanho, etiqueta = info
        ultimo_zip = (url, tamanho)
        if not precisa_ler(dados["anos"].get(str(ano)), tamanho, etiqueta, ano, hoje):
            resultado.pulados.append(ano)
            continue
        with zipfile.ZipFile(remoto_fn(url, tamanho, contato=contato)) as z:
            dados["anos"][str(ano)] = {"tamanho": tamanho, "etiqueta": etiqueta, "lido_em": instante_utc(),
                                       **ler_ano(z, orgaos, teto)}
        resultado.lidos.append(ano)
        Path(estado).mkdir(parents=True, exist_ok=True)
        gravar_json(caminho, {**dados, "coletado_em": instante_utc()}, comprimir=True)
    faltam = {c for a in dados["anos"].values() for fs in a["fornecedores"].values() for c in fs} - set(dados["nomes"])
    if faltam and ultimo_zip and not resultado.interrompida:
        with zipfile.ZipFile(remoto_fn(*ultimo_zip, contato=contato)) as z:
            novos = ler_nomes(z, faltam)
        dados["nomes"].update(novos)
        resultado.nomes = len(novos)
        gravar_json(caminho, {**dados, "coletado_em": instante_utc()}, comprimir=True)
    return resultado


def _baixar_texto(url: str, contato: str) -> str:
    """Um arquivo pequeno (a tabela de órgãos), inteiro, em texto."""
    with _abrir(urllib.request.Request(url, headers=_cabecalhos(contato))) as r:
        return r.read().decode("utf-8-sig")


# ------------------------------------------------------------------------------------------ publicação

def entes_do_estado(dados: dict) -> dict[str, dict]:
    """Por ente: os anos (``COLUNAS_ENTE``) e os fornecedores do maior valor ao menor, cada um com os anos
    (``[CNPJ, nome, [[ano, contratos, valor], ...]]``), até ``FORNECEDORES_PUBLICADOS``."""
    nomes = dados.get("nomes") or {}
    saida: dict[str, dict] = {}
    for ano, a in sorted((dados.get("anos") or {}).items()):
        for ente, linha in a["entes"].items():
            saida.setdefault(ente, {"anos": {}, "_f": {}})["anos"][ano] = linha
        for ente, fs in a["fornecedores"].items():
            por_cnpj = saida.setdefault(ente, {"anos": {}, "_f": {}})["_f"]
            for cnpj, (n, v) in fs.items():
                por_cnpj.setdefault(cnpj, []).append([ano, n, v])
    for registro in saida.values():
        f = registro.pop("_f")
        ordem = sorted(f.items(), key=lambda x: (-sum(v for _, _, v in x[1]), x[0]))[:FORNECEDORES_PUBLICADOS]
        registro["fornecedores"] = [[cnpj, nomes.get(cnpj), anos] for cnpj, anos in ordem]
    return saida


def publicar(estado: Path | str, gravar: Callable[[str, Any], Any], *, gerado_em: str) -> dict | None:
    """Grava ``tce/ente/<grupo>.json.gz`` (comprimido, ``comum.grupo_do_ente``) com os contratos de cada ente
    registrados no tribunal de contas, e devolve o resumo para o índice."""
    caminho = Path(estado) / ARQUIVO
    if not caminho.exists():
        return None
    dados = ler_json(caminho)
    if dados.get("versao") != VERSAO_ESTADO:
        raise ValueError(f"{caminho}: versão {dados.get('versao')!r} do estado do TCE-RS não suportada")
    grupos: dict[str, dict[str, dict]] = {}
    por_ente = entes_do_estado(dados)
    for ente, registro in por_ente.items():
        grupos.setdefault(grupo_do_ente(ente), {})[ente] = {"tribunal": TRIBUNAL, **registro}
    for grupo, entes in sorted(grupos.items()):
        gravar(f"tce/ente/{grupo}.json.gz", {
            "versao": 1, "tipo": "tce-entes", "gerado_em": gerado_em,
            "tribunais": {TRIBUNAL: {"sistema": SISTEMA, "fonte": FONTE, "coletado_em": dados.get("coletado_em"),
                                     "primeiro_ano": PRIMEIRO_ANO}},
            "colunas": COLUNAS_ENTE, "colunas_fornecedor": ["cnpj", "nome", "anos"], "entes": entes,
        })
    anos = dados.get("anos") or {}
    return {"tribunal": TRIBUNAL, "anos": sorted(anos), "entes": len(por_ente),
            "arquivos": len(grupos), "sem_ente": {a: x["sem_ente"] for a, x in sorted(anos.items())}}
