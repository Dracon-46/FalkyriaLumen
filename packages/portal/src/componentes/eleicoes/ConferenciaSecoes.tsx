/**
 * Conferência seção a seção (ADR-053): a votação de cada seção publicada nos
 * dados abertos do TSE, somada, ao lado do total do sistema de resultados.
 * No Brasil, a tabela do Brasil e a lista das UFs que não batem (ou a
 * confirmação de que todas batem); numa UF, a tabela dela.
 */

import { instante, numero } from "@/lib/formato";
import type { AbrangenciaConferida, FeedConferencia } from "@/lib/tipos";

/** Diferença com sinal; zero como "0" e sem divulgado como "—". */
function diferenca(v: number | null): string {
  if (v === null) return "—";
  return v === 0 ? "0" : `${v > 0 ? "+" : "−"}${numero(Math.abs(v))}`;
}

/** A tabela de uma abrangência: cada número votado, a soma das seções, o divulgado e a diferença. */
function Tabela({ abr }: { abr: AbrangenciaConferida }) {
  return (
    <div className="tabela-rolavel">
      <table className="tabela" style={{ marginTop: 8 }}>
        <thead>
          <tr>
            <th>Votos</th>
            <th className="n">Soma das seções</th>
            <th className="n">Total divulgado</th>
            <th className="n">Diferença</th>
          </tr>
        </thead>
        <tbody>
          {abr.linhas.map((l) => (
            <tr key={`${l.rotulo}-${l.numero ?? ""}`} className={l.diferenca ? "linha-diferenca" : undefined}>
              <td>
                {l.rotulo}
                {l.detalhe && <div className="total-detalhe">{l.detalhe}</div>}
              </td>
              <td className="n">{numero(l.secoes)}</td>
              <td className="n">{numero(l.divulgado)}</td>
              <td className="n">{diferenca(l.diferenca)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** O cartão da conferência. `uf`: a sigla, para mostrar só a UF; sem ela, o Brasil e a lista das UFs. */
export function ConferenciaSecoes({ conferencia: c, uf }: { conferencia: FeedConferencia; uf?: string | null }) {
  const daUf = uf ? c.ufs.find((u) => u.uf === uf) : undefined;
  const abr = daUf ?? c.brasil;
  const divergentes = c.ufs.filter((u) => u.conferida && !u.confere);
  const semConferir = c.ufs.filter((u) => !u.conferida);
  const secoes = daUf ? daUf.secoes : c.secoes.no_arquivo;
  const lugar = daUf ? daUf.nome : "no Brasil";
  return (
    <section className="cartao cartao-corpo" aria-labelledby="titulo-conferencia">
      <h2 id="titulo-conferencia" className="titulo-secao">
        Conferência seção a seção
      </h2>
      <p className={abr.confere ? "conferencia-ok" : "conferencia-diferenca"}>
        {!abr.conferida
          ? `O total divulgado ${daUf ? `de ${daUf.nome}` : "do Brasil"} não pôde ser lido na conferência.`
          : abr.confere
            ? `Confere: somando os votos das ${numero(secoes)} seções ${daUf ? `de ${daUf.nome}` : "do país e do exterior"}, cada candidato, os brancos e os nulos têm exatamente o total divulgado ${lugar}.`
            : `Há diferença entre a soma das seções e o total divulgado ${lugar}: veja as linhas marcadas.`}
      </p>
      {!daUf && abr.conferida && (
        <p className="candidato-detalhe">
          {divergentes.length === 0 && semConferir.length === 0
            ? `Também confere em cada uma das ${c.ufs.filter((u) => u.uf !== "zz").length} UFs${c.ufs.some((u) => u.uf === "zz") ? " e no exterior" : ""}.`
            : [
                divergentes.length ? `Com diferença: ${divergentes.map((u) => u.nome).join(", ")}.` : "",
                semConferir.length ? `Sem o total divulgado para conferir: ${semConferir.map((u) => u.nome).join(", ")}.` : "",
              ].filter(Boolean).join(" ")}
        </p>
      )}
      {abr.conferida && <Tabela abr={abr} />}
      <p className="candidato-detalhe">
        Duas publicações independentes do TSE: a votação por seção, dos dados abertos (o conteúdo de cada boletim de
        urna, uma linha por seção e número votado), e o total do sistema de resultados. Nulos técnicos são os votos em
        números que estavam na urna mas não estão na lista de candidatos do resultado. O arquivo traz só as seções com
        voto ({numero(c.secoes.no_arquivo)}, de {numero(c.secoes.divulgadas)} no total divulgado: as que não foram
        instaladas não têm votos). Conferido em {instante(c.conferido_em)}
        {c.origem_secoes.url && (
          <>
            {" "}· <a href={c.origem_secoes.url}>votação por seção</a>
          </>
        )}
        {c.origem_secoes.sha256 && <> (SHA-256 <code>{c.origem_secoes.sha256.slice(0, 16)}…</code>)</>}
        {c.origem_divulgado.url && (
          <>
            {" "}· <a href={c.origem_divulgado.url}>total divulgado</a>
          </>
        )}
        .
      </p>
    </section>
  );
}

/** Aviso no lugar do cartão quando a votação por seção do turno ainda não saiu nos dados abertos. */
export function ConferenciaPendente({ turno }: { turno: number }) {
  return (
    <section className="cartao cartao-corpo" aria-labelledby="titulo-conferencia">
      <h2 id="titulo-conferencia" className="titulo-secao">
        Conferência seção a seção
      </h2>
      <p className="candidato-detalhe">
        A votação por seção do {turno}º turno ainda não está nos dados abertos do TSE. Quando sair, a carga soma os votos
        de cada seção e compara com o total divulgado, como já faz com o 1º turno (veja o 1º turno).
      </p>
    </section>
  );
}
