"""Testes do verificador de vocabulário controlado.

Cobrem o caminho feliz, os caminhos de erro e — o mais importante — os falsos
positivos conhecidos. O falso positivo aqui não é um detalhe: se 'desvio
padrão' disparasse, o motor de detecção seria impossível de escrever, e a
tentação seria desligar o verificador. Um guarda-corpo que atrapalha o
trabalho legítimo acaba desativado, e aí não guarda mais nada.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lint_vocabulario import Vocabulario, normalizar  # noqa: E402


@pytest.fixture(scope="module")
def vocab() -> Vocabulario:
    return Vocabulario.carregar()


# --------------------------------------------------------------------------
# Normalização
# --------------------------------------------------------------------------

@pytest.mark.parametrize("entrada,esperado", [
    ("Corrupção", "corrupcao"),
    ("CORRUPÇÃO", "corrupcao"),
    ("corrupcao", "corrupcao"),
    ("Indício", "indicio"),
    ("órgão", "orgao"),
    ("FRAUDE", "fraude"),
])
def test_normalizar_remove_acento_e_caixa(entrada, esperado):
    assert normalizar(entrada) == esperado


# --------------------------------------------------------------------------
# Deteccao de termo proibido
# --------------------------------------------------------------------------

@pytest.mark.parametrize("texto,termo", [
    ("Houve desvio de verba na prefeitura.", "desvio"),
    ("Contrato com indício de fraude.", "fraude"),
    ("Caso claro de superfaturamento.", "superfaturamento"),
    ("A empresa é suspeita.", "suspeita"),
    ("Contratação irregular.", "irregular"),
    ("Isso configura crime.", "crime"),
    ("O gestor é culpado.", "culpado"),
])
def test_detecta_termo_proibido(vocab, texto, termo):
    achados = vocab.verificar_texto(texto)
    assert len(achados) == 1
    assert achados[0].termo == termo
    assert achados[0].sugestao


def test_detecta_termo_acentuado(vocab):
    """Escrever com acento nao pode ser rota de fuga."""
    achados = vocab.verificar_texto("Indícios de corrupção no município.")
    assert [a.termo for a in achados] == ["corrupcao"]


def test_detecta_independente_de_caixa(vocab):
    achados = vocab.verificar_texto("FRAUDE comprovada")
    assert [a.termo for a in achados] == ["fraude"]


def test_reporta_linha_e_coluna(vocab):
    texto = "linha limpa\noutra linha limpa\nisto e fraude"
    achados = vocab.verificar_texto(texto)
    assert len(achados) == 1
    assert achados[0].linha == 3
    assert achados[0].coluna == texto.splitlines()[2].index("fraude") + 1


def test_varios_termos_na_mesma_linha(vocab):
    achados = vocab.verificar_texto("houve fraude e desvio")
    assert sorted(a.termo for a in achados) == ["desvio", "fraude"]


# --------------------------------------------------------------------------
# Falsos positivos conhecidos — o coracao destes testes
# --------------------------------------------------------------------------

@pytest.mark.parametrize("texto", [
    "Escore robusto calculado com desvio padrão.",
    "MAD é o desvio absoluto mediano da amostra.",
    "O desvio absoluto médio mede a aderência.",
    "Dois desvios padrão acima da mediana.",
    "Teste de desvio da distribuição esperada (Benford).",
])
def test_expressao_estatistica_legitima_nao_dispara(vocab, texto):
    """'desvio' sozinho e proibido, mas 'desvio padrao' e nome de medida."""
    assert vocab.verificar_texto(texto) == []


def test_identificador_snake_case_nao_dispara(vocab):
    """\\b impede casar dentro de identificador: o underscore e caractere de palavra."""
    assert vocab.verificar_texto("valor = desvio_padrao(amostra)") == []


def test_desvio_sozinho_ainda_dispara(vocab):
    """A mascara de expressoes permitidas nao pode abrir buraco geral."""
    achados = vocab.verificar_texto("houve desvio de recursos")
    assert [a.termo for a in achados] == ["desvio"]


def test_expressao_permitida_e_termo_proibido_na_mesma_linha(vocab):
    achados = vocab.verificar_texto("desvio padrão alto sugere fraude")
    assert [a.termo for a in achados] == ["fraude"]


def test_termo_como_substring_nao_dispara(vocab):
    """'crime' nao pode casar dentro de outra palavra."""
    assert vocab.verificar_texto("discriminemos os casos") == []


# --------------------------------------------------------------------------
# Marcador de excecao
# --------------------------------------------------------------------------

def test_marcador_de_excecao_isenta_a_linha(vocab):
    texto = f'texto_contestacao = "houve fraude"  # {vocab.marcador}'
    assert vocab.verificar_texto(texto) == []


def test_marcador_isenta_apenas_a_propria_linha(vocab):
    texto = (
        f'campo = "fraude"  # {vocab.marcador}\n'
        'titulo = "fraude"'
    )
    achados = vocab.verificar_texto(texto)
    assert len(achados) == 1
    assert achados[0].linha == 2


# --------------------------------------------------------------------------
# Texto aprovado do DOC-08
# --------------------------------------------------------------------------

def test_frase_aprovada_do_doc08_passa(vocab):
    aprovado = (
        "O preço unitário contratado foi de R$ 48,00. A mediana observada "
        "para este item no mesmo trimestre, entre 412 contratações de outros "
        "entes, foi de R$ 11,20. O valor está 4,3 vezes acima dessa "
        "referência. Documento fonte disponível para verificação."
    )
    assert vocab.verificar_texto(aprovado) == []


def test_frase_reprovada_do_doc08_falha(vocab):
    reprovado = (
        "Prefeitura pagou R$ 48,00 em item que custa R$ 11,20, indicando "
        "superfaturamento de mais de 300%."
    )
    achados = vocab.verificar_texto(reprovado)
    assert [a.termo for a in achados] == ["superfaturamento"]


def test_frase_aprovada_de_fracionamento_passa(vocab):
    aprovado = (
        "Foram identificadas 14 contratações diretas com o mesmo fornecedor, "
        "para objetos de descrição similar, no intervalo de 180 dias, somando "
        "R$ 218.400,00. O limite legal para dispensa por valor nesta "
        "categoria, na data dos atos, era de R$ 65.492,11."
    )
    assert vocab.verificar_texto(aprovado) == []


# --------------------------------------------------------------------------
# Integridade da configuracao
# --------------------------------------------------------------------------

def test_todo_proibido_tem_sugestao(vocab):
    faltando = [t for t, s in vocab.proibidos.items() if not s.strip()]
    assert faltando == [], f"termos sem orientacao de substituicao: {faltando}"

def test_lista_de_proibidos_esta_normalizada(vocab):
    assert all(t == normalizar(t) for t in vocab.proibidos)

def test_permitidos_ordenados_do_maior_para_o_menor(vocab):
    tamanhos = [len(p) for p in vocab.permitidos]
    assert tamanhos == sorted(tamanhos, reverse=True)

def test_toda_expressao_permitida_contem_termo_proibido(vocab):
    """Uma expressao permitida que nao contem termo proibido e ruido na lista."""
    for expressao in vocab.permitidos:
        assert any(termo in expressao for termo in vocab.proibidos), \
            f"{expressao!r} nao precisa estar na lista de permitidos"


# --------------------------------------------------------------------------
# 'esquema': proibido como conluio, legitimo como modelagem de dados
# --------------------------------------------------------------------------

@pytest.mark.parametrize("texto", [
    "DOC-05: esquema canônico e dicionário de dados.",
    "Alarme de mudança de esquema na fonte (RF-CO-17).",
    "Registrar a versão do esquema em cada execução.",
    "Toda fonte é convertida para o esquema de dados único.",
])
def test_esquema_como_termo_de_modelagem_nao_dispara(vocab, texto):
    assert vocab.verificar_texto(texto) == []


def test_esquema_como_conluio_dispara(vocab):
    achados = vocab.verificar_texto("A prefeitura montou um esquema com a empresa.")
    assert [a.termo for a in achados] == ["esquema"]


def test_rotulos_publicos_estao_entre_os_alvos(vocab):
    assert "packages/canonico/lumen_canonico/rotulos.py" in vocab.alvos


# --------------------------------------------------------------------------
# Arquivos, alvos e isencoes
#
# O modo de falha mais perigoso deste verificador nao e deixar de pegar um
# termo: e isentar arquivos demais em silencio. Um bug na isencao faria o
# guarda-corpo aprovar tudo, e ninguem perceberia ate a primeira publicacao.
# --------------------------------------------------------------------------

import json as _json

from lint_vocabulario import main as _main


def _arvore(raiz, arquivos: dict[str, str]):
    for caminho, conteudo in arquivos.items():
        destino = raiz / caminho
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(conteudo, encoding="utf-8")


def _config(tmp_path, **sobrescrever) -> "Path":
    base = _json.load(open(Path(__file__).resolve().parent.parent / "vocabulario.json", encoding="utf-8"))
    base.update(sobrescrever)
    arquivo = tmp_path / "vocab.json"
    arquivo.write_text(_json.dumps(base), encoding="utf-8")
    return arquivo


def test_verificar_arquivo_real(vocab, tmp_path):
    arquivo = tmp_path / "pagina.md"
    arquivo.write_text("linha limpa\nhouve fraude aqui\n", encoding="utf-8")
    achados = vocab.verificar_arquivo(arquivo)
    assert [(a.linha, a.termo) for a in achados] == [(2, "fraude")]
    assert achados[0].caminho == arquivo


def test_arquivo_binario_e_ignorado_sem_erro(vocab, tmp_path):
    arquivo = tmp_path / "imagem.png"
    arquivo.write_bytes(b"\x89PNG\r\n\x1a\n\xff\xfe\x00fraude")
    assert vocab.verificar_arquivo(arquivo) == []


def test_coleta_encontra_os_alvos_e_respeita_isentos(tmp_path):
    _arvore(tmp_path, {
        "conteudo/pagina.md": "texto",
        "conteudo/contestacao_ente.md": "texto de terceiro",
        "packages/deteccao/regras/b01.py": "codigo",
        "packages/deteccao/motor/interno.py": "nao e alvo",
    })
    vocab = Vocabulario.carregar(_config(tmp_path))
    encontrados = {p.relative_to(tmp_path).as_posix() for p in vocab.coletar_alvos(tmp_path)}
    assert "conteudo/pagina.md" in encontrados
    assert "packages/deteccao/regras/b01.py" in encontrados
    assert "conteudo/contestacao_ente.md" not in encontrados   # isento
    assert "packages/deteccao/motor/interno.py" not in encontrados  # fora dos alvos


def test_isencao_nao_isenta_arquivo_comum(vocab, tmp_path):
    """Regressao: a isencao de 'contestacao*' nao pode vazar para outros arquivos."""
    assert vocab.esta_isento(tmp_path / "conteudo" / "contestacao_resposta.md")
    assert not vocab.esta_isento(tmp_path / "conteudo" / "pagina.md")
    assert not vocab.esta_isento(tmp_path / "packages" / "deteccao" / "regras" / "b01.py")


def test_violacao_em_arquivo_de_regra_e_detectada_de_ponta_a_ponta(tmp_path, capsys):
    """O modelo de explicacao de uma regra vive em regras/ e e varrido na CI."""
    _arvore(tmp_path, {
        "packages/deteccao/regras/b01.py":
            'EXPLICACAO = "Indicio de fraude por fracionamento"\n',
    })
    codigo = _main(["--config", str(_config(tmp_path)), "--raiz", str(tmp_path)])
    saida = capsys.readouterr().out
    assert codigo == 1
    assert "fraude" in saida and "b01.py" in saida


# --------------------------------------------------------------------------
# Linha de comando
# --------------------------------------------------------------------------

def test_cli_arquivo_limpo_sai_com_zero(tmp_path, capsys):
    arquivo = tmp_path / "ok.md"
    arquivo.write_text("valor 4,3 vezes acima da referencia", encoding="utf-8")
    assert _main([str(arquivo)]) == 0
    assert "nenhuma violação" in capsys.readouterr().out


def test_cli_violacao_sai_com_um_e_orienta(tmp_path, capsys):
    arquivo = tmp_path / "ruim.md"
    arquivo.write_text("caso de corrupção", encoding="utf-8")
    assert _main([str(arquivo)]) == 1
    saida = capsys.readouterr().out
    assert "corrupcao" in saida
    assert "DOC-08" in saida
    assert "lumen:vocabulario-ok" in saida


def test_cli_sem_alvos_nao_falha(tmp_path, capsys):
    assert _main(["--config", str(_config(tmp_path)), "--raiz", str(tmp_path)]) == 0
    assert "Nenhum arquivo alvo" in capsys.readouterr().out


def test_cli_listar(capsys):
    assert _main(["--listar"]) == 0
    saida = capsys.readouterr().out
    assert "termos proibidos" in saida
    assert "desvio padrao" in saida


def test_cli_ignora_argumento_que_nao_e_arquivo(tmp_path, capsys):
    assert _main([str(tmp_path / "nao_existe.md")]) == 0


def test_config_sem_proibidos_nao_quebra():
    vazio = Vocabulario({"proibidos": {}, "permitidos": []})
    assert vazio.verificar_texto("fraude") == []


# --------------------------------------------------------------------------
# Expressao permitida partida entre linhas
#
# Bug encontrado ao simular a CI sobre o proprio README: texto com quebra de
# linha manual parte "esquema canonico" em duas linhas, e a verificacao linha
# a linha acusava o "esquema" orfao. Em markdown e docstring isso acontece o
# tempo todo.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("texto", [
    "o modelo usa o esquema\ncanônico do DOC-05",
    "o modelo usa o esquema\n    canônico do DOC-05",      # linha seguinte indentada
    "calculado pelo desvio\npadrão robusto",
    "o desvio absoluto\nmediano da amostra",               # expressao de tres palavras
])
def test_expressao_permitida_partida_entre_linhas_nao_dispara(vocab, texto):
    assert vocab.verificar_texto(texto) == []


def test_termo_orfao_no_fim_da_linha_ainda_dispara(vocab):
    """A quebra de linha nao pode virar rota de fuga para o termo sozinho."""
    achados = vocab.verificar_texto("montaram um esquema\npara direcionar a compra")
    assert [(a.linha, a.termo) for a in achados] == [(1, "esquema")]


def test_numero_de_linha_preservado_apos_mascara_multilinha(vocab):
    texto = "linha 1 com desvio\npadrão\nlinha 3\nlinha 4 com fraude"
    achados = vocab.verificar_texto(texto)
    assert [(a.linha, a.termo) for a in achados] == [(4, "fraude")]


def test_coluna_preservada_apos_mascara(vocab):
    texto = "desvio padrão e fraude"
    achados = vocab.verificar_texto(texto)
    assert achados[0].coluna == texto.index("fraude") + 1


def test_verificar_linha_usa_o_numero_informado(vocab):
    achados = vocab.verificar_linha("houve fraude", 42, Path("x.md"))
    assert achados[0].linha == 42
