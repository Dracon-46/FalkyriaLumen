/** Áreas da malha ↔ partes do feed, inclusive as UFs das eleições anteriores a 1994. */
import { describe, expect, it } from "vitest";
import { chaveDaArea, EXTERIOR, formaDoExterior, indexarPartes, parteDaArea, partesSemArea } from "../areas";
import type { Parte } from "../tipos";

function parte(codigo: string, ibge: string | null, nome = codigo): Parte {
  return { codigo, nome, ibge, lider: "1", cor: 0, pct_secoes: 100, finalizada: true, eleitorado: null };
}

describe("áreas do mapa", () => {
  it("UF atual pela sigla; município pelo código IBGE", () => {
    expect(chaveDaArea("35", "uf")).toBe("sp");
    expect(chaveDaArea("3550308", "mu")).toBe("3550308");
    const m = indexarPartes([parte("sp", "35"), parte("3550308", "3550308")]);
    expect(parteDaArea(m, "35", "uf")?.codigo).toBe("sp");
    expect(parteDaArea(m, "3550308", "mu")?.codigo).toBe("3550308");
  });

  it("Território do Guaporé pinta a área de Rondônia; Guanabara e o exterior ficam fora", () => {
    const partes = [
      parte("gp", "11", "Território do Guaporé (atual Rondônia)"),
      parte("gb", null, "Guanabara"),
      parte("df-antigo", null, "Distrito Federal (cidade do Rio de Janeiro)"),
      parte("sp", "35"),
      parte("zz", null, "Exterior"),
    ];
    const m = indexarPartes(partes);
    expect(parteDaArea(m, "11", "uf")?.codigo).toBe("gp");
    expect(parteDaArea(m, "33", "uf")).toBeUndefined();
    const fora = partesSemArea(partes, ["11", "33", "35", "53"], "uf").map((p) => p.codigo);
    expect(fora).toEqual(["gb", "df-antigo", "zz"]);
    // No mapa do Brasil, a área do exterior entra junto com as da malha
    expect(partesSemArea(partes, ["11", "33", "35", "53", EXTERIOR], "uf").map((p) => p.codigo)).toEqual(["gb", "df-antigo"]);
    expect(parteDaArea(m, EXTERIOR, "uf")?.nome).toBe("Exterior");
  });

  it("exterior é um quadrado no Atlântico, na projeção do mapa", () => {
    const f = formaDoExterior({ k: 1, x0: -74, y0: -5, escala: 25 }, 1000);
    expect(f.codigo).toBe("zz");
    expect(f.centro).toEqual([(-38.5 + 74) * 25, (27.5 + 5) * 25]);
    expect(f.caixa[2] - f.caixa[0]).toBeCloseTo(60);
    expect(f.d.startsWith("M") && f.d.endsWith("Z")).toBe(true);
  });

  it("município que ainda não está na malha aparece fora do mapa", () => {
    const partes = [parte("5101837", "5101837", "Boa Esperança do Norte"), parte("5103403", "5103403")];
    expect(partesSemArea(partes, ["5103403"], "mu").map((p) => p.nome)).toEqual(["Boa Esperança do Norte"]);
  });
});
