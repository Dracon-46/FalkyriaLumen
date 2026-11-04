/**
 * A navegação dentro da aba Parlamentares (ADR-060): os deputados federais, os senadores, os deputados estaduais e os
 * vereadores (ADR-062) e as votações.
 */

import Link from "next/link";

/** Os links, com o da página aberta marcado. */
export function NavParlamentares({ atual }: { atual: "deputados" | "senadores" | "estaduais" | "vereadores" | "votacoes" }) {
  return (
    <nav className="nav-secao" aria-label="Parlamentares">
      <Link href="/parlamentares/" aria-current={atual === "deputados" ? "page" : undefined}>Deputados federais</Link>
      <Link href="/parlamentares/?casa=senado" aria-current={atual === "senadores" ? "page" : undefined}>Senadores</Link>
      <Link href="/parlamentares/estaduais/" aria-current={atual === "estaduais" ? "page" : undefined}>Deputados estaduais</Link>
      <Link href="/parlamentares/vereadores/" aria-current={atual === "vereadores" ? "page" : undefined}>Vereadores</Link>
      <Link href="/parlamentares/votacoes/" aria-current={atual === "votacoes" ? "page" : undefined}>Votações</Link>
    </nav>
  );
}
