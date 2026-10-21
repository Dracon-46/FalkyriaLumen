"""Contratos dos municípios paranaenses registrados no Tribunal de Contas do Estado, pelo SIM-AM (ADR-050).

O TCE-PR publica, sem chave, um ZIP por município e ano no Portal Informação para Todos
(``pit.tce.pr.gov.br/Arquivos/AAAA/AAAA_<IBGE de 6 dígitos>_Contrato.zip``), desde 2013. Dentro dele:

- ``Contrato.xml``: um registro por contratado, com a entidade (prefeitura, câmara, fundo, autarquia, consórcio),
  o documento do contratado (o CPF já vem mascarado pelo tribunal), o valor do contrato e a parte daquele
  contratado (``vlDesteContratado``), que é a que se soma;
- ``ContratoAditivo.xml``: os aditivos assinados no ano, com o valor (``vlAditivo``). A supressão vem com valor
  positivo e entra negativa no acréscimo líquido.

O ZIP do estado (``AAAA_PIT_TodosArquivos.zip``, 1,3 GB) só serve para saber, com um pedido de cabeçalho, se o ano
mudou; os 399 arquivos dos municípios são pequenos (20 MB no ano). Alguns XML trazem caractere de controle, que o XML
não aceita, e ele é trocado por espaço antes da leitura; o arquivo que ainda assim não abre fica de fora e vai para
os ``problemas`` da coleta, sem derrubar o ano. O ente é o município do arquivo; a entidade com
"consórcio" no nome fica sem ente. Quem não tem CNPJ válido entra na soma anônima de pessoa física: o tribunal
publica o nome, e o Lumen não guarda. O estado (``tce-pr.json.gz``) segue o formato comum de ``tce``.
"""

from __future__ import annotations

import io
import re
import time
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable
from xml.etree import ElementTree

from lumen_canonico.documentos import cnpj_valido, mascarar_cpfs_no_texto

from . import tce
from .cadastro import Cadastro
from .comum import gravar_json, instante_utc, sem_acento, tipo_do_ente
from .contratacoes import teto_do_ente

