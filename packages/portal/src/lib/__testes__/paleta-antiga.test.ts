import { describe, expect, it } from "vitest";
import { corDaRegraAtual } from "../cores";
import { naRegraAtual } from "../paleta-antiga";
import type { FeedResultado } from "../tipos";
import { validarFeed } from "../validacao";
import { AMOSTRA, lerJson } from "./apoio";

describe("feeds gravados antes do ADR-052", () => {
  it("PL azul e PT vermelho; os demais andam duas posições", () => {
    expect(corDaRegraAtual(0, "PT")).toBe(1);
    expect(corDaRegraAtual(1, "PL")).toBe(0);
    expect(corDaRegraAtual(0, "PSDB")).toBe(2);
    expect(corDaRegraAtual(5, "MDB")).toBe(7);
    expect(corDaRegraAtual(6, "MDB")).toBe(-1);
    expect(corDaRegraAtual(-1, null)).toBe(-1);
  });

  it("o 2º turno de 2026 como foi publicado: Lula na posição 0, Flávio na 1", () => {
    const atual = validarFeed(lerJson(`${AMOSTRA}/1989-2t-geral/presidente/br.json`)) as FeedResultado;
    expect(atual.paleta).toBe(2);
    expect(naRegraAtual(atual)).toBe(atual);
    // O mesmo feed sem `paleta`, com as cores da regra anterior
    const antigo: FeedResultado = {
      ...atual,
      paleta: undefined,
      candidatos: [
        { ...atual.candidatos[0]!, numero: "13", partido: "PT", cor: 0 },
        { ...atual.candidatos[1]!, numero: "22", partido: "PL", cor: 1 },
      ],
      partes: [{ ...atual.partes[0]!, lider: "13", partido: undefined, cor: 0 },
        { ...atual.partes[1]!, lider: "22", partido: undefined, cor: 1 }],
    };
    const lido = naRegraAtual(antigo);
    expect(lido.candidatos.map((c) => c.cor)).toEqual([1, 0]);
    expect(lido.partes.map((p) => p.cor)).toEqual([1, 0]);
  });
});
