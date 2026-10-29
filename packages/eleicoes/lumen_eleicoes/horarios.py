"""Horários das urnas: quando cada seção abriu, fechou e quando o boletim chegou ao TSE (ADR-056).

O boletim de urna de cada seção vem dos dados abertos do TSE como tabela (``bweb_<turno>t_<UF>_<data>.zip``, de
2018 em diante; o conjunto ``resultados-<ano>-boletim-de-urna`` lista os arquivos). Uma linha por seção, cargo e
número votado; a seção repete, em todas as linhas dela, os dados que interessam aqui:

- ``DT_ABERTURA`` e ``DT_ENCERRAMENTO``: quando a urna abriu e fechou, no horário local da seção;
- ``DT_EMISSAO_BU``: quando a urna emitiu o boletim, também no horário local (de 2020 em diante);
- ``DT_BU_RECEBIDO``: quando o boletim chegou ao TSE, no horário de Brasília (de 2020 em diante);
- ``QT_APTOS``, ``QT_COMPARECIMENTO`` e ``QT_ABSTENCOES`` da seção e o tipo de urna (apurada, votação manual...).

Horário local e de Brasília. Desde 2022 a votação é das 8h às 17h de Brasília no país todo: no Acre a urna abre
às 6h locais. A diferença de cada município sai da hora de abertura das seções dele (a mais comum) e os horários
de abertura, encerramento e emissão passam para o de Brasília, comparáveis entre as UFs. Antes de 2022 a votação
era das 8h às 17h locais, e os horários ficam como vieram (``horario: "local"``). No exterior, sempre locais.

Arquivos gravados (JSON comprimido com gzip), no site dos painéis, como o eleitorado (ADR-055)::

    horarios/<ano>/br.json.gz             o Brasil e cada UF, por turno
    horarios/<ano>/uf-<sigla>.json.gz     a UF e o resumo de cada município
    horarios/<ano>/mu/<grupo>.json.gz     os municípios do grupo: as zonas e cada seção

Os arquivos do 1º turno são grandes (SP: 1,4 GB comprimido; o país, perto de 5 GB), mas só a primeira linha de
cada seção é lida inteira (``ler_csv``): MG leva perto de um minuto. ``lumen eleicoes horarios`` baixa uma UF
por vez, lê e apaga o ZIP antes da próxima.
"""

from __future__ import annotations

import csv
import gzip
import io
import json
import tarfile
import time
import urllib.request
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable

from .eleitorado import UF_EXTERIOR, grupo
from .municipios import CadastroMunicipios, nome_da_uf

CATALOGO = "https://dadosabertos.tse.jus.br/api/3/action/package_show?id=resultados-{ano}-boletim-de-urna"
ANOS_HORARIOS = (2026, 2024, 2022, 2020, 2018)
ANO_HORARIO_UNIFICADO = 2022
VERSAO_HORARIOS = 1
DIR_HORARIOS = "horarios/{ano}"
ABERTURA_OFICIAL = 8 * 60           # 8h (de Brasília desde 2022; local antes)
ENCERRAMENTO_OFICIAL = 17 * 60      # 17h
FILA = ENCERRAMENTO_OFICIAL + 30    # fechar depois das 17h30 é sinal de fila na hora de encerrar
PASSO = 10                          # minutos de cada barra dos gráficos

# Nomes de coluna que mudam de um ano para o outro (2018: "SG_ UF", com espaço)
ALIASES = {"SG_ UF": "SG_UF"}
COLUNAS = ("NR_TURNO", "SG_UF", "CD_MUNICIPIO", "NR_ZONA", "NR_SECAO", "NR_LOCAL_VOTACAO", "QT_APTOS",
           "QT_COMPARECIMENTO", "QT_ABSTENCOES", "DS_TIPO_URNA", "DT_ABERTURA", "DT_ENCERRAMENTO")
OPCIONAIS = ("DT_EMISSAO_BU", "DT_BU_RECEBIDO")

# Uma seção lida: [turno, uf, município TSE, zona, seção, local, aptos, comparecimento, abstenções, tipo de urna,
# abertura, encerramento, emissão, recebido] — os quatro horários em minutos desde a meia-noite do dia da eleição
# (horário como veio: local nos três primeiros, Brasília no recebido); None quando ausente.
Secao = list


# ---------------------------------------------------------------- fonte

