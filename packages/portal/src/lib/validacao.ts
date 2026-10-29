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
  VERSAO_ELEITORADO,
  VERSAO_HORARIOS,
  VERSAO_FEED,
  VERSAO_ZONAS,
  type ArquivoEleitorado,
  type ArquivoHorarios,
  type ArquivoZonas,
  type CadastroMunicipios,
  type FeedConferencia,
  type FeedHistorico,
  type FeedPanorama,
  type FeedResultado,
  type Indice,
  type IndiceZonas,
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
function versao(o: Objeto, onde: string, esperada: number = VERSAO_FEED): void {
  if (o.versao !== esperada) {
    throw new ErroFeed(`${onde}: versão ${String(o.versao)} não suportada (esperada ${esperada})`);
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

/** Confere o feed da conferência seção a seção (`tipo: "conferencia"`). */
export function validarConferencia(bruto: unknown, onde = "conferencia"): FeedConferencia {
  const o = objeto(bruto, onde);
  versao(o, onde);
  if (o.tipo !== "conferencia") throw new ErroFeed(`${onde}: tipo ${String(o.tipo)} não é conferência`);
  exigir(o, ["brasil", "ufs", "secoes", "confere"], onde);
  lista(objeto(o.brasil, `${onde}.brasil`).linhas, `${onde}.brasil.linhas`);
  lista(o.ufs, `${onde}.ufs`);
  return o as unknown as FeedConferencia;
}

/** Confere o cadastro de municípios usado pela busca. */
export function validarMunicipios(bruto: unknown): CadastroMunicipios {
  const o = objeto(bruto, "municipios");
  versao(o, "municipios");
  lista(o.municipios, "municipios.municipios");
  return o as unknown as CadastroMunicipios;
}

/** Confere o índice das zonas de um ano (`geo/zonas-<ano>/indice.json`). */
export function validarIndiceZonas(bruto: unknown, onde = "zonas/indice"): IndiceZonas {
  const o = objeto(bruto, onde);
  versao(o, onde, VERSAO_ZONAS);
  if (o.tipo !== "zonas-indice") throw new ErroFeed(`${onde}: tipo ${String(o.tipo)} não é índice de zonas`);
  objeto(o.municipios, `${onde}.municipios`);
  return o as unknown as IndiceZonas;
}

/**
 * Confere o arquivo das zonas de um município. Cada local precisa de
 * longitude e latitude numéricas e de uma zona da lista: é o que vira ponto
 * e área no mapa.
 */
export function validarZonas(bruto: unknown, onde = "zonas"): ArquivoZonas {
  const o = objeto(bruto, onde);
  versao(o, onde, VERSAO_ZONAS);
  if (o.tipo !== "zonas") throw new ErroFeed(`${onde}: tipo ${String(o.tipo)} não é de zonas`);
  exigir(o, ["ano", "municipio", "origem", "zonas", "locais"], onde);
  const zonas = new Set(lista(o.zonas, `${onde}.zonas`).map((z) => String(objeto(z, `${onde}.zonas`).zona)));
  for (const [i, l] of lista(o.locais, `${onde}.locais`).entries()) {
    const local = lista(l, `${onde}.locais[${i}]`);
    if (typeof local[0] !== "number" || typeof local[1] !== "number" || !zonas.has(String(local[2]))) {
      throw new ErroFeed(`${onde}.locais[${i}] fora do formato`);
    }
  }
  return o as unknown as ArquivoZonas;
}

/** Arquivo do eleitorado (ADR-055): versão, tipo, o lugar com o total e, no município, as seções no formato. */
export function validarEleitorado(bruto: unknown, onde = "eleitorado"): ArquivoEleitorado {
  const o = objeto(bruto, onde);
  versao(o, onde, VERSAO_ELEITORADO);
  if (o.tipo !== "eleitorado") throw new ErroFeed(`${onde}: tipo ${String(o.tipo)} não é do eleitorado`);
  exigir(o, ["ano", "nivel", "origem", "lugar"], onde);
  const lugar = objeto(o.lugar, `${onde}.lugar`);
  if (typeof lugar.eleitores !== "number") throw new ErroFeed(`${onde}.lugar sem o total de eleitores`);
  if (o.secoes !== undefined) {
    for (const [i, s] of lista(o.secoes, `${onde}.secoes`).entries()) {
      const secao = lista(s, `${onde}.secoes[${i}]`);
      if (secao.length !== 4 || typeof secao[3] !== "number") throw new ErroFeed(`${onde}.secoes[${i}] fora do formato`);
    }
  }
  return o as unknown as ArquivoEleitorado;
}

/** Os horários das urnas de um lugar (ADR-056): versão, tipo, o lugar com os turnos e as seções no formato. */
export function validarHorarios(bruto: unknown, onde = "horarios"): ArquivoHorarios {
  const o = objeto(bruto, onde);
  versao(o, onde, VERSAO_HORARIOS);
  if (o.tipo !== "horarios") throw new ErroFeed(`${onde}: tipo ${String(o.tipo)} não é dos horários das urnas`);
  exigir(o, ["ano", "nivel", "horario", "lugar"], onde);
  const lugar = objeto(o.lugar, `${onde}.lugar`);
  objeto(lugar.turnos, `${onde}.lugar.turnos`);
  if (o.secoes !== undefined) {
    for (const [i, s] of lista(o.secoes, `${onde}.secoes`).entries()) {
      const secao = lista(s, `${onde}.secoes[${i}]`);
      if (secao.length !== 11 || typeof secao[0] !== "number") throw new ErroFeed(`${onde}.secoes[${i}] fora do formato`);
    }
  }
  return o as unknown as ArquivoHorarios;
}
