"""Regra J-01 em modo silencioso: contratos do painel cruzados com as sanções da CGU."""

import gzip
import json
from datetime import date

import pytest

from lumen_deteccao import cli, j01
from lumen_deteccao.j01 import (
    A_CONFERIR,
    FORA_DO_ALCANCE,
    MESMA_ESFERA,
    MESMO_ORGAO,
    NAO_INFORMADO,
    TODAS_AS_ESFERAS,
    Municipios,
    alcance,
    cruzar,
    impede_contratar,
    indice_por_cnpj,
    retrato_mais_recente,
    vigente,
)

CNPJ = "14310577000104"
COLUNAS = ["chave", "orgao", "ente", "uf", "municipio", "tipo_pessoa", "fornecedor_cnpj", "fornecedor_nome",
           "valor_global", "data_assinatura", "processo", "instrumento", "objeto"]
MUNICIPIOS = Municipios([("4311403", "RS", "Lajeado"), ("4311429", "RS", "Lajeado do Bugre"),
                         ("4314902", "RS", "Porto Alegre")])


def _sancao(**troca):
    base = {"cadastro": "CEIS", "chave_origem": "1", "data_referencia": "2026-10-15", "tipo_pessoa": "PJ",
            "documento": CNPJ, "categoria": "Impedimento/proibição de contratar com prazo determinado",
            "data_inicio": "2026-01-01", "data_fim": "2027-01-01", "abrangencia": "Todas as Esferas em todos os Poderes",
            "orgao_sancionador": "Prefeitura Municipal de Lajeado - RS", "esfera_orgao_sancionador": "municipal",
            "uf_orgao_sancionador": "RS", "fundamentacao_legal": "LEI 14133 - ART. 156" + " X" * 400}
    base.update(troca)
    return base


def _contrato(**troca):
    base = {"chave": "87297982000110-2-000123/2026", "orgao": "87297982000110", "ente": "4311403", "uf": "RS",
            "municipio": "4311403", "tipo_pessoa": "PJ", "fornecedor_cnpj": CNPJ, "fornecedor_nome": "EMPRESA",
            "valor_global": 1000.0, "data_assinatura": "2026-03-10", "processo": None, "instrumento": "Contrato",
            "objeto": "Serviço"}
    base.update(troca)
    return [base[c] for c in COLUNAS]


def _dia(*contratos, dia="2026-03-11", esfera="M", razao="MUNICIPIO DE LAJEADO"):
    return {"versao": 1, "dia": dia, "colunas": {"contratos": COLUNAS},
            "orgaos": {"87297982000110": [razao, esfera, "4311403"]}, "contratos": list(contratos)}


# ------------------------------------------------------------------ peças

@pytest.mark.parametrize("categoria,esperado", [
    ("Impedimento/proibição de contratar com prazo determinado", True),
    ("Suspensão", True),
    ("Declaração de Inidoneidade sem prazo determinado", True),
    ("Suspensão/Interdição das atividades com prazo determinado", False),
    ("Multa", False), ("Demissão", False), (None, False),
])
def test_impede_contratar(categoria, esperado):
    assert impede_contratar(categoria) is esperado


def test_vigente_na_assinatura():
    s = _sancao(data_inicio="2026-01-01", data_fim="2026-06-30")
    assert vigente(s, date(2026, 1, 1)) and vigente(s, date(2026, 6, 30))
    assert not vigente(s, date(2025, 12, 31)) and not vigente(s, date(2026, 7, 1))
    assert vigente(_sancao(data_fim=None), date(2099, 1, 1))
    assert not vigente(_sancao(data_inicio=None), date(2026, 3, 1))


