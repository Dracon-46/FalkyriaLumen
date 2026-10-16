"use client";

/**
 * Série histórica de um indicador, em SVG direto como os outros gráficos do portal: uma linha no tempo, a
 * grade, a linha do zero quando a série cruza o zero, e as faixas dos períodos que estão sendo comparados.
 * O cursor (ou o teclado, pelas setas) mostra o valor de cada mês; a mesma série fica em tabela, recolhida.
 */

import { useMemo, useRef, useState } from "react";
import { Paginacao, usePaginacao } from "@/componentes/Paginacao";
import { type Periodo, periodoCurto, valorNaUnidade } from "@/lib/economia";

const L = 640;
const A = 240;
const M = { esq: 56, dir: 12, topo: 12, base: 28 };

/** Ano com fração do mês (`2025-07` → 2025,5); na série anual, o meio do ano. */
function tempo(periodo: string): number {
  if (periodo.length === 4) return Number(periodo) + 0.5;
  return Number(periodo.slice(0, 4)) + (Number(periodo.slice(5, 7)) - 1) / 12;
}

/** Marcas redondas para o eixo vertical (3 a 6 linhas). */
function marcas(min: number, max: number): number[] {
  const bruto = (max - min) / 4 || 1;
  const potencia = 10 ** Math.floor(Math.log10(bruto));
  const passo = [1, 2, 2.5, 5, 10].map((f) => f * potencia).find((p) => p >= bruto) ?? bruto;
  const saida = [];
  for (let v = Math.floor(min / passo) * passo; v <= max + passo / 2; v += passo) saida.push(Number(v.toFixed(10)));
  return saida;
}

/** Linha do indicador no tempo, com as faixas dos períodos comparados (A e B). */
export function GraficoLinha({
  titulo,
  serie,
  unidade,
  faixas = [],
}: {
  titulo: string;
  serie: [string, number][];
  unidade: string;
  faixas?: (Periodo & { classe: string })[];
}) {
  const [foco, setFoco] = useState<number | null>(null);
  const svg = useRef<SVGSVGElement>(null);
  const invertida = useMemo(() => [...serie].reverse(), [serie]);
  const tabela = usePaginacao(invertida);
  const dados = useMemo(() => {
    if (serie.length < 2) return null;
    const t0 = tempo(serie[0]![0]);
    const t1 = tempo(serie[serie.length - 1]![0]);
    const valores = serie.map(([, v]) => v);
    let min = Math.min(...valores);
    let max = Math.max(...valores);
    if (min === max) {
      min -= 1;
      max += 1;
    }
    const grade = marcas(min, max);
    return { t0, t1, grade, min: Math.min(min, grade[0]!), max: Math.max(max, grade[grade.length - 1]!) };
  }, [serie]);
  if (!dados) return <p className="situacao-painel">Série curta demais para o gráfico.</p>;

  const px = (t: number) => M.esq + ((t - dados.t0) / (dados.t1 - dados.t0 || 1)) * (L - M.esq - M.dir);
  const py = (v: number) => M.topo + (1 - (v - dados.min) / (dados.max - dados.min)) * (A - M.topo - M.base);
  const anos = Array.from(new Set(serie.map(([k]) => Number(k.slice(0, 4)))));
  const passoAno = Math.max(1, Math.ceil(anos.length / 8));
  const rotulosAno = anos.filter((a) => a % passoAno === 0);

  const mover = (clienteX: number) => {
    const r = svg.current?.getBoundingClientRect();
    if (!r) return;
    const x = ((clienteX - r.left) / r.width) * L;
    let melhor = 0;
    serie.forEach(([k], i) => {
      if (Math.abs(px(tempo(k)) - x) < Math.abs(px(tempo(serie[melhor]![0])) - x)) melhor = i;
    });
    setFoco(melhor);
  };
  const teclado = (e: React.KeyboardEvent) => {
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    e.preventDefault();
    const atual = foco ?? serie.length - 1;
    setFoco(Math.max(0, Math.min(serie.length - 1, atual + (e.key === "ArrowRight" ? 1 : -1))));
  };
  const ponto = foco !== null ? serie[foco] : null;

  return (
    <figure className="grafico grafico-linha">
      <svg
        ref={svg}
        viewBox={`0 0 ${L} ${A}`}
        role="img"
        aria-label={titulo}
        tabIndex={0}
        onPointerMove={(e) => mover(e.clientX)}
        onPointerLeave={() => setFoco(null)}
        onKeyDown={teclado}
        onBlur={() => setFoco(null)}
      >
        {faixas.map((f) => {
          const x0 = Math.max(M.esq, px(tempo(f.de)));
          const x1 = Math.min(L - M.dir, px(tempo(f.ate) + 1 / 12));
          return x1 > x0 ? (
            <rect key={f.classe} className={f.classe} x={x0} y={M.topo} width={x1 - x0} height={A - M.topo - M.base} />
          ) : null;
        })}
        {dados.grade.map((v) => (
          <g key={v}>
            <line className={v === 0 ? "eixo" : "grade-linha"} x1={M.esq} x2={L - M.dir} y1={py(v)} y2={py(v)} />
            <text x={M.esq - 6} y={py(v) + 4} textAnchor="end">
              {v.toLocaleString("pt-BR")}
            </text>
          </g>
        ))}
        {rotulosAno.map((a) => (
          <text key={a} x={px(a + 0.5)} y={A - 8} textAnchor="middle">
            {a}
          </text>
        ))}
        <polyline
          className="linha-serie"
          fill="none"
          strokeWidth={2}
          strokeLinejoin="round"
          points={serie.map(([k, v]) => `${px(tempo(k)).toFixed(1)},${py(v).toFixed(1)}`).join(" ")}
        />
        {ponto && (
          <>
            <line className="eixo" x1={px(tempo(ponto[0]))} x2={px(tempo(ponto[0]))} y1={M.topo} y2={A - M.base} />
            <circle className="ponto-serie" cx={px(tempo(ponto[0]))} cy={py(ponto[1])} r={4} />
          </>
        )}
      </svg>
      <figcaption className="candidato-detalhe" aria-live="polite">
        {ponto
          ? `${periodoCurto(ponto[0])}: ${valorNaUnidade(ponto[1], unidade)}`
          : `${periodoCurto(serie[0]![0])} a ${periodoCurto(serie[serie.length - 1]![0])} · passe o cursor ou use as setas`}
      </figcaption>
      <details>
        <summary>Ver os dados em tabela</summary>
        <div className="tabela-rolavel">
          <table className="tabela">
            <thead>
              <tr>
                <th scope="col">Período</th>
                <th scope="col" className="num">
                  Valor ({unidade})
                </th>
              </tr>
            </thead>
            <tbody>
              {tabela.visiveis.map(([k, v]) => (
                <tr key={k}>
                  <td>{periodoCurto(k)}</td>
                  <td className="num">{v.toLocaleString("pt-BR", { maximumFractionDigits: 4 })}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Paginacao {...tabela} rotulo="valores da série" />
      </details>
    </figure>
  );
}
