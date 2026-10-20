import { describe, expect, it } from "vitest";
import {
  MANDATOS,
  type Indicador,
  mesValido,
  normalizarFeed,
  periodoCurto,
  recortar,
  resumir,
  tamanho,
  valorNaUnidade,
  variacaoTexto,
} from "../economia";

function indicador(parcial: Partial<Indicador> & Pick<Indicador, "serie">): Indicador {
  const ultimoPonto = parcial.serie[parcial.serie.length - 1];
  return {
    nome: "x",
    grupo: "g",
    unidade: "% do PIB",
    periodicidade: "mensal",
    definicao: "",
    leitura: null,
    limitacoes: [],
    agregacao: "nivel",
    fonte: "SGS",
    coletado_em: "2026-10-16T00:00:00+00:00",
    ultimo: ultimoPonto ? { periodo: ultimoPonto[0], valor: ultimoPonto[1] } : null,
    lacunas: [],
    ...parcial,
  };
}

const meses = (ano: number, valor: (m: number) => number): [string, number][] =>
  Array.from({ length: 12 }, (_, i) => [`${ano}-${String(i + 1).padStart(2, "0")}`, valor(i + 1)]);

describe("períodos", () => {
  it("mandatos em ordem, sem buraco nem sobreposição", () => {
    for (let i = 1; i < MANDATOS.length; i++) {
      const anterior = MANDATOS[i - 1]!;
      const atual = MANDATOS[i]!;
      expect(atual.de > anterior.ate).toBe(true);
      expect(tamanho({ de: anterior.ate, ate: atual.de }, "mensal")).toBe(2);
    }
    expect(MANDATOS.every((m) => mesValido(m.de) && mesValido(m.ate))).toBe(true);
  });

  it("mês válido e tamanho do período", () => {
    expect(mesValido("2025-13")).toBe(false);
    expect(mesValido(null)).toBe(false);
    expect(tamanho({ de: "2019-01", ate: "2022-12" }, "mensal")).toBe(48);
    expect(tamanho({ de: "2019-01", ate: "2022-12" }, "anual")).toBe(4);
    expect(tamanho({ de: "2022-01", ate: "2021-12" }, "mensal")).toBe(0);
  });

  it("recorta a série mensal pelo mês e a anual pelo ano", () => {
    const m = indicador({ serie: [["2018-12", 1], ["2019-01", 2], ["2022-12", 3], ["2023-01", 4]] });
    expect(recortar(m, { de: "2019-01", ate: "2022-12" }).map(([k]) => k)).toEqual(["2019-01", "2022-12"]);
    const a = indicador({ periodicidade: "anual", serie: [["2018", 1], ["2019", 2], ["2022", 3], ["2023", 4]] });
    expect(recortar(a, { de: "2019-01", ate: "2022-12" }).map(([k]) => k)).toEqual(["2019", "2022"]);
  });
});

describe("resumo de um período", () => {
  it("nível: início é o último valor antes do período, e a variação em pontos percentuais", () => {
    const divida = indicador({ serie: [["2018-11", 76], ["2018-12", 75.3], ["2020-12", 86.9], ["2022-12", 71.7]] });
    const r = resumir(divida, { de: "2019-01", ate: "2022-12" });
    expect(r.inicio).toEqual({ periodo: "2018-12", valor: 75.3 });
    expect(r.fim).toEqual({ periodo: "2022-12", valor: 71.7 });
    expect(r.variacao).toBeCloseTo(-3.6);
    expect(variacaoTexto(r)).toBe("−3,60 p.p.");
    expect(r.media).toBeCloseTo((86.9 + 71.7) / 2);
  });

  it("nível em reais: variação em percentual; sem valor antes, o início é o primeiro do período", () => {
    const pib = indicador({ unidade: "R$ milhões correntes", serie: [["2019-01", 100], ["2019-12", 110]] });
    const r = resumir(pib, { de: "2019-01", ate: "2019-12" });
    expect(r.inicio?.periodo).toBe("2019-01");
    expect(r.variacao).toBeCloseTo(10);
    expect(variacaoTexto(r)).toBe("+10,0%");
    expect(variacaoTexto(resumir(pib, { de: "2030-01", ate: "2030-12" }))).toBe("—");
  });

  it("taxa mensal: acumula só com todos os meses até o último publicado", () => {
    const ipca = indicador({ unidade: "% no mês", agregacao: "variacao_mensal", serie: meses(2025, () => 1) });
    expect(resumir(ipca, { de: "2025-01", ate: "2025-12" }).acumulado).toBeCloseTo(12.6825, 3);
    // período que passa do último mês publicado: acumula até ele e diz até quando
    const emCurso = resumir(ipca, { de: "2025-07", ate: "2026-12" });
    expect(emCurso.acumulado).toBeCloseTo((1.01 ** 6 - 1) * 100, 6);
    expect(emCurso.ateEfetivo).toBe("2025-12");
    const comBuraco = indicador({ ...ipca, serie: ipca.serie.filter(([k]) => k !== "2025-06") });
    const r = resumir(comBuraco, { de: "2025-01", ate: "2025-12" });
    expect(r.acumulado).toBeNull();
    expect([r.observacoes, r.esperadas]).toEqual([11, 12]);
  });

  it("taxa anual: acumula os anos publicados", () => {
    const pib = indicador({
      unidade: "% no ano",
      periodicidade: "anual",
      agregacao: "variacao_anual",
      serie: [["2023", 3.24], ["2024", 3.42], ["2025", 2.29]],
    });
    const r = resumir(pib, { de: "2023-01", ate: "2026-12" });
    expect(r.ateEfetivo).toBe("2025-12");
    expect(r.acumulado).toBeCloseTo((1.0324 * 1.0342 * 1.0229 - 1) * 100, 6);
  });
});

