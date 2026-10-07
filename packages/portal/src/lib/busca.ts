/** Busca de municípios e UFs para o atalho Ctrl+K. */

import type { Municipio } from "./tipos";

/** Nome de cada UF pela sigla em minúsculas, como nos feeds; "zz" é o exterior. */
export const UFS: Record<string, string> = {
  ac: "Acre", al: "Alagoas", am: "Amazonas", ap: "Amapá", ba: "Bahia", ce: "Ceará", df: "Distrito Federal",
  es: "Espírito Santo", go: "Goiás", ma: "Maranhão", mg: "Minas Gerais", ms: "Mato Grosso do Sul",
  mt: "Mato Grosso", pa: "Pará", pb: "Paraíba", pe: "Pernambuco", pi: "Piauí", pr: "Paraná",
  rj: "Rio de Janeiro", rn: "Rio Grande do Norte", ro: "Rondônia", rr: "Roraima", rs: "Rio Grande do Sul",
  sc: "Santa Catarina", se: "Sergipe", sp: "São Paulo", to: "Tocantins", zz: "Exterior",
};

/** Código IBGE de 2 dígitos ↔ sigla (o mapa do Brasil usa o código). */
export const CODIGO_UF: Record<string, string> = {
  "11": "ro", "12": "ac", "13": "am", "14": "rr", "15": "pa", "16": "ap", "17": "to", "21": "ma", "22": "pi",
  "23": "ce", "24": "rn", "25": "pb", "26": "pe", "27": "al", "28": "se", "29": "ba", "31": "mg", "32": "es",
  "33": "rj", "35": "sp", "41": "pr", "42": "sc", "43": "rs", "50": "ms", "51": "mt", "52": "go", "53": "df",
};

/** Sem acento, minúsculas, espaço único: "São Paulo" e "sao  paulo" casam. */
export function normalizar(texto: string): string {
  return texto
    .normalize("NFD")
    .replace(/\p{M}/gu, "")
    .toLowerCase()
    .replace(/[^a-z0-9 ]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/** Um item da lista de resultados da busca: o que mostrar e para onde navegar. */
export interface Achado {
  tipo: "uf" | "mu";
  /** Nome do arquivo do feed: "uf-sp" ou "mu-3550308". */
  abrangencia: string;
  /** Nome do estado ou do município. */
  rotulo: string;
  /** Linha secundária: "Estado", ou o nome da UF do município (e "capital"). */
  detalhe: string;
  uf: string;
}

/** Chave do município nos feeds: código IBGE no Brasil; no exterior, que não tem IBGE, "zz-<código TSE>". */
export function chaveMunicipio(m: Municipio): string {
  return m.ibge ?? `${m.uf}-${m.tse}`;
}

/**
 * Até `limite` resultados: UFs primeiro, depois municípios; dentro de cada
 * grupo, quem começa com o termo vem antes de quem só o contém, e capitais
 * antes das demais.
 */
export function buscar(termo: string, municipios: Municipio[], limite = 12): Achado[] {
  const t = normalizar(termo);
  if (!t) return [];
  const ufs: Achado[] = Object.entries(UFS)
    .filter(([sigla, nome]) => sigla === t || normalizar(nome).startsWith(t))
    .map(([sigla, nome]) => ({ tipo: "uf", abrangencia: `uf-${sigla}`, rotulo: nome, detalhe: "Estado", uf: sigla }));
  const pontuados: { m: Municipio; p: number }[] = [];
  for (const m of municipios) {
    const n = normalizar(m.nome);
    const pos = n.indexOf(t);
    if (pos < 0) continue;
    const comeca = pos === 0 || n[pos - 1] === " ";
    pontuados.push({ m, p: (pos === 0 ? 0 : comeca ? 1 : 2) * 2 + (m.capital ? 0 : 1) });
  }
  pontuados.sort((a, b) => a.p - b.p || a.m.nome.localeCompare(b.m.nome, "pt-BR"));
  const mus: Achado[] = pontuados.map(({ m }) => ({
    tipo: "mu",
    abrangencia: `mu-${chaveMunicipio(m)}`,
    rotulo: m.nome,
    detalhe: `${UFS[m.uf] ?? m.uf.toUpperCase()}${m.capital ? " · capital" : ""}`,
    uf: m.uf,
  }));
  return [...ufs, ...mus].slice(0, limite);
}
