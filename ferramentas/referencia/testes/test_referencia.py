"""A referência técnica (DOC-11) sai do código: nada pode ficar sem documentação."""

from __future__ import annotations

import json
from pathlib import Path

import referencia as r


def test_todo_o_codigo_esta_documentado():
    """Função, classe, método ou componente novo sem texto quebra a suíte (e a CI)."""
    faltando = [f for a in r.coletar() for f in a.sem_documentacao()]
    assert not faltando, "sem documentação:\n" + "\n".join(faltando)


def test_cobre_os_pacotes_e_o_portal():
    caminhos = {a.caminho for a in r.coletar()}
    assert "packages/eleicoes/lumen_eleicoes/coletor.py" in caminhos
    assert "packages/portal/src/lib/topojson.ts" in caminhos
    assert "ferramentas/lint-vocabulario/lint_vocabulario.py" in caminhos
    assert not any("/testes/" in c or "__testes__" in c for c in caminhos)


def test_le_python_sem_executar(tmp_path, monkeypatch):
    monkeypatch.setattr(r, "RAIZ", tmp_path)
    arq = tmp_path / "m.py"
    arq.write_text('"""Módulo."""\n\nclass A(B):\n    """Classe."""\n\n    def f(self, x: int = 1) -> str:\n'
                   '        pass\n\n\ndef g():\n    def interna():\n        pass\n\n\nasync def h(*a):\n'
                   '    """H."""\n', encoding="utf-8")
    a = r.ler_python(arq)
    assert a.doc == "Módulo."
    assert [(i.tipo, i.nome) for i in a.itens] == [("classe", "A"), ("metodo", "A.f"), ("funcao", "g"),
                                                   ("funcao", "h")]
    assert a.itens[0].assinatura == "class A(B)"
    assert a.itens[1].assinatura == "def f(self, x: int=1) -> str"
    assert a.itens[3].assinatura.startswith("async def h")
    assert a.sem_documentacao() == ["m.py:6: metodo A.f", "m.py:10: funcao g"]


def test_le_typescript(tmp_path, monkeypatch):
    monkeypatch.setattr(r, "RAIZ", tmp_path)
    (tmp_path / "x").mkdir()
    arq = tmp_path / "x" / "c.tsx"
    arq.write_text('"use client";\n\n/** Arquivo. */\n\nimport x from "y";\n\n/** Faz. */\nexport function Comp() {\n'
                   '  function interna() {}\n}\n\nexport const A = 1;\nconst b = 2;\n\n/**\n * Tipo.\n */\n'
                   'export interface I {\n  a: string;\n}\n\ntype T = string;\n\n// comentário de linha não conta\n'
                   'export async function f(a: number) {\n}\n', encoding="utf-8")
    a = r.ler_typescript(arq)
    assert a.doc == "Arquivo."
    assert [(i.tipo, i.nome, bool(i.doc)) for i in a.itens] == [
        ("componente", "Comp", True), ("constante", "A", False), ("interface", "I", True),
        ("tipo", "T", False), ("funcao", "f", False)]
    assert a.itens[2].doc == "Tipo."


def test_cli_exporta_json(tmp_path, capsys):
    destino = tmp_path / "ref.json"
    assert r.main(["--json", str(destino), "ferramentas/referencia"]) == 0
    dados = json.loads(destino.read_text(encoding="utf-8"))
    assert dados["arquivos"][0]["caminho"] == "ferramentas/referencia/referencia.py"
    assert r.main(["--verificar", "ferramentas/referencia"]) == 0
    assert "0 sem documentação" in capsys.readouterr().out
    assert Path(r.RAIZ / "pyproject.toml").exists()


def test_lista_os_testes_com_contagem():
    testes = {t.caminho: t for t in r.coletar_testes()}
    proprio = testes["ferramentas/referencia/testes/test_referencia.py"]
    assert proprio.testes >= 6 and proprio.doc.startswith("A referência técnica")
    portal = [t for t in testes.values() if t.caminho.endswith(".test.ts")]
    assert portal and all(t.testes > 0 for t in portal)
