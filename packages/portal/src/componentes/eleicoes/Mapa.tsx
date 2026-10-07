"use client";

/**
 * Mapa coroplético das partes (UFs no Brasil, municípios na UF), desenhado em
 * SVG a partir da malha do IBGE. Cada área leva a cor de quem está à frente,
 * mas só as três primeiras posições da paleta são pintadas: da quarta em
 * diante a área fica cinza ("Outros"), porque só essas três passam na
 * validação para daltonismo em todos os pares lado a lado (ADR-020). O nome
 * e o percentual de quem lidera continuam na dica e na tabela.
 *
 * Interativo: botões + e −, Ctrl (ou ⌘) + rolagem e pinça no trackpad para
 * aproximar em torno do cursor; arrastar para mover quando aproximado; dois
 * dedos na tela de toque; teclas +, − e 0 com o foco no mapa. A rolagem
 * simples continua rolando a página. As contas da janela estão em
 * `lib/zoom.ts`; a ligação área ↔ parte, em `lib/areas.ts`.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { chaveDaArea, indexarPartes, parteDaArea, partesSemArea } from "@/lib/areas";
import { UFS } from "@/lib/busca";
import { CORES_NO_MAPA, varCorMapa } from "@/lib/cores";
import { carregarMalha } from "@/lib/feeds";
import { numero, percentual } from "@/lib/formato";
import type { Parte } from "@/lib/tipos";
import { projetar, type MapaProjetado } from "@/lib/topojson";
import {
  aproximar,
  centro,
  deslocar,
  type Limites,
  PASSO_ZOOM,
  type Vista,
  viewBox,
  vistaInicial,
  zoomDe,
  ZOOM_MAXIMO,
} from "@/lib/zoom";

/** Entrada do mapa: a malha a desenhar, as partes do feed que a colorem e as ações de seleção. */
interface Props {
  /** URL da malha do IBGE (Brasil por UF, ou UF por município). */
  malha: string;
  /** "uf" quando as áreas são UFs (mapa do Brasil); "mu" quando são municípios. */
  nivel: "uf" | "mu";
  partes: Parte[];
  /** Código da parte em destaque (o município aberto, por exemplo). */
  selecionado?: string | null;
  onSelecionar: (parte: Parte) => void;
  /** Rótulo do que lidera: candidato (resultado) ou partido (panorama). */
  rotuloLider: (parte: Parte) => string;
  titulo: string;
}

/** Caixa flutuante da área sob o cursor ou com foco; `x` e `y` em pixels relativos ao contêiner do mapa. */
interface Dica {
  /** null quando a área não tem dados no feed. */
  parte: Parte | null;
  nome: string;
  x: number;
  y: number;
}

/** Arrasto em curso: onde começou (pixels), a janela de então e a escala pixel → malha. */
interface Arrasto {
  x0: number;
  y0: number;
  vista: Vista;
  escala: number;
  moveu: boolean;
}

/** Deslocamento, em pixels, a partir do qual o gesto é arrasto e não clique. */
const LIMIAR_ARRASTO = 5;

/** Os dois toques de uma pinça e a distância entre eles, ou null se não há exatamente dois. */
function pincaDe(dedos: Map<number, [number, number]>): { meio: [number, number]; distancia: number } | null {
  const [a, b] = [...dedos.values()];
  if (dedos.size !== 2 || !a || !b) return null;
  return { meio: [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2], distancia: Math.hypot(a[0] - b[0], a[1] - b[1]) };
}

/** Ponto da tela (clientX, clientY) em coordenadas da malha, pela matriz atual do SVG. */
function pontoNaMalha(svg: SVGSVGElement | null, cx: number, cy: number): [number, number] | null {
  const m = svg?.getScreenCTM?.();
  if (!svg || !m) return null;
  const p = new DOMPoint(cx, cy).matrixTransform(m.inverse());
  return [p.x, p.y];
}

/**
 * Baixa a malha (uma vez por visita, por `carregarMalha`), projeta e pinta.
 * Cada área com dados é um botão: clique, Enter ou espaço abre a parte, e o
 * foco pelo teclado mostra a mesma dica do cursor. Sem malha no servidor, o
 * mapa dá lugar a um aviso e a tabela segue com os números. Partes sem área
 * na malha (exterior, UFs que não existem mais) viram botões abaixo do mapa.
 */
