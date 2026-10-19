"""O reconhecimento dos itens comparados com a ANP é o mesmo no Python e no portal (ADR-037).

O portal reconhece no navegador os itens de combustível e de gás de cozinha do modal da contratação, com uma
cópia das regras de ``especificacao.reconhecer``. Os casos ficam num arquivo só, lido pelos dois testes: se
uma regra mudar de um lado e não do outro, um dos dois falha.
"""

import json
from pathlib import Path

import pytest
from lumen_mercado.especificacao import COMBUSTIVEL, GAS_DE_COZINHA, reconhecer

CASOS = json.loads((Path(__file__).parent / "fixtures" / "reconhecimento_anp.json").read_text(encoding="utf-8"))["casos"]


@pytest.mark.parametrize("descricao, unidade, produto", CASOS)
def test_caso_compartilhado(descricao, unidade, produto):
    e = reconhecer(descricao, unidade)
    if produto is None:
        assert e is None or e.categoria not in {COMBUSTIVEL, GAS_DE_COZINHA}
    else:
        assert e is not None and e.produto == produto and e.referencia == "anp"
