"""Testes da máquina de estados do indício.

A regra mais importante do projeto está aqui: um indício grave não chega ao
público sem evidência e sem dois revisores humanos distintos. Estes testes
são a garantia de que isso continua verdade depois de qualquer refatoração.
"""

from decimal import Decimal
from pathlib import Path

import pytest

from lumen_canonico import rotulos
from lumen_canonico.indicio import (
    AUTOR_SISTEMA,
    ESTADOS_TERMINAIS,
    TRANSICOES,
    Estado,
    Indicio,
    Severidade,
    TransicaoInvalida,
    classificar_severidade,
)


def novo(score="0.60", evidencia=True, **extra) -> Indicio:
    base = dict(
        indicio_id="ind-1",
        regra_codigo="B-01",
        regra_versao=1,
        ente_id="3550308",
        alvo_tipo="fornecedor_no_ente",
        alvo_id="forn-1",
        score=Decimal(score),
        parametros_aplicados={"janela_dias": 180, "similaridade_minima": "0.80"},
        valores_observados={"soma": "218400.00", "limite_aplicado": "65492.11", "contratacoes": 14},
        explicacao="Foram identificadas 14 contratações diretas com o mesmo fornecedor.",
        evidencias=("reg-abc",) if evidencia else (),
    )
    base.update(extra)
    return Indicio(**base)


# --------------------------------------------------------------------------
# Severidade
# --------------------------------------------------------------------------

@pytest.mark.parametrize("score,esperada", [
    ("0", Severidade.BAIXA),
    ("0.44", Severidade.BAIXA),
    ("0.4499", Severidade.BAIXA),
    ("0.45", Severidade.MEDIA),
    ("0.70", Severidade.MEDIA),
    ("0.7001", Severidade.ALTA),
    ("1", Severidade.ALTA),
])
def test_limiares_de_severidade_do_doc07(score, esperada):
    assert classificar_severidade(Decimal(score)) is esperada


@pytest.mark.parametrize("score", ["-0.01", "1.01", "7"])
def test_score_fora_do_intervalo_e_recusado(score):
    with pytest.raises(ValueError):
        novo(score=score)


def test_revisores_exigidos_por_severidade():
    assert Severidade.BAIXA.revisores_exigidos == 0
    assert Severidade.MEDIA.revisores_exigidos == 1
    assert Severidade.ALTA.revisores_exigidos == 2


# --------------------------------------------------------------------------
# Fluxo completo
# --------------------------------------------------------------------------

def test_fluxo_completo_de_severidade_media():
    ind = novo(score="0.60")
    ind.enviar_para_revisao()
    ind.aprovar("revisora.ana")
    ind.publicar("revisora.ana", "documento fonte confere com o que a regra leu")
    assert ind.estado is Estado.PUBLICADO
    assert ind.rotulo_publico == rotulos.ATIVIDADE_PARA_ANALISE

    ind.marcar_contestado("CT-2026-0001")
    assert ind.estado is Estado.CONTESTADO
    assert ind.protocolo_contestacao == "CT-2026-0001"

    ind.manter_com_resposta("revisora.ana", "contestação não afasta o que foi observado")
    ind.encerrar("revisora.ana", "TCE concluiu a análise")
    assert ind.terminal
    assert [t.para for t in ind.historico] == [
        Estado.EM_REVISAO, Estado.PUBLICADO, Estado.CONTESTADO,
        Estado.PUBLICADO_COM_RESPOSTA, Estado.ENCERRADO,
    ]


# --------------------------------------------------------------------------
# PUB-05: severidade alta exige dois revisores distintos
# --------------------------------------------------------------------------

def test_severidade_alta_com_um_revisor_nao_publica():
    ind = novo(score="0.85")
    ind.enviar_para_revisao()
    ind.aprovar("revisor.a")
    with pytest.raises(TransicaoInvalida, match="2 revisor"):
        ind.publicar("revisor.a", "ok")
    assert ind.estado is Estado.EM_REVISAO


