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
