"""Simulação de noite de apuração, para testar o coletor e o portal ao vivo.

Fora de dia de eleição não há o que acompanhar ao vivo: os arquivos do TSE
estão todos finalizados. A simulação pega arquivos finais (os de
``testes/fixtures/tse``, ou outros com os mesmos nomes) e os serve por HTTP
como se a totalização estivesse em andamento: em cada etapa, as seções
totalizadas e os votos crescem até chegar, na última, exatamente ao
resultado oficial.

**Os números intermediários são fictícios.** Cada candidato recebe uma variação
determinística que some ao longo das etapas (a liderança pode mudar no
caminho, como numa apuração real), e o resultado final é o publicado. Tudo
o que o coletor grava a partir daqui leva ``origem.simulacao = true``, e o
portal exibe a faixa "Simulação" — nunca se confunde com apuração real.

Uso::

    lumen eleicoes simular --arquivos testes/fixtures/tse --etapas 12
"""

from __future__ import annotations

import email.utils
import hashlib
import json
import re
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .tse import BRT

_ARQUIVO = re.compile(r"^[a-z]{2}(?:\d{5})?-(?:c\d{4}-)?e\d{6}-(?:u|ab)(?:_recorte)?\.json$")


def _formatar(valor: float, casas: int = 2) -> str:
    """Número no formato do TSE: texto com ``casas`` decimais e vírgula (47.031 → ``"47,03"``)."""
    return f"{valor:.{casas}f}".replace(".", ",")


def _variacao(semente: int, chave: str) -> float:
    """Variação determinística entre -0,3 e +0,3 para a ``chave`` (o número do candidato).

    Vem do SHA-256 da semente com a chave: a mesma semente dá sempre os mesmos números intermediários, e
    a simulação é reproduzível.
    """
    h = hashlib.sha256(f"{semente}:{chave}".encode()).digest()
    return (int.from_bytes(h[:4], "big") / 0xFFFFFFFF - 0.5) * 0.6   # entre -0,3 e +0,3


