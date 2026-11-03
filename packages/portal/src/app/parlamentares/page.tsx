/**
 * Página `/parlamentares/`: os parlamentares e o que fizeram no mandato (ADR-060). Por enquanto, os deputados
 * federais. O trabalho é do `PainelParlamentares`, que roda no navegador e lê `parlamentares/` publicado com os painéis.
 */

import type { Metadata } from "next";
import { Suspense } from "react";
import { PainelParlamentares } from "@/componentes/parlamentares/PainelParlamentares";

/** Título e descrição da página, usados pelo navegador e nas prévias de link. */
export const metadata: Metadata = {
  title: "Parlamentares",
  description:
    "Os deputados federais: como votaram no Plenário, a presença nas sessões, as proposições que apresentaram e a " +
    "cota parlamentar, pelos dados abertos da Câmara dos Deputados.",
};

/** Título e o painel, que lê a URL com `useSearchParams` e por isso fica dentro de `Suspense`. */
export default function Parlamentares() {
  return (
    <div className="painel">
      <div className="painel-topo">
        <h1>Parlamentares</h1>
      </div>
      <Suspense fallback={<p>Carregando…</p>}>
        <PainelParlamentares />
      </Suspense>
    </div>
  );
}
