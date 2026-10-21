import { afterEach, describe, expect, it, vi } from "vitest";
import { ligacoesDoEnte } from "@/componentes/Ligacoes";
import { lerPorFuncao, lerPorNatureza, lerReceitas, somarAberturas, variacao, type Abertura } from "../gastos";
import { obterDoSiconfi, urlDca, urlDcaNaFonte } from "../governos";
import { ErroFeed } from "../validacao";

const linha = (cod_conta: string, conta: string, valor: number, coluna = "Despesas Liquidadas") =>
  ({ coluna, cod_conta, conta, valor });

describe("abertura por área (DCA, Anexo I-E)", () => {
  it("lê o total, as funções e as subfunções da despesa liquidada", () => {
    const a = lerPorFuncao({ items: [
      linha("TotalDespesas", "Despesas Exceto Intraorçamentárias", 131688419.93),
      linha("TotalDespesas", "Despesas Exceto Intraorçamentárias", 135933241.22, "Despesas Empenhadas"),
      linha("TotalDespesas", "10 - Saúde", 28171405.62),
      linha("TotalDespesas", "10.301 - Atenção Básica", 11954931.93),
      linha("TotalDespesas", "FU10 - Demais Subfunções", 1000),
      linha("TotalDespesas", "Despesas Intraorçamentárias", 18753373.69),
    ] })!;
    expect(a.total).toBe(131688419.93);
    expect(a.valores).toEqual({ "10": 28171405.62, "10.301": 11954931.93, FU10: 1000 });
    expect(a.nomes["10.301"]).toBe("Atenção Básica");
    expect(a.pai).toEqual({ "10.301": "10", FU10: "10" });
    // Até 2016, o total vinha entre parênteses
    expect(lerPorFuncao({ items: [linha("T", "Despesas (Exceto Intraorçamentárias)", 5)] })!.total).toBe(5);
    expect(lerPorFuncao({ items: [] })).toBeNull();
    expect(() => lerPorFuncao(null)).toThrow(ErroFeed);
  });
});