TRIBUNAL = "TCE-PR"
SISTEMA = "SIM-AM"
FONTE = "Tribunal de Contas do Estado do Paraná, Portal Informação para Todos (pit.tce.pr.gov.br)"
URL_ESTADO = "https://pit.tce.pr.gov.br/Arquivos/{ano}_PIT_TodosArquivos.zip"
URL_MUNICIPIO = "https://pit.tce.pr.gov.br/Arquivos/{ano}/{ano}_{ibge6}_Contrato.zip"
ARQUIVO = "tce-pr.json.gz"
PRIMEIRO_ANO = 2013
UF = "PR"
OPERACOES_QUE_REDUZEM = ("SUPRESSAO",)
_REFERENCIA = re.compile(rb"&#(x[0-9A-Fa-f]+|[0-9]+);")
_CONTROLE = re.compile(rb"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _caractere_xml(codigo: int) -> bool:
    """O caractere é aceito em XML 1.0?"""
    return (codigo in (0x9, 0xA, 0xD) or 0x20 <= codigo <= 0xD7FF or 0xE000 <= codigo <= 0xFFFD
            or 0x10000 <= codigo <= 0x10FFFF)


def ler_xml(dados: bytes) -> ElementTree.Element:
    """O XML, com as referências e os bytes de caracteres que o XML não aceita trocados por espaço."""
    def trocar(m: re.Match) -> bytes:
        texto = m.group(1)
        codigo = int(texto[1:], 16) if texto[:1] == b"x" else int(texto)
        return m.group(0) if _caractere_xml(codigo) else b" "
    return ElementTree.fromstring(_CONTROLE.sub(b" ", _REFERENCIA.sub(trocar, dados)))


def municipios(cadastro: Cadastro) -> list[str]:
    """Os municípios do Paraná no cadastro, pelo código IBGE de 7 dígitos."""
    return sorted(c for c, e in cadastro.entes.items() if e.uf == UF and tipo_do_ente(c) == "municipio")


def _valor(texto: str | None) -> float | None:
    """``"1306000.00"`` → 1306000.0; vazio ou fora do formato → ``None``."""
    try:
        return float(texto) if texto not in (None, "") else None
    except ValueError:
        return None


def _consorcio(entidade: str | None) -> bool:
    """A entidade é um consórcio (reúne vários municípios)?"""
    return "CONSORCIO" in sem_acento(entidade or "").upper()


def ler_municipio(conteudo: bytes, ente: str, soma: tce.SomaAno, nomes: dict[str, str]) -> None:
    """Soma os contratos e os aditivos do ZIP de um município e guarda o nome de cada CNPJ."""
    with zipfile.ZipFile(io.BytesIO(conteudo)) as z:
        for arquivo in z.namelist():
            if arquivo.endswith("_Contrato.xml"):
                for c in ler_xml(z.read(arquivo)).iter("Contrato"):
                    documento = "".join(d for d in (c.get("nrDocContratado") or "") if d.isdigit())
                    cnpj = documento if cnpj_valido(documento) else None
                    valor = _valor(c.get("vlDesteContratado"))
                    soma.contrato(None if _consorcio(c.get("nmEntidade")) else ente,
                                  valor if valor is not None else _valor(c.get("vlContrato")), cnpj=cnpj)
                    if cnpj and c.get("nmContratado"):
                        nomes[cnpj] = mascarar_cpfs_no_texto(c.get("nmContratado").strip())
            elif arquivo.endswith("_ContratoAditivo.xml"):
                for a in ler_xml(z.read(arquivo)).iter("ContratoAditivo"):
                    operacao = sem_acento(a.get("dsTipoOperacaoAditivoContrato") or "").upper()
                    valor = _valor(a.get("vlAditivo")) or 0.0
                    soma.aditivo(ente, -valor if operacao.startswith(OPERACOES_QUE_REDUZEM) else valor)


def coletar(estado: Path | str, cadastro: Cadastro, *, contato: str, hoje: date | None = None,
            anos: list[int] | None = None, limite_minutos: float | None = None,
            cabecalho_fn: Callable[..., tuple[int, str] | None] = tce.cabecalho,
            baixar_fn: Callable[..., bytes | None] = tce.baixar,
            relogio: Callable[[], float] = time.monotonic) -> tce.ResultadoTce:
    """Lê os anos que mudaram, município a município, e grava ``ARQUIVO`` depois de cada ano completo; o ano
    interrompido pelo prazo não é gravado e volta na execução seguinte."""
    hoje = hoje or datetime.now(timezone.utc).date()
    caminho = Path(estado) / ARQUIVO
    dados = tce.ler_estado(caminho, tribunal=TRIBUNAL, sistema=SISTEMA, fonte=FONTE, primeiro_ano=PRIMEIRO_ANO)
    teto = lambda ente: teto_do_ente(ente, cadastro)  # noqa: E731
    resultado = tce.ResultadoTce(TRIBUNAL)
    prazo = relogio() + limite_minutos * 60 if limite_minutos else None
    lista = municipios(cadastro)
    for ano in anos or range(PRIMEIRO_ANO, hoje.year + 1):
        info = cabecalho_fn(URL_ESTADO.format(ano=ano), contato=contato)
        if info is None:
            resultado.ausentes.append(ano)
            continue
        tamanho, etiqueta = info
        if not tce.precisa_ler(dados["anos"].get(str(ano)), tamanho, etiqueta, ano, hoje):
            resultado.pulados.append(ano)
            continue
        soma, nomes = tce.SomaAno(teto), {}
        for ente in lista:
            if prazo is not None and relogio() >= prazo:
                resultado.interrompida = True
                break
            conteudo = baixar_fn(URL_MUNICIPIO.format(ano=ano, ibge6=ente[:6]), contato=contato)
            if not conteudo:
                continue
            try:
                ler_municipio(conteudo, ente, soma, nomes)
            except (ElementTree.ParseError, zipfile.BadZipFile) as erro:
                resultado.problemas.append(f"{ano}/{ente}: {erro}")
        if resultado.interrompida:
            break
        dados["anos"][str(ano)] = {"tamanho": tamanho, "etiqueta": etiqueta, "lido_em": instante_utc(),
                                   **soma.para_json()}
        novos = {c: n for c, n in nomes.items() if c not in dados["nomes"]}
        dados["nomes"].update(nomes)
        resultado.lidos.append(ano)
        resultado.nomes += len(novos)
        Path(estado).mkdir(parents=True, exist_ok=True)
        gravar_json(caminho, {**dados, "coletado_em": instante_utc()}, comprimir=True)
    return resultado
