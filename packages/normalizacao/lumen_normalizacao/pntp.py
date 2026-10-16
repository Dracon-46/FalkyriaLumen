"""Normalização da planilha de avaliações do PNTP para ``AvaliacaoTransparencia``.

Uma linha por entidade avaliada no ciclo (a prefeitura e a câmara de cada município, os poderes estaduais
e federais, consórcios, estatais), com o índice, o percentual dos essenciais, o nível e o endereço do
portal. O ciclo vem do nome do arquivo no ZIP (``pntp_2025/avaliacoes_pntp_2025.xlsx``), que a
orquestração lê da URL guardada no bronze.

O layout é o de 2023 em diante. A planilha de 2022 tem outro: sem código da entidade nem código IBGE,
com o nome e o e-mail de quem preencheu. Ela vai inteira para a quarentena com esse motivo; o bronze a
guarda (ADR-032).
"""

from __future__ import annotations

import zipfile
from decimal import Decimal, InvalidOperation

from lumen_canonico.fato import AvaliacaoTransparencia, Esfera
from lumen_canonico.identidade import id_canonico
from lumen_canonico.ufs import SIGLA_PARA_CODIGO, UFS

from . import qualidade as q
from .comum import Contexto
from .qualidade import EntradaQuarentena, RegistroRejeitado, ResultadoNormalizacao
from .transformacoes import chave_texto, texto_ou_nulo
from .xlsx import data_do_excel, linhas

VERSAO_NORMALIZADOR = "pntp-1"

FRACAO_FORA_DA_FAIXA = "fracao_fora_da_faixa"

COLUNAS = ("Código Entidade", "Poder", "Esfera", "Unidade Gestora", "UF", "ibge", "Data Envio", "Autoavaliação",
           "Avaliação Validada?", "Avaliação Certificável?", "Índice de Transparência", "% das Essenciais",
           "Nível de Transparência", "Histórico do Nível", "Link Site Principal")
ESFERAS_PNTP = {"municipal": Esfera.MUNICIPAL, "estadual": Esfera.ESTADUAL, "federal": Esfera.UNIAO,
                "distrital": Esfera.DISTRITAL}
UF_POR_NOME = {chave_texto(nome): sigla for sigla, nome, _ in UFS.values()}
NAO_AVALIADO = "Não Avaliado"
CASAS = Decimal("0.0001")


def _texto(valor: object) -> str | None:
    """Texto sem espaços nas pontas; vazio e o traço que a planilha usa para ausência viram nulo."""
    t = (texto_ou_nulo(valor) or "").strip()
    return None if t in ("", "-") else t


def _sim_nao(valor: object) -> bool | None:
    """"Sim" e "Não" como booleano; o traço (entidade não avaliada) vira nulo."""
    t = chave_texto(_texto(valor))
    return True if t == "sim" else False if t == "nao" else None


def _fracao(valor: object, campo: str, marcas: list[str]) -> Decimal | None:
    """Número de 0 a 1 com quatro casas (a planilha grava o valor binário do Excel: 0,95849999999999991).

    Fora de 0 a 1 (há "% das Essenciais" igual a 5 e a 6,6 em 2025) vira nulo com ``fracao_fora_da_faixa``:
    a entidade continua no cadastro, sem o número errado. Texto que não é número rejeita a linha.
    """
    t = _texto(valor)
    if t is None:
        return None
    try:
        d = Decimal(t).quantize(CASAS)
    except InvalidOperation as erro:
        raise RegistroRejeitado("não numérico", campo, valor) from erro
    if not Decimal(0) <= d <= Decimal(1):
        marcas.append(FRACAO_FORA_DA_FAIXA)
        return None
    return d


def _ente(esfera: Esfera | None, uf: str | None, municipio: str | None) -> str | None:
    """Código do ente da entidade: o município, a UF, ``53`` no DF ou ``1`` na União."""
    if esfera is Esfera.UNIAO:
        return "1"
    if esfera is Esfera.DISTRITAL:
        return "53"
    if esfera is Esfera.ESTADUAL:
        return SIGLA_PARA_CODIGO.get(uf or "")
    if esfera is Esfera.MUNICIPAL:
        return municipio
    return None


