"use client";

/**
 * Gráfico de evolução da apuração, desenhado em SVG direto, sem biblioteca
 * de gráficos: são linhas, eixos e uma dica, e o `viewBox` fixo deixa o
 * navegador escalar o desenho para a largura disponível.
 */

import { useMemo, useRef, useState } from "react";
import { varCor } from "@/lib/cores";
import { hora, percentual } from "@/lib/formato";
import type { FeedHistorico } from "@/lib/tipos";

const L = 640;
const A = 240;
const M = { esq: 40, dir: 120, topo: 12, base: 28 };
const SERIES = 4;

/** A linha de um candidato: x = % de seções totalizadas, y = % dos votos no ponto. */
interface Serie {
  numero: string;
  rotulo: string;
  cor: number;
  pontos: { x: number; y: number }[];
}

/**
 * Evolução do percentual de votos válidos ao longo da apuração.
 *
 * Eixo horizontal: percentual de seções totalizadas (não o relógio) — é o que
 * mostra como a vantagem mudou conforme as urnas chegaram. Um só eixo
 * vertical, em % dos válidos; as quatro primeiras séries, rotuladas na ponta,
 * com legenda; a dica lista todas no ponto mais próximo do cursor.
 */
export function GraficoEvolucao({ historico }: { historico: FeedHistorico }) {
  const [foco, setFoco] = useState<number | null>(null);
  const svg = useRef<SVGSVGElement>(null);

  const { series, xs, instantes, maxY } = useMemo(() => {
    const pontos = historico.pontos.filter((p) => p.pct_secoes != null);
    const totais = pontos.map((p) => Object.values(p.votos).reduce((s, v) => s + v, 0));
    const ultimo = pontos[pontos.length - 1];
    const ordem = [...historico.candidatos]
      .sort((a, b) => (ultimo?.votos[b.numero] ?? 0) - (ultimo?.votos[a.numero] ?? 0))
      .slice(0, SERIES);
    let maxY = 0;
    const series: Serie[] = ordem.map((c) => ({
      numero: c.numero,
      rotulo: c.nome_urna,
      cor: c.cor,
      pontos: pontos.map((p, i) => {
        const total = totais[i] ?? 0;
        const y = total ? (100 * (p.votos[c.numero] ?? 0)) / total : 0;
        if (y > maxY) maxY = y;
        return { x: p.pct_secoes ?? 0, y };
      }),
    }));
    return { series, xs: pontos.map((p) => p.pct_secoes ?? 0), instantes: pontos.map((p) => p.t), maxY };
  }, [historico]);

  if (xs.length < 2 || !series.length) return null;
  const topoY = Math.min(100, Math.ceil((maxY + 5) / 10) * 10);
  const px = (x: number) => M.esq + (x / 100) * (L - M.esq - M.dir);
  const py = (y: number) => M.topo + (1 - y / topoY) * (A - M.topo - M.base);
  const marcasY = Array.from({ length: topoY / 10 + 1 }, (_, i) => i * 10).filter((v) => v % 20 === 0 || topoY <= 40);

  const mover = (clienteX: number) => {
    const r = svg.current?.getBoundingClientRect();
    if (!r) return;
    const x = ((clienteX - r.left) / r.width) * L;
    const valor = ((x - M.esq) / (L - M.esq - M.dir)) * 100;
    let melhor = 0;
    xs.forEach((v, i) => {
      if (Math.abs(v - valor) < Math.abs((xs[melhor] ?? 0) - valor)) melhor = i;
    });
    setFoco(melhor);
  };

  // Rótulos na ponta direita, afastados para não se sobreporem
  const finais = series
    .map((s) => ({ s, y: py(s.pontos[s.pontos.length - 1]?.y ?? 0) }))
    .sort((a, b) => a.y - b.y);
  for (let i = 1; i < finais.length; i++) {
    const anterior = finais[i - 1];
    const atual = finais[i];
    if (anterior && atual && atual.y - anterior.y < 14) atual.y = anterior.y + 14;
  }

  return (
    <section className="cartao cartao-corpo grafico" aria-labelledby="titulo-evolucao">
      <h2 id="titulo-evolucao" className="titulo-secao">
        Evolução da apuração
      </h2>
      <svg
        ref={svg}
        viewBox={`0 0 ${L} ${A}`}
        role="img"
        aria-label="Percentual dos votos válidos de cada candidato conforme as seções foram totalizadas"
        onPointerMove={(e) => mover(e.clientX)}
        onPointerLeave={() => setFoco(null)}
      >
        {marcasY.map((v) => (
          <g key={v}>
            <line className="grade-linha" x1={M.esq} x2={L - M.dir} y1={py(v)} y2={py(v)} />
            <text x={M.esq - 6} y={py(v) + 4} textAnchor="end">
              {v}%
            </text>
          </g>
        ))}
        <line className="eixo" x1={M.esq} x2={L - M.dir} y1={py(0)} y2={py(0)} />
        {[0, 25, 50, 75, 100].map((v) => (
          <text key={v} x={px(v)} y={A - 8} textAnchor="middle">
            {v}%
          </text>
        ))}
        {series.map((s) => (
          <polyline
            key={s.numero}
            fill="none"
            stroke={varCor(s.cor)}
            strokeWidth={2}
            strokeLinejoin="round"
            points={s.pontos.map((p) => `${px(p.x).toFixed(1)},${py(p.y).toFixed(1)}`).join(" ")}
          />
        ))}
        {finais.map(({ s, y }) => (
          <text key={s.numero} x={L - M.dir + 8} y={y + 4} style={{ fill: "var(--texto)" }}>
            {s.rotulo.length > 16 ? `${s.rotulo.slice(0, 15)}…` : s.rotulo}
          </text>
        ))}
        {foco !== null && (
          <line className="eixo" x1={px(xs[foco] ?? 0)} x2={px(xs[foco] ?? 0)} y1={M.topo} y2={py(0)} />
        )}
      </svg>
      <div className="legenda">
        {series.map((s) => (
          <span key={s.numero} className="legenda-item">
            <span className="dica-chave" style={{ background: varCor(s.cor) }} />
            {s.rotulo}
          </span>
        ))}
        <span className="legenda-item">Eixo horizontal: seções totalizadas</span>
      </div>
      {foco !== null && (
        <div className="candidato-detalhe" aria-live="polite">
          <strong>{percentual(xs[foco])}</strong> das seções{instantes[foco] ? ` (${hora(instantes[foco])})` : ""}:{" "}
          {series.map((s) => `${s.rotulo} ${percentual(s.pontos[foco]?.y)}`).join(" · ")}
        </div>
      )}
    </section>
  );
}
