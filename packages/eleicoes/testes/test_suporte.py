"""Cadastro de municípios, malhas do IBGE, servidor local, verificação, configuração e CLI."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from lumen_eleicoes import cli, geo, tse
from lumen_eleicoes.configuracao import ConfiguracaoAusente, carregar
from lumen_eleicoes.municipios import CadastroMunicipios, nome_da_uf, nomes_do_ibge
from lumen_eleicoes.servidor import ServidorPortal
from lumen_eleicoes.verificacao import verificar_diretorio
from lumen_ingestao.bronze import ArtefatoBruto

RAIZ = Path(__file__).resolve().parents[3]
FIX_TSE = RAIZ / "testes" / "fixtures" / "tse"
FIX_IBGE = RAIZ / "testes" / "fixtures" / "ibge"
AMOSTRA = RAIZ / "testes" / "fixtures" / "eleicoes_feed"
SEM_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))


# ------------------------------------------------------------------ municípios

def test_cadastro_tse_com_nomes_do_ibge(tmp_path):
    municipios = tse.ler_municipios((FIX_TSE / "mun-e006257-cm_recorte.json").read_bytes())
    nomes = nomes_do_ibge((FIX_IBGE / "municipios_nivelado_amostra.json").read_bytes())
    assert nomes["3550308"] == "São Paulo"
    cad = CadastroMunicipios.de_tse(municipios, nomes)
    sp = cad.por_tse("SP", 71072)
    assert (sp.nome, sp.nome_tse, sp.ibge, sp.chave, sp.capital) == ("São Paulo", "SÃO PAULO", "3550308", "3550308", True)
    assert cad.por_ibge("3550308") is sp
    assert cad.por_tse("ac", "1120").nome == "Acrelândia"            # sem nome IBGE na amostra: o do TSE, legível
    assert cad.por_tse("zz", "29254").chave == "zz-29254"
    assert sorted(m.tse for m in cad.da_uf("ac")) == ["01058", "01120", "01570"]
    caminho = cad.gravar(tmp_path / "municipios.json")
    de_volta = CadastroMunicipios.carregar(caminho)
    assert len(de_volta) == len(cad) == 9
    assert de_volta.por_tse("sp", "71072") == sp
    assert json.loads(caminho.read_text(encoding="utf-8"))["versao"] == 1


def test_completar_municipio_fora_do_cadastro():
    cad = CadastroMunicipios()
    m = cad.completar("AP", 6130, "LARANJAL DO JARI")
    assert (m.uf, m.tse, m.ibge, m.chave, m.nome) == ("ap", "06130", None, "ap-06130", "Laranjal do Jari")
    assert cad.completar("ap", "06130", "outro nome") is m


@pytest.mark.parametrize("tse_nome, esperado", [
    ("SÃO PAULO", "São Paulo"),
    ("SANT'ANA DO LIVRAMENTO", "Sant'Ana do Livramento"),
    ("ESTRELA D'OESTE", "Estrela d'Oeste"),
    ("PAU D'ARCO DO PIAUÍ", "Pau d'Arco do Piauí"),
    ("EMBU-GUAÇU", "Embu-Guaçu"),
    ("DE MOURA", "De Moura"),
    ("ABU DHABI", "Abu Dhabi"),
    ("Já Formatado", "Já Formatado"),
    ("", ""),
])
def test_nome_legivel(tse_nome, esperado):
    from lumen_eleicoes.municipios import nome_legivel
    assert nome_legivel(tse_nome) == esperado


def test_nomes_de_uf():
    assert nome_da_uf("sp") == "São Paulo"
    assert nome_da_uf("ZZ") == "Exterior"
    assert nome_da_uf("br") == "Brasil"
    assert nome_da_uf("xx") == "XX"
    assert nomes_do_ibge([{"id": 1, "nome": "A"}, {"municipio-id": 2, "municipio-nome": "B"}, {}]) == {"1": "A", "2": "B"}


# ------------------------------------------------------------------ malhas

def test_malha_real_do_acre_e_valida():
    topo = geo.validar_topojson((FIX_IBGE / "malha_uf12_municipios_minima.json").read_bytes())
    codigos = geo.codigos_da_malha(topo)
    assert len(codigos) == 22 and codigos[0] == "1200013" and all(c.startswith("12") for c in codigos)


@pytest.mark.parametrize("ruim", [
    {"type": "FeatureCollection"},
    {"type": "Topology", "arcs": [], "objects": {}},
    {"type": "Topology", "arcs": [[[0, 0]]], "objects": {"x": {"geometries": []}}},
    {"type": "Topology", "arcs": [[[0, 0]]], "objects": {"x": {"geometries": [{"type": "Polygon", "arcs": [[0]]}]}}},
    {"type": "Topology", "arcs": [[[0, 0]]], "objects": {"x": {"geometries": [
        {"type": "Point", "arcs": [], "properties": {"codarea": "1"}}]}}},
    {"type": "Topology", "arcs": [[[0, 0]]], "objects": {"x": {"geometries": [
        {"type": "Polygon", "arcs": [[5]], "properties": {"codarea": "1"}}]}}},
])
def test_malha_invalida_e_recusada(ruim):
    with pytest.raises(geo.MalhaInvalida):
        geo.validar_topojson(json.dumps(ruim))


def test_urls_das_malhas():
    assert geo.url_brasil_por_uf().endswith("/paises/BR?formato=application/json&intrarregiao=UF&qualidade=minima")
    assert "/estados/35?" in geo.url_uf_por_municipio("35", "intermediaria")


class _ClienteFalso:
    def __init__(self, conteudo: bytes, status: int = 200):
        self.conteudo, self.status, self.pedidos = conteudo, status, []

    def obter(self, url, cabecalhos=None):
        self.pedidos.append(url)
        return ArtefatoBruto(conteudo=self.conteudo, fonte_id="ibge_malhas", url_solicitada=url, url_efetiva=url,
                             status_http=self.status, tipo_midia="application/json")


def test_baixar_malhas_grava_os_bytes_validados(tmp_path):
    bruto = (FIX_IBGE / "malha_uf12_municipios_minima.json").read_bytes()
    cliente = _ClienteFalso(bruto)
    gravados = geo.baixar_malhas(cliente, tmp_path, ufs=["ac"])
    assert [p.name for p in gravados] == ["br-uf.json", "uf-ac-mu.json"]
    assert (tmp_path / "geo" / "uf-ac-mu.json").read_bytes() == bruto
    with pytest.raises(ValueError):
        geo.baixar_malhas(cliente, tmp_path, qualidade="ultra")
    with pytest.raises(geo.MalhaInvalida):
        geo.baixar_malhas(_ClienteFalso(b"", 503), tmp_path, ufs=["ac"])


# ------------------------------------------------------------------ servidor

@pytest.fixture
def site(tmp_path):
    raiz = tmp_path / "out"
    (raiz / "eleicoes").mkdir(parents=True)
    (raiz / "index.html").write_text("<h1>Lumen</h1>", encoding="utf-8")
    (raiz / "eleicoes" / "index.html").write_text("<h1>Eleições</h1>", encoding="utf-8")
    (raiz / "_next" / "static").mkdir(parents=True)
    (raiz / "_next" / "static" / "a.js").write_text("1", encoding="utf-8")
    (raiz / "sobre.html").write_text("sobre", encoding="utf-8")
    return raiz


def _get(url):
    try:
        with SEM_PROXY.open(url, timeout=5) as r:
            return r.status, {k.lower(): v for k, v in r.headers.items()}, r.read()
    except urllib.error.HTTPError as e:
        return e.code, {k.lower(): v for k, v in e.headers.items()}, b""


def test_servidor_entrega_site_e_feeds(site):
    with ServidorPortal(site, AMOSTRA, porta=0) as srv:
        st, cab, corpo = _get(srv.endereco + "/dados/eleicoes/indice.json")
        assert st == 200 and cab["cache-control"] == "no-cache" and "application/json" in cab["content-type"]
        assert json.loads(corpo)["versao"] == 1
        st, _, corpo = _get(srv.endereco + "/eleicoes/")
        assert st == 200 and "Eleições" in corpo.decode()
        st, cab, _ = _get(srv.endereco + "/_next/static/a.js")
        assert "immutable" in cab["cache-control"] and cab["x-content-type-options"] == "nosniff"
        assert _get(srv.endereco + "/sobre")[2] == b"sobre"
        # Não sai do diretório servido
        assert _get(srv.endereco + "/dados/eleicoes/../../../../etc/passwd")[0] == 404
        assert _get(srv.endereco + "/%2e%2e/%2e%2e/etc/passwd")[0] == 404
        assert _get(srv.endereco + "/dados/eleicoes/nao-existe.json")[0] == 404


# ------------------------------------------------------------------ verificação

def test_verificacao_acusa_problemas(tmp_path):
    assert not verificar_diretorio(tmp_path).ok
    (tmp_path / "indice.json").write_text(json.dumps({"versao": 1, "eleicoes": [{
        "id": "2022-1t-geral", "origem": "dados_abertos", "ufs": ["sp"],
        "cargos": [{"slug": "presidente", "nivel": "br"}, {"slug": "governador", "nivel": "uf"}]}]}))
    pasta = tmp_path / "2022-1t-geral" / "presidente"
    pasta.mkdir(parents=True)
    (pasta / "uf-sp.json").write_text(json.dumps({"versao": 2}))
    (pasta / "mu-x.json").write_text("{quebrado")
    base = json.loads((AMOSTRA / "2026-1t-geral" / "presidente" / "br.json").read_text(encoding="utf-8"))
    base["candidatos"] = list(reversed(base["candidatos"]))
    base["candidatos"][0]["pct"] = 120
    (pasta / "mu-y.json").write_text(json.dumps(base))
    (pasta / "mu-z.json").write_text(json.dumps({"versao": 1, "tipo": "outro"}))
    (pasta / "mu-w.json").write_text(json.dumps({"versao": 1, "tipo": "resultado"}))
    hist = {"versao": 1, "tipo": "historico", "candidatos": [], "pontos": [{"t": "2"}, {"t": "1"}]}
    (pasta / "historico-br.json").write_text(json.dumps(hist))
    rel = verificar_diretorio(tmp_path)
    texto = "\n".join(rel.problemas)
    for esperado in ("br.json: o índice lista", "governador/uf-sp.json: UF listada", "versao 2", "ilegível",
                     "fora da ordem", "fora de 0–100", "tipo desconhecido", "faltam", "evolução fora de ordem"):
        assert esperado in texto, esperado


# ------------------------------------------------------------------ configuração e CLI

def test_configuracao_exige_contato(tmp_path, monkeypatch):
    monkeypatch.delenv("LUMEN_CONTATO", raising=False)
    monkeypatch.delenv("LUMEN_DADOS", raising=False)
    monkeypatch.delenv("LUMEN_ELEICOES_SAIDA", raising=False)
    with pytest.raises(ConfiguracaoAusente):
        carregar(tmp_path / "nao-existe.toml")
    toml = tmp_path / "lumen.toml"
    toml.write_text('[coleta]\ncontato = "c@exemplo.org"\n[dados]\nraiz = "d"\n'
                    '[eleicoes]\nsaida = "feeds"\nrpm_resultados = 120\n', encoding="utf-8")
    cfg = carregar(toml)
    assert (cfg.contato, cfg.saida, cfg.arquivos, cfg.rpm_resultados) == (
        "c@exemplo.org", Path("feeds"), Path("d/eleicoes/arquivos"), 120)
    assert cfg.bronze == Path("d/bronze")
    assert cfg.user_agent.startswith("Lumen/") and "c@exemplo.org" in cfg.user_agent
    monkeypatch.setenv("LUMEN_ELEICOES_SAIDA", "outra")
    assert carregar(toml).saida == Path("outra")
    assert carregar(tmp_path / "x.toml", exigir_contato=False).contato == ""


def test_cli_verificar_e_amostra(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("LUMEN_CONTATO", raising=False)
    assert cli.main(["--config", str(tmp_path / "x.toml"), "--saida", str(AMOSTRA), "verificar"]) == 0
    assert "0 problema(s)" in capsys.readouterr().out
    assert cli.main(["--config", str(tmp_path / "x.toml"), "--saida", str(tmp_path / "f"), "amostra"]) == 0
    assert (tmp_path / "f" / "indice.json").exists()
    assert cli.main(["--config", str(tmp_path / "x.toml"), "--saida", str(tmp_path / "vazio"), "verificar"]) == 1
    # Comandos que vão à rede exigem contato
    assert cli.main(["--config", str(tmp_path / "x.toml"), "catalogo"]) == 2


def test_cli_anos_validos():
    assert cli._anos("2022, 2018") == [2022, 2018]
    with pytest.raises(Exception):
        cli._anos("2023")
    assert cli._lista("SP, rj,") == ["sp", "rj"] and cli._lista(None) is None


def test_cli_historico_sem_arquivos(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("LUMEN_CONTATO", "c@exemplo.org")
    toml = tmp_path / "lumen.toml"
    toml.write_text(f'[dados]\nraiz = "{tmp_path / "dados"}"\n', encoding="utf-8")
    codigo = cli.main(["--config", str(toml), "--saida", str(tmp_path / "f"), "historico", "processar",
                       "--anos", "2022"])
    assert codigo == 2
    assert "historico baixar" in capsys.readouterr().err


def test_cli_simular_contra_fixtures(tmp_path, monkeypatch):
    monkeypatch.setenv("LUMEN_CONTATO", "c@exemplo.org")
    monkeypatch.setattr(cli.time, "sleep", lambda s: None)
    toml = tmp_path / "lumen.toml"
    toml.write_text(f'[dados]\nraiz = "{tmp_path / "dados"}"\n', encoding="utf-8")
    assert cli.main(["--config", str(toml), "--saida", str(tmp_path / "f"), "simular", "--etapas", "2",
                     "--intervalo", "0", "--ufs", "sp"]) == 0
    indice = json.loads((tmp_path / "f" / "indice.json").read_text(encoding="utf-8"))
    assert indice["eleicoes"][0]["simulacao"] is True and indice["eleicoes"][0]["ao_vivo"] is False
    assert cli.main(["--config", str(toml), "--saida", str(tmp_path / "f"), "simular", "--eleicao", "1990-1t-x",
                     "--etapas", "1"]) == 2


# ------------------------------------------------------------------ CLI de ponta a ponta (servidores locais)

class _Arquivos:
    """Servidor HTTP local que responde caminhos fixos com bytes fixos."""

    def __init__(self, rotas: dict[str, bytes]):
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        self.rotas = rotas
        rotas_ref = self.rotas

        class T(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                corpo = rotas_ref.get(self.path)
                if corpo is None:
                    self.send_response(404)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Length", str(len(corpo)))
                self.end_headers()
                self.wfile.write(corpo)

        self.http = ThreadingHTTPServer(("127.0.0.1", 0), T)
        self.base = f"http://127.0.0.1:{self.http.server_address[1]}"
        threading.Thread(target=self.http.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()

    def parar(self):
        self.http.shutdown()
        self.http.server_close()


def _sem_proxy_no_cliente(monkeypatch):
    """Os clientes do CLI usam o abridor padrão; nos testes, sem o proxy do ambiente."""
    import lumen_ingestao.coleta_http as ch
    original = ch.baixar_http

    def baixar(url, fonte_id, **kw):
        kw["abridor"] = SEM_PROXY
        return original(url, fonte_id, **kw)
    monkeypatch.setattr("lumen_ingestao.cliente_http.baixar_http", baixar)


@pytest.fixture
def cfg_toml(tmp_path, monkeypatch):
    monkeypatch.setenv("LUMEN_CONTATO", "c@exemplo.org")
    _sem_proxy_no_cliente(monkeypatch)
    toml = tmp_path / "lumen.toml"
    # Servidores locais: sem espera do limitador de taxa. Caminho com barras: no Windows, a contrabarra
    # numa string TOML seria lida como escape.
    toml.write_text(f'[dados]\nraiz = "{(tmp_path / "dados").as_posix()}"\n[eleicoes]\nrpm_resultados = 60000\n'
                    'rpm_dados_abertos = 60000\nrpm_ibge = 60000\n', encoding="utf-8")
    return toml


def test_cli_catalogo_municipios_e_ao_vivo(tmp_path, cfg_toml, capsys):
    from lumen_eleicoes.simulacao import Cenario, ServidorSimulado
    saida = tmp_path / "feeds"
    ibge = _Arquivos({"/api/v1/localidades/municipios": (FIX_IBGE / "municipios_nivelado_amostra.json").read_bytes()})
    try:
        with ServidorSimulado(Cenario(FIX_TSE, etapas=1)) as srv:
            import lumen_eleicoes.geo as g
            g_base = g.BASE_LOCALIDADES
            g.BASE_LOCALIDADES = ibge.base + "/api/v1/localidades"
            try:
                assert cli.main(["--config", str(cfg_toml), "catalogo", "--base", srv.base]) == 0
                saida_cat = json.loads(capsys.readouterr().out)
                assert saida_cat["sistema_de_resultados"][0]["id"] == "2026-1t-geral"
                assert cli.main(["--config", str(cfg_toml), "--saida", str(saida), "municipios",
                                 "--base", srv.base]) == 0
            finally:
                g.BASE_LOCALIDADES = g_base
            cad = CadastroMunicipios.carregar(saida / "municipios.json")
            assert cad.por_tse("sp", "71072").nome == "São Paulo"
            assert cli.main(["--config", str(cfg_toml), "--saida", str(saida), "ao-vivo", "--eleicao",
                             "2026-1t-geral", "--cargos", "presidente", "--ufs", "sp", "--uma-vez",
                             "--base", srv.base]) == 0
            assert (saida / "2026-1t-geral" / "presidente" / "uf-sp.json").exists()
            assert any((tmp_path / "dados" / "bronze").rglob("*.json"))
            assert cli.main(["--config", str(cfg_toml), "--saida", str(saida), "ao-vivo", "--eleicao",
                             "1999-1t-geral", "--base", srv.base]) == 2
            assert cli.main(["--config", str(cfg_toml), "--saida", str(saida), "municipios", "--eleicao", "x",
                             "--base", srv.base]) == 2
    finally:
        ibge.parar()


def test_cli_ao_vivo_com_prazo_sai_com_codigo_para_continuar(tmp_path, cfg_toml, capsys, monkeypatch):
    from lumen_eleicoes.coletor import ColetorAoVivo
    from lumen_eleicoes.simulacao import Cenario, ServidorSimulado
    argumentos = ["--config", str(cfg_toml), "--saida", str(tmp_path / "feeds"), "ao-vivo", "--eleicao",
                  "2026-1t-geral", "--cargos", "presidente", "--ufs", "sp", "--intervalo", "0",
                  "--limite-minutos", "0.000001"]
    # Apuração em 20%: o prazo vence depois da primeira passada, e a próxima execução continua
    with ServidorSimulado(Cenario(FIX_TSE, etapas=5)) as srv:
        assert cli.main(argumentos + ["--base", srv.base]) == cli.CODIGO_PRAZO
    assert "prazo de 1e-06 min atingido" in capsys.readouterr().out
    assert (tmp_path / "feeds" / "2026-1t-geral" / "presidente" / "uf-sp.json").exists()
    # Apuração terminada (o recorte das fixtures é de antes do fim, sem a marca): o coletor para por ter
    # terminado, e o prazo não muda a saída
    monkeypatch.setattr(ColetorAoVivo, "_finalizada", lambda self: True)
    with ServidorSimulado(Cenario(FIX_TSE, etapas=1)) as srv:
        assert cli.main(argumentos + ["--base", srv.base]) == 0
    assert "prazo de" not in capsys.readouterr().out


def test_cli_mapas(tmp_path, cfg_toml):
    bruto = (FIX_IBGE / "malha_uf12_municipios_minima.json").read_bytes()
    srv = _Arquivos({"/api/v3/malhas/paises/BR?formato=application/json&intrarregiao=UF&qualidade=minima": bruto,
                     "/api/v3/malhas/estados/12?formato=application/json&intrarregiao=municipio&qualidade=minima":
                         bruto})
    import lumen_eleicoes.geo as g
    base = g.BASE_MALHAS
    g.BASE_MALHAS = srv.base + "/api/v3/malhas"
    try:
        assert cli.main(["--config", str(cfg_toml), "--saida", str(tmp_path / "f"), "mapas", "--ufs", "ac"]) == 0
    finally:
        g.BASE_MALHAS = base
        srv.parar()
    assert (tmp_path / "f" / "geo" / "uf-ac-mu.json").read_bytes() == bruto


def _json_final(texto: str):
    """O CLI imprime andamento e, no fim, o resumo em JSON: pega só o resumo."""
    inicio = max(texto.rfind("\n["), texto.rfind("\n{"))
    return json.loads(texto[inicio + 1:] if inicio >= 0 else texto)


def _zip(arquivos: dict[str, str]) -> bytes:
    import io
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for nome, texto in arquivos.items():
            zf.writestr(nome, texto.encode("latin-1"))
    return buf.getvalue()


def test_cli_historico_baixar_e_processar(tmp_path, cfg_toml, capsys):
    import lumen_eleicoes.dados_abertos as da_mod
    dados = RAIZ / "testes" / "fixtures" / "tse" / "dados_abertos"
    votacao = _zip({"votacao_candidato_munzona_2022_CE.csv":
                    (dados / "votacao_candidato_munzona_2022_CE_inicio.csv").read_text(encoding="latin-1")})
    detalhe = _zip({"detalhe_votacao_munzona_2022_BR.csv":
                    (dados / "detalhe_votacao_munzona_2022_BRASIL_inicio.csv").read_text(encoding="latin-1")})
    hist = _zip({"Historico_Totalizacao_Presidente_BR_1T_2022.csv":
                 (dados / "Historico_Totalizacao_Presidente_BR_1T_2022_inicio.csv").read_text(encoding="latin-1")})
    srv = _Arquivos({})
    pacote = {"success": True, "result": {"resources": [
        {"name": "v", "url": srv.base + "/odsele/votacao_candidato_munzona/votacao_candidato_munzona_2022.zip"},
        {"name": "d", "url": srv.base + "/odsele/detalhe_votacao_munzona/detalhe_votacao_munzona_2022.zip"},
        {"name": "h", "url": srv.base + "/eleicoes/eleicoes2022/Historico_Totalizacao_Presidente_BR_1T_2022.zip"}]}}
    srv.rotas.update({
        "/ckan?id=resultados-2022": json.dumps(pacote).encode(),
        "/odsele/votacao_candidato_munzona/votacao_candidato_munzona_2022.zip": votacao,
        "/odsele/detalhe_votacao_munzona/detalhe_votacao_munzona_2022.zip": detalhe,
        "/eleicoes/eleicoes2022/Historico_Totalizacao_Presidente_BR_1T_2022.zip": hist,
    })
    ckan = da_mod.CKAN
    da_mod.CKAN = srv.base + "/ckan"
    try:
        assert cli.main(["--config", str(cfg_toml), "historico", "baixar", "--anos", "2022"]) == 0
        baixados = _json_final(capsys.readouterr().out)
        assert len(baixados) == 3
        pasta = tmp_path / "dados" / "eleicoes" / "arquivos" / "2022"
        assert (pasta / "votacao_candidato_munzona_2022.zip.manifesto.json").exists()
        assert cli.main(["--config", str(cfg_toml), "--saida", str(tmp_path / "f"), "historico", "processar",
                         "--anos", "2022"]) == 0
        resumo = _json_final(capsys.readouterr().out)
        assert resumo[0]["eleicoes"] == ["2022-1t-geral"] and resumo[0]["linhas"] == 3
    finally:
        da_mod.CKAN = ckan
        srv.parar()
    feed = json.loads((tmp_path / "f" / "2022-1t-geral" / "deputado-federal" / "uf-ce.json").read_text())
    assert feed["origem"]["sha256"] and feed["origem"]["fonte"] == "dados_abertos"
    # O manifesto entrou no bronze
    registros = list((tmp_path / "dados" / "bronze").rglob("registros/*/*.json"))
    assert registros


def test_cli_historico_ckan_fora_do_ar_usa_enderecos_conhecidos(tmp_path, cfg_toml, capsys):
    import lumen_eleicoes.carga as c
    import lumen_eleicoes.dados_abertos as da_mod
    srv = _Arquivos({})
    ckan = da_mod.CKAN
    da_mod.CKAN = srv.base + "/ckan"
    try:
        from lumen_ingestao.cliente_http import ClienteHttp
        cliente = ClienteHttp("x", user_agent="Lumen/t (+c@exemplo.org)", rpm=6000, dormir=lambda s: None)
        urls = c.urls_do_ano(cliente, 2018)
    finally:
        da_mod.CKAN = ckan
        srv.parar()
    assert urls[da_mod.CONJUNTO_VOTACAO] == [da_mod.url_conjunto(da_mod.CONJUNTO_VOTACAO, 2018)]
    assert "usando os endereços conhecidos" in capsys.readouterr().err
