"""Documentos de identificação: CNPJ e CPF.

Dois cuidados que este módulo centraliza para que nenhum outro precise
reinventar:

**CNPJ alfanumérico.** A Receita Federal passou a emitir, a partir de julho de
2026, CNPJ com letras nas doze primeiras posições (raiz e ordem); os dois
dígitos verificadores continuam numéricos. O cálculo do dígito usa, para cada
caractere, o valor do código ASCII menos 48: "0" a "9" continuam valendo 0 a
9 e "A" passa a valer 17. Com isso o algoritmo antigo é um caso particular do
novo, e um único validador serve aos dois formatos. Um sistema que validasse
só o formato numérico começaria a mandar para a quarentena, em silêncio, todo
fornecedor novo — exatamente o tipo de falha que o projeto não percebe porque
o pipeline continua verde.

**CPF nunca circula sem máscara.** Pela política do DOC-08 (seção 5.1) e pelo
RF-NO-10, o documento de pessoa física é mascarado na normalização, antes de
qualquer camada consultável. A máscara preserva só os seis dígitos centrais,
no mesmo formato adotado pelo Portal da Transparência (``***.456.789-**``),
o que permite conferir coincidência com publicações oficiais sem expor o
documento inteiro.
"""

from __future__ import annotations

import re
from enum import Enum

_PESOS_DV1 = (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
_PESOS_DV2 = (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
_CNPJ_FORMA = re.compile(r"^[0-9A-Z]{12}[0-9]{2}$")
_SEPARADORES = re.compile(r"[\s./\-]")


class TipoDocumento(str, Enum):
    """Classificação de um documento de pessoa, como ``classificar`` a devolve.

    ``INVALIDO`` cobre documento ausente, mal formado, com dígito verificador errado ou incoerente com o
    tipo de pessoa declarado; nessa condição o documento não segue para camadas consultáveis
    (``documento_publicavel`` devolve None).
    """

    CNPJ = "cnpj"
    CPF = "cpf"
    ESTRANGEIRO = "estrangeiro"
    INVALIDO = "invalido"


def limpar(documento: str | None) -> str:
    """Remove pontuação e espaços e põe letras em caixa alta."""
    if documento is None:
        return ""
    return _SEPARADORES.sub("", str(documento)).upper()


def _valor_caractere(c: str) -> int:
    """Valor do caractere no cálculo do dígito verificador: código ASCII menos 48 (0 a 9 nos dígitos, 17 no ``A``)."""
    return ord(c) - 48


def _dv(base: str, pesos: tuple[int, ...]) -> int:
    """Um dígito verificador pelo módulo 11 com os pesos dados: resto menor que 2 vira 0, senão 11 menos o resto.

    Cada caractere entra pelo ``_valor_caractere``, e por isso o mesmo cálculo serve ao CNPJ numérico e ao
    alfanumérico.
    """
    soma = sum(_valor_caractere(c) * p for c, p in zip(base, pesos))
    resto = soma % 11
    return 0 if resto < 2 else 11 - resto


def calcular_dv_cnpj(base12: str) -> str:
    """Os dois dígitos verificadores de uma base de 12 caracteres."""
    base12 = limpar(base12)
    if len(base12) != 12 or not re.fullmatch(r"[0-9A-Z]{12}", base12):
        raise ValueError(f"base de CNPJ precisa de 12 caracteres alfanuméricos: {base12!r}")
    dv1 = _dv(base12, _PESOS_DV1)
    dv2 = _dv(base12 + str(dv1), _PESOS_DV2)
    return f"{dv1}{dv2}"


def cnpj_valido(documento: str | None) -> bool:
    """CNPJ numérico ou alfanumérico com dígitos verificadores corretos."""
    d = limpar(documento)
    if not _CNPJ_FORMA.match(d):
        return False
    if d == d[0] * 14:  # 00000000000000 e similares passam no cálculo, mas não existem
        return False
    return calcular_dv_cnpj(d[:12]) == d[12:]


def cnpj_raiz(documento: str) -> str:
    """Os oito primeiros caracteres: identificam a empresa, todas as filiais."""
    d = limpar(documento)
    if not _CNPJ_FORMA.match(d):
        raise ValueError(f"CNPJ mal formado: {documento!r}")
    return d[:8]


def cpf_valido(documento: str | None) -> bool:
    """CPF de 11 dígitos com os dois dígitos verificadores corretos.

    Sequências de um só dígito repetido passam no cálculo, mas não são documentos reais, e são recusadas antes
    dele. O CPF não tem forma alfanumérica: qualquer letra torna o documento inválido.
    """
    d = limpar(documento)
    if not re.fullmatch(r"[0-9]{11}", d) or d == d[0] * 11:
        return False
    for tamanho in (9, 10):
        soma = sum(int(d[i]) * (tamanho + 1 - i) for i in range(tamanho))
        dv = (soma * 10) % 11 % 10
        if dv != int(d[tamanho]):
            return False
    return True


def mascarar_cpf(documento: str | None) -> str | None:
    """``12345678909`` → ``***.456.789-**``. Entrada inválida vira None.

    Devolver None, e não o texto original, é deliberado: um CPF mal digitado
    na fonte continua sendo dado pessoal, e não deve passar adiante só porque
    o dígito verificador não confere.
    """
    d = limpar(documento)
    if not re.fullmatch(r"[0-9]{11}", d):
        return None
    return f"***.{d[3:6]}.{d[6:9]}-**"


def classificar(documento: str | None, tipo_pessoa: str | None = None) -> TipoDocumento:
    """Classifica pelo tipo de pessoa declarado e, na falta dele, pelo formato.

    O PNCP declara ``tipoPessoa`` (PJ, PF ou PE, pessoa estrangeira). Quando
    o tipo é declarado, ele manda: um "PF" com 14 dígitos é inconsistência da
    fonte e vira INVALIDO, nunca é reinterpretado como CNPJ.
    """
    d = limpar(documento)
    tipo = (tipo_pessoa or "").strip().upper()
    if tipo == "PE":
        return TipoDocumento.ESTRANGEIRO
    if tipo == "PF":
        return TipoDocumento.CPF if cpf_valido(d) else TipoDocumento.INVALIDO
    if tipo == "PJ":
        return TipoDocumento.CNPJ if cnpj_valido(d) else TipoDocumento.INVALIDO
    if cnpj_valido(d):
        return TipoDocumento.CNPJ
    if cpf_valido(d):
        return TipoDocumento.CPF
    return TipoDocumento.INVALIDO


def documento_publicavel(documento: str | None, tipo_pessoa: str | None = None) -> str | None:
    """O documento na forma em que pode seguir para camadas consultáveis.

    CNPJ segue limpo e inteiro (é dado público de pessoa jurídica); CPF segue
    mascarado; estrangeiro segue como veio, sem pontuação; inválido não segue.
    """
    tipo = classificar(documento, tipo_pessoa)
    if tipo is TipoDocumento.CNPJ:
        return limpar(documento)
    if tipo is TipoDocumento.CPF:
        return mascarar_cpf(documento)
    if tipo is TipoDocumento.ESTRANGEIRO:
        d = limpar(documento)
        return d or None
    return None
