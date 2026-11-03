import { describe, expect, it } from "vitest";
import { ordenar, proximaOrdem } from "../ordem";

const linhas = [{ n: "Évora", v: 10 }, { n: "abaré", v: null }, { n: "Bagé", v: 30 }, { n: "Acará", v: 20 }];
const valores = { nome: (l: (typeof linhas)[number]) => l.n, valor: (l: (typeof linhas)[number]) => l.v };

describe("ordenação das tabelas", () => {
  it("ordena número e texto nos dois sentidos, com o vazio sempre no fim", () => {
    expect(ordenar(linhas, { coluna: "valor", sentido: "desc" }, valores).map((l) => l.v)).toEqual([30, 20, 10, null]);
    expect(ordenar(linhas, { coluna: "valor", sentido: "asc" }, valores).map((l) => l.v)).toEqual([10, 20, 30, null]);
    expect(ordenar(linhas, { coluna: "nome", sentido: "asc" }, valores).map((l) => l.n)).toEqual(["abaré", "Acará", "Bagé", "Évora"]);
  });

  it("sem ordem ou com coluna desconhecida, mantém a lista como veio, sem mudar a original", () => {
    expect(ordenar(linhas, null, valores)).toEqual(linhas);
    expect(ordenar(linhas, { coluna: "x", sentido: "asc" }, valores)).not.toBe(linhas);
  });

  it("clicar na mesma coluna inverte; noutra, começa pelo sentido padrão dela", () => {
    expect(proximaOrdem(null, "valor", "desc")).toEqual({ coluna: "valor", sentido: "desc" });
    expect(proximaOrdem({ coluna: "valor", sentido: "desc" }, "valor", "desc")).toEqual({ coluna: "valor", sentido: "asc" });
    expect(proximaOrdem({ coluna: "valor", sentido: "asc" }, "nome", "asc")).toEqual({ coluna: "nome", sentido: "asc" });
  });
});
