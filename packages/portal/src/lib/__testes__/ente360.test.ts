import { describe, expect, it } from "vitest";
import { lerArquivos, lerChave, urlArquivos } from "../documentos";
import {
  abrangenciaDoEnte,
  arquivoTransparencia,
  eleicoesDoEnte,
  estataisDoEnte,
  federaisDaSest,
  urlDoEnte,
} from "../ente360";
import type { CompanhiaCvm, FeedEstatais } from "../estatais";
import type { EleicaoIndice, Indice } from "../tipos";

describe("documentos do PNCP", () => {
  it("lê a chave dos painéis e monta o endereço da lista de arquivos", () => {
    expect(lerChave("74118514000182-1-000028/2026")).toEqual({ tipo: "compra", cnpj: "74118514000182", ano: 2026, sequencial: 28 });
    expect(lerChave("49269244000163-2-003049/2025")?.tipo).toBe("contrato");
    expect(lerChave("qualquer coisa")).toBeNull();
    expect(urlArquivos(lerChave("74118514000182-1-000028/2026")!)).toBe(
      "https://pncp.gov.br/api/pncp/v1/orgaos/74118514000182/compras/2026/28/arquivos");
    expect(urlArquivos(lerChave("49269244000163-2-003049/2025")!)).toBe(
      "https://pncp.gov.br/api/pncp/v1/orgaos/49269244000163/contratos/2025/3049/arquivos");
  });

  it("guarda só documentos ativos com endereço do PNCP (resposta real recortada)", () => {
    const docs = lerArquivos([
      { url: "https://pncp.gov.br/pncp-api/v1/orgaos/74118514000182/compras/2026/28/arquivos/1", statusAtivo: true,
        titulo: "AVISO_DE_DISPENSA_ELETRONICA_00_2026_Flaldario.pdf", tipoDocumentoNome: "Aviso de Contratação Direta",
        dataPublicacaoPncp: "2026-10-14T09:25:55" },
      { uri: "https://pncp.gov.br/pncp-api/v1/orgaos/49269244000163/contratos/2025/3049/arquivos/1", titulo: "CONTRATO.pdf",
        tipoDocumentoNome: "Contrato" },
      { url: "https://pncp.gov.br/x/2", statusAtivo: false, titulo: "removido.pdf" },
      { url: "https://outro.site/arquivo.pdf", titulo: "fora" },
      null,
    ]);
    expect(docs.map((d) => d.titulo)).toEqual(["AVISO_DE_DISPENSA_ELETRONICA_00_2026_Flaldario.pdf", "CONTRATO.pdf"]);
    expect(docs[0]!.publicado_em).toBe("2026-10-14T09:25:55");
    expect(docs[1]!.publicado_em).toBeNull();
    expect(lerArquivos({ erro: 1 })).toEqual([]);
  });
});

const cargo = (slug: string, nome: string) => ({ slug, codigo: 1, nome, tipo: "majoritario" as const, nivel: "mu" as const, vagas: 1 });
const eleicao = (id: string, data: string, turno: number, cargos: ReturnType<typeof cargo>[], extra: Partial<EleicaoIndice> = {}): EleicaoIndice => ({
  id, nome: id, ano: Number(data.slice(0, 4)), turno, tipo: "geral", data, origem: "dados_abertos", ao_vivo: false,
  atualizado_em: null, cargos, ufs: ["sp"], ...extra,
});

