"""Avaliação das entregas obrigatórias ao SICONFI (família I, RF-CF-01 e RF-CF-02).

É a avaliação mais objetiva do projeto: compara o que o ente entregou, segundo
o extrato do próprio Tesouro, com o que a LC 101/2000 manda entregar, no prazo
que ela fixa. Não há estatística nem interpretação.

Três resultados possíveis por obrigação e período, e um quarto que protege o
ente quando a dúvida é nossa:

``cumpre``                 entregue dentro do prazo
``cumpre_parcialmente``    entregue, mas depois do prazo
``nao_cumpre``             não consta no extrato e o prazo já venceu
``indeterminado``          a coleta do extrato falhou, ou o prazo ainda não
                           venceu: não se atribui nada ao ente (RF-CF-07)

Os prazos vêm de ``parametros_legais`` pela data de referência do envio,
nunca fixados aqui (DOC-09, seção 1.3).

Limites conhecidos desta versão, registrados para a revisão metodológica:

- A opção semestral do art. 63 da LRF (municípios com menos de 50 mil
  habitantes) é reconhecida pela periodicidade que o próprio ente declarou no
  extrato. Um município que optou pelo semestral e não entregou nada não tem
  como ser distinguido de um que é quadrimestral; nesse caso a avaliação usa
  a periodicidade padrão e registra a ressalva no motivo.
- Entregas retificadas aparecem com a data da retificação. Quando só existe a
  versão retificada, a data de entrega original não é conhecida e a avaliação
  de prazo fica indeterminada em vez de supor atraso.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Iterable

from lumen_canonico.fato import EntregaSiconfi, Esfera
from lumen_deteccao.parametros_legais import ParametroIndisponivel, ParametrosLegais
from lumen_ingestao.portas import AvaliacaoConformidade, ResultadoCriterio
from lumen_normalizacao.transformacoes import chave_texto

DISPOSITIVO_DCA = "LC 101/2000, art. 51, § 1º"
DISPOSITIVO_RREO = "LC 101/2000, art. 52"
DISPOSITIVO_RGF = "LC 101/2000, art. 55, § 2º"

# Entregáveis como o Tesouro os nomeia no extrato (comparados sem acento e caixa)
_DCA = ("balanco anual (dca)",)
_RREO = ("relatorio resumido de execucao orcamentaria",
         "relatorio resumido de execucao orcamentaria simplificado")
_RGF = ("relatorio de gestao fiscal", "relatorio de gestao fiscal simplificado")

STATUS_RETIFICADO = "RE"


@dataclass(frozen=True)
class AvaliacaoEntrega:
    """Resultado de uma obrigação num período, pronto para a tabela ``conformidade``."""

    ente_codigo_ibge: str
    criterio: str
    periodo_referencia: str
    avaliacao: AvaliacaoConformidade
    prazo: date | None
    entregue_em: datetime | None


def _do_tipo(entregas: Iterable[EntregaSiconfi], nomes: tuple[str, ...], instituicao_contem: str | None = None):
    """Filtra as entregas cujo entregável está em ``nomes``, comparado na forma de ``chave_texto``.

    ``instituicao_contem``, quando informado (já na forma de ``chave_texto``), restringe às entregas cuja
    instituição contém o trecho: é o que separa o RGF de cada Poder.
    """
    for e in entregas:
        if chave_texto(e.entregavel) in nomes:
            if instituicao_contem and instituicao_contem not in chave_texto(e.instituicao):
                continue
            yield e


def _fim_do_bimestre(exercicio: int, periodo: int) -> date:
    """Último dia do bimestre ``periodo`` (1 a 6) do exercício, data de onde corre o prazo do RREO."""
    mes = periodo * 2
    return date(exercicio, mes, calendar.monthrange(exercicio, mes)[1])


def _fim_do_periodo(exercicio: int, periodo: int, meses: int) -> date:
    """Último dia do período de ``meses`` meses (4 no quadrimestre, 6 no semestre), de onde corre o prazo do RGF."""
    mes = periodo * meses
    return date(exercicio, mes, calendar.monthrange(exercicio, mes)[1])


def _decidir(ente: str, criterio: str, periodo_ref: str, dispositivo: str, prazo: date | None,
             candidatas: list[EntregaSiconfi], hoje: date, coleta_ok: bool) -> AvaliacaoEntrega:
    """Aplica a decisão comum a todas as obrigações e monta a ``AvaliacaoEntrega``.

    A ordem protege o ente: coleta que falhou ou prazo sem parâmetro dão indeterminado antes de qualquer
    outra conclusão (RF-CF-07). Havendo entrega, vale a data mais antiga das versões originais (as
    retificadas só contam na falta delas): até o prazo, cumpre; depois, cumpre parcialmente, salvo quando só
    existe versão retificada, caso em que o atraso não pode ser afirmado e o resultado é indeterminado. Sem
    entrega, prazo ainda aberto dá indeterminado e prazo vencido dá não cumpre.
    """
    def montar(resultado: ResultadoCriterio, motivo: str | None = None,
               quando: datetime | None = None) -> AvaliacaoEntrega:
        return AvaliacaoEntrega(
            ente_codigo_ibge=ente, criterio=criterio, periodo_referencia=periodo_ref,
            avaliacao=AvaliacaoConformidade(criterio=criterio, dispositivo_legal=dispositivo,
                                            resultado=resultado, motivo_indeterminado=motivo),
            prazo=prazo, entregue_em=quando,
        )

    if not coleta_ok:
        return montar(ResultadoCriterio.INDETERMINADO,
                      "a coleta do extrato de entregas falhou para este ente; "
                      "a ausência não pode ser atribuída a ele")
    if prazo is None:
        return montar(ResultadoCriterio.INDETERMINADO, "prazo legal sem parâmetro conferido para a data")
    if candidatas:
        originais = [c for c in candidatas if (c.status_relatorio or "").upper() != STATUS_RETIFICADO]
        base = originais or candidatas
        com_data = [c for c in base if c.entregue_em is not None]
        if not com_data:
            return montar(ResultadoCriterio.INDETERMINADO, "entrega registrada sem data no extrato")
        primeira = min(com_data, key=lambda c: c.entregue_em)
        if primeira.entregue_em.date() <= prazo:
            return montar(ResultadoCriterio.CUMPRE, quando=primeira.entregue_em)
        if not originais:
            return montar(ResultadoCriterio.INDETERMINADO,
                          "só consta a versão retificada; a data da entrega original não é conhecida",
                          quando=primeira.entregue_em)
        return montar(ResultadoCriterio.CUMPRE_PARCIALMENTE, quando=primeira.entregue_em)
    if hoje <= prazo:
        return montar(ResultadoCriterio.INDETERMINADO, f"prazo legal ainda não venceu ({prazo.isoformat()})")
    return montar(ResultadoCriterio.NAO_CUMPRE)


def avaliar_dca(ente_codigo_ibge: str, esfera: Esfera, exercicio: int, entregas: Iterable[EntregaSiconfi],
                params: ParametrosLegais, *, hoje: date, coleta_ok: bool = True) -> AvaliacaoEntrega:
    """Contas anuais do exercício, com o prazo do art. 51 vigente no ano do envio."""
    referencia = date(exercicio + 1, 1, 1)
    tipo = "municipio" if esfera is Esfera.MUNICIPAL else "estado"
    try:
        mes = int(params.obter(f"prazo_contas_anuais_{tipo}_mes", referencia).valor)
        dia = int(params.obter(f"prazo_contas_anuais_{tipo}_dia", referencia).valor)
        prazo: date | None = date(exercicio + 1, mes, dia)
    except ParametroIndisponivel:
        prazo = None
    candidatas = [e for e in _do_tipo(entregas, _DCA) if e.exercicio == exercicio]
    return _decidir(ente_codigo_ibge, "dca_entregue_no_prazo", str(exercicio), DISPOSITIVO_DCA,
                    prazo, candidatas, hoje, coleta_ok)


def avaliar_rreo(ente_codigo_ibge: str, exercicio: int, periodo: int, entregas: Iterable[EntregaSiconfi],
                 params: ParametrosLegais, *, hoje: date, coleta_ok: bool = True) -> AvaliacaoEntrega:
    """RREO do bimestre (1 a 6), versão completa ou simplificada."""
    if not 1 <= periodo <= 6:
        raise ValueError("o RREO é bimestral: período de 1 a 6")
    fim = _fim_do_bimestre(exercicio, periodo)
    try:
        prazo: date | None = fim + timedelta(days=int(params.obter("prazo_rreo_dias", fim).valor))
    except ParametroIndisponivel:
        prazo = None
    candidatas = [e for e in _do_tipo(entregas, _RREO)
                  if e.exercicio == exercicio and e.periodo == periodo]
    return _decidir(ente_codigo_ibge, "rreo_entregue_no_prazo", f"{exercicio}-B{periodo}",
                    DISPOSITIVO_RREO, prazo, candidatas, hoje, coleta_ok)


def periodicidade_rgf_declarada(entregas: Iterable[EntregaSiconfi], exercicio: int) -> str | None:
    """``S`` se o ente declarou RGF semestral no exercício, ``Q`` se quadrimestral."""
    vistas = {(e.periodicidade or "").upper() for e in _do_tipo(entregas, _RGF) if e.exercicio == exercicio}
    if "S" in vistas:
        return "S"
    if "Q" in vistas:
        return "Q"
    return None


def avaliar_rgf(ente_codigo_ibge: str, exercicio: int, periodo: int, entregas: list[EntregaSiconfi],
                params: ParametrosLegais, *, hoje: date, coleta_ok: bool = True,
                instituicao_contem: str | None = None) -> AvaliacaoEntrega:
    """RGF do período, na periodicidade declarada pelo ente (quadrimestral por padrão).

    ``instituicao_contem`` restringe a um Poder ("prefeitura", "camara"): o
    RGF é emitido por cada Poder (LRF, art. 54), e cada um tem sua obrigação.
    """
    declarada = periodicidade_rgf_declarada(entregas, exercicio)
    periodicidade = declarada or "Q"
    meses = 6 if periodicidade == "S" else 4
    maximo = 12 // meses
    if not 1 <= periodo <= maximo:
        raise ValueError(f"RGF {'semestral' if meses == 6 else 'quadrimestral'}: período de 1 a {maximo}")
    fim = _fim_do_periodo(exercicio, periodo, meses)
    try:
        prazo: date | None = fim + timedelta(days=int(params.obter("prazo_rgf_dias", fim).valor))
    except ParametroIndisponivel:
        prazo = None
    filtro = chave_texto(instituicao_contem) if instituicao_contem else None
    candidatas = [e for e in _do_tipo(entregas, _RGF, filtro)
                  if e.exercicio == exercicio and e.periodo == periodo]
    rotulo = "S" if periodicidade == "S" else "Q"
    resultado = _decidir(ente_codigo_ibge, "rgf_entregue_no_prazo", f"{exercicio}-{rotulo}{periodo}",
                         DISPOSITIVO_RGF, prazo, candidatas, hoje, coleta_ok)
    if declarada is None and resultado.avaliacao.resultado is ResultadoCriterio.NAO_CUMPRE:
        # Sem nenhuma entrega no exercício, não se sabe se o ente optou pelo
        # semestral (art. 63). O período quadrimestral é o padrão da lei, mas
        # a conclusão fica registrada como indeterminada, não como ausência.
        return AvaliacaoEntrega(
            ente_codigo_ibge=resultado.ente_codigo_ibge, criterio=resultado.criterio,
            periodo_referencia=resultado.periodo_referencia,
            avaliacao=AvaliacaoConformidade(
                criterio=resultado.criterio, dispositivo_legal=DISPOSITIVO_RGF,
                resultado=ResultadoCriterio.INDETERMINADO,
                motivo_indeterminado="nenhum RGF no exercício: a periodicidade escolhida pelo "
                                     "ente (art. 63 da LRF) não é conhecida"),
            prazo=resultado.prazo, entregue_em=None,
        )
    return resultado


def ausentes(cadastro: Iterable[str], entregas: Iterable[EntregaSiconfi], *, exercicio: int,
             coletados: set[str]) -> dict[str, list[str]]:
    """Lista de ausentes por entregável, a partir do cadastro de entes.

    Só entra na lista quem teve o extrato coletado com sucesso (``coletados``):
    para os demais, a ausência seria do Lumen, não do ente. Devolve
    ``{"dca": [códigos], "rreo": [...], "rgf": [...]}`` — "ausente" aqui
    significa "nenhuma entrega daquele tipo no exercício".
    """
    entregas = [e for e in entregas if e.exercicio == exercicio]
    tem = {
        "dca": {e.ente_codigo_ibge for e in _do_tipo(entregas, _DCA)},
        "rreo": {e.ente_codigo_ibge for e in _do_tipo(entregas, _RREO)},
        "rgf": {e.ente_codigo_ibge for e in _do_tipo(entregas, _RGF)},
    }
    lista = sorted(c for c in cadastro if c in coletados)
    return {tipo: [c for c in lista if c not in presentes] for tipo, presentes in tem.items()}
