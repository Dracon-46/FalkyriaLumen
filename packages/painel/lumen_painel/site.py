"""O diretório publicado dos painéis (GitHub Pages, ADR-028).

O site é refeito inteiro a cada publicação, a partir do estado guardado (os dias do PNCP e o extrato de
entregas por UF): não há o que sincronizar arquivo a arquivo, como no bucket das eleições. Os JSON avulsos vão
sem compressão (o GitHub Pages comprime na entrega a quem aceita gzip); os conjuntos por grupo vão em ``.json.gz``,
que o portal descomprime, para o site caber no limite e na implantação do Pages.

Desenho do diretório::

    indice.json                       versão, quando foi gerado, cobertura de cada painel
    entes.json                        cadastro para a busca: código, nome, UF, tipo, população
    contratacoes/panorama.json        Brasil: totais, esferas, UFs, meses, modalidades, fornecedores
    contratacoes/ente/<grupo>.json.gz   os entes do grupo (``comum.grupo_do_ente``): União (1), estado, DF ou
                                        municípios, comprimido
    contratacoes/orgao/<grupo>.json.gz  os órgãos do grupo (``comum.grupo_do_cnpj``): prefeitura, câmara, autarquia,
                                        fundação ou empresa pública, comprimido
    conformidade/panorama.json        Brasil: resultados por UF e por obrigação
    conformidade/uf/<sigla>.json      entes da UF, com o resumo de cada um
    conformidade/ente/<código>.json   as obrigações avaliadas de um ente e o grupo de pares (ADR-038)
    conformidade/pares/<id>.json      um grupo de pares: critérios, distribuição e os entes que o formam
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from .comum import gravar_json

PAGINA = """<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><title>Lumen · dados dos painéis</title>
<meta name="viewport" content="width=device-width, initial-scale=1"></head>
<body style="font-family:system-ui,sans-serif;max-width:40rem;margin:2rem auto;padding:0 1rem;line-height:1.5">
<h1>Lumen · dados dos painéis</h1>
<p>Arquivos JSON lidos pelo portal do Lumen nas áreas de contratações e de conformidade. Cada número vem do
PNCP ou do extrato de entregas do SICONFI, com a data da coleta em <code>indice.json</code>.</p>
</body></html>
"""


class Site:
    """Escreve os arquivos do site num diretório, contando quantos gravou."""

    def __init__(self, raiz: Path | str, *, limpar: bool = True):
        """Com ``limpar``, apaga o que houver no diretório antes de começar (o site é refeito inteiro)."""
        self.raiz = Path(raiz)
        if limpar and self.raiz.exists():
            shutil.rmtree(self.raiz)
        self.raiz.mkdir(parents=True, exist_ok=True)
        self.arquivos = 0

    def gravar(self, relativo: str, conteudo: Any) -> Path:
        """Grava ``conteudo`` como JSON em ``raiz/relativo``; o caminho não pode sair da raiz.

        Caminho terminado em ``.json.gz`` sai comprimido com gzip: são os conjuntos grandes (base de CNPJ e
        emendas, ADR-043 e ADR-044), que o portal descomprime no navegador para caber no limite do GitHub Pages.
        """
        destino = (self.raiz / relativo).resolve()
        if self.raiz.resolve() not in destino.parents:
            raise ValueError(f"caminho fora do site: {relativo}")
        self.arquivos += 1
        return gravar_json(destino, conteudo, comprimir=relativo.endswith(".json.gz"))

    def finalizar(self) -> None:
        """Página de apresentação e ``.nojekyll`` (o GitHub Pages serve os arquivos como estão)."""
        (self.raiz / ".nojekyll").write_text("", encoding="utf-8")
        (self.raiz / "index.html").write_text(PAGINA, encoding="utf-8")
