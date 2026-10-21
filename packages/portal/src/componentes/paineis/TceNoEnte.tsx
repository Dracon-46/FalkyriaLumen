"use client";

/**
 * Na página de um ente em Contratações: os contratos ano a ano no PNCP ao lado dos registrados no tribunal de contas
 * (ADR-050), quando o tribunal do ente já está no Lumen. Mostra a cobertura de antes de 2024, quando nem toda
 * contratação passava pelo PNCP. As duas fontes não se somam.
 */

import { useEffect, useState } from "react";
import { numero } from "@/lib/formato";
import { moedaCompacta } from "@/lib/paineis";
import { anoAAnoComPncp, carregarTce, type TceEnte } from "@/lib/tce";

/** A tabela ano a ano; não aparece quando o tribunal do ente não está no Lumen. */
export function TceNoEnte({ codigo, meses }: {
  codigo: string;
  meses: { mes: string; contratos: number; valor_contratos: number }[];
}) {
  const [tce, setTce] = useState<TceEnte | null>(null);
  useEffect(() => {
    setTce(null);
    const c = new AbortController();
    carregarTce(codigo, c.signal)
      .then(setTce)
      .catch(() => undefined);
    return () => c.abort();
  }, [codigo]);
  if (!tce) return null;
  const linhas = anoAAnoComPncp(tce, meses);
  const traco = (v: number | null, f: (n: number) => string) => (v === null ? "—" : f(v));
  return (
    <section className="cartao cartao-corpo" aria-labelledby="titulo-tce-ente">
      <h2 id="titulo-tce-ente" className="titulo-secao">No PNCP e no tribunal de contas ({tce.tribunal}), ano a ano</h2>
      <div className="tabela-rolavel">
        <table className="tabela">
          <thead>
            <tr>
              <th>Ano</th>
              <th className="n">Contratos no PNCP</th>
              <th className="n so-largo">Valor no PNCP</th>
              <th className="n">Contratos no {tce.tribunal}</th>
              <th className="n so-largo">Valor no {tce.tribunal}</th>
            </tr>
          </thead>
          <tbody>
            {linhas.map((l) => (
              <tr key={l.ano}>
                <td>{l.ano}</td>
                <td className="n">{traco(l.pncpContratos, numero)}</td>
                <td className="n so-largo">{traco(l.pncpValor, moedaCompacta)}</td>
                <td className="n">{traco(l.tceContratos, numero)}</td>
                <td className="n so-largo">{traco(l.tceValor, moedaCompacta)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="busca-detalhe">
        PNCP pela data de publicação do contrato; {tce.sistema}, o sistema do {tce.tribunal}, pelo ano do contrato
        {tce.primeiroAno ? `, desde ${tce.primeiroAno}` : ""}. As duas fontes não se somam: de 2021 em diante, muitos contratos estão nas duas, e
        antes de 2024 nem toda contratação passava pelo PNCP. Um traço indica que a fonte não tem o ano no Lumen.
      </p>
    </section>
  );
}
