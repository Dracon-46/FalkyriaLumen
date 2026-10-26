"""Conferência seção a seção (ADR-053): soma da votação por seção contra o total divulgado."""

import io
import json
from pathlib import Path

from lumen_eleicoes import conferencia, feeds, tse
from lumen_eleicoes.transferencia import Manifesto

FIX = Path(__file__).resolve().parents[3] / "testes" / "fixtures" / "tse"

CABECALHO = ('"DT_GERACAO";"HH_GERACAO";"ANO_ELEICAO";"CD_TIPO_ELEICAO";"NM_TIPO_ELEICAO";"NR_TURNO";"CD_ELEICAO";'
             '"DS_ELEICAO";"DT_ELEICAO";"TP_ABRANGENCIA";"SG_UF";"SG_UE";"NM_UE";"CD_MUNICIPIO";"NM_MUNICIPIO";'
             '"NR_ZONA";"NR_SECAO";"CD_CARGO";"DS_CARGO";"NR_VOTAVEL";"NM_VOTAVEL";"QT_VOTOS";"NR_LOCAL_VOTACAO";'
             '"SQ_CANDIDATO";"NM_LOCAL_VOTACAO";"DS_LOCAL_VOTACAO_ENDERECO"')


def linha(uf: str, secao: int, numero: str, nome: str, votos: int, turno: int = 1, cargo: int = 1) -> str:
    """Uma linha do CSV da votação por seção, no formato do TSE."""
    return (f'"06/10/2026";"14:03:43";2026;2;"Eleição Ordinária";{turno};{6256 + turno};"Eleição Geral Federal 2026";'
            f'"04/10/2026";"F";"{uf.upper()}";"BR";"BRASIL";1;"X";1;{secao};{cargo};"Presidente";{numero};"{nome}";'
            f'{votos};1;1;"ESCOLA";"RUA"')


def csv_secoes(linhas: list[str]) -> io.BytesIO:
    """O CSV em Latin-1, como o TSE publica."""
    return io.BytesIO(("\r\n".join([CABECALHO, *linhas]) + "\r\n").encode("latin-1"))


def test_soma_por_turno_uf_e_secao():
    somas = conferencia.somar_secoes(csv_secoes([
        linha("sp", 1, "13", "LULA", 10), linha("sp", 1, "22", "FLAVIO", 7), linha("sp", 2, "13", "LULA", 3),
        linha("ba", 1, "13", "LULA", 20), linha("ba", 1, "95", "VOTO BRANCO", 1),
        linha("ba", 1, "13", "LULA", 50, turno=2),
        linha("ba", 1, "55", "GOVERNADOR", 99, cargo=3),           # outro cargo: fora
    ]))
    assert set(somas) == {1, 2}
    um = somas[1]
    assert um.eleicao_tse == 6257 and um.brasil == {"13": 33, "22": 7, "95": 1}
    assert um.por_uf["sp"]["13"] == 13 and um.secoes_por_uf == {"sp": 2, "ba": 1} and len(um.secoes) == 3
    assert somas[2].brasil == {"13": 50}


def test_linhas_comparam_candidatos_brancos_nulos_e_tecnicos():
    r = tse.ler_resultado((FIX / "br-c0001-e006257-u.json").read_bytes())
    votos = {c.numero: c.votos for c in r.candidatos}
    votos.update({"95": r.votos.brancos, "96": r.votos.nulos - r.votos.nulos_tecnicos, "28": r.votos.nulos_tecnicos})
    linhas = conferencia.linhas_da_conferencia(votos, r, {"28": "LEONARDO ALVES DE ARAUJO"})
    assert all(linha["diferenca"] == 0 for linha in linhas)
    tecnicos = linhas[-1]
    assert tecnicos["rotulo"] == "Nulos técnicos" and tecnicos["secoes"] == 5246 and "28 (LEONARDO" in tecnicos["detalhe"]
    # Um voto a menos num candidato aparece como diferença
    votos["13"] -= 1
    lula = next(linha for linha in conferencia.linhas_da_conferencia(votos, r, {}) if linha["numero"] == "13")
    assert lula["diferenca"] == -1


