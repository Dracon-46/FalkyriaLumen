"""Locais de votação por zona: leitura do CSV do TSE, filtro pelo contorno do município e arquivos do mapa.

Os recortes em ``testes/fixtures/tse/locais_votacao`` são linhas reais dos arquivos de 2024 e 2026, sem
edição: São Caetano do Sul (SP), com as zonas 166 e 269, uma linha por local (mais uma segunda seção de um
local e uma linha do 2º turno), e duas linhas de Bragança Paulista (zonas 27 e 298).
"""

from __future__ import annotations

import io
import json
import threading
import urllib.request
import zipfile
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from lumen_eleicoes import cli, geo, preparacao, referencias, zonas
from lumen_eleicoes import dados_abertos as da
from lumen_eleicoes.configuracao import carregar
from lumen_eleicoes.transferencia import Manifesto
from lumen_ingestao.cliente_http import ClienteHttp

FIX = Path(__file__).resolve().parents[3] / "testes" / "fixtures" / "tse" / "locais_votacao"
RECORTE_2026 = FIX / "eleitorado_local_votacao_2026_SP_recorte.csv"
RECORTE_2024 = FIX / "eleitorado_local_votacao_2024_recorte.csv"
SAO_CAETANO, BRAGANCA = "3548807", "3507605"


