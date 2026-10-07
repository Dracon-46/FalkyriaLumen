#!/usr/bin/env python3
"""Extrai a referência técnica do código e confere que nada ficou sem documentação.

A referência técnica do Lumen (DOC-11) é gerada a partir do próprio código:
o texto de cada arquivo, classe, função e método é a docstring (Python) ou o
comentário JSDoc (TypeScript) que está ao lado dele. Assim a documentação não
envelhece separada do código — muda no mesmo commit.

Para isso funcionar, nada pode ficar sem texto. ``--verificar`` lista o que
falta e sai com erro; o teste ``test_referencia.py`` roda a mesma conferência
na suíte, então a CI recusa função nova sem documentação.

O que conta como item:

- Python: o módulo, cada classe, cada função de módulo e cada método de
  classe. Funções definidas dentro de outras funções (auxiliares locais) são
  parte da que as contém e ficam de fora.
- TypeScript: cada função, componente, classe, interface e tipo declarados no
  nível do arquivo, exportados ou não, e cada constante exportada.

Uso::

    python ferramentas/referencia/referencia.py --verificar
    python ferramentas/referencia/referencia.py --json docs-src/referencia.json
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]

ALVOS_PYTHON = ["packages/*/lumen_*/**/*.py", "ferramentas/*/*.py"]
ALVOS_TS = ["packages/portal/src/**/*.ts", "packages/portal/src/**/*.tsx"]
IGNORADOS = ("__testes__", "/testes/", "__pycache__", "node_modules", ".test.ts")


@dataclass
class Item:
    """Uma declaração documentável: o tipo, o nome, a assinatura como está no código e o texto dela."""

    tipo: str            # modulo, classe, funcao, metodo, interface, tipo, constante, componente
    nome: str
    assinatura: str
    doc: str
    linha: int


@dataclass
class Arquivo:
    """Um arquivo de código com o texto de abertura e as declarações que ele contém."""

    caminho: str
    linguagem: str
    linhas: int
    doc: str
    itens: list[Item] = field(default_factory=list)

    def sem_documentacao(self) -> list[str]:
        """Linhas ``arquivo:linha: tipo nome`` de tudo que está sem texto, inclusive o próprio arquivo."""
        faltando = [] if self.doc.strip() else [f"{self.caminho}: módulo"]
        faltando += [f"{self.caminho}:{i.linha}: {i.tipo} {i.nome}" for i in self.itens if not i.doc.strip()]
        return faltando


# ---------------------------------------------------------------- Python

def _assinatura(no: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Assinatura da função reconstruída da árvore sintática (``def nome(args) -> retorno``)."""
    args = ast.unparse(no.args)
    retorno = f" -> {ast.unparse(no.returns)}" if no.returns else ""
    prefixo = "async def" if isinstance(no, ast.AsyncFunctionDef) else "def"
    return f"{prefixo} {no.name}({args}){retorno}"


def _bases(no: ast.ClassDef) -> str:
    """``class Nome(Base1, Base2)`` reconstruído da árvore sintática."""
    bases = ", ".join(ast.unparse(b) for b in no.bases)
    return f"class {no.name}({bases})" if bases else f"class {no.name}"