describe("abertura por tipo de gasto (DCA, Anexo I-D)", () => {
  // Linhas reais de São Sepé, 2024: pessoal (com uma modalidade intraorçamentária) e investimentos
  const bruto = { items: [
    linha("DO3.0.00.00.00.00", "3.0.00.00.00 - Despesas Correntes", 149004701.16),
    linha("DO3.1.00.00.00.00", "3.1.00.00.00 - Pessoal e Encargos Sociais", 83496811.89),
    linha("DO3.1.71.00.00.00", "3.1.71.00.00 - Transferências a Consórcios Públicos mediante contrato de rateio", 25892.4),
    linha("DO3.1.90.00.00.00", "3.1.90.00.00 - Aplicações Diretas", 78795083.54),
    linha("DO3.1.90.01.00.00", "3.1.90.01.00 - Aposentadorias do RPPS, Reserva Remunerada e Reformas dos Militares", 21863928.27),
    linha("DO3.1.90.03.00.00", "3.1.90.03.00 - Pensões do RPPS e do Militar", 3263787.06),
    linha("DO3.1.90.04.00.00", "3.1.90.04.00 - Contratação por Tempo Determinado", 2642598.22),
    linha("DO3.1.90.11.00.00", "3.1.90.11.00 - Vencimentos e Vantagens Fixas - Pessoal Civil", 45386238.85),
    linha("DO3.1.90.13.00.00", "3.1.90.13.00 - Obrigações Patronais", 1129700.65),
    linha("DO3.1.90.13.01.00", "3.1.90.13.01 - FGTS", 111162.0),
    linha("DO3.1.90.16.00.00", "3.1.90.16.00 - Outras Despesas Variáveis - Pessoal Civil", 3856471.87),
    linha("DO3.1.90.91.00.00", "3.1.90.91.00 - Sentenças Judiciais", 652358.62),
    linha("DI3.1.91.00.00.00", "3.1.91.00.00 - Aplicação Direta Decorrente de Operação entre Órgãos…", 4675835.95),
    linha("DI3.1.91.13.00.00", "3.1.91.13.00 - Contribuições Patronais", 4675835.95),
    linha("DO4.0.00.00.00.00", "4.0.00.00.00 - Despesas de Capital", 1437092.46),
    linha("DO4.4.00.00.00.00", "4.4.00.00.00 - Investimentos", 1437092.46),
    linha("DO4.4.20.00.00.00", "4.4.20.00.00 - Transferências à União", 60221.96),
    linha("DO4.4.30.00.00.00", "4.4.30.00.00 - Transferências a Estados e ao Distrito Federal", 74924.55),
    linha("DO4.4.71.00.00.00", "4.4.71.00.00 - Transferências a Consórcios Públicos mediante contrato de rateio", 178.88),
    linha("DO4.4.90.00.00.00", "4.4.90.00.00 - Aplicações Diretas", 1301767.07),
    linha("DO4.4.90.51.00.00", "4.4.90.51.00 - Obras e Instalações", 596207.43),
    linha("DO4.4.90.52.00.00", "4.4.90.52.00 - Equipamentos e Material Permanente", 535559.64),
    linha("DO4.4.90.61.00.00", "4.4.90.61.00 - Aquisição de Imóveis", 170000),
  ] };

  it("soma as modalidades sem as intraorçamentárias e abre os elementos", () => {
    const a = lerPorNatureza(bruto)!;
    expect(a.total).toBeCloseTo(78820975.94 + 1437092.46, 2);
    expect(a.valores["3.1"]).toBeCloseTo(78820975.94, 2);           // sem os 4,7 milhões intraorçamentários
    expect(a.nomes["3.1"]).toBe("Pessoal e encargos sociais");
    expect(a.valores["3.1|11"]).toBe(45386238.85);
    expect(a.valores["3.1|13"]).toBe(1129700.65);                   // só a modalidade 90, não a 91
    expect(a.nomes["3.1|m71"]).toBe("Transferências a Consórcios Públicos mediante contrato de rateio");
    expect(a.valores["3.1|demais"]).toBeUndefined();               // os elementos cobrem a modalidade 90 inteira
    expect(a.valores["4.4|51"]).toBe(596207.43);
    expect(a.nomes["4.4|51"]).toBe("Obras e Instalações");
    expect(a.valores["4.4|m20"]).toBe(60221.96);
    expect(a.valores["4.4|demais"]).toBeUndefined();
    expect(a.pai["4.4|52"]).toBe("4.4");
    expect(lerPorNatureza({ items: [] })).toBeNull();
  });

  it("põe em Demais o que os elementos da modalidade não cobrem", () => {
    const a = lerPorNatureza({ items: [
      linha("DO3.3.90.00.00.00", "3.3.90.00.00 - Aplicações Diretas", 100),
      linha("DO3.3.90.30.00.00", "3.3.90.30.00 - Material de Consumo", 60),
    ] })!;
    expect(a.valores).toEqual({ "3.3": 100, "3.3|30": 60, "3.3|demais": 40 });
    expect(a.nomes["3.3"]).toBe("Outras despesas correntes (custeio)");
  });
});

describe("somas de um mandato", () => {
  const ano = (total: number, saude: number, atencao: number): Abertura =>
    ({ total, valores: { "10": saude, "10.301": atencao, "12": total - saude }, nomes: { "10": "Saúde",
       "10.301": "Atenção Básica", "12": "Educação" }, pai: { "10.301": "10" } });
  const porAno = new Map<string, Abertura | null>([["2021", ano(100, 40, 10)], ["2022", ano(200, 50, 20)],
                                                   ["2023", null], ["2024", ano(300, 60, 30)]]);

  it("soma os anos com contas, converte cada um e ordena da maior para a menor", () => {
    // Converte dobrando 2021 e deixa 2024 de fora (sem conversão)
    const s = somarAberturas(["2021", "2022", "2023", "2024"], porAno,
                             (v, a) => (a === "2024" ? null : a === "2021" ? v * 2 : v));
    expect(s.anos).toEqual(["2021", "2022"]);
    expect(s.total).toBe(400);
    expect(s.linhas.map((l) => [l.codigo, l.total])).toEqual([["12", 270], ["10", 130]]);
    expect(s.linhas[1]!.porAno).toEqual({ "2021": 80, "2022": 50 });
    expect(s.linhas[1]!.filhos.map((f) => [f.nome, f.total])).toEqual([["Atenção Básica", 40]]);
    expect(variacao(150, 100)).toBe(50);
    expect(variacao(1, 0)).toBeNull();
  });
});

