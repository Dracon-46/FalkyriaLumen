"""Base pública de CNPJ da Receita Federal: cadastro e quadro societário dos fornecedores do painel (ADR-043).

A Receita publica a base inteira todo mês num compartilhamento do Nextcloud
(``arquivos.receitafederal.gov.br/index.php/s/YggdBLfdninEJX9``), uma pasta por mês (``2026-10``) com ZIPs de
CSV em ISO-8859-1 separados por ``;``. Em outubro de 2026, perto de 8 GB compactados: Estabelecimentos (5,4 GB),
Empresas (1,4 GB), Sócios (0,7 GB), Simples (0,3 GB) e as tabelas de código (CNAE, natureza jurídica,
qualificação, motivo, município e país). A lista e os arquivos saem pelo WebDAV público do compartilhamento.

Só entram as empresas que aparecem no Lumen: os CNPJs de fornecedor dos contratos guardados no estado do painel
(minimização, DOC-08). Cada ZIP é baixado, lido em fluxo e apagado, um de cada vez; a linha é filtrada pelo CNPJ
antes de passar pelo leitor de CSV, que é a parte cara. O que fica, por ADR-043:

- **empresa**: razão social (com o CPF do MEI mascarado), natureza jurídica, porte e capital social;
- **estabelecimento** (o CNPJ do contrato): matriz ou filial, nome fantasia, situação cadastral, data e motivo,
  data de início da atividade, CNAE principal e secundários, município e UF, e a situação especial. Fica de fora o
  endereço de rua, o telefone e o e-mail;
- **Simples e MEI**: a opção e as datas;
- **sócios**: pessoa jurídica com CNPJ e nome; pessoa física com nome, qualificação e data de entrada, sem o CPF
  parcial; estrangeiro com nome e país. Fora a faixa etária e o representante legal.

O estado é ``cnpj-fornecedores.json.gz``, com o mês da base e as tabelas de código usadas. A publicação abre o
estado em arquivos por prefixo do CNPJ (``cnpj/<3 dígitos>.json.gz``, comprimidos), com os códigos, e os
nomes dos códigos ficam em ``cnpj/tabelas.json``.
"""

from __future__ import annotations

import base64
import csv
import io
import re
import shutil
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator
from xml.etree import ElementTree

from lumen_canonico.documentos import mascarar_cpfs_no_texto

from .comum import gravar_json, instante_utc, ler_json

COMPARTILHAMENTO = "YggdBLfdninEJX9"
WEBDAV = "https://arquivos.receitafederal.gov.br/public.php/webdav"
FONTE = "Receita Federal, dados abertos do CNPJ (arquivos.receitafederal.gov.br)"
ARQUIVO = "cnpj-fornecedores.json.gz"
VERSAO_ESTADO = 1
TENTATIVAS = 4
TABELAS = {"cnae": "Cnaes", "natureza": "Naturezas", "qualificacao": "Qualificacoes", "motivo": "Motivos",
           "municipio": "Municipios", "pais": "Paises"}
SITUACOES = {"01": "Nula", "1": "Nula", "02": "Ativa", "2": "Ativa", "03": "Suspensa", "3": "Suspensa",
             "04": "Inapta", "4": "Inapta", "08": "Baixada", "8": "Baixada"}
PORTES = {"00": "Não informado", "01": "Microempresa", "03": "Empresa de pequeno porte", "05": "Demais"}
TIPOS_SOCIO = {"1": "PJ", "2": "PF", "3": "estrangeiro"}
_MES = re.compile(r"^\d{4}-\d{2}$")
_DAV = "{DAV:}"


# ------------------------------------------------------------------------------------------ fonte

def _cabecalhos(contato: str) -> dict[str, str]:
    """User-Agent com o contato e a autenticação do compartilhamento público (o token é o usuário, sem senha)."""
    credencial = base64.b64encode(f"{COMPARTILHAMENTO}:".encode()).decode()
    return {"User-Agent": f"Lumen (contato: {contato})", "Authorization": f"Basic {credencial}"}


