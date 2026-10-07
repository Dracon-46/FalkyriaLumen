/** Decodificação do TopoJSON do IBGE com a malha real do Acre: arcos, anéis fechados e projeção. */
import { describe, expect, it } from "vitest";
import { aneisDaGeometria, decodificarArcos, projetar, type Topologia } from "../topojson";
import { FIX_IBGE, lerJson } from "./apoio";

const acre = lerJson(`${FIX_IBGE}/malha_uf12_municipios_minima.json`) as Topologia;

describe("TopoJSON do IBGE", () => {
  it("decodifica arcos quantizados e por diferença", () => {
    const arcos = decodificarArcos(acre);
    expect(arcos).toHaveLength(63);
    const [lon, lat] = arcos[0]![0]!;
    // Primeiro ponto: 6865 * escala + translação
    expect(lon).toBeCloseTo(6865 * 0.0010000679071030813 - 73.9904, 9);
    expect(lat).toBeCloseTo(1531 * 0.0007679040548258139 - 11.1456, 9);
    // O Acre fica entre 66° e 74° O, 7° e 11,2° S
    for (const arco of arcos) {
      for (const [x, y] of arco) {
        expect(x).toBeGreaterThan(-74.1);
        expect(x).toBeLessThan(-66.5);
        expect(y).toBeGreaterThan(-11.2);
        expect(y).toBeLessThan(-7);
      }
    }
  });

  it("monta anéis fechados, inclusive com arcos invertidos", () => {
    const arcos = decodificarArcos(acre);
    const geometrias = Object.values(acre.objects)[0]!.geometries;
    for (const g of geometrias) {
      for (const anel of aneisDaGeometria(g as never, arcos)) {
        expect(anel[0]).toEqual(anel[anel.length - 1]);
      }
    }
  });

  it("projeta os 22 municípios dentro do retângulo pedido", () => {
    const mapa = projetar(acre, 800);
    expect(mapa.largura).toBe(800);
    expect(mapa.altura).toBeGreaterThan(300);
    expect(mapa.altura).toBeLessThan(600);
    expect(mapa.formas.map((f) => f.codigo)).toContain("1200013");
    expect(mapa.formas).toHaveLength(22);
    for (const f of mapa.formas) {
      expect(f.d.startsWith("M")).toBe(true);
      expect(f.d.endsWith("Z")).toBe(true);
      const numeros = f.d.match(/-?\d+(\.\d+)?/g)!.map(Number);
      for (const n of numeros) {
        expect(n).toBeGreaterThanOrEqual(-0.5);
        expect(n).toBeLessThanOrEqual(800.5);
      }
      expect(f.centro[0]).toBeGreaterThan(0);
    }
  });

  it("aceita MultiPolygon e malha vazia", () => {
    const topo: Topologia = {
      type: "Topology",
      arcs: [[[0, 0], [1, 0], [1, 1], [0, 0]], [[2, 2], [3, 2], [3, 3], [2, 2]]],
      objects: { x: { type: "GeometryCollection", geometries: [
        { type: "MultiPolygon", arcs: [[[0]], [[1]]], properties: { codarea: "99" } },
      ] } },
    };
    const mapa = projetar(topo, 100);
    expect(mapa.formas[0]!.d.match(/M/g)).toHaveLength(2);
    expect(projetar({ type: "Topology", arcs: [], objects: {} }).formas).toEqual([]);
    expect(() =>
      projetar({ ...topo, objects: { x: { type: "GeometryCollection", geometries: [
        { type: "Polygon", arcs: [[7]], properties: { codarea: "1" } }] } } }),
    ).toThrow(/arco 7/);
  });
});
