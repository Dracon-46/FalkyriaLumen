import { describe, expect, it } from "vitest";
import {
  buscarEntes,
  cnpj,
  codigoSeguro,
  conferir,
  dataCurta,
  descreverEnte,
  lerEntes,
  mesCurto,
  moeda,
  moedaCompacta,
  tipoDoCodigo,
  topoDoEixo,
  urlsPainel,
  type EnteBusca,
} from "../paineis";
import { ErroFeed } from "../validacao";

const ENTES: EnteBusca[] = [
  { codigo: "35", nome: "São Paulo", uf: "SP", esfera: "E", populacao: 46_000_000 },
  { codigo: "3550308", nome: "São Paulo", uf: "SP", esfera: "M", populacao: 11_900_000 },
  { codigo: "3548708", nome: "São Bernardo do Campo", uf: "SP", esfera: "M", populacao: 810_000 },
  { codigo: "2111300", nome: "São Luís", uf: "MA", esfera: "M", populacao: 1_000_000 },
  { codigo: "3304557", nome: "Rio de Janeiro", uf: "RJ", esfera: "M", populacao: 6_200_000 },
  { codigo: "1", nome: "União", uf: null, esfera: "F", populacao: null },
];

describe("busca de entes", () => {
  it("põe estados antes, quem começa com o termo antes e o maior antes", () => {
    expect(buscarEntes("sao", ENTES).map((e) => e.codigo)).toEqual(["35", "3550308", "2111300", "3548708"]);
    expect(buscarEntes("paulo", ENTES).map((e) => e.codigo)).toEqual(["35", "3550308"]);
    expect(buscarEntes("sp", ENTES).map((e) => e.codigo)).toEqual(["35"]);
    expect(buscarEntes("uniao", ENTES)[0]?.codigo).toBe("1");
    expect(buscarEntes("  ", ENTES)).toEqual([]);
    expect(buscarEntes("s", ENTES, 2)).toHaveLength(2);
  });

  it("lê o entes.json pelas colunas e ignora formato desconhecido", () => {
    const bruto = { versao: 1, colunas: ["codigo", "nome", "uf", "esfera", "populacao"], entes: [["43", "Rio Grande do Sul", "RS", "E", 11]] };
    expect(lerEntes(bruto)).toEqual([{ codigo: "43", nome: "Rio Grande do Sul", uf: "RS", esfera: "E", populacao: 11 }]);
    expect(lerEntes({ versao: 2 })).toEqual([]);
    expect(lerEntes(null)).toEqual([]);
  });

  it("descreve e classifica pelo código", () => {
    expect(["1", "53", "35", "3550308", "x"].map(tipoDoCodigo)).toEqual(["uniao", "df", "estado", "municipio", null]);
    expect(descreverEnte({ codigo: "3550308", uf: "SP" })).toBe("Município · SP");
    expect(descreverEnte({ codigo: "3550308", uf: null })).toBe("Município");
    expect(descreverEnte({ codigo: "35", uf: "SP" })).toBe("Estado");
    expect(descreverEnte({ codigo: "53", uf: "DF" })).toBe("Distrito Federal");
    expect(descreverEnte({ codigo: "1", uf: null })).toBe("União");
  });
});

describe("arquivos dos painéis", () => {
  it("só monta caminhos com código e UF válidos", () => {
    expect(urlsPainel.contratacoesEnte("3550308")).toMatch(/\/contratacoes\/ente\/3550308\.json$/);
    expect(urlsPainel.conformidadeUf("SP")).toMatch(/\/conformidade\/uf\/SP\.json$/);
    expect(() => codigoSeguro("../x")).toThrow(ErroFeed);
    expect(() => urlsPainel.conformidadeUf("sp/../")).toThrow(ErroFeed);
    expect(urlsPainel.indice()).toMatch(/\/indice\.json$/);
    expect(urlsPainel.entes()).toMatch(/\/entes\.json$/);
  });

  it("confere versão e tipo", () => {
    expect(conferir({ versao: 1, tipo: "contratacoes-ente" }, "contratacoes-ente", "u")).toBeTruthy();
    expect(() => conferir({ versao: 2, tipo: "contratacoes-ente" }, "contratacoes-ente", "u")).toThrow(/versão/);
    expect(() => conferir({ versao: 1, tipo: "x" }, "contratacoes-ente", "u")).toThrow(/tipo/);
    expect(() => conferir("x", "contratacoes-ente", "u")).toThrow(/inesperado/);
  });
});

describe("formato", () => {
  it("formata reais, meses, datas e CNPJ", () => {
    expect(moeda(1234.5).replace(/\s/g, " ")).toBe("R$ 1.234,50");
    expect(moeda(null)).toBe("—");
    expect(moedaCompacta(1_500_000)).toMatch(/^R\$ 1,5\s?mi/);
    expect(moedaCompacta(undefined)).toBe("—");
    expect(mesCurto("2026-03")).toBe("mar/2026");
    expect(mesCurto("2026-13")).toBe("2026-13");
    expect(dataCurta("2026-10-13")).toBe("13/10/2026");
    expect(dataCurta("2026-04-30T02:00:00+00:00")).toBe("29/04/2026");
    expect(dataCurta("lixo")).toBe("—");
    expect(dataCurta(null)).toBe("—");
    expect(cnpj("07854402000100")).toBe("07.854.402/0001-00");
    expect(cnpj("123")).toBe("123");
    expect(cnpj(null)).toBe("—");
  });

  it("arredonda o topo do eixo", () => {
    expect([0, 3, 10, 11, 180, 4_200_000].map(topoDoEixo)).toEqual([1, 5, 10, 20, 200, 5_000_000]);
    expect(topoDoEixo(7)).toBe(10);
  });
});
