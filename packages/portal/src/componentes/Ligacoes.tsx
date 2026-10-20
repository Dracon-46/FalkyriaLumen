/**
 * O mesmo ente nas outras abas (visão 360, ADR-035): de Contratações, Conformidade e Governos municipais, um link
 * para cada uma das outras e para o resultado das eleições do lugar. A aba aberta fica de fora.
 */

import Link from "next/link";
import { CODIGO_UF } from "@/lib/busca";
import { tipoDoCodigo } from "@/lib/paineis";

/** As abas que mostram um ente. */
export type AbaDoEnte = "contratacoes" | "conformidade" | "governos";

/** Os links do ente nas outras abas, na ordem da tela. */
export function ligacoesDoEnte(codigo: string, atual: AbaDoEnte): { href: string; rotulo: string }[] {
  const tipo = tipoDoCodigo(codigo);
  const uf = CODIGO_UF[codigo.slice(0, 2)];
  const saida: { aba: AbaDoEnte | "eleicoes"; href: string; rotulo: string }[] = [
    { aba: "contratacoes", href: `/contratacoes/?ente=${codigo}`, rotulo: "Contratações publicadas no PNCP" },
    { aba: "conformidade", href: `/conformidade/?ente=${codigo}`,
      rotulo: "Conformidade: entregas da LRF, grupo de pares e despesa com pessoal" },
  ];
  if (tipo === "municipio") {
    saida.push({ aba: "governos", href: `/economia/municipio/?ente=${codigo}`,
                 rotulo: "Despesa mandato a mandato e com o que foi gasto" });
    saida.push({ aba: "eleicoes", href: `/eleicoes/?a=mu-${codigo}`, rotulo: "Eleições no município" });
  } else if ((tipo === "estado" || tipo === "df") && uf) {
    saida.push({ aba: "eleicoes", href: `/eleicoes/?a=uf-${uf}`,
                 rotulo: tipo === "df" ? "Eleições no Distrito Federal" : "Eleições no estado" });
  }
  return saida.filter((l) => l.aba !== atual).map(({ href, rotulo }) => ({ href, rotulo }));
}

/** A faixa "Este ente nas outras abas". */
export function LigacoesDoEnte({ codigo, atual }: { codigo: string; atual: AbaDoEnte }) {
  const links = ligacoesDoEnte(codigo, atual);
  if (links.length === 0) return null;
  const nome = tipoDoCodigo(codigo) === "municipio" ? "Este município" : "Este ente";
  return (
    <nav className="cartao cartao-corpo ligacoes" aria-label={`${nome} nas outras abas`}>
      <span className="ligacoes-titulo">{nome} nas outras abas:</span>
      <ul>
        {links.map((l) => (
          <li key={l.href}>
            <Link href={l.href}>{l.rotulo}</Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
