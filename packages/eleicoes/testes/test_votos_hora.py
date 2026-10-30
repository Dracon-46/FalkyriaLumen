"""Votos por hora (ADR-057): dos logs das urnas, lidos por pedaços do ZIP do TSE, às contagens publicadas.

Os logs dos testes são montados aqui, com o formato real (data e hora, nível, número da urna, aplicação,
mensagem e código de controle, separados por tabulação), sem nenhuma linha de log real: os logs do TSE trazem o
título de eleitor de mesários.
"""

from __future__ import annotations

import gzip
import io
import json
import tarfile
import zipfile

import pytest

from lumen_eleicoes import referencias
from lumen_eleicoes import votos_hora as v


def _linha(momento: str, app: str, mensagem: str) -> str:
    return f"{momento}\tINFO\t02263093\t{app}\t{mensagem}\t0123456789ABCDEF"


def _log(*linhas: str) -> bytes:
    """Um ``-log.jez``: ZIP com o ``logd.dat`` em Latin-1."""
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("logd.dat", "\r\n".join(linhas).encode("latin-1"))
    return saida.getvalue()


def _votos(dia: str, *horas: str) -> list[str]:
    return [_linha(f"{dia} {h}", "VOTA", "O voto do eleitor foi computado") for h in horas]


# Seção do Acre: urna pronta às 6h locais (8h de Brasília); o log do 2º turno traz o 1º junto
LOG_AC_2T = _log(
    _linha("04/10/2026 06:00:01", "VOTA", "Urna pronta para receber votos"),
    *_votos("04/10/2026", "06:03:22", "06:15:00"),
    _linha("25/10/2026 05:21:46", "LOGD", "Início das operações do logd"),
    _linha("25/10/2026 06:00:01", "VOTA", "Urna pronta para receber votos"),
    *_votos("25/10/2026", "06:01:10", "06:09:59", "06:10:00", "07:30:00", "15:20:00"),
    _linha("25/10/2026 15:21:00", "VOTA", "Operador selecionou: Encerrar votação"),
)
LOG_DF_2T = _log(_linha("25/10/2026 08:00:01", "VOTA", "Urna pronta para receber votos"),
                 *_votos("25/10/2026", "08:00:30", "16:59:00", "17:40:00"))
# Urna trocada às 9h: ficou pronta tarde, mas a seção segue o fuso do município
LOG_AC_TROCADA = _log(_linha("25/10/2026 09:00:00", "VOTA", "Urna pronta para receber votos"),
                      *_votos("25/10/2026", "09:05:00"))


def _zip_transmitido(logs: dict[str, bytes]) -> bytes:
    """Um ``bu_imgbu_logjez_rdv_vscmr`` em miniatura: para cada seção, o boletim e o log."""
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("leiame.pdf", b"%PDF-1.4")
        for nome, log in logs.items():
            zf.writestr(f"{nome}-bu.dat", b"\x00" * 300)
            zf.writestr(f"{nome}-log.jez", log)
    return saida.getvalue()


class _Memoria:
    """Leitor em memória com a interface de ``LeitorRemoto``."""

    def __init__(self, dados: bytes):
        self.dados, self.recebidos, self.pedidos = dados, 0, 0

    def ler(self, inicio: int, tamanho: int) -> bytes:
        pedaco = self.dados[inicio:] if inicio < 0 else self.dados[inicio:inicio + tamanho]
        self.recebidos += len(pedaco)
        self.pedidos += 1
        return pedaco


ARQUIVO_AC = _zip_transmitido({"o03221ac0153800080068": LOG_AC_2T, "o03221ac0153800080070": LOG_AC_TROCADA})
ARQUIVO_DF = _zip_transmitido({"o03221df9701200170043": LOG_DF_2T})


def test_conta_so_o_ultimo_dia_e_acha_a_urna_pronta():
    c = v.contar_log(LOG_AC_2T)
    assert (c.dia, c.pronta) == ("2026-10-25", 360)
    assert dict(c.faixas) == {360: 2, 370: 1, 450: 1, 920: 1}
    assert v.contar_log(_log(_linha("25/10/2026 05:00:00", "LOGD", "Início"))).dia is None


def test_diferenca_para_brasilia():
    assert (v.diferenca(360), v.diferenca(480), v.diferenca(420), v.diferenca(None)) == (120, 0, 60, None)
    assert v.diferenca(600) == 0 and v.diferenca(0) == 180       # fora da faixa: 0 a 3 horas


