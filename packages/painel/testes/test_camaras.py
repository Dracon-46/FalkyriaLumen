"""O cadastro das câmaras municipais com o SAPL (ADR-062)."""

import io
import json

from lumen_painel import camaras
from lumen_painel.cadastro import Cadastro, Ente


class _Resposta(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_endereco_padrao_do_interlegis():
    assert camaras.endereco("São José dos Campos", "SP") == "sapl.saojosedoscampos.sp.leg.br"
    assert camaras.endereco("Pau d'Arco do Piauí", "PI") == "sapl.paudarcodopiaui.pi.leg.br"


def test_testar_le_o_total_e_falha_sem_api():
    resposta = json.dumps({"pagination": {"total_entries": 327}}).encode()
    assert camaras.testar("x", contato="c", abrir=lambda p: _Resposta(resposta)) == 327

    def recusar(p):
        raise OSError("sem endereço")

    assert camaras.testar("x", contato="c", abrir=recusar) is None
    assert camaras.testar("x", contato="c", abrir=lambda p: _Resposta(b"<html>")) is None


def test_levantamento_grava_so_as_que_responderam(tmp_path):
    cadastro = Cadastro({"3509502": Ente("3509502", "Campinas", "SP", "M", 1_100_000),
                         "4209102": Ente("4209102", "Joinville", "SC", "M", 600_000),
                         "35": Ente("35", "São Paulo", "SP", "E", 46_000_000)})
    r = camaras.levantar(tmp_path, cadastro, contato="c",
                         testar_fn=lambda host, contato: 327 if "campinas" in host else None)
    assert r == {"municipios": 2, "com_sapl": 1}
    assert camaras.ler(tmp_path) == {"3509502": ["sapl.campinas.sp.leg.br", 327]}
