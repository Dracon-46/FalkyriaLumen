import { gzipSync } from "node:zlib";
import { afterEach, describe, expect, it, vi } from "vitest";
import { anoAAnoComPncp, carregarTce, type TceEnte, tceNoPeriodo } from "../tce";

const sepe: TceEnte = {
  tribunal: "TCE-RS", sistema: "LicitaCon", fonte: "f", primeiroAno: 2016, coletadoEm: null,
  anos: { "2019": [10, 1000, 1, 2, 50, 3, 30], "2020": [5, 500, 0, 0, 0, 0, 0], "2023": [7, 700, 0, 1, 10, 1, 5] },
  fornecedores: [
    ["09537392000105", "EMPRESA X", [["2019", 4, 600], ["2023", 2, 300]]],
    ["11111111000191", null, [["2020", 1, 100]]],
  ],
};

describe("contratos no tribunal de contas", () => {
  it("soma os anos do mandato, com os fornecedores do período", () => {
    const r = tceNoPeriodo(sepe, ["2017", "2018", "2019", "2020"], (v) => v);
    expect(r).toMatchObject({ anos: ["2019", "2020"], contratos: 15, valor: 1500, foraDaSoma: 1, pfContratos: 2,
                              pfValor: 50, aditivos: 3, aditivosValor: 30 });
    expect(r.fornecedores).toEqual([{ cnpj: "09537392000105", nome: "EMPRESA X", contratos: 4, valor: 600 },
                                    { cnpj: "11111111000191", nome: "11111111000191", contratos: 1, valor: 100 }]);
  });

  it("conta os aditivos sem valor quando o tribunal não separa o acréscimo (TCE-CE)", () => {
    const ce: TceEnte = { ...sepe, tribunal: "TCE-CE", anos: { "2019": [10, 1000, 0, 0, 0, 3, null], "2020": [5, 500, 0, 0, 0, 2, 0] } };
    expect(tceNoPeriodo(ce, ["2019", "2020"], (v) => v)).toMatchObject({ aditivos: 5, aditivosValor: null });
  });

  it("deixa de fora o ano que a conversão não alcança", () => {
    const r = tceNoPeriodo(sepe, ["2019", "2023"], (v, ano) => (ano === "2023" ? null : v * 2));
    expect(r.anos).toEqual(["2019"]);
    expect(r.valor).toBe(2000);
    expect(r.fornecedores[0]).toMatchObject({ contratos: 4, valor: 1200 });
  });
});

describe("ano a ano ao lado do PNCP", () => {
  it("soma os meses do PNCP por ano e junta com o tribunal, do mais recente ao mais antigo", () => {
    const meses = [
      { mes: "2022", contratos: 4, valor_contratos: 40 },               // ano publicado inteiro (ADR-046)
      { mes: "2023-01", contratos: 2, valor_contratos: 20 },
      { mes: "2023-07", contratos: 1, valor_contratos: 5 },
    ];
    expect(anoAAnoComPncp(sepe, meses)).toEqual([
      { ano: "2023", pncpContratos: 3, pncpValor: 25, tceContratos: 7, tceValor: 700 },
      { ano: "2022", pncpContratos: 4, pncpValor: 40, tceContratos: null, tceValor: null },
      { ano: "2020", pncpContratos: null, pncpValor: null, tceContratos: 5, tceValor: 500 },
      { ano: "2019", pncpContratos: null, pncpValor: null, tceContratos: 10, tceValor: 1000 },
    ]);
  });
});

describe("leitura por grupo de entes", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("acha o ente e o tribunal dele no arquivo do grupo", async () => {
    const grupo = { versao: 1, tipo: "tce-entes", gerado_em: "x",
                    tribunais: { "TCE-RS": { sistema: "LicitaCon", fonte: "f", coletado_em: "c", primeiro_ano: 2016 } },
                    colunas: [], colunas_fornecedor: [],
                    entes: { "4319604": { tribunal: "TCE-RS", anos: sepe.anos, fornecedores: sepe.fornecedores } } };
    vi.stubGlobal("fetch", vi.fn(async (url: string) =>
      url.endsWith("/tce/ente/196.json.gz") ? new Response(gzipSync(JSON.stringify(grupo))) : new Response("", { status: 404 })));
    const t = await carregarTce("4319604");
    expect(t).toMatchObject({ tribunal: "TCE-RS", sistema: "LicitaCon", primeiroAno: 2016, coletadoEm: "c" });
    expect(await carregarTce("4319699")).toBeNull();          // mesmo grupo, ente que não está nele
    expect(await carregarTce("3550308")).toBeNull();          // grupo que não existe
  });
});