class Cenario:
    """Arquivos finais e a etapa atual da apuração simulada."""

    def __init__(self, raiz: Path | str, *, etapas: int = 10, semente: int = 7,
                 inicio: datetime | None = None, passo: timedelta = timedelta(minutes=6)):
        """Indexa os arquivos da raiz que o servidor vai entregar e começa na etapa 1.

        Entram resultados (``-u``), andamentos (``-ab``), o catálogo (``ele-c``) e os municípios (``mun-e``),
        pelo nome sem o sufixo ``_recorte``. O relógio simulado parte de ``inicio`` (por padrão, 04/10/2026
        às 17h de Brasília) e anda ``passo`` a cada etapa.
        """
        if etapas < 1:
            raise ValueError("etapas precisa ser ao menos 1")
        self.raiz = Path(raiz)
        self.etapas = etapas
        self.etapa = 1
        self.semente = semente
        self.inicio = inicio or datetime(2026, 10, 4, 17, 0, 0, tzinfo=BRT)
        self.passo = passo
        self.arquivos: dict[str, Path] = {}
        for p in sorted(self.raiz.glob("*.json")):
            nome = p.name.replace("_recorte", "")
            if _ARQUIVO.match(p.name) or nome.startswith(("ele-c", "mun-e")):
                self.arquivos[nome] = p
        self.trava = threading.Lock()

    @property
    def fracao(self) -> float:
        """Fração da apuração na etapa atual: ``etapa / etapas``, 1 na última."""
        return self.etapa / self.etapas

    @property
    def instante(self) -> datetime:
        """Horário simulado da etapa atual: ``inicio`` mais um ``passo`` por etapa já avançada."""
        return self.inicio + self.passo * (self.etapa - 1)

    def avancar(self) -> bool:
        """Próxima etapa. Devolve False quando já estava na última."""
        with self.trava:
            if self.etapa >= self.etapas:
                return False
            self.etapa += 1
            return True

    def ufs(self) -> list[str]:
        """UFs com arquivo de resultado de UF no cenário (para o plano de coleta)."""
        saida = set()
        for nome in self.arquivos:
            m = re.match(r"^([a-z]{2})-c\d{4}-e\d{6}-u\.json$", nome)
            if m and m.group(1) != "br":
                saida.add(m.group(1))
        return sorted(saida)

    # ------------------------------------------------------------ conteúdo

    def conteudo(self, nome: str) -> bytes | None:
        """Bytes que o servidor entrega para o arquivo ``nome``, ou None se o cenário não o tem.

        Resultados e andamentos são reescritos para a etapa atual; os demais (catálogo, municípios) saem
        como estão.
        """
        caminho = self.arquivos.get(nome)
        if caminho is None:
            return None
        bruto = caminho.read_bytes()
        if nome.endswith("-u.json"):
            return json.dumps(self._resultado(json.loads(bruto)), ensure_ascii=False).encode()
        if nome.endswith("-ab.json"):
            return json.dumps(self._andamento(json.loads(bruto)), ensure_ascii=False).encode()
        return bruto

    def _carimbo(self, d: dict) -> None:
        """Põe o instante da etapa nos campos ``dt`` e ``ht``, data e hora separadas como o TSE publica."""
        d["dt"] = self.instante.strftime("%d/%m/%Y")
        d["ht"] = self.instante.strftime("%H:%M:%S")

    def _secoes(self, s: dict, f: float) -> None:
        """Ajusta as seções totalizadas do bloco ``s`` à fração ``f`` do total, com os percentuais em texto."""
        ts = int(s.get("ts") or 0)
        st = ts if f >= 1 else int(ts * f)
        s["st"] = str(st)
        pct = 100.0 * st / ts if ts else 0.0
        s["pst"], s["pstn"] = _formatar(pct), _formatar(pct, 9)

    def _resultado(self, d: dict) -> dict:
        """Arquivo de resultado (``-u``) como estaria na etapa atual; na última, o original intacto.

        Trabalha numa cópia: carimba o instante da etapa, marca a totalização como parcial, escala seções,
        comparecimento, brancos, nulos, anulados e legenda pela fração ``f``, e os votos de cada candidato por
        ``f * (1 + variação * (1 - f))`` — a variação some quando ``f`` chega a 1. A situação dos candidatos é
        apagada, e os válidos e os percentuais são recalculados a partir dos votos da etapa.
        """
        f = self.fracao
        if f >= 1:
            return d
        d = json.loads(json.dumps(d))
        self._carimbo(d)
        d["tf"], d["and"] = "n", "p"
        d.pop("md", None)
        if d.get("s"):
            self._secoes(d["s"], f)
        e = d.get("e") or {}
        if e.get("c"):
            e["c"] = str(int(int(e["c"]) * f))
        validos = 0
        candidatos = []
        for cargo in d.get("carg", []):
            for a in cargo.get("agr", []):
                for p in a.get("par", []):
                    for c in p.get("cand", []):
                        final = int(c.get("vap") or 0)
                        fator = f * (1 + _variacao(self.semente, str(c.get("n"))) * (1 - f))
                        atual = max(0, int(final * fator))
                        c["vap"] = str(atual)
                        c["st"], c["e"] = "", "n"
                        if (c.get("dvt") or "").startswith("Válido"):
                            validos += atual
                        candidatos.append(c)
        for c in candidatos:
            pct = 100.0 * int(c["vap"]) / validos if validos else 0.0
            c["pvap"], c["pvapn"] = _formatar(pct), _formatar(pct, 9)
        v = d.get("v") or {}
        for campo in ("vb", "vn", "tvn", "van", "vansj", "vl"):
            if v.get(campo):
                v[campo] = str(int(int(v[campo]) * f))
        v["vv"] = v["vvc"] = v["vnom"] = str(validos)
        return d

    def _andamento(self, d: dict) -> dict:
        """Arquivo de andamento (``-ab``) na etapa atual: cada abrangência marcada como parcial, com o
        instante e as seções da etapa. Na última, o original."""
        f = self.fracao
        if f >= 1:
            return d
        d = json.loads(json.dumps(d))
        for a in d.get("abr", []):
            self._carimbo(a)
            a["and"] = "p"
            if a.get("s"):
                self._secoes(a["s"], f)
        return d


