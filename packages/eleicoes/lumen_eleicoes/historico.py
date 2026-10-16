"""Eleições passadas: dos arquivos de dados abertos aos feeds do portal.

Um ano por vez. O detalhe da apuração (pequeno) é lido inteiro primeiro; o
arquivo de votação (grande) é lido um CSV por vez — o ``_BR`` com o
Presidente e depois um por UF —, e cada CSV vira os feeds do que ele contém
antes de o próximo ser aberto. Assim a memória fica proporcional à maior UF,
não ao Brasil.

O que sai, por eleição (ano e turno) e cargo:

- cargo nacional (Presidente): ``br``, ``uf-*`` e ``mu-*``;
- cargo estadual: ``uf-*``, ``mu-*`` e o panorama ``br`` (quem lidera em cada UF);
- cargo municipal: ``mu-*`` e os panoramas ``uf-*`` e ``br``.

No município com duas zonas eleitorais ou mais, o feed ``mu-*`` leva as zonas em ``partes`` (quem lidera em
cada zona, com as cores do próprio feed). Quais municípios têm mais de uma zona sai do detalhe da apuração;
sem ele, os feeds saem sem zonas.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable, Mapping

from . import dados_abertos as da
from .feeds import (
    Abrangencia,
    EscritorFeeds,
    abrangencia_brasil,
    abrangencia_municipio,
    abrangencia_uf,
    abrangencia_zona,
    atribuir_cores,
    entrada_indice,
    feed_historico,
    feed_panorama,
    feed_resultado,
    nome_eleicao,
    origem_json,
    panorama_nacional,
    parte_json,
    parte_zona_json,
    proporcional,
    ranking_partidos,
)
from .modelo import CARGOS, Cargo, Eleicao, Nivel, ResultadoAbrangencia, TipoCargo
from .municipios import CadastroMunicipios
from .transferencia import Manifesto

log = logging.getLogger("lumen.eleicoes.historico")

LIMITE_CANDIDATOS_MUNICIPIO = 50


@dataclass
class ResumoAno:
    """Contagens do processamento de um ano, devolvidas por ``ProcessadorAno.processar``.

    ``municipios_sem_ibge`` junta, como ``<uf><código TSE>``, os municípios do Brasil que apareceram nos
    dados sem código IBGE no cadastro: entram nos feeds, mas o mapa não os colore.
    """

    ano: int
    eleicoes: list[str] = field(default_factory=list)
    arquivos: int = 0
    linhas_lidas: int = 0
    linhas_ignoradas: int = 0
    municipios_sem_ibge: set[str] = field(default_factory=set)


def _cargo(codigo: int, codigo_tse: int | None) -> Cargo:
    """``Cargo`` a partir do código: nome da tabela ``CARGOS`` e tipo dado por ``proporcional``.

    Sem o código da eleição no TSE, ``eleicao_tse`` fica 0.
    """
    slug, nome, _ = CARGOS[codigo]
    tipo = TipoCargo.PROPORCIONAL if proporcional(codigo) else TipoCargo.MAJORITARIO
    return Cargo(codigo=codigo, nome=nome, tipo=tipo, eleicao_tse=codigo_tse or 0)


def _ordem_cores(r: ResultadoAbrangencia) -> list[str]:
    """Números dos candidatos válidos na ordem do resultado: a ordem em que ``atribuir_cores`` distribui as cores."""
    return [c.numero for c in r.candidatos if c.valido]


# Resultados por zona de cada município: chave do município ("mu", uf, tse) → número da zona → resultado
Zonas = dict[da.Abr, dict[str, ResultadoAbrangencia]]


def _partes_zonas(municipio: da.Abr, zonas: Zonas, cores: dict[str, int], por_partido: bool) -> list[dict]:
    """Partes do feed do município: uma por zona, em ordem numérica; nenhuma se o município tem uma só."""
    do_municipio = zonas.get(municipio) or {}
    if len(do_municipio) < 2:
        return []
    uf = municipio[1]
    return [parte_zona_json(abrangencia_zona(uf, z), r, cores, por_partido=por_partido)
            for z, r in sorted(do_municipio.items(), key=lambda kv: int(kv[0]))]


class ProcessadorAno:
    """Transforma os ZIPs de um ano em feeds. Um objeto por ano processado."""

    def __init__(self, ano: int, escritor: EscritorFeeds, cadastro: CadastroMunicipios, *,
                 origem_votacao: Manifesto | None = None, origem_detalhe: Manifesto | None = None,
                 limite_candidatos_municipio: int = LIMITE_CANDIDATOS_MUNICIPIO,
                 progresso: Callable[[str], None] | None = None,
                 fotos_ao_vivo: Mapping[str, Iterable[str]] | None = None):
        """Prepara o estado que se acumula ao longo do ano.

        A origem dos feeds vem do manifesto do ZIP de votação quando há um (URL, SHA-256 e instante do
        download); sem ele, só a URL oficial do conjunto. Os dicionários guardam o que só pode ser emitido no
        fim — índice, panoramas nacionais, vagas somadas das UFs —, porque cada CSV é emitido e descartado
        antes de o próximo ser aberto. ``fotos_ao_vivo`` (id da eleição → ``sq`` dos candidatos cuja foto a
        coleta ao vivo baixou) deixa os feeds com as fotos que já estão publicadas.
        """
        self.ano = ano
        self.escritor = escritor
        self.cadastro = cadastro
        self.limite = limite_candidatos_municipio
        self.progresso = progresso or (lambda _msg: None)
        self.origem = origem_json(
            "dados_abertos",
            url=origem_votacao.url if origem_votacao else da.url_conjunto(da.CONJUNTO_VOTACAO, ano),
            sha256=origem_votacao.sha256 if origem_votacao else None,
            coletado_em=origem_votacao.baixado_em if origem_votacao else None,
        )
        self.origem_detalhe = origem_detalhe
        self.resumo = ResumoAno(ano=ano)
        self.eleicoes: dict[str, Eleicao] = {}
        self.ufs: dict[str, set[str]] = defaultdict(set)
        self.ufs_cargo: dict[str, dict[int, set[str]]] = defaultdict(lambda: defaultdict(set))
        self.vagas: dict[str, dict[int, int]] = defaultdict(dict)
        self.atualizado: dict[str, datetime] = {}
        self.panoramas_uf: dict[tuple[str, int], dict[str, dict]] = defaultdict(dict)
        self.partes_estaduais: dict[tuple[str, int], dict[str, dict]] = defaultdict(dict)
        self.ultimo_estadual: dict[tuple[str, int], datetime] = {}
        self.finais_br: dict[tuple[str, int], ResultadoAbrangencia] = {}
        self.zonas_de: set[tuple[str, str]] = set()
        self.fotos_ao_vivo = {eid: set(sqs) for eid, sqs in (fotos_ao_vivo or {}).items()}

    # ------------------------------------------------------------ entrada

    def processar(self, zip_votacao: Path | str, zip_detalhe: Path | str | None) -> ResumoAno:
        """Lê os ZIPs do ano, grava todos os feeds e devolve o resumo.

        O detalhe da apuração, quando informado, é lido inteiro antes e dá os totais de cada abrangência
        (comparecimento, brancos, nulos, seções). A votação é lida um CSV por vez, cada um com um agregador
        próprio, emitido e limpo antes do próximo. Se o ZIP tem o arquivo ``_BR``, o Presidente vem só dele e
        é pulado nos arquivos por UF. Os municípios com duas zonas ou mais, conhecidos pelo detalhe, também
        têm a votação somada por zona. No fim, emite os panoramas nacionais e atualiza o índice.
        """
        totais: dict = {}
        if zip_detalhe:
            with da.abrir_zip(zip_detalhe) as zf:
                br = da.tem_arquivo_br(zf.namelist())
                self.progresso(f"{self.ano}: lendo detalhe da apuração")
                totais = da.ler_detalhe(da.fluxos_do_zip(zf), pular_presidente_nos_estados=br)
            self.zonas_de = da.municipios_com_zonas(totais)
            # Totais de zona só servem aos municípios com mais de uma; os demais sairiam da memória só no fim
            totais = {k: t for k, t in totais.items() if k[2][0] != "zn" or (k[2][1], k[2][2]) in self.zonas_de}
        with da.abrir_zip(zip_votacao) as zf:
            nomes = zf.namelist()
            br = da.tem_arquivo_br(nomes)
            for nome in da.entradas_csv(nomes):
                self.progresso(f"{self.ano}: {nome}")
                agregador = da.AgregadorVotacao(pular_presidente=br and not nome.upper().endswith("_BR.CSV"),
                                                zonas_de=self.zonas_de)
                with zf.open(nome) as fluxo:
                    agregador.ler(fluxo)
                self.resumo.arquivos += 1
                self.resumo.linhas_lidas += agregador.linhas_lidas
                self.resumo.linhas_ignoradas += agregador.linhas_ignoradas
                self._emitir(agregador, totais)
                agregador.limpar()
        self._emitir_panoramas_nacionais()
        self._atualizar_indice()
        self.resumo.eleicoes = sorted(self.eleicoes)
        return self.resumo

    # ------------------------------------------------------------ eleição

    def _eleicao(self, eid: str, agregador: da.AgregadorVotacao) -> Eleicao:
        """``Eleicao`` do id (``"2022-1t-geral"``), criada na primeira vez em que aparece.

        A data vem do agregador; se o primeiro CSV não a trazia, é preenchida quando um seguinte trouxer.
        """
        e = self.eleicoes.get(eid)
        if e is None:
            ano, turno, tipo = eid.split("-")
            e = Eleicao(id=eid, ano=int(ano), turno=int(turno[0]), tipo=tipo,
                        nome=nome_eleicao(int(ano), int(turno[0]), tipo),
                        data=agregador.datas.get(eid), ciclo=f"ele{ano}", pleito=None, origem="dados_abertos")
            self.eleicoes[eid] = e
        elif e.data is None and agregador.datas.get(eid):
            e.data = agregador.datas[eid]
        return e

    def _registrar_cargo(self, e: Eleicao, cargo: Cargo) -> None:
        """Acrescenta o cargo à eleição, se ainda não estiver lá, mantendo a lista ordenada por código."""
        if all(c.codigo != cargo.codigo for c in e.cargos):
            e.cargos.append(cargo)
            e.cargos.sort(key=lambda c: c.codigo)

    def _abr(self, chave: da.Abr, agregador: da.AgregadorVotacao) -> Abrangencia:
        """Converte a chave do agregador (``("br",)``, ``("uf", uf)`` ou ``("mu", uf, tse)``) em ``Abrangencia``.

        Município fora do cadastro entra por ``CadastroMunicipios.completar``, com o nome publicado no CSV;
        os do Brasil que ficam sem código IBGE são anotados no resumo.
        """
        if chave[0] == "br":
            return abrangencia_brasil()
        if chave[0] == "uf":
            return abrangencia_uf(chave[1])
        uf, tse = chave[1], chave[2]
        m = self.cadastro.por_tse(uf, tse)
        if m is None:
            m = self.cadastro.completar(uf, tse, agregador.nomes_municipios.get((uf, tse), tse))
        if not m.ibge and uf != "zz":
            self.resumo.municipios_sem_ibge.add(f"{uf}{tse}")
        return abrangencia_municipio(m)

    def _fotos(self, e: Eleicao, cargo: Cargo, pasta: str) -> dict[str, str]:
        """``sq`` → caminho da foto que a coleta ao vivo da mesma eleição baixou, no mesmo desenho do
        coletor (``fotos/<ciclo>/<eleição no TSE>/<br ou UF>/<sq>.jpeg``; ver ``coletor._fotos``)."""
        sqs = self.fotos_ao_vivo.get(e.id)
        if not sqs or not cargo.eleicao_tse:
            return {}
        return {sq: f"fotos/ele{e.ano}/{cargo.eleicao_tse}/{pasta}/{sq}.jpeg" for sq in sqs}

    # ------------------------------------------------------------ emissão

    def _emitir(self, agregador: da.AgregadorVotacao, totais: dict) -> None:
        """Emite os feeds de tudo o que um CSV agregou.

        Agrupa os resultados por eleição e cargo, registra o cargo na eleição, acompanha o instante mais
        recente e as UFs com resultado (para o índice) e despacha para a emissão municipal ou para a dos
        cargos nacional e estaduais, conforme o nível do cargo. Os resultados por zona vão à parte, por
        município, para entrar no feed do município.
        """
        grupos: dict[tuple[str, int], dict[da.Abr, ResultadoAbrangencia]] = defaultdict(dict)
        zonas: dict[tuple[str, int], Zonas] = defaultdict(lambda: defaultdict(dict))
        for chave in agregador.chaves():
            eid, cargo, abr = chave
            r = agregador.resultado(chave, totais.get(chave))
            if abr[0] == "zn":
                zonas[(eid, cargo)][("mu", abr[1], abr[2])][abr[3]] = r
            else:
                grupos[(eid, cargo)][abr] = r
        for (eid, codigo), resultados in grupos.items():
            e = self._eleicao(eid, agregador)
            cargo = _cargo(codigo, agregador.codigos_tse.get((eid, codigo)))
            self._registrar_cargo(e, cargo)
            nivel = CARGOS[codigo][2]
            for abr_chave, r in resultados.items():
                if r.atualizado_em and (eid not in self.atualizado or r.atualizado_em > self.atualizado[eid]):
                    self.atualizado[eid] = r.atualizado_em
                if abr_chave[0] != "br":
                    self.ufs[eid].add(abr_chave[1])
                    self.ufs_cargo[eid][codigo].add(abr_chave[1])
            if nivel is Nivel.MUNICIPIO:
                self._emitir_municipal(e, cargo, resultados, agregador, zonas.get((eid, codigo), {}))
            else:
                self._emitir_majoritario_ou_estadual(e, cargo, resultados, agregador, nivel,
                                                     zonas.get((eid, codigo), {}))

    def _emitir_majoritario_ou_estadual(self, e: Eleicao, cargo: Cargo,
                                        resultados: dict[da.Abr, ResultadoAbrangencia],
                                        agregador: da.AgregadorVotacao, nivel: Nivel,
                                        zonas: Zonas | None = None) -> None:
        """Grava os feeds de cargo nacional ou estadual: municípios, UFs e, para o Presidente, o Brasil.

        As cores do Presidente são as do resultado nacional, as mesmas em todas as UFs; nos cargos estaduais,
        cada UF tem as suas, pela ordem dos candidatos (ou dos partidos, nos proporcionais). O feed de UF leva
        as partes dos municípios e o do Brasil, as das UFs; nos proporcionais, o de município fica com os
        ``limite`` mais votados e os eleitos, e o de município com mais de uma zona, as zonas em ``partes``.
        Num cargo estadual, a parte de cada UF fica guardada para o panorama nacional, emitido no fim do ano.
        """
        zonas = zonas or {}
        por_partido = proporcional(cargo)
        ufs = sorted({k[1] for k in resultados if k[0] == "uf"})
        cores_br: dict[str, int] = {}
        if nivel is Nivel.BRASIL and ("br",) in resultados:
            topo = resultados[("br",)]
            cores_br = atribuir_cores(_ordem_cores(topo))
        partes_br = []
        fotos_br = self._fotos(e, cargo, "br")
        for uf in ufs:
            fotos = fotos_br if nivel is Nivel.BRASIL else self._fotos(e, cargo, uf)
            r_uf = resultados[("uf", uf)]
            if nivel is Nivel.BRASIL:
                cores = cores_br
            elif por_partido:
                cores = atribuir_cores(p for p, _ in ranking_partidos(r_uf))
            else:
                cores = atribuir_cores(_ordem_cores(r_uf))
            partes_uf = []
            for chave, r_mu in sorted((k, v) for k, v in resultados.items() if k[0] == "mu" and k[1] == uf):
                abr_mu = self._abr(chave, agregador)
                partes_uf.append(parte_json(abr_mu, r_mu, cores, por_partido=por_partido))
                self.escritor.gravar(e.id, cargo.slug, abr_mu, feed_resultado(
                    eleicao=e, cargo=cargo, abr=abr_mu, resultado=r_mu, cores=cores, origem=self.origem,
                    limite_candidatos=self.limite if por_partido else None,
                    partes=_partes_zonas(chave, zonas, cores, por_partido), fotos=fotos))
            abr_uf = abrangencia_uf(uf)
            self.escritor.gravar(e.id, cargo.slug, abr_uf, feed_resultado(
                eleicao=e, cargo=cargo, abr=abr_uf, resultado=r_uf, cores=cores, origem=self.origem,
                partes=partes_uf, fotos=fotos))
            if r_uf.vagas:
                self.vagas[e.id][cargo.codigo] = self.vagas[e.id].get(cargo.codigo, 0) + r_uf.vagas
            if nivel is Nivel.BRASIL:
                partes_br.append(parte_json(abr_uf, r_uf, cores_br))
            else:
                # Cargo estadual: a UF entra no panorama nacional (governadores,
                # senadores e bancadas por partido), emitido no fim do ano.
                self.partes_estaduais[(e.id, cargo.codigo)][uf] = parte_json(
                    abr_uf, r_uf, cores, por_partido=por_partido)
                if r_uf.atualizado_em:
                    atual = self.ultimo_estadual.get((e.id, cargo.codigo))
                    if atual is None or r_uf.atualizado_em > atual:
                        self.ultimo_estadual[(e.id, cargo.codigo)] = r_uf.atualizado_em
        if nivel is Nivel.BRASIL and ("br",) in resultados:
            r_br = resultados[("br",)]
            self.escritor.gravar(e.id, cargo.slug, abrangencia_brasil(), feed_resultado(
                eleicao=e, cargo=cargo, abr=abrangencia_brasil(), resultado=r_br, cores=cores_br,
                origem=self.origem, partes=partes_br, fotos=fotos_br))
            self.finais_br[(e.id, cargo.codigo)] = r_br
            if r_br.vagas:
                self.vagas[e.id][cargo.codigo] = r_br.vagas

    def _emitir_municipal(self, e: Eleicao, cargo: Cargo, resultados: dict[da.Abr, ResultadoAbrangencia],
                          agregador: da.AgregadorVotacao, zonas: Zonas | None = None) -> None:
        """Grava os feeds de cargo municipal: um por município, com as zonas quando há mais de uma, e o
        panorama de cada UF.

        Cada município tem as próprias cores (por candidato, ou por partido nos proporcionais), que valem
        também para as zonas dele. O panorama de cada UF fica guardado para o panorama nacional, emitido no
        fim do ano.
        """
        zonas = zonas or {}
        por_partido = proporcional(cargo)
        por_uf: dict[str, list[dict]] = defaultdict(list)
        ultimo: dict[str, datetime] = {}
        for chave, r in sorted(resultados.items()):
            abr = self._abr(chave, agregador)
            if por_partido:
                cores = atribuir_cores(p for p, _ in ranking_partidos(r))
            else:
                cores = atribuir_cores(_ordem_cores(r))
            self.escritor.gravar(e.id, cargo.slug, abr, feed_resultado(
                eleicao=e, cargo=cargo, abr=abr, resultado=r, cores=cores, origem=self.origem,
                partes=_partes_zonas(chave, zonas, cores, por_partido), fotos=self._fotos(e, cargo, chave[1])))
            # No panorama, a linha do município mostra o partido do líder (ou,
            # para vereador, o partido mais votado e a bancada eleita); a cor
            # é atribuída lá, pela ordem do placar.
            por_uf[chave[1]].append(parte_json(abr, r, cores, por_partido=por_partido))
            if r.atualizado_em and (chave[1] not in ultimo or r.atualizado_em > ultimo[chave[1]]):
                ultimo[chave[1]] = r.atualizado_em
            if r.vagas:
                self.vagas[e.id][cargo.codigo] = self.vagas[e.id].get(cargo.codigo, 0) + r.vagas
        for uf, partes in por_uf.items():
            abr_uf = abrangencia_uf(uf)
            panorama = feed_panorama(eleicao=e, cargo=cargo, abr=abr_uf, partes=partes, origem=self.origem,
                                     atualizado_em=ultimo.get(uf))
            self.escritor.gravar(e.id, cargo.slug, abr_uf, panorama)
            self.panoramas_uf[(e.id, cargo.codigo)][uf] = panorama

    def _emitir_panoramas_nacionais(self) -> None:
        """Grava o feed ``br`` dos cargos sem resultado nacional próprio, com o que foi guardado durante o ano.

        Cargo municipal: o panorama nacional junta os panoramas das UFs. Cargo estadual: um panorama com uma
        parte por UF (governadores, senadores, bancadas), em ordem de UF.
        """
        for (eid, codigo), por_uf in self.panoramas_uf.items():
            e = self.eleicoes[eid]
            cargo = e.cargo(codigo)
            self.escritor.gravar(eid, cargo.slug, abrangencia_brasil(), panorama_nacional(
                eleicao=e, cargo=cargo, por_uf=por_uf, origem=self.origem, atualizado_em=self.atualizado.get(eid)))
        for (eid, codigo), por_uf in self.partes_estaduais.items():
            e = self.eleicoes[eid]
            cargo = e.cargo(codigo)
            partes = [dict(p) for _, p in sorted(por_uf.items())]
            self.escritor.gravar(eid, cargo.slug, abrangencia_brasil(), feed_panorama(
                eleicao=e, cargo=cargo, abr=abrangencia_brasil(), partes=partes, origem=self.origem,
                atualizado_em=self.ultimo_estadual.get((eid, codigo))))

    def _atualizar_indice(self) -> None:
        """Registra no índice cada eleição do ano como histórica (``ao_vivo=False``), com UFs, vagas e o
        instante mais recente."""
        for eid, e in self.eleicoes.items():
            self.escritor.atualizar_indice(entrada_indice(
                e, origem="dados_abertos", ao_vivo=False, atualizado_em=self.atualizado.get(eid),
                ufs=self.ufs.get(eid, ()), vagas=self.vagas.get(eid), ufs_por_cargo=self.ufs_cargo.get(eid, {})))

    # ------------------------------------------------------------ evolução

    def gravar_evolucao(self, turno: int, fluxo) -> bool:
        """Grava ``historico-br.json`` do Presidente a partir do Historico_Totalizacao."""
        tipo = da.tipo_do_ano(self.ano)
        eid = f"{self.ano}-{turno}t-{tipo}"
        final = self.finais_br.get((eid, 1))
        e = self.eleicoes.get(eid)
        if final is None or e is None:
            return False
        pontos = da.ler_historico_totalizacao(fluxo)
        if not pontos:
            return False
        rotulos = list(pontos[-1].votos)
        mapa = {r: (da.casar_rotulo(r, final.candidatos) or r) for r in rotulos}
        cores = atribuir_cores(_ordem_cores(final))
        candidatos = []
        for c in final.candidatos:
            if c.valido and c.numero in mapa.values():
                candidatos.append({"numero": c.numero, "nome_urna": c.nome_urna, "partido": c.partido,
                                   "cor": cores.get(c.numero, -1)})
        for rotulo, chave in mapa.items():
            if chave == rotulo:  # sem correspondência: entra pelo rótulo publicado
                candidatos.append({"numero": rotulo, "nome_urna": rotulo.replace("_", " "), "partido": None,
                                   "cor": -1})
        serie = [{"t": p.instante.isoformat(), "pct_secoes": p.pct_secoes,
                  "votos": {mapa[r]: v for r, v in p.votos.items()}} for p in pontos]
        url = da.url_historico_presidente(self.ano, turno)
        self.escritor.gravar_historico(eid, "presidente", abrangencia_brasil(), feed_historico(
            eleicao=e, cargo=e.cargo(1), abr=abrangencia_brasil(), pontos=serie, candidatos=candidatos,
            origem=origem_json("dados_abertos", url=url)))
        return True
