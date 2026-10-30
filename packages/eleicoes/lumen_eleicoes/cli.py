"""Linha de comando da aba Eleições (``lumen eleicoes ...``).

Exemplos::

    lumen eleicoes preparar --servir                # tudo: mapa, 1933 a 2026, portal no navegador
    lumen eleicoes preparar --nuvem --limite-minutos 280 --apagar-zips   # a mesma carga no GitHub Actions
    lumen eleicoes publicar                         # envia ao R2 os feeds que mudaram
    lumen eleicoes catalogo                         # o que o TSE publica agora
    lumen eleicoes municipios                       # cadastro TSE ↔ IBGE (busca e mapa)
    lumen eleicoes mapas                            # malhas do IBGE para o mapa
    lumen eleicoes mapas --contornos                # contornos finos dos municípios do mapa das zonas
    lumen eleicoes zonas --anos 2026,2024           # locais de votação: mapa das zonas eleitorais
    lumen eleicoes eleitorado --anos 2026           # perfil, comparecimento por perfil e seções
    lumen eleicoes horarios --anos 2026             # abertura, encerramento e boletim de cada urna
    lumen eleicoes votos-hora --ano 2026 --ufs todas --montar   # votos por hora, pelos logs das urnas
    lumen eleicoes ao-vivo --eleicao 2026-1t-geral  # noite da apuração
    lumen eleicoes historico baixar --anos 2022,2018,1950
    lumen eleicoes historico processar --anos 2022,2018,1950
    lumen eleicoes simular                          # apuração fictícia para testar a tela
    lumen eleicoes servir                           # portal + feeds em http://127.0.0.1:8080
    lumen eleicoes verificar                        # confere o contrato dos feeds gravados
    lumen eleicoes medir --resumo resumo.md         # tamanho dos feeds contra os limites gratuitos
"""

from __future__ import annotations

import argparse
import json
import logging
import signal
import sys
import threading
import time
import urllib.request
from datetime import datetime
from pathlib import Path

from lumen_ingestao.bronze import ArmazemBronzeLocal
from lumen_ingestao.cliente_http import ClienteHttp

from . import antigas, carga, conferencia, eleitorado, geo, horarios, medicao, referencias, tse, votos_hora, zonas
from . import dados_abertos as da
from .coletor import FONTE_ID, ColetorAoVivo, ResumoPassada, plano_padrao
from .configuracao import ConfiguracaoAusente, ConfiguracaoEleicoes, carregar, carregar_publicacao
from .feeds import EscritorFeeds
from .municipios import CadastroMunicipios, nomes_do_ibge
from .preparacao import OpcoesPreparacao, Preparacao
from .publicacao import LimiteDoArmazenamento, Nuvem
from .simulacao import Cenario, ServidorSimulado, gerar_amostra
from .transferencia import baixar_arquivo
from .verificacao import verificar_diretorio

# ``ao-vivo --limite-minutos``: o prazo venceu com a apuração em andamento. O fluxo do GitHub Actions dispara
# a continuação ao receber este código (a máquina tem 6 horas; a apuração pode passar disso).
CODIGO_PRAZO = 3

RAIZ_REPO = Path(__file__).resolve().parents[3]
FIXTURES_TSE = RAIZ_REPO / "testes" / "fixtures" / "tse"
SITE_PADRAO = RAIZ_REPO / "packages" / "portal" / "out"


def _lista(texto: str | None) -> list[str] | None:
    """Converte ``a, b, c`` em lista sem espaços e em minúsculas; texto ausente vira ``None`` (padrão do comando)."""
    return [x.strip().lower() for x in texto.split(",") if x.strip()] if texto else None


def _anos(texto: str) -> list[int]:
    """Tipo do argparse para ``--anos``: anos sem repetição, do mais recente ao mais antigo.

    ``todos`` são todos os anos dos dados abertos, de 2026 a 1933. Recusa ano sem eleição ordinária nos
    dados abertos (fora de ``carga.anos_disponiveis``).
    """
    if texto.strip().lower() == "todos":
        return carga.anos_disponiveis()
    anos = sorted({int(x) for x in texto.split(",") if x.strip()}, reverse=True)
    validos = set(carga.anos_disponiveis())
    fora = [a for a in anos if a not in validos]
    if fora:
        raise argparse.ArgumentTypeError(f"anos sem eleição ordinária nos dados abertos: {fora}")
    return anos


def _anos_locais(texto: str) -> list[int]:
    """Tipo do argparse para ``zonas --anos``: anos com locais de votação (2018 em diante), do mais recente ao
    mais antigo; ``todos`` são os de ``zonas.ANOS_LOCAIS``."""
    if texto.strip().lower() == "todos":
        return list(zonas.ANOS_LOCAIS)
    anos = sorted({int(x) for x in texto.split(",") if x.strip()}, reverse=True)
    fora = [a for a in anos if a not in zonas.ANOS_LOCAIS]
    if fora:
        raise argparse.ArgumentTypeError(f"anos sem locais de votação nos dados abertos: {fora}")
    return anos


def _anos_eleitorado(texto: str) -> list[int]:
    """Tipo do argparse para ``eleitorado --anos``: anos de ``eleitorado.ANOS_ELEITORADO``, do mais recente ao
    mais antigo; ``todos`` são todos eles."""
    if texto.strip().lower() == "todos":
        return list(eleitorado.ANOS_ELEITORADO)
    anos = sorted({int(x) for x in texto.split(",") if x.strip()}, reverse=True)
    fora = [a for a in anos if a not in eleitorado.ANOS_ELEITORADO]
    if fora:
        raise argparse.ArgumentTypeError(f"anos sem o perfil do eleitorado tratado pelo Lumen: {fora}")
    return anos


