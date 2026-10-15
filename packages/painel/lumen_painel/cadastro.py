"""Cadastro dos entes federativos para os painéis: nome, UF, esfera, população e se é capital.

Vem do cadastro do SICONFI (``/entes``, uma requisição só, com União, estados, Distrito Federal e todos os
municípios), já normalizado na silver como ``ente_federativo``. É o que dá nome aos códigos IBGE dos dois
painéis, a lista de entes cujo extrato de entregas a conformidade consulta e a busca do portal, que mostra
também os entes sem nenhuma publicação no período (UC-01, exceção 4a).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from lumen_normalizacao.silver import consolidar, ler_entidade

from .comum import NOMES_UF, UFS, instante_utc, ler_json, tipo_do_ente

ESFERAS = {"uniao": "F", "estadual": "E", "municipal": "M", "distrital": "D"}


@dataclass(frozen=True)
class Ente:
    """Um ente do cadastro, na forma compacta que o estado dos painéis guarda."""

    codigo: str
    nome: str
    uf: str | None
    esfera: str | None          # F, E, M ou D
    populacao: int | None = None
    capital: bool = False

    def para_lista(self) -> list:
        """``[nome, uf, esfera, população, capital]``, a linha do arquivo do cadastro."""
        return [self.nome, self.uf, self.esfera, self.populacao, self.capital]


class Cadastro:
    """Entes por código IBGE, com nome de reserva para o código que não está no cadastro."""

    def __init__(self, entes: dict[str, Ente], gerado_em: str | None = None):
        """Guarda os entes e o instante em que o cadastro foi montado."""
        self.entes = entes
        self.gerado_em = gerado_em

    def __len__(self) -> int:
        """Quantos entes o cadastro tem."""
        return len(self.entes)

    def get(self, codigo: str) -> Ente | None:
        """O ente do código, ou ``None``."""
        return self.entes.get(codigo)

    def nome(self, codigo: str) -> str:
        """Nome do ente; sem cadastro, "União", o nome do estado ou o próprio código."""
        ente = self.entes.get(codigo)
        if ente is not None:
            return ente.nome
        tipo = tipo_do_ente(codigo)
        if tipo == "uniao":
            return "União"
        if tipo in ("estado", "df"):
            return NOMES_UF[UFS[codigo]]
        return codigo

    def da_uf(self, uf: str, *, so_municipios: bool = False) -> list[Ente]:
        """Entes da UF, em ordem de código: o estado (ou o DF) e os municípios, ou só os municípios."""
        uf = uf.upper()
        return [e for c, e in sorted(self.entes.items()) if e.uf == uf
                and (tipo_do_ente(c) == "municipio" or not so_municipios)]

    def para_json(self) -> dict:
        """O cadastro como o arquivo ``cadastro-entes.json.gz`` do estado dos painéis o guarda."""
        return {"versao": 1, "gerado_em": self.gerado_em, "fonte": "SICONFI, cadastro de entes (/entes)",
                "colunas": ["nome", "uf", "esfera", "populacao", "capital"],
                "entes": {c: e.para_lista() for c, e in sorted(self.entes.items())}}

    @classmethod
    def de_json(cls, dados: dict) -> "Cadastro":
        """Reconstrói o cadastro a partir de ``para_json``."""
        entes = {}
        for codigo, (nome, uf, esfera, populacao, capital) in (dados.get("entes") or {}).items():
            entes[codigo] = Ente(codigo, nome, uf, esfera, populacao, bool(capital))
        return cls(entes, dados.get("gerado_em"))

    @classmethod
    def ler(cls, caminho: Path | str) -> "Cadastro":
        """Lê o arquivo do cadastro (comprimido ou não)."""
        return cls.de_json(ler_json(caminho))

    @classmethod
    def da_silver(cls, silver: Path | str) -> "Cadastro":
        """Monta o cadastro a partir dos ``ente_federativo`` da silver (um por código, o mais recente).

        Só entram os códigos que ``tipo_do_ente`` reconhece (União, UF, DF e municípios de UF conhecida).
        """
        entes: dict[str, Ente] = {}
        for linha in consolidar(ler_entidade(silver, "ente_federativo")):
            codigo = str(linha.get("codigo_ibge") or "")
            if tipo_do_ente(codigo) is None:
                continue
            entes[codigo] = Ente(
                codigo=codigo,
                nome=str(linha.get("nome") or codigo),
                uf=linha.get("uf") or (UFS.get(codigo[:2]) if codigo != "1" else None),
                esfera=ESFERAS.get(str(linha.get("esfera") or "")),
                populacao=linha.get("populacao"),
                capital=bool(linha.get("capital")),
            )
        return cls(entes, instante_utc())
