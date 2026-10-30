"""Votos por hora: quantos eleitores votaram em cada hora, pelos registros (logs) das urnas (ADR-057).

O TSE publica, de 2022 em diante, os arquivos que cada urna transmitiu para a totalização
(``bu_imgbu_logjez_rdv_vscmr_<ano>_<turno>t_<UF>.zip``, conjunto ``resultados-<ano>-arquivos-transmitidos-para-
totalizacao``). Cada seção tem ali o boletim, a imagem do boletim, o registro digital do voto, as assinaturas e o
log (``o<pleito><uf><município><zona><seção>-log.jez``, um ZIP com ``logd.dat``). No log, cada voto deixa a linha::

    04/10/2026 14:40:05	INFO	02263093	VOTA	O voto do eleitor foi computado	C8059082A7F11D8E

com a hora do relógio da urna (horário local da seção). O log também traz o título de mesários e outros dados que
não interessam aqui: só a contagem de votos por faixa de 10 minutos sai da leitura; nenhuma linha é guardada.

Tamanho e leitura. Os arquivos são enormes (2026: 219 GB nos dois turnos; o 2º turno de SP tem 26 GB), mas o log
é perto de metade e cada um é pequeno (perto de 90 KB). ``LeitorRemoto`` lê o índice do ZIP (o diretório central,
no fim do arquivo) e busca só os logs, um pedido HTTP ``Range`` por seção, em várias conexões ao mesmo tempo: nada
vai para o disco. O log do 2º turno traz também o do 1º (é o mesmo registro, acumulado): conta só o último dia com
votos do log, que é o do turno do arquivo.

Horário de Brasília. Desde 2022 a votação vai das 8h às 17h de Brasília: a diferença de cada seção sai da hora em
que a urna ficou "pronta para receber votos" (6h no Acre, 2 horas de diferença); vale a diferença mais comum entre
as seções do município, porque uma urna trocada fica pronta mais tarde. No exterior, o horário fica o local.

Arquivos gravados (JSON comprimido com gzip), no site dos painéis, como os horários das urnas (ADR-056)::

    votos-hora/<ano>/br.json.gz             o Brasil e cada UF, por turno
    votos-hora/<ano>/uf-<sigla>.json.gz     a UF e cada município
    votos-hora/<ano>/mu/<grupo>.json.gz     os municípios do grupo (3º e 4º dígitos do IBGE): zonas e seções

A coleta é por UF (``coletar``, que grava a parcial da UF) e a montagem junta as parciais do ano (``montar``):
no GitHub Actions, cada UF roda num job à parte.
"""

from __future__ import annotations

import gzip
import http.client
import json
import os
import re
import ssl
import struct
import tarfile
import threading
import time
import urllib.parse
import urllib.request
import zipfile
import zlib
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Callable, Iterable, Iterator

from .eleitorado import UF_EXTERIOR
from .municipios import CadastroMunicipios, nome_da_uf

CATALOGO = ("https://dadosabertos.tse.jus.br/api/3/action/package_show"
            "?id=resultados-{ano}-arquivos-transmitidos-para-totalizacao")
ANOS_VOTOS = (2026, 2024, 2022)
VERSAO_VOTOS = 1
DIR_VOTOS = "votos-hora/{ano}"
ABERTURA_OFICIAL = 8 * 60            # 8h de Brasília
PASSO = 10                           # minutos de cada faixa
MARCA_VOTO = "\tO voto do eleitor foi computado\t"
MARCA_PRONTA = "\tUrna pronta para receber votos\t"
NOME_LOG = re.compile(r"^o(\d{5})([a-z]{2})(\d{5})(\d{4})(\d{4})-log\.jez$")

# Uma seção lida: [turno, uf, município TSE, zona, seção, diferença para Brasília em minutos (None: sem a linha da
# urna pronta), {faixa de 10 minutos no horário local (minutos desde a meia-noite): votos}]
Secao = list


# ---------------------------------------------------------------- fonte

