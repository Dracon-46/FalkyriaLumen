"""Horários das urnas (ADR-056): do boletim de urna do TSE aos arquivos do site dos painéis.

Os recortes em ``testes/fixtures/tse/horarios`` são linhas reais, sem alteração, dos boletins de urna do 2º turno
de 2026 (``bweb_2t_<UF>_261020260742.csv``): três seções de Senador Guiomard (AC, zona 8), onde a urna abre às 6h
locais (8h de Brasília), e duas de Brasília (DF, zona 17). O formato de 2018 (``"SG_ UF"``, datas
``dd/mm/aaaa`` e sem os horários do boletim) é montado no teste.
"""

from __future__ import annotations

import gzip
import io
import json
import tarfile
import zipfile
from pathlib import Path

import pytest

from lumen_eleicoes import horarios as h
from lumen_eleicoes import referencias

FIX = Path(__file__).resolve().parents[3] / "testes" / "fixtures" / "tse" / "horarios"
AC, DF = FIX / "bweb_2t_AC_recorte.csv", FIX / "bweb_2t_DF_recorte.csv"
GUIOMARD, BRASILIA = "1200450", "5300108"


def _secoes() -> dict:
    secoes: dict = {}
    for caminho in (AC, DF):
        with open(caminho, "rb") as f:
            h.ler_csv(f, secoes)
    return secoes


def _ler_gz(caminho: Path) -> dict:
    return json.loads(gzip.decompress(caminho.read_bytes()))


def test_minutos_nos_dois_formatos_do_tse():
    assert h.minutos("2026-10-25 19:42:19", "2026-10-25") == 19 * 60 + 42
    assert h.minutos("07/10/2018 17:05:59", "2018-10-07") == 17 * 60 + 5
    assert h.minutos("2026-10-26 00:10:00", "2026-10-25") == 1440 + 10      # recebido no dia seguinte
    assert h.minutos("#NULO#", "2026-10-25") is None
    assert h.minutos("", "2026-10-25") is None and h.minutos(None, None) is None
    assert h.minutos("ontem", "2026-10-25") is None
    assert h.minutos("2026-10-25 08:00:01", None) == 480                    # sem dia: o do próprio horário


def test_le_uma_entrada_por_secao_do_boletim_real():
    secoes = _secoes()
    assert sorted(secoes) == [(2, "ac", "01538", "8", 68), (2, "ac", "01538", "8", 70), (2, "ac", "01538", "8", 97),
                              (2, "df", "97012", "17", 43), (2, "df", "97012", "17", 46)]
    # turno, UF, TSE, zona, seção, local, aptos, comparecimento, abstenções, tipo, abertura, encerramento, emissão,
    # recebido (os três primeiros no horário local; o recebido no de Brasília)
    assert secoes[(2, "ac", "01538", "8", 68)] == [2, "ac", "01538", "8", 68, "1074", 220, 169, 51, "Apurada",
                                                   6 * 60, 15 * 60, 15 * 60 + 3, 19 * 60 + 42]
    assert secoes[(2, "df", "97012", "17", 43)][10:] == [8 * 60, 17 * 60 + 5, 17 * 60 + 7, 19 * 60 + 35]
    for s in secoes.values():
        assert s[6] == s[7] + s[8]


def test_formato_de_2018_sem_horarios_do_boletim():
    csv_2018 = ('"DT_PLEITO";"NR_TURNO";"SG_ UF";"CD_MUNICIPIO";"NR_ZONA";"NR_SECAO";"NR_LOCAL_VOTACAO";'
                '"QT_APTOS";"QT_COMPARECIMENTO";"QT_ABSTENCOES";"DS_TIPO_URNA";"DT_ABERTURA";"DT_ENCERRAMENTO";'
                '"NR_VOTAVEL";"QT_VOTOS"\r\n'
                '"07/10/2018";1;"AC";1538;8;68;1074;200;150;50;"APURADA";"07/10/2018 08:00:01";'
                '"07/10/2018 17:31:10";17;80\r\n'
                '"07/10/2018";1;"AC";1538;8;68;1074;200;150;50;"APURADA";"07/10/2018 08:00:01";'
                '"07/10/2018 17:31:10";13;70\r\n')
    secoes = h.ler_csv(io.BytesIO(csv_2018.encode("latin-1")))
    assert list(secoes.values()) == [[1, "ac", "01538", "8", 68, "1074", 200, 150, 50, "Apurada", 480,
                                      17 * 60 + 31, None, None]]
    # antes de 2022, os horários ficam locais
    assert h.em_brasilia(list(secoes.values()), 2018)[0][10:12] == [480, 17 * 60 + 31]


def test_csv_sem_coluna_obrigatoria_e_recusado():
    with pytest.raises(ValueError, match="DT_ABERTURA"):
        h.ler_csv(io.BytesIO(b'"NR_TURNO";"SG_UF"\r\n1;"AC"\r\n'))


def test_horario_de_brasilia_pela_abertura_do_municipio():
    secoes = list(_secoes().values())
    assert h.diferencas(secoes, 2026) == {(2, "ac", "01538"): 120, (2, "df", "97012"): 0}
    assert h.diferencas(secoes, 2020) == {}
    guiomard = h.em_brasilia(secoes, 2026)[0]
    assert guiomard[10:] == [8 * 60, 17 * 60, 17 * 60 + 3, 19 * 60 + 42]   # o recebido já era de Brasília


