"""Estatais com ações na bolsa: cadastro, controle no FRE e demonstrações da CVM, com arquivos reais recortados.

As fixtures são linhas reais dos dados abertos da CVM de 2025 e 2026 (Petrobras, Banco do Brasil, BB
Seguridade, Sabesp, EMAE e Santos Brasil), com os dados de pessoas trocados por fictícios: responsável do
cadastro, representantes legais e acionistas pessoa física.
"""

import io
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pytest
from lumen_economia import cli, cvm, estatais
from lumen_economia.cvm import ArquivoCvmIlegivel, classificar, esfera_do_controlador
from lumen_economia.estatais import extrair, modelo, nivel

from lumen_ingestao.bronze import ArtefatoBruto
from lumen_ingestao.coleta_http import ErroColeta
from lumen_ingestao.zip_remoto import ErroZipRemoto
from lumen_painel.comum import ler_json

FIX = Path(__file__).resolve().parents[3] / "testes" / "fixtures" / "cvm"
AGORA = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)
PETROBRAS, BB, BBSEG = "33.000.167/0001-01", "00.000.000/0001-91", "17.344.597/0001-94"
SABESP, EMAE, SANTOS = "43.776.517/0001-80", "02.302.101/0001-42", "02.762.121/0001-04"


def _ler(nome: str) -> bytes:
    return (FIX / nome).read_bytes()


def _zip_dfp() -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in FIX.glob("dfp_cia_aberta_*2025.csv")}


class _Cliente:
    """Responde o cadastro e o ``Last-Modified`` dos ZIPs; ``falhar`` lista trechos de URL que dão erro."""

    def __init__(self, falhar=(), modificado="Sun, 11 Oct 2026 10:22:25 GMT", status=200):
        self.falhar, self.modificado, self.status, self.pedidos = falhar, modificado, status, []

    def obter(self, url, cabecalhos=None):
        self.pedidos.append(url)
        if any(f in url for f in self.falhar):
            raise ErroColeta("sem resposta")
        corpo = _ler("cad_cia_aberta.csv") if url == cvm.URL_CADASTRO else b"x"
        return ArtefatoBruto(conteudo=corpo, fonte_id="cvm_dados_abertos", url_solicitada=url, url_efetiva=url,
                             status_http=self.status if url == cvm.URL_CADASTRO else 206, tipo_midia="text/csv",
                             cabecalhos={"Last-Modified": self.modificado})


class _Membro:
    def __init__(self, conteudo):
        self.conteudo = conteudo


def _baixar(pedidos=None, sem_ano=()):
    """Falso ``baixar_membro``: DFP de 2025 e FRE de 2026 das fixtures; os outros anos não têm os arquivos."""
    arquivos = {**_zip_dfp(), "fre_cia_aberta_posicao_acionaria_2026.csv": _ler("fre_cia_aberta_posicao_acionaria_2026.csv")}

    def baixar(cliente, url, nome):
        if pedidos is not None:
            pedidos.append(nome)
        if any(str(a) in url for a in sem_ano):
            raise ErroColeta(f"{url} respondeu 404")
        if nome not in arquivos:
            raise ErroZipRemoto(f"{url} não tem {nome}")
        return _Membro(arquivos[nome])
    return baixar


# ------------------------------------------------------------------ cadastro e controle

def test_candidatas_so_ativas_e_estatais_uma_por_cnpj():
    c = cvm.candidatas(_ler("cad_cia_aberta.csv"))
    assert set(c) == {PETROBRAS, BB, BBSEG, SABESP, EMAE, SANTOS}
    assert c[PETROBRAS].controle_declarado == "ESTATAL HOLDING" and c[PETROBRAS].cd_cvm == "9512"
    assert "RESP" not in c[PETROBRAS].para_json() and "email" not in str(c[PETROBRAS].para_json()).lower()


def test_colunas_ausentes():
    with pytest.raises(ArquivoCvmIlegivel, match="colunas ausentes"):
        cvm.candidatas("<html>manutenção</html>".encode("latin-1"))


def test_controladores_diretos_pessoa_juridica_e_pessoa_fisica_so_contada():
    cnpjs = {PETROBRAS, BB, BBSEG, SABESP, EMAE, SANTOS, "00.000.000/0000-00"}
    c = cvm.controladores([_ler("fre_cia_aberta_posicao_acionaria_2026.csv")], cnpjs)
    assert c[PETROBRAS]["controladores"] == [{"nome": "União Federal", "cnpj": "00.394.460/0001-41",
                                              "percentual_ordinarias": 50.26, "percentual_total": 29.021}]
    assert c[BBSEG]["controladores"][0]["cnpj"] == BB
    assert c[SABESP]["controladores"] == [] and c[SABESP]["controladores_pessoa_fisica"] == 0
    # a cadeia de controle da Santos Brasil (CMA CGM) tem acionistas indiretos: só o direto conta
    assert [x["nome"] for x in c[SANTOS]["controladores"]] == ["CMA TERMINALS ATLANTIC S.A."]
    ficticia = c["00.000.000/0000-00"]
    assert ficticia["controladores"] == [] and ficticia["controladores_pessoa_fisica"] == 1
    assert "123.456.789-09" not in str(c) and "FICTÍCIA" not in str(c)


