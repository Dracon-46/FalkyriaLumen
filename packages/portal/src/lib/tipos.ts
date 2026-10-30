/**
 * Tipos do contrato dos feeds da aba Eleições (versão 1).
 *
 * Espelho de `packages/eleicoes/lumen_eleicoes/feeds.py`. Quem muda um lado
 * muda o outro: os testes de `validacao.test.ts` leem a amostra gerada pelo
 * Python (`testes/fixtures/eleicoes_feed`) e falham se os dois divergirem.
 */

/**
 * Versão do contrato que este portal entende. Arquivo com outra versão é
 * recusado na chegada (`validacao.ts`), em vez de exibido com número errado.
 */
export const VERSAO_FEED = 1;

/**
 * Versão do formato do mapa das zonas (`geo/zonas-<ano>/`), espelho de
 * `zonas.VERSAO_ZONAS` no Python. É independente da dos feeds: um lado pode
 * mudar sem o outro.
 */
export const VERSAO_ZONAS = 1;
/** Versão dos arquivos do eleitorado (`eleitorado-<ano>/`, ADR-055). */
export const VERSAO_ELEITORADO = 1;
/** Versão dos arquivos dos horários das urnas (ADR-056). */
export const VERSAO_HORARIOS = 1;
/** Versão dos arquivos dos votos por hora (ADR-057). */
export const VERSAO_VOTOS_HORA = 1;

/** Majoritário (vence quem tem mais votos) ou proporcional (vagas repartidas pelo quociente eleitoral). */
export type TipoCargo = "majoritario" | "proporcional";
/** Onde o cargo é disputado: Brasil (Presidente), UF (Governador, Senador, deputados) ou município. */
export type Nivel = "br" | "uf" | "mu";
/** Recorte geográfico de um arquivo de feed: Brasil, UF ou município. */
export type TipoAbrangencia = "br" | "uf" | "mu";

/** Identificação da eleição, repetida em cada feed: um pleito num turno, como o eleitor o reconhece. */
export interface ResumoEleicao {
  /** Ex.: "2026-1t-geral"; é o diretório dos feeds e o parâmetro `e` da URL. */
  id: string;
  nome: string;
  ano: number;
  turno: number;
  /** "geral", "municipal", "suplementar" ou "consulta". */
  tipo: string;
  /** Dia da votação, "AAAA-MM-DD", sem fuso. */
  data: string | null;
}

/** Cargo em disputa numa eleição, como aparece no índice e no cabeçalho de cada feed. */
export interface CargoFeed {
  /** Identificador do cargo nos caminhos dos feeds e no parâmetro `c` da URL (ex.: "presidente"). */
  slug: string;
  /** Código do cargo no TSE. */
  codigo: number;
  nome: string;
  tipo: TipoCargo;
  nivel: Nivel;
  /** Cadeiras em disputa, quando a fonte informa. */
  vagas: number | null;
  /** UFs em que há dados do cargo (Deputado Distrital só no DF); ausente quando o índice não restringe. */
  ufs?: string[];
}

/** Linha de uma eleição no `indice.json`: o resumo, de onde vêm os dados e os cargos disponíveis. */
export interface EleicaoIndice extends ResumoEleicao {
  /** "resultados" (sistema de divulgação, ao vivo) ou "dados_abertos" (Portal de Dados Abertos, eleições passadas). */
  origem: "resultados" | "dados_abertos" | string;
  /** Apuração em andamento: a tela relê os feeds a cada 15 s. */
  ao_vivo: boolean;
  atualizado_em: string | null;
  cargos: CargoFeed[];
  /** UFs com dados nesta eleição, em minúsculas. */
  ufs: string[];
  /** Números intermediários fictícios, gerados para testar a apuração ao vivo. */
  simulacao?: boolean;
  /** Amostra de desenvolvimento: resultados oficiais de só alguns estados e municípios. */
  amostra?: boolean;
  /**
   * `false` nas eleições de 1933 a 1990, que o TSE publica só por UF: não há
   * mapa nem resultado por município. Ausente vale como `true`.
   */
  municipios?: boolean;
}

