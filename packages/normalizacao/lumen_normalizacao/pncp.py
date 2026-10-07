"""Normalização das respostas do PNCP para o esquema canônico.

Entrada: o conteúdo bruto de um artefato da camada bronze, exatamente como a
API respondeu. Saída: registros canônicos (``lumen_canonico.fato``) e a
quarentena. A função é pura e determinística: o mesmo artefato produz sempre
os mesmos registros, com os mesmos ids (RF-NO-11), o que permite apagar a
silver e regerá-la a partir do bronze a qualquer momento (RF-NO-12).

Mapeamento dos códigos do PNCP
------------------------------
Os domínios abaixo foram lidos dos endpoints oficiais
(``/api/pncp/v1/modalidades`` e afins) em 05/10/2026. Código desconhecido não
derruba o registro: vira nulo com marcação, porque o PNCP acrescenta códigos
de tempos em tempos e uma modalidade nova não deve tirar contratações
inteiras da análise.

Resolução do ente federativo
----------------------------
O PNCP informa a esfera do órgão (``esferaId``) e o município onde fica a
unidade (``unidadeOrgao.codigoIbge``). O ente sai da combinação:

======== =====================================================
esfera   ente
======== =====================================================
M        o município da unidade (código IBGE de 7 dígitos)
E        o estado, pelos 2 primeiros dígitos do código IBGE
D        o Distrito Federal (``53``)
F        a União (``1``, convenção do SICONFI)
N/vazio  não resolvido: nulo, com marcação, para resolução por CNPJ
======== =====================================================
"""

from __future__ import annotations

from datetime import date
from typing import Any

from lumen_canonico.documentos import (
    TipoDocumento,
    classificar,
    cnpj_valido,
    documento_publicavel,
    limpar,
)
from lumen_canonico.fato import (
    AmparoLegal,
    AtaRegistroPreco,
    Contrato,
    Esfera,
    ItemContratacao,
    Modalidade,
    Orgao,
    Poder,
    ProcessoContratacao,
    ResultadoItem,
    TipoPessoa,
    UnidadeGestora,
)
from lumen_canonico.identidade import id_canonico

from . import qualidade as q
from .comum import Contexto, converter, nao_negativo, obrigatorio, processar_lista
from .qualidade import RegistroRejeitado, ResultadoNormalizacao
from .transformacoes import (
    booleano_ou_nulo,
    chave_texto,
    data_ou_nula,
    decimal_ou_nulo,
    instante_brt_ou_nulo,
    inteiro_ou_nulo,
    texto_ou_nulo,
)

VERSAO_NORMALIZADOR = "pncp-1"

ESFERAS = {"F": Esfera.UNIAO, "E": Esfera.ESTADUAL, "M": Esfera.MUNICIPAL, "D": Esfera.DISTRITAL}
PODERES = {"E": Poder.EXECUTIVO, "L": Poder.LEGISLATIVO, "J": Poder.JUDICIARIO}

MODALIDADES: dict[int, Modalidade] = {
    1: Modalidade.LEILAO,
    2: Modalidade.DIALOGO,
    3: Modalidade.CONCURSO,
    4: Modalidade.CONCORRENCIA,
    5: Modalidade.CONCORRENCIA,
    6: Modalidade.PREGAO,
    7: Modalidade.PREGAO,
    8: Modalidade.DISPENSA,
    9: Modalidade.INEXIGIBILIDADE,
    10: Modalidade.MANIFESTACAO_INTERESSE,
    11: Modalidade.PRE_QUALIFICACAO,
    12: Modalidade.CREDENCIAMENTO,
    13: Modalidade.LEILAO,
    14: Modalidade.INAPLICABILIDADE,
    15: Modalidade.CHAMADA_PUBLICA,
    16: Modalidade.CONCORRENCIA,
    17: Modalidade.CONCORRENCIA,
    18: Modalidade.PREGAO,
    19: Modalidade.PREGAO,
}

