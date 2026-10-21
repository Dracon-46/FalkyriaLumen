"""Contratos dos municípios paranaenses no SIM-AM do TCE-PR (ADR-050)."""

from __future__ import annotations

import io
import zipfile
from datetime import date

from lumen_painel import comum, tce, tce_pr
from lumen_painel.cadastro import Cadastro, Ente

CADASTRO = Cadastro({"4106902": Ente("4106902", "Curitiba", "PR", "M", 1_800_000),
                     "4100103": Ente("4100103", "Abatiá", "PR", "M", 7_000),
                     "41": Ente("41", "Paraná", "PR", "E", 11_000_000),
                     "4319604": Ente("4319604", "São Sepé", "RS", "M", 23_000)})
CONTRATOS = """<?xml version="1.0" encoding="utf-8"?><root>
<Contrato cdIBGE="410690" nmEntidade="MUNICÍPIO DE CURITIBA" idContrato="1" nmContratado="BANCO DO BRASIL SA"
 nrDocContratado="00000000000191" vlContrato="1000.00" vlDesteContratado="1000.00"/>
<Contrato cdIBGE="410690" nmEntidade="MUNICÍPIO DE CURITIBA" idContrato="2" nmContratado="EMPRESA X 123.456.789-09"
 nrDocContratado="09537392000105" vlContrato="900.00" vlDesteContratado="600.00"/>
<Contrato cdIBGE="410690" nmEntidade="MUNICÍPIO DE CURITIBA" idContrato="2" nmContratado="EMPRESA Y"
 nrDocContratado="11111111000191" vlContrato="900.00" vlDesteContratado="300.00"/>
<Contrato cdIBGE="410690" nmEntidade="FUNDO MUNICIPAL DE SAÚDE" idContrato="3" nmContratado="FULANA DE TAL"
 nrDocContratado="***.456.789-**" vlContrato="50.00" vlDesteContratado="50.00"/>
<Contrato cdIBGE="410690" nmEntidade="CONSÓRCIO METROPOLITANO" idContrato="4" nmContratado="EMPRESA Z"
 nrDocContratado="22222222000122" vlContrato="70.00" vlDesteContratado="70.00"/>
</root>"""
ADITIVOS = """<?xml version="1.0" encoding="utf-8"?><root>
<ContratoAditivo idcontrato="1" dsTipoOperacaoAditivoContrato="Reajuste de Valores" vlAditivo="100.00"/>
<ContratoAditivo idcontrato="2" dsTipoOperacaoAditivoContrato="Supressão (Redução de Valor)" vlAditivo="30.00"/>
</root>"""


def _zip(ano: int, ibge6: str, **arquivos: str) -> bytes:
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as z:
        for nome, texto in arquivos.items():
            z.writestr(f"{ano}_{ibge6}_{nome}.xml", texto)
    return saida.getvalue()


ZIP_CURITIBA = _zip(2022, "410690", Contrato=CONTRATOS, ContratoAditivo=ADITIVOS)


def test_municipio_por_contratado_com_consorcio_pessoa_fisica_e_aditivos():
    soma, nomes = tce.SomaAno(lambda ente: tce_pr.teto_do_ente(ente, CADASTRO)), {}
    tce_pr.ler_municipio(ZIP_CURITIBA, "4106902", soma, nomes)
    r = soma.para_json()
    # 4 registros do município (o contrato 2 tem dois contratados), um com pessoa física; o consórcio sem ente
    assert r["entes"]["4106902"] == [4, 1950.0, 0, 1, 50.0, 2, 70.0]
    assert r["sem_ente"] == [1, 70.0]
    assert r["fornecedores"]["4106902"] == {"00000000000191": [1, 1000.0], "09537392000105": [1, 600.0],
                                            "11111111000191": [1, 300.0]}
    assert nomes["09537392000105"] == "EMPRESA X ***.456.789-**" and "FULANA DE TAL" not in str(nomes)
    assert tce_pr.municipios(CADASTRO) == ["4100103", "4106902"]


def test_coleta_baixa_os_municipios_dos_anos_que_mudaram(tmp_path):
    pedidos = []

    def baixar(url, *, contato):
        pedidos.append(url)
        return ZIP_CURITIBA if url.endswith("_410690_Contrato.zip") else None

    cabecalhos = {tce_pr.URL_ESTADO.format(ano=2022): (1000, "e1")}
    r = tce_pr.coletar(tmp_path, CADASTRO, contato="c", hoje=date(2023, 3, 1), anos=[2021, 2022],
                       cabecalho_fn=lambda url, contato: cabecalhos.get(url), baixar_fn=baixar)
    assert r.para_json() == {"tribunal": "TCE-PR", "lidos": [2022], "pulados": [], "ausentes": [2021], "nomes": 3,
                             "interrompida": False}
    assert len(pedidos) == 2                                          # Abatiá e Curitiba
    estado = comum.ler_json(tmp_path / tce_pr.ARQUIVO)
    assert estado["tribunal"] == "TCE-PR" and estado["anos"]["2022"]["entes"]["4106902"][0] == 4
    # Prazo vencido no meio do ano: o ano não é gravado e volta na próxima execução
    tempo = iter([0, 0, 120])
    r2 = tce_pr.coletar(tmp_path, CADASTRO, contato="c", hoje=date(2024, 3, 10), anos=[2022],
                        cabecalho_fn=lambda url, contato: (2000, "e2"), baixar_fn=baixar,
                        limite_minutos=1, relogio=lambda: next(tempo))
    assert r2.interrompida and r2.lidos == []
    assert comum.ler_json(tmp_path / tce_pr.ARQUIVO)["anos"]["2022"]["etiqueta"] == "e1"
