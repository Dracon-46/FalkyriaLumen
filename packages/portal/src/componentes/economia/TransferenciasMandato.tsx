"use client";

/**
 * Transferências da União no mandato aberto em Governos municipais (ADR-054): quanto foi para a prefeitura e os
 * fundos municipais, ano a ano, por tipo, por função e pelas ações que mais pesam, e quanto foi para as entidades
 * sem fins lucrativos do município (as escolas pelo PDDE, associações). FPM e FPE não estão no arquivo da CGU.
 */

import { BaixarCsv } from "@/componentes/BaixarCsv";
import { Numero } from "@/componentes/paineis/Comuns";
import { type TransferenciasEnte, transferenciasNoPeriodo } from "@/lib/transferencias";

/** As transferências do ente: carregando, sem arquivo, com erro ou lidas. */
export type EstadoTransferencias =
  | { fase: "carregando" }
  | { fase: "pronto"; transferencias: TransferenciasEnte | null }
  | { fase: "erro" };

/** Os tipos como a CGU os agrupa, no texto da tela. */
const TIPOS: Record<string, string> = {
  constitucionais: "Constitucionais e royalties",
  legais: "Legais, voluntárias e específicas",
  outros: "Outras",
};

/** Ações mostradas na lista. */
const ACOES = 10;

/** Mês `AAAAMM` como "set/2026". */
function mesCurto(m: string): string {
  const nomes = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
  return `${nomes[Number(m.slice(4, 6)) - 1] ?? m.slice(4, 6)}/${m.slice(0, 4)}`;
}

/** A seção das transferências no mandato aberto (e no comparado, se houver). */
export function TransferenciasMandato({ estado, anos, anosComparado, rotulos, conv, fmt, unidade }: {
  estado: EstadoTransferencias;
  anos: string[];
  anosComparado: string[] | null;
  rotulos: [string, string];
  conv: (valor: number, ano: string) => number | null;
  fmt: (v: number | null | undefined) => string;
  unidade: string;
}) {
  if (estado.fase === "carregando") return <p className="busca-detalhe">Lendo as transferências da União…</p>;
  if (estado.fase === "erro") return <p className="busca-detalhe">As transferências da União não puderam ser lidas agora.</p>;
  const t = estado.transferencias;
  if (!t) {
    return (
      <>
        <h3 className="modal-subtitulo">Transferências da União</h3>
        <p className="busca-detalhe">Sem transferência da União para o município no arquivo da CGU (de 2014 em diante).</p>
      </>
    );
  }
  const r = transferenciasNoPeriodo(t, anos, conv);
  const outro = anosComparado ? transferenciasNoPeriodo(t, anosComparado, conv) : null;
  const antesDe2014 = anos.filter((a) => Number(a) < 2014);
  const primeiro = t.meses[0];
  const ultimo = t.meses[t.meses.length - 1];

  return (
    <>
      <h3 className="modal-subtitulo">Transferências da União no mandato</h3>
      <div className="totais">
        <Numero rotulo={`À prefeitura e aos fundos municipais em ${rotulos[0]}`} valor={fmt(r.governo)}
          detalhe={r.entidades ? `e ${fmt(r.entidades)} a entidades do município` : undefined} />
        {outro && (
          <Numero rotulo={`À prefeitura e aos fundos municipais em ${rotulos[1]}`} valor={fmt(outro.governo)}
            detalhe={outro.entidades ? `e ${fmt(outro.entidades)} a entidades do município` : undefined} />
        )}
      </div>
      <div className="tabela-rolavel">
        <table className="tabela">
          <thead>
            <tr>
              <th>Ano</th>
              <th className="n">À prefeitura e fundos</th>
              <th className="n">A entidades do município</th>
            </tr>
          </thead>
          <tbody>
            {r.porAno.map((x) => (
              <tr key={x.ano}>
                <td>
                  {x.ano}
                  {x.meses > 0 && x.meses < 12 && <span className="busca-detalhe"> · {x.meses} de 12 meses</span>}
                </td>
                <td className="n">{x.governo === null ? "—" : fmt(x.governo)}</td>
                <td className="n">{x.entidades === null ? "—" : fmt(x.entidades)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {r.porArea.length > 0 && (
        <p className="busca-detalhe">
          Por área (à prefeitura e fundos): {r.porArea.map((a) => `${a.chave} ${fmt(a.valor)}`).join(" · ")}.
          {r.porTipo.length > 0 && <> Por tipo: {r.porTipo.map((a) => `${TIPOS[a.chave] ?? a.chave} ${fmt(a.valor)}`).join(" · ")}.</>}
        </p>
      )}
      {r.porAcao.length > 0 && (
        <div className="tabela-rolavel">
          <table className="tabela">
            <thead>
              <tr>
                <th>Ação (como o Portal da Transparência a nomeia)</th>
                <th className="n">No mandato</th>
              </tr>
            </thead>
            <tbody>
              {r.porAcao.slice(0, ACOES).map((a) => (
                <tr key={a.chave}>
                  <td>{a.chave}</td>
                  <td className="n">{fmt(a.valor)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {r.porAno.some((x) => x.governo !== null || x.entidades !== null) && (
        <BaixarCsv nome={`transferencias-${rotulos[0]}`}
          colunas={["Ano", "Meses lidos", `À prefeitura e fundos (${unidade})`, `A entidades do município (${unidade})`]}
          linhas={() => r.porAno.map((x) => [x.ano, x.meses, x.governo ?? "", x.entidades ?? ""])} />
      )}
      <p className="busca-detalhe">
        Transferências da União registradas no Portal da Transparência (CGU), arquivo mensal
        {primeiro && ultimo ? ` de ${mesCurto(primeiro)} a ${mesCurto(ultimo)}` : ""}, pelo ano do repasse; valores{" "}
        {unidade}. Prefeitura e fundos: o próprio município e os fundos dele (como o Fundo Municipal de Saúde).
        Entidades: as sem fins lucrativos do município, como as unidades executoras das escolas (PDDE). Não estão aqui o
        FPM e as cotas-partes, que o arquivo da CGU não traz: eles aparecem nas receitas do município, acima.
        {antesDe2014.length > 0 && ` O arquivo começa em 2014: ${antesDe2014.join(", ")} fica${antesDe2014.length > 1 ? "m" : ""} sem dado.`}
        {r.incompletos.length > 0 && ` Ano com menos de 12 meses: ${r.incompletos.join(", ")} (a carga ainda não chegou a todos os meses, ou o ano não acabou).`}
      </p>
    </>
  );
}
