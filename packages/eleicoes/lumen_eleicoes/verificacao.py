"""Conferência dos feeds gravados: o que o portal vai ler está íntegro?

Roda depois de cada processamento (``lumen eleicoes verificar``) e na CI,
sobre os feeds de amostra. Não confere os números contra o TSE — isso é o
papel dos testes —, confere o contrato: versão, campos obrigatórios,
referências do índice que apontam para arquivo existente e somas que não
podem ser violadas (votos de candidatos válidos não passam dos válidos).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from . import VERSAO_ESQUEMA_FEED

CAMPOS_RESULTADO = ("versao", "tipo", "eleicao", "cargo", "abrangencia", "atualizado_em", "origem",
                    "totalizacao", "comparecimento", "votos", "candidatos", "partes", "avisos")
CAMPOS_PANORAMA = ("versao", "tipo", "eleicao", "cargo", "abrangencia", "origem", "totalizacao",
                   "partidos", "partes")


@dataclass
class Relatorio:
    """Resultado da conferência: quantos feeds foram lidos e a lista de problemas encontrados."""

    arquivos: int = 0
    problemas: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Nenhum problema encontrado."""
        return not self.problemas


def _ler(caminho: Path, rel: Relatorio) -> dict | None:
    """JSON do arquivo; se não der para ler, None e o problema anotado no relatório."""
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as erro:
        rel.problemas.append(f"{caminho}: ilegível ({erro})")
        return None


def verificar_feed(caminho: Path, dados: dict, rel: Relatorio) -> None:
    """Confere um feed contra o contrato do portal e anota no relatório o que falhar.

    Versão, tipo e campos obrigatórios vêm primeiro; se algum falha, o resto não é conferido. Nos
    resultados, a soma dos candidatos válidos não pode passar dos votos válidos (exceto com candidatos
    omitidos ou aviso de fonte sem destinação), a ordem tem de ser decrescente e os percentuais ficar
    entre 0 e 100. Na evolução, os pontos têm de estar em ordem de tempo. Na conferência seção a seção
    (ADR-053), só os campos: a diferença entre as seções e o divulgado é o que ela mostra, não um defeito do feed.
    """
    if dados.get("versao") != VERSAO_ESQUEMA_FEED:
        rel.problemas.append(f"{caminho}: versao {dados.get('versao')!r}, esperado {VERSAO_ESQUEMA_FEED}")
        return
    tipo = dados.get("tipo")
    obrigatorios = {"resultado": CAMPOS_RESULTADO, "panorama": CAMPOS_PANORAMA,
                    "historico": ("versao", "tipo", "pontos", "candidatos"),
                    "conferencia": ("versao", "tipo", "secoes", "brasil", "ufs", "confere")}.get(tipo)
    if obrigatorios is None:
        rel.problemas.append(f"{caminho}: tipo desconhecido {tipo!r}")
        return
    faltando = [c for c in obrigatorios if c not in dados]
    if faltando:
        rel.problemas.append(f"{caminho}: faltam {', '.join(faltando)}")
        return
    if tipo == "resultado":
        validos = dados["votos"].get("validos")
        soma = sum(c["votos"] for c in dados["candidatos"] if c.get("valido"))
        if validos is not None and soma > validos and dados.get("candidatos_omitidos", 0) == 0:
            sem_destinacao = any("destinação" in a for a in dados.get("avisos", []))
            if not sem_destinacao:
                rel.problemas.append(f"{caminho}: candidatos somam {soma} votos válidos, acima de {validos}")
        votos = [c["votos"] for c in dados["candidatos"] if c.get("valido")]
        if votos != sorted(votos, reverse=True):
            rel.problemas.append(f"{caminho}: candidatos fora da ordem de votação")
        for c in dados["candidatos"]:
            if c.get("pct") is not None and not (0 <= c["pct"] <= 100.0001):
                rel.problemas.append(f"{caminho}: percentual fora de 0–100 ({c['numero']})")
    if tipo == "historico":
        instantes = [p.get("t") for p in dados["pontos"] if p.get("t")]
        if instantes != sorted(instantes):
            rel.problemas.append(f"{caminho}: pontos da evolução fora de ordem")


def verificar_zonas(caminho: Path, dados: dict, rel: Relatorio) -> None:
    """Confere um arquivo do mapa das zonas (``geo/zonas-<ano>/``, ver ``zonas.py``).

    No índice, os municípios; no arquivo de um município, que cada local tenha longitude, latitude, uma zona
    da lista de zonas, eleitores e nome, e que a contagem de locais por zona bata com a lista.
    """
    from .zonas import VERSAO_ZONAS
    if dados.get("versao") != VERSAO_ZONAS:
        rel.problemas.append(f"{caminho}: versao {dados.get('versao')!r}, esperado {VERSAO_ZONAS}")
        return
    if dados.get("tipo") == "zonas-indice":
        if not isinstance(dados.get("municipios"), dict):
            rel.problemas.append(f"{caminho}: índice das zonas sem municípios")
        return
    faltando = [c for c in ("tipo", "ano", "municipio", "origem", "zonas", "locais") if c not in dados]
    if dados.get("tipo") != "zonas" or faltando:
        rel.problemas.append(f"{caminho}: arquivo de zonas fora do contrato ({', '.join(faltando) or dados.get('tipo')})")
        return
    contagem = {z["zona"]: 0 for z in dados["zonas"]}
    for local in dados["locais"]:
        ok = (isinstance(local, list) and len(local) == 5 and all(isinstance(v, (int, float)) for v in local[:2])
              and local[2] in contagem and isinstance(local[3], int))
        if not ok:
            rel.problemas.append(f"{caminho}: local fora do formato {local!r}")
            return
        contagem[local[2]] += 1
    if any(z["locais"] != contagem[z["zona"]] for z in dados["zonas"]):
        rel.problemas.append(f"{caminho}: locais por zona não batem com a lista de locais")


