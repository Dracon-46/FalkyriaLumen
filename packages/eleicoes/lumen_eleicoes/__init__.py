"""Aba Eleições do Lumen: resultados oficiais do TSE, ao vivo e históricos.

Fontes:

- **Sistema de divulgação de resultados** (``resultados.tse.jus.br``): eleições
  cujo prazo de divulgação ainda não venceu — em 2026, os ciclos 2024 e 2026.
  É a fonte ao vivo na noite da apuração.
- **Dados abertos** (``dadosabertos.tse.jus.br`` / ``cdn.tse.jus.br``): todas
  as eleições anteriores, em arquivos CSV por município e zona.

O módulo coleta, preserva a prova na camada bronze do Lumen, agrega e grava
os *feeds* JSON que o portal lê (``feeds.py``). O portal nunca consulta o TSE
diretamente: um coletor só, com identificação e limite de taxa, em vez de
cada visitante batendo no servidor do tribunal (princípio P6).

Linguagem: resultados de eleição são números oficiais e não passam por
interpretação. Ainda assim, todo texto exibido segue o vocabulário
controlado do DOC-08.
"""

VERSAO_ESQUEMA_FEED = 1
