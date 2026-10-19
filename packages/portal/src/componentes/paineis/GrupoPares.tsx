"use client";

/**
 * Grupo de pares do ente na conformidade (ADR-038; UC-06): quais entes são comparáveis a ele, por quais
 * critérios, e como a fração entregue no prazo se distribui entre eles. É contexto, não avaliação: a tela não
 * ordena nem classifica o ente pela posição no grupo, e a lista dos entes vem por nome (PUB-07).
 */

import Link from "next/link";
import { useEffect, useState } from "react";
import { Paginacao, usePaginacao } from "@/componentes/Paginacao";
import { numero, percentual } from "@/lib/formato";
import {
  carregarConformidadePares,
  faixaCentral,
  type EntePares,
  type ParesConformidade,
  type ResumoConformidade,
} from "@/lib/paineis";
import { Numero } from "./Comuns";

const METODO = "https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-038.md";

/** A lista dos entes do grupo: fechada, carregando, lida ou com erro. */
type Lista = { fase: "fechada" } | { fase: "carregando" } | { fase: "pronta"; entes: EntePares[] } | { fase: "erro" };

/** A seção do grupo de pares; não aparece nos arquivos publicados antes dele. */
export function GrupoPares({ pares, resumo }: { pares: ParesConformidade | undefined; resumo: ResumoConformidade }) {
  const [lista, setLista] = useState<Lista>({ fase: "fechada" });
  const id = pares?.grupo?.id ?? null;
  useEffect(() => setLista({ fase: "fechada" }), [id]);
  const pagina = usePaginacao(lista.fase === "pronta" ? lista.entes : []);
  if (!pares) return null;

  const abrir = () => {
    if (!id) return;
    setLista({ fase: "carregando" });
    carregarConformidadePares(id)
      .then((r) => setLista(r ? { fase: "pronta", entes: r.entes } : { fase: "erro" }))
      .catch(() => setLista({ fase: "erro" }));
  };

  return (
    <section className="cartao cartao-corpo" aria-labelledby="titulo-pares">
      <h2 id="titulo-pares" className="titulo-secao">Grupo de pares</h2>
      {!pares.grupo ? (
        <p className="busca-detalhe">Sem grupo de pares: {pares.motivo}. A comparação fica de fora.</p>
      ) : (
        <>
          <p>
            {pares.grupo.descricao} · {numero(pares.grupo.entes)} entes
          </p>
          {pares.grupo.criterios.motivo && (
            <p className="busca-detalhe">
              Na região, o grupo teria menos de {pares.grupo.criterios.minimo_entes} municípios: a comparação é
              com o mesmo porte em todo o país.
            </p>
          )}
          {pares.grupo.abaixo_do_minimo && (
            <p className="busca-detalhe">
              Grupo com menos de {pares.grupo.criterios.minimo_entes} entes: pouca base para comparar.
            </p>
          )}
          <div className="totais">
            <Numero
              rotulo="Este ente, entregues no prazo"
              valor={resumo.no_prazo === null ? "sem obrigação avaliável" : percentual(resumo.no_prazo * 100)}
            />
            <Numero
              rotulo="Mediana do grupo"
              valor={pares.no_prazo ? percentual(pares.no_prazo.mediana * 100) : "—"}
              detalhe={pares.no_prazo ? `metade dos entes ${faixaCentral(pares.no_prazo)}` : undefined}
            />
            <Numero rotulo="Entes do grupo com obrigação avaliável" valor={numero(pares.no_prazo?.entes ?? 0)} />
          </div>
          <p className="busca-detalhe">
            Critérios: porte pela população (classes de tamanho do IBGE) e região; a receita corrente líquida
            ainda não entra. A posição no grupo é contexto, não avaliação do ente.{" "}
            <a href={METODO} target="_blank" rel="noreferrer">
              Como o grupo é formado
            </a>
            .
          </p>
          {lista.fase === "fechada" && (
            <button type="button" className="botao-link" onClick={abrir}>
              ver os {numero(pares.grupo.entes)} entes do grupo
            </button>
          )}
          {lista.fase === "carregando" && <p className="busca-detalhe">Carregando…</p>}
          {lista.fase === "erro" && <p className="busca-detalhe">A lista do grupo não pôde ser lida agora.</p>}
          {lista.fase === "pronta" && (
            <>
              <div className="tabela-rolavel">
                <table className="tabela">
                  <thead>
                    <tr>
                      <th>Ente</th>
                      <th>UF</th>
                      <th className="n">População</th>
                      <th className="n">No prazo</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pagina.visiveis.map((e) => (
                      <tr key={e.codigo}>
                        <td>
                          <Link href={`/conformidade/?ente=${e.codigo}`}>{e.nome}</Link>
                        </td>
                        <td>{e.uf ?? "—"}</td>
                        <td className="n">{numero(e.populacao)}</td>
                        <td className="n">{e.no_prazo === null ? "—" : percentual(e.no_prazo * 100)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <Paginacao {...pagina} rotulo="entes" />
            </>
          )}
        </>
      )}
    </section>
  );
}
