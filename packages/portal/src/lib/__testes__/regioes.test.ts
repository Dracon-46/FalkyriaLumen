import { describe, expect, it } from "vitest";
import { completarComFeedsDasUfs } from "../modos-mapa";
import { REGIOES, resultadoDaRegiao, ufDaParte, ufsDaRegiao } from "../regioes";
import type { FeedResultado, Parte } from "../tipos";
import { validarFeed } from "../validacao";
import { AMOSTRA, lerJson } from "./apoio";

const feed = (arquivo: string) =>
  validarFeed(lerJson(`${AMOSTRA}/1989-2t-geral/presidente/${arquivo}.json`)) as FeedResultado;

describe("regiões", () => {
  it("as cinco regiões cobrem as 27 UFs, cada uma uma vez", () => {
    const ufs = REGIOES.flatMap((r) => r.ufs);
    expect(ufs).toHaveLength(27);
    expect(new Set(ufs).size).toBe(27);
    expect(ufsDaRegiao("sul")).toEqual(["pr", "rs", "sc"]);
    expect(ufsDaRegiao(null)).toBeNull();
  });

  it("a UF de uma parte: a sigla ou os dois primeiros dígitos do IBGE", () => {
    const p = (codigo: string, ibge: string | null = null) =>
      ({ codigo, nome: codigo, ibge, lider: null, cor: -1, pct_secoes: null, finalizada: true, eleitorado: null }) as Parte;
    expect(ufDaParte(p("sp"))).toBe("sp");
    expect(ufDaParte(p("3550308", "3550308"))).toBe("sp");
    expect(ufDaParte(p("zz-29254"))).toBeNull();
  });

  it("o resultado da região soma os votos das UFs; falta uma UF, não soma", () => {
    const br = feed("br");
    const ac = feed("uf-ac");
    const df = feed("uf-df");
    const r = resultadoDaRegiao(br, "Teste", [ac, df], 2, [])!;
    const lula = (f: FeedResultado) => f.candidatos.find((c) => c.numero === "13")!.votos;
    expect(lula(r)).toBe(lula(ac) + lula(df));
    expect(r.votos.validos).toBe(ac.votos.validos! + df.votos.validos!);
    expect(r.comparecimento.comparecimento).toBe(ac.comparecimento.comparecimento! + df.comparecimento.comparecimento!);
    expect(r.candidatos.every((c) => !c.eleito)).toBe(true);
    expect(r.candidatos[0]!.votos).toBeGreaterThanOrEqual(r.candidatos[1]!.votos);
    expect(resultadoDaRegiao(br, "Teste", [ac], 2, [])).toBeNull();
  });

  it("as partes de UF ganham percentuais e abstenção pelos feeds das UFs", () => {
    const br = feed("br");
    const completas = completarComFeedsDasUfs(
      br.partes.map((p) => ({ ...p, pcts: undefined, pct_abstencao: undefined })),
      [feed("uf-ac")],
    );
    const ac = completas.find((p) => p.codigo === "ac")!;
    expect(ac.pct_abstencao).toBe(feed("uf-ac").comparecimento.pct_abstencao);
    expect(Object.keys(ac.pcts ?? {})).toContain("13");
    expect(completas.find((p) => p.codigo === "df")!.pcts).toBeUndefined();
  });
});
