"""Modelo canônico do Lumen: entidades, identidade, documentos e rótulos públicos.

``VERSAO_LUMEN`` é a versão do sistema, a mesma do ``pyproject.toml``. Fica
aqui, na camada mais baixa, porque vai no User-Agent de toda coleta
(RF-CO-09) e todos os pacotes coletores precisam dela sem depender da
orquestração.
"""

VERSAO_LUMEN = "0.6.0"