def _avaliacao(ctx: Contexto, ciclo: int, d: dict) -> list:
    """Uma linha da planilha como ``AvaliacaoTransparencia``; código e nome da entidade são obrigatórios."""
    codigo = _texto(d.get("Código Entidade"))
    nome = _texto(d.get("Unidade Gestora"))
    if not codigo:
        raise RegistroRejeitado("campo obrigatório ausente", "Código Entidade")
    if not nome:
        raise RegistroRejeitado("campo obrigatório ausente", "Unidade Gestora")
    marcas: list[str] = []
    esfera = ESFERAS_PNTP.get(chave_texto(_texto(d.get("Esfera"))))
    if esfera is None:
        marcas.append(q.ESFERA_NAO_INFORMADA)
    uf = UF_POR_NOME.get(chave_texto(_texto(d.get("UF"))))
    ibge = _texto(d.get("ibge"))
    municipio = ibge if ibge and ibge.isdigit() and len(ibge) == 7 else None
    if municipio is None:
        marcas.append(q.CODIGO_IBGE_AUSENTE)
    ente = _ente(esfera, uf, municipio)
    nivel = _texto(d.get("Nível de Transparência"))
    avaliada = nivel is not None and nivel != NAO_AVALIADO
    historico = _texto(d.get("Histórico do Nível")) or ""
    anterior = historico.split("->", 1)[0].strip() if "->" in historico else None
    return [AvaliacaoTransparencia(
        id=id_canonico("avaliacao_transparencia", ciclo, codigo), ciclo=ciclo, codigo_entidade=codigo,
        entidade=nome, poder=_texto(d.get("Poder")), esfera=esfera, uf=uf, municipio_codigo_ibge=municipio,
        ente_id=id_canonico("ente_federativo", ente) if ente else None, ente_codigo_ibge=ente,
        avaliada=avaliada, data_envio=data_do_excel(_texto(d.get("Data Envio"))) if avaliada else None,
        autoavaliacao=_sim_nao(d.get("Autoavaliação")), validada=_sim_nao(d.get("Avaliação Validada?")),
        certificavel=_sim_nao(d.get("Avaliação Certificável?")),
        indice=_fracao(d.get("Índice de Transparência"), "Índice de Transparência", marcas) if avaliada else None,
        percentual_essenciais=_fracao(d.get("% das Essenciais"), "% das Essenciais", marcas) if avaliada else None,
        nivel=nivel, nivel_anterior=anterior or None, link_portal=_texto(d.get("Link Site Principal")),
        chave_origem=codigo, marcacoes_qualidade=marcas, **ctx.prov(),
    )]


def _quarentena_do_artefato(ctx: Contexto, motivo: str, valor: object = None) -> ResultadoNormalizacao:
    """Resultado com uma entrada só na quarentena, para a planilha que não pôde ser lida."""
    r = ResultadoNormalizacao()
    r.quarentena.append(EntradaQuarentena(fonte_id=ctx.fonte_id, documento_fonte_id=ctx.documento_fonte_id,
                                          chave_origem=None, posicao=None, motivo=motivo, campo=None,
                                          valor_recebido=q.resumir_valor(valor)))
    return r


def normalizar_avaliacoes(conteudo: bytes, *, ciclo: int, fonte_id: str,
                          documento_fonte_id: str) -> ResultadoNormalizacao:
    """Planilha de avaliações de um ciclo do PNTP como registros ``AvaliacaoTransparencia``.

    Planilha ilegível ou sem as colunas do layout de 2023 em diante vai inteira para a quarentena; cada
    linha com problema vai sozinha, e o resto segue.
    """
    ctx = Contexto(fonte_id, documento_fonte_id, None)
    try:
        tabela = linhas(conteudo)
        cabecalho = [c.strip() for c in next(tabela)]
    except (zipfile.BadZipFile, KeyError, StopIteration, ValueError) as erro:
        return _quarentena_do_artefato(ctx, f"planilha ilegível: {erro}", conteudo[:200])
    faltando = [c for c in COLUNAS if c not in cabecalho]
    if faltando:
        return _quarentena_do_artefato(
            ctx, f"layout sem as colunas {faltando} (o de 2022 não tem código da entidade nem IBGE)", cabecalho)
    resultado = ResultadoNormalizacao()
    for posicao, linha in enumerate(tabela):
        d = dict(zip(cabecalho, linha))
        if not any((v or "").strip() for v in linha):
            continue
        resultado.lidos += 1
        try:
            resultado.registros.extend(_avaliacao(ctx, ciclo, d))
        except RegistroRejeitado as rej:
            resultado.quarentena.append(EntradaQuarentena(
                fonte_id=fonte_id, documento_fonte_id=documento_fonte_id, chave_origem=d.get("Código Entidade"),
                posicao=posicao, motivo=rej.motivo, campo=rej.campo, valor_recebido=q.resumir_valor(rej.valor)))
    return resultado