def listar(caminho: str, *, contato: str, tentativas: int = TENTATIVAS,
           esperar: Callable[[float], None] = time.sleep) -> list[tuple[str, int | None]]:
    """Os itens de uma pasta do compartilhamento (``""`` é a raiz): nome e tamanho em bytes (pasta sem tamanho).

    Resposta vazia ou cortada, e falha de rede, são tentadas de novo: em 26/10/2026 a raiz veio vazia uma vez e
    derrubou a coleta da semana."""
    pasta = caminho.strip("/")
    for tentativa in range(tentativas):
        pedido = urllib.request.Request(f"{WEBDAV}/{pasta}/" if pasta else f"{WEBDAV}/", method="PROPFIND",
                                        headers={**_cabecalhos(contato), "Depth": "1"})
        try:
            with urllib.request.urlopen(pedido, timeout=120) as resposta:
                raiz = ElementTree.fromstring(resposta.read())
            break
        except urllib.error.HTTPError as erro:
            if erro.code < 500 or tentativa + 1 == tentativas:
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError, ElementTree.ParseError):
            if tentativa + 1 == tentativas:
                raise
        esperar(10 * (tentativa + 1))
    saida = []
    for r in raiz.findall(f"{_DAV}response"):
        href = (r.findtext(f"{_DAV}href") or "").rstrip("/")
        nome = href.rsplit("/", 1)[-1]
        tamanho = r.findtext(f".//{_DAV}getcontentlength")
        if nome and nome != pasta.rsplit("/", 1)[-1] and nome != "webdav":
            saida.append((nome, int(tamanho) if tamanho else None))
    return saida


def mes_mais_recente(itens: Iterable[tuple[str, int | None]]) -> str | None:
    """A pasta ``AAAA-MM`` mais recente da raiz do compartilhamento."""
    meses = sorted(nome for nome, tamanho in itens if tamanho is None and _MES.match(nome))
    return meses[-1] if meses else None


