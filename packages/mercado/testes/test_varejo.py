"""Varejo pela API oficial: leitura das ofertas, filtro do que é o mesmo produto, coleta e referência por data.

A resposta usada aqui segue o formato documentado da busca do Mercado Livre (``results`` com ``id``,
``title``, ``price``, ``currency_id``, ``condition``, ``permalink``, ``seller``, ``shipping``); a conferência
contra a API real é o teste de contrato e o comando ``lumen mercado varejo testar``. O servidor é local:
confere que o token vai no cabeçalho do pedido, que 401/403 conta como recusa da loja e que a resposta
fica no bronze sem o token.
"""

import json
import threading
from datetime import date, datetime, timezone
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from lumen_mercado import cli, varejo
from lumen_mercado.especificacao import reconhecer

from lumen_ingestao.bronze import ArmazemBronzeLocal
from lumen_ingestao.cliente_http import ClienteHttp
from lumen_ingestao.portas import Janela, ResultadoCriterio, coletar_janela

AGORA = datetime(2026, 3, 11, 12, tzinfo=timezone.utc)


def _resposta(itens):
    return json.dumps({"site_id": "MLB", "paging": {"total": len(itens)}, "results": itens}).encode()


def _oferta(i, titulo, preco, **extra):
    base = {"id": f"MLB{i}", "title": titulo, "price": preco, "currency_id": "BRL", "condition": "new",
            "permalink": f"https://produto.mercadolivre.com.br/MLB-{i}", "seller": {"id": 99},
            "shipping": {"free_shipping": i % 2 == 0}, "official_store_id": 7 if i == 1 else None}
    base.update(extra)
    return base


def test_ler_ofertas():
    conteudo = _resposta([
        _oferta(1, "Notebook Lenovo Intel Core i5 8GB 256GB SSD", 3199.9),
        _oferta(2, "Notebook Dell i5 8gb 256gb ssd", "3299.00"),
        {"id": "MLB3", "title": "sem preço"},
        {"title": "sem id", "price": 10},
        "lixo",
    ])
    ofertas = varejo.ler_ofertas(conteudo, AGORA)
    assert [o.id for o in ofertas] == ["MLB1", "MLB2"]
    assert ofertas[0].preco == Decimal("3199.9") and ofertas[0].loja_oficial and not ofertas[0].frete_gratis
    assert ofertas[1].preco == Decimal("3299.00") and ofertas[1].vendedor == "99" and ofertas[1].frete_gratis
    assert varejo.ler_ofertas(b"nao json", AGORA) == [] and varejo.ler_ofertas(b"[]", AGORA) == []


def test_comparaveis_so_novos_em_reais_e_do_mesmo_produto():
    espec = reconhecer("Notebook i5 8GB RAM SSD 256GB", "Unidade")
    ofertas = varejo.ler_ofertas(_resposta([
        _oferta(1, "Notebook Lenovo Intel Core i5 8GB 256GB SSD", 3199.9),
        _oferta(2, "Notebook Lenovo Intel Core i5 8GB 256GB SSD", 2500, condition="used"),
        _oferta(3, "Notebook Lenovo Intel Core i5 8GB 256GB SSD", 600, currency_id="USD"),
        _oferta(4, "Notebook Lenovo Intel Core i7 8GB 256GB SSD", 4100),
        _oferta(5, "Capa para notebook i5 8gb 256gb", 80),
        _oferta(1, "Notebook Lenovo Intel Core i5 8GB 256GB SSD", 3100),            # mesmo id: conta uma vez
    ]), AGORA)
    assert [o.id for o in varejo.ofertas_comparaveis(espec, ofertas)] == ["MLB1"]


def test_url_e_consulta():
    url = varejo.url_busca("notebook i5 8gb ssd 256gb")
    assert url.startswith("https://api.mercadolibre.com/sites/MLB/search?") and "limit=50" in url
    assert varejo.consulta_da_url(url) == "notebook i5 8gb ssd 256gb"
    assert varejo.consulta_da_url("https://x/y") is None


class _Loja(BaseHTTPRequestHandler):
    pedidos: list = []

    def log_message(self, *a):
        pass

    def do_GET(self):
        _Loja.pedidos.append((self.path, self.headers.get("Authorization")))
        if "recusar" in self.path:
            self.send_response(403)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"message": "forbidden", "status": 403}')
            return
        corpo = _resposta([_oferta(i, f"Notebook Marca{i} Intel Core i5 8GB 256GB SSD", 3000 + 100 * i)
                           for i in range(10)])
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(corpo)


