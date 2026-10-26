import { describe, expect, it } from "vitest";
import { type TransferenciasEnte, transferenciasNoPeriodo } from "../transferencias";

const governo = (total: number, acao: string) => ({
  total,
  por_tipo: { legais: total },
  por_area: { Saúde: total },
  por_acao: { [acao]: total },
});

const t: TransferenciasEnte = {
  fonte: "CGU",
  meses: [...Array.from({ length: 12 }, (_, i) => `2025${String(i + 1).padStart(2, "0")}`), "202601", "202602"],
  anos: {
    "2025": { governo: governo(100, "TETO MAC"), entidades: { total: 10, por_area: { Educação: 10 } } },
    "2026": { governo: governo(50, "PDDE") },
  },
};

describe("transferências no mandato", () => {
  it("soma o período, ano a ano, por área e por ação, e aponta o ano incompleto", () => {
    const r = transferenciasNoPeriodo(t, ["2024", "2025", "2026"], (v) => v * 2);
    expect(r.governo).toBe(300);
    expect(r.entidades).toBe(20);
    expect(r.porAno).toEqual([
      { ano: "2024", governo: null, entidades: null, meses: 0 },
      { ano: "2025", governo: 200, entidades: 20, meses: 12 },
      { ano: "2026", governo: 100, entidades: null, meses: 2 },
    ]);
    expect(r.porArea).toEqual([{ chave: "Saúde", valor: 300 }]);
    expect(r.porAcao.map((a) => a.chave)).toEqual(["TETO MAC", "PDDE"]);
    expect(r.incompletos).toEqual(["2026"]);
  });
  it("o ano que a conversão não alcança fica de fora", () => {
    const r = transferenciasNoPeriodo(t, ["2025", "2026"], (v, ano) => (ano === "2026" ? null : v));
    expect(r.governo).toBe(100);
    expect(r.porAcao).toEqual([{ chave: "TETO MAC", valor: 100 }]);
  });
});
