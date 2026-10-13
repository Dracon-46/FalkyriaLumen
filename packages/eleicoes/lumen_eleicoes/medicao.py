"""Tamanho dos feeds gravados, contra os limites dos armazenamentos gratuitos (adendo do ADR-026).

Serve para decidir onde publicar (Cloudflare R2 ou Supabase Storage) e para estimar quanto uma noite de
apuração consome de tráfego de saída, que no Supabase gratuito tem cota (no R2, é grátis). Mede:

- o total e cada grupo: uma eleição (``2026-1t-geral/…``), as malhas (``geo/``), as fotos e os arquivos
  da raiz (``indice.json``, ``municipios.json``);
- o tamanho comprimido com gzip, perto do que o navegador baixa quando o servidor comprime JSON;
- os maiores arquivos, contra o limite por arquivo;
- o pior caso de saída por visitante e por hora de apuração, em duas visões: Brasil e o estado de feed
  mais pesado (o de um estado grande chega a dez vezes o nacional). O portal relê o feed aberto e a
  evolução a cada 15 s e o índice a cada minuto (``packages/portal/src/lib/feeds.ts``). "Pior caso"
  porque supõe que o feed mudou entre duas leituras; quando não mudou, o navegador revalida e recebe
  só um 304.

Não lê nem interpreta o conteúdo dos feeds: só o tamanho.
"""

from __future__ import annotations

import gzip
from dataclasses import dataclass, field
from pathlib import Path

# Limites dos planos gratuitos verificados em 13/10/2026 (documentação de cada serviço), em bytes decimais.
GB = 1_000_000_000
MB = 1_000_000
LIMITES = {
    "supabase_gratuito": {"armazenamento": 1 * GB, "arquivo": 50 * MB, "saida": 5 * GB, "saida_cache": 5 * GB},
    "r2_gratuito": {"armazenamento": 10 * GB, "arquivo": None, "saida": None, "saida_cache": None},
}

# Leituras do portal durante a apuração (feeds.ts e PainelEleicoes.tsx)
LEITURAS_FEED_POR_HORA = 3600 // 15
LEITURAS_INDICE_POR_HORA = 3600 // 60

INDICE = "indice.json"
PREFIXO_EVOLUCAO = "historico-"
VISOES = ("brasil", "estado")


def _gzip(conteudo: bytes) -> int:
    """Tamanho do conteúdo comprimido com gzip no nível padrão dos servidores (6)."""
    return len(gzip.compress(conteudo, compresslevel=6, mtime=0))


def visao_de(abrangencia: str) -> str | None:
    """Visão do portal a que a abrangência do arquivo pertence: ``brasil`` (``br``), ``estado`` (``uf-xx``)."""
    if abrangencia == "br":
        return "brasil"
    if abrangencia.startswith("uf-"):
        return "estado"
    return None


def grupo_de(relativo: str) -> str:
    """Grupo do arquivo: ``raiz`` para os da raiz, senão a primeira pasta (``geo``, ``fotos`` ou a eleição)."""
    partes = relativo.split("/")
    return "raiz" if len(partes) == 1 else partes[0]


@dataclass
class Tamanho:
    """Quantidade de arquivos e bytes, sem e com gzip."""

    arquivos: int = 0
    bytes: int = 0
    bytes_gzip: int = 0

    def somar(self, b: int, bz: int) -> None:
        """Acrescenta um arquivo de ``b`` bytes (``bz`` com gzip)."""
        self.arquivos += 1
        self.bytes += b
        self.bytes_gzip += bz

    def para_json(self) -> dict:
        """Contagens como dicionário, para o JSON do comando."""
        return {"arquivos": self.arquivos, "bytes": self.bytes, "bytes_gzip": self.bytes_gzip}


@dataclass
class Medicao:
    """O que ``medir`` encontrou num diretório de feeds."""

    pasta: str
    total: Tamanho = field(default_factory=Tamanho)
    grupos: dict[str, Tamanho] = field(default_factory=dict)
    maiores: list[dict] = field(default_factory=list)
    # Por eleição e visão (brasil, estado): o par feed + evolução mais pesado, que é o que o portal relê ao vivo
    visoes: dict[str, dict[str, dict]] = field(default_factory=dict)
    indice_gzip: int = 0

    def saida_por_visitante_hora(self, eleicao: str, visao: str = "brasil") -> int | None:
        """Pior caso, em bytes com gzip, de um visitante acompanhando ``eleicao`` na ``visao`` por uma hora."""
        n = self.visoes.get(eleicao, {}).get(visao)
        if n is None:
            return None
        feed = n["bytes_gzip"] + n["evolucao_gzip"]
        return LEITURAS_FEED_POR_HORA * feed + LEITURAS_INDICE_POR_HORA * self.indice_gzip

    def cabe(self, plano: str) -> dict[str, bool | None]:
        """Se o total e o maior arquivo cabem nos limites do plano (``None`` quando o plano não tem limite)."""
        lim = LIMITES[plano]
        maior = max((m["bytes"] for m in self.maiores), default=0)
        return {
            "armazenamento": None if lim["armazenamento"] is None else self.total.bytes <= lim["armazenamento"],
            "arquivo": None if lim["arquivo"] is None else maior <= lim["arquivo"],
        }

    def para_json(self) -> dict:
        """A medição inteira, com a saída estimada por eleição, o que cabe em cada plano e os limites usados."""
        return {
            "pasta": self.pasta,
            "total": self.total.para_json(),
            "grupos": {g: t.para_json() for g, t in sorted(self.grupos.items())},
            "maiores": self.maiores,
            "visoes": {
                e: {v: {**n, "saida_pior_caso_por_visitante_hora": self.saida_por_visitante_hora(e, v)}
                    for v, n in sorted(por_visao.items())}
                for e, por_visao in sorted(self.visoes.items())
            },
            "indice_gzip": self.indice_gzip,
            "cabe": {p: self.cabe(p) for p in LIMITES},
            "limites": LIMITES,
        }