def _anos_horarios(texto: str) -> list[int]:
    """Tipo do argparse para ``horarios --anos``: anos de ``horarios.ANOS_HORARIOS``; ``todos`` são todos eles."""
    if texto.strip().lower() == "todos":
        return list(horarios.ANOS_HORARIOS)
    anos = sorted({int(x) for x in texto.split(",") if x.strip()}, reverse=True)
    fora = [a for a in anos if a not in horarios.ANOS_HORARIOS]
    if fora:
        raise argparse.ArgumentTypeError(f"anos sem boletim de urna nos dados abertos: {fora}")
    return anos


def _cliente(cfg: ConfiguracaoEleicoes, fonte: str, rpm: int) -> ClienteHttp:
    """Cliente HTTP da fonte, com o User-Agent da configuração e limite de ``rpm`` requisições por minuto."""
    return ClienteHttp(fonte, user_agent=cfg.user_agent, rpm=rpm)


def _imprimir(dados) -> None:
    """Imprime ``dados`` como JSON indentado, com acentos e ``str`` para o que não for serializável."""
    print(json.dumps(dados, ensure_ascii=False, indent=2, default=str))


def _catalogo(cliente: ClienteHttp, base: str) -> list:
    """Baixa e lê o catálogo de eleições do sistema de resultados; encerra o programa se não vier HTTP 200."""
    art = cliente.obter(tse.url_catalogo(base))
    if art.status_http != 200:
        raise SystemExit(f"erro: catálogo do TSE respondeu HTTP {art.status_http}")
    return tse.ler_catalogo(art.conteudo)


def _nuvem(cfg: ConfiguracaoEleicoes, args) -> Nuvem:
    """Ponte com o armazenamento da nuvem a partir do ``[publicacao]`` e das variáveis de ambiente.

    Levanta ``ConfiguracaoAusente`` se faltar endpoint, bucket ou chave; ``main`` transforma isso em
    mensagem e código 2.
    """
    pub = carregar_publicacao(Path(args.config) if args.config else None)
    return Nuvem.de_configuracao(pub, cfg)


def _cadastro(cfg: ConfiguracaoEleicoes) -> CadastroMunicipios:
    """Cadastro de municípios do diretório dos feeds; sem ele, o que vem com o pacote (``referencias``).

    O do diretório dos feeds é o mais novo: ``lumen eleicoes municipios`` grava ali a versão corrente.
    """
    caminho = cfg.saida / referencias.ARQUIVO_CADASTRO
    if caminho.exists():
        return CadastroMunicipios.carregar(caminho)
    return referencias.cadastro_embutido()


# ---------------------------------------------------------------- comandos

def cmd_catalogo(cfg, args) -> int:
    """Imprime as eleições do sistema de resultados (cargos e UFs de cada uma) e os anos dos dados abertos."""
    eleicoes = _catalogo(_cliente(cfg, FONTE_ID, cfg.rpm_resultados), args.base)
    _imprimir({
        "sistema_de_resultados": [{"id": e.id, "nome": e.nome, "data": e.data, "ciclo": e.ciclo,
                                   "cargos": [c.slug for c in e.cargos], "ufs": e.abrangencias}
                                  for e in eleicoes],
        "dados_abertos": {"gerais": list(da.ANOS_GERAIS), "municipais": list(da.ANOS_MUNICIPAIS),
                          "por_uf_1933_a_1990": list(antigas.ANOS_ANTIGOS)},
    })
    return 0


def cmd_municipios(cfg, args) -> int:
    """Grava o ``municipios.json`` (cadastro TSE ↔ IBGE) e imprime o arquivo e as contagens.

    Usa o cadastro de municípios de uma eleição do catálogo — por padrão a geral mais recente, que tem
    todos os municípios e o exterior — e os nomes do IBGE; se o IBGE não responder, ficam os nomes do TSE.
    """
    cliente = _cliente(cfg, FONTE_ID, cfg.rpm_resultados)
    eleicoes = _catalogo(cliente, args.base)
    if args.eleicao:
        escolhida = next((e for e in eleicoes if e.id == args.eleicao), None)
    else:
        # A eleição geral mais recente tem todos os municípios e o exterior
        escolhida = next((e for e in eleicoes if e.tipo == "geral"), eleicoes[0] if eleicoes else None)
    if escolhida is None or not escolhida.cargos:
        print("erro: eleição não encontrada no catálogo do TSE", file=sys.stderr)
        return 2
    art = cliente.obter(tse.url_municipios(escolhida.ciclo, escolhida.cargos[0].eleicao_tse, args.base))
    if art.status_http != 200:
        print(f"erro: cadastro de municípios respondeu HTTP {art.status_http}", file=sys.stderr)
        return 1
    municipios_tse = tse.ler_municipios(art.conteudo)
    nomes = {}
    ibge = _cliente(cfg, "ibge_localidades", cfg.rpm_ibge).obter(geo.url_municipios_ibge())
    if ibge.status_http == 200:
        nomes = nomes_do_ibge(ibge.conteudo)
    else:
        print(f"aviso: IBGE respondeu HTTP {ibge.status_http}; nomes ficam como o TSE publica", file=sys.stderr)
    cadastro = CadastroMunicipios.de_tse(municipios_tse, nomes)
    caminho = cadastro.gravar(cfg.saida / "municipios.json")
    _imprimir({"arquivo": caminho, "municipios": len(cadastro),
               "sem_ibge": sum(1 for m in cadastro if not m.ibge), "fonte": escolhida.id})
    return 0


def cmd_mapas(cfg, args) -> int:
    """Baixa as malhas do IBGE para o mapa (todas as UFs ou as pedidas) e imprime os arquivos gravados.

    Com ``--contornos``, baixa em vez disso o contorno fino (qualidade ``maxima``) de cada município listado
    nos índices do mapa das zonas (``geo/zonas-<ano>/indice.json``) do diretório dos feeds.
    """
    bronze = None if args.sem_bronze else ArmazemBronzeLocal(cfg.bronze)
    cliente = _cliente(cfg, geo.FONTE_ID, cfg.rpm_ibge)
    if args.contornos:
        codigos = zonas.municipios_dos_indices(cfg.saida)
        if not codigos:
            print("erro: nenhum índice das zonas no diretório dos feeds; rode `lumen eleicoes zonas` antes",
                  file=sys.stderr)
            return 2
        gravados = geo.baixar_contornos(cliente, cfg.saida, codigos, bronze=bronze)
        _imprimir({"contornos": [str(p) for p in gravados]})
        return 0
    gravados = geo.baixar_malhas(cliente, cfg.saida, ufs=_lista(args.ufs), qualidade=args.qualidade, bronze=bronze)
    _imprimir({"malhas": [str(p) for p in gravados]})
    return 0