@pytest.mark.parametrize("troca,esfera,uf,municipio,orgao,esperado", [
    ({}, "uniao", "SP", None, None, TODAS_AS_ESFERAS),
    ({"abrangencia": None}, "municipal", "RS", "4311403", None, NAO_INFORMADO),
    ({"abrangencia": "Em todos os Poderes da Esfera do órgão sancionador"}, "municipal", "RS", "4311403", None,
     MESMA_ESFERA),
    ({"abrangencia": "Em todos os Poderes da Esfera do órgão sancionador"}, "municipal", "RS", "4314902", None,
     FORA_DO_ALCANCE),
    ({"abrangencia": "Em todos os Poderes da Esfera do órgão sancionador",
      "orgao_sancionador": "Secretaria Municipal de Obras"}, "municipal", "RS", "4311403", None, A_CONFERIR),
    ({"abrangencia": "Em todos os Poderes da Esfera do órgão sancionador"}, "municipal", "SC", "4205407", None,
     FORA_DO_ALCANCE),
    ({"abrangencia": "Em todos os Poderes da Esfera do órgão sancionador"}, "estadual", "RS", None, None,
     FORA_DO_ALCANCE),
    ({"abrangencia": "Na Esfera e no Poder do órgão sancionador", "esfera_orgao_sancionador": "estadual"},
     "estadual", "RS", None, None, MESMA_ESFERA),
    ({"abrangencia": "Na Esfera e no Poder do órgão sancionador", "esfera_orgao_sancionador": "estadual",
      "uf_orgao_sancionador": None}, "estadual", "RS", None, None, A_CONFERIR),
    ({"abrangencia": "Em todos os Poderes da Esfera do órgão sancionador", "esfera_orgao_sancionador": "uniao",
      "uf_orgao_sancionador": "DF"}, "uniao", "RJ", None, None, MESMA_ESFERA),
    ({"abrangencia": "Em todos os Poderes da Esfera do órgão sancionador", "esfera_orgao_sancionador": "distrital",
      "uf_orgao_sancionador": "DF"}, "estadual", "DF", None, None, A_CONFERIR),
    ({"abrangencia": "Em todos os Poderes da Esfera do órgão sancionador", "esfera_orgao_sancionador": None},
     "municipal", "RS", "4311403", None, A_CONFERIR),
    ({"abrangencia": "No órgão sancionador", "esfera_orgao_sancionador": "uniao",
      "orgao_sancionador": "MINISTERIO DA SAUDE"}, "uniao", "RJ", None, "MINISTÉRIO DA SAÚDE", MESMO_ORGAO),
    ({"abrangencia": "No órgão sancionador", "esfera_orgao_sancionador": "uniao",
      "orgao_sancionador": "MINISTERIO DA SAUDE"}, "uniao", "RJ", None, "MINISTERIO DA FAZENDA", A_CONFERIR),
    ({"abrangencia": "No órgão sancionador", "esfera_orgao_sancionador": "uniao"}, "municipal", "RS", "4311403",
     None, FORA_DO_ALCANCE),
    ({"abrangencia": "Abrangência nova da CGU"}, "uniao", "RJ", None, None, A_CONFERIR),
])
def test_alcance(troca, esfera, uf, municipio, orgao, esperado):
    s = _sancao(**troca)
    assert alcance(s, esfera, uf, municipio_contratante=municipio, orgao_contratante=orgao,
                   municipios=MUNICIPIOS) == esperado


def test_sem_cadastro_de_municipios_o_municipal_fica_a_conferir():
    s = _sancao(abrangencia="Em todos os Poderes da Esfera do órgão sancionador")
    assert alcance(s, "municipal", "RS", municipio_contratante="4311403") == A_CONFERIR


def test_municipio_citado_por_palavra_inteira():
    assert MUNICIPIOS.citados("PREFEITURA MUNICIPAL DE LAJEADO - RS", "rs") == {"4311403"}
    assert MUNICIPIOS.citados("Prefeitura de Lajeado do Bugre", "RS") == {"4311403", "4311429"}
    assert MUNICIPIOS.citados("Prefeitura de Lajeadinho", "RS") == set()
    assert MUNICIPIOS.citados(None, None) == set()


def test_cadastro_de_municipios_que_acompanha_o_lumen():
    m = Municipios.do_cadastro()
    assert m.citados("Prefeitura Municipal de Itapetininga (SP)", "SP") == {"3522307"}


