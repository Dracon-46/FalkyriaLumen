/**
 * Página `/parlamentares/senador/?id=`: um senador pelo código do Senado (ADR-060, adendo). O trabalho é do
 * `PainelDeputado`, o mesmo dos deputados, com a casa `senado`.
 */

import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { PainelDeputado } from "@/componentes/parlamentares/PainelDeputado";

/** Título e descrição da página, usados pelo navegador e nas prévias de link. */
export const metadata: Metadata = {
  title: "Senador",
  description:
    "Um senador: os votos nominais no Plenário, a participação nas votações, as matérias de que é autor e a cota " +
    "parlamentar, por ano, pelos dados abertos do Senado Federal.",
};

/** Título, a volta para a lista e o painel, que lê a URL com `useSearchParams` e por isso fica dentro de `Suspense`. */
export default function PaginaSenador() {
  return (
    <div className="painel">
      <div className="painel-topo">
        <h1>Senador</h1>
        <Link href="/parlamentares/?casa=senado">todos os senadores</Link>
      </div>
      <Suspense fallback={<p>Carregando…</p>}>
        <PainelDeputado casa="senado" />
      </Suspense>
    </div>
  );
}