def urls_do_ano(ano: int, *, user_agent: str, tentativas: int = 3,
                abrir: Callable = urllib.request.urlopen, esperar: Callable[[float], None] = time.sleep,
                existe: Callable[[str], bool] | None = None, turnos: Iterable[int] = ()) -> list[tuple[int, str, str]]:
    """Os arquivos transmitidos das urnas no ano, como ``(turno, UF, URL)``, pelo catálogo de dados abertos.

    Como em ``horarios.urls_do_ano``, o catálogo às vezes responde uma versão antiga (em 30/10/2026, ora com o 2º
    turno de 2026, ora sem): pergunta ``tentativas`` vezes e fica com a resposta que lista mais arquivos. Mesmo
    assim pode faltar o turno de uma UF, ou o turno inteiro: os nomes seguem um padrão, e o turno que falta (dos
    listados em alguma UF e dos ``turnos`` esperados) é procurado no servidor (``existe(url)``, um HEAD) pelo nome
    que teria.
    """
    melhor: list[tuple[int, str, str]] = []
    for i in range(tentativas):
        pedido = urllib.request.Request(CATALOGO.format(ano=ano), headers={"User-Agent": user_agent})
        with abrir(pedido, timeout=60) as resposta:
            recursos = json.loads(resposta.read())["result"]["resources"]
        achados = []
        for r in recursos:
            url = r.get("url") or ""
            m = re.search(r"bu_imgbu_logjez_rdv_vscmr_\d{4}_(\d)t_([A-Za-z]{2})\.zip$", url)
            if m:
                achados.append((int(m.group(1)), m.group(2).lower(), url))
        if len(achados) > len(melhor):
            melhor = achados
        if i + 1 < tentativas:
            esperar(2)
    existe = existe or (lambda url: _existe(url, user_agent))
    return completar(sorted(set(melhor)), existe, turnos)


def completar(urls: list[tuple[int, str, str]], existe: Callable[[str], bool],
              turnos: Iterable[int] = ()) -> list[tuple[int, str, str]]:
    """Acrescenta os turnos que o catálogo não listou (os de outra UF e os ``turnos`` esperados), se o arquivo
    existe no servidor: o endereço é o de um arquivo listado com o turno e a sigla trocados."""
    achados = set(urls)
    modelo = next((url for _, _, url in urls if re.search(r"_\dt_[A-Za-z]{2}\.zip$", url)), None)
    if modelo is None:
        return sorted(achados)
    m = re.search(r"_(\d)t_([A-Za-z]{2})\.zip$", modelo)
    assert m is not None
    for t in sorted({t for t, _, _ in urls} | set(turnos)):
        for uf in sorted({u for _, u, _ in urls}):
            if any(x[0] == t and x[1] == uf for x in achados):
                continue
            url = f"{modelo[:m.start(1)]}{t}t_{uf.upper()}{modelo[m.end(2):]}"
            if existe(url):
                achados.add((t, uf, url))
    return sorted(achados)


def _existe(url: str, user_agent: str) -> bool:
    """O servidor tem o arquivo (HEAD com resposta 200)?"""
    try:
        pedido = urllib.request.Request(url, method="HEAD", headers={"User-Agent": user_agent})
        with urllib.request.urlopen(pedido, timeout=60) as resposta:
            return resposta.status == 200
    except OSError:
        return False


# ---------------------------------------------------------------- ZIP remoto

class ErroRemoto(Exception):
    """O servidor não respondeu ao pedido de um pedaço do arquivo depois das tentativas."""


def _proxy_para(host: str) -> tuple[str, int] | None:
    """O proxy HTTPS do ambiente (``HTTPS_PROXY``), se o host não está em ``NO_PROXY``."""
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    if not proxy or urllib.request.proxy_bypass(host):
        return None
    p = urllib.parse.urlsplit(proxy if "://" in proxy else f"http://{proxy}")
    return p.hostname or "", p.port or 8080


