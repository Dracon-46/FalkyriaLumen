/**
 * Rodapé de todas as páginas: de onde vêm os números, o compromisso editorial do projeto, o link da situação das
 * coletas (ADR-039) e a assinatura da Falkyria.
 */

import Link from "next/link";

/** Página da Falkyria no portfólio do autor. */
const FALKYRIA = "https://dracon-46.github.io/Portifolio/#falkyria";

/** Rodapé: de onde vêm os números, o compromisso editorial do projeto e a assinatura da Falkyria. */
export function Rodape() {
  return (
    <footer className="rodape">
      <p>
        Os resultados eleitorais são os publicados pelo Tribunal Superior Eleitoral, sem nenhum cálculo de projeção;
        cada tela informa o arquivo de origem e o horário da última atualização.
      </p>
      <p>
        Nas áreas de contratações e conformidade, os números são os publicados no PNCP e no extrato de entregas do
        Tesouro Nacional, com o link ou a data de cada um. Quando o Lumen sinalizar uma atividade para análise, ela
        virá com a evidência e a regra aplicada; a conclusão sobre qualquer caso cabe aos órgãos de controle.
      </p>
      <p>
        <Link href="/operacao/">Situação das coletas</Link>: quando cada fonte foi lida pela última vez e o que falhou.
      </p>
      <p className="rodape-assinatura">
        <a href={FALKYRIA} target="_blank" rel="noopener noreferrer" className="rodape-falkyria">
          {/* A ave escura no tema claro e a branca no escuro; o CSS mostra uma das duas */}
          <img src="/falkyria/falkyria.svg" alt="" width={20} height={20} className="falkyria-claro" />
          <img src="/falkyria/falkyria-branca.svg" alt="" width={20} height={20} className="falkyria-escuro" />
          Um produto Falkyria
        </a>
        <span>© 2026 Falkyria. Todos os direitos reservados.</span>
      </p>
    </footer>
  );
}
