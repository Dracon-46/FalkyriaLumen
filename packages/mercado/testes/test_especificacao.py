"""Reconhecimento de itens comparáveis: o que entra na regra A-05, o que fica de fora e por quê.

O erro caro é comparar produtos diferentes. Por isso metade dos casos aqui são de coisas que parecem o
produto e não são (lubrificante, álcool 70%, mochila para notebook, monitor de sinais vitais, toner,
locação de impressoras, combustível por cartão, vasilhame e botijão de outro tamanho) e de descrições vagas
demais para comparar.
"""

import pytest
from lumen_mercado.especificacao import (
    COMBUSTIVEL,
    DIESEL_S10,
    DIESEL_S500,
    ETANOL,
    GAS_DE_COZINHA,
    GASOLINA,
    GASOLINA_ADITIVADA,
    GLP,
    GNV,
    IMPRESSORA,
    MONITOR,
    NOTEBOOK,
    normalizar_titulo,
    oferta_confere,
    reconhecer,
    sem_acento,
    unidade_canonica,
    unidade_do_produto,
)


@pytest.mark.parametrize("descricao, unidade, produto", [
    ("GASOLINA COMUM", "Litro", GASOLINA),
    ("Combustível - Gasolina comum", "LT", GASOLINA),
    ("Gasolina aditivada", "LITRO (L)", GASOLINA_ADITIVADA),
    ("ÓLEO DIESEL S10", "Litro", DIESEL_S10),
    ("Óleo diesel S-10 comum", "L", DIESEL_S10),
    ("Diesel S-500 comum", "L", DIESEL_S500),
    ("ETANOL HIDRATADO COMBUSTÍVEL", "Litro", ETANOL),
    ("ALCOOL ETILICO HIDRATADO COMBUSTIVEL", "Litros", ETANOL),
    ("GNV - gás natural veicular", "m³", GNV),
])
def test_combustiveis_reconhecidos(descricao, unidade, produto):
    e = reconhecer(descricao, unidade)
    assert e is not None and e.categoria == COMBUSTIVEL and e.produto == produto and e.referencia == "anp"


@pytest.mark.parametrize("descricao, unidade", [
    ("OLEO DIESEL", "Litro"),                                     # S10 ou S500? preços diferentes
    ("GASOLINA COMUM", "Unidade"),                                # unidade errada para combustível
    ("Fornecimento de combustível com taxa de administração", "Serviço"),
    ("Gerenciamento de abastecimento da frota: gasolina comum", "Litro"),
    ("OLEO LUBRIFICANTE 15W40 para motor diesel", "Litro"),
    ("ARLA 32", "Litro"),
    ("ÁLCOOL 70% LÍQUIDO", "Litro"),
    ("Álcool etílico hidratado 70 INPM", "Litro"),
    ("Gasolina premium", "Litro"),                                # sem série da ANP
    ("Gasolina comum e gás GLP P13", "Litro"),                    # dois produtos no mesmo item
    ("Querosene de aviação", "Litro"),
    ("", "Litro"),
])
def test_combustiveis_fora(descricao, unidade):
    assert reconhecer(descricao, unidade) is None


def test_notebook_com_processador_memoria_e_ssd():
    e = reconhecer("NOTEBOOK, processador Intel Core i5, 8GB RAM, SSD 256GB, tela 15.6, teclado ABNT2, "
                   "fonte bivolt, Windows 11 Pro", "Unidade")
    assert e.categoria == NOTEBOOK and e.consulta == "notebook i5 8gb ssd 256gb" and e.referencia == "varejo"
    e = reconhecer("Notebook com processador Ryzen 5, memória RAM de 16 GB, SSD de 512 GB", "UN")
    assert e.consulta == "notebook ryzen 5 16gb ssd 512gb"
    e = reconhecer("Notebook core i7, 16 GB DDR4, SSD 1 TB", "unidade")
    assert e.consulta == "notebook i7 16gb ssd 1tb"


@pytest.mark.parametrize("descricao, unidade", [
    ("Notebook i5", "Unidade"),                                   # sem memória nem SSD
    ("MOCHILA PARA NOTEBOOK", "Unidade"),
    ("Carregador notebook Dell 65W", "Unidade"),
    ("Notebook i5 8GB SSD 256GB", "Caixa"),
    ("Manutenção de notebooks i5 8GB SSD 256GB", "Unidade"),
])
def test_notebook_fora(descricao, unidade):
    assert reconhecer(descricao, unidade) is None


