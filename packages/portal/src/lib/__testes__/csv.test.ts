import { describe, expect, it } from "vitest";
import { celulaCsv, nomeDoArquivo, paraCsv } from "../csv";

describe("CSV das tabelas", () => {
  it("escreve número com vírgula decimal, sem milhar e com duas casas no máximo", () => {
    expect(celulaCsv(1234567.891)).toBe("1234567,89");
    expect(celulaCsv(0.1 + 0.2)).toBe("0,3");
    expect(celulaCsv(42)).toBe("42");
    expect(celulaCsv(-150.5)).toBe("-150,5");
    expect(celulaCsv(Number.NaN)).toBe("");
    expect(celulaCsv(null)).toBe("");
  });

  it("põe aspas quando o texto tem separador, aspas ou quebra, e não deixa texto virar fórmula", () => {
    expect(celulaCsv("CONSTRUTORA X; Y")).toBe('"CONSTRUTORA X; Y"');
    expect(celulaCsv('O "BOM" PREÇO')).toBe('"O ""BOM"" PREÇO"');
    expect(celulaCsv("linha\noutra")).toBe('"linha\noutra"');
    expect(celulaCsv("=HYPERLINK(1)")).toBe("'=HYPERLINK(1)");
    expect(celulaCsv("-compra")).toBe("'-compra");
    expect(celulaCsv("Porto Alegre")).toBe("Porto Alegre");
  });

  it("monta as linhas com as colunas na frente e o nome do arquivo sem acento", () => {
    expect(paraCsv(["CNPJ", "Valor"], [["00394460000141", 10.5], ["", null]])).toBe(
      "CNPJ;Valor\r\n00394460000141;10,5\r\n;\r\n",
    );
    expect(nomeDoArquivo("contratacoes-4314902", null, "Órgãos e entidades")).toBe(
      "lumen-contratacoes-4314902-orgaos-e-entidades.csv",
    );
    expect(nomeDoArquivo("", "fornecedores")).toBe("lumen-fornecedores.csv");
  });
});
