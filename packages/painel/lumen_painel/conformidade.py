"""Painel de conformidade fiscal: as entregas da LRF ao Tesouro, ente por ente (UC-07, RF-CF-01 e RF-CF-02).

Duas etapas, em momentos diferentes:

1. **Coleta, por UF** (``coletar_uf``): o extrato de entregas do SICONFI de cada ente da UF (o estado, ou o
   DF, e os municípios), nos exercícios pedidos. Guarda no estado, em ``conformidade-<UF>.json.gz``, só as
   entregas que a avaliação usa (contas anuais, RREO e RGF, inclusive os simplificados) e, por ente e
   exercício, se a consulta deu certo — um extrato que não veio não pode virar ausência do ente (RF-CF-07).
2. **Avaliação, na publicação** (``avaliar_ente``): cada obrigação vencida até a data da publicação é
   avaliada pelas funções de ``lumen_conformidade.entregas_siconfi``, com os prazos de
   ``lumen_deteccao.parametros_legais``. A avaliação roda a cada publicação, e não na coleta, porque um prazo
   que vence entre duas coletas muda o resultado sem que o extrato mude.

Exercícios: desde 2021 (``INICIO_HISTORICO``, o ano em que o PNCP começou e o painel de contratações também).
O anterior e o corrente são coletados de novo a cada execução, porque ainda recebem entregas e retificações; os
encerrados são coletados uma vez (``maximo_anteriores`` por execução, para caber no prazo do fluxo) e depois
reaproveitados do estado (``exercicios_a_coletar``).

Obrigações avaliadas (cada exercício coletado, o corrente até a data da publicação):

- contas anuais (DCA) do exercício anterior — LC 101/2000, art. 51;
- RREO de cada bimestre encerrado — art. 52;
- RGF de cada período encerrado, na periodicidade que o ente declarou (quadrimestral ou semestral, art. 63),
  separado por Poder no município (prefeitura e câmara) e só do Poder Executivo no estado e no DF — art. 55.

Quando o extrato tem RGF do período, mas de outra instituição, e nenhum da instituição procurada, o resultado
é indeterminado ("instituição não identificada"), e não "não consta": o nome que o Tesouro dá à instituição
varia, e a dúvida é do Lumen, não do ente.

Resultados publicados com a linguagem do DOC-08: "entregue no prazo", "entregue após o prazo", "não consta
no extrato" (com o prazo vencido) e "indeterminado" (com o motivo). O panorama ordena por UF e por nome, não
por resultado (PUB-07).
"""

from __future__ import annotations

import calendar
import re
import shutil
import tempfile
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

from lumen_canonico.fato import Esfera
from lumen_conformidade import entregas_siconfi as es
from lumen_deteccao.parametros_legais import ParametrosLegais
from lumen_ingestao.coleta_http import ErroColeta
from lumen_ingestao.portas import Janela, ResultadoCriterio
from lumen_normalizacao.silver import consolidar, ler_entidade
from lumen_normalizacao.transformacoes import chave_texto

from .cadastro import Cadastro
from .comum import (
    FUSO_BRASILIA,
    UFS,
    gravar_json,
    hoje_brasilia,
    instante_utc,
    ler_json,
    tipo_do_ente,
    uf_do_ente,
)

INICIO_HISTORICO = 2021
# Exercícios encerrados coletados por execução, além do anterior e do corrente: cada um custa uma consulta por
# ente, e o fluxo diário já usa perto do prazo com dois
MAXIMO_ANTERIORES = 1

COLUNAS_ENTREGAS = ["instituicao", "entregavel", "exercicio", "periodo", "periodicidade", "status", "entregue_em"]
ENTREGAVEIS = set(es._DCA) | set(es._RREO) | set(es._RGF)
ESFERAS = {"E": Esfera.ESTADUAL, "M": Esfera.MUNICIPAL, "D": Esfera.DISTRITAL}
# Instituição de cada Poder no extrato, procurada sem acento e sem caixa
PODERES_MUNICIPIO = (("executivo", "Poder Executivo", "prefeitura"), ("legislativo", "Poder Legislativo", "camara"))
PODERES_ESTADO = (("executivo", "Poder Executivo", "governo"),)
ROTULOS_RESULTADO = {
    "cumpre": "Entregue no prazo",
    "cumpre_parcialmente": "Entregue após o prazo",
    "nao_cumpre": "Não consta no extrato",
    "indeterminado": "Indeterminado",
}
ORDINAIS = {1: "1º", 2: "2º", 3: "3º", 4: "4º", 5: "5º", 6: "6º"}
_PARAM_URL = re.compile(r"[?&](id_ente|an_referencia)=([0-9]+)")


