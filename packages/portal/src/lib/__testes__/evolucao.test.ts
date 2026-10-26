import { describe, expect, it } from "vitest";
import { escalaVertical, pontosDaEscala, seriesDaEvolucao, vantagem } from "../evolucao";
import type { FeedHistorico } from "../tipos";

const historico = {
  candidatos: [
    { numero: "22", nome_urna: "B", partido: "PL", cor: 0 },
    { numero: "13", nome_urna: "A", partido: "PT", cor: 1 },
  ],
  pontos: [
    { t: null, pct_secoes: 0, votos: { "13": 0, "22": 0 } },
    { t: null, pct_secoes: 10, votos: { "13": 40, "22": 60 } },
    { t: null, pct_secoes: null, votos: { "13": 1, "22": 1 } },
    { t: null, pct_secoes: 100, votos: { "13": 520, "22": 480 } },
  ],
} as unknown as FeedHistorico;

describe("evolução da apuração", () => {
  it("ordena pelo último ponto e descarta leituras sem voto ou sem seção", () => {
    const { series, xs } = seriesDaEvolucao(historico, 4);
    expect(series.map((s) => s.numero)).toEqual(["13", "22"]);
    expect(xs).toEqual([10, 100]);
    expect(series[0]?.pontos.map((p) => p.y)).toEqual([40, 52]);
  });
  it("vantagem do primeiro sobre o segundo, negativa quando ele estava atrás", () => {
    const { series } = seriesDaEvolucao(historico, 4);
    expect(vantagem(series).map((p) => Math.round(p.y))).toEqual([-20, 4]);
    expect(vantagem(series.slice(0, 1))).toEqual([]);
  });
  it("escala vertical justa: disputa apertada não fica num eixo de 0 a 60%", () => {
    const e = escalaVertical([48.2, 51.7, 49.9]);
    expect(e.min).toBe(48);
    expect(e.max).toBe(52);
    expect(e.marcas.length).toBeLessThanOrEqual(7);
    expect(escalaVertical([2, 98])).toMatchObject({ min: 0, max: 100 });
    // A vantagem sempre mostra o zero
    expect(escalaVertical([3, 5], { zero: true }).min).toBe(0);
    expect(escalaVertical([-4, 2], { zero: true }).marcas).toContain(0);
  });
});

describe("escala da evolução", () => {
  it("ignora o começo da apuração (menos de 2% das seções), se sobrar o bastante", () => {
    const pontos = [{ x: 0.3, y: 15 }, { x: 1, y: 4 }, { x: 5, y: 1 }, { x: 100, y: 3.6 }];
    expect(pontosDaEscala(pontos).map((p) => p.y)).toEqual([1, 3.6]);
    expect(pontosDaEscala(pontos.slice(0, 3))).toHaveLength(3);
  });
});
