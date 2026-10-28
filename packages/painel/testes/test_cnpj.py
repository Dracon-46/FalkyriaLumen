"""Testes da base de CNPJ da Receita: filtro pelos fornecedores, o que entra de cada arquivo e a publicação."""

import io
import json
import urllib.error
import zipfile

import pytest

from lumen_painel import cnpj, comum

FORNECEDOR = "00000000000191"          # Banco do Brasil, matriz (dado público de pessoa jurídica)
MEI = "12345678000195"                 # fictício
FORA = "99999999000199"                # não é fornecedor no estado


def _linha(*campos: str) -> str:
    return ";".join(f'"{c}"' for c in campos)


def _estabelecimento(cnpj14: str, nome_fantasia: str, situacao: str, cnae: str, secundarios: str, uf: str,
                     municipio: str, especial: str = "") -> str:
    # 30 colunas, como na Receita; telefone e e-mail preenchidos para conferir que ficam de fora
    return _linha(cnpj14[:8], cnpj14[8:12], cnpj14[12:], "1", nome_fantasia, situacao, "20050103", "00", "", "",
                  "19660801", cnae, secundarios, "RUA", "DIREITA", "100", "", "CENTRO", "70000000", uf, municipio,
                  "61", "33333333", "", "", "", "", "contato@exemplo.org", especial, "20240101" if especial else "")


ARQUIVOS = {
    "Empresas0.zip": [
        _linha("00000000", "BANCO DO BRASIL SA", "2038", "10", "120000000000,00", "05", ""),
        _linha("12345678", "FULANA DE TAL 52998224725", "2135", "50", "5000,00", "01", ""),
        _linha("99999999", "OUTRA EMPRESA LTDA", "2062", "49", "1,00", "01", ""),
    ],
    "Estabelecimentos0.zip": [
        _estabelecimento(FORNECEDOR, "DIRECAO GERAL", "02", "6422100", "6499999,6611803", "DF", "9701"),
        _estabelecimento("00000000000272", "AGENCIA", "02", "6422100", "", "DF", "9701"),   # filial, não pedida
        _estabelecimento(MEI, "", "08", "4321500", "", "RS", "8801", "RECUPERACAO JUDICIAL"),
        _estabelecimento(FORA, "", "02", "4321500", "", "SP", "7107"),
    ],
    "Socios0.zip": [
        _linha("00000000", "1", "UNIAO FEDERAL", "00394460000141", "22", "19660801", "", "***000000**", "", "00", "0"),
        _linha("12345678", "2", "FULANA DE TAL", "***982247**", "50", "20200101", "", "***000000**", "", "00", "5"),
        _linha("12345678", "3", "JOHN DOE", "***999999**", "49", "20210101", "249", "***111111**", "REPR", "05", "0"),
        _linha("99999999", "2", "NAO PEDIDO", "***123456**", "49", "20200101", "", "***000000**", "", "00", "4"),
    ],
    "Simples.zip": [
        _linha("12345678", "S", "20200101", "00000000", "S", "20200101", "00000000"),
        _linha("00000000", "N", "00000000", "00000000", "N", "00000000", "00000000"),
    ],
    "Cnaes.zip": [_linha("6422100", "Bancos múltiplos, com carteira comercial"), _linha("6499999", "Outras atividades"),
                  _linha("6611803", "Bolsa"), _linha("4321500", "Instalação e manutenção elétrica"),
                  _linha("0111301", "Cultivo de arroz")],
    "Naturezas.zip": [_linha("2038", "Sociedade de Economia Mista"), _linha("2135", "Empresário (Individual)")],
    "Qualificacoes.zip": [_linha("22", "Sócio"), _linha("50", "Empresário"), _linha("49", "Sócio-Administrador")],
    "Motivos.zip": [_linha("00", "Sem motivo"), _linha("01", "Extinção por encerramento liquidação voluntária")],
    "Municipios.zip": [_linha("9701", "BRASILIA"), _linha("8801", "PORTO ALEGRE"), _linha("7107", "SAO PAULO")],
    "Paises.zip": [_linha("249", "ESTADOS UNIDOS")],
}