def test_retrato_mais_recente_e_indice():
    antiga = _sancao(chave_origem="9", data_referencia="2026-10-14")
    sancoes = [antiga, _sancao(), _sancao(chave_origem="2", categoria="Multa"),
               _sancao(chave_origem="3", cadastro="CEPIM", data_referencia="2026-10-14"),
               _sancao(chave_origem="4", tipo_pessoa="PF", documento="***.456.789-**")]
    recentes = retrato_mais_recente(sancoes)
    assert antiga not in recentes and len(recentes) == 4
    indice = indice_por_cnpj(sancoes)
    assert list(indice) == [CNPJ] and [s["chave_origem"] for s in indice[CNPJ]] == ["1"]


# ------------------------------------------------------------------ cruzamento

def test_cruzar_conta_e_classifica():
    dias = [_dia(_contrato(), _contrato(chave="sem-cnpj", fornecedor_cnpj=None, tipo_pessoa="PF"),
                 _contrato(chave="sem-data", data_assinatura=None), _contrato(chave="antes", data_assinatura="2025-12-01"),
                 _contrato(chave="outro", fornecedor_cnpj="11222333000181")),
            _dia(_contrato(chave="poa", municipio="4314902"), dia="2026-03-12")]
    sancoes = [_sancao(), _sancao(chave_origem="2", abrangencia="Em todos os Poderes da Esfera do órgão sancionador")]
    r = cruzar(dias, sancoes, MUNICIPIOS)
    assert (r.contratos, r.contratos_com_cnpj, r.sem_data_assinatura) == (6, 5, 1)
    assert r.dias == ["2026-03-11", "2026-03-12"] and r.retratos == {"CEIS": "2026-10-15"}
    assert r.fora_do_alcance == 1   # a sanção de Lajeado não alcança o contrato de Porto Alegre
    assert [(c["contrato"]["chave"], c["alcance"]) for c in r.coincidencias] == [
        ("87297982000110-2-000123/2026", TODAS_AS_ESFERAS), ("poa", TODAS_AS_ESFERAS),
        ("87297982000110-2-000123/2026", MESMA_ESFERA)]
    c = r.coincidencias[0]
    assert c["contrato"]["orgao"] == "MUNICIPIO DE LAJEADO" and c["contrato"]["esfera"] == "municipal"
    assert c["contrato"]["link_pncp"].startswith("https://pncp.gov.br/app/contratos/87297982000110/2026/")
    assert len(c["sancao"]["fundamentacao_legal"]) <= j01.LIMITE_TEXTO and c["sancao"]["fundamentacao_legal"].endswith("…")
    assert r.por_alcance()[TODAS_AS_ESFERAS] == 2 and r.por_alcance()[A_CONFERIR] == 0


def test_resumo_so_tem_contagens_e_json_tem_o_detalhe():
    r = cruzar([_dia(_contrato())], [_sancao()], MUNICIPIOS)
    resumo = r.resumo_markdown()
    assert "EMPRESA" not in resumo and "LAJEADO" not in resumo.upper() and CNPJ not in resumo
    assert "Coincidências para análise: 1, de 1 fornecedores" in resumo
    completo = r.para_json(gerado_em="2026-10-16T12:00:00+00:00")
    assert completo["regra"] == "J-01" and completo["modo"] == "silencioso"
    assert completo["dias_de_contratos"] == {"quantidade": 1, "de": "2026-03-11", "ate": "2026-03-11"}
    assert completo["fornecedores_distintos"] == 1 and completo["coincidencias"][0]["fornecedor"]["cnpj"] == CNPJ


def _gravar_dia(pasta, dados, nome=None):
    caminho = pasta / (nome or f"contratacoes-{dados['dia']}.json.gz")
    caminho.write_bytes(gzip.compress(json.dumps(dados).encode()))
    return caminho


def test_ler_dias(tmp_path):
    _gravar_dia(tmp_path, _dia(dia="2026-03-12"))
    _gravar_dia(tmp_path, _dia(dia="2026-03-11"))
    (tmp_path / "contratacoes-2026-03-13.json.gz").write_bytes(b"")   # marcador vazio do fluxo
    assert [d["dia"] for d in j01.ler_dias(tmp_path)] == ["2026-03-11", "2026-03-12"]
    _gravar_dia(tmp_path, {"versao": 2, "dia": "2026-03-14"})
    with pytest.raises(ValueError, match="versão 2"):
        list(j01.ler_dias(tmp_path))


