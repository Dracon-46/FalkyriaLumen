"use client";

/**
 * Contratos registrados no tribunal de contas no mandato aberto em Governos municipais (ADR-050): quantos e
 * quanto, pelo ano do contrato, os aditivos, a soma anônima de pessoa física e os fornecedores do mandato, cada
 * um com o link para a página da empresa (visão 360). Na comparação, o total do outro mandato ao lado. Por
 * enquanto, os municípios gaúchos (LicitaCon do TCE-RS, desde 2016) e paranaenses (SIM-AM do TCE-PR, desde 2013).
 */

import Link from "next/link";
import { useState } from "react";
import { numero } from "@/lib/formato";
import { cnpj as formatarCnpj } from "@/lib/paineis";
import { type TceEnte, tceNoPeriodo } from "@/lib/tce";
import { Numero } from "@/componentes/paineis/Comuns";

/** Fornecedores mostrados antes de "ver todos". */
const INICIAIS = 10;

/** Os contratos do município no tribunal: carregando, sem arquivo (tribunal fora do Lumen), com erro ou lidos. */
export type EstadoTce = { fase: "carregando" } | { fase: "pronto"; tce: TceEnte | null } | { fase: "erro" };

/** A seção dos contratos no tribunal de contas, no mandato aberto (e no comparado, se houver). */
export function TceMandato({ estado, anos, anosComparado, rotulos, conv, fmt, unidade }: {
  estado: EstadoTce;
  anos: string[];
  anosComparado: string[] | null;
  rotulos: [string, string];
  conv: (valor: number, ano: string) => number | null;
  fmt: (v: number | null | undefined) => string;
  unidade: string;
}) {
  const [todos, setTodos] = useState(false);
  if (estado.fase === "carregando") return null;
  if (estado.fase === "erro") return <p className="busca-detalhe">Os contratos no tribunal de contas não puderam ser lidos agora.</p>;
  const t = estado.tce;
  if (!t) return null;
  const r = tceNoPeriodo(t, anos, conv);
  const outro = anosComparado ? tceNoPeriodo(t, anosComparado, conv) : null;
  const fornecedores = todos ? r.fornecedores : r.fornecedores.slice(0, INICIAIS);
  const detalhe = (x: typeof r) => x.anos.length
    ? `${numero(x.contratos)} contrato(s) de ${x.anos.join(", ")}` : `nenhum contrato registrado nos anos do mandato`;

  return (
    <>
      <h3 className="modal-subtitulo">Contratos registrados no tribunal de contas ({t.tribunal})</h3>
      <div className="totais">
        <Numero rotulo={`Contratado em ${rotulos[0]}`} valor={fmt(r.valor)} detalhe={detalhe(r)} />
        {outro && <Numero rotulo={`Contratado em ${rotulos[1]}`} valor={fmt(outro.valor)} detalhe={detalhe(outro)} />}
        {r.aditivos > 0 && (
          <Numero rotulo="Aditivos" valor={numero(r.aditivos)} detalhe={`acréscimo líquido de ${fmt(r.aditivosValor)}`} />
        )}
      </div>
      {r.fornecedores.length > 0 && (
        <div className="tabela-rolavel">
          <table className="tabela">
            <thead>
              <tr>
                <th>Fornecedor (pessoa jurídica)</th>
                <th className="n">Contratos</th>
                <th className="n">Valor</th>
              </tr>
            </thead>
            <tbody>
              {fornecedores.map((f) => (
                <tr key={f.cnpj}>
                  <td>
                    <Link href={`/pessoa-juridica/?cnpj=${f.cnpj}`}>{f.nome}</Link>
                    <div className="busca-detalhe">{formatarCnpj(f.cnpj)}</div>
                  </td>
                  <td className="n">{numero(f.contratos)}</td>
                  <td className="n">{fmt(f.valor)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {r.fornecedores.length > INICIAIS && (
        <button type="button" className="botao-link" onClick={() => setTodos(!todos)}>
          {todos ? "mostrar menos" : `ver os ${r.fornecedores.length} fornecedores`}
        </button>
      )}
      <p className="busca-detalhe">
        Contratos que os órgãos do município (prefeitura, câmara, fundos, autarquias e fundações; consórcios ficam
        de fora) registraram no {t.sistema}, o sistema do {t.tribunal}, pelo ano do contrato, desde {t.primeiroAno}.
        Valores {unidade}. Contrato acima do
        teto de plausibilidade conta e fica fora da soma
        {r.foraDaSoma ? ` (${numero(r.foraDaSoma)} no mandato)` : ""}; com pessoa física, só a soma
        {r.pfContratos ? ` (${numero(r.pfContratos)} contrato(s), ${fmt(r.pfValor)})` : ""}. A lista traz os 100
        maiores fornecedores do município em todos os anos. Diferente do PNCP, aqui estão também os anos antes de
        2024, quando nem toda contratação passava por ele.
      </p>
    </>
  );
}
