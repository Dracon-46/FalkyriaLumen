import { gzipSync } from "node:zlib";
import { afterEach, describe, expect, it, vi } from "vitest";
import { obterJsonComprimido } from "../comprimido";
import { anosDesde, carregarEmpresa, mesPorExtenso, resolver, urlCnpj } from "../receita";
import { ErroFeed } from "../validacao";

const tabelas = { natureza: { "2038": "Sociedade de Economia Mista" }, situacao: { "02": "Ativa" },
                  porte: { "05": "Demais" }, cnae: { "6422100": "Bancos múltiplos" }, municipio: { "9701": "BRASILIA" },
                  qualificacao: { "22": "Sócio" }, pais: {}, motivo: {} };
const arquivo = { versao: 1, tipo: "cnpj", gerado_em: "x", mes: "2026-10", fonte: "Receita", empresas: {
  "00000000000191": { razao_social: "BANCO DO BRASIL SA", natureza: "2038", porte: "05", situacao: "02",
                      cnae_principal: "6422100", cnaes_secundarios: ["9999999"], municipio: "9701", uf: "DF",
                      socios: [{ tipo: "PJ", nome: "UNIAO FEDERAL", qualificacao: "22", desde: "1966-08-01",
                                 cnpj: "00394460000141" }] } } };

describe("fornecedor na Receita", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("acha o arquivo comprimido pelo prefixo do CNPJ e recusa CNPJ inválido", () => {
    expect(urlCnpj("00000000000191")).toMatch(/\/cnpj\/000\.json\.gz$/);
    expect(() => urlCnpj("123")).toThrow(ErroFeed);
  });

  it("lê o arquivo comprimido e põe os nomes no lugar dos códigos; sem a base ou sem o CNPJ, nulo", async () => {
    const fetch = vi.fn(async (url: string) =>
      url.endsWith("/cnpj/000.json.gz") ? new Response(gzipSync(JSON.stringify(arquivo)))
        : url.endsWith("/cnpj/tabelas.json") ? new Response(JSON.stringify({ versao: 1, tipo: "cnpj-tabelas", tabelas }))
          : new Response("", { status: 404 }));
    vi.stubGlobal("fetch", fetch);
    const lido = await carregarEmpresa("00000000000191");
    expect(lido?.mes).toBe("2026-10");
    expect(lido?.empresa).toMatchObject({
      razao_social: "BANCO DO BRASIL SA", situacao: "Ativa", porte: "Demais", municipio: "BRASILIA",
      natureza: { codigo: "2038", nome: "Sociedade de Economia Mista" },
      cnae_principal: { codigo: "6422100", nome: "Bancos múltiplos" },
      cnaes_secundarios: [{ codigo: "9999999", nome: null }],
    });
    expect(lido?.empresa.socios[0]).toMatchObject({ qualificacao: "Sócio", cnpj: "00394460000141" });
    expect(await carregarEmpresa("00000000000272")).toBeNull();     // mesmo arquivo, CNPJ que não está nele
    expect(await carregarEmpresa("12345678000195")).toBeNull();     // arquivo que não existe
  });

  it("lê também o arquivo que o servidor já entregou descomprimido", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ a: 1 }))));
    expect(await obterJsonComprimido("/x.json.gz")).toEqual({ a: 1 });
  });

  it("monta a empresa com os campos vazios como nulos", () => {
    const e = resolver("12345678000195", { razao_social: "X" }, {});
    expect(e).toMatchObject({ situacao: null, natureza: null, simples: null, socios: [], cnaes_secundarios: [] });
  });

  it("escreve o mês e conta os anos de atividade", () => {
    expect(mesPorExtenso("2026-10")).toBe("outubro de 2026");
    expect(mesPorExtenso(null)).toBe("");
    expect(anosDesde("1966-08-01", new Date(2026, 9, 21))).toBe(60);
    expect(anosDesde("2025-10-22", new Date(2026, 9, 21))).toBe(0);
    expect(anosDesde(null)).toBeNull();
  });
});
