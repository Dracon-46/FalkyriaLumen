"""Testes das emendas parlamentares (CGU): recebido por ente, categorias pela natureza jurídica e publicação."""

import zipfile

from lumen_painel import comum, emendas
from lumen_painel.cadastro import Cadastro, Ente

CABECALHO_FAVORECIDO = ("Código da Emenda;Código do Autor da Emenda;Nome do Autor da Emenda;Número da emenda;"
                        "Tipo de Emenda;Ano/Mês;Código do Favorecido;Favorecido;Natureza Jurídica;Tipo Favorecido;"
                        "UF Favorecido;Município Favorecido;Valor Recebido")
CABECALHO_EMENDA = ("Código da Emenda;Ano da Emenda;Tipo de Emenda;Código do Autor da Emenda;Nome do Autor da Emenda;"
                    "Número da emenda;Localidade de aplicação do recurso;Código Município IBGE;Município;"
                    "Código UF IBGE;UF;Região;Código Função;Nome Função;Código Subfunção;Nome Subfunção;Código Programa;"
                    "Nome Programa;Código Ação;Nome Ação;Código Plano Orçamentário;Nome Plano Orçamentário;"
                    "Valor Empenhado;Valor Liquidado;Valor Pago;Valor Restos A Pagar Inscritos;"
                    "Valor Restos A Pagar Cancelados;Valor Restos A Pagar Pagos")


def _favorecido(emenda, ano_mes, documento, nome, natureza, tipo, uf, municipio, valor):
    return ";".join(f'"{c}"' for c in (emenda, "1", "DEPUTADA A", "0001", "Emenda Individual", ano_mes, documento,
                                       nome, natureza, tipo, uf, municipio, valor))


def _emenda(codigo, funcao, acao):
    campos = [codigo, "2025", "Emenda Individual", "1", "DEPUTADA A", "0001", "MÚLTIPLO", "Sem informação", "", "",
              "", "", "10", funcao, "", "", "", "", "", acao, "", "", "1,00", "1,00", "1,00", "0", "0", "0"]
    return ";".join(f'"{c}"' for c in campos)


