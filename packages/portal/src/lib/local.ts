/**
 * O local escolhido (União, estado, DF ou município), que filtra todas as abas do portal (ADR-035).
 *
 * Não há página própria: a pessoa escolhe o local no cabeçalho, ou entra num município ou estado em qualquer
 * aba, e as outras abas passam a abrir já nele: Eleições no mapa do município, Contratações e Conformidade no
 * ente, as estatais filtradas pelas que ele controla. O local fica na URL de cada aba e, entre uma visita e
 * outra, na memória do navegador.
 */

import { CODIGO_UF } from "./busca";
import { tipoDoCodigo } from "./paineis";

/** O local escolhido: código IBGE (1 para a União), nome e UF. */
export interface Local {
  codigo: string;
  nome: string;
  uf: string | null;
}

/** As áreas do portal que o local filtra. */
export type Area = "eleicoes" | "contratacoes" | "conformidade" | "economia" | "estatais";

const CHAVE_MEMORIA = "lumen.local";
const CODIGO = /^(1|\d{2}|\d{7})$/;

/** Sigla da UF em minúsculas pelo código de 2 dígitos ("35" → "sp"). */
function siglaDaUf(codigo: string): string | null {
  return CODIGO_UF[codigo.slice(0, 2)] ?? null;
}

/** Código IBGE da UF pela sigla ("sp" → "35"). */
export function codigoDaUf(sigla: string): string | null {
  return Object.entries(CODIGO_UF).find(([, s]) => s === sigla.toLowerCase())?.[0] ?? null;
}

/**
 * O endereço da aba já filtrado pelo local. Sem local, o da aba no Brasil. Eleições abrem no mapa do município
 * ou do estado (a eleição e o cargo de `atual`, se houver); a União não tem página de conformidade.
 */
export function hrefDaArea(area: Area, local: Local | null, atual?: URLSearchParams): string {
  const base = { eleicoes: "/eleicoes/", contratacoes: "/contratacoes/", conformidade: "/conformidade/",
                 economia: "/economia/", estatais: "/economia/estatais/" }[area];
  if (!local || !CODIGO.test(local.codigo)) return base;
  const tipo = tipoDoCodigo(local.codigo);
  if (area === "eleicoes") {
    const p = new URLSearchParams();
    for (const k of ["e", "c"]) if (atual?.get(k)) p.set(k, atual.get(k)!);
    if (tipo === "municipio") p.set("a", `mu-${local.codigo}`);
    else if (tipo === "estado" || tipo === "df") {
      const uf = siglaDaUf(local.codigo);
      if (uf) p.set("a", `uf-${uf}`);
    }
    const q = p.toString();
    return q ? `${base}?${q}` : base;
  }
  if (area === "economia") return base;
  if (area === "conformidade" && tipo === "uniao") return base;
  return `${base}?ente=${local.codigo}`;
}

/**
 * O local que a URL da aba aberta indica, ou `null` se ela está no Brasil ou não é de uma área com local:
 * `?ente=` em Contratações, Conformidade e Estatais; `?uf=` em Conformidade; `?a=mu-…` ou `?a=uf-…` em Eleições.
 * Só o código: o nome vem do cadastro.
 */
export function codigoNaUrl(caminho: string, params: URLSearchParams): string | null {
  const ente = params.get("ente");
  if (/^\/(contratacoes|conformidade|economia\/estatais|economia\/municipio)\/?$/.test(caminho) && ente &&
      CODIGO.test(ente)) return ente;
  if (/^\/conformidade\/?$/.test(caminho)) {
    const uf = params.get("uf");
    return uf ? codigoDaUf(uf) : null;
  }
  if (/^\/eleicoes\/?$/.test(caminho)) {
    const a = params.get("a") ?? "";
    const mu = /^mu-(\d{7})$/.exec(a);
    if (mu) return mu[1]!;
    const uf = /^uf-([a-z]{2})$/.exec(a);
    if (uf) return codigoDaUf(uf[1]!);
  }
  return null;
}

/** O local guardado no navegador, ou `null` (sem memória, em janela privada, ou valor estranho). */
export function lerMemoria(): Local | null {
  try {
    const bruto = window.localStorage.getItem(CHAVE_MEMORIA);
    if (!bruto) return null;
    const x = JSON.parse(bruto) as Partial<Local>;
    return x && typeof x.codigo === "string" && CODIGO.test(x.codigo) && typeof x.nome === "string"
      ? { codigo: x.codigo, nome: x.nome, uf: typeof x.uf === "string" ? x.uf : null } : null;
  } catch {
    return null;
  }
}

/** Guarda (ou apaga, com `null`) o local no navegador; sem memória disponível, só não guarda. */
export function gravarMemoria(local: Local | null): void {
  try {
    if (local) window.localStorage.setItem(CHAVE_MEMORIA, JSON.stringify(local));
    else window.localStorage.removeItem(CHAVE_MEMORIA);
  } catch {
    // janela privada ou armazenamento bloqueado: o local vale só pela URL
  }
}

/** Avisa as abas abertas na mesma página que o local mudou. */
export const EVENTO_LOCAL = "lumen:local";
