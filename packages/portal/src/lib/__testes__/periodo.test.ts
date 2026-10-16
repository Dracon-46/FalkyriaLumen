import { describe, expect, it } from "vitest";
import { filtrarOpcoes } from "../escolha";
import type { ContratacoesEnte, ContratacoesPanorama } from "../paineis";
import {
  lerPeriodo,
  mesesDoArquivo,
  noPeriodo,
  paginar,
  paginasVisiveis,
  recortarMunicipios,
  recortarPanorama,
  recortarSecoes,
  somarMeses,
  temMesAMes,
  temRecorte,
  totalDePaginas,
} from "../periodo";

const mes = (m: string, processos: number, valor_estimado: number, contratos: number, valor_contratos: number) => ({
  mes: m, processos, valor_estimado, processos_sem_valor: 0, contratos, valor_contratos, valores_a_conferir: 0,
});

const ENTE: ContratacoesEnte = {
  versao: 1,
  tipo: "contratacoes-ente",
  gerado_em: "2026-10-16T00:00:00Z",
  cobertura: { de: "2026-01-02", ate: "2026-03-30", dias: 60, faltando: [] },
  ente: { codigo: "35", nome: "São Paulo", uf: "SP", tipo: "estado", populacao: 46_000_000 },
  totais: { ...mes("", 6, 600, 3, 300), orgaos: 2, fornecedores: 2 },
  meses: [mes("2026-01", 1, 100, 1, 100), mes("2026-02", 2, 200, 1, 50), mes("2026-03", 3, 300, 1, 150)],
  modalidades: [
    { codigo: 8, nome: "Dispensa", processos: 4, valor_estimado: 400, meses: [["2026-01", 1, 100], ["2026-03", 3, 300]] },
    { codigo: 6, nome: "Pregão", processos: 2, valor_estimado: 200, meses: [["2026-02", 2, 200]] },
  ],
  orgaos: [
    { cnpj: "1", nome: "A", ...mes("", 5, 500, 2, 250), meses: [["2026-01", 1, 100, 1, 100], ["2026-03", 4, 400, 1, 150]] },
    { cnpj: "2", nome: "B", ...mes("", 1, 100, 1, 50), meses: [["2026-02", 1, 100, 1, 50]] },
  ],
  fornecedores: [
    { cnpj: "11", nome: "X", contratos: 2, valor: 250, meses: [["2026-01", 1, 100], ["2026-03", 1, 150]] },
    { cnpj: "22", nome: "Y", contratos: 1, valor: 50, meses: [["2026-02", 1, 50]] },
  ],
  pessoas_fisicas: { contratos: 1, valor: 10, meses: [["2026-02", 1, 10]] },
  recentes: [
    { data: "2026-03-30", chave: "p3", orgao: "A", modalidade: "Dispensa", objeto: null, valor_estimado: 1, situacao: null, link: null },
    { data: "2026-01-10", chave: "p1", orgao: "A", modalidade: "Dispensa", objeto: null, valor_estimado: 1, situacao: null, link: null },
  ],
  contratos_recentes: [],
  a_conferir: [],
  municipios: [{ codigo: "3550308", nome: "São Paulo", processos: 6, valor_estimado: 600, contratos: 3,
                 valor_contratos: 300, meses: [["2026-02", 2, 200, 1, 50]] }],
};

