"""Regra J-01 em modo silencioso: contrato assinado com fornecedor que constava num cadastro de sanções.

A pergunta do DOC-07 é se, na data da assinatura, o fornecedor estava num cadastro da CGU que o impedia
de contratar. Este módulo cruza os contratos do painel (um arquivo por dia do PNCP, ADR-028) com as sanções
da silver (CEIS e CNEP, ADR-030) e devolve as coincidências **para análise**. Nada daqui é publicado: o
relatório vai para o armazenamento privado, e o resumo público só tem contagens (ADR-031).

Como a coincidência é decidida:

1. **Mesmo CNPJ.** Só pessoa jurídica: o arquivo do dia do painel não guarda documento de pessoa física
   (RNF-19 e RNF-20), e o CPF da sanção é mascarado.
2. **Sanção que impede contratar.** Impedimento ou proibição de contratar, suspensão e declaração de
   inidoneidade. Multa, publicação extraordinária, demissão e interdição de atividades não entram. O CEPIM
   também não: ele impede transferências voluntárias (convênios), não contratos.
3. **Vigente na assinatura.** Início da sanção até a data da assinatura; fim depois dela, ou sem fim.
4. **Alcance**, pela abrangência que o órgão sancionador publicou, comparada com a esfera e a UF de quem
   contratou. A CGU não publica o município do órgão sancionador, e o nome do órgão não casa com
   segurança com o do PNCP: esses casos ficam "a conferir", e não descartados.

Limites conhecidos (os falsos positivos do DOC-07): o cadastro é o retrato de hoje, então uma sanção já
excluída não aparece (falso negativo) e uma sanção suspensa por decisão judicial pode aparecer; a inclusão
retroativa no cadastro faz parecer que a sanção já constava na assinatura.
"""

from __future__ import annotations

import gzip
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator

from lumen_normalizacao.transformacoes import chave_texto

VERSAO_RELATORIO = 1

# Alcance da sanção sobre a contratação, do mais para o menos claro.
TODAS_AS_ESFERAS = "todas_as_esferas"
MESMA_ESFERA = "mesma_esfera"
MESMO_ORGAO = "mesmo_orgao"
A_CONFERIR = "a_conferir"
NAO_INFORMADO = "abrangencia_nao_informada"
FORA_DO_ALCANCE = "fora_do_alcance"
ALCANCES = (TODAS_AS_ESFERAS, MESMA_ESFERA, MESMO_ORGAO, A_CONFERIR, NAO_INFORMADO)

CADASTROS_DE_CONTRATACAO = ("CEIS", "CNEP")
PREFIXOS_QUE_IMPEDEM = ("impedimento/proibicao de contratar", "suspensao", "declaracao de inidoneidade")
PREFIXOS_QUE_NAO_IMPEDEM = ("suspensao/interdicao",)
ESFERAS_DO_PAINEL = {"F": "uniao", "E": "estadual", "M": "municipal", "D": "distrital"}
LIMITE_TEXTO = 300


def impede_contratar(categoria: str | None) -> bool:
    """A categoria da sanção impede o sancionado de contratar com a administração?"""
    c = chave_texto(categoria)
    if not c or c.startswith(PREFIXOS_QUE_NAO_IMPEDEM):
        return False
    return c.startswith(PREFIXOS_QUE_IMPEDEM)


def _data(texto: str | None) -> date | None:
    """Data ISO (``AAAA-MM-DD``) do registro; vazio ou ilegível vira None."""
    try:
        return date.fromisoformat(str(texto)[:10]) if texto else None
    except ValueError:
        return None


def vigente(sancao: dict, dia: date) -> bool:
    """A sanção valia em ``dia``: começou nele ou antes, e não terminou antes dele."""
    inicio, fim = _data(sancao.get("data_inicio")), _data(sancao.get("data_fim"))
    return inicio is not None and inicio <= dia and (fim is None or dia <= fim)


def _palavras(texto: str | None) -> str:
    """Texto sem acento, em minúsculas, com pontuação trocada por espaço e cercado de espaços.

    É a forma em que o nome de um município é procurado no nome do órgão sancionador, palavra por palavra:
    `` lajeado `` casa com "PREFEITURA MUNICIPAL DE LAJEADO - RS", e não com "Lajeado Novo".
    """
    return f" {' '.join(re.sub(r'[^a-z0-9]+', ' ', chave_texto(texto)).split())} "


