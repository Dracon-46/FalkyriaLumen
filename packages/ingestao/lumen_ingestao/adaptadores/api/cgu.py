"""Adaptadores do Portal da Transparência (CGU): cadastros de sanções CEIS, CNEP e CEPIM.

Os três cadastros vêm dos arquivos de dados abertos, e não da API: a API pede
chave (``chave-api-dados``) e devolve 15 registros por página, e o próprio
Portal recomenda os arquivos para volume alto. Os arquivos não pedem chave
(ADR-030).

- Página de download: ``https://portaldatransparencia.gov.br/download-de-dados/<cadastro>``.
  O HTML declara a data do arquivo mais recente num ``arquivos.push({"ano" :
  "2026", "mes" : "10", "dia" : "15", "origem" : "CEIS"})``.
- Arquivo: ``.../download-de-dados/<cadastro>/AAAAMMDD``, que redireciona para
  ``dadosabertos-download.cgu.gov.br/.../AAAAMMDD_<CADASTRO>.zip``. O ZIP
  traz um CSV só, em ISO-8859-1, separado por ``;``.

Cada arquivo é o retrato completo do cadastro no dia, e não um incremento: a
janela da coleta não se aplica, e cada coleta guarda no bronze o retrato mais
recente (o bronze não duplica o conteúdo se o retrato não mudou). O CEIS de
15/10/2026 tinha 23.787 sanções em 3,4 MB; o CNEP, 1.840; o CEPIM, 3.521
impedimentos.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Iterator

from ...bronze import ArtefatoBruto
from ...coleta_http import ErroColeta
from ...portas import Janela, Periodicidade, ReferenciaArtefato
from ._simples import FonteListaFixa

BASE_PORTAL = "https://portaldatransparencia.gov.br"
DISPOSITIVO_CGU = "Lei 12.846/2013, arts. 22 e 23; Lei 14.133/2021, art. 161; Decreto 8.777/2016 (dados abertos)"

_DATA_DO_ARQUIVO = re.compile(
    r'arquivos\.push\(\{\s*"ano"\s*:\s*"(?P<ano>\d{4})"\s*,\s*"mes"\s*:\s*"(?P<mes>\d{2})"\s*,'
    r'\s*"dia"\s*:\s*"(?P<dia>\d{2})"\s*,\s*"origem"\s*:\s*"(?P<origem>[A-Za-z]+)"\s*\}\)')


class DataDoArquivoAusente(ErroColeta):
    """A página de download respondeu, mas sem a data do arquivo: o formato da página mudou ou ela falhou."""


def data_do_arquivo(html: str, cadastro: str) -> date:
    """Data do arquivo mais recente do ``cadastro`` declarada na página de download.

    Com mais de uma data declarada, vale a mais recente. Sem nenhuma, levanta ``DataDoArquivoAusente``.
    """
    datas = [date(int(m["ano"]), int(m["mes"]), int(m["dia"]))
             for m in _DATA_DO_ARQUIVO.finditer(html) if m["origem"].upper() == cadastro.upper()]
    if not datas:
        raise DataDoArquivoAusente(f"a página de download do {cadastro} não declara a data do arquivo")
    return max(datas)


class FonteCguCadastro(FonteListaFixa):
    """Base dos cadastros de sanções da CGU: descobre a data do arquivo na página de download e baixa o ZIP.

    A subclasse define ``fonte_id`` e ``cadastro`` (o nome no caminho do Portal: ``ceis``, ``cnep``,
    ``cepim``). A página de download conta como consulta para ``reportar_conformidade``, como o arquivo.
    """

    objetos = frozenset({"Sancao"})
    periodicidade = Periodicidade.DIARIA
    dispositivo = DISPOSITIVO_CGU
    cadastro: str

    def __init__(self, cliente, base: str = BASE_PORTAL):
        """Usa ``BASE_PORTAL`` como base padrão."""
        super().__init__(cliente, base)

    def _pedir(self, url: str, aceita: str) -> ArtefatoBruto:
        """GET com o ``Accept`` dado, contado como respondido ou falho como em ``FonteListaFixa._obter``."""
        try:
            a = self.cliente.obter(url, {"Accept": aceita})
        except ErroColeta:
            self.falhas += 1
            raise
        if a.status_http >= 500:
            self.falhas += 1
        else:
            self.respondidas += 1
        return a

    def listar(self, janela: Janela) -> Iterator[ReferenciaArtefato]:
        """Uma referência, a do arquivo mais recente; a janela não se aplica (cada arquivo é o cadastro inteiro).

        A página de download que responde com erro, ou sem a data do arquivo, levanta ``ErroColeta``:
        sem a data não há o que baixar, e a coleta inteira falha com o motivo.
        """
        pagina = self._pedir(f"{self.base}/download-de-dados/{self.cadastro}", "text/html")
        if pagina.status_http != 200:
            raise ErroColeta(f"página de download do {self.cadastro} respondeu {pagina.status_http}")
        dia = data_do_arquivo(pagina.conteudo.decode("utf-8", errors="replace"), self.cadastro)
        yield ReferenciaArtefato(url=f"{self.base}/download-de-dados/{self.cadastro}/{dia:%Y%m%d}",
                                 objeto="Sancao", chave_origem=f"{self.cadastro.upper()}-{dia:%Y%m%d}",
                                 metadados={"cadastro": self.cadastro.upper(), "data_arquivo": dia.isoformat()})

    def baixar(self, ref: ReferenciaArtefato) -> ArtefatoBruto:
        """Baixa o ZIP do dia, seguindo o redirecionamento para o servidor de arquivos da CGU."""
        return self._pedir(ref.url, "application/zip")


class FonteCguCeis(FonteCguCadastro):
    """CEIS: Cadastro Nacional de Empresas Inidôneas e Suspensas (Lei 12.846/2013, art. 23; Lei 14.133/2021, art. 161)."""

    fonte_id = "cgu_ceis"
    cadastro = "ceis"


class FonteCguCnep(FonteCguCadastro):
    """CNEP: Cadastro Nacional de Empresas Punidas (Lei 12.846/2013, art. 22)."""

    fonte_id = "cgu_cnep"
    cadastro = "cnep"


class FonteCguCepim(FonteCguCadastro):
    """CEPIM: entidades privadas sem fins lucrativos impedidas de receber transferências da União (Decreto 7.592/2011)."""

    fonte_id = "cgu_cepim"
    cadastro = "cepim"