/** Conteúdo de `indice.json`: as eleições publicadas no servidor. É o primeiro arquivo que a aba lê. */
export interface Indice {
  versao: number;
  gerado_em: string | null;
  eleicoes: EleicaoIndice[];
}

/** Recorte de um feed (Brasil, UF ou município), com os códigos que o ligam ao cadastro e à malha. */
export interface AbrangenciaFeed {
  tipo: TipoAbrangencia;
  /** "br", sigla da UF em minúsculas ou chave do município (código IBGE; no exterior, "zz-<código TSE>"). */
  codigo: string;
  nome: string;
  /** Sigla da UF em minúsculas; null no Brasil. */
  uf: string | null;
  /** Código IBGE (2 dígitos na UF, 7 no município); null no Brasil e no exterior. */
  ibge: string | null;
  /** Código TSE do município (5 dígitos); null fora do município. */
  tse: string | null;
}

/**
 * De onde vieram os números do feed. A tela mostra a fonte, o link para o
 * arquivo original e o SHA-256 da cópia guardada: qualquer pessoa pode
 * conferir o número contra o documento oficial.
 */
export interface Origem {
  /** "resultados", "dados_abertos" ou outro nome de fonte, exibido como veio. */
  fonte: string;
  /** Endereço do arquivo original na fonte. */
  url: string | null;
  /** SHA-256 da cópia do arquivo original guardada pelo coletor. */
  sha256: string | null;
  /** Instante da coleta, ISO 8601 com fuso. */
  coletado_em: string | null;
  /** Identificador dessa cópia na camada bronze do Lumen. */
  registro_bronze: string | null;
  /** Este arquivo é de uma simulação (números intermediários fictícios). */
  simulacao?: boolean;
  /** Este arquivo é de uma amostra de desenvolvimento. */
  amostra?: boolean;
}

/** Andamento da totalização na abrangência, como o TSE publica. */
export interface Totalizacao {
  secoes: number | null;
  secoes_totalizadas: number | null;
  /** Percentual de seções totalizadas (0 a 100). */
  pct_secoes: number | null;
  finalizada: boolean;
  /** A fonte indica que os votos restantes já não mudam o resultado; null quando não informa. */
  matematicamente_definida: boolean | null;
}

/** Eleitorado apto, quem compareceu e quem se absteve, com os percentuais. */
export interface Comparecimento {
  eleitorado: number | null;
  comparecimento: number | null;
  abstencao: number | null;
  pct_comparecimento: number | null;
  pct_abstencao: number | null;
  /** Eleitores das seções que não funcionaram: no eleitorado, mas nem no comparecimento nem na abstenção. */
  eleitorado_secoes_nao_instaladas?: number | null;
}

/** Destino dos votos na abrangência: válidos, brancos, nulos, anulados e de legenda. */
export interface Votos {
  validos: number | null;
  brancos: number | null;
  /** Total de nulos, com os técnicos (os feeds ao vivo gravados antes de 26/10/2026 traziam só os comuns). */
  nulos: number | null;
  /** Parte dos nulos que o TSE separa como nulo técnico, quando a fonte publica. */
  nulos_tecnicos?: number | null;
  /** Votos anulados, inclusive os sub judice; não entram nos válidos. */
  anulados: number | null;
  /** Proporcionais: votos dados só ao número do partido. */
  legenda: number | null;
  pct_validos: number | null;
  pct_brancos: number | null;
  pct_nulos: number | null;
}

