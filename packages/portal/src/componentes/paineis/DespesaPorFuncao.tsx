"use client";

/**
 * Despesa por função do ente (ADR-041; RF-PU-05). Abre no total gasto em cada função, com a fatia do total; o filtro
 * "por habitante, com o grupo" mostra o valor por habitante ao lado da mediana e da metade central do grupo de
 * pares, e de que lado dela o ente fica (entes de tamanhos diferentes só se comparam por habitante). É contexto,
 * como o resto do cartão: a diferença tem causas que a tabela não mostra, e a tela as lista.
 */

import { useState } from "react";
import Link from "next/link";
import { numero, percentual } from "@/lib/formato";
import {
  faixaCentralEmReais,
  moeda,
  posicaoNoGrupo,
  urlDcaDoEnte,
  type DespesaPares,
  type LinhaDespesa,
  moedaCompacta,
  tipoDoCodigo,
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
  const [porHabitante, setPorHabitante] = useState(false);
  if (!despesa || despesa.exercicio === null) return null;
  const { exercicio } = despesa;
  // No total, as funções vão do maior para o menor valor do ente; por habitante, pela mediana do grupo (como vêm)
  const funcoes = porHabitante ? despesa.funcoes
    : [...despesa.funcoes.slice(0, 1), ...despesa.funcoes.slice(1).filter((l) => l.valor).sort((x, y) => y.valor - x.valor)];
  const total = despesa.funcoes[0]?.valor ?? 0;
  const visiveis = todas ? funcoes : funcoes.slice(0, LINHAS_INICIAIS);
  const semDistribuicao = !porHabitante || despesa.entes_com_dca < minimo;

  return (
    <>
      <h3 className="modal-subtitulo">Despesa por função ({exercicio})</h3>
      <div className="filtro-periodo-atalhos gasto-controles" role="group" aria-label="Mostrar">
        <button type="button" className="botao" aria-pressed={!porHabitante} onClick={() => setPorHabitante(false)}>
          Total gasto
        </button>
        <button type="button" className="botao" aria-pressed={porHabitante} onClick={() => setPorHabitante(true)}>
          Por habitante, com o grupo
        </button>
      </div>
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
          {porHabitante && semDistribuicao && (
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
                  <th className="n">{porHabitante ? "Este ente, por habitante" : "Total gasto"}</th>
                  {!porHabitante && <th className="n">% do total</th>}
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
                    <td className="n">{porHabitante ? moeda(l.por_habitante) : moedaCompacta(l.valor)}</td>
                    {!porHabitante && <td className="n">{total ? percentual((l.valor / total) * 100) : "—"}</td>}
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
        {porHabitante ? (
          <>
            Despesa liquidada na DCA de {exercicio} (Anexo I-E), sem as intraorçamentárias, dividida pela população
            do cadastro do SICONFI
            {semDistribuicao ? ". " : `; a distribuição é entre os ${numero(despesa.entes_com_dca)} entes do grupo com a DCA lida. `}
            A diferença para o grupo tem causas que a tabela não mostra: o ente que sedia hospital ou escola regional
            atende os vizinhos, a classificação por função varia de um ente para outro, a população pode estar
            desatualizada e a DCA é a que o ente entregou. É contexto, não avaliação.
          </>
        ) : (
          <>
            Despesa liquidada na DCA de {exercicio} (Anexo I-E), sem as intraorçamentárias, em reais da época. A
            comparação com o grupo de pares é por habitante, porque os entes têm tamanhos diferentes.
          </>
        )}{" "}
        {tipoDoCodigo(codigo) === "municipio" && (
          <>
            <Link href={`/economia/municipio/?ente=${codigo}`}>Mandato a mandato e com o que foi gasto</Link> ·{" "}
          </>
        )}
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