def test_histograma_e_percentis():
    hist = h.Histograma(16 * 60 + 30, 22 * 60)
    for valor in (None, 15 * 60, 17 * 60, 17 * 60 + 9, 17 * 60 + 10, 23 * 60):
        hist.contar(valor)
    j = hist.para_json()
    assert (j["antes"], j["depois"], j["contagens"][3], j["contagens"][4], sum(j["contagens"])) == (1, 1, 2, 1, 3)
    secoes = h.em_brasilia(list(_secoes().values()), 2026)
    r = h.resumo(secoes, completo=True)
    assert (r["secoes"], r["aptos"], r["comparecimento"], r["depois_17h30"]) == (5, 1530, 1205, 0)
    assert r["encerramento"] == [17 * 60 + 4, 17 * 60 + 5, 17 * 60 + 5]
    assert sum(r["histogramas"]["encerramento"]["contagens"]) == 5 and r["tipos_urna"] == {"Apurada": 5}
    assert "histogramas" not in h.resumo(secoes, completo=False)


def test_montar_do_brasil_a_secao():
    secoes = list(_secoes().values())
    luanda = [2, "zz", "29998", "1", 1, "1", 10, 4, 6, "Apurada", 600, 1300, 1301, 2000]   # horário de Angola
    sem_cadastro = [2, "ac", "99999", "1", 1, "1", 10, 4, 6, "Apurada", 360, 900, 901, 1200]
    arquivos, r = h.montar(2026, [*secoes, luanda, sem_cadastro], referencias.cadastro_embutido(), {"fonte": "t"})
    assert (r.secoes, r.municipios, r.turnos) == (7, 3, [2]) and r.sem_cadastro == ["ac99999"]
    assert sorted(arquivos) == ["horarios/2026/br.json", "horarios/2026/mu/001.json", "horarios/2026/mu/004.json",
                                "horarios/2026/mu/zz.json", "horarios/2026/uf-ac.json", "horarios/2026/uf-df.json",
                                "horarios/2026/uf-zz.json"]
    br = arquivos["horarios/2026/br.json"]
    assert (br["versao"], br["tipo"], br["horario"], br["nivel"]) == (1, "horarios", "brasilia", "br")
    assert br["lugar"]["turnos"]["2"]["secoes"] == 6                       # o exterior fica de fora do Brasil
    assert set(br["partes"]) == {"ac", "df", "zz"} and br["partes"]["zz"]["nome"] == "Exterior"
    uf = arquivos["horarios/2026/uf-ac.json"]
    assert list(uf["partes"]) == [GUIOMARD] and uf["partes"][GUIOMARD]["turnos"]["2"]["secoes"] == 3
    mu = arquivos["horarios/2026/mu/004.json"]
    assert (mu["tipo"], list(mu["municipios"])) == ("horarios-grupo", [GUIOMARD])
    g = mu["municipios"][GUIOMARD]
    assert g["lugar"]["nome"] == "Senador Guiomard" and [z["zona"] for z in g["zonas"]] == ["8"]
    assert g["secoes"][0] == [2, "8", 68, "1074", 220, 169, "Apurada", "08:00", "17:00", "17:03", "19:42"]
    assert arquivos["horarios/2026/mu/001.json"]["municipios"][BRASILIA]["lugar"]["uf"] == "df"
    # no exterior, o horário fica o local
    assert arquivos["horarios/2026/mu/zz.json"]["municipios"]["zz-29998"]["secoes"][0][7:9] == ["10:00", "21:40"]


def test_hhmm_no_dia_seguinte():
    assert h._hhmm(1440 + 70) == "+1 01:10" and h._hhmm(None) is None and h._hhmm(5) == "00:05"


def test_gravar_apaga_o_antigo_e_empacota(tmp_path):
    site = tmp_path / "site"
    antigo = site / "horarios" / "2026" / "mu" / "999.json.gz"
    antigo.parent.mkdir(parents=True)
    antigo.write_bytes(b"velho")
    r = h.gravar(2026, list(_secoes().values()), site, referencias.cadastro_embutido(), urls=["b", "a"])
    assert r.municipios == 2 and not antigo.exists()
    br = _ler_gz(site / "horarios" / "2026" / "br.json.gz")
    assert br["origem"]["urls"] == ["a", "b"] and br["ano"] == 2026
    pacote = h.empacotar(2026, site, tmp_path / "pacotes")
    with tarfile.open(pacote) as tar:
        nomes = tar.getnames()
    assert pacote.name == "horarios-2026.tar" and "horarios/2026/br.json.gz" in nomes and len(nomes) == 5


def test_ler_zip(tmp_path):
    caminho = tmp_path / "bweb_2t_AC_261020260742.zip"
    with zipfile.ZipFile(caminho, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(AC, "bweb_2t_AC_261020260742.csv")
        zf.writestr("_leiame-boletimurnaweb.pdf", b"%PDF-1.4")
    assert len(h.ler_zip(caminho)) == 3


class _Resposta(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def test_urls_do_ano_fica_com_a_resposta_mais_completa():
    base = "https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2026/buweb/"
    so_1t = [{"url": base + "bweb_1t_AC_091020261755.zip"}, {"url": base + "leiame.pdf"}]
    completo = [*so_1t, {"url": base + "bweb_2t_AC_261020260742.zip"}]
    respostas = iter([so_1t, completo, so_1t])

    def abrir(pedido, timeout):
        assert pedido.get_header("User-agent") == "Lumen/teste"
        return _Resposta(json.dumps({"result": {"resources": next(respostas)}}).encode())
    urls = h.urls_do_ano(2026, user_agent="Lumen/teste", abrir=abrir, esperar=lambda _: None)
    assert urls == [(1, "ac", base + "bweb_1t_AC_091020261755.zip"), (2, "ac", base + "bweb_2t_AC_261020260742.zip")]