def test_mesmo_revisor_aprovando_duas_vezes_conta_uma():
    ind = novo(score="0.85")
    ind.enviar_para_revisao()
    ind.aprovar("revisor.a")
    ind.aprovar("revisor.a")
    ind.aprovar("  revisor.a  ")
    assert ind.aprovacoes == ("revisor.a",)
    with pytest.raises(TransicaoInvalida):
        ind.publicar("revisor.a", "ok")


def test_severidade_alta_com_dois_revisores_distintos_publica():
    ind = novo(score="0.85")
    ind.enviar_para_revisao()
    ind.aprovar("revisor.a")
    ind.aprovar("revisor.b")
    ind.publicar("revisor.b", "dupla revisão concluída")
    assert ind.estado is Estado.PUBLICADO


def test_sistema_nao_pode_aprovar():
    ind = novo()
    ind.enviar_para_revisao()
    with pytest.raises(TransicaoInvalida, match="humano"):
        ind.aprovar(AUTOR_SISTEMA)


def test_aprovar_fora_da_revisao_e_recusado():
    ind = novo()
    with pytest.raises(TransicaoInvalida):
        ind.aprovar("revisor.a")


# --------------------------------------------------------------------------
# RN-02: sem evidência não há indício publicável
# --------------------------------------------------------------------------

def test_publicar_sem_evidencia_e_recusado():
    ind = novo(evidencia=False)
    ind.enviar_para_revisao()
    ind.aprovar("revisor.a")
    with pytest.raises(TransicaoInvalida, match="evidência"):
        ind.publicar("revisor.a", "ok")


def test_evidencia_anexada_depois_libera_publicacao():
    ind = novo(evidencia=False)
    ind.enviar_para_revisao()
    ind.aprovar("revisor.a")
    ind.anexar_evidencia("reg-xyz")
    ind.publicar("revisor.a", "evidência anexada e conferida")
    assert ind.evidencias == ("reg-xyz",)


def test_evidencia_duplicada_nao_se_repete():
    ind = novo()
    ind.anexar_evidencia("reg-abc")
    assert ind.evidencias == ("reg-abc",)


# --------------------------------------------------------------------------
# Severidade baixa: só estatística
# --------------------------------------------------------------------------

def test_severidade_baixa_nao_entra_na_revisao():
    ind = novo(score="0.30")
    with pytest.raises(TransicaoInvalida, match="baixa"):
        ind.enviar_para_revisao()


def test_severidade_baixa_so_pode_ser_descartada():
    ind = novo(score="0.30")
    ind.descartar(AUTOR_SISTEMA, "score abaixo do limiar de publicação")
    assert ind.estado is Estado.DESCARTADO


# --------------------------------------------------------------------------
# Não dá para pular a revisão
# --------------------------------------------------------------------------

def test_detectado_nao_vai_direto_para_publicado():
    ind = novo(score="0.60")
    with pytest.raises(TransicaoInvalida):
        ind.publicar("alguem", "tentando pular a revisão")
    assert ind.estado is Estado.DETECTADO


def _forcar(ind: Indicio, estado: Estado) -> Indicio:
    ind.estado = estado
    return ind


@pytest.mark.parametrize("origem", list(Estado))
@pytest.mark.parametrize("destino", list(Estado))
def test_tabela_completa_de_transicoes(origem, destino):
    """Todo par (origem, destino) do diagrama do DOC-05: só o permitido passa."""
    ind = _forcar(novo(), origem)
    if destino in TRANSICOES[origem]:
        ind._transitar(destino, "revisor.a", "teste da tabela")
        assert ind.estado is destino
    else:
        with pytest.raises(TransicaoInvalida):
            ind._transitar(destino, "revisor.a", "teste da tabela")
        assert ind.estado is origem


def test_estados_terminais_do_diagrama():
    assert ESTADOS_TERMINAIS == {Estado.DESCARTADO, Estado.REMOVIDO, Estado.ENCERRADO}


# --------------------------------------------------------------------------
# RN-04: toda decisão registra autor e justificativa
# --------------------------------------------------------------------------