/** Um candidato no resultado; o feed traz a lista dos mais votados para os menos votados. */
export interface Candidato {
  /** Número de urna; identifica o candidato também nas séries do histórico. */
  numero: string;
  /** Nome como aparece na urna; é o que a tela exibe. */
  nome_urna: string;
  nome: string;
  partido: string | null;
  /** Coligação ou federação pela qual concorre, quando há. */
  agremiacao: string | null;
  /** Partidos que compõem a agremiação. */
  composicao: string | null;
  votos: number;
  /** Percentual dos votos válidos; null quando os votos do candidato não são válidos. */
  pct: number | null;
  /** Situação como o TSE publica: "Eleito", "2º turno", "Não eleito" ou vazio. */
  situacao: string;
  eleito: boolean;
  segundo_turno: boolean;
  /** Os votos contam como válidos (falso quando a destinação é de anulação). */
  valido: boolean;
  /** Destinação dos votos ("Válido", "Anulado sub judice"...); null quando a fonte não informa. */
  destinacao: string | null;
  /** Vice (executivo) ou 1º suplente (Senado). */
  vice: string | null;
  /**
   * Posição na paleta (0 a 7) ou -1 (cinza). PL é sempre 0 (azul) e PT
   * sempre 1 (vermelho), ADR-052; os demais, pela ordem de votação, fixa
   * durante a apuração. Nos proporcionais, é a do partido.
   */
  cor: number;
  /** Caminho relativo da foto ("fotos/….jpg"); `urls.foto` só aceita esse formato. */
  foto: string | null;
  /**
   * O candidato não tinha número de urna (eleições até os anos 1980): `numero`
   * é só um identificador estável do feed e não é exibido.
   */
  sem_numero?: boolean;
}

/** Votação de partido isolado, coligação ou federação nos proporcionais, com as vagas obtidas. */
export interface Agremiacao {
  nome: string;
  /** "isolado", "coligação" ou "federação". */
  tipo: string;
  composicao: string | null;
  votos: number;
  vagas: number | null;
}

/**
 * Linha de uma abrangência filha (UF no Brasil, município na UF, zona
 * eleitoral no município), para o mapa e a tabela. Na zona, `codigo` é o
 * número da zona e `ibge` é null.
 */
export interface Parte {
  codigo: string;
  nome: string;
  ibge: string | null;
  /** Quem está à frente: número do candidato ou, quando a parte é contada por partido, a sigla; null sem votos. */
  lider: string | null;
  partido?: string | null;
  nome_urna?: string | null;
  votos?: number | null;
  pct?: number | null;
  /** Vantagem do líder sobre o segundo, em pontos percentuais. */
  margem?: number | null;
  /** Posição na paleta de quem está à frente; o mapa só pinta as quatro primeiras. */
  cor: number;
  /** Abstenção sobre o eleitorado da parte (feeds gravados desde 26/10/2026). */
  pct_abstencao?: number | null;
  /** Percentual dos válidos dos mais votados na parte, por número (ou sigla); desde 26/10/2026. */
  pcts?: Record<string, number | null>;
  eleito?: boolean;
  segundo_turno?: boolean;
  pct_secoes: number | null;
  finalizada: boolean;
  eleitorado: number | null;
  /** Panorama nacional de cargo municipal: municípios liderados pelo partido à frente na UF. */
  liderados?: number;
  /** Proporcionais: eleitos por partido na parte. */
  bancada?: Record<string, number>;
}

/**
 * Arquivo de resultado (`br.json`, `uf-<sigla>.json`, `mu-<chave>.json`):
 * candidatos com votos, comparecimento e destino dos votos de uma
 * abrangência, mais as `partes` filhas que pintam o mapa.
 */
export interface FeedResultado {
  versao: number;
  /** Regra das cores (`cores.ts`): 2 desde o ADR-052; ausente nos feeds gravados antes. */
  paleta?: number;
  tipo: "resultado";
  eleicao: ResumoEleicao;
  cargo: CargoFeed;
  abrangencia: AbrangenciaFeed;
  atualizado_em: string | null;
  ao_vivo: boolean;
  origem: Origem;
  totalizacao: Totalizacao;
  comparecimento: Comparecimento;
  votos: Votos;
  /** Proporcionais: votos necessários para cada vaga; null quando não se aplica. */
  quociente_eleitoral: number | null;
  candidatos: Candidato[];
  /** Candidatos fora do arquivo (município com lista limitada); a lista completa está no arquivo da UF. */
  candidatos_omitidos: number;
  agremiacoes: Agremiacao[];
  /**
   * Abrangências filhas (UFs no Brasil, municípios na UF), para o mapa e a
   * tabela. No município com mais de uma zona eleitoral, as zonas (só nas
   * eleições lidas dos dados abertos; ao vivo, o TSE não publica por zona).
   */
  partes: Parte[];
  /** Ressalvas da fonte, exibidas antes dos números. */
  avisos: string[];
}