def _nome_do_caminho(caminho: str) -> str:
    """Último segmento do caminho da URL, sem a query string: o nome do arquivo no cenário."""
    return caminho.split("?", 1)[0].rstrip("/").rsplit("/", 1)[-1]


class ServidorSimulado:
    """HTTP local que responde como ``resultados.tse.jus.br/oficial``, com 304 e Last-Modified."""

    def __init__(self, cenario: Cenario, porta: int = 0):
        """Abre o servidor em ``127.0.0.1`` (porta 0 escolhe uma livre) e monta ``base`` com o prefixo ``/oficial``.

        O tratador localiza o arquivo só pelo nome, ignorando o resto do caminho; responde 404 ao que o
        cenário não tem e 304 quando ``If-Modified-Since`` coincide com o instante da etapa, que vai como
        ``Last-Modified`` — como o servidor do TSE, cujo 304 o coletor usa para não baixar de novo o que não
        mudou.
        """
        self.cenario = cenario
        cen = cenario

        class Tratador(BaseHTTPRequestHandler):
            """Responde ``GET`` com o conteúdo do cenário na etapa atual."""

            def log_message(self, *a):
                pass

            def do_GET(self):
                nome = _nome_do_caminho(self.path)
                conteudo = cen.conteudo(nome)
                if conteudo is None:
                    self.send_response(404)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                ultima = email.utils.format_datetime(cen.instante.astimezone(timezone.utc), usegmt=True)
                if self.headers.get("If-Modified-Since") == ultima:
                    self.send_response(304)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(conteudo)))
                self.send_header("Last-Modified", ultima)
                self.end_headers()
                self.wfile.write(conteudo)

        self.http = ThreadingHTTPServer(("127.0.0.1", porta), Tratador)
        self.base = f"http://127.0.0.1:{self.http.server_address[1]}/oficial"
        self._thread: threading.Thread | None = None

    def iniciar(self) -> "ServidorSimulado":
        """Atende numa thread daemon e devolve o próprio servidor."""
        self._thread = threading.Thread(target=self.http.serve_forever, kwargs={"poll_interval": 0.05},
                                        daemon=True)
        self._thread.start()
        return self

    def parar(self) -> None:
        """Encerra o laço de atendimento e fecha o socket."""
        self.http.shutdown()
        self.http.server_close()

    def __enter__(self) -> "ServidorSimulado":
        """Inicia o servidor ao entrar no bloco ``with``."""
        return self.iniciar()

    def __exit__(self, *exc) -> None:
        """Para o servidor ao sair do bloco ``with``, com ou sem exceção."""
        self.parar()


# ---------------------------------------------------------------- amostra

def _andamento_minimo(uf: str, municipios: list[str], instante: datetime) -> dict:
    """Arquivo ``-ab`` mínimo com os municípios dados já finalizados (uma seção, 100%), no ``instante`` dado.

    Usado por ``gerar_amostra`` para guiar o coletor na eleição municipal da amostra.
    """
    return {"abr": [{"tpabr": "mun", "cdabr": m, "and": "f", "dt": instante.strftime("%d/%m/%Y"),
                     "ht": instante.strftime("%H:%M:%S"), "s": {"ts": "1", "st": "1", "pst": "100,00"}}
                    for m in municipios]}


ANOS_DA_AMOSTRA_ANTIGA = (1945, 1950, 1989)


def _zips_de_recortes(recortes: Path, destino: Path, ano: int) -> list[Path | None]:
    """ZIPs dos três conjuntos por UF de um ano, montados dos recortes reais (``<conjunto>_<ano>_recorte.txt``).

    Devolve [candidatos, detalhe, partidos], com None no conjunto sem recorte.
    """
    import zipfile

    from .antigas import CONJUNTOS_UF, nome_arquivo_uf
    destino.mkdir(parents=True, exist_ok=True)
    zips: list[Path | None] = []
    for conjunto in CONJUNTOS_UF:
        recorte = recortes / f"{conjunto}_{ano}{'_br' if ano in (1933, 1934) else ''}_recorte.txt"
        if not recorte.exists():
            zips.append(None)
            continue
        caminho = destino / nome_arquivo_uf(conjunto, ano)
        with zipfile.ZipFile(caminho, "w") as zf:
            zf.writestr(f"{conjunto.upper()}_{ano}.txt", recorte.read_bytes())
        zips.append(caminho)
    return zips


