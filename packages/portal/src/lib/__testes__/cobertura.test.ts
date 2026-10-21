import { describe, expect, it } from "vitest";
import {
  type Cobertura,
  contarPorUf,
  dadoDoValor,
  dadoPadrao,
  opcoesDeDado,
  pncpPorAno,
  temDado,
  valorDoDado,
} from "../cobertura";

const cobertura: Cobertura = {
  versao: 1, tipo: "cobertura", gerado_em: "x",
  pncp: { de: "2021-08-02", ate: "2026-10-20", anos: ["2021", "2025", "2026"] },
  siconfi: { extrato: ["2025", "2026"], dca: 2025, rgf: 2025, rcl: null },
  limite_art_176: 20000,
  uniao: { pncp: ["2021"] },
  colunas: ["codigo", "ate_20_mil", "pncp", "extrato", "dca", "rgf", "rcl"],
  entes: [
    ["43", false, ["2025", "2026"], ["2025"], true, true, false],
    ["4314902", false, ["2021", "2025"], ["2025", "2026"], true, false, false],
    ["4300034", true, ["2026"], [], false, false, false],
    ["4319604", false, [], ["2025"], false, true, false],
    ["53", false, ["2025"], ["2025"], true, true, false],
  ],
};

describe("cobertura por ente e UF", () => {
  it("conta por UF no recorte e guarda quem não tem o dado", () => {
    const { brasil, ufs } = contarPorUf(cobertura, { fonte: "pncp", ano: "2025" }, "todos");
    expect(brasil).toMatchObject({ entes: 5, com: 3, sem: [] });
    expect(ufs.map((u) => [u.uf, u.entes, u.com, u.sem])).toEqual([
      ["DF", 1, 1, []],
      ["RS", 4, 2, ["4300034", "4319604"]],
    ]);
    const acima = contarPorUf(cobertura, { fonte: "pncp", ano: "2025" }, "acima");
    expect(acima.ufs.find((u) => u.uf === "RS")?.sem).toEqual(["4319604"]);
    expect(contarPorUf(cobertura, { fonte: "dca" }, "ate").brasil).toMatchObject({ entes: 1, com: 0 });
  });

  it("lê cada fonte da linha", () => {
    const linha = cobertura.entes[1]!;
    expect([
      temDado(linha, { fonte: "pncp", ano: "2021" }),
      temDado(linha, { fonte: "extrato", ano: "2026" }),
      temDado(linha, { fonte: "dca" }),
      temDado(linha, { fonte: "rgf" }),
    ]).toEqual([true, true, true, false]);
  });

  it("série do PNCP por ano, opções da caixa e o dado de partida", () => {
    expect(pncpPorAno(cobertura, "todos")).toEqual([
      { ano: "2021", com: 1, entes: 5 }, { ano: "2025", com: 3, entes: 5 }, { ano: "2026", com: 2, entes: 5 },
    ]);
    const opcoes = opcoesDeDado(cobertura);
    expect(opcoes.map((o) => o.valor)).toEqual(["pncp:2026", "pncp:2025", "pncp:2021", "extrato:2026", "extrato:2025",
                                                 "dca", "rgf"]);           // sem a RCL, que não tem exercício
    expect(opcoes[5]?.rotulo).toBe("DCA de 2025 (despesa por função)");
    expect(dadoPadrao(cobertura)).toEqual({ fonte: "pncp", ano: "2025" });   // o último ano inteiro
    expect(dadoPadrao({ ...cobertura, pncp: { de: "2026-01-01", ate: "2026-10-20", anos: ["2026"] } }))
      .toEqual({ fonte: "pncp", ano: "2026" });
    expect(dadoDoValor(valorDoDado({ fonte: "extrato", ano: "2025" }), cobertura)).toEqual({ fonte: "extrato", ano: "2025" });
    expect(dadoDoValor("rcl", cobertura)).toBeNull();
    expect(dadoDoValor("pncp:1999", cobertura)).toBeNull();
  });
});
