import { describe, expect, it } from "vitest";
import {
  aproximar,
  centro,
  deslocar,
  limitar,
  PASSO_ZOOM,
  viewBox,
  vistaInicial,
  zoomDe,
  ZOOM_MAXIMO,
  type Limites,
} from "../zoom";

const L: Limites = { largura: 1000, altura: 800, maxZoom: ZOOM_MAXIMO };

describe("zoom do mapa", () => {
  it("começa no mapa inteiro", () => {
    const v = vistaInicial(L);
    expect(v).toEqual({ x: 0, y: 0, w: 1000, h: 800 });
    expect(zoomDe(v, L)).toBe(1);
    expect(viewBox(v)).toBe("0 0 1000 800");
  });

  it("aproxima mantendo o ponto sob o cursor no mesmo lugar", () => {
    const v = aproximar(vistaInicial(L), 2, [250, 200], L);
    expect(v.w).toBe(500);
    expect(v.h).toBe(400);
    // O ponto estava a 25% da largura e da altura da janela; continua
    expect((250 - v.x) / v.w).toBeCloseTo(0.25);
    expect((200 - v.y) / v.h).toBeCloseTo(0.25);
    expect(zoomDe(v, L)).toBe(2);
  });

  it("não afasta além do mapa inteiro nem aproxima além do máximo", () => {
    expect(aproximar(vistaInicial(L), 0.5, [500, 400], L)).toEqual(vistaInicial(L));
    let v = vistaInicial(L);
    for (let i = 0; i < 20; i++) v = aproximar(v, PASSO_ZOOM, [500, 400], L);
    expect(zoomDe(v, L)).toBeCloseTo(ZOOM_MAXIMO);
  });

  it("arrasta sem mostrar área fora do mapa", () => {
    const v = aproximar(vistaInicial(L), 2, centro(vistaInicial(L)), L);
    expect(v).toEqual({ x: 250, y: 200, w: 500, h: 400 });
    expect(deslocar(v, 100, 50, L)).toEqual({ x: 150, y: 150, w: 500, h: 400 });
    expect(deslocar(v, 10_000, 10_000, L)).toEqual({ x: 0, y: 0, w: 500, h: 400 });
    expect(deslocar(v, -10_000, -10_000, L)).toEqual({ x: 500, y: 400, w: 500, h: 400 });
    // No mapa inteiro, arrastar não move nada
    expect(deslocar(vistaInicial(L), 100, 100, L)).toEqual(vistaInicial(L));
  });

  it("corrige janela fora da proporção ou do mapa", () => {
    expect(limitar({ x: -5, y: 900, w: 2000, h: 10 }, L)).toEqual(vistaInicial(L));
  });
});
