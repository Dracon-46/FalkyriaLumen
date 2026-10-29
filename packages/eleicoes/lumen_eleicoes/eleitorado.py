"""Eleitorado: quantos eleitores, quem são e quem compareceu, do Brasil à seção (ADR-055).

Três arquivos dos dados abertos do TSE, todos com uma linha por combinação de características e a quantidade
de eleitores dela (nunca um eleitor por linha):

- ``perfil_eleitorado_<ano>.zip``: o eleitorado de cada zona de cada município, por gênero, faixa etária,
  grau de escolaridade e estado civil, com quantos têm biometria. É o cadastro fechado antes da eleição
  (o de 2026 foi gerado em 14/7/2026). Desde 2022, um CSV por UF; antes, um só.
- ``perfil_comparecimento_abstencao_<ano>.zip`` (de 2018 em diante): por zona e turno, quantos estavam aptos,
  quantos compareceram e quantos faltaram, pelas mesmas características.
- ``eleitorado_local_votacao_<ano>.zip`` (o mesmo do mapa das zonas, ``zonas.py``): o eleitorado de cada
  seção, com o local de votação.

Ficam de fora, de propósito, as colunas de raça ou cor, deficiência, identidade de gênero, nome social,
povos indígenas e quilombolas e intérprete de Libras: são dados sensíveis (LGPD, art. 5º, II) e o DOC-08,
seção 5.1, manda não publicá-los, mesmo agregados.

Arquivos gravados (JSON comprimido com gzip), publicados no site dos painéis, no GitHub Pages, e não no bucket
das eleições: o Supabase gratuito está perto do limite (ADR-055)::

    eleitorado/<ano>/br.json.gz             o Brasil (com o exterior) e o resumo de cada UF
    eleitorado/<ano>/uf-<sigla>.json.gz     a UF (``zz``: o exterior) e o resumo de cada município
    eleitorado/<ano>/mu/<grupo>.json.gz     os municípios do grupo, cada um com as zonas e as seções

O grupo é o do painel de contratações (o 3º, o 4º e o 5º dígitos do código IBGE; ``zz`` para o exterior): perto
de 700 arquivos por ano em vez de 5.700, para a implantação do GitHub Pages caber no prazo. ``empacotar`` junta
os arquivos de um ano num ``.tar``, guardado como anexo da versão ``painel-estado`` e desempacotado no site.

Cada lugar traz o perfil (``eleitores``, ``biometria`` e as quatro características, cada uma uma lista de
``[rótulo, eleitores]``) e, por turno, ``aptos``, ``comparecimento``, ``abstencao`` e as características
como ``[rótulo, aptos, comparecimento]``.
"""

from __future__ import annotations

import gzip
import io
import json
import tarfile
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from lumen_ingestao.bronze import ArmazemBronze

from . import carga
from . import dados_abertos as da
from .configuracao import ConfiguracaoEleicoes
from .feeds import origem_json
from .municipios import CadastroMunicipios, nome_da_uf
from .transferencia import Manifesto, baixar_arquivo
from .zonas import url_locais

CONJUNTO_PERFIL = "perfil_eleitorado"
CONJUNTO_COMPARECIMENTO = "perfil_comparecimento_abstencao"
# O perfil existe desde 1994, mas com colunas diferentes antes de 2014; o comparecimento por perfil, desde 2018.
ANOS_ELEITORADO = (2026, 2024, 2022, 2020, 2018)
VERSAO_ELEITORADO = 1
# Sobe quando o que sai das mesmas entradas muda: o ``preparar`` grava de novo os anos de uma revisão anterior
REVISAO_ELEITORADO = 1
DIR_ELEITORADO = "eleitorado/{ano}"
UF_EXTERIOR = "zz"

