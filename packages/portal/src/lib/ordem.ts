/**
 * Ordenação das tabelas pelo cabeçalho da coluna (`componentes/ThOrdem`): a coluna escolhida e o sentido, e a função
 * que ordena as linhas por ela. Texto em ordem alfabética do português; número do maior para o menor no primeiro clique.
 */

/** A coluna e o sentido; `null` deixa a ordem que a tabela já tinha. */
export interface Ordem {
  coluna: string;
  sentido: "asc" | "desc";
}

const comparador = new Intl.Collator("pt-BR", { sensitivity: "base", numeric: true });

/** Um valor de célula para ordenar: número, texto ou ausente (vai para o fim nos dois sentidos). */
export type ValorOrdem = number | string | null | undefined;

/** As linhas ordenadas pela coluna (`valores[coluna](linha)`), sem mudar a lista recebida. */
export function ordenar<T>(linhas: readonly T[], ordem: Ordem | null, valores: Record<string, (linha: T) => ValorOrdem>): T[] {
  const ler = ordem ? valores[ordem.coluna] : undefined;
  if (!ordem || !ler) return [...linhas];
  const sinal = ordem.sentido === "asc" ? 1 : -1;
  return linhas
    .map((linha, i) => ({ linha, i, v: ler(linha) }))
    .sort((a, b) => {
      const vazioA = a.v === null || a.v === undefined || a.v === "";
      const vazioB = b.v === null || b.v === undefined || b.v === "";
      if (vazioA || vazioB) return vazioA === vazioB ? a.i - b.i : vazioA ? 1 : -1;
      const c = typeof a.v === "number" && typeof b.v === "number" ? a.v - b.v : comparador.compare(String(a.v), String(b.v));
      return c === 0 ? a.i - b.i : sinal * c;
    })
    .map((x) => x.linha);
}

/** O próximo estado ao clicar numa coluna: na mesma coluna, inverte; noutra, começa pelo sentido padrão dela. */
export function proximaOrdem(atual: Ordem | null, coluna: string, padrao: Ordem["sentido"]): Ordem {
  if (atual?.coluna === coluna) return { coluna, sentido: atual.sentido === "asc" ? "desc" : "asc" };
  return { coluna, sentido: padrao };
}
