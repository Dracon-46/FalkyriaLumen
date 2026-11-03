/** Página inicial do portal: apresenta o Lumen, com a luz ao fundo (ADR-061), e leva às áreas. */

import Link from "next/link";
import { Luz } from "@/componentes/Luz";

/**
 * Apresentação e um cartão por área (Eleições, Contratações, Economia, Conformidade, Parlamentares, Empresas e
 * entidades, Avisos).
 */
export default function Inicio() {
  return (
    <>
      <section className="inicio-heroi">
        <Luz />
        <span className="inicio-selo">Dados públicos do Brasil, com a fonte de cada número</span>
        <h1>
          O dinheiro público, <em>à luz</em> dos documentos oficiais
        </h1>
        <p className="inicio-intro">
          O Lumen reúne dados públicos do Brasil em um só lugar e mostra, ao lado de cada informação, o documento oficial
          de onde ela saiu.
        </p>
      </section>
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
        <Link href="/economia/" className="cartao inicio-cartao">
          <h2>Economia e estatais</h2>
          <p>
            Inflação, juros, dívida e resultado fiscal das séries oficiais, e quanto as empresas estatais gastam e
            investem, pelos dados da SEST e da CVM.
          </p>
        </Link>
        <Link href="/conformidade/" className="cartao inicio-cartao">
          <h2>Conformidade</h2>
          <p>
            Se as contas anuais, o RREO e o RGF de cada estado e município constam do extrato do Tesouro Nacional, e em
            que data, contra o prazo da Lei de Responsabilidade Fiscal.
          </p>
        </Link>
        <Link href="/parlamentares/" className="cartao inicio-cartao">
          <h2>Parlamentares</h2>
          <p>
            Os deputados federais: como votaram no Plenário, a presença nas sessões, as proposições que apresentaram e a
            cota parlamentar, com os fornecedores, pelos dados abertos da Câmara.
          </p>
        </Link>
        <Link href="/pessoa-juridica/" className="cartao inicio-cartao">
          <h2>Empresas e entidades</h2>
          <p>
            Uma empresa ou entidade pelo CNPJ ou pelo nome: o cadastro na Receita, os contratos com a União, os
            estados e os municípios no PNCP, as emendas parlamentares recebidas e os convênios com a União.
          </p>
        </Link>
        <Link href="/avisos/" className="cartao inicio-cartao">
          <h2>Avisos</h2>
          <p>
            O que aconteceu em cada estado e município e merece um olhar, como contrato com empresa sancionada ou
            relatório fiscal em atraso, com a fonte e um link para contestar.
          </p>
        </Link>
      </div>
    </>
  );
}
