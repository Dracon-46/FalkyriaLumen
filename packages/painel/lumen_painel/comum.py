"""Peças comuns dos painéis: JSON em disco, códigos dos entes, modalidades do PNCP, links e valores."""

from __future__ import annotations

import gzip
import json
import os
import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

# Brasília não tem horário de verão desde 2019: a data "de hoje" dos painéis é a de UTC-3.
FUSO_BRASILIA = timezone(timedelta(hours=-3))

# Nomes das modalidades como o PNCP as publica (/api/pncp/v1/modalidades, lido em 05/10/2026), sem os
# espaços sobrando no fim e com o travessão trocado por hífen, para ficarem iguais entre si.
MODALIDADES: dict[int, str] = {
    1: "Leilão - Eletrônico",
    2: "Diálogo Competitivo",
    3: "Concurso",
    4: "Concorrência - Eletrônica",
    5: "Concorrência - Presencial",
    6: "Pregão - Eletrônico",
    7: "Pregão - Presencial",
    8: "Dispensa",
    9: "Inexigibilidade",
    10: "Manifestação de Interesse",
    11: "Pré-qualificação",
    12: "Credenciamento",
    13: "Leilão - Presencial",
    14: "Inaplicabilidade da Licitação",
    15: "Chamada pública",
    16: "Concorrência - Eletrônica Internacional",
    17: "Concorrência - Presencial Internacional",
    18: "Pregão - Eletrônico Internacional",
    19: "Pregão - Presencial Internacional",
}

# Código IBGE de 2 dígitos → sigla da UF
UFS: dict[str, str] = {
    "11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA", "16": "AP", "17": "TO", "21": "MA", "22": "PI",
    "23": "CE", "24": "RN", "25": "PB", "26": "PE", "27": "AL", "28": "SE", "29": "BA", "31": "MG", "32": "ES",
    "33": "RJ", "35": "SP", "41": "PR", "42": "SC", "43": "RS", "50": "MS", "51": "MT", "52": "GO", "53": "DF",
}
CODIGO_DA_UF: dict[str, str] = {sigla: codigo for codigo, sigla in UFS.items()}
NOMES_UF: dict[str, str] = {
    "AC": "Acre", "AL": "Alagoas", "AM": "Amazonas", "AP": "Amapá", "BA": "Bahia", "CE": "Ceará",
    "DF": "Distrito Federal", "ES": "Espírito Santo", "GO": "Goiás", "MA": "Maranhão", "MG": "Minas Gerais",
    "MS": "Mato Grosso do Sul", "MT": "Mato Grosso", "PA": "Pará", "PB": "Paraíba", "PE": "Pernambuco",
    "PI": "Piauí", "PR": "Paraná", "RJ": "Rio de Janeiro", "RN": "Rio Grande do Norte", "RO": "Rondônia",
    "RR": "Roraima", "RS": "Rio Grande do Sul", "SC": "Santa Catarina", "SE": "Sergipe", "SP": "São Paulo",
    "TO": "Tocantins",
}

UNIAO = "1"
DISTRITO_FEDERAL = "53"

# numeroControlePNCP: <CNPJ do órgão>-<tipo>-<sequencial>/<ano>; tipo 1 é contratação, 2 é contrato
_NUMERO_CONTROLE = re.compile(r"^(?P<cnpj>\d{14})-(?P<tipo>[12])-(?P<seq>\d{1,9})/(?P<ano>\d{4})$")
_CAMINHO_PNCP = {"1": "editais", "2": "contratos"}


def hoje_brasilia(agora: datetime | None = None) -> date:
    """A data corrente em Brasília (UTC-3)."""
    return (agora or datetime.now(timezone.utc)).astimezone(FUSO_BRASILIA).date()


