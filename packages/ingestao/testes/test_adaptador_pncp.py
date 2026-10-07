"""Adaptador PNCP contra um servidor local que imita a API real.

As respostas servidas são as fixtures capturadas da API em 05/10/2026, com o
comportamento real: modalidade obrigatória (400 sem ela), 204 em página vazia
e paginação anunciada em ``totalPaginas``.
"""

import json
import threading
import urllib.parse
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from lumen_ingestao.adaptadores.api.pncp import (
    ChaveCompra,
    FontePncpAtas,
    FontePncpContratacoes,
    FontePncpContratos,
    FontePncpItens,
)
from lumen_ingestao.bronze import ArmazemBronzeLocal
from lumen_ingestao.cliente_http import ClienteHttp
from lumen_ingestao.coleta_http import user_agent_lumen
from lumen_ingestao.portas import FonteDados, Janela, ResultadoCriterio, coletar_janela

FIX = Path(__file__).resolve().parents[3] / "testes" / "fixtures" / "pncp"
UA = user_agent_lumen("0.2.0", "contato@exemplo.org")


def _json(nome):
    return json.loads((FIX / nome).read_text(encoding="utf-8"))


class _PncpFalso(BaseHTTPRequestHandler):
    pedidos: list = []

    def log_message(self, *a):
        pass

    def _responder(self, status, corpo=None):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        if corpo is not None:
            self.wfile.write(json.dumps(corpo, ensure_ascii=False).encode())

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = dict(urllib.parse.parse_qsl(u.query))
        _PncpFalso.pedidos.append((u.path, q))
        if u.path.startswith("/consulta/v1/contratacoes/"):
            if "codigoModalidadeContratacao" not in q:
                return self._responder(400, _json("erro_400_parametro_ausente.json"))
            if q["codigoModalidadeContratacao"] != "8" or q["dataInicial"] != "20260901":
                return self._responder(204)
            pagina = int(q["pagina"])
            corpo = _json("contratacoes_publicacao_dispensa_20260901_p1.json" if pagina == 1
                          else "contratacoes_publicacao_pregao_20260901_p1.json")
            corpo.update(totalPaginas=2, numeroPagina=pagina)
            return self._responder(200, corpo)
        if u.path == "/consulta/v1/contratos":
            corpo = _json("contratos_20260901_p1.json")
            corpo.update(totalPaginas=1)
            return self._responder(200, corpo)
        if u.path == "/consulta/v1/atas":
            corpo = _json("atas_20260901_p1.json")
            corpo.update(totalPaginas=1)
            return self._responder(200, corpo)
        base = "/pncp/v1/orgaos/97229181000164/compras/2026/406/itens"
        if u.path == base:
            return self._responder(200, _json("compra_97229181000164_2026_406_itens.json"))
        if u.path.startswith(base + "/") and u.path.endswith("/resultados"):
            return self._responder(200, _json("compra_97229181000164_2026_406_item1_resultados.json"))
        return self._responder(404, {"error": "Not Found"})


@pytest.fixture
def pncp():
    _PncpFalso.pedidos = []
    s = ThreadingHTTPServer(("127.0.0.1", 0), _PncpFalso)
    threading.Thread(target=lambda: s.serve_forever(poll_interval=0.05), daemon=True).start()
    yield f"http://127.0.0.1:{s.server_address[1]}"
    s.shutdown()


def _cliente(fonte_id, sem_proxy):
    return ClienteHttp(fonte_id, user_agent=UA, rpm=6000, abridor=sem_proxy, dormir=lambda s: None)


def test_implementa_a_porta(sem_proxy, pncp):
    fonte = FontePncpContratacoes(_cliente("pncp_contratacoes", sem_proxy), base=f"{pncp}/consulta")
    assert isinstance(fonte, FonteDados)
    cap = fonte.descrever_capacidades()
    assert cap.objetos == {"ProcessoContratacao"} and cap.suporta_incremental


def test_coleta_janela_com_paginacao_sem_baixar_a_primeira_pagina_duas_vezes(sem_proxy, pncp, tmp_path):
    fonte = FontePncpContratacoes(_cliente("pncp_contratacoes", sem_proxy), base=f"{pncp}/consulta",
                                  modalidades=(6, 8), tamanho_pagina=10)
    armazem = ArmazemBronzeLocal(tmp_path / "bronze")
    resumo = coletar_janela(fonte, Janela(date(2026, 9, 1), date(2026, 9, 2)), armazem)
    # dia 1: modalidade 6 (204) + modalidade 8 (2 páginas); dia 2: 204 + 204
    assert resumo.listados == 5
    assert len(resumo.guardados) == 5 and resumo.falhas == []
    paginas_mod8 = [q for p, q in _PncpFalso.pedidos
                    if q.get("codigoModalidadeContratacao") == "8" and q["dataInicial"] == "20260901"]
    assert sorted(q["pagina"] for q in paginas_mod8) == ["1", "2"]  # cada página uma vez
    assert {r.status_http for r in resumo.guardados} == {200, 204}
    rel = fonte.reportar_conformidade()
    assert rel.avaliacoes[0].resultado is ResultadoCriterio.CUMPRE


