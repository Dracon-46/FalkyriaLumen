"""Parâmetros legais datados.

Implementa o DOC-09, seção 1.3: valores legais nunca ficam no código, e toda
consulta é feita pela data do ato, não pela data de hoje.

Três garantias:

1. **Vigência sem sobreposição.** Duas entradas da mesma chave não podem
   valer no mesmo dia — senão o resultado dependeria da ordem do arquivo.
   Isso é verificado na carga, não na consulta.
2. **Dinheiro em Decimal.** ``float`` não representa R$ 65.492,11 com exatidão,
   e uma regra de fracionamento compara somas com limites ao centavo.
3. **Não verificado não é servido.** Um parâmetro que ninguém conferiu na norma
   original é recusado por padrão. A regra que depende dele não dispara, e o
   motivo fica registrado (DOC-07, UC-13 exceção 5a). O sistema prefere calar a
   afirmar um limite legal errado.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable

ARQUIVO_PADRAO = Path(__file__).with_name("parametros_legais.toml")


class ErroParametro(Exception):
    """Erro de configuração ou consulta de parâmetro legal."""


class ParametroIndisponivel(ErroParametro, LookupError):
    """Não há parâmetro vigente e utilizável para a chave nesta data.

    Não é falha do sistema: é a condição em que a regra não pode opinar. Quem
    chama deve registrar o motivo e seguir, sem disparar indício.
    """


class ConfiguracaoInvalida(ErroParametro, ValueError):
    """O arquivo de parâmetros tem erro que tornaria as consultas ambíguas."""


@dataclass(frozen=True)
class ParametroLegal:
    """Um valor legal com vigência, fundamento e estado de verificação.

    ``vigente_ate`` nulo significa vigência em aberto. ``verificado`` diz se alguém conferiu o valor na
    norma original; ``ParametrosLegais.obter`` só entrega parâmetro não verificado a quem aceita isso
    explicitamente.
    """

    chave: str
    valor: Decimal
    vigente_de: date
    vigente_ate: date | None
    fundamento: str
    atualizado_por: str
    verificado: bool
    verificado_em: date | None = None
    fonte_verificacao: str | None = None

    def vigente_em(self, dia: date) -> bool:
        """Verdadeiro se ``dia`` está na vigência, com as duas pontas inclusivas e o fim em aberto quando não há
        ``vigente_ate``.
        """
        return self.vigente_de <= dia and (self.vigente_ate is None or dia <= self.vigente_ate)

    def citacao(self) -> str:
        """Texto que acompanha o indício como referência comparada."""
        return f"{self.fundamento}, valor fixado pelo {self.atualizado_por}"


def _para_decimal(bruto, chave: str) -> Decimal:
    """Converte o valor lido do TOML para ``Decimal``.

    Recusa ``float``: o TOML aceitaria o número sem aspas, mas ele já chegaria impreciso, e os limites
    legais são comparados ao centavo. Valor não numérico também levanta ``ConfiguracaoInvalida``.
    """
    if isinstance(bruto, float):
        # TOML aceitaria 65492.11 sem aspas, e o float já chegaria impreciso.
        raise ConfiguracaoInvalida(
            f"{chave}: escreva o valor entre aspas para evitar imprecisão de float"
        )
    try:
        return Decimal(str(bruto))
    except InvalidOperation as erro:
        raise ConfiguracaoInvalida(f"{chave}: valor {bruto!r} não é numérico") from erro


class ParametrosLegais:
    """Catálogo de parâmetros legais por chave, com as vigências de cada chave em ordem cronológica.

    A validação acontece na construção: um catálogo com vigências sobrepostas ou dados incoerentes nem chega
    a existir, e assim nenhuma consulta depende da ordem do arquivo.
    """

    def __init__(self, parametros: Iterable[ParametroLegal]):
        """Agrupa os parâmetros por chave, ordena cada grupo pelo início da vigência e valida o conjunto."""
        self._por_chave: dict[str, list[ParametroLegal]] = {}
        for p in parametros:
            self._por_chave.setdefault(p.chave, []).append(p)
        for lista in self._por_chave.values():
            lista.sort(key=lambda p: p.vigente_de)
        self._validar()

    @classmethod
    def carregar(cls, caminho: Path = ARQUIVO_PADRAO) -> "ParametrosLegais":
        """Lê o catálogo de um arquivo TOML (por padrão, o ``parametros_legais.toml`` do pacote).

        Cada chave é uma lista de tabelas (``[[chave]]``), uma por vigência, com ``valor``, ``vigente_de``,
        ``fundamento``, ``atualizado_por`` e ``verificado`` obrigatórios. Campo ausente ou formato errado
        levanta ``ConfiguracaoInvalida``.
        """
        with open(caminho, "rb") as fh:
            dados = tomllib.load(fh)
        parametros = []
        for chave, entradas in dados.items():
            if not isinstance(entradas, list):
                raise ConfiguracaoInvalida(f"{chave}: use [[{chave}]] para cada vigência")
            for e in entradas:
                faltando = {"valor", "vigente_de", "fundamento", "atualizado_por", "verificado"} - e.keys()
                if faltando:
                    raise ConfiguracaoInvalida(f"{chave}: campos ausentes {sorted(faltando)}")
                parametros.append(ParametroLegal(
                    chave=chave,
                    valor=_para_decimal(e["valor"], chave),
                    vigente_de=e["vigente_de"],
                    vigente_ate=e.get("vigente_ate"),
                    fundamento=e["fundamento"],
                    atualizado_por=e["atualizado_por"],
                    verificado=bool(e["verificado"]),
                    verificado_em=e.get("verificado_em"),
                    fonte_verificacao=e.get("fonte_verificacao"),
                ))
        return cls(parametros)

    def _validar(self) -> None:
        """Recusa, com ``ConfiguracaoInvalida``, o catálogo que tornaria as consultas ambíguas.

        Por chave, confere três coisas: fim de vigência anterior ao início, entrada marcada como verificada sem
        ``verificado_em`` e vigências sobrepostas (inclusive uma anterior ainda em aberto quando a seguinte
        começa).
        """
        for chave, lista in self._por_chave.items():
            for p in lista:
                if p.vigente_ate is not None and p.vigente_ate < p.vigente_de:
                    raise ConfiguracaoInvalida(
                        f"{chave}: vigente_ate {p.vigente_ate} anterior a vigente_de {p.vigente_de}"
                    )
                if p.verificado and p.verificado_em is None:
                    raise ConfiguracaoInvalida(
                        f"{chave} ({p.vigente_de}): marcado como verificado sem verificado_em"
                    )
            for anterior, seguinte in zip(lista, lista[1:]):
                if anterior.vigente_ate is None or anterior.vigente_ate >= seguinte.vigente_de:
                    raise ConfiguracaoInvalida(
                        f"{chave}: vigências sobrepostas entre {anterior.vigente_de} e "
                        f"{seguinte.vigente_de}. Encerre a anterior com vigente_ate."
                    )

    @property
    def chaves(self) -> list[str]:
        """Chaves cadastradas, em ordem alfabética."""
        return sorted(self._por_chave)

    def obter(self, chave: str, vigente_em: date, *, aceitar_nao_verificado: bool = False) -> ParametroLegal:
        """Parâmetro vigente na data do ato.

        ``vigente_em`` é a data do ato analisado — nunca ``date.today()``.
        """
        if chave not in self._por_chave:
            raise ParametroIndisponivel(f"parâmetro desconhecido: {chave}")
        for p in self._por_chave[chave]:
            if p.vigente_em(vigente_em):
                if not p.verificado and not aceitar_nao_verificado:
                    raise ParametroIndisponivel(
                        f"{chave} em {vigente_em}: existe, mas ainda não foi conferido "
                        f"na norma original ({p.fundamento})"
                    )
                return p
        raise ParametroIndisponivel(
            f"{chave}: nenhum valor cadastrado vigente em {vigente_em}"
        )

    def pendentes_de_verificacao(self) -> list[ParametroLegal]:
        """Todas as entradas, de qualquer chave, ainda não conferidas na norma original.

        São as que ``obter`` recusa por padrão: enquanto estiverem aqui, as regras que dependem delas não
        disparam.
        """
        return [p for lista in self._por_chave.values() for p in lista if not p.verificado]

    def vigencias(self, chave: str) -> list[ParametroLegal]:
        """Todas as entradas da chave, da mais antiga para a mais recente."""
        if chave not in self._por_chave:
            raise ParametroIndisponivel(f"parâmetro desconhecido: {chave}")
        return list(self._por_chave[chave])

    def lacunas(self, chave: str, desde: date, ate: date) -> list[tuple[date, date]]:
        """Intervalos entre ``desde`` e ``ate`` em que a chave não tem valor.

        Sobreposição já é recusada na carga; o que sobra de risco é o buraco:
        esquecer de cadastrar o decreto de um ano faz a regra calar o ano
        inteiro sem ninguém notar. Esta consulta torna o buraco visível, e o
        teste de cobertura contínua a usa para falhar antes de chegar à
        produção.
        """
        if ate < desde:
            raise ValueError("intervalo invertido")
        buracos: list[tuple[date, date]] = []
        cursor = desde
        for p in self.vigencias(chave):
            fim_p = p.vigente_ate or date.max
            if fim_p < cursor:
                continue
            if p.vigente_de > ate:
                break
            if p.vigente_de > cursor:
                buracos.append((cursor, min(p.vigente_de - timedelta(days=1), ate)))
            if fim_p >= ate:
                return buracos
            cursor = fim_p + timedelta(days=1)
        if cursor <= ate:
            buracos.append((cursor, ate))
        return buracos
