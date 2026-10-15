/**
 * Zonas eleitorais no mapa do município (ADR-029).
 *
 * A Justiça Eleitoral não publica os limites das zonas; publica onde fica
 * cada local de votação e a zona dele (arquivo `geo/zonas-<ano>/mu-<ibge>.json`,
 * gravado por `lumen eleicoes zonas`). O desenho dá a cada local a área mais
 * próxima dele (Voronoi, `voronoi.ts`), recortada pelo contorno do município
 * na tela, e a zona é a soma das áreas dos seus locais. É um contorno
 * aproximado e a tela diz isso.
 *
 * Um mesmo prédio pode ser local de duas zonas (seções de zonas diferentes
 * no mesmo endereço). O ponto fica com a zona que tem mais eleitores ali; a
 * outra continua com os seus outros locais.
 */

import type { ArquivoZonas } from "./tipos";
import { type Caixa, celulasVoronoi, type Ponto } from "./voronoi";

/** Um local de votação já projetado, para os pontos do mapa e a dica. */
export interface LocalNoMapa {
  x: number;
  y: number;
  zona: string;
  nome: string;
  eleitores: number;
}

/** Uma zona desenhada: a área (as células dos locais dela) e o contorno, para o destaque. */
export interface ZonaDesenhada {
  zona: string;
  /** Atributo `d` com as células da zona (cada uma um subcaminho fechado). */
  d: string;
  /** Lados que separam a zona de outra (ou da borda do desenho), para o contorno de destaque. */
  contorno: string;
  /** Onde escrever o número da zona: o local da zona mais perto do centro de massa dos eleitores dela. */
  rotulo: Ponto;
  /** Eleitores da zona no município (do arquivo): decide quem ganha o lugar do rótulo quando não cabem todos. */
  eleitores: number;
}

/** O desenho das zonas de um município. */
export interface DesenhoZonas {
  zonas: ZonaDesenhada[];
  /** Fronteiras entre zonas diferentes, todas num caminho (cada lado uma vez). */
  fronteiras: string;
  locais: LocalNoMapa[];
}

/** Coordenada com poucas casas no `d`: 0,001 unidade do mapa é menos de 1 m numa UF. */
function fmt(v: number): string {
  return (Math.round(v * 1000) / 1000).toString();
}

/** Acrescenta `valor` à lista da `chave`, criando a lista na primeira vez. */
function acrescentar(mapa: Map<string, string[]>, chave: string, valor: string): void {
  const lista = mapa.get(chave);
  if (lista) lista.push(valor);
  else mapa.set(chave, [valor]);
}

/**
 * Desenha as zonas a partir dos locais de votação. `projetar` leva longitude
 * e latitude ao SVG (a mesma projeção do mapa da UF); `caixa` limita as
 * células (a caixa do município, com folga: o recorte fino é o do contorno,
 * feito na tela por `clipPath`).
 */
