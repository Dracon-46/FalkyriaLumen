/**
 * Página `/contratacoes/`: o painel de contratações (ADR-028). O trabalho é do
 * `PainelContratacoes`, que roda no navegador e lê os arquivos publicados pelo
 * fluxo `paineis`; o site é exportado como estático.
 */

import type { Metadata } from "next";
import { Suspense } from "react";
import { PainelContratacoes } from "@/componentes/paineis/PainelContratacoes";

/** Título e descrição da página, usados pelo navegador e nas prévias de link. */
export const metadata: Metadata = {
  title: "Contratações",
  description:
    "O que a União, os estados e os municípios publicaram no PNCP: processos de contratação, contratos, órgãos e " +
    "fornecedores, com o link de cada publicação.",
};

/** Envolve o painel em `Suspense`: ele lê a URL com `useSearchParams`, que só existe no navegador. */
export default function Contratacoes() {
  return (
    <Suspense fallback={<p>Carregando…</p>}>
      <PainelContratacoes />
    </Suspense>
  );
}