def baixar(caminho: str, destino: Path, *, contato: str, tentativas: int = TENTATIVAS,
           esperar: Callable[[float], None] = time.sleep) -> Path:
    """Baixa um arquivo do compartilhamento para ``destino``, retomando do ponto em que parou (``Range``)."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    for tentativa in range(tentativas):
        ja = destino.stat().st_size if destino.exists() else 0
        cabecalhos = {**_cabecalhos(contato), **({"Range": f"bytes={ja}-"} if ja else {})}
        try:
            pedido = urllib.request.Request(f"{WEBDAV}/{caminho}", headers=cabecalhos)
            with urllib.request.urlopen(pedido, timeout=300) as resposta, open(destino, "ab" if ja else "wb") as f:
                if ja and resposta.status != 206:
                    f.seek(0)
                    f.truncate()
                shutil.copyfileobj(resposta, f, 1 << 20)
            return destino
        except urllib.error.HTTPError as erro:
            if erro.code == 416:            # já estava completo
                return destino
            if tentativa + 1 == tentativas:
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if tentativa + 1 == tentativas:
                raise
        esperar(10 * (tentativa + 1))
    return destino


def linhas_do_zip(arquivo: Path) -> Iterator[str]:
    """As linhas do CSV (o único arquivo do ZIP), em texto, lidas em fluxo."""
    with zipfile.ZipFile(arquivo) as z, z.open(z.infolist()[0]) as bruto:
        yield from io.TextIOWrapper(bruto, encoding="latin-1", newline="")


def _campos(linha: str) -> list[str]:
    """Os campos de uma linha do CSV da Receita."""
    return next(csv.reader([linha], delimiter=";"))


# ------------------------------------------------------------------------------------------ leitura

def _data(texto: str) -> str | None:
    """``20210518`` → ``2021-05-18``; vazio e ``00000000`` viram nulo."""
    return f"{texto[:4]}-{texto[4:6]}-{texto[6:8]}" if re.fullmatch(r"\d{8}", texto or "") and texto != "00000000" else None


def _numero(texto: str) -> float | None:
    """``120000000000,00`` → 120000000000.0."""
    try:
        return float(texto.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def ler_tabela(linhas: Iterable[str]) -> dict[str, str]:
    """Uma tabela de código da Receita (``"0111301";"Cultivo de arroz"``) como dicionário."""
    saida = {}
    for linha in linhas:
        campos = _campos(linha)
        if len(campos) >= 2 and campos[0]:
            saida[campos[0].strip()] = campos[1].strip()
    return saida


def ler_empresas(linhas: Iterable[str], basicos: set[str]) -> dict[str, dict]:
    """Por CNPJ básico (8 dígitos): razão social com o CPF mascarado, natureza jurídica, porte e capital social."""
    saida = {}
    for linha in linhas:
        if linha[1:9] not in basicos:
            continue
        c = _campos(linha)
        saida[c[0]] = {"razao_social": mascarar_cpfs_no_texto(c[1].strip()), "natureza": c[2] or None,
                       "capital_social": _numero(c[4]), "porte": c[5] or None}
    return saida


def ler_estabelecimentos(linhas: Iterable[str], cnpjs: set[str]) -> dict[str, dict]:
    """Por CNPJ (14 dígitos), o estabelecimento, sem endereço de rua, telefone e e-mail."""
    saida = {}
    for linha in linhas:
        if linha[1:9] + linha[12:16] + linha[19:21] not in cnpjs:
            continue
        c = _campos(linha)
        saida[c[0] + c[1] + c[2]] = {
            "matriz": c[3] == "1", "nome_fantasia": mascarar_cpfs_no_texto(c[4].strip()) or None,
            "situacao": c[5] or None, "data_situacao": _data(c[6]), "motivo": c[7] or None,
            "cidade_exterior": c[8].strip() or None, "pais": c[9] or None, "inicio_atividade": _data(c[10]),
            "cnae_principal": c[11] or None, "cnaes_secundarios": [x for x in c[12].split(",") if x],
            "uf": c[19] or None, "municipio": c[20] or None,
            "situacao_especial": c[28].strip() or None, "data_situacao_especial": _data(c[29]),
        }
    return saida


def ler_socios(linhas: Iterable[str], basicos: set[str]) -> dict[str, list[dict]]:
    """Por CNPJ básico, os sócios: PJ com CNPJ e nome; PF com nome (sem o CPF parcial); estrangeiro com o país."""
    saida: dict[str, list[dict]] = {}
    for linha in linhas:
        if linha[1:9] not in basicos:
            continue
        c = _campos(linha)
        tipo = TIPOS_SOCIO.get(c[1], c[1])
        socio = {"tipo": tipo, "nome": mascarar_cpfs_no_texto(c[2].strip()), "qualificacao": c[4] or None,
                 "desde": _data(c[5])}
        if tipo == "PJ" and re.fullmatch(r"\d{14}", c[3]):
            socio["cnpj"] = c[3]
        if tipo == "estrangeiro" and c[6]:
            socio["pais"] = c[6]
        saida.setdefault(c[0], []).append(socio)
    return saida


def ler_simples(linhas: Iterable[str], basicos: set[str]) -> dict[str, dict]:
    """Por CNPJ básico, a opção pelo Simples e pelo MEI, com as datas."""
    saida = {}
    for linha in linhas:
        if linha[1:9] not in basicos:
            continue
        c = _campos(linha)
        saida[c[0]] = {"simples": c[1] == "S", "simples_desde": _data(c[2]), "simples_ate": _data(c[3]),
                       "mei": c[4] == "S", "mei_desde": _data(c[5]), "mei_ate": _data(c[6])}
    return saida


# ------------------------------------------------------------------------------------------ fornecedores

def fornecedores_do_estado(estado: Path | str) -> set[str]:
    """Os CNPJs (14 dígitos) de fornecedor dos contratos guardados no estado do painel."""
    saida: set[str] = set()
    for caminho in Path(estado).glob("contratacoes-*.json.gz"):
        if caminho.stat().st_size == 0:
            continue
        dados = ler_json(caminho)
        colunas = (dados.get("colunas") or {}).get("contratos") or []
        if "fornecedor_cnpj" not in colunas:
            continue
        i = colunas.index("fornecedor_cnpj")
        saida.update(c[i] for c in dados.get("contratos") or [] if isinstance(c[i], str) and re.fullmatch(r"\d{14}", c[i]))
    return saida


# ------------------------------------------------------------------------------------------ coleta

@dataclass
class ResultadoCnpj:
    """O que a coleta fez: o mês da base, quantos CNPJs pedidos e achados, os arquivos lidos e se pulou."""

    mes: str | None = None
    pedidos: int = 0
    achados: int = 0
    arquivos: list[str] = field(default_factory=list)
    pulada: str | None = None

    def para_json(self) -> dict:
        """Resumo para imprimir na linha de comando."""
        return {"mes": self.mes, "pedidos": self.pedidos, "achados": self.achados, "arquivos": self.arquivos,
                "pulada": self.pulada}


def coletar(estado: Path | str, *, contato: str, temporario: Path | None = None, mes: str | None = None,
            listar_fn=listar, baixar_fn=baixar) -> ResultadoCnpj:
    """Lê a base do ``mes`` (padrão: o mais recente) para os fornecedores do estado e grava ``ARQUIVO``.

    Pula quando o estado já é do mesmo mês e tem todos os fornecedores. Arquivo que não baixa interrompe a coleta
    sem gravar nada (o estado anterior continua valendo).
    """
    estado = Path(estado)
    cnpjs = fornecedores_do_estado(estado)
    resultado = ResultadoCnpj(pedidos=len(cnpjs))
    mes = mes or mes_mais_recente(listar_fn("", contato=contato))
    resultado.mes = mes
    if mes is None:
        raise RuntimeError("o compartilhamento da Receita não tem pasta de mês")
    caminho_estado = estado / ARQUIVO
    anterior = ler_json(caminho_estado) if caminho_estado.exists() else {}
    if anterior.get("mes") == mes and cnpjs <= set(anterior.get("pedidos") or []):
        resultado.pulada = f"o estado já tem a base de {mes} para todos os fornecedores"
        resultado.achados = len(anterior.get("empresas") or {})
        return resultado
    basicos = {c[:8] for c in cnpjs}
    arquivos = sorted(nome for nome, tamanho in listar_fn(mes, contato=contato) if nome.endswith(".zip"))
    pasta = Path(tempfile.mkdtemp(prefix="cnpj-", dir=temporario))
    empresas: dict[str, dict] = {}
    estabelecimentos: dict[str, dict] = {}
    socios: dict[str, list[dict]] = {}
    simples: dict[str, dict] = {}
    tabelas: dict[str, dict[str, str]] = {}
    try:
        for nome in arquivos:
            local = baixar_fn(f"{mes}/{nome}", pasta / nome, contato=contato)
            linhas = linhas_do_zip(local)
            base = nome.removesuffix(".zip").rstrip("0123456789")
            if base == "Empresas":
                empresas.update(ler_empresas(linhas, basicos))
            elif base == "Estabelecimentos":
                estabelecimentos.update(ler_estabelecimentos(linhas, cnpjs))
            elif base == "Socios":
                for b, lista in ler_socios(linhas, basicos).items():
                    socios.setdefault(b, []).extend(lista)
            elif base == "Simples":
                simples.update(ler_simples(linhas, basicos))
            else:
                chave = next((k for k, v in TABELAS.items() if v == base), None)
                if chave:
                    tabelas[chave] = ler_tabela(linhas)
            local.unlink(missing_ok=True)
            resultado.arquivos.append(nome)
    finally:
        shutil.rmtree(pasta, ignore_errors=True)
    dados = montar(cnpjs, empresas, estabelecimentos, socios, simples, tabelas, mes)
    resultado.achados = len(dados["empresas"])
    gravar_json(caminho_estado, dados, comprimir=True)
    return resultado


def montar(cnpjs: set[str], empresas: dict, estabelecimentos: dict, socios: dict, simples: dict,
           tabelas: dict[str, dict[str, str]], mes: str) -> dict:
    """O estado: por CNPJ achado, a empresa, o estabelecimento, o Simples e os sócios; só as tabelas usadas."""
    saida: dict[str, dict] = {}
    usados: dict[str, set[str]] = {k: set() for k in TABELAS}
    for cnpj in sorted(cnpjs):
        est = estabelecimentos.get(cnpj)
        emp = empresas.get(cnpj[:8])
        if not est and not emp:
            continue
        registro = {"empresa": emp, "estabelecimento": est, "simples": simples.get(cnpj[:8]),
                    "socios": socios.get(cnpj[:8], [])}
        saida[cnpj] = registro
        if emp and emp.get("natureza"):
            usados["natureza"].add(emp["natureza"])
        if est:
            usados["cnae"].update([est["cnae_principal"], *est["cnaes_secundarios"]] if est["cnae_principal"] else
                                  est["cnaes_secundarios"])
            for chave in ("motivo", "municipio", "pais"):
                if est.get(chave):
                    usados[chave].add(est[chave])
        for s in registro["socios"]:
            if s.get("qualificacao"):
                usados["qualificacao"].add(s["qualificacao"])
            if s.get("pais"):
                usados["pais"].add(s["pais"])
    return {
        "versao": VERSAO_ESTADO, "mes": mes, "coletado_em": instante_utc(), "fonte": FONTE,
        "pedidos": sorted(cnpjs),
        "tabelas": {k: {c: n for c, n in (tabelas.get(k) or {}).items() if c in usados[k]} for k in TABELAS},
        "empresas": saida,
    }


# ------------------------------------------------------------------------------------------ publicação

def para_publicar(registro: dict) -> dict:
    """O registro de um CNPJ como vai para o site: os códigos como estão (os nomes ficam em ``cnpj/tabelas.json``)
    e sem os campos vazios, para a base caber no limite do GitHub Pages."""
    emp = registro.get("empresa") or {}
    est = registro.get("estabelecimento") or {}
    simples = {k: v for k, v in (registro.get("simples") or {}).items() if v not in (None, False)}
    saida = {
        "razao_social": emp.get("razao_social"), "natureza": emp.get("natureza"), "porte": emp.get("porte"),
        "capital_social": emp.get("capital_social"), "matriz": est.get("matriz"),
        "nome_fantasia": est.get("nome_fantasia"), "situacao": est.get("situacao"),
        "data_situacao": est.get("data_situacao"),
        "motivo": est.get("motivo") if est.get("motivo") not in ("00", "0") else None,
        "inicio_atividade": est.get("inicio_atividade"), "cnae_principal": est.get("cnae_principal"),
        "cnaes_secundarios": est.get("cnaes_secundarios"), "municipio": est.get("municipio"), "uf": est.get("uf"),
        "cidade_exterior": est.get("cidade_exterior"), "pais": est.get("pais"),
        "situacao_especial": est.get("situacao_especial"), "data_situacao_especial": est.get("data_situacao_especial"),
        "simples": simples or None,
        "socios": [{k: v for k, v in s.items() if v is not None} for s in registro.get("socios") or []],
    }
    return {k: v for k, v in saida.items() if v not in (None, [], "")}


def publicar(estado: Path | str, gravar: Callable[[str, Any], Any], *, gerado_em: str) -> dict | None:
    """Grava ``cnpj/<3 primeiros dígitos>.json.gz`` e ``cnpj/tabelas.json`` a partir do estado; devolve o resumo."""
    caminho = Path(estado) / ARQUIVO
    if not caminho.exists():
        return None
    dados = ler_json(caminho)
    if dados.get("versao") != VERSAO_ESTADO:
        raise ValueError(f"{caminho}: versão {dados.get('versao')!r} do estado do CNPJ não suportada")
    base = {"versao": 1, "gerado_em": gerado_em, "mes": dados.get("mes"), "fonte": dados.get("fonte")}
    gravar("cnpj/tabelas.json", {**base, "tipo": "cnpj-tabelas", "tabelas": {
        **(dados.get("tabelas") or {}), "situacao": {c: n for c, n in SITUACOES.items() if len(c) == 2},
        "porte": PORTES}})
    grupos: dict[str, dict[str, dict]] = {}
    for cnpj, registro in (dados.get("empresas") or {}).items():
        grupos.setdefault(cnpj[:3], {})[cnpj] = para_publicar(registro)
    for prefixo, empresas in sorted(grupos.items()):
        gravar(f"cnpj/{prefixo}.json.gz", {**base, "tipo": "cnpj", "empresas": empresas})
    return {"mes": dados.get("mes"), "empresas": len(dados.get("empresas") or {}), "arquivos": len(grupos),
            "coletado_em": dados.get("coletado_em")}