@pytest.mark.parametrize("nome,cnpj,esfera", [
    ("Ministério da Economia / Secretaria do Tesouro Nacional", "00.394.460/0001-41", "federal"),
    ("BANCO NACIONAL DE DESENVOLVIMENTO ECONÔMICO E SOCIAL", "33.657.248/0001-89", "federal"),
    ("União", "11.111.111/0001-11", "federal"),
    ("Governo do Estado de Sergipe", "13.128.798/0011-75", "estadual"),
    ("Fazenda do Estado de São Paulo - FESP", "46.379.400/0001-50", "estadual"),
    ("Estado de Minas Gerais (Casa Civil)", "18.715.615/0001-60", "estadual"),
    ("GOVERNO DO DISTRITO FEDERAL", "00.394.601/0001-26", "distrital"),
    ("SECRETARIA DE ESTADO DE PLANEJAMENTO, ORÇAMENTO E ADMINISTRAÇÃO DO DISTRITO FEDERAL", "00.394.684/0001-53",
     "distrital"),
    ("Prefeitura do Município de São Paulo", "46.392.130/0007-03", "municipal"),
    ("CIA SANEAMENTO BASICO DO ESTADO DE SAO PAULO - SABESP", SABESP, None),
    ("Equatorial Participações e Investimentos S.A.", "38.419.702/0001-87", None),
])
def test_esfera_do_controlador(nome, cnpj, esfera):
    assert esfera_do_controlador(nome, cnpj) == esfera


def test_classificar_segue_a_cadeia():
    controle = {
        "A": {"controladores": [{"nome": "Estado do Paraná", "cnpj": "1"}], "controladores_pessoa_fisica": 0},
        "B": {"controladores": [{"nome": "A SA", "cnpj": "A"}], "controladores_pessoa_fisica": 0},
        "C": {"controladores": [{"nome": "B SA", "cnpj": "B"}], "controladores_pessoa_fisica": 0},
        "D": {"controladores": [], "controladores_pessoa_fisica": 0},
        "E": {"controladores": [{"nome": "D SA", "cnpj": "D"}], "controladores_pessoa_fisica": 0},
        "F": {"controladores": [{"nome": "Grupo Privado SA", "cnpj": "9"}], "controladores_pessoa_fisica": 0},
        "G": {"controladores": [], "controladores_pessoa_fisica": 1},
    }
    k = classificar(controle)
    assert k["A"] == {"classe": "publico_direto", "esfera": "estadual", "controlada_por": None}
    assert k["C"] == {"classe": "publico_indireto", "esfera": "estadual", "controlada_por": "B"}
    assert k["D"]["classe"] == "sem_controlador"
    assert k["E"] == {"classe": "sem_controlador", "esfera": None, "controlada_por": "D"}
    assert k["F"]["classe"] == "privado" and k["G"]["classe"] == "privado"


# ------------------------------------------------------------------ demonstrações

def _companhia(cnpj):
    lido = estatais._coletar_dfp(None, _baixar(), 2025, {cnpj})
    return lido["companhias"][cnpj]


def test_contas_do_ultimo_exercicio_em_reais():
    p = _companhia(PETROBRAS)
    dre = p["demonstracoes"]["DRE"]
    assert dre["base"] == "con" and dre["inicio"] == "2025-01-01" and dre["fim"] == "2025-12-31"
    assert ["3.01", "Receita de Venda de Bens e/ou Serviços", 497_549_000_000.0, True] in dre["contas"]
    assert not any(c[0].startswith("3.99") for c in dre["contas"])
    assert p["demonstracoes"]["DFC"]["demonstracao"] == "DFC_MI"
    assert p["documento"]["link"].startswith("http://www.rad.cvm.gov.br/")


def test_versao_mais_recente_da_entrega():
    s = _companhia(SABESP)
    assert s["documento"]["versao"] == 2 and s["demonstracoes"]["DRE"]["versao"] == 2


