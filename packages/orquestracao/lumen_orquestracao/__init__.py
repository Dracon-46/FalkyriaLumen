"""Pipeline local do Lumen: coleta → bronze → normalização → silver.

Até a entrada do Dagster (ADR-009), as etapas rodam por esta linha de comando.
Cada etapa foi escrita como função pura sobre diretórios — exatamente a forma
de um ativo do Dagster —, então a migração troca o disparo, não as etapas.
"""