def verificar_eleitorado(caminho: Path, dados: dict, rel: Relatorio) -> None:
    """Confere o conteúdo de um lugar do eleitorado (Brasil, UF ou um município do grupo; ver ``eleitorado.py``).

    O lugar tem o total e as quatro características, cada uma somando o total; no município, cada seção é
    ``[zona, seção, local, eleitores]`` com uma zona da lista. ``lumen eleicoes eleitorado`` confere tudo o que
    grava, antes de empacotar.
    """
    from .eleitorado import CARACTERISTICAS, VERSAO_ELEITORADO
    if dados.get("versao") != VERSAO_ELEITORADO:
        rel.problemas.append(f"{caminho}: versao {dados.get('versao')!r}, esperado {VERSAO_ELEITORADO}")
        return
    lugar = dados.get("lugar")
    if dados.get("tipo") != "eleitorado" or not isinstance(lugar, dict) or not isinstance(lugar.get("eleitores"), int):
        rel.problemas.append(f"{caminho}: arquivo do eleitorado fora do contrato")
        return
    for nome, _, _ in CARACTERISTICAS:
        lista = lugar.get(nome) or []
        if lista and sum(v[1] for v in lista) != lugar["eleitores"]:
            rel.problemas.append(f"{caminho}: {nome} não soma o total de eleitores")
    if dados.get("nivel") == "municipio":
        zonas = {z.get("zona") for z in dados.get("zonas") or []}
        for s in dados.get("secoes") or []:
            if not (isinstance(s, list) and len(s) == 4 and s[0] in zonas and isinstance(s[3], int)):
                rel.problemas.append(f"{caminho}: seção fora do formato {s!r}")
                return


def verificar_diretorio(raiz: Path | str) -> Relatorio:
    """Confere o diretório dos feeds: o índice, os arquivos que ele promete e cada feed.

    A existência dos arquivos listados no índice só é cobrada nas eleições históricas (``dados_abertos``):
    na coleta ao vivo, uma UF do plano pode ainda não ter sido publicada pelo TSE. Depois, cada
    ``<eleição>/<cargo>/*.json`` passa por ``verificar_feed`` e cada arquivo do mapa das zonas
    (``geo/zonas-<ano>/*.json``) por ``verificar_zonas``. As malhas do IBGE em ``geo/`` não são feeds.
    """
    raiz = Path(raiz)
    rel = Relatorio()
    indice_arq = raiz / "indice.json"
    if not indice_arq.exists():
        rel.problemas.append(f"{indice_arq}: índice ausente")
        return rel
    indice = _ler(indice_arq, rel)
    if indice is None:
        return rel
    if indice.get("versao") != VERSAO_ESQUEMA_FEED:
        rel.problemas.append(f"{indice_arq}: versao {indice.get('versao')!r}")
    for e in indice.get("eleicoes", []):
        # Na coleta ao vivo, uma UF do plano pode ainda não ter arquivo (o
        # TSE não publicou); a cobrança de existência vale para o histórico.
        if e.get("origem") != "dados_abertos":
            continue
        for cargo in e.get("cargos", []):
            pasta = raiz / e["id"] / cargo["slug"]
            if cargo["nivel"] == "br" or cargo["nivel"] == "mu":
                if not (pasta / "br.json").exists():
                    rel.problemas.append(f"{pasta}/br.json: o índice lista o cargo, mas o arquivo não existe")
            # As UFs do próprio cargo, quando o índice as traz (Deputado Distrital só no DF); senão, as da eleição
            for uf in cargo.get("ufs", e.get("ufs", [])):
                if uf == "zz" and cargo["nivel"] != "br":
                    continue
                arq = pasta / f"uf-{uf}.json"
                if cargo["nivel"] == "uf" and uf != "zz" and not arq.exists():
                    rel.problemas.append(f"{arq}: UF listada no índice sem arquivo")
    for arquivo in sorted(raiz.glob("*/*/*.json")):
        if arquivo.relative_to(raiz).parts[0] == "geo":
            continue
        dados = _ler(arquivo, rel)
        rel.arquivos += 1
        if dados is not None:
            verificar_feed(arquivo, dados, rel)
    for arquivo in sorted(raiz.glob("geo/zonas-*/*.json")):
        dados = _ler(arquivo, rel)
        rel.arquivos += 1
        if dados is not None:
            verificar_zonas(arquivo, dados, rel)
    return rel
