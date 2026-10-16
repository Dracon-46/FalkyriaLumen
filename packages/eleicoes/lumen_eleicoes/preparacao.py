"""``lumen eleicoes preparar``: a aba Eleições pronta num comando.

O repositório traz o código, o mapa e o cadastro de municípios, mas não os
resultados: os arquivos do TSE somam vários GB (só a votação por município de
2022 tem 642 MB compactados) e são publicados e corrigidos pelo próprio
tribunal. Este comando busca tudo na fonte oficial uma vez, guarda os ZIPs
com o SHA-256 de cada um (ADR-021) e gera os feeds que o portal lê:

1. instala as referências embutidas (malhas do IBGE e cadastro TSE ↔ IBGE)
   no diretório dos feeds (``referencias.instalar``);
2. gera o portal estático quando ele não existe ou o código mudou depois da
   última geração (``npm ci`` e ``npm run build``);
3. com ``--servir``, sobe o servidor local e abre o navegador antes da carga:
   cada eleição aparece no portal assim que fica pronta;
4. coleta, no sistema de resultados, as eleições ordinárias que já
   aconteceram e ainda não estão nos dados abertos (em outubro de 2026, o 1º
   turno de 2026), até a totalização terminar, com todos os municípios;
5. baixa os locais de votação de 2026 a 2018 e grava o mapa das zonas
   eleitorais dos municípios com mais de uma zona (``zonas.py``, ADR-029);
6. baixa e processa os dados abertos de 1933 a 1990 (resultados por UF);
7. baixa e processa os dados abertos de 2024 a 1994, do mais recente para o
   mais antigo, com todos os municípios e, onde há mais de uma, as zonas.

É retomável. ``<estado>/preparar.json`` registra cada etapa concluída e o
SHA-256 dos arquivos de entrada; rodar de novo pula o que já está pronto
(``--refazer`` ignora o registro, ``--atualizar`` consulta a fonte e só
reprocessa o ano cujos arquivos mudaram). Um ano de 1994 em diante processado
por uma versão anterior do processamento (``VERSAO_PROCESSAMENTO``) é refeito
uma vez: foi assim que os feeds dos municípios ganharam as zonas eleitorais. Um erro num ano não interrompe os
outros: o resumo final lista o que falhou e o comando devolve 1.

Na nuvem (``--nuvem``, ADR-026), a mesma sequência roda numa máquina que
começa vazia: antes de tudo, ``publicacao.Nuvem.restaurar`` traz o índice
publicado e o estado; depois de cada ano e de cada passada do sistema de
resultados, ``sincronizar`` publica o que mudou e guarda o estado. Com
``--limite-minutos``, a carga para sozinha antes do prazo da máquina, e a
execução seguinte continua de onde esta parou.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
import webbrowser
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

from lumen_ingestao.bronze import ArmazemBronze, ArmazemBronzeLocal
from lumen_ingestao.cliente_http import ClienteHttp

from . import antigas, carga, referencias, tse, zonas
from . import dados_abertos as da
from .coletor import FONTE_ID, ColetorAoVivo, ResumoPassada, plano_padrao
from .configuracao import ConfiguracaoEleicoes
from .feeds import EscritorFeeds
from .modelo import Eleicao
from .municipios import CadastroMunicipios

RAIZ_REPO = Path(__file__).resolve().parents[3]
DIR_PORTAL = RAIZ_REPO / "packages" / "portal"
ARQUIVO_ESTADO = "preparar.json"
# O que, mudando, exige gerar o portal de novo (os feeds não: o portal os lê em tempo de execução)
FONTES_DO_PORTAL = ("src", "package.json", "package-lock.json", "next.config.ts", "next.config.mjs",
                    "next.config.js", "tsconfig.json")
TIPOS_AO_VIVO = ("geral", "municipal")
ORCAMENTO_MUNICIPAL = 1000
# Depois do prazo da carga (``limite_minutos``), a publicação ainda tem esta folga para terminar o que gerou;
# passou dela, para entre dois lotes. No GitHub Actions: prazo de 280 minutos, publicação até 330, máquina 355.
FOLGA_PUBLICACAO = 50 * 60
MAX_PASSADAS = 500
# Versão do processamento dos dados abertos de 1994 em diante. Sobe quando o que sai de um mesmo ZIP muda
# (2: zonas eleitorais nos feeds dos municípios); ano registrado com versão menor é processado de novo.
VERSAO_PROCESSAMENTO = 2


class PortalIndisponivel(RuntimeError):
    """Não foi possível gerar o portal (Node.js ausente ou ``npm`` falhou)."""


def _agora() -> str:
    """Instante atual em ISO 8601, UTC, sem frações de segundo."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# ---------------------------------------------------------------- registro do que já foi feito

