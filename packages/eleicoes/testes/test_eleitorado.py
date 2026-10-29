"""Eleitorado (ADR-055): perfil, comparecimento por perfil e seções, do recorte real de Borá (SP) a arquivos.

Os recortes em ``testes/fixtures/tse/eleitorado`` são as linhas de Borá (SP), o menor município do país, dos
arquivos de 2026 do TSE, com as colunas sensíveis (raça ou cor, deficiência, identidade de gênero, nome
social, povos indígenas e quilombolas, Libras) trocadas por "não informado": o Lumen não as lê nem as publica.
"""

from __future__ import annotations

import csv
import gzip
import io
import json
import tarfile
import zipfile
from pathlib import Path

from lumen_eleicoes import eleitorado as el
from lumen_eleicoes import referencias
from lumen_eleicoes.transferencia import Manifesto

FIX = Path(__file__).resolve().parents[3] / "testes" / "fixtures" / "tse" / "eleitorado"
PERFIL = FIX / "perfil_eleitorado_2026_SP_recorte.csv"
COMPARECIMENTO = FIX / "perfil_comparecimento_abstencao_2026_SP_recorte.csv"
LOCAIS = FIX / "eleitorado_local_votacao_2026_SP_recorte.csv"
BORA_TSE, BORA_IBGE = "62430", "3507209"


def _soma(caminho: Path, coluna: str) -> int:
    with open(caminho, encoding="latin-1", newline="") as f:
        return sum(int(linha[coluna]) for linha in csv.DictReader(f, delimiter=";"))


def _zip(caminho: Path, arquivos: dict[str, Path]) -> Path:
    with zipfile.ZipFile(caminho, "w", zipfile.ZIP_DEFLATED) as zf:
        for nome, origem in arquivos.items():
            zf.write(origem, nome)
        zf.writestr("leiame.pdf", b"%PDF-1.4")
    return caminho


def test_rotulo_e_ordem_das_categorias():
    assert el.rotulo("ENSINO MÉDIO  COMPLETO") == "Ensino médio completo"
    assert el.rotulo("30 a 34 anos") == "30 a 34 anos"
    assert el.rotulo("Inválido") == el.rotulo("INVÁLIDA") == "Inválida"     # o mesmo nos dois arquivos
    p = el.Perfil(eleitores=6)
    p.caracteristicas["faixa_etaria"].update({(-3, "Inválida"): 1, (2529, "25 a 29 anos"): 2, (1600, "16 anos"): 3})
    p.caracteristicas["genero"].update({(0, "Não informado"): 1, (4, "Feminino"): 3, (2, "Masculino"): 2})
    j = el.perfil_json(p)
    assert j["faixa_etaria"] == [["16 anos", 3], ["25 a 29 anos", 2], ["Inválida", 1]]   # inválida no fim
    assert j["genero"] == [["Masculino", 2], ["Feminino", 3], ["Não informado", 1]]
    assert j["escolaridade"] == [] and j["estado_civil"] == []


def test_perfil_do_recorte_soma_o_total_em_cada_caracteristica():
    with open(PERFIL, "rb") as f:
        zonas = el.ler_perfil(f)
    assert list(zonas) == [("sp", BORA_TSE, "12")]
    p = zonas[("sp", BORA_TSE, "12")]
    assert p.eleitores == _soma(PERFIL, "QT_ELEITORES") and 0 < p.biometria <= p.eleitores
    j = el.perfil_json(p)
    for nome in ("genero", "faixa_etaria", "escolaridade", "estado_civil"):
        assert sum(n for _, n in j[nome]) == p.eleitores, nome
    assert {r for r, _ in j["genero"]} <= {"Masculino", "Feminino", "Não informado"}
    assert "raca" not in json.dumps(j) and "Parda" not in json.dumps(j)


def test_comparecimento_do_recorte_por_turno_e_caracteristica():
    with open(COMPARECIMENTO, "rb") as f:
        zonas = el.ler_comparecimento(f)
    c = zonas[(("sp", BORA_TSE, "12"), 1)]
    assert c.aptos == _soma(COMPARECIMENTO, "QT_APTOS") and c.aptos == c.comparecimento + c.abstencao
    t = el.turnos_json({1: c})["1"]
    assert sum(a for _, a, _ in t["escolaridade"]) == c.aptos and sum(v for _, _, v in t["genero"]) == c.comparecimento