class Municipios:
    """Nomes dos municípios por UF, para achar o município citado no nome do órgão sancionador.

    A CGU publica a UF do órgão sancionador, mas não o município; quase sempre ele está no nome
    ("Prefeitura Municipal de Lajeado - RS").
    """

    def __init__(self, registros: Iterable[tuple[str, str, str]]):
        """Recebe (código IBGE, sigla da UF, nome) de cada município."""
        self._por_uf: dict[str, list[tuple[str, str]]] = {}
        for ibge, uf, nome in registros:
            self._por_uf.setdefault(uf.upper(), []).append((_palavras(nome), ibge))

    @classmethod
    def do_cadastro(cls) -> "Municipios":
        """Os 5.570 municípios do cadastro que acompanha o Lumen (o mesmo da aba Eleições)."""
        from importlib.resources import files
        dados = json.loads(files("lumen_eleicoes").joinpath("dados/municipios.json").read_text(encoding="utf-8"))
        return cls((m["ibge"], m["uf"], m["nome"]) for m in dados["municipios"] if m.get("ibge"))

    def citados(self, texto: str | None, uf: str | None) -> set[str]:
        """Códigos IBGE dos municípios da ``uf`` cujo nome aparece inteiro no ``texto``."""
        alvo = _palavras(texto)
        return {ibge for nome, ibge in self._por_uf.get((uf or "").upper(), []) if nome in alvo}


def alcance(sancao: dict, esfera_contratante: str | None, uf_contratante: str | None, *,
            municipio_contratante: str | None = None, orgao_contratante: str | None = None,
            municipios: Municipios | None = None) -> str:
    """Se a sanção alcança quem contratou, pela abrangência publicada, pela esfera, pela UF e pelo município.

    "Todas as esferas" alcança qualquer um. "Na esfera do órgão sancionador" alcança a mesma esfera: na
    estadual e na distrital, também a mesma UF; na municipal, o mesmo município, quando o nome do órgão
    sancionador o cita (cita outro: fora do alcance; não cita nenhum: a conferir). "No órgão sancionador"
    passa pelas mesmas condições e, no fim, depende do órgão: com o mesmo nome, ``mesmo_orgao``; com nome
    diferente (o PNCP e a CGU escrevem o mesmo órgão de jeitos diferentes), a conferir. Sem abrangência
    publicada, ``abrangencia_nao_informada``.
    """
    texto = chave_texto(sancao.get("abrangencia"))
    if not texto:
        return NAO_INFORMADO
    if "todas as esferas" in texto:
        return TODAS_AS_ESFERAS
    restrita_ao_orgao = "no orgao sancionador" in texto or "outro orgao" in texto
    if not (restrita_ao_orgao or "esfera do orgao sancionador" in texto or "na esfera e no poder" in texto):
        return A_CONFERIR
    esfera = sancao.get("esfera_orgao_sancionador")
    uf = sancao.get("uf_orgao_sancionador")
    if not esfera or not esfera_contratante:
        return A_CONFERIR
    if esfera != esfera_contratante:
        # O Distrito Federal acumula as competências de estado e de município.
        distrito = "distrital" in (esfera, esfera_contratante) and uf == uf_contratante == "DF"
        return A_CONFERIR if distrito else FORA_DO_ALCANCE
    if esfera != "uniao":
        if not uf or not uf_contratante:
            return A_CONFERIR
        if uf != uf_contratante:
            return FORA_DO_ALCANCE
    if esfera == "municipal":
        citados = municipios.citados(sancao.get("orgao_sancionador"), uf) if municipios else set()
        if not citados or not municipio_contratante:
            return A_CONFERIR
        if municipio_contratante not in citados:
            return FORA_DO_ALCANCE
    if restrita_ao_orgao:
        mesmo = orgao_contratante and _palavras(orgao_contratante) == _palavras(sancao.get("orgao_sancionador"))
        return MESMO_ORGAO if mesmo else A_CONFERIR
    return MESMA_ESFERA


