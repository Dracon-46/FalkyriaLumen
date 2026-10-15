"use client";

/**
 * Cabeçalho do portal, presente em todas as páginas. É componente de cliente
 * porque marca a aba atual pelo caminho da página (`usePathname`), que no
 * site estático só o navegador conhece.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";

const ABAS = [
  { href: "/eleicoes/", rotulo: "Eleições", pronta: true },
  { href: "/contratacoes/", rotulo: "Contratações", pronta: true },
  { href: "/conformidade/", rotulo: "Conformidade", pronta: true },
] as const;

/** Cabeçalho do Lumen: a marca e as abas. Cada aba é uma área do portal. */
export function Cabecalho() {
  const caminho = usePathname() ?? "/";
  return (
    <header className="cabecalho">
      <div className="cabecalho-dentro">
        <Link href="/" className="marca" aria-label="Lumen, página inicial">
          <span className="marca-nome">Lumen</span>
          <span className="marca-casa">Falkyria</span>
        </Link>
        <nav aria-label="Áreas do portal">
          <div className="abas">
            {ABAS.map((a) => (
              <Link
                key={a.href}
                href={a.href}
                className="aba"
                aria-current={caminho.startsWith(a.href.replace(/\/$/, "")) ? "page" : undefined}
              >
                {a.rotulo}
                {!a.pronta && <span className="aba-breve">em breve</span>}
              </Link>
            ))}
          </div>
        </nav>
      </div>
    </header>
  );
}
