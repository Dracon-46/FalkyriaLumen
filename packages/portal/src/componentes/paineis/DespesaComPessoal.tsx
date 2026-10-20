/**
 * Despesa com pessoal do Poder Executivo em % da receita corrente líquida ajustada, pelo RGF do último período do
 * exercício (ADR-042; LRF, arts. 19, 20, 22 e 59). Mostra o percentual e os limites que o próprio relatório
 * declara, ao lado da mediana do grupo de pares. São os números do ente; a verificação cabe ao tribunal de contas.
 */

import { numero, percentual } from "@/lib/formato";
import {
  faixaCentral,
  faixaDoLimite,
  moeda,
  periodoDoRgf,
  urlRgfDoEnte,
  type PessoalPares,
} from "@/lib/paineis";
import { Numero } from "./Comuns";

const METODO = "https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-042.md";

/** A seção da despesa com pessoal; não aparece nos arquivos publicados antes dela. */
export function DespesaComPessoal({ codigo, pessoal, minimo }: { codigo: string; pessoal: PessoalPares | undefined;
  minimo: number }) {
  if (!pessoal || pessoal.exercicio === null) return null;
  const { exercicio, ente, grupo } = pessoal;
  const limites = ente?.limites ?? {};
  const faixa = ente ? faixaDoLimite(ente.percentual, limites) : null;

  return (
    <>
      <h3 className="modal-subtitulo">Despesa com pessoal do Poder Executivo ({exercicio})</h3>
      {ente ? (
        <div className="totais">
          <Numero
            rotulo={`Este ente, RGF do ${periodoDoRgf(ente.periodo, ente.periodicidade, exercicio)}`}
            valor={`${percentual(ente.percentual)} da RCL ajustada`}
            detalhe={[faixa, ente.dtp !== null ? `${moeda(ente.dtp)} em 12 meses` : null].filter(Boolean).join(" · ")}
          />
          <Numero
            rotulo="Limites declarados no mesmo RGF"
            valor={`${percentual(limites.maximo)} máximo`}
            detalhe={`prudencial ${percentual(limites.prudencial)} · alerta ${percentual(limites.alerta)}`}
          />
          <Numero
            rotulo="Mediana do grupo"
            valor={grupo ? percentual(grupo.mediana) : "—"}
            detalhe={grupo ? `metade dos entes ${faixaCentral(grupo, 1)}` : undefined}
          />
        </div>
      ) : (
        <p className="busca-detalhe">
          O RGF do Poder Executivo do último período de {exercicio} não foi lido no SICONFI até a última consulta
          (ele é tentado de novo toda semana).
        </p>
      )}
      {ente && ente.percentual > 100 && (
        <p className="busca-detalhe">
          Mais de 100%: a despesa com pessoal declarada passa de toda a receita corrente líquida ajustada declarada no
          mesmo RGF{ente.rcl_ajustada !== null ? ` (${moeda(ente.rcl_ajustada)})` : ""}. Vale conferir o relatório na
          fonte.
        </p>
      )}
      {!grupo && (
        <p className="busca-detalhe">
          Só {numero(pessoal.entes_com_rgf)} entes do grupo têm o RGF de {exercicio} lido, menos que o mínimo de{" "}
          {minimo}: sem a distribuição do grupo.
        </p>
      )}
      <p className="busca-detalhe">
        Despesa total com pessoal do Poder Executivo nos últimos 12 meses, sobre a receita corrente líquida ajustada,
        no Anexo 1 do RGF. Os limites são os que o próprio relatório declara: o máximo (em regra, 54% para o
        Executivo municipal e 49% para o estadual; 48,6% no estado com tribunal de contas dos municípios; LRF, art.
        20), o prudencial (95% dele, art. 22) e o de alerta (90%, art. 59). O Poder Legislativo tem limite próprio e não entra aqui. São os números do ente; a verificação do
        cumprimento cabe ao tribunal de contas.{" "}
        {ente && (
          <>
            <a href={urlRgfDoEnte(codigo, exercicio, ente)} target="_blank" rel="noreferrer">
              O RGF no SICONFI
            </a>{" "}
            ·{" "}
          </>
        )}
        <a href={METODO} target="_blank" rel="noreferrer">
          Como a comparação é feita
        </a>
        .
      </p>
    </>
  );
}