def test_parametros_da_url_seguem_a_api_real(sem_proxy, pncp):
    fonte = FontePncpContratacoes(_cliente("pncp_contratacoes", sem_proxy), base=f"{pncp}/consulta",
                                  modalidades=(8,), tamanho_pagina=50)
    refs = list(fonte.listar(Janela(date(2026, 9, 1), date(2026, 9, 1))))
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(refs[0].url).query))
    assert q == {"dataInicial": "20260901", "dataFinal": "20260901", "codigoModalidadeContratacao": "8",
                 "pagina": "1", "tamanhoPagina": "50"}
    assert refs[1].metadados["pagina"] == "2"


def test_modo_atualizacao_usa_outro_endpoint_e_outra_fonte(sem_proxy):
    f = FontePncpContratacoes(_cliente("pncp_contratacoes_atualizacao", sem_proxy), modo="atualizacao")
    assert f.caminho == "/v1/contratacoes/atualizacao" and f.fonte_id == "pncp_contratacoes_atualizacao"


@pytest.mark.parametrize("kw,erro", [
    ({"tamanho_pagina": 51}, "entre 10 e 50"),
    ({"tamanho_pagina": 5}, "entre 10 e 50"),
    ({"modo": "outro"}, "modo"),
    ({"modalidades": ()}, "modalidade"),
])
def test_configuracao_invalida(sem_proxy, kw, erro):
    with pytest.raises(ValueError, match=erro):
        FontePncpContratacoes(_cliente("pncp_contratacoes", sem_proxy), **kw)


def test_cliente_de_outra_fonte_e_recusado(sem_proxy):
    with pytest.raises(ValueError, match="cliente da fonte"):
        FontePncpContratacoes(_cliente("pncp_contratos", sem_proxy))


def test_contratos_e_atas(sem_proxy, pncp, tmp_path):
    armazem = ArmazemBronzeLocal(tmp_path / "bronze")
    contratos = FontePncpContratos(_cliente("pncp_contratos", sem_proxy), base=f"{pncp}/consulta")
    atas = FontePncpAtas(_cliente("pncp_atas", sem_proxy), base=f"{pncp}/consulta")
    j = Janela(date(2026, 9, 1), date(2026, 9, 1))
    assert len(coletar_janela(contratos, j, armazem).guardados) == 1
    assert len(coletar_janela(atas, j, armazem).guardados) == 1
    assert contratos.tamanho_pagina == 500
    with pytest.raises(ValueError):
        FontePncpContratos(_cliente("pncp_contratos", sem_proxy), modo="x")
    with pytest.raises(ValueError):
        FontePncpAtas(_cliente("pncp_atas", sem_proxy), modo="x")
    assert FontePncpAtas(_cliente("pncp_atas_atualizacao", sem_proxy), modo="atualizacao").caminho == "/v1/atas/atualizacao"


def test_itens_e_resultados_da_compra(sem_proxy, pncp, tmp_path):
    chave = ChaveCompra.de_numero_controle("97229181000164-1-000406/2026")
    fonte = FontePncpItens(_cliente("pncp_itens", sem_proxy), [chave], base=f"{pncp}/pncp")
    resumo = coletar_janela(fonte, Janela(date(2026, 9, 1), date(2026, 9, 1)), ArmazemBronzeLocal(tmp_path / "b"))
    # 1 lista de itens + 3 resultados (todos os itens têm temResultado = true)
    assert resumo.listados == 4 and resumo.falhas == []
    assert fonte.descrever_capacidades().objetos == {"ItemContratacao", "ResultadoItem"}
    assert fonte.reportar_conformidade().avaliacoes[0].resultado is ResultadoCriterio.INDETERMINADO


def test_chave_de_compra():
    c = ChaveCompra.de_numero_controle("97229181000164-1-000406/2026")
    assert (c.cnpj, c.ano, c.sequencial) == ("97229181000164", 2026, 406)
    assert c.numero_controle == "97229181000164-1-000406/2026"
    for ruim in ("", "97229181000164-2-000239/2026", "abc"):
        with pytest.raises(ValueError):
            ChaveCompra.de_numero_controle(ruim)


def test_sessao_sem_consulta_e_indeterminada(sem_proxy):
    f = FontePncpContratos(_cliente("pncp_contratos", sem_proxy))
    assert f.reportar_conformidade().avaliacoes[0].resultado is ResultadoCriterio.INDETERMINADO


def test_falha_5xx_torna_a_sessao_indeterminada(sem_proxy):
    f = FontePncpContratos(_cliente("pncp_contratos", sem_proxy))
    f._status[503] += 1
    a = f.reportar_conformidade().avaliacoes[0]
    assert a.resultado is ResultadoCriterio.INDETERMINADO and "5xx" in a.motivo_indeterminado
