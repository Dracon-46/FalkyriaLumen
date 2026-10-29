/**
 * O eleitorado (ADR-055): a leitura dos arquivos e as contas do painel (as linhas de cada característica com o
 * comparecimento do turno, os lugares abaixo e as seções filtradas).
 *
 * Os arquivos ficam no site dos painéis (GitHub Pages), comprimidos, e não no bucket das eleições, que está perto
 * do limite gratuito: `eleitorado/<ano>/br.json.gz`, `uf-<sigla>.json.gz` e `mu/<grupo>.json.gz`, com os
 * municípios do grupo (o 3º, o 4º e o 5º dígitos do código IBGE; `zz` para o exterior).
 */

import { obterJsonComprimido } from "./comprimido";
import { memorizar } from "./feeds";
import { BASE_PAINEL } from "./paineis";
import { validarEleitorado } from "./validacao";
import type {
  ArquivoEleitorado,
  Caracteristica,
  PerfilEleitorado,
  TurnoEleitorado,
} from "./tipos";

/** Primeiro ano com o eleitorado publicado pelo Lumen (o comparecimento por perfil começa em 2018). */
export const ANO_INICIAL_ELEITORADO = 2018;

/** As características, na ordem das abas. */
export const CARACTERISTICAS: { id: Caracteristica; rotulo: string }[] = [
  { id: "faixa_etaria", rotulo: "Faixa etária" },
  { id: "genero", rotulo: "Gênero" },
  { id: "escolaridade", rotulo: "Escolaridade" },
  { id: "estado_civil", rotulo: "Estado civil" },
];

/** Percentual de `parte` em `total` (0 a 100); sem total, `null`. */
export function pct(parte: number, total: number): number | null {
  return total > 0 ? (parte / total) * 100 : null;
}

/** O turno a mostrar: o da eleição aberta, se o arquivo já o tem; senão, o mais recente publicado. */
export function turnoAMostrar(turnos: Record<string, unknown>, turnoEleicao: number | null | undefined): string | null {
  const chaves = Object.keys(turnos).sort();
  if (turnoEleicao && chaves.includes(String(turnoEleicao))) return String(turnoEleicao);
  return chaves.at(-1) ?? null;
}

/** Uma linha da tabela de uma característica: eleitores do cadastro e, no turno, aptos e comparecimento. */
export interface LinhaCaracteristica {
  rotulo: string;
  eleitores: number;
  pctEleitorado: number | null;
  aptos: number | null;
  comparecimento: number | null;
  pctComparecimento: number | null;
}

/**
 * As linhas de uma característica: o perfil (cadastro antes da eleição) e, quando há, o comparecimento no
 * turno, pelo rótulo. Categoria que só aparece num dos dois entra com o outro lado vazio.
 */
export function linhasDaCaracteristica(perfil: PerfilEleitorado, id: Caracteristica,
  turno: TurnoEleitorado | null): LinhaCaracteristica[] {
  const doTurno = new Map((turno?.[id] ?? []).map(([r, aptos, comp]) => [r, { aptos, comp }] as const));
  const linhas: LinhaCaracteristica[] = perfil[id].map(([rotulo, eleitores]) => {
    const t = doTurno.get(rotulo);
    doTurno.delete(rotulo);
    return {
      rotulo, eleitores, pctEleitorado: pct(eleitores, perfil.eleitores),
      aptos: t?.aptos ?? null, comparecimento: t?.comp ?? null, pctComparecimento: t ? pct(t.comp, t.aptos) : null,
    };
  });
  for (const [rotulo, t] of doTurno) {
    linhas.push({ rotulo, eleitores: 0, pctEleitorado: null, aptos: t.aptos, comparecimento: t.comp,
      pctComparecimento: pct(t.comp, t.aptos) });
  }
  return linhas;
}

/** Um lugar abaixo do arquivo (UF, município ou zona), com a abrangência para abri-lo quando dá. */
export interface LinhaLugar {
  chave: string;
  nome: string;
  /** Abrangência do feed (`uf-sp`, `mu-3550308`); `null` para a zona, que abre dentro do município. */
  abrangencia: string | null;
  eleitores: number;
  pctBiometria: number | null;
  pctComparecimento: number | null;
}

