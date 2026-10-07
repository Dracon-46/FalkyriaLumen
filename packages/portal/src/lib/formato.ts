/** Números, percentuais e datas no padrão brasileiro. */

const inteiro = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 });
const pct2 = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const compacto = new Intl.NumberFormat("pt-BR", { notation: "compact", maximumFractionDigits: 1 });

/** Inteiro com separador de milhar: 1234567 → "1.234.567"; ausente → "—". */
export function numero(valor: number | null | undefined): string {
  return valor === null || valor === undefined ? "—" : inteiro.format(valor);
}

/** Forma curta para espaço apertado: 1500000 → "1,5 mi"; ausente → "—". */
export function numeroCompacto(valor: number | null | undefined): string {
  return valor === null || valor === undefined ? "—" : compacto.format(valor);
}

/** 47.027772 → "47,03%". */
export function percentual(valor: number | null | undefined): string {
  return valor === null || valor === undefined ? "—" : `${pct2.format(valor)}%`;
}

const dataHora = new Intl.DateTimeFormat("pt-BR", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  timeZone: "America/Sao_Paulo",
});
const soData = new Intl.DateTimeFormat("pt-BR", {
  day: "numeric",
  month: "long",
  year: "numeric",
  timeZone: "UTC",
});
const soHora = new Intl.DateTimeFormat("pt-BR", { hour: "2-digit", minute: "2-digit", timeZone: "America/Sao_Paulo" });

/** ISO com fuso → "05/10/2026, 02:58:39" no horário de Brasília. */
export function instante(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : dataHora.format(d);
}

/** ISO com fuso → "20:15", só hora e minuto, no horário de Brasília. */
export function hora(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : soHora.format(d);
}

/** "2026-10-04" → "4 de outubro de 2026". A data da eleição não tem fuso. */
export function dataPorExtenso(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(`${iso.slice(0, 10)}T00:00:00Z`);
  return Number.isNaN(d.getTime()) ? "—" : soData.format(d);
}

/** Há quanto tempo, para o selo "atualizado há 2 min". */
export function haQuanto(iso: string | null | undefined, agora: Date = new Date()): string {
  if (!iso) return "";
  const d = new Date(iso);
  const s = Math.round((agora.getTime() - d.getTime()) / 1000);
  if (Number.isNaN(s)) return "";
  if (s < 0) return "agora";
  if (s < 60) return "há menos de 1 min";
  if (s < 3600) return `há ${Math.floor(s / 60)} min`;
  if (s < 86400) return `há ${Math.floor(s / 3600)} h`;
  const dias = Math.floor(s / 86400);
  return dias === 1 ? "há 1 dia" : `há ${inteiro.format(dias)} dias`;
}

/** Iniciais para o lugar da foto: "FLAVIO BOLSONARO" → "FB". */
export function iniciais(nome: string): string {
  const partes = nome
    .replace(/[^\p{L}\s]/gu, " ")
    .split(/\s+/)
    .filter((p) => p.length > 2 || /^[A-ZÀ-Ú]$/.test(p));
  const primeira = partes[0]?.[0] ?? nome[0] ?? "?";
  const ultima = partes.length > 1 ? (partes[partes.length - 1]?.[0] ?? "") : "";
  return (primeira + ultima).toUpperCase();
}
