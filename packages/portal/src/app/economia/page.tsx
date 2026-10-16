/**
 * Página `/economia/`: Economia e Contas Públicas (ADR-033). O trabalho é do `PainelEconomia`, que roda no
 * navegador e lê `economia/indicadores.json`, publicado com os painéis; o site é exportado como estático.
 */

import type { Metadata } from "next";
import { Suspense } from "react";
import { PainelEconomia } from "@/componentes/economia/PainelEconomia";

/** Título e descrição da página, usados pelo navegador e nas prévias de link. */
export const metadata: Metadata = {
  title: "Economia e Contas Públicas",
  description:
    "Inflação, juros, dívida pública, resultado fiscal e atividade econômica, das séries oficiais do Banco Central e " +
    "do IBGE, com a fonte de cada número e a comparação entre períodos.",
};

/** Envolve o painel em `Suspense`: ele lê a URL com `useSearchParams`, que só existe no navegador. */
export default function Economia() {
  return (
    <Suspense fallback={<p>Carregando…</p>}>
      <PainelEconomia />
    </Suspense>
  );
}
