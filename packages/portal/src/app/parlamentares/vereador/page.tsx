/**
 * Página `/parlamentares/vereador/?casa=<IBGE>&id=`: um vereador pelo id no SAPL da câmara (ADR-062). O trabalho é do
 * `PainelDeputado`, o mesmo dos deputados, com a casa da URL.
 */

import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { PainelDeputado } from "@/componentes/parlamentares/PainelDeputado";

/** Título e descrição da página, usados pelo navegador e nas prévias de link. */
export const metadata: Metadata = {
  title: "Vereador",
  description:
    "Um vereador: os votos nominais nos projetos, a presença nas sessões e os projetos que apresentou, por ano, pelo " +
    "SAPL da câmara municipal.",
};

/** Título, a volta para as câmaras e o painel, que lê a URL com `useSearchParams` e por isso fica dentro de `Suspense`. */
export default function PaginaVereador() {
  return (
    <div className="painel">
      <div className="painel-topo">
        <h1>Vereador</h1>
        <Link href="/parlamentares/vereadores/">todas as câmaras</Link>
      </div>
      <Suspense fallback={<p>Carregando…</p>}>
        <PainelDeputado />
      </Suspense>
    </div>
  );
}
