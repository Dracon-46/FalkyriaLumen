"""Avisos: o que aconteceu em cada ente e merece um olhar, reunido numa página só (ADR-047).

Sem os avisos, quem acompanha um município precisa abrir cada painel e cada contratação. Aqui o Lumen junta,
por ente, os sinais que ele já calcula a partir de dados públicos, cada um com o que aconteceu, o que
observar e a fonte:

- **fornecedor sancionado** (regra J-01, ADR-031): contrato assinado com empresa que, na data da assinatura,
  constava no CEIS ou no CNEP numa sanção que impede contratar, com o alcance da sanção;
- **valor a conferir** (ADR-028): processo ou contrato publicado com valor acima do teto de plausibilidade,
  fora das somas dos painéis;
- **LRF: não consta no extrato**: relatório com prazo vencido que não aparece no extrato do Tesouro;
- **LRF: entregas após o prazo**: no exercício, ``ATRASOS_MINIMOS`` ou mais relatórios entregues depois do
  prazo legal (um atraso isolado é comum e não vira aviso);
- **portal de transparência**: entidade do ente com nível "Inexistente" ou "Inicial" no PNTP.

Nenhum aviso é conclusão sobre a conduta de alguém: é o fato observado nos dados, com a referência usada. Todo
aviso tem um código estável (``id``) e pode ser contestado por quem é citado (``contestacoes``, das issues
com o rótulo ``contestacao``): a marca aparece na publicação seguinte, sem análise prévia (DOC-08, seção 6);
contestação fechada com o rótulo ``removido`` tira o aviso, com ``retificado`` mantém com a nota. A ordem é
sempre pela data, nunca por ente (PUB-07). Fornecedor pessoa física não aparece em aviso nenhum (RNF-19).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from lumen_canonico.documentos import mascarar_cpfs_no_texto

from .cadastro import Cadastro
from .comum import UFS, ler_json, tipo_do_ente, uf_do_ente

ARQUIVO_J01 = "deteccao-j01.json.gz"
ARQUIVO_CONTESTACOES = "contestacoes.json"
# Atrasos no mesmo exercício a partir dos quais as entregas após o prazo viram aviso
ATRASOS_MINIMOS = 3
NIVEIS_BAIXOS = {"Inexistente", "Inicial"}
ULTIMOS_PANORAMA = 200

TIPOS = {
    "fornecedor_sancionado": "Contrato com empresa sancionada",
    "valor_a_conferir": "Valor a conferir na fonte",
    "lrf_nao_consta": "Relatório fiscal não consta no extrato",
    "lrf_atrasos": "Relatórios fiscais entregues após o prazo",
    "transparencia_baixa": "Portal de transparência com nível baixo",
}

CADASTROS = {"CEIS": "https://portaldatransparencia.gov.br/sancoes/ceis",
             "CNEP": "https://portaldatransparencia.gov.br/sancoes/cnep"}
ALCANCE = {
    "todas_as_esferas": "a sanção vale para contratos com qualquer órgão público, de qualquer esfera",
    "mesma_esfera": "a sanção vale para a esfera de governo deste órgão",
    "mesmo_orgao": "a sanção foi aplicada por este mesmo órgão",
    "a_conferir": "o alcance da sanção depende do texto dela: confira se alcança este órgão",
    "abrangencia_nao_informada": "o cadastro não informa o alcance da sanção: confira se alcança este órgão",
}


def codigo_do_aviso(*partes: object) -> str:
    """Código estável do aviso (12 caracteres), a partir do tipo e do que o identifica."""
    return hashlib.sha1("|".join(str(p) for p in partes).encode("utf-8")).hexdigest()[:12]


@dataclass
class Aviso:
    """Um aviso, na forma do arquivo publicado."""

    id: str
    tipo: str
    data: str | None
    ente: str | None          # None: órgão sem ente no PNCP (empresas públicas federais, por exemplo)
    titulo: str
    detalhe: list[str]
    observar: str
    fonte: dict
    orgao: dict | None = None
    chave: str | None = None
    valor: float | None = None
    contestacao: dict | None = None
    uf: str | None = None     # a UF do contrato, quando não há ente

    def lugar(self) -> str | None:
        """Em que arquivo o aviso entra: ``"1"`` (a União), a sigla da UF, ou None se não há como saber."""
        if self.ente == "1":
            return "1"
        if self.ente and self.ente[:2] in UFS:
            return UFS[self.ente[:2]]
        return self.uf.upper() if self.uf and self.uf.upper() in UFS.values() else None

    def para_json(self, cadastro: Cadastro) -> dict:
        """O aviso com o nome do ente, como o portal lê."""
        ente = ({"codigo": self.ente, "nome": cadastro.nome(self.ente), "uf": uf_do_ente(self.ente),
                 "tipo": tipo_do_ente(self.ente)} if self.ente else
                {"codigo": None, "nome": "Órgão sem ente identificado no PNCP", "uf": self.uf, "tipo": None})
        return {"id": self.id, "tipo": self.tipo, "rotulo": TIPOS[self.tipo], "data": self.data, "ente": ente,
                "orgao": self.orgao, "titulo": self.titulo, "detalhe": self.detalhe, "observar": self.observar,
                "fonte": self.fonte, "chave": self.chave, "valor": self.valor, "contestacao": self.contestacao}


def _moeda(v: float | None) -> str:
    """"R$ 1.234.567,89"."""
    if v is None:
        return "sem valor publicado"
    return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _data(iso: str | None) -> str:
    """"2026-10-13" → "13/10/2026"."""
    if not iso or len(iso) < 10:
        return iso or "—"
    return f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}"


# ------------------------------------------------------------------------------------------ sinais

def de_j01(relatorio: dict, orgaos: dict[str, list]) -> list[Aviso]:
    """Os avisos das coincidências da J-01. O ente é o do órgão contratante (``orgaos``: CNPJ → [nome, esfera, ente])."""
    saida = []
    for c in relatorio.get("coincidencias") or []:
        contrato, forn, s = c.get("contrato") or {}, c.get("fornecedor") or {}, c.get("sancao") or {}
        cnpj_forn = str(forn.get("cnpj") or "")
        if len(cnpj_forn) != 14:          # só pessoa jurídica (a regra já filtra; aqui não passa nada além)
            continue
        ente = (orgaos.get(str(contrato.get("orgao_cnpj"))) or [None, None, None])[2] or None
        cadastro = str(s.get("cadastro") or "").upper()
        vigencia = f"de {_data(s.get('data_inicio'))}" + (f" a {_data(s.get('data_fim'))}" if s.get("data_fim") else ", sem fim")
        saida.append(Aviso(
            id=codigo_do_aviso("j01", contrato.get("chave"), cnpj_forn, s.get("codigo")),
            tipo="fornecedor_sancionado", data=contrato.get("data_assinatura"), ente=ente,
            titulo=f"Contrato assinado com empresa que constava no {cadastro or 'cadastro de sanções'} na data da assinatura",
            detalhe=[f"Fornecedor: {mascarar_cpfs_no_texto(forn.get('nome')) or '—'} (CNPJ {cnpj_forn})",
                     f"Sanção: {s.get('categoria') or '—'}, {vigencia}, aplicada por {s.get('orgao_sancionador') or '—'}",
                     f"Contrato: {_moeda(contrato.get('valor_global'))}, assinado em {_data(contrato.get('data_assinatura'))}"
                     + (f" — {mascarar_cpfs_no_texto(contrato['objeto'], todos=False)}" if contrato.get("objeto") else "")],
            observar=(f"Pela abrangência registrada, {ALCANCE.get(c.get('alcance'), 'confira o alcance da sanção')}. "
                      "Vale conferir se o órgão consultou os cadastros antes de contratar e se a sanção continua "
                      "em vigor; uma decisão judicial pode ter suspendido a sanção depois do registro."),
            fonte={"nome": f"CGU ({cadastro}) e PNCP", "link": contrato.get("link_pncp"),
                   "outra": CADASTROS.get(cadastro)},
            orgao={"cnpj": contrato.get("orgao_cnpj"), "nome": contrato.get("orgao")},
            chave=contrato.get("chave"), valor=contrato.get("valor_global"), uf=contrato.get("uf")))
    return saida


def de_valores_a_conferir(ente: str, lista: Iterable[dict]) -> list[Aviso]:
    """Os avisos dos valores acima do teto de plausibilidade do ente (a lista ``a_conferir`` do arquivo dele)."""
    saida = []
    for x in lista:
        tipo = "contrato" if x.get("tipo") == "contrato" else "processo"
        saida.append(Aviso(
            id=codigo_do_aviso("conferir", x.get("chave")), tipo="valor_a_conferir", data=x.get("data"), ente=ente,
            titulo=f"{'Contrato' if tipo == 'contrato' else 'Processo'} publicado com valor de {_moeda(x.get('valor'))}, "
                   "acima do teto de plausibilidade do ente",
            detalhe=[t for t in [f"Órgão: {x.get('orgao') or '—'}",
                                 f"Fornecedor: {mascarar_cpfs_no_texto(x['fornecedor'])}" if x.get("fornecedor") else None,
                                 f"Objeto: {mascarar_cpfs_no_texto(x['objeto'], todos=False)}" if x.get("objeto") else None] if t],
            observar=("O valor fica fora das somas dos painéis. Confira no documento publicado se é o valor real ou "
                      "erro de digitação (valor total lançado como unitário, casas decimais trocadas); se for real, "
                      "o tamanho dele frente ao orçamento do ente merece atenção."),
            fonte={"nome": "PNCP", "link": x.get("link")}, orgao={"cnpj": None, "nome": x.get("orgao")},
            chave=x.get("chave"), valor=x.get("valor")))
    return saida


def de_conformidade(ente: str, obrigacoes: Iterable[dict]) -> list[Aviso]:
    """Os avisos da LRF de um ente: cada relatório que não consta, e os atrasos somados por exercício."""
    saida, atrasos = [], {}
    for o in obrigacoes:
        if o.get("resultado") == "nao_cumpre":
            saida.append(Aviso(
                id=codigo_do_aviso("lrf", ente, o.get("exercicio"), o.get("criterio"), o.get("periodo"), o.get("poder")),
                tipo="lrf_nao_consta", data=o.get("prazo"), ente=ente,
                titulo=f"{o.get('rotulo')}: não consta no extrato de entregas do Tesouro",
                detalhe=[f"Prazo legal: {_data(o.get('prazo'))} ({o.get('dispositivo') or 'LRF'})"],
                observar=("O prazo venceu e o relatório não aparece no SICONFI. Pode ter sido publicado só no portal do "
                          "ente, ou não ter sido feito; sem ele, o ente fica sujeito às restrições do art. 51, § 2º, e "
                          "do art. 52, § 2º, da LRF (transferências voluntárias e operações de crédito)."),
                fonte={"nome": "SICONFI (extrato de entregas)", "link": "https://siconfi.tesouro.gov.br/siconfi/index.jsf"}))
        elif o.get("resultado") == "cumpre_parcialmente":
            atrasos.setdefault(int(o.get("exercicio") or 0), []).append(o)
    for ano, lista in sorted(atrasos.items()):
        if len(lista) < ATRASOS_MINIMOS:
            continue
        ultimo = max(lista, key=lambda o: o.get("prazo") or "")
        saida.append(Aviso(
            id=codigo_do_aviso("lrf-atrasos", ente, ano), tipo="lrf_atrasos", data=ultimo.get("prazo"), ente=ente,
            titulo=f"{len(lista)} relatórios fiscais de {ano} entregues após o prazo",
            detalhe=[f"{o.get('rotulo')}: prazo {_data(o.get('prazo'))}, entregue em {_data(o.get('entregue_em'))}"
                     for o in sorted(lista, key=lambda o: o.get("prazo") or "")][:12],
            observar=("Entregar depois do prazo é comum e nem sempre tem efeito, mas atrasos repetidos dizem algo da "
                      "gestão fiscal do ente e atrasam o controle social e dos tribunais de contas."),
            fonte={"nome": "SICONFI (extrato de entregas)", "link": "https://siconfi.tesouro.gov.br/siconfi/index.jsf"}))
    return saida


def de_transparencia(publicacao: dict[str, dict]) -> list[Aviso]:
    """Os avisos do PNTP: entidade com nível "Inexistente" ou "Inicial" (os arquivos ``transparencia/*.json``)."""
    saida = []
    for arquivo in publicacao.values():
        ciclo = arquivo.get("ciclo")
        for ente, entidades in (arquivo.get("entes") or {}).items():
            for e in entidades:
                if not e.get("avaliada") or e.get("nivel") not in NIVEIS_BAIXOS:
                    continue
                indice = e.get("indice")
                saida.append(Aviso(
                    id=codigo_do_aviso("pntp", ciclo, e.get("codigo_entidade")), tipo="transparencia_baixa",
                    data=(e.get("data_envio") or f"{ciclo}-12-31")[:10], ente=ente,
                    titulo=f"{e.get('entidade')}: portal de transparência com nível {e.get('nivel')} no PNTP {ciclo}",
                    detalhe=[t for t in [f"Índice: {indice * 100:.1f}% dos critérios avaliados" if isinstance(indice, (int, float)) else None,
                                         f"Nível no ciclo anterior: {e['nivel_anterior']}" if e.get("nivel_anterior") else None,
                                         f"Portal: {e['link']}" if e.get("link") else "Portal: não informado"] if t],
                    observar=("O PNTP confere se o portal publica o que a Lei de Acesso à Informação e a LRF exigem "
                              "(receitas, despesas, contratos, servidores). Nível baixo quer dizer que boa parte disso não "
                              "está no portal, e o que não é publicado não pode ser acompanhado."),
                    fonte={"nome": "PNTP (tribunais de contas e Atricon)", "link": arquivo.get("url")},
                    orgao={"cnpj": None, "nome": e.get("entidade")}))
    return saida


# ------------------------------------------------------------------------------------------ contestações

_CODIGO = re.compile(r"\b([0-9a-f]{12})\b")


def ler_contestacoes(issues: Iterable[dict]) -> dict[str, dict]:
    """Código do aviso → a contestação (issue com o rótulo ``contestacao``): situação, link e data.

    Aberta: "em análise". Fechada com ``removido``: o aviso sai; com ``retificado``: fica com a nota; fechada sem
    esses rótulos: "mantido", com a contestação ao lado (DOC-08, 6.2).
    """
    saida: dict[str, dict] = {}
    for i in issues:
        rotulos = {(r.get("name") if isinstance(r, dict) else str(r)) for r in i.get("labels") or []}
        if "contestacao" not in rotulos:
            continue
        m = _CODIGO.search(f"{i.get('title') or ''} {i.get('body') or ''}")
        if not m:
            continue
        aberta = i.get("state") == "open"
        situacao = ("em_analise" if aberta else "removido" if "removido" in rotulos
                    else "retificado" if "retificado" in rotulos else "mantido")
        saida[m.group(1)] = {"situacao": situacao, "link": i.get("html_url"), "em": (i.get("created_at") or "")[:10]}
    return saida


# ------------------------------------------------------------------------------------------ publicação

@dataclass
class Avisos:
    """Os avisos reunidos na publicação, por ente."""

    lista: list[Aviso] = field(default_factory=list)

    def juntar(self, avisos: Iterable[Aviso]) -> None:
        """Acrescenta avisos (o mesmo código entra uma vez só)."""
        vistos = {a.id for a in self.lista}
        for a in avisos:
            if a.id not in vistos:
                self.lista.append(a)
                vistos.add(a.id)

    def aplicar_contestacoes(self, contestacoes: dict[str, dict]) -> None:
        """Marca os avisos contestados e tira os que a contestação mostrou serem erro do dado de origem."""
        for a in self.lista:
            a.contestacao = contestacoes.get(a.id)
        self.lista = [a for a in self.lista if not (a.contestacao and a.contestacao["situacao"] == "removido")]


def arquivo_do_lugar(lugar: str) -> str:
    """``avisos/uniao.json`` para a União (``"1"``); senão, o arquivo da UF (``avisos/uf-sp.json``)."""
    return "avisos/uniao.json" if lugar == "1" else f"avisos/uf-{lugar.lower()}.json"


def montar(avisos: Avisos, cadastro: Cadastro, *, gerado_em: str) -> dict[str, dict]:
    """Os arquivos: um por UF (e o da União), com os avisos do estado e dos municípios, e o panorama."""
    ordem = sorted(avisos.lista, key=lambda a: (a.data or "", a.id), reverse=True)
    arquivos: dict[str, dict] = {}
    contagem: dict[str, dict[str, int]] = {}
    for a in ordem:
        lugar = a.lugar()
        if lugar is None:
            continue
        arq = arquivos.setdefault(arquivo_do_lugar(lugar), {"versao": 1, "tipo": "avisos", "gerado_em": gerado_em,
                                                            "uf": None if lugar == "1" else lugar, "avisos": []})
        arq["avisos"].append(a.para_json(cadastro))
        contagem.setdefault("União" if lugar == "1" else lugar, {t: 0 for t in TIPOS})[a.tipo] += 1
    por_tipo = {t: sum(c[t] for c in contagem.values()) for t in TIPOS}
    arquivos["avisos/panorama.json"] = {
        "versao": 1, "tipo": "avisos-panorama", "gerado_em": gerado_em, "tipos": TIPOS, "total": len(ordem),
        "por_tipo": por_tipo, "por_lugar": [{"lugar": k, **v} for k, v in sorted(contagem.items())],
        "contestados": sum(1 for a in ordem if a.contestacao),
        "ultimos": [a.para_json(cadastro) for a in ordem[:ULTIMOS_PANORAMA]],
    }
    return arquivos


def publicar(estado: Path | str, avisos: Avisos, cadastro: Cadastro, gravar: Callable[[str, dict], None], *,
             gerado_em: str) -> dict:
    """Lê a J-01 e as contestações do estado, junta aos avisos já reunidos, grava e devolve o resumo."""
    estado = Path(estado)
    caminho = estado / ARQUIVO_CONTESTACOES
    if caminho.exists() and caminho.stat().st_size:
        dados = ler_json(caminho)
        avisos.aplicar_contestacoes(ler_contestacoes(dados if isinstance(dados, list) else []))
    arquivos = montar(avisos, cadastro, gerado_em=gerado_em)
    for nome, conteudo in sorted(arquivos.items()):
        gravar(nome, conteudo)
    return {"total": arquivos["avisos/panorama.json"]["total"], "por_tipo": arquivos["avisos/panorama.json"]["por_tipo"],
            "contestados": arquivos["avisos/panorama.json"]["contestados"], "arquivos": len(arquivos)}


def ler_j01(estado: Path | str) -> dict:
    """O relatório da J-01 guardado no estado (``deteccao-j01.json.gz``), ou vazio."""
    caminho = Path(estado) / ARQUIVO_J01
    return ler_json(caminho) if caminho.exists() and caminho.stat().st_size else {}