class LeitorRemoto:
    """Lê pedaços de um arquivo HTTPS por ``Range``, com uma conexão persistente por thread e novas tentativas."""

    def __init__(self, url: str, *, user_agent: str, tentativas: int = 5, timeout: float = 120,
                 dormir: Callable[[float], None] = time.sleep):
        """Arquivo em ``url``; ``user_agent`` identifica a coleta (obrigatório, princípio P6)."""
        if not user_agent or not user_agent.strip():
            raise ValueError("user_agent é obrigatório: a coleta precisa se identificar")
        self.url = url
        self._partes = urllib.parse.urlsplit(url)
        self._caminho = self._partes.path + (f"?{self._partes.query}" if self._partes.query else "")
        self.user_agent = user_agent
        self.tentativas = tentativas
        self.timeout = timeout
        self.dormir = dormir
        self.recebidos = 0
        self.pedidos = 0
        self._local = threading.local()
        self._trava = threading.Lock()
        self._contexto = ssl.create_default_context()

    def _conexao(self) -> http.client.HTTPSConnection:
        """A conexão desta thread (aberta na primeira vez, pelo proxy do ambiente quando há)."""
        con = getattr(self._local, "con", None)
        if con is None:
            host, porta = self._partes.hostname or "", self._partes.port or 443
            proxy = _proxy_para(host)
            if proxy:
                con = http.client.HTTPSConnection(proxy[0], proxy[1], timeout=self.timeout, context=self._contexto)
                con.set_tunnel(host, porta)
            else:
                con = http.client.HTTPSConnection(host, porta, timeout=self.timeout, context=self._contexto)
            self._local.con = con
        return con

    def _fechar(self) -> None:
        """Fecha a conexão desta thread depois de um erro; o próximo pedido abre outra."""
        con = getattr(self._local, "con", None)
        if con is not None:
            con.close()
            self._local.con = None

    def ler(self, inicio: int, tamanho: int) -> bytes:
        """Os ``tamanho`` bytes a partir de ``inicio``; ``inicio`` negativo lê os últimos ``-inicio`` bytes."""
        faixa = f"bytes={inicio}" if inicio < 0 else f"bytes={inicio}-{inicio + tamanho - 1}"
        erro: Exception | None = None
        for tentativa in range(1, self.tentativas + 1):
            try:
                con = self._conexao()
                con.request("GET", self._caminho, headers={"Range": faixa, "User-Agent": self.user_agent,
                                                          "Accept-Encoding": "identity"})
                resposta = con.getresponse()
                corpo = resposta.read()
                if resposta.status != 206:
                    raise ErroRemoto(f"HTTP {resposta.status} ao pedir {faixa} de {self.url}")
                with self._trava:
                    self.recebidos += len(corpo)
                    self.pedidos += 1
                return corpo
            except (OSError, http.client.HTTPException, ErroRemoto) as e:
                erro = e
                self._fechar()
                if tentativa < self.tentativas:
                    self.dormir(min(60, 2 ** tentativa))
        raise ErroRemoto(f"{self.url}: {faixa} sem resposta depois de {self.tentativas} tentativas ({erro})")


@dataclass(frozen=True)
class Entrada:
    """Um arquivo dentro do ZIP: nome, método de compressão, tamanho comprimido e onde começa o cabeçalho local."""

    nome: str
    metodo: int
    comprimido: int
    cabecalho: int
    extra: int = 0


def entradas_do_zip(ler: Callable[[int, int], bytes]) -> list[Entrada]:
    """As entradas do ZIP pelo diretório central, com ZIP64 (arquivos e posições acima de 4 GB).

    ``ler(inicio, tamanho)`` devolve os bytes; ``inicio`` negativo, os últimos bytes do arquivo.
    """
    fim = ler(-(22 + 65535 + 20), 0)
    i = fim.rfind(b"PK\x05\x06")
    if i < 0:
        raise ValueError("ZIP sem o fim do diretório central")
    _, _, _, _, total, tam_cd, ini_cd, _ = struct.unpack("<4s4H2LH", fim[i:i + 22])
    if ini_cd == 0xFFFFFFFF or tam_cd == 0xFFFFFFFF or total == 0xFFFF:
        j = fim.rfind(b"PK\x06\x07", 0, i)
        if j < 0:
            raise ValueError("ZIP64 sem o localizador do fim do diretório central")
        _, _, pos64, _ = struct.unpack("<4sLQL", fim[j:j + 20])
        fim64 = ler(pos64, 56)
        if fim64[:4] != b"PK\x06\x06":
            raise ValueError("ZIP64 sem o fim do diretório central")
        _, _, _, _, _, _, _, total, tam_cd, ini_cd = struct.unpack("<4sQ2H2L4Q", fim64)
    cd = ler(ini_cd, tam_cd)
    entradas, p = [], 0
    for _ in range(total):
        if cd[p:p + 4] != b"PK\x01\x02":
            raise ValueError("diretório central fora do formato")
        (_, _, _, _, metodo, _, _, _, comprimido, descomprimido, n_nome, n_extra, n_coment, _, _, _,
         cabecalho) = struct.unpack("<4s6H3L5H2L", cd[p:p + 46])
        nome = cd[p + 46:p + 46 + n_nome].decode("utf-8", "replace")
        extra = cd[p + 46 + n_nome:p + 46 + n_nome + n_extra]
        q = 0
        while q + 4 <= len(extra):
            ident, tam = struct.unpack("<2H", extra[q:q + 4])
            if ident == 1:      # ZIP64: os campos que não couberam em 32 bits, nesta ordem
                campos, r = extra[q + 4:q + 4 + tam], 0
                if descomprimido == 0xFFFFFFFF:
                    r += 8
                if comprimido == 0xFFFFFFFF:
                    comprimido = struct.unpack("<Q", campos[r:r + 8])[0]
                    r += 8
                if cabecalho == 0xFFFFFFFF:
                    cabecalho = struct.unpack("<Q", campos[r:r + 8])[0]
            q += 4 + tam
        entradas.append(Entrada(nome, metodo, comprimido, cabecalho, n_extra))
        p += 46 + n_nome + n_extra + n_coment
    return entradas


