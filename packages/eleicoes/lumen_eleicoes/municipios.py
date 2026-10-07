"""Cadastro de municípios da aba Eleições: código TSE, código IBGE e nome.

O TSE identifica município por um código próprio de 5 dígitos; o IBGE (e as
malhas do mapa) por um de 7. A correspondência oficial vem do próprio TSE,
no arquivo ``mun-e<eleição>-cm.json`` do sistema de resultados (campo
``cdi``). O nome exibido vem do IBGE, com acentuação e caixa corretas
(o TSE publica em maiúsculas); sem o IBGE, usa-se o do TSE.

O cadastro é gravado em ``municipios.json`` no diretório dos feeds, e é o
mesmo arquivo que o portal usa na busca (Ctrl+K). Municípios do exterior
(UF ``zz``) não têm código IBGE: a chave deles é o código TSE.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from lumen_canonico.ufs import SIGLA_PARA_CODIGO, UFS

from .modelo import MunicipioTse

UF_EXTERIOR = "zz"
NOME_EXTERIOR = "Exterior"


_MINUSCULAS = frozenset({"de", "da", "do", "das", "dos", "e", "d", "del", "la", "y"})


def nome_legivel(nome: str) -> str:
    """``"SANT'ANA DO LIVRAMENTO"`` → ``"Sant'Ana do Livramento"``.

    O TSE publica nomes em maiúsculas. Quando o nome do IBGE não está à mão
    (cadastro ainda não montado, município do exterior), esta é a forma de
    exibição. Texto que já tem minúsculas é mantido como veio.
    """
    if not nome or nome != nome.upper():
        return nome

    def palavra(p: str, primeira: bool) -> str:
        if not primeira and p in _MINUSCULAS:
            return p
        partes = p.split("'")
        saida = [partes[0] if (len(partes) > 1 and partes[0] == "d") else partes[0].capitalize()]
        saida += [x.capitalize() for x in partes[1:]]
        return "'".join(saida)

    resultado = []
    for i, p in enumerate(nome.lower().split()):
        resultado.append("-".join(palavra(h, i == 0 and j == 0) for j, h in enumerate(p.split("-"))))
    return " ".join(resultado)


def nome_da_uf(sigla: str) -> str:
    """Nome por extenso da UF pela sigla, em qualquer caixa; ``ZZ`` é o exterior e ``BR`` o Brasil.

    Sigla desconhecida volta em maiúsculas.
    """
    sigla = sigla.upper()
    if sigla == "ZZ":
        return NOME_EXTERIOR
    if sigla == "BR":
        return "Brasil"
    codigo = SIGLA_PARA_CODIGO.get(sigla)
    return UFS[codigo][1] if codigo else sigla


def codigo_ibge_da_uf(sigla: str) -> str | None:
    """Código IBGE de 2 dígitos da UF pela sigla; None para o exterior e siglas desconhecidas."""
    return SIGLA_PARA_CODIGO.get(sigla.upper())


@dataclass(frozen=True)
class Municipio:
    """Município no cadastro da aba: códigos TSE e IBGE, nome de exibição e o nome como o TSE publica.

    ``nome`` é o do IBGE quando disponível; sem ele, a forma legível do nome do TSE (``nome_legivel``).
    """

    uf: str                      # minúsculas
    tse: str                     # 5 dígitos
    ibge: str | None             # 7 dígitos; None no exterior
    nome: str                    # do IBGE quando disponível
    nome_tse: str
    capital: bool = False

    @property
    def chave(self) -> str:
        """Identificador estável no feed: IBGE no Brasil, ``zz-<tse>`` fora."""
        return self.ibge if self.ibge else f"{self.uf}-{self.tse}"


class CadastroMunicipios:
    """Cadastro em memória, indexado pelo par (UF, código TSE) e pelo código IBGE.

    A iteração segue UF, nome e código TSE, que é também a ordem gravada em ``municipios.json``.
    """

    def __init__(self, municipios: Iterable[Municipio] = ()):
        """Cadastro com os municípios dados (vazio por padrão)."""
        self._por_tse: dict[tuple[str, str], Municipio] = {}
        self._por_ibge: dict[str, Municipio] = {}
        for m in municipios:
            self.adicionar(m)

    def adicionar(self, m: Municipio) -> None:
        """Inclui o município, substituindo o de mesma chave; sem código IBGE, entra só no índice por TSE."""
        self._por_tse[(m.uf, m.tse)] = m
        if m.ibge:
            self._por_ibge[m.ibge] = m

    def __len__(self) -> int:
        """Quantidade de municípios, contados pelo código TSE."""
        return len(self._por_tse)

    def __iter__(self):
        """Municípios em ordem de UF, nome e código TSE."""
        return iter(sorted(self._por_tse.values(), key=lambda m: (m.uf, m.nome, m.tse)))

    def por_tse(self, uf: str, codigo_tse: str | int) -> Municipio | None:
        """Município pela UF e pelo código TSE; aceita UF em qualquer caixa e código sem os zeros à esquerda."""
        return self._por_tse.get((uf.lower(), str(codigo_tse).zfill(5)))

    def por_ibge(self, codigo: str) -> Municipio | None:
        """Município pelo código IBGE de 7 dígitos; None se não estiver no cadastro."""
        return self._por_ibge.get(str(codigo))

    def da_uf(self, uf: str) -> list[Municipio]:
        """Municípios de uma UF, na ordem de iteração do cadastro."""
        uf = uf.lower()
        return [m for m in self if m.uf == uf]

    # ------------------------------------------------------------ montagem

    @classmethod
    def de_tse(cls, municipios_tse: Iterable[MunicipioTse],
               nomes_ibge: dict[str, str] | None = None) -> "CadastroMunicipios":
        """Monta o cadastro a partir do arquivo de municípios do TSE, com os nomes do IBGE quando houver.

        Sem nome do IBGE para o código (e no exterior, que não tem código IBGE), o nome exibido é o do TSE
        em forma legível.
        """
        nomes_ibge = nomes_ibge or {}
        return cls(
            Municipio(uf=m.uf, tse=m.codigo_tse.zfill(5), ibge=m.codigo_ibge,
                      nome=nomes_ibge.get(m.codigo_ibge or "", "") or nome_legivel(m.nome),
                      nome_tse=m.nome, capital=m.capital)
            for m in municipios_tse
        )

    def completar(self, uf: str, codigo_tse: str | int, nome_tse: str) -> Municipio:
        """Município que aparece nos dados mas não no cadastro atual.

        Acontece com eleições antigas: municípios desmembrados, fundidos ou
        recodificados depois. Entra com o nome publicado e sem código IBGE,
        para não sumir do resultado; o mapa simplesmente não o colore.
        """
        existente = self.por_tse(uf, codigo_tse)
        if existente:
            return existente
        m = Municipio(uf=uf.lower(), tse=str(codigo_tse).zfill(5), ibge=None,
                      nome=nome_legivel(nome_tse), nome_tse=nome_tse)
        self.adicionar(m)
        return m

    # ------------------------------------------------------------ arquivo

    def para_json(self) -> dict:
        """Conteúdo de ``municipios.json``: a versão do formato e a lista de municípios."""
        return {"versao": 1, "municipios": [asdict(m) for m in self]}

    def gravar(self, caminho: Path | str) -> Path:
        """Grava ``municipios.json`` compacto, em UTF-8, por troca atômica (``.tmp`` e ``replace``)."""
        caminho = Path(caminho)
        caminho.parent.mkdir(parents=True, exist_ok=True)
        tmp = caminho.with_name(caminho.name + ".tmp")
        tmp.write_text(json.dumps(self.para_json(), ensure_ascii=False, separators=(",", ":")),
                       encoding="utf-8")
        tmp.replace(caminho)
        return caminho

    @classmethod
    def carregar(cls, caminho: Path | str) -> "CadastroMunicipios":
        """Lê um cadastro gravado por ``gravar``."""
        dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
        return cls(Municipio(**m) for m in dados.get("municipios", []))


def nomes_do_ibge(conteudo: bytes | str | list) -> dict[str, str]:
    """``/api/v1/localidades/municipios`` (qualquer visão) → {código: nome}."""
    if isinstance(conteudo, (bytes, str)):
        conteudo = json.loads(conteudo)
    saida: dict[str, str] = {}
    for item in conteudo:
        codigo = item.get("id") or item.get("municipio-id")
        nome = item.get("nome") or item.get("municipio-nome")
        if codigo and nome:
            saida[str(codigo)] = nome
    return saida