def nome_do_arquivo(uf: str) -> str:
    """``conformidade-SP.json.gz``."""
    return f"conformidade-{uf.upper()}.json.gz"


@dataclass(frozen=True)
class Entrega:
    """Uma entrega do extrato com os campos que ``entregas_siconfi`` lê (a forma compacta do estado)."""

    ente_codigo_ibge: str
    instituicao: str
    entregavel: str
    exercicio: int
    periodo: int
    periodicidade: str | None
    status_relatorio: str | None
    entregue_em: datetime | None

    def para_lista(self) -> list:
        """A linha do estado, na ordem de ``COLUNAS_ENTREGAS``."""
        return [self.instituicao, self.entregavel, self.exercicio, self.periodo, self.periodicidade,
                self.status_relatorio, self.entregue_em.isoformat() if self.entregue_em else None]

    @classmethod
    def da_lista(cls, ente: str, linha: list) -> "Entrega":
        """Reconstrói a entrega a partir da linha do estado."""
        instituicao, entregavel, exercicio, periodo, periodicidade, status, entregue = linha
        return cls(ente, instituicao, entregavel, int(exercicio), int(periodo), periodicidade, status,
                   _em_brasilia(entregue))


def _em_brasilia(iso: str | None) -> datetime | None:
    """Instante da entrega no horário de Brasília: o prazo legal é um dia do calendário local, e uma entrega
    às 22h do último dia (1h do dia seguinte em UTC) está dentro dele."""
    if not iso:
        return None
    instante = datetime.fromisoformat(iso)
    return instante.astimezone(FUSO_BRASILIA) if instante.tzinfo else instante


# ---------------------------------------------------------------------------------------------- coleta

def coletas_por_ente(registros: Iterable) -> dict[tuple[str, int], bool]:
    """Se o extrato de cada (ente, exercício) veio inteiro: todas as páginas com status 200 (ou 204).

    Lê o código do ente e o exercício da URL de cada registro do bronze (``id_ente`` e ``an_referencia``).
    """
    saida: dict[tuple[str, int], bool] = {}
    for r in registros:
        params = dict(_PARAM_URL.findall(r.url_solicitada or ""))
        if "id_ente" not in params or "an_referencia" not in params:
            continue
        chave = (params["id_ente"], int(params["an_referencia"]))
        saida[chave] = saida.get(chave, True) and r.status_http in (200, 204)
    return saida


def estado_da_uf(uf: str, entes: list[str], exercicios: list[int], silver: Path | str,
                 coletas: dict[tuple[str, int], bool], *, agora: str | None = None) -> dict:
    """O arquivo ``conformidade-<UF>.json.gz``: entregas relevantes e a situação da coleta de cada ente."""
    por_ente: dict[str, list[Entrega]] = {c: [] for c in entes}
    for linha in consolidar(ler_entidade(silver, "entrega_siconfi")):
        codigo = str(linha.get("ente_codigo_ibge"))
        if codigo not in por_ente or chave_texto(linha.get("entregavel")) not in ENTREGAVEIS:
            continue
        if int(linha.get("exercicio") or 0) not in exercicios:
            continue
        por_ente[codigo].append(Entrega(
            codigo, linha.get("instituicao") or "", linha.get("entregavel") or "", int(linha["exercicio"]),
            int(linha.get("periodo") or 0), linha.get("periodicidade"), linha.get("status_relatorio"),
            _em_brasilia(linha.get("entregue_em"))))
    return {
        "versao": 1, "uf": uf.upper(), "coletado_em": agora or instante_utc(), "exercicios": sorted(exercicios),
        "fonte": "SICONFI, extrato de entregas (/extrato_entregas), por ente e exercício",
        "colunas": COLUNAS_ENTREGAS,
        "entes": {c: {"coleta": {str(a): bool(coletas.get((c, a), False)) for a in sorted(exercicios)},
                      "entregas": [e.para_lista() for e in sorted(por_ente[c], key=lambda e: e.para_lista()[:4])]}
                  for c in sorted(por_ente)},
    }


