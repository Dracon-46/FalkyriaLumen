import { describe, expect, it } from "vitest";
import {
  anoBase,
  anosMunicipais,
  anosMunicipaisComDespesa,
  eleicoesMunicipais,
  eleitoNoFeed,
  emReaisDe,
  foiAoSegundoTurno,
  ipcaMedioAnual,
  lerDca,
  lerSidraAnual,
  mandatoDe,
  populacaoPorAno,
  quemGovernou,
  resumirMandatos,
  urlDca,
} from "../governos";
import type { Candidato, Feed, Indice } from "../tipos";
import { ErroFeed } from "../validacao";

const candidato = (nome: string, situacao: string): Candidato =>
  ({ numero: "10", nome_urna: nome, nome, partido: "PX", agremiacao: null, composicao: null, votos: 1, pct: 50,
     situacao, eleito: situacao === "Eleito", segundo_turno: situacao === "2º turno", valido: true,
     destinacao: null, vice: null, cor: 0, foto: null }) as Candidato;
const resultado = (...c: Candidato[]) => ({ tipo: "resultado", candidatos: c }) as unknown as Feed;

describe("mandatos", () => {
  it("lista os anos de eleição municipal com prefeito na UF", () => {
    const e = (ano: number, turno: number, tipo: string, ufs?: string[]) =>
      ({ id: `${ano}-${turno}t-${tipo}`, ano, turno, tipo, cargos: [{ slug: "prefeito", ufs }] });
    const indice = { eleicoes: [e(2024, 1, "municipal", ["rs", "sp"]), e(2024, 2, "municipal"), e(2022, 1, "geral"),
                                e(2020, 1, "municipal"), e(2016, 1, "municipal", ["sp"])] } as unknown as Indice;
    expect(anosMunicipais(indice, "RS")).toEqual([2020, 2024]);
    expect(anosMunicipais(null, "RS")).toEqual([]);
  });

  it("tira os mandatos do calendário: a eleição do ano só depois de outubro", () => {
    expect(eleicoesMunicipais(new Date(2026, 9, 20))).toEqual([2000, 2004, 2008, 2012, 2016, 2020, 2024]);
    expect(eleicoesMunicipais(new Date(2028, 5, 1)).at(-1)).toBe(2024);
    expect(eleicoesMunicipais(new Date(2028, 10, 2)).at(-1)).toBe(2028);
  });

  it("acha o eleito e o 2º turno e monta o mandato", () => {
    const primeiro = resultado(candidato("A", "2º turno"), candidato("B", "2º turno"), candidato("C", "Não eleito"));
    expect(eleitoNoFeed(primeiro)).toBeNull();
    expect(foiAoSegundoTurno(primeiro)).toBe(true);
    const eleito = eleitoNoFeed(resultado(candidato("B", "Eleito")));
    const m = mandatoDe(2024, eleito, 2, true);
    expect([m.de, m.ate, m.prefeito, m.turno]).toEqual([2025, 2028, "B", 2]);
    expect(quemGovernou(m)).toBe("B (PX)");
    expect(quemGovernou(mandatoDe(2020, null, null, true))).toBe("eleito não identificado no resultado do TSE");
    expect(quemGovernou(mandatoDe(2016, null, null, false))).toBe("resultado não publicado no Lumen");
  });
});