def cmd_zonas(cfg, args) -> int:
    """Baixa os locais de votação de cada ano e grava o mapa das zonas eleitorais (``geo/zonas-<ano>/``).

    O andamento vai para o stderr; no stdout, só o resumo de cada ano em JSON: municípios com mais de uma
    zona, locais e descartados.
    """
    bronze = None if args.sem_bronze else ArmazemBronzeLocal(cfg.bronze)
    cadastro = _cadastro(cfg)
    resumos = []

    def andamento(msg: str) -> None:
        print(msg, file=sys.stderr, flush=True)
    for ano in args.anos:
        caminho, manifesto = zonas.baixar_locais(cfg, ano, bronze=bronze, atualizar=args.atualizar, saida=andamento)
        resumos.append(zonas.gravar_zonas(ano, caminho, cfg.saida, cadastro, manifesto=manifesto,
                                          progresso=andamento).para_json())
    _imprimir(resumos)
    return 0


def _aviso_passada(r: ResumoPassada) -> None:
    """Imprime a linha de acompanhamento de uma passada do coletor e, no stderr, até cinco dos erros dela."""
    agora = datetime.now().strftime("%H:%M:%S")
    print(f"{agora}  baixados {r.baixados:>4}  sem mudança {r.nao_modificados:>4}  feeds {r.feeds:>4}  "
          f"fila {r.pendentes_municipais:>5}  erros {len(r.erros):>3}" + ("  [totalização concluída]"
                                                                           if r.finalizada else ""),
          flush=True)
    for erro in r.erros[:5]:
        print(f"          {erro}", file=sys.stderr)


def _instalar_parada() -> list[bool]:
    """Instala o tratamento de Ctrl+C e devolve a sinalização que o laço do coletor consulta.

    O primeiro Ctrl+C só marca ``sinal[0]``, e o coletor para ao fim da passada em curso; o segundo
    interrompe na hora. É uma lista, e não um ``bool``, para o tratador poder alterá-la.
    """
    sinal = [False]

    def parar(*_):
        if sinal[0]:
            raise KeyboardInterrupt
        sinal[0] = True
        print("\nparando ao fim desta passada (Ctrl+C de novo para sair já)", file=sys.stderr)
    # Só a thread principal recebe sinais; chamado de outra (testes, uso
    # embutido), o coletor roda até o fim das passadas sem parada por Ctrl+C.
    if threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGINT, parar)
    return sinal


def cmd_ao_vivo(cfg, args) -> int:
    """Coleta a apuração em andamento de uma eleição do catálogo, imprimindo uma linha por passada.

    Roda até a totalização terminar, até Ctrl+C ou, com ``--uma-vez``, por uma passada só. Devolve 2
    se a eleição não está no sistema de resultados. Com ``--nuvem``, restaura o estado antes, publica
    os feeds a cada passada que gravou algo e sincroniza no fim (ADR-026). Com ``--limite-minutos``, para
    ao fim da passada em que o prazo vence e, se a apuração não terminou, devolve ``CODIGO_PRAZO``: a
    próxima execução continua do estado gravado.
    """
    cliente = _cliente(cfg, FONTE_ID, cfg.rpm_resultados)
    eleicoes = {e.id: e for e in _catalogo(cliente, args.base)}
    if args.eleicao not in eleicoes:
        print(f"erro: {args.eleicao} não está no sistema de resultados. Disponíveis: {', '.join(eleicoes)}",
              file=sys.stderr)
        return 2
    plano = plano_padrao(eleicoes[args.eleicao], cargos=_lista(args.cargos), ufs=_lista(args.ufs),
                         municipios_proporcionais=args.municipios_proporcionais,
                         fotos_municipais=args.fotos_municipais, orcamento_municipal=args.orcamento)
    nuvem = _nuvem(cfg, args) if args.nuvem else None
    if nuvem is not None:
        nuvem.restaurar()
    coletor = ColetorAoVivo(cliente, EscritorFeeds(cfg.saida), plano, cadastro=_cadastro(cfg),
                            bronze=None if args.sem_bronze else ArmazemBronzeLocal(cfg.bronze),
                            base=args.base, estado=cfg.estado / f"coleta-{args.eleicao}.json")
    sinal = _instalar_parada()
    fim = time.monotonic() + args.limite_minutos * 60 if args.limite_minutos else None
    vencido = [False]

    def parar() -> bool:
        if sinal[0]:
            return True
        # O coletor só consulta entre passadas: aqui ele já não parou por ter terminado.
        if fim is not None and time.monotonic() >= fim:
            vencido[0] = True
        return vencido[0]

    def publicar() -> None:
        # Falha ao publicar não derruba a apuração: a próxima passada publica de novo o que ficou
        try:
            nuvem.sincronizar()
        except Exception as erro:  # noqa: BLE001
            print(f"erro ao publicar na nuvem: {erro}", file=sys.stderr, flush=True)

    def aviso(r: ResumoPassada) -> None:
        _aviso_passada(r)
        if nuvem is not None and r.feeds:
            publicar()
    try:
        coletor.executar(intervalo_s=args.intervalo, max_passadas=1 if args.uma_vez else None,
                         parar=parar, aviso=aviso,
                         estavel_s=args.parar_estavel * 60 if args.parar_estavel > 0 else None)
        if coletor.pendentes_ao_parar:
            print(f"parada: todas as seções totalizadas e nada mudou em {args.parar_estavel:g} min; o TSE ainda "
                  f"não marcou como finalizados: {', '.join(coletor.pendentes_ao_parar)}", flush=True)
        if vencido[0]:
            print(f"prazo de {args.limite_minutos:g} min atingido com a apuração em andamento; rode de novo para "
                  "continuar: o estado continua", flush=True)
    finally:
        if nuvem is not None:
            publicar()
    return CODIGO_PRAZO if vencido[0] else 0