# (chave no arquivo, colunas de código e de rótulo; no comparecimento de 2026 a escolaridade é "grau de instrução")
CARACTERISTICAS = (
    ("genero", ("CD_GENERO",), ("DS_GENERO",)),
    ("faixa_etaria", ("CD_FAIXA_ETARIA",), ("DS_FAIXA_ETARIA",)),
    ("escolaridade", ("CD_GRAU_ESCOLARIDADE", "CD_GRAU_INSTRUCAO"), ("DS_GRAU_ESCOLARIDADE", "DS_GRAU_INSTRUCAO")),
    ("estado_civil", ("CD_ESTADO_CIVIL",), ("DS_ESTADO_CIVIL",)),
)
COLUNAS_LUGAR = ("SG_UF", "CD_MUNICIPIO", "NR_ZONA")
COLUNAS_SECOES = ("NR_TURNO", "SG_UF", "CD_MUNICIPIO", "NR_ZONA", "NR_SECAO", "NR_LOCAL_VOTACAO", "NM_LOCAL_VOTACAO",
                  "QT_ELEITOR_SECAO")

Zona = tuple[str, str, str]                     # (uf, código TSE do município, zona)
Categoria = tuple[int, str]                     # (código, rótulo)


def url_perfil(ano: int) -> str:
    """Endereço do ZIP do perfil do eleitorado de um ano na CDN do TSE."""
    return f"{da.CDN}/{CONJUNTO_PERFIL}/{CONJUNTO_PERFIL}_{ano}.zip"


def url_comparecimento(ano: int) -> str:
    """Endereço do ZIP do comparecimento e da abstenção por perfil de um ano."""
    return f"{da.CDN}/{CONJUNTO_COMPARECIMENTO}/{CONJUNTO_COMPARECIMENTO}_{ano}.zip"


def baixar(cfg: ConfiguracaoEleicoes, url: str, *, bronze: ArmazemBronze | None = None, atualizar: bool = False,
           saida: Callable[[str], None] | None = None) -> tuple[Path, Manifesto]:
    """Baixa um ZIP do eleitorado para ``<arquivos>/eleitorado/`` (retomável, com manifesto) e registra o
    manifesto no bronze."""
    destino = cfg.arquivos / "eleitorado" / url.rsplit("/", 1)[-1]
    escrever = saida or (lambda msg: print(msg, flush=True))
    escrever(url)
    manifesto = baixar_arquivo(url, destino, user_agent=cfg.user_agent, atualizar=atualizar,
                               progresso=carga.progresso_mb(saida=escrever))
    carga.registrar_manifesto(bronze, manifesto)
    return destino, manifesto


# ---------------------------------------------------------------- leitura

# Rótulos que mudam de um arquivo para o outro (a faixa etária inválida é "Inválida" no perfil e "Inválido" no
# comparecimento): ficam iguais, para a categoria sair numa linha só
ROTULOS_IGUAIS = {"Inválido": "Inválida"}


def rotulo(texto: str) -> str:
    """Rótulo do TSE para exibir: ``"ENSINO MÉDIO COMPLETO"`` → ``"Ensino médio completo"``; o que já vem em
    caixa mista (``"30 a 34 anos"``) fica como está."""
    t = " ".join(texto.split())
    t = t[:1] + t[1:].lower() if t.isupper() else t
    return ROTULOS_IGUAIS.get(t, t)


def _codigo(valor: str | None) -> int:
    """Código da característica como inteiro (os negativos são "não informado" ou "inválido")."""
    try:
        return int((valor or "").strip())
    except ValueError:
        return -1


@dataclass
class Perfil:
    """Eleitorado de um lugar: total, com biometria e por característica (código e rótulo → eleitores)."""

    eleitores: int = 0
    biometria: int = 0
    caracteristicas: dict[str, Counter] = field(default_factory=lambda: defaultdict(Counter))

    def somar(self, outro: "Perfil") -> None:
        """Acrescenta o perfil de outro lugar (uma zona ao município, por exemplo)."""
        self.eleitores += outro.eleitores
        self.biometria += outro.biometria
        for nome, contagem in outro.caracteristicas.items():
            self.caracteristicas[nome].update(contagem)


