"""Eleições de 1933 a 1990: leitura dos arquivos por UF do TSE e feeds gerados.

As fixtures (``testes/fixtures/tse/dados_abertos_uf``) são linhas reais, sem alteração, recortadas dos
arquivos publicados pelo TSE; os ZIPs são montados aqui, como o tribunal os publica.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lumen_eleicoes import antigas
from lumen_eleicoes.dados_abertos import AVISO_SEM_DETALHE, aviso_validos_da_epoca, situacao_publicada
from lumen_eleicoes.feeds import EscritorFeeds, eleicao_de_indice
from lumen_eleicoes.modelo import Nivel, TipoCargo
from lumen_eleicoes.transferencia import Manifesto
from lumen_eleicoes.verificacao import verificar_diretorio


@pytest.fixture
def processar(tmp_path, zips_antigos):
    """Função que processa um ano das fixtures e devolve o resumo e o diretório dos feeds."""
    def rodar(ano: int, origem: Manifesto | None = None) -> tuple[antigas.ResumoAntigo, Path]:
        saida = tmp_path / "feeds"
        resumo = antigas.ProcessadorAnoAntigo(ano, EscritorFeeds(saida), origem=origem).processar_zips(
            *zips_antigos(tmp_path / "zips", ano))
        return resumo, saida
    return rodar


def ler(saida: Path, relativo: str) -> dict:
    """Feed gravado, já decodificado."""
    return json.loads((saida / relativo).read_text(encoding="utf-8"))


# ------------------------------------------------------------------ endereços, UFs e regras da época

def test_enderecos_dos_conjuntos():
    assert antigas.url_conjunto_uf(antigas.CONJUNTO_CANDIDATO_UF, 1933).endswith(
        "/votacao_candidato_uf/votacao_candidato_uf_1933_br.zip")
    assert antigas.url_conjunto_uf(antigas.CONJUNTO_DETALHE_UF, 1950).endswith(
        "/detalhe_votacao_uf/detalhe_votacao_uf_1950.zip")
    assert antigas.nome_arquivo_uf(antigas.CONJUNTO_PARTIDO_UF, 1934) == "votacao_partido_uf_1934_br.zip"
    assert antigas.ANOS_ANTIGOS[0] == 1933 and antigas.ANOS_ANTIGOS[-1] == 1990


@pytest.mark.parametrize("sigla, ano, esperado", [
    ("DF", 1950, ("df-antigo", None)),        # cidade do Rio de Janeiro: fora do mapa atual
    ("DF", 1960, ("df", "53")),
    ("GP", 1950, ("gp", "11")),               # Guaporé: mesmo território de Rondônia
    ("RB", 1950, ("rb", "14")),               # Rio Branco: mesmo território de Roraima
    ("GB", 1962, ("gb", None)),
    ("Fernando de Noronha", 1945, ("fn", None)),
    ("Iguaçu", 1945, ("ig", None)),
    ("Ponta Porã", 1945, ("pp", None)),
    ("ZZ", 1989, ("zz", None)),
    ("sp", 1950, ("sp", "35")),
    ("Território X", 1945, ("territorio-x", None)),
])
def test_uf_historica(sigla, ano, esperado):
    uf = antigas.uf_historica(sigla, ano)
    assert (uf.codigo, uf.ibge) == esperado
    assert uf.nome
    abr = antigas.abrangencia_uf_historica(uf)
    assert (abr.tipo, abr.codigo, abr.ibge) == ("uf", uf.codigo, uf.ibge)


def test_votos_validos_pelas_regras_da_epoca():
    assert "branco e nulos" in aviso_validos_da_epoca(1950)
    assert "branco e nulos" in aviso_validos_da_epoca(1962)
    assert "branco também" in aviso_validos_da_epoca(1965)      # depois do Código Eleitoral de 1965
    assert "branco também" in aviso_validos_da_epoca(1996)      # até a Lei 9.504/97
    assert aviso_validos_da_epoca(1998) is None
    assert antigas.aviso_soma_diferente(900, 1000).endswith("usam o total do detalhe.")
    assert "1.000 votos" in antigas.aviso_soma_diferente(1000, 900)
    assert antigas.aviso_soma_diferente(1000, 900).endswith("usam a soma dos candidatos.")


def test_chave_do_candidato_sem_numero_e_estavel():
    assert antigas.chave_candidato(13, "LULA", "PT", nacional=True) == ("13", True)
    nacional, publicado = antigas.chave_candidato(None, "Eurico Gaspar Dutra", "PSD", nacional=True)
    assert not publicado and nacional.startswith("s") and len(nacional) == 11
    # Nos cargos nacionais só o nome liga as UFs; a grafia (acento, caixa) não importa
    assert antigas.chave_candidato(None, "EURICO GASPAR DUTRA", "PTB", nacional=True)[0] == nacional
    # Nos estaduais, homônimos de partidos diferentes não se fundem
    assert (antigas.chave_candidato(None, "JOÃO", "PSD", nacional=False)
            != antigas.chave_candidato(None, "JOÃO", "UDN", nacional=False))


def test_cargo_antigo():
    presidente = antigas.cargo_antigo(1, "PRESIDENTE", True)
    assert (presidente.slug, presidente.nivel, presidente.slug_fixo) == ("presidente", Nivel.BRASIL, None)
    deputado = antigas.cargo_antigo(6, "DEPUTADO", False)        # 1933: "Deputado", não "Deputado Federal"
    assert (deputado.slug, deputado.nivel, deputado.tipo) == ("deputado", Nivel.UF, TipoCargo.PROPORCIONAL)
    vereador = antigas.cargo_antigo(8, "VEREADOR", False)        # 1934: código 8 era vereador
    assert (vereador.slug, vereador.nome, vereador.tipo) == ("vereador", "Vereador", TipoCargo.PROPORCIONAL)
    vice = antigas.cargo_antigo(2, "VICE-PRESIDENTE", True)
    assert (vice.slug, vice.nivel, vice.tipo) == ("vice-presidente", Nivel.BRASIL, TipoCargo.MAJORITARIO)
    assert antigas.cargo_antigo(99, "", False).slug == "cargo-99"


def test_leitura_pula_cabecalho_e_linhas_com_outro_numero_de_colunas():
    texto = '"DATA_GERACAO";"X"\n"a";"b"\n' + ";".join(f'"{i}"' for i in range(26)) + "\n"
    linhas = list(antigas.linhas_tabela(texto, antigas.COLUNAS_CANDIDATO))
    assert len(linhas) == 1 and linhas[0]["TOTAL_VOTOS"] == "25"
    assert antigas._numero("#NULO#") is None and antigas._numero("-3") is None and antigas._numero("x") is None
    assert antigas._texto("#NE#") is None and antigas._texto(None) is None


def test_bytes_do_windows_no_texto_latin1():
    # 1954, SP: "LUIZ COLOMBO D’AVILA FLORENCE" vem com o apóstrofo 0x92 do Windows-1252
    assert antigas.decodificar("D\x92AVILA ÇÃO".encode("latin-1")) == "D’AVILA ÇÃO"
    assert antigas.decodificar(b"\x81") == "\x81"                  # sem equivalente: fica como está


def test_situacoes_de_1933_e_1934():
    assert situacao_publicada("ELEITO 1º TURNO QE") == "Eleito no 1º turno por QE"
    assert situacao_publicada("ELEITO 2º TURNO") == "Eleito no 2º turno"


def test_ano_fora_do_periodo_por_uf(tmp_path):
    with pytest.raises(ValueError):
        antigas.ProcessadorAnoAntigo(1994, EscritorFeeds(tmp_path))


# ------------------------------------------------------------------ anos reais

def test_1933_dois_turnos_de_apuracao_com_detalhe_sem_turno(processar):
    resumo, saida = processar(1933)
    assert resumo.eleicoes == ["1933-1t-geral", "1933-2t-geral"] and resumo.linhas_ignoradas == 0
    indice = ler(saida, "indice.json")
    nomes = {e["id"]: e["nome"] for e in indice["eleicoes"]}
    assert nomes["1933-1t-geral"] == "Eleição de 1933 — Assembleia Nacional Constituinte — 1º turno"
    assert all(e["municipios"] is False for e in indice["eleicoes"])
    ac = ler(saida, "1933-1t-geral/deputado/uf-ac.json")
    assert ac["cargo"]["slug"] == "deputado" and ac["cargo"]["nivel"] == "uf"
    assert antigas.AVISO_TURNOS_1932 in ac["avisos"] and antigas.AVISO_SO_POR_UF in ac["avisos"]
    alberto = ac["candidatos"][0]
    assert (alberto["nome_urna"], alberto["votos"], alberto["situacao"], alberto["eleito"], alberto["sem_numero"]) == (
        "ALBERTO AUGUSTTO DINIZ", 948, "Eleito no 1º turno por QE", True, True)
    # O detalhe de 1933 não tem turno (-3): vale para as duas etapas
    assert ac["comparecimento"]["eleitorado"] == 1968
    # Candidatos somam 1867 e o detalhe registra 1864: a base é a maior, e os percentuais não passam de 100%
    assert ac["votos"]["validos"] == 1867
    assert not any(a.startswith("Os candidatos deste arquivo somam") for a in ac["avisos"])   # diferença ínfima
    segundo = ler(saida, "1933-2t-geral/deputado/uf-ac.json")
    assert segundo["comparecimento"]["eleitorado"] == 1968
    # 2º turno de apuração: cada cédula contava para vários nomes; a soma passa do número de votantes
    assert segundo["votos"]["validos"] == 977 + 889 + 941 + 899 and antigas.AVISO_VARIOS_NOMES_1932 in segundo["avisos"]
    assert sum(c["pct"] for c in segundo["candidatos"]) == pytest.approx(100.0)
    assert {a["nome"]: a["vagas"] for a in ac["agremiacoes"]}["CHAPA POPULAR"] == 2
    br = ler(saida, "1933-1t-geral/deputado/br.json")
    assert br["tipo"] == "panorama" and [p["codigo"] for p in br["partes"]] == ["ac"]


def test_1945_territorios_extintos_e_distrito_federal_antigo(processar):
    resumo, saida = processar(1945)
    br = ler(saida, "1945-1t-geral/presidente/br.json")
    partes = {p["codigo"]: p["ibge"] for p in br["partes"]}
    assert partes == {"df-antigo": None, "fn": None, "gp": "11", "ig": None, "pp": None, "rb": "14"}
    assert antigas.AVISO_MAPA_FRONTEIRAS in br["avisos"]
    # Só o Distrito Federal tem detalhe no recorte: o total do Brasil sai da soma dos candidatos
    assert AVISO_SEM_DETALHE in br["avisos"]
    dutra = next(c for c in br["candidatos"] if c["nome"] == "EURICO GASPAR DUTRA")
    assert dutra["votos"] == 166070 + 77 + 1118 + 11373 + 4028 + 71 and dutra["sem_numero"] is True
    assert dutra["situacao"] == "Eleito"
    assert br["votos"]["validos"] == sum(c["votos"] for c in br["candidatos"])
    df = ler(saida, "1945-1t-geral/presidente/uf-df-antigo.json")
    assert df["abrangencia"]["nome"] == "Distrito Federal (cidade do Rio de Janeiro)"
    assert (df["comparecimento"]["eleitorado"], df["votos"]["brancos"]) == (549353, 2510)
    # Cores: a mesma do Brasil para o mesmo candidato em todas as UFs
    cor = {c["numero"]: c["cor"] for c in br["candidatos"]}
    assert all(c["cor"] == cor[c["numero"]] for c in df["candidatos"])
    assert verificar_diretorio(saida).ok


def test_1950_presidente_e_vice_votados_separadamente(processar):
    origem = Manifesto(url="https://exemplo/v.zip", arquivo="v.zip", tamanho=1, sha256="ab" * 32, etag=None,
                       ultima_modificacao=None, baixado_em="2026-10-06T12:00:00+00:00")
    resumo, saida = processar(1950, origem)
    indice = ler(saida, "indice.json")
    e = next(x for x in indice["eleicoes"] if x["id"] == "1950-1t-geral")
    assert [c["slug"] for c in e["cargos"]] == ["presidente", "vice-presidente"]
    reconstruida = eleicao_de_indice(e)
    assert reconstruida.cargos[1].slug == "vice-presidente" and reconstruida.cargos[1].nivel is Nivel.BRASIL
    br = ler(saida, "1950-1t-geral/presidente/br.json")
    assert br["origem"]["sha256"] == "ab" * 32 and br["origem"]["url"] == "https://exemplo/v.zip"
    assert br["votos"]["validos"] == 9049 + 3653 + 2549          # nominais do detalhe de AC, GP e RB
    assert br["candidatos"][0]["pct"] is not None
    assert {p["codigo"] for p in br["partes"]} == {"ac", "gp", "rb"}
    assert antigas.AVISO_MAPA_FRONTEIRAS not in br["avisos"]   # Guaporé e Rio Branco estão no mapa atual
    assert ler(saida, "1950-1t-geral/vice-presidente/uf-gp.json")["abrangencia"]["ibge"] == "11"


def test_1962_guanabara_fora_do_mapa(processar):
    _, saida = processar(1962)
    gb = ler(saida, "1962-1t-geral/senador/uf-gb.json")
    assert gb["abrangencia"]["nome"] == "Guanabara" and gb["abrangencia"]["ibge"] is None
    assert sum(c["eleito"] for c in gb["candidatos"]) >= 1
    # Em 1962 a sigla do partido está em branco na fonte: vem da composição da legenda, se é um partido só
    partidos = {c["nome"]: (c["partido"], c["agremiacao"]) for c in gb["candidatos"]}
    assert partidos["GILBERTO MARINHO"] == ("PTN", None)
    assert partidos["AURÉLIO VIANNA"] == (None, "ALIANÇA SOCIAL TRABALHISTA")   # coligação PTB / PSB
    br = ler(saida, "1962-1t-geral/senador/br.json")
    assert br["tipo"] == "panorama" and antigas.AVISO_MAPA_FRONTEIRAS in br["avisos"]
    # Quem lidera é de coligação, sem partido identificável: a UF fica sem cor de partido no placar
    assert br["partes"][0]["nome_urna"] == "AURÉLIO VIANNA" and br["partes"][0]["partido"] is None


def test_1986_linhas_sem_nome_e_votacao_por_partido(processar):
    resumo, saida = processar(1986)
    assert resumo.linhas_ignoradas == 0
    ap = ler(saida, "1986-1t-geral/deputado-federal/uf-ap.json")
    sem_nome = [c for c in ap["candidatos"] if c["nome_urna"].startswith("Candidato nº")]
    assert sem_nome and all("sem_numero" not in c for c in sem_nome)
    assert next(c for c in ap["candidatos"] if c["numero"] == "1313")["votos"] == 1932
    vagas = {a["nome"]: (a["votos"], a["vagas"]) for a in ap["agremiacoes"]}
    assert vagas["PFL"] == (29030 + 2490, 3)
    assert ap["votos"]["legenda"] == 8227 and ap["votos"]["validos"] == 61613 + 8227
    assert aviso_validos_da_epoca(1986) in ap["avisos"]


def test_1989_dois_turnos_com_numero_e_exterior(processar):
    resumo, saida = processar(1989)        # sem o arquivo por partido, que não existe na fonte
    assert resumo.eleicoes == ["1989-1t-geral", "1989-2t-geral"]
    br = ler(saida, "1989-2t-geral/presidente/br.json")
    assert [c["numero"] for c in br["candidatos"]] == ["13", "20"]
    assert all("sem_numero" not in c for c in br["candidatos"])
    assert br["votos"]["validos"] == 128798 + 720743 + 10171
    assert sum(c["votos"] for c in br["candidatos"]) == br["votos"]["validos"]
    assert {p["codigo"] for p in br["partes"]} == {"ac", "df", "zz"}
    assert antigas.AVISO_MAPA_FRONTEIRAS not in br["avisos"]   # o exterior nunca está no mapa
    nomes = {e["id"]: e["nome"] for e in ler(saida, "indice.json")["eleicoes"]}
    assert nomes["1989-2t-geral"] == "Eleições 1989 — 2º turno"
    assert verificar_diretorio(saida).ok


def test_leitura_sem_detalhe_e_candidato_sem_votacao():
    linha = ['"1/1/2014"', '"0"', '"1950"', '"1"', '"E"', '"AC"', '"AC"', '"5"', '"-1"', '"-3"', '"{nome}"', '"#NE#"',
             '"SENADOR"', '"-1"', '"#NULO#"', '"2"', '"DEFERIDO"', '"1"', '"{sit}"', '"-3"', '"PSD"', '"P"', '"-3"',
             '"#NULO#"', '"#NULO#"', '"{votos}"']
    texto = "\n".join(";".join(linha).format(nome=n, sit=s, votos=v) for n, s, v in (
        ("A", "ELEITO", "10"), ("B", "NÃO ELEITO", "-1"), ("", "NÃO ELEITO", "3"), ("A", "", "5")))
    leitura = antigas.ler_ano(1950, candidatos=[texto])
    assert leitura.sem_nome == 1
    grupo = leitura.candidatos[("1950-1t-geral", 5, "ac")]
    assert sorted(c.votos or 0 for c in grupo.values()) == [0, 3, 15]   # linha repetida soma; ausente é None
    r = antigas._resultado(leitura, "1950-1t-geral", leitura.cargos[("1950-1t-geral", 5)], "ac",
                           list(grupo.values()), None, [])
    assert AVISO_SEM_DETALHE in r.avisos and antigas.AVISO_SEM_VOTACAO in r.avisos
    sem_votacao = next(c for c in r.candidatos if c.nome == "B")
    assert (sem_votacao.pct_validos, sem_votacao.destinacao) == (None, "Votação não registrada")
    assert next(c for c in r.candidatos if c.nome == "Nome não registrado na fonte").votos == 3


def test_verificacao_cobra_as_ufs_de_cada_cargo(processar):
    _, saida = processar(1962)
    indice = ler(saida, "indice.json")
    e = indice["eleicoes"][0]
    e["ufs"].append("sp")                       # a eleição tem SP, mas nenhum cargo diz ter dado lá
    (saida / "indice.json").write_text(json.dumps(indice), encoding="utf-8")
    assert verificar_diretorio(saida).ok
    for c in e["cargos"]:
        del c["ufs"]                            # sem as UFs do cargo, valem as da eleição
    (saida / "indice.json").write_text(json.dumps(indice), encoding="utf-8")
    problemas = verificar_diretorio(saida).problemas
    assert any("senador/uf-sp.json" in p for p in problemas)
