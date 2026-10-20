/**
 * Painel operacional (RF-AD-05; ADR-039): o arquivo `operacao.json`, publicado com os painéis, com as execuções
 * dos fluxos de dados, o volume diário do PNCP e a coleta da conformidade. Fala do Lumen e das fontes, nunca de
 * um ente.
 */

import { BASE_PAINEL, conferir } from "./paineis";
import { obterJson } from "./feeds";

/** Um alerta: de fluxo, de volume ou de coleta da conformidade, com o link da execução quando há. */
export interface AlertaOperacao {
  tipo: "fluxo" | "volume" | "conformidade";
  texto: string;
  url: string | null;
}

/** Uma linha do quadro dos fluxos: execuções na janela, falhas, a última e a última com sucesso. */
export interface FluxoOperacao {
  fluxo: string;
  descricao: string;
  cadencia_horas: number | null;
  execucoes: number;
  falhas: number;
  canceladas: number;
  taxa_falha: number | null;
  ultima: { inicio: string; situacao: string | null; resultado: string | null; evento: string | null; url: string | null } | null;
  ultimo_sucesso: string | null;
  horas_desde_sucesso: number | null;
  atrasado: boolean;
}

/** Um dia da série do PNCP: processos e contratos publicados, a referência do dia e o alerta. */
export interface DiaVolume {
  dia: string;
  coletado: boolean;
  util: boolean;
  processos: number | null;
  contratos: number | null;
  referencia: number | null;
  alerta: string | null;
}

/** A coleta da conformidade de uma UF. */
export interface ColetaUf {
  uf: string;
  coletado_em: string | null;
  horas_desde_coleta: number | null;
  entes: number;
  coleta_malsucedida: number;
  atrasada: boolean;
}

/** Arquivo `operacao.json`. Sem as execuções (publicado fora do GitHub Actions), `fluxos` vem nulo. */
export interface Operacao {
  versao: 1;
  tipo: "operacao";
  gerado_em: string;
  parametros: {
    janela_dias: number;
    tolerancia_horas: number;
    semanas_base: number;
    fracao_minima: number;
    horas_conformidade: number;
    calibrados: boolean;
  };
  alertas: AlertaOperacao[];
  fluxos: FluxoOperacao[] | null;
  contratacoes: { dias: DiaVolume[]; faltando: string[] };
  conformidade: ColetaUf[];
}

/** Lê e confere `operacao.json`; `null` se ainda não foi publicado. */
export async function carregarOperacao(sinal?: AbortSignal): Promise<Operacao | null> {
  const url = `${BASE_PAINEL}/operacao.json`;
  const bruto = await obterJson(url, { sinal });
  return bruto === null ? null : conferir<Operacao>(bruto, "operacao", url);
}

const RESULTADOS: Record<string, string> = {
  success: "concluída",
  failure: "falhou",
  timed_out: "passou do prazo da máquina",
  startup_failure: "não começou",
  cancelled: "cancelada",
  skipped: "pulada",
};

/** O resultado de uma execução em português; sem resultado, a situação ("em andamento", "na fila"). */
export function rotuloExecucao(situacao: string | null, resultado: string | null): string {
  if (resultado) return RESULTADOS[resultado] ?? resultado;
  if (situacao === "in_progress") return "em andamento";
  if (situacao === "queued" || situacao === "waiting" || situacao === "pending") return "na fila";
  return situacao ?? "—";
}
