import { describe, expect, it } from "vitest";
import { type ConveniosEnte, conveniosNoPeriodo } from "../convenios";

const arquivo: ConveniosEnte = {
  versao: 1, tipo: "convenios-ente", gerado_em: "x", ente: "4319604", data_arquivo: "20261009", fonte: null,
  categorias: { governo_municipal: "Governo municipal", entidade: "Entidade sem fins lucrativos" },
  convenios: [
    ["2", "INADIMPLENTE", "Equipamento", "Ministério da Saúde", "entidade", "97227383000177", "ASSOCIACAO", 420, 420, 0,
     "2019-06-02", "2021-06-02", null],
    ["9", "CONCLUÍDO", "Praça", "Ministério das Cidades", "governo_municipal", "97229181000164", "MUNICIPIO", 100, 100, 0,
     "2021-03-01", "2022-03-01", null],
    ["1", "EM EXECUÇÃO", "Habitação", "Ministério das Cidades", "governo_municipal", "97229181000164", "MUNICIPIO",
     2800, 10, 300, "2026-04-30", "2029-04-30", null],
  ],
  pessoa_fisica: { "2020": 5, "2026": 7 },
};

describe("convênios no mandato", () => {
  it("pega os convênios iniciados nos anos, do maior ao menor, com os totais e a situação", () => {
    const r = conveniosNoPeriodo(arquivo, ["2017", "2018", "2019", "2020"], (v) => v);
    expect(r.quantidade).toBe(1);
    expect(r.lista[0]).toMatchObject({ numero: "2", situacao: "INADIMPLENTE", valor: 420, liberado: 420 });
    expect(r.porSituacao).toEqual([{ situacao: "INADIMPLENTE", quantidade: 1, valor: 420 }]);
    expect(r.pessoaFisica).toBe(5);
  });

  it("converte pelo ano de início e deixa de fora o que a conversão não alcança", () => {
    const r = conveniosNoPeriodo(arquivo, ["2021", "2025", "2026"], (v, ano) => (ano === "2021" ? null : v * 2));
    expect(r.lista.map((x) => x.numero)).toEqual(["1"]);
    expect([r.valor, r.liberado, r.pessoaFisica]).toEqual([5600, 20, 14]);
  });
});
