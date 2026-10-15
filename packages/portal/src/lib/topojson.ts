/**
 * TopoJSON do IBGE → caminhos SVG, sem biblioteca.
 *
 * O IBGE publica as malhas em TopoJSON (`formato=application/json`): cada
 * fronteira é um arco desenhado uma vez e compartilhado pelos dois vizinhos,
 * com coordenadas inteiras (quantizadas) e codificadas por diferença. Decodificar
 * é somar as diferenças e aplicar `transform`. São ~80 linhas; uma biblioteca
 * de mapas traria centenas de KB para o navegador por isso.
 *
 * Projeção: equiretangular com correção do cosseno da latitude central. Para
 * um país inteiro na tela, a distorção é desprezível frente à de Mercator e o
 * cálculo é trivial (DOC-04, princípio de não depender do que não se precisa).
 * A projeção de um mapa fica guardada (`Projecao`): o contorno fino de um
 * município e os locais de votação são desenhados por cima do mapa da UF no
 * mesmo enquadramento (`projetarCom`, `pontoProjetado`).
 */

/** O arquivo TopoJSON como o IBGE publica: arcos compartilhados e objetos que os referenciam. */
export interface Topologia {
  type: "Topology";
  /** Cada arco é uma lista de pontos; com `transform`, inteiros codificados por diferença. */
  arcs: [number, number][][];
  /** Quantização: coordenada real = acumulado × `scale` + `translate`. */
  transform?: { scale: [number, number]; translate: [number, number] };
  objects: Record<string, { type: string; geometries: Geometria[] }>;
}

/**
 * Uma área da malha (UF ou município). Os números em `arcs` são índices de
 * arcos; índice negativo `~i` indica o arco `i` percorrido ao contrário.
 */
interface Geometria {
  type: "Polygon" | "MultiPolygon" | string;
  arcs: number[][] | number[][][];
  properties?: { codarea?: string };
}

/** Uma área pronta para o SVG. */
export interface Forma {
  /** `codarea` da malha: código IBGE da UF ou do município. */
  codigo: string;
  /** Atributo `d` do `<path>`. */
  d: string;
  /** Centro da caixa envolvente, para posicionar rótulos e dicas. */
  centro: [number, number];
  /** Caixa envolvente no SVG: x mínimo, y mínimo, x máximo, y máximo. */
  caixa: [number, number, number, number];
}

/**
 * Como longitude e latitude viram coordenadas do SVG num mapa: o fator do
 * cosseno (`k`), a origem e a escala. Com ela, outra malha ou um ponto caem
 * no mesmo lugar do mapa já desenhado.
 */
export interface Projecao {
  k: number;
  x0: number;
  y0: number;
  escala: number;
}

/** Resultado de `projetar`: as formas, o tamanho do `viewBox` que as enquadra e a projeção usada. */
export interface MapaProjetado {
  largura: number;
  /** Proporcional à largura, conforme o formato da região. */
  altura: number;
  formas: Forma[];
  projecao: Projecao;
}

/** Par de coordenadas: [longitude, latitude] na malha decodificada, [x, y] depois da projeção. */
type Ponto = [number, number];

/** Longitude e latitude → coordenadas do SVG, na projeção de um mapa. */
export function pontoProjetado(p: Projecao, lon: number, lat: number): [number, number] {
  return [(lon * p.k - p.x0) * p.escala, (-lat - p.y0) * p.escala];
}

/**
 * Arcos em coordenadas reais. Com `transform`, soma as diferenças ponto a
 * ponto e aplica escala e translação; sem ele, as coordenadas já são reais.
 */
export function decodificarArcos(topo: Topologia): Ponto[][] {
  const [sx, sy] = topo.transform?.scale ?? [1, 1];
  const [tx, ty] = topo.transform?.translate ?? [0, 0];
  return topo.arcs.map((arco) => {
    let x = 0;
    let y = 0;
    return arco.map(([dx, dy]) => {
      if (topo.transform) {
        x += dx;
        y += dy;
        return [x * sx + tx, y * sy + ty] as Ponto;
      }
      return [dx, dy] as Ponto;
    });
  });
}

/** Costura os arcos de um anel (contorno fechado), invertendo os de índice negativo. */
function anel(indices: number[], arcos: Ponto[][]): Ponto[] {
  const pontos: Ponto[] = [];
  for (const i of indices) {
    const original = arcos[i < 0 ? ~i : i];
    if (!original) throw new Error(`arco ${i} inexistente`);
    const arco = i < 0 ? [...original].reverse() : original;
    // Arcos consecutivos compartilham a ponta: não repete o ponto.
    pontos.push(...(pontos.length ? arco.slice(1) : arco));
  }
  return pontos;
}

