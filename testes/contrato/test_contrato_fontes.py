"""Testes de contrato contra as fontes reais (DOC-09, seção 3.2).

Validam só o **esquema** — que os campos que o normalizador lê continuam
existindo, com o tipo esperado —, nunca o conteúdo. Rodam diariamente por
agendamento na CI e não bloqueiam entrega: quando falham, alarmam, porque
significam que a fonte mudou de formato sem aviso (risco R-03).

    LUMEN_TESTE_CONTRATO=1 python -m pytest -m contrato

O esquema de referência é o das fixtures de ``testes/fixtures``: se a fonte
real deixar de ter um campo que a fixture tem, o teste acusa.
"""

from __future__ import annotations

import json
import os
import urllib.request
from datetime import date, timedelta
from pathlib import Path

import pytest

from lumen_canonico import VERSAO_LUMEN

pytestmark = pytest.mark.contrato

if os.environ.get("LUMEN_TESTE_CONTRATO") != "1":
    pytest.skip("defina LUMEN_TESTE_CONTRATO=1 para consultar as fontes reais", allow_module_level=True)

FIX = Path(__file__).resolve().parents[1] / "fixtures"
UA = f"Lumen/{VERSAO_LUMEN} (teste de contrato de esquema; +https://github.com/Dracon-46/FalkyriaLumen)"
ONTEM = (date.today() - timedelta(days=1)).strftime("%Y%m%d")


def _obter(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        corpo = r.read()
        return r.status, (json.loads(corpo) if corpo.strip() else None)


def _campos(obj: dict) -> set[str]:
    return set(obj) if isinstance(obj, dict) else set()


def _referencia(caminho: str):
    return json.loads((FIX / caminho).read_text(encoding="utf-8"))


@pytest.mark.parametrize("url,fixture,chave", [
    (f"https://pncp.gov.br/api/consulta/v1/contratacoes/publicacao?dataInicial={ONTEM}&dataFinal={ONTEM}"
     "&codigoModalidadeContratacao=8&pagina=1&tamanhoPagina=10",
     "pncp/contratacoes_publicacao_dispensa_20260901_p1.json", "data"),
    (f"https://pncp.gov.br/api/consulta/v1/contratos?dataInicial={ONTEM}&dataFinal={ONTEM}&pagina=1&tamanhoPagina=10",
     "pncp/contratos_20260901_p1.json", "data"),
])
def test_pncp_mantem_os_campos_lidos_pelo_normalizador(url, fixture, chave):
    status, corpo = _obter(url)
    if status == 204:
        pytest.skip("sem publicações ontem para esta consulta")
    ref = _referencia(fixture)
    assert _campos(corpo) >= _campos(ref) - {chave} | {chave}
    faltando = _campos(ref[chave][0]) - _campos(corpo[chave][0])
    assert not faltando, f"campos sumiram da fonte: {sorted(faltando)}"


def test_pncp_continua_exigindo_modalidade():
    try:
        _obter(f"https://pncp.gov.br/api/consulta/v1/contratacoes/publicacao?dataInicial={ONTEM}"
               f"&dataFinal={ONTEM}&pagina=1")
    except urllib.error.HTTPError as e:
        assert e.code == 400
    else:
        pytest.fail("o PNCP deixou de exigir codigoModalidadeContratacao: revisar o adaptador")


def test_siconfi_entes_mantem_esquema():
    _, corpo = _obter("https://apidatalake.tesouro.gov.br/ords/siconfi/tt/entes")
    ref = _referencia("siconfi/entes_amostra.json")["items"][0]
    assert _campos(ref) <= _campos(corpo["items"][0])
    assert corpo["count"] > 5000


def test_ibge_municipios_mantem_esquema():
    _, corpo = _obter("https://servicodados.ibge.gov.br/api/v1/localidades/municipios?view=nivelado")
    ref = _referencia("ibge/municipios_nivelado_amostra.json")[0]
    assert _campos(ref) <= _campos(corpo[0])
    assert len(corpo) >= 5570


def test_tse_resultados_mantem_esquema():
    _, cfg = _obter("https://resultados.tse.jus.br/oficial/comum/config/ele-c.json")
    assert {"pl", "arq"} <= _campos(cfg)


# ---------------------------------------------------------------- aba Eleições (TSE e IBGE)

def _obter_bytes(url: str, cabecalhos: dict | None = None) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(cabecalhos or {})})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def _primeiras_linhas_do_zip(url: str, n: int = 2) -> list[str]:
    """Lê só o começo do primeiro CSV de um ZIP remoto (Range), sem baixar o arquivo."""
    import struct
    import zlib
    bruto = _obter_bytes(url, {"Range": "bytes=0-131071"})
    assert bruto[:4] == b"PK\x03\x04", "não é ZIP"
    nome_len, extra_len = struct.unpack("<HH", bruto[26:30])
    inicio = 30 + nome_len + extra_len
    texto = zlib.decompressobj(-15).decompress(bruto[inicio:], 64 * 1024).decode("latin-1")
    return texto.splitlines()[:n]


def test_tse_resultado_mantem_os_campos_lidos():
    from lumen_eleicoes import tse
    eleicoes = tse.ler_catalogo(_obter_bytes(tse.url_catalogo()))
    geral = next(e for e in eleicoes if e.tipo == "geral")
    pres = geral.cargo("presidente")
    bruto = json.loads(_obter_bytes(tse.url_resultado(geral.ciclo, pres.eleicao_tse, 1, "br")))
    assert {"carg", "s", "e", "v", "dt", "ht", "tf"} <= _campos(bruto)
    cand = bruto["carg"][0]["agr"][0]["par"][0]["cand"][0]
    assert {"n", "sqcand", "nmu", "vap", "dvt", "st"} <= _campos(cand)
    r = tse.ler_resultado(bruto)
    assert sum(c.votos for c in r.candidatos if c.valido) == r.votos.validos
    ab = tse.ler_andamento(_obter_bytes(tse.url_andamento(geral.ciclo, pres.eleicao_tse, "br")))
    assert len(ab) >= 27
    municipios = tse.ler_municipios(_obter_bytes(tse.url_municipios(geral.ciclo, pres.eleicao_tse)))
    assert len([m for m in municipios if m.codigo_ibge]) >= 5570


