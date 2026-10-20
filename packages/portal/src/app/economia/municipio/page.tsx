/**
 * Página `/economia/municipio/`: os governos municipais de um município (ADR-040). O trabalho é do
 * `PainelGovernos`, que roda no navegador e lê as fontes sob demanda.
 */

import type { Metadata } from "next";
import { Suspense } from "react";
import { PainelGovernos } from "@/componentes/economia/PainelGovernos";

/** Título e descrição da página, usados pelo navegador e nas prévias de link. */
export const metadata: Metadata = {
  title: "Governos municipais",
  description:
    "Cada mandato de prefeito de um município, com quem foi eleito, a população e a despesa do município no " +
    "período, corrigida pela inflação e por habitante.",
};

/** Envolve o painel em `Suspense`: ele lê a URL com `useSearchParams`, que só existe no navegador. */
export default function GovernosMunicipais() {
  return (
    <Suspense fallback={<p>Carregando…</p>}>
      <PainelGovernos />
    </Suspense>
  );
}