def test_monitor_e_impressora():
    e = reconhecer('Monitor LED 24" Full HD', "Unidade")
    assert e.categoria == MONITOR and e.consulta == "monitor 24 polegadas full hd"
    assert reconhecer("Monitor 21,5 polegadas", "UN").consulta == "monitor 21.5 polegadas"
    e = reconhecer("Impressora multifuncional laser monocromática", "Unidade")
    assert e.categoria == IMPRESSORA and e.consulta == "multifuncional laser monocromatica"
    assert reconhecer("Impressora tanque de tinta colorida", "UN").consulta == "impressora tanque de tinta colorida"
    assert reconhecer("Impressora térmica", "UN") is None         # sem tecnologia comparável


@pytest.mark.parametrize("descricao, unidade", [
    ("MONITOR MULTIPARAMETRICO 10 POLEGADAS", "Unidade"),
    ("Monitor de sinais vitais 12 pol", "Unidade"),
    ("Suporte para monitor 24 polegadas", "Unidade"),
    ("TONER PARA IMPRESSORA LASER", "Unidade"),
    ("Locação de impressoras multifuncionais laser", "Mês"),
    ("Monitor", "Unidade"),
])
def test_monitor_e_impressora_fora(descricao, unidade):
    assert reconhecer(descricao, unidade) is None


def test_unidades():
    assert unidade_canonica("Litro") == unidade_canonica("LT") == unidade_canonica("LITRO (L)") == "litro"
    assert unidade_canonica("m³") == unidade_canonica("M3") == "m3"
    assert unidade_canonica("Unidade") == unidade_canonica("UN") == unidade_canonica("Und.") == "unidade"
    assert unidade_canonica("Caixa") is None and unidade_canonica(None) is None and unidade_canonica("") is None


def test_normalizacao_de_titulo():
    assert normalizar_titulo('Monitor LG 24" Full HD') == "monitor lg 24pol full hd"
    assert normalizar_titulo("Notebook 8 GB 256 GB") == "notebook 8gb 256gb"
    assert normalizar_titulo("Tela 15,6 polegadas") == "tela 15.6pol"
    assert sem_acento("  Ação  Àgua ") == "acao agua"


def test_oferta_confere_com_a_especificacao():
    e = reconhecer("NOTEBOOK Intel Core i5, 8GB RAM, SSD 256GB", "Unidade")
    assert oferta_confere(e, "Notebook Lenovo Ideapad 1 Intel Core i5 8GB 256GB SSD 15.6")
    assert not oferta_confere(e, "Notebook Dell Inspiron Intel Core I5 8gb 512gb Ssd")      # outro SSD
    assert not oferta_confere(e, "Mochila Para Notebook i5 8gb 256gb")
    assert not oferta_confere(e, "Notebook Acer i5 8 GB 256 GB SSD Usado")
    assert not oferta_confere(e, "")


@pytest.mark.parametrize("descricao, unidade", [
    ("GÁS LIQUEFEITO DE PETRÓLEO - GLP, BOTIJÃO DE 13 KG", "Unidade"),
    ("Registro de preços para recarga de gás GLP P13, mediante troca do vasilhame vazio", "Recarga"),
    ("Gás de cozinha P-13", "BOTIJÃO"),
    ("Botijão de gás 13 kg (somente o gás)", "UN"),
    ("GÁS GLP P13 botijão", "Unidade"),
])
def test_gas_de_cozinha(descricao, unidade):
    e = reconhecer(descricao, unidade)
    assert e is not None and e.categoria == GAS_DE_COZINHA and e.produto == GLP
    assert e.unidade == "botijao_13kg" and e.referencia == "anp"


@pytest.mark.parametrize("descricao, unidade", [
    ("Gás GLP", "Unidade"),                                       # sem o tamanho do botijão
    ("Gás GLP P45", "Unidade"),                                   # outro tamanho, outro preço
    ("GLP a granel para cozinha industrial", "Kg"),
    ("Gás GLP 13 kg", "Kg"),                                      # preço por quilo, não por botijão
    ("Vasilhame vazio para GLP 13 kg", "Unidade"),                # compra do vasilhame, não do gás
    ("Botijão de gás P13 completo (vasilhame + gás)", "Unidade"),
    ("Regulador de gás GLP 13 kg com mangueira", "Unidade"),
    ("Locação de botijão P13 de GLP", "Mês"),
])
def test_gas_de_cozinha_fora(descricao, unidade):
    assert reconhecer(descricao, unidade) is None


def test_unidade_do_botijao_e_do_produto():
    assert unidade_canonica("Botijão") == "botijao" and unidade_canonica("RECARGA") == "botijao"
    assert unidade_canonica("P13") == "botijao"
    assert unidade_do_produto(GLP) == "botijao_13kg" and unidade_do_produto(GNV) == "m3"
    assert unidade_do_produto(GASOLINA) == "litro"
