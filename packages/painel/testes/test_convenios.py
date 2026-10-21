"""Testes dos convênios da União (CGU): por ente, categorias, o que fica de fora e a publicação."""

import zipfile

from lumen_painel import comum, convenios
from lumen_painel.cadastro import Cadastro, Ente

CABECALHO = ("NÚMERO CONVÊNIO;UF;CÓDIGO SIAFI MUNICÍPIO;NOME MUNICÍPIO;SITUAÇÃO CONVÊNIO;NÚMERO ORIGINAL;"
             "NÚMERO PROCESSO DO CONVÊNIO;OBJETO DO CONVÊNIO;CÓDIGO ÓRGÃO SUPERIOR;NOME ÓRGÃO SUPERIOR;"
             "CÓDIGO ÓRGÃO CONCEDENTE;NOME ÓRGÃO CONCEDENTE;CÓDIGO UG CONCEDENTE;NOME UG CONCEDENTE;CÓDIGO CONVENENTE;"
             "TIPO CONVENENTE;NOME CONVENENTE;TIPO ENTE CONVENENTE;TIPO INSTRUMENTO;VALOR CONVÊNIO;VALOR LIBERADO;"
             "DATA PUBLICAÇÃO;DATA INÍCIO VIGÊNCIA;DATA FINAL VIGÊNCIA;VALOR CONTRAPARTIDA;DATA ÚLTIMA LIBERAÇÃO;"
             "VALOR ÚLTIMA LIBERAÇÃO")


def _linha(numero, uf, municipio, situacao, objeto, tipo, codigo, nome, valor, liberado, inicio):
    campos = [numero, uf, "8801", municipio, situacao, "", "", objeto, "36000", "Ministério da Saúde", "", "", "", "",
              codigo, tipo, nome, "", "CONVENIO", valor, liberado, "", inicio, "30/04/2029", "100,00", "", ""]
    return ";".join(f'"{c}"' for c in campos)


LINHAS = [
    _linha("1", "RS", "SAO SEPE", "EM EXECUÇÃO", "Unidades habitacionais", "Administração Pública Municipal",
           "97229181000164", "MUNICIPIO DE SAO SEPE", "2800000,00", "1000,00", "30/04/2026"),
    _linha("2", "RS", "SAO SEPE", "INADIMPLENTE", "Equipamento, contato 123.456.789-09", "Entidades Sem Fins Lucrativos",
           "97227383000177", "ASSOCIACAO HOSPITAL", "420000,00", "420000,00", "02/06/2019"),
    _linha("3", "RS", "SAO SEPE", "CONCLUÍDO", "Bolsa", "Pessoa Física", "***.123.456-**", "FULANO", "5000,00",
           "5000,00", "01/03/2020"),
    _linha("4", "RS", "PORTO ALEGRE", "CONCLUÍDO", "Rodovia", "Administração Pública Estadual ou do Distrito Federal",
           "87934675000196", "ESTADO DO RS", "9000000,00", "9000000,00", "10/01/2018"),
    _linha("5", "RS", "SAO SEPE", "CONVÊNIO ANULADO", "Anulado", "Administração Pública Municipal",
           "97229181000164", "MUNICIPIO DE SAO SEPE", "1,00", "0,00", "01/01/2020"),
    _linha("6", "RS", "SAO SEPE", "CONCLUÍDO", "Antigo", "Administração Pública Municipal",
           "97229181000164", "MUNICIPIO DE SAO SEPE", "1,00", "1,00", "01/01/1998"),
    _linha("7", "RJ", "PARATI", "CONCLUÍDO", "Turismo", "Administração Pública Municipal",
           "29172467000109", "MUNICIPIO DE PARATY", "50000,00", "50000,00", "01/01/2022"),
    _linha("8", "XX", "LUGAR NENHUM", "CONCLUÍDO", "?", "Administração Pública Municipal",
           "11111111000191", "?", "1,00", "1,00", "01/01/2022"),
]