export function desenharZonas(arquivo: ArquivoZonas, projetar: (lon: number, lat: number) => Ponto,
  caixa: Caixa): DesenhoZonas {
  const locais: LocalNoMapa[] = arquivo.locais.map(([lon, lat, zona, eleitores, nome]) => {
    const [x, y] = projetar(lon, lat);
    return { x, y, zona, nome, eleitores };
  });
  // Um ponto por coordenada (arredondada a 0,001 unidade): fica a zona com mais eleitores ali
  const porLugar = new Map<string, LocalNoMapa>();
  for (const l of locais) {
    const chave = `${fmt(l.x)},${fmt(l.y)}`;
    const atual = porLugar.get(chave);
    if (!atual || l.eleitores > atual.eleitores) porLugar.set(chave, l);
  }
  const sitios = [...porLugar.values()];
  const celulas = celulasVoronoi(sitios.map((l) => [l.x, l.y] as Ponto), caixa);

  const partes = new Map<string, string[]>();
  const contornos = new Map<string, string[]>();
  const fronteiras: string[] = [];
  celulas.forEach((celula, i) => {
    if (!celula) return;
    const zona = sitios[i]!.zona;
    const vs = celula.vertices;
    const d = `M${vs.map((v) => `${fmt(v[0])} ${fmt(v[1])}`).join("L")}Z`;
    acrescentar(partes, zona, d);
    vs.forEach((v, k) => {
      const viz = celula.vizinhos[k]!;
      if (viz >= 0 && sitios[viz]!.zona === zona) return;
      const w = vs[(k + 1) % vs.length]!;
      const lado = `M${fmt(v[0])} ${fmt(v[1])}L${fmt(w[0])} ${fmt(w[1])}`;
      acrescentar(contornos, zona, lado);
      // Cada fronteira entre duas zonas aparece nas duas células; desenha uma vez só
      if (viz >= 0 && viz > i) fronteiras.push(lado);
    });
  });

  const zonas: ZonaDesenhada[] = [];
  for (const z of arquivo.zonas) {
    const d = partes.get(z.zona);
    if (!d) continue;
    const dela = sitios.filter((l) => l.zona === z.zona);
    const peso = dela.reduce((s, l) => s + Math.max(l.eleitores, 1), 0);
    const cx = dela.reduce((s, l) => s + l.x * Math.max(l.eleitores, 1), 0) / peso;
    const cy = dela.reduce((s, l) => s + l.y * Math.max(l.eleitores, 1), 0) / peso;
    let melhor = dela[0]!;
    for (const l of dela) {
      if ((l.x - cx) ** 2 + (l.y - cy) ** 2 < (melhor.x - cx) ** 2 + (melhor.y - cy) ** 2) melhor = l;
    }
    zonas.push({
      zona: z.zona,
      d: d.join(""),
      contorno: (contornos.get(z.zona) ?? []).join(""),
      rotulo: [melhor.x, melhor.y],
      eleitores: z.eleitores,
    });
  }
  return { zonas, fronteiras: fronteiras.join(""), locais };
}

/** Caixa com folga proporcional (`fracao` do maior lado), para as células irem além do contorno. */
export function caixaComFolga(caixa: Caixa, fracao = 0.05): Caixa {
  const [x0, y0, x1, y1] = caixa;
  const f = Math.max(x1 - x0, y1 - y0) * fracao;
  return [x0 - f, y0 - f, x1 + f, y1 + f];
}

/**
 * Números das zonas que cabem sem encostar uns nos outros: a zona com mais
 * eleitores escolhe primeiro, e um rótulo a menos de `distancia` de outro já
 * posto fica de fora (aparece ao aproximar; a dica e a tabela têm todos).
 */
export function rotulosVisiveis(zonas: ZonaDesenhada[], distancia: number): Set<string> {
  const postos: Ponto[] = [];
  const saida = new Set<string>();
  const d2 = distancia * distancia;
  for (const z of [...zonas].sort((a, b) => b.eleitores - a.eleitores || Number(a.zona) - Number(b.zona))) {
    if (postos.every((p) => (p[0] - z.rotulo[0]) ** 2 + (p[1] - z.rotulo[1]) ** 2 >= d2)) {
      postos.push(z.rotulo);
      saida.add(z.zona);
    }
  }
  return saida;
}

/**
 * Índices dos pontos que ficam quando eles se amontoam: no máximo um por casa
 * de uma grade de lado `distancia`. Onde os locais são esparsos, ficam todos;
 * no centro denso de uma capital, sobra uma amostra, e aproximar mostra o resto.
 */
export function rarear(pontos: { x: number; y: number }[], distancia: number): number[] {
  if (distancia <= 0) return pontos.map((_, i) => i);
  const ocupadas = new Set<string>();
  const saida: number[] = [];
  pontos.forEach((p, i) => {
    const chave = `${Math.floor(p.x / distancia)},${Math.floor(p.y / distancia)}`;
    if (ocupadas.has(chave)) return;
    ocupadas.add(chave);
    saida.push(i);
  });
  return saida;
}
