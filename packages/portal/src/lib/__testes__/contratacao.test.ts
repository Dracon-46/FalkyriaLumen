import { afterEach, describe, expect, it, vi } from "vitest";
import {
  carregarContrato, carregarItens, carregarProcesso, carregarTermos, lerContrato, lerItens, lerProcesso,
  lerResultados, lerTermos, parte,
} from "../contratacao";

const COMPRA = "74118514000182-1-000028/2026";
const CONTRATO = "49269244000163-2-003049/2025";

afterEach(() => vi.unstubAllGlobals());

describe("contratação no PNCP", () => {
  it("pessoa física e estrangeira aparecem sem nome nem documento", () => {
    expect(parte("PJ", "12345678000190", "EMPRESA FICTÍCIA LTDA")).toEqual(
      { pj: true, cnpj: "12345678000190", nome: "EMPRESA FICTÍCIA LTDA" });
    expect(parte("PF", "***123456**", "PESSOA FICTÍCIA")).toEqual({ pj: false, cnpj: null, nome: null });
    expect(parte("PE", "X1", "ESTRANGEIRA")).toEqual({ pj: false, cnpj: null, nome: null });
  });

  it("lê o processo, com o órgão da chave quando a resposta não traz", () => {
    const p = lerProcesso(COMPRA, {
      objetoCompra: " Serviço de limpeza ", modalidadeNome: "Dispensa", amparoLegal: { nome: "Art. 75, II", descricao: "" },
      valorTotalEstimado: 1000.5, valorTotalHomologado: "x", srp: false, unidadeOrgao: { municipioNome: "Fictícia", ufSigla: "SP" },
    });
    expect(p.objeto).toBe("Serviço de limpeza");
    expect(p.amparoLegal).toEqual({ nome: "Art. 75, II", descricao: null });
    expect(p.valorEstimado).toBe(1000.5);
    expect(p.valorHomologado).toBeNull();
    expect(p.srp).toBe(false);
    expect(p.orgao).toEqual({ cnpj: "74118514000182", nome: null });
    expect(p.unidade).toEqual({ nome: null, municipio: "Fictícia", uf: "SP", ibge: null });
  });

  it("lê itens, resultados e termos, e ignora o que não é lista", () => {
    expect(lerItens([{ numeroItem: 1, descricao: "Limpeza", materialOuServicoNome: "Serviço", temResultado: true }, null])).toEqual([
      { numero: 1, descricao: "Limpeza", tipo: "Serviço", quantidade: null, unidade: null, valorUnitario: null,
        valorTotal: null, situacao: null, temResultado: true },
      { numero: 0, descricao: "—", tipo: null, quantidade: null, unidade: null, valorUnitario: null, valorTotal: null,
        situacao: null, temResultado: false },
    ]);
    const r = lerResultados([{ tipoPessoa: "PF", niFornecedor: "***1**", nomeRazaoSocialFornecedor: "X", valorTotalHomologado: 10 }]);
    expect(r[0]!.fornecedor).toEqual({ pj: false, cnpj: null, nome: null });
    expect(r[0]!.valorTotal).toBe(10);
    expect(lerTermos([{ tipoTermoContratoNome: "Termo Aditivo", valorAcrescido: 50, prazoAditadoDias: 90 }])[0]).toMatchObject(
      { tipo: "Termo Aditivo", valorAcrescido: 50, prazoAditado: 90 });
    expect(lerItens(null)).toEqual([]);
    expect(lerResultados({})).toEqual([]);
    expect(lerTermos("x")).toEqual([]);
  });

  it("lê o contrato e só liga ao processo de origem com chave válida", () => {
    const c = lerContrato(CONTRATO, {
      objetoContrato: "Limpeza", tipoContrato: { nome: "Contrato" }, valorGlobal: 1200, tipoPessoa: "PJ",
      niFornecedor: "12345678000190", nomeRazaoSocialFornecedor: "EMPRESA FICTÍCIA LTDA",
      numeroControlePncpCompra: COMPRA, orgaoEntidade: { cnpj: "49269244000163", razaoSocial: "Órgão Fictício" },
    });
    expect(c.tipo).toBe("Contrato");
    expect(c.fornecedor.nome).toBe("EMPRESA FICTÍCIA LTDA");
    expect(c.chaveProcesso).toBe(COMPRA);
    expect(c.orgao.nome).toBe("Órgão Fictício");
    expect(lerContrato(CONTRATO, { numeroControlePncpCompra: "lixo" }).chaveProcesso).toBeNull();
  });

  it("pede à API certa, trata 204 como vazio e não mistura compra com contrato", async () => {
    const urls: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      urls.push(url);
      if (url.includes("/termos")) return new Response(null, { status: 204 });
      if (url.includes("/itens")) {
        const pagina = Number(new URL(url).searchParams.get("pagina"));
        const n = pagina === 1 ? 50 : 3;
        return Response.json(Array.from({ length: n }, (_, i) => ({ numeroItem: (pagina - 1) * 50 + i + 1, descricao: "x" })));
      }
      return Response.json({ objetoCompra: "Limpeza", objetoContrato: "Limpeza" });
    }));
    expect((await carregarProcesso(COMPRA))?.objeto).toBe("Limpeza");
    expect(urls[0]).toBe("https://pncp.gov.br/api/consulta/v1/orgaos/74118514000182/compras/2026/28");
    expect(await carregarItens(COMPRA)).toHaveLength(53);
    expect(urls.filter((u) => u.includes("/itens"))).toHaveLength(2);
    expect(await carregarTermos(CONTRATO)).toEqual([]);
    expect((await carregarContrato(CONTRATO))?.objeto).toBe("Limpeza");
    expect(urls.at(-1)).toBe("https://pncp.gov.br/api/pncp/v1/orgaos/49269244000163/contratos/2025/3049");
    expect(await carregarProcesso(CONTRATO)).toBeNull();
    expect(await carregarContrato(COMPRA)).toBeNull();
    expect(await carregarItens("lixo")).toEqual([]);
  });

  it("erro do PNCP vira erro de feed", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("x", { status: 500 })));
    await expect(carregarProcesso(COMPRA)).rejects.toThrow("PNCP respondeu 500");
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("rede"); }));
    await expect(carregarContrato(CONTRATO)).rejects.toThrow("sem resposta do PNCP");
  });
});
