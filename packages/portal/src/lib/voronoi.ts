/**
 * Diagrama de Voronoi: a região de cada ponto é a parte do plano mais perto
 * dele que de qualquer outro. É o que desenha as zonas eleitorais no mapa do
 * município (`zonas.ts`): cada local de votação fica com a área mais próxima,
 * e a zona é a soma das áreas dos seus locais.
 *
 * Sem biblioteca, como o resto do mapa. Cada célula começa como a caixa do
 * desenho e é cortada pelo semiplano de cada vizinho (a mediatriz entre os
 * dois pontos). Os vizinhos vêm de uma grade, do anel mais perto para o mais
 * longe; um ponto a mais de duas vezes o raio da célula não a alcança e é
 * pulado, e os anéis param quando todos os que restam estão nessa situação.
 *
 * Cada lado da célula guarda de quem é a mediatriz que o formou (ou -1, a
 * caixa): é assim que a fronteira entre duas zonas sai sem calcular união de
 * polígonos — é o lado entre dois locais de zonas diferentes.
 */

/** Ponto [x, y] nas coordenadas do desenho. */
export type Ponto = [number, number];

/** Caixa do desenho: x mínimo, y mínimo, x máximo, y máximo. */
export type Caixa = [number, number, number, number];

/** Região de um ponto: os vértices em ordem e, para cada lado, o ponto do outro lado (-1: a caixa). */
export interface Celula {
  /** Índice do ponto dono da célula. */
  ponto: number;
  /** Vértices; o lado `i` vai de `vertices[i]` a `vertices[i + 1]` (o último fecha no primeiro). */
  vertices: Ponto[];
  /** Para cada lado, o índice do ponto vizinho cuja mediatriz o formou, ou -1 se é a borda da caixa. */
  vizinhos: number[];
}

/**
 * Corta o polígono pelo semiplano dos pontos mais perto de `a` que de `b`,
 * mantendo de quem é cada lado. O lado novo, sobre a mediatriz, é de `vizinho`.
 */
export function cortar(vertices: Ponto[], vizinhos: number[], a: Ponto, b: Ponto, vizinho: number): Celula | null {
  const mx = (a[0] + b[0]) / 2;
  const my = (a[1] + b[1]) / 2;
  const nx = b[0] - a[0];
  const ny = b[1] - a[1];
  // Positivo: do lado de b (fora); negativo ou zero: do lado de a (dentro)
  const lado = (p: Ponto) => (p[0] - mx) * nx + (p[1] - my) * ny;
  // A mediatriz não alcança a célula: devolve a mesma, sem alocar (é o caso da maioria dos vizinhos)
  if (vertices.every((v) => lado(v) <= 0)) return { ponto: -1, vertices, vizinhos };
  const saida: Ponto[] = [];
  const donos: number[] = [];
  const n = vertices.length;
  for (let i = 0; i < n; i++) {
    const p = vertices[i]!;
    const q = vertices[(i + 1) % n]!;
    const dono = vizinhos[i]!;
    const lp = lado(p);
    const lq = lado(q);
    const dentroP = lp <= 0;
    const dentroQ = lq <= 0;
    if (dentroP) {
      saida.push(p);
      donos.push(dono);
    }
    if (dentroP !== dentroQ) {
      const t = lp / (lp - lq);
      const corte: Ponto = [p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])];
      if (dentroP) {
        // Sai do semiplano: o trecho até o corte é do lado original; dali segue a mediatriz
        donos[donos.length - 1] = dono;
        saida.push(corte);
        donos.push(vizinho);
      } else {
        // Entra no semiplano: do corte em diante, o resto do lado original
        saida.push(corte);
        donos.push(dono);
      }
    }
  }
  if (saida.length < 3) return null;
  return { ponto: -1, vertices: saida, vizinhos: donos };
}

/** Distância ao quadrado. */
function d2(a: Ponto, b: Ponto): number {
  const dx = a[0] - b[0];
  const dy = a[1] - b[1];
  return dx * dx + dy * dy;
}