@dataclass
class Comparecimento:
    """Um turno num lugar: aptos, comparecimento e abstenção, no total e por característica."""

    aptos: int = 0
    comparecimento: int = 0
    abstencao: int = 0
    caracteristicas: dict[str, dict[Categoria, list[int]]] = field(
        default_factory=lambda: defaultdict(lambda: defaultdict(lambda: [0, 0])))

    def somar(self, outro: "Comparecimento") -> None:
        """Acrescenta o turno de outro lugar."""
        self.aptos += outro.aptos
        self.comparecimento += outro.comparecimento
        self.abstencao += outro.abstencao
        for nome, categorias in outro.caracteristicas.items():
            for cat, (aptos, comp) in categorias.items():
                alvo = self.caracteristicas[nome][cat]
                alvo[0] += aptos
                alvo[1] += comp


def _colunas_das_caracteristicas(linhas: da.Linhas) -> list[tuple[str, int, int]]:
    """Posição das colunas de código e de rótulo de cada característica neste arquivo (as que existem)."""
    saida = []
    for nome, codigos, rotulos in CARACTERISTICAS:
        cod = next((linhas.indice(c) for c in codigos if linhas.tem(c)), None)
        rot = next((linhas.indice(c) for c in rotulos if linhas.tem(c)), None)
        if cod is not None and rot is not None:
            saida.append((nome, cod, rot))
    return saida


def _zona(linha: list[str], ix: dict[str, int]) -> Zona | None:
    """A zona da linha, ``(uf, código TSE com 5 dígitos, zona)``; None sem zona."""
    zona = da.zona_da_linha(linha[ix["NR_ZONA"]])
    if zona is None:
        return None
    return linha[ix["SG_UF"]].strip().lower(), str(da._int(linha[ix["CD_MUNICIPIO"]])).zfill(5), zona


def ler_perfil(fluxo: io.BufferedIOBase, zonas: dict[Zona, Perfil] | None = None) -> dict[Zona, Perfil]:
    """Lê um CSV do perfil do eleitorado e acumula o perfil de cada zona."""
    zonas = {} if zonas is None else zonas
    linhas = da.Linhas(fluxo, COLUNAS_LUGAR)
    ix = linhas.colunas
    i_qt = linhas.indice("QT_ELEITORES") if linhas.tem("QT_ELEITORES") else linhas.indice("QT_ELEITORES_PERFIL")
    if i_qt is None:
        raise da.FormatoNaoReconhecido("perfil do eleitorado sem QT_ELEITORES nem QT_ELEITORES_PERFIL")
    i_bio = linhas.indice("QT_ELEITORES_BIOMETRIA")
    cols = _colunas_das_caracteristicas(linhas)
    for linha in linhas:
        chave = _zona(linha, ix)
        if chave is None:
            continue
        qt = da._int(linha[i_qt])
        p = zonas.get(chave)
        if p is None:
            p = zonas[chave] = Perfil()
        p.eleitores += qt
        if i_bio is not None:
            p.biometria += da._int(linha[i_bio])
        for nome, cod, rot in cols:
            p.caracteristicas[nome][(_codigo(linha[cod]), rotulo(linha[rot]))] += qt
    return zonas


def ler_comparecimento(fluxo: io.BufferedIOBase, zonas: dict[tuple[Zona, int], Comparecimento] | None = None,
                       ) -> dict[tuple[Zona, int], Comparecimento]:
    """Lê um CSV do comparecimento por perfil e acumula, por zona e turno, aptos, comparecimento e abstenção."""
    zonas = {} if zonas is None else zonas
    linhas = da.Linhas(fluxo, (*COLUNAS_LUGAR, "NR_TURNO", "QT_APTOS", "QT_COMPARECIMENTO", "QT_ABSTENCAO"))
    ix = linhas.colunas
    cols = _colunas_das_caracteristicas(linhas)
    for linha in linhas:
        chave = _zona(linha, ix)
        turno = da._int(linha[ix["NR_TURNO"]])
        if chave is None or turno not in (1, 2):
            continue
        aptos, comp = da._int(linha[ix["QT_APTOS"]]), da._int(linha[ix["QT_COMPARECIMENTO"]])
        c = zonas.get((chave, turno))
        if c is None:
            c = zonas[(chave, turno)] = Comparecimento()
        c.aptos += aptos
        c.comparecimento += comp
        c.abstencao += da._int(linha[ix["QT_ABSTENCAO"]])
        for nome, cod, rot in cols:
            alvo = c.caracteristicas[nome][(_codigo(linha[cod]), rotulo(linha[rot]))]
            alvo[0] += aptos
            alvo[1] += comp
    return zonas


