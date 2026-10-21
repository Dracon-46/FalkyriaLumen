/**
 * Página `/avisos/`: o que aconteceu em cada local e merece um olhar (ADR-047). O trabalho é do `PainelAvisos`,
 * que roda no navegador e lê os arquivos `avisos/` publicados com os painéis.
 */

import type { Metadata } from "next";
import { Suspense } from "react";
import { PainelAvisos } from "@/componentes/avisos/PainelAvisos";

/** Título e descrição da página, usados pelo navegador e nas prévias de link. */
export const metadata: Metadata = {
  title: "Avisos",
  description:
    "O que aconteceu em cada estado e município e o que observar: contratos com empresa sancionada, valores a " +
    "conferir, relatórios fiscais que não constam ou em atraso e portais de transparência com nível baixo. Cada " +
    "aviso traz a fonte e pode ser contestado.",
};

/** Envolve o painel em `Suspense`: ele lê a URL com `useSearchParams`, que só existe no navegador. */
export default function Avisos() {
  return (
    <Suspense fallback={<p>Carregando…</p>}>
      <PainelAvisos />
    </Suspense>
  );
}
