import { gzipSync } from "node:zlib";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  anosDaPessoa,
  buscarPessoasJuridicas,
  carregarPessoaJuridica,
  casaComONome,
  cnpjDoTexto,
  contratosPorAno,
  contratosPorEnte,
  emendasPorEnte,
  palavrasDaBusca,
  type PessoaJuridica,
  prefixoDaPalavra,
  recortarPessoa,
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
                                             convenios: 1, valorConvenios: 100, liberado: 80, contratosTce: 0,
                                             valorTce: 0 });
    expect(totaisDaPessoa({ ...pessoa, tce: [["4319604", "2019", 3, 900], ["4319604", "2020", 1, 50]] }))
      .toMatchObject({ contratosTce: 4, valorTce: 950 });
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

describe("período na página do CNPJ", () => {
  it("lista os anos de todas as fontes e recorta pelas pontas", () => {
    const comTce = { ...pessoa, tce: [["4319604", "2019", 3, 900], ["4319604", "2020", 1, 50]] as [string, string, number, number][] };
    expect(anosDaPessoa(comTce)).toEqual(["2019", "2020", "2021", "2022", "2023", "2025", "2026"]);
    const r = recortarPessoa(comTce, "2020", "2023");
    expect(r.contratos).toEqual([]);                          // os contratos são de 2025 e 2026
    expect(r.emendas.map((l) => l[1])).toEqual(["2023", "2022", "2023"]);
    expect(r.tce?.map((l) => l[1])).toEqual(["2020"]);
    expect(r.convenios.map((c) => c[1])).toEqual(["9"]);      // início em 2021
    expect(recortarPessoa(comTce, null, null)).toBe(comTce);
    expect(recortarPessoa(comTce, "2026", null).contratos.map((l) => l[1])).toEqual(["2026", "2026"]);
  });
});

describe("busca pelo nome", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("usa as palavras de três letras ou mais, pelo começo, com o prefixo dividido quando preciso", () => {
    expect(palavrasDaBusca("Ação Social São José Ltda. - ME")).toEqual(["acao", "social", "sao", "jose"]);
    expect(prefixoDaPalavra("comercio", ["co"])).toBe("com");
    expect(prefixoDaPalavra("saude", ["co"])).toBe("sa");
    expect(casaComONome("GENTE SEGURADORA SA", ["segur", "gen"])).toBe(true);
    expect(casaComONome("GENTE SEGURADORA SA", ["seguro"])).toBe(false);
  });

  it("lê só o arquivo da palavra com menos nomes e devolve os que têm todas as palavras", async () => {
    const indice = { versao: 1, tipo: "pj-busca-indice", divididos: ["co"], arquivos: { com: 3, ge: 1 } };
    const ge = { versao: 1, tipo: "pj-busca", prefixo: "ge",
                 pessoas: [["90180605000102", "GENTE SEGURADORA SA", 42], ["11111111000191", "GERAL COMERCIO", 9]] };
    const pedidos: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      pedidos.push(url);
      if (url.endsWith("/pj/busca/indice.json")) return new Response(JSON.stringify(indice), { headers: { "content-type": "application/json" } });
      if (url.endsWith("/pj/busca/ge.json.gz")) return new Response(gzipSync(JSON.stringify(ge)));
      return new Response("", { status: 404 });
    }));
    expect(await buscarPessoasJuridicas("comercio gente")).toEqual([]);           // "gente" e "comercio" juntos: nenhum
    expect(await buscarPessoasJuridicas("seguradora gente")).toEqual([]);         // "se" não tem arquivo
    expect((await buscarPessoasJuridicas("gente"))?.map((a) => a.cnpj)).toEqual(["90180605000102"]);
    expect(pedidos.some((u) => u.endsWith("/com.json.gz"))).toBe(false);          // o de "ge" tem menos nomes
    expect(await buscarPessoasJuridicas("sa")).toEqual([]);                        // palavra curta demais
  });
});
