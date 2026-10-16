/**
 * Opções de uma caixa de escolha com busca (`componentes/Escolha.tsx`), que substitui os `<select>` do portal:
 * a pessoa pode abrir a lista e escolher, ou escrever parte do nome e escolher entre o que casa.
 */

import { normalizar } from "./busca";

/** Uma opção: o valor, o texto, o grupo (cabeçalho na lista) e um detalhe opcional, que também é buscado. */
export interface Opcao {
  valor: string;
  rotulo: string;
  grupo?: string;
  detalhe?: string;
}

/**
 * As opções que casam com o termo: todas as palavras do termo, sem acento nem caixa, em qualquer parte do
 * rótulo, do grupo ou do detalhe ("pres 2022" acha "Presidente · 2022"). Termo vazio devolve todas.
 */
export function filtrarOpcoes(opcoes: readonly Opcao[], termo: string): Opcao[] {
  const palavras = normalizar(termo).split(" ").filter(Boolean);
  if (palavras.length === 0) return [...opcoes];
  return opcoes.filter((o) => {
    const texto = normalizar(`${o.rotulo} ${o.grupo ?? ""} ${o.detalhe ?? ""}`);
    return palavras.every((p) => texto.includes(p));
  });
}
