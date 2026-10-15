"""Referências que vêm com o pacote: malhas do mapa e cadastro de municípios.

O mapa precisa das malhas do IBGE, e a busca e os resultados por município
precisam do cadastro TSE ↔ IBGE. As duas coisas mudam raramente (um município
novo a cada poucos anos) e são pequenas — 1,4 MB de malhas na qualidade
``minima``, 1,5 MB de contornos em ``maxima`` dos 191 municípios com mais
de uma zona eleitoral e 0,5 MB de cadastro —, por isso ficam versionadas em
``lumen_eleicoes/dados`` e o portal funciona sem nenhum download prévio. A
proveniência (endereços, data e SHA-256 do que foi publicado pelas fontes)
está em ``dados/LEIAME.md``.

Quem precisar da versão corrente das fontes continua tendo
``lumen eleicoes mapas`` e ``lumen eleicoes municipios``, que gravam por cima
no diretório dos feeds. ``instalar`` nunca sobrescreve um arquivo que já está
lá, para não desfazer essa atualização.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from .feeds import substituir_arquivo
from .municipios import CadastroMunicipios

DIR_DADOS = Path(__file__).resolve().parent / "dados"
ARQUIVO_CADASTRO = "municipios.json"
DIR_MALHAS = "geo"


def arquivos_embutidos() -> list[tuple[Path, str]]:
    """(arquivo no pacote, caminho relativo no diretório dos feeds) de cada referência embutida.

    Cadastro primeiro, depois as malhas em ordem de nome (``br-uf.json`` e ``uf-<sigla>-mu.json``) e os
    contornos finos dos municípios com mais de uma zona eleitoral (``mu/<código IBGE>.json``).
    """
    itens = [(DIR_DADOS / ARQUIVO_CADASTRO, ARQUIVO_CADASTRO)]
    itens += [(p, f"{DIR_MALHAS}/{p.name}") for p in sorted((DIR_DADOS / DIR_MALHAS).glob("*.json"))]
    itens += [(p, f"{DIR_MALHAS}/mu/{p.name}") for p in sorted((DIR_DADOS / DIR_MALHAS / "mu").glob("*.json"))]
    return [(origem, destino) for origem, destino in itens if origem.exists()]


def instalar(saida: Path | str, *, substituir: bool = False) -> list[Path]:
    """Copia as referências embutidas para o diretório dos feeds e devolve os arquivos copiados.

    Arquivo que já existe no destino fica como está (pode ser uma versão mais nova, baixada da fonte),
    exceto com ``substituir=True``. A cópia passa por um ``.tmp`` e ``replace``: quem lê o diretório
    nunca vê um arquivo pela metade.
    """
    saida = Path(saida)
    copiados = []
    for origem, relativo in arquivos_embutidos():
        destino = saida / relativo
        if destino.exists() and not substituir:
            continue
        destino.parent.mkdir(parents=True, exist_ok=True)
        tmp = destino.with_name(destino.name + ".tmp")
        shutil.copyfile(origem, tmp)
        substituir_arquivo(tmp, destino)
        copiados.append(destino)
    return copiados


def cadastro_embutido() -> CadastroMunicipios:
    """Cadastro de municípios que vem com o pacote (vazio se o arquivo não estiver instalado)."""
    caminho = DIR_DADOS / ARQUIVO_CADASTRO
    return CadastroMunicipios.carregar(caminho) if caminho.exists() else CadastroMunicipios()
