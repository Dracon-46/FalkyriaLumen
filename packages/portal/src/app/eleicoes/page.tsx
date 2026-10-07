/**
 * Página `/eleicoes/`: a aba Eleições. O trabalho todo é do `PainelEleicoes`,
 * que roda no navegador e lê os feeds; o site é exportado como estático, então
 * não há servidor de aplicação entre o leitor e os arquivos.
 */

import type { Metadata } from "next";
import { Suspense } from "react";
import { PainelEleicoes } from "@/componentes/eleicoes/PainelEleicoes";

/** Título e descrição da página, usados pelo navegador e nas prévias de link. */
export const metadata: Metadata = {
  title: "Eleições",
  description: "Resultados oficiais do TSE: apuração ao vivo e eleições desde 1994, por estado e município.",
};

/**
 * Envolve o painel em `Suspense`: ele lê a URL com `useSearchParams`, que só
 * existe no navegador. O HTML gerado no build traz o "Carregando…" do fallback.
 */
export default function Eleicoes() {
  return (
    <Suspense fallback={<p>Carregando…</p>}>
      <PainelEleicoes />
    </Suspense>
  );
}
