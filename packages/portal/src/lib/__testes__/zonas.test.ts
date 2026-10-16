/** Zonas eleitorais no mapa: Voronoi dos locais de votação, desenho das zonas, zoom até o município. */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { memorizar } from "../feeds";
import { pontoProjetado, projetar, projetarCom, type Topologia } from "../topojson";
import { type ArquivoZonas, VERSAO_FEED, VERSAO_ZONAS } from "../tipos";
import { validarIndiceZonas, validarZonas } from "../validacao";
import { celulasVoronoi, cortar, type Ponto } from "../voronoi";
import { caixaComFolga, desenharZonas, rarear, rotulosVisiveis } from "../zonas";
import { enquadrar, interpolar, suavizar, zoomMaximoPara, ZOOM_MAXIMO, type Limites } from "../zoom";
import { FIX_IBGE, lerJson, RAIZ } from "./apoio";

/** Área de um polígono (fórmula do laço). */
function area(vs: Ponto[]): number {
  let s = 0;
  vs.forEach((v, i) => {
    const w = vs[(i + 1) % vs.length]!;
    s += v[0] * w[1] - w[0] * v[1];
  });
  return Math.abs(s) / 2;
}

/** Gerador pseudoaleatório fixo, para os testes darem sempre o mesmo resultado. */
function sorteio(semente: number): () => number {
  let x = semente;
  return () => {
    x = (x * 1103515245 + 12345) % 2147483648;
    return x / 2147483648;
  };
}

describe("Voronoi", () => {
  it("corta pela mediatriz e marca de quem é o lado novo", () => {
    const quadrado: Ponto[] = [[0, 0], [2, 0], [2, 2], [0, 2]];
    const c = cortar(quadrado, [-1, -1, -1, -1], [0.5, 1], [1.5, 1], 7)!;
    expect(area(c.vertices)).toBeCloseTo(2);
    expect(c.vizinhos.filter((v) => v === 7)).toHaveLength(1);
    expect(Math.max(...c.vertices.map((v) => v[0]))).toBeCloseTo(1);
    // Corte que não deixa nada
    expect(cortar([[0, 0], [1, 0], [1, 1]], [-1, -1, -1], [10, 0], [0, 0], 3)).toBeNull();
  });

  it("dois pontos dividem a caixa ao meio", () => {
    const [a, b] = celulasVoronoi([[1, 1], [3, 1]], [0, 0, 4, 2]);
    expect(area(a!.vertices)).toBeCloseTo(4);
    expect(area(b!.vertices)).toBeCloseTo(4);
    expect(a!.vizinhos).toContain(1);
    expect(b!.vizinhos).toContain(0);
  });

  it("cobre a caixa sem sobra nem sobreposição, e cada ponto fica na própria célula", () => {
    const r = sorteio(42);
    const pontos: Ponto[] = Array.from({ length: 300 }, () => [r() * 100, r() * 60]);
    const celulas = celulasVoronoi(pontos, [0, 0, 100, 60]);
    const soma = celulas.reduce((s, c) => s + (c ? area(c.vertices) : 0), 0);
    expect(soma).toBeCloseTo(100 * 60, 6);
    // Um ponto qualquer da caixa está na célula do ponto mais perto
    for (let k = 0; k < 200; k++) {
      const q: Ponto = [r() * 100, r() * 60];
      let maisPerto = 0;
      pontos.forEach((p, i) => {
        if (Math.hypot(p[0] - q[0], p[1] - q[1]) < Math.hypot(pontos[maisPerto]![0] - q[0], pontos[maisPerto]![1] - q[1])) {
          maisPerto = i;
        }
      });
      expect(dentro(q, celulas[maisPerto]!.vertices)).toBe(true);
    }
    // Vizinhança simétrica: se o lado de i é de j, o de j tem um lado de i
    celulas.forEach((c, i) => {
      for (const j of c!.vizinhos) if (j >= 0) expect(celulas[j]!.vizinhos).toContain(i);
    });
  });

  it("ponto repetido não forma célula", () => {
    const celulas = celulasVoronoi([[1, 1], [1, 1], [3, 1]], [0, 0, 4, 2]);
    expect(celulas[1]).toBeNull();
    expect(area(celulas[0]!.vertices) + area(celulas[2]!.vertices)).toBeCloseTo(8);
    expect(celulasVoronoi([], [0, 0, 1, 1])).toEqual([]);
  });
});

/** Ponto dentro de polígono convexo (ou na borda). */
function dentro(q: Ponto, vs: Ponto[]): boolean {
  let sinal = 0;
  for (let i = 0; i < vs.length; i++) {
    const a = vs[i]!;
    const b = vs[(i + 1) % vs.length]!;
    const cruz = (b[0] - a[0]) * (q[1] - a[1]) - (b[1] - a[1]) * (q[0] - a[0]);
    if (Math.abs(cruz) < 1e-9) continue;
    if (sinal === 0) sinal = Math.sign(cruz);
    else if (Math.sign(cruz) !== sinal) return false;
  }
  return true;
}