def retrato_mais_recente(sancoes: Iterable[dict]) -> list[dict]:
    """Só as sanções do retrato mais recente de cada cadastro: a que saiu do cadastro não conta mais."""
    lista = list(sancoes)
    recentes: dict[str, str] = {}
    for s in lista:
        ref = s.get("data_referencia") or ""
        if ref > recentes.get(s.get("cadastro") or "", ""):
            recentes[s.get("cadastro") or ""] = ref
    return [s for s in lista if (s.get("data_referencia") or "") == recentes.get(s.get("cadastro") or "", "")]


def indice_por_cnpj(sancoes: Iterable[dict]) -> dict[str, list[dict]]:
    """Sanções que impedem contratar, do CEIS e do CNEP, por CNPJ do sancionado."""
    indice: dict[str, list[dict]] = {}
    for s in retrato_mais_recente(sancoes):
        documento = s.get("documento") or ""
        if (s.get("cadastro") in CADASTROS_DE_CONTRATACAO and s.get("tipo_pessoa") == "PJ" and len(documento) == 14
                and impede_contratar(s.get("categoria"))):
            indice.setdefault(documento, []).append(s)
    return indice


def ler_dias(estado: Path | str) -> Iterator[dict]:
    """Os arquivos do dia do painel (``contratacoes-AAAA-MM-DD.json.gz``) do diretório, em ordem de data."""
    for caminho in sorted(Path(estado).glob("contratacoes-*.json.gz")):
        if caminho.stat().st_size == 0:
            continue
        with gzip.open(caminho, "rt", encoding="utf-8") as fh:
            dados = json.load(fh)
        if dados.get("versao") != 1:
            raise ValueError(f"{caminho.name}: versão {dados.get('versao')!r} do arquivo do dia não suportada")
        yield dados


def _curto(texto: str | None) -> str | None:
    """Texto cortado em ``LIMITE_TEXTO`` caracteres, para o relatório não carregar fundamentações inteiras."""
    if not texto:
        return None
    return texto if len(texto) <= LIMITE_TEXTO else texto[: LIMITE_TEXTO - 1].rstrip() + "…"


@dataclass
class Relatorio:
    """O que o cruzamento encontrou: as coincidências para análise e as contagens que o resumo mostra."""

    coincidencias: list[dict] = field(default_factory=list)
    dias: list[str] = field(default_factory=list)
    contratos: int = 0
    contratos_com_cnpj: int = 0
    sem_data_assinatura: int = 0
    fora_do_alcance: int = 0
    retratos: dict[str, str] = field(default_factory=dict)
    sancoes_no_indice: int = 0

    def por_alcance(self) -> dict[str, int]:
        """Coincidências por alcance, na ordem de ``ALCANCES``, com zero onde não houve nenhuma."""
        contagem = Counter(c["alcance"] for c in self.coincidencias)
        return {a: contagem.get(a, 0) for a in ALCANCES}

    def para_json(self, gerado_em: str | None = None) -> dict:
        """O relatório completo, com as coincidências: só para o armazenamento privado."""
        return {
            "versao": VERSAO_RELATORIO, "regra": "J-01", "modo": "silencioso",
            "gerado_em": gerado_em or datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "retratos_das_sancoes": self.retratos, "sancoes_que_impedem_contratar": self.sancoes_no_indice,
            "dias_de_contratos": {"quantidade": len(self.dias), "de": min(self.dias, default=None),
                                  "ate": max(self.dias, default=None)},
            "contratos": self.contratos, "contratos_com_cnpj": self.contratos_com_cnpj,
            "sem_data_assinatura": self.sem_data_assinatura, "fora_do_alcance": self.fora_do_alcance,
            "por_alcance": self.por_alcance(),
            "fornecedores_distintos": len({c["fornecedor"]["cnpj"] for c in self.coincidencias}),
            "coincidencias": self.coincidencias,
        }

    def resumo_markdown(self) -> str:
        """Resumo só com contagens, sem nome de fornecedor nem de órgão: é o que pode aparecer em público."""
        linhas = [
            "### Regra J-01 em modo silencioso (sanções da CGU × contratos do PNCP)",
            "",
            f"- Retratos das sanções: {', '.join(f'{k} de {v}' for k, v in sorted(self.retratos.items())) or 'nenhum'}",
            f"- Dias de contratos: {len(self.dias)} ({min(self.dias, default='-')} a {max(self.dias, default='-')})",
            f"- Contratos lidos: {self.contratos} ({self.contratos_com_cnpj} com CNPJ do fornecedor)",
            f"- Coincidências para análise: {len(self.coincidencias)}, de "
            f"{len({c['fornecedor']['cnpj'] for c in self.coincidencias})} fornecedores",
            "",
            "| Alcance da sanção | Coincidências |",
            "|---|---|",
            *[f"| {a.replace('_', ' ')} | {n} |" for a, n in self.por_alcance().items()],
            f"| fora do alcance (não listadas) | {self.fora_do_alcance} |",
            "",
            "O detalhe fica no armazenamento privado: nada disto é publicado (ADR-031).",
        ]
        return "\n".join(linhas) + "\n"


