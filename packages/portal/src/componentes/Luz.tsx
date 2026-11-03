"use client";

/**
 * A luz da página inicial (ADR-061): pontos que se movem devagar e se ligam por linhas quando passam perto, como os
 * dados que o Lumen junta. Desenhada em canvas, sem biblioteca: as cores vêm das variáveis do tema (`--marca-1`,
 * `--marca-2` e `--luz`), o mouse puxa as ligações para perto, e a animação para com a aba escondida. Para quem pede
 * menos movimento no sistema, desenha uma vez, parada. É decorativa (`aria-hidden`).
 */

import { useEffect, useRef } from "react";

/** Um ponto: posição, velocidade, raio e qual das três cores usa. */
interface Ponto {
  x: number;
  y: number;
  vx: number;
  vy: number;
  r: number;
  cor: number;
}

/** Pixels de área por ponto: menos pontos em tela pequena. */
const AREA_POR_PONTO = 9000;
/** Distância até a qual dois pontos se ligam. */
const ALCANCE = 130;

/** O canvas que cobre o pai (que precisa de `position: relative`). */
export function Luz() {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    const parado = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const estilo = getComputedStyle(document.documentElement);
    const cores = ["--marca-1", "--marca-2", "--luz"].map((v) => estilo.getPropertyValue(v).trim() || "#7ea8ff");
    // Sobre o fundo claro, a mesma rede precisa de mais tinta para aparecer
    const forca = estilo.getPropertyValue("color-scheme").includes("dark") ? 1 : 1.8;
    let pontos: Ponto[] = [];
    let largura = 0;
    let altura = 0;
    let quadro = 0;
    const mouse = { x: -1e4, y: -1e4 };

    /** Ajusta o canvas ao tamanho do pai (com a densidade da tela) e espalha os pontos de novo. */
    const medir = () => {
      const caixa = canvas.getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      largura = caixa.width;
      altura = caixa.height;
      canvas.width = Math.round(largura * dpr);
      canvas.height = Math.round(altura * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const n = Math.max(24, Math.min(140, Math.round((largura * altura) / AREA_POR_PONTO)));
      pontos = Array.from({ length: n }, () => ({
        x: Math.random() * largura, y: Math.random() * altura,
        vx: (Math.random() - 0.5) * 0.35, vy: (Math.random() - 0.5) * 0.35,
        r: 1.2 + Math.random() * 1.8, cor: Math.random() < 0.12 ? 2 : Math.random() < 0.5 ? 0 : 1,
      }));
    };

    /** Um quadro: move os pontos, liga os próximos e desenha. */
    const desenhar = () => {
      ctx.clearRect(0, 0, largura, altura);
      for (const p of pontos) {
        if (!parado) {
          p.x += p.vx;
          p.y += p.vy;
          if (p.x < 0 || p.x > largura) p.vx *= -1;
          if (p.y < 0 || p.y > altura) p.vy *= -1;
        }
      }
      for (let i = 0; i < pontos.length; i++) {
        const a = pontos[i]!;
        for (let j = i + 1; j < pontos.length; j++) {
          const b = pontos[j]!;
          const d = Math.hypot(a.x - b.x, a.y - b.y);
          if (d > ALCANCE) continue;
          const perto = Math.hypot((a.x + b.x) / 2 - mouse.x, (a.y + b.y) / 2 - mouse.y) < 160 ? 1.8 : 1;
          ctx.globalAlpha = Math.min(1, (1 - d / ALCANCE) * 0.3 * perto * forca);
          ctx.strokeStyle = cores[a.cor]!;
          ctx.lineWidth = 0.8;
          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(b.x, b.y);
          ctx.stroke();
        }
      }
      for (const p of pontos) {
        ctx.globalAlpha = Math.min(1, (p.cor === 2 ? 0.95 : 0.7) * forca);
        ctx.fillStyle = cores[p.cor]!;
        ctx.shadowColor = cores[p.cor]!;
        ctx.shadowBlur = p.cor === 2 ? 12 : 6;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.shadowBlur = 0;
      ctx.globalAlpha = 1;
      if (!parado && !document.hidden) quadro = requestAnimationFrame(desenhar);
    };

    /** Volta a animar quando a aba aparece de novo. */
    const visibilidade = () => {
      cancelAnimationFrame(quadro);
      if (!document.hidden && !parado) quadro = requestAnimationFrame(desenhar);
    };
    /** Guarda a posição do mouse em relação ao canvas. */
    const mover = (e: PointerEvent) => {
      const caixa = canvas.getBoundingClientRect();
      mouse.x = e.clientX - caixa.left;
      mouse.y = e.clientY - caixa.top;
    };

    medir();
    desenhar();
    const observador = new ResizeObserver(() => {
      medir();
      if (parado) desenhar();
    });
    observador.observe(canvas);
    document.addEventListener("visibilitychange", visibilidade);
    window.addEventListener("pointermove", mover, { passive: true });
    return () => {
      cancelAnimationFrame(quadro);
      observador.disconnect();
      document.removeEventListener("visibilitychange", visibilidade);
      window.removeEventListener("pointermove", mover);
    };
  }, []);

  return <canvas ref={ref} aria-hidden="true" />;
}