def _arquivo(tmp_path):
    favorecidos = [
        _favorecido("E1", "202503", "12231796000172", "FUNDO MUNICIPAL DE SAUDE", "Fundo Público da Administração "
                    "Direta Municipal", "Pessoa Jurídica", "RS", "SÃO SEPÉ", "100000,00"),
        _favorecido("E1", "202504", "12231796000172", "FUNDO MUNICIPAL DE SAUDE", "Fundo Público da Administração "
                    "Direta Municipal", "Pessoa Jurídica", "RS", "SÃO SEPÉ", "50000,00"),   # mesma emenda e ano: soma
        _favorecido("E2", "202506", "09537392000105", "FULANA DE TAL 52998224725", "Empresário (Individual)",
                    "Pessoa Jurídica", "RS", "SÃO SEPÉ", "1000,00"),
        _favorecido("E2", "202506", "***.123.456-**", "PESSOA FISICA", "Sem informação", "Pessoa Fisica", "RS",
                    "SÃO SEPÉ", "500,00"),
        _favorecido("E3", "202506", "00000000000191", "BANCO DO BRASIL SA", "Sociedade de Economia Mista",
                    "Pessoa Jurídica", "DF", "BRASÍLIA", "9999999,00"),                    # agente financeiro
        _favorecido("E4", "202601", "87934675000196", "ESTADO DO RS", "Estado ou Distrito Federal",
                    "Pessoa Jurídica", "RS", "PORTO ALEGRE", "200000,00"),
        _favorecido("E5", "202602", "46523015000135", "MUNICIPIO DE EMBU", "Município", "Pessoa Jurídica", "SP",
                    "EMBU", "30000,00"),                                                     # nome antigo
    ]
    caminho = tmp_path / "EmendasParlamentares.zip"
    with zipfile.ZipFile(caminho, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("EmendasParlamentares_PorFavorecido.csv",
                   ("\r\n".join([CABECALHO_FAVORECIDO, *favorecidos]) + "\r\n").encode("latin-1"))
        z.writestr("EmendasParlamentares.csv", ("\r\n".join([
            CABECALHO_EMENDA, _emenda("E1", "Saúde", "ATENCAO BASICA"), _emenda("E2", "Urbanismo", "PAVIMENTACAO"),
            _emenda("E9", "Defesa", "NAO USADA")]) + "\r\n").encode("latin-1"))
    return caminho


def _cadastro():
    return Cadastro({"4319604": Ente("4319604", "São Sepé", "RS", "M", 21551),
                     "43": Ente("43", "Rio Grande do Sul", "RS", "E", 11_000_000),
                     "3515004": Ente("3515004", "Embu das Artes", "SP", "M", 250_000)})


def test_categorias_pela_natureza_juridica():
    assert emendas.categoria("Pessoa Jurídica", "Município") == "governo_municipal"
    assert emendas.categoria("Pessoa Jurídica", "Fundo Público da Administração Direta Municipal") == "governo_municipal"
    assert emendas.categoria("Pessoa Jurídica", "Estado ou Distrito Federal") == "governo_estadual"
    assert emendas.categoria("Pessoa Jurídica", "Associação Privada") == "entidade"
    assert emendas.categoria("Pessoa Jurídica", "Sociedade Empresária Limitada") == "empresa"
    assert emendas.categoria("Pessoa Jurídica", "Sociedade de Economia Mista") is None
    assert emendas.categoria("Pessoa Fisica", "Sem informação") == "pessoa_fisica"
    assert emendas.categoria("Inscrição Genérica", "Sem informação") is None


def test_coleta_soma_por_ente_sem_pessoa_fisica_identificada_e_pula_o_mesmo_arquivo(tmp_path):
    zip_ = _arquivo(tmp_path)
    estado = tmp_path / "estado"
    baixados = []

    def baixar(destino, *, contato):
        baixados.append(destino)
        destino.write_bytes(zip_.read_bytes())
        return destino, "Sat, 10 Oct 2026 02:57:21 GMT"

    r = emendas.coletar(estado, _cadastro(), contato="c@exemplo.org", temporario=tmp_path,
                        data_fn=lambda contato: "Sat, 10 Oct 2026 02:57:21 GMT", baixar_fn=baixar)
    assert (r.baixado, r.entes, r.emendas) == (True, 3, 2)          # descritas: só E1 e E2 estão no arquivo principal
    dados = comum.ler_json(estado / emendas.ARQUIVO)
    sepe = dados["recebido"]["4319604"]
    assert ["2025", "E1", "governo_municipal", "12231796000172", "FUNDO MUNICIPAL DE SAUDE", 150000.0] in sepe
    # Empresa com o CPF do MEI mascarado; pessoa física só com a soma
    assert ["2025", "E2", "empresa", "09537392000105", "FULANA DE TAL ***.982.247-**", 1000.0] in sepe
    assert ["2025", "E2", "pessoa_fisica", None, None, 500.0] in sepe
    assert dados["recebido"]["43"] == [["2026", "E4", "governo_estadual", "87934675000196", "ESTADO DO RS", 200000.0]]
    assert dados["recebido"]["3515004"][0][5] == 30000.0                     # "EMBU" é Embu das Artes
    assert dados["sem_lugar"] == {"2025": 9999999.0}                         # o agente financeiro fica fora
    assert dados["emendas"]["E1"][4:] == ["Saúde", "ATENCAO BASICA"] and "E9" not in dados["emendas"]
    assert "52998224725" not in str(dados) and "123.456" not in str(dados)
    # Mesmo arquivo (mesma data): não baixa de novo
    baixados.clear()
    de_novo = emendas.coletar(estado, _cadastro(), contato="c@exemplo.org",
                              data_fn=lambda contato: "Sat, 10 Oct 2026 02:57:21 GMT", baixar_fn=baixar)
    assert not de_novo.baixado and baixados == [] and de_novo.entes == 3


def test_publica_um_arquivo_por_ente(tmp_path):
    zip_ = _arquivo(tmp_path)
    estado = tmp_path / "estado"
    emendas.coletar(estado, _cadastro(), contato="c@exemplo.org", data_fn=lambda contato: None,
                    baixar_fn=lambda destino, *, contato: (destino.write_bytes(zip_.read_bytes()) and destino, None))
    gravados = {}
    resumo = emendas.publicar(estado, lambda caminho, dados: gravados.setdefault(caminho, dados), gerado_em="x")
    assert resumo["entes"] == 3 and set(gravados) == {"emendas/ente/4319604.json.gz", "emendas/ente/43.json.gz",
                                                      "emendas/ente/3515004.json.gz"}
    sepe = gravados["emendas/ente/4319604.json.gz"]
    assert sepe["tipo"] == "emendas-ente" and set(sepe["emendas"]) == {"E1", "E2"}
    assert sepe["categorias"]["governo_municipal"] == "Governo municipal"
    assert emendas.publicar(tmp_path / "vazio", lambda c, d: None, gerado_em="x") is None
