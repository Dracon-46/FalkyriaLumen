/**
 * O que acompanha os números da tela: as faixas de aviso no topo (simulação,
 * amostra, ressalvas da fonte) e a linha de origem no fim, que liga cada
 * número ao arquivo oficial de onde saiu.
 */

import { instante } from "@/lib/formato";
import type { EleicaoIndice, Feed } from "@/lib/tipos";

/** Avisos que precisam aparecer antes dos números: simulação, amostra e ressalvas da fonte. */
export function Faixas({ eleicao, feed }: { eleicao: EleicaoIndice; feed: Feed | null }) {
  const simulacao = eleicao.simulacao || feed?.origem.simulacao;
  const amostra = eleicao.amostra || feed?.origem.amostra;
  return (
    <>
      {simulacao && (
        <div className="faixa faixa-simulacao" role="note">
          <strong>Simulação.</strong> Os números intermediários desta tela são fictícios, gerados para testar a
          apuração ao vivo. Só o resultado final, ao término da simulação, é o oficial do TSE.
        </div>
      )}
      {amostra && !simulacao && (
        <div className="faixa faixa-simulacao" role="note">
          <strong>Amostra de desenvolvimento.</strong> Resultados oficiais do TSE de apenas alguns estados e
          municípios, para testar o portal sem a coleta completa.
        </div>
      )}
      {feed && feed.avisos.length === 1 && (
        <div className="faixa" role="note">
          {feed.avisos[0]}
        </div>
      )}
      {feed && feed.avisos.length > 1 && (
        // Eleições antigas trazem várias ressalvas: uma faixa só, em lista, em vez de uma pilha de faixas
        <div className="faixa" role="note">
          <ul className="faixa-lista">
            {feed.avisos.map((a) => (
              <li key={a}>{a}</li>
            ))}
          </ul>
        </div>
      )}
    </>
  );
}

/** De onde vieram os números desta tela. */
export function Origem({ feed }: { feed: Feed }) {
  const o = feed.origem;
  const fonte =
    o.fonte === "resultados"
      ? "sistema de divulgação de resultados do TSE"
      : o.fonte === "dados_abertos"
        ? "Portal de Dados Abertos do TSE"
        : o.fonte;
  return (
    <p className="candidato-detalhe so-tela">
      Fonte: {fonte}
      {o.url && (
        <>
          {" "}
          (
          <a href={o.url} rel="noopener noreferrer" target="_blank">
            arquivo original
          </a>
          )
        </>
      )}
      {o.coletado_em && `, coletado em ${instante(o.coletado_em)}`}.
      {o.sha256 && (
        <>
          {" "}
          SHA-256 da cópia guardada: <code style={{ overflowWrap: "anywhere" }}>{o.sha256}</code>.
        </>
      )}
    </p>
  );
}
