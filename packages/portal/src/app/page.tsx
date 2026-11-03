/** Página inicial do portal: apresenta o Lumen, com a luz ao fundo (ADR-061), e leva às áreas. */

import Link from "next/link";
import { Luz } from "@/componentes/Luz";

/** Apresentação e um cartão por área, todos do mesmo tamanho, quatro por linha no computador. */
export default function Inicio() {
  return (
    <>
      <section className="inicio-heroi">
        <Luz />
        <span className="inicio-selo">Dados públicos do Brasil, com a fonte de cada número</span>
        <h1>O dinheiro público, à luz dos documentos oficiais</h1>
        <p className="inicio-intro">
          O Lumen reúne dados públicos do Brasil em um só lugar e mostra, ao lado de cada informação, o documento oficial
          de onde ela saiu.
        </p>
      </section>
      <div className="inicio-grade">
        <Link href="/eleicoes/" className="cartao inicio-cartao">
          <h2>Eleições</h2>
          <p>Resultados oficiais do TSE de 1933 a 2026, ao vivo na apuração, por estado, município e zona.</p>
        </Link>
        <Link href="/contratacoes/" className="cartao inicio-cartao">
          <h2>Contratações</h2>
          <p>O que União, estados e municípios publicaram no PNCP: processos, contratos, órgãos e fornecedores.</p>
        </Link>
        <Link href="/conformidade/" className="cartao inicio-cartao">
          <h2>Conformidade</h2>
          <p>Se cada estado e município entregou ao Tesouro os relatórios da LRF, e em que data, contra o prazo.</p>
        </Link>
        <Link href="/economia/" className="cartao inicio-cartao">
          <h2>Economia</h2>
          <p>Inflação, juros, dívida, gastos por mandato de cada município e o que as estatais gastam e investem.</p>
        </Link>
        <Link href="/parlamentares/" className="cartao inicio-cartao">
          <h2>Parlamentares</h2>
          <p>Como cada deputado federal votou, a presença nas sessões, os projetos e a cota parlamentar.</p>
        </Link>
        <Link href="/pessoa-juridica/" className="cartao inicio-cartao">
          <h2>Empresas e entidades</h2>
          <p>Tudo de um CNPJ: cadastro, contratos, pagamentos da União, emendas, convênios e tribunais de contas.</p>
        </Link>
        <Link href="/avisos/" className="cartao inicio-cartao">
          <h2>Avisos</h2>
          <p>O que aconteceu em cada local e merece um olhar, com a fonte e um link para contestar.</p>
        </Link>
        <Link href="/operacao/" className="cartao inicio-cartao">
          <h2>Situação das coletas</h2>
          <p>Quando cada fonte foi lida pela última vez, o que falhou e a cobertura por estado e município.</p>
        </Link>
      </div>
    </>
  );
}
