"""Os deputados estaduais pelas fontes próprias das Assembleias (ADR-062, adendo 2): o SPL da Ágape e os votos de
Goiás."""

import urllib.parse
from datetime import date

from lumen_painel import assembleias, vereadores
from lumen_painel.cadastro import Cadastro, Ente


def _fontes():
    """O SPL de Goiás e a transparência da Alego de mentira."""
    parlamentares = [
        {"parlamentarID": 87, "parlamentarNome": "Alessandro Moreira", "parlamentarRazaoSocial": "ALESSANDRO MOREIRA DOS SANTOS",
         "partidoSigla": "PP", "parlamentarSituacao": "Ativo", "parlamentarPerfil": "<p>Esposa: ...</p>"},
        {"parlamentarID": 90, "parlamentarNome": "Bruno Peixoto", "parlamentarRazaoSocial": "BRUNO REGIANY PEIXOTO PIMENTA",
         "partidoSigla": "UNIÃO", "parlamentarSituacao": "Ativo"},
    ]
    proposicoes = {
        "2025": [
            {"id": 1, "sigla": "PLO", "tipo": "Projeto de Lei Ordinária", "numero": "1452", "data": "22/12/2025 14:17:46",
             "assunto": "ASSEGURA  AO CONDÔMINO", "AutorRequerenteDados": {"nomeRazao": "BRUNO REGIANY PEIXOTO PIMENTA",
                                                                         "cpf_cnpj": "39495760704", "setor": "GABINETE DEP. BRUNO PEIXOTO"},
             "CoAutores": [{"nomeRazao": "Alessandro Moreira"}]},
            {"id": 2, "sigla": "REQ", "tipo": "Requerimento", "numero": "9", "data": "01/03/2025 10:00:00",
             "assunto": "Requer", "AutorRequerenteDados": {"nomeRazao": None, "setor": "Gab. Dep. Alessandro Moreira"}},
            {"id": 3, "sigla": "VT", "tipo": "Veto", "numero": "5", "data": "01/03/2025 10:00:00", "assunto": "Veta",
             "AutorRequerenteDados": {"nomeRazao": "GOVERNADORIA"}},
            {"id": 4, "sigla": "PEC", "tipo": "Proposta de Emenda Constitucional", "numero": "2", "data": "05/05/2025 09:00:00",
             "assunto": "Altera", "AutorRequerenteDados": {"nomeRazao": "Alessandro Moreira"}},
        ],
    }
    detalhes = [
        {"data_sessao": "2025-06-26", "pauta_id": 22745, "parlamentar": "Alessandro Moreira", "tipo_voto": "SIM",
         "partido_sigla": "PP", "resultado_votacao": "APROVADO EM 1ª DISCUSSÃO", "tipo_votacao": "NOMINAL",
         "ementa_projeto": "AUTOR - DEPUTADO X\nASSUNTO - INSTITUI DIRETRIZES"},
        {"data_sessao": "2025-06-26", "pauta_id": 22745, "parlamentar": "ALESSANDRO MOREIRA", "tipo_voto": "SIM",
         "partido_sigla": "PP", "resultado_votacao": "APROVADO EM 1ª DISCUSSÃO", "tipo_votacao": "NOMINAL"},
        {"data_sessao": "2025-06-26", "pauta_id": 22745, "parlamentar": "Bruno Peixoto", "tipo_voto": "NÃO",
         "partido_sigla": "UNIÃO", "resultado_votacao": "APROVADO EM 1ª DISCUSSÃO", "tipo_votacao": "NOMINAL"},
        {"data_sessao": "2025-06-26", "pauta_id": 22746, "parlamentar": "Fulano Sem Cadastro", "tipo_voto": "SIM",
         "resultado_votacao": "APROVADO", "tipo_votacao": "NOMINAL"},
        {"data_sessao": "2025-06-26", "pauta_id": 22747, "parlamentar": "Bruno Peixoto", "tipo_voto": "SECRETO",
         "tipo_votacao": "SECRETA"},
    ]
    resumo = [{"pauta_id": 22745, "numero_processo_projeto": "PROCESSO 2025001 - PROJETO DE LEI"}]

    def ler(url: str):
        partes = urllib.parse.urlsplit(url)
        q = dict(urllib.parse.parse_qsl(partes.query))
        if partes.path.endswith("/parlamentar/"):
            return {"total": len(parlamentares), "parlamentares": parlamentares if q["pag"] == "1" else []}
        if partes.path.endswith("/proposicao/"):
            linhas = proposicoes.get(q["ano"], [])
            return {"total": len(linhas), "Data": linhas if q["pag"] == "1" else []}
        if partes.path.endswith("votacoes.json"):
            if q["ano"] != "2025":
                return []
            return detalhes if q["tipo"] == "detalhes" else resumo
        raise AssertionError(url)
    return ler


