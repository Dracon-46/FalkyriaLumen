"""Adaptador do PNTP: as avaliações dos portais de transparência de todos os entes, por ciclo.

O Programa Nacional de Transparência Pública (PNTP) é a avaliação anual, pelos tribunais de contas com a
Atricon, dos portais de transparência do Executivo e do Legislativo de todos os municípios, dos estados, do
DF e da União (além de consórcios, estatais e outros poderes): 11.697 entidades em 2025, cada uma com o
índice e o nível de transparência e o endereço do portal. É o cadastro nacional dos portais que a ADR-028
pedia, e a avaliação de transparência mais ampla que existe.

- Página: ``https://radardatransparencia.atricon.org.br/downloads.html``, que lista as bases por ciclo
  (``dados/dados_pntp_AAAA.zip``, de 2022 em diante).
- Base: um ZIP por ciclo (338 MB em 2025) com ``pntp_AAAA/avaliacoes_pntp_AAAA.xlsx`` (1,6 MB, uma linha
  por entidade) e as respostas a cada critério, por UF. O adaptador baixa só a planilha de avaliações,
  por ``Range`` (``zip_remoto``), e o bronze guarda a planilha como está dentro do ZIP, conferida pelo
  CRC-32 (ADR-032).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Iterable, Iterator

from ...bronze import ArtefatoBruto
from ...coleta_http import ErroColeta
from ...portas import Janela, Periodicidade, ReferenciaArtefato
from ...zip_remoto import baixar_membro
from ._simples import FonteListaFixa

BASE_RADAR = "https://radardatransparencia.atricon.org.br"
DISPOSITIVO_PNTP = "LC 101/2000, art. 48; Lei 12.527/2011, art. 8º (avaliação do PNTP pelos tribunais de contas)"
TIPO_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

_BASE_DO_CICLO = re.compile(r"dados/dados_pntp_(\d{4})\.zip")


def ciclos_publicados(html: str) -> list[int]:
    """Os ciclos com base publicada na página de downloads, em ordem crescente."""
    return sorted({int(m) for m in _BASE_DO_CICLO.findall(html)})


def membro_de_avaliacoes(ciclo: int) -> str:
    """Caminho da planilha de avaliações dentro do ZIP do ciclo."""
    return f"pntp_{ciclo}/avaliacoes_pntp_{ciclo}.xlsx"


class FontePntpAvaliacoes(FonteListaFixa):
    """Planilha de avaliações do PNTP de cada ciclo publicado (ou dos ``ciclos`` pedidos)."""

    fonte_id = "pntp_avaliacoes"
    objetos = frozenset({"AvaliacaoTransparencia"})
    periodicidade = Periodicidade.ANUAL
    dispositivo = DISPOSITIVO_PNTP

    def __init__(self, cliente, *, ciclos: Iterable[int] | None = None, base: str = BASE_RADAR):
        """Sem ``ciclos``, todos os que a página de downloads lista."""
        super().__init__(cliente, base)
        self.ciclos = sorted(set(ciclos)) if ciclos else None

    def _pedir(self, url: str, cabecalhos: dict) -> ArtefatoBruto:
        """GET contado como respondido ou falho, como em ``FonteListaFixa._obter``."""
        try:
            a = self.cliente.obter(url, cabecalhos)
        except ErroColeta:
            self.falhas += 1
            raise
        if a.status_http >= 500:
            self.falhas += 1
        else:
            self.respondidas += 1
        return a

    def listar(self, janela: Janela) -> Iterator[ReferenciaArtefato]:
        """Uma referência por ciclo; a janela não se aplica (cada ciclo é uma avaliação anual completa).

        Ciclo pedido que a página não lista levanta ``ErroColeta``: a base ainda não saiu.
        """
        pagina = self._pedir(f"{self.base}/downloads.html", {"Accept": "text/html"})
        if pagina.status_http != 200:
            raise ErroColeta(f"página de downloads do PNTP respondeu {pagina.status_http}")
        publicados = ciclos_publicados(pagina.conteudo.decode("utf-8", errors="replace"))
        faltando = sorted(set(self.ciclos or []) - set(publicados))
        if faltando:
            raise ErroColeta(f"ciclos sem base publicada no Radar: {faltando} (publicados: {publicados})")
        for ciclo in self.ciclos or publicados:
            yield ReferenciaArtefato(url=f"{self.base}/dados/dados_pntp_{ciclo}.zip", objeto="AvaliacaoTransparencia",
                                     chave_origem=str(ciclo), metadados={"ciclo": str(ciclo),
                                                                         "membro": membro_de_avaliacoes(ciclo)})

    def baixar(self, ref: ReferenciaArtefato) -> ArtefatoBruto:
        """A planilha de avaliações de dentro do ZIP, por ``Range``, com a identidade do ZIP nos cabeçalhos."""
        membro = ref.metadados["membro"]
        try:
            m = baixar_membro(self.cliente, ref.url, membro)
        except ErroColeta:
            self.falhas += 1
            raise
        self.respondidas += 1
        cabecalhos = {"X-Lumen-Zip-Membro": membro, "X-Lumen-Zip-Tamanho": str(m.tamanho_do_zip),
                      "X-Lumen-Zip-Crc32": f"{m.entrada.crc32:08x}"}
        if m.etag:
            cabecalhos["ETag"] = m.etag
        if m.ultima_modificacao:
            cabecalhos["Last-Modified"] = m.ultima_modificacao
        url = f"{ref.url}#{membro}"
        return ArtefatoBruto(conteudo=m.conteudo, fonte_id=self.fonte_id, url_solicitada=url, url_efetiva=url,
                             status_http=200, tipo_midia=TIPO_XLSX, cabecalhos=cabecalhos,
                             coletado_em=datetime.now(timezone.utc))
