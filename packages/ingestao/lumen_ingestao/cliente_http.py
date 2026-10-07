"""Cliente HTTP com a política de coleta responsável do DOC-06, seção 5.

``baixar_http`` faz uma requisição. Este módulo decide **quando** e **quantas
vezes** fazê-la:

- **Vazão** (RF-CO-08): balde de fichas por fonte, no limite declarado em
  ``CapacidadesFonte.limite_requisicoes_por_minuto``. O padrão do projeto é
  conservador; aumentar exige evidência de que a fonte suporta.
- **Retentativa** (RF-CO-15): espera exponencial com variação aleatória para
  falha sem resposta (``ErroColeta``) e para respostas que indicam
  sobrecarga passageira (429, 500, 502, 503, 504). ``Retry-After`` da fonte
  tem precedência sobre o cálculo, até o teto configurado.
- **Recuo** (DOC-06, "suspensão temporária da fonte após falhas sucessivas"):
  depois de N falhas seguidas a fonte fica suspensa por um período, e as
  chamadas seguintes falham na hora com ``FonteSuspensa``, sem tocar a rede.

A resposta final, mesmo de erro, é devolvida como artefato (ADR-012): quem
decide se um 503 persistente é ausência de publicação é o avaliador de
conformidade, não o cliente. As tentativas intermediárias não são
preservadas como prova; ficam no registro estruturado.

Relógio, espera e sorteio são injetáveis para que os testes sejam
determinísticos e rápidos.
"""

from __future__ import annotations

import email.utils
import logging
import random
import time
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

from .bronze import ArtefatoBruto
from .coleta_http import ErroColeta, baixar_http

log = logging.getLogger("lumen.coleta")

STATUS_RETENTAVEIS = frozenset({429, 500, 502, 503, 504})


class FonteSuspensa(ErroColeta):
    """A fonte acumulou falhas seguidas e está em recuo; nada foi requisitado."""


@dataclass
class LimitadorTaxa:
    """Balde de fichas: até ``rpm`` requisições por minuto, sem rajada maior que ``rajada``."""

    rpm: int
    rajada: int = 1
    relogio: Callable[[], float] = time.monotonic
    dormir: Callable[[float], None] = time.sleep
    _fichas: float = field(init=False)
    _ultimo: float = field(init=False)

    def __post_init__(self) -> None:
        """Valida ``rpm`` e ``rajada`` e começa com o balde cheio."""
        if self.rpm < 1:
            raise ValueError("rpm precisa ser positivo (princípio P6)")
        if self.rajada < 1:
            raise ValueError("rajada precisa ser positiva")
        self._fichas = float(self.rajada)
        self._ultimo = self.relogio()

    def _repor(self) -> None:
        """Acrescenta as fichas acumuladas desde a última reposição, à razão de ``rpm`` por minuto, até ``rajada``."""
        agora = self.relogio()
        self._fichas = min(float(self.rajada), self._fichas + (agora - self._ultimo) * self.rpm / 60.0)
        self._ultimo = agora

    def aguardar(self) -> float:
        """Bloqueia até haver ficha. Devolve quanto esperou, em segundos."""
        self._repor()
        esperado = 0.0
        if self._fichas < 1.0:
            falta = (1.0 - self._fichas) * 60.0 / self.rpm
            self.dormir(falta)
            esperado = falta
            self._repor()
            self._fichas = max(self._fichas, 1.0)
        self._fichas -= 1.0
        return esperado


@dataclass(frozen=True)
class PoliticaRetentativa:
    """Parâmetros de retentativa e de recuo da fonte.

    ``max_tentativas`` inclui a primeira requisição. A espera entre tentativas parte de
    ``espera_base_s`` e não passa de ``espera_teto_s``; ``falhas_para_suspender`` falhas
    seguidas suspendem a fonte por ``suspensao_s`` segundos.
    """

    max_tentativas: int = 4
    espera_base_s: float = 2.0
    espera_teto_s: float = 120.0
    falhas_para_suspender: int = 5
    suspensao_s: float = 900.0

    def __post_init__(self) -> None:
        """Exige ao menos uma tentativa."""
        if self.max_tentativas < 1:
            raise ValueError("max_tentativas precisa ser ao menos 1")

    def espera(self, tentativa: int, sorteio: float) -> float:
        """Exponencial com variação de ±50%: 2s, 4s, 8s... até o teto."""
        bruta = self.espera_base_s * (2 ** (tentativa - 1))
        return min(self.espera_teto_s, bruta * (0.5 + sorteio))


def interpretar_retry_after(valor: str | None, agora: datetime | None = None) -> float | None:
    """``Retry-After`` em segundos ou em data HTTP. Devolve segundos ou None."""
    if not valor:
        return None
    valor = valor.strip()
    if valor.isdigit():
        return float(valor)
    try:
        quando = email.utils.parsedate_to_datetime(valor)
    except (TypeError, ValueError):
        return None
    if quando is None:
        return None
    if quando.tzinfo is None:
        quando = quando.replace(tzinfo=timezone.utc)
    referencia = agora or datetime.now(timezone.utc)
    return max(0.0, (quando - referencia).total_seconds())