def medir(pasta: Path | str, *, maiores: int = 10) -> Medicao:
    """Mede os arquivos publicáveis de ``pasta`` (ignora os temporários ``.tmp`` e os ocultos)."""
    pasta = Path(pasta)
    m = Medicao(str(pasta))
    if not pasta.is_dir():
        return m
    todos: list[dict] = []
    pares: dict[tuple[str, str, str], dict] = {}   # (eleição, cargo, abrangência) → feed e evolução
    for caminho in sorted(pasta.rglob("*")):
        if not caminho.is_file() or caminho.name.endswith(".tmp") or caminho.name.startswith("."):
            continue
        rel = caminho.relative_to(pasta).as_posix()
        conteudo = caminho.read_bytes()
        b, bz = len(conteudo), _gzip(conteudo)
        m.total.somar(b, bz)
        m.grupos.setdefault(grupo_de(rel), Tamanho()).somar(b, bz)
        todos.append({"arquivo": rel, "bytes": b, "bytes_gzip": bz})
        if rel == INDICE:
            m.indice_gzip = bz
        partes = rel.split("/")
        if len(partes) == 3 and partes[2].endswith(".json"):
            nome = partes[2][: -len(".json")]
            evolucao = nome.startswith(PREFIXO_EVOLUCAO)
            abrangencia = nome[len(PREFIXO_EVOLUCAO):] if evolucao else nome
            if visao_de(abrangencia):
                item = pares.setdefault((partes[0], partes[1], abrangencia),
                                        {"cargo": partes[1], "abrangencia": abrangencia, "bytes": 0, "bytes_gzip": 0,
                                         "evolucao_gzip": 0})
                if evolucao:
                    item["evolucao_gzip"] = bz
                else:
                    item["bytes"], item["bytes_gzip"] = b, bz
    for (eleicao, _, abrangencia), item in sorted(pares.items()):
        if not item["bytes"]:
            continue                      # evolução sem o feed: o portal não chega a abrir
        por_visao = m.visoes.setdefault(eleicao, {})
        visao = visao_de(abrangencia)
        atual = por_visao.get(visao)
        if atual is None or item["bytes_gzip"] + item["evolucao_gzip"] > atual["bytes_gzip"] + atual["evolucao_gzip"]:
            por_visao[visao] = item
    m.maiores = sorted(todos, key=lambda x: (-x["bytes"], x["arquivo"]))[:maiores]
    return m


def _legivel(n: int | None) -> str:
    """Bytes em kB, MB ou GB decimais, com uma casa (``None`` vira travessão)."""
    if n is None:
        return "—"
    for unidade, base in (("GB", GB), ("MB", MB), ("kB", 1000)):
        if n >= base:
            return f"{n / base:.1f} {unidade}".replace(".", ",")
    return f"{n} B"


def _sim_nao(v: bool | None) -> str:
    """Célula da tabela de limites: "sem limite", "sim" ou "não" em negrito."""
    return "sem limite" if v is None else ("sim" if v else "**não**")


def resumo_markdown(m: Medicao) -> str:
    """Resumo em Markdown para o resumo da execução no GitHub Actions."""
    linhas = [
        "## Tamanho dos feeds",
        "",
        f"{m.total.arquivos} arquivo(s), {_legivel(m.total.bytes)} ({_legivel(m.total.bytes_gzip)} com gzip).",
        "",
        "| Grupo | Arquivos | Tamanho | Com gzip |",
        "|---|---:|---:|---:|",
    ]
    linhas += [f"| {g} | {t.arquivos} | {_legivel(t.bytes)} | {_legivel(t.bytes_gzip)} |"
               for g, t in sorted(m.grupos.items())]
    linhas += ["", "| Plano | Cabe no armazenamento | Maior arquivo cabe |", "|---|---|---|"]
    for plano in LIMITES:
        c = m.cabe(plano)
        linhas.append(f"| {plano.replace('_', ' ')} | {_sim_nao(c['armazenamento'])} | {_sim_nao(c['arquivo'])} |")
    if m.visoes:
        cota = LIMITES["supabase_gratuito"]["saida"]
        linhas += ["", "### Saída durante a apuração (pior caso, com gzip)", "",
                   "| Eleição | Visão | Feed mais pesado | Feed + evolução | Por visitante e hora | "
                   "Horas-visitante na cota do Supabase |",
                   "|---|---|---|---:|---:|---:|"]
        for e, por_visao in sorted(m.visoes.items()):
            for v in VISOES:
                n = por_visao.get(v)
                if n is None:
                    continue
                hora = m.saida_por_visitante_hora(e, v) or 0
                horas = f"{cota // hora:,}".replace(",", ".") if hora else "—"
                linhas.append(f"| {e} | {v} | `{n['cargo']}/{n['abrangencia']}` | "
                              f"{_legivel(n['bytes_gzip'] + n['evolucao_gzip'])} | {_legivel(hora)} | {horas} |")
        linhas += ["", "Pior caso: o feed muda entre duas leituras de 15 s. Quando não muda, o navegador recebe "
                   "só um 304. A cota do Supabase gratuito é de 5 GB de saída sem cache por mês, somada a todo o "
                   "uso da organização; no R2, a saída é grátis."]
    linhas += ["", "### Maiores arquivos", "", "| Arquivo | Tamanho | Com gzip |", "|---|---:|---:|"]
    linhas += [f"| `{x['arquivo']}` | {_legivel(x['bytes'])} | {_legivel(x['bytes_gzip'])} |" for x in m.maiores]
    return "\n".join(linhas) + "\n"
