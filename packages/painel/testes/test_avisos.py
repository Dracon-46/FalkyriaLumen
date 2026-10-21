"""Avisos (ADR-047): cada sinal vira aviso com fonte e código estável; contestação marca ou tira; arquivos por UF."""

from lumen_painel import avisos as av
from lumen_painel import comum
from lumen_painel.cadastro import Cadastro, Ente

CADASTRO = Cadastro({"3550308": Ente("3550308", "São Paulo", "SP", "M"), "35": Ente("35", "São Paulo", "SP", "E"),
                     "1": Ente("1", "União", None, "F")})
J01 = {"coincidencias": [
    {"alcance": "todas_as_esferas",
     "contrato": {"chave": "11111111000111-2-000001/2026", "link_pncp": "https://pncp.gov.br/x", "orgao_cnpj": "11111111000111",
                  "orgao": "PREFEITURA FICTÍCIA", "uf": "SP", "data_assinatura": "2026-03-10", "valor_global": 1500.5,
                  "objeto": "Limpeza"},
     "fornecedor": {"cnpj": "22222222000122", "nome": "EMPRESA FICTÍCIA LTDA"},
     "sancao": {"cadastro": "CEIS", "codigo": "9", "categoria": "Inidoneidade", "data_inicio": "2025-01-01",
                "data_fim": None, "orgao_sancionador": "CGU"}},
    {"alcance": "a_conferir",
     "contrato": {"chave": "33333333000133-2-000002/2026", "orgao_cnpj": "33333333000133", "orgao": "EMPRESA PÚBLICA",
                  "uf": "DF", "data_assinatura": "2026-04-01", "valor_global": None},
     "fornecedor": {"cnpj": "22222222000133", "nome": "FULANO FICTÍCIO 12345678909"},
     "sancao": {"cadastro": "CNEP", "codigo": "8"}},
    {"alcance": "mesma_esfera", "contrato": {"orgao_cnpj": "11111111000111"}, "fornecedor": {"cnpj": "123"}, "sancao": {}},
]}
ORGAOS = {"11111111000111": ["PREFEITURA FICTÍCIA", "M", "3550308"], "33333333000133": ["EMPRESA PÚBLICA", None, None]}


def test_j01_vira_aviso_com_alcance_e_fonte_e_orgao_sem_ente_fica_na_uf():
    a, b = av.de_j01(J01, ORGAOS)                      # o terceiro (sem CNPJ de 14 dígitos) não entra
    assert a.tipo == "fornecedor_sancionado" and a.ente == "3550308" and a.data == "2026-03-10"
    assert "CEIS" in a.titulo and "EMPRESA FICTÍCIA LTDA (CNPJ 22222222000122)" in a.detalhe[0]
    assert "qualquer órgão público" in a.observar and a.fonte["outra"] == av.CADASTROS["CEIS"]
    assert "R$ 1.500,50" in a.detalhe[2] and a.lugar() == "SP"
    assert b.ente is None and b.lugar() == "DF" and "sem valor publicado" in b.detalhe[2]
    assert "FULANO FICTÍCIO ***.456.789-** (CNPJ" in b.detalhe[0] and "12345678909" not in str(b.detalhe)  # MEI
    assert b.para_json(CADASTRO)["ente"]["nome"] == "Órgão sem ente identificado no PNCP"
    assert av.de_j01(J01, ORGAOS)[0].id == a.id         # código estável


