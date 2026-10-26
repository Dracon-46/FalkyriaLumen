"use client";

/**
 * Mapa do mundo do exterior: cada cidade em que brasileiros votam é um
 * círculo no lugar dela (`lib/exterior.ts`), com área proporcional ao
 * eleitorado e a cor do modo escolhido (quem lidera, a força da vitória...).
 *
 * Malha dos países: Natural Earth 1:110 milhões (domínio público), no formato
 * do pacote `world-atlas` 2.0.2, sem a Antártida, em `public/geo/mundo-110m.json`.
 * Os botões de região trocam o recorte; a lista abaixo do mapa tem as cidades
 * sem posição na tabela.
 */

import { useEffect, useMemo, useState } from "react";
import { coordenadaDaCidade, REGIOES_DO_MUNDO } from "@/lib/exterior";
import { carregarMalha } from "@/lib/feeds";
import { numero, percentual } from "@/lib/formato";
import type { Parte } from "@/lib/tipos";
import { type MapaProjetado, pontoProjetado, projetar } from "@/lib/topojson";

/** A malha dos países, servida com o próprio portal (não com os feeds). */
const MALHA_MUNDO = "/geo/mundo-110m.json";

/** Uma cidade pronta para desenhar: a parte, onde fica no SVG e o raio. */
interface Ponto {
  parte: Parte;
  x: number;
  y: number;
  r: number;
}

/**
 * Mapa do exterior. `corDe` é a cor da parte no modo do mapa; `escolhida`, a
 * cidade aberta (destacada); o clique abre a cidade.
 */
export function MapaExterior({
  partes,
  corDe,
  rotuloLider,
  onSelecionar,
  escolhida,
}: {
  partes: Parte[];
  corDe: (p: Parte | undefined) => string;
  rotuloLider: (p: Parte) => string;
  onSelecionar: (p: Parte) => void;
  escolhida?: string | null;
}) {
  const [mapa, setMapa] = useState<MapaProjetado | null>(null);
  const [falhou, setFalhou] = useState(false);
  const [regiao, setRegiao] = useState("mundo");
  const [sob, setSob] = useState<Ponto | null>(null);

  useEffect(() => {
    let vivo = true;
    carregarMalha(MALHA_MUNDO)
      .then((topo) => vivo && (topo ? setMapa(projetar(topo, 1000)) : setFalhou(true)))
      .catch(() => vivo && setFalhou(true));
    return () => {
      vivo = false;
    };
  }, []);

  const { pontos, semPosicao } = useMemo(() => {
    if (!mapa) return { pontos: [] as Ponto[], semPosicao: [] as Parte[] };
    const maior = Math.max(1, ...partes.map((p) => p.eleitorado ?? 0));
    const pontos: Ponto[] = [];
    const semPosicao: Parte[] = [];
    for (const p of partes) {
      const c = coordenadaDaCidade(p.codigo);
      if (!c) {
        semPosicao.push(p);
        continue;
      }
      const [x, y] = pontoProjetado(mapa.projecao, c[0], c[1]);
      // Área proporcional ao eleitorado: o raio vai de 1,5 a 9 unidades do mapa (de 1000 de largura)
      pontos.push({ parte: p, x, y, r: 1.5 + 7.5 * Math.sqrt((p.eleitorado ?? 0) / maior) });
    }
    // Os grandes por baixo: as cidades pequenas ao lado de uma grande continuam visíveis
    pontos.sort((a, b) => b.r - a.r);
    return { pontos, semPosicao };
  }, [mapa, partes]);

  if (falhou) return <div className="mapa-vazio">Mapa do mundo indisponível; as cidades estão na tabela.</div>;
  if (!mapa) return <div className="mapa-vazio mapa-carregando">Carregando o mapa…</div>;

  const caixa = (REGIOES_DO_MUNDO.find((r) => r.id === regiao) ?? REGIOES_DO_MUNDO[0]!).caixa;
  const [x0, y0] = pontoProjetado(mapa.projecao, caixa[0], caixa[3]);
  const [x1, y1] = pontoProjetado(mapa.projecao, caixa[2], caixa[1]);
  // Na região aproximada, círculos e traços encolhem junto, para não cobrirem o mapa
  const escala = (x1 - x0) / mapa.largura;
  const raio = (r: number) => r * Math.max(0.3, Math.sqrt(escala));

  return (
    <div className="mapa mapa-exterior">
      <div className="filtro-periodo-atalhos" role="group" aria-label="Região do mapa">
        {REGIOES_DO_MUNDO.map((r) => (
          <button key={r.id} type="button" className="botao" aria-pressed={r.id === regiao} onClick={() => setRegiao(r.id)}>
            {r.rotulo}
          </button>
        ))}
      </div>
      <svg viewBox={`${x0} ${y0} ${x1 - x0} ${y1 - y0}`} role="group" aria-label="Cidades do exterior no mapa do mundo"
        onPointerLeave={() => setSob(null)}>
        <g className="paises" aria-hidden="true">
          {mapa.formas.map((f, i) => (
            <path key={i} d={f.d} />
          ))}
        </g>
        <g className="cidades">
          {pontos.map((p) => (
            <circle
              key={p.parte.codigo}
              cx={p.x}
              cy={p.y}
              r={raio(p.r)}
              style={{ fill: corDe(p.parte) }}
              className={p.parte.codigo === escolhida ? "cidade-escolhida" : undefined}
              tabIndex={0}
              role="button"
              aria-label={`${p.parte.nome}: ${p.parte.lider ? `${rotuloLider(p.parte)} ${percentual(p.parte.pct)}` : "sem dados"}`}
              onPointerEnter={() => setSob(p)}
              onFocus={() => setSob(p)}
              onBlur={() => setSob(null)}
              onClick={() => onSelecionar(p.parte)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onSelecionar(p.parte);
                }
              }}
            />
          ))}
        </g>
      </svg>
      <p className="candidato-detalhe" aria-live="polite">
        {sob ? (
          <>
            <strong>{sob.parte.nome}</strong>
            {sob.parte.lider ? ` · ${rotuloLider(sob.parte)} ${percentual(sob.parte.pct)}` : " · sem dados"}
            {sob.parte.eleitorado ? ` · ${numero(sob.parte.eleitorado)} eleitores` : ""}
          </>
        ) : (
          "Cada círculo é uma cidade, com área proporcional ao eleitorado; passe o cursor para ver o resultado e clique para abrir."
        )}
      </p>
      {semPosicao.length > 0 && (
        <div className="legenda" aria-label="Cidades sem posição no mapa">
          {semPosicao.map((p) => (
            <button key={p.codigo} type="button" className="botao" onClick={() => onSelecionar(p)}>
              <span className="amostra-cor" style={{ background: corDe(p) }} />
              {p.nome}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
