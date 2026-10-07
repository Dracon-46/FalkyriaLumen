/**
 * Regras de navegação da aba: o que abrir quando a URL não diz tudo, e qual
 * arquivo ler para cada combinação de cargo e abrangência.
 *
 * | cargo disputado em | Brasil       | UF                    | município |
 * |--------------------|--------------|-----------------------|-----------|
 * | Brasil (Presidente)| resultado    | resultado             | resultado |
 * | UF (Governador...) | panorama     | resultado             | resultado |
 * | município          | panorama     | panorama              | resultado |
 *
 * "Panorama" é o placar por partido com o líder de cada parte; "resultado"
 * é a lista de candidatos com votos. Os dois têm `partes`, que pintam o mapa.
 */

import type { CargoFeed, EleicaoIndice, Indice, Selecao } from "./tipos";

/** A eleição pedida; sem ela (ou não encontrada), a primeira ao vivo; senão, a primeira do índice. */
export function escolherEleicao(indice: Indice, id: string | null): EleicaoIndice | null {
  const lista = indice.eleicoes;
  if (!lista.length) return null;
  return lista.find((e) => e.id === id) ?? lista.find((e) => e.ao_vivo) ?? lista[0] ?? null;
}

/** O cargo pedido; sem ele (ou não encontrado), o primeiro da eleição. */
export function escolherCargo(eleicao: EleicaoIndice, slug: string | null): CargoFeed | null {
  return eleicao.cargos.find((c) => c.slug === slug) ?? eleicao.cargos[0] ?? null;
}

/** Cargo disponível na abrangência? (Deputado Distrital só no DF, por exemplo.) */
export function cargoNaAbrangencia(cargo: CargoFeed, uf: string | null): boolean {
  if (!uf || !cargo.ufs || cargo.nivel === "br") return true;
  return cargo.ufs.includes(uf);
}

/** Abrangência válida para o cargo; município de cargo municipal fica, o resto cai para o Brasil. */
export function ajustarAbrangencia(cargo: CargoFeed, abrangencia: string, uf: string | null): string {
  if (abrangencia === "br") return "br";
  if (uf && !cargoNaAbrangencia(cargo, uf)) return "br";
  return abrangencia;
}

/** As duas telas possíveis, uma por tipo de feed (ver a tabela no início do arquivo). */
export type TipoTela = "resultado" | "panorama";

/**
 * Panorama quando a abrangência está acima do nível em que o cargo é
 * disputado (governador visto do Brasil, prefeito visto da UF); resultado
 * nos demais casos. É a tabela do início do arquivo em forma de código.
 */
export function tipoDeTela(cargo: CargoFeed, abrangencia: string): TipoTela {
  const nivelAbr = abrangencia === "br" ? 0 : abrangencia.startsWith("uf-") ? 1 : 2;
  const nivelCargo = cargo.nivel === "br" ? 0 : cargo.nivel === "uf" ? 1 : 2;
  return nivelAbr < nivelCargo ? "panorama" : "resultado";
}

/** Abrangência "acima" da atual, para o botão de voltar: município → UF → Brasil. */
export function abrangenciaAcima(abrangencia: string, ufDoMunicipio: string | null): string {
  if (abrangencia.startsWith("mu-")) return ufDoMunicipio ? `uf-${ufDoMunicipio}` : "br";
  return "br";
}

/** Preenche eleição e cargo que a URL não trouxe; com o índice vazio, limpa os dois e volta ao Brasil. */
export function selecaoCompleta(indice: Indice, s: Selecao): Selecao {
  const e = escolherEleicao(indice, s.eleicao);
  if (!e) return { ...s, eleicao: null, cargo: null, abrangencia: "br" };
  const c = escolherCargo(e, s.cargo);
  return { ...s, eleicao: e.id, cargo: c?.slug ?? null };
}

/**
 * Eleições do seletor em grupos, na ordem do índice: sem grupo quando todas
 * têm resultado por município; com as de 1933 a 1990 presentes, dois grupos,
 * para ficar claro onde o detalhe por município acaba.
 */
export function gruposDeEleicoes(eleicoes: EleicaoIndice[]): [string | null, EleicaoIndice[]][] {
  const porUf = eleicoes.filter((e) => e.municipios === false);
  if (!porUf.length) return [[null, eleicoes]];
  const porMunicipio = eleicoes.filter((e) => e.municipios !== false);
  const grupos: [string | null, EleicaoIndice[]][] = [];
  if (porMunicipio.length) grupos.push(["Por estado e município", porMunicipio]);
  grupos.push(["1933 a 1990: só por estado", porUf]);
  return grupos;
}