describe("fontes", () => {
  it("lê o SIDRA anual e põe o Censo 2022 nos anos sem estimativa", () => {
    const bruto = [{ D3C: "Ano (Código)", V: "Valor" }, { D3C: "2021", V: "23492" }, { D3C: "2024", V: "21575" },
                   { D3C: "2025", V: "..." }];
    const est = lerSidraAnual(bruto);
    expect(est).toEqual([["2021", 23492], ["2024", 21575]]);
    const pop = populacaoPorAno(est, 21219);
    expect([pop.get("2021"), pop.get("2022"), pop.get("2023"), pop.get("2024")]).toEqual([23492, 21219, 21219, 21575]);
    expect(() => lerSidraAnual({})).toThrow(ErroFeed);
  });

  it("lê a despesa liquidada das funções na DCA (linhas reais de São Sepé, 2024)", () => {
    const linha = (conta: string, coluna: string, valor: number) =>
      ({ exercicio: 2024, anexo: "DCA-Anexo I-E", rotulo: "Total Geral da Despesa por Função", coluna,
         cod_conta: "TotalDespesas", conta, valor });
    const bruto = { items: [
      linha("Despesas Exceto Intraorçamentárias", "Despesas Empenhadas", 135933241.22),
      linha("Despesas Exceto Intraorçamentárias", "Despesas Liquidadas", 131688419.93),
      linha("10 - Saúde", "Despesas Liquidadas", 28171405.62),
      linha("10.301 - Atenção Básica", "Despesas Liquidadas", 11954931.93),
      linha("12 - Educação", "Despesas Liquidadas", 32649948.05),
      linha("Despesas Intraorçamentárias", "Despesas Liquidadas", 18753373.69),
    ] };
    expect(lerDca(bruto)).toEqual({ total: 131688419.93, saude: 28171405.62, educacao: 32649948.05 });
    expect(lerDca({ items: [] })).toBeNull();
    // Até 2016, o total vinha com parênteses (São Sepé, 2014)
    expect(lerDca({ items: [linha("Despesas (Exceto Intraorçamentárias)", "Despesas Liquidadas", 51021921)] }))
      .toEqual({ total: 51021921 });
    expect(() => lerDca(null)).toThrow(ErroFeed);
    expect(urlDca("4319604", 2024)).toBe("/api/siconfi/dca/?an_exercicio=2024&no_anexo=DCA-Anexo%20I-E&id_ente=4319604");
  });
});

describe("inflação e mandatos", () => {
  // IPCA de 1% ao mês em 2023 e 2024: a média de 2024 é 1,01^12 vezes a de 2023
  const serie = [...Array(24)].map((_, i) => [`${2023 + Math.floor(i / 12)}-${String((i % 12) + 1).padStart(2, "0")}`, 1] as [string, number]);
  const medias = ipcaMedioAnual({ serie: [...serie, ["2025-01", 1]] });

  it("corrige pelo IPCA médio do ano, só com anos completos", () => {
    expect([...medias.keys()]).toEqual(["2023", "2024"]);
    expect(anoBase(medias)).toBe("2024");
    expect(emReaisDe(100, "2023", "2024", medias)).toBeCloseTo(100 * 1.01 ** 12, 6);
    expect(emReaisDe(100, "2022", "2024", medias)).toBeNull();
  });

  it("resume cada mandato: população com quebra de método e média da despesa por habitante", () => {
    const estimativas: [string, number][] = [["2019", 23621], ["2020", 23555], ["2021", 23492], ["2024", 21575]];
    const pop = populacaoPorAno(estimativas, 21219);
    const despesas = new Map([["2023", { total: 1_000_000, saude: 200_000 }], ["2024", { total: 1_100_000 }]]);
    const anos = anosMunicipaisComDespesa(["2023", "2024"], pop, despesas, medias, "2024");
    expect(anos[0]!.reais.total).toBeCloseTo(1_000_000 * 1.01 ** 12, 4);
    expect(anos[0]!.porHabitante.saude).toBeCloseTo((200_000 * 1.01 ** 12) / 21219, 6);
    const [m2017, m2021] = resumirMandatos([mandatoDe(2016, null, null, false), mandatoDe(2020, null, null, true)],
                                           estimativas, anos);
    expect(m2017!.populacaoInicio).toEqual(["2019", 23621]);
    expect(m2017!.variacaoPopulacao).toBeCloseTo((23555 / 23621 - 1) * 100, 6);
    expect(m2017!.anosComContas).toBe(0);
    expect(m2021!.quebraPopulacao).toBe("2024");
    expect(m2021!.variacaoPopulacao).toBeNull();
    expect(m2021!.anosComContas).toBe(2);
    expect(m2021!.mediaReal.total).toBeCloseTo((1_000_000 * 1.01 ** 12 + 1_100_000) / 2, 4);
  });
});