def conteudo(ler: Callable[[int, int], bytes], e: Entrada) -> bytes:
    """O conteúdo descomprimido de uma entrada: um pedido com folga para o cabeçalho local; outro, se faltar."""
    folga = 30 + len(e.nome.encode()) + e.extra + 64
    bloco = ler(e.cabecalho, folga + e.comprimido)
    if bloco[:4] != b"PK\x03\x04":
        raise ValueError(f"{e.nome}: cabeçalho local fora do lugar")
    n_nome, n_extra = struct.unpack("<2H", bloco[26:30])
    inicio = 30 + n_nome + n_extra
    dados = bloco[inicio:inicio + e.comprimido]
    if len(dados) < e.comprimido:
        dados += ler(e.cabecalho + inicio + len(dados), e.comprimido - len(dados))
    if e.metodo == 0:
        return dados
    if e.metodo == 8:
        return zlib.decompress(dados, -15)
    raise ValueError(f"{e.nome}: compressão {e.metodo} não suportada")


# ---------------------------------------------------------------- leitura do log

@dataclass
class LogContado:
    """O que sai de um log: o dia contado, a hora local em que a urna ficou pronta e os votos por faixa."""

    dia: str | None = None
    pronta: int | None = None
    faixas: Counter = field(default_factory=Counter)


def contar_log(jez: bytes) -> LogContado:
    """Conta os votos computados do último dia com votos de um ``-log.jez``, por faixa de ``PASSO`` minutos no
    horário local, e acha a hora em que a urna ficou pronta nesse dia. Nenhuma linha é guardada."""
    linhas_por_dia: dict[str, list[int]] = defaultdict(list)
    prontas: dict[str, int] = {}
    with zipfile.ZipFile(BytesIO(jez)) as zf:
        for nome in zf.namelist():
            if not nome.lower().endswith(".dat"):
                continue
            for linha in zf.read(nome).decode("latin-1").splitlines():
                if MARCA_VOTO in linha:
                    linhas_por_dia[linha[:10]].append(int(linha[11:13]) * 60 + int(linha[14:16]))
                elif MARCA_PRONTA in linha:
                    prontas.setdefault(linha[:10], int(linha[11:13]) * 60 + int(linha[14:16]))
    if not linhas_por_dia:
        return LogContado()
    dia = max(linhas_por_dia, key=lambda d: (d[6:10], d[3:5], d[0:2]))
    faixas = Counter(m - m % PASSO for m in linhas_por_dia[dia])
    return LogContado(dia=f"{dia[6:10]}-{dia[3:5]}-{dia[0:2]}", pronta=prontas.get(dia), faixas=faixas)


def diferenca(pronta: int | None) -> int | None:
    """Minutos a somar ao horário local da urna para ter o de Brasília: a hora cheia entre a urna pronta e as 8h
    (0 a 3 horas); sem a hora da urna pronta, None."""
    if pronta is None:
        return None
    return min(max(round((ABERTURA_OFICIAL - pronta) / 60), 0), 3) * 60