def cmd_historico_baixar(cfg, args) -> int:
    """Baixa os ZIPs dos dados abertos de cada ano e registra o manifesto de cada um no bronze.

    Imprime, por arquivo, o caminho, o SHA-256 e o tamanho. Até 1990 são os três conjuntos por UF.
    """
    cliente = _cliente(cfg, carga.FONTE_DADOS_ABERTOS, cfg.rpm_dados_abertos)
    bronze = None if args.sem_bronze else ArmazemBronzeLocal(cfg.bronze)
    feitos = []
    for ano in args.anos:
        for m in carga.baixar_ano(cfg, cliente, ano, bronze=bronze, atualizar=args.atualizar):
            feitos.append({"arquivo": str(cfg.arquivos / str(ano) / m.arquivo), "sha256": m.sha256,
                           "tamanho": m.tamanho})
    _imprimir(feitos)
    return 0


def cmd_historico_processar(cfg, args) -> int:
    """Gera os feeds de cada ano a partir dos ZIPs já baixados e imprime um resumo por ano.

    Devolve 2 se faltar o ZIP de votação de algum ano; os demais conjuntos são opcionais.
    """
    cadastro = _cadastro(cfg)
    escritor = EscritorFeeds(cfg.saida)
    resumos = []
    for ano in args.anos:
        try:
            r = carga.processar_ano(cfg, ano, escritor=escritor, cadastro=cadastro,
                                    limite_municipio=args.limite_municipio)
        except carga.ArquivoAusente as erro:
            print(f"erro: {erro} não existe; rode `lumen eleicoes historico baixar --anos {ano}`", file=sys.stderr)
            return 2
        resumos.append(r.para_json())
    _imprimir(resumos)
    return 0


def cmd_preparar(cfg, args) -> int:
    """Deixa a aba pronta: mapa, portal, 2026 do sistema de resultados e os dados abertos de 1933 a 2026.

    Retomável; imprime o andamento e, no fim, o resumo em JSON. Devolve 1 se alguma etapa falhou.
    """
    opcoes = OpcoesPreparacao(
        anos=args.anos, ao_vivo=not args.sem_ao_vivo, historico=not args.sem_historico, portal=not args.sem_portal,
        zonas=not args.sem_zonas, conferencia=not args.sem_conferencia,
        servir=args.servir, abrir_navegador=not args.sem_navegador, host=args.host, porta=args.porta,
        refazer=args.refazer, atualizar=args.atualizar, municipios_proporcionais=args.municipios_proporcionais,
        limite_municipio=args.limite_municipio, base=args.base, bronze=not args.sem_bronze,
        limite_minutos=args.limite_minutos, apagar_arquivos=args.apagar_zips)
    nuvem = _nuvem(cfg, args) if args.nuvem else None
    sinal = _instalar_parada()
    prep = Preparacao(cfg, opcoes, cliente_resultados=_cliente(cfg, FONTE_ID, cfg.rpm_resultados),
                      cliente_dados=_cliente(cfg, carga.FONTE_DADOS_ABERTOS, cfg.rpm_dados_abertos),
                      parar=lambda: sinal[0], nuvem=nuvem)
    resumo = prep.executar()
    print()
    _imprimir(resumo.para_json())
    prep.aguardar()
    return 1 if resumo.erros else 0


def cmd_eleitorado(cfg, args) -> int:
    """O eleitorado (ADR-055): baixa o perfil, o comparecimento por perfil e os locais de votação de cada ano,
    grava ``eleitorado/<ano>/`` (``.json.gz``) sob ``--saida`` e, com ``--pacotes``, junta cada ano num
    ``eleitorado-<ano>.tar`` para o site dos painéis.

    O andamento vai para o stderr; no stdout, o resumo de cada ano em JSON. Devolve 1 se algum ano falhou (os
    outros continuam). Só o perfil é obrigatório: sem o comparecimento por perfil ou os locais, o ano sai sem eles.
    """
    bronze = None if args.sem_bronze else ArmazemBronzeLocal(cfg.bronze)
    cadastro = _cadastro(cfg)
    saida = Path(args.saida) if args.saida else cfg.saida
    resumos, falhou = [], False

    def andamento(msg: str) -> None:
        print(msg, file=sys.stderr, flush=True)
    for ano in args.anos:
        caminhos, manifestos = {}, {}
        try:
            for nome, url in (("perfil", eleitorado.url_perfil(ano)),
                              ("comparecimento", eleitorado.url_comparecimento(ano)),
                              ("secoes", zonas.url_locais(ano))):
                try:
                    caminhos[nome], manifestos[nome] = eleitorado.baixar(cfg, url, bronze=bronze,
                                                                         atualizar=args.atualizar, saida=andamento)
                except Exception as erro:  # noqa: BLE001 - só o perfil é obrigatório
                    if nome == "perfil":
                        raise
                    andamento(f"{ano}: sem {nome} ({erro})")
            r = eleitorado.gravar_eleitorado(ano, saida, cadastro, perfil=caminhos["perfil"],
                                             comparecimento=caminhos.get("comparecimento"),
                                             locais=caminhos.get("secoes"), manifestos=manifestos,
                                             progresso=andamento)
            resumo = r.para_json()
            if args.pacotes:
                resumo["pacote"] = str(eleitorado.empacotar(ano, saida, args.pacotes))
            resumos.append(resumo)
        except Exception as erro:  # noqa: BLE001 - um ano com erro não impede os outros
            falhou = True
            andamento(f"erro no eleitorado de {ano}: {erro}")
            resumos.append({"ano": ano, "erro": str(erro)})
        finally:
            if args.apagar_zips:
                for caminho in caminhos.values():
                    caminho.unlink(missing_ok=True)
    _imprimir(resumos)
    return 1 if falhou else 0


