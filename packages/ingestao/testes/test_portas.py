"""Testes da porta FonteDados e do laço de coleta.

A fonte falsa abaixo existe para provar que a porta é implementável por um
adaptador comum — e para exercitar os modos de falha que um adaptador real
vai encontrar.
"""

from datetime import date
from typing import Iterator

import pytest

from lumen_ingestao.bronze import ArmazemBronzeLocal, ArtefatoBruto, IntegridadeViolada
from lumen_ingestao.portas import (
    AvaliacaoConformidade,
    CapacidadesFonte,
    FonteDados,
    Janela,
    Periodicidade,
    ReferenciaArtefato,
    RelatorioConformidade,
    ResultadoCriterio,
    coletar_janela,
)


class FonteFalsa:
    """Adaptador mínimo que implementa a porta."""

    fonte_id = "fonte_falsa"

    def __init__(self, documentos: dict[str, tuple[int, bytes]], quebra_em: set[str] = frozenset()):
        self.documentos = documentos
        self.quebra_em = quebra_em

    def descrever_capacidades(self) -> CapacidadesFonte:
        return CapacidadesFonte(
            objetos=frozenset({"Contrato"}),
            periodicidade=Periodicidade.DIARIA,
            suporta_incremental=True,
            limite_requisicoes_por_minuto=20,
        )

    def listar(self, janela: Janela) -> Iterator[ReferenciaArtefato]:
        for url in self.documentos:
            yield ReferenciaArtefato(url=url, objeto="Contrato")

    def baixar(self, ref: ReferenciaArtefato) -> ArtefatoBruto:
        if ref.url in self.quebra_em:
            raise ConnectionError("conexão recusada")
        status, corpo = self.documentos[ref.url]
        return ArtefatoBruto(
            conteudo=corpo, fonte_id=self.fonte_id, url_solicitada=ref.url,
            url_efetiva=ref.url, status_http=status, tipo_midia="application/json",
        )

    def reportar_conformidade(self) -> RelatorioConformidade:
        return RelatorioConformidade(fonte_id=self.fonte_id, avaliacoes=(
            AvaliacaoConformidade(
                criterio="publica amparo legal da contratação",
                dispositivo_legal="Lei 14.133/2021, art. 174",
                resultado=ResultadoCriterio.NAO_CUMPRE,
            ),
        ))


JANELA = Janela(date(2026, 9, 1), date(2026, 9, 30))


@pytest.fixture
def armazem(tmp_path):
    return ArmazemBronzeLocal(tmp_path / "bronze")


def test_fonte_falsa_implementa_a_porta():
    assert isinstance(FonteFalsa({}), FonteDados)


def test_coleta_preserva_tudo_o_que_foi_listado(armazem):
    fonte = FonteFalsa({
        "https://x.gov.br/c/1": (200, b'{"n": 1}'),
        "https://x.gov.br/c/2": (200, b'{"n": 2}'),
    })
    resumo = coletar_janela(fonte, JANELA, armazem)
    assert resumo.listados == 2
    assert len(resumo.guardados) == 2
    assert resumo.falhas == []
    assert resumo.conteudos_novos == 2


def test_falha_em_um_artefato_nao_interrompe_os_demais(armazem):
    fonte = FonteFalsa(
        {"https://x.gov.br/ok": (200, b"ok"), "https://x.gov.br/quebra": (200, b"x"),
         "https://x.gov.br/ok2": (200, b"ok2")},
        quebra_em={"https://x.gov.br/quebra"},
    )
    resumo = coletar_janela(fonte, JANELA, armazem)
    assert len(resumo.guardados) == 2
    assert resumo.falhas == [("https://x.gov.br/quebra", "ConnectionError: conexão recusada")]


def test_resposta_de_erro_e_contada_como_prova_e_nao_como_falha(armazem):
    """Princípio P5: 404 datado é achado, não falha de coleta."""
    fonte = FonteFalsa({"https://x.gov.br/sumiu": (404, b"nao encontrado")})
    resumo = coletar_janela(fonte, JANELA, armazem)
    assert resumo.falhas == []
    assert resumo.respostas_de_erro == 1


