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

/**
 * Janela que mostra a `caixa` inteira (x mínimo, y mínimo, x máximo, y
 * máximo, em coordenadas da malha) com uma `margem` em volta, na proporção do
 * mapa e dentro dos limites. É o enquadramento do município aberto.
 */
export function enquadrar(caixa: [number, number, number, number], l: Limites, margem = 0.12): Vista {
  const [x0, y0, x1, y1] = caixa;
  const cx = (x0 + x1) / 2;
  const cy = (y0 + y1) / 2;
  const w = Math.max(x1 - x0, ((y1 - y0) * l.largura) / l.altura) * (1 + 2 * margem);
  const h = (w * l.altura) / l.largura;
  return limitar({ x: cx - w / 2, y: cy - h / 2, w, h }, l);
}

/**
 * Aproximação máxima com um município aberto: a de sempre, ou mais, para o
 * menor município ainda poder ser visto de perto (quatro vezes o enquadramento dele).
 */
export function zoomMaximoPara(caixa: [number, number, number, number] | null, l: Omit<Limites, "maxZoom">): number {
  if (!caixa) return ZOOM_MAXIMO;
  const largura = Math.max(caixa[2] - caixa[0], ((caixa[3] - caixa[1]) * l.largura) / l.altura, 1e-9);
  return Math.max(ZOOM_MAXIMO, (4 * l.largura) / largura);
}

/**
 * Janela no instante `t` (0 a 1) da passagem de `a` para `b`. A largura
 * varia em escala logarítmica e o centro acompanha: aproximar oito vezes
 * parece tão rápido no começo quanto no fim.
 */
export function interpolar(a: Vista, b: Vista, t: number): Vista {
  const s = Math.min(1, Math.max(0, t));
  const w = a.w * (b.w / a.w) ** s;
  const k = a.w === b.w ? s : (a.w - w) / (a.w - b.w);
  const cx = a.x + a.w / 2 + (b.x + b.w / 2 - a.x - a.w / 2) * k;
  const cy = a.y + a.h / 2 + (b.y + b.h / 2 - a.y - a.h / 2) * k;
  const h = (w * a.h) / a.w;
  return { x: cx - w / 2, y: cy - h / 2, w, h };
}

/** Curva da animação: começa rápida e desacelera no fim. */
export function suavizar(t: number): number {
  return 1 - (1 - Math.min(1, Math.max(0, t))) ** 3;
}