def _zip(caminho: Path, arquivos: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(caminho, "w", zipfile.ZIP_DEFLATED) as zf:
        for nome, conteudo in arquivos.items():
            zf.writestr(nome, conteudo)
        zf.writestr("leiame.pdf", b"%PDF-1.4")
    return caminho


@pytest.fixture
def zip_2026(tmp_path):
    corpo = RECORTE_2026.read_bytes()
    # O _BRASIL repete os arquivos por UF e não pode ser somado de novo
    return _zip(tmp_path / "eleitorado_local_votacao_2026.zip", {
        "eleitorado_local_votacao_2026_SP.csv": corpo, "eleitorado_local_votacao_2026_BRASIL.csv": corpo})


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("LUMEN_CONTATO", "c@exemplo.org")
    monkeypatch.delenv("LUMEN_ELEICOES_SAIDA", raising=False)
    toml = tmp_path / "lumen.toml"
    toml.write_text(f'[dados]\nraiz = "{(tmp_path / "dados").as_posix()}"\n[eleicoes]\n'
                    f'saida = "{(tmp_path / "feeds").as_posix()}"\n', encoding="utf-8")
    return carregar(toml)


def ler(caminho: Path) -> dict:
    return json.loads(caminho.read_text(encoding="utf-8"))


# ------------------------------------------------------------------ leitura

def test_coordenada_aceita_ponto_e_virgula():
    assert zonas.coordenada("-23,6292671") == pytest.approx(-23.6292671)
    assert zonas.coordenada("-23.6332363") == pytest.approx(-23.6332363)
    assert zonas.coordenada("-1") is None and zonas.coordenada("") is None and zonas.coordenada(None) is None
    assert zonas.coordenada("#NULO#") is None and zonas.coordenada("abc") is None and zonas.coordenada("nan") is None
    assert zonas.url_locais(2026).endswith("/eleitorado_locais_votacao/eleitorado_local_votacao_2026.zip")


def test_le_o_recorte_real_de_2026(zip_2026):
    municipios = zonas.ler_zip_locais(zip_2026)
    scs = municipios[("sp", "70777")]
    assert scs.nome_tse == "SÃO CAETANO DO SUL" and scs.zonas == ["166", "269"]
    assert len(scs.locais) == 31                                # o 2º turno não entra
    local = scs.locais[("269", "1074")]
    assert local.eleitores == 395 + 401                         # duas seções do mesmo local
    assert scs.locais[("166", "1074")].eleitores == 375         # o mesmo prédio também é local da zona 166
    assert local.lat == pytest.approx(-23.6409505) and local.lon == pytest.approx(-46.5627076)
    assert municipios[("sp", "62510")].zonas == ["27", "298"]


def test_recorte_de_2024_com_ponto_decimal_e_sem_coordenada():
    with open(RECORTE_2024, "rb") as fh:
        scs = zonas.ler_locais(fh)[("sp", "70777")]
    com, sem = scs.locais[("166", "1040")], scs.locais[("166", "1244")]
    assert com.lat == pytest.approx(-23.6332363) and sem.lat is None and sem.eleitores == 270


def test_linha_sem_zona_e_coordenada_fora_do_brasil_ficam_de_fora():
    cab = RECORTE_2026.read_bytes().split(b"\r\n")[0]
    linha = RECORTE_2026.read_bytes().split(b"\r\n")[1]
    colunas = cab.decode("latin-1").replace('"', "").split(";")
    valores = linha.decode("latin-1").split(";")
    sem_zona = valores.copy()
    sem_zona[colunas.index("NR_ZONA")] = "0"
    no_mar = valores.copy()
    no_mar[colunas.index("NR_LOCAL_VOTACAO")] = "9999"
    no_mar[colunas.index("NR_LATITUDE")] = '"10,5"'
    corpo = b"\r\n".join([cab, ";".join(sem_zona).encode("latin-1"), ";".join(no_mar).encode("latin-1")])
    m = zonas.ler_locais(io.BytesIO(corpo))[("sp", "70777")]
    assert list(m.locais) == [("269", "9999")] and m.locais[("269", "9999")].lat is None


# ------------------------------------------------------------------ contorno

QUADRADO = [[(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]]


def test_dentro_e_distancia_da_borda():
    assert zonas.dentro((0.5, 0.5), QUADRADO) and not zonas.dentro((1.5, 0.5), QUADRADO)
    # Buraco: a regra par-ímpar o deixa de fora
    com_buraco = QUADRADO + [[(0.4, 0.4), (0.6, 0.4), (0.6, 0.6), (0.4, 0.6)]]
    assert not zonas.dentro((0.5, 0.5), com_buraco) and zonas.dentro((0.2, 0.2), com_buraco)
    assert zonas.distancia_borda_m((1.001, 0.5), QUADRADO) == pytest.approx(111.3, abs=1)
    assert zonas.no_contorno_fino((1.002, 0.5), QUADRADO) and not zonas.no_contorno_fino((1.01, 0.5), QUADRADO)
    assert zonas.caixa(QUADRADO) == (0.0, 0.0, 1.0, 1.0)


def test_sem_contorno_fino_vale_a_malha_da_uf():
    vizinho = [[(1.0, 0.0), (2.0, 0.0), (2.0, 1.0), (1.0, 1.0)]]
    assert zonas.no_municipio((0.5, 0.5), QUADRADO, [vizinho])
    assert not zonas.no_municipio((1.5, 0.5), QUADRADO, [vizinho])          # dentro do vizinho
    assert zonas.no_municipio((-0.02, 0.5), QUADRADO, [vizinho])            # fora de todos, perto
    assert not zonas.no_municipio((-0.5, 0.5), QUADRADO, [vizinho])         # longe


def test_aneis_da_malha_sem_transform():
    topo = {"type": "Topology", "arcs": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
            "objects": {"o": {"type": "GeometryCollection", "geometries": [
                {"type": "MultiPolygon", "arcs": [[[0]]], "properties": {"codarea": "1"}},
                {"type": "Point", "coordinates": [0, 0], "properties": {"codarea": "2"}}]}}}
    assert zonas.aneis_da_malha(topo) == {"1": [[(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)]]}


# ------------------------------------------------------------------ arquivos

def test_grava_o_mapa_das_zonas(zip_2026, tmp_path):
    raiz = tmp_path / "feeds"
    manifesto = Manifesto(url="https://cdn/x.zip", arquivo="x.zip", tamanho=1, sha256="ab" * 32, etag=None,
                          ultima_modificacao=None, baixado_em="2026-10-15T12:00:00+00:00")
    avisos = []
    r = zonas.gravar_zonas(2026, zip_2026, raiz, referencias.cadastro_embutido(), manifesto=manifesto,
                           progresso=avisos.append)
    assert (r.municipios, r.zonas, r.locais, r.sem_coordenada, r.fora_do_municipio) == (2, 4, 33, 0, 0)
    assert r.para_json()["ano"] == 2026 and avisos

    indice = ler(raiz / "geo" / "zonas-2026" / "indice.json")
    assert indice["tipo"] == "zonas-indice" and indice["municipios"] == {BRAGANCA: 2, SAO_CAETANO: 2}
    assert indice["origem"] == {"fonte": "dados_abertos", "url": "https://cdn/x.zip", "sha256": "ab" * 32,
                                "coletado_em": "2026-10-15T12:00:00+00:00", "registro_bronze": None}

    scs = ler(raiz / "geo" / "zonas-2026" / f"mu-{SAO_CAETANO}.json")
    assert scs["versao"] == 1 and scs["tipo"] == "zonas" and scs["ano"] == 2026
    assert scs["municipio"] == {"ibge": SAO_CAETANO, "tse": "70777", "uf": "sp", "nome": "São Caetano do Sul"}
    assert [z["zona"] for z in scs["zonas"]] == ["166", "269"]
    assert sum(z["locais"] for z in scs["zonas"]) == len(scs["locais"]) == 31
    assert sum(z["eleitores"] for z in scs["zonas"]) == sum(local[3] for local in scs["locais"])
    lon, lat, zona, eleitores, nome = scs["locais"][0]
    assert zona == "166" and isinstance(eleitores, int) and nome
    assert [loc[2] for loc in scs["locais"]] == sorted((loc[2] for loc in scs["locais"]), key=int)
    assert scs["descartados"] == {"sem_coordenada": 0, "fora_do_municipio": 0}

    # Mesmos bytes a cada geração
    antes = (raiz / "geo" / "zonas-2026" / f"mu-{SAO_CAETANO}.json").read_bytes()
    zonas.gravar_zonas(2026, zip_2026, raiz, referencias.cadastro_embutido(), manifesto=manifesto)
    assert (raiz / "geo" / "zonas-2026" / f"mu-{SAO_CAETANO}.json").read_bytes() == antes


def test_local_em_outro_municipio_e_descartado(tmp_path):
    corpo = RECORTE_2026.read_bytes().split(b"\r\n")
    cab, linha = corpo[0], corpo[1]
    colunas = cab.decode("latin-1").replace('"', "").split(";")
    errado = linha.decode("latin-1").split(";")
    errado[colunas.index("NR_LOCAL_VOTACAO")] = "8888"
    errado[colunas.index("NR_LATITUDE")] = '"-23,5505"'            # Praça da Sé, na capital
    errado[colunas.index("NR_LONGITUDE")] = '"-46,6333"'
    linhas = [cab] + [x for x in corpo[1:] if x] + [";".join(errado).encode("latin-1")]
    z = _zip(tmp_path / "l.zip", {"eleitorado_local_votacao_2026_SP.csv": b"\r\n".join(linhas)})
    r = zonas.gravar_zonas(2026, z, tmp_path / "feeds", referencias.cadastro_embutido())
    assert r.fora_do_municipio == 1
    scs = ler(tmp_path / "feeds" / "geo" / "zonas-2026" / f"mu-{SAO_CAETANO}.json")
    assert scs["descartados"]["fora_do_municipio"] == 1 and len(scs["locais"]) == 31

    # Só com a malha da UF (sem o contorno fino): a regra da malha simplificada também descarta
    malhas = tmp_path / "malhas"
    malhas.mkdir()
    (malhas / "uf-sp-mu.json").write_bytes((referencias.DIR_DADOS / "geo" / "uf-sp-mu.json").read_bytes())
    r = zonas.gravar_zonas(2026, z, tmp_path / "f2", referencias.cadastro_embutido(), malhas=malhas)
    assert r.fora_do_municipio >= 1 and r.municipios == 2


def test_municipio_sem_malha_ou_fora_do_cadastro_fica_de_fora(zip_2026, tmp_path):
    r = zonas.gravar_zonas(2026, zip_2026, tmp_path / "feeds", referencias.cadastro_embutido(),
                           malhas=tmp_path / "vazio")
    assert r.municipios == 0 and sorted(r.sem_malha) == ["sp62510", "sp70777"]
    assert ler(tmp_path / "feeds" / "geo" / "zonas-2026" / "indice.json")["municipios"] == {}


def test_contornos_finos_embutidos_cobrem_o_mapa_das_zonas():
    embutidos = referencias.arquivos_embutidos()
    contornos = [destino for _, destino in embutidos if destino.startswith("geo/mu/")]
    assert f"geo/mu/{SAO_CAETANO}.json" in contornos and len(contornos) >= 190
    topo = ler(referencias.DIR_DADOS / "geo" / "mu" / f"{SAO_CAETANO}.json")
    assert list(zonas.aneis_da_malha(topo)) == [SAO_CAETANO]


# ------------------------------------------------------------------ download, comando e preparar

class _Cdn:
    """CDN local com o ZIP de locais de 2026."""

    def __init__(self, conteudo: bytes):
        class T(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                ok = self.path.endswith("/eleitorado_local_votacao_2026.zip")
                corpo = conteudo if ok else b"nao existe"
                self.send_response(200 if ok else 404)
                self.send_header("Content-Length", str(len(corpo)))
                self.end_headers()
                self.wfile.write(corpo)
        self.http = ThreadingHTTPServer(("127.0.0.1", 0), T)
        self.base = f"http://127.0.0.1:{self.http.server_address[1]}"
        threading.Thread(target=self.http.serve_forever, daemon=True).start()

    def fechar(self):
        self.http.shutdown()
        self.http.server_close()


@pytest.fixture
def cdn(zip_2026, monkeypatch):
    srv = _Cdn(zip_2026.read_bytes())
    monkeypatch.setattr(da, "CDN", srv.base)
    yield srv
    srv.fechar()


def test_comando_zonas(cfg, cdn, capsys, monkeypatch):
    monkeypatch.setattr(cli, "carregar", lambda *a, **k: cfg)
    assert cli.main(["zonas", "--anos", "2026", "--sem-bronze"]) == 0
    saida = json.loads(capsys.readouterr().out)
    assert saida[0]["ano"] == 2026 and saida[0]["municipios"] == 2
    assert (cfg.saida / "geo" / "zonas-2026" / f"mu-{SAO_CAETANO}.json").exists()
    assert (cfg.arquivos / "locais" / "eleitorado_local_votacao_2026.zip.manifesto.json").exists()
    assert cli._anos_locais("todos") == list(zonas.ANOS_LOCAIS) and cli._anos_locais("2018,2026") == [2026, 2018]
    with pytest.raises(Exception):
        cli._anos_locais("2016")


def test_etapa_das_zonas_no_preparar(cfg, cdn, monkeypatch):
    linhas = []
    op = preparacao.OpcoesPreparacao(anos=[2026], ao_vivo=False, portal=False, bronze=False, apagar_arquivos=True)
    prep = preparacao.Preparacao(cfg, op, saida=linhas.append, hoje=date(2026, 10, 15), dormir=lambda s: None)
    prep.carregar_zonas(2026)
    assert prep.resumo.zonas == [{"ano": 2026, "situacao": "gravadas", "municipios": 2, "locais": 33}]
    assert prep.estado.zonas_prontas(2026) and not (cfg.arquivos / "locais" / "eleitorado_local_votacao_2026.zip").exists()
    assert prep.anos_das_zonas() == [2026]
    # 2026 é o ano em aberto: conferido na fonte a cada execução, e com a mesma fonte não grava de novo
    prep.carregar_zonas(2026)
    assert prep.resumo.zonas[-1] == {"ano": 2026, "situacao": "sem mudança na fonte"}
    # Ano fechado já gravado: nem consulta a fonte
    monkeypatch.setattr(preparacao.da, "ANO_EM_ABERTO", 2030)
    prep.carregar_zonas(2026)
    assert prep.resumo.zonas[-1] == {"ano": 2026, "situacao": "já gravadas"}
    # Ano que a fonte não tem: vira erro do resumo, sem derrubar a carga
    prep.carregar_zonas(2024)
    assert prep.resumo.zonas[-1] == {"ano": 2024, "situacao": "erro"} and prep.resumo.erros
    estado = json.loads((cfg.estado / preparacao.ARQUIVO_ESTADO).read_text(encoding="utf-8"))
    assert estado["zonas"]["2026"]["municipios"] == 2


def test_ano_processado_por_versao_anterior_e_refeito(tmp_path):
    estado = preparacao.EstadoPreparacao(tmp_path / "p.json")
    estado.anos = {"2022": {"entradas": {}}, "1950": {"entradas": {}}}
    assert not estado.ano_pronto(2022) and estado.ano_pronto(1950) and not estado.ano_pronto(2018)
    estado.marcar_ano(2022, {}, ["2022-1t-geral"])
    assert estado.ano_pronto(2022)
    assert preparacao.EstadoPreparacao.carregar(tmp_path / "p.json").anos["2022"]["processamento"] == (
        preparacao.VERSAO_PROCESSAMENTO)


def test_local_sem_coordenada_conta_no_municipio(tmp_path):
    # A linha de 2024 (local 1244, coordenada -1) junto das de 2026: mesmo cabeçalho
    sem = RECORTE_2024.read_bytes().split(b"\r\n")[2]
    corpo = RECORTE_2026.read_bytes().rstrip(b"\r\n") + b"\r\n" + sem + b"\r\n"
    z = _zip(tmp_path / "l.zip", {"eleitorado_local_votacao_2026_SP.csv": corpo})
    r = zonas.gravar_zonas(2026, z, tmp_path / "feeds", referencias.cadastro_embutido())
    assert r.sem_coordenada == 1
    scs = ler(tmp_path / "feeds" / "geo" / "zonas-2026" / f"mu-{SAO_CAETANO}.json")
    z166 = next(z for z in scs["zonas"] if z["zona"] == "166")
    # Os eleitores do local sem coordenada contam na zona; o local não entra no mapa
    assert z166["eleitores"] == sum(loc[3] for loc in scs["locais"] if loc[2] == "166") + 270


def test_executar_com_a_etapa_das_zonas(cfg, cdn):
    # parar(): começa a etapa das zonas e faz 2026; para antes dos dados abertos (que iriam ao CKAN)
    respostas = iter([False, False])
    op = preparacao.OpcoesPreparacao(anos=[2026], ao_vivo=False, portal=False, bronze=False)
    prep = preparacao.Preparacao(cfg, op, saida=lambda m: None, parar=lambda: next(respostas, True),
                                 dormir=lambda s: None)
    r = prep.executar()
    assert [z["situacao"] for z in r.zonas] == ["gravadas"] and r.anos == []
    assert r.para_json()["zonas"][0]["municipios"] == 2
    # Sem o histórico, o mapa das zonas continua (já gravado, não baixa de novo); só --sem-zonas o tira
    sem_historico = preparacao.Preparacao(cfg, preparacao.OpcoesPreparacao(anos=[2026], ao_vivo=False, portal=False,
                                                                           historico=False, bronze=False),
                                          saida=lambda m: None)
    assert [z["ano"] for z in sem_historico.executar().zonas] == [2026]
    sem = preparacao.Preparacao(cfg, preparacao.OpcoesPreparacao(anos=[2026], ao_vivo=False, portal=False,
                                                                 historico=False, zonas=False, bronze=False),
                                saida=lambda m: None)
    assert sem.executar().zonas == []


def test_baixar_contornos(tmp_path, monkeypatch):
    fino = (referencias.DIR_DADOS / "geo" / "mu" / f"{SAO_CAETANO}.json").read_bytes()
    pedidos = []

    class T(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            pedidos.append(self.path)
            corpo, status = (fino, 200) if f"/municipios/{SAO_CAETANO}?" in self.path else (b"{}", 404)
            if f"/municipios/{BRAGANCA}?" in self.path:
                corpo, status = fino, 200                     # resposta com o município errado
            self.send_response(status)
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            self.wfile.write(corpo)
    http = ThreadingHTTPServer(("127.0.0.1", 0), T)
    threading.Thread(target=http.serve_forever, daemon=True).start()
    try:
        monkeypatch.setattr(geo, "BASE_MALHAS", f"http://127.0.0.1:{http.server_address[1]}")
        cliente = ClienteHttp(geo.FONTE_ID, user_agent="Lumen/teste (+c@exemplo.org)", rpm=60000,
                              abridor=urllib.request.build_opener(urllib.request.ProxyHandler({})),
                              dormir=lambda s: None)
        gravados = geo.baixar_contornos(cliente, tmp_path, [SAO_CAETANO, SAO_CAETANO])
        assert gravados == [tmp_path / "geo" / "mu" / f"{SAO_CAETANO}.json"] and gravados[0].read_bytes() == fino
        assert "qualidade=maxima" in pedidos[0] and len(pedidos) == 1
        with pytest.raises(geo.MalhaInvalida, match="só do município"):
            geo.baixar_contornos(cliente, tmp_path, [BRAGANCA])
        with pytest.raises(geo.MalhaInvalida, match="HTTP 404"):
            geo.baixar_contornos(cliente, tmp_path, ["1100015"])
        with pytest.raises(ValueError):
            geo.baixar_contornos(cliente, tmp_path, ["35"])
        with pytest.raises(ValueError):
            geo.baixar_contornos(cliente, tmp_path, [SAO_CAETANO], qualidade="ultra")
    finally:
        http.shutdown()
        http.server_close()


def test_verificador_confere_o_mapa_das_zonas(zip_2026, tmp_path):
    from lumen_eleicoes.verificacao import Relatorio, verificar_diretorio, verificar_zonas
    raiz = tmp_path / "feeds"
    referencias.instalar(raiz)
    zonas.gravar_zonas(2026, zip_2026, raiz, referencias.cadastro_embutido())
    (raiz / "indice.json").write_text('{"versao":1,"eleicoes":[]}', encoding="utf-8")
    rel = verificar_diretorio(raiz)
    assert rel.ok and rel.arquivos == 3                      # o índice das zonas e os dois municípios
    caminho = raiz / "geo" / "zonas-2026" / f"mu-{SAO_CAETANO}.json"
    dados = ler(caminho)
    for estrago, esperado in (
        ({**dados, "versao": 9}, "versao 9"),
        ({**dados, "tipo": "outro"}, "fora do contrato"),
        ({k: v for k, v in dados.items() if k != "locais"}, "fora do contrato"),
        ({**dados, "locais": [[1, 2, "999", 3, "x"]]}, "fora do formato"),
        ({**dados, "locais": dados["locais"][1:]}, "não batem"),
        ({"versao": 1, "tipo": "zonas-indice"}, "sem municípios"),
    ):
        r = Relatorio()
        verificar_zonas(caminho, estrago, r)
        assert esperado in r.problemas[0], estrago.get("tipo")


def test_regravar_apaga_municipio_que_saiu_e_lista_os_sem_contorno(zip_2026, tmp_path):
    raiz = tmp_path / "feeds"
    antigo = raiz / "geo" / "zonas-2026" / "mu-9999999.json"
    antigo.parent.mkdir(parents=True)
    antigo.write_text("{}", encoding="utf-8")
    r = zonas.gravar_zonas(2026, zip_2026, raiz, referencias.cadastro_embutido())
    assert r.removidos == 1 and not antigo.exists() and r.sem_contorno == []
    # Só com a malha da UF: os dois municípios ficam sem o contorno fino, e o resumo diz isso
    malhas = tmp_path / "malhas"
    malhas.mkdir()
    (malhas / "uf-sp-mu.json").write_bytes((referencias.DIR_DADOS / "geo" / "uf-sp-mu.json").read_bytes())
    r = zonas.gravar_zonas(2026, zip_2026, tmp_path / "f2", referencias.cadastro_embutido(), malhas=malhas)
    assert sorted(r.sem_contorno) == [BRAGANCA, SAO_CAETANO] and r.para_json()["sem_contorno"]
    assert zonas.municipios_dos_indices(raiz) == {BRAGANCA, SAO_CAETANO}
    assert zonas.municipios_dos_indices(tmp_path / "vazio") == set()


def test_revisao_ou_contornos_novos_regravam_as_zonas(tmp_path, monkeypatch):
    estado = preparacao.EstadoPreparacao(tmp_path / "p.json")
    estado.marcar_zonas(2026, {"x.zip": "ab"}, 2)
    assert estado.zonas_prontas(2026)
    monkeypatch.setattr(zonas, "REVISAO_ZONAS", zonas.REVISAO_ZONAS + 1)
    assert not estado.zonas_prontas(2026)
    monkeypatch.undo()
    monkeypatch.setattr(zonas, "assinatura_contornos", lambda: "outra")
    assert not estado.zonas_prontas(2026)
    # Registro de antes da revisão: grava de novo
    estado.zonas["2024"] = {"entradas": {}}
    assert not estado.zonas_prontas(2024)


def test_comando_mapas_contornos(cfg, monkeypatch, capsys):
    monkeypatch.setattr(cli, "carregar", lambda *a, **k: cfg)
    assert cli.main(["mapas", "--contornos", "--sem-bronze"]) == 2           # sem índice das zonas
    indice = cfg.saida / "geo" / "zonas-2026" / "indice.json"
    indice.parent.mkdir(parents=True)
    indice.write_text(json.dumps({"municipios": {SAO_CAETANO: 2}}), encoding="utf-8")
    pedidos = []
    monkeypatch.setattr(geo, "baixar_contornos", lambda cliente, raiz, codigos, bronze=None: (
        pedidos.append(sorted(codigos)) or [Path(raiz) / "geo" / "mu" / f"{c}.json" for c in codigos]))
    capsys.readouterr()
    assert cli.main(["mapas", "--contornos", "--sem-bronze"]) == 0
    assert pedidos == [[SAO_CAETANO]] and "contornos" in json.loads(capsys.readouterr().out)