@dataclass
class Secao:
    """Uma seção eleitoral: zona, número, local de votação e eleitorado."""

    zona: str
    numero: int
    local: str
    eleitores: int


def ler_secoes(fluxo: io.BufferedIOBase, municipios: dict[tuple[str, str], list[Secao]] | None = None,
               nomes_locais: dict[tuple[str, str], dict[str, str]] | None = None,
               ) -> tuple[dict[tuple[str, str], list[Secao]], dict[tuple[str, str], dict[str, str]]]:
    """Lê um CSV de locais de votação e guarda as seções de cada município (só o 1º turno: o 2º repete as dos
    municípios que o tiveram) e o nome de cada local, por ``"<zona>-<local>"``."""
    municipios = {} if municipios is None else municipios
    nomes_locais = {} if nomes_locais is None else nomes_locais
    linhas = da.Linhas(fluxo, COLUNAS_SECOES)
    ix = linhas.colunas
    for linha in linhas:
        if da._int(linha[ix["NR_TURNO"]]) != 1:
            continue
        chave = _zona(linha, ix)
        if chave is None:
            continue
        uf, tse, zona = chave
        local = str(da._int(linha[ix["NR_LOCAL_VOTACAO"]]))
        municipios.setdefault((uf, tse), []).append(
            Secao(zona, da._int(linha[ix["NR_SECAO"]]), local, da._int(linha[ix["QT_ELEITOR_SECAO"]])))
        nomes_locais.setdefault((uf, tse), {}).setdefault(f"{zona}-{local}", linha[ix["NM_LOCAL_VOTACAO"]].strip())
    return municipios, nomes_locais


def _ler_zip(caminho: Path | str, leitor: Callable[[io.BufferedIOBase], object]) -> None:
    """Passa cada CSV do ZIP (os por UF; o ``_BRASIL`` só se for o único) ao ``leitor``."""
    with zipfile.ZipFile(caminho) as zf:
        for nome in da.entradas_csv(zf.namelist()):
            with zf.open(nome) as fluxo:
                leitor(fluxo)


# ---------------------------------------------------------------- arquivos

def _ordem(cat: Categoria) -> tuple[int, int]:
    """Ordem das categorias: pelo código (que segue a idade e a escolaridade), com "não informado" no fim."""
    codigo = cat[0]
    return (1, 0) if codigo <= 0 else (0, codigo)


def _juntar_rotulos(itens: Iterable[tuple[Categoria, object]]) -> list[tuple[str, list]]:
    """Agrupa por rótulo, na ordem dos códigos: dois códigos com o mesmo rótulo viram uma linha."""
    saida: dict[str, list] = {}
    for (_cod, rot), valor in sorted(itens, key=lambda kv: _ordem(kv[0])):
        valores = valor if isinstance(valor, list) else [valor]
        atual = saida.get(rot)
        saida[rot] = list(valores) if atual is None else [a + b for a, b in zip(atual, valores)]
    return list(saida.items())


def perfil_json(p: Perfil) -> dict:
    """O perfil para o arquivo: total, biometria e cada característica como ``[rótulo, eleitores]``."""
    saida: dict = {"eleitores": p.eleitores, "biometria": p.biometria}
    for nome, _, _ in CARACTERISTICAS:
        saida[nome] = [[rot, v[0]] for rot, v in _juntar_rotulos(p.caracteristicas.get(nome, {}).items())]
    return saida


def turnos_json(turnos: dict[int, Comparecimento]) -> dict:
    """Os turnos para o arquivo: ``{"1": {aptos, comparecimento, abstencao, <característica>: [[rótulo, aptos,
    comparecimento]]}}``."""
    saida = {}
    for turno in sorted(turnos):
        c = turnos[turno]
        t: dict = {"aptos": c.aptos, "comparecimento": c.comparecimento, "abstencao": c.abstencao}
        for nome, _, _ in CARACTERISTICAS:
            t[nome] = [[rot, *v] for rot, v in _juntar_rotulos(c.caracteristicas.get(nome, {}).items())]
        saida[str(turno)] = t
    return saida


