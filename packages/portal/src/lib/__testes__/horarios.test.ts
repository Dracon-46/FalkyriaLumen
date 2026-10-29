// Horários das urnas (ADR-056): horas, barras dos histogramas, lugares abaixo, seções e a leitura.
import { gzipSync } from "node:zlib";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  barrasDoHistograma,
  carregarHorarios,
  hhmm,
  lugaresDosHorarios,
  secoesDosHorarios,
  turnoDosHorarios,
  urlHorarios,
} from "../horarios";
import { BASE_PAINEL } from "../paineis";
import type { ArquivoHorarios, ResumoHorarios } from "../tipos";
import { validarHorarios } from "../validacao";

const resumo = (secoes: number, depois = 0): ResumoHorarios => ({
  secoes, aptos: secoes * 300, comparecimento: secoes * 240, depois_17h30: depois,
  encerramento: [1024, 1030, 1100], recebido: [1180, 1200, 1300],
});

function arquivo(nivel: ArquivoHorarios["nivel"], extra: Partial<ArquivoHorarios> = {}): ArquivoHorarios {
  return { versao: 1, tipo: "horarios", ano: 2026, horario: "brasilia", nivel, origem: {},
    lugar: { chave: "1200450", nome: "Senador Guiomard", turnos: { "1": resumo(3), "2": resumo(3) } }, ...extra };
}

describe("horários das urnas", () => {
  it("minutos desde a meia-noite em hora e minuto, também no dia seguinte", () => {
    expect(hhmm(17 * 60 + 5)).toBe("17:05");
    expect(hhmm(1440 + 10)).toBe("+1 00:10");
    expect(hhmm(null)).toBe("—");
  });

  it("as barras do histograma sem as faixas vazias do fim", () => {
    const barras = barrasDoHistograma({ inicio: 990, passo: 10, contagens: [0, 2, 5, 0, 0], antes: 0, depois: 1 });
    expect(barras).toEqual([{ rotulo: "16:30", valor: 0 }, { rotulo: "16:40", valor: 2 }, { rotulo: "16:50", valor: 5 }]);
  });

  it("o turno da eleição aberta, se o arquivo o tem; senão o mais recente", () => {
    expect(turnoDosHorarios({ "1": 0, "2": 0 }, 1)).toBe("1");
    expect(turnoDosHorarios({ "1": 0 }, 2)).toBe("1");
    expect(turnoDosHorarios({}, null)).toBeNull();
  });

  it("os lugares abaixo, no turno, em ordem de nome; as zonas abrem no município", () => {
    const uf = arquivo("uf", { partes: {
      "1200450": { nome: "Senador Guiomard", turnos: { "2": resumo(3) } },
      "1200013": { nome: "Acrelândia", turnos: { "1": resumo(2, 1), "2": resumo(2) } },
    } });
    expect(lugaresDosHorarios(uf, "2").map((l) => [l.nome, l.abrangencia])).toEqual([
      ["Acrelândia", "mu-1200013"], ["Senador Guiomard", "mu-1200450"]]);
    expect(lugaresDosHorarios(uf, "1").map((l) => l.resumo.depois_17h30)).toEqual([1]);
    const mu = arquivo("municipio", { zonas: [{ zona: "8", turnos: { "2": resumo(3) } }] });
    expect(lugaresDosHorarios(mu, "2")[0]).toMatchObject({ nome: "Zona 8", abrangencia: null });
  });

  it("as seções do turno, com o nome do local do eleitorado, filtradas sem acento", () => {
    const mu = arquivo("municipio", { secoes: [
      [2, "8", 68, "1074", 220, 169, "Apurada", "08:00", "17:00", "17:03", "19:42"],
      [2, "8", 70, "1171", 288, 229, "Apurada", "08:00", "17:00", "17:03", "19:54"],
      [1, "8", 68, "1074", 220, 180, "Apurada", "08:00", "17:02", "17:04", "18:10"],
    ] });
    const locais = { "8-1074": "ESCOLA SÃO JOSÉ" };
    expect(secoesDosHorarios(mu, "2", null, "", locais).map((s) => [s.secao, s.local])).toEqual([
      [68, "ESCOLA SÃO JOSÉ"], [70, "Local 1171"]]);
    expect(secoesDosHorarios(mu, "2", "8", "sao jose", locais).map((s) => s.recebido)).toEqual(["19:42"]);
    expect(secoesDosHorarios(mu, "1", "9", "")).toEqual([]);
  });

  it("a leitura recusa versão, tipo e seção fora do contrato", () => {
    const bom = arquivo("municipio", { secoes: [[2, "8", 68, "1074", 220, 169, "Apurada", "08:00", "17:00", null, null]] });
    expect(validarHorarios(JSON.parse(JSON.stringify(bom))).lugar.nome).toBe("Senador Guiomard");
    expect(() => validarHorarios({ ...bom, versao: 2 })).toThrow();
    expect(() => validarHorarios({ ...bom, tipo: "eleitorado" })).toThrow();
    expect(() => validarHorarios({ ...bom, secoes: [[2, "8", 68]] })).toThrow();
  });
});

describe("leitura dos horários no site dos painéis", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("cada lugar no arquivo dele; o município no arquivo do grupo", () => {
    expect(urlHorarios(2026, "br")).toBe(`${BASE_PAINEL}/horarios/2026/br.json.gz`);
    expect(urlHorarios(2026, "uf-ac")).toBe(`${BASE_PAINEL}/horarios/2026/uf-ac.json.gz`);
    expect(urlHorarios(2026, "mu-1200450")).toBe(`${BASE_PAINEL}/horarios/2026/mu/004.json.gz`);
    expect(urlHorarios(2026, "mu-zz-29998")).toBe(`${BASE_PAINEL}/horarios/2026/mu/zz.json.gz`);
    expect(urlHorarios(2026, "regiao-norte")).toBeNull();
  });

  it("descomprime o grupo e devolve o município com a origem do grupo", async () => {
    const mu = { ...arquivo("municipio"), origem: undefined };
    const corpo = gzipSync(JSON.stringify({ versao: 1, tipo: "horarios-grupo", ano: 2022, horario: "brasilia",
      origem: { fonte: "dados_abertos" }, municipios: { "1200450": mu } }));
    vi.stubGlobal("fetch", vi.fn(async () => new Response(corpo, { status: 200 })));
    const a = await carregarHorarios(2022, "mu-1200450");
    expect(a?.lugar.nome).toBe("Senador Guiomard");
    expect((a?.origem as { fonte: string }).fonte).toBe("dados_abertos");
    expect(await carregarHorarios(2022, "mu-1200401")).toBeNull();
    vi.stubGlobal("fetch", vi.fn(async () => new Response("", { status: 404 })));
    expect(await carregarHorarios(2020, "br")).toBeNull();
  });
});
