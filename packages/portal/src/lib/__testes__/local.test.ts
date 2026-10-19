import { describe, expect, it } from "vitest";
import { lerArquivos, lerChave, urlArquivos } from "../documentos";
import { type CompanhiaCvm, estataisDoEnte } from "../estatais";
import { codigoDaUf, codigoNaUrl, hrefDaArea } from "../local";
import { arquivoTransparencia } from "../transparencia";

describe("documentos do PNCP", () => {
  it("lê a chave dos painéis e monta o endereço da lista de arquivos", () => {
    expect(lerChave("74118514000182-1-000028/2026")).toEqual({ tipo: "compra", cnpj: "74118514000182", ano: 2026, sequencial: 28 });
    expect(lerChave("49269244000163-2-003049/2025")?.tipo).toBe("contrato");
    expect(lerChave("qualquer coisa")).toBeNull();
    expect(urlArquivos(lerChave("74118514000182-1-000028/2026")!)).toBe(
      "https://pncp.gov.br/api/pncp/v1/orgaos/74118514000182/compras/2026/28/arquivos");
    expect(urlArquivos(lerChave("49269244000163-2-003049/2025")!)).toBe(
      "https://pncp.gov.br/api/pncp/v1/orgaos/49269244000163/contratos/2025/3049/arquivos");
  });

  it("guarda só documentos ativos com endereço do PNCP (resposta real recortada)", () => {
    const docs = lerArquivos([
      { url: "https://pncp.gov.br/pncp-api/v1/orgaos/74118514000182/compras/2026/28/arquivos/1", statusAtivo: true,
        titulo: "AVISO_DE_DISPENSA_ELETRONICA_00_2026_Flaldario.pdf", tipoDocumentoNome: "Aviso de Contratação Direta",
        dataPublicacaoPncp: "2026-10-14T09:25:55" },
      { uri: "https://pncp.gov.br/pncp-api/v1/orgaos/49269244000163/contratos/2025/3049/arquivos/1", titulo: "CONTRATO.pdf",
        tipoDocumentoNome: "Contrato" },
      { url: "https://pncp.gov.br/x/2", statusAtivo: false, titulo: "removido.pdf" },
      { url: "https://outro.site/arquivo.pdf", titulo: "fora" },
      null,
    ]);
    expect(docs.map((d) => d.titulo)).toEqual(["AVISO_DE_DISPENSA_ELETRONICA_00_2026_Flaldario.pdf", "CONTRATO.pdf"]);
    expect(docs[0]!.publicado_em).toBe("2026-10-14T09:25:55");
    expect(lerArquivos({ erro: 1 })).toEqual([]);
  });
});

describe("filtro de local", () => {
  const sp = { codigo: "3550308", nome: "São Paulo", uf: "SP" };
  const estado = { codigo: "35", nome: "São Paulo", uf: "SP" };
  const uniao = { codigo: "1", nome: "União", uf: null };

  it("cada aba abre no local escolhido", () => {
    expect(hrefDaArea("eleicoes", sp)).toBe("/eleicoes/?a=mu-3550308");
    expect(hrefDaArea("eleicoes", estado, new URLSearchParams("e=2022-1t-geral&c=governador&a=mu-1"))).toBe(
      "/eleicoes/?e=2022-1t-geral&c=governador&a=uf-sp");
    expect(hrefDaArea("eleicoes", uniao)).toBe("/eleicoes/");
    expect(hrefDaArea("contratacoes", sp)).toBe("/contratacoes/?ente=3550308");
    expect(hrefDaArea("contratacoes", uniao)).toBe("/contratacoes/?ente=1");
    expect(hrefDaArea("conformidade", estado)).toBe("/conformidade/?ente=35");
    expect(hrefDaArea("conformidade", uniao)).toBe("/conformidade/");
    expect(hrefDaArea("estatais", sp)).toBe("/economia/estatais/?ente=3550308");
    expect(hrefDaArea("economia", sp)).toBe("/economia/");
    expect(hrefDaArea("contratacoes", null)).toBe("/contratacoes/");
    expect(hrefDaArea("contratacoes", { codigo: "x", nome: "?", uf: null })).toBe("/contratacoes/");
  });

  it("a aba aberta num município ou estado vira o local", () => {
    const u = (q: string) => new URLSearchParams(q);
    expect(codigoNaUrl("/contratacoes/", u("ente=3550308"))).toBe("3550308");
    expect(codigoNaUrl("/conformidade/", u("ente=35"))).toBe("35");
    expect(codigoNaUrl("/conformidade/", u("uf=MG"))).toBe("31");
    expect(codigoNaUrl("/economia/estatais/", u("ente=1"))).toBe("1");
    expect(codigoNaUrl("/eleicoes/", u("e=2024-1t-municipal&a=mu-3550308"))).toBe("3550308");
    expect(codigoNaUrl("/eleicoes/", u("a=uf-rj"))).toBe("33");
    expect(codigoNaUrl("/eleicoes/", u("a=mu-ap-06130"))).toBeNull();
    expect(codigoNaUrl("/eleicoes/", u(""))).toBeNull();
    expect(codigoNaUrl("/economia/", u("ente=35"))).toBeNull();
    expect(codigoNaUrl("/contratacoes/", u("ente=../x"))).toBeNull();
    expect(codigoDaUf("sp")).toBe("35");
    expect(codigoDaUf("zz")).toBeNull();
  });

  it("arquivo da transparência do ente", () => {
    expect(arquivoTransparencia("3550308")).toBe("transparencia/uf-sp.json");
    expect(arquivoTransparencia("1")).toBe("transparencia/uniao.json");
    expect(arquivoTransparencia("99")).toBeNull();
  });

  it("estatais pela esfera do controlador e pela sede", () => {
    const c = (nome: string, esfera: string | null, uf: string, municipio: string) => ({
      cnpj: nome, nome, uf, municipio, controle: { classe: esfera ? "publico_direto" : "privado", esfera },
    }) as unknown as CompanhiaCvm;
    const feed = {
      companhias: [c("PETROBRAS", "federal", "RJ", "RIO DE JANEIRO"), c("METRÔ", "estadual", "SP", "SÃO PAULO"),
                   c("CEMIG", "estadual", "MG", "BELO HORIZONTE"), c("SPTURIS", "municipal", "SP", "SÃO PAULO"),
                   c("CEB", "distrital", "DF", "BRASÍLIA"), c("SABESP", null, "SP", "SÃO PAULO")],
    };
    const nomes = (l: CompanhiaCvm[]) => l.map((x) => x.nome);
    expect(nomes(estataisDoEnte(feed, "União", null, "uniao"))).toEqual(["PETROBRAS"]);
    expect(nomes(estataisDoEnte(feed, "São Paulo", "SP", "estado"))).toEqual(["METRÔ"]);
    expect(nomes(estataisDoEnte(feed, "São Paulo", "SP", "municipio"))).toEqual(["SPTURIS"]);
    expect(estataisDoEnte(feed, "Campinas", "SP", "municipio")).toEqual([]);
    expect(nomes(estataisDoEnte(feed, "Distrito Federal", "DF", "df"))).toEqual(["CEB"]);
    expect(estataisDoEnte(feed, "x", null, null)).toEqual([]);
  });
});