def resumo_json(p: Perfil, turnos: dict[int, Comparecimento]) -> dict:
    """O resumo de um lugar dentro do arquivo do lugar acima: eleitores, biometria e o comparecimento de cada
    turno (``[aptos, comparecimento]``)."""
    return {"eleitores": p.eleitores, "biometria": p.biometria,
            "turnos": {str(t): [c.aptos, c.comparecimento] for t, c in sorted(turnos.items())}}


@dataclass
class _Lugar:
    """Um lugar sendo somado: o perfil e os turnos."""

    perfil: Perfil = field(default_factory=Perfil)
    turnos: dict[int, Comparecimento] = field(default_factory=lambda: defaultdict(Comparecimento))

    def somar(self, outro: "_Lugar") -> None:
        """Acrescenta outro lugar a este."""
        self.perfil.somar(outro.perfil)
        for t, c in outro.turnos.items():
            self.turnos[t].somar(c)


@dataclass
class ResumoEleitorado:
    """O que ``gravar_eleitorado`` produziu num ano, para o resumo da linha de comando."""

    ano: int
    eleitores: int = 0
    ufs: int = 0
    municipios: int = 0
    zonas: int = 0
    secoes: int = 0
    turnos: list[int] = field(default_factory=list)
    sem_cadastro: list[str] = field(default_factory=list)

    def para_json(self) -> dict:
        """Dicionário para imprimir em JSON."""
        return {"ano": self.ano, "eleitores": self.eleitores, "ufs": self.ufs, "municipios": self.municipios,
                "zonas": self.zonas, "secoes": self.secoes, "turnos": self.turnos, "sem_cadastro": self.sem_cadastro}


def _origens(manifestos: dict[str, Manifesto | None], urls: dict[str, str]) -> dict:
    """O bloco ``origem`` de cada arquivo lido (perfil, comparecimento e seções)."""
    saida = {}
    for nome, url in urls.items():
        m = manifestos.get(nome)
        saida[nome] = origem_json("dados_abertos", url=m.url if m else url, sha256=m.sha256 if m else None,
                                  coletado_em=m.baixado_em if m else None)
    return saida


def grupo(chave: str) -> str:
    """O arquivo que leva o município: o 3º, o 4º e o 5º dígitos do código IBGE (como ``comum.grupo_do_ente``
    dos painéis); ``zz`` para as cidades do exterior (``zz-<código TSE>``)."""
    return chave[2:5] if len(chave) == 7 and chave.isdigit() else UF_EXTERIOR