def cmd_horarios(cfg, args) -> int:
    """Os horários das urnas (ADR-056): baixa o boletim de urna de cada UF e turno do ano, uma UF por vez, guarda
    uma linha por seção, grava ``horarios/<ano>/`` sob ``--saida`` e, com ``--pacotes``, ``horarios-<ano>.tar``.

    O andamento vai para o stderr; no stdout, o resumo de cada ano em JSON. Devolve 1 se algum ano falhou.
    """
    cadastro = _cadastro(cfg)
    saida = Path(args.saida) if args.saida else cfg.saida
    resumos, falhou = [], False

    def andamento(msg: str) -> None:
        print(msg, file=sys.stderr, flush=True)
    for ano in args.anos:
        try:
            urls = horarios.urls_do_ano(ano, user_agent=cfg.user_agent)
            if not urls:
                raise RuntimeError("o catálogo do TSE não lista boletins de urna do ano")
            secoes: dict = {}
            for turno, uf, url in urls:
                destino = cfg.arquivos / "horarios" / url.rsplit("/", 1)[-1]
                andamento(f"{ano} {turno}º turno {uf.upper()}: {url}")
                baixar_arquivo(url, destino, user_agent=cfg.user_agent, atualizar=args.atualizar,
                               progresso=carga.progresso_mb(saida=andamento))
                antes = len(secoes)
                horarios.ler_zip(destino, secoes)
                andamento(f"{ano} {turno}º turno {uf.upper()}: {len(secoes) - antes} seções")
                if args.apagar_zips:
                    destino.unlink(missing_ok=True)
            r = horarios.gravar(ano, list(secoes.values()), saida, cadastro, urls=[u for _, _, u in urls])
            resumo = r.para_json()
            if args.pacotes:
                resumo["pacote"] = str(horarios.empacotar(ano, saida, args.pacotes))
            resumos.append(resumo)
        except Exception as erro:  # noqa: BLE001 - um ano com erro não impede os outros
            falhou = True
            andamento(f"erro nos horários de {ano}: {erro}")
            resumos.append({"ano": ano, "erro": str(erro)})
    _imprimir(resumos)
    return 1 if falhou else 0


def cmd_votos_hora(cfg, args) -> int:
    """Os votos por hora (ADR-057): com ``--ufs``, lê os logs das urnas das UFs pela rede (sem baixar os arquivos)
    e grava a parcial de cada UF em ``--parciais``; com ``--montar``, junta as parciais do ano, grava
    ``votos-hora/<ano>/`` sob ``--saida`` e, com ``--pacotes``, ``votos-hora-<ano>.tar``.

    O andamento vai para o stderr; no stdout, o resumo em JSON. Devolve 1 se alguma UF falhou.
    """
    def andamento(msg: str) -> None:
        print(msg, file=sys.stderr, flush=True)
    parciais = Path(args.parciais)
    resumo: dict = {"ano": args.ano, "coleta": []}
    falhou = False
    urls = votos_hora.urls_do_ano(args.ano, user_agent=cfg.user_agent, tentativas=5)
    if args.ufs:
        ufs = sorted({uf for _, uf, _ in urls}) if args.ufs == ["todas"] else args.ufs
        if not urls:
            raise SystemExit(f"erro: o catálogo do TSE não lista os arquivos das urnas de {args.ano}")
        for uf in ufs:
            try:
                turnos = sum(1 for _, u, _ in urls if u == uf)
                if args.turnos_esperados and turnos < args.turnos_esperados:
                    raise RuntimeError(f"o catálogo do TSE listou {turnos} turno(s) de {uf.upper()}, e não "
                                       f"{args.turnos_esperados}: respondeu uma versão antiga")
                r = votos_hora.coletar(uf, urls, parciais, user_agent=cfg.user_agent,
                                       trabalhadores=args.trabalhadores, progresso=andamento)
                andamento(f"{uf.upper()}: {r.secoes} seções, {r.votos} votos, {r.megabytes:,.0f} MB")
                resumo["coleta"].append(r.para_json())
            except Exception as erro:  # noqa: BLE001 - uma UF com erro não impede as outras
                falhou = True
                andamento(f"erro nos votos por hora de {uf.upper()}: {erro}")
                resumo["coleta"].append({"uf": uf, "erro": str(erro)})
    if args.montar:
        secoes = votos_hora.ler_parciais(parciais)
        saida = Path(args.saida) if args.saida else cfg.saida
        r = votos_hora.gravar(args.ano, secoes, saida, _cadastro(cfg), urls=[u for _, _, u in urls])
        resumo["montagem"] = r.para_json()
        if args.pacotes:
            resumo["montagem"]["pacote"] = str(votos_hora.empacotar(args.ano, saida, args.pacotes))
    _imprimir(resumo)
    return 1 if falhou else 0


def cmd_conferir(cfg, args) -> int:
    """Só a conferência seção a seção (ADR-053): soma a votação por seção de Presidente dos anos pedidos e
    compara com o total do sistema de resultados; grava ``<eleição>/presidente/conferencia.json``.

    O andamento vai para o stderr; no stdout, o resumo em JSON. Devolve 1 se a conferência falhou.
    """
    opcoes = OpcoesPreparacao(anos=args.anos, ao_vivo=False, historico=False, zonas=False, portal=False,
                              abrir_navegador=False, refazer=args.refazer, base=args.base,
                              bronze=not args.sem_bronze)
    prep = Preparacao(cfg, opcoes, cliente_resultados=_cliente(cfg, FONTE_ID, cfg.rpm_resultados),
                      cliente_dados=_cliente(cfg, carga.FONTE_DADOS_ABERTOS, cfg.rpm_dados_abertos),
                      saida=lambda msg: print(msg, file=sys.stderr, flush=True))
    for ano in args.anos:
        prep.conferir_secoes(ano)
    _imprimir(prep.resumo.conferencias)
    return 1 if prep.resumo.erros else 0