def test_indicadores_empresa_banco_e_seguradora():
    modelo_, v = extrair(_companhia(PETROBRAS)["demonstracoes"])
    assert modelo_ == "empresa"
    assert v["receita"]["valor"] == 497_549_000_000.0 and v["custos"]["valor"] == -260_551_000_000.0
    assert v["resultado"]["valor"] == 110_605_000_000.0 and v["resultado"]["conta"] == "3.11"
    assert v["pessoal"]["valor"] == 46_406_000_000.0 and v["impostos"]["valor"] == 207_791_000_000.0
    assert v["insumos"]["valor"] == -292_210_000_000.0
    assert v["caixa_investimentos"]["valor"] == -86_114_000_000.0
    assert v["aquisicoes_ativos"]["valor"] == -108_714_000_000.0
    assert v["aquisicoes_ativos"]["linhas"][0][1] == "Aquisições de ativos imobilizados e intangíveis"

    modelo_, v = extrair(_companhia(BB)["demonstracoes"])
    assert modelo_ == "banco"
    assert v["receita"]["descricao"] == "Receitas de Intermediação Financeira"
    assert v["pessoal"]["conta"] == "7.09.01" and v["pessoal"]["valor"] == 29_698_178_000.0
    assert v["impostos"]["valor"] == -2_248_771_000.0   # créditos tributários: negativo, como publicado
    assert v["insumos"]["conta"] == "7.03"

    modelo_, v = extrair(_companhia(BBSEG)["demonstracoes"])
    assert modelo_ == "seguradora"
    assert v["resultado"]["conta"] == "3.13" and v["pessoal"]["conta"] == "7.11.01"
    assert v["aquisicoes_ativos"] is None   # holding sem compra de imobilizado: ausente, não zero


def test_aquisicoes_sem_vendas_nem_dupla_contagem():
    dfc = [["6.02", "Caixa Líquido Atividades de Investimento", -10.0, True],
           ["6.02.01", "No Imobilizado", -4.0, False],
           ["6.02.02", "Adições ao intangível", -3.0, False],
           ["6.02.02.01", "Adições ao intangível - software", -1.0, False],
           ["6.02.03", "Alienação de ativos imobilizados", 2.0, False],
           ["6.02.04", "Baixa de imobilizado", -0.5, False],
           ["6.02.05", "Aplicações financeiras", -5.0, False]]
    _, v = extrair({"DFC": {"contas": dfc}})
    assert v["aquisicoes_ativos"]["valor"] == -7.0 and len(v["aquisicoes_ativos"]["linhas"]) == 2
    assert v["receita"] is None and v["pessoal"] is None


def test_modelo_e_nivel():
    assert modelo([["3.01", "Receitas de Intermediação Financeira", 1, True]]) == "banco"
    assert modelo([["3.01", "Receitas das Operações de Previdência", 1, True]]) == "seguradora"
    assert modelo([]) == "outro"
    assert nivel("3.04") == 2 and nivel("3.04.05.01") == 4


# ------------------------------------------------------------------ coleta, estado e publicação

def test_coleta_e_publicacao(tmp_path):
    pedidos = []
    cliente = _Cliente()
    resumo = estatais.coletar(cliente, tmp_path, [2024, 2025], baixar=_baixar(pedidos), agora=AGORA)
    assert resumo.candidatas == 6 and resumo.com_controle == 6
    assert resumo.anos_lidos == {"2024": 0, "2025": 6} and not resumo.falhas
    assert "fre_cia_aberta_posicao_acionaria_2025.csv" in pedidos   # tentou o ano anterior também

    # mesma data de modificação e mesmas candidatas: não baixa de novo
    pedidos.clear()
    resumo = estatais.coletar(cliente, tmp_path, [2025], baixar=_baixar(pedidos), agora=AGORA)
    assert resumo.anos_mantidos == ["2025"] and not any(p.startswith("dfp_") for p in pedidos)

    feed = estatais.montar(estatais.ler_estado(tmp_path), agora=AGORA)
    assert feed["tipo"] == "estatais" and feed["urls"]["dfp"]["2025"] == cvm.url_dfp(2025)
    por = {c["cnpj"]: c for c in feed["companhias"]}
    assert por[PETROBRAS]["controle"]["classe"] == "publico_direto" and por[PETROBRAS]["controle"]["esfera"] == "federal"
    assert por[BBSEG]["controle"]["classe"] == "publico_indireto"
    assert por[BBSEG]["controle"]["controlada_por_nome"] == "BANCO DO BRASIL S.A."
    assert por[SABESP]["controle"]["classe"] == "sem_controlador"
    assert por[EMAE]["controle"] == {**por[EMAE]["controle"], "classe": "sem_controlador", "controlada_por": SABESP}
    assert por[SANTOS]["controle"]["classe"] == "privado"
    assert por[PETROBRAS]["exercicios"]["2025"]["bases"] == {"DRE": "consolidado", "DFC": "consolidado, método indireto",
                                                            "DVA": "consolidado"}
    # públicas primeiro, pela receita do último exercício
    assert [c["cnpj"] for c in feed["companhias"]][:2] == [PETROBRAS, BB]
    assert {i["id"] for i in feed["indicadores"]} == {i.id for i in estatais.INDICADORES}

    r = estatais.publicar(tmp_path, tmp_path / "site", agora=AGORA)
    assert r["companhias"] == 6 and r["controle"]["publico_direto"] == 2
    assert ler_json(tmp_path / "site" / "economia" / "estatais.json")["companhias"][0]["cnpj"] == PETROBRAS


