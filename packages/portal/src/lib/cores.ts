/**
 * Paleta da aba Eleições (ADR-020, ADR-052).
 *
 * O feed traz um índice, não a cor. PL e PT têm índice fixo — azul (0) e
 * vermelho (1) — em qualquer cargo, nível e eleição, e nenhum outro partido os
 * recebe. Os demais ganham o índice pela ordem de votação no nível mais alto
 * do cargo, na primeira leitura, e o mantêm dali em diante (a cor segue a
 * entidade; a ultrapassagem no meio da apuração não troca cores).
 *
 * Valores: paleta categórica validada para daltonismo (deuteranopia,
 * protanopia, tritanopia) com o validador do método de visualização — ordem
 * fixa, oito posições, versões próprias para fundo claro e escuro. No
 * **mapa** (coroplético, todos os pares lado a lado) pintam as quatro
 * primeiras posições — azul, vermelho, amarelo e verde —, a combinação que
 * passa em todos os pares nos dois temas; da quinta em diante a área aparece
 * como "Outros" (cinza), e o nome e o número continuam na dica, na lista e na
 * tabela (alívio exigido pelo contraste do amarelo < 3:1 no fundo claro).
 */

/**
 * Paleta para fundo claro, na ordem das posições (o índice `cor` do feed).
 * Os mesmos valores estão em `globals.css` como `--serie-1` a `--serie-8`;
 * a tela usa as variáveis, e esta lista serve a quem precisa do hexadecimal.
 */
export const PALETA_CLARA = [
  "#2a78d6", // azul (PL)
  "#e34948", // vermelho (PT)
  "#eda100", // amarelo
  "#008300", // verde
  "#e87ba4", // magenta
  "#4a3aa7", // violeta
  "#1baf7a", // verde-água
  "#eb6834", // laranja
] as const;

/** Paleta para fundo escuro, mesmas posições; espelha as variáveis do tema escuro em `globals.css`. */
export const PALETA_ESCURA = [
  "#3987e5",
  "#e34948",
  "#c98500",
  "#008300",
  "#d55181",
  "#9085e9",
  "#199e70",
  "#d95926",
] as const;

/** Posições que o mapa pinta; o resto é "Outros". */
export const CORES_NO_MAPA = 4;

/** Variável CSS da posição: as cores reais vêm de `globals.css` (claro/escuro). */
export function varCor(indice: number | null | undefined): string {
  if (indice === null || indice === undefined || indice < 0 || indice >= PALETA_CLARA.length) {
    return "var(--serie-outros)";
  }
  return `var(--serie-${indice + 1})`;
}

/** Cor da área no mapa: só as quatro primeiras posições; o resto, "Outros". */
export function varCorMapa(indice: number | null | undefined): string {
  if (indice === null || indice === undefined || indice < 0) return "var(--mapa-sem-lider)";
  return indice < CORES_NO_MAPA ? varCor(indice) : "var(--serie-outros)";
}

/** Mistura com branco (fator 1 = cor cheia); usado no fundo das iniciais. */
export function clarear(hex: string, fator: number): string {
  const n = Number.parseInt(hex.slice(1), 16);
  const f = Math.min(1, Math.max(0, fator));
  const canal = (c: number) => Math.round(255 - (255 - c) * f);
  return `#${[(n >> 16) & 255, (n >> 8) & 255, n & 255].map((c) => canal(c).toString(16).padStart(2, "0")).join("")}`;
}

/** Hexadecimal da posição na paleta clara; fora dela, um cinza neutro. */
export function hexClaro(indice: number): string {
  return PALETA_CLARA[indice] ?? "#8a8f98";
}
