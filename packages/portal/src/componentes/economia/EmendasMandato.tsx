"use client";

/**
 * Emendas parlamentares recebidas no mandato aberto em Governos municipais (ADR-044): quanto chegou aos
 * favorecidos do município, por categoria, por autor e por favorecido pessoa jurídica, com o link para a página
 * do favorecido pelo CNPJ (visão 360, ADR-049). Na comparação, o total do outro mandato ao lado.
 */

import Link from "next/link";
import { useState } from "react";
import { BaixarCsv } from "@/componentes/BaixarCsv";
import { percentual } from "@/lib/formato";
import { type EmendasEnte, recebidoNoPeriodo } from "@/lib/emendas";
import { cnpj as formatarCnpj } from "@/lib/paineis";
import { Numero } from "@/componentes/paineis/Comuns";

/** Linhas mostradas antes de "ver todos", nas listas de autores e favorecidos. */
const INICIAIS = 8;

/** As emendas do mandato: carregando, sem arquivo, com erro ou lidas. */
export type EstadoEmendas = { fase: "carregando" } | { fase: "pronto"; emendas: EmendasEnte | null } | { fase: "erro" };

/** A seção das emendas recebidas no mandato aberto (e no comparado, se houver). */
export function EmendasMandato({ estado, anos, anosComparado, rotulos, conv, fmt, unidade }: {
  estado: EstadoEmendas;
  anos: string[];
  anosComparado: string[] | null;
  rotulos: [string, string];
  conv: (valor: number, ano: string) => number | null;
  fmt: (v: number | null | undefined) => string;
  unidade: string;
}) {
  const [todosAutores, setTodosAutores] = useState(false);
  const [todosFavorecidos, setTodosFavorecidos] = useState(false);
  if (estado.fase === "carregando") return <p className="busca-detalhe">Lendo as emendas parlamentares…</p>;
  if (estado.fase === "erro") return <p className="busca-detalhe">As emendas parlamentares não puderam ser lidas agora.</p>;
  const e = estado.emendas;
  if (!e) {
    return (
      <>
        <h3 className="modal-subtitulo">Emendas parlamentares recebidas</h3>
        <p className="busca-detalhe">Nenhum pagamento de emenda parlamentar a favorecidos do município no arquivo da CGU.</p>
      </>
    );
  }
  const r = recebidoNoPeriodo(e, anos, conv);
  const outro = anosComparado ? recebidoNoPeriodo(e, anosComparado, conv) : null;
  const autores = todosAutores ? r.porAutor : r.porAutor.slice(0, INICIAIS);
  const favorecidos = todosFavorecidos ? r.favorecidos : r.favorecidos.slice(0, INICIAIS);
  const fatia = (v: number) => (r.total ? percentual((v / r.total) * 100) : "—");

  return (
    <>
      <h3 className="modal-subtitulo">Emendas parlamentares recebidas</h3>
      <div className="totais">
        <Numero rotulo={`Recebido em ${rotulos[0]}`} valor={fmt(r.total)}
          detalhe={r.anos.length ? `pagamentos de ${r.anos.join(", ")}` : "nenhum pagamento nos anos do mandato"} />
        {outro && (
          <Numero rotulo={`Recebido em ${rotulos[1]}`} valor={fmt(outro.total)}
            detalhe={outro.anos.length ? `pagamentos de ${outro.anos.join(", ")}` : "nenhum pagamento nos anos do mandato"} />
        )}
      </div>
      {r.total > 0 && (
        <>
          <div className="tabela-rolavel">
            <table className="tabela">
              <thead>
                <tr>
                  <th>Para quem</th>
                  <th className="n">Recebido</th>
                  <th className="n">% do recebido</th>
                </tr>
              </thead>
              <tbody>
                {r.porCategoria.map((c) => (
                  <tr key={c.chave}>
                    <td>{c.rotulo}</td>
                    <td className="n">{fmt(c.valor)}</td>
                    <td className="n">{fatia(c.valor)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <BaixarCsv nome={`emendas-por-categoria-${rotulos[0]}`}
            colunas={["Para quem", `Recebido (${unidade})`, "% do recebido"]}
            linhas={() => r.porCategoria.map((c) => [c.rotulo, c.valor, r.total ? (c.valor / r.total) * 100 : null])} />
          <div className="tabela-rolavel">
            <table className="tabela">
              <thead>
                <tr>
                  <th>Autor da emenda</th>
                  <th>Tipo</th>
                  <th className="n">Recebido</th>
                </tr>
              </thead>
              <tbody>
                {autores.map((a) => (
                  <tr key={a.chave}>
                    <td>{a.rotulo}</td>
                    <td className="busca-detalhe">{a.detalhe}</td>
                    <td className="n">{fmt(a.valor)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {r.porAutor.length > INICIAIS && (
            <button type="button" className="botao-link" onClick={() => setTodosAutores(!todosAutores)}>
              {todosAutores ? "mostrar menos" : `ver os ${r.porAutor.length} autores`}
            </button>
          )}
          <BaixarCsv nome={`emendas-por-autor-${rotulos[0]}`} colunas={["Autor da emenda", "Tipo", `Recebido (${unidade})`]}
            linhas={() => r.porAutor.map((a) => [a.rotulo, a.detalhe, a.valor])} />
          {r.favorecidos.length > 0 && (
            <div className="tabela-rolavel">
              <table className="tabela">
                <thead>
                  <tr>
                    <th>Favorecido (pessoa jurídica)</th>
                    <th>Categoria</th>
                    <th className="n">Recebido</th>
                  </tr>
                </thead>
                <tbody>
                  {favorecidos.map((f) => (
                    <tr key={f.chave}>
                      <td>
                        <Link href={`/pessoa-juridica/?cnpj=${f.cnpj}`}>{f.rotulo}</Link>
                        <div className="busca-detalhe">{formatarCnpj(f.cnpj)}</div>
                      </td>
                      <td className="busca-detalhe">{f.detalhe}</td>
                      <td className="n">{fmt(f.valor)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {r.favorecidos.length > INICIAIS && (
            <button type="button" className="botao-link" onClick={() => setTodosFavorecidos(!todosFavorecidos)}>
              {todosFavorecidos ? "mostrar menos" : `ver os ${r.favorecidos.length} favorecidos`}
            </button>
          )}
          {r.favorecidos.length > 0 && (
            <BaixarCsv nome={`emendas-favorecidos-${rotulos[0]}`}
              colunas={["CNPJ", "Favorecido (pessoa jurídica)", "Categoria", `Recebido (${unidade})`]}
              linhas={() => r.favorecidos.map((f) => [formatarCnpj(f.cnpj), f.rotulo, f.detalhe, f.valor])} />
          )}
        </>
      )}
      <p className="busca-detalhe">
        Pagamentos de emendas parlamentares aos favorecidos do município, pelo ano do pagamento (Portal da
        Transparência, arquivo de {e.data_arquivo ? new Date(e.data_arquivo).toLocaleDateString("pt-BR") : "data não informada"}).
        Valores {unidade}. O banco que opera os repasses fica de fora, e a pessoa física entra só na soma. O link do
        favorecido abre o que o Lumen tem dele: o cadastro na Receita, os contratos com cada ente, as emendas e os
        convênios.
      </p>
    </>
  );
}