def exercicios_a_coletar(anterior: dict | None, hoje: date, *, maximo_anteriores: int = MAXIMO_ANTERIORES,
                         inicio: int = INICIO_HISTORICO) -> tuple[list[int], list[int]]:
    """Quais exercícios coletar agora e quais manter do estado anterior da UF.

    O anterior e o corrente são sempre coletados. Um exercício encerrado que o estado já tem, com a consulta de
    todos os entes completa, é mantido; os que faltam (ou vieram com falha) entram na coleta, do mais recente
    para o mais antigo, até ``maximo_anteriores``.
    """
    abertos = [hoje.year - 1, hoje.year]
    coleta_anterior = {}
    if anterior:
        anos = {int(a) for a in anterior.get("exercicios") or []}
        for ano in anos:
            coleta_anterior[ano] = all((info.get("coleta") or {}).get(str(ano), False)
                                       for info in (anterior.get("entes") or {}).values())
    manter = sorted(a for a, completo in coleta_anterior.items() if completo and inicio <= a < abertos[0])
    faltam = [a for a in range(abertos[0] - 1, inicio - 1, -1) if a not in manter]
    return sorted(abertos + faltam[:maximo_anteriores]), manter


def juntar_estados(novo: dict, anterior: dict | None, manter: list[int]) -> dict:
    """O estado novo da UF com os exercícios ``manter`` (entregas e situação da coleta) do estado anterior."""
    if not anterior or not manter:
        return novo
    pos = COLUNAS_ENTREGAS.index("exercicio")
    for codigo, info in novo["entes"].items():
        antes = (anterior.get("entes") or {}).get(codigo) or {}
        info["entregas"] = sorted(info["entregas"] + [e for e in antes.get("entregas") or [] if int(e[pos]) in manter],
                                  key=lambda e: e[:4])
        for ano in manter:
            info["coleta"][str(ano)] = bool((antes.get("coleta") or {}).get(str(ano), False))
        info["coleta"] = dict(sorted(info["coleta"].items()))
    novo["exercicios"] = sorted(set(novo["exercicios"]) | set(manter))
    return novo


@dataclass
class ResultadoUf:
    """Resumo da coleta de uma UF para a saída do comando."""

    uf: str
    entes: int = 0
    exercicios: list[int] = field(default_factory=list)
    consultas_ok: int = 0
    consultas: int = 0
    gravado: bool = False
    problemas: list[str] = field(default_factory=list)

    def para_json(self) -> dict:
        """O resumo como dicionário."""
        return {"uf": self.uf, "entes": self.entes, "exercicios": self.exercicios, "consultas": self.consultas,
                "consultas_ok": self.consultas_ok,
                "gravado": self.gravado, "problemas": self.problemas}


