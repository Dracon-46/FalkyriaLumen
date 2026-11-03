"use client";

/**
 * Cabeçalho de coluna que ordena a tabela (`lib/ordem.ts`): um clique ordena pela coluna (números do maior para o
 * menor, textos de A a Z), outro inverte. Marca `aria-sort` para leitor de tela e mostra a seta do sentido.
 */

import type { ReactNode } from "react";
import { type Ordem, proximaOrdem } from "@/lib/ordem";

/** O `<th>` com o botão de ordenar; `texto` diz se a coluna começa de A a Z em vez do maior para o menor. */
export function ThOrdem({ coluna, ordem, onOrdenar, children, className, texto = false }: {
  coluna: string;
  ordem: Ordem | null;
  onOrdenar: (ordem: Ordem) => void;
  children: ReactNode;
  className?: string;
  texto?: boolean;
}) {
  const ativa = ordem?.coluna === coluna;
  const seta = !ativa ? "↕" : ordem.sentido === "asc" ? "▲" : "▼";
  return (
    <th className={className} aria-sort={ativa ? (ordem.sentido === "asc" ? "ascending" : "descending") : undefined}>
      <button type="button" className="th-ordem" onClick={() => onOrdenar(proximaOrdem(ordem, coluna, texto ? "asc" : "desc"))}>
        {children}
        <span className="th-ordem-seta" aria-hidden="true">{seta}</span>
      </button>
    </th>
  );
}
