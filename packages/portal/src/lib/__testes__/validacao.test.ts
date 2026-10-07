import { describe, expect, it } from "vitest";
import { ErroFeed, validarFeed, validarHistorico, validarIndice, validarMunicipios } from "../validacao";
import { AMOSTRA, arquivosJson, lerJson } from "./apoio";

/**
 * Contrato entre o Python (que grava) e o portal (que lê): a amostra em
 * testes/fixtures/eleicoes_feed é gerada por `lumen eleicoes amostra` e
 * conferida byte a byte do lado Python. Se um lado mudar sem o outro, um dos
 * dois conjuntos de testes quebra.
 */
describe("feeds da amostra gerada pelo Python", () => {
  const arquivos = arquivosJson(AMOSTRA);

  it("tem índice, resultados, panoramas e evolução", () => {
    expect(arquivos).toContain("indice.json");
    expect(arquivos.some((a) => a.endsWith("/br.json"))).toBe(true);
    expect(arquivos.some((a) => a.includes("historico-"))).toBe(true);
  });

  it("índice válido e com cargos e UFs", () => {
    const indice = validarIndice(lerJson(`${AMOSTRA}/indice.json`));
    expect(indice.eleicoes.map((e) => e.id)).toEqual([
      "2026-1t-geral",
      "2024-1t-municipal",
      "1989-2t-geral",
      "1989-1t-geral",
      "1950-1t-geral",
      "1945-1t-geral",
    ]);
    const geral = indice.eleicoes[0]!;
    expect(geral.amostra).toBe(true);
    expect(geral.cargos.map((c) => c.slug)).toEqual(["presidente", "governador", "senador", "deputado-federal"]);
    expect(geral.cargos[1]!.ufs).toEqual(["sp"]);
  });

  for (const arquivo of arquivosJson(AMOSTRA)) {
    if (arquivo === "indice.json") continue;
    it(`valida ${arquivo}`, () => {
      const bruto = lerJson(`${AMOSTRA}/${arquivo}`);
      if (arquivo.includes("historico-")) {
        const h = validarHistorico(bruto);
        expect(h.pontos.length).toBeGreaterThan(0);
        return;
      }
      const feed = validarFeed(bruto, arquivo);
      if (feed.tipo === "resultado") {
        // Contrato: válidos em ordem decrescente, percentuais entre 0 e 100
        const validos = feed.candidatos.filter((c) => c.valido).map((c) => c.votos);
        expect(validos).toEqual([...validos].sort((a, b) => b - a));
        for (const c of feed.candidatos) if (c.pct !== null) expect(c.pct).toBeLessThanOrEqual(100);
      } else {
        expect(feed.partidos.length).toBeGreaterThan(0);
      }
    });
  }

  it("presidente no Brasil: números oficiais do 1º turno de 2026", () => {
    const br = validarFeed(lerJson(`${AMOSTRA}/2026-1t-geral/presidente/br.json`));
    expect(br.tipo).toBe("resultado");
    if (br.tipo !== "resultado") return;
    expect(br.candidatos[0]).toMatchObject({ numero: "22", votos: 56104503 });
    expect(br.votos.validos).toBe(119300788);
    expect(br.partes.map((p) => p.codigo)).toContain("sp");
  });
});

describe("eleições de 1933 a 1990 na amostra", () => {
  it("só por UF, com candidatos sem número de urna", () => {
    const indice = validarIndice(lerJson(`${AMOSTRA}/indice.json`));
    const antigas = indice.eleicoes.filter((e) => e.ano < 1994);
    expect(antigas.every((e) => e.municipios === false)).toBe(true);
    expect(indice.eleicoes.filter((e) => e.ano >= 1994).every((e) => e.municipios === undefined)).toBe(true);
    const br = validarFeed(lerJson(`${AMOSTRA}/1945-1t-geral/presidente/br.json`));
    if (br.tipo !== "resultado") throw new Error("esperado resultado");
    expect(br.candidatos.every((c) => c.sem_numero === true)).toBe(true);
    expect(Object.fromEntries(br.partes.map((p) => [p.codigo, p.ibge]))).toEqual({
      "df-antigo": null,
      fn: null,
      gp: "11",
      ig: null,
      pp: null,
      rb: "14",
    });
    expect(br.avisos.length).toBeGreaterThan(1);
  });

  it("1989 tem número de urna e o exterior", () => {
    const br = validarFeed(lerJson(`${AMOSTRA}/1989-2t-geral/presidente/br.json`));
    if (br.tipo !== "resultado") throw new Error("esperado resultado");
    expect(br.candidatos.map((c) => [c.numero, c.sem_numero])).toEqual([
      ["13", undefined],
      ["20", undefined],
    ]);
    expect(br.partes.map((p) => p.codigo)).toContain("zz");
  });
});

describe("recusa o que não reconhece", () => {
  it("versão diferente", () => {
    expect(() => validarIndice({ versao: 2, eleicoes: [] })).toThrow(ErroFeed);
    expect(() => validarFeed({ versao: 9, tipo: "resultado" })).toThrow(/versão 9/);
  });
  it("tipo desconhecido e campos ausentes", () => {
    expect(() => validarFeed({ versao: 1, tipo: "outro" })).toThrow(/desconhecido/);
    expect(() => validarFeed({ versao: 1, tipo: "resultado" })).toThrow(/faltam/);
    expect(() => validarFeed([])).toThrow(/objeto/);
    expect(() => validarHistorico({ versao: 1, tipo: "resultado" })).toThrow(/não é histórico/);
    expect(() => validarIndice({ versao: 1, eleicoes: [{ id: "x" }] })).toThrow(/faltam/);
    expect(() => validarMunicipios({ versao: 1, municipios: {} })).toThrow(/lista/);
  });
  it("voto que não é número", () => {
    const base = lerJson(`${AMOSTRA}/2026-1t-geral/presidente/br.json`) as Record<string, unknown>;
    const cands = (base.candidatos as Record<string, unknown>[]).map((c) => ({ ...c, votos: "10" }));
    expect(() => validarFeed({ ...base, candidatos: cands })).toThrow(/não é número/);
  });
  it("panorama sem partidos", () => {
    const base = lerJson(`${AMOSTRA}/2024-1t-municipal/prefeito/uf-sp.json`) as Record<string, unknown>;
    expect(validarFeed(base).tipo).toBe("panorama");
    const { partidos: _p, ...sem } = base;
    expect(() => validarFeed(sem)).toThrow(/faltam partidos/);
    expect(validarMunicipios({ versao: 1, municipios: [] }).municipios).toEqual([]);
  });
});