const ARQUIVO: ArquivoZonas = {
  versao: 1,
  tipo: "zonas",
  ano: 2026,
  municipio: { ibge: "3548807", tse: "70777", uf: "sp", nome: "São Caetano do Sul" },
  origem: { fonte: "dados_abertos", url: null, sha256: null, coletado_em: null, registro_bronze: null },
  zonas: [
    { zona: "166", locais: 2, eleitores: 900 },
    { zona: "269", locais: 2, eleitores: 700 },
  ],
  locais: [
    [0, 0, "166", 500, "A"],
    [0, 2, "166", 400, "B"],
    [4, 0, "269", 300, "C"],
    [4, 2, "269", 400, "D"],
    // Mesmo prédio que "D", com menos eleitores: o ponto fica com a 269
    [4, 2, "166", 10, "D"],
  ],
  descartados: { sem_coordenada: 0, fora_do_municipio: 0 },
};

describe("desenho das zonas", () => {
  const desenho = desenharZonas(ARQUIVO, (lon, lat) => [lon, lat], [-1, -1, 5, 3]);

  it("uma área por zona, com a fronteira entre as duas", () => {
    expect(desenho.zonas.map((z) => z.zona)).toEqual(["166", "269"]);
    expect(desenho.locais).toHaveLength(5);
    // As células de cada zona são subcaminhos fechados
    for (const z of desenho.zonas) expect(z.d.match(/M/g)).toHaveLength(2);
    // A fronteira é a reta x = 2, de y = -1 a y = 3, em dois lados (um por par de células vizinhas)
    const xs = [...desenho.fronteiras.matchAll(/[ML](-?[\d.]+) /g)].map((m) => Number(m[1]));
    expect(xs.length).toBeGreaterThan(0);
    for (const x of xs) expect(x).toBeCloseTo(2);
    // O contorno de destaque da zona 166 tem a fronteira e a borda do desenho, não o lado entre as células dela
    const contorno = desenho.zonas[0]!.contorno;
    expect(contorno).not.toContain("M-1 1L2 1");
    expect(contorno).not.toContain("M2 1L-1 1");
    expect(contorno).toContain("M-1 1L-1 -1");
    expect(desenho.zonas[0]!.rotulo[0]).toBe(0);
  });

  it("caixa com folga", () => {
    expect(caixaComFolga([0, 0, 10, 4], 0.1)).toEqual([-1, -1, 11, 5]);
  });

  it("rótulos que não cabem saem, a zona maior primeiro", () => {
    expect(desenho.zonas.map((z) => z.eleitores)).toEqual([900, 700]);
    // Os dois rótulos estão a 4 unidades: cabem com distância 3, não com 5
    expect([...rotulosVisiveis(desenho.zonas, 3)].sort()).toEqual(["166", "269"]);
    expect([...rotulosVisiveis(desenho.zonas, 5)]).toEqual(["166"]);
  });

  it("pontos amontoados são rareados por uma grade", () => {
    const pontos = [{ x: 0.1, y: 0.1 }, { x: 0.2, y: 0.3 }, { x: 5, y: 5 }, { x: 5.4, y: 9 }];
    expect(rarear(pontos, 1)).toEqual([0, 2, 3]);
    expect(rarear(pontos, 0)).toEqual([0, 1, 2, 3]);
    expect(rarear(pontos, 100)).toEqual([0]);
  });
});

describe("zoom até o município", () => {
  const L: Limites = { largura: 1000, altura: 800, maxZoom: 200 };

  it("enquadra a caixa com margem, na proporção do mapa", () => {
    const v = enquadrar([400, 300, 500, 340], L, 0.1);
    expect(v.w).toBeCloseTo(120);
    expect(v.h).toBeCloseTo(96);
    expect(v.x + v.w / 2).toBeCloseTo(450);
    expect(v.y + v.h / 2).toBeCloseTo(320);
    // Caixa alta: manda a altura
    const alta = enquadrar([0, 0, 10, 100], { ...L, maxZoom: 1000 }, 0);
    expect(alta.h).toBeCloseTo(100);
  });

  it("deixa aproximar além do padrão para o município pequeno", () => {
    expect(zoomMaximoPara(null, L)).toBe(ZOOM_MAXIMO);
    expect(zoomMaximoPara([0, 0, 500, 400], L)).toBe(ZOOM_MAXIMO);
    expect(zoomMaximoPara([0, 0, 5, 4], L)).toBeCloseTo(800);
  });

  it("interpola a janela com a largura em escala logarítmica", () => {
    const a = { x: 0, y: 0, w: 1000, h: 800 };
    const b = { x: 400, y: 300, w: 10, h: 8 };
    expect(interpolar(a, b, 0)).toEqual(a);
    const fim = interpolar(a, b, 1);
    expect(fim.x).toBeCloseTo(400);
    expect(fim.w).toBeCloseTo(10);
    expect(interpolar(a, b, 0.5).w).toBeCloseTo(100);
    expect(interpolar(a, a, 0.3)).toEqual(a);
    expect(suavizar(0)).toBe(0);
    expect(suavizar(1)).toBe(1);
    expect(suavizar(0.5)).toBeGreaterThan(0.5);
  });
});