# Amparos que são dispensa *por valor* e o parâmetro legal que dá o limite.
# Só a Lei 14.133 tem limites cadastrados; os do art. 29 da Lei 13.303
# (estatais) dependem de regulamento de cada empresa e ficam sem parâmetro:
# a regra cala para eles, por projeto.
AMPARO_DISPENSA_POR_VALOR: dict[int, str | None] = {
    18: "dispensa_obras_engenharia",   # Lei 14.133/2021, art. 75, I
    19: "dispensa_compras_servicos",   # Lei 14.133/2021, art. 75, II
    84: None,                          # Lei 13.303/2016, art. 29, I
    85: None,                          # Lei 13.303/2016, art. 29, II
}

_PREFIXOS_NATUREZA = (
    ("dispensa de licitacao", "dispensa"),
    ("inexigibilidade de licitacao", "inexigibilidade"),
    ("inaplicabilidade de licitacao", "inaplicabilidade"),
    ("credenciamento", "credenciamento"),
    ("pre-qualificacao", "pre_qualificacao"),
    ("procedimento de manifestacao de interesse", "manifestacao_interesse"),
    ("manifestacao de interesse", "manifestacao_interesse"),
    ("criterio de desempate", "criterio_desempate"),
    ("margem de preferencia", "margem_preferencia"),
    ("pregao", "licitacao"),
    ("concorrencia", "licitacao"),
    ("concurso", "licitacao"),
    ("leilao", "licitacao"),
    ("dialogo competitivo", "licitacao"),
    ("licitacao", "licitacao"),
)


def natureza_do_amparo(codigo: int | None, descricao: str | None) -> str | None:
    """Natureza do dispositivo, lida do prefixo da descrição publicada."""
    texto = chave_texto(descricao)
    for prefixo, natureza in _PREFIXOS_NATUREZA:
        if texto.startswith(prefixo):
            return natureza
    if codigo in AMPARO_DISPENSA_POR_VALOR:
        return "dispensa"
    return None


# ---------------------------------------------------------------------------
# Peças comuns
# ---------------------------------------------------------------------------

def resolver_ente(esfera: Esfera | None, codigo_ibge_unidade: str | None) -> str | None:
    """Código do ente federativo (ver tabela no topo do módulo)."""
    if esfera is Esfera.UNIAO:
        return "1"
    if esfera is Esfera.DISTRITAL:
        return "53"
    codigo = limpar(codigo_ibge_unidade)
    if not codigo.isdigit() or len(codigo) != 7:
        return None
    if esfera is Esfera.MUNICIPAL:
        return codigo
    if esfera is Esfera.ESTADUAL:
        return codigo[:2]
    return None


