import { describe, expect, it } from "vitest";
import { atalhosPadrao } from "../../componentes/FiltroPeriodo";
import { exerciciosDoArquivo, recortarConformidade, resumoNoPeriodo, somarResumos } from "../conformidade";
import type { ConformidadeEnte, ConformidadePanorama, ResumoConformidade } from "../paineis";
import { anoNoPeriodo, noPeriodo, porAno, somarMeses } from "../periodo";

const r = (cumpre: number, avaliaveis: number, indeterminado = 0): ResumoConformidade => ({
  cumpre, cumpre_parcialmente: 0, nao_cumpre: avaliaveis - cumpre, indeterminado, avaliaveis,
  no_prazo: avaliaveis ? cumpre / avaliaveis : null,
});

describe("anos publicados ano a ano", () => {
  it("o ano só entra inteiro no período; o mês, como antes", () => {
    expect(noPeriodo("2023", { de: "2023-01", ate: "2023-12" })).toBe(true);
    expect(noPeriodo("2023", { de: "2022-01", ate: null })).toBe(true);
    expect(noPeriodo("2023", { de: "2023-03", ate: null })).toBe(false);
    expect(noPeriodo("2023", { de: null, ate: "2023-06" })).toBe(false);
    expect(noPeriodo("2025-03", { de: "2025-01", ate: "2025-12" })).toBe(true);
    expect(somarMeses([["2023", 5, 10], ["2025-01", 1, 2]], { de: "2023-01", ate: "2023-12" }, 2)).toEqual([5, 10]);
  });

  it("o gráfico soma os meses por ano", () => {
    const soma = (a: { mes: string; n: number }, b: { mes: string; n: number }) => ({ mes: a.mes, n: a.n + b.n });
    expect(porAno([{ mes: "2023", n: 9 }, { mes: "2025-01", n: 1 }, { mes: "2025-02", n: 2 }], soma)).toEqual(
      [{ mes: "2023", n: 9 }, { mes: "2025", n: 3 }]);
  });

  it("os atalhos: tudo, último mês, últimos 3 e cada ano", () => {
    const a = atalhosPadrao(["2023", "2024", "2025-01", "2025-02", "2025-03"]);
    expect(a.map((x) => x.rotulo)).toEqual(["Tudo", "Último mês", "Últimos 3 meses", "2023", "2024", "2025"]);
    expect(a[2]!.p).toEqual({ de: "2025-01", ate: "2025-03" });
    expect(atalhosPadrao(["2021", "2022"]).map((x) => x.rotulo)).toEqual(["Tudo", "2021", "2022"]);
  });
});

describe("Conformidade por exercício", () => {
  it("soma os resumos e refaz a fração no prazo", () => {
    expect(somarResumos([r(3, 4), r(1, 4, 2)])).toEqual(
      { cumpre: 4, cumpre_parcialmente: 0, nao_cumpre: 4, indeterminado: 2, avaliaveis: 8, no_prazo: 0.5 });
    expect(somarResumos([]).no_prazo).toBeNull();
    const pe = { "2024": r(1, 2), "2025": r(4, 4) };
    expect(resumoNoPeriodo(r(5, 6), pe, { de: "2025-01", ate: "2025-12" })).toEqual(r(4, 4));
    expect(resumoNoPeriodo(r(5, 6), undefined, { de: "2025-01", ate: null })).toEqual(r(5, 6));
    expect(anoNoPeriodo(2025, { de: "2025-06", ate: "2026-03" })).toBe(true);
  });

  it("refaz o panorama e filtra as obrigações do ente", () => {
    const panorama = {
      versao: 1, tipo: "conformidade-panorama", gerado_em: "", avaliado_em: "", entes: 1, brasil: r(5, 6),
      brasil_por_exercicio: { "2024": r(1, 2), "2025": r(4, 4) },
      criterios: [{ criterio: "rreo", nome: "RREO", ...r(5, 6), por_exercicio: { "2025": r(4, 4) } }],
      ufs: [{ uf: "RS", entes: 1, coletado_em: null, ...r(5, 6), por_exercicio: { "2024": r(1, 2) } }],
    } as ConformidadePanorama;
    const p = recortarConformidade(panorama, { de: "2024-01", ate: "2024-12" });
    expect([p.brasil.cumpre, p.criterios[0]!.avaliaveis, p.ufs[0]!.cumpre]).toEqual([1, 0, 1]);
    expect(exerciciosDoArquivo(panorama)).toEqual(["2024", "2025"]);
    const ente = {
      versao: 1, tipo: "conformidade-ente", resumo: r(2, 2), por_exercicio: { "2024": r(1, 1), "2025": r(1, 1) },
      obrigacoes: [{ exercicio: 2024 }, { exercicio: 2025 }],
    } as unknown as ConformidadeEnte;
    const e = recortarConformidade(ente, { de: "2025-01", ate: "2025-12" });
    expect([e.resumo.avaliaveis, e.obrigacoes.length]).toEqual([1, 1]);
    expect(recortarConformidade(ente, { de: null, ate: null })).toBe(ente);
  });
});
