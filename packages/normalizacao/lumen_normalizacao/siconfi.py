"""Normalização das respostas do SICONFI (cadastro de entes, extrato de entregas e demonstrativos fiscais)."""

from __future__ import annotations

from datetime import date

from lumen_canonico.documentos import cnpj_valido, limpar
from lumen_canonico.fato import EnteFederativo, EntregaSiconfi, Esfera, LinhaDemonstrativo
from lumen_canonico.identidade import id_canonico
from lumen_canonico.ufs import sigla_da_uf

from . import qualidade as q
from .comum import Contexto, converter, processar_lista
from .qualidade import RegistroRejeitado, ResultadoNormalizacao
from .transformacoes import decimal_ou_nulo, instante_brt_ou_nulo, inteiro_ou_nulo, texto_ou_nulo

VERSAO_NORMALIZADOR = "siconfi-1"

ESFERAS_SICONFI = {"U": Esfera.UNIAO, "E": Esfera.ESTADUAL, "M": Esfera.MUNICIPAL, "D": Esfera.DISTRITAL}

POPULACAO_INCONSISTENTE = "populacao_inconsistente"
UF_DIVERGENTE = "uf_divergente_da_fonte"


def _ente(ctx: Contexto, d: dict) -> list:
    """Converte uma linha do cadastro de entes do SICONFI em ``EnteFederativo``.

    Aceita o código ``1`` (União) e códigos IBGE de 2 ou 7 dígitos. A UF sai do código, porque o SICONFI
    publica ``BR`` para os estados, e a divergência com a UF da fonte vira marcação. CNPJ inválido é
    descartado com marcação, e a população publicada para a União segue marcada como inconsistente.
    """
    codigo = str(d.get("cod_ibge") or "").strip()
    if codigo != "1" and not (codigo.isdigit() and len(codigo) in (2, 7)):
        raise RegistroRejeitado("código IBGE do ente inválido", "cod_ibge", d.get("cod_ibge"))
    esfera = ESFERAS_SICONFI.get(str(d.get("esfera") or "").strip().upper())
    if esfera is None:
        raise RegistroRejeitado("esfera desconhecida", "esfera", d.get("esfera"))
    marcas: list[str] = []
    # O SICONFI publica uf = "BR" para os estados; a UF certa sai do código.
    uf_fonte = texto_ou_nulo(d.get("uf"))
    uf = sigla_da_uf(codigo) if codigo != "1" else None
    if uf_fonte and uf and uf_fonte.strip() != uf:
        marcas.append(UF_DIVERGENTE)
    populacao = converter(inteiro_ou_nulo, d, "populacao")
    if esfera is Esfera.UNIAO:
        # A população publicada para a União não corresponde à do país;
        # mantida como veio, com marcação, e nunca usada em grupo de pares.
        marcas.append(POPULACAO_INCONSISTENTE)
    cnpj = limpar(d.get("cnpj")) or None
    if cnpj and not cnpj_valido(cnpj):
        marcas.append(q.CNPJ_ORGAO_INVALIDO)
        cnpj = None
    capital = (str(d.get("capital") or "").strip() == "1")
    return [EnteFederativo(
        id=id_canonico("ente_federativo", codigo), codigo_ibge=codigo,
        nome=texto_ou_nulo(d.get("ente")) or codigo, esfera=esfera, uf=uf, cnpj=cnpj,
        capital=capital, regiao=texto_ou_nulo(d.get("regiao")), populacao=populacao,
        populacao_referencia=f"SICONFI exercício {d.get('exercicio')}" if populacao is not None else None,
        chave_origem=codigo, marcacoes_qualidade=marcas, **ctx.prov(),
    )]


def normalizar_entes(conteudo: bytes, *, fonte_id: str, documento_fonte_id: str) -> ResultadoNormalizacao:
    """Cadastro de entes do SICONFI, com a lista em ``items`` (formato do ORDS)."""
    ctx = Contexto(fonte_id, documento_fonte_id, None)
    return processar_lista(conteudo, ctx, lambda d: _ente(ctx, d),
                            lambda d: str(d.get("cod_ibge")), paginado=False, lista_em="items")