def test_formato_antigo_com_qt_eleitores_perfil():
    csv_2018 = ('"SG_UF";"CD_MUNICIPIO";"NR_ZONA";"CD_GENERO";"DS_GENERO";"CD_FAIXA_ETARIA";"DS_FAIXA_ETARIA";'
                '"QT_ELEITORES_PERFIL";"QT_ELEITORES_BIOMETRIA"\r\n'
                '"SP";"62430";"12";"4";"FEMININO";"1600";"16 anos";"3";"2"\r\n'
                '"SP";"62430";"0";"4";"FEMININO";"1600";"16 anos";"9";"9"\r\n')        # zona 0: fica de fora
    zonas = el.ler_perfil(io.BytesIO(csv_2018.encode("latin-1")))
    p = zonas[("sp", BORA_TSE, "12")]
    assert (p.eleitores, p.biometria) == (3, 2) and el.perfil_json(p)["genero"] == [["Feminino", 3]]


def test_secoes_so_do_primeiro_turno_com_o_nome_do_local():
    with open(LOCAIS, "rb") as f:
        secoes, nomes = el.ler_secoes(f)
    lista = secoes[("sp", BORA_TSE)]
    assert sum(s.eleitores for s in lista) == sum(
        int(r["QT_ELEITOR_SECAO"]) for r in csv.DictReader(open(LOCAIS, encoding="latin-1", newline=""), delimiter=";")
        if r["NR_TURNO"] == "1")
    assert all(f"{s.zona}-{s.local}" in nomes[("sp", BORA_TSE)] for s in lista)


def _ler_gz(caminho: Path) -> dict:
    return json.loads(gzip.decompress(caminho.read_bytes()))


def test_grava_brasil_uf_e_grupo_comprimidos_e_apaga_o_que_sobrou(tmp_path):
    perfil = _zip(tmp_path / "perfil.zip", {"perfil_eleitorado_2026_SP.csv": PERFIL})
    comp = _zip(tmp_path / "comp.zip", {"perfil_comparecimento_abstencao_2026_SP.csv": COMPARECIMENTO})
    locais = _zip(tmp_path / "locais.zip", {"eleitorado_local_votacao_2026_SP.csv": LOCAIS})
    sobra = tmp_path / "site" / "eleitorado" / "2026" / "mu" / "999.json.gz"
    sobra.parent.mkdir(parents=True)
    sobra.write_bytes(b"")
    manifesto = Manifesto(url="https://cdn.tse.jus.br/x.zip", arquivo="perfil.zip", tamanho=1, sha256="ab",
                          etag=None, ultima_modificacao=None, baixado_em="2026-10-29T00:00:00+00:00")
    r = el.gravar_eleitorado(2026, tmp_path / "site", referencias.cadastro_embutido(), perfil=perfil,
                             comparecimento=comp, locais=locais, manifestos={"perfil": manifesto})
    total = _soma(PERFIL, "QT_ELEITORES")
    assert (r.eleitores, r.ufs, r.municipios, r.zonas, r.turnos, r.sem_cadastro) == (total, 1, 1, 1, [1], [])
    d = tmp_path / "site" / "eleitorado" / "2026"
    assert sorted(p.relative_to(d).as_posix() for p in d.rglob("*.gz")) == ["br.json.gz", "mu/072.json.gz",
                                                                            "uf-sp.json.gz"]
    assert el.grupo(BORA_IBGE) == "072" and el.grupo("zz-29530") == "zz"
    br = _ler_gz(d / "br.json.gz")
    assert br["tipo"] == "eleitorado" and br["nivel"] == "br" and br["lugar"]["eleitores"] == total
    assert br["origem"]["perfil"]["sha256"] == "ab" and br["origem"]["secoes"]["url"].endswith("_2026.zip")
    assert br["partes"]["sp"]["nome"] == "São Paulo" and br["partes"]["sp"]["turnos"]["1"][0] == total
    uf = _ler_gz(d / "uf-sp.json.gz")
    assert uf["partes"][BORA_IBGE]["nome"] == "Borá" and uf["partes"][BORA_IBGE]["secoes"] == r.secoes
    grupo = _ler_gz(d / "mu" / "072.json.gz")
    assert grupo["tipo"] == "eleitorado-grupo" and list(grupo["municipios"]) == [BORA_IBGE]
    mu = grupo["municipios"][BORA_IBGE]
    assert "origem" not in mu and mu["lugar"]["chave"] == BORA_IBGE and [z["zona"] for z in mu["zonas"]] == ["12"]
    assert mu["zonas"][0]["eleitores"] == total and mu["lugar"]["turnos"]["1"]["aptos"] == total
    assert all(len(s) == 4 and f"{s[0]}-{s[2]}" in mu["locais"] for s in mu["secoes"])
    # Os mesmos dados dão os mesmos bytes, e o pacote leva os caminhos a partir da raiz do site
    antes = (d / "br.json.gz").read_bytes()
    el.gravar_eleitorado(2026, tmp_path / "site", referencias.cadastro_embutido(), perfil=perfil,
                         comparecimento=comp, locais=locais, manifestos={"perfil": manifesto})
    assert (d / "br.json.gz").read_bytes() == antes
    pacote = el.empacotar(2026, tmp_path / "site", tmp_path / "pacotes")
    with tarfile.open(pacote) as tar:
        assert tar.getnames() == ["eleitorado/2026/br.json.gz", "eleitorado/2026/mu/072.json.gz",
                                  "eleitorado/2026/uf-sp.json.gz"]
    assert el.empacotar(2026, tmp_path / "site", tmp_path / "pacotes").read_bytes() == pacote.read_bytes()