# ------------------------------------------------------------------ linha de comando

def _silver_com_sancoes(raiz, *sancoes):
    pasta = raiz / "silver" / "sancao" / "exercicio=NA" / "uf=NA"
    pasta.mkdir(parents=True)
    linhas = [json.dumps({**s, "id": s["chave_origem"], "_coletado_em": "2026-10-16T00:00:00+00:00"}) for s in sancoes]
    (pasta / "reg1.jsonl").write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return raiz / "silver"


def test_cli_j01(tmp_path, capsys, monkeypatch):
    estado = tmp_path / "estado"
    estado.mkdir()
    _gravar_dia(estado, _dia(_contrato()))
    silver = _silver_com_sancoes(tmp_path, _sancao())
    enviados = []
    monkeypatch.setattr(cli, "_enviar_ao_privado", lambda corpo, chave, config: enviados.append(chave) or chave)
    resumo = tmp_path / "resumo.md"
    saida = tmp_path / "rel" / "j01.json.gz"
    assert cli.main(["j01", "--estado", str(estado), "--silver", str(silver), "--saida", str(saida),
                     "--resumo", str(resumo), "--privado"]) == 0
    contagens = json.loads(capsys.readouterr().out)
    assert contagens["coincidencias"] == 1 and "coincidencias" not in json.dumps(contagens["por_alcance"])
    assert enviados == ["deteccao/j01/ultimo.json.gz"]
    assert json.loads(gzip.decompress(saida.read_bytes()))["coincidencias"][0]["alcance"] == TODAS_AS_ESFERAS
    assert "Regra J-01" in resumo.read_text(encoding="utf-8")


def test_cli_j01_sem_sancoes_ou_sem_dias(tmp_path, capsys):
    estado = tmp_path / "estado"
    estado.mkdir()
    assert cli.main(["j01", "--estado", str(estado), "--silver", str(tmp_path / "vazia")]) == 2
    assert "não tem sanções" in capsys.readouterr().err
    silver = _silver_com_sancoes(tmp_path, _sancao())
    assert cli.main(["j01", "--estado", str(estado), "--silver", str(silver)]) == 2
    assert "contratacoes-" in capsys.readouterr().err


def test_cli_j01_usa_a_silver_da_configuracao(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("LUMEN_CONTATO", "a@b.org")
    monkeypatch.setenv("LUMEN_DADOS", str(tmp_path))
    _silver_com_sancoes(tmp_path, _sancao())
    estado = tmp_path / "estado"
    estado.mkdir()
    _gravar_dia(estado, _dia(_contrato()))
    from lumen_orquestracao.cli import main
    assert main(["--config", str(tmp_path / "x.toml"), "deteccao", "j01", "--estado", str(estado)]) == 0
    assert json.loads(capsys.readouterr().out)["coincidencias"] == 1


def test_envio_ao_privado_usa_o_bucket_de_estado(monkeypatch):
    from lumen_eleicoes import configuracao as ce
    from lumen_ingestao import s3
    gravados = []
    pub = ce.ConfiguracaoPublicacao(endpoint="https://x.example", bucket="publico", chave_acesso="a",
                                    chave_secreta="b", bucket_estado="privado", regiao="sa-east-1")
    monkeypatch.setattr(ce, "carregar_publicacao", lambda caminho=None: pub)
    monkeypatch.setattr(s3.ClienteS3, "gravar", lambda self, chave, corpo, **kw: gravados.append((self.bucket, chave, kw)))
    assert cli._enviar_ao_privado(b"x", "deteccao/j01/a.json.gz", None) == "privado/deteccao/j01/a.json.gz"
    assert gravados[0][:2] == ("privado", "deteccao/j01/a.json.gz") and gravados[0][2]["sem_sobrescrever"] is False
