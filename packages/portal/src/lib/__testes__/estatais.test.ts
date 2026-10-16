import { describe, expect, it } from "vitest";
import {
  comoGasto,
  controlePublico,
  type CompanhiaCvm,
  type EmpresaSest,
  execucao,
  exerciciosDe,
  filtrar,
  mesAbreviado,
  ordenarPor,
  realizado,
  valorCvm,
} from "../estatais";

const ect: EmpresaSest = {
  codigo_siest: "4006", sigla: "ECT", nome: "Empresa Brasileira de Correios e Telégrafos", cnpj: "34.028.316/0001-03",
  dependente: false, grupo: null, setor: "Produtivo", capital: "Capital Fechado", natureza: "Empresa Pública",
  ministerio: "Ministério das Comunicações", situacao: "ativa", inativa_desde: null,
  exercicios: {
    "2024": { total_usos: { aprovado: 29_728_089_571, realizado: 28_230_888_138, ate_mes: 12 } },
    "2025": { total_usos: { aprovado: 30_054_073_267, realizado: 26_690_971_912, ate_mes: 12 },
              pessoal: { aprovado: 15_606_584_495, realizado: 15_210_551_820, ate_mes: 12 } },
  },
};
const ebserh: EmpresaSest = { ...ect, codigo_siest: "3612", sigla: "EBSERH", nome: "Empresa Brasileira de Serviços Hospitalares",
                              cnpj: null, dependente: true, exercicios: {} };

const petrobras = {
  cnpj: "33.000.167/0001-01", nome: "PETRÓLEO BRASILEIRO S.A. - PETROBRAS", cd_cvm: "9512", setor: "Petróleo e Gás",
  categoria: "Categoria A", uf: "RJ", municipio: "RIO DE JANEIRO", controle_declarado: "ESTATAL HOLDING",
  controle: { classe: "publico_direto", esfera: "federal", controlada_por: null, controlada_por_nome: null,
              controladores: [{ nome: "União Federal", cnpj: "00.394.460/0001-41", percentual_ordinarias: 50.26, percentual_total: 29.021 }],
              data_referencia: "2026-12-31" },
  modelo: "empresa",
  exercicios: { "2025": { documento: null, bases: {}, fim: "2025-12-31",
                          valores: { receita: { conta: "3.01", descricao: "Receita", valor: 497_549_000_000 },
                                     insumos: { conta: "7.02", descricao: "Insumos", valor: -292_210_000_000 },
                                     aquisicoes_ativos: null } } },
} as CompanhiaCvm;
const sabesp = { ...petrobras, cnpj: "43.776.517/0001-80", nome: "CIA SANEAMENTO BÁSICO ESTADO SÃO PAULO",
                 controle: { ...petrobras.controle, classe: "sem_controlador", esfera: null, controladores: [] } } as CompanhiaCvm;

describe("estatais", () => {
  it("exercícios, realizado e execução", () => {
    expect(exerciciosDe([ect, ebserh])).toEqual(["2025", "2024"]);
    expect(realizado(ect, "2025", "pessoal")).toBe(15_210_551_820);
    expect(realizado(ect, "2024", "pessoal")).toBeNull();          // ausente, não zero
    expect(execucao(ect.exercicios["2025"]!.total_usos)).toBeCloseTo(88.81, 2);
    expect(execucao({ aprovado: 0, realizado: 5, ate_mes: 12 })).toBeNull();
    expect(execucao(null)).toBeNull();
    expect(mesAbreviado(12)).toBe("dez");
    expect(mesAbreviado(null)).toBe("");
  });

  it("busca sem acento por nome, sigla, CNPJ ou controlador", () => {
    expect(filtrar([ect, ebserh], "correios").map((e) => e.sigla)).toEqual(["ECT"]);
    expect(filtrar([ect, ebserh], "servicos hospitalares").map((e) => e.sigla)).toEqual(["EBSERH"]);
    expect(filtrar([ect, ebserh], "34.028.316").map((e) => e.sigla)).toEqual(["ECT"]);
    expect(filtrar([ect, ebserh], "", (e) => e.dependente === true).map((e) => e.sigla)).toEqual(["EBSERH"]);
    expect(filtrar([petrobras, sabesp], "uniao").map((c) => c.cnpj)).toEqual([petrobras.cnpj]);
  });

  it("controle, valores e gastos como saída", () => {
    expect(controlePublico(petrobras)).toBe(true);
    expect(controlePublico(sabesp)).toBe(false);
    expect(valorCvm(petrobras, "2025", "receita")).toBe(497_549_000_000);
    expect(valorCvm(petrobras, "2025", "aquisicoes_ativos")).toBeNull();
    expect(valorCvm(petrobras, "2024", "receita")).toBeNull();
    expect(comoGasto(-292_210_000_000, true)).toBe(292_210_000_000);
    expect(comoGasto(10, false)).toBe(10);
    expect(comoGasto(null, true)).toBeNull();
  });

  it("ordena pelo valor, ausentes por último, empate pelo nome", () => {
    const lista = ordenarPor([ebserh, ect], (e) => realizado(e, "2025", "total_usos"), (e) => e.sigla);
    expect(lista.map((e) => e.sigla)).toEqual(["ECT", "EBSERH"]);
    const empate = ordenarPor([{ n: "b", v: 1 }, { n: "a", v: 1 }, { n: "c", v: null }], (x) => x.v, (x) => x.n);
    expect(empate.map((x) => x.n)).toEqual(["a", "b", "c"]);
    expect(ordenarPor([{ n: "b", v: null }, { n: "a", v: null }], (x) => x.v, (x) => x.n).map((x) => x.n)).toEqual(["a", "b"]);
  });
});