/** Os lugares abaixo: as UFs no Brasil, os municípios na UF, as zonas no município; em ordem de nome (zona: número). */
export function lugaresAbaixo(arquivo: ArquivoEleitorado, turno: string | null): LinhaLugar[] {
  if (arquivo.nivel === "municipio") {
    return (arquivo.zonas ?? []).map((z) => {
      const t = turno ? z.turnos[turno] : undefined;
      return { chave: z.zona, nome: `Zona ${z.zona}`, abrangencia: null, eleitores: z.eleitores,
        pctBiometria: pct(z.biometria, z.eleitores), pctComparecimento: t ? pct(t.comparecimento, t.aptos) : null };
    });
  }
  const prefixo = arquivo.nivel === "br" ? "uf-" : "mu-";
  return Object.entries(arquivo.partes ?? {})
    .map(([chave, p]) => {
      const t = turno ? p.turnos[turno] : undefined;
      return { chave, nome: p.nome, abrangencia: `${prefixo}${chave}`, eleitores: p.eleitores,
        pctBiometria: pct(p.biometria, p.eleitores), pctComparecimento: t ? pct(t[1], t[0]) : null };
    })
    .sort((a, b) => a.nome.localeCompare(b.nome, "pt-BR"));
}

/** Uma seção do município, com o nome do local de votação. */
export interface LinhaSecao {
  zona: string;
  secao: number;
  local: string;
  eleitores: number;
}

/** As seções do município, de uma zona (ou todas, com `null`), filtradas pelo nome do local (sem acento e caixa). */
export function secoesDoMunicipio(arquivo: ArquivoEleitorado, zona: string | null, termo: string): LinhaSecao[] {
  const normal = (s: string) => s.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();
  const busca = normal(termo.trim());
  return (arquivo.secoes ?? [])
    .filter(([z]) => zona === null || z === zona)
    .map(([z, secao, local, eleitores]) => ({
      zona: z, secao, eleitores, local: arquivo.locais?.[`${z}-${local}`] ?? `Local ${local}`,
    }))
    .filter((s) => !busca || normal(s.local).includes(busca) || String(s.secao) === busca);
}

/** O arquivo do grupo do município: o 3º, o 4º e o 5º dígitos do código IBGE; `zz` para as cidades do exterior. */
export function grupoDoMunicipio(chave: string): string {
  return /^\d{7}$/.test(chave) ? chave.slice(2, 5) : "zz";
}

/** Endereço do arquivo que leva o lugar (`br`, `uf-<sigla>` ou `mu-<chave>`, como a abrangência dos feeds). */
export function urlEleitorado(ano: number, abrangencia: string): string | null {
  const base = `${BASE_PAINEL}/eleitorado/${ano}`;
  if (abrangencia === "br") return `${base}/br.json.gz`;
  const uf = /^uf-([a-z]{2})$/.exec(abrangencia);
  if (uf) return `${base}/uf-${uf[1]}.json.gz`;
  const mu = /^mu-(\d{7}|zz-\d{5})$/.exec(abrangencia);
  return mu ? `${base}/mu/${grupoDoMunicipio(mu[1]!)}.json.gz` : null;
}

const cache = new Map<string, Promise<unknown>>();

/**
 * O eleitorado de um lugar num ano; `null` quando o ano ou o lugar não tem o arquivo (antes de 2018, ou
 * ainda não publicado). No município, o arquivo do grupo é lido uma vez e serve aos outros municípios dele.
 */
export async function carregarEleitorado(ano: number, abrangencia: string): Promise<ArquivoEleitorado | null> {
  const url = urlEleitorado(ano, abrangencia);
  if (!url) return null;
  const bruto = await memorizar(cache, url, () => obterJsonComprimido(url), 40);
  if (bruto === null || typeof bruto !== "object") return null;
  if (!abrangencia.startsWith("mu-")) return validarEleitorado(bruto, url);
  const grupo = bruto as { origem?: unknown; municipios?: Record<string, unknown> };
  const municipio = grupo.municipios?.[abrangencia.slice(3)];
  return municipio ? validarEleitorado({ ...(municipio as object), origem: grupo.origem ?? {} }, url) : null;
}
