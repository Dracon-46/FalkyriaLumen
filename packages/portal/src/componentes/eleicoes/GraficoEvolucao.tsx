"use client";

/**
 * Gráfico de evolução da apuração, desenhado em SVG direto, sem biblioteca
 * de gráficos: são linhas, eixos e uma dica, e o `viewBox` fixo deixa o
 * navegador escalar o desenho para a largura disponível.
 */

import { useMemo, useRef, useState, type KeyboardEvent } from "react";
import { varCor } from "@/lib/cores";
import { escalaVertical, pontosDaEscala, seriesDaEvolucao, vantagem } from "@/lib/evolucao";
import { hora, percentual } from "@/lib/formato";
import type { FeedHistorico } from "@/lib/tipos";

const L = 640;
const A = 280;
const M = { esq: 52, dir: 120, topo: 12, base: 28 };
const SERIES = 4;

/** Valor do eixo vertical: até uma casa decimal, sem zeros sobrando. */
const decimal = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });

/** Pontos percentuais com sinal ("+2,4 p.p."); o zero vai sem sinal. */
function pontosPercentuais(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  const n = Math.abs(v) < 0.005 ? 0 : v;
  return `${n > 0 ? "+" : n < 0 ? "−" : ""}${decimal.format(Math.abs(n))} p.p.`;
}

/** Corta o nome de urna para caber na ponta direita do gráfico. */
function curto(rotulo: string): string {
  return rotulo.length > 16 ? `${rotulo.slice(0, 15)}…` : rotulo;
}

/**
 * Evolução dos votos válidos ao longo da apuração.
 *
 * Eixo horizontal: percentual de seções totalizadas (não o relógio) — é o que
 * mostra como a vantagem mudou conforme as urnas chegaram. Duas leituras, um
 * só eixo vertical em cada: **% dos válidos** (as quatro primeiras séries,
 * rotuladas na ponta, com legenda) e **vantagem** (diferença do primeiro para
 * o segundo, em pontos percentuais, com o zero marcado). A escala vertical se
 * ajusta à faixa dos dados a partir de 2% das seções (`pontosDaEscala`): numa
 * disputa apertada, as linhas não ficam coladas no meio de um eixo de 0 a 60%,
 * e a oscilação das primeiras urnas é recortada na borda. O detalhe abaixo mostra o ponto sob
 * o cursor (ou escolhido com as setas) e, sem foco, o último.
 */