def _entrega(ctx: Contexto, d: dict) -> list:
    """Converte uma linha do extrato de entregas em ``EntregaSiconfi``.

    Ente, exercício, período, instituição e entregável são obrigatórios e formam a chave natural. A data de
    status do extrato vira ``entregue_em``, a data usada pela conformidade na avaliação de prazo.
    """
    codigo = str(d.get("cod_ibge") or "").strip()
    if not codigo:
        raise RegistroRejeitado("campo obrigatório ausente", "cod_ibge")
    exercicio = converter(inteiro_ou_nulo, d, "exercicio")
    periodo = converter(inteiro_ou_nulo, d, "periodo")
    instituicao = texto_ou_nulo(d.get("instituicao"))
    entregavel = texto_ou_nulo(d.get("entregavel"))
    for campo, valor in (("exercicio", exercicio), ("periodo", periodo),
                         ("instituicao", instituicao), ("entregavel", entregavel)):
        if valor is None:
            raise RegistroRejeitado("campo obrigatório ausente", campo)
    chave = f"{codigo}|{instituicao}|{entregavel}|{exercicio}|{periodo}"
    return [EntregaSiconfi(
        id=id_canonico("entrega_siconfi", codigo, instituicao, entregavel, exercicio, periodo),
        ente_id=id_canonico("ente_federativo", codigo), ente_codigo_ibge=codigo,
        exercicio=exercicio, instituicao=instituicao, entregavel=entregavel, periodo=periodo,
        periodicidade=texto_ou_nulo(d.get("periodicidade")),
        status_relatorio=texto_ou_nulo(d.get("status_relatorio")),
        entregue_em=converter(instante_brt_ou_nulo, d, "data_status", hoje=ctx.hoje),
        forma_envio=texto_ou_nulo(d.get("forma_envio")),
        tipo_relatorio=texto_ou_nulo(d.get("tipo_relatorio")),
        populacao_declarada=converter(inteiro_ou_nulo, d, "populacao"),
        chave_origem=chave, **ctx.prov(),
    )]


def normalizar_extrato(conteudo: bytes, *, fonte_id: str, documento_fonte_id: str,
                       hoje: date | None = None) -> ResultadoNormalizacao:
    """Extrato de entregas de um ente ao SICONFI, com a lista em ``items`` (formato do ORDS)."""
    ctx = Contexto(fonte_id, documento_fonte_id, hoje)
    return processar_lista(conteudo, ctx, lambda d: _entrega(ctx, d),
                            lambda d: f"{d.get('cod_ibge')}|{d.get('entregavel')}|{d.get('periodo')}",
                            paginado=False, lista_em="items")


def _linha_demonstrativo(ctx: Contexto, d: dict) -> list:
    """Converte uma linha do RREO, do RGF ou da DCA em ``LinhaDemonstrativo``.

    Ente, exercício, demonstrativo, anexo, coluna, código da conta e conta são obrigatórios. O período é
    obrigatório no RREO e no RGF e nulo na DCA; o valor, quando vem, precisa ser numérico. A DCA não traz o
    campo ``demonstrativo``: ele vem do anexo (``DCA-Anexo I-E`` é da DCA).
    """
    codigo = str(d.get("cod_ibge") or "").strip()
    if not codigo:
        raise RegistroRejeitado("campo obrigatório ausente", "cod_ibge")
    exercicio = converter(inteiro_ou_nulo, d, "exercicio")
    if exercicio is None:
        raise RegistroRejeitado("campo obrigatório ausente", "exercicio")
    textos = {c: texto_ou_nulo(d.get(c)) for c in ("demonstrativo", "anexo", "coluna", "cod_conta", "conta")}
    if textos["demonstrativo"] is None and (textos["anexo"] or "").upper().startswith("DCA"):
        textos["demonstrativo"] = "DCA"
    for campo, valor in textos.items():
        if valor is None:
            raise RegistroRejeitado("campo obrigatório ausente", campo)
    periodo = converter(inteiro_ou_nulo, d, "periodo")
    if periodo is None and not textos["demonstrativo"].upper().startswith("DCA"):
        raise RegistroRejeitado("campo obrigatório ausente", "periodo")
    instituicao, rotulo = texto_ou_nulo(d.get("instituicao")), texto_ou_nulo(d.get("rotulo"))
    partes = (codigo, exercicio, periodo, textos["demonstrativo"], textos["anexo"], instituicao, rotulo,
              textos["coluna"], textos["cod_conta"], textos["conta"])
    return [LinhaDemonstrativo(
        id=id_canonico("linha_demonstrativo", *(p if p is not None else "-" for p in partes)),
        ente_id=id_canonico("ente_federativo", codigo), ente_codigo_ibge=codigo, exercicio=exercicio,
        periodo=periodo, periodicidade=texto_ou_nulo(d.get("periodicidade")),
        demonstrativo=textos["demonstrativo"], anexo=textos["anexo"], instituicao=instituicao, rotulo=rotulo,
        coluna=textos["coluna"], cod_conta=textos["cod_conta"], conta=textos["conta"],
        valor=converter(decimal_ou_nulo, d, "valor"),
        populacao_declarada=converter(inteiro_ou_nulo, d, "populacao"),
        chave_origem="|".join("-" if p is None else str(p) for p in partes), **ctx.prov(),
    )]


def normalizar_demonstrativo(conteudo: bytes, *, fonte_id: str, documento_fonte_id: str) -> ResultadoNormalizacao:
    """Página do RREO, do RGF ou da DCA de um ente, com a lista em ``items`` (formato do ORDS)."""
    ctx = Contexto(fonte_id, documento_fonte_id, None)
    return processar_lista(conteudo, ctx, lambda d: _linha_demonstrativo(ctx, d),
                            lambda d: f"{d.get('cod_ibge')}|{d.get('anexo')}|{d.get('cod_conta')}|{d.get('coluna')}",
                            paginado=False, lista_em="items")