def _rodar_simulacao(cfg, arquivos: Path, eleicao_id: str, etapas: int, intervalo: float,
                     ufs: list[str] | None, estado: Path | None) -> int:
    """Roda o coletor ao vivo contra um servidor local que publica os arquivos finais em ``etapas``.

    A cada intervalo entre passadas o cenário avança uma etapa, até ``etapas`` passadas. Por ser
    local, o cliente ignora o proxy do ambiente e tem limite de taxa folgado. Devolve 2 se a eleição
    não está no catálogo da simulação.
    """
    cen = Cenario(arquivos, etapas=etapas)
    with ServidorSimulado(cen) as srv:
        # Servidor local: sem proxy do ambiente e sem limite de taxa relevante
        cliente = ClienteHttp(FONTE_ID, user_agent=cfg.user_agent, rpm=6000,
                              abridor=urllib.request.build_opener(urllib.request.ProxyHandler({})))
        eleicoes = {e.id: e for e in _catalogo(cliente, srv.base)}
        if eleicao_id not in eleicoes:
            print(f"erro: {eleicao_id} não está no catálogo da simulação ({', '.join(eleicoes)})",
                  file=sys.stderr)
            return 2
        plano = plano_padrao(eleicoes[eleicao_id], ufs=ufs or cen.ufs(), simulacao=True)
        coletor = ColetorAoVivo(cliente, EscritorFeeds(cfg.saida), plano, cadastro=_cadastro(cfg),
                                base=srv.base, estado=estado)

        def dormir(segundos):
            time.sleep(segundos)
            cen.avancar()
        sinal = _instalar_parada()
        coletor.executar(intervalo_s=intervalo, max_passadas=etapas, parar=lambda: sinal[0], dormir=dormir,
                         aviso=_aviso_passada)
    return 0


def cmd_simular(cfg, args) -> int:
    """Simula uma apuração a partir dos arquivos finais (as fixtures, por padrão), avisando no stderr que
    os números intermediários são fictícios.
    """
    print("SIMULAÇÃO: números intermediários fictícios; o resultado final é o oficial do TSE.", file=sys.stderr)
    return _rodar_simulacao(cfg, Path(args.arquivos), args.eleicao, args.etapas, args.intervalo,
                            _lista(args.ufs), cfg.estado / f"simulacao-{args.eleicao}.json")


def cmd_publicar(cfg, args) -> int:
    """Envia ao bucket público os feeds novos ou alterados e grava o estado no privado (ADR-026)."""
    try:
        resumo = _nuvem(cfg, args).sincronizar()
    except LimiteDoArmazenamento as erro:
        print(f"erro: {erro}", file=sys.stderr)
        return 1
    _imprimir({"enviados": resumo.enviados, "iguais": resumo.iguais, "bytes": resumo.bytes})
    return 0


def cmd_amostra(cfg, args) -> int:
    """Feeds a partir dos arquivos reais das fixtures, para desenvolver o portal sem rede, com o mapa e o
    cadastro de municípios que vêm com o pacote."""
    gravados = gerar_amostra(Path(args.arquivos), cfg.saida)
    if not args.sem_referencias:
        referencias.instalar(cfg.saida)
    _imprimir({"amostra": str(cfg.saida), "arquivos": len(gravados)})
    return 0


def cmd_servir(cfg, args) -> int:  # pragma: no cover - laço de servidor
    """Serve o portal gerado e os feeds em HTTP local até Ctrl+C; devolve 2 se o portal não foi gerado."""
    from .servidor import ServidorPortal
    site = Path(args.site)
    if not (site / "index.html").exists():
        print(f"erro: {site} não tem o portal gerado; rode `make portal` (ou `npm run build` em "
              "packages/portal)", file=sys.stderr)
        return 2
    srv = ServidorPortal(site, cfg.saida, host=args.host, porta=args.porta)
    print(f"portal em {srv.endereco}/eleicoes/  (feeds de {cfg.saida})")
    try:
        srv.servir_para_sempre()
    except KeyboardInterrupt:
        pass
    return 0


def cmd_verificar(cfg, args) -> int:
    """Confere o contrato dos feeds gravados; imprime cada problema e o total, e devolve 1 se houver algum."""
    rel = verificar_diretorio(cfg.saida)
    for p in rel.problemas:
        print(p)
    print(f"{rel.arquivos} feed(s) conferido(s), {len(rel.problemas)} problema(s).")
    return 0 if rel.ok else 1


def cmd_medir(cfg, args) -> int:
    """Mede os feeds gravados contra os limites do R2 e do Supabase gratuitos; imprime JSON.

    ``--resumo`` também grava o resumo em Markdown (no GitHub Actions, o ``$GITHUB_STEP_SUMMARY``).
    Devolve 1 se não houver nenhum feed para medir.
    """
    m = medicao.medir(cfg.saida, maiores=args.maiores)
    _imprimir(m.para_json())
    if args.resumo:
        with open(args.resumo, "a", encoding="utf-8") as fh:
            fh.write(medicao.resumo_markdown(m))
    return 0 if m.total.arquivos else 1


# ---------------------------------------------------------------- argumentos

