/**
 * Página `/parlamentares/deputado/?id=`: um deputado federal pelo id da Câmara (ADR-060). O trabalho é do
 * `PainelDeputado`, que roda no navegador e lê `parlamentares/camara/<id>.json.gz` publicado com os painéis.
 */

import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { PainelDeputado } from "@/componentes/parlamentares/PainelDeputado";

/** Título e descrição da página, usados pelo navegador e nas prévias de link. */
export const metadata: Metadata = {
  title: "Deputado federal",
  description:
    "Um deputado federal: os votos no Plenário com a orientação do Governo, a presença nas sessões, as proposições " +
    "que apresentou e a cota parlamentar, por ano, pelos dados abertos da Câmara dos Deputados.",
};

/** Título, a volta para a lista e o painel, que lê a URL com `useSearchParams` e por isso fica dentro de `Suspense`. */
export default function PaginaDeputado() {
  return (
    <div className="painel">
      <div className="painel-topo">
        <h1>Deputado federal</h1>
        <Link href="/parlamentares/">todos os parlamentares</Link>
      </div>
      <Suspense fallback={<p>Carregando…</p>}>
        <PainelDeputado />
      </Suspense>
    </div>
  );
}
