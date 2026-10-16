"use client";

/**
 * Tela de panorama: o cargo visto de uma abrangência acima daquela em que é
 * disputado (governadores no Brasil, prefeitos na UF). Mostra os 30 primeiros
 * partidos do placar e a lista das partes, com filtro quando passam de 30.
 */

import { useMemo, useState } from "react";
import { Paginacao, usePaginacao } from "@/componentes/Paginacao";
import { normalizar } from "@/lib/busca";
import { varCor } from "@/lib/cores";
import { numero, percentual } from "@/lib/formato";
import type { FeedPanorama, Parte } from "@/lib/tipos";

/** Entrada do panorama: o feed, como chamar as partes e o que fazer ao escolher uma delas. */
interface Props {
  feed: FeedPanorama;
  /** "UF" quando as partes são estados; "município" quando são municípios. */
  rotuloParte: "estado" | "município";
  onSelecionar: (parte: Parte) => void;
}

/** Placar por partido e a lista das partes com quem lidera em cada uma. */
export function Panorama({ feed, rotuloParte, onSelecionar }: Props) {
  const [filtro, setFiltro] = useState("");
  const proporcional = feed.cargo.tipo === "proporcional";
  const partes = useMemo(() => {
    const t = normalizar(filtro);
    const lista = t ? feed.partes.filter((p) => normalizar(p.nome).includes(t)) : feed.partes;
    return [...lista].sort((a, b) => a.nome.localeCompare(b.nome, "pt-BR"));
  }, [feed.partes, filtro]);
  const plural = rotuloParte === "estado" ? "estados" : "municípios";
  const paginaPartidos = usePaginacao(feed.partidos);
  const paginaPartes = usePaginacao(partes);
  return (
    <section className="cartao cartao-corpo" aria-labelledby="titulo-panorama">
      <h2 id="titulo-panorama" className="titulo-secao">
        {proporcional ? "Eleitos por partido" : `Partidos à frente nos ${plural}`}
      </h2>
      <table className="tabela">
        <thead>
          <tr>
            <th>Partido</th>
            <th className="n">{proporcional ? `${rotuloParte === "estado" ? "Estados" : "Municípios"} onde é o mais votado` : "À frente em"}</th>
            <th className="n">Eleitos</th>
          </tr>
        </thead>
        <tbody>
          {paginaPartidos.visiveis.map((p) => (
            <tr key={p.partido}>
              <td>
                <span className="legenda-item">
                  <span className="amostra-cor" style={{ background: varCor(p.cor) }} />
                  {p.partido}
                </span>
              </td>
              <td className="n">{numero(p.liderados)}</td>
              <td className="n">{numero(p.eleitos)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <Paginacao {...paginaPartidos} rotulo="partidos" />
      <details style={{ marginTop: 16 }} open={feed.partes.length <= 30}>
        <summary>
          {rotuloParte === "estado" ? "Estados" : "Municípios"} ({numero(feed.partes.length)})
        </summary>
        {feed.partes.length > 20 && (
          <input
            className="seletor"
            style={{ width: "100%", margin: "8px 0" }}
            placeholder={`Filtrar ${plural}`}
            value={filtro}
            onChange={(e) => setFiltro(e.target.value)}
            aria-label={`Filtrar ${plural}`}
          />
        )}
        <table className="tabela">
          <thead>
            <tr>
              <th>{rotuloParte === "estado" ? "Estado" : "Município"}</th>
              <th>{proporcional ? "Partido mais votado" : "À frente"}</th>
              <th className="n">%</th>
            </tr>
          </thead>
          <tbody>
            {paginaPartes.visiveis.map((p) => (
              <tr key={p.codigo} className="clicavel">
                <td>
                  <button type="button" className="botao-link" onClick={() => onSelecionar(p)}>
                    {p.nome}
                  </button>
                </td>
                <td>
                  <span className="legenda-item">
                    <span className="amostra-cor" style={{ background: varCor(p.cor) }} />
                    {p.nome_urna ? `${p.nome_urna} (${p.partido ?? "—"})` : (p.partido ?? "—")}
                    {p.eleito ? " · eleito" : p.segundo_turno ? " · 2º turno" : ""}
                  </span>
                </td>
                <td className="n">{percentual(p.pct)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <Paginacao {...paginaPartes} rotulo={plural} />
      </details>
    </section>
  );
}
