"use client";

/**
 * Despesa por função do ente, por habitante, ao lado do grupo de pares (ADR-041; RF-PU-05). Mostra o valor do
 * ente, a mediana e a metade central do grupo, e de que lado dela o ente fica. É contexto, como o resto do cartão:
 * a diferença tem causas que a tabela não mostra, e a tela as lista.
 */

import { useState } from "react";
import { numero } from "@/lib/formato";
import {
  faixaCentralEmReais,
  moeda,
  posicaoNoGrupo,
  urlDcaDoEnte,
  type DespesaPares,
  type LinhaDespesa,
} from "@/lib/paineis";

const METODO = "https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-041.md";
/** Linhas mostradas antes de "ver todas": o total e as sete funções de maior mediana no grupo. */
const LINHAS_INICIAIS = 8;
const ROTULOS_POSICAO = {
  acima: "acima da metade central",
  abaixo: "abaixo da metade central",
  central: "na metade central",
} as const;

/** A posição do ente na linha, ou um traço sem distribuição. */
function posicao(linha: LinhaDespesa): string {
  if (!linha.grupo || linha.por_habitante === null) return "—";
  return ROTULOS_POSICAO[posicaoNoGrupo(linha.por_habitante, linha.grupo)];
}

/** A seção da despesa por função; não aparece nos arquivos publicados antes dela. */
export function DespesaPorFuncao({ codigo, despesa, minimo }: { codigo: string; despesa: DespesaPares | undefined;
  minimo: number }) {
  const [todas, setTodas] = useState(false);
  if (!despesa || despesa.exercicio === null) return null;
  const { exercicio, funcoes } = despesa;
  const visiveis = todas ? funcoes : funcoes.slice(0, LINHAS_INICIAIS);
  const semDistribuicao = despesa.entes_com_dca < minimo;

  return (
    <>
      <h3 className="modal-subtitulo">Despesa por função, por habitante ({exercicio})</h3>
      {funcoes.length === 0 ? (
        <p className="busca-detalhe">
          A DCA de {exercicio} deste ente não foi lida no SICONFI até a última consulta (ela é tentada de novo
          toda semana).
        </p>
      ) : (
        <>
          {despesa.confere === false && (
            <p className="busca-detalhe">
              As funções desta DCA não somam o total declarado: o ente fica fora das distribuições do grupo.
            </p>
          )}
          {semDistribuicao && (
            <p className="busca-detalhe">
              Só {numero(despesa.entes_com_dca)} entes do grupo têm a DCA de {exercicio} lida, menos que o mínimo
              de {minimo}: a tabela mostra os valores do ente, sem a distribuição do grupo.
            </p>
          )}
          <div className="tabela-rolavel">
            <table className="tabela">
              <thead>
                <tr>
                  <th>Função</th>
                  <th className="n">Este ente</th>
                  {!semDistribuicao && (
                    <>
                      <th className="n">Mediana do grupo</th>
                      <th>Metade dos entes do grupo</th>
                      <th>Este ente fica</th>
                    </>
                  )}
                </tr>
              </thead>
              <tbody>
                {visiveis.map((l) => (
                  <tr key={l.codigo}>
                    <td>{l.codigo === "total" ? <strong>{l.nome}</strong> : l.nome}</td>
                    <td className="n">{moeda(l.por_habitante)}</td>
                    {!semDistribuicao && (
                      <>
                        <td className="n">{l.grupo ? moeda(l.grupo.mediana) : "—"}</td>
                        <td>{l.grupo ? faixaCentralEmReais(l.grupo) : "—"}</td>
                        <td>{posicao(l)}</td>
                      </>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {funcoes.length > LINHAS_INICIAIS && (
            <button type="button" className="botao-link" onClick={() => setTodas(!todas)}>
              {todas ? "mostrar menos" : `ver as ${funcoes.length - 1} funções com valor`}
            </button>
          )}
        </>
      )}
      <p className="busca-detalhe">
        Despesa liquidada na DCA de {exercicio} (Anexo I-E), sem as intraorçamentárias, dividida pela população do
        cadastro do SICONFI
        {semDistribuicao ? ". " : `; a distribuição é entre os ${numero(despesa.entes_com_dca)} entes do grupo com a DCA lida. `}
        A diferença para o grupo tem causas que a tabela não mostra: o ente que sedia hospital ou escola regional
        atende os vizinhos, a classificação por função varia de um ente para outro, a população pode estar
        desatualizada e a DCA é a que o ente entregou. É contexto, não avaliação.{" "}
        <a href={urlDcaDoEnte(codigo, exercicio)} target="_blank" rel="noreferrer">
          A DCA no SICONFI
        </a>{" "}
        ·{" "}
        <a href={METODO} target="_blank" rel="noreferrer">
          Como a comparação é feita
        </a>
        .
      </p>
    </>
  );
}