def tipo_do_ente(codigo: str | None) -> str | None:
    """``uniao`` (código 1), ``df`` (53), ``estado`` (2 dígitos) ou ``municipio`` (7 dígitos); senão ``None``."""
    if not codigo:
        return None
    if codigo == UNIAO:
        return "uniao"
    if codigo == DISTRITO_FEDERAL:
        return "df"
    if len(codigo) == 2 and codigo in UFS:
        return "estado"
    if len(codigo) == 7 and codigo.isdigit() and codigo[:2] in UFS:
        return "municipio"
    return None


def uf_do_ente(codigo: str | None) -> str | None:
    """Sigla da UF de um ente estadual, distrital ou municipal; ``None`` para a União e código desconhecido."""
    tipo = tipo_do_ente(codigo)
    if tipo in ("estado", "df", "municipio"):
        return UFS[codigo[:2]]
    return None


def link_pncp(numero_controle: str | None) -> str | None:
    """Página pública do processo (``/app/editais/…``) ou do contrato (``/app/contratos/…``) no PNCP."""
    m = _NUMERO_CONTROLE.match((numero_controle or "").strip())
    if not m:
        return None
    return (f"https://pncp.gov.br/app/{_CAMINHO_PNCP[m.group('tipo')]}/{m.group('cnpj')}/"
            f"{m.group('ano')}/{int(m.group('seq'))}")


def valor(bruto: Any) -> float | None:
    """Valor em reais com duas casas, a partir do texto ou número da silver; vazio ou inválido vira ``None``."""
    if bruto is None or bruto == "":
        return None
    try:
        return float(round(Decimal(str(bruto)), 2))
    except (InvalidOperation, ValueError):
        return None


def somar(a: float, b: float | None) -> float:
    """Soma em reais arredondada a centavos (os valores ausentes contam zero)."""
    return round(a + (b or 0.0), 2)


def ler_json(caminho: Path | str) -> Any:
    """Lê JSON de ``caminho``, descomprimindo quando o arquivo começa com a assinatura do gzip."""
    dados = Path(caminho).read_bytes()
    if dados[:2] == b"\x1f\x8b":
        dados = gzip.decompress(dados)
    return json.loads(dados)


def grupo_do_ente(codigo: str) -> str:
    """O arquivo que leva o ente nos conjuntos publicados por grupo (contratações, emendas, convênios).

    Município: o 3º, o 4º e o 5º dígitos do código IBGE, que se espalham entre as UFs (723 grupos, o maior com 46
    municípios); os primeiros dígitos são os da UF e fariam grupos de até 345. UF, DF e União: o próprio código.
    Menos arquivos deixam a implantação do GitHub Pages dentro do prazo.
    """
    return codigo[2:5] if len(codigo) == 7 else codigo


def grupo_do_orgao(cnpj: str) -> str:
    """O arquivo que leva o órgão nas contratações publicadas por grupo: o 6º, o 7º e o 8º dígitos do CNPJ (1.000
    grupos, o maior com 48 órgãos em outubro de 2026); os primeiros se concentram em poucos valores."""
    return cnpj[5:8]


def gravar_json(caminho: Path | str, conteudo: Any, *, comprimir: bool = False) -> Path:
    """Grava JSON compacto em UTF-8 por troca atômica (temporário no mesmo diretório e ``os.replace``).

    ``comprimir`` grava com gzip (nível 6, sem data no cabeçalho, para o mesmo conteúdo dar os mesmos bytes).
    """
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    corpo = json.dumps(conteudo, ensure_ascii=False, separators=(",", ":"), sort_keys=False).encode("utf-8")
    if comprimir:
        corpo = gzip.compress(corpo, compresslevel=6, mtime=0)
    temporario = caminho.with_name(f".{caminho.name}.{os.getpid()}.tmp")
    temporario.write_bytes(corpo)
    os.replace(temporario, caminho)
    return caminho


def instante_utc(agora: datetime | None = None) -> str:
    """Instante em ISO 8601, UTC, sem frações de segundo (``2026-10-14T12:00:00Z``)."""
    return (agora or datetime.now(timezone.utc)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
