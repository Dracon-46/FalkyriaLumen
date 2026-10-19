import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  acharReferencia, type ArquivoAnp, carregarComparacaoAnp, compararComAnp, type ProdutoAnp, reconhecerAnp, unidadeCanonica,
} from "../mercado";

afterEach(() => vi.unstubAllGlobals());

// Os mesmos casos do teste do Python (packages/mercado/testes/test_reconhecimento_compartilhado.py)
const CASOS = (JSON.parse(readFileSync(resolve(__dirname, "../../../../mercado/testes/fixtures/reconhecimento_anp.json"), "utf-8")) as
  { casos: [string, string, ProdutoAnp | null][] }).casos;

describe("reconhecimento do item, igual ao do Python", () => {
  it.each(CASOS)("%s (%s) → %s", (descricao, unidade, produto) => {
    expect(reconhecerAnp(descricao, unidade)).toBe(produto);
  });

  it("unidades", () => {
    expect(["Litro", "LT", "LITRO (L)"].map(unidadeCanonica)).toEqual(["litro", "litro", "litro"]);
    expect(["m³", "M3"].map(unidadeCanonica)).toEqual(["m3", "m3"]);
    expect(["Unidade", "UN", "Und."].map(unidadeCanonica)).toEqual(["unidade", "unidade", "unidade"]);
    expect(["Botijão", "RECARGA", "P13"].map(unidadeCanonica)).toEqual(["botijao", "botijao", "botijao"]);
    expect([unidadeCanonica("Caixa"), unidadeCanonica(null), unidadeCanonica("")]).toEqual([null, null, null]);
  });
});

/** Um arquivo da ANP de SP com duas semanas, no formato que os painéis publicam. */
const SP: ArquivoAnp = {
  versao: 1, tipo: "anp-precos", uf: "SP", ano: 2026, gerado_em: "G", fonte: "ANP", pagina: "p",
  semanas: [["2026-09-20", "2026-09-26", "s0.xlsx"], ["2026-09-27", "2026-10-03", "s1.xlsx"]],
  produtos: {
    GASOLINA: {
      uf: [[0, 1227, 5.49, 6.09, 6.39, 6.59, 8.97], [1, 1251, 5.49, 6.13, 6.4, 6.59, 8.97]],
      municipios: { "3550308": [[0, 210, 5.49, 5.99, 6.19, 6.49, 8.97], [1, 4, 5.49, 5.99, 6.29, 6.59, 8.97]] },
    },
  },
};

describe("referência da ANP", () => {
  it("a semana que contém a data, no município com 5 coletas ou mais, senão na UF", () => {
    const mu = acharReferencia([SP], "GASOLINA", "3550308", "2026-09-22")!;
    expect([mu.escopo, mu.inicio, mu.mediana, mu.n, mu.planilha]).toEqual(["municipio", "2026-09-20", 6.19, 210, "s0.xlsx"]);
    const uf = acharReferencia([SP], "GASOLINA", "3550308", "2026-09-29")!;   // só 4 coletas no município
    expect([uf.escopo, uf.mediana]).toEqual(["uf", 6.4]);
    expect(acharReferencia([SP], "GASOLINA", "3550308", "2026-10-08")?.inicio).toBe("2026-09-27");   // 5 dias depois
    expect(acharReferencia([SP], "GASOLINA", "3550308", "2026-10-20")).toBeNull();                 // longe demais
    expect(acharReferencia([SP], "ETANOL", "3550308", "2026-09-22")).toBeNull();
  });

  it("leitura pelos limiares da A-05", () => {
    const ref = acharReferencia([SP], "GASOLINA", "3550308", "2026-09-22");
    expect(compararComAnp("GASOLINA", 6.5, "estimado", "d", ref).situacao).toBe("dentro");
    const acima = compararComAnp("GASOLINA", 7.5, "homologado", "d", ref);
    expect([acima.situacao, acima.limiar, acima.conferirUnidade]).toEqual(["acima", 1.2, false]);
    expect(compararComAnp("GASOLINA", 20, "estimado", "d", ref).conferirUnidade).toBe(true);
    expect(compararComAnp("GASOLINA", 0.01, "estimado", "d", ref).situacao).toBe("fora_de_escala");
    expect(compararComAnp("GASOLINA", 7640000, "estimado", "d", ref).situacao).toBe("fora_de_escala");
    expect(compararComAnp("GLP", 130, "estimado", "d", null).limiar).toBe(1.25);
    expect(compararComAnp("GLP", 130, "estimado", "d", null).situacao).toBe("sem_referencia");
  });

  it("lê o arquivo da UF no ano da data e o do ano vizinho perto da virada", async () => {
    const urls: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      urls.push(url);
      return url.endsWith("uf-sp-2026.json") ? Response.json(SP) : new Response("", { status: 404 });
    }));
    const c = await carregarComparacaoAnp("GASOLINA", 7.5, "homologado", "2026-09-22", "SP", "3550308");
    expect(c.situacao).toBe("acima");
    expect(urls).toEqual(["https://dracon-46.github.io/FalkyriaLumen/mercado/anp/uf-sp-2026.json"]);
    urls.length = 0;
    await carregarComparacaoAnp("GASOLINA", 7.5, "estimado", "2026-01-03", "SP", null);
    expect(urls.map((u) => u.slice(-17))).toEqual(["uf-sp-2026.json", "uf-sp-2025.json"].map((x) => `anp/${x}`.slice(-17)));
    const sem = await carregarComparacaoAnp("GASOLINA", 7.5, "estimado", "2024-05-01", "SP", null);
    expect(sem.motivo).toContain("ainda não publicou");
    expect((await carregarComparacaoAnp("GASOLINA", 7.5, "estimado", "2026-09-22", null, null)).motivo).toContain("UF");
  });
});