def _orgao_e_unidade(
    ctx: Contexto,
    cnpj_bruto: Any,
    razao_social: Any,
    esfera_cod: Any,
    poder_cod: Any,
    unidade: dict | None,
) -> tuple[Orgao, UnidadeGestora | None, list[str]]:
    """Monta o órgão e, se houver código de unidade, a unidade gestora; devolve também as marcações.

    CNPJ ausente ou com dígito verificador inválido rejeita o registro, porque o órgão é a chave de quem
    contrata. Esfera, poder e código IBGE não informados não rejeitam: viram nulo com marcação, e o ente é
    resolvido por ``resolver_ente`` quando possível. Quem chama acrescenta as marcações devolvidas às do
    registro principal.
    """
    cnpj = limpar(cnpj_bruto)
    if not cnpj:
        raise RegistroRejeitado("campo obrigatório ausente", "orgaoEntidade.cnpj")
    if not cnpj_valido(cnpj):
        raise RegistroRejeitado("CNPJ do órgão com dígito verificador inválido", "orgaoEntidade.cnpj", cnpj)
    marcas: list[str] = []
    esfera = ESFERAS.get(str(esfera_cod or "").strip().upper())
    if esfera is None:
        marcas.append(q.ESFERA_NAO_INFORMADA)
    poder = PODERES.get(str(poder_cod or "").strip().upper())
    if poder is None:
        marcas.append(q.PODER_NAO_INFORMADO)
    unidade = unidade or {}
    codigo_ibge = texto_ou_nulo(unidade.get("codigoIbge"))
    if codigo_ibge is None:
        marcas.append(q.CODIGO_IBGE_AUSENTE)
    ente_codigo = resolver_ente(esfera, codigo_ibge)
    if ente_codigo is None:
        marcas.append(q.ENTE_NAO_RESOLVIDO)
    ente_id = id_canonico("ente_federativo", ente_codigo) if ente_codigo else None
    orgao = Orgao(
        id=id_canonico("orgao", cnpj),
        cnpj=cnpj,
        razao_social=texto_ou_nulo(razao_social) or cnpj,
        esfera=esfera,
        poder=poder,
        ente_id=ente_id,
        ente_codigo_ibge=ente_codigo,
        chave_origem=cnpj,
        marcacoes_qualidade=list(marcas),
        **ctx.prov(),
    )
    ug = None
    codigo_unidade = texto_ou_nulo(unidade.get("codigoUnidade"))
    if codigo_unidade is not None:
        ug = UnidadeGestora(
            id=id_canonico("unidade_gestora", cnpj, codigo_unidade.strip()),
            orgao_id=orgao.id,
            orgao_cnpj=cnpj,
            codigo=codigo_unidade.strip(),
            nome=texto_ou_nulo(unidade.get("nomeUnidade")),
            municipio_codigo_ibge=codigo_ibge,
            municipio_nome=texto_ou_nulo(unidade.get("municipioNome")),
            uf=texto_ou_nulo(unidade.get("ufSigla")),
            chave_origem=f"{cnpj}/{codigo_unidade.strip()}",
            **ctx.prov(),
        )
    return orgao, ug, marcas


def _amparo(ctx: Contexto, dados: dict | None) -> AmparoLegal | None:
    """Amparo legal publicado com a contratação, ou None se ausente.

    Guarda a descrição como publicada, a natureza lida do prefixo dela e, para as dispensas por valor, a
    chave do parâmetro legal que dá o limite (``AMPARO_DISPENSA_POR_VALOR``).
    """
    if not dados or dados.get("codigo") is None:
        return None
    codigo = inteiro_ou_nulo(dados.get("codigo"))
    descricao = texto_ou_nulo(dados.get("descricao"))
    return AmparoLegal(
        id=id_canonico("amparo_legal", "pncp", codigo),
        codigo_pncp=codigo,
        nome=texto_ou_nulo(dados.get("nome")) or f"código {codigo}",
        descricao_publicada=descricao,
        natureza=natureza_do_amparo(codigo, descricao),
        parametro_limite=AMPARO_DISPENSA_POR_VALOR.get(codigo),
        chave_origem=str(codigo),
        **ctx.prov(),
    )


def _fornecedor(documento: Any, tipo_pessoa: Any, nome: Any) -> tuple[str | None, str | None, TipoPessoa | None, list[str]]:
    """(fornecedor_id, documento publicável, tipo, marcações)."""
    marcas: list[str] = []
    tipo_txt = (texto_ou_nulo(tipo_pessoa) or "").strip().upper() or None
    try:
        tipo = TipoPessoa(tipo_txt) if tipo_txt else None
    except ValueError:
        tipo = None
    if not texto_ou_nulo(documento):
        return None, None, tipo, marcas
    publicavel = documento_publicavel(documento, tipo_txt)
    if publicavel is None:
        marcas.append(q.DOCUMENTO_FORNECEDOR_INVALIDO)
        return None, None, tipo, marcas
    if classificar(documento, tipo_txt) is TipoDocumento.CPF:
        # Pessoa física: o id não pode ser derivado do CPF inteiro (seria
        # reversível por força bruta). Máscara + nome distingue na prática.
        fid = id_canonico("fornecedor_pf", publicavel, texto_ou_nulo(nome) or "?")
    else:
        fid = id_canonico("fornecedor", publicavel)
    return fid, publicavel, tipo, marcas


# ---------------------------------------------------------------------------
# Contratações (/v1/contratacoes/publicacao e /atualizacao, e o detalhe)
# ---------------------------------------------------------------------------