@pytest.fixture
def receita(tmp_path):
    """Os ZIPs da Receita num diretório e as funções de listar e baixar que os servem."""
    origem = tmp_path / "receita"
    origem.mkdir()
    for nome, linhas in ARQUIVOS.items():
        with zipfile.ZipFile(origem / nome, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr(f"K3241.{nome}.CSV", ("\r\n".join(linhas) + "\r\n").encode("latin-1"))
    baixados = []

    def listar(caminho, *, contato):
        if caminho == "":
            return [("2026-09", None), ("2026-10", None), ("cnpj.tar.gz", 1)]
        return [(n, (origem / n).stat().st_size) for n in sorted(ARQUIVOS)]

    def baixar(caminho, destino, *, contato):
        baixados.append(caminho)
        destino.write_bytes((origem / caminho.split("/")[-1]).read_bytes())
        return destino

    return listar, baixar, baixados


def _estado(tmp_path, fornecedores):
    estado = tmp_path / "estado"
    colunas = ["chave", "orgao", "ente", "uf", "municipio", "tipo_pessoa", "fornecedor_cnpj", "fornecedor_nome",
               "valor_global", "data_assinatura", "processo", "instrumento", "objeto"]
    contratos = [["k", "o", None, None, None, "PJ", f, "X", 1.0, None, None, None, None] for f in fornecedores]
    contratos.append(["k2", "o", None, None, None, "PF", None, None, 1.0, None, None, None, None])
    comum.gravar_json(estado / "contratacoes-2026-10-19.json.gz",
                      {"versao": 1, "colunas": {"contratos": colunas}, "contratos": contratos}, comprimir=True)
    return estado


def test_coleta_so_os_fornecedores_e_o_que_o_adr_043_deixa_entrar(tmp_path, receita):
    listar, baixar, baixados = receita
    estado = _estado(tmp_path, [FORNECEDOR, MEI])
    r = cnpj.coletar(estado, contato="c@exemplo.org", temporario=tmp_path, listar_fn=listar, baixar_fn=baixar)
    assert (r.mes, r.pedidos, r.achados, r.pulada) == ("2026-10", 2, 2, None)
    assert baixados[0].startswith("2026-10/") and len(r.arquivos) == len(ARQUIVOS)
    assert not list(tmp_path.glob("cnpj-*"))                       # o temporário foi apagado
    dados = comum.ler_json(estado / cnpj.ARQUIVO)
    assert set(dados["empresas"]) == {FORNECEDOR, MEI}
    texto = json.dumps(dados, ensure_ascii=False)
    # O CPF do MEI sai mascarado; o CPF parcial dos sócios, o telefone, o e-mail e o endereço não entram
    assert "52998224725" not in texto and "FULANA DE TAL ***.982.247-**" in texto
    assert "982247" not in texto.replace("***.982.247-**", "") and "33333333" not in texto
    assert "contato@exemplo.org" not in texto and "DIREITA" not in texto and "NAO PEDIDO" not in texto
    mei = dados["empresas"][MEI]
    assert mei["simples"]["mei"] is True and mei["estabelecimento"]["situacao_especial"] == "RECUPERACAO JUDICIAL"
    assert [s["tipo"] for s in mei["socios"]] == ["PF", "estrangeiro"]
    assert mei["socios"][1] == {"tipo": "estrangeiro", "nome": "JOHN DOE", "qualificacao": "49", "desde": "2021-01-01",
                                "pais": "249"}
    bb = dados["empresas"][FORNECEDOR]
    assert bb["empresa"]["capital_social"] == 120000000000.0
    assert bb["socios"] == [{"tipo": "PJ", "nome": "UNIAO FEDERAL", "qualificacao": "22", "desde": "1966-08-01",
                             "cnpj": "00394460000141"}]
    assert bb["estabelecimento"]["cnaes_secundarios"] == ["6499999", "6611803"]
    # Só as tabelas usadas
    assert "0111301" not in dados["tabelas"]["cnae"] and dados["tabelas"]["municipio"] == {
        "9701": "BRASILIA", "8801": "PORTO ALEGRE"}
    # De novo, com o mesmo mês e os mesmos fornecedores: pula sem baixar
    baixados.clear()
    de_novo = cnpj.coletar(estado, contato="c@exemplo.org", listar_fn=listar, baixar_fn=baixar)
    assert de_novo.pulada and baixados == [] and de_novo.achados == 2


def test_publica_por_prefixo_comprimido_com_os_codigos_e_a_tabela_dos_nomes(tmp_path, receita):
    listar, baixar, _ = receita
    estado = _estado(tmp_path, [FORNECEDOR, MEI, "55555555000100"])   # um CNPJ que a Receita não tem
    cnpj.coletar(estado, contato="c@exemplo.org", listar_fn=listar, baixar_fn=baixar)
    gravados = {}
    resumo = cnpj.publicar(estado, lambda caminho, dados: gravados.setdefault(caminho, dados),
                           gerado_em="2026-10-21T12:00:00Z")
    assert resumo["mes"] == "2026-10" and resumo["empresas"] == 2
    assert set(gravados) == {"cnpj/tabelas.json", "cnpj/000.json.gz", "cnpj/123.json.gz"}
    bb = gravados["cnpj/000.json.gz"]["empresas"][FORNECEDOR]
    assert (bb["situacao"], bb["porte"], bb["municipio"], bb["natureza"]) == ("02", "05", "9701", "2038")
    assert bb["cnae_principal"] == "6422100" and "motivo" not in bb and "situacao_especial" not in bb
    assert bb["socios"] == [{"tipo": "PJ", "nome": "UNIAO FEDERAL", "qualificacao": "22", "desde": "1966-08-01",
                             "cnpj": "00394460000141"}]
    tabelas = gravados["cnpj/tabelas.json"]["tabelas"]
    assert tabelas["natureza"]["2038"] == "Sociedade de Economia Mista" and tabelas["situacao"]["02"] == "Ativa"
    assert tabelas["porte"]["05"] == "Demais" and tabelas["pais"]["249"] == "ESTADOS UNIDOS"
    mei = gravados["cnpj/123.json.gz"]["empresas"][MEI]
    assert mei["simples"] == {"simples": True, "simples_desde": "2020-01-01", "mei": True, "mei_desde": "2020-01-01"}
    assert cnpj.publicar(tmp_path / "vazio", lambda c, d: None, gerado_em="x") is None


def test_listar_le_o_webdav_e_baixar_retoma(tmp_path, monkeypatch):
    xml = b"""<?xml version="1.0"?><d:multistatus xmlns:d="DAV:">
      <d:response><d:href>/public.php/webdav/2026-10/</d:href><d:propstat><d:prop/></d:propstat></d:response>
      <d:response><d:href>/public.php/webdav/2026-10/Cnaes.zip</d:href><d:propstat><d:prop>
        <d:getcontentlength>22078</d:getcontentlength></d:prop></d:propstat></d:response>
      </d:multistatus>"""
    pedidos = []
    respostas = [urllib.error.URLError("caiu"), io.BytesIO(b"resto")]

    class Resposta(io.BytesIO):
        status = 206

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def urlopen(pedido, timeout):
        pedidos.append(pedido)
        if pedido.get_method() == "PROPFIND":
            return Resposta(xml)
        r = respostas.pop(0)
        if isinstance(r, Exception):
            raise r
        return Resposta(r.read())

    monkeypatch.setattr(cnpj.urllib.request, "urlopen", urlopen)
    assert cnpj.listar("2026-10", contato="c@exemplo.org") == [("Cnaes.zip", 22078)]
    assert pedidos[0].headers["Depth"] == "1" and pedidos[0].full_url.endswith("/webdav/2026-10/")
    destino = tmp_path / "x.zip"
    destino.write_bytes(b"come")                                   # já havia um pedaço
    cnpj.baixar("2026-10/x.zip", destino, contato="c@exemplo.org", esperar=lambda s: None)
    assert destino.read_bytes() == b"comeresto"
    assert pedidos[-1].headers["Range"] == "bytes=4-"
    assert cnpj.mes_mais_recente([("2026-09", None), ("2026-10", None), ("cnpj.tar.gz", 1)]) == "2026-10"


def test_listar_tenta_de_novo_quando_a_resposta_vem_vazia(monkeypatch):
    xml = (b'<?xml version="1.0"?><d:multistatus xmlns:d="DAV:"><d:response><d:href>/public.php/webdav/2026-10/'
           b'</d:href></d:response></d:multistatus>')
    respostas = [b"", xml]

    class Resposta(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(cnpj.urllib.request, "urlopen", lambda pedido, timeout: Resposta(respostas.pop(0)))
    esperas = []
    assert cnpj.listar("", contato="c@exemplo.org", esperar=esperas.append) == [("2026-10", None)]
    assert esperas == [10]
    respostas[:] = [b"", b"", b"", b""]
    with pytest.raises(cnpj.ElementTree.ParseError):
        cnpj.listar("", contato="c@exemplo.org", esperar=esperas.append)