def montar(ano: int, perfis: dict[Zona, Perfil], comparecimentos: dict[tuple[Zona, int], Comparecimento],
           secoes: dict[tuple[str, str], list[Secao]], nomes_locais: dict[tuple[str, str], dict[str, str]],
           cadastro: CadastroMunicipios, origem: dict) -> tuple[dict[str, dict], ResumoEleitorado]:
    """Os arquivos do ano (caminho relativo, sem o ``.gz`` → conteúdo) e o resumo.

    Município sem lugar no cadastro (sem código IBGE no Brasil) fica de fora e é anotado no resumo.
    """
    resumo = ResumoEleitorado(ano=ano)
    zonas: dict[Zona, _Lugar] = defaultdict(_Lugar)
    for chave, p in perfis.items():
        zonas[chave].perfil = p
    for (chave, turno), c in comparecimentos.items():
        zonas[chave].turnos[turno] = c
    resumo.turnos = sorted({t for _, t in comparecimentos})

    municipios: dict[tuple[str, str], dict[str, _Lugar]] = defaultdict(dict)
    for (uf, tse, zona), lugar in zonas.items():
        municipios[(uf, tse)][zona] = lugar
    brasil = _Lugar()
    ufs: dict[str, _Lugar] = defaultdict(_Lugar)
    resumos_mu: dict[str, dict[str, dict]] = defaultdict(dict)
    dir_ano = DIR_ELEITORADO.format(ano=ano)
    arquivos: dict[str, dict] = {}
    grupos: dict[str, dict[str, dict]] = defaultdict(dict)
    base = {"versao": VERSAO_ELEITORADO, "tipo": "eleitorado", "ano": ano, "origem": origem}
    # Cada município do grupo, sem a origem (que vai uma vez no arquivo do grupo)
    base_mu = {"versao": VERSAO_ELEITORADO, "tipo": "eleitorado", "ano": ano}
    for (uf, tse), zonas_mu in sorted(municipios.items()):
        cad = cadastro.por_tse(uf, tse)
        if cad is None or (uf != UF_EXTERIOR and not cad.ibge):
            resumo.sem_cadastro.append(f"{uf}{tse}")
            continue
        mu = _Lugar()
        for lugar in zonas_mu.values():
            mu.somar(lugar)
        ufs[uf].somar(mu)
        brasil.somar(mu)
        lista = sorted(secoes.get((uf, tse), []), key=lambda s: (int(s.zona), s.numero))
        grupos[grupo(cad.chave)][cad.chave] = {
            **base_mu, "nivel": "municipio",
            "lugar": {"chave": cad.chave, "uf": uf, "nome": cad.nome, **perfil_json(mu.perfil),
                      "turnos": turnos_json(mu.turnos)},
            "zonas": [{"zona": z, **perfil_json(lugar.perfil), "turnos": turnos_json(lugar.turnos)}
                      for z, lugar in sorted(zonas_mu.items(), key=lambda kv: int(kv[0]))],
            # [zona, seção, local, eleitores]; o nome do local em "locais", por "<zona>-<local>"
            "secoes": [[s.zona, s.numero, s.local, s.eleitores] for s in lista],
            "locais": dict(sorted((nomes_locais.get((uf, tse)) or {}).items())),
        }
        resumos_mu[uf][cad.chave] = {"nome": cad.nome, "zonas": len(zonas_mu), "secoes": len(lista),
                                     **resumo_json(mu.perfil, mu.turnos)}
        resumo.municipios += 1
        resumo.zonas += len(zonas_mu)
        resumo.secoes += len(lista)
    for g, municipios_do_grupo in sorted(grupos.items()):
        arquivos[f"{dir_ano}/mu/{g}.json"] = {"versao": VERSAO_ELEITORADO, "tipo": "eleitorado-grupo", "ano": ano,
                                              "origem": origem, "municipios": municipios_do_grupo}
    for uf, lugar in sorted(ufs.items()):
        nome = "Exterior" if uf == UF_EXTERIOR else (nome_da_uf(uf) or uf.upper())
        arquivos[f"{dir_ano}/uf-{uf}.json"] = {
            **base, "nivel": "uf",
            "lugar": {"chave": uf, "nome": nome, **perfil_json(lugar.perfil), "turnos": turnos_json(lugar.turnos)},
            "partes": dict(sorted(resumos_mu[uf].items(), key=lambda kv: kv[1]["nome"])),
        }
    arquivos[f"{dir_ano}/br.json"] = {
        **base, "nivel": "br",
        "lugar": {"chave": "br", "nome": "Brasil", **perfil_json(brasil.perfil), "turnos": turnos_json(brasil.turnos)},
        "partes": {uf: {"nome": "Exterior" if uf == UF_EXTERIOR else (nome_da_uf(uf) or uf.upper()),
                        **resumo_json(lugar.perfil, lugar.turnos)} for uf, lugar in sorted(ufs.items())},
    }
    resumo.eleitores = brasil.perfil.eleitores
    resumo.ufs = len(ufs)
    return arquivos, resumo