/** Linha do placar por partido num panorama; o feed ordena por eleitos, depois partes lideradas e votos. */
export interface PlacarPartido {
  partido: string;
  /** Partes (UFs ou municípios) em que o partido está à frente. */
  liderados: number;
  eleitos: number;
  votos: number;
  /** Posição na paleta, pela ordem do placar: nos panoramas a cor identifica o partido. */
  cor: number;
}

/**
 * Arquivo de panorama: o cargo visto de cima, onde não existe resultado
 * único (cargo municipal na UF ou no Brasil, cargo estadual no Brasil).
 * Traz o placar por partido e o líder de cada parte, em vez de candidatos.
 */
export interface FeedPanorama {
  versao: number;
  /** Regra das cores (`cores.ts`): 2 desde o ADR-052; ausente nos feeds gravados antes. */
  paleta?: number;
  tipo: "panorama";
  eleicao: ResumoEleicao;
  cargo: CargoFeed;
  abrangencia: AbrangenciaFeed;
  atualizado_em: string | null;
  ao_vivo: boolean;
  origem: Origem;
  /** Partes com totalização concluída, em número e em percentual. */
  totalizacao: { partes: number; partes_finalizadas: number; pct_partes: number | null };
  partidos: PlacarPartido[];
  partes: Parte[];
  avisos: string[];
}

/** Uma leitura da apuração no histórico: instante, seções totalizadas e votos por número de candidato. */
export interface PontoEvolucao {
  /** Instante da leitura, ISO 8601 com fuso. */
  t: string | null;
  pct_secoes: number | null;
  /** Votos acumulados por número de candidato. */
  votos: Record<string, number>;
}

/** Arquivo `historico-<abrangência>.json`: a sequência de leituras que desenha o gráfico de evolução. */
export interface FeedHistorico {
  versao: number;
  /** Regra das cores (`cores.ts`): 2 desde o ADR-052; ausente nos feeds gravados antes. */
  paleta?: number;
  tipo: "historico";
  eleicao: ResumoEleicao;
  cargo: CargoFeed;
  abrangencia: AbrangenciaFeed;
  origem: Origem;
  candidatos: { numero: string; nome_urna: string; partido: string | null; cor: number }[];
  /** Leituras em ordem cronológica. */
  pontos: PontoEvolucao[];
}

/** Uma linha da conferência seção a seção: um número votado (ou brancos, nulos, nulos técnicos). */
export interface LinhaConferencia {
  rotulo: string;
  /** Número votado (95 branco, 96 nulo); null nos nulos técnicos, que juntam os números fora da lista. */
  numero: string | null;
  /** Nos nulos técnicos, os números e nomes que eles somam. */
  detalhe: string | null;
  /** Soma das seções. */
  secoes: number;
  /** Total do sistema de resultados; null quando o arquivo divulgado não separa esse número. */
  divulgado: number | null;
  diferenca: number | null;
}

/** Uma abrangência conferida: as linhas e se todas batem. */
export interface AbrangenciaConferida {
  conferida: boolean;
  confere: boolean;
  linhas: LinhaConferencia[];
}

/**
 * Arquivo `<eleição>/presidente/conferencia.json` (ADR-053): a votação por
 * seção dos dados abertos, somada, contra o total do sistema de resultados,
 * no Brasil e em cada UF (com o exterior).
 */
export interface FeedConferencia {
  versao: number;
  tipo: "conferencia";
  eleicao: ResumoEleicao;
  cargo: CargoFeed;
  conferido_em: string;
  origem_secoes: Origem;
  origem_divulgado: Origem;
  secoes: { no_arquivo: number; divulgadas: number | null };
  brasil: AbrangenciaConferida;
  ufs: (AbrangenciaConferida & { uf: string; nome: string; secoes: number; secoes_divulgadas: number | null })[];
  confere: boolean;
}

/** Os dois tipos de arquivo que a tela principal exibe; o campo `tipo` os distingue. */
export type Feed = FeedResultado | FeedPanorama;

/** Município no cadastro TSE ↔ IBGE, usado pela busca. */
export interface Municipio {
  /** Sigla da UF em minúsculas ("zz" no exterior). */
  uf: string;
  /** Código TSE (5 dígitos). */
  tse: string;
  /** Código IBGE (7 dígitos); null no exterior. */
  ibge: string | null;
  /** Nome do IBGE, com acentos e caixa corretos; sem IBGE, o do TSE. */
  nome: string;
  /** Nome como o TSE publica (maiúsculas). */
  nome_tse: string;
  capital: boolean;
}