def urls_do_ano(ano: int, *, user_agent: str, tentativas: int = 3,
                abrir: Callable = urllib.request.urlopen, esperar: Callable[[float], None] = time.sleep,
                ) -> list[tuple[int, str, str]]:
    """Os arquivos de boletim de urna do ano, como ``(turno, UF, URL)``, pelo catálogo de dados abertos do TSE.

    O catálogo às vezes responde uma versão antiga (em 29/10/2026, ora com o 2º turno de 2026, ora sem): pergunta
    ``tentativas`` vezes e fica com a resposta que lista mais arquivos.
    """
    melhor: list[tuple[int, str, str]] = []
    for i in range(tentativas):
        pedido = urllib.request.Request(CATALOGO.format(ano=ano), headers={"User-Agent": user_agent})
        with abrir(pedido, timeout=60) as resposta:
            recursos = json.loads(resposta.read())["result"]["resources"]
        achados = []
        for r in recursos:
            url = r.get("url") or ""
            nome = url.rsplit("/", 1)[-1].lower()
            partes = nome.split("_")
            if nome.startswith("bweb_") and nome.endswith(".zip") and len(partes) >= 3 and partes[1][:1].isdigit():
                achados.append((int(partes[1][0]), partes[2].lower(), url))
        if len(achados) > len(melhor):
            melhor = achados
        if i + 1 < tentativas:
            esperar(2)
    return sorted(set(melhor))


# ---------------------------------------------------------------- leitura