@dataclass
class ResumoColeta:
    """O que ``coletar`` leu de uma UF."""

    uf: str
    secoes: int = 0
    votos: int = 0
    sem_votos: int = 0
    megabytes: float = 0
    pedidos: int = 0
    segundos: float = 0

    def para_json(self) -> dict:
        """Dicionário para imprimir em JSON."""
        return {"uf": self.uf, "secoes": self.secoes, "votos": self.votos, "sem_votos": self.sem_votos,
                "megabytes": round(self.megabytes, 1), "pedidos": self.pedidos, "segundos": round(self.segundos)}


def ler_arquivo(turno: int, url: str, *, user_agent: str, trabalhadores: int = 24,
                progresso: Callable[[str], None] | None = None, leitor: LeitorRemoto | None = None,
                ) -> Iterator[Secao]:
    """As seções de um arquivo transmitido (um turno de uma UF), lendo só os logs pela rede."""
    leitor = leitor or LeitorRemoto(url, user_agent=user_agent)
    logs = [e for e in entradas_do_zip(leitor.ler) if NOME_LOG.match(e.nome.rsplit("/", 1)[-1])]
    logs.sort(key=lambda e: e.cabecalho)

    def um(e: Entrada) -> Secao:
        _, uf, tse, zona, secao = NOME_LOG.match(e.nome.rsplit("/", 1)[-1]).groups()  # type: ignore[union-attr]
        contado = contar_log(conteudo(leitor.ler, e))
        return [turno, uf, tse, str(int(zona)), int(secao), diferenca(contado.pronta), dict(contado.faixas)]

    with ThreadPoolExecutor(max_workers=trabalhadores) as pool:
        for i, secao in enumerate(pool.map(um, logs), 1):
            if progresso and i % 2000 == 0:
                progresso(f"      {i} de {len(logs)} seções, {leitor.recebidos / 1e6:,.0f} MB")
            yield secao


def coletar(uf: str, urls: Iterable[tuple[int, str, str]], destino: Path | str, *, user_agent: str,
            trabalhadores: int = 24, progresso: Callable[[str], None] | None = None,
            abrir: Callable[[str], LeitorRemoto] | None = None) -> ResumoColeta:
    """Lê os arquivos da UF (os dois turnos) e grava a parcial ``destino/<uf>.json.gz``: uma linha por seção.

    ``abrir(url)`` dá o leitor de cada arquivo (nos testes, um arquivo em memória)."""
    r = ResumoColeta(uf=uf)
    inicio = time.monotonic()
    secoes: list[Secao] = []
    for turno, uf_url, url in urls:
        if uf_url != uf:
            continue
        if progresso:
            progresso(f"{turno}º turno {uf.upper()}: {url}")
        leitor = abrir(url) if abrir else LeitorRemoto(url, user_agent=user_agent)
        for s in ler_arquivo(turno, url, user_agent=user_agent, trabalhadores=trabalhadores, progresso=progresso,
                             leitor=leitor):
            votos = sum(s[6].values())
            r.secoes += 1
            r.votos += votos
            r.sem_votos += votos == 0
            secoes.append(s)
        r.megabytes += leitor.recebidos / 1e6
        r.pedidos += leitor.pedidos
    r.segundos = time.monotonic() - inicio
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)
    (destino / f"{uf}.json.gz").write_bytes(_gz({"uf": uf, "secoes": secoes}))
    return r


def ler_parciais(pasta: Path | str) -> list[Secao]:
    """As seções das parciais gravadas por ``coletar`` (``<uf>.json.gz``), com as faixas de volta a números."""
    secoes = []
    for caminho in sorted(Path(pasta).glob("*.json.gz")):
        for s in json.loads(gzip.decompress(caminho.read_bytes()))["secoes"]:
            secoes.append([*s[:6], {int(k): v for k, v in s[6].items()}])
    return secoes


# ---------------------------------------------------------------- horário de Brasília e somas

def em_brasilia(secoes: list[Secao]) -> list[Secao]:
    """As seções com as faixas no horário de Brasília, pela diferença mais comum entre as seções do município: a
    urna que ficou pronta tarde (trocada, com defeito) não muda o fuso da seção. No exterior, o horário fica o
    local."""
    comuns: dict[tuple, Counter] = defaultdict(Counter)
    for s in secoes:
        if s[5] is not None:
            comuns[(s[0], s[1], s[2])][s[5]] += 1
    saida = []
    for s in secoes:
        c = comuns.get((s[0], s[1], s[2]))
        d = 0 if s[1] == UF_EXTERIOR or not c else c.most_common(1)[0][0]
        saida.append([*s[:5], d, {f + d: v for f, v in s[6].items()}])
    return saida


