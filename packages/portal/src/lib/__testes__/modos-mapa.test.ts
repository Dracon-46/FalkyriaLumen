import { describe, expect, it } from "vitest";
import { CIDADES_EXTERIOR, coordenadaDaCidade } from "../exterior";
import { corDaParte, type ContextoMudanca, forcaNa, FAIXAS_PCT, modoDisponivel, mudancaNaParte } from "../modos-mapa";
import type { Parte } from "../tipos";
import { cortarNoAntimeridiano } from "../topojson";

function parte(codigo: string, extra: Partial<Parte>): Parte {
  return { codigo, nome: codigo, ibge: null, lider: "13", cor: 1, pct_secoes: 100, finalizada: true, eleitorado: 10, ...extra };
}

const ctx = (primeiro: Parte[]): ContextoMudanca => ({
  primeiro: new Map(primeiro.map((p) => [p.codigo, p])),
  a: { numero: "13", nome: "LULA", cor: 1 },
  b: { numero: "22", nome: "FLAVIO", cor: 0 },
});

describe("modos de cor do mapa", () => {
  it("vencedor: a cor cheia; % de votos: a mesma cor, mais forte quanto maior o percentual", () => {
    const p = parte("sp", { pct: 52 });
    expect(corDaParte("vencedor", p, null)).toBe("var(--serie-2)");
    expect(corDaParte("intensidade", p, null)).toBe("color-mix(in srgb, var(--serie-2) 60%, var(--superficie))");
    expect(corDaParte("intensidade", parte("ba", { pct: 75 }), null)).toBe("var(--serie-2)");
    expect(forcaNa(FAIXAS_PCT, 44)).toBeLessThan(forcaNa(FAIXAS_PCT, 61));
    expect(corDaParte("vencedor", parte("x", { lider: null }), null)).toBe("var(--mapa-sem-lider)");
  });

  it("mudança: quanto um finalista cresceu a mais que o outro, com o resto dos 100% no 2º turno", () => {
    const um = parte("sp", { lider: "22", pct: 47, pcts: { "22": 47, "13": 45 } });
    // 2º turno: só o líder no feed antigo, o outro sai do resto
    const dois = parte("sp", { lider: "13", pct: 52 });
    expect(mudancaNaParte(dois, um, ctx([um]))).toBeCloseTo(52 - 45 - (48 - 47));
    expect(corDaParte("mudanca", dois, ctx([um]))).toContain("var(--serie-2)");
    // No 1º turno sem `pcts` e com outro líder, falta o percentual de um deles
    const semPcts = parte("rj", { lider: "22", pct: 47 });
    expect(mudancaNaParte(parte("rj", { pct: 52 }), semPcts, ctx([semPcts]))).toBeNull();
    expect(modoDisponivel("mudanca", [parte("rj", { pct: 52 })], ctx([semPcts]))).toBe(false);
  });

  it("abstenção só com o dado no feed", () => {
    expect(modoDisponivel("abstencao", [parte("sp", {})], null)).toBe(false);
    const p = parte("sp", { pct_abstencao: 22 });
    expect(modoDisponivel("abstencao", [p], null)).toBe(true);
    expect(corDaParte("abstencao", p, null)).toBe("color-mix(in srgb, var(--texto) 56%, var(--superficie))");
  });
});

describe("mapa do mundo", () => {
  it("as 186 cidades do exterior de 2026 têm posição", () => {
    expect(Object.keys(CIDADES_EXTERIOR)).toHaveLength(186);
    expect(coordenadaDaCidade("zz-29955")).toEqual([-9.14, 38.72]); // Lisboa
    expect(coordenadaDaCidade("sp")).toBeNull();
  });

  it("anel que cruza 180° vira um pedaço de cada lado", () => {
    const anel: [number, number][] = [[170, 0], [179, 1], [-179, 1], [-170, 0], [-179, -1], [179, -1]];
    const pedacos = cortarNoAntimeridiano(anel);
    expect(pedacos).toHaveLength(2);
    expect(pedacos.every((r) => r.every(([lon]) => lon > 0) || r.every(([lon]) => lon < 0))).toBe(true);
    const brasil: [number, number][] = [[-50, -10], [-40, -10], [-45, -5]];
    expect(cortarNoAntimeridiano(brasil)).toEqual([brasil]);
  });
});
