"use client";

/**
 * Situação das coletas (RF-AD-05; ADR-039): os alertas, as execuções dos fluxos de dados, o volume diário do
 * PNCP contra o usual e a coleta da conformidade por UF. É a saúde do Lumen e das fontes, não dos entes.
 */

import { useEffect, useState } from "react";
import { haQuanto, instante, numero, numeroCompacto, percentual } from "@/lib/formato";
import { carregarOperacao, rotuloExecucao, type Operacao } from "@/lib/operacao";
import { dataCurta } from "@/lib/paineis";
import { GraficoBarras, Situacao } from "./Comuns";

const METODO = "https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-039.md";

/** Carregando, o arquivo lido (null quando ainda não publicado) ou o erro. */
type Estado = { fase: "carregando" } | { fase: "pronto"; dados: Operacao | null } | { fase: "erro"; erro: string };

/** A página inteira da situação das coletas. */
export function PainelOperacao() {
  const [estado, setEstado] = useState<Estado>({ fase: "carregando" });
  useEffect(() => {
    const c = new AbortController();
    carregarOperacao(c.signal)
      .then((dados) => setEstado({ fase: "pronto", dados }))
      .catch((e: Error) => {
        if (e.name !== "AbortError") setEstado({ fase: "erro", erro: e.message });
      });
    return () => c.abort();
  }, []);

  if (estado.fase === "carregando") return <Situacao>Carregando…</Situacao>;
  if (estado.fase === "erro") return <Situacao>Não foi possível ler a situação das coletas agora ({estado.erro}).</Situacao>;
  if (!estado.dados) return <Situacao>A situação das coletas ainda não foi publicada.</Situacao>;
  const d = estado.dados;
  const p = d.parametros;
  return (
    <>
      <p className="painel-periodo">
        Atualizado em {instante(d.gerado_em)} · janela de {p.janela_dias} dias · limiares iniciais, não calibrados ·{" "}
        <a href={METODO} target="_blank" rel="noreferrer">
          como é medido
        </a>
      </p>

      <section className="cartao cartao-corpo" aria-labelledby="titulo-alertas">
        <h2 id="titulo-alertas" className="titulo-secao">Alertas</h2>
        {d.alertas.length === 0 ? (
          <p className="busca-detalhe">Nenhum alerta: fluxos em dia, volume do PNCP dentro do usual e conformidade coletada.</p>
        ) : (
          <ul>
            {d.alertas.map((a, i) => (
              <li key={i}>
                {a.texto}
                {a.url && (
                  <>
                    {" · "}
                    <a href={a.url} target="_blank" rel="noreferrer">
                      ver a execução
                    </a>
                  </>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="cartao cartao-corpo" aria-labelledby="titulo-fluxos">
        <h2 id="titulo-fluxos" className="titulo-secao">Fluxos de dados (GitHub Actions)</h2>
        {!d.fluxos ? (
          <p className="busca-detalhe">As execuções não foram lidas nesta publicação.</p>
        ) : (
          <div className="tabela-rolavel">
            <table className="tabela">
              <thead>
                <tr>
                  <th>Fluxo</th>
                  <th>Última execução</th>
                  <th>Última com sucesso</th>
                  <th className="n">Execuções</th>
                  <th className="n">Falhas</th>
                </tr>
              </thead>
              <tbody>
                {d.fluxos.map((f) => (
                  <tr key={f.fluxo}>
                    <td>
                      {f.descricao}
                      <div className="busca-detalhe">{f.cadencia_horas === null ? "sob demanda" : f.cadencia_horas > 24 ? "toda semana" : "todo dia"}</div>
                    </td>
                    <td>
                      {f.ultima ? (
                        <>
                          {f.ultima.url ? (
                            <a href={f.ultima.url} target="_blank" rel="noreferrer">
                              {rotuloExecucao(f.ultima.situacao, f.ultima.resultado)}
                            </a>
                          ) : (
                            rotuloExecucao(f.ultima.situacao, f.ultima.resultado)
                          )}
                          <div className="busca-detalhe">{instante(f.ultima.inicio)}</div>
                        </>
                      ) : (
                        `nenhuma em ${p.janela_dias} dias`
                      )}
                    </td>
                    <td>
                      {f.ultimo_sucesso ? haQuanto(f.ultimo_sucesso) : "nenhuma"}
                      {f.atrasado && <div className="busca-detalhe">além da cadência e da tolerância de {p.tolerancia_horas} h</div>}
                    </td>
                    <td className="n">{numero(f.execucoes)}</td>
                    <td className="n">
                      {numero(f.falhas)}
                      {f.taxa_falha !== null && <div className="busca-detalhe">{percentual(f.taxa_falha * 100)}</div>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="cartao cartao-corpo" aria-labelledby="titulo-volume">
        <h2 id="titulo-volume" className="titulo-secao">Volume diário do PNCP</h2>
        <p className="busca-detalhe">
          Processos publicados por dia. Dia útil com menos de {percentual(p.fracao_minima * 100)} da mediana do mesmo
          dia da semana nas {p.semanas_base} semanas anteriores é alerta: a fonte respondeu, mas com muito menos que
          o usual. Fins de semana, feriados, pontos facultativos e pontes nacionais ficam de fora.
        </p>
        <GraficoBarras
          titulo="Processos publicados por dia"
          barras={d.contratacoes.dias.map((x) => ({ rotulo: `${x.dia.slice(8, 10)}/${x.dia.slice(5, 7)}`, valor: x.processos ?? 0 }))}
          formatar={numero}
          formatarEixo={numeroCompacto}
        />
        {d.contratacoes.faltando.length > 0 && (
          <p className="busca-detalhe">
            {numero(d.contratacoes.faltando.length)} dia(s) sem coleta desde o primeiro guardado:{" "}
            {d.contratacoes.faltando.map(dataCurta).join(", ")}.
          </p>
        )}
      </section>

      <section className="cartao cartao-corpo" aria-labelledby="titulo-coleta-conformidade">
        <h2 id="titulo-coleta-conformidade" className="titulo-secao">Coleta da conformidade (SICONFI)</h2>
        <div className="tabela-rolavel">
          <table className="tabela">
            <thead>
              <tr>
                <th>UF</th>
                <th>Extrato coletado</th>
                <th className="n">Entes</th>
                <th className="n">Coleta malsucedida</th>
              </tr>
            </thead>
            <tbody>
              {d.conformidade.map((c) => (
                <tr key={c.uf}>
                  <td>{c.uf}</td>
                  <td>
                    {c.coletado_em ? haQuanto(c.coletado_em) : "nunca"}
                    {c.atrasada && <div className="busca-detalhe">mais de {p.horas_conformidade} h</div>}
                  </td>
                  <td className="n">{numero(c.entes)}</td>
                  <td className="n">{numero(c.coleta_malsucedida)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
