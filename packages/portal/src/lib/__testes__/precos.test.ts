import { afterEach, describe, expect, it, vi } from "vitest";
import { lerItens } from "../contratacao";
import {
  carregarComparacao, compararPreco, type CompraComparavel, escoreRobusto, type ItemParaComparar, lerCompras, mesmaUnidade,
  urlPrecos,
} from "../precos";

afterEach(() => vi.unstubAllGlobals());

const ITEM: ItemParaComparar = {
  catalogo: "1422", material: false, unidade: "Metro Quadrado", preco: 244.86, tipoPreco: "estimado",
  data: "2026-10-16", uasg: "193008", numeroCompra: "36", ano: 2026,
};

/** Uma compra fictícia da pesquisa de preços, no formato da API. */
function bruta(preco: number, extra: Record<string, unknown> = {}) {
  return {
    idCompra: "98337103900062026", numeroItemCompra: 1, codigoItemCatalogo: 1422, nomeUnidadeMedida: "METRO QUADRADO",
    siglaUnidadeMedida: "M2", quantidade: 1000.0, precoUnitario: preco, niFornecedor: "12345678000190",
    nomeFornecedor: "EMPRESA FICTÍCIA LTDA", nomeOrgao: "PREFEITURA FICTÍCIA", municipio: "FICTÍCIA", estado: "BA",
    esfera: "M", dataCompra: "2026-09-01", dataResultado: "2026-09-02", ...extra,
  };
}

const compras = (precos: number[], extra: Record<string, unknown> = {}): CompraComparavel[] =>
  lerCompras({ resultado: precos.map((p) => bruta(p, extra)) });

describe("leitura da pesquisa de preços", () => {
  it("lê o código do catálogo só do Compras.gov.br e o tipo do item", () => {
    const [a, b, c] = lerItens([
      { numeroItem: 1, materialOuServico: "S", catalogo: { id: 1, nome: "Catálogo do Compras.gov.br" }, catalogoCodigoItem: "1422" },
      { numeroItem: 2, materialOuServico: "M", catalogo: null, catalogoCodigoItem: null },
      { numeroItem: 3, materialOuServico: "M", catalogo: { id: 9, nome: "Outro" }, catalogoCodigoItem: "77" },
    ]);
    expect([a!.catalogo, a!.material]).toEqual(["1422", false]);
    expect([b!.catalogo, b!.material]).toEqual([null, true]);
    expect(c!.catalogo).toBeNull();
  });

  it("guarda o id da compra inteiro mesmo quando a API o manda como número grande, e esconde pessoa física", () => {
    const [m, pf] = lerCompras({ resultado: [
      { idCompra: 93115006000202026, idCompraItem: "9311500600020202600001", precoUnitario: 13, nomeUnidadeFornecimento: "GARRAFÃO",
        capacidadeUnidadeFornecimento: 20, niFornecedor: "12345678000190", nomeFornecedor: "EMPRESA FICTÍCIA LTDA" },
      { idCompra: "1", precoUnitario: 10, niFornecedor: "12345678901", nomeFornecedor: "PESSOA FICTÍCIA" },
    ] });
    expect(m!.idCompra).toBe("93115006000202026");
    expect(m!.capacidade).toBe(20);
    expect(m!.fornecedor?.cnpj).toBe("12345678000190");
    expect(pf!.fornecedor).toBeNull();
    expect(lerCompras({ erro: 1 })).toEqual([]);
  });

  it("casa a unidade pelo nome, pela sigla e pela capacidade", () => {
    expect(mesmaUnidade("Metro Quadrado", { unidade: "METRO QUADRADO", capacidade: null })).toBe(true);
    expect(mesmaUnidade("Unidade", { unidade: "UN", capacidade: null })).toBe(true);
    expect(mesmaUnidade("Garrafão 20,00 L", { unidade: "GARRAFÃO", capacidade: 20 })).toBe(true);
    expect(mesmaUnidade("Garrafão 10,00 L", { unidade: "GARRAFÃO", capacidade: 20 })).toBe(false);
    expect(mesmaUnidade("Unidade", { unidade: "METRO QUADRADO", capacidade: null })).toBe(false);
    expect(mesmaUnidade(null, { unidade: "UNIDADE", capacidade: null })).toBe(false);
  });

  it("monta o endereço pelo caminho do portal, material e serviço", () => {
    expect(urlPrecos(ITEM, "2025-10-16", "2026-10-16", 2)).toBe(
      "/api/precos/servico/?pagina=2&tamanhoPagina=500&codigoItemCatalogo=1422&dataCompraInicio=2025-10-16&dataCompraFim=2026-10-16");
    expect(urlPrecos({ catalogo: "445485", material: true }, "a", "b", 1)).toContain(
      "/api/precos/material/?pagina=1&tamanhoPagina=500&tipo=codigoItemCatalogo&codigo=445485");
  });
});

