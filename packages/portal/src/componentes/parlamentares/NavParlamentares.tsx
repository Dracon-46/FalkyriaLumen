/**
 * A navegação dentro da aba Parlamentares (ADR-060): a lista dos deputados e as votações do Plenário.
 */

import Link from "next/link";

/** Os dois links, com o da página aberta marcado. */
export function NavParlamentares({ atual }: { atual: "deputados" | "votacoes" }) {
  return (
    <nav className="nav-secao" aria-label="Parlamentares">
      <Link href="/parlamentares/" aria-current={atual === "deputados" ? "page" : undefined}>Deputados federais</Link>
      <Link href="/parlamentares/votacoes/" aria-current={atual === "votacoes" ? "page" : undefined}>Votações</Link>
    </nav>
  );
}