def ler_python(caminho: Path) -> Arquivo:
    """Lê um módulo Python pela árvore sintática (sem importar nem executar nada).

    Entram o módulo, as funções e classes do nível do módulo e os métodos das
    classes. ``__main__.py`` sem docstring recebe um texto padrão: o papel dele
    é sempre o mesmo.
    """
    texto = caminho.read_text(encoding="utf-8")
    arvore = ast.parse(texto)
    arq = Arquivo(caminho=caminho.relative_to(RAIZ).as_posix(), linguagem="python",
                  linhas=texto.count("\n") + 1, doc=ast.get_docstring(arvore) or "")
    if caminho.name == "__main__.py" and not arq.doc:
        arq.doc = "Ponto de entrada de `python -m`: repassa para o `main` do CLI do pacote."
    for no in arvore.body:
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
            arq.itens.append(Item("funcao", no.name, _assinatura(no), ast.get_docstring(no) or "", no.lineno))
        elif isinstance(no, ast.ClassDef):
            arq.itens.append(Item("classe", no.name, _bases(no), ast.get_docstring(no) or "", no.lineno))
            for filho in no.body:
                if isinstance(filho, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    arq.itens.append(Item("metodo", f"{no.name}.{filho.name}", _assinatura(filho),
                                          ast.get_docstring(filho) or "", filho.lineno))
    return arq


# ---------------------------------------------------------------- TypeScript

_DECL = re.compile(
    r"^(?P<export>export\s+(?:default\s+)?)?(?P<async>async\s+)?"
    r"(?:(?P<fn>function)\s+(?P<fnome>\w+)\s*(?P<fsig>(?:<[^>]*>)?\([^)]*\)?)"
    r"|(?P<cls>class)\s+(?P<cnome>\w+)"
    r"|(?P<iface>interface)\s+(?P<inome>\w+)"
    r"|(?P<tipo>type)\s+(?P<tnome>\w+)\s*="
    r"|(?P<const>const)\s+(?P<knome>\w+)\b)"
)


def _jsdoc_antes(linhas: list[str], indice: int) -> str:
    """Texto do bloco ``/** ... */`` imediatamente acima da linha (comentários de linha não contam)."""
    j = indice - 1
    while j >= 0 and not linhas[j].strip():
        j -= 1
    if j < 0 or not linhas[j].strip().endswith("*/"):
        return ""
    fim = j
    while j >= 0 and "/**" not in linhas[j]:
        j -= 1
    if j < 0:
        return ""
    bloco = "\n".join(linhas[j:fim + 1])
    bloco = re.sub(r"^\s*/\*\*\s?|\s*\*/\s*$", "", bloco)
    return "\n".join(re.sub(r"^\s*\*\s?", "", ln) for ln in bloco.splitlines()).strip()


def _doc_de_arquivo_ts(linhas: list[str]) -> str:
    """Bloco ``/** */`` do topo do arquivo (depois de um eventual ``"use client"``)."""
    i = 0
    while i < len(linhas) and (not linhas[i].strip() or linhas[i].strip().startswith(('"use client"', "'use client'"))):
        i += 1
    if i < len(linhas) and linhas[i].strip().startswith("/**"):
        j = i
        while j < len(linhas) and "*/" not in linhas[j]:
            j += 1
        return _jsdoc_antes(linhas, j + 1)
    return ""


def ler_typescript(caminho: Path) -> Arquivo:
    """Lê um arquivo TypeScript por expressão regular, só as declarações do nível do arquivo.

    Não é um analisador de TypeScript: reconhece ``function``, ``class``,
    ``interface``, ``type`` e ``export const`` no começo da linha, que é como o
    portal declara tudo. A página padrão de cada rota do Next herda o texto do
    arquivo quando não tem bloco próprio.
    """
    texto = caminho.read_text(encoding="utf-8")
    linhas = texto.splitlines()
    arq = Arquivo(caminho=caminho.relative_to(RAIZ).as_posix(), linguagem="typescript",
                  linhas=len(linhas), doc=_doc_de_arquivo_ts(linhas))
    for i, linha in enumerate(linhas):
        if linha.startswith((" ", "\t")):
            continue
        m = _DECL.match(linha)
        if not m:
            continue
        exportado = bool(m.group("export"))
        if m.group("fn"):
            nome = m.group("fnome")
            tipo = "componente" if caminho.suffix == ".tsx" and nome[:1].isupper() else "funcao"
        elif m.group("cls"):
            nome, tipo = m.group("cnome"), "classe"
        elif m.group("iface"):
            nome, tipo = m.group("inome"), "interface"
        elif m.group("tipo"):
            nome, tipo = m.group("tnome"), "tipo"
        else:
            if not exportado:
                continue
            nome, tipo = m.group("knome"), "constante"
        if caminho.parent.name == "app" or "/app/" in arq.caminho:
            # Páginas do Next: o componente padrão é a página; o texto do arquivo a descreve.
            if m.group("export") and "default" in m.group("export") and not _jsdoc_antes(linhas, i):
                doc = arq.doc or f"Página `{arq.caminho}`."
                arq.itens.append(Item(tipo, nome, linha.strip().rstrip("{").strip(), doc, i + 1))
                continue
        arq.itens.append(Item(tipo, nome, linha.strip().rstrip("{").strip(), _jsdoc_antes(linhas, i), i + 1))
    return arq


# ---------------------------------------------------------------- coleta

def coletar(raiz: Path = RAIZ, filtros: list[str] | None = None) -> list[Arquivo]:
    """Todos os arquivos dos alvos, fora testes e gerados; ``filtros`` restringe por prefixo de caminho."""
    arquivos: list[Arquivo] = []
    vistos: set[Path] = set()
    for padrao, leitor in [(p, ler_python) for p in ALVOS_PYTHON] + [(p, ler_typescript) for p in ALVOS_TS]:
        for caminho in sorted(raiz.glob(padrao)):
            rel = caminho.relative_to(raiz).as_posix()
            if caminho in vistos or any(x in f"/{rel}" for x in IGNORADOS):
                continue
            if filtros and not any(rel.startswith(f) for f in filtros):
                continue
            vistos.add(caminho)
            arquivos.append(leitor(caminho))
    return arquivos


@dataclass
class ArquivoTeste:
    """Um arquivo de testes: o texto de abertura e quantos testes ele contém."""

    caminho: str
    doc: str
    testes: int


def coletar_testes(raiz: Path = RAIZ) -> list[ArquivoTeste]:
    """Arquivos de teste (Python e TypeScript) com o texto de abertura e a contagem de testes.

    Entra no DOC-11 como o mapa do que cada suíte garante. A contagem é
    estática: funções ``test_*`` em Python; chamadas ``it(`` em TypeScript
    (os testes gerados em laço contam uma vez).
    """
    saida = []
    for caminho in sorted([*raiz.glob("packages/*/testes/test_*.py"), *raiz.glob("ferramentas/*/testes/test_*.py"),
                           *raiz.glob("testes/*/test_*.py")]):
        arvore = ast.parse(caminho.read_text(encoding="utf-8"))
        n = sum(1 for no in arvore.body if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef))
                and no.name.startswith("test_"))
        saida.append(ArquivoTeste(caminho.relative_to(raiz).as_posix(), ast.get_docstring(arvore) or "", n))
    for caminho in sorted(raiz.glob("packages/portal/src/**/*.test.ts")):
        texto = caminho.read_text(encoding="utf-8")
        doc = re.search(r"/\*\*(.*?)\*/", texto, re.S)
        saida.append(ArquivoTeste(caminho.relative_to(raiz).as_posix(),
                                  "\n".join(re.sub(r"^\s*\*\s?", "", ln) for ln in doc.group(1).splitlines()).strip()
                                  if doc else "", len(re.findall(r"^\s*it\(", texto, re.M))))
    return saida


