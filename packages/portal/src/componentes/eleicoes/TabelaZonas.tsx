"use client";

/**
 * Tabela das zonas eleitorais do município aberto, ligada ao mapa: passar o
 * cursor (ou o foco) numa linha destaca a zona no mapa, e o clique fixa o
 * destaque (o mesmo que clicar na zona). Quando o feed traz o resultado por
 * zona (eleições lidas dos dados abertos do TSE), mostra quem lidera em cada
 * uma; ao vivo, o TSE só publica o resultado do município, e a tabela fica
 * com o eleitorado e os locais de votação de cada zona.
 */

import { useMemo } from "react";
import { Paginacao, usePaginacao } from "@/componentes/Paginacao";
import { varCorMapa } from "@/lib/cores";
import { numero, percentual } from "@/lib/formato";
import type { ArquivoZonas, Parte } from "@/lib/tipos";

/** Entrada da tabela: o resultado e os números de cada zona, e as ações ligadas ao mapa. */
interface Props {
  /** Resultado por zona (partes do feed do município); vazio quando a fonte não publica por zona. */
  partes: Parte[];
  /** Zonas e locais de votação do município, quando o ano tem o mapa das zonas. */
  arquivo: ArquivoZonas | null;
  rotulo: (p: Parte) => string;
  /** Zona com o destaque fixado (clique). */
  escolhida: string | null;
  onEscolher: (zona: string) => void;
  /** Cursor ou foco numa linha: destaca a zona no mapa sem fixar. */
  onDestacar: (zona: string | null) => void;
}

/** Uma linha por zona, em ordem numérica, juntando o resultado do feed e os números do arquivo das zonas. */
export function TabelaZonas({ partes, arquivo, rotulo, escolhida, onEscolher, onDestacar }: Props) {
  const porZona = useMemo(() => new Map(partes.map((p) => [p.codigo, p] as const)), [partes]);
  const info = useMemo(() => new Map((arquivo?.zonas ?? []).map((z) => [z.zona, z] as const)), [arquivo]);
  const zonas = useMemo(
    () => [...new Set([...porZona.keys(), ...info.keys()])].sort((a, b) => Number(a) - Number(b)),
    [porZona, info],
  );
  const pagina = usePaginacao(zonas);
  if (zonas.length < 2) return null;
  const comResultado = partes.length > 0;
  return (
    <section className="cartao cartao-corpo so-tela" aria-labelledby="titulo-zonas">
      <h2 id="titulo-zonas" className="titulo-secao">
        Por zona eleitoral ({zonas.length})
      </h2>
      {!comResultado && (
        <p className="candidato-detalhe">
          O resultado por zona sai nos dados abertos do TSE depois da totalização; ao vivo, o sistema de resultados
          publica só o total do município.
        </p>
      )}
      <div className="tabela-rolavel">
        <table className="tabela tabela-zonas">
          <thead>
            <tr>
              <th>Zona</th>
              {comResultado && (
                <>
                  <th>Mais votado</th>
                  <th className="n">%</th>
                </>
              )}
              <th className="n">Eleitores</th>
              {arquivo && <th className="n so-largo">Locais</th>}
            </tr>
          </thead>
          <tbody onMouseLeave={() => onDestacar(null)}>
            {pagina.visiveis.map((z) => {
              const p = porZona.get(z);
              const i = info.get(z);
              return (
                <tr
                  key={z}
                  className={z === escolhida ? "clicavel linha-escolhida" : "clicavel"}
                  onMouseEnter={() => onDestacar(z)}
                >
                  <td>
                    <button
                      type="button"
                      className="botao-link"
                      aria-pressed={z === escolhida}
                      onClick={() => onEscolher(z)}
                      onFocus={() => onDestacar(z)}
                      onBlur={() => onDestacar(null)}
                    >
                      {comResultado && (
                        <span className="amostra-cor" style={{ background: varCorMapa(p?.lider ? p.cor : null) }} />
                      )}
                      Zona {z}
                    </button>
                  </td>
                  {comResultado && (
                    <>
                      <td>{p?.lider ? rotulo(p) : "—"}</td>
                      <td className="n">{percentual(p?.pct)}</td>
                    </>
                  )}
                  <td className="n">{numero(p?.eleitorado ?? i?.eleitores)}</td>
                  {arquivo && <td className="n so-largo">{numero(i?.locais)}</td>}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <Paginacao {...pagina} rotulo="zonas" />
    </section>
  );
}