@pytest.fixture
def loja():
    _Loja.pedidos = []
    s = ThreadingHTTPServer(("127.0.0.1", 0), _Loja)
    threading.Thread(target=lambda: s.serve_forever(poll_interval=0.05), daemon=True).start()
    yield f"http://127.0.0.1:{s.server_address[1]}"
    s.shutdown()


def _cliente(sem_proxy):
    return ClienteHttp(varejo.FONTE_ID, user_agent="Lumen/teste (+teste@exemplo.org)", rpm=6000,
                       abridor=sem_proxy, dormir=lambda s: None)


def test_coleta_com_token_e_recusa(loja, sem_proxy, tmp_path):
    fonte = varejo.FonteMercadoLivre(_cliente(sem_proxy), ["notebook i5 8gb ssd 256gb", "recusar isto",
                                                           "notebook i5 8gb ssd 256gb", " "],
                                     base=loja, token="segredo")
    assert fonte.consultas == ("notebook i5 8gb ssd 256gb", "recusar isto")
    assert fonte.descrever_capacidades().exige_autenticacao
    armazem = ArmazemBronzeLocal(tmp_path / "bronze")
    resumo = coletar_janela(fonte, Janela(date(2026, 3, 11), date(2026, 3, 11)), armazem)
    assert len(resumo.guardados) == 2 and fonte.recusadas == 1 and fonte.respondidas == 1
    assert {a for _, a in _Loja.pedidos} == {"Bearer segredo"}
    for r in armazem.listar_registros(varejo.FONTE_ID):
        assert "segredo" not in json.dumps(r.cabecalhos)
    relatorio = fonte.reportar_conformidade()
    assert relatorio.avaliacoes[0].resultado == ResultadoCriterio.INDETERMINADO
    assert "credencial" in relatorio.avaliacoes[0].motivo_indeterminado

    indice = varejo.OfertasVarejo.do_bronze(armazem)
    assert indice.consultas() == ["notebook i5 8gb ssd 256gb"]
    espec = reconhecer("Notebook i5 8GB RAM SSD 256GB", "Unidade")
    hoje = date.today()
    ref = indice.referencia(espec, hoje)
    assert ref.quantidade == 10 and ref.mediana == Decimal("3450.000") and ref.escopo == "brasil"
    assert indice.referencia(espec, hoje, minimo_ofertas=11) is None
    assert indice.referencia(espec, date(2020, 1, 1)) is None


def test_sem_token_e_conformidade(loja, sem_proxy, monkeypatch):
    monkeypatch.delenv(varejo.VARIAVEL_TOKEN, raising=False)
    fonte = varejo.FonteMercadoLivre(_cliente(sem_proxy), ["monitor 24 polegadas full hd"], base=loja)
    assert fonte.token is None and not fonte.descrever_capacidades().exige_autenticacao
    assert fonte.reportar_conformidade().avaliacoes[0].motivo_indeterminado == "nenhuma consulta feita nesta sessão"
    ref = next(fonte.listar(Janela(date(2026, 3, 11), date(2026, 3, 11))))
    assert fonte.baixar(ref).status_http == 200 and _Loja.pedidos[-1][1] is None
    assert fonte.reportar_conformidade().avaliacoes[0].resultado == ResultadoCriterio.CUMPRE
    with pytest.raises(ValueError):
        varejo.FonteMercadoLivre(ClienteHttp("outra_fonte", user_agent="x", rpm=1), [])


def test_cli_testar_e_coletar(loja, sem_proxy, cfg, monkeypatch, capsys):
    monkeypatch.setattr(cli, "_cliente", lambda c, f: _cliente(sem_proxy))
    monkeypatch.setattr(varejo, "BASE_ML", loja)
    assert cli.main(["varejo", "testar", "--consulta", "notebook i5 8gb ssd 256gb"]) == 0
    saida = json.loads(capsys.readouterr().out)
    assert saida["status"] == 200 and saida["comparaveis"] == 10 and "permalink" in saida["campos_do_primeiro_resultado"]
    assert cli.main(["varejo", "testar", "--consulta", "recusar isto"]) == 1
    capsys.readouterr()
    assert cli.main(["varejo", "coletar", "--sem-padrao", "--consultas", "notebook i5 8gb ssd 256gb"]) == 0
    assert json.loads(capsys.readouterr().out)["guardados"] == 1
    assert cli.main(["varejo", "coletar", "--sem-padrao", "--consultas", "recusar isto"]) == 1
