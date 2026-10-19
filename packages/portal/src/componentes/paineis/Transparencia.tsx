"use client";

/**
 * Portais de transparência do ente, avaliados pelo PNTP (tribunais de contas e Atricon): uma linha por entidade
 * (prefeitura, câmara, poderes, consórcios, estatais), com o nível, o índice e o link do portal. Aparece na
 * página do ente em Conformidade (ADR-035).
 */

import { useEffect, useState } from "react";
import { Paginacao, usePaginacao } from "@/componentes/Paginacao";
import { percentual } from "@/lib/formato";
import { dataCurta } from "@/lib/paineis";
import { carregarTransparencia, type EntidadeTransparencia, type FeedTransparencia } from "@/lib/transparencia";

/** O andamento da leitura da avaliação. */
type Estado = { fase: "carregando" } | { fase: "pronto"; feed: FeedTransparencia | null; entidades: EntidadeTransparencia[] }
  | { fase: "erro" };

/** A seção dos portais de transparência de um ente. */
export function Transparencia({ codigo }: { codigo: string }) {
  const [estado, setEstado] = useState<Estado>({ fase: "carregando" });
  useEffect(() => {
    const c = new AbortController();
    setEstado({ fase: "carregando" });
    carregarTransparencia(codigo, c.signal)
      .then((r) => setEstado({ fase: "pronto", feed: r?.feed ?? null, entidades: r?.entidades ?? [] }))
      .catch((e: Error) => {
        if (e.name !== "AbortError") setEstado({ fase: "erro" });
      });
    return () => c.abort();
  }, [codigo]);
  const pagina = usePaginacao(estado.fase === "pronto" ? estado.entidades : []);

  return (
    <section className="cartao cartao-corpo" aria-labelledby="titulo-transparencia">
      <h2 id="titulo-transparencia" className="titulo-secao">Portais de transparência (PNTP)</h2>
      {estado.fase === "carregando" && <p className="busca-detalhe">Carregando…</p>}
      {estado.fase === "erro" && <p className="busca-detalhe">A avaliação do PNTP não pôde ser lida agora.</p>}
      {estado.fase === "pronto" && !estado.feed && (
        <p className="busca-detalhe">A avaliação do PNTP ainda não foi publicada pelo Lumen.</p>
      )}
      {estado.fase === "pronto" && estado.feed && estado.entidades.length === 0 && (
        <p className="busca-detalhe">Nenhuma entidade deste ente no ciclo {estado.feed.ciclo} do PNTP.</p>
      )}
      {estado.fase === "pronto" && estado.feed && estado.entidades.length > 0 && (
        <>
          <div className="tabela-rolavel">
            <table className="tabela">
              <thead>
                <tr>
                  <th>Entidade</th>
                  <th>Nível</th>
                  <th className="n">Índice</th>
                  <th>Portal</th>
                </tr>
              </thead>
              <tbody>
                {pagina.visiveis.map((e) => (
                  <tr key={e.codigo_entidade}>
                    <td>
                      {e.entidade}
                      <div className="busca-detalhe">{e.poder ?? "—"}</div>
                    </td>
                    <td>
                      {e.avaliada ? e.nivel ?? "—" : "Não avaliada"}
                      {e.nivel_anterior && e.nivel_anterior !== e.nivel && (
                        <div className="busca-detalhe">antes: {e.nivel_anterior}</div>
                      )}
                    </td>
                    <td className="n">{e.indice !== null ? percentual(e.indice * 100) : "—"}</td>
                    <td>
                      {e.link ? (
                        <a href={e.link.startsWith("http") ? e.link : `https://${e.link}`} target="_blank" rel="noreferrer">
                          abrir o portal
                        </a>
                      ) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Paginacao {...pagina} rotulo="entidades" />
          <p className="busca-detalhe">
            Ciclo {estado.feed.ciclo} do{" "}
            {estado.feed.url ? <a href={estado.feed.url} target="_blank" rel="noreferrer">PNTP</a> : "PNTP"} (tribunais
            de contas e Atricon), coletado em {dataCurta(estado.feed.coletado_em)}. O índice é a parte dos critérios
            avaliados que o portal atende; não é nota sobre a gestão do ente.
          </p>
        </>
      )}
    </section>
  );
}
