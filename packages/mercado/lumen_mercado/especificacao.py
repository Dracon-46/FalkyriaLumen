"""O que um item de compra pública é, quando dá para comparar com o mercado (ADR-027, seção 3).

A descrição de um item no PNCP é texto livre, escrito pelo servidor, e quase nunca traz código de catálogo
(a amostra real em ``testes/fixtures/pncp`` não traz). Comparar com o mercado só faz sentido quando o item
é identificável sem ambiguidade; na dúvida, ``reconhecer`` devolve ``None`` e o item fica fora da regra.
Errar para o lado de não comparar custa uma comparação a menos; errar para o outro lado é comparar
produtos diferentes e apontar uma diferença que não existe.

Três famílias, por enquanto:

- **combustíveis** (gasolina comum e aditivada, etanol, diesel S10 e S500, GNV), comparados com o preço de
  bomba da ANP. Exige unidade em litro (ou m³ no GNV): fornecimento por cartão, taxa de administração e
  gestão de frota são serviços, não o combustível, e ficam de fora pela unidade e pelas palavras;
- **gás de cozinha** (GLP no botijão de 13 kg, o P13), comparado com o preço de revenda da ANP, que é o do
  botijão cheio com a troca do vazio. Exige que o texto diga 13 kg (ou P13) e que a unidade seja o botijão
  ou a recarga; vasilhame novo, botijão completo, regulador e os outros tamanhos ficam de fora;
- **informática padronizada** (notebook, monitor, impressora), comparada com ofertas do varejo. Exige os
  atributos que definem o preço (processador, memória e armazenamento no notebook; polegadas no monitor;
  tecnologia na impressora). A oferta só conta se o título contiver todos eles (``termos``).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

COMBUSTIVEL = "combustivel"
GAS_DE_COZINHA = "gas_de_cozinha"
NOTEBOOK = "notebook"
MONITOR = "monitor"
IMPRESSORA = "impressora"

# Produtos como a ANP os nomeia na série histórica; o diesel sem indicação é o S500.
GASOLINA = "GASOLINA"
GASOLINA_ADITIVADA = "GASOLINA ADITIVADA"
ETANOL = "ETANOL"
DIESEL_S10 = "DIESEL S10"
DIESEL_S500 = "DIESEL"
GNV = "GNV"
GLP = "GLP"

# Unidade em que cada produto da ANP é comparado: o preço de bomba é por litro, o GNV por metro cúbico e o
# gás de cozinha pelo botijão de 13 kg.
UNIDADE_ANP = {GNV: "m3", GLP: "botijao_13kg"}


def unidade_do_produto(produto: str) -> str:
    """Unidade em que o preço da ANP desse produto é publicado (``litro``, ``m3`` ou ``botijao_13kg``)."""
    return UNIDADE_ANP.get(produto, "litro")


@dataclass(frozen=True)
class Especificacao:
    """Item reconhecido: a categoria, o produto comparável, a unidade e como achá-lo no mercado.

    ``referencia`` diz onde está o preço de mercado (``anp`` ou ``varejo``). Para o varejo, ``consulta`` é o
    texto de busca e ``termos`` são as expressões que o título de uma oferta precisa conter, todas, para
    contar como o mesmo produto (procuradas no título normalizado por ``normalizar_titulo``).
    """

    categoria: str
    produto: str
    unidade: str
    referencia: str
    consulta: str | None = None
    termos: tuple[str, ...] = ()


def sem_acento(texto: str | None) -> str:
    """Minúsculas, sem acentos e com espaços simples: a forma em que descrições e títulos são comparados."""
    decomposto = unicodedata.normalize("NFKD", texto or "")
    limpo = "".join(c for c in decomposto if not unicodedata.combining(c)).lower()
    return re.sub(r"\s+", " ", limpo).strip()


def normalizar_titulo(texto: str | None) -> str:
    """Título ou descrição com números colados às unidades (``8 GB`` → ``8gb``, ``24"`` → ``24pol``).

    Assim ``8 GB``, ``8GB`` e ``8gb`` casam com o mesmo termo, e as várias grafias de polegada (aspas,
    ``pol``, ``polegadas``) viram uma só.
    """
    t = sem_acento(texto).replace("”", '"').replace("″", '"').replace("''", '"')
    t = re.sub(r"(\d)[.,](\d)", r"\1.\2", t)
    t = re.sub(r"(\d)\s*(gb|tb)\b", r"\1\2", t)
    t = re.sub(r"(\d)\s*(\"|pol\.?|polegadas?)(?=\W|$)", r"\1pol", t)
    return t


# ------------------------------------------------------------------ unidades

_LITRO = {"l", "lt", "lts", "ltr", "ltrs", "lit", "litro", "litros"}
_M3 = {"m3", "m³", "metro cubico", "metros cubicos"}
_UNIDADE = {"un", "und", "unid", "unidade", "unidades", "uni", "pc", "pca", "peca", "pecas"}
_BOTIJAO = {"botijao", "botijoes", "bot", "btj", "recarga", "recargas", "carga", "cargas", "p13", "p 13"}


def unidade_canonica(texto: str | None) -> str | None:
    """``litro``, ``m3``, ``unidade`` ou ``botijao`` a partir da unidade de medida da fonte; None se nenhuma.

    Aceita as grafias encontradas no PNCP: ``Litro``, ``LT``, ``L``, ``LITRO (L)``, ``Unidade``, ``UN``,
    ``Botijão``, ``Recarga``. Caixa, pacote e kit não viram ``unidade``: o preço deles não é o de um produto.
    """
    t = sem_acento(texto).replace("³", "3")
    if not t:
        return None
    t = re.sub(r"[()\[\].,;:/\\-]", " ", t)
    palavras = t.split()
    if t in _M3 or (palavras and palavras[0] in {"m3"}):
        return "m3"
    if t in _LITRO or (palavras and palavras[0] in _LITRO):
        return "litro"
    if t in _UNIDADE or (palavras and palavras[0] in _UNIDADE):
        return "unidade"
    if t in _BOTIJAO or (palavras and palavras[0] in _BOTIJAO):
        return "botijao"
    return None


# ------------------------------------------------------------------ combustíveis

_FORA_COMBUSTIVEL = re.compile(
    r"lubrificante|oleo (de |para )?motor|oleo 2 ?t|\barla\b|graxa|filtro|fluido|\btaxa\b|administra|"
    r"gerenciamento|gestao|cartao|servico|lava ?jato|troca de oleo|aditivo para|\bgel\b|70 ?%|70 ?inpm|"
    r"isopropil|antissept|assepsia|hospitalar|limpeza|absoluto|anidro|\bp\.? ?a\.?\b|premium|podium|"
    r"octanagem|aviacao|\bqav\b|querosene|maritimo|\bbotij|\bglp\b|\bgas de cozinha\b|gas liquefeito"
)


def _combustivel(d: str) -> str | None:
    """Produto ANP de uma descrição de combustível (sem acento); None quando não dá para dizer qual é."""
    if _FORA_COMBUSTIVEL.search(d):
        return None
    if re.search(r"\bgnv\b|gas natural veicular", d):
        return GNV
    if re.search(r"\bgasolina\b", d):
        return GASOLINA_ADITIVADA if re.search(r"aditivad", d) else GASOLINA
    if re.search(r"\bdiesel\b|\bs ?-? ?10\b|\bs ?-? ?500\b", d):
        if re.search(r"\bs ?-? ?10\b", d):
            return DIESEL_S10
        if re.search(r"\bs ?-? ?500\b|diesel comum", d):
            return DIESEL_S500
        return None   # "óleo diesel" sem dizer qual: S10 e S500 têm preços diferentes
    if re.search(r"\betanol\b", d) or (re.search(r"\balcool\b", d)
                                        and re.search(r"combust|hidratado|veicul|automot", d)):
        return ETANOL
    return None


# ------------------------------------------------------------------ gás de cozinha

_GLP = re.compile(r"\bglp\b|gas liquefeito|gas de cozinha|gas de botijao|botij(ao|oes) de gas|gas butano")
_P13 = re.compile(r"\bp ?-? ?13\b|\b13 ?(kg|quilos?|kilos?)\b")
# O preço da ANP é o do botijão de 13 kg cheio, trocado pelo vazio. Vasilhame novo, botijão completo (gás
# mais vasilhame), acessórios, outros tamanhos, granel e uso industrial têm outro preço.
_FORA_GLP = re.compile(
    r"completo|vasilhame novo|com vasilhame|incluindo (o )?vasilhame|aquisicao de vasilhame|"
    r"botij(ao|oes) novos?\b|regulador|mangueira|valvula|\bp ?-? ?(2|5|8|20|45|90|190)\b|"
    r"\b(2|5|8|20|45|90|190) ?kg\b|granel|empilhadeira|industrial|\bgasolina\b|\bdiesel\b|\betanol\b|"
    r"\bgnv\b|\blocacao\b|aluguel|instalacao|manutencao"
)
# Falar do vasilhame vazio é normal na recarga ("mediante troca do vasilhame vazio"); sem troca, é a compra
# do próprio vasilhame.
_VASILHAME = re.compile(r"\bcasco|vazio|vasilhame")
_TROCA = re.compile(r"troca|devolu|permuta|substitui|retorno|recarga|reabastec")


def _gas_de_cozinha(d: str) -> bool:
    """A descrição (sem acento) é de GLP no botijão de 13 kg, só o gás, com a troca do vazio?"""
    if not (_GLP.search(d) and _P13.search(d)) or _FORA_GLP.search(d):
        return False
    return not (_VASILHAME.search(d) and not _TROCA.search(d))


# ------------------------------------------------------------------ informática

# Acessório, peça ou serviço *antes* do nome do produto ("mochila para notebook", "toner para impressora",
# "locação de impressoras") muda o objeto; depois dele é só especificação ("notebook ... teclado ABNT2,
# fonte bivolt"), e não conta.
_ACESSORIO = re.compile(
    r"mochila|\bcapa|carregador|\bfonte\b|bateria|suporte|\bbase\b|cooler|teclado|mouse|maleta|bolsa|"
    r"pelicula|\bcabo|adaptador|\bhd\b|manutencao|conserto|locacao|aluguel|outsourcing|servico|toner|"
    r"cartucho|\btinta|refil|cilindro|fotocondutor|\bpeca|reparo|garantia|tela para|braco|kit"
)
_CATEGORIA = re.compile(r"\bnotebook|\blaptop|\bmonitor|\bimpressora|multifuncional")
# "Monitor" também é equipamento de saúde; esses nunca são informática.
_MONITOR_DE_SAUDE = re.compile(
    r"cardiac|multiparametr|sinais vitais|pressao arterial|glicose|\bbebe\b|fetal|veterin|oximetr|"
    r"hospitalar|\becg\b|holter|paciente|desfibril"
)
_PRODUTO_USADO = re.compile(r"\busad[oa]s?\b|recondicionad|seminov|vitrine|\bpara retirada de pecas\b")


def _acessorio_ou_servico(d: str) -> bool:
    """O texto trata de acessório, peça ou serviço do produto, e não do produto em si?"""
    m = _CATEGORIA.search(d)
    if m is None:
        return False
    if re.search(r"\bpara (o |a |os |as )?(notebook|laptop|monitor|impressora|multifuncional)", d):
        return True
    return bool(_ACESSORIO.search(d[:m.start()]))


def _notebook(d: str) -> Especificacao | None:
    """Notebook com processador, memória e armazenamento identificados; sem os três, não compara."""
    proc = None
    m = re.search(r"\b(?:core\s*)?(i[3579])\b", d)
    if m:
        proc = (m.group(1), rf"\b{m.group(1)}\b")
    else:
        m = re.search(r"\bryzen\s*([3579])\b", d)
        if m:
            proc = (f"ryzen {m.group(1)}", rf"\bryzen\s*{m.group(1)}\b")
    ram = (re.search(r"\b(\d{1,2})gb(?:\s*(?:de\s*)?(?:memoria\s*)?ram\b|\s*ddr\d)", d)
           or re.search(r"memoria\s*(?:ram\s*)?(?:de\s*)?(?:no minimo\s*|minima de\s*|minimo de\s*)?(\d{1,2})gb", d)
           or re.search(r"\bram\s*(?:de\s*)?(?:no minimo\s*|minima de\s*|minimo de\s*)?(\d{1,2})gb", d)
           # logo depois do processador, como nos títulos e na própria consulta ("i5 8gb ssd 256gb")
           or re.search(r"\b(?:i[3579]|ryzen\s*[3579])\s+(\d{1,2})gb\b", d))
    ssd = (re.search(r"ssd\s*(?:de\s*)?(?:no minimo\s*|minimo de\s*)?(\d{3,4})gb", d)
           or re.search(r"\b(\d{3,4})gb\s*(?:de\s*)?ssd", d))
    ssd_tb = (re.search(r"ssd\s*(?:de\s*)?(\d)tb", d) or re.search(r"\b(\d)tb\s*(?:de\s*)?ssd", d))
    if not proc or not ram or not (ssd or ssd_tb):
        return None
    armazenamento = f"{ssd.group(1)}gb" if ssd else f"{ssd_tb.group(1)}tb"
    return Especificacao(
        categoria=NOTEBOOK,
        produto=f"notebook {proc[0]} {ram.group(1)}gb ssd {armazenamento}",
        unidade="unidade", referencia="varejo",
        consulta=f"notebook {proc[0]} {ram.group(1)}gb ssd {armazenamento}",
        termos=(r"\bnotebook\b", proc[1], rf"\b{ram.group(1)}gb\b", rf"\b{armazenamento}\b"),
    )


def _monitor(d: str) -> Especificacao | None:
    """Monitor com o tamanho da tela em polegadas; sem o tamanho, não compara."""
    m = re.search(r"\b(\d{2}(?:\.\d)?)pol\b", d)
    if not m:
        return None
    tamanho = m.group(1)
    termos = [r"\bmonitor\b", rf"\b{re.escape(tamanho)}pol\b"]
    rotulo = f"monitor {tamanho} polegadas"
    if re.search(r"full ?hd|\bfhd\b|1920 ?x ?1080", d):
        termos.append(r"full ?hd|\bfhd\b|1920 ?x ?1080")
        rotulo += " full hd"
    return Especificacao(categoria=MONITOR, produto=rotulo, unidade="unidade", referencia="varejo",
                         consulta=rotulo, termos=tuple(termos))


def _impressora(d: str) -> Especificacao | None:
    """Impressora pela tecnologia (laser ou tanque de tinta), multifuncional ou não, colorida ou mono."""
    if re.search(r"\blaser\b", d):
        tecnologia, termo = "laser", r"\blaser\b"
    elif re.search(r"tanque de tinta|ecotank|ink ?tank|jato de tinta", d):
        tecnologia, termo = "tanque de tinta", r"tanque de tinta|ecotank|ink ?tank|jato de tinta"
    else:
        return None
    multi = bool(re.search(r"multifuncional", d))
    cor = "colorida" if re.search(r"\bcolor|colorid|\bcores\b", d) else (
        "monocromatica" if re.search(r"monocrom|\bmono\b|preto e branco", d) else None)
    termos = [r"multifuncional" if multi else r"\bimpressora\b", termo]
    rotulo = f"{'multifuncional' if multi else 'impressora'} {tecnologia}"
    if cor == "colorida":
        termos.append(r"\bcolor|colorid")
        rotulo += " colorida"
    elif cor == "monocromatica":
        termos.append(r"monocrom|\bmono\b|preto e branco")
        rotulo += " monocromatica"
    return Especificacao(categoria=IMPRESSORA, produto=rotulo, unidade="unidade", referencia="varejo",
                         consulta=rotulo, termos=tuple(termos))


# ------------------------------------------------------------------ entrada

def reconhecer(descricao: str | None, unidade_medida: str | None) -> Especificacao | None:
    """Especificação comparável do item, ou None quando ele não é reconhecido com segurança.

    A unidade decide antes da descrição: combustível só em litro (GNV em m³), gás de cozinha só por botijão
    ou unidade, e informática só por unidade.
    """
    d = normalizar_titulo(descricao)
    if not d:
        return None
    unidade = unidade_canonica(unidade_medida)
    if _GLP.search(d):
        if not _gas_de_cozinha(d) or unidade not in {"botijao", "unidade"}:
            return None
        return Especificacao(categoria=GAS_DE_COZINHA, produto=GLP, unidade=unidade_do_produto(GLP),
                             referencia="anp")
    produto = _combustivel(d)
    if produto is not None:
        esperada = unidade_do_produto(produto)
        if unidade != esperada:
            return None
        return Especificacao(categoria=COMBUSTIVEL, produto=produto, unidade=esperada, referencia="anp")
    if unidade != "unidade" or _acessorio_ou_servico(d):
        return None
    if re.search(r"\bnotebook\b|\blaptop\b", d):
        return _notebook(d)
    if re.search(r"\bmonitor\b", d):
        return None if _MONITOR_DE_SAUDE.search(d) else _monitor(d)
    if re.search(r"\bimpressora\b|multifuncional", d):
        return _impressora(d)
    return None


def oferta_confere(especificacao: Especificacao, titulo: str | None) -> bool:
    """O título da oferta contém todos os termos da especificação (e nenhum sinal de acessório)?"""
    t = normalizar_titulo(titulo)
    if not t or _acessorio_ou_servico(t) or _PRODUTO_USADO.search(t) or _MONITOR_DE_SAUDE.search(t):
        return False
    return all(re.search(termo, t) for termo in especificacao.termos)