def _contratacao(ctx: Contexto, d: dict) -> list:
    """Converte uma contratação do PNCP em órgão, unidade gestora, amparo legal e processo de contratação.

    Número de controle, ano, sequencial, objeto e data de publicação são obrigatórios, e valores negativos
    rejeitam o registro. Modalidade desconhecida, valor estimado zerado e valor homologado ausente não
    rejeitam: o processo segue com marcação de qualidade.
    """
    chave = str(obrigatorio(d, "numeroControlePNCP")).strip()
    orgao_d = d.get("orgaoEntidade") or {}
    orgao, ug, marcas = _orgao_e_unidade(
        ctx, orgao_d.get("cnpj"), orgao_d.get("razaoSocial"),
        orgao_d.get("esferaId"), orgao_d.get("poderId"), d.get("unidadeOrgao"),
    )
    ano = converter(inteiro_ou_nulo, d, "anoCompra")
    sequencial = converter(inteiro_ou_nulo, d, "sequencialCompra")
    if ano is None:
        raise RegistroRejeitado("campo obrigatório ausente", "anoCompra")
    if sequencial is None:
        raise RegistroRejeitado("campo obrigatório ausente", "sequencialCompra")
    objeto = texto_ou_nulo(obrigatorio(d, "objetoCompra"))
    publicado_em = converter(instante_brt_ou_nulo, d, "dataPublicacaoPncp", hoje=ctx.hoje)
    if publicado_em is None:
        raise RegistroRejeitado("campo obrigatório ausente", "dataPublicacaoPncp")

    cod_modalidade = converter(inteiro_ou_nulo, d, "modalidadeId")
    modalidade = MODALIDADES.get(cod_modalidade) if cod_modalidade is not None else None
    if modalidade is None:
        marcas.append(q.MODALIDADE_DESCONHECIDA)

    estimado = nao_negativo(converter(decimal_ou_nulo, d, "valorTotalEstimado"), "valorTotalEstimado")
    homologado = nao_negativo(converter(decimal_ou_nulo, d, "valorTotalHomologado"), "valorTotalHomologado")
    if estimado is not None and estimado == 0:
        marcas.append(q.VALOR_ESTIMADO_ZERO)
    if homologado is None:
        marcas.append(q.VALOR_HOMOLOGADO_AUSENTE)

    amparo = _amparo(ctx, d.get("amparoLegal"))
    unidade = d.get("unidadeOrgao") or {}
    processo = ProcessoContratacao(
        id=id_canonico("processo_contratacao", chave),
        chave_origem=chave,
        orgao_id=orgao.id,
        orgao_cnpj=orgao.cnpj,
        ente_id=orgao.ente_id,
        unidade_gestora_id=ug.id if ug else None,
        uf=texto_ou_nulo(unidade.get("ufSigla")),
        municipio_codigo_ibge=texto_ou_nulo(unidade.get("codigoIbge")),
        ano=ano,
        sequencial=sequencial,
        numero=texto_ou_nulo(d.get("numeroCompra")),
        processo=texto_ou_nulo(d.get("processo")),
        modalidade=modalidade,
        modalidade_codigo_origem=cod_modalidade,
        modo_disputa=texto_ou_nulo(d.get("modoDisputaNome")),
        amparo_legal_id=amparo.id if amparo else None,
        amparo_legal_codigo=amparo.codigo_pncp if amparo else None,
        objeto=objeto,
        informacao_complementar=texto_ou_nulo(d.get("informacaoComplementar")),
        srp=converter(booleano_ou_nulo, d, "srp"),
        valor_estimado=estimado,
        valor_homologado=homologado,
        data_publicacao=publicado_em.date(),
        publicado_em=publicado_em,
        abertura_propostas_em=converter(instante_brt_ou_nulo, d, "dataAberturaProposta", hoje=ctx.hoje),
        encerramento_propostas_em=converter(instante_brt_ou_nulo, d, "dataEncerramentoProposta", hoje=ctx.hoje),
        atualizado_em=converter(instante_brt_ou_nulo, d, "dataAtualizacaoGlobal", hoje=ctx.hoje),
        situacao=texto_ou_nulo(d.get("situacaoCompraNome")),
        sistema_origem=texto_ou_nulo(d.get("usuarioNome")),
        link_sistema_origem=texto_ou_nulo(d.get("linkSistemaOrigem")),
        marcacoes_qualidade=sorted(set(marcas)),
        **ctx.prov(),
    )
    saida: list = [orgao]
    if ug:
        saida.append(ug)
    if amparo:
        saida.append(amparo)
    saida.append(processo)
    return saida


