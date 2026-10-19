/**
 * Página `/ente/`: a visão 360 de um ente (ADR-035). O trabalho é do `PainelEnte`, que roda no navegador e lê os
 * arquivos de cada área (eleições, contratações, conformidade, transparência e estatais).
 */

import type { Metadata } from "next";
import { Suspense } from "react";
import { PainelEnte } from "@/componentes/ente/PainelEnte";

/** Título e descrição da página, usados pelo navegador e nas prévias de link. */
export const metadata: Metadata = {
  title: "Visão 360 de um ente",
  description:
    "Tudo o que o Lumen publica sobre a União, um estado ou um município: eleições, contratações com os documentos, " +
    "entregas da LRF, o portal de transparência e as estatais.",
};

/** Envolve o painel em `Suspense`: ele lê a URL com `useSearchParams`, que só existe no navegador. */
export default function Ente() {
  return (
    <Suspense fallback={<p>Carregando…</p>}>
      <PainelEnte />
    </Suspense>
  );
}
