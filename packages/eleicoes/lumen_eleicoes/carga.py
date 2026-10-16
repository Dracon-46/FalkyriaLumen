"""Carga das eleições passadas: baixar e processar um ano dos dados abertos do TSE.

Usado por ``lumen eleicoes historico baixar|processar`` e por ``lumen eleicoes
preparar``. Dois formatos, escolhidos pelo ano:

- 1994 a 2024 (``dados_abertos`` e ``historico``): votação por município e
  zona, detalhe da apuração e, a partir de 2014, o histórico da totalização
  do Presidente. Endereços do pacote do CKAN, com os da CDN como reserva.
- 1933 a 1990 (``antigas``): votação por candidato, detalhe e votação por
  partido, só por UF. Endereços fixos da CDN; o TSE não os lista de outro
  jeito estável.

Em todos os anos, só a votação por candidato é obrigatória: o detalhe, a
votação por partido e o histórico da totalização enriquecem o resultado, e um
404 neles vira aviso, não erro (o de partido de 1989 não existe na fonte).
"""

from __future__ import annotations

import json
import sys
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from lumen_ingestao.bronze import ArmazemBronze, ArtefatoBruto
from lumen_ingestao.cliente_http import ClienteHttp

from . import antigas
from . import dados_abertos as da
from .configuracao import ConfiguracaoEleicoes
from .feeds import EscritorFeeds
from .historico import ProcessadorAno
from .municipios import CadastroMunicipios
from .transferencia import ErroTransferencia, Manifesto, baixar_arquivo, ler_manifesto

FONTE_DADOS_ABERTOS = "tse_dados_abertos"
HISTORICO_TOTALIZACAO = "historico_totalizacao"

Aviso = Callable[[str], None]


def _aviso_padrao(msg: str) -> None:
    """Escreve o aviso no stderr."""
    print(msg, file=sys.stderr, flush=True)


def anos_disponiveis() -> list[int]:
    """Todos os anos com eleição ordinária nos dados abertos, do mais recente ao mais antigo."""
    return sorted(set(da.ANOS_GERAIS) | set(da.ANOS_MUNICIPAIS) | set(antigas.ANOS_ANTIGOS), reverse=True)


class ArquivoAusente(FileNotFoundError):
    """Falta o ZIP de votação de um ano: é preciso baixar antes de processar."""


# ---------------------------------------------------------------- baixar

def urls_do_ano(cliente: ClienteHttp, ano: int, aviso: Aviso = _aviso_padrao) -> dict[str, list[str]]:
    """Endereços dos ZIPs de um ano de 1994 em diante, por conjunto: votação, detalhe e histórico.

    Parte dos endereços conhecidos da CDN e os troca pelos que o pacote do CKAN lista. Se o CKAN
    falhar ou responder algo ilegível, ficam os conhecidos, sem o histórico da totalização (que só o
    CKAN informa).
    """
    urls = {da.CONJUNTO_VOTACAO: [da.url_conjunto(da.CONJUNTO_VOTACAO, ano)],
            da.CONJUNTO_DETALHE: [da.url_conjunto(da.CONJUNTO_DETALHE, ano)], HISTORICO_TOTALIZACAO: []}
    art = cliente.obter(da.url_pacote(ano))
    if art.status_http == 200:
        try:
            grupos = da.classificar_recursos(da.ler_pacote(art.conteudo))
        except ValueError as erro:
            aviso(f"aviso: CKAN {ano}: {erro}; usando os endereços conhecidos")
            return urls
        for chave in urls:
            if grupos.get(chave):
                urls[chave] = sorted({r.url for r in grupos[chave]})
    else:
        aviso(f"aviso: CKAN {ano} respondeu HTTP {art.status_http}; usando os endereços conhecidos")
    return urls