/** Conteúdo de `municipios.json`: o cadastro completo, baixado só quando a busca abre. */
export interface CadastroMunicipios {
  versao: number;
  municipios: Municipio[];
}

/**
 * Um local de votação no arquivo das zonas: longitude, latitude, número da
 * zona, eleitores (soma das seções do local) e nome, como o TSE publica.
 */
export type LocalVotacao = [number, number, string, number, string];

/** Uma zona eleitoral do município no arquivo das zonas. */
export interface ZonaDoMunicipio {
  /** Número da zona, sem zeros à esquerda. */
  zona: string;
  /** Locais da zona com coordenada (os que entram no mapa). */
  locais: number;
  /** Eleitores da zona no município, inclusive os de locais sem coordenada. */
  eleitores: number;
}

/**
 * Arquivo `geo/zonas-<ano>/mu-<ibge>.json`: as zonas de um município com mais
 * de uma e os locais de votação de cada uma (ADR-029). Gravado por
 * `lumen eleicoes zonas` a partir dos dados abertos do TSE.
 */
export interface ArquivoZonas {
  versao: number;
  tipo: "zonas";
  ano: number;
  municipio: { ibge: string; tse: string; uf: string; nome: string };
  origem: Origem;
  zonas: ZonaDoMunicipio[];
  locais: LocalVotacao[];
  /** Locais deixados de fora: sem coordenada, ou com coordenada fora do município. Opcional na leitura. */
  descartados?: { sem_coordenada: number; fora_do_municipio: number };
}

/** As características do eleitorado publicadas (as sensíveis, como raça ou cor, ficam de fora: ADR-055). */
export type Caracteristica = "genero" | "faixa_etaria" | "escolaridade" | "estado_civil";

/** Perfil de um lugar: total, com biometria e, em cada característica, `[rótulo, eleitores]`. */
export interface PerfilEleitorado extends Record<Caracteristica, [string, number][]> {
  eleitores: number;
  biometria: number;
}

/** Um turno num lugar: aptos, comparecimento e abstenção; em cada característica, `[rótulo, aptos, comparecimento]`. */
export interface TurnoEleitorado extends Record<Caracteristica, [string, number, number][]> {
  aptos: number;
  comparecimento: number;
  abstencao: number;
}

/** O lugar do arquivo (Brasil, UF ou município), com o perfil e os turnos que o TSE já publicou. */
export interface LugarEleitorado extends PerfilEleitorado {
  chave: string;
  nome: string;
  uf?: string;
  turnos: Record<string, TurnoEleitorado>;
}

/** Resumo de um lugar abaixo (UF no Brasil, município na UF): eleitores, biometria e `[aptos, comparecimento]` por turno. */
export interface ParteEleitorado {
  nome: string;
  eleitores: number;
  biometria: number;
  turnos: Record<string, [number, number]>;
  zonas?: number;
  secoes?: number;
}

/** Uma zona no arquivo do município: o perfil e os turnos dela. */
export interface ZonaEleitorado extends PerfilEleitorado {
  zona: string;
  turnos: Record<string, TurnoEleitorado>;
}

/**
 * Arquivo `eleitorado-<ano>/{br,uf-<sigla>,mu-<chave>}.json` (ADR-055): o perfil do eleitorado, o
 * comparecimento por perfil e, no município, as zonas e as seções (`[zona, seção, local, eleitores]`).
 */
export interface ArquivoEleitorado {
  versao: number;
  tipo: "eleitorado";
  ano: number;
  nivel: "br" | "uf" | "municipio";
  origem: Record<string, Origem>;
  lugar: LugarEleitorado;
  partes?: Record<string, ParteEleitorado>;
  zonas?: ZonaEleitorado[];
  secoes?: [string, number, string, number][];
  locais?: Record<string, string>;
}

/** Contagem por faixa de `passo` minutos a partir de `inicio` (minutos desde a meia-noite), com o que fica fora. */
export interface HistogramaHorarios {
  inicio: number;
  passo: number;
  contagens: number[];
  antes: number;
  depois: number;
}