def por_hora(faixas: dict[int, int]) -> list[int]:
    """``[primeira hora, votos nela, na seguinte, ...]`` até a última hora com votos; sem votos, ``[]``."""
    horas = Counter()
    for f, v in faixas.items():
        horas[f // 60] += v
    horas = {h: v for h, v in horas.items() if v}
    if not horas:
        return []
    primeira, ultima = min(horas), max(horas)
    return [primeira, *(horas.get(h, 0) for h in range(primeira, ultima + 1))]


def por_faixa(faixas: dict[int, int]) -> dict:
    """``{inicio, passo, contagens}`` de 10 em 10 minutos, da primeira à última faixa com votos."""
    com_votos = [f for f, v in faixas.items() if v]
    if not com_votos:
        return {"inicio": None, "passo": PASSO, "contagens": []}
    inicio, fim = min(com_votos), max(com_votos)
    return {"inicio": inicio, "passo": PASSO, "contagens": [faixas.get(f, 0) for f in range(inicio, fim + 1, PASSO)]}


def _somar(secoes: Iterable[Secao]) -> Counter:
    """Os votos das seções somados por faixa."""
    total: Counter = Counter()
    for s in secoes:
        total.update(s[6])
    return total


def _turnos(secoes: list[Secao], *, completo: bool) -> dict:
    """``{"1": {...}, "2": {...}}``: votos, seções e votos por hora; com ``completo``, também de 10 em 10 minutos."""
    por_turno: dict[int, list[Secao]] = defaultdict(list)
    for s in secoes:
        por_turno[s[0]].append(s)
    saida = {}
    for t, lista in sorted(por_turno.items()):
        faixas = _somar(lista)
        resumo = {"votos": sum(faixas.values()), "secoes": len(lista), "por_hora": por_hora(faixas)}
        if completo:
            resumo["por_faixa"] = por_faixa(faixas)
        saida[str(t)] = resumo
    return saida


def grupo(chave: str) -> str:
    """O arquivo que leva o município: o 3º e o 4º dígitos do código IBGE (100 arquivos, e não os 750 dos
    horários: o site dos painéis está perto do limite de arquivos); ``zz`` para as cidades do exterior."""
    return chave[2:4] if len(chave) == 7 and chave.isdigit() else UF_EXTERIOR


@dataclass
class ResumoVotos:
    """O que ``gravar`` produziu num ano."""

    ano: int
    secoes: int = 0
    votos: int = 0
    municipios: int = 0
    turnos: list[int] = field(default_factory=list)
    sem_cadastro: list[str] = field(default_factory=list)

    def para_json(self) -> dict:
        """Dicionário para imprimir em JSON."""
        return {"ano": self.ano, "secoes": self.secoes, "votos": self.votos, "municipios": self.municipios,
                "turnos": self.turnos, "sem_cadastro": self.sem_cadastro}


def montar(ano: int, secoes: list[Secao], cadastro: CadastroMunicipios, origem: dict) -> tuple[dict[str, dict],
                                                                                              ResumoVotos]:
    """Os arquivos do ano (caminho relativo, sem o ``.gz`` → conteúdo) e o resumo."""
    secoes = em_brasilia(secoes)
    base = {"versao": VERSAO_VOTOS, "tipo": "votos-hora", "ano": ano, "horario": "brasilia"}
    r = ResumoVotos(ano=ano, secoes=len(secoes), votos=sum(sum(s[6].values()) for s in secoes),
                    turnos=sorted({s[0] for s in secoes}))
    por_uf: dict[str, list[Secao]] = defaultdict(list)
    por_mu: dict[tuple[str, str], list[Secao]] = defaultdict(list)
    for s in secoes:
        por_uf[s[1]].append(s)
        por_mu[(s[1], s[2])].append(s)
    dir_ano = DIR_VOTOS.format(ano=ano)
    grupos: dict[str, dict[str, dict]] = defaultdict(dict)
    resumos_mu: dict[str, dict[str, dict]] = defaultdict(dict)
    for (uf, tse), lista in sorted(por_mu.items()):
        cad = cadastro.por_tse(uf, tse)
        if cad is None or (uf != UF_EXTERIOR and not cad.ibge):
            r.sem_cadastro.append(f"{uf}{tse}")
            continue
        zonas: dict[str, list[Secao]] = defaultdict(list)
        for s in lista:
            zonas[s[3]].append(s)
        grupos[grupo(cad.chave)][cad.chave] = {
            **base, "nivel": "municipio",
            "lugar": {"chave": cad.chave, "uf": uf, "nome": cad.nome, "turnos": _turnos(lista, completo=True)},
            "zonas": [{"zona": z, "turnos": _turnos(zs, completo=False)}
                      for z, zs in sorted(zonas.items(), key=lambda kv: int(kv[0]))],
            # [turno, zona, seção, primeira hora, votos nela, na seguinte, ...]
            "secoes": [[s[0], s[3], s[4], *por_hora(s[6])]
                       for s in sorted(lista, key=lambda s: (s[0], int(s[3]), s[4]))],
        }
        resumos_mu[uf][cad.chave] = {"nome": cad.nome, "turnos": _turnos(lista, completo=False)}
        r.municipios += 1
    arquivos: dict[str, dict] = {}
    for g, municipios in sorted(grupos.items()):
        arquivos[f"{dir_ano}/mu/{g}.json"] = {"versao": VERSAO_VOTOS, "tipo": "votos-hora-grupo", "ano": ano,
                                              "horario": "brasilia", "origem": origem, "municipios": municipios}

    def nome(uf: str) -> str:
        return "Exterior" if uf == UF_EXTERIOR else (nome_da_uf(uf) or uf.upper())
    for uf, lista in sorted(por_uf.items()):
        arquivos[f"{dir_ano}/uf-{uf}.json"] = {
            **base, "origem": origem, "nivel": "uf",
            "lugar": {"chave": uf, "nome": nome(uf), "turnos": _turnos(lista, completo=True)},
            "partes": dict(sorted(resumos_mu[uf].items(), key=lambda kv: kv[1]["nome"])),
        }
    arquivos[f"{dir_ano}/br.json"] = {
        **base, "origem": origem, "nivel": "br",
        # O Brasil sem o exterior: lá o horário é o local de cada país
        "lugar": {"chave": "br", "nome": "Brasil",
                  "turnos": _turnos([s for s in secoes if s[1] != UF_EXTERIOR], completo=True)},
        "partes": {uf: {"nome": nome(uf), "turnos": _turnos(lista, completo=False)}
                   for uf, lista in sorted(por_uf.items())},
    }
    return arquivos, r


def _gz(dados: dict) -> bytes:
    """JSON compacto comprimido com gzip, sem data no cabeçalho."""
    return gzip.compress(json.dumps(dados, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
                         compresslevel=9, mtime=0)


def gravar(ano: int, secoes: list[Secao], raiz: Path | str, cadastro: CadastroMunicipios, *,
           urls: Iterable[str] = ()) -> ResumoVotos:
    """Grava ``votos-hora/<ano>/`` sob ``raiz`` (``.json.gz``) e apaga o que sobrou de uma gravação anterior."""
    origem = {"fonte": "dados_abertos", "conjunto": f"resultados-{ano}-arquivos-transmitidos-para-totalizacao",
              "urls": sorted(urls)}
    arquivos, r = montar(ano, secoes, cadastro, origem)
    raiz = Path(raiz)
    gravados = set()
    for relativo, dados in arquivos.items():
        caminho = raiz / f"{relativo}.gz"
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_bytes(_gz(dados))
        gravados.add(caminho)
    for antigo in (raiz / DIR_VOTOS.format(ano=ano)).rglob("*.json.gz"):
        if antigo not in gravados:
            antigo.unlink()
    return r


def empacotar(ano: int, raiz: Path | str, destino: Path | str) -> Path:
    """Junta ``votos-hora/<ano>/`` em ``destino/votos-hora-<ano>.tar`` (como ``horarios.empacotar``)."""
    raiz = Path(raiz)
    saida = Path(destino) / f"votos-hora-{ano}.tar"
    saida.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(saida, "w", format=tarfile.PAX_FORMAT) as tar:
        for caminho in sorted((raiz / DIR_VOTOS.format(ano=ano)).rglob("*.json.gz")):
            info = tarfile.TarInfo(caminho.relative_to(raiz).as_posix())
            info.size, info.mtime, info.mode = caminho.stat().st_size, 0, 0o644
            with open(caminho, "rb") as f:
                tar.addfile(info, f)
    return saida