def test_falhas_mantem_o_que_havia(tmp_path):
    estatais.coletar(_Cliente(), tmp_path, [2025], baixar=_baixar(), agora=AGORA)
    resumo = estatais.coletar(_Cliente(falhar=("cad_cia", "dfp_cia_aberta_2025")), tmp_path, [2025],
                              baixar=_baixar(), agora=AGORA)
    assert set(resumo.falhas) == {"cadastro", "dfp_2025"}
    dados = estatais.ler_estado(tmp_path)
    assert len(dados["cadastro"]["companhias"]) == 6 and dados["dfp"]["2025"]["ultima_falha"]
    assert dados["dfp"]["2025"]["companhias"] and dados["falhas"]["motivos"]["cadastro"]


def test_sem_cadastro_nao_segue(tmp_path):
    resumo = estatais.coletar(_Cliente(status=503), tmp_path, [2025], baixar=_baixar(), agora=AGORA)
    assert "cadastro" in resumo.falhas and resumo.candidatas == 0
    assert estatais.montar(estatais.ler_estado(tmp_path), agora=AGORA)["companhias"] == []


def test_estado_de_outra_versao(tmp_path):
    from lumen_painel.comum import gravar_json
    gravar_json(tmp_path / estatais.ARQUIVO_ESTADO, {"versao": 99}, comprimir=True)
    with pytest.raises(ValueError, match="versão 99"):
        estatais.ler_estado(tmp_path)


def test_ultima_modificacao_erro():
    class C:
        def obter(self, url, cabecalhos=None):
            return ArtefatoBruto(conteudo=b"", fonte_id="x", url_solicitada=url, url_efetiva=url, status_http=404,
                                 tipo_midia="text/html")
    with pytest.raises(ErroColeta, match="404"):
        estatais.ultima_modificacao(C(), cvm.url_dfp(2025))


def test_membro_erro_que_nao_e_ausencia_sobe():
    with pytest.raises(ErroColeta, match="404"):
        estatais._membro(_baixar(sem_ano=(2025,)), None, cvm.url_dfp(2025), "x.csv")


def test_anos_padrao_e_urls():
    assert estatais.anos_padrao(AGORA) == [2021, 2022, 2023, 2024, 2025]
    assert cvm.url_fre(2026).endswith("/FRE/DADOS/fre_cia_aberta_2026.zip")
    assert cvm.membro_dfp(2025, "DRE", "con") == "dfp_cia_aberta_DRE_con_2025.csv"


def test_cli(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "_cliente", lambda args, fonte=None: _Cliente())
    monkeypatch.setattr(cli.sest, "coletar", lambda cliente, estado: cli.sest.ResumoColetaSest())
    monkeypatch.setattr(estatais, "baixar_membro", _baixar())
    monkeypatch.setattr(estatais, "anos_padrao", lambda agora: [2025])
    assert cli.main(["estatais", "--estado", str(tmp_path)]) == 0
    assert '"candidatas": 6' in capsys.readouterr().out
    assert cli.main(["publicar", "--estado", str(tmp_path), "--saida", str(tmp_path / "site")]) == 0
    assert (tmp_path / "site" / "economia" / "estatais.json").exists()
    assert cli.main(["estatais", "--estado", str(tmp_path), "--anos", "2025"]) == 0


def test_zip_real_recortado(tmp_path):
    """Os nomes dos arquivos das fixtures são os do ZIP publicado (conferido em 16/10/2026)."""
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        for nome, conteudo in _zip_dfp().items():
            z.writestr(nome, conteudo)
    nomes = set(zipfile.ZipFile(io.BytesIO(b.getvalue())).namelist())
    esperados = {cvm.membro_dfp(2025, d, base) for d in cvm.DEMONSTRACOES for base in cvm.BASES}
    assert esperados | {cvm.membro_documentos(2025)} == nomes
