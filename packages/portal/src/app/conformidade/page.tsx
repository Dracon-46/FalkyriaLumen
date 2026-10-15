/**
 * Página `/conformidade/`: o painel de conformidade fiscal (ADR-028). O
 * trabalho é do `PainelConformidade`, que roda no navegador e lê os arquivos
 * publicados pelo fluxo `paineis`; o site é exportado como estático.
 */

import type { Metadata } from "next";
import { Suspense } from "react";
import { PainelConformidade } from "@/componentes/paineis/PainelConformidade";

/** Título e descrição da página, usados pelo navegador e nas prévias de link. */
export const metadata: Metadata = {
  title: "Conformidade",
  description:
    "Se os relatórios da Lei de Responsabilidade Fiscal de cada estado e município constam do extrato do Tesouro " +
    "Nacional, e em que data, contra o prazo legal.",
};

/** Envolve o painel em `Suspense`: ele lê a URL com `useSearchParams`, que só existe no navegador. */
export default function Conformidade() {
  return (
    <Suspense fallback={<p>Carregando…</p>}>
      <PainelConformidade />
    </Suspense>
  );
}
