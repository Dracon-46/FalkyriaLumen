/**
 * Rodapé de todas as páginas: de onde vêm os números, o compromisso editorial do projeto e o link da situação das
 * coletas (ADR-039).
 */

import Link from "next/link";

/** Rodapé: de onde vêm os números e o compromisso editorial do projeto. */
export function Rodape() {
  return (
    <footer className="rodape">
      <p>
        Lumen, um projeto Falkyria. Os resultados eleitorais são os publicados pelo Tribunal Superior Eleitoral, sem
        nenhum cálculo de projeção; cada tela informa o arquivo de origem e o horário da última atualização.
      </p>
      <p>
        Nas áreas de contratações e conformidade, os números são os publicados no PNCP e no extrato de entregas do
        Tesouro Nacional, com o link ou a data de cada um. Quando o Lumen sinalizar uma atividade para análise, ela
        virá com a evidência e a regra aplicada; a conclusão sobre qualquer caso cabe aos órgãos de controle.
      </p>
      <p>
        <Link href="/operacao/">Situação das coletas</Link>: quando cada fonte foi lida pela última vez e o que falhou.
      </p>
    </footer>
  );
}