def test_chave_do_nome():
    assert assembleias.chave("Gab. Dep. João Coser") == "JOAO COSER"
    assert assembleias.chave("GABINETE DO DEPUTADO JOÃO COSER") == "JOAO COSER"


def test_coleta_e_publicacao_de_goias(tmp_path):
    r = assembleias.coletar(tmp_path, contato="c", hoje=date(2025, 12, 30), casas=["52"], ler_fn=_fontes())
    assert r["52"]["lidos"] == ["proposicoes-2023", "votos-2023", "proposicoes-2024", "votos-2024",
                                "proposicoes-2025", "votos-2025"]
    assert r["52"]["problemas"] == ["2025: 1 voto(s) sem deputado no cadastro"]
    c = assembleias.ler_estado(tmp_path)["52"]
    a = c["materias"]["2025"]
    assert a["projetos"] == {"1": ["PLO", "1452", "ASSEGURA AO CONDÔMINO", "2025-12-22", ["87", "90"]],
                             "4": ["PEC", "2", "Altera", "2025-05-05", ["87"]]}
    assert a["contagem"] == {"87": {"PLO": 1, "REQ": 1, "PEC": 1}, "90": {"PLO": 1}}
    assert "39495760704" not in str(c)                     # o CPF que a API traz não é guardado
    votacao = c["votacoes"]["2025"]["votacoes"]["22745"]
    assert votacao == ["2025-06-26", "PROCESSO 2025001 - PROJETO DE LEI", "INSTITUI DIRETRIZES",
                       "APROVADO EM 1ª DISCUSSÃO", 1, {"87": "S", "90": "N"}, {"87": "PP", "90": "UNIÃO"}]

    cadastro = Cadastro({"52": Ente("52", "Goiás", "GO", "E", 7_000_000)})
    gravados: dict[str, dict] = {}
    linhas = assembleias.publicar(tmp_path, cadastro, lambda nome, x: gravados.setdefault(nome, x), gerado_em="x")
    assert linhas == [["52", "Goiás", "GO", "alegodigital.al.go.leg.br", 2, 1, ["2025"], "spl"]]
    bruno = gravados["parlamentares/estadual/52/90.json.gz"]
    assert bruno["tipo"] == "estadual-deputado" and bruno["partido"] == "UNIÃO" and bruno["legislaturas"] == [2023]
    assert bruno["anos"]["2025"]["votos"] == {"22745": "N"} and bruno["anos"]["2025"]["presenca"] == [0, 0]
    votos = gravados["parlamentares/estadual/52/votos-2025.json.gz"]["votos"]
    assert votos == {"22745": [["87", "S", "PP"], ["90", "N", "UNIÃO"]]}

    # o índice das Assembleias junta as do SAPL e as das fontes próprias
    resumo = vereadores.publicar(tmp_path, cadastro, lambda nome, x: gravados.__setitem__(nome, x), gerado_em="x",
                                 estaduais=linhas)
    assert resumo["assembleias"] == 1 and resumo["deputados_estaduais"] == 2
    assert gravados["parlamentares/estadual/indice.json"]["camaras"] == linhas


def test_assembleia_fora_do_ar_fica_com_a_leitura_anterior(tmp_path):
    assembleias.coletar(tmp_path, contato="c", hoje=date(2025, 12, 30), casas=["52"], ler_fn=_fontes())

    def fora(url: str):
        raise OSError("fora do ar")
    r = assembleias.coletar(tmp_path, contato="c", hoje=date(2026, 3, 1), casas=["52"], ler_fn=fora)
    assert r["52"]["erro"].startswith("OSError")
    assert assembleias.ler_estado(tmp_path)["52"]["materias"]["2025"]["projetos"]


