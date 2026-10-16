"""Um arquivo de dentro de um ZIP remoto, sem baixar o ZIP inteiro (requisições com ``Range``).

Algumas fontes só publicam o que interessa dentro de um ZIP grande: a base do PNTP de 2025 tem 338 MB, e
a planilha de avaliações que o Lumen lê, 1,6 MB. Quando o servidor aceita ``Range`` (responde 206), três
leituras curtas bastam: o fim do ZIP (o diretório central, com o deslocamento e o CRC-32 de cada arquivo),
o cabeçalho local e os bytes comprimidos do arquivo pedido. O CRC-32 do diretório central confere que o
conteúdo descomprimido é o mesmo que está no ZIP publicado (ADR-032).

Só ZIP comum (até 4 GB e 65.535 arquivos, sem ZIP64), com o arquivo guardado sem compressão ou com
*deflate*, que é o que as ferramentas de escritório e de servidor geram.
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass

from .cliente_http import ClienteHttp
from .coleta_http import ErroColeta

FIM_DO_ZIP = b"PK\x05\x06"
ENTRADA_CENTRAL = b"PK\x01\x02"
CABECALHO_LOCAL = b"PK\x03\x04"
LEITURA_DO_FIM = 65_536 + 22          # o comentário do ZIP tem no máximo 65.535 bytes
FOLGA_DO_CABECALHO = 1_024             # o campo extra local pode diferir do central


class ErroZipRemoto(ErroColeta):
    """O ZIP remoto não pôde ser lido por partes: servidor sem ``Range``, formato não suportado ou CRC errado."""


@dataclass(frozen=True)
class EntradaZip:
    """Um arquivo do diretório central do ZIP: nome, método, tamanhos, CRC-32 e onde começa."""

    nome: str
    metodo: int
    crc32: int
    tamanho_comprimido: int
    tamanho: int
    deslocamento: int


@dataclass(frozen=True)
class MembroBaixado:
    """O arquivo descomprimido e o que identifica o ZIP de onde saiu (para a proveniência no bronze)."""

    conteudo: bytes
    entrada: EntradaZip
    tamanho_do_zip: int
    etag: str | None
    ultima_modificacao: str | None


def _faixa(cliente: ClienteHttp, url: str, inicio: int, fim: int | None = None) -> tuple[bytes, dict]:
    """Bytes ``inicio``..``fim`` (inclusivos; sem ``fim``, ``inicio`` negativo conta do final) e os cabeçalhos."""
    faixa = f"bytes={inicio}-" + ("" if fim is None else str(fim)) if inicio >= 0 else f"bytes={inicio}"
    artefato = cliente.obter(url, {"Range": faixa, "Accept": "application/zip"})
    if artefato.status_http != 206:
        raise ErroZipRemoto(f"{url} respondeu {artefato.status_http} a Range: {faixa} (esperado 206)")
    return artefato.conteudo, {k.lower(): v for k, v in artefato.cabecalhos.items()}


def ler_diretorio(fim_do_zip: bytes) -> tuple[int, int, int]:
    """(quantidade de entradas, tamanho, deslocamento) do diretório central, a partir do fim do ZIP."""
    pos = fim_do_zip.rfind(FIM_DO_ZIP)
    if pos < 0 or len(fim_do_zip) - pos < 22:
        raise ErroZipRemoto("fim do ZIP não encontrado (arquivo não é ZIP ou é ZIP64)")
    _, _, _, entradas, tamanho, deslocamento, _ = struct.unpack("<HHHHIIH", fim_do_zip[pos + 4:pos + 22])
    if deslocamento == 0xFFFFFFFF or entradas == 0xFFFF:
        raise ErroZipRemoto("ZIP64 não suportado")
    return entradas, tamanho, deslocamento


def entradas(diretorio: bytes) -> list[EntradaZip]:
    """As entradas do diretório central, na ordem em que aparecem."""
    saida = []
    pos = 0
    while pos + 46 <= len(diretorio) and diretorio[pos:pos + 4] == ENTRADA_CENTRAL:
        (_, _, flags, metodo, _, _, crc, comprimido, tamanho, n_nome, n_extra, n_coment, _, _, _,
         deslocamento) = struct.unpack("<HHHHHHIIIHHHHHII", diretorio[pos + 4:pos + 46])
        bruto = diretorio[pos + 46:pos + 46 + n_nome]
        nome = bruto.decode("utf-8" if flags & 0x800 else "cp437")
        saida.append(EntradaZip(nome, metodo, crc, comprimido, tamanho, deslocamento))
        pos += 46 + n_nome + n_extra + n_coment
    return saida


def descomprimir(entrada: EntradaZip, dados: bytes) -> bytes:
    """Conteúdo do arquivo a partir dos bytes comprimidos, conferido pelo tamanho e pelo CRC-32."""
    if entrada.metodo == 0:
        conteudo = dados
    elif entrada.metodo == 8:
        conteudo = zlib.decompress(dados, -15)
    else:
        raise ErroZipRemoto(f"{entrada.nome}: método de compressão {entrada.metodo} não suportado")
    if len(conteudo) != entrada.tamanho or zlib.crc32(conteudo) != entrada.crc32:
        raise ErroZipRemoto(f"{entrada.nome}: tamanho ou CRC-32 não confere com o diretório do ZIP")
    return conteudo


def baixar_membro(cliente: ClienteHttp, url: str, nome: str) -> MembroBaixado:
    """O arquivo ``nome`` de dentro do ZIP em ``url``, em três requisições com ``Range``.

    Levanta ``ErroZipRemoto`` se o servidor não aceita ``Range``, se o ZIP não tem o arquivo ou se o
    conteúdo não confere com o CRC-32 publicado no diretório central.
    """
    fim, cab = _faixa(cliente, url, -LEITURA_DO_FIM)
    total = int(cab.get("content-range", "/0").rsplit("/", 1)[-1] or 0)
    _, tamanho_dir, deslocamento_dir = ler_diretorio(fim)
    inicio_do_trecho = total - len(fim)
    if deslocamento_dir >= inicio_do_trecho:
        diretorio = fim[deslocamento_dir - inicio_do_trecho:deslocamento_dir - inicio_do_trecho + tamanho_dir]
    else:
        diretorio, _ = _faixa(cliente, url, deslocamento_dir, deslocamento_dir + tamanho_dir - 1)
    achadas = [e for e in entradas(diretorio) if e.nome == nome]
    if not achadas:
        raise ErroZipRemoto(f"{url} não tem {nome}")
    e = achadas[0]
    trecho, _ = _faixa(cliente, url, e.deslocamento,
                       e.deslocamento + 30 + len(nome.encode()) + FOLGA_DO_CABECALHO + e.tamanho_comprimido)
    if trecho[:4] != CABECALHO_LOCAL:
        raise ErroZipRemoto(f"{nome}: cabeçalho local não encontrado no deslocamento {e.deslocamento}")
    n_nome, n_extra = struct.unpack("<HH", trecho[26:30])
    inicio = 30 + n_nome + n_extra
    conteudo = descomprimir(e, trecho[inicio:inicio + e.tamanho_comprimido])
    return MembroBaixado(conteudo, e, total, cab.get("etag"), cab.get("last-modified"))