describe("comparação (DOC-07, A-01)", () => {
  const faixa = Array.from({ length: 40 }, (_, i) => 150 + i); // 150 a 189, mediana 169,5

  it("tira da conta outra unidade, o total lançado como unitário, a própria compra e o sem preço", () => {
    const lista = [
      ...compras(faixa),
      ...compras([838802.5, 720010], { quantidade: 1 }),
      ...compras([300], { nomeUnidadeMedida: "UNIDADE" }),
      ...compras([250], { idCompra: "19300806000362026" }),
      ...compras([0]),
    ];
    const c = compararPreco(ITEM, lista, "2025-10-16");
    expect(c.n).toBe(40);
    expect(c.descartados).toEqual({ outraUnidade: 1, totalComoUnitario: 2, semPreco: 1, propriaCompra: 1 });
    expect(c.mediana).toBe(169.5);
    expect(c.razao).toBeCloseTo(244.86 / 169.5);
    expect(c.situacao).toBe("acima");
    expect(c.acimaDe).toBe(1);
  });

  it("dentro da faixa, abaixo, poucas, fora de escala e sem comparáveis", () => {
    expect(compararPreco({ ...ITEM, preco: 172 }, compras(faixa), "x").situacao).toBe("dentro");
    expect(compararPreco({ ...ITEM, preco: 60 }, compras(faixa), "x").situacao).toBe("abaixo");
    expect(compararPreco(ITEM, compras(faixa.slice(0, 10)), "x").situacao).toBe("poucas");
    expect(compararPreco({ ...ITEM, preco: 5000 }, compras(faixa), "x").situacao).toBe("fora_de_escala");
    const vazia = compararPreco(ITEM, compras([10, 20], { nomeUnidadeMedida: "UNIDADE" }), "x");
    expect(vazia.situacao).toBe("sem_comparaveis");
    expect(vazia.unidadeMaisComum).toBe("UNIDADE");
  });

  it("quantidade 1 vale em unidade que não se divide", () => {
    const c = compararPreco({ ...ITEM, unidade: "Unidade" }, compras(faixa, { nomeUnidadeMedida: "UNIDADE", quantidade: 1 }), "x");
    expect(c.n).toBe(40);
  });

  it("escore robusto com MAD e, quando a maioria dos preços é igual, com a distância média à mediana", () => {
    expect(escoreRobusto(10, [8, 9, 10, 11, 12])).toBeCloseTo(0);
    expect(escoreRobusto(20, [8, 9, 10, 11, 12])).toBeCloseTo(0.6745 * 10 / 1);
    expect(escoreRobusto(20, [10, 10, 10, 10, 30])).toBeCloseTo(10 / (1.253314 * 4));
    expect(escoreRobusto(10, [10, 10, 10])).toBeNull();
  });

  it("pede as páginas que faltam (até 4) e junta", async () => {
    const urls: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      urls.push(url);
      return Response.json({ resultado: faixa.map((p) => bruta(p)), totalPaginas: 9 });
    }));
    const c = await carregarComparacao(ITEM);
    expect(urls).toHaveLength(4);
    expect(urls[0]).toContain("dataCompraInicio=2025-10-16&dataCompraFim=2026-10-16");
    expect(c.n).toBe(160);
  });

  it("erro da fonte vira erro de feed", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("x", { status: 403 })));
    await expect(carregarComparacao(ITEM)).rejects.toThrow("respondeu 403");
  });
});
