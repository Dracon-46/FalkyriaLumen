/**
 * Layout raiz do portal: a moldura comum a todas as páginas (cabeçalho, área
 * principal e rodapé), os metadados padrão e o estilo global.
 */

import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import { Cabecalho } from "@/componentes/Cabecalho";
import { Rodape } from "@/componentes/Rodape";
import "./globals.css";

/** Metadados padrão. Cada página define só o `title`, que entra no modelo "%s · Lumen". */
export const metadata: Metadata = {
  title: { default: "Lumen", template: "%s · Lumen" },
  description:
    "Falkyria Lumen: dados públicos do Brasil, com a fonte de cada número. Resultados oficiais das eleições, " +
    "contratações públicas e conformidade fiscal.",
  icons: { icon: "/icone.svg" },
};

/** Largura do dispositivo no celular e cor da barra do navegador conforme o tema claro ou escuro do sistema. */
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#fcfcfb" },
    { media: "(prefers-color-scheme: dark)", color: "#1a1a19" },
  ],
};

/**
 * Moldura de todas as páginas. O primeiro elemento é o link "Ir para o
 * conteúdo", fora da tela, para quem navega por teclado ou leitor de tela
 * pular direto ao `<main>`.
 */
export default function Raiz({ children }: { children: ReactNode }) {
  return (
    <html lang="pt-BR">
      <body>
        <a className="so-leitor" href="#conteudo">
          Ir para o conteúdo
        </a>
        <Cabecalho />
        <main id="conteudo" className="pagina">
          {children}
        </main>
        <Rodape />
      </body>
    </html>
  );
}
