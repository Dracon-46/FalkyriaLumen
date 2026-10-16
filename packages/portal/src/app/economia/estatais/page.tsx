/**
 * Página `/economia/estatais/`: os gastos e investimentos das empresas estatais (ADR-034). O trabalho é do
 * `PainelEstatais`, que roda no navegador e lê `economia/estatais.json`, publicado com os painéis.
 */

import type { Metadata } from "next";
import { Suspense } from "react";
import { PainelEstatais } from "@/componentes/economia/PainelEstatais";

/** Título e descrição da página, usados pelo navegador e nas prévias de link. */
export const metadata: Metadata = {
  title: "Empresas estatais",
  description:
    "Quanto gastam e investem as empresas estatais, que não publicam no PNCP: as federais pelo Programa de " +
    "Dispêndios Globais da SEST e as com ações na bolsa pelas demonstrações entregues à CVM.",
};

/** Envolve o painel em `Suspense`: ele lê a URL com `useSearchParams`, que só existe no navegador. */
export default function Estatais() {
  return (
    <Suspense fallback={<p>Carregando…</p>}>
      <PainelEstatais />
    </Suspense>
  );
}
