/** Quadro de comparecimento e destino dos votos de um resultado. */

import { numero, percentual } from "@/lib/formato";
import type { FeedResultado } from "@/lib/tipos";

/** Um número com rótulo e, quando há, o percentual logo abaixo. */
function Bloco({ rotulo, valor, detalhe }: { rotulo: string; valor: string; detalhe?: string }) {
  return (
    <div>
      <div className="total-rotulo">{rotulo}</div>
      <div className="total-valor">{valor}</div>
      {detalhe && <div className="total-detalhe">{detalhe}</div>}
    </div>
  );
}

/** Comparecimento e destino dos votos, como o TSE publica. */
export function Totais({ feed }: { feed: FeedResultado }) {
  const { comparecimento: c, votos: v } = feed;
  return (
    <section className="cartao cartao-corpo" aria-labelledby="titulo-totais">
      <h2 id="titulo-totais" className="titulo-secao">
        Comparecimento e votos
      </h2>
      <div className="totais">
        <Bloco rotulo="Eleitorado" valor={numero(c.eleitorado)} />
        <Bloco rotulo="Comparecimento" valor={numero(c.comparecimento)} detalhe={percentual(c.pct_comparecimento)} />
        <Bloco rotulo="Abstenção" valor={numero(c.abstencao)} detalhe={percentual(c.pct_abstencao)} />
        <Bloco rotulo="Válidos" valor={numero(v.validos)} detalhe={percentual(v.pct_validos)} />
        <Bloco rotulo="Brancos" valor={numero(v.brancos)} detalhe={percentual(v.pct_brancos)} />
        <Bloco rotulo="Nulos" valor={numero(v.nulos)}
          detalhe={`${percentual(v.pct_nulos)}${v.nulos_tecnicos ? ` · ${numero(v.nulos_tecnicos)} técnicos` : ""}`} />
        {!!v.anulados && <Bloco rotulo="Anulados" valor={numero(v.anulados)} />}
        {!!v.legenda && <Bloco rotulo="De legenda" valor={numero(v.legenda)} />}
        {!!c.eleitorado_secoes_nao_instaladas && (
          <Bloco rotulo="Em seções não instaladas" valor={numero(c.eleitorado_secoes_nao_instaladas)}
            detalhe="eleitores, fora do comparecimento e da abstenção" />
        )}
      </div>
      {!!v.nulos_tecnicos && (
        <p className="candidato-detalhe">
          O TSE publica os nulos em duas parcelas, nulos e nulos técnicos; o número acima é o total, e com ele
          válidos, brancos e nulos somam o comparecimento.
        </p>
      )}
    </section>
  );
}
