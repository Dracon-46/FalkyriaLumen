"""Bloco de fato administrativo do esquema canônico (DOC-05, seção 3.1).

Este é o bloco que o README deixou de propósito para depois: o DOC-05 foi
escrito a partir da documentação do PNCP, e o esquema deveria nascer das
respostas reais da API, que costumam divergir da documentação. Ele nasceu
delas: os campos abaixo foram desenhados sobre respostas capturadas da API de
consulta do PNCP em 05/10/2026 (as amostras estão em
``testes/fixtures/pncp/``). As divergências encontradas entre o DOC-05 e a
fonte real estão registradas na ADR-017 e resumidas aqui:

1. **Ente federativo, órgão e unidade gestora são três coisas.** O PNCP
   identifica quem contrata pelo CNPJ do órgão (``orgaoEntidade``), que pode
   ser a prefeitura, mas também uma câmara, uma autarquia ou uma empresa
   pública municipal. O código IBGE que vem junto é o do município onde fica
   a unidade, não o do ente: uma secretaria estadual em Fortaleza traz o
   código de Fortaleza. O ente federativo (União, estado, DF ou município) é
   resolvido a partir da esfera do órgão, e quando a fonte não informa a
   esfera ele fica explicitamente nulo, à espera de resolução.
2. **"Não se aplica" vira nulo.** O PNCP usa ``N`` em ``esferaId`` e
   ``poderId`` tanto para "não se aplica" quanto, na prática, para "não
   informado" (um município com ``poderId = N``). Pelo princípio 4 do DOC-05
   nada é preenchido por inferência: o valor fica nulo e a ausência é
   registrada como marcação de qualidade.
3. **A modalidade tem mais valores que os do DOC-05.** O domínio oficial do
   PNCP tem 19 modalidades, entre elas credenciamento, pré-qualificação,
   manifestação de interesse, inaplicabilidade e chamada pública. O enum
   canônico foi ampliado, e o código original da fonte é preservado ao lado.
4. **O agente que autorizou não vem na API.** Nenhum dos recursos de
   consulta do PNCP traz o signatário do ato. Ele aparece, quando aparece,
   nos documentos anexos (aviso de contratação direta, ato de autorização).
   O ``AtoAutorizativo`` do DOC-05 continua no modelo, mas sua fonte passa a
   ser a extração de documentos da fase 4, e a ausência desse dado na API é,
   ela mesma, insumo para o módulo de conformidade.
5. **O software que publicou vem na API.** ``usuarioNome`` identifica o
   sistema que enviou o registro ao PNCP (por exemplo, o fornecedor do
   portal do município). É exatamente o sinal de "família de plataforma" de
   que a fase 4 precisa, e passa a ser guardado em ``sistema_origem``.

Dinheiro é sempre ``Decimal``; datas sem hora são ``date``; instantes são
``datetime`` com fuso. O PNCP publica instantes sem fuso, no horário de
Brasília; a normalização atribui UTC-3 fixo, correto para todo o período
coberto pela Lei 14.133 (o horário de verão foi extinto em 2019).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, ClassVar


class Esfera(str, Enum):
    """Esfera federativa do ente ou do órgão: União, estadual, municipal ou distrital.

    Quando a fonte não informa a esfera (o ``N`` do PNCP), o campo fica nulo com marcação de qualidade, em
    vez de receber um valor inferido (item 2 do topo deste módulo).
    """

    UNIAO = "uniao"
    ESTADUAL = "estadual"
    MUNICIPAL = "municipal"
    DISTRITAL = "distrital"


class Poder(str, Enum):
    """Poder a que o órgão pertence.

    A normalização do PNCP só preenche executivo, legislativo e judiciário; ``N`` ou ausência viram nulo com
    marcação de qualidade. ``AUTONOMO`` existe no domínio canônico, mas nenhum normalizador o preenche nesta
    versão.
    """

    EXECUTIVO = "executivo"
    LEGISLATIVO = "legislativo"
    JUDICIARIO = "judiciario"
    AUTONOMO = "autonomo"


class Modalidade(str, Enum):
    """Modalidade de contratação. Ampliada a partir do domínio real do PNCP."""

    PREGAO = "pregao"
    CONCORRENCIA = "concorrencia"
    CONCURSO = "concurso"
    LEILAO = "leilao"
    DIALOGO = "dialogo"
    DISPENSA = "dispensa"
    INEXIGIBILIDADE = "inexigibilidade"
    CREDENCIAMENTO = "credenciamento"
    PRE_QUALIFICACAO = "pre_qualificacao"
    MANIFESTACAO_INTERESSE = "manifestacao_interesse"
    INAPLICABILIDADE = "inaplicabilidade"
    CHAMADA_PUBLICA = "chamada_publica"

    @property
    def eh_contratacao_direta(self) -> bool:
        """Verdadeiro para dispensa e inexigibilidade, as contratações diretas da Lei 14.133/2021 (arts. 72 a 75)."""
        return self in (Modalidade.DISPENSA, Modalidade.INEXIGIBILIDADE)


class Sensibilidade(str, Enum):
    """Notação do DOC-05, seção 3: governa exibição, exportação e retenção."""

    PUBLICO = "P"             # dado público de ato administrativo
    AGENTE_PUBLICO = "PA"     # agente público no exercício da função
    SENSIVEL = "S"            # sujeito a mascaramento
    INTERNO = "I"             # metadado do próprio Lumen (ids, proveniência)


class TipoPessoa(str, Enum):
    """Tipo de pessoa do fornecedor, com os códigos que o PNCP declara em ``tipoPessoa``.

    O tipo declarado decide a classificação do documento (``documentos.classificar``): PJ segue com o CNPJ
    inteiro, PF com o CPF mascarado e PE (pessoa estrangeira) com o documento como veio.
    """

    JURIDICA = "PJ"
    FISICA = "PF"
    ESTRANGEIRA = "PE"


class CadastroSancao(str, Enum):
    """Cadastro da CGU de onde vem a sanção ou o impedimento (Portal da Transparência).

    CEIS: empresas inidôneas e suspensas; CNEP: empresas punidas pela Lei 12.846/2013; CEPIM: entidades
    privadas sem fins lucrativos impedidas de receber transferências da União.
    """

    CEIS = "CEIS"
    CNEP = "CNEP"
    CEPIM = "CEPIM"


# ---------------------------------------------------------------------------
# Base comum
# ---------------------------------------------------------------------------

def _serializar(valor: Any) -> Any:
    """Converte um valor para tipos aceitos pelo JSON, percorrendo listas e dicionários.

    ``Decimal`` vira texto, e não número, para que o valor monetário chegue à silver sem passar por
    ``float``; datas e instantes viram ISO 8601 e enums viram o seu valor.
    """
    if isinstance(valor, Decimal):
        return str(valor)
    if isinstance(valor, (date, datetime)):
        return valor.isoformat()
    if isinstance(valor, Enum):
        return valor.value
    if isinstance(valor, (list, tuple)):
        return [_serializar(v) for v in valor]
    if isinstance(valor, dict):
        return {k: _serializar(v) for k, v in valor.items()}
    return valor


@dataclass
class RegistroCanonico:
    """Campos de proveniência que todo registro de fato carrega (princípio 2)."""

    SENSIBILIDADE: ClassVar[dict[str, Sensibilidade]] = {}
    ENTIDADE: ClassVar[str] = ""

    def __post_init__(self) -> None:
        """Recusa a criação do registro se algum campo não tiver classificação de sensibilidade (RNF-18)."""
        sem_classificacao = {f.name for f in fields(self)} - set(self.sensibilidade_completa())
        if sem_classificacao:
            # RNF-18: todo campo precisa de classificação. Falhar na criação é
            # a forma de impedir que um campo novo chegue à camada consultável
            # sem que alguém tenha decidido o que ele é.
            raise TypeError(
                f"{type(self).__name__}: campos sem classificação de sensibilidade "
                f"{sorted(sem_classificacao)}"
            )

    @classmethod
    def sensibilidade_completa(cls) -> dict[str, Sensibilidade]:
        """Mapa campo → sensibilidade: os campos de proveniência comuns somados ao ``SENSIBILIDADE`` da subclasse."""
        base = {
            "id": Sensibilidade.INTERNO,
            "documento_fonte_id": Sensibilidade.INTERNO,
            "fonte_id": Sensibilidade.INTERNO,
            "chave_origem": Sensibilidade.PUBLICO,
            "marcacoes_qualidade": Sensibilidade.INTERNO,
        }
        base.update(cls.SENSIBILIDADE)
        return base

    def para_dict(self) -> dict[str, Any]:
        """Dicionário serializável do registro, com ``_entidade`` indicando a entidade canônica.

        É a forma gravada na silver, uma linha JSON por registro.
        """
        dados = {k: _serializar(v) for k, v in asdict(self).items()}
        dados["_entidade"] = self.ENTIDADE
        return dados


# ---------------------------------------------------------------------------
# Quem contrata
# ---------------------------------------------------------------------------

@dataclass
class EnteFederativo(RegistroCanonico):
    """União, estado, Distrito Federal ou município. Chave: código IBGE.

    A União não tem código IBGE de município nem de UF; o SICONFI usa ``1``
    para ela, e o Lumen adota a mesma convenção.
    """

    ENTIDADE: ClassVar[str] = "ente_federativo"
    SENSIBILIDADE: ClassVar[dict[str, Sensibilidade]] = {
        "codigo_ibge": Sensibilidade.PUBLICO,
        "nome": Sensibilidade.PUBLICO,
        "esfera": Sensibilidade.PUBLICO,
        "uf": Sensibilidade.PUBLICO,
        "cnpj": Sensibilidade.PUBLICO,
        "capital": Sensibilidade.PUBLICO,
        "regiao": Sensibilidade.PUBLICO,
        "populacao": Sensibilidade.PUBLICO,
        "populacao_referencia": Sensibilidade.PUBLICO,
        "porte": Sensibilidade.PUBLICO,
    }

    id: str
    codigo_ibge: str
    nome: str
    esfera: Esfera
    uf: str | None
    cnpj: str | None = None
    capital: bool | None = None
    regiao: str | None = None
    populacao: int | None = None
    populacao_referencia: str | None = None   # ex.: "IBGE estimativa 2026"
    porte: str | None = None
    fonte_id: str | None = None
    documento_fonte_id: str | None = None
    chave_origem: str | None = None
    marcacoes_qualidade: list[str] = field(default_factory=list)


@dataclass
class Orgao(RegistroCanonico):
    """Pessoa jurídica de direito público ou estatal que contrata. Chave: CNPJ."""

    ENTIDADE: ClassVar[str] = "orgao"
    SENSIBILIDADE: ClassVar[dict[str, Sensibilidade]] = {
        "cnpj": Sensibilidade.PUBLICO,
        "razao_social": Sensibilidade.PUBLICO,
        "esfera": Sensibilidade.PUBLICO,
        "poder": Sensibilidade.PUBLICO,
        "ente_id": Sensibilidade.INTERNO,
        "ente_codigo_ibge": Sensibilidade.PUBLICO,
    }

    id: str
    cnpj: str
    razao_social: str
    esfera: Esfera | None
    poder: Poder | None
    ente_id: str | None
    ente_codigo_ibge: str | None
    fonte_id: str | None = None
    documento_fonte_id: str | None = None
    chave_origem: str | None = None
    marcacoes_qualidade: list[str] = field(default_factory=list)


@dataclass
class UnidadeGestora(RegistroCanonico):
    """Unidade do órgão que conduziu o ato. Chave: CNPJ do órgão + código.

    É a unidade gestora que o art. 75, § 1º, I, da Lei 14.133 usa para somar
    as dispensas no exercício. Sem ela a família B agregaria unidades
    autônomas que a lei conta separadamente (falso positivo conhecido da B-01).
    """

    ENTIDADE: ClassVar[str] = "unidade_gestora"
    SENSIBILIDADE: ClassVar[dict[str, Sensibilidade]] = {
        "orgao_id": Sensibilidade.INTERNO,
        "orgao_cnpj": Sensibilidade.PUBLICO,
        "codigo": Sensibilidade.PUBLICO,
        "nome": Sensibilidade.PUBLICO,
        "municipio_codigo_ibge": Sensibilidade.PUBLICO,
        "municipio_nome": Sensibilidade.PUBLICO,
        "uf": Sensibilidade.PUBLICO,
    }

    id: str
    orgao_id: str
    orgao_cnpj: str
    codigo: str
    nome: str | None
    municipio_codigo_ibge: str | None
    municipio_nome: str | None
    uf: str | None
    fonte_id: str | None = None
    documento_fonte_id: str | None = None
    chave_origem: str | None = None
    marcacoes_qualidade: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# O ato
# ---------------------------------------------------------------------------

@dataclass
class AmparoLegal(RegistroCanonico):
    """Dispositivo invocado. Chave: código do domínio do PNCP.

    ``descricao_publicada`` é guardada como a fonte publica, sem edição. Ela
    pode citar valores defasados: no domínio do PNCP o art. 75, II ainda diz
    "inferiores a R$ 50.000,00", o valor original da lei. O limite usado pelas
    regras vem sempre de ``parametros_legais``, nunca deste texto.
    """

    ENTIDADE: ClassVar[str] = "amparo_legal"
    SENSIBILIDADE: ClassVar[dict[str, Sensibilidade]] = {
        "codigo_pncp": Sensibilidade.PUBLICO,
        "nome": Sensibilidade.PUBLICO,
        "descricao_publicada": Sensibilidade.PUBLICO,
        "natureza": Sensibilidade.PUBLICO,
        "parametro_limite": Sensibilidade.INTERNO,
    }

    id: str
    codigo_pncp: int
    nome: str
    descricao_publicada: str | None
    natureza: str | None          # dispensa, inexigibilidade, licitacao, ...
    parametro_limite: str | None  # chave em parametros_legais, quando é dispensa por valor
    fonte_id: str | None = None
    documento_fonte_id: str | None = None
    chave_origem: str | None = None
    marcacoes_qualidade: list[str] = field(default_factory=list)


@dataclass
class ProcessoContratacao(RegistroCanonico):
    """Licitação, dispensa ou inexigibilidade. Chave: numeroControlePNCP."""

    ENTIDADE: ClassVar[str] = "processo_contratacao"
    SENSIBILIDADE: ClassVar[dict[str, Sensibilidade]] = {
        "orgao_id": Sensibilidade.INTERNO,
        "orgao_cnpj": Sensibilidade.PUBLICO,
        "ente_id": Sensibilidade.INTERNO,
        "unidade_gestora_id": Sensibilidade.INTERNO,
        "uf": Sensibilidade.PUBLICO,
        "municipio_codigo_ibge": Sensibilidade.PUBLICO,
        "ano": Sensibilidade.PUBLICO,
        "sequencial": Sensibilidade.PUBLICO,
        "numero": Sensibilidade.PUBLICO,
        "processo": Sensibilidade.PUBLICO,
        "modalidade": Sensibilidade.PUBLICO,
        "modalidade_codigo_origem": Sensibilidade.PUBLICO,
        "modo_disputa": Sensibilidade.PUBLICO,
        "amparo_legal_id": Sensibilidade.INTERNO,
        "amparo_legal_codigo": Sensibilidade.PUBLICO,
        "objeto": Sensibilidade.PUBLICO,
        "informacao_complementar": Sensibilidade.PUBLICO,
        "srp": Sensibilidade.PUBLICO,
        "valor_estimado": Sensibilidade.PUBLICO,
        "valor_homologado": Sensibilidade.PUBLICO,
        "data_publicacao": Sensibilidade.PUBLICO,
        "publicado_em": Sensibilidade.PUBLICO,
        "abertura_propostas_em": Sensibilidade.PUBLICO,
        "encerramento_propostas_em": Sensibilidade.PUBLICO,
        "atualizado_em": Sensibilidade.PUBLICO,
        "situacao": Sensibilidade.PUBLICO,
        "sistema_origem": Sensibilidade.PUBLICO,
        "link_sistema_origem": Sensibilidade.PUBLICO,
        "quantidade_participantes": Sensibilidade.PUBLICO,
    }

    id: str
    chave_origem: str
    orgao_id: str
    orgao_cnpj: str
    ente_id: str | None
    unidade_gestora_id: str | None
    uf: str | None
    municipio_codigo_ibge: str | None
    ano: int
    sequencial: int
    numero: str | None
    processo: str | None
    modalidade: Modalidade | None
    modalidade_codigo_origem: int | None
    modo_disputa: str | None
    amparo_legal_id: str | None
    amparo_legal_codigo: int | None
    objeto: str
    informacao_complementar: str | None
    srp: bool | None
    valor_estimado: Decimal | None
    valor_homologado: Decimal | None
    data_publicacao: date
    publicado_em: datetime
    abertura_propostas_em: datetime | None
    encerramento_propostas_em: datetime | None
    atualizado_em: datetime | None
    situacao: str | None
    sistema_origem: str | None
    link_sistema_origem: str | None
    quantidade_participantes: int | None = None   # não vem na consulta; vem dos resultados
    fonte_id: str | None = None
    documento_fonte_id: str | None = None
    marcacoes_qualidade: list[str] = field(default_factory=list)


@dataclass
class ItemContratacao(RegistroCanonico):
    """Item de um processo. Chave: processo + número do item.

    É a base das regras de preço (família A). O PNCP publica o item no
    processo, com valor estimado, e o preço efetivo no resultado do item
    (``ResultadoItem``); os dois ficam separados porque um item pode ter mais
    de um resultado, e porque estimado e homologado são fatos distintos.
    """

    ENTIDADE: ClassVar[str] = "item_contratacao"
    SENSIBILIDADE: ClassVar[dict[str, Sensibilidade]] = {
        "processo_id": Sensibilidade.INTERNO,
        "numero_item": Sensibilidade.PUBLICO,
        "descricao_original": Sensibilidade.PUBLICO,
        "material_ou_servico": Sensibilidade.PUBLICO,
        "quantidade": Sensibilidade.PUBLICO,
        "unidade_medida": Sensibilidade.PUBLICO,
        "valor_unitario_estimado": Sensibilidade.PUBLICO,
        "valor_total_estimado": Sensibilidade.PUBLICO,
        "orcamento_sigiloso": Sensibilidade.PUBLICO,
        "criterio_julgamento": Sensibilidade.PUBLICO,
        "situacao": Sensibilidade.PUBLICO,
        "catalogo": Sensibilidade.PUBLICO,
        "catalogo_codigo_item": Sensibilidade.PUBLICO,
        "ncm_nbs_codigo": Sensibilidade.PUBLICO,
        "catalogo_item_id": Sensibilidade.INTERNO,
        "tem_resultado": Sensibilidade.PUBLICO,
    }

    id: str
    processo_id: str
    numero_item: int
    descricao_original: str
    material_ou_servico: str | None
    quantidade: Decimal | None
    unidade_medida: str | None
    valor_unitario_estimado: Decimal | None
    valor_total_estimado: Decimal | None
    orcamento_sigiloso: bool | None
    criterio_julgamento: str | None
    situacao: str | None
    catalogo: str | None
    catalogo_codigo_item: str | None
    ncm_nbs_codigo: str | None
    catalogo_item_id: str | None = None  # preenchido pelo enriquecimento (fase 2)
    tem_resultado: bool | None = None
    chave_origem: str | None = None
    fonte_id: str | None = None
    documento_fonte_id: str | None = None
    marcacoes_qualidade: list[str] = field(default_factory=list)


@dataclass
class ResultadoItem(RegistroCanonico):
    """Resultado homologado de um item, com o fornecedor. Chave: item + sequencial."""

    ENTIDADE: ClassVar[str] = "resultado_item"
    SENSIBILIDADE: ClassVar[dict[str, Sensibilidade]] = {
        "item_id": Sensibilidade.INTERNO,
        "processo_id": Sensibilidade.INTERNO,
        "sequencial_resultado": Sensibilidade.PUBLICO,
        "fornecedor_id": Sensibilidade.INTERNO,
        "fornecedor_documento": Sensibilidade.SENSIVEL,
        "fornecedor_tipo_pessoa": Sensibilidade.PUBLICO,
        "fornecedor_nome": Sensibilidade.PUBLICO,
        "porte_fornecedor": Sensibilidade.PUBLICO,
        "quantidade_homologada": Sensibilidade.PUBLICO,
        "valor_unitario_homologado": Sensibilidade.PUBLICO,
        "valor_total_homologado": Sensibilidade.PUBLICO,
        "percentual_desconto": Sensibilidade.PUBLICO,
        "data_resultado": Sensibilidade.PUBLICO,
        "cancelado": Sensibilidade.PUBLICO,
    }

    id: str
    item_id: str
    processo_id: str
    sequencial_resultado: int
    fornecedor_id: str | None
    fornecedor_documento: str | None      # CNPJ inteiro; CPF já mascarado
    fornecedor_tipo_pessoa: TipoPessoa | None
    fornecedor_nome: str | None
    porte_fornecedor: str | None
    quantidade_homologada: Decimal | None
    valor_unitario_homologado: Decimal | None
    valor_total_homologado: Decimal | None
    percentual_desconto: Decimal | None
    data_resultado: date | None
    cancelado: bool = False
    chave_origem: str | None = None
    fonte_id: str | None = None
    documento_fonte_id: str | None = None
    marcacoes_qualidade: list[str] = field(default_factory=list)


@dataclass
class Contrato(RegistroCanonico):
    """Contrato ou empenho com força de contrato. Chave: numeroControlePNCP.

    O recurso ``/v1/contratos`` do PNCP mistura contrato (termo inicial),
    empenho, carta-contrato e outros instrumentos; o tipo fica em
    ``tipo_instrumento``. ``valor_acumulado`` é o valor já executado segundo a
    fonte, e vem zerado com frequência em contratos recém-publicados.
    """

    ENTIDADE: ClassVar[str] = "contrato"
    SENSIBILIDADE: ClassVar[dict[str, Sensibilidade]] = {
        "processo_chave_origem": Sensibilidade.PUBLICO,
        "processo_id": Sensibilidade.INTERNO,
        "ata_chave_origem": Sensibilidade.PUBLICO,
        "orgao_id": Sensibilidade.INTERNO,
        "orgao_cnpj": Sensibilidade.PUBLICO,
        "ente_id": Sensibilidade.INTERNO,
        "unidade_gestora_id": Sensibilidade.INTERNO,
        "uf": Sensibilidade.PUBLICO,
        "municipio_codigo_ibge": Sensibilidade.PUBLICO,
        "ano": Sensibilidade.PUBLICO,
        "sequencial": Sensibilidade.PUBLICO,
        "numero": Sensibilidade.PUBLICO,
        "processo": Sensibilidade.PUBLICO,
        "tipo_instrumento": Sensibilidade.PUBLICO,
        "categoria": Sensibilidade.PUBLICO,
        "fornecedor_id": Sensibilidade.INTERNO,
        "fornecedor_documento": Sensibilidade.SENSIVEL,
        "fornecedor_tipo_pessoa": Sensibilidade.PUBLICO,
        "fornecedor_nome": Sensibilidade.PUBLICO,
        "objeto": Sensibilidade.PUBLICO,
        "valor_inicial": Sensibilidade.PUBLICO,
        "valor_global": Sensibilidade.PUBLICO,
        "valor_parcela": Sensibilidade.PUBLICO,
        "numero_parcelas": Sensibilidade.PUBLICO,
        "valor_acumulado": Sensibilidade.PUBLICO,
        "data_assinatura": Sensibilidade.PUBLICO,
        "vigencia_inicio": Sensibilidade.PUBLICO,
        "vigencia_fim": Sensibilidade.PUBLICO,
        "publicado_em": Sensibilidade.PUBLICO,
        "atualizado_em": Sensibilidade.PUBLICO,
        "numero_retificacao": Sensibilidade.PUBLICO,
        "receita": Sensibilidade.PUBLICO,
        "fruto_adesao": Sensibilidade.PUBLICO,
        "sistema_origem": Sensibilidade.PUBLICO,
    }

    id: str
    chave_origem: str
    processo_chave_origem: str | None
    processo_id: str | None
    ata_chave_origem: str | None
    orgao_id: str
    orgao_cnpj: str
    ente_id: str | None
    unidade_gestora_id: str | None
    uf: str | None
    municipio_codigo_ibge: str | None
    ano: int
    sequencial: int
    numero: str | None
    processo: str | None
    tipo_instrumento: str | None
    categoria: str | None
    fornecedor_id: str | None
    fornecedor_documento: str | None
    fornecedor_tipo_pessoa: TipoPessoa | None
    fornecedor_nome: str | None
    objeto: str
    valor_inicial: Decimal | None
    valor_global: Decimal | None
    valor_parcela: Decimal | None
    numero_parcelas: int | None
    valor_acumulado: Decimal | None
    data_assinatura: date | None
    vigencia_inicio: date | None
    vigencia_fim: date | None
    publicado_em: datetime | None
    atualizado_em: datetime | None
    numero_retificacao: int | None
    receita: bool | None
    fruto_adesao: bool | None
    sistema_origem: str | None
    fonte_id: str | None = None
    documento_fonte_id: str | None = None
    marcacoes_qualidade: list[str] = field(default_factory=list)


@dataclass
class AtaRegistroPreco(RegistroCanonico):
    """Ata de registro de preços. Chave: numeroControlePNCPAta. Base da regra A-03."""

    ENTIDADE: ClassVar[str] = "ata_registro_preco"
    SENSIBILIDADE: ClassVar[dict[str, Sensibilidade]] = {
        "processo_chave_origem": Sensibilidade.PUBLICO,
        "processo_id": Sensibilidade.INTERNO,
        "orgao_cnpj": Sensibilidade.PUBLICO,
        "orgao_nome": Sensibilidade.PUBLICO,
        "unidade_codigo": Sensibilidade.PUBLICO,
        "unidade_nome": Sensibilidade.PUBLICO,
        "numero": Sensibilidade.PUBLICO,
        "ano": Sensibilidade.PUBLICO,
        "objeto": Sensibilidade.PUBLICO,
        "data_assinatura": Sensibilidade.PUBLICO,
        "vigencia_inicio": Sensibilidade.PUBLICO,
        "vigencia_fim": Sensibilidade.PUBLICO,
        "cancelada": Sensibilidade.PUBLICO,
        "data_cancelamento": Sensibilidade.PUBLICO,
        "sistema_origem": Sensibilidade.PUBLICO,
    }

    id: str
    chave_origem: str
    processo_chave_origem: str | None
    processo_id: str | None
    orgao_cnpj: str
    orgao_nome: str | None
    unidade_codigo: str | None
    unidade_nome: str | None
    numero: str | None
    ano: int | None
    objeto: str | None
    data_assinatura: date | None
    vigencia_inicio: date | None
    vigencia_fim: date | None
    cancelada: bool
    data_cancelamento: date | None
    sistema_origem: str | None
    fonte_id: str | None = None
    documento_fonte_id: str | None = None
    marcacoes_qualidade: list[str] = field(default_factory=list)


@dataclass
class EntregaSiconfi(RegistroCanonico):
    """Uma entrega declarada ao SICONFI (extrato de entregas do Tesouro).

    Chave: ente + instituição + entregável + exercício + período. É fato
    publicado pelo Tesouro sobre o ente, e é a base objetiva da família I: o
    que não aparece aqui, para um ente com coleta bem-sucedida, não foi
    entregue.
    """

    ENTIDADE: ClassVar[str] = "entrega_siconfi"
    SENSIBILIDADE: ClassVar[dict[str, Sensibilidade]] = {
        "ente_id": Sensibilidade.INTERNO,
        "ente_codigo_ibge": Sensibilidade.PUBLICO,
        "exercicio": Sensibilidade.PUBLICO,
        "instituicao": Sensibilidade.PUBLICO,
        "entregavel": Sensibilidade.PUBLICO,
        "periodo": Sensibilidade.PUBLICO,
        "periodicidade": Sensibilidade.PUBLICO,
        "status_relatorio": Sensibilidade.PUBLICO,
        "entregue_em": Sensibilidade.PUBLICO,
        "forma_envio": Sensibilidade.PUBLICO,
        "tipo_relatorio": Sensibilidade.PUBLICO,
        "populacao_declarada": Sensibilidade.PUBLICO,
    }

    id: str
    ente_id: str
    ente_codigo_ibge: str
    exercicio: int
    instituicao: str
    entregavel: str
    periodo: int
    periodicidade: str | None        # M, B, Q, S, A
    status_relatorio: str | None     # HO homologado, RE retificado (siglas do Tesouro)
    entregue_em: datetime | None
    forma_envio: str | None
    tipo_relatorio: str | None
    populacao_declarada: int | None
    chave_origem: str | None = None
    fonte_id: str | None = None
    documento_fonte_id: str | None = None
    marcacoes_qualidade: list[str] = field(default_factory=list)


@dataclass
class Sancao(RegistroCanonico):
    """Sanção ou impedimento de pessoa física ou jurídica num cadastro da CGU (CEIS, CNEP ou CEPIM).

    Chave: cadastro + código da sanção no Portal (no CEPIM, que não tem código, CNPJ + convênio). É fato
    publicado pela CGU, como veio: o Lumen não decide se a sanção alcança uma contratação; isso é a regra
    J-01 da Fase 2, com a abrangência, o órgão sancionador e as datas daqui (ADR-030).

    Cada arquivo do Portal é o retrato do cadastro inteiro num dia. ``data_referencia`` é o dia do retrato:
    uma sanção que sai do cadastro deixa de aparecer nos retratos seguintes, e o que está no cadastro hoje é
    o que tem a ``data_referencia`` mais recente. ``fornecedor_id`` é o mesmo id do fornecedor no PNCP
    (CNPJ; CPF mascarado mais nome), o que permite cruzar as duas fontes sem o CPF inteiro.

    O CEPIM não publica datas: ``data_inicio`` e ``data_fim`` ficam nulas, e o impedimento vale enquanto a
    entidade estiver no retrato. Observações livres, nome fantasia e o nome informado pelo órgão ficam no
    bronze e não vêm para cá (minimização, DOC-08, seção 5).
    """

    ENTIDADE: ClassVar[str] = "sancao"
    SENSIBILIDADE: ClassVar[dict[str, Sensibilidade]] = {
        "cadastro": Sensibilidade.PUBLICO,
        "data_referencia": Sensibilidade.PUBLICO,
        "fornecedor_id": Sensibilidade.INTERNO,
        "documento": Sensibilidade.SENSIVEL,
        "tipo_pessoa": Sensibilidade.PUBLICO,
        "nome": Sensibilidade.PUBLICO,
        "razao_social_receita": Sensibilidade.PUBLICO,
        "categoria": Sensibilidade.PUBLICO,
        "numero_processo": Sensibilidade.PUBLICO,
        "numero_convenio": Sensibilidade.PUBLICO,
        "valor_multa": Sensibilidade.PUBLICO,
        "data_inicio": Sensibilidade.PUBLICO,
        "data_fim": Sensibilidade.PUBLICO,
        "data_publicacao": Sensibilidade.PUBLICO,
        "data_transito_julgado": Sensibilidade.PUBLICO,
        "data_origem_informacao": Sensibilidade.PUBLICO,
        "meio_publicacao": Sensibilidade.PUBLICO,
        "abrangencia": Sensibilidade.PUBLICO,
        "orgao_sancionador": Sensibilidade.PUBLICO,
        "uf_orgao_sancionador": Sensibilidade.PUBLICO,
        "esfera_orgao_sancionador": Sensibilidade.PUBLICO,
        "fundamentacao_legal": Sensibilidade.PUBLICO,
        "origem_informacao": Sensibilidade.PUBLICO,
    }

    id: str
    cadastro: CadastroSancao
    data_referencia: date | None
    fornecedor_id: str | None
    documento: str | None            # CNPJ inteiro; CPF sempre mascarado (***.456.789-**)
    tipo_pessoa: TipoPessoa | None
    nome: str
    razao_social_receita: str | None
    categoria: str | None            # CEIS e CNEP: categoria da sanção; CEPIM: motivo do impedimento
    numero_processo: str | None
    numero_convenio: str | None      # só no CEPIM
    valor_multa: Decimal | None      # só no CNEP
    data_inicio: date | None
    data_fim: date | None            # nula: sem prazo determinado ou não publicada
    data_publicacao: date | None
    data_transito_julgado: date | None
    data_origem_informacao: date | None
    meio_publicacao: str | None
    abrangencia: str | None
    orgao_sancionador: str | None    # no CEPIM, o órgão concedente
    uf_orgao_sancionador: str | None
    esfera_orgao_sancionador: Esfera | None
    fundamentacao_legal: str | None
    origem_informacao: str | None
    chave_origem: str | None = None
    fonte_id: str | None = None
    documento_fonte_id: str | None = None
    marcacoes_qualidade: list[str] = field(default_factory=list)


ENTIDADES_FATO: tuple[type[RegistroCanonico], ...] = (
    EnteFederativo,
    Orgao,
    UnidadeGestora,
    AmparoLegal,
    ProcessoContratacao,
    ItemContratacao,
    ResultadoItem,
    Contrato,
    AtaRegistroPreco,
    EntregaSiconfi,
    Sancao,
)