class ClienteHttp:
    """Cliente de uma fonte: limite de taxa, retentativa e recuo em torno de ``baixar_http``.

    O limitador e a contagem de falhas seguidas pertencem à fonte, então cada fonte tem
    o seu cliente. A política completa está descrita no módulo.
    """

    def __init__(
        self,
        fonte_id: str,
        *,
        user_agent: str,
        rpm: int,
        politica: PoliticaRetentativa | None = None,
        abridor: urllib.request.OpenerDirector | None = None,
        timeout: float = 60,
        relogio: Callable[[], float] = time.monotonic,
        dormir: Callable[[float], None] = time.sleep,
        sorteio: Callable[[], float] = random.random,
    ):
        """Configura a identificação, o limitador de ``rpm`` por minuto e a política de retentativa.

        Sem ``politica``, usa a padrão. Relógio, espera e sorteio são injetáveis para testes determinísticos.
        """
        self.fonte_id = fonte_id
        self.user_agent = user_agent
        self.politica = politica or PoliticaRetentativa()
        self.abridor = abridor
        self.timeout = timeout
        self.relogio = relogio
        self.dormir = dormir
        self.sorteio = sorteio
        self.limitador = LimitadorTaxa(rpm=rpm, relogio=relogio, dormir=dormir)
        self.falhas_seguidas = 0
        self.suspensa_ate: float | None = None
        self.requisicoes = 0

    @property
    def suspensa(self) -> bool:
        """Indica se a fonte está em recuo agora, isto é, se o prazo de suspensão ainda não venceu."""
        return self.suspensa_ate is not None and self.relogio() < self.suspensa_ate

    def _registrar_falha(self) -> None:
        """Conta mais uma falha seguida e suspende a fonte ao atingir ``falhas_para_suspender``."""
        self.falhas_seguidas += 1
        if self.falhas_seguidas >= self.politica.falhas_para_suspender:
            self.suspensa_ate = self.relogio() + self.politica.suspensao_s
            log.warning("fonte_suspensa", extra={"fonte": self.fonte_id,
                                                 "falhas_seguidas": self.falhas_seguidas,
                                                 "suspensao_s": self.politica.suspensao_s})

    def obter(self, url: str, cabecalhos: dict[str, str] | None = None) -> ArtefatoBruto:
        """Faz o GET com limite de taxa, retentativa e recuo, e devolve a resposta final como artefato.

        Com a fonte em recuo, levanta ``FonteSuspensa`` sem tocar a rede. Falha sem resposta
        é retentada; na última tentativa, ou se a fonte entrar em recuo, ``ErroColeta`` é
        propagado. Status retentável (429, 500, 502, 503, 504) espera o ``Retry-After`` da
        fonte ou o tempo calculado, sempre até o teto; nos mesmos casos de parada, a resposta
        de erro é devolvida como artefato. Qualquer outra resposta zera as falhas seguidas.
        Vencido o recuo, a fonte ganha nova chance, mas uma falha já volta a suspendê-la.
        """
        if self.suspensa:
            raise FonteSuspensa(f"{self.fonte_id} em recuo após {self.falhas_seguidas} falhas seguidas")
        if self.suspensa_ate is not None:
            # Recuo vencido: dá uma nova chance, mas uma falha já volta a suspender.
            self.suspensa_ate = None
            self.falhas_seguidas = max(0, self.politica.falhas_para_suspender - 1)
        ultima_excecao: ErroColeta | None = None
        for tentativa in range(1, self.politica.max_tentativas + 1):
            ultima = tentativa == self.politica.max_tentativas
            self.limitador.aguardar()
            self.requisicoes += 1
            try:
                artefato = baixar_http(url, self.fonte_id, user_agent=self.user_agent,
                                       timeout=self.timeout, abridor=self.abridor,
                                       cabecalhos=cabecalhos)
            except ErroColeta as erro:
                ultima_excecao = erro
                self._registrar_falha()
                log.info("tentativa_sem_resposta", extra={"fonte": self.fonte_id, "url": url,
                                                         "tentativa": tentativa, "erro": str(erro)})
                if ultima or self.suspensa:
                    raise
                self.dormir(self.politica.espera(tentativa, self.sorteio()))
                continue
            if artefato.status_http in STATUS_RETENTAVEIS:
                self._registrar_falha()
                log.info("tentativa_com_erro", extra={"fonte": self.fonte_id, "url": url,
                                                     "tentativa": tentativa, "status": artefato.status_http})
                if ultima or self.suspensa:
                    return artefato
                pedida = interpretar_retry_after(artefato.cabecalhos.get("Retry-After")
                                                 or artefato.cabecalhos.get("retry-after"))
                calculada = self.politica.espera(tentativa, self.sorteio())
                self.dormir(min(self.politica.espera_teto_s, pedida if pedida is not None else calculada))
                continue
            self.falhas_seguidas = 0
            return artefato
        raise ultima_excecao or ErroColeta("tentativas esgotadas")  # pragma: no cover