def gerar_amostra(arquivos: Path | str, saida: Path | str) -> list[Path]:
    """Feeds de desenvolvimento a partir dos arquivos finais reais das fixtures.

    Roda o coletor de verdade, uma passada, contra o servidor simulado na
    etapa final (conteúdo idêntico ao publicado pelo TSE) e normaliza o que
    varia entre execuções — porta local, instante da coleta e da geração —,
    para que a amostra versionada no repositório seja reproduzível byte a
    byte (``test_amostra.py``). Os feeds levam ``origem.amostra = true`` e o
    portal mostra a faixa "Amostra".

    Inclui a eleição municipal de 2024 só para São Paulo (o resultado de
    prefeito da capital é real; o andamento e o cadastro mínimos que guiam o
    coletor são montados aqui) e, dos recortes reais em
    ``dados_abertos_uf``, as eleições de 1945, 1950 e 1989 (só por UF, com
    territórios extintos, o Distrito Federal antigo e o exterior).
    """
    import shutil
    import tempfile
    import urllib.request

    from lumen_ingestao.cliente_http import ClienteHttp

    from . import tse
    from .coletor import FONTE_ID, ColetorAoVivo, plano_padrao
    from .feeds import EscritorFeeds, _gravar_json

    arquivos, saida = Path(arquivos), Path(saida)
    with tempfile.TemporaryDirectory() as tmp:
        dir_tse = Path(tmp) / "tse"
        shutil.copytree(arquivos, dir_tse, ignore=shutil.ignore_patterns("dados_abertos", "dados_abertos_uf", "*.md"))
        quando = datetime(2024, 10, 6, 22, 0, tzinfo=BRT)
        (dir_tse / "sp-e000619-ab.json").write_text(json.dumps(_andamento_minimo("sp", ["71072"], quando)))
        (dir_tse / "mun-e000619-cm.json").write_text(json.dumps({"abr": [{"cd": "sp", "mu": [
            {"cd": "71072", "cdi": "3550308", "nm": "SÃO PAULO", "c": "s", "z": []}]}]}, ensure_ascii=False))
        cen = Cenario(dir_tse, etapas=1)
        with ServidorSimulado(cen) as srv:
            abridor = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            cliente = ClienteHttp(FONTE_ID, user_agent="Lumen/amostra (+https://github.com/Dracon-46/FalkyriaLumen)",
                                  rpm=60000, abridor=abridor, dormir=lambda s: None)
            catalogo = {e.id: e for e in tse.ler_catalogo(cen.conteudo("ele-c.json"))}
            escritor = EscritorFeeds(saida)
            for eid, cargos, ufs in (("2026-1t-geral", None, ["sp"]), ("2024-1t-municipal", ["prefeito"], ["sp"])):
                plano = plano_padrao(catalogo[eid], cargos=cargos, ufs=ufs)
                ColetorAoVivo(cliente, escritor, plano, base=srv.base).executar(max_passadas=1, intervalo_s=0)
            base_local = srv.base
        recortes = arquivos / "dados_abertos_uf"
        if recortes.exists():
            from .antigas import ProcessadorAnoAntigo
            for ano in ANOS_DA_AMOSTRA_ANTIGA:
                zips = _zips_de_recortes(recortes, Path(tmp) / "uf" / str(ano), ano)
                ProcessadorAnoAntigo(ano, escritor).processar_zips(*zips)
    gravados = []
    for caminho in sorted(saida.rglob("*.json")):
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        if caminho.name == "indice.json":
            dados["gerado_em"] = None
            for e in dados.get("eleicoes", []):
                e["amostra"] = True
        origem = dados.get("origem")
        if isinstance(origem, dict):
            if origem.get("url"):
                origem["url"] = origem["url"].replace(base_local, tse.BASE)
            origem["coletado_em"] = None
            origem["amostra"] = True
        _gravar_json(caminho, dados)
        gravados.append(caminho)
    return gravados