def minutos(texto: str | None, dia: str | None) -> int | None:
    """``"2026-10-25 19:42:19"`` ou ``"25/10/2026 19:42:19"`` → minutos desde a meia-noite de ``dia``
    (``AAAA-MM-DD``, o dia da eleição); ausente ou ilegível → None. Um boletim recebido no dia seguinte passa de
    1.440."""
    if not texto or texto[0] == "#":
        return None
    try:
        if texto[2] == "/":
            momento = datetime.strptime(texto[:19], "%d/%m/%Y %H:%M:%S")
        else:
            momento = datetime.strptime(texto[:19], "%Y-%m-%d %H:%M:%S")
    except (ValueError, IndexError):
        return None
    base = datetime.strptime(dia, "%Y-%m-%d") if dia else momento.replace(hour=0, minute=0, second=0)
    return int((momento - base).total_seconds() // 60)


def _dia(texto: str) -> str | None:
    """O dia (``AAAA-MM-DD``) de um ``DT_PLEITO`` ou de um horário do TSE, nos dois formatos."""
    if not texto or texto[0] == "#":
        return None
    if len(texto) >= 10 and texto[2] == "/":
        return f"{texto[6:10]}-{texto[3:5]}-{texto[0:2]}"
    return texto[:10]


def _numero(linha: list[str], ix: dict[str, int], coluna: str) -> int:
    """Valor inteiro não negativo da coluna; vazio, texto e negativos viram 0."""
    try:
        return max(0, int(linha[ix[coluna]]))
    except (ValueError, IndexError):
        return 0


def ler_csv(fluxo: io.BufferedIOBase, secoes: dict[tuple, Secao] | None = None) -> dict[tuple, Secao]:
    """Lê um CSV de boletim de urna e guarda uma entrada por seção e turno (a primeira linha de cada seção).

    As linhas de uma seção vêm juntas: só a primeira de cada seção passa pelo leitor de CSV; as outras são
    reconhecidas pelo começo da linha (até o número da seção) e puladas, o que deixa a leitura do 1º turno de SP
    (perto de 15 GB descomprimidos) em minutos.
    """
    secoes = {} if secoes is None else secoes
    texto = io.TextIOWrapper(fluxo, encoding="latin-1", newline="")
    cabecalho = next(csv.reader([texto.readline()], delimiter=";"))
    ix = {ALIASES.get(c.strip(), c.strip()): i for i, c in enumerate(cabecalho)}
    faltando = [c for c in COLUNAS if c not in ix]
    if faltando:
        raise ValueError(f"boletim de urna sem as colunas {', '.join(faltando)}")
    corte = max(ix[c] for c in ("NR_TURNO", "SG_UF", "CD_MUNICIPIO", "NR_ZONA", "NR_SECAO")) + 1
    i_dia = ix.get("DT_PLEITO")
    anterior = None
    for bruta in texto:
        prefixo = bruta.split(";", corte)[:corte]
        if prefixo == anterior:
            continue
        anterior = prefixo
        linha = next(csv.reader([bruta], delimiter=";"))
        try:
            turno = int(linha[ix["NR_TURNO"]])
            chave = (turno, linha[ix["SG_UF"]].strip().lower(), str(int(linha[ix["CD_MUNICIPIO"]])).zfill(5),
                     str(int(linha[ix["NR_ZONA"]])), int(linha[ix["NR_SECAO"]]))
        except (ValueError, IndexError):
            continue
        if chave in secoes:
            continue
        dia = _dia(linha[i_dia]) if i_dia is not None else None
        dia = dia or _dia(linha[ix["DT_ABERTURA"]])

        secoes[chave] = [*chave, str(_numero(linha, ix, "NR_LOCAL_VOTACAO")), _numero(linha, ix, "QT_APTOS"),
                         _numero(linha, ix, "QT_COMPARECIMENTO"), _numero(linha, ix, "QT_ABSTENCOES"),
                         linha[ix["DS_TIPO_URNA"]].strip().capitalize(),
                         *(minutos(linha[ix[c]], dia) if c in ix else None
                           for c in ("DT_ABERTURA", "DT_ENCERRAMENTO", "DT_EMISSAO_BU", "DT_BU_RECEBIDO"))]
    return secoes


def ler_zip(caminho: Path | str, secoes: dict[tuple, Secao] | None = None) -> dict[tuple, Secao]:
    """Lê o CSV de um ZIP de boletim de urna (o único CSV dele)."""
    secoes = {} if secoes is None else secoes
    with zipfile.ZipFile(caminho) as zf:
        for nome in zf.namelist():
            if nome.lower().endswith(".csv"):
                with zf.open(nome) as fluxo:
                    ler_csv(fluxo, secoes)
    return secoes


def _ordem_secao(s: Secao) -> tuple:
    """Ordem das seções no arquivo do município: turno, zona (como número) e seção."""
    return (s[0], s[1], s[2], int(s[3]), s[4])


# ---------------------------------------------------------------- horário de Brasília

def diferencas(secoes: Iterable[Secao], ano: int) -> dict[tuple[int, str, str], int]:
    """Minutos a somar aos horários locais de cada município para ter o de Brasília, por ``(turno, uf, tse)``.

    De 2022 em diante, a urna abre às 8h de Brasília: a diferença é a hora cheia mais comum entre 8h e a abertura
    das seções do município (0 em quase todo o país; 60 e 120 no Norte e no Centro-Oeste). Antes, e no exterior,
    os horários ficam locais (diferença 0).
    """
    contagens: dict[tuple[int, str, str], Counter] = defaultdict(Counter)
    for s in secoes:
        if ano >= ANO_HORARIO_UNIFICADO and s[1] != UF_EXTERIOR and s[10] is not None:
            contagens[(s[0], s[1], s[2])][round((ABERTURA_OFICIAL - s[10]) / 60)] += 1
    return {k: (min(max(c.most_common(1)[0][0], 0), 3) * 60) for k, c in contagens.items()}


def em_brasilia(secoes: list[Secao], ano: int) -> list[Secao]:
    """As seções com abertura, encerramento e emissão no horário de Brasília (de 2022 em diante; ver
    ``diferencas``); o recebido já vem nele."""
    dif = diferencas(secoes, ano)
    saida = []
    for s in secoes:
        d = dif.get((s[0], s[1], s[2]), 0)
        saida.append([*s[:10], *(None if v is None else v + d for v in s[10:13]), s[13]])
    return saida


# ---------------------------------------------------------------- resumos

@dataclass
class Histograma:
    """Contagem por faixa de ``passo`` minutos, de ``inicio`` a ``fim``, com o que fica antes e depois."""

    inicio: int
    fim: int
    passo: int = PASSO
    contagens: list[int] = field(default_factory=list)
    antes: int = 0
    depois: int = 0

    def __post_init__(self) -> None:
        """Sem contagens dadas, uma faixa zerada para cada ``passo`` de ``inicio`` a ``fim``."""
        if not self.contagens:
            self.contagens = [0] * ((self.fim - self.inicio) // self.passo)

    def contar(self, valor: int | None) -> None:
        """Conta um horário (em minutos); ausente não conta."""
        if valor is None:
            return
        if valor < self.inicio:
            self.antes += 1
        elif valor >= self.fim:
            self.depois += 1
        else:
            self.contagens[(valor - self.inicio) // self.passo] += 1

    def para_json(self) -> dict:
        """``{inicio, passo, contagens, antes, depois}``."""
        return {"inicio": self.inicio, "passo": self.passo, "contagens": self.contagens, "antes": self.antes,
                "depois": self.depois}


def _percentil(ordenados: list[int], p: float) -> int | None:
    """O percentil ``p`` (0 a 1) de valores já ordenados; vazio → None."""
    if not ordenados:
        return None
    return ordenados[min(len(ordenados) - 1, int(p * len(ordenados)))]


def resumo(secoes: list[Secao], *, completo: bool) -> dict:
    """O resumo de um lugar num turno: seções, aptos, comparecimento, quantas fecharam depois das 17h30 e os
    percentis (mediana, 90% e o último) do encerramento e do recebimento. Com ``completo``, também os
    histogramas da abertura, do encerramento e do recebimento, e os tipos de urna."""
    encerramentos = sorted(s[11] for s in secoes if s[11] is not None)
    recebidos = sorted(s[13] for s in secoes if s[13] is not None)
    saida: dict = {
        "secoes": len(secoes), "aptos": sum(s[6] for s in secoes), "comparecimento": sum(s[7] for s in secoes),
        "depois_17h30": sum(1 for v in encerramentos if v > FILA),
        "encerramento": [_percentil(encerramentos, 0.5), _percentil(encerramentos, 0.9),
                         encerramentos[-1] if encerramentos else None],
        "recebido": [_percentil(recebidos, 0.5), _percentil(recebidos, 0.9), recebidos[-1] if recebidos else None],
    }
    if completo:
        abertura = Histograma(7 * 60 + 30, 10 * 60)
        encerramento = Histograma(16 * 60 + 30, 22 * 60)
        recebimento = Histograma(17 * 60, 24 * 60)
        for s in secoes:
            abertura.contar(s[10])
            encerramento.contar(s[11])
            recebimento.contar(s[13])
        saida["histogramas"] = {"abertura": abertura.para_json(), "encerramento": encerramento.para_json(),
                                "recebido": recebimento.para_json() if recebidos else None}
        saida["tipos_urna"] = dict(Counter(s[9] for s in secoes).most_common())
    return saida


def _por_turno(secoes: list[Secao], *, completo: bool) -> dict:
    """``{"1": resumo, "2": resumo}`` das seções."""
    turnos: dict[int, list[Secao]] = defaultdict(list)
    for s in secoes:
        turnos[s[0]].append(s)
    return {str(t): resumo(lista, completo=completo) for t, lista in sorted(turnos.items())}


def _hhmm(valor: int | None) -> str | None:
    """Minutos → ``"17:42"``; no dia seguinte, ``"+1 08:10"``."""
    if valor is None:
        return None
    dias, resto = divmod(valor, 1440)
    texto = f"{resto // 60:02d}:{resto % 60:02d}"
    return f"+{dias} {texto}" if dias else texto


@dataclass
class ResumoHorarios:
    """O que ``gravar`` produziu num ano."""

    ano: int
    secoes: int = 0
    municipios: int = 0
    turnos: list[int] = field(default_factory=list)
    sem_cadastro: list[str] = field(default_factory=list)

    def para_json(self) -> dict:
        """Dicionário para imprimir em JSON."""
        return {"ano": self.ano, "secoes": self.secoes, "municipios": self.municipios, "turnos": self.turnos,
                "sem_cadastro": self.sem_cadastro}


def montar(ano: int, secoes: list[Secao], cadastro: CadastroMunicipios, origem: dict) -> tuple[dict[str, dict],
                                                                                              ResumoHorarios]:
    """Os arquivos do ano (caminho relativo, sem o ``.gz`` → conteúdo) e o resumo."""
    secoes = em_brasilia(secoes, ano)
    horario = "brasilia" if ano >= ANO_HORARIO_UNIFICADO else "local"
    base = {"versao": VERSAO_HORARIOS, "tipo": "horarios", "ano": ano, "horario": horario}
    r = ResumoHorarios(ano=ano, secoes=len(secoes), turnos=sorted({s[0] for s in secoes}))
    por_uf: dict[str, list[Secao]] = defaultdict(list)
    por_mu: dict[tuple[str, str], list[Secao]] = defaultdict(list)
    for s in secoes:
        por_uf[s[1]].append(s)
        por_mu[(s[1], s[2])].append(s)
    dir_ano = DIR_HORARIOS.format(ano=ano)
    arquivos: dict[str, dict] = {}
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
            "lugar": {"chave": cad.chave, "uf": uf, "nome": cad.nome, "turnos": _por_turno(lista, completo=True)},
            "zonas": [{"zona": z, "turnos": _por_turno(zs, completo=False)}
                      for z, zs in sorted(zonas.items(), key=lambda kv: int(kv[0]))],
            # [turno, zona, seção, local, aptos, comparecimento, tipo de urna, abertura, encerramento, emissão,
            # recebido], os horários como "HH:MM"
            "secoes": [[s[0], s[3], s[4], s[5], s[6], s[7], s[9], *(_hhmm(v) for v in s[10:14])]
                       for s in sorted(lista, key=_ordem_secao)],
        }
        resumos_mu[uf][cad.chave] = {"nome": cad.nome, "turnos": _por_turno(lista, completo=False)}
        r.municipios += 1
    for g, municipios in sorted(grupos.items()):
        arquivos[f"{dir_ano}/mu/{g}.json"] = {"versao": VERSAO_HORARIOS, "tipo": "horarios-grupo", "ano": ano,
                                              "horario": horario, "origem": origem, "municipios": municipios}

    def nome(uf: str) -> str:
        return "Exterior" if uf == UF_EXTERIOR else (nome_da_uf(uf) or uf.upper())
    for uf, lista in sorted(por_uf.items()):
        arquivos[f"{dir_ano}/uf-{uf}.json"] = {
            **base, "origem": origem, "nivel": "uf",
            "lugar": {"chave": uf, "nome": nome(uf), "turnos": _por_turno(lista, completo=True)},
            "partes": dict(sorted(resumos_mu[uf].items(), key=lambda kv: kv[1]["nome"])),
        }
    no_brasil = [s for s in secoes if s[1] != UF_EXTERIOR]
    arquivos[f"{dir_ano}/br.json"] = {
        **base, "origem": origem, "nivel": "br",
        # O Brasil sem o exterior: lá os horários são locais de cada país e não se somam aos de Brasília
        "lugar": {"chave": "br", "nome": "Brasil", "turnos": _por_turno(no_brasil, completo=True)},
        "partes": {uf: {"nome": nome(uf), "turnos": _por_turno(lista, completo=False)}
                   for uf, lista in sorted(por_uf.items())},
    }
    return arquivos, r


def _gz(dados: dict) -> bytes:
    """JSON compacto comprimido com gzip, sem data no cabeçalho."""
    return gzip.compress(json.dumps(dados, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
                         compresslevel=9, mtime=0)


def gravar(ano: int, secoes: list[Secao], raiz: Path | str, cadastro: CadastroMunicipios, *,
           urls: Iterable[str] = ()) -> ResumoHorarios:
    """Grava ``horarios/<ano>/`` sob ``raiz`` (``.json.gz``) e apaga o que sobrou de uma gravação anterior."""
    origem = {"fonte": "dados_abertos", "conjunto": f"resultados-{ano}-boletim-de-urna", "urls": sorted(urls)}
    arquivos, r = montar(ano, secoes, cadastro, origem)
    raiz = Path(raiz)
    gravados = set()
    for relativo, conteudo in arquivos.items():
        caminho = raiz / f"{relativo}.gz"
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_bytes(_gz(conteudo))
        gravados.add(caminho)
    for antigo in (raiz / DIR_HORARIOS.format(ano=ano)).rglob("*.json.gz"):
        if antigo not in gravados:
            antigo.unlink()
    return r


def empacotar(ano: int, raiz: Path | str, destino: Path | str) -> Path:
    """Junta ``horarios/<ano>/`` em ``destino/horarios-<ano>.tar`` (como ``eleitorado.empacotar``)."""
    raiz = Path(raiz)
    saida = Path(destino) / f"horarios-{ano}.tar"
    saida.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(saida, "w", format=tarfile.PAX_FORMAT) as tar:
        for caminho in sorted((raiz / DIR_HORARIOS.format(ano=ano)).rglob("*.json.gz")):
            info = tarfile.TarInfo(caminho.relative_to(raiz).as_posix())
            info.size, info.mtime, info.mode = caminho.stat().st_size, 0, 0o644
            with open(caminho, "rb") as f:
                tar.addfile(info, f)
    return saida

