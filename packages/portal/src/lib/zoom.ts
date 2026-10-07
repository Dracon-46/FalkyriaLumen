/**
 * Aproximação e arrasto do mapa, como contas puras sobre a janela visível.
 *
 * O mapa é um SVG cuja `viewBox` é a janela: aproximar é encolher a janela em
 * torno de um ponto, arrastar é deslocá-la. As coordenadas são as da malha
 * projetada (as mesmas de `MapaProjetado`), não pixels — por isso nada aqui
 * depende do tamanho da tela, e as contas têm teste sem navegador.
 */

/** Janela visível em coordenadas da malha: canto superior esquerdo, largura e altura. */
export interface Vista {
  x: number;
  y: number;
  w: number;
  h: number;
}

/** Tamanho do mapa inteiro e o quanto ele pode ser aproximado. */
export interface Limites {
  largura: number;
  altura: number;
  /** Aproximação máxima; com 16, o menor município de MG ou de SP fica com tamanho clicável. */
  maxZoom: number;
}

/** Aproximação máxima do mapa: 16 vezes o mapa inteiro. */
export const ZOOM_MAXIMO = 16;
/** Passo dos botões + e − e das teclas. */
export const PASSO_ZOOM = 1.6;

/** O mapa inteiro. */
export function vistaInicial(l: Limites): Vista {
  return { x: 0, y: 0, w: l.largura, h: l.altura };
}

/** Quantas vezes a janela está aproximada (1 = mapa inteiro). */
export function zoomDe(v: Vista, l: Limites): number {
  return l.largura / v.w;
}

/**
 * Mantém a janela dentro do mapa: tamanho entre o mapa inteiro e
 * `1/maxZoom` dele, sempre na proporção do mapa, e sem mostrar área de fora.
 */
export function limitar(v: Vista, l: Limites): Vista {
  const w = Math.min(l.largura, Math.max(l.largura / l.maxZoom, v.w));
  const h = (w * l.altura) / l.largura;
  const x = Math.min(Math.max(v.x, 0), l.largura - w);
  const y = Math.min(Math.max(v.y, 0), l.altura - h);
  return { x, y, w, h };
}

/**
 * Aproxima (`fator` > 1) ou afasta (< 1) mantendo `ponto` — coordenadas da
 * malha, em geral sob o cursor — no mesmo lugar da tela.
 */
export function aproximar(v: Vista, fator: number, ponto: [number, number], l: Limites): Vista {
  const alvo = limitar({ ...v, w: v.w / fator }, l);
  const fx = (ponto[0] - v.x) / v.w;
  const fy = (ponto[1] - v.y) / v.h;
  return limitar({ x: ponto[0] - fx * alvo.w, y: ponto[1] - fy * alvo.h, w: alvo.w, h: alvo.h }, l);
}

/** Desloca o conteúdo `dx`, `dy` (unidades da malha; positivo = para a direita e para baixo). */
export function deslocar(v: Vista, dx: number, dy: number, l: Limites): Vista {
  return limitar({ ...v, x: v.x - dx, y: v.y - dy }, l);
}

/** Centro da janela, para aproximar pelos botões. */
export function centro(v: Vista): [number, number] {
  return [v.x + v.w / 2, v.y + v.h / 2];
}

/** `viewBox` do SVG para a janela. */
export function viewBox(v: Vista): string {
  return `${v.x} ${v.y} ${v.w} ${v.h}`;
}