def test_valores_a_conferir_lrf_e_transparencia():
    v = av.de_valores_a_conferir("35", [{"data": "2026-05-02", "tipo": "contrato", "chave": "k", "orgao": "Secretaria",
                                         "valor": 2.4e11, "objeto": "Obra", "link": "https://pncp.gov.br/k"}])
    assert v[0].tipo == "valor_a_conferir" and "R$ 240.000.000.000,00" in v[0].titulo and v[0].chave == "k"
    obrig = [{"exercicio": 2025, "criterio": "rreo", "periodo": "1", "rotulo": "RREO do 1º bimestre de 2025",
              "resultado": "nao_cumpre", "prazo": "2025-03-30", "dispositivo": "LRF, art. 52"}]
    obrig += [{"exercicio": 2025, "criterio": "rgf", "periodo": str(i), "rotulo": f"RGF {i}", "resultado": "cumpre_parcialmente",
               "prazo": f"2025-0{i}-30", "entregue_em": f"2025-0{i + 1}-02"} for i in (1, 2, 3)]
    obrig += [{"exercicio": 2026, "resultado": "cumpre_parcialmente", "prazo": "2026-01-30"}]   # um só em 2026
    lrf = av.de_conformidade("3550308", obrig)
    assert [x.tipo for x in lrf] == ["lrf_nao_consta", "lrf_atrasos"]
    assert lrf[1].titulo == "3 relatórios fiscais de 2025 entregues após o prazo" and lrf[1].data == "2025-03-30"
    pntp = av.de_transparencia({"transparencia/uf-sp.json": {"ciclo": 2025, "url": "https://radar", "entes": {"3550308": [
        {"codigo_entidade": "1", "entidade": "Câmara Fictícia", "avaliada": True, "nivel": "Inicial", "indice": 0.2},
        {"codigo_entidade": "2", "entidade": "Prefeitura", "avaliada": True, "nivel": "Ouro", "indice": 0.9},
        {"codigo_entidade": "3", "entidade": "Outra", "avaliada": False, "nivel": "Inexistente"}]}}})
    assert len(pntp) == 1 and "nível Inicial" in pntp[0].titulo and "20.0%" in pntp[0].detalhe[0]


def test_contestacoes_marcam_retificam_ou_tiram_o_aviso():
    lista = av.de_j01(J01, ORGAOS)
    a, b = lista[0].id, lista[1].id
    issues = [{"title": f"[contestação] {a}", "state": "open", "labels": [{"name": "contestacao"}],
               "html_url": "https://github.com/x/1", "created_at": "2026-10-20T10:00:00Z"},
              {"title": "[contestação]", "body": f"Aviso: {b}", "state": "closed",
               "labels": [{"name": "contestacao"}, {"name": "removido"}], "html_url": "u2"},
              {"title": f"{a}", "state": "open", "labels": [{"name": "dado-divergente"}]}]
    c = av.ler_contestacoes(issues)
    assert c[a] == {"situacao": "em_analise", "link": "https://github.com/x/1", "em": "2026-10-20"}
    assert c[b]["situacao"] == "removido"
    todos = av.Avisos()
    todos.juntar(lista)
    todos.juntar(lista)                                  # o mesmo código entra uma vez
    todos.aplicar_contestacoes(c)
    assert [x.id for x in todos.lista] == [a] and todos.lista[0].contestacao["situacao"] == "em_analise"


def test_arquivos_por_uf_em_ordem_de_data_e_panorama(tmp_path):
    todos = av.Avisos()
    todos.juntar(av.de_j01(J01, ORGAOS))
    todos.juntar(av.de_valores_a_conferir("1", [{"data": "2026-06-01", "chave": "u", "valor": 1e12}]))
    comum.gravar_json(tmp_path / av.ARQUIVO_CONTESTACOES, [])
    gravados = {}
    resumo = av.publicar(tmp_path, todos, CADASTRO, lambda n, c: gravados.__setitem__(n, c), gerado_em="G")
    assert sorted(gravados) == ["avisos/panorama.json", "avisos/uf-df.json", "avisos/uf-sp.json", "avisos/uniao.json"]
    assert resumo["total"] == 3 and resumo["por_tipo"]["fornecedor_sancionado"] == 2
    p = gravados["avisos/panorama.json"]
    assert [x["data"] for x in p["ultimos"]] == ["2026-06-01", "2026-04-01", "2026-03-10"]
    assert {x["lugar"] for x in p["por_lugar"]} == {"União", "SP", "DF"}
    sp = gravados["avisos/uf-sp.json"]
    assert sp["uf"] == "SP" and sp["avisos"][0]["ente"] == {"codigo": "3550308", "nome": "São Paulo", "uf": "SP",
                                                           "tipo": "municipio"}
    assert av.ler_j01(tmp_path) == {}
