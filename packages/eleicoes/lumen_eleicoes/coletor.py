"""Coleta ao vivo do sistema de divulgação de resultados do TSE.

Na noite da apuração, o portal mostra números que mudam a cada minuto. O
coletor é quem os busca — um só, identificado e com limite de taxa (P6) —,
guarda cada resposta na camada bronze e regrava os feeds que mudaram. O
portal só lê os feeds.

Uma passada:

1. **Andamento.** Lê o ``-ab`` do Brasil (situação de cada UF) e, das UFs que
   avançaram, o ``-ab`` da UF (situação de cada município). Toda leitura é
   condicional (``If-Modified-Since``): o que não mudou volta 304, sem corpo.
2. **Resultados de topo.** Brasil e UFs que avançaram, para cada cargo.
3. **Municípios.** Os que avançaram entram numa fila; a cada passada saem
   até ``orcamento_municipal`` deles, os nunca baixados primeiro. Assim o
   Brasil e as UFs nunca esperam pelos 5.570 municípios.
4. **Feeds.** Município, UF (com os municípios em ``partes``), Brasil (com
   as UFs), a evolução da totalização (um ponto a cada avanço) e o índice.
   Só é regravado o que mudou.

As cores dos candidatos são atribuídas no nível mais alto do cargo e ficam
fixas durante a noite (``feeds.atribuir_cores``). O que precisa sobreviver a
um reinício (cores, evolução, ``partes`` e fotos baixadas) fica em
``<estado>``; o resto é refeito na primeira passada, que baixa tudo.
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from lumen_ingestao.bronze import ArmazemBronze
from lumen_ingestao.cliente_http import ClienteHttp
from lumen_ingestao.coleta_http import ErroColeta

from . import tse
from .feeds import (
    Abrangencia,
    EscritorFeeds,
    abrangencia_brasil,
    abrangencia_municipio,
    abrangencia_uf,
    atribuir_cores,
    entrada_indice,
    feed_historico,
    feed_panorama,
    feed_resultado,
    origem_json,
    panorama_nacional,
    parte_json,
    proporcional,
    ranking_partidos,
    recolorir,
)
from .modelo import AndamentoAbrangencia, Cargo, Eleicao, Nivel, ResultadoAbrangencia
from .municipios import CadastroMunicipios, Municipio, nome_legivel

log = logging.getLogger("lumen.eleicoes.coletor")

FONTE_ID = "tse_resultados"
RPM_PADRAO = 300
MAX_PONTOS_EVOLUCAO = 2000
LIMITE_CANDIDATOS_MUNICIPIO = 50


@dataclass
class PlanoColeta:
    """O que coletar de uma eleição: cargos, UFs, os cargos que descem ao município e os que têm foto.

    ``orcamento_municipal`` limita os arquivos de município baixados por passada; ``simulacao`` marca
    os feeds gerados contra o servidor simulado. Montado por ``plano_padrao``.
    """

    eleicao: Eleicao
    cargos: list[Cargo]
    ufs: list[str]
    municipios_para: set[int]               # códigos de cargo coletados por município
    fotos_para: set[int]                    # códigos de cargo com foto dos candidatos
    orcamento_municipal: int = 600
    simulacao: bool = False

    def grupos(self) -> dict[int, list[Cargo]]:
        """Cargos agrupados pela "eleição" do TSE que os contém (um andamento cada)."""
        saida: dict[int, list[Cargo]] = {}
        for c in self.cargos:
            saida.setdefault(c.eleicao_tse, []).append(c)
        return saida


def plano_padrao(eleicao: Eleicao, *, cargos: Iterable[str] | None = None, ufs: Iterable[str] | None = None,
                 municipios_proporcionais: bool = False, fotos_municipais: bool = False,
                 orcamento_municipal: int = 600, simulacao: bool = False) -> PlanoColeta:
    """Plano razoável para a noite da eleição.

    - Todos os cargos da eleição, ou só os pedidos.
    - Por município: cargos majoritários sempre; proporcionais estaduais só
      se pedido (um arquivo por município por cargo, com centenas de
      candidatos). Vereador é sempre por município: não existe outro nível.
    - Fotos: dos cargos majoritários nacionais e estaduais; as dos
      municipais só se pedido (dezenas de milhares de imagens).
    """
    pedidos = set(cargos) if cargos is not None else None
    escolhidos = [c for c in eleicao.cargos if pedidos is None or c.slug in pedidos]
    if not escolhidos:
        raise ValueError(f"nenhum dos cargos pedidos existe em {eleicao.id}")
    if ufs:
        lista_ufs = [u.lower() for u in ufs]
    elif eleicao.tipo == "geral":
        lista_ufs = list(tse.UFS_TSE) + [tse.UF_EXTERIOR]
    else:
        lista_ufs = list(eleicao.abrangencias) or [u for u in tse.UFS_TSE if u != "df"]
    municipais = {c.codigo for c in escolhidos
                  if not proporcional(c) or municipios_proporcionais or c.nivel is Nivel.MUNICIPIO}
    fotos = {c.codigo for c in escolhidos if not proporcional(c)
             and (fotos_municipais or c.nivel is not Nivel.MUNICIPIO)}
    return PlanoColeta(eleicao=eleicao, cargos=escolhidos, ufs=lista_ufs, municipios_para=municipais,
                       fotos_para=fotos, orcamento_municipal=orcamento_municipal, simulacao=simulacao)


@dataclass
class ResumoPassada:
    """Contagens de uma passada do coletor, para o acompanhamento na linha de comando.

    ``nao_modificados`` são as respostas 304 e ``ausentes``, as 404; ``pendentes_municipais`` é o que
    ficou na fila para as próximas passadas e ``finalizada`` diz se a totalização terminou.
    """

    requisicoes: int = 0
    baixados: int = 0
    nao_modificados: int = 0
    ausentes: int = 0
    feeds: int = 0
    fotos: int = 0
    pendentes_municipais: int = 0
    erros: list[str] = field(default_factory=list)
    finalizada: bool = False


class EstadoColeta:
    """O que precisa sobreviver a um reinício do coletor."""

    def __init__(self, caminho: Path | None):
        """Carrega o estado gravado em ``caminho``, se existir; sem caminho, o estado fica só na memória."""
        self.caminho = caminho
        self.cores: dict[str, dict[str, int]] = {}
        self.partes: dict[str, dict[str, dict]] = {}
        self.evolucao: dict[str, list[dict]] = {}
        self.fotos: set[str] = set()
        if caminho and caminho.exists():
            dados = json.loads(caminho.read_text(encoding="utf-8"))
            self.cores = dados.get("cores", {})
            self.partes = dados.get("partes", {})
            self.evolucao = dados.get("evolucao", {})
            self.fotos = set(dados.get("fotos", []))

    def gravar(self) -> None:
        """Grava o estado em JSON de forma atômica (arquivo temporário e ``os.replace``); sem caminho, nada faz."""
        if not self.caminho:
            return
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.caminho.with_name(self.caminho.name + ".tmp")
        tmp.write_text(json.dumps({"cores": self.cores, "partes": self.partes, "evolucao": self.evolucao,
                                   "fotos": sorted(self.fotos)}, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.caminho)


def _partidos(r: ResultadoAbrangencia) -> dict[str, str | None]:
    """Partido de cada candidato, pelo número: dá a cor fixa de PL e PT (ADR-052)."""
    return {c.numero: c.partido for c in r.candidatos}


def _topo(cargo: Cargo, abr: Abrangencia) -> bool:
    """A abrangência é o nível mais alto em que o cargo é disputado?"""
    return {"br": Nivel.BRASIL, "uf": Nivel.UF, "mu": Nivel.MUNICIPIO}[abr.tipo] is cargo.nivel


class ColetorAoVivo:
    """Coletor da noite da apuração: passadas sobre o sistema de resultados que regravam o que mudou.

    Entre passadas guarda o ``Last-Modified`` de cada URL (para as leituras condicionais), o último
    andamento lido, o último resultado de cada cargo e abrangência (``ultimo``) e a fila de municípios.
    Dentro da passada, ``sujos`` marca os feeds de UF e Brasil a regravar no fim.
    """

    def __init__(self, cliente: ClienteHttp, escritor: EscritorFeeds, plano: PlanoColeta, *,
                 cadastro: CadastroMunicipios | None = None, bronze: ArmazemBronze | None = None,
                 base: str = tse.BASE, estado: Path | None = None):
        """Prepara o coletor; ``estado`` é o arquivo que preserva cores, evolução, ``partes`` e fotos."""
        self.cliente = cliente
        self.escritor = escritor
        self.plano = plano
        self.e = plano.eleicao
        self.cadastro = cadastro or CadastroMunicipios()
        self.bronze = bronze
        self.base = base.rstrip("/")
        self.estado = EstadoColeta(estado)
        self.modificado: dict[str, str] = {}
        self.andamento: dict[str, dict[str, AndamentoAbrangencia]] = {}
        self.ultimo: dict[str, tuple[ResultadoAbrangencia, dict]] = {}
        self.municipios_da_eleicao: dict[int, dict[str, list[str]]] = {}
        self.fila: deque[tuple[int, str, str]] = deque()
        self.na_fila: set[tuple[int, str, str]] = set()
        self.baixados_alguma_vez: set[tuple[int, str, str]] = set()
        self.sujos: set[str] = set()
        self.passadas = 0
        self.pendentes_ao_parar: list[str] = []      # resultados sem a marca de finalizada na parada por estabilidade
        self._resumo = ResumoPassada()

    # ------------------------------------------------------------ rede

    def _obter(self, url: str, *, condicional: bool = True) -> tuple[bytes, dict] | None:
        """GET de uma URL do sistema de resultados; devolve o conteúdo e o bloco ``origem`` do feed.

        Com ``condicional``, manda ``If-Modified-Since`` com o ``Last-Modified`` da última resposta à mesma
        URL. Devolve ``None`` em 304 (nada mudou), 404 e falha, cada caso contado no resumo da passada. A
        resposta 200 vai para o bronze, quando há um, e o registro entra na ``origem``.
        """
        r = self._resumo
        cab = {}
        if condicional and url in self.modificado:
            cab["If-Modified-Since"] = self.modificado[url]
        r.requisicoes += 1
        try:
            art = self.cliente.obter(url, cab)
        except ErroColeta as erro:
            r.erros.append(f"{url}: {erro}")
            return None
        if art.status_http == 304:
            r.nao_modificados += 1
            return None
        if art.status_http == 404:
            r.ausentes += 1
            return None
        if art.status_http != 200:
            r.erros.append(f"{url}: HTTP {art.status_http}")
            return None
        r.baixados += 1
        registro = self.bronze.guardar(art) if self.bronze else None
        cab_resp = {k.lower(): v for k, v in art.cabecalhos.items()}
        if cab_resp.get("last-modified"):
            self.modificado[url] = cab_resp["last-modified"]
        origem = origem_json("resultados", url=url, sha256=art.sha256, coletado_em=art.coletado_em,
                             registro_bronze=registro.registro_id if registro else None)
        if self.plano.simulacao:
            origem["simulacao"] = True
        return art.conteudo, origem

    # ------------------------------------------------------------ preparação

    def preparar(self) -> None:
        """Lê o cadastro de municípios de cada "eleição" do TSE no plano."""
        for ele in self.plano.grupos():
            obtido = self._obter(tse.url_municipios(self.e.ciclo, ele, self.base), condicional=False)
            if obtido is None:
                continue
            por_uf: dict[str, list[str]] = {}
            for m in tse.ler_municipios(obtido[0]):
                por_uf.setdefault(m.uf, []).append(m.codigo_tse)
                if self.cadastro.por_tse(m.uf, m.codigo_tse) is None:
                    self.cadastro.adicionar(Municipio(uf=m.uf, tse=m.codigo_tse.zfill(5), ibge=m.codigo_ibge,
                                                      nome=nome_legivel(m.nome), nome_tse=m.nome,
                                                      capital=m.capital))
            self.municipios_da_eleicao[ele] = por_uf

    # ------------------------------------------------------------ passada

    def passada(self) -> ResumoPassada:
        """Uma passada completa: andamento, resultados de topo, fila de municípios, agregados e índice.

        Só as UFs cujo andamento mudou são baixadas, e só os municípios que avançaram entram na fila. A
        primeira passada lê antes o cadastro de municípios (``preparar``). Ao fim, grava o estado e
        devolve o resumo.
        """
        self._resumo = ResumoPassada()
        if self.passadas == 0 and not self.municipios_da_eleicao:
            self.preparar()
        for ele, cargos in self.plano.grupos().items():
            ufs_mudaram = self._andamento_brasil(ele)
            for uf in self.plano.ufs:
                if uf not in ufs_mudaram:
                    continue
                mudaram = self._andamento_uf(ele, uf)
                for cargo in cargos:
                    if cargo.codigo in self.plano.municipios_para:
                        self._enfileirar(cargo.codigo, uf, mudaram)
            for cargo in cargos:
                self._coletar_topo(cargo, ufs_mudaram)
        self._coletar_municipios()
        for cargo in self.plano.cargos:
            self._regravar_agregados(cargo)
        self.sujos.clear()
        self._resumo.pendentes_municipais = len(self.fila)
        self._resumo.finalizada = self._finalizada()
        self._atualizar_indice(ao_vivo=not self._resumo.finalizada)
        self.estado.gravar()
        self.passadas += 1
        return self._resumo

    def executar(self, *, intervalo_s: float = 30, max_passadas: int | None = None,
                 parar: Callable[[], bool] = lambda: False, dormir: Callable[[float], None] = time.sleep,
                 aviso: Callable[[ResumoPassada], None] | None = None, estavel_s: float | None = 3600,
                 relogio: Callable[[], float] = time.monotonic) -> None:
        """Passadas até a totalização terminar, ``parar()`` responder sim ou ``max_passadas``.

        Também para quando todas as seções estão totalizadas e nada muda há ``estavel_s`` segundos, mesmo sem
        a marca de finalizada do TSE: em 2026, os deputados de Rondônia ficaram com 100% das seções e
        sem ``tf = "s"``, e o coletor rodaria até o prazo da máquina. Os resultados ainda sem a marca ficam em
        ``pendentes_ao_parar``. ``estavel_s=None`` desliga essa parada.
        """
        self.pendentes_ao_parar = []
        ultima_mudanca = relogio()
        try:
            while not parar():
                resumo = self.passada()
                if resumo.baixados or resumo.feeds:
                    ultima_mudanca = relogio()
                if aviso:
                    aviso(resumo)
                if max_passadas is not None and self.passadas >= max_passadas:
                    break
                if resumo.finalizada and not self.fila:
                    break
                if estavel_s is not None and self.secoes_completas() and relogio() - ultima_mudanca >= estavel_s:
                    self.pendentes_ao_parar = self.sem_marca_de_finalizada()
                    break
                # Com fila de municípios, a próxima passada vem logo.
                dormir(intervalo_s if not self.fila else min(intervalo_s, 5))
        finally:
            # Coletor parado: o feed deixa de ser "ao vivo", mesmo que a apuração continue.
            self._atualizar_indice(ao_vivo=False)
            self.estado.gravar()

    # ------------------------------------------------------------ andamento

    def _andamento_brasil(self, ele: int) -> set[str]:
        """Lê o ``-ab`` do Brasil e devolve as UFs do plano cujo andamento mudou desde a última leitura.

        Sem leitura anterior, devolve todas. Enquanto o andamento nacional não for lido (404 ou falha),
        também todas: cada UF é consultada a cada passada. Depois de lido, 304 ou falha devolvem vazio.
        """
        chave = f"{ele}/br"
        obtido = self._obter(tse.url_andamento(self.e.ciclo, ele, "br", self.base))
        if obtido is None:
            # 304: nada mudou. 404 (eleição sem andamento nacional) ou falha:
            # na primeira passada vale tudo; depois, cada UF é consultada.
            if chave in self.andamento:
                return set()
            return set(self.plano.ufs)
        atual = tse.ler_andamento(obtido[0])
        anterior = list(self.andamento.get(chave, {}).values())
        self.andamento[chave] = {a.codigo: a for a in atual}
        if not anterior:
            return set(self.plano.ufs)
        return set(tse.mudaram(anterior, atual)) & set(self.plano.ufs)

    def _andamento_uf(self, ele: int, uf: str) -> list[str]:
        """Lê o ``-ab`` da UF e devolve os códigos TSE dos municípios cujo andamento mudou.

        Se a UF não publica andamento, a primeira passada devolve todos os municípios da eleição na UF
        (do cadastro lido em ``preparar``); as seguintes, nenhum.
        """
        chave = f"{ele}/{uf}"
        obtido = self._obter(tse.url_andamento(self.e.ciclo, ele, uf, self.base))
        if obtido is None:
            if chave not in self.andamento and self.passadas == 0:
                # Sem andamento publicado: todos os municípios da eleição na UF
                return list(self.municipios_da_eleicao.get(ele, {}).get(uf, []))
            return []
        atual = [a for a in tse.ler_andamento(obtido[0]) if a.tipo == "mun"]
        anterior = list(self.andamento.get(chave, {}).values())
        self.andamento[chave] = {a.codigo: a for a in atual}
        return tse.mudaram(anterior, atual)

    def _enfileirar(self, cargo: int, uf: str, municipios: Iterable[str]) -> None:
        """Põe na fila os municípios do cargo e da UF que ainda não estão nela (``na_fila`` evita duplicata)."""
        for m in municipios:
            item = (cargo, uf, m)
            if item not in self.na_fila:
                self.fila.append(item)
                self.na_fila.add(item)

    # ------------------------------------------------------------ resultados

    def _chave_cores(self, cargo: Cargo, abr: Abrangencia) -> str:
        """Chave das cores no estado: o nível mais alto do cargo (Brasil, UF ou o próprio município).

        Compartilhar a chave entre os níveis é o que dá ao candidato a mesma cor em todos os mapas.
        """
        if cargo.nivel is Nivel.BRASIL:
            return f"{cargo.codigo}/br"
        if cargo.nivel is Nivel.UF:
            return f"{cargo.codigo}/uf-{abr.uf}"
        return f"{cargo.codigo}/{abr.arquivo}"

    def _ordem(self, cargo: Cargo, r: ResultadoAbrangencia) -> list[str]:
        """Ordem de votação usada nas cores: partidos nos cargos proporcionais, candidatos válidos nos demais."""
        if proporcional(cargo):
            return [p for p, _ in ranking_partidos(r)]
        return [c.numero for c in r.candidatos if c.valido]

    def _dir_fotos(self, cargo: Cargo, uf: str) -> str:
        """Pasta das fotos do cargo no sistema de resultados: ``br`` para cargo nacional, a UF nos demais."""
        # Fotos ficam na pasta da abrangência do cargo: "br" para Presidente.
        return "br" if cargo.nivel is Nivel.BRASIL else uf

    def _fotos(self, cargo: Cargo, uf: str, r: ResultadoAbrangencia, *, baixar: bool) -> dict[str, str]:
        """Mapa ``sq`` → caminho relativo da foto, para os cargos do plano que têm foto.

        Com ``baixar``, busca as que não estão no disco nem em ``estado.fotos`` e as grava de forma
        atômica; sem, só lista as que já existem. As presentes entram em ``estado.fotos``, para não serem
        pedidas de novo depois de um reinício.
        """
        if cargo.codigo not in self.plano.fotos_para:
            return {}
        pasta = self._dir_fotos(cargo, uf)
        saida = {}
        for c in r.candidatos:
            if not c.sq:
                continue
            relativo = f"fotos/{self.e.ciclo}/{cargo.eleicao_tse}/{pasta}/{c.sq}.jpeg"
            destino = self.escritor.raiz / relativo
            if baixar and c.sq not in self.estado.fotos and not destino.exists():
                obtido = self._obter(tse.url_foto(self.e.ciclo, cargo.eleicao_tse, pasta, c.sq, self.base),
                                     condicional=False)
                if obtido is None:
                    continue
                destino.parent.mkdir(parents=True, exist_ok=True)
                tmp = destino.with_name(destino.name + ".tmp")
                tmp.write_bytes(obtido[0])
                os.replace(tmp, destino)
                self._resumo.fotos += 1
            if destino.exists():
                self.estado.fotos.add(c.sq)
                saida[c.sq] = relativo
        return saida

    def _coletar_topo(self, cargo: Cargo, ufs_mudaram: set[str]) -> None:
        """Baixa o resultado de topo do cargo: o do Brasil (cargo nacional) e os das UFs que mudaram.

        Cargo municipal não tem topo e é ignorado; o exterior só entra para cargo nacional.
        """
        if cargo.nivel is Nivel.MUNICIPIO:
            return
        if cargo.nivel is Nivel.BRASIL:
            self._baixar_resultado(cargo, "br", None)
        for uf in self.plano.ufs:
            if uf == tse.UF_EXTERIOR and cargo.nivel is not Nivel.BRASIL:
                continue
            if uf in ufs_mudaram:
                self._baixar_resultado(cargo, uf, None)

    def _baixar_resultado(self, cargo: Cargo, uf: str, municipio: str | None) -> None:
        """Baixa e processa o resultado de um cargo numa abrangência (Brasil, UF ou município).

        No nível mais alto do cargo, atualiza as cores fixas do estado; abaixo dele, usa as fixas ou, se o
        topo ainda não foi lido, cores provisórias pela ordem local. O feed do município é gravado aqui,
        com sua ``parte`` guardada para o feed da UF; UF e Brasil só são marcados em ``sujos`` e gravados
        em ``_regravar_agregados``. Também registra o ponto de evolução.
        """
        url = tse.url_resultado(self.e.ciclo, cargo.eleicao_tse, cargo.codigo, uf, municipio, self.base)
        obtido = self._obter(url)
        if municipio is not None:
            self.baixados_alguma_vez.add((cargo.codigo, uf, municipio))
        if obtido is None:
            return
        conteudo, origem = obtido
        r = tse.ler_resultado(conteudo)
        if municipio is None:
            abr = abrangencia_brasil() if uf == "br" else abrangencia_uf(uf)
        else:
            # Fora do cadastro (não deveria acontecer com o -cm da própria eleição):
            # entra com o código, para o resultado não sumir.
            m = self.cadastro.por_tse(uf, municipio) or self.cadastro.completar(
                uf, municipio, f"Município TSE {municipio}")
            abr = abrangencia_municipio(m)
        chave_cores = self._chave_cores(cargo, abr)
        cores = self.estado.cores.setdefault(chave_cores, {})
        if _topo(cargo, abr):
            cores.update(atribuir_cores(self._ordem(cargo, r), cores, partidos=_partidos(r)))
        elif not cores:
            # O topo ainda não foi lido: cores provisórias pela ordem local.
            cores = atribuir_cores(self._ordem(cargo, r), partidos=_partidos(r))
        chave = f"{cargo.codigo}/{abr.arquivo}"
        self.ultimo[chave] = (r, origem)
        self.sujos.add(chave)
        if abr.tipo == "mu":
            fotos = self._fotos(cargo, uf, r, baixar=True) if _topo(cargo, abr) else {}
            self.escritor.gravar(self.e.id, cargo.slug, abr, feed_resultado(
                eleicao=self.e, cargo=cargo, abr=abr, resultado=r, cores=cores, origem=origem,
                limite_candidatos=LIMITE_CANDIDATOS_MUNICIPIO if proporcional(cargo) else None,
                fotos=fotos, ao_vivo=not r.totalizacao.finalizada))
            self._resumo.feeds += 1
            pai = f"{cargo.codigo}/uf-{uf}"
            self.estado.partes.setdefault(pai, {})[abr.codigo] = parte_json(
                abr, r, cores, por_partido=proporcional(cargo))
            self.sujos.add(pai)
        elif _topo(cargo, abr):
            self._fotos(cargo, uf, r, baixar=True)
        if abr.tipo == "uf":
            self.sujos.add(f"{cargo.codigo}/br")
        self._registrar_evolucao(cargo, abr, r, cores)

    def _coletar_municipios(self) -> None:
        """Consome a fila de municípios até o orçamento da passada, os nunca baixados primeiro; o resto espera."""
        # Os nunca baixados vão na frente: o mapa precisa estar completo
        # antes de ficar atualizado.
        primeiro = [i for i in self.fila if i not in self.baixados_alguma_vez]
        depois = [i for i in self.fila if i in self.baixados_alguma_vez]
        ordem = deque(primeiro + depois)
        feitos = 0
        while ordem and feitos < self.plano.orcamento_municipal:
            item = ordem.popleft()
            self.na_fila.discard(item)
            codigo, uf, municipio = item
            self._baixar_resultado(self.e.cargo(codigo), uf, municipio)
            feitos += 1
        self.fila = ordem

    # ------------------------------------------------------------ agregados

    def _regravar_agregados(self, cargo: Cargo) -> None:
        """Regrava UF e Brasil que mudaram (por si ou por um município)."""
        if cargo.nivel is Nivel.MUNICIPIO:
            if any(s.startswith(f"{cargo.codigo}/") for s in self.sujos):
                self._regravar_panoramas(cargo)
            return
        cores_br = self.estado.cores.get(f"{cargo.codigo}/br", {})
        partes_br = []
        for uf in self.plano.ufs:
            chave = f"{cargo.codigo}/uf-{uf}"
            if chave not in self.ultimo:
                continue
            r, origem = self.ultimo[chave]
            abr = abrangencia_uf(uf)
            if cargo.nivel is Nivel.BRASIL:
                partes_br.append(parte_json(abr, r, cores_br))
            if chave not in self.sujos:
                continue
            cores = self.estado.cores.get(self._chave_cores(cargo, abr), {})
            partes = recolorir(sorted(self.estado.partes.get(chave, {}).values(), key=lambda p: p["codigo"]), cores)
            self.escritor.gravar(self.e.id, cargo.slug, abr, feed_resultado(
                eleicao=self.e, cargo=cargo, abr=abr, resultado=r, cores=cores, origem=origem, partes=partes,
                fotos=self._fotos(cargo, uf, r, baixar=False), ao_vivo=not r.totalizacao.finalizada))
            self._resumo.feeds += 1
        if cargo.nivel is Nivel.UF and any(s.startswith(f"{cargo.codigo}/uf-") for s in self.sujos):
            self._regravar_panorama_estadual(cargo)
        chave_br = f"{cargo.codigo}/br"
        if cargo.nivel is Nivel.BRASIL and chave_br in self.ultimo and chave_br in self.sujos:
            r, origem = self.ultimo[chave_br]
            self.escritor.gravar(self.e.id, cargo.slug, abrangencia_brasil(), feed_resultado(
                eleicao=self.e, cargo=cargo, abr=abrangencia_brasil(), resultado=r, cores=cores_br,
                origem=origem, partes=partes_br, fotos=self._fotos(cargo, "br", r, baixar=False),
                ao_vivo=not r.totalizacao.finalizada))
            self._resumo.feeds += 1

    def _regravar_panoramas(self, cargo: Cargo) -> None:
        """Cargo municipal: panorama de cada UF e o nacional, das ``partes`` dos municípios."""
        municipais = [(r, o) for k, (r, o) in self.ultimo.items() if k.startswith(f"{cargo.codigo}/mu-")]
        instantes = [r.atualizado_em for r, _ in municipais if r.atualizado_em]
        atualizado = max(instantes) if instantes else None
        origem = municipais[-1][1] if municipais else origem_json("resultados")
        por_uf: dict[str, dict] = {}
        for uf in self.plano.ufs:
            partes = [dict(p) for p in sorted(self.estado.partes.get(f"{cargo.codigo}/uf-{uf}", {}).values(),
                                              key=lambda p: p["codigo"])]
            if not partes:
                continue
            abr = abrangencia_uf(uf)
            panorama = feed_panorama(eleicao=self.e, cargo=cargo, abr=abr, partes=partes, origem=origem,
                                     atualizado_em=atualizado,
                                     ao_vivo=any(not p.get("finalizada") for p in partes))
            self.escritor.gravar(self.e.id, cargo.slug, abr, panorama)
            self._resumo.feeds += 1
            por_uf[uf] = panorama
        if por_uf:
            self.escritor.gravar(self.e.id, cargo.slug, abrangencia_brasil(), panorama_nacional(
                eleicao=self.e, cargo=cargo, por_uf=por_uf, origem=origem, atualizado_em=atualizado,
                ao_vivo=any(p["ao_vivo"] for p in por_uf.values())))
            self._resumo.feeds += 1

    def _regravar_panorama_estadual(self, cargo: Cargo) -> None:
        """Cargo estadual: panorama nacional com o líder (ou a bancada) de cada UF."""
        ufs = [(uf, self.ultimo[f"{cargo.codigo}/uf-{uf}"]) for uf in self.plano.ufs
               if f"{cargo.codigo}/uf-{uf}" in self.ultimo]
        if not ufs:
            return
        partes = [parte_json(abrangencia_uf(uf), r, {}, por_partido=proporcional(cargo)) for uf, (r, _) in ufs]
        instantes = [r.atualizado_em for _, (r, _) in ufs if r.atualizado_em]
        self.escritor.gravar(self.e.id, cargo.slug, abrangencia_brasil(), feed_panorama(
            eleicao=self.e, cargo=cargo, abr=abrangencia_brasil(), partes=partes, origem=ufs[-1][1][1],
            atualizado_em=max(instantes) if instantes else None,
            ao_vivo=any(not r.totalizacao.finalizada for _, (r, _) in ufs)))
        self._resumo.feeds += 1

    # ------------------------------------------------------------ evolução e índice

    def _registrar_evolucao(self, cargo: Cargo, abr: Abrangencia, r: ResultadoAbrangencia,
                            cores: dict[str, int]) -> None:
        """Acrescenta um ponto à evolução da totalização e regrava o feed ``historico-`` da abrangência.

        Só Brasil e UF, em cargos não proporcionais. Ponto igual ao anterior (mesmo percentual de seções e
        mesmos votos) é descartado; acima de ``MAX_PONTOS_EVOLUCAO``, saem os mais antigos, menos o
        primeiro.
        """
        if abr.tipo == "mu" or proporcional(cargo):
            return
        chave = f"{cargo.codigo}/{abr.arquivo}"
        pontos = self.estado.evolucao.setdefault(chave, [])
        ponto = {"t": r.atualizado_em.isoformat() if r.atualizado_em else None,
                 "pct_secoes": r.totalizacao.pct_secoes,
                 "votos": {c.numero: c.votos for c in r.candidatos if c.valido}}
        if pontos and pontos[-1]["pct_secoes"] == ponto["pct_secoes"] and pontos[-1]["votos"] == ponto["votos"]:
            return
        pontos.append(ponto)
        if len(pontos) > MAX_PONTOS_EVOLUCAO:
            # Mantém o primeiro ponto e os mais recentes
            del pontos[1:len(pontos) - MAX_PONTOS_EVOLUCAO + 1]
        candidatos = [{"numero": c.numero, "nome_urna": c.nome_urna, "partido": c.partido,
                       "cor": cores.get(c.numero, -1)} for c in r.candidatos if c.valido]
        origem = origem_json("resultados")
        if self.plano.simulacao:
            origem["simulacao"] = True
        self.escritor.gravar_historico(self.e.id, cargo.slug, abr, feed_historico(
            eleicao=self.e, cargo=cargo, abr=abr, pontos=pontos, candidatos=candidatos, origem=origem))

    def secoes_completas(self) -> bool:
        """Todos os resultados de topo com 100% das seções totalizadas e a fila de municípios vazia."""
        topo = [r for k, (r, _) in self.ultimo.items() if "/mu-" not in k]
        return bool(topo) and not self.fila and all((r.totalizacao.pct_secoes or 0) >= 100 for r in topo)

    def sem_marca_de_finalizada(self) -> list[str]:
        """Resultados de topo (``código do cargo/arquivo``) que o TSE ainda não marcou como finalizados."""
        return sorted(k for k, (r, _) in self.ultimo.items() if "/mu-" not in k and not r.totalizacao.finalizada)

    def _finalizada(self) -> bool:
        """A totalização terminou? Havendo resultado de topo, quando todos estão finalizados.

        Só com resultados municipais, quando todos estão finalizados e a fila de municípios está vazia.
        """
        topo = [r for k, (r, _) in self.ultimo.items() if "/mu-" not in k]
        if topo:
            return all(r.totalizacao.finalizada for r in topo)
        municipais = [r for r, _ in self.ultimo.values()]
        return bool(municipais) and all(r.totalizacao.finalizada for r in municipais) and not self.fila

    def ufs_por_cargo(self) -> dict[int, set[str]]:
        """UFs com dado recebido, por cargo (Brasil conta como cargo presente, sem UF)."""
        municipais = {c.codigo for c in self.plano.cargos if c.nivel is Nivel.MUNICIPIO}
        saida: dict[int, set[str]] = {}
        for chave in self.ultimo:
            codigo, arquivo = chave.split("/", 1)
            ufs = saida.setdefault(int(codigo), set())
            if arquivo.startswith("uf-"):
                ufs.add(arquivo[3:])
        # Cargo municipal: o arquivo da UF é o panorama, montado das partes
        for chave in self.estado.partes:
            codigo, arquivo = chave.split("/", 1)
            if int(codigo) in municipais:
                saida.setdefault(int(codigo), set()).add(arquivo[3:])
        return saida

    def _atualizar_indice(self, *, ao_vivo: bool) -> None:
        """Atualiza a linha da eleição no ``indice.json``, com ``ao_vivo`` dizendo se a coleta continua.

        Leva o instante mais recente dos resultados, as UFs com dado por cargo e as vagas dos cargos
        nacionais.
        """
        instantes = [r.atualizado_em for r, _ in self.ultimo.values() if r.atualizado_em]
        codigos = {c.codigo for c in self.plano.cargos}
        presentes = {k: v for k, v in self.ufs_por_cargo().items() if k in codigos}
        vagas = {c.codigo: self.ultimo[f"{c.codigo}/br"][0].vagas for c in self.plano.cargos
                 if f"{c.codigo}/br" in self.ultimo and c.nivel is Nivel.BRASIL}
        entrada = entrada_indice(self.e, origem="resultados", ao_vivo=ao_vivo,
                                 atualizado_em=max(instantes) if instantes else None,
                                 ufs=sorted({u for v in presentes.values() for u in v}) or self.plano.ufs,
                                 vagas=vagas, ufs_por_cargo=presentes)
        if self.plano.simulacao:
            entrada["simulacao"] = True
        self.escritor.atualizar_indice(entrada)
