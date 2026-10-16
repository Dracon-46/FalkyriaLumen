"""Normalização das avaliações do PNTP com a amostra real de 2025 e o cabeçalho real de 2022."""

import io
import zipfile
from datetime import date
from decimal import Decimal

from lumen_canonico.fato import AvaliacaoTransparencia, Esfera
from lumen_canonico.identidade import id_canonico
from lumen_normalizacao.pntp import FRACAO_FORA_DA_FAIXA, normalizar_avaliacoes
from lumen_normalizacao.qualidade import CODIGO_IBGE_AUSENTE


def _norm(conteudo, ciclo=2025):
    return normalizar_avaliacoes(conteudo, ciclo=ciclo, fonte_id="pntp_avaliacoes", documento_fonte_id="reg1")


def _por_codigo(r):
    return {a.codigo_entidade: a for a in r.registros}


def test_amostra_real_de_2025(fixture_bytes):
    r = _norm(fixture_bytes("pntp/avaliacoes_pntp_2025_amostra.xlsx"))
    assert (r.lidos, len(r.registros), len(r.quarentena)) == (8, 8, 0)
    assert all(isinstance(a, AvaliacaoTransparencia) and a.ciclo == 2025 for a in r.registros)
    a = _por_codigo(r)
    sume = a["10669"]
    assert sume.entidade == "Câmara Municipal de Sumé" and sume.poder == "Legislativo"
    assert (sume.esfera, sume.uf, sume.municipio_codigo_ibge, sume.ente_codigo_ibge) == (
        Esfera.MUNICIPAL, "PB", "2516300", "2516300")
    assert sume.ente_id == id_canonico("ente_federativo", "2516300")
    assert sume.indice == Decimal("0.9585") and sume.percentual_essenciais == Decimal("1.0000")
    assert (sume.nivel, sume.nivel_anterior) == ("Diamante", "Intermediário")
    assert sume.data_envio == date(2025, 4, 21) and sume.validada is True and sume.certificavel is True
    assert sume.link_portal == "https://camaradesume.pb.gov.br/"
    assert sume.id == id_canonico("avaliacao_transparencia", 2025, "10669")


def test_ente_de_cada_esfera(fixture_bytes):
    a = _por_codigo(_norm(fixture_bytes("pntp/avaliacoes_pntp_2025_amostra.xlsx")))
    assert a["11160"].esfera is Esfera.ESTADUAL and a["11160"].ente_codigo_ibge == "21"      # Maranhão
    assert a["11354"].esfera is Esfera.UNIAO and a["11354"].ente_codigo_ibge == "1"          # Caixa
    assert a["11293"].esfera is Esfera.DISTRITAL and a["11293"].ente_codigo_ibge == "53"     # MPDFT


def test_nao_avaliada_fica_no_cadastro_sem_indice(fixture_bytes):
    abaira = _por_codigo(_norm(fixture_bytes("pntp/avaliacoes_pntp_2025_amostra.xlsx")))["7"]
    assert abaira.avaliada is False and abaira.nivel == "Não Avaliado"
    assert abaira.indice is None and abaira.percentual_essenciais is None and abaira.data_envio is None
    assert abaira.validada is None and abaira.link_portal is None


def test_inexistente_tem_indice_zero(fixture_bytes):
    consorcio = _por_codigo(_norm(fixture_bytes("pntp/avaliacoes_pntp_2025_amostra.xlsx")))["11468"]
    assert consorcio.avaliada is True and consorcio.nivel == "Inexistente" and consorcio.indice == Decimal("0.0000")


def test_percentual_fora_da_faixa_vira_nulo_com_marcacao(fixture_bytes):
    piedade = _por_codigo(_norm(fixture_bytes("pntp/avaliacoes_pntp_2025_amostra.xlsx")))["3778"]
    assert piedade.percentual_essenciais is None and FRACAO_FORA_DA_FAIXA in piedade.marcacoes_qualidade
    assert piedade.indice is not None


def test_layout_de_2022_vai_para_a_quarentena(fixture_bytes):
    r = _norm(fixture_bytes("pntp/avaliacoes_pntp_2022_cabecalho.xlsx"), ciclo=2022)
    assert not r.registros and len(r.quarentena) == 1
    assert "2022" in r.quarentena[0].motivo and "Código Entidade" in r.quarentena[0].motivo


def _planilha(*linhas):
    """Planilha mínima com o cabeçalho de 2023 em diante e as linhas dadas (strings em linha)."""
    from lumen_normalizacao.pntp import COLUNAS
    linhas = [list(COLUNAS), *linhas]
    xml = "".join(f'<row r="{n}">' + "".join(f'<c r="{chr(65 + i)}{n}" t="inlineStr"><is><t>{v}</t></is></c>'
                                             for i, v in enumerate(linha)) + "</row>"
                  for n, linha in enumerate(linhas, 1))
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("xl/workbook.xml", '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                   'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
                   '<sheet name="a" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/'
                   '2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr("xl/worksheets/sheet1.xml", '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/'
                   f'2006/main"><sheetData>{xml}</sheetData></worksheet>')
    return b.getvalue()


def _linha(**troca):
    base = {"Código Entidade": "1", "Poder": "Executivo", "Esfera": "Municipal", "Unidade Gestora": "Prefeitura",
            "UF": "Bahia", "ibge": "2900108", "Data Envio": "45768", "Autoavaliação": "Sim",
            "Avaliação Validada?": "Sim", "Avaliação Certificável?": "Não", "Índice de Transparência": "0.5",
            "% das Essenciais": "1", "Nível de Transparência": "Intermediário", "Histórico do Nível": " -> Básico",
            "Link Site Principal": "https://exemplo.ba.gov.br"}
    base.update(troca)
    from lumen_normalizacao.pntp import COLUNAS
    return [base[c] for c in COLUNAS]


def test_casos_de_borda():
    r = _norm(_planilha(
        _linha(),
        _linha(**{"Código Entidade": "2", "Índice de Transparência": "metade"}),
        _linha(**{"Código Entidade": "3", "Unidade Gestora": "-"}),
        _linha(**{"Código Entidade": "-"}),
        _linha(**{"Código Entidade": "5", "Esfera": "Outra", "ibge": "-"}),
        [""] * 15,
    ))
    assert [a.codigo_entidade for a in r.registros] == ["1", "5"]
    um = r.registros[0]
    assert um.nivel_anterior is None and um.autoavaliacao is True and um.certificavel is False
    cinco = r.registros[1]
    assert cinco.esfera is None and cinco.ente_codigo_ibge is None and CODIGO_IBGE_AUSENTE in cinco.marcacoes_qualidade
    assert sorted((q.campo, q.chave_origem) for q in r.quarentena) == [
        ("Código Entidade", "-"), ("Unidade Gestora", "3"), ("Índice de Transparência", "2")]


def test_planilha_ilegivel():
    r = _norm(b"isto nao e xlsx")
    assert not r.registros and "planilha ilegível" in r.quarentena[0].motivo
