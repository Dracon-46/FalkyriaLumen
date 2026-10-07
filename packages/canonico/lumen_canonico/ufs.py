"""Unidades da federação: código IBGE, sigla, nome e região.

Tabela fixa, conferida contra ``/api/v1/localidades/estados`` do IBGE (o teste
``test_ufs_conferem_com_o_ibge`` falha se divergir da fixture capturada).
"""

from __future__ import annotations

UFS: dict[str, tuple[str, str, str]] = {
    # código: (sigla, nome, sigla da região)
    "11": ("RO", "Rondônia", "N"),
    "12": ("AC", "Acre", "N"),
    "13": ("AM", "Amazonas", "N"),
    "14": ("RR", "Roraima", "N"),
    "15": ("PA", "Pará", "N"),
    "16": ("AP", "Amapá", "N"),
    "17": ("TO", "Tocantins", "N"),
    "21": ("MA", "Maranhão", "NE"),
    "22": ("PI", "Piauí", "NE"),
    "23": ("CE", "Ceará", "NE"),
    "24": ("RN", "Rio Grande do Norte", "NE"),
    "25": ("PB", "Paraíba", "NE"),
    "26": ("PE", "Pernambuco", "NE"),
    "27": ("AL", "Alagoas", "NE"),
    "28": ("SE", "Sergipe", "NE"),
    "29": ("BA", "Bahia", "NE"),
    "31": ("MG", "Minas Gerais", "SE"),
    "32": ("ES", "Espírito Santo", "SE"),
    "33": ("RJ", "Rio de Janeiro", "SE"),
    "35": ("SP", "São Paulo", "SE"),
    "41": ("PR", "Paraná", "S"),
    "42": ("SC", "Santa Catarina", "S"),
    "43": ("RS", "Rio Grande do Sul", "S"),
    "50": ("MS", "Mato Grosso do Sul", "CO"),
    "51": ("MT", "Mato Grosso", "CO"),
    "52": ("GO", "Goiás", "CO"),
    "53": ("DF", "Distrito Federal", "CO"),
}

SIGLA_PARA_CODIGO: dict[str, str] = {sigla: codigo for codigo, (sigla, _, _) in UFS.items()}


def sigla_da_uf(codigo_ibge: str | int | None) -> str | None:
    """Sigla a partir de qualquer código IBGE de UF (2 dígitos) ou município (7)."""
    if codigo_ibge is None:
        return None
    texto = str(codigo_ibge).strip()
    if len(texto) not in (2, 7) or not texto.isdigit():
        return None
    entrada = UFS.get(texto[:2])
    return entrada[0] if entrada else None