def test_minas_proposicoes_e_verba(tmp_path):
    def ler(url: str):
        partes = urllib.parse.urlsplit(url)
        q = dict(urllib.parse.parse_qsl(partes.query))
        caminho = partes.path.removeprefix("/api/v2/")
        if caminho == "deputados/em_exercicio":
            return {"list": [{"id": 12193, "nome": "Adalclever Lopes", "partido": "PV"}]}
        if caminho == "deputados/que_exerceram_mandato":
            return {"listaDeputado": []}
        if caminho == "proposicoes/tipos":
            return {"list": [{"sigla": "PL", "pesquisaDirigida": "S"}, {"sigla": "RQC", "pesquisaDirigida": "S"},
                             {"sigla": "IMP", "pesquisaDirigida": "N"}]}
        if caminho == "proposicoes/pesquisa/direcionada":
            assert q["tipo"] in ("PL", "RQC")
            itens = [] if q["ano"] != "2025" or q["p"] != "1" else [
                {"siglaTipoProjeto": "PL", "tipoProjeto": "PROJETO DE LEI", "numero": "5450", "assunto": "Institui  o dia",
                 "dataPublicacao": "2025-03-04", "autoresEstruturados": [{"id": 12193}, {"id": 99, "nome": "Deputada Ex",
                                                                                         "partido": "PT"}]},
                {"siglaTipoProjeto": "RQC", "tipoProjeto": "REQUERIMENTO DE COMISSÃO", "numero": "1",
                 "autoresEstruturados": [{"id": 12193}]}]
            itens = [x for x in itens if x["siglaTipoProjeto"] == q["tipo"]]
            return {"resultado": {"noOcorrencias": len(itens), "listaItem": itens}}
        if caminho.startswith("prestacao_contas/verbas_indenizatorias/deputados/12193/2025/9"):
            return {"list": [{"descTipoDespesa": "Combustível", "listaDetalheVerba": [
                {"valorReembolsado": 230.52, "dataReferencia": {"$": "2025-09-01"}, "cpfCnpj": "42927464000198",
                 "nomeEmitente": "Auto Posto do Alemão Ltda.", "descTipoDespesa": "Combustível"},
                {"valorReembolsado": 100.0, "dataReferencia": {"$": "2025-09-01"}, "cpfCnpj": "39495760704",
                 "nomeEmitente": "Fulano", "descTipoDespesa": "Combustível"}]}]}
        if caminho.startswith("prestacao_contas/"):
            return {"list": []}
        raise AssertionError(url)

    r = assembleias.coletar(tmp_path, contato="c", hoje=date(2025, 12, 30), casas=["31"], ler_fn=ler)
    assert "verba-2025" in r["31"]["lidos"]
    c = assembleias.ler_estado(tmp_path)["31"]
    assert c["deputados"]["99"] == ["Ex", "Ex", "PT", "Fora de exercício"]   # autora que saiu entra no cadastro
    assert c["materias"]["2025"]["projetos"] == {"PL-5450-2025": ["PL", "5450", "Institui o dia", "2025-03-04",
                                                                  ["12193", "99"]]}
    assert c["materias"]["2025"]["contagem"]["12193"] == {"PL": 1, "RQC": 1}
    verba = c["verbas"]["2025"]
    assert verba["verba"]["12193"] == {"categorias": {"Combustível": 330.52}, "meses": {"09": 330.52},
                                       "fornecedores": {"42927464000198": [1, 230.52]}, "pf": [1, 100.0]}
    assert "39495760704" not in str(c)

    cadastro = Cadastro({"31": Ente("31", "Minas Gerais", "MG", "E", 21_000_000)})
    gravados: dict[str, dict] = {}
    linhas = assembleias.publicar(tmp_path, cadastro, lambda nome, x: gravados.setdefault(nome, x), gerado_em="x")
    assert linhas[0][7] == "almg"
    ano = gravados["parlamentares/estadual/31/12193.json.gz"]["anos"]["2025"]
    assert ano["ceap"]["fornecedores"] == [["42927464000198", "Auto Posto do Alemão Ltda.", 1, 230.52]]
    assert gravados["parlamentares/estadual/31/indice.json"]["deputados"][0][9] == 330.52


def test_almg_espera_no_429():
    import io
    import urllib.error
    pedidos, pausas = [], []

    def ler(url: str):
        pedidos.append(url)
        if len(pedidos) == 1:
            raise urllib.error.HTTPError(url, 429, "Too Many Requests", {}, io.BytesIO())  # type: ignore[arg-type]
        return {"list": []}
    assert assembleias._almg("deputados/em_exercicio", contato="c", ler_fn=ler, esperar=pausas.append) == {"list": []}
    assert pausas == [60] and len(pedidos) == 2


