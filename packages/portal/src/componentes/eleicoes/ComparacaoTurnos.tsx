/** Quadro do 2º turno ao lado do 1º, na mesma abrangência (`lib/comparacao.ts`). */

import { type Comparacao, type Variacao } from "@/lib/comparacao";
import { varCor } from "@/lib/cores";
import { numero, percentual } from "@/lib/formato";

/** Número com sinal ("+1.234", "−1.234"); o zero vai sem sinal. */
function comSinal(v: number | null): string {
  if (v === null) return "—";
  return `${v > 0 ? "+" : v < 0 ? "−" : ""}${numero(Math.abs(v))}`;
}

/** Linha de um total (brancos, nulos...) com os dois turnos e a variação. */
function LinhaTotal({ rotulo, v }: { rotulo: string; v: Variacao }) {
  return (
    <tr>
      <td>{rotulo}</td>
      <td className="n">{numero(v.turno1)}</td>
      <td className="n">{numero(v.turno2)}</td>
      <td className="n">{comSinal(v.diferenca)}</td>
    </tr>
  );
}

/**
 * Comparação com o 1º turno: votos de cada finalista nos dois turnos, os
 * votos que foram para os demais candidatos, brancos, nulos, abstenção e
 * comparecimento — e a conta, em uma frase, de onde vieram os votos a mais.
 */
export function ComparacaoTurnos({ comparacao: c, onVerPrimeiro }: { comparacao: Comparacao; onVerPrimeiro: () => void }) {
  const { comparecimento, brancos, nulos, anulados, validos } = c;
  const explicados =
    comparecimento.diferenca !== null && brancos.diferenca !== null && nulos.diferenca !== null
      ? comparecimento.diferenca - brancos.diferenca - nulos.diferenca - (anulados.diferenca ?? 0)
      : null;
  const resto = explicados !== null && validos.diferenca !== null ? validos.diferenca - explicados : null;
  const partesValidos = [
    `comparecimento ${comSinal(comparecimento.diferenca)}`,
    `brancos ${comSinal(brancos.diferenca)}`,
    `nulos ${comSinal(nulos.diferenca)}`,
    ...(anulados.diferenca ? [`anulados ${comSinal(anulados.diferenca)}`] : []),
  ];
  return (
    <section className="cartao cartao-corpo" aria-labelledby="titulo-comparacao">
      <div className="grafico-cabeca">
        <h2 id="titulo-comparacao" className="titulo-secao">
          Comparação com o 1º turno
        </h2>
        <button type="button" className="botao" onClick={onVerPrimeiro}>
          Ver o 1º turno
        </button>
      </div>
      <div className="tabela-rolavel">
        <table className="tabela" style={{ marginTop: 8 }}>
          <thead>
            <tr>
              <th>Votos</th>
              <th className="n">1º turno</th>
              <th className="n">2º turno</th>
              <th className="n">Variação</th>
            </tr>
          </thead>
          <tbody>
            {c.finalistas.map((f) => (
              <tr key={f.numero}>
                <td>
                  <span className="amostra-cor" style={{ background: varCor(f.cor) }} /> {f.nome}
                  {f.partido ? ` (${f.partido})` : ""}
                </td>
                <td className="n">
                  {numero(f.votos1)}
                  <div className="total-detalhe">{percentual(f.pct1)}</div>
                </td>
                <td className="n">
                  {numero(f.votos2)}
                  <div className="total-detalhe">{percentual(f.pct2)}</div>
                </td>
                <td className="n">{comSinal(f.votos2 - f.votos1)}</td>
              </tr>
            ))}
            <tr>
              <td>Demais candidatos do 1º turno</td>
              <td className="n">{numero(c.demais)}</td>
              <td className="n">—</td>
              <td className="n">{comSinal(c.demais === null ? null : -c.demais)}</td>
            </tr>
            <LinhaTotal rotulo="Válidos" v={validos} />
            <LinhaTotal rotulo="Brancos" v={brancos} />
            <LinhaTotal rotulo="Nulos" v={nulos} />
            {!!(anulados.turno1 || anulados.turno2) && <LinhaTotal rotulo="Anulados" v={anulados} />}
            <LinhaTotal rotulo="Comparecimento" v={comparecimento} />
            <LinhaTotal rotulo="Abstenção" v={c.abstencao} />
          </tbody>
        </table>
      </div>
      {c.demais !== null && validos.diferenca !== null && (
        <p className="candidato-detalhe">
          Os finalistas somaram <strong>{comSinal(c.ganho)}</strong> votos em relação ao 1º turno. Na conta líquida,{" "}
          {numero(c.demais)} são os votos que os demais candidatos tiveram no 1º turno e {comSinal(validos.diferenca)} a
          variação dos votos válidos ({partesValidos.join(", ")}
          {resto ? `; ${comSinal(resto)} de diferença entre os totais que o TSE publica` : ""}). O voto é secreto: a conta
          mostra quanto mudou, não quem mudou de voto.
        </p>
      )}
    </section>
  );
}