def construir_parser() -> argparse.ArgumentParser:
    """Monta o parser de ``lumen eleicoes``: opções globais e um subcomando por ação.

    ``historico`` tem os seus próprios subcomandos, ``baixar`` e ``processar``.
    """
    p = argparse.ArgumentParser(prog="lumen eleicoes", description="Aba Eleições: resultados oficiais do TSE")
    p.add_argument("--config", help="caminho do lumen.toml")
    p.add_argument("--saida", help="diretório dos feeds (padrão: [eleicoes].saida)")
    p.add_argument("-v", "--verboso", action="store_true")
    sub = p.add_subparsers(dest="comando", required=True)

    c = sub.add_parser("preparar", help="tudo num comando: mapa, portal e as eleições de 1933 a 2026")
    c.add_argument("--servir", action="store_true", help="sobe o portal e abre o navegador antes da carga")
    c.add_argument("--anos", type=_anos, help="anos dos dados abertos (padrão: todos, de 2026 a 1933)")
    c.add_argument("--sem-ao-vivo", action="store_true", help="não coleta o sistema de resultados (2026)")
    c.add_argument("--sem-historico", action="store_true",
                   help="não baixa os dados abertos dos resultados (o mapa das zonas continua; --sem-zonas o tira)")
    c.add_argument("--sem-zonas", action="store_true", help="não baixa os locais de votação (mapa das zonas)")
    c.add_argument("--sem-conferencia", action="store_true",
                   help="não soma a votação por seção para conferir com o total divulgado (ADR-053)")
    c.add_argument("--sem-portal", action="store_true", help="não gera o portal (Node.js)")
    c.add_argument("--sem-navegador", action="store_true", help="com --servir, não abre o navegador")
    c.add_argument("--refazer", action="store_true", help="ignora o registro do que já foi feito")
    c.add_argument("--atualizar", action="store_true",
                   help="consulta a fonte e reprocessa o que mudou desde a última vez")
    c.add_argument("--municipios-proporcionais", action="store_true",
                   help="em 2026, também deputados por município (muito mais arquivos)")
    c.add_argument("--limite-municipio", type=int, default=50,
                   help="candidatos por município nos cargos proporcionais (o da UF tem todos)")
    c.add_argument("--sem-bronze", action="store_true", help="não guardar as respostas como prova")
    c.add_argument("--host", default="127.0.0.1")
    c.add_argument("--porta", type=int, default=8080)
    c.add_argument("--base", default=tse.BASE)
    c.add_argument("--nuvem", action="store_true",
                   help="restaura o estado do R2 antes e publica os feeds depois de cada etapa (ADR-026)")
    c.add_argument("--limite-minutos", type=float,
                   help="para sozinha depois disso; a próxima execução continua (GitHub Actions)")
    c.add_argument("--apagar-zips", action="store_true",
                   help="apaga os ZIPs de cada ano depois de processado (máquina com pouco disco)")

    c = sub.add_parser("publicar", help="envia ao R2 os feeds novos ou alterados (ADR-026)")

    c = sub.add_parser("catalogo", help="eleições disponíveis no sistema de resultados")
    c.add_argument("--base", default=tse.BASE)

    c = sub.add_parser("municipios", help="grava municipios.json (TSE ↔ IBGE)")
    c.add_argument("--eleicao", help="eleição do catálogo cujo cadastro usar (padrão: geral mais recente)")
    c.add_argument("--base", default=tse.BASE)

    c = sub.add_parser("mapas", help="baixa as malhas do IBGE")
    c.add_argument("--ufs", help="siglas separadas por vírgula (padrão: todas)")
    c.add_argument("--qualidade", default="minima", choices=geo.QUALIDADES)
    c.add_argument("--contornos", action="store_true",
                   help="contorno fino dos municípios do mapa das zonas (geo/mu/), em vez das malhas das UFs")
    c.add_argument("--sem-bronze", action="store_true")

    c = sub.add_parser("zonas", help="locais de votação: mapa das zonas eleitorais (ADR-029)")
    c.add_argument("--anos", type=_anos_locais, default=list(zonas.ANOS_LOCAIS),
                   help="anos separados por vírgula, ou todos (padrão: 2026 a 2018)")
    c.add_argument("--atualizar", action="store_true", help="consulta o servidor mesmo se já baixado")
    c.add_argument("--sem-bronze", action="store_true")

    c = sub.add_parser("eleitorado", help="perfil do eleitorado, comparecimento por perfil e seções (ADR-055)")
    c.add_argument("--anos", type=_anos_eleitorado, default=list(eleitorado.ANOS_ELEITORADO),
                   help="anos separados por vírgula, ou todos (padrão: 2026 a 2018)")
    c.add_argument("--saida", help="diretório onde gravar eleitorado/<ano>/ (padrão: o dos feeds)")
    c.add_argument("--pacotes", help="diretório onde gravar eleitorado-<ano>.tar, para o site dos painéis")
    c.add_argument("--apagar-zips", action="store_true", help="apaga os ZIPs do TSE depois de cada ano")
    c.add_argument("--atualizar", action="store_true", help="consulta o servidor mesmo se já baixado")
    c.add_argument("--sem-bronze", action="store_true")

    c = sub.add_parser("horarios", help="horários das urnas: abertura, encerramento e boletim de cada seção (ADR-056)")
    c.add_argument("--anos", type=_anos_horarios, default=list(horarios.ANOS_HORARIOS),
                   help="anos separados por vírgula, ou todos (padrão: 2026 a 2018)")
    c.add_argument("--saida", help="diretório onde gravar horarios/<ano>/ (padrão: o dos feeds)")
    c.add_argument("--pacotes", help="diretório onde gravar horarios-<ano>.tar, para o site dos painéis")
    c.add_argument("--apagar-zips", action="store_true", help="apaga cada ZIP do TSE depois de lido")
    c.add_argument("--atualizar", action="store_true", help="consulta o servidor mesmo se já baixado")

    c = sub.add_parser("votos-hora", help="votos por hora, pelos logs das urnas (ADR-057)")
    c.add_argument("--ano", type=int, choices=votos_hora.ANOS_VOTOS, required=True)
    c.add_argument("--ufs", type=lambda s: [u.strip().lower() for u in s.split(",") if u.strip()],
                   help="UFs a ler, separadas por vírgula, ou todas (zz: o exterior)")
    c.add_argument("--parciais", default="votos-hora-parciais", help="diretório das parciais de cada UF")
    c.add_argument("--montar", action="store_true", help="junta as parciais e grava votos-hora/<ano>/")
    c.add_argument("--saida", help="diretório onde gravar votos-hora/<ano>/ (padrão: o dos feeds)")
    c.add_argument("--pacotes", help="diretório onde gravar votos-hora-<ano>.tar, para o site dos painéis")
    c.add_argument("--trabalhadores", type=int, default=24, help="pedidos ao TSE ao mesmo tempo (padrão: 24)")
    c.add_argument("--turnos-esperados", type=int, default=0,
                   help="falha se o catálogo listar menos turnos da UF (o catálogo às vezes responde versão antiga)")

    c = sub.add_parser("conferir", help="conferência seção a seção: a votação por seção contra o total (ADR-053)")
    c.add_argument("--anos", type=_anos, default=list(conferencia.ANOS_SECAO),
                   help="anos separados por vírgula (padrão: o em aberto)")
    c.add_argument("--refazer", action="store_true", help="confere mesmo sem mudança no arquivo")
    c.add_argument("--base", default=tse.BASE, help="endereço do sistema de resultados")
    c.add_argument("--sem-bronze", action="store_true")

    c = sub.add_parser("ao-vivo", help="coleta a apuração em andamento")
    c.add_argument("--eleicao", required=True, help="id do catálogo, ex.: 2026-1t-geral")
    c.add_argument("--cargos", help="slugs separados por vírgula (padrão: todos)")
    c.add_argument("--ufs", help="siglas separadas por vírgula (padrão: todas)")
    c.add_argument("--intervalo", type=float, default=30, help="segundos entre passadas")
    c.add_argument("--orcamento", type=int, default=600, help="arquivos de município por passada")
    c.add_argument("--municipios-proporcionais", action="store_true",
                   help="também deputados por município (muito mais arquivos)")
    c.add_argument("--fotos-municipais", action="store_true", help="também fotos de prefeito e vereador")
    c.add_argument("--uma-vez", action="store_true", help="uma passada só")
    c.add_argument("--parar-estavel", type=float, default=60,
                   help="minutos sem mudança, com todas as seções totalizadas, para parar (0 desliga)")
    c.add_argument("--limite-minutos", type=float,
                   help="para ao fim da passada depois disso; com a apuração em andamento, sai com o código 3")
    c.add_argument("--sem-bronze", action="store_true", help="não guardar as respostas como prova")
    c.add_argument("--nuvem", action="store_true", help="publica no R2 a cada passada (ADR-026)")
    c.add_argument("--base", default=tse.BASE)

    h = sub.add_parser("historico", help="eleições passadas (dados abertos)")
    hs = h.add_subparsers(dest="acao", required=True)
    c = hs.add_parser("baixar", help="baixa os ZIPs do ano")
    c.add_argument("--anos", type=_anos, required=True, help="anos separados por vírgula, ou todos")
    c.add_argument("--atualizar", action="store_true", help="consulta o servidor mesmo se já baixado")
    c.add_argument("--sem-bronze", action="store_true")
    c = hs.add_parser("processar", help="gera os feeds a partir dos ZIPs baixados")
    c.add_argument("--anos", type=_anos, required=True, help="anos separados por vírgula, ou todos")
    c.add_argument("--limite-municipio", type=int, default=50,
                   help="candidatos por município nos cargos proporcionais (o da UF tem todos)")

    c = sub.add_parser("simular", help="apuração fictícia a partir de arquivos finais")
    c.add_argument("--arquivos", default=str(FIXTURES_TSE))
    c.add_argument("--eleicao", default="2026-1t-geral")
    c.add_argument("--etapas", type=int, default=12)
    c.add_argument("--intervalo", type=float, default=5)
    c.add_argument("--ufs")

    c = sub.add_parser("amostra", help="feeds de exemplo a partir das fixtures (sem rede)")
    c.add_argument("--arquivos", default=str(FIXTURES_TSE))
    c.add_argument("--sem-referencias", action="store_true",
                   help="sem o mapa e o cadastro (para regenerar a amostra versionada nos testes)")

    c = sub.add_parser("servir", help="serve o portal e os feeds localmente")
    c.add_argument("--site", default=str(SITE_PADRAO))
    c.add_argument("--host", default="127.0.0.1")
    c.add_argument("--porta", type=int, default=8080)

    sub.add_parser("verificar", help="confere o contrato dos feeds gravados")

    c = sub.add_parser("medir", help="tamanho dos feeds contra os limites gratuitos do R2 e do Supabase")
    c.add_argument("--resumo", help="acrescenta o resumo em Markdown a este arquivo")
    c.add_argument("--maiores", type=int, default=10, help="quantos dos maiores arquivos listar")
    return p