def test_entradas_e_conteudo_do_zip_sem_baixar_tudo():
    m = _Memoria(ARQUIVO_AC)
    entradas = v.entradas_do_zip(m.ler)
    assert [e.nome for e in entradas][:3] == ["leiame.pdf", "o03221ac0153800080068-bu.dat",
                                             "o03221ac0153800080068-log.jez"]
    log = next(e for e in entradas if e.nome.endswith("68-log.jez"))
    m.recebidos = 0
    assert v.conteudo(m.ler, log) == LOG_AC_2T
    assert m.recebidos < len(LOG_AC_2T) + 200                  # só o log, com o cabeçalho e a folga
    with pytest.raises(ValueError, match="fim do diretório central"):
        v.entradas_do_zip(_Memoria(b"nada de zip").ler)


def test_ler_arquivo_uma_secao_por_log():
    secoes = list(v.ler_arquivo(2, "https://exemplo/ac.zip", user_agent="Lumen/teste", trabalhadores=2,
                                leitor=_Memoria(ARQUIVO_AC)))
    assert secoes == [[2, "ac", "01538", "8", 68, 120, {360: 2, 370: 1, 450: 1, 920: 1}],
                      [2, "ac", "01538", "8", 70, 0, {540: 1}]]


def test_coletar_e_ler_as_parciais(tmp_path):
    urls = [(2, "ac", "https://exemplo/ac.zip"), (2, "df", "https://exemplo/df.zip")]
    arquivos = {"https://exemplo/ac.zip": ARQUIVO_AC, "https://exemplo/df.zip": ARQUIVO_DF}
    r = v.coletar("ac", urls, tmp_path, user_agent="Lumen/teste", abrir=lambda u: _Memoria(arquivos[u]))
    assert (r.secoes, r.votos, r.sem_votos, r.pedidos > 0) == (2, 6, 0, True)
    v.coletar("df", urls, tmp_path, user_agent="Lumen/teste", abrir=lambda u: _Memoria(arquivos[u]))
    secoes = v.ler_parciais(tmp_path)
    assert len(secoes) == 3 and secoes[0][6] == {360: 2, 370: 1, 450: 1, 920: 1}   # faixas de volta a números


def test_horario_de_brasilia_pelo_municipio():
    secoes = [[2, "ac", "01538", "8", 68, 120, {360: 2, 920: 1}], [2, "ac", "01538", "8", 70, 0, {540: 1}],
              [2, "zz", "29998", "1", 1, 0, {600: 3}]]
    b = v.em_brasilia(secoes)
    assert b[0][5:] == [120, {480: 2, 1040: 1}]
    assert b[1][5:] == [120, {660: 1}]               # a urna trocada segue o município
    assert b[2][5:] == [0, {600: 3}]                 # no exterior, o horário local


def test_por_hora_e_por_faixa():
    assert v.por_hora({480: 2, 490: 1, 600: 4, 1040: 1}) == [8, 3, 0, 4, 0, 0, 0, 0, 0, 0, 1]
    assert v.por_hora({}) == [] and v.por_hora({480: 0}) == []
    assert v.por_faixa({480: 2, 510: 1}) == {"inicio": 480, "passo": 10, "contagens": [2, 0, 0, 1]}
    assert v.por_faixa({}) == {"inicio": None, "passo": 10, "contagens": []}


def test_montar_do_brasil_a_secao():
    secoes = [[2, "ac", "01538", "8", 68, 120, {360: 2, 370: 1, 450: 1, 920: 1}],
              [2, "ac", "01538", "8", 70, 0, {540: 1}],
              [2, "df", "97012", "17", 43, 0, {480: 1, 1010: 1, 1060: 1}],
              [2, "zz", "29998", "1", 1, None, {600: 3}],
              [2, "ac", "99999", "1", 1, 120, {360: 1}]]
    arquivos, r = v.montar(2026, secoes, referencias.cadastro_embutido(), {"fonte": "teste"})
    assert (r.secoes, r.votos, r.municipios, r.turnos, r.sem_cadastro) == (5, 13, 3, [2], ["ac99999"])
    assert sorted(arquivos) == ["votos-hora/2026/br.json", "votos-hora/2026/mu/00.json", "votos-hora/2026/mu/zz.json",
                                "votos-hora/2026/uf-ac.json", "votos-hora/2026/uf-df.json", "votos-hora/2026/uf-zz.json"]
    br = arquivos["votos-hora/2026/br.json"]
    assert (br["tipo"], br["horario"], br["nivel"]) == ("votos-hora", "brasilia", "br")
    t = br["lugar"]["turnos"]["2"]
    assert (t["votos"], t["secoes"]) == (10, 4)                       # o exterior fica de fora do Brasil
    assert t["por_hora"] == [8, 5, 1, 0, 1, 0, 0, 0, 0, 1, 2]       # a seção sem cadastro conta no Brasil
    assert t["por_faixa"]["inicio"] == 480 and sum(t["por_faixa"]["contagens"]) == 10
    assert br["partes"]["zz"]["turnos"]["2"]["votos"] == 3 and "por_faixa" not in br["partes"]["ac"]["turnos"]["2"]
    grupo = arquivos["votos-hora/2026/mu/00.json"]
    assert grupo["tipo"] == "votos-hora-grupo" and set(grupo["municipios"]) == {"1200450", "5300108"}
    guiomard = grupo["municipios"]["1200450"]
    assert guiomard["secoes"] == [[2, "8", 68, 8, 3, 1, 0, 0, 0, 0, 0, 0, 0, 1], [2, "8", 70, 11, 1]]
    assert guiomard["zonas"][0]["turnos"]["2"]["por_hora"][0] == 8
    assert arquivos["votos-hora/2026/mu/zz.json"]["municipios"]["zz-29998"]["secoes"] == [[2, "1", 1, 10, 3]]