def normalizar_contratacoes(
    conteudo: bytes, *, fonte_id: str, documento_fonte_id: str, hoje: date | None = None,
) -> ResultadoNormalizacao:
    """Página de ``/v1/contratacoes/publicacao`` ou ``/v1/contratacoes/atualizacao``."""
    ctx = Contexto(fonte_id, documento_fonte_id, hoje)
    return processar_lista(conteudo, ctx, lambda d: _contratacao(ctx, d),
                            lambda d: d.get("numeroControlePNCP"), paginado=True)


def normalizar_contratacao_detalhe(
    conteudo: bytes, *, fonte_id: str, documento_fonte_id: str, hoje: date | None = None,
) -> ResultadoNormalizacao:
    """Resposta de ``/v1/orgaos/{cnpj}/compras/{ano}/{sequencial}`` (objeto único)."""
    ctx = Contexto(fonte_id, documento_fonte_id, hoje)
    return processar_lista(conteudo, ctx, lambda d: _contratacao(ctx, d),
                            lambda d: d.get("numeroControlePNCP"), paginado=False)


# ---------------------------------------------------------------------------
# Itens e resultados (/api/pncp/v1/orgaos/{cnpj}/compras/{ano}/{seq}/itens)
# ---------------------------------------------------------------------------

def _item(ctx: Contexto, processo_chave: str, d: dict) -> list:
    """Converte um item da contratação em ``ItemContratacao``, ligado ao processo pela chave de origem.

    Número do item e descrição são obrigatórios; quantidade ou valor negativo rejeita o item.
    """
    numero = converter(inteiro_ou_nulo, d, "numeroItem")
    if numero is None:
        raise RegistroRejeitado("campo obrigatório ausente", "numeroItem")
    descricao = texto_ou_nulo(obrigatorio(d, "descricao"))
    return [ItemContratacao(
        id=id_canonico("item_contratacao", processo_chave, numero),
        processo_id=id_canonico("processo_contratacao", processo_chave),
        numero_item=numero,
        descricao_original=descricao,
        material_ou_servico=texto_ou_nulo(d.get("materialOuServico")),
        quantidade=nao_negativo(converter(decimal_ou_nulo, d, "quantidade"), "quantidade"),
        unidade_medida=texto_ou_nulo(d.get("unidadeMedida")),
        valor_unitario_estimado=nao_negativo(converter(decimal_ou_nulo, d, "valorUnitarioEstimado"), "valorUnitarioEstimado"),
        valor_total_estimado=nao_negativo(converter(decimal_ou_nulo, d, "valorTotal"), "valorTotal"),
        orcamento_sigiloso=converter(booleano_ou_nulo, d, "orcamentoSigiloso"),
        criterio_julgamento=texto_ou_nulo(d.get("criterioJulgamentoNome")),
        situacao=texto_ou_nulo(d.get("situacaoCompraItemNome")),
        catalogo=texto_ou_nulo(d.get("catalogo")),
        catalogo_codigo_item=texto_ou_nulo(d.get("catalogoCodigoItem")),
        ncm_nbs_codigo=texto_ou_nulo(d.get("ncmNbsCodigo")),
        tem_resultado=converter(booleano_ou_nulo, d, "temResultado"),
        chave_origem=f"{processo_chave}#{numero}",
        **ctx.prov(),
    )]


