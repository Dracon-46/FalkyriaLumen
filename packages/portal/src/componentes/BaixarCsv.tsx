"use client";

/**
 * O link "baixar CSV" de uma tabela (ADR-051). As linhas são montadas só no clique, com a tabela inteira, e o nome
 * do arquivo começa pelo que a página está mostrando (o painel, o ente, o período), que vem de `PrefixoCsv`.
 */

import { createContext, useContext } from "react";
import { baixarCsv, type Celula, nomeDoArquivo } from "@/lib/csv";

/** O começo do nome dos arquivos da página: "contratacoes-4314902-de-2025-01", por exemplo. */
export const PrefixoCsv = createContext<string>("");

/** O link, embaixo da tabela: `nome` diz qual tabela é, `linhas` monta todas as linhas só quando a pessoa clica. */
export function BaixarCsv({ nome, colunas, linhas }: { nome: string; colunas: string[]; linhas: () => Celula[][] }) {
  const prefixo = useContext(PrefixoCsv);
  return (
    <p className="baixar-csv">
      <button type="button" className="botao-link" onClick={() => baixarCsv(nomeDoArquivo(prefixo, nome), colunas, linhas())}>
        baixar CSV
      </button>
    </p>
  );
}