def test_grupo_de_dois_digitos():
    assert (v.grupo("3550308"), v.grupo("1200450"), v.grupo("zz-29998")) == ("50", "00", "zz")


def test_gravar_apaga_o_antigo_e_empacota(tmp_path):
    site = tmp_path / "site"
    antigo = site / "votos-hora" / "2026" / "mu" / "99.json.gz"
    antigo.parent.mkdir(parents=True)
    antigo.write_bytes(b"velho")
    secoes = [[2, "df", "97012", "17", 43, 0, {480: 1}]]
    r = v.gravar(2026, secoes, site, referencias.cadastro_embutido(), urls=["b", "a"])
    assert r.municipios == 1 and not antigo.exists()
    br = json.loads(gzip.decompress((site / "votos-hora" / "2026" / "br.json.gz").read_bytes()))
    assert br["origem"]["urls"] == ["a", "b"]
    with tarfile.open(v.empacotar(2026, site, tmp_path / "pacotes")) as tar:
        assert sorted(tar.getnames()) == ["votos-hora/2026/br.json.gz", "votos-hora/2026/mu/00.json.gz",
                                          "votos-hora/2026/uf-df.json.gz"]


class _Resposta(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def test_urls_do_ano_fica_com_a_resposta_mais_completa():
    base = "https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2026/arqurnatot/"
    so_1t = [{"url": base + "bu_imgbu_logjez_rdv_vscmr_2026_1t_AC.zip"}, {"url": base + "leiame.pdf"}]
    completo = [*so_1t, {"url": base + "bu_imgbu_logjez_rdv_vscmr_2026_2t_ZZ.zip"}]
    respostas = iter([so_1t, completo, so_1t])

    def abrir(pedido, timeout):
        return _Resposta(json.dumps({"result": {"resources": next(respostas)}}).encode())
    assert v.urls_do_ano(2026, user_agent="Lumen/teste", abrir=abrir, esperar=lambda _: None,
                         existe=lambda _: False) == [
        (1, "ac", base + "bu_imgbu_logjez_rdv_vscmr_2026_1t_AC.zip"),
        (2, "zz", base + "bu_imgbu_logjez_rdv_vscmr_2026_2t_ZZ.zip")]


def test_leitor_exige_identificacao():
    with pytest.raises(ValueError, match="user_agent"):
        v.LeitorRemoto("https://exemplo/a.zip", user_agent=" ")


def test_completar_o_turno_que_o_catalogo_nao_listou():
    base = "https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2026/arqurnatot/"
    urls = [(1, "ac", base + "bu_imgbu_logjez_rdv_vscmr_2026_1t_AC.zip"),
            (1, "df", base + "bu_imgbu_logjez_rdv_vscmr_2026_1t_DF.zip"),
            (2, "ac", base + "bu_imgbu_logjez_rdv_vscmr_2026_2t_AC.zip")]
    perguntados = []

    def existe(url):
        perguntados.append(url)
        return url.endswith("_2t_DF.zip")
    assert v.completar(urls, existe)[-1] == (2, "df", base + "bu_imgbu_logjez_rdv_vscmr_2026_2t_DF.zip")
    assert perguntados == [base + "bu_imgbu_logjez_rdv_vscmr_2026_2t_DF.zip"]
    assert v.completar(urls, lambda _: False) == urls        # o servidor não tem: fica como o catálogo listou


def test_completar_o_turno_inteiro_que_o_catalogo_nao_listou():
    base = "https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2026/arqurnatot/"
    urls = [(1, "ac", base + "bu_imgbu_logjez_rdv_vscmr_2026_1t_AC.zip")]
    assert v.completar(urls, lambda u: True, turnos=range(1, 3)) == [
        *urls, (2, "ac", base + "bu_imgbu_logjez_rdv_vscmr_2026_2t_AC.zip")]
    assert v.completar([], lambda u: True, turnos=[2]) == []
