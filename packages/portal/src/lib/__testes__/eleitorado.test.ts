// Eleitorado (ADR-055): linhas por característica com o comparecimento, lugares abaixo, seções e a leitura.
import { gzipSync } from "node:zlib";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  carregarEleitorado,
  grupoDoMunicipio,
  linhasDaCaracteristica,
  lugaresAbaixo,
  pct,
  secoesDoMunicipio,
  turnoAMostrar,
  urlEleitorado,
} from "../eleitorado";
import { BASE_PAINEL } from "../paineis";
import type { ArquivoEleitorado, LugarEleitorado } from "../tipos";
import { validarEleitorado } from "../validacao";

const lugar: LugarEleitorado = {
  chave: "3507209", nome: "Borá", eleitores: 100, biometria: 90,
  genero: [["Masculino", 48], ["Feminino", 52]],
  faixa_etaria: [["16 anos", 10], ["18 anos", 90]],
  escolaridade: [["Superior completo", 100]],
  estado_civil: [["Solteiro", 60], ["Casado", 40]],
  turnos: {
    "1": { aptos: 100, comparecimento: 80, abstencao: 20, genero: [["Masculino", 48, 36], ["Feminino", 52, 44]],
      faixa_etaria: [["16 anos", 10, 5], ["18 anos", 90, 75]], escolaridade: [["Superior completo", 100, 80]],
      estado_civil: [["Solteiro", 60, 45], ["Casado", 40, 35], ["Viúvo", 0, 0]] },
  },
};

function arquivo(nivel: ArquivoEleitorado["nivel"], extra: Partial<ArquivoEleitorado> = {}): ArquivoEleitorado {
  return { versao: 1, tipo: "eleitorado", ano: 2026, nivel, origem: {}, lugar, ...extra };
}

describe("eleitorado", () => {
  it("o turno da eleição aberta, se publicado; senão o mais recente", () => {
    expect(turnoAMostrar({ "1": 0, "2": 0 }, 1)).toBe("1");
    expect(turnoAMostrar({ "1": 0 }, 2)).toBe("1");
    expect(turnoAMostrar({}, 1)).toBeNull();
    expect(pct(1, 0)).toBeNull();
  });

  it("cada categoria com a parte do eleitorado e o comparecimento no turno", () => {
    const linhas = linhasDaCaracteristica(lugar, "faixa_etaria", lugar.turnos["1"]!);
    expect(linhas.map((l) => [l.rotulo, l.pctEleitorado, l.pctComparecimento])).toEqual([
      ["16 anos", 10, 50], ["18 anos", 90, (75 / 90) * 100]]);
    // Categoria só no turno entra com o cadastro vazio; sem turno, só o cadastro
    expect(linhasDaCaracteristica(lugar, "estado_civil", lugar.turnos["1"]!).at(-1)).toMatchObject(
      { rotulo: "Viúvo", eleitores: 0, pctComparecimento: null });
    expect(linhasDaCaracteristica(lugar, "genero", null)[0]).toMatchObject({ aptos: null, pctComparecimento: null });
  });

  it("os lugares abaixo abrem a UF ou o município; as zonas abrem no próprio município", () => {
    const br = arquivo("br", { partes: { sp: { nome: "São Paulo", eleitores: 10, biometria: 5, turnos: { "1": [10, 8] } },
      ac: { nome: "Acre", eleitores: 4, biometria: 4, turnos: {} } } });
    expect(lugaresAbaixo(br, "1").map((l) => [l.nome, l.abrangencia, l.pctComparecimento])).toEqual([
      ["Acre", "uf-ac", null], ["São Paulo", "uf-sp", 80]]);
    const uf = arquivo("uf", { partes: { "3507209": { nome: "Borá", eleitores: 1, biometria: 1, turnos: {} } } });
    expect(lugaresAbaixo(uf, null)[0]!.abrangencia).toBe("mu-3507209");
    const mu = arquivo("municipio", { zonas: [{ ...lugar, zona: "12" }] });
    expect(lugaresAbaixo(mu, "1")[0]).toMatchObject({ nome: "Zona 12", abrangencia: null, pctComparecimento: 80 });
  });

  it("as seções da zona, com o nome do local, filtradas sem acento", () => {
    const mu = arquivo("municipio", {
      secoes: [["12", 1, "1015", 300], ["12", 2, "1023", 250], ["13", 5, "1015", 10]],
      locais: { "12-1015": "ESCOLA SÃO JOÃO", "12-1023": "CRECHE" },
    });
    expect(secoesDoMunicipio(mu, "12", "").map((s) => s.local)).toEqual(["ESCOLA SÃO JOÃO", "CRECHE"]);
    expect(secoesDoMunicipio(mu, null, "sao joao").map((s) => s.secao)).toEqual([1]);
    expect(secoesDoMunicipio(mu, null, "5")[0]).toMatchObject({ zona: "13", local: "Local 1015" });
  });

  it("a leitura recusa versão e seção fora do contrato", () => {
    const bom = arquivo("municipio", { secoes: [["12", 1, "1015", 300]] });
    expect(validarEleitorado(JSON.parse(JSON.stringify(bom))).lugar.nome).toBe("Borá");
    expect(() => validarEleitorado({ ...bom, versao: 2 })).toThrow();
    expect(() => validarEleitorado({ ...bom, secoes: [["12", 1, "1015"]] })).toThrow();
    expect(() => validarEleitorado({ ...bom, tipo: "zonas" })).toThrow();
  });
});

describe("leitura do eleitorado no site dos painéis", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("cada lugar no arquivo dele; o município no arquivo do grupo", () => {
    expect(urlEleitorado(2026, "br")).toBe(`${BASE_PAINEL}/eleitorado/2026/br.json.gz`);
    expect(urlEleitorado(2026, "uf-sp")).toBe(`${BASE_PAINEL}/eleitorado/2026/uf-sp.json.gz`);
    expect(urlEleitorado(2026, "mu-3507209")).toBe(`${BASE_PAINEL}/eleitorado/2026/mu/072.json.gz`);
    expect(urlEleitorado(2026, "mu-zz-29530")).toBe(`${BASE_PAINEL}/eleitorado/2026/mu/zz.json.gz`);
    expect(urlEleitorado(2026, "mu-../x")).toBeNull();
    expect(grupoDoMunicipio("zz-29530")).toBe("zz");
  });

  it("descomprime o grupo e devolve o município com a origem do grupo", async () => {
    const mu = { versao: 1, tipo: "eleitorado", ano: 2018, nivel: "municipio", lugar, zonas: [], secoes: [] };
    const corpo = gzipSync(JSON.stringify({ versao: 1, tipo: "eleitorado-grupo", ano: 2018,
      origem: { perfil: { fonte: "dados_abertos" } }, municipios: { "3507209": mu } }));
    vi.stubGlobal("fetch", vi.fn(async () => new Response(corpo, { status: 200 })));
    const a = await carregarEleitorado(2018, "mu-3507209");
    expect(a?.lugar.nome).toBe("Borá");
    expect((a?.origem as Record<string, { fonte: string }>).perfil!.fonte).toBe("dados_abertos");
    expect(await carregarEleitorado(2018, "mu-3500105")).toBeNull();          // outro do grupo, sem dados
    vi.stubGlobal("fetch", vi.fn(async () => new Response("", { status: 404 })));
    expect(await carregarEleitorado(2020, "br")).toBeNull();
  });
});