export function GraficoEvolucao({ historico }: { historico: FeedHistorico }) {
  const [foco, setFoco] = useState<number | null>(null);
  const [modo, setModo] = useState<"pct" | "vantagem">("pct");
  const svg = useRef<SVGSVGElement>(null);

  const { series, xs, instantes } = useMemo(() => seriesDaEvolucao(historico, SERIES), [historico]);
  const linhaVantagem = useMemo(() => vantagem(series), [series]);

  if (xs.length < 2 || !series.length) return null;
  const comVantagem = linhaVantagem.length > 0;
  const verVantagem = modo === "vantagem" && comVantagem;
  const escala = verVantagem
    ? escalaVertical(pontosDaEscala(linhaVantagem).map((p) => p.y), { zero: true })
    : escalaVertical(series.flatMap((s) => pontosDaEscala(s.pontos).map((p) => p.y)));
  const px = (x: number) => M.esq + (x / 100) * (L - M.esq - M.dir);
  const py = (y: number) => M.topo + (1 - (y - escala.min) / (escala.max - escala.min)) * (A - M.topo - M.base);
  const ponto = foco ?? xs.length - 1;

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

  const teclar = (e: KeyboardEvent<SVGSVGElement>) => {
    const passo = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    if (!passo) return;
    e.preventDefault();
    setFoco((f) => Math.min(xs.length - 1, Math.max(0, (f ?? xs.length - 1) + passo)));
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
  const [primeiro, segundo] = series;
  const xFoco = px(xs[ponto] ?? 0);

  return (
    <section className="cartao cartao-corpo grafico" aria-labelledby="titulo-evolucao">
      <div className="grafico-cabeca">
        <h2 id="titulo-evolucao" className="titulo-secao">
          Evolução da apuração
        </h2>
        {comVantagem && (
          <span className="filtro-periodo-atalhos" role="group" aria-label="Leitura do gráfico">
            <button type="button" className="botao" aria-pressed={!verVantagem} onClick={() => setModo("pct")}>
              % dos válidos
            </button>
            <button type="button" className="botao" aria-pressed={verVantagem} onClick={() => setModo("vantagem")}>
              Vantagem
            </button>
          </span>
        )}
      </div>
      <svg
        ref={svg}
        viewBox={`0 0 ${L} ${A}`}
        role="img"
        tabIndex={0}
        aria-label={
          verVantagem
            ? `Diferença entre ${primeiro?.rotulo} e ${segundo?.rotulo}, em pontos percentuais, conforme as seções foram totalizadas`
            : "Percentual dos votos válidos de cada candidato conforme as seções foram totalizadas"
        }
        onPointerMove={(e) => mover(e.clientX)}
        onPointerLeave={() => setFoco(null)}
        onKeyDown={teclar}
        onBlur={() => setFoco(null)}
      >
        {escala.marcas.map((v) => (
          <g key={v}>
            <line className={verVantagem && v === 0 ? "eixo" : "grade-linha"} x1={M.esq} x2={L - M.dir} y1={py(v)} y2={py(v)} />
            <text x={M.esq - 6} y={py(v) + 4} textAnchor="end">
              {verVantagem ? pontosPercentuais(v).replace(" p.p.", "") : `${decimal.format(v)}%`}
            </text>
          </g>
        ))}
        {!verVantagem && <line className="eixo" x1={M.esq} x2={L - M.dir} y1={py(escala.min)} y2={py(escala.min)} />}
        {[0, 25, 50, 75, 100].map((v) => (
          <text key={v} x={px(v)} y={A - 8} textAnchor="middle">
            {v}%
          </text>
        ))}
        <defs>
          <clipPath id="recorte-evolucao">
            <rect x={M.esq} y={M.topo - 4} width={L - M.esq - M.dir + 8} height={A - M.topo - M.base + 8} />
          </clipPath>
        </defs>
        {verVantagem ? (
          <g clipPath="url(#recorte-evolucao)">
            <text x={M.esq + 6} y={M.topo + 12}>
              ↑ {primeiro?.rotulo} à frente
            </text>
            <text x={M.esq + 6} y={A - M.base - 6}>
              ↓ {segundo?.rotulo} à frente
            </text>
            <polyline
              fill="none"
              stroke={varCor(primeiro?.cor)}
              strokeWidth={2}
              strokeLinejoin="round"
              points={linhaVantagem.map((p) => `${px(p.x).toFixed(1)},${py(p.y).toFixed(1)}`).join(" ")}
            />
            <circle className="grafico-marca" cx={xFoco} cy={py(linhaVantagem[ponto]?.y ?? 0)} r={4}
              style={{ fill: varCor(primeiro?.cor) }} />
          </g>
        ) : (
          <>
            <g clipPath="url(#recorte-evolucao)">
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
              {series.map((s) => (
                <circle key={s.numero} className="grafico-marca" cx={xFoco} cy={py(s.pontos[ponto]?.y ?? 0)} r={4}
                  style={{ fill: varCor(s.cor) }} />
              ))}
            </g>
            {finais.map(({ s, y }) => (
              <text key={s.numero} x={L - M.dir + 8} y={y + 4} style={{ fill: "var(--texto)" }}>
                {curto(s.rotulo)}
              </text>
            ))}
          </>
        )}
        {foco !== null && <line className="eixo" x1={xFoco} x2={xFoco} y1={M.topo} y2={A - M.base} />}
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
      <div className="candidato-detalhe" aria-live="polite">
        <strong>{percentual(xs[ponto])}</strong> das seções{instantes[ponto] ? ` (${hora(instantes[ponto])})` : ""}:{" "}
        {series.map((s) => `${s.rotulo} ${percentual(s.pontos[ponto]?.y)}`).join(" · ")}
        {comVantagem && ` · diferença ${pontosPercentuais(linhaVantagem[ponto]?.y)}`}
      </div>
    </section>
  );
}
