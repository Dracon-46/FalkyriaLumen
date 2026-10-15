/** Página inicial do portal: apresenta o Lumen e leva às três áreas. */

import Link from "next/link";

/** Apresentação e um cartão por área (Eleições, Contratações, Conformidade), com o estado de cada uma. */
export default function Inicio() {
  return (
    <>
      <h1>Dados públicos, com a fonte de cada número</h1>
      <p className="inicio-intro">
        O Lumen reúne dados públicos do Brasil em um só lugar e mostra, ao lado de cada informação, o documento oficial
        de onde ela saiu.
      </p>
      <div className="inicio-grade">
        <Link href="/eleicoes/" className="cartao inicio-cartao">
          <h2>Eleições</h2>
          <p>
            Resultados oficiais do TSE, ao vivo na noite da apuração e de todas as eleições desde 1994: Presidente,
            governadores, senadores, deputados, prefeitos e vereadores, por estado e por município.
          </p>
        </Link>
        <Link href="/contratacoes/" className="cartao inicio-cartao">
          <h2>Contratações</h2>
          <p>
            O que a União, os estados e os municípios publicaram no PNCP: processos de contratação, contratos, órgãos e
            fornecedores, mês a mês, com o link de cada publicação.
          </p>
        </Link>
        <Link href="/conformidade/" className="cartao inicio-cartao">
          <h2>Conformidade</h2>
          <p>
            Se as contas anuais, o RREO e o RGF de cada estado e município constam do extrato do Tesouro Nacional, e em
            que data, contra o prazo da Lei de Responsabilidade Fiscal.
          </p>
        </Link>
      </div>
    </>
  );
}
