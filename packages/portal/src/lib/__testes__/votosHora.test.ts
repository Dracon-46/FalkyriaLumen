// Votos por hora (ADR-057): hora de pico, fila depois das 17h, metade dos votos, lugares, seções e a leitura.
import { gzipSync } from "node:zlib";
import { afterEach, describe, expect, it, vi } from "vitest";
import { BASE_PAINEL } from "../paineis";
import type { ArquivoVotosHora, TurnoVotosHora } from "../tipos";
import { validarVotosHora } from "../validacao";
import {
  carregarVotosHora,
  depoisDoFim,
  grupoDosVotos,
  horaDePico,
  horas,
  locaisDasSecoes,
  lugaresDosVotos,
  metadeAte,
  secoesDosVotos,
  turnoDosVotos,
  urlVotosHora,
} from "../votosHora";

const turno = (votos: number, porHora: number[]): TurnoVotosHora => ({ votos, secoes: 2, por_hora: porHora });

function arquivo(nivel: ArquivoVotosHora["nivel"], extra: Partial<ArquivoVotosHora> = {}): ArquivoVotosHora {
  return { versao: 1, tipo: "votos-hora", ano: 2026, horario: "brasilia", nivel, origem: {},
    lugar: { chave: "1200450", nome: "Senador Guiomard", turnos: { "1": turno(10, [8, 4, 6]) } }, ...extra };
}

describe("votos por hora", () => {
  it("as horas, a de mais votos e os votos depois das 17h", () => {
    expect(horas([8, 4, 6])).toEqual([{ hora: 8, votos: 4 }, { hora: 9, votos: 6 }]);
    expect(horas([])).toEqual([]);
    expect(horaDePico([8, 4, 6, 6])).toEqual({ hora: 9, votos: 6 });            // no empate, a primeira
    expect(horaDePico([8, 0])).toBeNull();
    expect(depoisDoFim([15, 10, 20, 5, 2])).toBe(7);
  });

  it("até que horas metade votou, pelas faixas de 10 minutos", () => {
    const t: TurnoVotosHora = { votos: 10, secoes: 1, por_hora: [8, 10],
      por_faixa: { inicio: 480, passo: 10, contagens: [2, 2, 1, 5] } };
    expect(metadeAte(t)).toBe(510);                                              // 2 + 2 + 1 = 5 até 8h30
    expect(metadeAte({ ...t, por_faixa: undefined })).toBeNull();
    expect(metadeAte({ ...t, por_faixa: { inicio: null, passo: 10, contagens: [] } })).toBeNull();
  });

  it("o turno da eleição aberta, se o arquivo o tem; senão o mais recente", () => {
    expect(turnoDosVotos({ "1": 0, "2": 0 }, 1)).toBe("1");
    expect(turnoDosVotos({ "1": 0 }, 2)).toBe("1");
  });

  it("os lugares abaixo em ordem de nome; as zonas abrem no município", () => {
    const uf = arquivo("uf", { partes: {
      "1200450": { nome: "Senador Guiomard", turnos: { "1": turno(5, [8, 5]) } },
      "1200013": { nome: "Acrelândia", turnos: { "1": turno(3, [8, 3]), "2": turno(2, [9, 2]) } },
    } });
    expect(lugaresDosVotos(uf, "1").map((l) => [l.nome, l.abrangencia])).toEqual([
      ["Acrelândia", "mu-1200013"], ["Senador Guiomard", "mu-1200450"]]);
    expect(lugaresDosVotos(uf, "2")).toHaveLength(1);
    const mu = arquivo("municipio", { zonas: [{ zona: "8", turnos: { "1": turno(10, [8, 10]) } }] });
    expect(lugaresDosVotos(mu, "1")[0]).toMatchObject({ nome: "Zona 8", abrangencia: null });
  });

  it("as seções do turno com o local do eleitorado, filtradas sem acento", () => {
    const mu = arquivo("municipio", { secoes: [[1, "8", 68, 8, 3, 1], [1, "8", 70, 11, 1], [2, "8", 68, 9, 4]] });
    const locais = locaisDasSecoes([["8", 68, "1074", 220], ["8", 70, "1171", 288]], { "8-1074": "ESCOLA SÃO JOSÉ" });
    expect(secoesDosVotos(mu, "1", null, "", locais).map((s) => [s.secao, s.local, s.votos])).toEqual([
      [68, "ESCOLA SÃO JOSÉ", 4], [70, null, 1]]);
    expect(secoesDosVotos(mu, "1", "8", "sao jose", locais).map((s) => s.secao)).toEqual([68]);
    expect(secoesDosVotos(mu, "2", null, "68")[0]!.porHora).toEqual([9, 4]);
    expect(locaisDasSecoes(undefined, {})).toBeUndefined();
  });

  it("a leitura recusa versão, tipo e seção fora do contrato", () => {
    const bom = arquivo("municipio", { secoes: [[1, "8", 68, 8, 3]] });
    expect(validarVotosHora(JSON.parse(JSON.stringify(bom))).lugar.nome).toBe("Senador Guiomard");
    expect(() => validarVotosHora({ ...bom, versao: 2 })).toThrow();
    expect(() => validarVotosHora({ ...bom, tipo: "horarios" })).toThrow();
    expect(() => validarVotosHora({ ...bom, secoes: [[1, "8"]] })).toThrow();
  });
});

describe("leitura dos votos por hora no site dos painéis", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("cada lugar no arquivo dele; o município no arquivo do grupo de dois dígitos", () => {
    expect(urlVotosHora(2026, "br")).toBe(`${BASE_PAINEL}/votos-hora/2026/br.json.gz`);
    expect(urlVotosHora(2026, "uf-sp")).toBe(`${BASE_PAINEL}/votos-hora/2026/uf-sp.json.gz`);
    expect(urlVotosHora(2026, "mu-3550308")).toBe(`${BASE_PAINEL}/votos-hora/2026/mu/50.json.gz`);
    expect(urlVotosHora(2026, "mu-zz-29998")).toBe(`${BASE_PAINEL}/votos-hora/2026/mu/zz.json.gz`);
    expect(urlVotosHora(2026, "regiao-norte")).toBeNull();
    expect(grupoDosVotos("1200450")).toBe("00");
  });

  it("descomprime o grupo e devolve o município com a origem do grupo", async () => {
    const mu = { ...arquivo("municipio"), origem: undefined };
    const corpo = gzipSync(JSON.stringify({ versao: 1, tipo: "votos-hora-grupo", ano: 2022, horario: "brasilia",
      origem: { fonte: "dados_abertos" }, municipios: { "1200450": mu } }));
    vi.stubGlobal("fetch", vi.fn(async () => new Response(corpo, { status: 200 })));
    const a = await carregarVotosHora(2022, "mu-1200450");
    expect(a?.lugar.nome).toBe("Senador Guiomard");
    expect((a?.origem as { fonte: string }).fonte).toBe("dados_abertos");
    expect(await carregarVotosHora(2022, "mu-1200401")).toBeNull();
    vi.stubGlobal("fetch", vi.fn(async () => new Response("", { status: 404 })));
    expect(await carregarVotosHora(2024, "br")).toBeNull();
  });
});