def normalizar_itens(
    conteudo: bytes, *, processo_chave_origem: str, fonte_id: str,
    documento_fonte_id: str, hoje: date | None = None,
) -> ResultadoNormalizacao:
    """Itens de uma contratação (``/v1/orgaos/{cnpj}/compras/{ano}/{sequencial}/itens``), em lista sem paginação.

    A chave do processo vem de quem chama (``processo_chave_origem``) e compõe o id e a chave de origem de
    cada item.
    """
    ctx = Contexto(fonte_id, documento_fonte_id, hoje)
    return processar_lista(conteudo, ctx, lambda d: _item(ctx, processo_chave_origem, d),
                            lambda d: f"{processo_chave_origem}#{d.get('numeroItem')}", paginado=False)


def _resultado(ctx: Contexto, processo_chave: str, d: dict) -> list:
    """Converte um resultado de item (o fornecedor e os valores homologados) em ``ResultadoItem``.

    O documento do fornecedor passa por ``_fornecedor``: CPF segue mascarado e documento inválido vira nulo
    com marcação. O resultado fica marcado como cancelado quando a fonte informa data de cancelamento.
    """
    numero_item = converter(inteiro_ou_nulo, d, "numeroItem")
    sequencial = converter(inteiro_ou_nulo, d, "sequencialResultado")
    if numero_item is None:
        raise RegistroRejeitado("campo obrigatório ausente", "numeroItem")
    if sequencial is None:
        raise RegistroRejeitado("campo obrigatório ausente", "sequencialResultado")
    fid, documento, tipo, marcas = _fornecedor(d.get("niFornecedor"), d.get("tipoPessoa"),
                                               d.get("nomeRazaoSocialFornecedor"))
    return [ResultadoItem(
        id=id_canonico("resultado_item", processo_chave, numero_item, sequencial),
        item_id=id_canonico("item_contratacao", processo_chave, numero_item),
        processo_id=id_canonico("processo_contratacao", processo_chave),
        sequencial_resultado=sequencial,
        fornecedor_id=fid,
        fornecedor_documento=documento,
        fornecedor_tipo_pessoa=tipo,
        fornecedor_nome=texto_ou_nulo(d.get("nomeRazaoSocialFornecedor")),
        porte_fornecedor=texto_ou_nulo(d.get("porteFornecedorNome")),
        quantidade_homologada=nao_negativo(converter(decimal_ou_nulo, d, "quantidadeHomologada"), "quantidadeHomologada"),
        valor_unitario_homologado=nao_negativo(converter(decimal_ou_nulo, d, "valorUnitarioHomologado"), "valorUnitarioHomologado"),
        valor_total_homologado=nao_negativo(converter(decimal_ou_nulo, d, "valorTotalHomologado"), "valorTotalHomologado"),
        percentual_desconto=converter(decimal_ou_nulo, d, "percentualDesconto"),
        data_resultado=converter(data_ou_nula, d, "dataResultado", hoje=ctx.hoje),
        cancelado=d.get("dataCancelamento") is not None,
        chave_origem=f"{processo_chave}#{numero_item}#{sequencial}",
        marcacoes_qualidade=marcas,
        **ctx.prov(),
    )]


def normalizar_resultados(
    conteudo: bytes, *, processo_chave_origem: str, fonte_id: str,
    documento_fonte_id: str, hoje: date | None = None,
) -> ResultadoNormalizacao:
    """Resultados dos itens de uma contratação, em lista sem paginação, ligados por ``processo_chave_origem``."""
    ctx = Contexto(fonte_id, documento_fonte_id, hoje)
    return processar_lista(conteudo, ctx, lambda d: _resultado(ctx, processo_chave_origem, d),
                            lambda d: f"{processo_chave_origem}#{d.get('numeroItem')}#{d.get('sequencialResultado')}",
                            paginado=False)


# ---------------------------------------------------------------------------
# Contratos (/v1/contratos e /v1/contratos/atualizacao)
# ---------------------------------------------------------------------------