COMANDOS = {"preparar": cmd_preparar, "publicar": cmd_publicar, "catalogo": cmd_catalogo, "municipios": cmd_municipios, "mapas": cmd_mapas, "zonas": cmd_zonas, "eleitorado": cmd_eleitorado, "horarios": cmd_horarios, "votos-hora": cmd_votos_hora, "conferir": cmd_conferir, "ao-vivo": cmd_ao_vivo,
            "simular": cmd_simular, "amostra": cmd_amostra, "servir": cmd_servir, "verificar": cmd_verificar,
            "medir": cmd_medir}


def main(argv: list[str] | None = None) -> int:
    """Ponto de entrada: lê argumentos e configuração e despacha para o comando; devolve o código de saída.

    Os comandos que não consultam as fontes (``servir``, ``verificar``, ``amostra``, ``publicar``, ``medir``)
    dispensam o contato da coleta. ``--saida`` sobrepõe o diretório dos feeds da configuração. Falta de
    configuração da nuvem (``--nuvem``, ``publicar``) vira mensagem e código 2.
    """
    args = construir_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verboso else logging.WARNING,
                        format="%(asctime)s %(name)s %(message)s")
    offline = args.comando in ("servir", "verificar", "amostra", "publicar", "medir")
    try:
        cfg = carregar(Path(args.config) if args.config else None, exigir_contato=not offline)
    except ConfiguracaoAusente as erro:
        print(f"erro: {erro}", file=sys.stderr)
        return 2
    if args.saida:
        cfg.saida = Path(args.saida)
    if args.comando == "historico":
        return (cmd_historico_baixar if args.acao == "baixar" else cmd_historico_processar)(cfg, args)
    try:
        return COMANDOS[args.comando](cfg, args)
    except ConfiguracaoAusente as erro:
        print(f"erro: {erro}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