describe("formato", () => {
  it("período e valores nas unidades", () => {
    expect(periodoCurto("2025-03")).toBe("mar/2025");
    expect(periodoCurto("2025")).toBe("2025");
    expect(valorNaUnidade(82.87, "% do PIB")).toBe("82,87% do PIB");
    expect(valorNaUnidade(4.581, "% em 12 meses")).toBe("4,58%");
    expect(valorNaUnidade(13402023.7, "R$ milhões correntes")).toBe("R$ 13,4 tri");
    expect(valorNaUnidade(950000, "R$ milhões correntes")).toBe("R$ 950 bi");
    expect(valorNaUnidade(3777, "R$ por mês (preços do último trimestre)")).toBe("R$ 3.777,00");
    expect(valorNaUnidade(213421037, "pessoas")).toBe("213,4 milhões");
    expect(valorNaUnidade(3705.42, "R$ bilhões de 2025")).toBe("R$ 3.705,4 bi");
    expect(valorNaUnidade(111.7192, "índice (2002 = 100)")).toBe("111,72");
    expect(valorNaUnidade(null, "%")).toBe("—");
  });
});

describe("arquivo", () => {
  it("indicador sem agregação é tratado como nível, e campos ausentes viram listas vazias", () => {
    const feed = normalizarFeed({
      versao: 1,
      tipo: "economia",
      gerado_em: "",
      grupos: [],
      indicadores: { divida: { nome: "Dívida" } as unknown as Indicador },
    });
    const d = feed.indicadores.divida!;
    expect([d.agregacao, d.serie, d.limitacoes, d.lacunas]).toEqual(["nivel", [], [], []]);
  });
});

describe("quebra de método", () => {
  const pop = {
    nome: "População", grupo: "populacao", unidade: "pessoas", periodicidade: "anual", definicao: "", leitura: null,
    limitacoes: [], agregacao: "nivel", fonte: "IBGE", coletado_em: null, lacunas: [], quebras: ["2013", "2024"],
    serie: [["2018", 208.5e6], ["2019", 210.1e6], ["2020", 211.8e6], ["2021", 213.3e6], ["2024", 212.6e6],
            ["2025", 213.4e6]],
    ultimo: { periodo: "2025", valor: 213.4e6 },
  } as unknown as Indicador;

  it("não calcula variação quando o período atravessa uma quebra", () => {
    const r = resumir(pop, { de: "2023-01", ate: "2026-12" });
    expect(r.inicio?.periodo).toBe("2021");
    expect(r.fim?.periodo).toBe("2025");
    expect(r.quebra).toBe("2024");
    expect(r.variacao).toBeNull();
  });

  it("calcula quando início e fim estão do mesmo lado", () => {
    const r = resumir(pop, { de: "2019-01", ate: "2022-12" });
    expect(r.quebra).toBeNull();
    expect(r.variacao).toBeCloseTo((213.3 / 208.5 - 1) * 100, 6);
  });
});

describe("valor anual", () => {
  const despesa = {
    nome: "Despesa total da União", grupo: "despesa_uniao", unidade: "R$ bilhões de 2025", periodicidade: "anual",
    definicao: "", leitura: null, limitacoes: [], agregacao: "valor_anual", fonte: "", coletado_em: null, lacunas: [],
    serie: [["2019", 3100], ["2020", 3900], ["2021", 3300], ["2022", 3200], ["2023", 3500], ["2024", 3600]],
    ultimo: { periodo: "2024", valor: 3600 },
  } as unknown as Indicador;

  it("mantém a agregação ao ler o arquivo", () => {
    const feed = normalizarFeed({ indicadores: { d: { ...despesa }, x: { ...despesa, agregacao: "outra" } } } as never);
    expect([feed.indicadores.d!.agregacao, feed.indicadores.x!.agregacao]).toEqual(["valor_anual", "nivel"]);
  });

  it("resume pela média dos anos do período, sem acumular", () => {
    const r = resumir(despesa, { de: "2019-01", ate: "2022-12" });
    expect(r.media).toBe(3375);
    expect(r.acumulado).toBeNull();
    expect([r.observacoes, r.esperadas]).toEqual([4, 4]);
    const parcial = resumir(despesa, { de: "2023-01", ate: "2026-12" });
    expect(parcial.media).toBe(3550);
    expect(parcial.ateEfetivo).toBe("2024-12");
  });
});
