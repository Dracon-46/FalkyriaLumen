"""Carga dos dados abertos (``carga``), referências embutidas e o comando único ``preparar``."""

from __future__ import annotations

import json
import threading
import urllib.request
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

from lumen_eleicoes import antigas, carga, cli, geo, preparacao, referencias
from lumen_eleicoes.coletor import FONTE_ID, ColetorAoVivo
from lumen_eleicoes.configuracao import carregar
from lumen_eleicoes.feeds import EscritorFeeds
from lumen_eleicoes.modelo import Eleicao
from lumen_eleicoes.municipios import CadastroMunicipios
from lumen_eleicoes.simulacao import Cenario, ServidorSimulado
from lumen_eleicoes.transferencia import ErroTransferencia
from lumen_ingestao.cliente_http import ClienteHttp

RAIZ = Path(__file__).resolve().parents[3]
FIX_TSE = RAIZ / "testes" / "fixtures" / "tse"
FIX = FIX_TSE / "dados_abertos_uf"
SEM_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))
UA = "Lumen/teste (+c@exemplo.org)"


class Arquivos:
    """Servidor HTTP local que responde caminhos fixos; o resto é 404."""

    def __init__(self, rotas: dict[str, bytes] | None = None):
        self.rotas = dict(rotas or {})
        self.pedidos: list[str] = []
        rotas_ref, pedidos = self.rotas, self.pedidos

        class T(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                pedidos.append(self.path)
                corpo = rotas_ref.get(self.path)
                self.send_response(200 if corpo is not None else 404)
                self.send_header("Content-Length", str(len(corpo or b"")))
                self.end_headers()
                self.wfile.write(corpo or b"")

        self.http = ThreadingHTTPServer(("127.0.0.1", 0), T)
        self.base = f"http://127.0.0.1:{self.http.server_address[1]}"
        threading.Thread(target=self.http.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.http.shutdown()
        self.http.server_close()


def cliente(fonte: str = carga.FONTE_DADOS_ABERTOS) -> ClienteHttp:
    """Cliente sem proxy e sem espera do limitador de taxa."""
    return ClienteHttp(fonte, user_agent=UA, rpm=60000, abridor=SEM_PROXY, dormir=lambda s: None)


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("LUMEN_CONTATO", "c@exemplo.org")
    monkeypatch.delenv("LUMEN_ELEICOES_SAIDA", raising=False)
    toml = tmp_path / "lumen.toml"
    toml.write_text(f'[dados]\nraiz = "{(tmp_path / "dados").as_posix()}"\n[eleicoes]\n'
                    f'saida = "{(tmp_path / "feeds").as_posix()}"\nrpm_resultados = 60000\n'
                    'rpm_dados_abertos = 60000\n', encoding="utf-8")
    c = carregar(toml)
    c.toml = toml
    return c


@pytest.fixture
def cdn_antiga(tmp_path, monkeypatch, zips_antigos):
    """CDN local com os ZIPs de 1950 e 1989 montados das fixtures (o de partido de 1989 não existe, como na fonte)."""
    rotas = {}
    for ano in (1950, 1989):
        for conjunto, caminho in zip(antigas.CONJUNTOS_UF, zips_antigos(tmp_path / "cdn", ano)):
            if caminho is not None:
                rotas[f"/{conjunto}/{caminho.name}"] = caminho.read_bytes()
    with Arquivos(rotas) as srv:
        monkeypatch.setattr(antigas, "CDN", srv.base)
        yield srv


# ------------------------------------------------------------------ carga

def da_ano_em_aberto() -> int:
    from lumen_eleicoes import dados_abertos
    return dados_abertos.ANO_EM_ABERTO


def test_anos_disponiveis_vao_de_2026_a_1933():
    anos = carga.anos_disponiveis()
    assert anos[0] == 2026 and anos[-1] == 1933 and 2024 in anos and da_ano_em_aberto() == 2026 and 1950 in anos and 1994 in anos and 1993 not in anos
    assert cli._anos("todos") == anos and cli._anos("1950, 1989") == [1989, 1950]
    with pytest.raises(Exception):
        cli._anos("1951")


def test_baixar_e_processar_ano_antigo(cfg, cdn_antiga, capsys):
    avisos = []
    manifestos = carga.baixar_ano(cfg, cliente(), 1989, bronze=None, aviso=avisos.append)
    assert [m.arquivo for m in manifestos] == ["votacao_candidato_uf_1989.zip", "detalhe_votacao_uf_1989.zip"]
    assert len(avisos) == 1 and "votacao_partido_uf_1989.zip" in avisos[0] and "404" in avisos[0]
    r = carga.processar_ano(cfg, 1989, escritor=EscritorFeeds(cfg.saida), cadastro=CadastroMunicipios(),
                            progresso=lambda m: None)
    assert r.eleicoes == ["1989-1t-geral", "1989-2t-geral"] and r.arquivos == 8 and r.linhas == 72
    feed = json.loads((cfg.saida / "1989-1t-geral" / "presidente" / "br.json").read_text(encoding="utf-8"))
    assert feed["origem"]["sha256"] == manifestos[0].sha256
    assert feed["origem"]["url"].endswith("/votacao_candidato_uf/votacao_candidato_uf_1989.zip")


def test_conjunto_opcional_corrompido_nao_derruba_o_ano(cfg, zips_antigos):
    pasta = cfg.arquivos / "1986"
    zips_antigos(pasta, 1986)
    (pasta / "votacao_partido_uf_1986.zip").write_bytes(b"<html>erro</html>")
    avisos = []
    r = carga.processar_ano(cfg, 1986, escritor=EscritorFeeds(cfg.saida), cadastro=CadastroMunicipios(),
                            progresso=avisos.append)
    assert r.eleicoes == ["1986-1t-geral"] and any("não é um ZIP válido" in a for a in avisos)


def test_sem_a_votacao_por_candidato_o_ano_falha(cfg, monkeypatch):
    with Arquivos() as srv:
        monkeypatch.setattr(antigas, "CDN", srv.base)
        with pytest.raises(ErroTransferencia) as erro:
            carga.baixar_ano(cfg, cliente(), 1950, bronze=None, aviso=lambda m: None)
    assert erro.value.status == 404
    with pytest.raises(carga.ArquivoAusente):
        carga.processar_ano(cfg, 1950, escritor=EscritorFeeds(cfg.saida), cadastro=CadastroMunicipios())
    with pytest.raises(carga.ArquivoAusente):
        carga.processar_ano(cfg, 2022, escritor=EscritorFeeds(cfg.saida), cadastro=CadastroMunicipios())


def test_alvos_de_ano_recente_vem_do_ckan(monkeypatch):
    import lumen_eleicoes.dados_abertos as da
    with Arquivos() as srv:
        monkeypatch.setattr(da, "CKAN", srv.base + "/ckan")
        avisos = []
        alvos = carga.alvos_do_ano(cliente(), 2018, avisos.append)
    assert [(c, ob) for c, _, ob in alvos] == [(da.CONJUNTO_VOTACAO, True), (da.CONJUNTO_DETALHE, False)]
    assert "usando os endereços conhecidos" in avisos[0]


def test_cli_historico_de_ano_antigo(cfg, cdn_antiga, capsys):
    assert cli.main(["--config", str(cfg.toml), "historico", "baixar", "--anos", "1950", "--sem-bronze"]) == 0
    saida = capsys.readouterr().out
    baixados = json.loads(saida[saida.index("\n[") + 1:])
    assert {Path(b["arquivo"]).name for b in baixados} == {
        "votacao_candidato_uf_1950.zip", "detalhe_votacao_uf_1950.zip"}
    assert cli.main(["--config", str(cfg.toml), "historico", "processar", "--anos", "1950"]) == 0
    saida = capsys.readouterr().out
    resumo = json.loads(saida[saida.rfind("\n[") + 1:])
    assert resumo[0]["eleicoes"] == ["1950-1t-geral"] and resumo[0]["municipios_sem_ibge"] == 0
    assert cli.main(["--config", str(cfg.toml), "historico", "processar", "--anos", "1954"]) == 2


# ------------------------------------------------------------------ referências embutidas

def test_referencias_embutidas_cobrem_o_brasil(tmp_path):
    itens = referencias.arquivos_embutidos()
    destinos = [d for _, d in itens]
    malhas = [d for d in destinos if d.startswith("geo/") and not d.startswith("geo/mu/")]
    contornos = [d for d in destinos if d.startswith("geo/mu/")]
    assert destinos[0] == "municipios.json" and "geo/br-uf.json" in destinos and len(malhas) == 1 + 27
    assert len(destinos) == 1 + len(malhas) + len(contornos) and len(contornos) >= 190
    cad = referencias.cadastro_embutido()
    assert len(cad) > 5700 and cad.por_ibge("3550308").nome == "São Paulo"
    assert sum(1 for m in cad if not m.ibge) > 100                         # exterior
    municipios_nas_malhas = 0
    for origem, destino in itens[1:]:
        topo = geo.validar_topojson(origem.read_bytes())
        if destino.startswith("geo/mu/"):
            # Contorno fino: só o município do nome do arquivo, que também está na malha da UF
            assert geo.codigos_da_malha(topo) == [Path(destino).stem] and cad.por_ibge(Path(destino).stem)
        elif destino != "geo/br-uf.json":
            municipios_nas_malhas += len(geo.codigos_da_malha(topo))
    assert municipios_nas_malhas == 5570
    copiados = referencias.instalar(tmp_path)
    assert len(copiados) == len(itens) and (tmp_path / "geo" / "uf-sp-mu.json").exists()
    # Não sobrescreve o que já está lá (pode ser versão mais nova baixada da fonte), exceto se pedido
    (tmp_path / "municipios.json").write_text('{"versao":1,"municipios":[]}', encoding="utf-8")
    assert referencias.instalar(tmp_path) == []
    assert len(CadastroMunicipios.carregar(tmp_path / "municipios.json")) == 0
    assert len(referencias.instalar(tmp_path, substituir=True)) == len(itens)


def test_cadastro_do_cli_usa_o_embutido_sem_arquivo(cfg):
    assert len(cli._cadastro(cfg)) > 5700


def test_amostra_instala_o_mapa(tmp_path, monkeypatch):
    monkeypatch.delenv("LUMEN_CONTATO", raising=False)
    assert cli.main(["--config", str(tmp_path / "x.toml"), "--saida", str(tmp_path / "f"), "amostra"]) == 0
    assert (tmp_path / "f" / "geo" / "br-uf.json").exists() and (tmp_path / "f" / "municipios.json").exists()


# ------------------------------------------------------------------ preparar: partes

def test_registro_do_que_foi_feito(tmp_path):
    caminho = tmp_path / "e" / "preparar.json"
    estado = preparacao.EstadoPreparacao.carregar(caminho)
    assert not estado.ano_pronto(1950) and estado.entradas_do_ano(1950) == {}
    estado.marcar_ano(1950, {"a.zip": "ff"}, ["1950-1t-geral"])
    estado.marcar_ao_vivo("2026-1t-geral")
    de_volta = preparacao.EstadoPreparacao.carregar(caminho)
    assert de_volta.ano_pronto(1950) and de_volta.entradas_do_ano(1950) == {"a.zip": "ff"}
    assert de_volta.ao_vivo_pronto("2026-1t-geral")
    caminho.write_text("{quebrado", encoding="utf-8")
    assert preparacao.EstadoPreparacao.carregar(caminho).anos == {}


def test_portal_desatualizado(tmp_path):
    import os
    portal = tmp_path / "portal"
    (portal / "src").mkdir(parents=True)
    (portal / "src" / "a.tsx").write_text("x")
    assert preparacao.portal_desatualizado(portal)
    (portal / "out").mkdir()
    indice = portal / "out" / "index.html"
    indice.write_text("<html>")
    os.utime(portal / "src" / "a.tsx", (1_000_000, 1_000_000))
    assert not preparacao.portal_desatualizado(portal)
    os.utime(portal / "src" / "a.tsx", (indice.stat().st_mtime + 10,) * 2)
    assert preparacao.portal_desatualizado(portal)


def test_construir_portal(tmp_path):
    chamadas = []

    def executar(passo, cwd):
        chamadas.append(passo[1:])
        return SimpleNamespace(returncode=0)
    with pytest.raises(preparacao.PortalIndisponivel, match="Node.js"):
        preparacao.construir_portal(tmp_path, executar=executar, localizar=lambda n: None)
    preparacao.construir_portal(tmp_path, executar=executar, localizar=lambda n: "/bin/npm")
    assert chamadas == [["ci"], ["run", "build"]]
    (tmp_path / "node_modules").mkdir()
    chamadas.clear()
    preparacao.construir_portal(tmp_path, executar=executar, localizar=lambda n: "/bin/npm")
    assert chamadas == [["run", "build"]]
    with pytest.raises(preparacao.PortalIndisponivel, match="run build"):
        preparacao.construir_portal(tmp_path, executar=lambda p, cwd: SimpleNamespace(returncode=1),
                                    localizar=lambda n: "/bin/npm")


def test_quais_eleicoes_vem_do_sistema_de_resultados():
    def e(id_, ano, tipo, data):
        return Eleicao(id=id_, ano=ano, turno=1, tipo=tipo, nome=id_, data=data, ciclo=f"ele{ano}", pleito=None,
                       origem="resultados")
    lista = [e("2026-1t-geral", 2026, "geral", date(2026, 10, 4)), e("2026-2t-geral", 2026, "geral", date(2026, 10, 25)),
             e("2024-1t-municipal", 2024, "municipal", date(2024, 10, 6)),
             e("2026-sup", 2026, "suplementar", date(2026, 3, 1)), e("2026-x", 2026, "geral", None)]
    agora, futuras = preparacao.eleicoes_ao_vivo(lista, date(2026, 10, 6))
    assert [x.id for x in agora] == ["2026-1t-geral", "2026-x"] and [x.id for x in futuras] == ["2026-2t-geral"]
    # Com o 1º turno de 2026 já processado dos dados abertos, ele sai da coleta; o 2º turno continua
    agora, futuras = preparacao.eleicoes_ao_vivo(lista, date(2026, 10, 26), {"2026-1t-geral"})
    assert [x.id for x in agora] == ["2026-2t-geral", "2026-x"] and futuras == []


def test_dentro_de(tmp_path):
    assert preparacao.dentro_de(tmp_path / "a" / "b", tmp_path / "a")
    assert preparacao.dentro_de(tmp_path, tmp_path)
    assert not preparacao.dentro_de(tmp_path / "b", tmp_path / "a")


# ------------------------------------------------------------------ preparar: de ponta a ponta

def _preparacao(cfg, dir_portal: Path, base: str, **opcoes) -> tuple[preparacao.Preparacao, list[str], list[str]]:
    linhas: list[str] = []
    abertos: list[str] = []
    construcoes: list[int] = []

    def construir():
        construcoes.append(1)
        (dir_portal / "out").mkdir(parents=True, exist_ok=True)
        (dir_portal / "out" / "index.html").write_text("<html>portal</html>", encoding="utf-8")
    op = preparacao.OpcoesPreparacao(base=base, bronze=False, porta=0, **opcoes)
    prep = preparacao.Preparacao(cfg, op, cliente_resultados=cliente(FONTE_ID), cliente_dados=cliente(),
                                 saida=linhas.append, construir=construir, abrir=abertos.append,
                                 hoje=date(2026, 10, 6), portal=dir_portal, dormir=lambda s: None)
    prep.construcoes = construcoes
    return prep, linhas, abertos


def test_preparar_tudo_e_retomar(cfg, cdn_antiga, tmp_path, monkeypatch):
    portal = tmp_path / "portal"
    (portal / "src").mkdir(parents=True)
    with ServidorSimulado(Cenario(FIX_TSE, etapas=1)) as tse_local:
        prep, linhas, abertos = _preparacao(cfg, portal, tse_local.base, anos=[1989, 1950], servir=True)
        resumo = prep.executar()
        try:
            # Servidor no ar: o portal e os feeds pela mesma porta
            with urllib.request.urlopen(resumo.endereco.replace("/eleicoes/", "/dados/eleicoes/indice.json"),
                                        timeout=5) as r:
                indice = json.loads(r.read())
        finally:
            prep.servidor.parar()
    assert resumo.erros == [] and resumo.portal == "gerado" and resumo.referencias == len(referencias.arquivos_embutidos())
    assert abertos == [resumo.endereco]
    ids = {e["id"] for e in indice["eleicoes"]}
    assert {"2026-1t-geral", "1989-1t-geral", "1989-2t-geral", "1950-1t-geral"} <= ids
    # O recorte das fixtures é de antes do fim da totalização: fotografia tirada, sem marcar como concluída
    assert resumo.ao_vivo == [{"eleicao": "2026-1t-geral", "situacao": "em andamento", "passadas": 2}]
    assert any("ao-vivo --eleicao 2026-1t-geral" in linha for linha in linhas)
    assert [a["ano"] for a in resumo.anos] == [1950, 1989]        # antigos em ordem cronológica
    assert (cfg.saida / "2026-1t-geral" / "presidente" / "uf-sp.json").exists()
    assert (cfg.saida / "geo" / "br-uf.json").exists()
    estado = json.loads((cfg.estado / "preparar.json").read_text(encoding="utf-8"))
    assert set(estado["anos"]) == {"1950", "1989"} and estado["ao_vivo"] == {}
    assert any("1989-1t-geral" in e for e in estado["anos"]["1989"]["eleicoes"])

    # Segunda vez, agora com a totalização concluída: anos já prontos, portal já gerado
    monkeypatch.setattr(ColetorAoVivo, "_finalizada", lambda self: True)
    with ServidorSimulado(Cenario(FIX_TSE, etapas=1)) as tse_local:
        prep2, linhas2, _ = _preparacao(cfg, portal, tse_local.base, anos=[1989, 1950])
        resumo2 = prep2.executar()
    assert prep2.construcoes == [] and resumo2.portal == "atualizado"
    assert [a["situacao"] for a in resumo2.anos] == ["já processado", "já processado"]
    assert resumo2.ao_vivo == [{"eleicao": "2026-1t-geral", "situacao": "concluída", "passadas": 1}]
    with ServidorSimulado(Cenario(FIX_TSE, etapas=1)) as tse_local:
        prep2b, _, _ = _preparacao(cfg, portal, tse_local.base, historico=False)
        assert prep2b.executar().ao_vivo == [{"eleicao": "2026-1t-geral", "situacao": "já coletada"}]

    # Com --atualizar: consulta a fonte e não reprocessa o que não mudou
    with ServidorSimulado(Cenario(FIX_TSE, etapas=1)) as tse_local:
        prep3, _, _ = _preparacao(cfg, portal, tse_local.base, anos=[1950], ao_vivo=False, atualizar=True)
        resumo3 = prep3.executar()
    assert resumo3.anos == [{"ano": 1950, "situacao": "sem mudança na fonte"}]


def test_preparar_segue_depois_de_um_erro(cfg, cdn_antiga, tmp_path):
    portal = tmp_path / "portal"
    prep, linhas, _ = _preparacao(cfg, portal, "http://127.0.0.1:9", anos=[1954, 1950], portal=False)
    resumo = prep.executar()
    # Catálogo inacessível e 1954 fora da CDN local: os dois viram erro; 1950 é processado mesmo assim
    assert any("catálogo" in e for e in resumo.erros) and any(e.startswith("1954") for e in resumo.erros)
    assert {a["ano"]: a["situacao"] for a in resumo.anos} == {1950: "processado", 1954: "erro"}
    assert resumo.portal == "não gerado"


def test_preparar_avisa_feeds_dentro_do_portal_e_falha_do_node(cfg, tmp_path):
    portal = tmp_path / "portal"
    cfg.saida = portal / "public" / "dados" / "eleicoes"
    linhas: list[str] = []

    def construir():
        raise preparacao.PortalIndisponivel("Node.js não encontrado")
    prep = preparacao.Preparacao(cfg, preparacao.OpcoesPreparacao(ao_vivo=False, historico=False, servir=True,
                                                                  bronze=False),
                                 cliente_resultados=cliente(FONTE_ID), cliente_dados=cliente(), saida=linhas.append,
                                 construir=construir, portal=portal, dormir=lambda s: None)
    resumo = prep.executar()
    assert resumo.portal == "falhou" and resumo.erros == ["portal: Node.js não encontrado"]
    assert any("dentro do portal" in linha for linha in linhas)
    assert any("sem o portal gerado" in linha for linha in linhas) and prep.servidor is None
    prep.aguardar()                                                # sem servidor: volta na hora


def test_preparar_parado_pelo_usuario(cfg, tmp_path):
    # Base numa porta local fechada: o catálogo falha na hora, sem depender da rede (na CI o
    # endereço real do TSE responde e a coleta ao vivo começaria antes da parada).
    chamadas = iter([False, False, True])
    prep = preparacao.Preparacao(cfg, preparacao.OpcoesPreparacao(portal=False, bronze=False,
                                                                  base="http://127.0.0.1:9"),
                                 cliente_resultados=cliente(FONTE_ID), cliente_dados=cliente(),
                                 saida=lambda m: None, parar=lambda: next(chamadas, True), dormir=lambda s: None)
    resumo = prep.executar()
    assert resumo.anos == [] and resumo.ao_vivo == []
    assert [e for e in resumo.erros if e.startswith("catálogo do sistema de resultados")]


def test_cli_preparar(cfg, monkeypatch, capsys):
    capturado = {}

    class Falsa:
        def __init__(self, c, opcoes, **kw):
            capturado["opcoes"] = opcoes

        def executar(self):
            return preparacao.ResumoPreparacao(erros=capturado.get("erros", []))

        def aguardar(self):
            capturado["aguardou"] = True
    monkeypatch.setattr(cli, "Preparacao", Falsa)
    assert cli.main(["--config", str(cfg.toml), "preparar", "--servir", "--anos", "1950", "--sem-ao-vivo"]) == 0
    op = capturado["opcoes"]
    assert (op.servir, op.anos, op.ao_vivo, op.historico, op.portal) == (True, [1950], False, True, True)
    assert capturado["aguardou"] and json.loads(capsys.readouterr().out.strip())["erros"] == []
    capturado["erros"] = ["x"]
    assert cli.main(["--config", str(cfg.toml), "preparar"]) == 1


def test_fixtures_antigas_documentadas():
    leiame = (FIX_TSE / "README.md").read_text(encoding="utf-8")
    for arq in sorted(FIX.glob("*.txt")):
        assert arq.name in leiame, arq.name