def coletar_uf(cfg, uf: str, cadastro: Cadastro, exercicios: list[int] | None, estado: Path | str, *,
               coletar=None, normalizar=None, temporario: Path | None = None,
               maximo_anteriores: int = MAXIMO_ANTERIORES) -> ResultadoUf:
    """Coleta o extrato de entregas dos entes da UF e grava o estado da UF.

    Sem ``exercicios``, escolhe por ``exercicios_a_coletar``, a partir do estado já gravado; com eles, coleta
    exatamente esses. Os exercícios do estado anterior que não foram coletados agora são mantidos. Grava mesmo
    com consultas que falharam: o ente fica com a coleta marcada como malsucedida e a avaliação dele sai
    indeterminada. ``coletar`` e ``normalizar`` são as funções de ``lumen_orquestracao.etapas``.
    """
    if coletar is None or normalizar is None:
        from lumen_orquestracao import etapas
        coletar = coletar or etapas.coletar
        normalizar = normalizar or etapas.normalizar
    from lumen_ingestao.bronze import ArmazemBronzeLocal

    uf = uf.upper()
    entes = [e.codigo for e in cadastro.da_uf(uf)]
    resultado = ResultadoUf(uf, entes=len(entes))
    caminho = Path(estado) / nome_do_arquivo(uf)
    anterior = ler_json(caminho) if caminho.exists() and caminho.stat().st_size else None
    if anterior is not None and anterior.get("versao") != 1:
        anterior = None
    if exercicios is None:
        exercicios, manter = exercicios_a_coletar(anterior, hoje_brasilia(), maximo_anteriores=maximo_anteriores)
    else:
        manter = sorted({int(a) for a in (anterior or {}).get("exercicios") or []} - set(exercicios))
    resultado.exercicios = list(exercicios)
    if not entes:
        resultado.problemas.append("nenhum ente da UF no cadastro")
        return resultado
    raiz = Path(tempfile.mkdtemp(prefix=f"conformidade-{uf}-", dir=temporario))
    try:
        cfg_uf = replace(cfg, raiz_dados=raiz)
        hoje = hoje_brasilia()
        for exercicio in exercicios:
            try:
                coletar(cfg_uf, "siconfi_extrato", Janela(hoje, hoje), entes=entes, exercicio=exercicio)
            except ErroColeta as erro:
                resultado.problemas.append(f"{exercicio}: coleta interrompida ({type(erro).__name__}: {erro})")
        normalizar(cfg_uf, ["siconfi_extrato"])
        coletas = coletas_por_ente(ArmazemBronzeLocal(cfg_uf.bronze).listar_registros("siconfi_extrato"))
        resultado.consultas = len(entes) * len(exercicios)
        resultado.consultas_ok = sum(1 for c in entes for a in exercicios if coletas.get((c, a)))
        novo = estado_da_uf(uf, entes, exercicios, cfg_uf.silver, coletas)
        gravar_json(caminho, juntar_estados(novo, anterior, manter), comprimir=True)
        resultado.gravado = True
        return resultado
    finally:
        shutil.rmtree(raiz, ignore_errors=True)


# ---------------------------------------------------------------------------------------------- avaliação

def _fim_do_periodo(exercicio: int, periodo: int, meses: int) -> date:
    """Último dia do período de ``meses`` meses (2 no bimestre, 4 no quadrimestre, 6 no semestre)."""
    mes = periodo * meses
    return date(exercicio, mes, calendar.monthrange(exercicio, mes)[1])


def _item(a: es.AvaliacaoEntrega, exercicio: int, rotulo: str, poder: str | None) -> dict:
    """Uma obrigação avaliada, na forma do arquivo do ente."""
    resultado = a.avaliacao.resultado.value
    return {"exercicio": exercicio, "criterio": a.criterio, "periodo": a.periodo_referencia, "rotulo": rotulo,
            "poder": poder, "resultado": resultado, "rotulo_resultado": ROTULOS_RESULTADO[resultado],
            "prazo": a.prazo.isoformat() if a.prazo else None,
            "entregue_em": a.entregue_em.isoformat() if a.entregue_em else None,
            "dispositivo": a.avaliacao.dispositivo_legal, "motivo": a.avaliacao.motivo_indeterminado}


def _instituicao_nao_identificada(a: es.AvaliacaoEntrega, entregas: list[Entrega], exercicio: int,
                                  periodo: int) -> es.AvaliacaoEntrega:
    """Troca "não consta" por indeterminado quando há RGF do período de outra instituição (ver o módulo)."""
    if a.avaliacao.resultado is not ResultadoCriterio.NAO_CUMPRE:
        return a
    outros = [e for e in es._do_tipo(entregas, es._RGF) if e.exercicio == exercicio and e.periodo == periodo]
    if not outros:
        return a
    return replace(a, avaliacao=replace(
        a.avaliacao, resultado=ResultadoCriterio.INDETERMINADO,
        motivo_indeterminado="o extrato tem RGF do período, mas a instituição deste Poder não foi identificada "
                             "pelo nome; a ausência não pode ser atribuída ao ente"))


