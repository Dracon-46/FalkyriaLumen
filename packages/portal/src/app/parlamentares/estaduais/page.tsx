/**
 * Página `/parlamentares/estaduais/`: as Assembleias Legislativas com dados do SAPL do Interlegis (ADR-062). O
 * trabalho é do `PainelCamaras`, com a esfera estadual, que lê `parlamentares/estadual/indice.json`.
 */

import type { Metadata } from "next";
import { Suspense } from "react";
import { PainelCamaras } from "@/componentes/parlamentares/PainelCamaras";

/** Título e descrição da página, usados pelo navegador e nas prévias de link. */
export const metadata: Metadata = {
  title: "Deputados estaduais",
  description:
    "As Assembleias Legislativas com os deputados estaduais: projetos apresentados, presença nas sessões e o voto de " +
    "cada um nas votações nominais.",
};

/** Título e o painel, que lê a URL com `useSearchParams` e por isso fica dentro de `Suspense`. */
export default function DeputadosEstaduais() {
  return (
    <div className="painel">
      <div className="painel-topo">
        <h1>Parlamentares</h1>
      </div>
      <Suspense fallback={<p>Carregando…</p>}>
        <PainelCamaras esfera="estadual" />
      </Suspense>
    </div>
  );
}
