"""Normalização dos cadastros de sanções da CGU (CEIS, CNEP e CEPIM) para ``Sancao``.

O artefato do bronze é o ZIP do Portal da Transparência, com um CSV só
(``AAAAMMDD_CEIS.csv``), em ISO-8859-1, separado por ``;``. O dia no nome do
CSV é a ``data_referencia`` dos registros: cada arquivo é o retrato do
cadastro inteiro naquele dia (ADR-030).

Três cuidados:

- **CPF mascarado.** O CEIS publica o CPF inteiro das pessoas físicas
  sancionadas. Ele passa por ``identificar_fornecedor``, o mesmo caminho dos
  fornecedores do PNCP: o documento sai mascarado (``***.456.789-**``) e o id
  do fornecedor sai da máscara mais o nome, nunca do CPF inteiro.
- **"Sem Informação" é ausência.** A CGU escreve "Sem Informação" em
  abrangência e meio de publicação quando o órgão não informou; vira nulo.
- **Fim da sanção muito distante é o que foi publicado.** Há sanções "com
  prazo determinado" que terminam em 31/12/2099. A data é mantida como veio,
  com a marcação ``data_fim_distante``, em vez de mandar a sanção para a
  quarentena como erro de digitação.
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from datetime import date, datetime

from lumen_canonico.fato import CadastroSancao, Esfera, Sancao
from lumen_canonico.identidade import id_canonico
from lumen_canonico.ufs import SIGLA_PARA_CODIGO

from . import qualidade as q
from .comum import Contexto, converter, obrigatorio
from .pncp import identificar_fornecedor
from .qualidade import EntradaQuarentena, RegistroRejeitado, ResultadoNormalizacao
from .transformacoes import ValorIlegivel, data_ou_nula, moeda_br, texto_ou_nulo

VERSAO_NORMALIZADOR = "cgu-1"

DATA_FIM_DISTANTE = "data_fim_distante"
DATA_REFERENCIA_AUSENTE = "data_referencia_ausente"

SEM_INFORMACAO = {"sem informação", "sem informacao"}
ESFERAS_CGU = {"FEDERAL": Esfera.UNIAO, "ESTADUAL": Esfera.ESTADUAL, "MUNICIPAL": Esfera.MUNICIPAL,
               "DISTRITAL": Esfera.DISTRITAL}
TIPOS_PESSOA_CGU = {"F": "PF", "J": "PJ"}

# Colunas que a normalização lê; faltando alguma, o formato mudou e o artefato inteiro vai para a quarentena.
COLUNAS_SANCAO = ("CADASTRO", "CÓDIGO DA SANÇÃO", "TIPO DE PESSOA", "CPF OU CNPJ DO SANCIONADO",
                  "NOME DO SANCIONADO", "RAZÃO SOCIAL - CADASTRO RECEITA", "NÚMERO DO PROCESSO",
                  "CATEGORIA DA SANÇÃO", "DATA INÍCIO SANÇÃO", "DATA FINAL SANÇÃO", "DATA PUBLICAÇÃO",
                  "PUBLICAÇÃO", "DATA DO TRÂNSITO EM JULGADO", "ABRAGÊNCIA DA SANÇÃO", "ÓRGÃO SANCIONADOR",
                  "UF ÓRGÃO SANCIONADOR", "ESFERA ÓRGÃO SANCIONADOR", "FUNDAMENTAÇÃO LEGAL",
                  "DATA ORIGEM INFORMAÇÃO", "ORIGEM INFORMAÇÕES")
COLUNAS_CEPIM = ("CNPJ ENTIDADE", "NOME ENTIDADE", "NÚMERO CONVÊNIO", "ÓRGÃO CONCEDENTE", "MOTIVO DO IMPEDIMENTO")

_NOME_CSV = re.compile(r"(?P<data>\d{8})_(?P<cadastro>[A-Za-z]+)\.csv$", re.IGNORECASE)


def decodificar(conteudo: bytes) -> str:
    """Texto do CSV: UTF-8 se for, senão Windows-1252, senão ISO-8859-1 (que aceita qualquer byte).

    A CGU publica em ISO-8859-1; o Windows-1252 vem antes porque coincide com ele em todo texto
    imprimível e ainda lê aspas e travessões que o ISO-8859-1 trocaria por caracteres de controle.
    """
    for codificacao in ("utf-8-sig", "cp1252"):
        try:
            return conteudo.decode(codificacao)
        except UnicodeDecodeError:
            continue
    return conteudo.decode("latin-1")


def abrir_arquivo(conteudo: bytes) -> tuple[str | None, bytes]:
    """(nome do CSV, bytes do CSV) do artefato: o CSV dentro do ZIP, ou o próprio conteúdo se não for ZIP.

    ZIP sem CSV, ou com mais de um, levanta ``ValueError``: não há como saber qual é o cadastro.
    """
    if not conteudo.startswith(b"PK\x03\x04"):
        return None, conteudo
    with zipfile.ZipFile(io.BytesIO(conteudo)) as z:
        csvs = [n for n in z.namelist() if n.lower().endswith(".csv")]
        if len(csvs) != 1:
            raise ValueError(f"ZIP com {len(csvs)} arquivos CSV (esperado 1): {z.namelist()}")
        return csvs[0], z.read(csvs[0])


def data_do_nome(nome: str | None) -> date | None:
    """Dia do retrato a partir do nome do CSV (``20261015_CEIS.csv`` → 15/10/2026); None se não houver."""
    m = _NOME_CSV.search(nome or "")
    if not m:
        return None
    try:
        return datetime.strptime(m["data"], "%Y%m%d").date()
    except ValueError:
        return None


def _informado(valor: object) -> str | None:
    """Texto como publicado, com vazio e "Sem Informação" virando nulo."""
    texto = texto_ou_nulo(valor)
    if texto is None or texto.strip().lower() in SEM_INFORMACAO:
        return None
    return texto


def _data_fim(ctx: Contexto, d: dict, campo: str, marcas: list[str]) -> date | None:
    """Data final da sanção; fora da faixa plausível, fica como publicada e ganha ``data_fim_distante``."""
    try:
        return data_ou_nula(d.get(campo), hoje=ctx.hoje)
    except ValorIlegivel as erro:
        texto = str(d.get(campo) or "").strip()
        if re.fullmatch(r"\d{2}/\d{2}/\d{4}", texto):
            try:
                valor = datetime.strptime(texto, "%d/%m/%Y").date()
            except ValueError:
                valor = None
            if valor is not None and valor.year > (ctx.hoje or date.today()).year:
                marcas.append(DATA_FIM_DISTANTE)
                return valor
        raise RegistroRejeitado(str(erro), campo, d.get(campo)) from erro


def _esfera(valor: object, marcas: list[str]) -> Esfera | None:
    """Esfera do órgão sancionador; ausente ou desconhecida fica nula com ``esfera_nao_informada``."""
    texto = (texto_ou_nulo(valor) or "").strip().upper()
    esfera = ESFERAS_CGU.get(texto)
    if esfera is None:
        marcas.append(q.ESFERA_NAO_INFORMADA)
    return esfera


def _uf(valor: object) -> str | None:
    """Sigla da UF do órgão sancionador, só se for uma das 27; o resto (vazio, ``BR``) vira nulo."""
    texto = (texto_ou_nulo(valor) or "").strip().upper()
    return texto if texto in SIGLA_PARA_CODIGO else None


def _sancao(ctx: Contexto, d: dict, cadastro_fonte: CadastroSancao | None, referencia: date | None) -> list:
    """Uma linha do CEIS ou do CNEP como ``Sancao``.

    Código da sanção, nome do sancionado e início da sanção são obrigatórios. Linha de um cadastro
    diferente do da fonte (um CNEP dentro do arquivo do CEIS) é rejeitada.
    """
    try:
        cadastro = CadastroSancao(str(obrigatorio(d, "CADASTRO")).strip().upper())
    except ValueError as erro:
        raise RegistroRejeitado("cadastro desconhecido", "CADASTRO", d.get("CADASTRO")) from erro
    if cadastro_fonte is not None and cadastro is not cadastro_fonte:
        raise RegistroRejeitado("cadastro da linha diverge do arquivo", "CADASTRO", d.get("CADASTRO"))
    codigo = str(obrigatorio(d, "CÓDIGO DA SANÇÃO")).strip()
    nome = texto_ou_nulo(obrigatorio(d, "NOME DO SANCIONADO"))
    marcas: list[str] = [] if referencia else [DATA_REFERENCIA_AUSENTE]
    tipo = TIPOS_PESSOA_CGU.get(str(d.get("TIPO DE PESSOA") or "").strip().upper())
    fid, documento, tipo_pessoa, marcas_doc = identificar_fornecedor(d.get("CPF OU CNPJ DO SANCIONADO"), tipo, nome)
    marcas.extend(marcas_doc)
    inicio = converter(data_ou_nula, d, "DATA INÍCIO SANÇÃO", hoje=ctx.hoje)
    if inicio is None:
        raise RegistroRejeitado("campo obrigatório ausente", "DATA INÍCIO SANÇÃO")
    fim = _data_fim(ctx, d, "DATA FINAL SANÇÃO", marcas)
    multa = converter(moeda_br, d, "VALOR DA MULTA") if "VALOR DA MULTA" in d else None
    # Razão social da Receita só para pessoa jurídica: de pessoa física, o nome publicado basta.
    razao = _informado(d.get("RAZÃO SOCIAL - CADASTRO RECEITA")) if tipo_pessoa and tipo_pessoa.value == "PJ" else None
    return [Sancao(
        id=id_canonico("sancao", cadastro.value, codigo), cadastro=cadastro, data_referencia=referencia,
        fornecedor_id=fid, documento=documento, tipo_pessoa=tipo_pessoa, nome=nome or codigo,
        razao_social_receita=razao, categoria=_informado(d.get("CATEGORIA DA SANÇÃO")),
        numero_processo=_informado(d.get("NÚMERO DO PROCESSO")), numero_convenio=None, valor_multa=multa,
        data_inicio=inicio, data_fim=fim,
        data_publicacao=converter(data_ou_nula, d, "DATA PUBLICAÇÃO", hoje=ctx.hoje),
        data_transito_julgado=converter(data_ou_nula, d, "DATA DO TRÂNSITO EM JULGADO", hoje=ctx.hoje),
        data_origem_informacao=converter(data_ou_nula, d, "DATA ORIGEM INFORMAÇÃO", hoje=ctx.hoje),
        meio_publicacao=_informado(d.get("PUBLICAÇÃO")), abrangencia=_informado(d.get("ABRAGÊNCIA DA SANÇÃO")),
        orgao_sancionador=_informado(d.get("ÓRGÃO SANCIONADOR")),
        uf_orgao_sancionador=_uf(d.get("UF ÓRGÃO SANCIONADOR")),
        esfera_orgao_sancionador=_esfera(d.get("ESFERA ÓRGÃO SANCIONADOR"), marcas),
        fundamentacao_legal=_informado(d.get("FUNDAMENTAÇÃO LEGAL")),
        origem_informacao=_informado(d.get("ORIGEM INFORMAÇÕES")),
        chave_origem=codigo, marcacoes_qualidade=marcas, **ctx.prov(),
    )]


def _impedimento(ctx: Contexto, d: dict, referencia: date | None) -> list:
    """Uma linha do CEPIM como ``Sancao``: entidade, convênio, órgão concedente e motivo, sem datas.

    CNPJ, nome da entidade e número do convênio são obrigatórios; o CEPIM não tem código de sanção, e a
    chave é CNPJ mais convênio.
    """
    nome = texto_ou_nulo(obrigatorio(d, "NOME ENTIDADE"))
    convenio = str(obrigatorio(d, "NÚMERO CONVÊNIO")).strip()
    fid, documento, tipo_pessoa, marcas_doc = identificar_fornecedor(obrigatorio(d, "CNPJ ENTIDADE"), "PJ", nome)
    if documento is None:
        raise RegistroRejeitado("CNPJ da entidade inválido", "CNPJ ENTIDADE", d.get("CNPJ ENTIDADE"))
    marcas: list[str] = ([] if referencia else [DATA_REFERENCIA_AUSENTE]) + marcas_doc
    return [Sancao(
        id=id_canonico("sancao", "CEPIM", documento, convenio), cadastro=CadastroSancao.CEPIM,
        data_referencia=referencia, fornecedor_id=fid, documento=documento, tipo_pessoa=tipo_pessoa,
        nome=nome or documento, razao_social_receita=None, categoria=_informado(d.get("MOTIVO DO IMPEDIMENTO")),
        numero_processo=None, numero_convenio=convenio, valor_multa=None, data_inicio=None, data_fim=None,
        data_publicacao=None, data_transito_julgado=None, data_origem_informacao=None, meio_publicacao=None,
        abrangencia=None, orgao_sancionador=_informado(d.get("ÓRGÃO CONCEDENTE")), uf_orgao_sancionador=None,
        esfera_orgao_sancionador=Esfera.UNIAO, fundamentacao_legal=None, origem_informacao=None,
        chave_origem=f"{documento}/{convenio}", marcacoes_qualidade=marcas, **ctx.prov(),
    )]


def _quarentena_do_artefato(ctx: Contexto, motivo: str, valor: object = None) -> ResultadoNormalizacao:
    """Resultado com uma entrada só na quarentena, para o artefato que não pôde ser lido como cadastro."""
    resultado = ResultadoNormalizacao()
    resultado.quarentena.append(EntradaQuarentena(
        fonte_id=ctx.fonte_id, documento_fonte_id=ctx.documento_fonte_id, chave_origem=None, posicao=None,
        motivo=motivo, campo=None, valor_recebido=q.resumir_valor(valor)))
    return resultado


def normalizar_sancoes(conteudo: bytes, *, fonte_id: str, documento_fonte_id: str,
                       hoje: date | None = None) -> ResultadoNormalizacao:
    """Arquivo do CEIS, do CNEP ou do CEPIM como registros ``Sancao``, um por linha do CSV.

    O formato (sanção ou impedimento) sai do cabeçalho; o cadastro esperado sai da fonte
    (``cgu_ceis`` → CEIS). Artefato ilegível ou com coluna faltando vai inteiro para a quarentena; cada
    linha com problema vai sozinha, e o resto segue (RF-NO-08).
    """
    ctx = Contexto(fonte_id, documento_fonte_id, hoje)
    try:
        nome, dados = abrir_arquivo(conteudo)
    except (ValueError, zipfile.BadZipFile) as erro:
        return _quarentena_do_artefato(ctx, f"arquivo ilegível: {erro}", conteudo[:200])
    if not dados.strip():
        return ResultadoNormalizacao()
    referencia = data_do_nome(nome)
    leitor = csv.DictReader(io.StringIO(decodificar(dados), newline=""), delimiter=";")
    colunas = {c.strip() for c in (leitor.fieldnames or [])}
    sufixo = fonte_id.rsplit("_", 1)[-1].upper()
    cadastro_fonte = CadastroSancao(sufixo) if sufixo in CadastroSancao.__members__ else None
    if "CNPJ ENTIDADE" in colunas:
        exigidas, extrator = COLUNAS_CEPIM, (lambda d: _impedimento(ctx, d, referencia))
    else:
        exigidas, extrator = COLUNAS_SANCAO, (lambda d: _sancao(ctx, d, cadastro_fonte, referencia))
    faltando = [c for c in exigidas if c not in colunas]
    if faltando:
        return _quarentena_do_artefato(ctx, f"cabeçalho sem as colunas {faltando} (o formato da fonte mudou?)",
                                       sorted(colunas))
    resultado = ResultadoNormalizacao()
    for posicao, linha in enumerate(leitor):
        d = {(k or "").strip(): v for k, v in linha.items()}
        resultado.lidos += 1
        try:
            resultado.registros.extend(extrator(d))
        except RegistroRejeitado as rej:
            chave = d.get("CÓDIGO DA SANÇÃO") or d.get("NÚMERO CONVÊNIO")
            resultado.quarentena.append(EntradaQuarentena(
                fonte_id=ctx.fonte_id, documento_fonte_id=ctx.documento_fonte_id, chave_origem=chave,
                posicao=posicao, motivo=rej.motivo, campo=rej.campo, valor_recebido=q.resumir_valor(rej.valor)))
    return resultado
