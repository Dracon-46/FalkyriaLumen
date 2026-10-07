/**
 * Página `/conformidade/`: a área de conformidade fiscal, ainda não publicada.
 * Por enquanto é só texto, sem leitura de dados: diz o que a área vai mostrar
 * e em que pé está a avaliação.
 */

import type { Metadata } from "next";

/** Título da página; o layout completa com " · Lumen". */
export const metadata: Metadata = { title: "Conformidade" };

/** Texto de apresentação da área. */
export default function Conformidade() {
  return (
    <div className="texto-corrido">
      <h1>Conformidade</h1>
      <p>
        Esta área vai mostrar, para cada estado e município, se os relatórios exigidos pela Lei de Responsabilidade
        Fiscal (RREO, RGF e contas anuais) constam do extrato do Tesouro Nacional e em que data foram entregues.
      </p>
      <p>
        A avaliação já está implementada e testada; quando a coleta do extrato falha ou o prazo ainda não venceu, o
        resultado aparece como indeterminado, e nada é atribuído ao ente.
      </p>
    </div>
  );
}