export function Mapa({ malha, nivel, partes, selecionado, onSelecionar, rotuloLider, titulo }: Props) {
  const [mapa, setMapa] = useState<MapaProjetado | null>(null);
  const [falhou, setFalhou] = useState(false);
  const [dica, setDica] = useState<Dica | null>(null);
  const [ativo, setAtivo] = useState<string | null>(null);
  const [vista, setVista] = useState<Vista | null>(null);
  const [lembrete, setLembrete] = useState(false);
  const caixa = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const arrasto = useRef<Arrasto | null>(null);
  const dedos = useRef(new Map<number, [number, number]>());
  const pinca = useRef<number | null>(null);
  const cliqueBloqueado = useRef(false);

  useEffect(() => {
    let vivo = true;
    setMapa(null);
    setVista(null);
    setFalhou(false);
    carregarMalha(malha)
      .then((topo) => {
        if (!vivo) return;
        if (topo) setMapa(projetar(topo, 1000));
        else setFalhou(true);
      })
      .catch(() => vivo && setFalhou(true));
    return () => {
      vivo = false;
    };
  }, [malha]);

  const limites: Limites | null = useMemo(
    () => (mapa ? { largura: mapa.largura, altura: mapa.altura, maxZoom: ZOOM_MAXIMO } : null),
    [mapa],
  );
  const janela = vista ?? (limites ? vistaInicial(limites) : null);
  const zoom = janela && limites ? zoomDe(janela, limites) : 1;

  const porCodigo = useMemo(() => indexarPartes(partes), [partes]);

  const fora = useMemo(
    () => (mapa ? partesSemArea(partes, mapa.formas.map((f) => f.codigo), nivel) : []),
    [mapa, partes, nivel],
  );

  const lideres = useMemo(() => {
    // Legenda: quem lidera ao menos uma área, na ordem da cor; do 4º em diante, "Outros"
    const vistos = new Map<number, string>();
    for (const p of partes) {
      if (!p.lider) continue;
      const k = p.cor >= 0 && p.cor < CORES_NO_MAPA ? p.cor : CORES_NO_MAPA;
      if (!vistos.has(k)) vistos.set(k, k < CORES_NO_MAPA ? rotuloLider(p) : "Outros");
    }
    return [...vistos.entries()].sort((a, b) => a[0] - b[0]);
  }, [partes, rotuloLider]);

  /** Aproxima por `fator` em torno de um ponto da tela, ou do centro da janela sem ele. */
  const zoomEm = useCallback(
    (fator: number, cliente?: [number, number]) => {
      if (!limites) return;
      setVista((v) => {
        const atual = v ?? vistaInicial(limites);
        const ponto = (cliente && pontoNaMalha(svgRef.current, cliente[0], cliente[1])) ?? centro(atual);
        return aproximar(atual, fator, ponto, limites);
      });
      setDica(null);
    },
    [limites],
  );

  // Rolagem: com Ctrl/⌘ (e a pinça do trackpad, que chega assim) aproxima; sem, rola a página e lembra o atalho.
  // O ouvinte é nativo porque o do React é passivo e não pode impedir a rolagem.
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg || !limites) return;
    let id: number | undefined;
    const rolar = (e: WheelEvent) => {
      if (!(e.ctrlKey || e.metaKey)) {
        setLembrete(true);
        window.clearTimeout(id);
        id = window.setTimeout(() => setLembrete(false), 1400);
        return;
      }
      e.preventDefault();
      zoomEm(Math.exp(-e.deltaY * 0.0025), [e.clientX, e.clientY]);
    };
    svg.addEventListener("wheel", rolar, { passive: false });
    return () => {
      svg.removeEventListener("wheel", rolar);
      window.clearTimeout(id);
    };
  }, [limites, zoomEm]);

  if (falhou) {
    return (
      <div className="mapa-vazio">
        Mapa indisponível: as malhas do IBGE não estão neste servidor (o comando <code>lumen eleicoes preparar</code>{" "}
        instala as que vêm com o Lumen). Os resultados estão na tabela abaixo.
      </div>
    );
  }
  if (!mapa || !janela || !limites) return <div className="mapa-vazio">Carregando o mapa…</div>;

  const mostrar = (area: { codigo: string; centro: [number, number] }, evento?: React.PointerEvent) => {
    if (arrasto.current?.moveu) return;
    const parte = parteDaArea(porCodigo, area.codigo, nivel) ?? null;
    const chave = chaveDaArea(area.codigo, nivel);
    const nome = parte?.nome ?? (nivel === "uf" ? (UFS[chave] ?? chave) : chave);
    const r = caixa.current?.getBoundingClientRect();
    let x = 0;
    let y = 0;
    if (evento && r) {
      x = evento.clientX - r.left;
      y = evento.clientY - r.top;
    } else if (r) {
      // Foco pelo teclado: o centro da área, levado da malha para a tela pela matriz atual do SVG
      const m = svgRef.current?.getScreenCTM?.();
      if (m) {
        const p = new DOMPoint(area.centro[0], area.centro[1]).matrixTransform(m);
        x = p.x - r.left;
        y = p.y - r.top;
      }
    }
    setDica({ parte, nome, x, y });
    setAtivo(area.codigo);
  };
  const esconder = () => {
    setDica(null);
    setAtivo(null);
  };

  // ------------------------------------------------------------ arrasto e toque

  const aoPressionar = (e: React.PointerEvent<SVGSVGElement>) => {
    dedos.current.set(e.pointerId, [e.clientX, e.clientY]);
    cliqueBloqueado.current = false;
    const doisDedos = pincaDe(dedos.current);
    if (doisDedos) {
      pinca.current = doisDedos.distancia;
      arrasto.current = null;
      return;
    }
    const m = svgRef.current?.getScreenCTM?.();
    arrasto.current = { x0: e.clientX, y0: e.clientY, vista: janela, escala: m ? 1 / m.a : 1, moveu: false };
  };

  const aoMover = (e: React.PointerEvent<SVGSVGElement>) => {
    if (!dedos.current.has(e.pointerId)) return;
    dedos.current.set(e.pointerId, [e.clientX, e.clientY]);
    const doisDedos = pincaDe(dedos.current);
    if (doisDedos && pinca.current) {
      zoomEm(doisDedos.distancia / pinca.current, doisDedos.meio);
      pinca.current = doisDedos.distancia;
      cliqueBloqueado.current = true;
      return;
    }
    const g = arrasto.current;
    if (!g) return;
    const dx = e.clientX - g.x0;
    const dy = e.clientY - g.y0;
    if (!g.moveu && Math.hypot(dx, dy) < LIMIAR_ARRASTO) return;
    if (!g.moveu) {
      g.moveu = true;
      e.currentTarget.setPointerCapture?.(e.pointerId);
      esconder();
    }
    cliqueBloqueado.current = true;
    setVista(deslocar(g.vista, dx * g.escala, dy * g.escala, limites));
  };

  const aoSoltar = (e: React.PointerEvent<SVGSVGElement>) => {
    dedos.current.delete(e.pointerId);
    if (dedos.current.size < 2) pinca.current = null;
    if (dedos.current.size === 0) arrasto.current = null;
  };

  const abrir = (parte: Parte | undefined) => {
    // O clique que encerra um arrasto (ou uma pinça) não abre a área sob o cursor
    if (cliqueBloqueado.current) {
      cliqueBloqueado.current = false;
      return;
    }
    if (parte) onSelecionar(parte);
  };

  const teclas = (e: React.KeyboardEvent) => {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.key === "+" || e.key === "=") zoomEm(PASSO_ZOOM);
    else if (e.key === "-" || e.key === "_") zoomEm(1 / PASSO_ZOOM);
    else if (e.key === "0") setVista(null);
    else return;
    e.preventDefault();
  };

  // Contorno por cima de tudo: no SVG, quem é desenhado depois cobre a borda dos vizinhos
  const destaque = mapa.formas.find((f) => f.codigo === ativo);
  const marcado = selecionado
    ? mapa.formas.find((f) => f.codigo === selecionado || parteDaArea(porCodigo, f.codigo, nivel)?.codigo === selecionado)
    : undefined;
  const aproximado = zoom > 1.001;

  return (
    <div className="mapa" ref={caixa} onPointerLeave={esconder} onKeyDown={teclas}>
      <svg
        ref={svgRef}
        viewBox={viewBox(janela)}
        role="group"
        aria-label={titulo}
        className={aproximado ? "mapa-aproximado" : undefined}
        onPointerDown={aoPressionar}
        onPointerMove={aoMover}
        onPointerUp={aoSoltar}
        onPointerCancel={aoSoltar}
      >
        {mapa.formas.map((f) => {
          const parte = parteDaArea(porCodigo, f.codigo, nivel);
          const chave = chaveDaArea(f.codigo, nivel);
          const nome = parte?.nome ?? (nivel === "uf" ? (UFS[chave] ?? chave) : chave);
          const rotulo = parte?.lider
            ? `${nome}: ${rotuloLider(parte)} lidera${parte.pct != null ? ` com ${percentual(parte.pct)}` : ""}`
            : `${nome}: sem dados`;
          return (
            <path
              key={f.codigo}
              d={f.d}
              fill={varCorMapa(parte?.lider ? parte.cor : null)}
              tabIndex={parte ? 0 : -1}
              role="button"
              aria-label={rotulo}
              onPointerMove={(e) => mostrar(f, e)}
              onFocus={() => mostrar(f)}
              onBlur={esconder}
              onClick={() => abrir(parte)}
              onKeyDown={(e) => {
                if ((e.key === "Enter" || e.key === " ") && parte) {
                  e.preventDefault();
                  onSelecionar(parte);
                }
              }}
            />
          );
        })}
        {marcado && <path className="contorno contorno-selecionado" d={marcado.d} aria-hidden="true" />}
        {destaque && <path className="contorno" d={destaque.d} aria-hidden="true" />}
      </svg>

      <div className="mapa-controles" role="group" aria-label="Aproximação do mapa">
        <button type="button" className="botao" onClick={() => zoomEm(PASSO_ZOOM)} aria-label="Aproximar"
          title="Aproximar (tecla +)" disabled={zoom >= ZOOM_MAXIMO - 0.001}>
          +
        </button>
        <button type="button" className="botao" onClick={() => zoomEm(1 / PASSO_ZOOM)} aria-label="Afastar"
          title="Afastar (tecla −)" disabled={!aproximado}>
          −
        </button>
        {aproximado && (
          <button type="button" className="botao" onClick={() => setVista(null)} title="Mapa inteiro (tecla 0)">
            Ver tudo
          </button>
        )}
      </div>
      {lembrete && (
        <div className="mapa-lembrete" aria-hidden="true">
          Use Ctrl + rolagem (⌘ no Mac) ou os botões para aproximar
        </div>
      )}

      {dica && (
        <div
          className="dica"
          style={{
            left: Math.max(0, Math.min(dica.x + 14, (caixa.current?.clientWidth ?? 600) - 270)),
            top: dica.y + 14,
          }}
        >
          <div>
            <strong>{dica.nome}</strong>
          </div>
          {dica.parte?.lider ? (
            <>
              <div className="dica-valor">
                <span className="dica-chave" style={{ background: varCorMapa(dica.parte.cor) }} />
                {percentual(dica.parte.pct)} · {rotuloLider(dica.parte)}
              </div>
              {dica.parte.margem != null && (
                <div className="candidato-detalhe">Vantagem de {percentual(dica.parte.margem).replace("%", " p.p.")}</div>
              )}
              <div className="candidato-detalhe">
                {dica.parte.finalizada ? "Totalização concluída" : `${percentual(dica.parte.pct_secoes)} das seções`}
                {dica.parte.eleitorado ? ` · ${numero(dica.parte.eleitorado)} eleitores` : ""}
              </div>
            </>
          ) : (
            <div className="candidato-detalhe">Sem dados para esta área.</div>
          )}
        </div>
      )}
      {lideres.length > 0 && (
        <div className="legenda" aria-label="Legenda do mapa">
          {lideres.map(([cor, rotulo]) => (
            <span key={cor} className="legenda-item">
              <span className="amostra-cor" style={{ background: varCorMapa(cor) }} />
              {rotulo}
            </span>
          ))}
        </div>
      )}
      {fora.length > 0 && nivel === "uf" && (
        <div className="legenda" aria-label="Fora do mapa atual">
          {fora.map((p) => (
            <button key={p.codigo} type="button" className="botao" onClick={() => onSelecionar(p)}>
              <span className="amostra-cor" style={{ background: varCorMapa(p.lider ? p.cor : null) }} />
              {p.nome}: {p.lider ? `${rotuloLider(p)} ${percentual(p.pct)}` : "sem dados"}
            </button>
          ))}
        </div>
      )}
      {fora.length > 0 && nivel === "mu" && (
        <p className="candidato-detalhe">
          {fora.length === 1 ? "1 município não tem área" : `${numero(fora.length)} municípios não têm área`} na malha
          atual do IBGE e aparece{fora.length === 1 ? "" : "m"} só na tabela.
        </p>
      )}
    </div>
  );
}
