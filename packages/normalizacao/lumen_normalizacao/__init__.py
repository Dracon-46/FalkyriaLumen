"""Normalização: transforma artefatos brutos da camada bronze em registros canônicos na silver.

Um módulo por fonte (``pncp``, ``ibge``, ``siconfi``), apoiado em peças comuns (``comum``,
``transformacoes``, ``qualidade``) e no escritor da silver (``silver``). Os normalizadores são puros e
determinísticos: o mesmo artefato produz sempre os mesmos registros, e o registro que não pode ser lido
vai para a quarentena sem interromper o lote.
"""