def _contrato(ctx: Contexto, d: dict) -> list:
    """Converte um contrato do PNCP em órgão, unidade gestora e ``Contrato``.

    Número de controle, ano, sequencial e objeto são obrigatórios. O processo de origem, quando informado, é
    ligado pelo mesmo id determinístico da contratação, e as marcações do órgão e do fornecedor seguem
    juntas no contrato.
    """
    chave = str(obrigatorio(d, "numeroControlePNCP")).strip()
    orgao_d = d.get("orgaoEntidade") or {}
    orgao, ug, marcas = _orgao_e_unidade(
        ctx, orgao_d.get("cnpj"), orgao_d.get("razaoSocial"),
        orgao_d.get("esferaId"), orgao_d.get("poderId"), d.get("unidadeOrgao"),
    )
    ano = converter(inteiro_ou_nulo, d, "anoContrato")
    sequencial = converter(inteiro_ou_nulo, d, "sequencialContrato")
    if ano is None:
        raise RegistroRejeitado("campo obrigatório ausente", "anoContrato")
    if sequencial is None:
        raise RegistroRejeitado("campo obrigatório ausente", "sequencialContrato")
    objeto = texto_ou_nulo(obrigatorio(d, "objetoContrato"))
    fid, documento, tipo, marcas_f = _fornecedor(d.get("niFornecedor"), d.get("tipoPessoa"),
                                                 d.get("nomeRazaoSocialFornecedor"))
    marcas.extend(marcas_f)
    processo_chave = texto_ou_nulo(d.get("numeroControlePncpCompra"))
    unidade = d.get("unidadeOrgao") or {}
    tipo_contrato = d.get("tipoContrato") or {}
    categoria = d.get("categoriaProcesso") or {}
    contrato = Contrato(
        id=id_canonico("contrato", chave),
        chave_origem=chave,
        processo_chave_origem=processo_chave,
        processo_id=id_canonico("processo_contratacao", processo_chave) if processo_chave else None,
        ata_chave_origem=texto_ou_nulo(d.get("numeroControlePncpAta")),
        orgao_id=orgao.id,
        orgao_cnpj=orgao.cnpj,
        ente_id=orgao.ente_id,
        unidade_gestora_id=ug.id if ug else None,
        uf=texto_ou_nulo(unidade.get("ufSigla")),
        municipio_codigo_ibge=texto_ou_nulo(unidade.get("codigoIbge")),
        ano=ano,
        sequencial=sequencial,
        numero=texto_ou_nulo(d.get("numeroContratoEmpenho")),
        processo=texto_ou_nulo(d.get("processo")),
        tipo_instrumento=texto_ou_nulo(tipo_contrato.get("nome")),
        categoria=texto_ou_nulo(categoria.get("nome")),
        fornecedor_id=fid,
        fornecedor_documento=documento,
        fornecedor_tipo_pessoa=tipo,
        fornecedor_nome=texto_ou_nulo(d.get("nomeRazaoSocialFornecedor")),
        objeto=objeto,
        valor_inicial=nao_negativo(converter(decimal_ou_nulo, d, "valorInicial"), "valorInicial"),
        valor_global=nao_negativo(converter(decimal_ou_nulo, d, "valorGlobal"), "valorGlobal"),
        valor_parcela=nao_negativo(converter(decimal_ou_nulo, d, "valorParcela"), "valorParcela"),
        numero_parcelas=converter(inteiro_ou_nulo, d, "numeroParcelas"),
        valor_acumulado=nao_negativo(converter(decimal_ou_nulo, d, "valorAcumulado"), "valorAcumulado"),
        data_assinatura=converter(data_ou_nula, d, "dataAssinatura", hoje=ctx.hoje),
        vigencia_inicio=converter(data_ou_nula, d, "dataVigenciaInicio", hoje=ctx.hoje),
        vigencia_fim=converter(data_ou_nula, d, "dataVigenciaFim", hoje=ctx.hoje),
        publicado_em=converter(instante_brt_ou_nulo, d, "dataPublicacaoPncp", hoje=ctx.hoje),
        atualizado_em=converter(instante_brt_ou_nulo, d, "dataAtualizacaoGlobal", hoje=ctx.hoje),
        numero_retificacao=converter(inteiro_ou_nulo, d, "numeroRetificacao"),
        receita=converter(booleano_ou_nulo, d, "receita"),
        fruto_adesao=converter(booleano_ou_nulo, d, "frutoAdesao"),
        sistema_origem=texto_ou_nulo(d.get("usuarioNome")),
        marcacoes_qualidade=sorted(set(marcas)),
        **ctx.prov(),
    )
    saida: list = [orgao]
    if ug:
        saida.append(ug)
    saida.append(contrato)
    return saida