describe("visão 360", () => {
  const indice: Indice = {
    versao: 1, gerado_em: null,
    eleicoes: [
      eleicao("2022-1t-geral", "2022-10-02", 1, [cargo("presidente", "Presidente"), cargo("governador", "Governador")]),
      eleicao("2022-2t-geral", "2022-10-30", 2, [cargo("presidente", "Presidente"), cargo("governador", "Governador")]),
      eleicao("2024-1t-municipal", "2024-10-06", 1, [cargo("prefeito", "Prefeito"), cargo("vereador", "Vereador")]),
      eleicao("2026-1t-geral", "2026-10-04", 1, [cargo("presidente", "Presidente")]),
      eleicao("1989-1t-geral", "1989-11-15", 1, [cargo("presidente", "Presidente")], { municipios: false }),
      eleicao("2026-simulacao", "2026-12-01", 1, [cargo("presidente", "Presidente")], { simulacao: true }),
    ],
  };

  it("abrangência e arquivo da transparência pelo código", () => {
    expect(abrangenciaDoEnte("3550308", "municipio")).toBe("mu-3550308");
    expect(abrangenciaDoEnte("35", "estado")).toBe("uf-sp");
    expect(abrangenciaDoEnte("53", "df")).toBe("uf-df");
    expect(abrangenciaDoEnte("1", "uniao")).toBe("br");
    expect(abrangenciaDoEnte("99", "estado")).toBeNull();
    expect(arquivoTransparencia("3550308")).toBe("transparencia/uf-sp.json");
    expect(arquivoTransparencia("1")).toBe("transparencia/uniao.json");
    expect(arquivoTransparencia("99")).toBeNull();
    expect(urlDoEnte("3550308")).toBe("/ente/?codigo=3550308");
  });

  it("escolhe a última eleição de cada cargo, sem simulação nem eleições só por UF", () => {
    const mu = eleicoesDoEnte(indice, "3550308", "municipio");
    expect(mu.map((r) => [r.eleicao.id, r.cargo, r.abrangencia])).toEqual([
      ["2024-1t-municipal", "prefeito", "mu-3550308"], ["2026-1t-geral", "presidente", "mu-3550308"]]);
    const uf = eleicoesDoEnte(indice, "35", "estado");
    expect(uf.map((r) => [r.eleicao.id, r.cargo])).toEqual([["2022-2t-geral", "governador"], ["2026-1t-geral", "presidente"]]);
    expect(eleicoesDoEnte(indice, "1", "uniao").map((r) => r.abrangencia)).toEqual(["br"]);
    expect(eleicoesDoEnte(indice, "99", "estado")).toEqual([]);
  });

  it("estatais pela esfera do controlador e pela sede", () => {
    const c = (nome: string, esfera: string | null, uf: string, municipio: string) => ({
      cnpj: nome, nome, uf, municipio, controle: { classe: esfera ? "publico_direto" : "privado", esfera },
    }) as unknown as CompanhiaCvm;
    const feed = {
      companhias: [c("PETROBRAS", "federal", "RJ", "RIO DE JANEIRO"), c("METRÔ", "estadual", "SP", "SÃO PAULO"),
                   c("CEMIG", "estadual", "MG", "BELO HORIZONTE"), c("SPTURIS", "municipal", "SP", "SÃO PAULO"),
                   c("CEB", "distrital", "DF", "BRASÍLIA"), c("SABESP", null, "SP", "SÃO PAULO")],
      federais: { empresas: [{ situacao: "ativa" }, { situacao: "ativa" }, { situacao: "inativa" }] },
    } as unknown as FeedEstatais;
    expect(estataisDoEnte(feed, "União", null, "uniao").map((x) => x.nome)).toEqual(["PETROBRAS"]);
    expect(estataisDoEnte(feed, "São Paulo", "SP", "estado").map((x) => x.nome)).toEqual(["METRÔ"]);
    expect(estataisDoEnte(feed, "São Paulo", "SP", "municipio").map((x) => x.nome)).toEqual(["SPTURIS"]);
    expect(estataisDoEnte(feed, "Campinas", "SP", "municipio")).toEqual([]);
    expect(estataisDoEnte(feed, "Distrito Federal", "DF", "df").map((x) => x.nome)).toEqual(["CEB"]);
    expect(estataisDoEnte(feed, "x", null, null)).toEqual([]);
    expect(federaisDaSest(feed)).toBe(2);
  });
});