def _arquivo(tmp_path):
    caminho = tmp_path / "20261009_Convenios.zip"
    with zipfile.ZipFile(caminho, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("20261009_Convenios.csv", ("\r\n".join([CABECALHO, *LINHAS]) + "\r\n").encode("latin-1"))
        z.writestr("20261009_Convenios_OrdensBancarias.csv", "x\r\n")
    return caminho


def _cadastro():
    return Cadastro({"4319604": Ente("4319604", "São Sepé", "RS", "M", 21551),
                     "43": Ente("43", "Rio Grande do Sul", "RS", "E", 11_000_000),
                     "3303807": Ente("3303807", "Paraty", "RJ", "M", 45_000)})


def test_convenios_por_ente_sem_pessoa_fisica_identificada(tmp_path):
    zip_ = _arquivo(tmp_path)
    estado = tmp_path / "estado"
    pedidos = []

    def baixar(data, destino, *, contato):
        pedidos.append(data)
        destino.write_bytes(zip_.read_bytes())
        return destino

    r = convenios.coletar(estado, _cadastro(), contato="c@exemplo.org", temporario=tmp_path,
                          data_fn=lambda contato: "20261009", baixar_fn=baixar)
    assert (r.baixado, r.entes, r.convenios, pedidos) == (True, 3, 4, ["20261009"])
    dados = comum.ler_json(estado / convenios.ARQUIVO)
    sepe = dados["convenios"]["4319604"]
    assert [c[0] for c in sepe] == ["2", "1"]                                   # pela data de início
    assert sepe[0][1:3] == ["INADIMPLENTE", "Equipamento, contato ***.456.789-**"]
    assert sepe[1][4:9] == ["governo_municipal", "97229181000164", "MUNICIPIO DE SAO SEPE", 2800000.0, 1000.0]
    assert sepe[1][10:12] == ["2026-04-30", "2029-04-30"]
    assert dados["pessoa_fisica"] == {"4319604": {"2020": 5000.0}}               # só a soma
    assert dados["convenios"]["43"][0][4] == "governo_estadual"                 # o estado vai para a UF
    assert dados["convenios"]["3303807"][0][0] == "7"                           # "PARATI" é Paraty
    assert dados["fora"] == {"anulados_ou_excluidos": 1, "antes_de_2001": 1, "sem_lugar": 1}
    assert "FULANO" not in str(dados) and "123.456.789-09" not in str(dados)
    # Mesmo arquivo: não baixa de novo
    pedidos.clear()
    de_novo = convenios.coletar(estado, _cadastro(), contato="c@exemplo.org",
                                data_fn=lambda contato: "20261009", baixar_fn=baixar)
    assert not de_novo.baixado and pedidos == [] and de_novo.convenios == 4


def test_publica_um_arquivo_comprimido_por_ente(tmp_path):
    zip_ = _arquivo(tmp_path)
    estado = tmp_path / "estado"
    convenios.coletar(estado, _cadastro(), contato="c@exemplo.org", data_fn=lambda contato: "20261009",
                      baixar_fn=lambda data, destino, *, contato: destino.write_bytes(zip_.read_bytes()) and destino)
    gravados = {}
    resumo = convenios.publicar(estado, lambda caminho, dados: gravados.setdefault(caminho, dados), gerado_em="x")
    assert resumo["entes"] == 3 and resumo["convenios"] == 4
    assert set(gravados) == {"convenios/ente/431.json.gz", "convenios/ente/43.json.gz", "convenios/ente/330.json.gz"}
    grupo = gravados["convenios/ente/431.json.gz"]
    assert grupo["tipo"] == "convenios-entes" and grupo["entes"]["4319604"]["pessoa_fisica"] == {"2020": 5000.0}
    assert grupo["categorias"]["entidade"] == "Entidade sem fins lucrativos"
    assert convenios.publicar(tmp_path / "vazio", lambda c, d: None, gerado_em="x") is None
