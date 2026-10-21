/**
 * Página `/pessoa-juridica/`: tudo o que o Lumen tem de uma empresa ou entidade pelo CNPJ (ADR-049). O trabalho é
 * do `PainelPessoaJuridica`, que roda no navegador e lê os arquivos `pj/` e `cnpj/` publicados com os painéis.
 */

import type { Metadata } from "next";
import { Suspense } from "react";
import { PainelPessoaJuridica } from "@/componentes/paineis/PainelPessoaJuridica";

/** Título e descrição da página, usados pelo navegador e nas prévias de link. */
export const metadata: Metadata = {
  title: "Empresa ou entidade",
  description:
    "Uma empresa ou entidade pelo CNPJ: o cadastro na Receita Federal, os contratos publicados no PNCP com cada " +
    "estado e município, as emendas parlamentares recebidas e os convênios com a União.",
};

/** Título e o painel, que lê a URL com `useSearchParams` e por isso fica dentro de `Suspense`. */
export default function PessoaJuridica() {
  return (
    <div className="painel">
      <div className="painel-topo">
        <h1>Empresa ou entidade</h1>
      </div>
      <Suspense fallback={<p>Carregando…</p>}>
        <PainelPessoaJuridica />
      </Suspense>
    </div>
  );
}