def _gz(dados: dict) -> bytes:
    """JSON compacto comprimido com gzip, sem data no cabeçalho: o mesmo conteúdo dá os mesmos bytes."""
    texto = json.dumps(dados, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return gzip.compress(texto, compresslevel=9, mtime=0)


def conferir(arquivos: dict[str, dict]) -> list[str]:
    """Os problemas de contrato nos arquivos montados (``verificacao.verificar_eleitorado``); vazio se tudo bate."""
    from .verificacao import Relatorio, verificar_eleitorado
    rel = Relatorio()
    for relativo, dados in arquivos.items():
        lugares = dados["municipios"].values() if dados.get("tipo") == "eleitorado-grupo" else [dados]
        for lugar in lugares:
            verificar_eleitorado(Path(relativo), lugar, rel)
    return rel.problemas


def gravar_eleitorado(ano: int, raiz: Path | str, cadastro: CadastroMunicipios, *, perfil: Path | str,
                      comparecimento: Path | str | None = None, locais: Path | str | None = None,
                      manifestos: dict[str, Manifesto | None] | None = None,
                      progresso: Callable[[str], None] | None = None) -> ResumoEleitorado:
    """Lê os ZIPs do ano, confere o contrato e grava ``eleitorado/<ano>/`` sob ``raiz`` (``.json.gz``). O que
    não sai desta gravação é apagado, para o diretório ficar igual ao que foi gravado.

    Levanta ``ValueError`` se algum arquivo montado sair do contrato (nada é gravado)."""
    escrever = progresso or (lambda _msg: None)
    manifestos = manifestos or {}
    urls = {"perfil": url_perfil(ano)}
    perfis: dict[Zona, Perfil] = {}
    escrever(f"{ano}: lendo o perfil do eleitorado")
    _ler_zip(perfil, lambda f: ler_perfil(f, perfis))
    comparecimentos: dict[tuple[Zona, int], Comparecimento] = {}
    if comparecimento:
        urls["comparecimento"] = url_comparecimento(ano)
        escrever(f"{ano}: lendo o comparecimento por perfil")
        _ler_zip(comparecimento, lambda f: ler_comparecimento(f, comparecimentos))
    secoes: dict[tuple[str, str], list[Secao]] = {}
    nomes: dict[tuple[str, str], dict[str, str]] = {}
    if locais:
        urls["secoes"] = url_locais(ano)
        escrever(f"{ano}: lendo as seções")
        _ler_zip(locais, lambda f: ler_secoes(f, secoes, nomes))
    arquivos, resumo = montar(ano, perfis, comparecimentos, secoes, nomes, cadastro, _origens(manifestos, urls))
    problemas = conferir(arquivos)
    if problemas:
        raise ValueError(f"eleitorado de {ano} fora do contrato: {'; '.join(problemas[:5])}")
    raiz = Path(raiz)
    gravados = set()
    for relativo, conteudo in arquivos.items():
        caminho = raiz / f"{relativo}.gz"
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_bytes(_gz(conteudo))
        gravados.add(caminho)
    destino = raiz / DIR_ELEITORADO.format(ano=ano)
    for antigo in destino.rglob("*.json.gz"):
        if antigo not in gravados:
            antigo.unlink()
    eleitores = f"{resumo.eleitores:,}".replace(",", ".")
    escrever(f"{ano}: {eleitores} eleitores, {resumo.municipios} municípios, {resumo.secoes} seções")
    return resumo


def empacotar(ano: int, raiz: Path | str, destino: Path | str) -> Path:
    """Junta ``eleitorado/<ano>/`` (já gravado sob ``raiz``) em ``destino/eleitorado-<ano>.tar``, com os caminhos
    a partir de ``raiz`` (o site desempacota na raiz dele). Os arquivos já vêm comprimidos: o ``.tar`` não comprime
    de novo. Ordem e metadados fixos: o mesmo conteúdo dá o mesmo pacote."""
    raiz = Path(raiz)
    pasta = raiz / DIR_ELEITORADO.format(ano=ano)
    saida = Path(destino) / f"eleitorado-{ano}.tar"
    saida.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(saida, "w", format=tarfile.PAX_FORMAT) as tar:
        for caminho in sorted(pasta.rglob("*.json.gz")):
            info = tarfile.TarInfo(caminho.relative_to(raiz).as_posix())
            info.size = caminho.stat().st_size
            info.mtime = 0
            info.mode = 0o644
            with open(caminho, "rb") as f:
                tar.addfile(info, f)
    return saida
