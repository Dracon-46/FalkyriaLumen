#!/usr/bin/env python3
"""Verificador de vocabulário controlado do Projeto Lumen.

Implementa a restrição do DOC-08, seção 3: nenhum texto destinado ao público
pode conter termo que impute conduta ilícita. O Lumen publica indícios, nunca
conclusões — e essa regra é imposta por ferramenta, não por disciplina, porque
basta um rótulo ou uma mensagem de erro escaparem para o projeto afirmar em
público algo que não tem competência para afirmar.

Roda na integração contínua e interrompe o build quando encontra violação.

Uso:
    python lint_vocabulario.py                 # varre os alvos configurados
    python lint_vocabulario.py arquivo.md ...  # varre arquivos específicos
    python lint_vocabulario.py --listar        # mostra a lista vigente
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

CONFIG_PADRAO = Path(__file__).with_name("vocabulario.json")


def normalizar(texto: str) -> str:
    """Remove acentos e caixa.

    Sem isso a verificação seria trivial de burlar: bastaria escrever
    'corrupção' com acento para escapar de uma lista que guarda 'corrupcao'.
    A comparação acontece sempre neste espaço normalizado.
    """
    decomposto = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in decomposto if not unicodedata.combining(c))
    return sem_acento.lower()


@dataclass(frozen=True)
class Violacao:
    caminho: Path
    linha: int
    coluna: int
    termo: str
    sugestao: str
    trecho: str

    def __str__(self) -> str:
        return (
            f"{self.caminho}:{self.linha}:{self.coluna}: termo proibido {self.termo!r}\n"
            f"    {self.trecho.strip()}\n"
            f"    use: {self.sugestao}"
        )


class Vocabulario:
    def __init__(self, config: dict):
        self.proibidos: dict[str, str] = {
            normalizar(termo): sugestao
            for termo, sugestao in config.get("proibidos", {}).items()
        }
        # Ordena da expressão mais longa para a mais curta: mascarar
        # "desvio absoluto mediano" antes de "desvio padrao" evita que um
        # prefixo comum consuma parte da expressão maior.
        self.permitidos: list[str] = sorted(
            (normalizar(p) for p in config.get("permitidos", [])),
            key=len,
            reverse=True,
        )
        # Entre as palavras de uma expressão permitida aceita-se qualquer
        # espaço em branco, inclusive quebra de linha. Texto com quebra manual
        # (markdown, docstring) parte "esquema canonico" em duas linhas o tempo
        # todo; verificar linha a linha acusaria o "esquema" órfão no fim de
        # uma delas.
        self._regex_permitidos = [
            re.compile(r"\b" + r"\s+".join(re.escape(p) for p in expr.split()) + r"\b")
            for expr in self.permitidos
        ]
        self.alvos: list[str] = config.get("alvos", [])
        self.isentos: list[str] = config.get("isentos", [])
        self.marcador: str = config.get("marcador_excecao", "lumen:vocabulario-ok")

        if self.proibidos:
            alternativas = "|".join(re.escape(t) for t in sorted(self.proibidos, key=len, reverse=True))
            # \b nas duas pontas: 'desvio' não casa dentro de 'desvio_padrao'
            # (o underscore é caractere de palavra), mas casa em 'desvio de verba'.
            self._regex = re.compile(rf"\b({alternativas})\b")
        else:
            self._regex = None

    @classmethod
    def carregar(cls, caminho: Path = CONFIG_PADRAO) -> "Vocabulario":
        with open(caminho, encoding="utf-8") as fh:
            return cls(json.load(fh))

    def _mascarar_permitidos(self, texto_normalizado: str) -> str:
        """Substitui expressões técnicas legítimas por espaços.

        'desvio padrao' é o nome de uma medida estatística e aparece o tempo
        todo no motor de detecção. A máscara troca cada caractere por espaço,
        mas preserva as quebras de linha: assim os números de linha e as
        colunas das demais palavras continuam exatos.
        """
        resultado = texto_normalizado
        for padrao in self._regex_permitidos:
            resultado = padrao.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), resultado)
        return resultado

    def verificar_texto(self, texto: str, caminho: Path = Path("<texto>")) -> list[Violacao]:
        if self._regex is None:
            return []
        originais = texto.splitlines()
        # O texto inteiro é normalizado e mascarado de uma vez, para que uma
        # expressão permitida partida entre linhas seja reconhecida.
        mascaradas = self._mascarar_permitidos(normalizar(texto)).splitlines()
        achados: list[Violacao] = []
        for numero, (original, mascarada) in enumerate(zip(originais, mascaradas), start=1):
            if self.marcador in original:
                continue
            achados.extend(
                Violacao(
                    caminho=caminho,
                    linha=numero,
                    coluna=m.start() + 1,
                    termo=m.group(1),
                    sugestao=self.proibidos[m.group(1)],
                    trecho=original,
                )
                for m in self._regex.finditer(mascarada)
            )
        return achados

    def verificar_linha(self, linha: str, numero: int, caminho: Path) -> list[Violacao]:
        """Verifica uma linha isolada, reportando-a com o número informado."""
        return [
            Violacao(v.caminho, numero, v.coluna, v.termo, v.sugestao, v.trecho)
            for v in self.verificar_texto(linha, caminho)
        ]

    def verificar_arquivo(self, caminho: Path) -> list[Violacao]:
        try:
            texto = caminho.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            return []  # binário ou ilegível: não é texto publicado
        return self.verificar_texto(texto, caminho)

    def esta_isento(self, caminho: Path) -> bool:
        como_posix = caminho.as_posix()
        return any(caminho.match(padrao) or Path(como_posix).match(padrao)
                   for padrao in self.isentos)

    def coletar_alvos(self, raiz: Path) -> list[Path]:
        encontrados: set[Path] = set()
        for padrao in self.alvos:
            for caminho in raiz.glob(padrao):
                if caminho.is_file() and not self.esta_isento(caminho):
                    encontrados.add(caminho)
        return sorted(encontrados)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verifica o vocabulário controlado do DOC-08 nos textos públicos."
    )
    parser.add_argument("arquivos", nargs="*", type=Path,
                        help="arquivos a verificar; omitido, usa os alvos do vocabulario.json")
    parser.add_argument("--config", type=Path, default=CONFIG_PADRAO)
    parser.add_argument("--raiz", type=Path, default=Path("."),
                        help="raiz para resolver os alvos configurados")
    parser.add_argument("--listar", action="store_true",
                        help="imprime a lista vigente e sai")
    args = parser.parse_args(argv)

    vocab = Vocabulario.carregar(args.config)

    if args.listar:
        print(f"{len(vocab.proibidos)} termos proibidos:\n")
        for termo in sorted(vocab.proibidos):
            print(f"  {termo:<20} -> {vocab.proibidos[termo]}")
        print(f"\n{len(vocab.permitidos)} expressões permitidas (mascaradas antes da checagem):\n")
        for expressao in sorted(vocab.permitidos):
            print(f"  {expressao}")
        return 0

    alvos = [a for a in args.arquivos if a.is_file()] if args.arquivos \
        else vocab.coletar_alvos(args.raiz)

    if not alvos:
        print("Nenhum arquivo alvo encontrado. Nada a verificar.")
        return 0

    violacoes: list[Violacao] = []
    for caminho in alvos:
        violacoes.extend(vocab.verificar_arquivo(caminho))

    if not violacoes:
        print(f"Vocabulário controlado: {len(alvos)} arquivo(s) verificado(s), nenhuma violação.")
        return 0

    for v in violacoes:
        print(v)
        print()

    plural = "ões" if len(violacoes) > 1 else "ão"
    print(f"{len(violacoes)} violaç{plural} de vocabulário controlado em "
          f"{len({v.caminho for v in violacoes})} arquivo(s).")
    print("O Lumen publica indícios, nunca conclusões. Ver DOC-08, seção 3.")
    print(f"Se o uso for legítimo, marque a linha com {vocab.marcador!r} "
          "e justifique na revisão.")
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        # Saída cortada por pipe (ex.: `--listar | head`). Comportamento
        # esperado de ferramenta de linha de comando: sair em silêncio.
        sys.stderr.close()
        sys.exit(0)