def main(argv: list[str] | None = None) -> int:
    """Linha de comando: ``--verificar`` sai com 1 se houver item sem texto; ``--json`` exporta a referência."""
    parser = argparse.ArgumentParser(description="Referência técnica extraída do código (DOC-11)")
    parser.add_argument("--verificar", action="store_true", help="lista o que está sem documentação")
    parser.add_argument("--json", type=Path, help="grava a referência em JSON (entrada do build do DOC-11)")
    parser.add_argument("prefixos", nargs="*", help="restringe a caminhos que começam com estes prefixos")
    args = parser.parse_args(argv)
    arquivos = coletar(filtros=args.prefixos or None)
    if args.json:
        dados = {"arquivos": [asdict(a) for a in arquivos],
                 "testes": [asdict(t) for t in coletar_testes()] if not args.prefixos else []}
        args.json.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{len(arquivos)} arquivos, {sum(len(a.itens) for a in arquivos)} itens → {args.json}")
    if args.verificar or not args.json:
        faltando = [f for a in arquivos for f in a.sem_documentacao()]
        for f in faltando:
            print(f)
        total = sum(len(a.itens) + 1 for a in arquivos)
        print(f"{total} itens em {len(arquivos)} arquivos; {len(faltando)} sem documentação.")
        return 1 if faltando else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
