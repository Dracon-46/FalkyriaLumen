import { describe, expect, it } from "vitest";
import { dataDaVersao, idsDasNovidades, lerChangelog, naoVistas, trechos } from "../novidades";

const CHANGELOG = `# Histórico de versões

Formato: o que mudou.

## Não lançado

### Tribunais de contas: o TCE-PR (ADR-050)

- Coleta nova, \`lumen painel tce-pr\`, no fluxo diário: os contratos dos
  municípios paranaenses.
- **Na tela**, no mandato aberto:
  - os contratos do mandato;
  - os fornecedores,
    com o link.

## 0.9.0 — 2026-10-21

### Empresa ou entidade pelo CNPJ (ADR-049)

Texto solto sem lista.

## 0.8.0 — 2026-10-15

## 0.7.0 — 2026-10-14

### Painéis (ADR-028)

- Um item.
`;

describe("novidades do CHANGELOG", () => {
  it("lê as versões, as mudanças, os itens com continuação e os subitens", () => {
    const v = lerChangelog(CHANGELOG);
    expect(v.map((x) => [x.versao, x.data, x.novidades.length])).toEqual([
      [null, null, 1], ["0.9.0", "2026-10-21", 1], ["0.7.0", "2026-10-14", 1],      // a 0.8.0 vazia some
    ]);
    const tce = v[0]!.novidades[0]!;
    expect(tce.id).toBe("no-ar/tribunais-de-contas-o-tce-pr-adr-050");
    expect(tce.itens).toEqual([
      { texto: "Coleta nova, `lumen painel tce-pr`, no fluxo diário: os contratos dos municípios paranaenses.", filhos: [] },
      { texto: "**Na tela**, no mandato aberto:", filhos: ["os contratos do mandato;", "os fornecedores, com o link."] },
    ]);
    expect(v[1]!.novidades[0]!.itens).toEqual([{ texto: "Texto solto sem lista.", filhos: [] }]);
    expect(idsDasNovidades(v)).toEqual(["no-ar/tribunais-de-contas-o-tce-pr-adr-050",
                                        "0.9.0/empresa-ou-entidade-pelo-cnpj-adr-049", "0.7.0/paineis-adr-028"]);
  });

  it("conta as mudanças desde a vista", () => {
    const ids = ["c", "b", "a"];
    expect(naoVistas(ids, null)).toBe(0);         // primeira visita: nada a avisar
    expect(naoVistas(ids, "c")).toBe(0);
    expect(naoVistas(ids, "a")).toBe(2);
    expect(naoVistas(ids, "antiga")).toBe(3);     // a vista já saiu da lista
  });

  it("separa o código e o destaque do texto", () => {
    expect(trechos("A **nova** aba `/novidades/` no ar")).toEqual([
      { tipo: "texto", valor: "A " }, { tipo: "forte", valor: "nova" }, { tipo: "texto", valor: " aba " },
      { tipo: "codigo", valor: "/novidades/" }, { tipo: "texto", valor: " no ar" },
    ]);
    expect(dataDaVersao("2026-10-21")).toBe("21/10/2026");
  });
});