def alvos_do_ano(cliente: ClienteHttp, ano: int, aviso: Aviso = _aviso_padrao) -> list[tuple[str, str, bool]]:
    """(conjunto, URL, obrigatório) de cada arquivo a baixar no ano.

    Até 1990, os três conjuntos por UF nos endereços fixos da CDN; depois, os do CKAN (``urls_do_ano``).
    Só a votação por candidato é obrigatória.
    """
    if ano in antigas.ANOS_ANTIGOS:
        return [(c, antigas.url_conjunto_uf(c, ano), c == antigas.CONJUNTO_CANDIDATO_UF) for c in antigas.CONJUNTOS_UF]
    return [(conjunto, url, conjunto == da.CONJUNTO_VOTACAO)
            for conjunto, urls in urls_do_ano(cliente, ano, aviso).items() for url in urls]


def registrar_manifesto(bronze: ArmazemBronze | None, manifesto: Manifesto) -> None:
    """Guarda o manifesto no bronze: o arquivo grande fica fora, o SHA-256 dele entra (ADR-021)."""
    if bronze is None:
        return
    bronze.guardar(ArtefatoBruto(
        conteudo=manifesto.para_json().encode("utf-8"), fonte_id=FONTE_DADOS_ABERTOS,
        url_solicitada=manifesto.url + "#manifesto", url_efetiva=manifesto.url, status_http=200,
        tipo_midia="application/vnd.lumen.manifesto+json",
        cabecalhos={"ETag": manifesto.etag or "", "Last-Modified": manifesto.ultima_modificacao or ""},
        coletado_em=datetime.fromisoformat(manifesto.baixado_em).astimezone(timezone.utc)))


def progresso_mb(passo: int = 50 * 1024 * 1024, saida: Callable[[str], None] | None = None):
    """Função de andamento para ``baixar_arquivo``: uma linha a cada ``passo`` bytes recebidos."""
    ultimo = 0
    escrever = saida or (lambda msg: print(msg, flush=True))

    def progresso(recebidos: int, total: int | None) -> None:
        nonlocal ultimo
        if total and recebidos - ultimo >= passo:
            ultimo = recebidos
            escrever(f"      {recebidos / 1e6:,.0f} de {total / 1e6:,.0f} MB")
    return progresso


def baixar_ano(cfg: ConfiguracaoEleicoes, cliente: ClienteHttp, ano: int, *, bronze: ArmazemBronze | None,
               atualizar: bool = False, saida: Callable[[str], None] | None = None,
               aviso: Aviso = _aviso_padrao) -> list[Manifesto]:
    """Baixa os ZIPs de um ano para ``<arquivos>/<ano>/`` e devolve os manifestos dos que vieram.

    Arquivo já baixado da mesma URL não é baixado de novo (``atualizar`` consulta o servidor). Um 404
    num conjunto opcional vira aviso; no obrigatório, ou qualquer outro erro, levanta
    ``ErroTransferencia``.
    """
    escrever = saida or (lambda msg: print(msg, flush=True))
    feitos = []
    for conjunto, url, obrigatorio in alvos_do_ano(cliente, ano, aviso):
        destino = cfg.arquivos / str(ano) / url.rsplit("/", 1)[-1]
        escrever(f"{ano}  {conjunto}  {url}")
        try:
            manifesto = baixar_arquivo(url, destino, user_agent=cfg.user_agent, atualizar=atualizar,
                                       progresso=progresso_mb(saida=escrever))
        except ErroTransferencia as erro:
            if erro.status == 404 and not obrigatorio:
                aviso(f"aviso: {url} não existe na fonte (HTTP 404); o ano segue sem esse conjunto")
                continue
            raise
        registrar_manifesto(bronze, manifesto)
        feitos.append(manifesto)
    return feitos


# ---------------------------------------------------------------- processar

@dataclass
class ResultadoAno:
    """O que o processamento de um ano produziu, no formato do resumo da linha de comando."""

    ano: int
    eleicoes: list[str] = field(default_factory=list)
    arquivos: int = 0
    linhas: int = 0
    linhas_ignoradas: int = 0
    municipios_sem_ibge: int = 0
    evolucao_turnos: list[int] = field(default_factory=list)

    def para_json(self) -> dict:
        """Dicionário para imprimir em JSON."""
        return asdict(self)