def normalizar_contratos(
    conteudo: bytes, *, fonte_id: str, documento_fonte_id: str, hoje: date | None = None,
) -> ResultadoNormalizacao:
    """Página de ``/v1/contratos`` ou ``/v1/contratos/atualizacao``."""
    ctx = Contexto(fonte_id, documento_fonte_id, hoje)
    return processar_lista(conteudo, ctx, lambda d: _contrato(ctx, d),
                            lambda d: d.get("numeroControlePNCP"), paginado=True)


# ---------------------------------------------------------------------------
# Atas de registro de preços (/v1/atas e /v1/atas/atualizacao)
# ---------------------------------------------------------------------------

def _ata(ctx: Contexto, d: dict) -> list:
    """Converte uma ata de registro de preços em ``AtaRegistroPreco``.

    O órgão vem só como CNPJ e nome no registro da ata, sem gerar ``Orgao``; CNPJ ausente ou inválido
    rejeita a ata. O processo de origem, quando informado, é ligado pelo id determinístico da contratação.
    """
    chave = str(obrigatorio(d, "numeroControlePNCPAta")).strip()
    cnpj = limpar(obrigatorio(d, "cnpjOrgao"))
    if not cnpj_valido(cnpj):
        raise RegistroRejeitado("CNPJ do órgão com dígito verificador inválido", "cnpjOrgao", cnpj)
    processo_chave = texto_ou_nulo(d.get("numeroControlePNCPCompra"))
    return [AtaRegistroPreco(
        id=id_canonico("ata_registro_preco", chave),
        chave_origem=chave,
        processo_chave_origem=processo_chave,
        processo_id=id_canonico("processo_contratacao", processo_chave) if processo_chave else None,
        orgao_cnpj=cnpj,
        orgao_nome=texto_ou_nulo(d.get("nomeOrgao")),
        unidade_codigo=texto_ou_nulo(d.get("codigoUnidadeOrgao")),
        unidade_nome=texto_ou_nulo(d.get("nomeUnidadeOrgao")),
        numero=texto_ou_nulo(d.get("numeroAtaRegistroPreco")),
        ano=converter(inteiro_ou_nulo, d, "anoAta"),
        objeto=texto_ou_nulo(d.get("objetoContratacao")),
        data_assinatura=converter(data_ou_nula, d, "dataAssinatura", hoje=ctx.hoje),
        vigencia_inicio=converter(data_ou_nula, d, "vigenciaInicio", hoje=ctx.hoje),
        vigencia_fim=converter(data_ou_nula, d, "vigenciaFim", hoje=ctx.hoje),
        cancelada=bool(converter(booleano_ou_nulo, d, "cancelado")),
        data_cancelamento=converter(data_ou_nula, d, "dataCancelamento", hoje=ctx.hoje),
        sistema_origem=texto_ou_nulo(d.get("usuario")),
        **ctx.prov(),
    )]


def normalizar_atas(
    conteudo: bytes, *, fonte_id: str, documento_fonte_id: str, hoje: date | None = None,
) -> ResultadoNormalizacao:
    """Página de ``/v1/atas`` ou ``/v1/atas/atualizacao``."""
    ctx = Contexto(fonte_id, documento_fonte_id, hoje)
    return processar_lista(conteudo, ctx, lambda d: _ata(ctx, d),
                            lambda d: d.get("numeroControlePNCPAta"), paginado=True)