def test_recoleta_sem_mudanca_e_registrada_mas_nao_conta_como_novo(armazem):
    fonte = FonteFalsa({"https://x.gov.br/c/1": (200, b"igual")})
    coletar_janela(fonte, JANELA, armazem)
    segunda = coletar_janela(fonte, JANELA, armazem)
    assert len(segunda.guardados) == 1
    assert segunda.conteudos_novos == 0
    assert segunda.guardados[0].versao == 2


def test_prova_corrompida_interrompe_a_coleta(armazem, tmp_path):
    """Incidente no armazém não pode ser tratado como falha de um artefato."""
    import os, stat
    fonte = FonteFalsa({"https://x.gov.br/c/1": (200, b"conteudo")})
    registro = coletar_janela(fonte, JANELA, armazem).guardados[0]
    objeto = (tmp_path / "bronze" / "objetos" / registro.sha256[:2]
              / registro.sha256[2:4] / registro.sha256)
    os.chmod(objeto, stat.S_IRUSR | stat.S_IWUSR)
    objeto.write_bytes(b"corrompido")

    with pytest.raises(IntegridadeViolada):
        coletar_janela(fonte, JANELA, armazem)


def test_adaptador_que_troca_o_fonte_id_e_rejeitado(armazem):
    class Trapaceira(FonteFalsa):
        def baixar(self, ref):
            art = super().baixar(ref)
            return ArtefatoBruto(**{**art.__dict__, "fonte_id": "outra_fonte"})

    resumo = coletar_janela(Trapaceira({"https://x.gov.br/c": (200, b"x")}), JANELA, armazem)
    assert resumo.guardados == []
    assert "outra_fonte" in resumo.falhas[0][1]


def test_falha_ao_listar_e_propagada(armazem):
    """Sem listagem não se sabe o que faltou; fingir sucesso esconderia a falha."""
    class ListagemQuebrada(FonteFalsa):
        def listar(self, janela):
            raise TimeoutError("fonte fora do ar")
            yield  # pragma: no cover

    with pytest.raises(TimeoutError):
        coletar_janela(ListagemQuebrada({}), JANELA, armazem)


# --------------------------------------------------------------------------
# Tipos da porta
# --------------------------------------------------------------------------

def test_janela_invertida_e_recusada():
    with pytest.raises(ValueError):
        Janela(date(2026, 9, 30), date(2026, 9, 1))


def test_janela_conta_dias_inclusive():
    assert Janela(date(2026, 9, 1), date(2026, 9, 30)).dias == 30
    assert Janela(date(2026, 9, 1), date(2026, 9, 1)).dias == 1


def test_capacidades_exigem_objeto_e_limite_de_taxa():
    with pytest.raises(ValueError):
        CapacidadesFonte(objetos=frozenset(), periodicidade=Periodicidade.DIARIA,
                         suporta_incremental=True, limite_requisicoes_por_minuto=10)
    with pytest.raises(ValueError, match="P6"):
        CapacidadesFonte(objetos=frozenset({"Contrato"}), periodicidade=Periodicidade.DIARIA,
                         suporta_incremental=True, limite_requisicoes_por_minuto=0)


def test_indeterminado_exige_motivo():
    """RF-CF-07: não atribuir ao ente uma falha que pode ser nossa."""
    with pytest.raises(ValueError, match="motivo"):
        AvaliacaoConformidade("publica contratos", "LC 131/2009", ResultadoCriterio.INDETERMINADO)
    ok = AvaliacaoConformidade("publica contratos", "LC 131/2009", ResultadoCriterio.INDETERMINADO,
                               motivo_indeterminado="portal fora do ar em todas as tentativas da janela")
    assert ok.motivo_indeterminado


def test_motivo_so_cabe_no_indeterminado():
    with pytest.raises(ValueError):
        AvaliacaoConformidade("x", "LC 131/2009", ResultadoCriterio.NAO_CUMPRE,
                              motivo_indeterminado="nao deveria estar aqui")


def test_avaliacao_exige_dispositivo_legal():
    with pytest.raises(ValueError, match="RF-CF-06"):
        AvaliacaoConformidade("publica contratos", "  ", ResultadoCriterio.NAO_CUMPRE)


def test_relatorio_de_conformidade_da_fonte():
    relatorio = FonteFalsa({}).reportar_conformidade()
    assert relatorio.avaliacoes[0].resultado is ResultadoCriterio.NAO_CUMPRE
    assert relatorio.avaliado_em.tzinfo is not None