def test_feed_da_conferencia(tmp_path):
    r = tse.ler_resultado((FIX / "br-c0001-e006257-u.json").read_bytes())
    linhas = [linha("sp", 1, c.numero, c.nome_urna, c.votos) for c in r.candidatos]
    linhas += [linha("sp", 1, "95", "VOTO BRANCO", r.votos.brancos),
               linha("sp", 1, "96", "VOTO NULO", r.votos.nulos - r.votos.nulos_tecnicos),
               linha("sp", 1, "28", "LEONARDO ALVES DE ARAUJO", r.votos.nulos_tecnicos)]
    soma = conferencia.somar_secoes(csv_secoes(linhas))[1]
    e = tse.ler_catalogo((FIX / "ele-c_recorte.json").read_bytes())
    e = next(x for x in e if x.id == "2026-1t-geral")
    manifesto = Manifesto(url="u", arquivo="votacao_secao_2026_BR.zip", tamanho=1, sha256="ab", etag=None,
                          ultima_modificacao=None, baixado_em="2026-10-26T00:00:00+00:00")
    feed = conferencia.feed_conferencia(eleicao=e, soma=soma, divulgado={"br": r}, manifesto=manifesto,
                                        urls_divulgado={"br": "https://resultados"})
    assert feed["tipo"] == "conferencia" and feed["brasil"]["confere"] is True
    # A UF sem resultado divulgado aparece sem conferência, e o todo não confere
    assert feed["ufs"] == [{"uf": "sp", "nome": "São Paulo", "secoes": 1, "secoes_divulgadas": None,
                            "conferida": False, "confere": False, "linhas": []}]
    assert feed["confere"] is False
    caminho = conferencia.gravar_conferencia(feeds.EscritorFeeds(tmp_path), e, feed)
    assert caminho == tmp_path / "2026-1t-geral" / "presidente" / "conferencia.json"
    assert json.loads(caminho.read_text(encoding="utf-8"))["secoes"]["no_arquivo"] == 1
    # O verificador dos feeds conhece o tipo
    from lumen_eleicoes.verificacao import Relatorio, verificar_feed
    rel = Relatorio()
    verificar_feed(caminho, feed, rel)
    assert rel.problemas == []


class _Resposta:
    """Resposta mínima do cliente HTTP: status e conteúdo."""

    def __init__(self, status_http: int, conteudo: bytes = b""):
        self.status_http = status_http
        self.conteudo = conteudo


class _ClienteResultados:
    """Sistema de resultados de mentira: o catálogo e o resultado do Brasil das fixtures; o resto, 404."""

    def __init__(self):
        self.pedidos: list[str] = []

    def obter(self, url: str, cabecalhos=None):
        self.pedidos.append(url)
        if url.endswith("ele-c.json"):
            return _Resposta(200, (FIX / "ele-c_recorte.json").read_bytes())
        if url.endswith("/br-c0001-e006257-u.json"):
            return _Resposta(200, (FIX / "br-c0001-e006257-u.json").read_bytes())
        return _Resposta(404)


def test_etapa_da_preparacao(tmp_path, monkeypatch):
    from lumen_eleicoes import preparacao
    from lumen_eleicoes.configuracao import carregar

    monkeypatch.setenv("LUMEN_CONTATO", "c@exemplo.org")
    monkeypatch.delenv("LUMEN_ELEICOES_SAIDA", raising=False)
    toml = tmp_path / "lumen.toml"
    toml.write_text(f'[dados]\nraiz = "{(tmp_path / "dados").as_posix()}"\n[eleicoes]\n'
                    f'saida = "{(tmp_path / "feeds").as_posix()}"\n', encoding="utf-8")
    cfg = carregar(toml)
    r = tse.ler_resultado((FIX / "br-c0001-e006257-u.json").read_bytes())
    zip_secoes = tmp_path / "votacao_secao_2026_BR.zip"
    import zipfile
    linhas = [linha("ba", 1, c.numero, c.nome_urna, c.votos) for c in r.candidatos]
    linhas += [linha("ba", 1, "95", "VOTO BRANCO", r.votos.brancos),
               linha("ba", 1, "96", "VOTO NULO", r.votos.nulos - r.votos.nulos_tecnicos),
               linha("ba", 1, "28", "LEONARDO ALVES DE ARAUJO", r.votos.nulos_tecnicos)]
    with zipfile.ZipFile(zip_secoes, "w") as zf:
        zf.writestr("votacao_secao_2026_BR.csv", csv_secoes(linhas).getvalue())
    manifesto = Manifesto(url="u", arquivo=zip_secoes.name, tamanho=1, sha256="ab", etag=None,
                          ultima_modificacao=None, baixado_em="2026-10-26T00:00:00+00:00")
    monkeypatch.setattr(conferencia, "baixar_secoes", lambda *a, **k: (zip_secoes, manifesto))
    cliente = _ClienteResultados()
    prep = preparacao.Preparacao(cfg, preparacao.OpcoesPreparacao(portal=False, bronze=False),
                                 cliente_resultados=cliente, saida=lambda m: None)
    prep.conferir_secoes(2026)
    assert prep.resumo.erros == [] and prep.resumo.conferencias == [{"ano": 2026, "situacao": "conferida", "turnos": [1]}]
    feed = json.loads((cfg.saida / "2026-1t-geral" / "presidente" / "conferencia.json").read_text(encoding="utf-8"))
    assert feed["brasil"]["confere"] is True and [u["uf"] for u in feed["ufs"]] == ["ba"]
    # A segunda vez, com o mesmo arquivo, não pede de novo o resultado divulgado
    pedidos = len(cliente.pedidos)
    prep.conferir_secoes(2026)
    assert len(cliente.pedidos) == pedidos and prep.resumo.conferencias[-1]["situacao"] == "sem mudança na fonte"