describe("contorno fino no enquadramento da UF", () => {
  const acre = lerJson(`${FIX_IBGE}/malha_uf12_municipios_minima.json`) as Topologia;

  it("projeta outra malha e pontos no mesmo lugar do mapa da UF", () => {
    const mapa = projetar(acre, 800);
    const mesma = projetarCom(acre, mapa.projecao, 1);
    expect(mesma.map((f) => f.d)).toEqual(mapa.formas.map((f) => f.d));
    const f = mapa.formas.find((x) => x.codigo === "1200013")!;
    expect(f.caixa[0]).toBeLessThan(f.caixa[2]);
    // Mais casas decimais no contorno fino
    expect(projetarCom(acre, mapa.projecao)[0]!.d).toMatch(/\.\d{2,3}/);
    const [x, y] = pontoProjetado(mapa.projecao, -70, -9);
    expect(x).toBeGreaterThan(0);
    expect(x).toBeLessThan(800);
    expect(y).toBeGreaterThan(0);
  });
});

describe("validação dos arquivos das zonas", () => {
  it("aceita o formato gravado pelo Python e recusa o resto", () => {
    expect(validarZonas(ARQUIVO).zonas).toHaveLength(2);
    expect(() => validarZonas({ ...ARQUIVO, versao: 2 })).toThrow(/versão/);
    expect(() => validarZonas({ ...ARQUIVO, tipo: "resultado" })).toThrow(/não é de zonas/);
    expect(() => validarZonas({ ...ARQUIVO, locais: [[0, 0, "999", 1, "x"]] })).toThrow(/fora do formato/);
    expect(() => validarZonas({ ...ARQUIVO, locais: [["0", 0, "166", 1, "x"]] })).toThrow(/fora do formato/);
    const { locais: _locais, ...semLocais } = ARQUIVO;
    expect(() => validarZonas(semLocais)).toThrow(/faltam locais/);
    const indice = { versao: 1, tipo: "zonas-indice", ano: 2026, municipios: { "3548807": 2 } };
    expect(validarIndiceZonas(indice).municipios["3548807"]).toBe(2);
    expect(() => validarIndiceZonas({ ...indice, tipo: "zonas" })).toThrow(/não é índice/);
    expect(() => validarIndiceZonas({ ...indice, municipios: [] })).toThrow(/esperado objeto/);
  });
});

describe("versão do mapa das zonas", () => {
  it("é a mesma do Python e independente da dos feeds", () => {
    const py = readFileSync(join(RAIZ, "packages/eleicoes/lumen_eleicoes/zonas.py"), "utf-8");
    expect(Number(/^VERSAO_ZONAS = (\d+)/m.exec(py)?.[1])).toBe(VERSAO_ZONAS);
    // Arquivo de zonas com a versão dos feeds diferente da das zonas continua aceito pela das zonas
    expect(validarZonas({ ...ARQUIVO, versao: VERSAO_ZONAS }).versao).toBe(VERSAO_ZONAS);
    expect(VERSAO_FEED).toBeGreaterThan(0);
    const { descartados: _d, ...semDescartados } = ARQUIVO;
    expect(validarZonas(semDescartados).descartados).toBeUndefined();
  });
});

describe("cache em memória", () => {
  it("sai o usado há mais tempo, não o mais antigo", async () => {
    const cache = new Map<string, Promise<number>>();
    let criados = 0;
    const criar = () => Promise.resolve(++criados);
    await memorizar(cache, "a", criar, 2);
    await memorizar(cache, "b", criar, 2);
    await memorizar(cache, "a", criar, 2);          // "a" volta para o fim da fila
    await memorizar(cache, "c", criar, 2);          // sai "b"
    expect([...cache.keys()]).toEqual(["a", "c"]);
    expect(criados).toBe(3);
  });

  it("falha atrasada não apaga a entrada que a substituiu", async () => {
    const cache = new Map<string, Promise<number>>();
    let rejeitar: (e: Error) => void = () => undefined;
    const lenta = memorizar(cache, "a", () => new Promise<number>((_, r) => (rejeitar = r)), 1);
    lenta.catch(() => undefined);
    await memorizar(cache, "b", () => Promise.resolve(1), 1);      // "a" sai pelo limite
    const nova = memorizar(cache, "a", () => Promise.resolve(2), 1);
    rejeitar(new Error("rede"));
    await lenta.catch(() => undefined);
    expect(cache.get("a")).toBe(nova);
    // E a falha da própria entrada a tira do cache
    const falha = memorizar(cache, "x", () => Promise.reject(new Error("rede")), 5);
    await falha.catch(() => undefined);
    expect(cache.has("x")).toBe(false);
  });
});
