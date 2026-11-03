/**
 * Página `/parlamentares/votacoes/`: as votações nominais do Plenário da Câmara, por ano, e cada uma com o voto de
 * cada partido e de cada deputado (ADR-060). O trabalho é do `PainelVotacoes`, que roda no navegador.
 */

import type { Metadata } from "next";
import { Suspense } from "react";
import { PainelVotacoes } from "@/componentes/parlamentares/PainelVotacoes";

/** Título e descrição da página, usados pelo navegador e nas prévias de link. */
export const metadata: Metadata = {
  title: "Votações na Câmara",
  description:
    "As votações nominais do Plenário da Câmara dos Deputados, ano a ano desde 2003: o resultado, a orientação do " +
    "Governo e como votou cada partido e cada deputado.",
};

/** Título e o painel, que lê a URL com `useSearchParams` e por isso fica dentro de `Suspense`. */
export default function Votacoes() {
  return (
    <div className="painel">
      <div className="painel-topo">
        <h1>Parlamentares</h1>
      </div>
      <Suspense fallback={<p>Carregando…</p>}>
        <PainelVotacoes />
      </Suspense>
    </div>
  );
}