/**
 * Os horários de um lugar num turno: seções, aptos, comparecimento, quantas fecharam depois das 17h30 e
 * `[mediana, 90%, último]` do encerramento e do recebimento (minutos desde a meia-noite; passa de 1.440 no dia
 * seguinte). No lugar do arquivo, também os histogramas e os tipos de urna.
 */
export interface ResumoHorarios {
  secoes: number;
  aptos: number;
  comparecimento: number;
  depois_17h30: number;
  encerramento: [number | null, number | null, number | null];
  recebido: [number | null, number | null, number | null];
  histogramas?: {
    abertura: HistogramaHorarios;
    encerramento: HistogramaHorarios;
    /** `null` antes de 2020: o TSE não publicava o recebimento. */
    recebido: HistogramaHorarios | null;
  };
  tipos_urna?: Record<string, number>;
}

/**
 * Uma seção nos horários: `[turno, zona, seção, local, aptos, comparecimento, tipo de urna, abertura,
 * encerramento, emissão do boletim, boletim recebido]`, os horários como `"HH:MM"` (`"+1 HH:MM"` no dia seguinte).
 */
export type SecaoHorarios = [number, string, number, string, number, number, string, string | null, string | null,
  string | null, string | null];

/**
 * Arquivo `horarios/<ano>/{br,uf-<sigla>}.json` ou um município de `mu/<grupo>.json` (ADR-056): quando as urnas
 * abriram e fecharam e quando os boletins chegaram ao TSE. `horario` diz se abertura, encerramento e emissão estão
 * no horário de Brasília (de 2022 em diante) ou no local de cada seção; o recebido é sempre o de Brasília.
 */
export interface ArquivoHorarios {
  versao: number;
  tipo: "horarios";
  ano: number;
  horario: "brasilia" | "local";
  nivel: "br" | "uf" | "municipio";
  origem: Record<string, unknown>;
  lugar: { chave: string; nome: string; uf?: string; turnos: Record<string, ResumoHorarios> };
  partes?: Record<string, { nome: string; turnos: Record<string, ResumoHorarios> }>;
  zonas?: { zona: string; turnos: Record<string, ResumoHorarios> }[];
  secoes?: SecaoHorarios[];
}

/**
 * Os votos de um lugar num turno, pelos logs das urnas: total, seções e `[primeira hora, votos nela, na seguinte,
 * ...]` (horas de Brasília); no lugar do arquivo, também de 10 em 10 minutos (`inicio` em minutos desde a meia-noite).
 */
export interface TurnoVotosHora {
  votos: number;
  secoes: number;
  por_hora: number[];
  por_faixa?: { inicio: number | null; passo: number; contagens: number[] };
}

/**
 * Arquivo `votos-hora/<ano>/{br,uf-<sigla>}.json` ou um município de `mu/<grupo>.json` (ADR-057). No município,
 * as seções são `[turno, zona, seção, primeira hora, votos nela, na seguinte, ...]`.
 */
export interface ArquivoVotosHora {
  versao: number;
  tipo: "votos-hora";
  ano: number;
  horario: "brasilia";
  nivel: "br" | "uf" | "municipio";
  origem: Record<string, unknown>;
  lugar: { chave: string; nome: string; uf?: string; turnos: Record<string, TurnoVotosHora> };
  partes?: Record<string, { nome: string; turnos: Record<string, TurnoVotosHora> }>;
  zonas?: { zona: string; turnos: Record<string, TurnoVotosHora> }[];
  secoes?: (number | string)[][];
}

/** Arquivo `geo/zonas-<ano>/indice.json`: código IBGE → número de zonas, dos municípios com mais de uma. */
export interface IndiceZonas {
  versao: number;
  tipo: "zonas-indice";
  ano: number;
  municipios: Record<string, number>;
}

/** O que está selecionado na tela; vai para a URL (ver `estado-url.ts`). */
export interface Selecao {
  eleicao: string | null;
  cargo: string | null;
  /** "br", "uf-sp" ou "mu-3550308" — o nome do arquivo do feed. */
  abrangencia: string;
  tv: boolean;
}
