import { describe, expect, it } from "vitest";
import { compararTurnos, primeiroTurnoDe } from "../comparacao";
import type { FeedResultado, Indice } from "../tipos";
import { validarFeed, validarIndice } from "../validacao";
import { AMOSTRA, lerJson } from "./apoio";

const indice = validarIndice(lerJson(`${AMOSTRA}/indice.json`)) as Indice;
const feed = (id: string) => validarFeed(lerJson(`${AMOSTRA}/${id}/presidente/br.json`)) as FeedResultado;

describe("comparação com o 1º turno", () => {
  it("acha o 1º turno do mesmo ano e tipo, com o cargo", () => {
    const segundo = indice.eleicoes.find((e) => e.id === "1989-2t-geral")!;
    expect(primeiroTurnoDe(indice, segundo, "presidente")?.id).toBe("1989-1t-geral");
    expect(primeiroTurnoDe(indice, segundo, "governador")).toBeNull();
    expect(primeiroTurnoDe(indice, indice.eleicoes.find((e) => e.id === "1989-1t-geral")!, "presidente")).toBeNull();
  });

  it("o ganho dos finalistas é o voto dos demais mais a variação dos válidos", () => {
    const um = feed("1989-1t-geral");
    const dois = feed("1989-2t-geral");
    const c = compararTurnos(um, dois);
    expect(c.finalistas.map((f) => f.nome)).toEqual(dois.candidatos.filter((x) => x.valido).map((x) => x.nome_urna));
    const lula = c.finalistas.find((f) => f.numero === "13")!;
    expect(lula.votos1).toBe(um.candidatos.find((x) => x.numero === "13")!.votos);
    expect(c.ganho).toBe(c.demais! + c.validos.diferenca!);
    expect(c.comparecimento.diferenca).toBe(dois.comparecimento.comparecimento! - um.comparecimento.comparecimento!);
  });
});
