import { describe, expect, it } from "vitest";
import {
  apareceNoPeriodo,
  cotaDoDeputado,
  cotaPorMes,
  type Deputado,
  filtrarDeputados,
  type LinhaDeputado,
  numerosNoPeriodo,
  totaisDoDeputado,
  votoPorExtenso,
  votosComVotacoes,
  type Votacao,
} from "../parlamentares";

const deputado: Deputado = {
  versao: 1, tipo: "camara-deputado", gerado_em: "x", id: "1", nome: "Fulana", partido: "PL", uf: "MT",
  legislaturas: [57], exercicio: [["2023-02-01", null]],
  anos: {
    "2024": { votos: { "v1": "S" }, presenca: [10, 20], autoria: [], contagem: { REQ: 3 },
              ceap: { categorias: { TELEFONIA: 100 }, meses: { "01": 100 }, fornecedores: [["09537392000105", "X", 1, 100]], pf: [0, 0] } },
    "2025": { votos: { "v2": "N", "v3": "S", "v4": "-" }, presenca: [5, 10],
              autoria: [["P1", "PL", "12", "2025", "Dá nome a uma ponte.", "2025-05-01", null]], contagem: { PL: 1, REQ: 2 },
              ceap: { categorias: { TELEFONIA: 50, COMBUSTÍVEIS: 70 }, meses: { "03": 70, "01": 50 },
                      fornecedores: [["09537392000105", "X NOVA", 2, 50], ["11111111000191", "Y", 1, 70]], pf: [1, 9] } },
  },
};

const votacoes: Record<string, Record<string, Votacao>> = {
  "2024": { v1: ["2024-03-01", "PL 1/2024", "", "", 1, 300, 100, 0, "Sim"] },
  "2025": { v2: ["2025-04-01", "PL 2/2025", "", "", 1, 300, 100, 0, "Sim"],
            v3: ["2025-05-01", "PEC 3/2025", "", "", 0, 200, 250, 0, "Liberado"] },
};

describe("parlamentares", () => {
  it("filtra a lista pelo começo das palavras do nome, pela UF e pelo partido", () => {
    const linhas: LinhaDeputado[] = [["1", "Fulana de Tal", "PL", "MT", [57], 0, 0, 0, 0, 0],
                                     ["2", "Beltrano", "PT", "SP", [57], 0, 0, 0, 0, 0]];
    expect(filtrarDeputados(linhas, { termo: "tal ful" }).map((l) => l[0])).toEqual(["1"]);
    expect(filtrarDeputados(linhas, { uf: "SP" }).map((l) => l[0])).toEqual(["2"]);
    expect(filtrarDeputados(linhas, { partido: "PL", termo: "bel" })).toEqual([]);
  });

  it("soma os números do período pedido e diz se o deputado aparece nele", () => {
    const l: LinhaDeputado = ["1", "Fulana", "PL", "MT", [57], 3, 2, 15, 30, 220,
                              { "2024": [1, 0, 10, 20, 100], "2025": [2, 2, 5, 10, 120] }];
    expect(numerosNoPeriodo(l, null)).toEqual([3, 2, 15, 30, 220]);
    expect(numerosNoPeriodo(l, ["2025", "2026"])).toEqual([2, 2, 5, 10, 120]);
    expect(apareceNoPeriodo(l, ["2023"])).toBe(false);
    expect(apareceNoPeriodo(l, ["2023", "2024"])).toBe(true);
  });

  it("soma os totais de um ano ou de todos", () => {
    expect(totaisDoDeputado(deputado, null)).toMatchObject({ votos: 3, sim: 2, nao: 1, presentes: 15, sessoes: 30,
                                                             proposicoes: 1, cota: 220, contagem: { PL: 1, REQ: 5 } });
    expect(totaisDoDeputado(deputado, "2025")).toMatchObject({ votos: 2, presentes: 5, sessoes: 10, cota: 120 });
  });

  it("junta a cota por categoria e fornecedor, com o nome mais recente, e põe os meses em ordem", () => {
    const c = cotaDoDeputado(deputado, null);
    expect(c.categorias).toEqual([["TELEFONIA", 150], ["COMBUSTÍVEIS", 70]]);
    expect(c.fornecedores).toEqual([["09537392000105", "X NOVA", 3, 150], ["11111111000191", "Y", 1, 70]]);
    expect(c.pf).toEqual([1, 9]);
    expect(cotaPorMes(deputado, "2025")).toEqual([{ mes: "01", valor: 50 }, { mes: "03", valor: 70 }]);
  });

  it("liga cada voto à votação, do mais recente ao mais antigo, e compara com a orientação do Governo", () => {
    const v = votosComVotacoes(deputado, null, votacoes);
    expect(v.map((x) => x.id)).toEqual(["v3", "v2", "v1", "v4"]);
    expect(v.map((x) => x.comOGoverno)).toEqual([null, false, true, null]);   // "Liberado" não é orientação Sim ou Não
    expect(votoPorExtenso("O")).toBe("Obstrução");
  });
});
