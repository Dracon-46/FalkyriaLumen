/**
 * Filtro de período da Conformidade: os resumos refeitos só com os exercícios escolhidos.
 *
 * Os arquivos trazem, além do resumo de todos os exercícios coletados, o resumo de cada um (`por_exercicio`).
 * No período, as contagens dos exercícios que ele toca são somadas e a fração no prazo é recalculada; na tela
 * do ente, as obrigações são filtradas pelo exercício. Arquivo antigo, sem o resumo por exercício, fica como
 * veio (o filtro não aparece nele).
 */

import type { ConformidadeEnte, ConformidadePanorama, ConformidadeUf, ResumoConformidade } from "./paineis";
import { anoNoPeriodo, type PeriodoMeses, temRecorte } from "./periodo";

const VAZIO: ResumoConformidade = { cumpre: 0, cumpre_parcialmente: 0, nao_cumpre: 0, indeterminado: 0, avaliaveis: 0, no_prazo: null };

/** Soma resumos e recalcula a fração no prazo (entregues no prazo ÷ avaliáveis). */
export function somarResumos(lista: ResumoConformidade[]): ResumoConformidade {
  const r = lista.reduce((s, x) => ({
    ...s, cumpre: s.cumpre + x.cumpre, cumpre_parcialmente: s.cumpre_parcialmente + x.cumpre_parcialmente,
    nao_cumpre: s.nao_cumpre + x.nao_cumpre, indeterminado: s.indeterminado + x.indeterminado,
    avaliaveis: s.avaliaveis + x.avaliaveis,
  }), { ...VAZIO });
  return { ...r, no_prazo: r.avaliaveis ? Math.round((r.cumpre / r.avaliaveis) * 10_000) / 10_000 : null };
}

/** O resumo no período a partir do resumo por exercício; sem ele, o resumo de todos os exercícios. */
export function resumoNoPeriodo(geral: ResumoConformidade, porExercicio: Record<string, ResumoConformidade> | undefined,
                                p: PeriodoMeses): ResumoConformidade {
  if (!temRecorte(p) || !porExercicio) return geral;
  return somarResumos(Object.entries(porExercicio).filter(([ano]) => anoNoPeriodo(ano, p)).map(([, r]) => r));
}

/** Os exercícios que o arquivo tem, do mais antigo ao mais recente (as opções do filtro). */
export function exerciciosDoArquivo(dados: ConformidadePanorama | ConformidadeUf | ConformidadeEnte): string[] {
  const anos = new Set<string>();
  if (dados.tipo === "conformidade-panorama") Object.keys(dados.brasil_por_exercicio ?? {}).forEach((a) => anos.add(a));
  else if (dados.tipo === "conformidade-uf") dados.entes.forEach((e) => Object.keys(e.por_exercicio ?? {}).forEach((a) => anos.add(a)));
  else if (dados.por_exercicio) dados.obrigacoes.forEach((o) => anos.add(String(o.exercicio)));
  return [...anos].sort();
}

/** Qualquer das três telas refeita no período. */
export function recortarConformidade<T extends ConformidadePanorama | ConformidadeUf | ConformidadeEnte>(dados: T, p: PeriodoMeses): T {
  if (!temRecorte(p)) return dados;
  const s = (r: ResumoConformidade, pe?: Record<string, ResumoConformidade>) => resumoNoPeriodo(r, pe, p);
  if (dados.tipo === "conformidade-panorama") {
    const d = dados as ConformidadePanorama;
    return {
      ...d, brasil: s(d.brasil, d.brasil_por_exercicio),
      criterios: d.criterios.map((c) => ({ ...c, ...s(c, c.por_exercicio) })),
      ufs: d.ufs.map((u) => ({ ...u, ...s(u, u.por_exercicio) })),
    } as T;
  }
  if (dados.tipo === "conformidade-uf") {
    const d = dados as ConformidadeUf;
    return { ...d, entes: d.entes.map((e) => ({ ...e, ...s(e, e.por_exercicio) })) } as T;
  }
  const d = dados as ConformidadeEnte;
  if (!d.por_exercicio) return dados;
  return { ...d, resumo: s(d.resumo, d.por_exercicio), obrigacoes: d.obrigacoes.filter((o) => anoNoPeriodo(o.exercicio, p)) } as T;
}
