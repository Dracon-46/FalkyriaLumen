/**
 * Página `/contratacoes/`: a área de contratações públicas (PNCP), ainda não
 * publicada. Por enquanto é só texto, sem leitura de dados: diz o que a área
 * vai mostrar e do que a publicação depende.
 */

import type { Metadata } from "next";

/** Título da página; o layout completa com " · Lumen". */
export const metadata: Metadata = { title: "Contratações" };

/** Texto de apresentação da área. */
export default function Contratacoes() {
  return (
    <div className="texto-corrido">
      <h1>Contratações</h1>
      <p>
        Esta área vai mostrar as contratações, contratos e atas publicados no Portal Nacional de Contratações Públicas
        (PNCP), com o amparo legal declarado em cada uma.
      </p>
      <p>
        A coleta e a normalização já funcionam (Fase 1 do roteiro); a publicação depende da revisão metodológica das
        regras de sinalização, que acompanham cada atividade para análise com a evidência primária e o dispositivo
        legal aplicado.
      </p>
    </div>
  );
}
