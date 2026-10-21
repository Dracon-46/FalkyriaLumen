"use client";

/**
 * Convênios da União iniciados no mandato aberto em Governos municipais (ADR-045): quantos, quanto foi
 * conveniado e liberado, a situação de cada um como o SIAFI a registra e a lista, do maior ao menor, com o link
 * do convenente pessoa jurídica para a página dele pelo CNPJ (visão 360, ADR-049).
 */

import Link from "next/link";
import { useState } from "react";
import { numero } from "@/lib/formato";
import { type ConveniosEnte, conveniosNoPeriodo } from "@/lib/convenios";
import { cnpj as formatarCnpj, dataCurta } from "@/lib/paineis";
import { Numero } from "@/componentes/paineis/Comuns";

/** Convênios mostrados antes de "ver todos". */
const INICIAIS = 10;

/** Os convênios do município: carregando, sem arquivo, com erro ou lidos. */
export type EstadoConvenios = { fase: "carregando" } | { fase: "pronto"; convenios: ConveniosEnte | null } | { fase: "erro" };

/** A seção dos convênios iniciados no mandato aberto (e no comparado, se houver). */
export function ConveniosMandato({ estado, anos, anosComparado, rotulos, conv, fmt, unidade }: {
  estado: EstadoConvenios;
  anos: string[];
  anosComparado: string[] | null;
  rotulos: [string, string];
  conv: (valor: number, ano: string) => number | null;
  fmt: (v: number | null | undefined) => string;
  unidade: string;
}) {
  const [todos, setTodos] = useState(false);
  if (estado.fase === "carregando") return <p className="busca-detalhe">Lendo os convênios…</p>;
  if (estado.fase === "erro") return <p className="busca-detalhe">Os convênios não puderam ser lidos agora.</p>;
  const c = estado.convenios;
  if (!c) {
    return (
      <>
        <h3 className="modal-subtitulo">Convênios com a União</h3>
        <p className="busca-detalhe">Nenhum convênio da União com início de 2001 em diante no arquivo da CGU.</p>
      </>
    );
  }
  const r = conveniosNoPeriodo(c, anos, conv);
  const outro = anosComparado ? conveniosNoPeriodo(c, anosComparado, conv) : null;
  const lista = todos ? r.lista : r.lista.slice(0, INICIAIS);

  return (
    <>
      <h3 className="modal-subtitulo">Convênios com a União iniciados no mandato</h3>
      <div className="totais">
        <Numero rotulo={`Conveniado em ${rotulos[0]}`} valor={fmt(r.valor)}
          detalhe={`${numero(r.quantidade)} ${r.quantidade === 1 ? "convênio" : "convênios"} · liberado ${fmt(r.liberado)}`} />
        {outro && (
          <Numero rotulo={`Conveniado em ${rotulos[1]}`} valor={fmt(outro.valor)}
            detalhe={`${numero(outro.quantidade)} ${outro.quantidade === 1 ? "convênio" : "convênios"} · liberado ${fmt(outro.liberado)}`} />
        )}
      </div>
      {r.porSituacao.length > 0 && (
        <p className="busca-detalhe">
          Situação hoje:{" "}
          {r.porSituacao.map((s, i) => `${i ? " · " : ""}${s.situacao.toLowerCase()} ${numero(s.quantidade)}`)}.
        </p>
      )}
      {lista.length > 0 && (
        <div className="tabela-rolavel">
          <table className="tabela">
            <thead>
              <tr>
                <th>Objeto</th>
                <th>Convenente</th>
                <th>Situação</th>
                <th className="n">Valor</th>
                <th className="n">Liberado</th>
              </tr>
            </thead>
            <tbody>
              {lista.map((x) => (
                <tr key={x.numero}>
                  <td>
                    {x.objeto}
                    <div className="busca-detalhe">
                      {x.orgao} · convênio {x.numero} · {dataCurta(x.inicio)}{x.fim ? ` a ${dataCurta(x.fim)}` : ""}
                    </div>
                  </td>
                  <td>
                    {x.cnpj ? <Link href={`/pessoa-juridica/?cnpj=${x.cnpj}`}>{x.convenente}</Link> : x.convenente}
                    <div className="busca-detalhe">
                      {c.categorias[x.categoria] ?? x.categoria}{x.cnpj ? ` · ${formatarCnpj(x.cnpj)}` : ""}
                    </div>
                  </td>
                  <td>{x.situacao.toLowerCase()}</td>
                  <td className="n">{fmt(x.valor)}</td>
                  <td className="n">{fmt(x.liberado)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {r.lista.length > INICIAIS && (
        <button type="button" className="botao-link" onClick={() => setTodos(!todos)}>
          {todos ? "mostrar menos" : `ver os ${numero(r.lista.length)} convênios`}
        </button>
      )}
      <p className="busca-detalhe">
        Convênios da União com início de vigência nos anos do mandato, com a situação como o SIAFI a registra hoje
        (Portal da Transparência, arquivo de {c.data_arquivo ? dataCurta(`${c.data_arquivo.slice(0, 4)}-${c.data_arquivo.slice(4, 6)}-${c.data_arquivo.slice(6, 8)}`) : "data não informada"}).
        Valores {unidade}, pelo ano de início. Convênio anulado ou excluído fica de fora
        {r.pessoaFisica ? `; convênios com pessoa física somam ${fmt(r.pessoaFisica)}, sem identificação` : ""}.
      </p>
    </>
  );
}
