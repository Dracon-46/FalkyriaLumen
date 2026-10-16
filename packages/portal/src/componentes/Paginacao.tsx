"use client";

/**
 * Paginação das listas e tabelas do portal: toda lista com mais de 20 itens mostra 20 por vez, com a
 * navegação embaixo ("anterior", os números e "próxima") e quantos itens há. A página volta à primeira
 * quando a lista muda (outro filtro, outro ente).
 */

import { useEffect, useMemo, useState } from "react";
import { numero } from "@/lib/formato";
import { paginar, paginasVisiveis, POR_PAGINA, totalDePaginas } from "@/lib/periodo";

/** A página atual de `itens` e o que a navegação precisa; volta à primeira quando `itens` muda. */
export function usePaginacao<T>(itens: readonly T[], porPagina = POR_PAGINA) {
  const [pagina, setPagina] = useState(1);
  useEffect(() => setPagina(1), [itens]);
  const visiveis = useMemo(() => paginar(itens, pagina, porPagina), [itens, pagina, porPagina]);
  return { visiveis, pagina, setPagina, total: itens.length, porPagina };
}

/** A navegação entre as páginas; não aparece quando tudo cabe numa página. */
export function Paginacao({
  pagina,
  setPagina,
  total,
  porPagina = POR_PAGINA,
  rotulo,
}: {
  pagina: number;
  setPagina: (n: number) => void;
  total: number;
  porPagina?: number;
  rotulo: string;
}) {
  const paginas = totalDePaginas(total, porPagina);
  if (paginas <= 1) return null;
  const inicio = (pagina - 1) * porPagina + 1;
  const fim = Math.min(total, pagina * porPagina);
  return (
    <nav className="paginacao" aria-label={`Páginas: ${rotulo}`}>
      <span className="busca-detalhe">
        {numero(inicio)}–{numero(fim)} de {numero(total)}
      </span>
      <span className="paginacao-botoes">
        <button type="button" className="botao" disabled={pagina <= 1} onClick={() => setPagina(pagina - 1)}>
          ‹ <span className="so-largo">Anterior</span>
        </button>
        {paginasVisiveis(pagina, paginas).map((n, i) =>
          n === null ? (
            <span key={`s${i}`} className="paginacao-salto" aria-hidden="true">
              …
            </span>
          ) : (
            <button
              key={n}
              type="button"
              className="botao paginacao-numero"
              aria-current={n === pagina ? "page" : undefined}
              aria-label={`Página ${n}`}
              onClick={() => setPagina(n)}
            >
              {n}
            </button>
          ),
        )}
        <button type="button" className="botao" disabled={pagina >= paginas} onClick={() => setPagina(pagina + 1)}>
          <span className="so-largo">Próxima</span> ›
        </button>
      </span>
    </nav>
  );
}