def test_dados_abertos_mantem_cabecalhos():
    from lumen_eleicoes import dados_abertos as da
    pacote = da.classificar_recursos(da.ler_pacote(_obter_bytes(da.url_pacote(2022))))
    assert pacote[da.CONJUNTO_VOTACAO] and pacote[da.CONJUNTO_DETALHE]
    for conjunto, obrigatorias in ((da.CONJUNTO_VOTACAO, da.COLUNAS_VOTACAO),
                                   (da.CONJUNTO_DETALHE, da.COLUNAS_DETALHE)):
        cabecalho = _primeiras_linhas_do_zip(da.url_conjunto(conjunto, 2022))[0]
        colunas = {c.strip('"') for c in cabecalho.split(";")}
        faltando = set(obrigatorias) - colunas
        assert not faltando, f"{conjunto}: colunas sumiram: {sorted(faltando)}"


def test_ibge_malha_continua_topojson():
    from lumen_eleicoes import geo
    topo = geo.validar_topojson(_obter_bytes(geo.url_uf_por_municipio("12")))
    assert len(geo.codigos_da_malha(topo)) == 22


@pytest.mark.skipif(os.environ.get("LUMEN_TESTE_CONTRATO_PESADO") != "1",
                    reason="baixa o detalhe da apuração de 2022 inteiro; defina LUMEN_TESTE_CONTRATO_PESADO=1")
def test_totais_de_2022_conferem_com_o_tse(tmp_path):
    """Aptos do 1º turno de 2022 para Presidente = 156.454.011 (cabeçalho do
    Historico_Totalizacao do próprio TSE, QT_APTOS_TOTAL)."""
    from lumen_eleicoes import dados_abertos as da
    from lumen_eleicoes.transferencia import baixar_arquivo
    destino = tmp_path / "detalhe.zip"
    baixar_arquivo(da.url_conjunto(da.CONJUNTO_DETALHE, 2022), destino, user_agent=UA)
    with da.abrir_zip(destino) as zf:
        br = da.tem_arquivo_br(zf.namelist())
        totais = da.ler_detalhe(da.fluxos_do_zip(zf), pular_presidente_nos_estados=br)
    t = totais[("2022-1t-geral", 1, ("br",))]
    assert t.aptos == 156_454_011
    assert 0.9 < t.validos / t.comparecimento < 1.0


def test_mercado_livre_busca_mantem_os_campos_lidos():
    """Busca do varejo (ADR-027): a resposta tem ``results`` com os campos que ``varejo.ler_ofertas`` lê.

    Com ``LUMEN_ML_TOKEN``, o pedido leva o token. Resposta 401/403 falha com a mensagem da loja, que diz se
    o acesso passou a exigir outro tipo de credencial.
    """
    url = "https://api.mercadolibre.com/sites/MLB/search?q=notebook%20i5%208gb%20ssd%20256gb&limit=5"
    cabecalhos = {"User-Agent": UA, "Accept": "application/json"}
    if os.environ.get("LUMEN_ML_TOKEN"):
        cabecalhos["Authorization"] = f"Bearer {os.environ['LUMEN_ML_TOKEN']}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=cabecalhos), timeout=60) as r:
            corpo = json.loads(r.read())
    except urllib.error.HTTPError as e:
        pytest.fail(f"a busca respondeu {e.code}: {e.read()[:300]!r} — revisar a credencial do varejo")
    assert corpo.get("results"), "a busca não trouxe resultados"
    faltando = {"id", "title", "price", "currency_id", "condition", "permalink"} - set(corpo["results"][0])
    assert not faltando, f"campos sumiram da busca: {sorted(faltando)}"


@pytest.mark.parametrize("serie", ["ca", "glp"])
def test_anp_serie_semestral_continua_publicada(serie):
    """O arquivo semestral mais recente previsto continua no endereço que ``anp.url_semestre`` monta.

    A série ``glp`` (gás de cozinha) usa o padrão de nome da ``ca``; este teste é a conferência.
    """
    from lumen_mercado.anp import url_semestre
    hoje = date.today()
    # folga de dois meses depois do fim do semestre para a publicação
    if hoje.month >= 9:
        ano, semestre = hoje.year, 1
    elif hoje.month >= 3:
        ano, semestre = hoje.year - 1, 2
    else:
        ano, semestre = hoje.year - 1, 1
    req = urllib.request.Request(url_semestre(ano, semestre, serie), headers={"User-Agent": UA}, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            assert r.status == 200
    except urllib.error.HTTPError as e:
        pytest.fail(f"série {serie} da ANP {ano}-{semestre} respondeu {e.code}: revisar url_semestre")


def test_anp_pagina_semanal_lista_planilhas_recentes():
    """A página do levantamento semanal cita planilhas ``revendas_lpc`` e a mais nova é das últimas semanas."""
    from lumen_mercado.anp import PAGINA_SEMANAS, links_semanais
    req = urllib.request.Request(PAGINA_SEMANAS, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        html = r.read().decode("utf-8", errors="replace")
    semanas = links_semanais(html)
    assert semanas, "nenhuma planilha revendas_lpc na página: revisar o padrão de links_semanais"
    assert semanas[-1].fim >= date.today() - timedelta(days=35), f"planilha mais nova termina em {semanas[-1].fim}"