def cruzar(dias: Iterable[dict], sancoes: Iterable[dict], municipios: Municipios | None = None) -> Relatorio:
    """Cruza os contratos dos ``dias`` do painel com as ``sancoes`` da silver e devolve o relatório.

    Sem ``municipios``, as sanções municipais de abrangência restrita ficam todas a conferir.
    """
    lista = list(sancoes)
    indice = indice_por_cnpj(lista)
    relatorio = Relatorio(sancoes_no_indice=sum(len(v) for v in indice.values()))
    for s in retrato_mais_recente(lista):
        relatorio.retratos[s.get("cadastro")] = s.get("data_referencia")
    for dia in dias:
        relatorio.dias.append(dia["dia"])
        colunas = dia["colunas"]["contratos"]
        orgaos = dia.get("orgaos", {})
        for linha in dia.get("contratos", []):
            c = dict(zip(colunas, linha))
            relatorio.contratos += 1
            cnpj = c.get("fornecedor_cnpj")
            if not cnpj:
                continue
            relatorio.contratos_com_cnpj += 1
            candidatas = indice.get(cnpj)
            if not candidatas:
                continue
            assinatura = _data(c.get("data_assinatura"))
            if assinatura is None:
                relatorio.sem_data_assinatura += 1
                continue
            razao, esfera_codigo, _ = (orgaos.get(c.get("orgao") or "") or [None, None, None])
            esfera = ESFERAS_DO_PAINEL.get(esfera_codigo or "")
            for s in candidatas:
                if not vigente(s, assinatura):
                    continue
                a = alcance(s, esfera, c.get("uf"), municipio_contratante=c.get("municipio"),
                            orgao_contratante=razao, municipios=municipios)
                if a == FORA_DO_ALCANCE:
                    relatorio.fora_do_alcance += 1
                    continue
                relatorio.coincidencias.append(_coincidencia(c, razao, esfera, s, a))
    relatorio.coincidencias.sort(key=lambda x: (ALCANCES.index(x["alcance"]), x["contrato"]["data_assinatura"],
                                                x["contrato"]["chave"] or ""))
    return relatorio


def _coincidencia(c: dict, orgao_nome: str | None, esfera: str | None, s: dict, a: str) -> dict:
    """Uma coincidência no formato do relatório: o contrato, o fornecedor, a sanção e o alcance."""
    from lumen_painel.comum import link_pncp
    return {
        "alcance": a,
        "contrato": {"chave": c.get("chave"), "link_pncp": link_pncp(c.get("chave")),
                     "orgao_cnpj": c.get("orgao"), "orgao": orgao_nome, "esfera": esfera, "uf": c.get("uf"),
                     "municipio": c.get("municipio"), "data_assinatura": c.get("data_assinatura"),
                     "valor_global": c.get("valor_global"), "objeto": c.get("objeto")},
        "fornecedor": {"cnpj": c.get("fornecedor_cnpj"), "nome": c.get("fornecedor_nome")},
        "sancao": {"cadastro": s.get("cadastro"), "codigo": s.get("chave_origem"), "categoria": s.get("categoria"),
                   "data_inicio": s.get("data_inicio"), "data_fim": s.get("data_fim"),
                   "abrangencia": s.get("abrangencia"), "orgao_sancionador": s.get("orgao_sancionador"),
                   "esfera": s.get("esfera_orgao_sancionador"), "uf": s.get("uf_orgao_sancionador"),
                   "fundamentacao_legal": _curto(s.get("fundamentacao_legal")),
                   "data_referencia": s.get("data_referencia")},
    }
