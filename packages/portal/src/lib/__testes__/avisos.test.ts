// Avisos (ADR-047): o arquivo de cada local, o recorte do estado com e sem os municípios, e os links do aviso.
import { afterEach, describe, expect, it, vi } from "vitest";
import { arquivoDeAvisos, type Aviso, carregarAvisosDoLocal, lerTipos, urlContestar, urlDaContratacao } from "../avisos";
import { codigoNaUrl, hrefDaArea } from "../local";
import { BASE_PAINEL } from "../paineis";

function aviso(id: string, codigo: string | null, tipo: Aviso["tipo"] = "lrf_atrasos"): Aviso {
  return {
    id, tipo, rotulo: "x", data: "2026-03-10", ente: { codigo, nome: "Ente fictício", uf: "SP", tipo: null }, orgao: null,
    titulo: "Título", detalhe: [], observar: "", fonte: { nome: "SICONFI", link: null }, chave: null, valor: null,
    contestacao: null,
  };
}

afterEach(() => vi.unstubAllGlobals());

describe("avisos", () => {
  it("cada local lê o arquivo da UF dele, ou o da União", () => {
    expect(arquivoDeAvisos("3550308")).toBe(`${BASE_PAINEL}/avisos/uf-sp.json`);
    expect(arquivoDeAvisos("35")).toBe(`${BASE_PAINEL}/avisos/uf-sp.json`);
    expect(arquivoDeAvisos("1")).toBe(`${BASE_PAINEL}/avisos/uniao.json`);
    expect(arquivoDeAvisos("99")).toBeNull();
    expect(arquivoDeAvisos("355030")).toBeNull();
  });

  it("o estado mostra os dele e, a pedido, os dos municípios; o município, só os dele", async () => {
    const arquivo = { versao: 1, tipo: "avisos", gerado_em: "G", uf: "SP",
                      avisos: [aviso("a", "35"), aviso("b", "3550308"), aviso("c", null), aviso("d", "3509502")] };
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(arquivo), { status: 200 })));
    expect((await carregarAvisosDoLocal("35", false))!.map((a) => a.id)).toEqual(["a"]);
    expect((await carregarAvisosDoLocal("35", true))!.map((a) => a.id)).toEqual(["a", "b", "c", "d"]);
    expect((await carregarAvisosDoLocal("3550308", true))!.map((a) => a.id)).toEqual(["b"]);
    vi.stubGlobal("fetch", vi.fn(async () => new Response("", { status: 404 })));
    expect(await carregarAvisosDoLocal("35", false)).toEqual([]);
    expect(await carregarAvisosDoLocal("abc", false)).toBeNull();
  });

  it("contestar abre o formulário com o código, e a contratação abre no modal do órgão", () => {
    const u = new URL(urlContestar({ id: "3f2a9c1b7d04", titulo: "Contrato com empresa sancionada" }));
    expect(u.pathname).toBe("/Dracon-46/FalkyriaLumen/issues/new");
    expect(u.searchParams.get("template")).toBe("contestacao.yml");
    expect(u.searchParams.get("title")).toBe("[contestação] 3f2a9c1b7d04");
    expect(u.searchParams.get("aviso")).toBe("3f2a9c1b7d04");
    expect(urlDaContratacao({ chave: "11111111000111-2-000001/2026" })).toBe(
      "/contratacoes/?orgao=11111111000111&pub=11111111000111-2-000001%2F2026");
    expect(urlDaContratacao({ chave: null })).toBeNull();
    expect(urlDaContratacao({ chave: "outra coisa" })).toBeNull();
  });

  it("os tipos da URL e a aba no filtro de local", () => {
    expect(lerTipos("lrf_atrasos,inventado,valor_a_conferir")).toEqual(["lrf_atrasos", "valor_a_conferir"]);
    expect(lerTipos(null)).toEqual([]);
    expect(hrefDaArea("avisos", { codigo: "3550308", nome: "São Paulo", uf: "SP" })).toBe("/avisos/?ente=3550308");
    expect(hrefDaArea("avisos", { codigo: "1", nome: "União", uf: null })).toBe("/avisos/?ente=1");
    expect(hrefDaArea("avisos", null)).toBe("/avisos/");
    expect(codigoNaUrl("/avisos/", new URLSearchParams("ente=35"))).toBe("35");
  });
});