def _opcional(caminho, progresso: Callable[[str], None]):
    """O ZIP de um conjunto opcional, se existe e é um ZIP válido; senão None, com aviso no segundo caso.

    Um arquivo que a fonte entregou corrompido (ou uma página de erro com HTTP 200) não pode derrubar
    o ano inteiro: o resultado sai sem esse conjunto, como quando ele não existe.
    """
    if not caminho.exists():
        return None
    if not zipfile.is_zipfile(caminho):
        progresso(f"aviso: {caminho.name} não é um ZIP válido; o ano segue sem esse conjunto")
        return None
    return caminho


def fotos_da_coleta(dir_estado: Path, ano: int) -> dict[str, set[str]]:
    """Fotos que a coleta ao vivo baixou, por eleição do ano: o ``sq`` de cada candidato com foto, lido do
    estado do coletor (``coleta-<eleição>.json``, restaurado da nuvem com o resto do estado)."""
    saida: dict[str, set[str]] = {}
    for arquivo in sorted(Path(dir_estado).glob(f"coleta-{ano}-*.json")):
        try:
            dados = json.loads(arquivo.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if dados.get("fotos"):
            saida[arquivo.stem[len("coleta-"):]] = {str(sq) for sq in dados["fotos"]}
    return saida


def processar_ano(cfg: ConfiguracaoEleicoes, ano: int, *, escritor: EscritorFeeds, cadastro: CadastroMunicipios,
                  limite_municipio: int = 50, progresso: Callable[[str], None] | None = None) -> ResultadoAno:
    """Gera os feeds de um ano a partir dos ZIPs já baixados; levanta ``ArquivoAusente`` sem o de votação.

    Até 1990, ``antigas.ProcessadorAnoAntigo`` com os três conjuntos por UF. Depois, ``ProcessadorAno``,
    mais a evolução da totalização do Presidente quando há ``Historico_Totalizacao`` do ano na pasta.
    """
    pasta = cfg.arquivos / str(ano)
    progresso = progresso or (lambda msg: print(msg, flush=True))
    if ano in antigas.ANOS_ANTIGOS:
        cand, det, part = (pasta / antigas.nome_arquivo_uf(c, ano) for c in antigas.CONJUNTOS_UF)
        if not cand.exists():
            raise ArquivoAusente(str(cand))
        proc = antigas.ProcessadorAnoAntigo(ano, escritor, origem=ler_manifesto(cand), progresso=progresso)
        r = proc.processar_zips(cand, _opcional(det, progresso), _opcional(part, progresso))
        return ResultadoAno(ano=ano, eleicoes=r.eleicoes, arquivos=r.feeds, linhas=r.linhas_lidas,
                            linhas_ignoradas=r.linhas_ignoradas)

    votacao = pasta / f"{da.CONJUNTO_VOTACAO}_{ano}.zip"
    detalhe = pasta / f"{da.CONJUNTO_DETALHE}_{ano}.zip"
    if not votacao.exists():
        raise ArquivoAusente(str(votacao))
    proc = ProcessadorAno(ano, escritor, cadastro, origem_votacao=ler_manifesto(votacao),
                          origem_detalhe=ler_manifesto(detalhe) if detalhe.exists() else None,
                          limite_candidatos_municipio=limite_municipio, progresso=progresso,
                          fotos_ao_vivo=fotos_da_coleta(cfg.estado, ano))
    resumo = proc.processar(votacao, detalhe if detalhe.exists() else None)
    evolucoes = []
    for zip_hist in sorted(pasta.glob("Historico_Totalizacao_Presidente_BR_*T_*.zip")):
        turno = int(zip_hist.name.split("_")[-2][0])
        with zipfile.ZipFile(zip_hist) as zf:
            csvs = [n for n in zf.namelist() if n.lower().endswith(".csv")]
            if csvs:
                with zf.open(csvs[0]) as fluxo:
                    if proc.gravar_evolucao(turno, fluxo):
                        evolucoes.append(turno)
    return ResultadoAno(ano=ano, eleicoes=resumo.eleicoes, arquivos=resumo.arquivos, linhas=resumo.linhas_lidas,
                        linhas_ignoradas=resumo.linhas_ignoradas,
                        municipios_sem_ibge=len(resumo.municipios_sem_ibge), evolucao_turnos=evolucoes)
