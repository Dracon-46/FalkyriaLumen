"""Regra A-05: preço pago acima da referência de mercado de fora do governo (DOC-07, família A; ADR-027).

Para cada item de compra pública reconhecido (``especificacao``), monta a referência de mercado no lugar e
na época da compra (ANP para combustível e gás de cozinha, varejo para informática) e calcula a razão entre o preço unitário
e a mediana dessa referência. A regra roda em **modo silencioso**: o resultado vai para um relatório
interno, com a referência inteira ao lado, e nada é publicado nem vira indício até a calibração.

O preço comparado é o homologado (o do resultado do item, que é o que foi efetivamente contratado). Sem
resultado, entra o estimado, marcado como tal: estimativa acima do mercado também interessa (a pesquisa de
preços da própria compra pode ter sido feita só com orçamentos altos), mas é outro fato e o relatório não
mistura os dois.

A data de referência é a do resultado; sem ela, a da publicação da compra. O lugar é o município da unidade
compradora, com o nome tirado do cadastro do IBGE (entidade ``ente_federativo`` da silver).
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal
from importlib import resources
from pathlib import Path
from typing import Iterable, Iterator

from . import VERSAO_REGRA
from .anp import PrecosAnp
from .especificacao import GAS_DE_COZINHA, Especificacao, reconhecer
from .referencia import ReferenciaMercado
from .varejo import OfertasVarejo

ACIMA = "acima_da_referencia"
DENTRO = "dentro_da_referencia"
SEM_REFERENCIA = "sem_referencia"
NAO_COMPARAVEL = "nao_comparavel"


@dataclass(frozen=True)
class ParametrosMercado:
    """Parâmetros lidos de ``parametros_mercado.toml`` (ou de outro arquivo, nos testes)."""

    modo: str
    valor_total_minimo_destaque: Decimal
    combustivel_limiar: Decimal
    combustivel_janela: int
    combustivel_minimo_municipio: int
    combustivel_minimo_uf: int
    gas_de_cozinha_limiar: Decimal
    varejo_limiar: Decimal
    varejo_janela: int
    varejo_minimo_ofertas: int
    consultas_padrao: tuple[str, ...]
    calibrado: bool

    @classmethod
    def carregar(cls, caminho: Path | None = None) -> "ParametrosMercado":
        """Lê o arquivo de parâmetros; sem caminho, o que vem com o pacote."""
        if caminho is None:
            texto = resources.files("lumen_mercado").joinpath("parametros_mercado.toml").read_text(encoding="utf-8")
        else:
            texto = Path(caminho).read_text(encoding="utf-8")
        d = tomllib.loads(texto)
        g, c, v = d["geral"], d["combustivel"], d["varejo"]
        gas = d.get("gas_de_cozinha", {})   # sem a seção, o gás usa o limiar do combustível
        return cls(modo=g["modo"], valor_total_minimo_destaque=Decimal(g["valor_total_minimo_destaque"]),
                   combustivel_limiar=Decimal(c["limiar_razao"]), combustivel_janela=int(c["janela_dias"]),
                   combustivel_minimo_municipio=int(c["minimo_municipio"]), combustivel_minimo_uf=int(c["minimo_uf"]),
                   gas_de_cozinha_limiar=Decimal(gas.get("limiar_razao", c["limiar_razao"])),
                   varejo_limiar=Decimal(v["limiar_razao"]), varejo_janela=int(v["janela_dias"]),
                   varejo_minimo_ofertas=int(v["minimo_ofertas"]),
                   consultas_padrao=tuple(v.get("consultas_padrao", {}).get("consultas", [])),
                   calibrado=bool(c.get("calibrado")) and bool(v.get("calibrado"))
                   and (not gas or bool(gas.get("calibrado"))))


@dataclass(frozen=True)
class ItemParaComparar:
    """Um item da silver com o processo e o resultado que o acompanham."""

    processo: dict
    item: dict
    resultado: dict | None = None


@dataclass
class Comparacao:
    """Resultado da regra A-05 para um item: o que foi pago, contra qual referência, e a distância.

    ``situacao`` é ``acima_da_referencia`` (razão no limiar ou acima), ``dentro_da_referencia``,
    ``sem_referencia`` (o item é comparável, mas faltou amostra de mercado na época e no lugar) ou
    ``nao_comparavel`` (o item não foi reconhecido; só aparece nas contagens).
    """

    item_id: str
    processo: str
    orgao_cnpj: str | None
    uf: str | None
    municipio_codigo_ibge: str | None
    municipio: str | None
    data_referencia: date
    descricao: str
    unidade_medida: str | None
    quantidade: Decimal | None
    preco_unitario: Decimal | None
    tipo_preco: str
    valor_total: Decimal | None
    especificacao: Especificacao | None
    situacao: str
    motivo: str
    referencia: ReferenciaMercado | None = None
    razao: Decimal | None = None
    limiar: Decimal | None = None
    fornecedor: str | None = None
    regra: str = VERSAO_REGRA
    modo: str = "silencioso"
    marcacoes: list[str] = field(default_factory=list)

    def para_dict(self) -> dict:
        """Forma serializável para o relatório (dinheiro e razão em texto, datas em ISO 8601)."""
        e = self.especificacao
        return {
            "regra": self.regra, "modo": self.modo, "situacao": self.situacao, "motivo": self.motivo,
            "item_id": self.item_id, "processo": self.processo, "orgao_cnpj": self.orgao_cnpj, "uf": self.uf,
            "municipio_codigo_ibge": self.municipio_codigo_ibge, "municipio": self.municipio,
            "data_referencia": self.data_referencia.isoformat(), "descricao": self.descricao,
            "unidade_medida": self.unidade_medida, "quantidade": _texto(self.quantidade),
            "preco_unitario": _texto(self.preco_unitario), "tipo_preco": self.tipo_preco,
            "valor_total": _texto(self.valor_total), "fornecedor": self.fornecedor,
            "categoria": e.categoria if e else None, "produto": e.produto if e else None,
            "referencia": self.referencia.para_dict() if self.referencia else None,
            "razao": _texto(self.razao), "limiar": _texto(self.limiar), "marcacoes": list(self.marcacoes),
        }


def _texto(valor: Decimal | None) -> str | None:
    """``Decimal`` em texto, ou None."""
    return None if valor is None else str(valor)


def _decimal(valor) -> Decimal | None:
    """Valor da silver (texto ou número) em ``Decimal``; None se ausente."""
    return None if valor in (None, "") else Decimal(str(valor))


def itens_da_silver(processos: Iterable[dict], itens: Iterable[dict], resultados: Iterable[dict]) -> Iterator[ItemParaComparar]:
    """Junta itens, processos e resultados (já consolidados) pelos ids canônicos.

    Do item com mais de um resultado, vale o primeiro não cancelado (menor sequencial).
    """
    por_processo = {p["id"]: p for p in processos}
    por_item: dict[str, dict] = {}
    for r in sorted(resultados, key=lambda r: (r["item_id"], r.get("sequencial_resultado") or 0)):
        if r.get("cancelado"):
            continue
        por_item.setdefault(r["item_id"], r)
    for i in itens:
        p = por_processo.get(i["processo_id"])
        if p is None:
            continue
        yield ItemParaComparar(processo=p, item=i, resultado=por_item.get(i["id"]))


def _preco(entrada: ItemParaComparar) -> tuple[Decimal | None, str, Decimal | None, date]:
    """(preço unitário, tipo, quantidade, data de referência): homologado se houver resultado, senão estimado."""
    i, r, p = entrada.item, entrada.resultado, entrada.processo
    data_publicacao = date.fromisoformat(p["data_publicacao"])
    if r and _decimal(r.get("valor_unitario_homologado")) is not None:
        quando = date.fromisoformat(r["data_resultado"]) if r.get("data_resultado") else data_publicacao
        return (_decimal(r["valor_unitario_homologado"]), "homologado",
                _decimal(r.get("quantidade_homologada")) or _decimal(i.get("quantidade")), quando)
    return _decimal(i.get("valor_unitario_estimado")), "estimado", _decimal(i.get("quantidade")), data_publicacao


def comparar(entradas: Iterable[ItemParaComparar], parametros: ParametrosMercado, *,
             anp: PrecosAnp | None = None, varejo: OfertasVarejo | None = None,
             municipios: dict[str, str] | None = None) -> Iterator[Comparacao]:
    """Aplica a regra A-05 a cada item e devolve a comparação, inclusive dos não comparáveis.

    ``municipios`` é {código IBGE: nome}, para achar o município nas coletas da ANP; sem o nome, a
    referência de combustível e de gás de cozinha usa a UF inteira.
    """
    municipios = municipios or {}
    for e in entradas:
        i, p, r = e.item, e.processo, e.resultado
        preco, tipo, quantidade, quando = _preco(e)
        espec = reconhecer(i.get("descricao_original"), i.get("unidade_medida"))
        codigo = p.get("municipio_codigo_ibge")
        base = dict(
            item_id=i["id"], processo=p.get("chave_origem") or p["id"], orgao_cnpj=p.get("orgao_cnpj"),
            uf=p.get("uf"), municipio_codigo_ibge=codigo, municipio=municipios.get(codigo or ""),
            data_referencia=quando, descricao=i.get("descricao_original") or "", unidade_medida=i.get("unidade_medida"),
            quantidade=quantidade, preco_unitario=preco, tipo_preco=tipo,
            valor_total=(preco * quantidade).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
            if preco is not None and quantidade is not None else None,
            especificacao=espec, fornecedor=(r or {}).get("fornecedor_nome"),
            modo=parametros.modo)
        if espec is None:
            yield Comparacao(**base, situacao=NAO_COMPARAVEL, motivo="item não reconhecido com segurança")
            continue
        if preco is None:
            yield Comparacao(**base, situacao=SEM_REFERENCIA, motivo="item sem preço unitário publicado")
            continue
        if espec.referencia == "anp":
            limiar = (parametros.gas_de_cozinha_limiar if espec.categoria == GAS_DE_COZINHA
                      else parametros.combustivel_limiar)
            if anp is None:
                ref, motivo = None, "preços da ANP não carregados"
            else:
                ref = anp.referencia(espec.produto, p.get("uf") or "", base["municipio"], quando,
                                     janela_dias=parametros.combustivel_janela,
                                     minimo_municipio=parametros.combustivel_minimo_municipio,
                                     minimo_uf=parametros.combustivel_minimo_uf)
                motivo = "sem coletas da ANP suficientes no município nem na UF em torno da data"
        else:
            limiar = parametros.varejo_limiar
            if varejo is None:
                ref, motivo = None, "ofertas de varejo não carregadas"
            else:
                ref = varejo.referencia(espec, quando, janela_dias=parametros.varejo_janela,
                                        minimo_ofertas=parametros.varejo_minimo_ofertas)
                motivo = "sem ofertas comparáveis suficientes em torno da data"
        if ref is None:
            yield Comparacao(**base, situacao=SEM_REFERENCIA, motivo=motivo, limiar=limiar)
            continue
        razao = (preco / ref.mediana).quantize(Decimal("0.001"), rounding=ROUND_HALF_EVEN)
        marcas = []
        if preco > ref.maximo:
            marcas.append("acima_do_maior_preco_observado")
        if ref.escopo != "municipio" and espec.referencia == "anp":
            marcas.append(f"referencia_da_{ref.escopo}")
        if tipo == "estimado":
            marcas.append("preco_estimado")
        if razao >= limiar:
            situacao = ACIMA
            motivo = f"preço unitário {razao}× a mediana da referência (limiar {limiar}×)"
        else:
            situacao = DENTRO
            motivo = f"preço unitário {razao}× a mediana da referência"
        yield Comparacao(**base, situacao=situacao, motivo=motivo, referencia=ref, razao=razao, limiar=limiar,
                         marcacoes=marcas)
