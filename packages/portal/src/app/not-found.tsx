/** Página de endereço inexistente (404), com o caminho de volta ao início. */

import Link from "next/link";

/** Aviso de página não encontrada e link para a página inicial. */
export default function NaoEncontrada() {
  return (
    <div className="texto-corrido">
      <h1>Página não encontrada</h1>
      <p>
        <Link href="/">Voltar para o início</Link>
      </p>
    </div>
  );
}
