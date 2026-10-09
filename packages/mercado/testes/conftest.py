"""Apoio dos testes da referência de mercado: configuração, silver e bronze de mentira em diretório temporário.

Os processos, itens e resultados da silver são montados aqui com as classes canônicas, com os campos que
a normalização do PNCP produz. Os testes recebem as funções pela fixture ``apoio`` (o modo de importação da
suíte não deixa um teste importar o ``conftest`` vizinho).
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from lumen_canonico.fato import EnteFederativo, Esfera, ItemContratacao, ProcessoContratacao, ResultadoItem
from lumen_canonico.identidade import id_canonico
from lumen_ingestao.bronze import ArmazemBronzeLocal, ArtefatoBruto
from lumen_normalizacao.silver import EscritorSilver
from lumen_orquestracao.configuracao import Configuracao

FIXTURES = Path(__file__).resolve().parents[3] / "testes" / "fixtures"
CABECALHO_ANP = ("Regiao - Sigla;Estado - Sigla;Municipio;Revenda;CNPJ da Revenda;Nome da Rua;Numero Rua;"
                 "Complemento;Bairro;Cep;Produto;Data da Coleta;Valor de Venda;Valor de Compra;Unidade de Medida;"
                 "Bandeira")


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    """Configuração do pipeline com dados num diretório temporário e o contato definido."""
    monkeypatch.setenv("LUMEN_CONTATO", "teste@exemplo.org")
    monkeypatch.setenv("LUMEN_DADOS", str(tmp_path / "dados"))
    return Configuracao(contato="teste@exemplo.org", raiz_dados=tmp_path / "dados")


def csv_anp(linhas: list[tuple]) -> bytes:
    """CSV no formato da série histórica: (uf, município, cnpj, produto, data dd/mm/aaaa, valor com vírgula)."""
    corpo = [CABECALHO_ANP]
    for uf, municipio, cnpj, produto, quando, valor in linhas:
        corpo.append(f"SE;{uf};{municipio};POSTO {cnpj};{cnpj};RUA A;1;;CENTRO;01000-000;{produto};{quando};"
                     f"{valor};;R$ / litro;BRANCA")
    return ("\n".join(corpo) + "\n").encode("utf-8")


def guardar_no_bronze(cfg: Configuracao, fonte_id: str, url: str, conteudo: bytes, status: int = 200,
                      quando: datetime | None = None, tipo: str = "application/json"):
    """Guarda um artefato no bronze local da configuração e devolve o registro."""
    artefato = ArtefatoBruto(conteudo=conteudo, fonte_id=fonte_id, url_solicitada=url, url_efetiva=url,
                             status_http=status, tipo_midia=tipo,
                             coletado_em=quando or datetime.now(timezone.utc))
    return ArmazemBronzeLocal(cfg.bronze).guardar(artefato)


def compra(cfg: Configuracao, *, chave: str = "11222333000181-1-000010/2026", uf: str = "SP",
           municipio: str = "3550308", publicado: date = date(2026, 3, 10),
           itens: list[tuple] = (), objeto: str = "Aquisição de combustíveis") -> None:
    """Grava na silver um processo e seus itens: (número, descrição, unidade, quantidade, estimado, homologado).

    ``homologado`` None deixa o item sem resultado. O resultado tem data igual à da publicação.
    """
    processo = ProcessoContratacao(
        id=id_canonico("processo_contratacao", chave), chave_origem=chave, orgao_id="o", orgao_cnpj=chave[:14],
        ente_id=None, unidade_gestora_id=None, uf=uf, municipio_codigo_ibge=municipio, ano=publicado.year,
        sequencial=int(chave.split("-")[2].split("/")[0]), numero=None, processo=None, modalidade=None,
        modalidade_codigo_origem=6, modo_disputa=None, amparo_legal_id=None, amparo_legal_codigo=None,
        objeto=objeto, informacao_complementar=None, srp=True, valor_estimado=None, valor_homologado=None,
        data_publicacao=publicado, publicado_em=datetime(publicado.year, publicado.month, publicado.day, 12,
                                                          tzinfo=timezone.utc),
        abertura_propostas_em=None, encerramento_propostas_em=None, atualizado_em=None, situacao=None,
        sistema_origem=None, link_sistema_origem=None)
    registros: list = [processo]
    for numero, descricao, unidade, quantidade, estimado, homologado in itens:
        item = ItemContratacao(
            id=id_canonico("item_contratacao", chave, numero), processo_id=processo.id, numero_item=numero,
            descricao_original=descricao, material_ou_servico="M", quantidade=Decimal(quantidade),
            unidade_medida=unidade, valor_unitario_estimado=Decimal(estimado) if estimado else None,
            valor_total_estimado=None, orcamento_sigiloso=False, criterio_julgamento=None, situacao=None,
            catalogo=None, catalogo_codigo_item=None, ncm_nbs_codigo=None, tem_resultado=homologado is not None,
            chave_origem=f"{chave}#{numero}")
        registros.append(item)
        if homologado is not None:
            registros.append(ResultadoItem(
                id=id_canonico("resultado_item", chave, numero, 1), item_id=item.id, processo_id=processo.id,
                sequencial_resultado=1, fornecedor_id=None, fornecedor_documento=None, fornecedor_tipo_pessoa=None,
                fornecedor_nome="AUTO POSTO EXEMPLO LTDA", porte_fornecedor=None,
                quantidade_homologada=Decimal(quantidade), valor_unitario_homologado=Decimal(homologado),
                valor_total_homologado=None, percentual_desconto=None, data_resultado=publicado))
    EscritorSilver(cfg.silver, "teste").gravar(f"t{abs(hash(chave)) % 10**8}", registros,
                                              coletado_em="2026-10-09T00:00:00+00:00")


def municipio(cfg: Configuracao, codigo: str = "3550308", nome: str = "São Paulo", uf: str = "SP") -> None:
    """Grava na silver o município (ente federativo) com o nome, como faz a normalização do IBGE."""
    EscritorSilver(cfg.silver, "teste").gravar(
        f"m{codigo}", [EnteFederativo(id=id_canonico("ente_federativo", codigo), codigo_ibge=codigo, nome=nome,
                                      esfera=Esfera.MUNICIPAL, uf=uf)], coletado_em="2026-10-09T00:00:00+00:00")


@pytest.fixture
def apoio():
    """As funções de apoio deste arquivo, para os testes chamarem sem importar o ``conftest``."""
    return SimpleNamespace(csv_anp=csv_anp, guardar_no_bronze=guardar_no_bronze, compra=compra, municipio=municipio)
