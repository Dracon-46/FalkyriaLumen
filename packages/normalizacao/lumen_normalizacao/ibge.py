"""Normalização das respostas do IBGE (localidades e população estimada)."""

from __future__ import annotations

from lumen_canonico.fato import EnteFederativo, Esfera
from lumen_canonico.identidade import id_canonico
from lumen_canonico.porte import classificar_porte

from .comum import Contexto, processar_lista
from .qualidade import RegistroRejeitado, ResultadoNormalizacao
from .transformacoes import ler_json, texto_ou_nulo

VERSAO_NORMALIZADOR = "ibge-1"


def _estado(ctx: Contexto, d: dict) -> list:
    """Converte uma UF da API de localidades em ``EnteFederativo``.

    O código precisa ter dois dígitos; o ``53`` (Distrito Federal) recebe esfera distrital e os demais,
    estadual. Sem nome publicado, o nome fica sendo o próprio código.
    """
    codigo = str(d.get("id") or "").strip()
    if len(codigo) != 2 or not codigo.isdigit():
        raise RegistroRejeitado("código de UF inválido", "id", d.get("id"))
    sigla = texto_ou_nulo(d.get("sigla"))
    return [EnteFederativo(
        id=id_canonico("ente_federativo", codigo), codigo_ibge=codigo,
        nome=texto_ou_nulo(d.get("nome")) or codigo,
        esfera=Esfera.DISTRITAL if codigo == "53" else Esfera.ESTADUAL,
        uf=sigla, regiao=texto_ou_nulo((d.get("regiao") or {}).get("sigla")),
        chave_origem=codigo, **ctx.prov(),
    )]


def normalizar_estados(conteudo: bytes, *, fonte_id: str, documento_fonte_id: str) -> ResultadoNormalizacao:
    """Resposta de ``/v1/localidades/estados``: cada UF vira um ente estadual (ou distrital, no caso do DF)."""
    ctx = Contexto(fonte_id, documento_fonte_id, None)
    return processar_lista(conteudo, ctx, lambda d: _estado(ctx, d), lambda d: str(d.get("id")), paginado=False)


def _municipio(ctx: Contexto, d: dict) -> list:
    """Converte uma linha da visão nivelada de municípios em ``EnteFederativo`` municipal.

    O código IBGE precisa ter sete dígitos. Sem nome publicado, o nome fica sendo o próprio código.
    """
    codigo = str(d.get("municipio-id") or "").strip()
    if len(codigo) != 7 or not codigo.isdigit():
        raise RegistroRejeitado("código de município inválido", "municipio-id", d.get("municipio-id"))
    return [EnteFederativo(
        id=id_canonico("ente_federativo", codigo), codigo_ibge=codigo,
        nome=texto_ou_nulo(d.get("municipio-nome")) or codigo,
        esfera=Esfera.MUNICIPAL, uf=texto_ou_nulo(d.get("UF-sigla")),
        regiao=texto_ou_nulo(d.get("regiao-sigla")),
        chave_origem=codigo, **ctx.prov(),
    )]


def normalizar_municipios(conteudo: bytes, *, fonte_id: str, documento_fonte_id: str) -> ResultadoNormalizacao:
    """Resposta de ``/v1/localidades/municipios?view=nivelado``."""
    ctx = Contexto(fonte_id, documento_fonte_id, None)
    return processar_lista(conteudo, ctx, lambda d: _municipio(ctx, d),
                            lambda d: str(d.get("municipio-id")), paginado=False)


def ler_populacao(conteudo: bytes) -> dict[str, tuple[int, str]]:
    """Agregado 6579 do SIDRA → ``{codigo_ibge: (população, ano)}``.

    Valores não numéricos (o SIDRA usa ``"-"`` e ``"..."`` para ausência) são
    ignorados: o ente fica sem população, e não com zero.
    """
    corpo = ler_json(conteudo)
    saida: dict[str, tuple[int, str]] = {}
    for variavel in corpo if isinstance(corpo, list) else []:
        for resultado in variavel.get("resultados", []):
            for serie in resultado.get("series", []):
                codigo = str(serie.get("localidade", {}).get("id", "")).strip()
                for ano, valor in (serie.get("serie") or {}).items():
                    texto = str(valor).strip()
                    if codigo and texto.isdigit():
                        saida[codigo] = (int(texto), str(ano))
    return saida


def aplicar_populacao(entes: list[EnteFederativo], populacao: dict[str, tuple[int, str]]) -> None:
    """Preenche população, referência e porte nos entes que têm estimativa."""
    for e in entes:
        if e.codigo_ibge in populacao:
            valor, ano = populacao[e.codigo_ibge]
            e.populacao = valor
            e.populacao_referencia = f"IBGE estimativa {ano}"
            e.porte = classificar_porte(valor) if e.esfera is Esfera.MUNICIPAL else None