def avaliar_ente(codigo: str, esfera: str, entregas: list[Entrega], coleta: dict[str, bool], exercicios: list[int],
                 params: ParametrosLegais, hoje: date) -> list[dict]:
    """As obrigações do ente vencidas ou entregues até ``hoje``, nos exercícios coletados, já avaliadas."""
    esfera_enum = ESFERAS[esfera]
    poderes = PODERES_MUNICIPIO if esfera == "M" else PODERES_ESTADO
    saida: list[dict] = []
    for exercicio in sorted(exercicios):
        ok = bool(coleta.get(str(exercicio)))
        if exercicio < hoje.year:
            # As contas anuais são enviadas no ano seguinte, mas aparecem no extrato do próprio exercício
            a = es.avaliar_dca(codigo, esfera_enum, exercicio, entregas, params, hoje=hoje, coleta_ok=ok)
            saida.append(_item(a, exercicio, f"Contas anuais (DCA) de {exercicio}", None))
        for periodo in range(1, 7):
            if _fim_do_periodo(exercicio, periodo, 2) >= hoje:
                break
            a = es.avaliar_rreo(codigo, exercicio, periodo, entregas, params, hoje=hoje, coleta_ok=ok)
            saida.append(_item(a, exercicio, f"RREO do {ORDINAIS[periodo]} bimestre de {exercicio}", None))
        semestral = es.periodicidade_rgf_declarada(entregas, exercicio) == "S"
        meses, nome = (6, "semestre") if semestral else (4, "quadrimestre")
        for periodo in range(1, 12 // meses + 1):
            if _fim_do_periodo(exercicio, periodo, meses) >= hoje:
                break
            for chave, rotulo_poder, instituicao in poderes:
                a = es.avaliar_rgf(codigo, exercicio, periodo, entregas, params, hoje=hoje, coleta_ok=ok,
                                   instituicao_contem=instituicao)
                a = _instituicao_nao_identificada(a, entregas, exercicio, periodo)
                saida.append(_item(a, exercicio, f"RGF do {ORDINAIS[periodo]} {nome} de {exercicio} — {rotulo_poder}",
                                   chave))
    return saida


def por_exercicio(obrigacoes: list[dict]) -> dict[str, dict]:
    """O resumo de cada exercício, para o filtro de período do portal: ``{"2025": resumo, ...}``."""
    anos: dict[int, list[dict]] = {}
    for o in obrigacoes:
        anos.setdefault(int(o["exercicio"]), []).append(o)
    return {str(a): resumo(lista) for a, lista in sorted(anos.items())}


def resumo(obrigacoes: list[dict]) -> dict:
    """Quantas obrigações em cada resultado e a fração entregue no prazo entre as avaliáveis.

    Avaliáveis são as com resultado determinado (entregue no prazo, após o prazo ou não consta); as
    indeterminadas ficam de fora da fração e aparecem à parte.
    """
    contagem = {r: 0 for r in ROTULOS_RESULTADO}
    for o in obrigacoes:
        contagem[o["resultado"]] += 1
    avaliaveis = contagem["cumpre"] + contagem["cumpre_parcialmente"] + contagem["nao_cumpre"]
    return {**contagem, "avaliaveis": avaliaveis,
            "no_prazo": round(contagem["cumpre"] / avaliaveis, 4) if avaliaveis else None}


@dataclass
class Avaliacao:
    """Todas as UFs avaliadas numa publicação: por ente, as obrigações e o resumo."""

    hoje: date
    entes: dict[str, dict] = field(default_factory=dict)        # código → arquivo do ente
    coletas: dict[str, str] = field(default_factory=dict)       # UF → coletado_em


def avaliar(arquivos: Iterable[Path], cadastro: Cadastro, *, hoje: date | None = None,
            params: ParametrosLegais | None = None, gerado_em: str | None = None) -> Avaliacao:
    """Lê os estados por UF e avalia cada ente estadual, distrital e municipal na data ``hoje``."""
    hoje = hoje or hoje_brasilia()
    params = params or ParametrosLegais.carregar()
    gerado_em = gerado_em or instante_utc()
    avaliacao = Avaliacao(hoje)
    for caminho in sorted(arquivos, key=lambda p: p.name):
        dados = ler_json(caminho)
        if dados.get("versao") != 1:
            raise ValueError(f"{caminho}: versão {dados.get('versao')!r} do estado da conformidade não suportada")
        avaliacao.coletas[dados["uf"]] = dados.get("coletado_em")
        exercicios = [int(x) for x in dados.get("exercicios") or []]
        for codigo, info in (dados.get("entes") or {}).items():
            tipo = tipo_do_ente(codigo)
            ente = cadastro.get(codigo)
            esfera = (ente.esfera if ente and ente.esfera in ESFERAS else
                      {"estado": "E", "df": "D", "municipio": "M"}.get(tipo or ""))
            if esfera is None:
                continue
            entregas = [Entrega.da_lista(codigo, linha) for linha in info.get("entregas") or []]
            obrigacoes = avaliar_ente(codigo, esfera, entregas, info.get("coleta") or {}, exercicios, params, hoje)
            avaliacao.entes[codigo] = {
                "versao": 1, "tipo": "conformidade-ente", "gerado_em": gerado_em, "avaliado_em": hoje.isoformat(),
                "coletado_em": dados.get("coletado_em"),
                "ente": {"codigo": codigo, "nome": cadastro.nome(codigo), "uf": uf_do_ente(codigo), "tipo": tipo,
                         "populacao": ente.populacao if ente else None},
                "coleta": info.get("coleta") or {}, "resumo": resumo(obrigacoes),
                "por_exercicio": por_exercicio(obrigacoes), "obrigacoes": obrigacoes,
            }
    return avaliacao


def uf_para_json(uf: str, avaliacao: Avaliacao, gerado_em: str) -> dict:
    """``conformidade/uf/<sigla>.json``: os entes avaliados da UF, por nome, com o resumo de cada um."""
    entes = [{"codigo": c, "nome": a["ente"]["nome"], "tipo": a["ente"]["tipo"], "populacao": a["ente"]["populacao"],
              **a["resumo"], "por_exercicio": a["por_exercicio"]}
             for c, a in avaliacao.entes.items() if uf_do_ente(c) == uf]
    entes.sort(key=lambda x: (x["tipo"] != "estado" and x["tipo"] != "df", x["nome"].casefold(), x["codigo"]))
    return {"versao": 1, "tipo": "conformidade-uf", "gerado_em": gerado_em, "avaliado_em": avaliacao.hoje.isoformat(),
            "coletado_em": avaliacao.coletas.get(uf), "uf": uf, "entes": entes}


def panorama_para_json(avaliacao: Avaliacao, gerado_em: str) -> dict:
    """``conformidade/panorama.json``: por UF e por tipo de obrigação, em ordem de UF (PUB-07)."""
    ufs = []
    for uf in sorted(set(UFS.values())):
        da_uf = [a for c, a in avaliacao.entes.items() if uf_do_ente(c) == uf]
        todas = [o for a in da_uf for o in a["obrigacoes"]]
        ufs.append({"uf": uf, "entes": len(da_uf), "coletado_em": avaliacao.coletas.get(uf), **resumo(todas),
                    "por_exercicio": por_exercicio(todas)})
    por_criterio: dict[str, list[dict]] = {}
    for a in avaliacao.entes.values():
        for o in a["obrigacoes"]:
            por_criterio.setdefault(o["criterio"], []).append(o)
    nomes = {"dca_entregue_no_prazo": "Contas anuais (DCA)", "rreo_entregue_no_prazo": "RREO",
             "rgf_entregue_no_prazo": "RGF"}
    todas = [o for a in avaliacao.entes.values() for o in a["obrigacoes"]]
    return {"versao": 1, "tipo": "conformidade-panorama", "gerado_em": gerado_em,
            "avaliado_em": avaliacao.hoje.isoformat(), "entes": len(avaliacao.entes), "brasil": resumo(todas),
            "brasil_por_exercicio": por_exercicio(todas),
            "criterios": [{"criterio": c, "nome": nomes.get(c, c), **resumo(lista), "por_exercicio": por_exercicio(lista)}
                          for c, lista in sorted(por_criterio.items())],
            "ufs": ufs}
