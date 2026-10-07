"""Configuração compartilhada da suíte.

As fixtures de fonte real ficam em ``testes/fixtures/`` (DOC-04, seção 5) e
são usadas por mais de um pacote: o adaptador testa a coleta com elas, e o
normalizador testa a conversão para o esquema canônico com as mesmas bytes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent
FIXTURES = RAIZ / "testes" / "fixtures"


def ler_fixture(caminho: str) -> bytes:
    return (FIXTURES / caminho).read_bytes()


@pytest.fixture
def fixture_bytes():
    """Função que lê uma fixture pelo caminho relativo a testes/fixtures."""
    return ler_fixture


@pytest.fixture
def sem_proxy():
    """Abridor HTTP que ignora proxy do ambiente, para servidores locais de teste."""
    import urllib.request
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))