describe("período", () => {
  it("lê da URL, ignora o inválido e põe em ordem", () => {
    const url = (q: string) => new URLSearchParams(q);
    expect(lerPeriodo(url("de=2026-02&ate=2026-03"))).toEqual({ de: "2026-02", ate: "2026-03" });
    expect(lerPeriodo(url("de=2026-05&ate=2026-01"))).toEqual({ de: "2026-01", ate: "2026-05" });
    expect(lerPeriodo(url("de=2026-13&ate=x"))).toEqual({ de: null, ate: null });
    expect(temRecorte({ de: null, ate: null })).toBe(false);
    expect(noPeriodo("2026-02-15", { de: "2026-02", ate: null })).toBe(true);
    expect(noPeriodo("2026-01-31", { de: "2026-02", ate: null })).toBe(false);
    expect(somarMeses([["2026-01", 1, 2], ["2026-02", 3, 4]], { de: "2026-02", ate: "2026-02" }, 2)).toEqual([3, 4]);
  });

  it("sem recorte, devolve os dados como vieram", () => {
    expect(recortarSecoes(ENTE, { de: null, ate: null })).toBe(ENTE);
    expect(mesesDoArquivo(ENTE)).toEqual(["2026-01", "2026-02", "2026-03"]);
    expect(temMesAMes(ENTE)).toBe(true);
    expect(temMesAMes({ modalidades: [{ codigo: 1, nome: "x", processos: 1, valor_estimado: 1 }], fornecedores: [] })).toBe(false);
  });

  it("refaz totais e tabelas com os meses escolhidos", () => {
    const r = recortarSecoes(ENTE, { de: "2026-02", ate: "2026-03" });
    expect([r.totais.processos, r.totais.valor_estimado, r.totais.contratos, r.totais.valor_contratos]).toEqual([5, 500, 2, 200]);
    expect(r.meses.map((m) => m.mes)).toEqual(["2026-02", "2026-03"]);
    expect(r.modalidades.map((m) => [m.nome, m.processos, m.valor_estimado])).toEqual([["Dispensa", 3, 300], ["Pregão", 2, 200]]);
    expect(r.orgaos.map((o) => [o.cnpj, o.processos, o.valor_contratos])).toEqual([["1", 4, 150], ["2", 1, 50]]);
    expect(r.fornecedores.map((f) => [f.cnpj, f.contratos, f.valor])).toEqual([["11", 1, 150], ["22", 1, 50]]);
    expect(r.totais.fornecedores).toBe(2);
    expect(r.pessoas_fisicas).toMatchObject({ contratos: 1, valor: 10 });
    expect(r.recentes.map((x) => x.chave)).toEqual(["p3"]);
    // um mês só: quem não teve movimento sai da tabela
    const jan = recortarSecoes(ENTE, { de: "2026-01", ate: "2026-01" });
    expect(jan.fornecedores.map((f) => f.cnpj)).toEqual(["11"]);
    expect(jan.orgaos.map((o) => o.cnpj)).toEqual(["1"]);
    expect(jan.pessoas_fisicas.contratos).toBe(0);
    expect(recortarMunicipios(ENTE.municipios!, { de: "2026-03", ate: null })[0]).toMatchObject({ processos: 0 });
    expect(recortarMunicipios(ENTE.municipios!, { de: "2026-02", ate: "2026-02" })[0]).toMatchObject({ processos: 2 });
  });

  it("panorama: esferas e UFs no período", () => {
    const panorama = {
      ...ENTE,
      tipo: "contratacoes-panorama",
      esferas: [{ esfera: "M", nome: "Municípios", ...mes("", 3, 0, 0, 0), meses: [["2026-01", 1, 0, 0, 0], ["2026-02", 2, 0, 0, 0]] }],
      sem_ente: mes("", 0, 0, 0, 0),
      ufs: [{ uf: "SP", estado: mes("", 1, 0, 0, 0), municipios: mes("", 2, 0, 0, 0), municipios_com_publicacao: 1,
              municipios_no_cadastro: 645, meses: [["2026-01", 1, 0], ["2026-02", 0, 2]] }],
      entes_com_publicacao: 1,
    } as unknown as ContratacoesPanorama;
    const r = recortarPanorama(panorama, { de: "2026-02", ate: null });
    expect(r.esferas[0]!.processos).toBe(2);
    expect([r.ufs[0]!.estado.processos, r.ufs[0]!.municipios.processos]).toEqual([0, 2]);
    expect(recortarPanorama(panorama, { de: null, ate: null })).toBe(panorama);
  });
});

describe("paginação", () => {
  const itens = Array.from({ length: 45 }, (_, i) => i + 1);
  it("20 por página, limitada ao intervalo", () => {
    expect(totalDePaginas(45)).toBe(3);
    expect(totalDePaginas(0)).toBe(1);
    expect(paginar(itens, 1)).toHaveLength(20);
    expect(paginar(itens, 3)).toEqual([41, 42, 43, 44, 45]);
    expect(paginar(itens, 99)).toEqual([41, 42, 43, 44, 45]);
    expect(paginar(itens, 0)[0]).toBe(1);
  });
  it("números visíveis com saltos", () => {
    expect(paginasVisiveis(1, 3)).toEqual([1, 2, 3]);
    expect(paginasVisiveis(5, 10)).toEqual([1, null, 4, 5, 6, null, 10]);
    expect(paginasVisiveis(1, 10)).toEqual([1, 2, null, 10]);
  });
});

describe("caixa de escolha", () => {
  const opcoes = [
    { valor: "a", rotulo: "Presidente · 2022", grupo: "Por estado e município" },
    { valor: "b", rotulo: "Governador · 2018", grupo: "Por estado e município" },
    { valor: "c", rotulo: "Senado 1950", grupo: "1933 a 1990: só por estado" },
  ];
  it("todas as palavras, sem acento nem caixa, no rótulo, grupo ou detalhe", () => {
    expect(filtrarOpcoes(opcoes, "").map((o) => o.valor)).toEqual(["a", "b", "c"]);
    expect(filtrarOpcoes(opcoes, "pres 2022").map((o) => o.valor)).toEqual(["a"]);
    expect(filtrarOpcoes(opcoes, "SÓ POR ESTADO").map((o) => o.valor)).toEqual(["c"]);
    expect(filtrarOpcoes(opcoes, "municipio").map((o) => o.valor)).toEqual(["a", "b"]);
    expect(filtrarOpcoes(opcoes, "prefeito")).toEqual([]);
  });
});