def test_comando_grava_os_anos_e_o_pacote_e_segue_sem_os_opcionais(tmp_path, monkeypatch, capsys):
    from lumen_eleicoes import cli
    monkeypatch.setenv("LUMEN_CONTATO", "c@exemplo.org")
    monkeypatch.setenv("LUMEN_DADOS", str(tmp_path / "dados"))
    zips = {"perfil": _zip(tmp_path / "perfil.zip", {"p_SP.csv": PERFIL}),
            "comparecimento": _zip(tmp_path / "comp.zip", {"c_SP.csv": COMPARECIMENTO})}

    def baixar(_cfg, url, **_k):
        nome = "perfil" if el.CONJUNTO_PERFIL + "/" in url else "comparecimento" if "comparecimento" in url else None
        if nome is None or "2022" in url and nome == "perfil":
            raise OSError("fora do ar")                              # os locais faltam; 2022, o perfil todo
        return zips[nome], Manifesto(url=url, arquivo=zips[nome].name, tamanho=1, sha256=nome, etag=None,
                                     ultima_modificacao=None, baixado_em="2026-10-29T00:00:00+00:00")

    monkeypatch.setattr(el, "baixar", baixar)
    codigo = cli.main(["eleitorado", "--anos", "2024,2022", "--saida", str(tmp_path / "site"),
                       "--pacotes", str(tmp_path / "pacotes"), "--sem-bronze"])
    resumo = json.loads(capsys.readouterr().out)
    assert codigo == 1 and resumo[0]["ano"] == 2024 and resumo[0]["secoes"] == 0
    assert resumo[0]["pacote"].endswith("eleitorado-2024.tar") and "fora do ar" in resumo[1]["erro"]
    assert (tmp_path / "site" / "eleitorado" / "2024" / "br.json.gz").exists()


def test_verificacao_do_contrato():
    from lumen_eleicoes.verificacao import Relatorio, verificar_eleitorado
    arquivos, _ = el.montar(2026, el.ler_perfil(open(PERFIL, "rb")), {}, *el.ler_secoes(open(LOCAIS, "rb")),
                            referencias.cadastro_embutido(), {})
    assert el.conferir(arquivos) == []
    mu = json.loads(json.dumps(arquivos["eleitorado/2026/mu/072.json"]["municipios"][BORA_IBGE]))
    mu["lugar"]["genero"][0][1] += 1
    mu["secoes"].append(["99", 1, "1", 10])
    rel = Relatorio()
    verificar_eleitorado(Path("mu.json"), mu, rel)
    assert len(rel.problemas) == 2
