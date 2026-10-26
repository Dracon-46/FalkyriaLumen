import { describe, expect, it } from "vitest";
import { urls } from "../feeds";
import { ErroFeed, validarConferencia } from "../validacao";

const linha = { rotulo: "LULA", numero: "13", detalhe: null, secoes: 10, divulgado: 10, diferenca: 0 };
const feed = {
  versao: 1,
  tipo: "conferencia",
  secoes: { no_arquivo: 1, divulgadas: 1 },
  brasil: { conferida: true, confere: true, linhas: [linha] },
  ufs: [{ uf: "sp", nome: "São Paulo", secoes: 1, secoes_divulgadas: 1, conferida: true, confere: true, linhas: [linha] }],
  confere: true,
};

describe("conferência seção a seção", () => {
  it("valida o feed e recusa outro tipo", () => {
    expect(validarConferencia(feed).brasil.linhas[0]!.secoes).toBe(10);
    expect(() => validarConferencia({ ...feed, tipo: "resultado" })).toThrow(ErroFeed);
    expect(() => validarConferencia({ ...feed, brasil: { linhas: "x" } })).toThrow(ErroFeed);
  });
  it("fica ao lado dos feeds do cargo", () => {
    expect(urls.conferencia("2026-1t-geral", "presidente")).toMatch(/\/2026-1t-geral\/presidente\/conferencia\.json$/);
  });
});