describe("ligações e links da fonte", () => {
  it("liga o ente às outras abas, sem a aba aberta", () => {
    const mun = ligacoesDoEnte("4319604", "governos").map((l) => l.href);
    expect(mun).toEqual(["/contratacoes/?ente=4319604", "/conformidade/?ente=4319604", "/eleicoes/?a=mu-4319604"]);
    const uf = ligacoesDoEnte("43", "conformidade").map((l) => l.href);
    expect(uf).toEqual(["/contratacoes/?ente=43", "/eleicoes/?a=uf-rs"]);
    expect(ligacoesDoEnte("53", "contratacoes").map((l) => l.href)).toContain("/eleicoes/?a=uf-df");
  });

  it("monta a consulta da DCA pelo portal e direto no SICONFI", () => {
    expect(urlDca("4319604", 2024, "I-D")).toBe(
      "/api/siconfi/dca/?an_exercicio=2024&no_anexo=DCA-Anexo%20I-D&id_ente=4319604");
    expect(urlDcaNaFonte("4319604", 2024)).toBe(
      "https://apidatalake.tesouro.gov.br/ords/siconfi/tt/dca?an_exercicio=2024&no_anexo=DCA-Anexo%20I-E&id_ente=4319604");
  });
});

describe("consulta ao SICONFI", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("tenta de novo quando a consulta falha, e desiste depois das esperas", async () => {
    const respostas = [new Response("", { status: 429 }), new Response(JSON.stringify({ items: [] }))];
    const fetch = vi.fn(async () => respostas.shift() ?? new Response("", { status: 503 }));
    vi.stubGlobal("fetch", fetch);
    await expect(obterDoSiconfi("/api/siconfi/dca/?x=1", undefined, [0])).resolves.toEqual({ items: [] });
    expect(fetch).toHaveBeenCalledTimes(2);
    await expect(obterDoSiconfi("/api/siconfi/dca/?x=2", undefined, [0])).rejects.toThrow(ErroFeed);
    expect(fetch).toHaveBeenCalledTimes(4);
  });
});

describe("receitas do município (DCA, Anexo I-C)", () => {
  const r = (cod_conta: string, valor: number, coluna = "Receitas Brutas Realizadas") => ({ coluna, cod_conta, conta: cod_conta, valor });

  it("agrupa pelo ementário antigo (até 2017): São Sepé, 2015", () => {
    const a = lerReceitas({ items: [
      r("TotalReceitas", 66763667), r("RO1.0.0.0.00.00.00", 59515398), r("RO1.1.0.0.00.00.00", 5432597),
      r("RO1.2.0.0.00.00.00", 2612530), r("RO1.7.0.0.00.00.00", 46527098), r("RO1.7.2.1.00.00.00", 21978191),
      r("RO1.7.2.2.00.00.00", 16911955), r("RO1.7.2.4.00.00.00", 7505122), r("RO2.0.0.0.00.00.00", 1078734),
      r("RO1.0.0.0.00.00.00", 6478639, "Deduções - FUNDEB"), r("RO1.0.0.0.00.00.00", 744094, "Outras Deduções da Receita"),
    ] })!;
    expect(a.total).toBe(59515398 + 1078734);                      // sem as intraorçamentárias do "Total Receitas"
    expect(a.valores).toMatchObject({ uniao: 21978191, estado: 16911955, fundeb: 7505122, impostos: 5432597 });
    expect(Object.values(a.valores).reduce((s, v) => s + v, 0)).toBe(a.total);
    expect(a.deducoes).toBe(6478639 + 744094);
  });

  it("agrupa pelo ementário novo (de 2018): São Sepé, 2024", () => {
    const a = lerReceitas({ items: [
      r("ReceitasExcetoIntraOrcamentarias", 151236848), r("RO1.0.0.0.00.0.0", 151108843), r("RO1.1.0.0.00.0.0", 19118926),
      r("RO1.2.0.0.00.0.0", 10594706), r("RO1.7.0.0.00.0.0", 111242471), r("RO1.7.1.0.00.0.0", 51619307),
      r("RO1.7.2.0.00.0.0", 40705721), r("RO1.7.5.0.00.0.0", 18872320), r("RO2.0.0.0.00.0.0", 128005),
    ] })!;
    expect(a.total).toBe(151236848);
    expect(a.valores).toMatchObject({ uniao: 51619307, estado: 40705721, fundeb: 18872320, outras_transferencias: 45123,
                                      outras_correntes: 151108843 - 19118926 - 10594706 - 111242471, capital: 128005 });
    expect(a.nomes.uniao).toMatch(/^Transferências da União/);
    expect(lerReceitas({ items: [] })).toBeNull();
  });
});
