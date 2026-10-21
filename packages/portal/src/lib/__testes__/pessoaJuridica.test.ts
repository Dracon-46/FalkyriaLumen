import { gzipSync } from "node:zlib";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  carregarPessoaJuridica,
  cnpjDoTexto,
  contratosPorAno,
  contratosPorEnte,
  emendasPorEnte,
  type PessoaJuridica,
  totaisDaPessoa,
} from "../pessoaJuridica";

const pessoa: PessoaJuridica = {
  cnpj: "09537392000105", nome: "EMPRESA X LTDA", gerado_em: "x", fontes: { emendas: "20261010", convenios: null },
  contratos: [["43", "2026", 1, 1000], ["4319604", "2025", 2, 150], ["4319604", "2026", 1, 0]],
  emendas: [["4319604", "2023", 30], ["4300034", "2022", 50], ["4300034", "2023", 10]],
  convenios: [["4319604", "9", "CONCLUÍDO", "Praça", "Ministério das Cidades", 100, 80, "2021-03-01"]],
};

describe("pessoa jurídica pelo CNPJ", () => {
  it("soma por ente, do maior valor ao menor, e por ano", () => {
    expect(contratosPorEnte(pessoa)).toEqual([
      { ente: "43", contratos: 1, valor: 1000, anos: ["2026"] },
      { ente: "4319604", contratos: 3, valor: 150, anos: ["2025", "2026"] },
    ]);
    expect(emendasPorEnte(pessoa).map((e) => [e.ente, e.valor, e.anos])).toEqual([
      ["4300034", 60, ["2022", "2023"]], ["4319604", 30, ["2023"]],
    ]);
    expect(contratosPorAno(pessoa)).toEqual([{ ano: "2025", contratos: 2, valor: 150 },
                                              { ano: "2026", contratos: 2, valor: 1000 }]);
    expect(totaisDaPessoa(pessoa)).toEqual({ contratos: 4, valorContratos: 1150, entesContratantes: 2, emendas: 90,
                                             convenios: 1, valorConvenios: 100, liberado: 80 });
  });

  it("aceita o CNPJ com pontuação e recusa o que não tem 14 dígitos", () => {
    expect(cnpjDoTexto("09.537.392/0001-05")).toBe("09537392000105");
    expect(cnpjDoTexto("0953739200010")).toBeNull();
  });
});

describe("leitura por grupo de CNPJ", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("acha o CNPJ no arquivo do grupo (6º a 8º dígitos)", async () => {
    const { cnpj, fontes, gerado_em, ...resto } = pessoa;
    const grupo = { versao: 1, tipo: "pessoas-juridicas", gerado_em, fontes, colunas: {}, pessoas: { [cnpj]: resto } };
    vi.stubGlobal("fetch", vi.fn(async (url: string) =>
      url.endsWith("/pj/392.json.gz") ? new Response(gzipSync(JSON.stringify(grupo))) : new Response("", { status: 404 })));
    const p = await carregarPessoaJuridica("09537392000105");
    expect(p?.nome).toBe("EMPRESA X LTDA");
    expect(p?.fontes.emendas).toBe("20261010");
    expect(await carregarPessoaJuridica("11537392000105")).toBeNull();     // mesmo grupo, CNPJ que não está nele
    expect(await carregarPessoaJuridica("11111111000191")).toBeNull();     // grupo que não existe
  });
});
