/**
 * Página `/parlamentares/vereadores/`: as câmaras municipais com dados do SAPL do Interlegis (ADR-062). O trabalho é
 * do `PainelCamaras`, que roda no navegador e lê `parlamentares/municipal/indice.json`.
 */

import type { Metadata } from "next";
import { Suspense } from "react";
import { PainelCamaras } from "@/componentes/parlamentares/PainelCamaras";

/** Título e descrição da página, usados pelo navegador e nas prévias de link. */
export const metadata: Metadata = {
  title: "Vereadores",
  description:
    "As câmaras municipais com os vereadores: projetos apresentados, presença nas sessões e o voto de cada um nas " +
    "votações nominais, pelo SAPL do Interlegis.",
};

/** Título e o painel, que lê a URL com `useSearchParams` e por isso fica dentro de `Suspense`. */
export default function Vereadores() {
  return (
    <div className="painel">
      <div className="painel-topo">
        <h1>Parlamentares</h1>
      </div>
      <Suspense fallback={<p>Carregando…</p>}>
        <PainelCamaras />
      </Suspense>
    </div>
  );
}