def test_sao_paulo_pelos_arquivos(tmp_path):
    import io
    arquivos = {
        "deputados/deputados.xml": "<Deputados><Deputado><IdDeputado>1139</IdDeputado><IdSPL>1000000335</IdSPL>"
                                   "<Matricula>300257</Matricula><NomeParlamentar>Danilo Balas</NomeParlamentar>"
                                   "<Partido>PL</Partido><Situacao>EXE</Situacao></Deputado></Deputados>",
        "processo_legislativo/naturezasSpl.xml": "<natureza><natureza><idNatureza>1</idNatureza><sgNatureza>PL</sgNatureza>"
                                                 "</natureza><natureza><idNatureza>7</idNatureza><sgNatureza>Req.   </sgNatureza>"
                                                 "</natureza></natureza>",
        "processo_legislativo/proposituras.zip": "<proposituras>"
            "<propositura><AnoLegislativo>2025</AnoLegislativo><Ementa>Institui  o dia</Ementa><DtPublicacao>2025-03-04T00:00:00-03:00"
            "</DtPublicacao><IdDocumento>10</IdDocumento><IdNatureza>1</IdNatureza><NroLegislativo>652</NroLegislativo></propositura>"
            "<propositura><DtPublicacao>2025-03-05T00:00:00-03:00</DtPublicacao><IdDocumento>11</IdDocumento><IdNatureza>7"
            "</IdNatureza><NroLegislativo>1</NroLegislativo></propositura>"
            "<propositura><DtPublicacao>1996-10-10T00:00:00-02:00</DtPublicacao><IdDocumento>166</IdDocumento><IdNatureza>1"
            "</IdNatureza></propositura></proposituras>",
        "processo_legislativo/documento_autor.zip": "<documentos_autores>"
            "<DocumentoAutor><IdAutor>1000000335</IdAutor><IdDocumento>10</IdDocumento></DocumentoAutor>"
            "<DocumentoAutor><IdAutor>105</IdAutor><IdDocumento>10</IdDocumento><NomeAutor>Governador</NomeAutor></DocumentoAutor>"
            "<DocumentoAutor><IdAutor>1000000335</IdAutor><IdDocumento>11</IdDocumento></DocumentoAutor></documentos_autores>",
        "deputados/despesas_gabinetes.xml": "<despesas>"
            "<despesa><Ano>2025</Ano><Matricula>300257</Matricula><Mes>3</Mes><Valor>200.0</Valor><CNPJ>42927464000198</CNPJ>"
            "<Tipo>A - COMBUSTÍVEIS</Tipo><Fornecedor>AUTO POSTO</Fornecedor></despesa>"
            "<despesa><Ano>2025</Ano><Matricula>300257</Matricula><Mes>3</Mes><Valor>2850.0</Valor><CNPJ>22145388877</CNPJ>"
            "<Tipo>N - MORADIA</Tipo><Fornecedor>LARA PESSOA FISICA</Fornecedor></despesa>"
            "<despesa><Ano>2015</Ano><Matricula>300257</Matricula><Mes>3</Mes><Valor>9.0</Valor><CNPJ>42927464000198</CNPJ>"
            "<Tipo>A</Tipo></despesa></despesas>",
    }
    r = assembleias.coletar(tmp_path, contato="c", hoje=date(2025, 12, 30), casas=["35"],
                            abrir_fn=lambda caminho: io.BytesIO(arquivos[caminho].encode()))
    assert r["35"]["lidos"] == ["2025"]
    c = assembleias.ler_estado(tmp_path)["35"]
    assert c["materias"]["2025"]["projetos"] == {"10": ["PL", "652", "Institui o dia", "2025-03-04", ["1000000335"]]}
    assert c["materias"]["2025"]["contagem"] == {"1000000335": {"PL": 1, "Req.": 1}}
    assert c["verbas"]["2025"]["verba"]["1000000335"] == {
        "categorias": {"A - COMBUSTÍVEIS": 200.0, "N - MORADIA": 2850.0}, "meses": {"03": 3050.0},
        "fornecedores": {"42927464000198": [1, 200.0]}, "pf": [1, 2850.0]}
    assert "LARA" not in str(c) and "22145388877" not in str(c)   # pessoa física: só a soma
    assert list(c["verbas"]) == ["2025"]
