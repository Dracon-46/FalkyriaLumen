/**
 * Conferência dos feeds na chegada.
 *
 * O portal recusa o que não reconhece em vez de exibir número errado: versão
 * diferente da esperada, tipo desconhecido ou campo obrigatório ausente viram
 * `ErroFeed`, que a tela mostra como "dados indisponíveis". A conferência é
 * estrutural e barata — o feed tem dezenas de KB e chega a cada 15 segundos
 * na noite da apuração.
 */

import {
  VERSAO_FEED,
  type CadastroMunicipios,
  type FeedHistorico,
  type FeedPanorama,
  type FeedResultado,
  type Indice,
} from "./tipos";

/**
 * Feed fora do contrato ou inacessível (sem resposta, HTTP de erro, conteúdo
 * que não é JSON). A mensagem diz onde está o problema e é a que a tela
 * mostra no aviso de dados indisponíveis.
 */
export class ErroFeed extends Error {
  constructor(mensagem: string) {
    super(mensagem);
    this.name = "ErroFeed";
  }
}

/** Objeto JSON ainda não conferido. */
type Objeto = Record<string, unknown>;

/** Exige um objeto JSON (não lista, não null); `onde` entra na mensagem de erro. */
function objeto(valor: unknown, onde: string): Objeto {
  if (typeof valor !== "object" || valor === null || Array.isArray(valor)) {
    throw new ErroFeed(`${onde}: esperado objeto`);
  }
  return valor as Objeto;
}

/** Exige uma lista JSON. */
function lista(valor: unknown, onde: string): unknown[] {
  if (!Array.isArray(valor)) throw new ErroFeed(`${onde}: esperado lista`);
  return valor;
}

/** Exige a presença dos campos (o valor pode ser null); a mensagem lista todos os ausentes de uma vez. */
function exigir(o: Objeto, campos: string[], onde: string): void {
  const faltando = campos.filter((c) => !(c in o));
  if (faltando.length) throw new ErroFeed(`${onde}: faltam ${faltando.join(", ")}`);
}

/**
 * Recusa versão diferente de `VERSAO_FEED`. Igualdade estrita, nem maior nem
 * menor: mudança incompatível no contrato sobe a versão, e o portal não
 * tenta adivinhar como ler o que não conhece.
 */
function versao(o: Objeto, onde: string): void {
  if (o.versao !== VERSAO_FEED) {
    throw new ErroFeed(`${onde}: versão ${String(o.versao)} não suportada (esperada ${VERSAO_FEED})`);
  }
}

/** Confere o `indice.json`: versão, campos de cada eleição e de cada um dos seus cargos. */
export function validarIndice(bruto: unknown): Indice {
  const o = objeto(bruto, "indice");
  versao(o, "indice");
  for (const [i, e] of lista(o.eleicoes, "indice.eleicoes").entries()) {
    const el = objeto(e, `indice.eleicoes[${i}]`);
    exigir(el, ["id", "nome", "ano", "turno", "tipo", "origem", "ao_vivo", "cargos", "ufs"], `eleição ${i}`);
    for (const c of lista(el.cargos, `eleição ${String(el.id)}.cargos`)) {
      exigir(objeto(c, "cargo"), ["slug", "codigo", "nome", "tipo", "nivel"], `cargo de ${String(el.id)}`);
    }
  }
  return o as unknown as Indice;
}

const CAMPOS_COMUNS = ["versao", "tipo", "eleicao", "cargo", "abrangencia", "origem", "partes"];

/**
 * Confere um feed de resultado ou de panorama, decidido pelo campo `tipo`.
 * No resultado, cada candidato precisa ter `votos` numérico — é o número
 * que a tela soma e compara. Tipo desconhecido é recusado.
 */
export function validarFeed(bruto: unknown, onde = "feed"): FeedResultado | FeedPanorama {
  const o = objeto(bruto, onde);
  versao(o, onde);
  if (o.tipo === "resultado") {
    exigir(o, [...CAMPOS_COMUNS, "totalizacao", "comparecimento", "votos", "candidatos", "avisos"], onde);
    for (const [i, c] of lista(o.candidatos, `${onde}.candidatos`).entries()) {
      const cand = objeto(c, `${onde}.candidatos[${i}]`);
      exigir(cand, ["numero", "nome_urna", "votos", "cor", "valido"], `${onde}.candidatos[${i}]`);
      if (typeof cand.votos !== "number") throw new ErroFeed(`${onde}.candidatos[${i}].votos não é número`);
    }
    lista(o.partes, `${onde}.partes`);
    return o as unknown as FeedResultado;
  }
  if (o.tipo === "panorama") {
    exigir(o, [...CAMPOS_COMUNS, "totalizacao", "partidos"], onde);
    lista(o.partidos, `${onde}.partidos`);
    lista(o.partes, `${onde}.partes`);
    return o as unknown as FeedPanorama;
  }
  throw new ErroFeed(`${onde}: tipo ${String(o.tipo)} desconhecido`);
}

/** Confere o feed de evolução da apuração (`tipo: "historico"`). */
export function validarHistorico(bruto: unknown, onde = "historico"): FeedHistorico {
  const o = objeto(bruto, onde);
  versao(o, onde);
  if (o.tipo !== "historico") throw new ErroFeed(`${onde}: tipo ${String(o.tipo)} não é histórico`);
  exigir(o, ["candidatos", "pontos"], onde);
  lista(o.pontos, `${onde}.pontos`);
  return o as unknown as FeedHistorico;
}

/** Confere o cadastro de municípios usado pela busca. */
export function validarMunicipios(bruto: unknown): CadastroMunicipios {
  const o = objeto(bruto, "municipios");
  versao(o, "municipios");
  lista(o.municipios, "municipios.municipios");
  return o as unknown as CadastroMunicipios;
}
