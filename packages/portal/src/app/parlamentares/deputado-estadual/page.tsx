/**
 * Página `/parlamentares/deputado-estadual/?casa=<código da UF>&id=`: um deputado estadual pelo id no SAPL da
 * Assembleia (ADR-062). O trabalho é do `PainelDeputado`, o mesmo dos deputados federais, com a casa da URL.
 */

import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { PainelDeputado } from "@/componentes/parlamentares/PainelDeputado";

/** Título e descrição da página, usados pelo navegador e nas prévias de link. */
export const metadata: Metadata = {
  title: "Deputado estadual",
  description:
    "Um deputado estadual: os votos nominais nos projetos, a presença nas sessões e os projetos que apresentou, por " +
    "ano, pelo SAPL da Assembleia Legislativa.",
};

/** Título, a volta para as Assembleias e o painel, que lê a URL com `useSearchParams` e por isso fica dentro de `Suspense`. */
export default function PaginaDeputadoEstadual() {
  return (
    <div className="painel">
      <div className="painel-topo">
        <h1>Deputado estadual</h1>
        <Link href="/parlamentares/estaduais/">todas as Assembleias</Link>
      </div>
      <Suspense fallback={<p>Carregando…</p>}>
        <PainelDeputado />
      </Suspense>
    </div>
  );
}
