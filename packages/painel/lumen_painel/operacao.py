"""Painel operacional (RF-AD-05; DOC-04, seção 8; ADR-039): saúde das coletas, atrasos, falhas e volume.

Um arquivo só, ``operacao.json``, publicado com os painéis, em três partes:

- **Fluxos**: as execuções dos fluxos de dados no GitHub Actions nos últimos ``JANELA_DIAS`` dias. O
  ``paineis-site`` as grava com ``gh run list`` em ``execucoes.json``, no estado, antes de publicar. Para
  cada fluxo: quantas execuções, quantas falharam, a última, a última com sucesso e, nos fluxos diários, se
  essa ficou velha demais (``TOLERANCIA_HORAS`` além da cadência, porque o GitHub atrasa os agendamentos).
- **Volume das contratações**: processos publicados no PNCP por dia, contra a mediana do mesmo dia da semana
  nas ``SEMANAS_BASE`` semanas anteriores. Dia útil abaixo de ``FRACAO_MINIMA`` dessa mediana é alerta. É o
  alarme mais importante do DOC-04: a fonte que responde com sucesso e quase nada. Fim de semana, feriado,
  ponto facultativo e ponte nacionais ficam de fora; dia não coletado também é alerta.
- **Conformidade**: há quanto tempo o extrato de cada UF foi coletado e quantos entes ficaram com a coleta
  malsucedida.

Os limiares são iniciais, não calibrados, e vão no próprio arquivo. Os alertas falam do Lumen e das fontes,
nunca de um ente.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from statistics import median
from typing import Iterable

JANELA_DIAS = 30
TOLERANCIA_HORAS = 12
SEMANAS_BASE = 8
MINIMO_SEMANAS = 4
FRACAO_MINIMA = 0.5
DIAS_SERIE = 60
HORAS_CONFORMIDADE = 24 + TOLERANCIA_HORAS

# Nome do fluxo (o ``name:`` do arquivo em .github/workflows) → (descrição, cadência em horas; None = sob demanda)
FLUXOS: dict[str, tuple[str, int | None]] = {
    "eleicoes-carga": ("Carga das eleições", 24),
    "paineis": ("Painéis: contratações, conformidade, economia e preços", 24),
    "deteccao-sancoes": ("Regra J-01, em modo silencioso", 24),
    "contrato-de-fontes": ("Testes de contrato das fontes", 24),
    "cnpj": ("Base de CNPJ da Receita, dos fornecedores", 168),
    "tce": ("Contratos nos tribunais de contas (TCE-RS, pelo intermediário em São Paulo, TCE-PR e TCE-PE)", 24),
    "eleicoes-ao-vivo": ("Apuração ao vivo", None),
    "paineis-carga": ("Carga das contratações por período", None),
    "mercado-referencia": ("Referência de mercado (A-05), em modo silencioso", None),
}
FALHAS = {"failure", "timed_out", "startup_failure"}


def _instante(texto: str | None) -> datetime | None:
    """ISO 8601 com ``Z`` ou fuso → ``datetime`` com fuso; ausente ou vazio → None."""
    if not texto:
        return None
    return datetime.fromisoformat(texto.replace("Z", "+00:00"))


def _iso(instante: datetime | None) -> str | None:
    """``datetime`` → ISO 8601 em UTC, sem frações; None → None."""
    return instante.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if instante else None


def _horas(desde: datetime | None, agora: datetime) -> float | None:
    """Horas entre ``desde`` e ``agora``, com uma casa; None sem ``desde``."""
    return round((agora - desde).total_seconds() / 3600, 1) if desde else None


# ------------------------------------------------------------------------------------------- fluxos

def resumir_fluxo(nome: str, execucoes: Iterable[dict], agora: datetime) -> dict:
    """Uma linha do quadro dos fluxos, a partir das execuções do ``gh run list`` (todas do mesmo fluxo).

    Falha é ``failure``, ``timed_out`` ou ``startup_failure``; cancelada e pulada não contam como falha nem
    entram na taxa. Atrasado: fluxo com cadência cuja última execução com sucesso passou da cadência mais a
    tolerância, ou que não tem nenhuma.
    """
    descricao, cadencia = FLUXOS[nome]
    inicio = agora - timedelta(days=JANELA_DIAS)
    todas = sorted(execucoes, key=lambda e: e["createdAt"])
    janela = [e for e in todas if _instante(e["createdAt"]) >= inicio]
    falhas = [e for e in janela if e.get("conclusion") in FALHAS]
    decididas = falhas + [e for e in janela if e.get("conclusion") == "success"]
    sucessos = [e for e in todas if e.get("conclusion") == "success"]
    ultimo_sucesso = _instante(sucessos[-1].get("updatedAt") or sucessos[-1]["createdAt"]) if sucessos else None
    horas = _horas(ultimo_sucesso, agora)
    ultima = janela[-1] if janela else None
    return {
        "fluxo": nome, "descricao": descricao, "cadencia_horas": cadencia,
        "execucoes": len(janela), "falhas": len(falhas),
        "canceladas": sum(1 for e in janela if e.get("conclusion") == "cancelled"),
        "taxa_falha": round(len(falhas) / len(decididas), 4) if decididas else None,
        "ultima": {"inicio": ultima["createdAt"], "situacao": ultima.get("status"),
                   "resultado": ultima.get("conclusion") or None, "evento": ultima.get("event"),
                   "url": ultima.get("url")} if ultima else None,
        "ultimo_sucesso": _iso(ultimo_sucesso), "horas_desde_sucesso": horas,
        "atrasado": cadencia is not None and (horas is None or horas > cadencia + TOLERANCIA_HORAS),
    }


def resumir_fluxos(execucoes: Iterable[dict], agora: datetime) -> list[dict]:
    """Uma linha por fluxo acompanhado (``FLUXOS``), na ordem de ``FLUXOS``; os outros fluxos ficam de fora."""
    por_fluxo: dict[str, list[dict]] = {nome: [] for nome in FLUXOS}
    for e in execucoes:
        if e.get("workflowName") in por_fluxo:
            por_fluxo[e["workflowName"]].append(e)
    return [resumir_fluxo(nome, lista, agora) for nome, lista in por_fluxo.items()]


# ------------------------------------------------------------------------------------------- volume

def pascoa(ano: int) -> date:
    """Domingo de Páscoa no calendário gregoriano (algoritmo de Meeus/Jones/Butcher)."""
    a, b, c = ano % 19, ano // 100, ano % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    m = (32 + 2 * e + 2 * i - h - k) % 7
    n = (a + 11 * h + 22 * m) // 451
    mes = (h + m - 7 * n + 114) // 31
    dia = (h + m - 7 * n + 114) % 31 + 1
    return date(ano, mes, dia)


def _feriado(dia: date) -> bool:
    """Feriado nacional ou ponto facultativo nacional de dia inteiro: os do calendário civil (Lei 662/1949, Lei
    6.802/1980 e Lei 14.759/2023), Carnaval, Sexta-feira Santa e Corpus Christi."""
    if (dia.month, dia.day) in {(1, 1), (4, 21), (5, 1), (9, 7), (10, 12), (11, 2), (11, 15), (11, 20), (12, 25)}:
        return True
    p = pascoa(dia.year)
    return dia in {p - timedelta(days=48), p - timedelta(days=47), p - timedelta(days=2), p + timedelta(days=60)}


def sem_expediente_nacional(dia: date) -> bool:
    """Dia em que o volume do PNCP cai sem que a fonte tenha problema: feriado ou ponto facultativo nacional,
    Quarta-feira de Cinzas e Quinta-feira Santa (expediente reduzido) e a ponte, a segunda-feira antes de um
    feriado na terça ou a sexta-feira depois de um na quinta. No PNCP de 2026, foram esses os dias úteis com
    menos da metade do volume usual (ADR-039)."""
    if _feriado(dia):
        return True
    p = pascoa(dia.year)
    if dia in {p - timedelta(days=46), p - timedelta(days=3)}:
        return True
    return ((dia.weekday() == 0 and _feriado(dia + timedelta(days=1)))
            or (dia.weekday() == 4 and _feriado(dia - timedelta(days=1))))


def volume_contratacoes(volume: dict[str, dict[str, int]], hoje: date) -> dict:
    """Os ``DIAS_SERIE`` dias até ontem, com processos e contratos, a referência do dia e o alerta.

    A referência é a mediana dos processos no mesmo dia da semana nas ``SEMANAS_BASE`` semanas anteriores
    (dias úteis coletados; ao menos ``MINIMO_SEMANAS``). Dia não coletado aparece com ``coletado: false``.
    """
    dias = []
    for n in range(DIAS_SERIE, 0, -1):
        dia = hoje - timedelta(days=n)
        chave = dia.isoformat()
        registro = volume.get(chave)
        util = dia.weekday() < 5 and not sem_expediente_nacional(dia)
        anteriores = [volume[c]["processos"] for k in range(1, SEMANAS_BASE + 1)
                      if (c := (dia - timedelta(weeks=k)).isoformat()) in volume
                      and not sem_expediente_nacional(dia - timedelta(weeks=k))]
        referencia = median(anteriores) if util and len(anteriores) >= MINIMO_SEMANAS else None
        alerta = None
        if registro is None:
            alerta = "dia não coletado"
        elif referencia and registro["processos"] < FRACAO_MINIMA * referencia:
            alerta = "volume abaixo do esperado"
        dias.append({"dia": chave, "coletado": registro is not None, "util": util,
                     "processos": registro["processos"] if registro else None,
                     "contratos": registro["contratos"] if registro else None,
                     "referencia": referencia, "alerta": alerta})
    return {"dias": dias}


# ------------------------------------------------------------------------------------- conformidade

def coleta_conformidade(coletas: dict[str, str | None], entes: dict[str, dict], agora: datetime,
                        uf_do_ente) -> list[dict]:
    """Por UF: quando o extrato foi coletado, há quantas horas, quantos entes e quantos com coleta malsucedida."""
    por_uf: dict[str, list[dict]] = {}
    for codigo, arquivo in entes.items():
        uf = uf_do_ente(codigo)
        if uf:
            por_uf.setdefault(uf, []).append(arquivo)
    linhas = []
    for uf in sorted(set(coletas) | set(por_uf)):
        coletado = _instante(coletas.get(uf))
        horas = _horas(coletado, agora)
        lista = por_uf.get(uf, [])
        linhas.append({"uf": uf, "coletado_em": coletas.get(uf), "horas_desde_coleta": horas,
                       "entes": len(lista),
                       "coleta_malsucedida": sum(1 for a in lista if not all((a.get("coleta") or {}).values())),
                       "atrasada": horas is None or horas > HORAS_CONFORMIDADE})
    return linhas


# ----------------------------------------------------------------------------------------- arquivo

def _tempo(horas: float) -> str:
    """Horas em palavras para o alerta: "30 h" até dois dias, depois "4 dias"."""
    return f"{round(horas)} h" if horas < 48 else f"{int(horas // 24)} dias"


def _data(iso: str) -> str:
    """``2026-10-18`` → ``18/10/2026``."""
    return date.fromisoformat(iso).strftime("%d/%m/%Y")


def _lista(itens: list[str], maximo: int = 5) -> str:
    """Até ``maximo`` itens separados por vírgula, com reticências se houver mais."""
    return ", ".join(itens[:maximo]) + ("…" if len(itens) > maximo else "")


def alertas(fluxos: list[dict], volume: dict, conformidade: list[dict]) -> list[dict]:
    """O que merece atenção, numa lista só, do mais grave ao menos: falha e atraso de fluxo, volume, coleta.

    A conformidade atrasada vira um alerta só, com as UFs: quando a coleta não roda, atrasam todas juntas.
    """
    saida = []
    for f in fluxos:
        if f["ultima"] and f["ultima"]["resultado"] in FALHAS:
            saida.append({"tipo": "fluxo", "texto": f"{f['descricao']}: a última execução falhou",
                          "url": f["ultima"]["url"]})
        if f["atrasado"]:
            texto = (f"{f['descricao']}: nenhuma execução com sucesso" if f["horas_desde_sucesso"] is None else
                     f"{f['descricao']}: última execução com sucesso há {_tempo(f['horas_desde_sucesso'])}")
            saida.append({"tipo": "fluxo", "texto": texto, "url": None})
    for d in volume["dias"][-JANELA_DIAS:]:
        if d["alerta"] == "volume abaixo do esperado":
            saida.append({"tipo": "volume", "url": None,
                          "texto": f"PNCP em {_data(d['dia'])}: {d['processos']} processos, contra {d['referencia']:g} "
                                   f"no mesmo dia da semana (mediana de {SEMANAS_BASE} semanas)"})
        elif d["alerta"] == "dia não coletado":
            saida.append({"tipo": "volume", "texto": f"PNCP em {_data(d['dia'])}: dia não coletado", "url": None})
    antigos = [d for d in volume.get("faltando", []) if d < volume["dias"][-JANELA_DIAS]["dia"]] if volume["dias"] else []
    if antigos:
        saida.append({"tipo": "volume", "url": None,
                      "texto": f"PNCP: {len(antigos)} dia(s) sem coleta antes dos últimos {JANELA_DIAS} dias "
                               f"({_lista([_data(d) for d in antigos])})"})
    atrasadas = [c for c in conformidade if c["atrasada"]]
    if atrasadas:
        horas = [c["horas_desde_coleta"] for c in atrasadas if c["horas_desde_coleta"] is not None]
        quais = "todas as UFs" if len(atrasadas) == len(conformidade) else _lista([c["uf"] for c in atrasadas], 9)
        texto = f"Conformidade: extrato de {quais} coletado há mais de {HORAS_CONFORMIDADE} h"
        if horas:
            texto += f" (o mais antigo, há {_tempo(max(horas))})"
        if len(horas) < len(atrasadas):
            texto += f"; {len(atrasadas) - len(horas)} UF(s) nunca coletada(s)"
        saida.append({"tipo": "conformidade", "texto": texto, "url": None})
    return saida


def operacao_para_json(*, execucoes: list[dict] | None, volume: dict[str, dict[str, int]],
                       faltando: list[str], coletas: dict[str, str | None], entes: dict[str, dict], uf_do_ente,
                       agora: datetime, hoje: date, gerado_em: str) -> dict:
    """``operacao.json``: ``agora`` mede os atrasos, ``hoje`` (Brasília) fecha a série de volume, ``faltando``
    são os dias do PNCP sem coleta desde o primeiro guardado. Sem ``execucoes`` (rodando fora do GitHub
    Actions), os fluxos ficam como None."""
    fluxos = resumir_fluxos(execucoes, agora) if execucoes is not None else None
    serie = {**volume_contratacoes(volume, hoje), "faltando": list(faltando)}
    conformidade = coleta_conformidade(coletas, entes, agora, uf_do_ente)
    return {
        "versao": 1, "tipo": "operacao", "gerado_em": gerado_em,
        "parametros": {"janela_dias": JANELA_DIAS, "tolerancia_horas": TOLERANCIA_HORAS,
                       "semanas_base": SEMANAS_BASE, "fracao_minima": FRACAO_MINIMA,
                       "horas_conformidade": HORAS_CONFORMIDADE, "calibrados": False},
        "alertas": alertas(fluxos or [], serie, conformidade),
        "fluxos": fluxos, "contratacoes": serie, "conformidade": conformidade,
    }
