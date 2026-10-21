"use client";

/**
 * Na página de novidades: diz quantas mudanças entraram desde a última visita e marca todas como vistas, o que
 * apaga o aviso da aba no cabeçalho.
 */

import { useEffect, useState } from "react";
import { CHAVE_VISTA, EVENTO_VISTAS, naoVistas } from "@/lib/novidades";

/** A frase das novidades desde a última visita; some quando não há nenhuma. */
export function MarcarNovidades({ ids }: { ids: string[] }) {
  const [novas, setNovas] = useState(0);
  useEffect(() => {
    const maisNova = ids[0];
    if (!maisNova) return;
    try {
      setNovas(naoVistas(ids, window.localStorage.getItem(CHAVE_VISTA)));
      window.localStorage.setItem(CHAVE_VISTA, maisNova);
    } catch {
      // sem armazenamento no navegador: a página funciona sem o aviso
    }
    window.dispatchEvent(new CustomEvent(EVENTO_VISTAS));
  }, [ids]);
  if (!novas) return null;
  return (
    <p className="faixa novidades-desde">
      {novas === 1 ? "1 mudança nova" : `${novas} mudanças novas`} desde a sua última visita, no alto da lista.
    </p>
  );
}