/** Anéis de um Polygon ou de todos os polígonos de um MultiPolygon; outros tipos não desenham nada. */
export function aneisDaGeometria(g: Geometria, arcos: Ponto[][]): Ponto[][] {
  if (g.type === "Polygon") return (g.arcs as number[][]).map((r) => anel(r, arcos));
  if (g.type === "MultiPolygon") {
    return (g.arcs as number[][][]).flatMap((poligono) => poligono.map((r) => anel(r, arcos)));
  }
  return [];
}

/** Geometrias do primeiro objeto da malha, com o código e os anéis em longitude e latitude. */
function geometriasDe(topo: Topologia): { codigo: string; aneis: Ponto[][] }[] {
  const objeto = Object.values(topo.objects)[0];
  if (!objeto) return [];
  const arcos = decodificarArcos(topo);
  return objeto.geometries.map((g) => ({
    codigo: String(g.properties?.codarea ?? ""),
    aneis: aneisDaGeometria(g, arcos),
  }));
}

/**
 * Formas do SVG a partir de anéis em longitude e latitude, na projeção dada.
 * `casas` é a precisão das coordenadas no `d`: uma casa basta para o mapa de
 * uma UF inteira; o contorno de um município visto de perto precisa de mais.
 */
function formasDe(geometrias: { codigo: string; aneis: Ponto[][] }[], p: Projecao, casas: number): Forma[] {
  const fator = 10 ** casas;
  const fmt = (v: number) => (Math.round(v * fator) / fator).toString();
  return geometrias.map((g) => {
    let gx0 = Infinity;
    let gy0 = Infinity;
    let gx1 = -Infinity;
    let gy1 = -Infinity;
    const d = g.aneis
      .filter((r) => r.length > 2)
      .map((r) => {
        const pts = r.map(([lon, lat]) => {
          const [px, py] = pontoProjetado(p, lon, lat);
          if (px < gx0) gx0 = px;
          if (px > gx1) gx1 = px;
          if (py < gy0) gy0 = py;
          if (py > gy1) gy1 = py;
          return `${fmt(px)} ${fmt(py)}`;
        });
        return `M${pts.join("L")}Z`;
      })
      .join("");
    return {
      codigo: g.codigo,
      d,
      centro: [(gx0 + gx1) / 2, (gy0 + gy1) / 2] as [number, number],
      caixa: [gx0, gy0, gx1, gy1] as [number, number, number, number],
    };
  });
}

/** Projeta e enquadra todas as geometrias do primeiro objeto num retângulo de `largura` px. */
export function projetar(topo: Topologia, largura = 1000): MapaProjetado {
  const geometrias = geometriasDe(topo);
  if (!geometrias.length) return { largura, altura: 0, formas: [], projecao: { k: 1, x0: 0, y0: 0, escala: 1 } };
  let minLat = Infinity;
  let maxLat = -Infinity;
  for (const g of geometrias) {
    for (const r of g.aneis) {
      for (const [, lat] of r) {
        if (lat < minLat) minLat = lat;
        if (lat > maxLat) maxLat = lat;
      }
    }
  }
  const k = Math.cos((((minLat + maxLat) / 2) * Math.PI) / 180);
  let x0 = Infinity;
  let y0 = Infinity;
  let x1 = -Infinity;
  let y1 = -Infinity;
  for (const g of geometrias) {
    for (const r of g.aneis) {
      for (const [lon, lat] of r) {
        const x = lon * k;
        const y = -lat;
        if (x < x0) x0 = x;
        if (x > x1) x1 = x;
        if (y < y0) y0 = y;
        if (y > y1) y1 = y;
      }
    }
  }
  const escala = largura / Math.max(x1 - x0, 1e-9);
  const altura = Math.round((y1 - y0) * escala);
  const projecao: Projecao = { k, x0, y0, escala };
  return { largura, altura, formas: formasDe(geometrias, projecao, 1), projecao };
}

/** Formas de outra malha (o contorno fino de um município) no enquadramento de um mapa já projetado. */
export function projetarCom(topo: Topologia, projecao: Projecao, casas = 3): Forma[] {
  return formasDe(geometriasDe(topo), projecao, casas);
}
