import { gzipSync } from "node:zlib";
import { afterEach, describe, expect, it, vi } from "vitest";
import { carregarEmendas, type EmendasEnte, recebidoNoPeriodo } from "../emendas";

const arquivo: EmendasEnte = {
  versao: 1, tipo: "emendas-ente", gerado_em: "x", ente: "4319604", data_arquivo: null, fonte: null,
  categorias: { governo_municipal: "Governo municipal", governo_estadual: "Governo estadual",
                entidade: "Entidade sem fins lucrativos", empresa: "Empresa", pessoa_fisica: "Pessoa física" },
  recebido: [
    ["2021", "E1", "governo_municipal", "12231796000172", "FUNDO MUNICIPAL DE SAUDE", 100],
    ["2022", "E1", "governo_municipal", "12231796000172", "FUNDO MUNICIPAL DE SAUDE", 50],
    ["2022", "E2", "empresa", "09537392000105", "EMPRESA X", 30],
    ["2022", "E2", "pessoa_fisica", null, null, 5],
    ["2025", "E3", "entidade", "11111111000191", "ASSOCIACAO Y", 1000],
  ],
  emendas: { E1: ["2021", "Emenda Individual", "DEPUTADA A", "0001", "Saúde", "ATENCAO BASICA"],
             E2: ["2022", "Emenda de Bancada", "BANCADA DO RS", "0002", "Urbanismo", "PAVIMENTACAO"], E3: null },
};

describe("emendas recebidas no mandato", () => {
  it("soma os anos do mandato por categoria, autor e favorecido pessoa jurídica", () => {
    const r = recebidoNoPeriodo(arquivo, ["2021", "2022", "2023", "2024"], (v) => v);
    expect(r.total).toBe(185);
    expect(r.anos).toEqual(["2021", "2022"]);
    expect(r.porCategoria.map((c) => [c.rotulo, c.valor])).toEqual([["Governo municipal", 150], ["Empresa", 30],
                                                                    ["Pessoa física", 5]]);
    expect(r.porAutor.map((a) => [a.rotulo, a.detalhe, a.valor])).toEqual([["DEPUTADA A", "Emenda Individual", 150],
                                                                           ["BANCADA DO RS", "Emenda de Bancada", 35]]);
    expect(r.favorecidos.map((f) => [f.cnpj, f.valor])).toEqual([["12231796000172", 150], ["09537392000105", 30]]);
  });

  it("converte cada ano e deixa de fora o que a conversão não alcança; autor sem descrição tem nome genérico", () => {
    const r = recebidoNoPeriodo(arquivo, ["2021", "2022", "2025"], (v, ano) => (ano === "2021" ? null : v * 2));
    expect(r.total).toBe((50 + 30 + 5 + 1000) * 2);
    expect(r.anos).toEqual(["2022", "2025"]);
    expect(r.porAutor[0]).toMatchObject({ rotulo: "Autor não informado", valor: 2000 });
  });
});

describe("leitura das emendas por grupo de entes", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("acha o ente no arquivo do grupo", async () => {
    const { recebido, emendas, ...resto } = arquivo;
    const grupo = { ...resto, tipo: "emendas-entes", entes: { "4319604": { recebido, emendas } } };
    vi.stubGlobal("fetch", vi.fn(async (url: string) =>
      url.endsWith("/emendas/ente/431.json.gz") ? new Response(gzipSync(JSON.stringify(grupo))) : new Response("", { status: 404 })));
    const e = await carregarEmendas("4319604");
    expect(e?.tipo).toBe("emendas-ente");
    expect(e?.recebido).toHaveLength(5);
    expect(await carregarEmendas("4319999")).toBeNull();
  });
});