@dataclass
class EstadoPreparacao:
    """O que ``preparar`` já concluiu, gravado em ``<estado>/preparar.json`` depois de cada etapa.

    ``anos`` guarda, por ano, quando terminou, as eleições geradas, o SHA-256 de cada ZIP de entrada e a
    versão do processamento; ``ao_vivo``, por eleição do sistema de resultados, quando a coleta terminou
    com a totalização concluída; ``zonas``, por ano, o SHA-256 do ZIP de locais de votação usado.
    """

    caminho: Path
    anos: dict[str, dict] = field(default_factory=dict)
    ao_vivo: dict[str, dict] = field(default_factory=dict)
    zonas: dict[str, dict] = field(default_factory=dict)

    @classmethod
    def carregar(cls, caminho: Path) -> "EstadoPreparacao":
        """Lê o registro; arquivo ausente ou ilegível vale como nada feito."""
        try:
            dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            dados = {}
        return cls(Path(caminho), anos=dict(dados.get("anos") or {}), ao_vivo=dict(dados.get("ao_vivo") or {}),
                   zonas=dict(dados.get("zonas") or {}))

    def gravar(self) -> None:
        """Grava o registro por troca atômica (``.tmp`` e ``replace``)."""
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.caminho.with_name(self.caminho.name + ".tmp")
        tmp.write_text(json.dumps({"versao": 1, "anos": self.anos, "ao_vivo": self.ao_vivo, "zonas": self.zonas},
                                  ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self.caminho)

    def ano_pronto(self, ano: int) -> bool:
        """Se o ano já foi processado por completo, pela versão atual do processamento (de 1994 em diante)."""
        registro = self.anos.get(str(ano))
        if registro is None:
            return False
        return ano in antigas.ANOS_ANTIGOS or registro.get("processamento", 1) >= VERSAO_PROCESSAMENTO

    def entradas_do_ano(self, ano: int) -> dict[str, str]:
        """{arquivo: SHA-256} dos ZIPs com que o ano foi processado."""
        return dict((self.anos.get(str(ano)) or {}).get("entradas") or {})

    def marcar_ano(self, ano: int, entradas: dict[str, str], eleicoes: list[str]) -> None:
        """Registra o ano como concluído e grava."""
        self.anos[str(ano)] = {"concluido_em": _agora(), "entradas": entradas, "eleicoes": eleicoes,
                               "processamento": VERSAO_PROCESSAMENTO}
        self.gravar()

    def zonas_prontas(self, ano: int) -> bool:
        """Se o mapa das zonas do ano já foi gravado pela revisão atual do cálculo e com os contornos atuais."""
        registro = self.zonas.get(str(ano))
        return bool(registro) and registro.get("revisao") == zonas.REVISAO_ZONAS and (
            registro.get("contornos") == zonas.assinatura_contornos())

    def entradas_das_zonas(self, ano: int) -> dict[str, str]:
        """{arquivo: SHA-256} do ZIP de locais com que o mapa das zonas do ano foi gravado."""
        return dict((self.zonas.get(str(ano)) or {}).get("entradas") or {})

    def marcar_zonas(self, ano: int, entradas: dict[str, str], municipios: int) -> None:
        """Registra o mapa das zonas do ano como gravado e grava."""
        self.zonas[str(ano)] = {"concluido_em": _agora(), "entradas": entradas, "municipios": municipios,
                                "revisao": zonas.REVISAO_ZONAS, "contornos": zonas.assinatura_contornos()}
        self.gravar()

    def ao_vivo_pronto(self, eleicao_id: str) -> bool:
        """Se a coleta da eleição já terminou com a totalização concluída."""
        return eleicao_id in self.ao_vivo

    def marcar_ao_vivo(self, eleicao_id: str) -> None:
        """Registra a coleta da eleição como concluída e grava."""
        self.ao_vivo[eleicao_id] = {"concluido_em": _agora()}
        self.gravar()


# ---------------------------------------------------------------- portal

def portal_desatualizado(portal: Path = DIR_PORTAL) -> bool:
    """Se o portal precisa ser gerado: sem ``out/index.html`` ou com código mais novo que ele."""
    indice = portal / "out" / "index.html"
    if not indice.exists():
        return True
    gerado = indice.stat().st_mtime
    for nome in FONTES_DO_PORTAL:
        caminho = portal / nome
        if not caminho.exists():
            continue
        arquivos = caminho.rglob("*") if caminho.is_dir() else [caminho]
        if any(a.is_file() and a.stat().st_mtime > gerado for a in arquivos):
            return True
    return False


def construir_portal(portal: Path = DIR_PORTAL, *, executar: Callable = subprocess.run,
                     localizar: Callable[[str], str | None] = shutil.which) -> None:
    """Instala as dependências do portal (se faltam) e gera o site estático em ``out/``.

    Exige o Node.js com ``npm`` no PATH; levanta ``PortalIndisponivel`` se não houver ou se um passo falhar.
    """
    npm = localizar("npm")
    if not npm:
        raise PortalIndisponivel("Node.js não encontrado: instale o Node.js 20.9 ou mais novo (https://nodejs.org) "
                                 "e rode de novo")
    passos = ([[npm, "ci"]] if not (portal / "node_modules").exists() else []) + [[npm, "run", "build"]]
    for passo in passos:
        r = executar(passo, cwd=str(portal))
        if getattr(r, "returncode", 0) != 0:
            raise PortalIndisponivel(f"`{' '.join(passo[1:])}` em {portal} terminou com erro")


def dentro_de(caminho: Path, pasta: Path) -> bool:
    """Se ``caminho`` está dentro de ``pasta`` (os dois resolvidos)."""
    caminho, pasta = Path(caminho).resolve(), Path(pasta).resolve()
    return pasta == caminho or pasta in caminho.parents


# ---------------------------------------------------------------- sistema de resultados

def eleicoes_ao_vivo(eleicoes: list[Eleicao], hoje: date, processadas: Iterable[str] = (),
                     ) -> tuple[list[Eleicao], list[Eleicao]]:
    """Separa as eleições do sistema de resultados em (coletar agora, ainda por acontecer).

    Entram as ordinárias (geral e municipal) que os dados abertos ainda não trazem; as que já trazem são
    processadas pelos arquivos completos. Nos anos fechados vale o ano; no ano em aberto
    (``da.ANO_EM_ABERTO``), a eleição: o 1º turno de 2026 sai dos dados abertos depois de processado
    (``processadas``, os ids que o processamento gravou), e o 2º turno continua ao vivo. Eleição com data
    futura fica para a noite da apuração.
    """
    nos_dados_abertos = set(da.ANOS_GERAIS) | set(da.ANOS_MUNICIPAIS)
    feitas = set(processadas)

    def nos_arquivos(e: Eleicao) -> bool:
        if e.ano == da.ANO_EM_ABERTO:
            return e.id in feitas
        return e.ano in nos_dados_abertos

    candidatas = [e for e in eleicoes if e.tipo in TIPOS_AO_VIVO and not nos_arquivos(e)]
    agora = [e for e in candidatas if e.data is None or e.data <= hoje]
    futuras = [e for e in candidatas if e.data is not None and e.data > hoje]
    return agora, futuras


# ---------------------------------------------------------------- execução

@dataclass
class OpcoesPreparacao:
    """O que ``preparar`` deve fazer; os padrões fazem tudo."""

    anos: list[int] | None = None          # anos dos dados abertos; None = todos
    ao_vivo: bool = True
    historico: bool = True
    zonas: bool = True
    portal: bool = True
    servir: bool = False
    abrir_navegador: bool = True
    host: str = "127.0.0.1"
    porta: int = 8080
    refazer: bool = False
    atualizar: bool = False
    municipios_proporcionais: bool = False
    limite_municipio: int = 50
    base: str = tse.BASE
    bronze: bool = True
    limite_minutos: float | None = None   # para sozinha depois disso (máquina com prazo, como o GitHub Actions)
    apagar_arquivos: bool = False         # apaga os ZIPs de cada ano depois de processado (disco pequeno)


@dataclass
class ResumoPreparacao:
    """O que aconteceu, etapa por etapa, para o resumo impresso no fim."""

    referencias: int = 0
    portal: str = "não gerado"
    endereco: str | None = None
    ao_vivo: list[dict] = field(default_factory=list)
    zonas: list[dict] = field(default_factory=list)
    anos: list[dict] = field(default_factory=list)
    erros: list[str] = field(default_factory=list)
    publicados: int = 0
    prazo_atingido: bool = False

    def para_json(self) -> dict:
        """Dicionário para imprimir em JSON."""
        return {"referencias_instaladas": self.referencias, "portal": self.portal, "endereco": self.endereco,
                "ao_vivo": self.ao_vivo, "zonas": self.zonas, "anos": self.anos, "erros": self.erros,
                "publicados_na_nuvem": self.publicados, "prazo_atingido": self.prazo_atingido}


class Preparacao:
    """Executa as etapas de ``preparar`` na ordem do módulo, registrando o andamento.

    Os clientes HTTP, o construtor do portal, o navegador, a espera e a data de hoje são injetáveis (testes).
    """

    def __init__(self, cfg: ConfiguracaoEleicoes, opcoes: OpcoesPreparacao, *,
                 cliente_resultados: ClienteHttp | None = None, cliente_dados: ClienteHttp | None = None,
                 parar: Callable[[], bool] = lambda: False, saida: Callable[[str], None] | None = None,
                 construir: Callable[[], None] | None = None, abrir: Callable[[str], object] = webbrowser.open,
                 hoje: date | None = None, portal: Path = DIR_PORTAL,
                 dormir: Callable[[float], None] = time.sleep, nuvem=None,
                 relogio: Callable[[], float] = time.monotonic):
        """Guarda configuração, opções e dependências; nada é feito até ``executar``.

        ``nuvem`` (``publicacao.Nuvem``) liga a restauração e a publicação; ``relogio`` mede o prazo de
        ``limite_minutos``.
        """
        self.cfg = cfg
        self.op = opcoes
        self.nuvem = nuvem
        self.relogio = relogio
        self._fim = relogio() + opcoes.limite_minutos * 60 if opcoes.limite_minutos else None
        self.cliente_resultados = cliente_resultados or ClienteHttp(FONTE_ID, user_agent=cfg.user_agent,
                                                                    rpm=cfg.rpm_resultados)
        self.cliente_dados = cliente_dados or ClienteHttp(carga.FONTE_DADOS_ABERTOS, user_agent=cfg.user_agent,
                                                          rpm=cfg.rpm_dados_abertos)
        self._parar_pedido = parar
        self.saida = saida or (lambda msg: print(msg, flush=True))
        self.portal = portal
        self.construir = construir or (lambda: construir_portal(self.portal))
        self.abrir = abrir
        self.hoje = hoje or date.today()
        self.dormir = dormir
        self.estado = EstadoPreparacao.carregar(cfg.estado / ARQUIVO_ESTADO)
        self.bronze: ArmazemBronze | None = ArmazemBronzeLocal(cfg.bronze) if opcoes.bronze else None
        self.escritor = EscritorFeeds(cfg.saida)
        self.resumo = ResumoPreparacao()
        self.servidor = None
        self._cadastro: CadastroMunicipios | None = None

    # ------------------------------------------------------------ apoio

    def parar(self) -> bool:
        """Se é hora de parar: Ctrl+C (ou sinal) ou o prazo de ``limite_minutos`` vencido."""
        if self._parar_pedido():
            return True
        if self._fim is not None and self.relogio() >= self._fim:
            if not self.resumo.prazo_atingido:
                self.resumo.prazo_atingido = True
                self.saida("prazo atingido: a carga para aqui, e a próxima execução continua de onde parou")
            return True
        return False

    def prazo_da_publicacao(self) -> bool:
        """Se a publicação deve parar: ``FOLGA_PUBLICACAO`` depois do prazo da carga, para a máquina não ser
        derrubada no meio de um envio (o que faltar sobe na execução seguinte)."""
        return self._fim is not None and self.relogio() >= self._fim + FOLGA_PUBLICACAO

    def sincronizar(self) -> None:
        """Na nuvem, publica o que mudou e guarda o estado; falha vira erro do resumo, sem derrubar a carga."""
        if self.nuvem is None:
            return
        try:
            r = self.nuvem.sincronizar(self.prazo_da_publicacao)
        except Exception as erro:  # noqa: BLE001 - a próxima sincronização tenta de novo
            self.resumo.erros.append(f"publicação na nuvem: {erro}")
            self.saida(f"erro ao publicar na nuvem: {erro}")
            return
        self.resumo.publicados += r.enviados
        if r.pendentes:
            self.resumo.prazo_atingido = True
            self.saida(f"prazo atingido na publicação: {r.pendentes} arquivo(s) sobem na próxima execução")

    def _etapa(self, titulo: str) -> None:
        """Título de etapa no andamento."""
        self.saida(f"\n== {titulo}")

    def cadastro(self) -> CadastroMunicipios:
        """Cadastro de municípios do diretório dos feeds (instalado na etapa 1), carregado uma vez."""
        if self._cadastro is None:
            caminho = self.cfg.saida / referencias.ARQUIVO_CADASTRO
            self._cadastro = (CadastroMunicipios.carregar(caminho) if caminho.exists()
                              else referencias.cadastro_embutido())
        return self._cadastro

    def anos_historicos(self) -> tuple[list[int], list[int]]:
        """Anos a carregar: (1933 a 1990, em ordem cronológica — são poucos e rápidos; 1994 em diante, do mais
        recente ao mais antigo, para as eleições mais procuradas ficarem prontas primeiro)."""
        anos = self.op.anos or carga.anos_disponiveis()
        antigos = sorted(a for a in anos if a in antigas.ANOS_ANTIGOS)
        recentes = sorted((a for a in anos if a not in antigas.ANOS_ANTIGOS), reverse=True)
        return antigos, recentes

    # ------------------------------------------------------------ etapas

    def instalar_referencias(self) -> None:
        """Etapa 1: mapa e cadastro no diretório dos feeds."""
        self._etapa("Mapa e cadastro de municípios")
        copiados = referencias.instalar(self.cfg.saida)
        self.resumo.referencias = len(copiados)
        self.saida(f"{len(copiados)} arquivo(s) instalado(s) em {self.cfg.saida}" if copiados
                   else "já instalados")

    def preparar_portal(self) -> None:
        """Etapa 2: gera o portal se preciso. Falha aqui não impede a carga dos dados."""
        self._etapa("Portal")
        if dentro_de(self.cfg.saida, self.portal / "public"):
            self.saida(f"aviso: os feeds estão em {self.cfg.saida}, dentro do portal; cada geração do portal "
                       "copia todos eles. Defina [eleicoes] saida = \"dados/eleicoes/feeds\" no lumen.toml.")
        if not portal_desatualizado(self.portal):
            self.resumo.portal = "atualizado"
            self.saida("já gerado e atualizado")
            return
        try:
            self.construir()
        except PortalIndisponivel as erro:
            self.resumo.portal = "falhou"
            self.resumo.erros.append(f"portal: {erro}")
            self.saida(f"erro: {erro}")
            return
        self.resumo.portal = "gerado"

    def iniciar_servidor(self) -> None:
        """Etapa 3: sobe o servidor numa thread e abre o navegador. Porta ocupada: o sistema escolhe outra."""
        from .servidor import ServidorPortal
        site = self.portal / "out"
        if not (site / "index.html").exists():
            self.saida("aviso: sem o portal gerado não há o que servir; os dados serão carregados mesmo assim")
            return
        try:
            srv = ServidorPortal(site, self.cfg.saida, host=self.op.host, porta=self.op.porta)
        except OSError:
            srv = ServidorPortal(site, self.cfg.saida, host=self.op.host, porta=0)
        self.servidor = srv.iniciar()
        self.resumo.endereco = f"{srv.endereco}/eleicoes/"
        self.saida(f"\nportal em {self.resumo.endereco} (as eleições aparecem conforme ficam prontas)")
        if self.op.abrir_navegador:
            self.abrir(self.resumo.endereco)

    def coletar_ao_vivo(self) -> None:
        """Etapa 4: eleições do sistema de resultados ainda fora dos dados abertos."""
        self._etapa("Sistema de resultados do TSE")
        try:
            art = self.cliente_resultados.obter(tse.url_catalogo(self.op.base))
            if art.status_http != 200:
                raise RuntimeError(f"HTTP {art.status_http}")
            catalogo = tse.ler_catalogo(art.conteudo)
        except Exception as erro:  # noqa: BLE001 - sem o catálogo, as outras etapas seguem
            self.resumo.erros.append(f"catálogo do sistema de resultados: {erro}")
            self.saida(f"erro: catálogo do sistema de resultados: {erro}")
            return
        processadas = {eid for registro in self.estado.anos.values() for eid in registro.get("eleicoes") or ()}
        agora, futuras = eleicoes_ao_vivo(catalogo, self.hoje, processadas)
        for e in futuras:
            self.saida(f"{e.id}: em {e.data:%d/%m/%Y}; na noite da apuração rode "
                       f"`lumen eleicoes ao-vivo --eleicao {e.id}`")
        for e in agora:
            if self.parar():
                return
            if self.estado.ao_vivo_pronto(e.id) and not (self.op.refazer or self.op.atualizar):
                self.saida(f"{e.id}: já coletada")
                self.resumo.ao_vivo.append({"eleicao": e.id, "situacao": "já coletada"})
                continue
            self.resumo.ao_vivo.append(self._coletar(e))

    def _coletar(self, e: Eleicao) -> dict:
        """Coleta uma eleição e devolve o resumo dela.

        Para quando a totalização terminou e a fila de municípios esvaziou; ou, se a apuração ainda não
        terminou, quando uma passada não traz nada novo (``preparar`` tira uma fotografia; acompanhar a
        apuração é o trabalho de ``lumen eleicoes ao-vivo``); ou em ``MAX_PASSADAS``.
        """
        self.saida(f"{e.id}: {e.nome}")
        plano = plano_padrao(e, municipios_proporcionais=self.op.municipios_proporcionais,
                             orcamento_municipal=ORCAMENTO_MUNICIPAL)
        coletor = ColetorAoVivo(self.cliente_resultados, self.escritor, plano, cadastro=self.cadastro(),
                                bronze=self.bronze, base=self.op.base,
                                estado=self.cfg.estado / f"coleta-{e.id}.json")
        ultimo: list[ResumoPassada] = []

        def aviso(r: ResumoPassada) -> None:
            ultimo[:] = [r]
            self.saida(f"   passada {coletor.passadas:>3}  baixados {r.baixados:>5}  feeds {r.feeds:>5}  "
                       f"municípios na fila {r.pendentes_municipais:>5}  erros {len(r.erros)}")
            for erro in r.erros[:3]:
                self.saida(f"      {erro}")
            if r.feeds:
                self.sincronizar()

        def basta() -> bool:
            r = ultimo[0] if ultimo else None
            sem_novidade = bool(r and coletor.passadas >= 2 and r.baixados == 0 and r.pendentes_municipais == 0)
            return self.parar() or sem_novidade
        try:
            coletor.executar(intervalo_s=5, max_passadas=MAX_PASSADAS, parar=basta, dormir=self.dormir,
                             aviso=aviso)
        except Exception as erro:  # noqa: BLE001 - uma eleição com erro não derruba as outras etapas
            self.resumo.erros.append(f"{e.id}: {erro}")
            return {"eleicao": e.id, "situacao": "erro"}
        r = ultimo[0] if ultimo else None
        concluida = bool(r and r.finalizada and r.pendentes_municipais == 0)
        if concluida:
            self.estado.marcar_ao_vivo(e.id)
        else:
            self.saida(f"{e.id}: a totalização ainda não terminou; para acompanhar, rode "
                       f"`lumen eleicoes ao-vivo --eleicao {e.id}`")
        return {"eleicao": e.id, "situacao": "concluída" if concluida else "em andamento",
                "passadas": coletor.passadas}

    def anos_das_zonas(self) -> list[int]:
        """Anos com locais de votação (2026 a 2018), limitados aos de ``anos`` quando a opção é dada."""
        return [a for a in zonas.ANOS_LOCAIS if not self.op.anos or a in self.op.anos]

    def carregar_zonas(self, ano: int) -> None:
        """Etapa 5, um ano: baixa os locais de votação, confere se mudaram e grava o mapa das zonas.

        O ano em aberto é sempre conferido na fonte (o eleitorado do 2º turno muda o arquivo).
        """
        atualizar = self.op.atualizar or ano == da.ANO_EM_ABERTO
        if self.estado.zonas_prontas(ano) and not (self.op.refazer or atualizar):
            self.saida(f"{ano}: zonas já gravadas")
            self.resumo.zonas.append({"ano": ano, "situacao": "já gravadas"})
            return
        try:
            caminho, manifesto = zonas.baixar_locais(self.cfg, ano, bronze=self.bronze,
                                                     atualizar=atualizar, saida=self.saida)
            entradas = {manifesto.arquivo: manifesto.sha256}
            if (self.estado.zonas_prontas(ano) and not self.op.refazer
                    and entradas == self.estado.entradas_das_zonas(ano)):
                self.saida(f"{ano}: locais de votação iguais aos já usados")
                self.resumo.zonas.append({"ano": ano, "situacao": "sem mudança na fonte"})
                return
            r = zonas.gravar_zonas(ano, caminho, self.cfg.saida, self.cadastro(), manifesto=manifesto,
                                   progresso=self.saida)
        except Exception as erro:  # noqa: BLE001 - um ano sem zonas não impede os outros nem os resultados
            self.resumo.erros.append(f"zonas {ano}: {erro}")
            self.resumo.zonas.append({"ano": ano, "situacao": "erro"})
            self.saida(f"erro nas zonas de {ano}: {erro}")
            return
        self.estado.marcar_zonas(ano, entradas, r.municipios)
        self.resumo.zonas.append({"ano": ano, "situacao": "gravadas", "municipios": r.municipios,
                                  "locais": r.locais})
        if self.op.apagar_arquivos:
            caminho.unlink(missing_ok=True)
        self.sincronizar()

    def carregar_ano(self, ano: int) -> None:
        """Etapas 6 e 7, um ano: baixa, confere se mudou, processa e registra. Erro vira item do resumo.

        O ano em aberto (``da.ANO_EM_ABERTO``) é sempre conferido na fonte, como com ``--atualizar``: o TSE
        acrescenta o 2º turno ao mesmo arquivo depois da eleição.
        """
        atualizar = self.op.atualizar or ano == da.ANO_EM_ABERTO
        if self.estado.ano_pronto(ano) and not (self.op.refazer or atualizar):
            self.saida(f"{ano}: já processado")
            self.resumo.anos.append({"ano": ano, "situacao": "já processado"})
            return
        try:
            manifestos = carga.baixar_ano(self.cfg, self.cliente_dados, ano, bronze=self.bronze,
                                          atualizar=atualizar, saida=self.saida, aviso=self.saida)
            entradas = {m.arquivo: m.sha256 for m in manifestos}
            if (self.estado.ano_pronto(ano) and not self.op.refazer
                    and entradas == self.estado.entradas_do_ano(ano)):
                self.saida(f"{ano}: arquivos iguais aos já processados")
                self.resumo.anos.append({"ano": ano, "situacao": "sem mudança na fonte"})
                return
            r = carga.processar_ano(self.cfg, ano, escritor=self.escritor, cadastro=self.cadastro(),
                                    limite_municipio=self.op.limite_municipio, progresso=self.saida)
        except Exception as erro:  # noqa: BLE001 - um ano com erro não impede os outros
            self.resumo.erros.append(f"{ano}: {erro}")
            self.resumo.anos.append({"ano": ano, "situacao": "erro"})
            self.saida(f"erro em {ano}: {erro}")
            return
        self.estado.marcar_ano(ano, entradas, r.eleicoes)
        self.resumo.anos.append({"ano": ano, "situacao": "processado", "eleicoes": r.eleicoes,
                                 "feeds": r.arquivos})
        self.saida(f"{ano}: {len(r.eleicoes)} eleição(ões), {r.arquivos} feed(s)")
        if self.op.apagar_arquivos:
            shutil.rmtree(self.cfg.arquivos / str(ano), ignore_errors=True)
        self.sincronizar()

    # ------------------------------------------------------------ tudo

    def executar(self) -> ResumoPreparacao:
        """Roda as etapas pedidas nas opções, na ordem do módulo, e devolve o resumo.

        Na nuvem, restaura antes de começar e sincroniza no fim (além de depois de cada etapa).
        """
        if self.nuvem is not None:
            self._etapa("Nuvem: índice publicado e estado da carga")
            try:
                self.nuvem.restaurar()
            except Exception as erro:  # noqa: BLE001 - sem restaurar, a carga refaria tudo e sobrescreveria o índice
                self.resumo.erros.append(f"restauração da nuvem: {erro}")
                self.saida(f"erro ao restaurar da nuvem: {erro}; a carga não continua")
                return self.resumo
            # O estado restaurado substitui o que foi lido ao criar a preparação
            self.estado = EstadoPreparacao.carregar(self.cfg.estado / ARQUIVO_ESTADO)
        self._executar_etapas()
        self.sincronizar()
        return self.resumo

    def _executar_etapas(self) -> None:
        """As etapas de ``executar``, sem a restauração e a sincronização final da nuvem."""
        self.instalar_referencias()
        if self.op.portal:
            self.preparar_portal()
        if self.op.servir:
            self.iniciar_servidor()
        if self.op.ao_vivo and not self.parar():
            self.coletar_ao_vivo()
        # Os locais de votação também são dados abertos: sem o histórico, ficam de fora
        anos_zonas = self.anos_das_zonas() if self.op.historico and self.op.zonas else []
        if anos_zonas and not self.parar():
            self._etapa("Zonas eleitorais: locais de votação de 2018 em diante")
            for ano in anos_zonas:
                if self.parar():
                    break
                self.carregar_zonas(ano)
        if self.op.historico:
            antigos, recentes = self.anos_historicos()
            for titulo, anos in (("Eleições de 1933 a 1990 (resultados por UF)", antigos),
                                 ("Eleições de 1994 em diante (todos os municípios)", recentes)):
                if anos and not self.parar():
                    self._etapa(titulo)
                for ano in anos:
                    if self.parar():
                        break
                    self.carregar_ano(ano)

    def aguardar(self) -> None:
        """Com o servidor no ar, segue servindo até ``parar()``; depois o encerra."""
        if self.servidor is None:
            return
        self.saida(f"\npronto: {self.resumo.endereco}  (Ctrl+C para encerrar)")
        try:
            while not self.parar():
                self.dormir(0.5)
        finally:
            self.servidor.parar()