@pytest.mark.parametrize("autor,justificativa", [("", "motivo"), ("   ", "motivo"), ("ana", ""), ("ana", "  ")])
def test_decisao_sem_autor_ou_justificativa_e_recusada(autor, justificativa):
    ind = novo(score="0.30")
    with pytest.raises(TransicaoInvalida, match="RN-04"):
        ind.descartar(autor, justificativa)


def test_historico_registra_quem_decidiu_e_por_que():
    ind = novo(score="0.30")
    ind.descartar("analista.bruno", "objeto de catálogo mal classificado")
    t = ind.historico[-1]
    assert (t.de, t.para) == (Estado.DETECTADO, Estado.DESCARTADO)
    assert t.autor == "analista.bruno"
    assert t.justificativa == "objeto de catálogo mal classificado"
    assert t.em.endswith("+00:00")


# --------------------------------------------------------------------------
# Contestação e correção (DOC-08, seção 6)
# --------------------------------------------------------------------------

def _publicado(score="0.60") -> Indicio:
    ind = novo(score=score)
    ind.enviar_para_revisao()
    ind.aprovar("revisor.a")
    if Decimal(score) > Decimal("0.70"):
        ind.aprovar("revisor.b")
    ind.publicar("revisor.a", "conferido")
    return ind


def test_contestacao_e_marcada_pelo_sistema_sem_analise_de_merito():
    ind = _publicado()
    ind.marcar_contestado("CT-9")
    assert ind.historico[-1].autor == AUTOR_SISTEMA
    assert ind.rotulo_publico == rotulos.ROTULO_CONTESTADO


def test_contestacao_exige_protocolo():
    ind = _publicado()
    with pytest.raises(TransicaoInvalida, match="protocolo"):
        ind.marcar_contestado("  ")


def test_retificacao_e_republicacao():
    ind = _publicado()
    ind.marcar_contestado("CT-10")
    ind.retificar("revisor.a", "erro de extração no PDF comprovado")
    assert ind.rotulo_publico == rotulos.ROTULO_RETIFICADO
    ind.republicar_retificado("revisor.a", "recalculado após correção")
    assert ind.estado is Estado.PUBLICADO


def test_remocao_quando_a_fonte_publicou_dado_errado():
    ind = _publicado()
    ind.marcar_contestado("CT-11")
    ind.remover("revisor.a", "o próprio ente publicou valor com casas decimais trocadas")
    assert ind.terminal
    assert ind.rotulo_publico == rotulos.ROTULO_REMOVIDO


def test_indicio_encerrado_nao_recebe_evidencia():
    ind = _publicado()
    ind.encerrar("revisor.a", "análise concluída")
    with pytest.raises(TransicaoInvalida):
        ind.anexar_evidencia("reg-novo")


# --------------------------------------------------------------------------
# Visibilidade pública
# --------------------------------------------------------------------------

@pytest.mark.parametrize("estado", [Estado.DETECTADO, Estado.EM_REVISAO,
                                    Estado.AGUARDANDO_DADO, Estado.DESCARTADO])
def test_estados_internos_nao_sao_publicos(estado):
    ind = _forcar(novo(), estado)
    assert ind.visivel_ao_publico is False
    assert ind.rotulo_publico is None


def test_todo_rotulo_publico_comeca_pela_atividade_ou_nota_de_remocao():
    for estado in Estado:
        rotulo = _forcar(novo(), estado).rotulo_publico
        if rotulo is not None:
            assert rotulo.startswith(("Atividade para análise", "Registro removido"))


# --------------------------------------------------------------------------
# Criação
# --------------------------------------------------------------------------

def test_indicio_exige_regra_e_versao():
    with pytest.raises(ValueError, match="RF-DE-02"):
        novo(regra_versao=0)


def test_indicio_exige_valores_observados():
    with pytest.raises(ValueError, match="RF-DE-03"):
        novo(valores_observados={})


# --------------------------------------------------------------------------
# Os rótulos públicos passam no verificador de vocabulário
# --------------------------------------------------------------------------

def test_rotulos_publicos_respeitam_o_vocabulario_controlado():
    from lint_vocabulario import Vocabulario

    arquivo = Path(rotulos.__file__)
    assert Vocabulario.carregar().verificar_arquivo(arquivo) == []