/** Raio da célula ao quadrado: a maior distância do ponto dono a um vértice dela. */
function raioAoQuadrado(p: Ponto, celula: Celula): number {
  let r = 0;
  for (const v of celula.vertices) r = Math.max(r, d2(p, v));
  return r;
}

/**
 * Células de Voronoi dos `pontos`, cortadas pela `caixa`. Pontos repetidos
 * (mesma coordenada) não formam célula própria: o primeiro fica com a área,
 * os demais ficam sem célula (`null` na posição deles).
 */
export function celulasVoronoi(pontos: Ponto[], caixa: Caixa): (Celula | null)[] {
  const n = pontos.length;
  if (!n) return [];
  const [x0, y0, x1, y1] = caixa;
  const largura = Math.max(x1 - x0, 1e-9);
  const altura = Math.max(y1 - y0, 1e-9);
  // Grade com cerca de dois pontos por casa
  const lado = Math.max(Math.sqrt((largura * altura * 2) / n), 1e-9);
  const colunas = Math.max(1, Math.ceil(largura / lado));
  const linhas = Math.max(1, Math.ceil(altura / lado));
  const casas: number[][] = Array.from({ length: colunas * linhas }, () => []);
  const casaDe = (p: Ponto): [number, number] => [
    Math.min(colunas - 1, Math.max(0, Math.floor((p[0] - x0) / lado))),
    Math.min(linhas - 1, Math.max(0, Math.floor((p[1] - y0) / lado))),
  ];
  const repetido = new Array<boolean>(n).fill(false);
  const vistos = new Map<string, number>();
  pontos.forEach((p, i) => {
    const chave = `${p[0]},${p[1]}`;
    if (vistos.has(chave)) {
      repetido[i] = true;
      return;
    }
    vistos.set(chave, i);
    const [c, l] = casaDe(p);
    casas[l * colunas + c]!.push(i);
  });

  const maiorAnel = Math.max(colunas, linhas);
  return pontos.map((p, i) => {
    if (repetido[i]) return null;
    let celula: Celula | null = {
      ponto: i,
      vertices: [
        [x0, y0],
        [x1, y0],
        [x1, y1],
        [x0, y1],
      ],
      vizinhos: [-1, -1, -1, -1],
    };
    const [c, l] = casaDe(p);
    for (let anel = 0; anel <= maiorAnel && celula; anel++) {
      // Um ponto do anel seguinte está a pelo menos (anel × lado) de distância; além de 2 × o raio, não corta
      if (anel > 1) {
        const limite = (anel - 1) * lado;
        if (limite * limite > 4 * raioAoQuadrado(p, celula)) break;
      }
      // Só as casas da borda do anel (o miolo já foi visto nos anéis anteriores), com a distância calculada uma vez
      const candidatos: [number, number][] = [];
      const visitar = (ll: number, cc: number) => {
        if (ll < 0 || ll >= linhas || cc < 0 || cc >= colunas) return;
        for (const j of casas[ll * colunas + cc]!) if (j !== i) candidatos.push([d2(p, pontos[j]!), j]);
      };
      if (anel === 0) visitar(l, c);
      for (let cc = c - anel; anel > 0 && cc <= c + anel; cc++) {
        visitar(l - anel, cc);
        visitar(l + anel, cc);
      }
      for (let ll = l - anel + 1; anel > 0 && ll <= l + anel - 1; ll++) {
        visitar(ll, c - anel);
        visitar(ll, c + anel);
      }
      // Sem ordenar: o raio só diminui a cada corte, então quem já está a mais de 2 × o raio pode ser pulado
      let raio2 = raioAoQuadrado(p, celula);
      for (const [dist2, j] of candidatos) {
        if (dist2 > 4 * raio2) continue;
        const cortada = cortar(celula.vertices, celula.vizinhos, p, pontos[j]!, j);
        if (!cortada) {
          celula = null;
          break;
        }
        if (cortada.vertices !== celula.vertices) {
          celula = cortada;
          raio2 = raioAoQuadrado(p, celula);
        }
      }
    }
    return celula ? { ...celula, ponto: i } : null;
  });
}
