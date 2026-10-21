/**
 * Página `/operacao/`: a situação das coletas do Lumen (RF-AD-05, ADR-039). O trabalho é do `PainelOperacao`,
 * que roda no navegador e lê o `operacao.json` publicado com os painéis.
 */

import type { Metadata } from "next";
import { PainelOperacao } from "@/componentes/paineis/PainelOperacao";

/** Título e descrição da página, usados pelo navegador e nas prévias de link. */
export const metadata: Metadata = {
  title: "Situação das coletas",
  description:
    "Execuções dos fluxos de dados do Lumen, volume diário publicado no PNCP contra o usual, coleta da " +
    "conformidade por UF e cobertura por ente e UF.",
};

/** A página: título e o painel. */
export default function SituacaoDasColetas() {
  return (
    <div className="painel">
      <div className="painel-topo">
        <h1>Situação das coletas</h1>
      </div>
      <PainelOperacao />
    </div>
  );
}
