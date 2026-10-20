"use client";

/**
 * Governos municipais (ADR-040): para o município de `?ente=`, cada mandato de prefeito, com quem foi eleito, a
 * população no começo e no fim e a média anual da despesa (total, saúde, educação, assistência social e
 * urbanismo), corrigida pelo IPCA e por habitante. Ano a ano, os mesmos números. Lido sob demanda das fontes
 * (`lib/governos.ts`); como a comparação de presidentes, mostra o que foi registrado, não o que causou a diferença.
 */

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { numero, percentual } from "@/lib/formato";
import { carregarEconomia } from "@/lib/economia";
import {
  anoBase,
  anosMunicipaisComDespesa,
  carregarMunicipio,
  type DadosMunicipio,
  FUNCOES,
  ipcaMedioAnual,
  PRIMEIRO_ANO_DCA,
  populacaoPorAno,
  quemGovernou,
  resumirMandatos,
  urlPopulacao,
} from "@/lib/governos";
import { carregarEntes, type EnteBusca, moeda, moedaCompacta, tipoDoCodigo } from "@/lib/paineis";
import { BuscaEnte } from "@/componentes/paineis/Comuns";

const METODO = "https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-040.md";
const POR_HABITANTE = FUNCOES.filter((f) => f.id !== "total");

/** O andamento da leitura do município. */
type Estado =
  | { fase: "vazio" }
  | { fase: "carregando" }
  | { fase: "pronto"; ente: EnteBusca; dados: DadosMunicipio; medias: Map<string, number>; base: string | null }
  | { fase: "erro"; mensagem: string };

/** A página dos governos municipais, a partir de `?ente=` na URL. */
export function PainelGovernos() {
  const params = useSearchParams();
  const router = useRouter();
  const codigo = params.get("ente");
  const [estado, setEstado] = useState<Estado>({ fase: "vazio" });

  useEffect(() => {
    if (!codigo) {
      setEstado({ fase: "vazio" });
      return;
    }
    if (tipoDoCodigo(codigo) !== "municipio") {
      setEstado({ fase: "erro", mensagem: "Escolha um município: a comparação é entre mandatos de prefeito." });
      return;
    }
    const c = new AbortController();
    setEstado({ fase: "carregando" });
    (async () => {
      const [entes, economia] = await Promise.all([carregarEntes(), carregarEconomia(c.signal)]);
      const ente = entes.find((e) => e.codigo === codigo);
      if (!ente || !ente.uf) throw new Error("município não encontrado no cadastro");
      const medias = economia?.indicadores.ipca ? ipcaMedioAnual(economia.indicadores.ipca) : new Map<string, number>();
      const base = anoBase(medias);
      const ultimo = base ? Number(base) + 1 : new Date().getFullYear() - 1;
      const dados = await carregarMunicipio(codigo, ente.uf, ultimo, c.signal);
      setEstado({ fase: "pronto", ente, dados, medias, base });
    })().catch((e: Error) => {
      if (e.name !== "AbortError") setEstado({ fase: "erro", mensagem: e.message });
    });
    return () => c.abort();
  }, [codigo]);

  return (
    <div className="painel">
      <div className="painel-topo">
        <div>
          <h1>Governos municipais</h1>
          <p className="painel-periodo">
            Cada mandato de prefeito, com a população e a despesa do município no período.{" "}
            <Link href="/economia/">Economia e Contas Públicas</Link>
          </p>
        </div>
        <BuscaEnte rotulo="Buscar município" onEscolher={(c) => router.push(`/economia/municipio/?ente=${c}`)} />
      </div>
      <aside className="faixa aviso-metodologico" aria-label="Aviso metodológico">
        Mostra o que os resultados do TSE, as estimativas do IBGE e as contas anuais entregues ao Tesouro registraram
        em cada mandato. Não mostra o que causou a diferença entre um mandato e outro: a despesa depende de receitas,
        transferências e obrigações que passam de um governo a outro, e de fatores de fora da prefeitura.{" "}
        <a href={METODO} target="_blank" rel="noreferrer">
          Como é calculado
        </a>
        .
      </aside>
      {estado.fase === "vazio" && <p className="situacao-painel">Escolha um município na busca.</p>}
      {estado.fase === "carregando" && <p className="situacao-painel">Lendo os resultados, a população e as contas…</p>}
      {estado.fase === "erro" && <p className="situacao-painel">{estado.mensagem}</p>}
      {estado.fase === "pronto" && <Municipio {...estado} />}
    </div>
  );
}

/** Os mandatos e os anos do município lido. */
function Municipio({ ente, dados, medias, base }: Extract<Estado, { fase: "pronto" }>) {
  const populacao = useMemo(() => populacaoPorAno(dados.estimativas, dados.censo2022), [dados]);
  const anos = useMemo(
    () => anosMunicipaisComDespesa([...dados.despesas.keys()].sort(), populacao, dados.despesas, medias, base),
    [dados, populacao, medias, base],
  );
  const resumos = useMemo(() => resumirMandatos(dados.mandatos, dados.estimativas, anos).reverse(), [dados, anos]);
  const reais = base ? `R$ de ${base}` : "R$";

  return (
    <>
      <h2 className="painel-ente">
        {ente.nome}
        <span className="busca-detalhe">
          {" "}
          município · {ente.uf}
          {ente.populacao ? ` · ${numero(ente.populacao)} habitantes` : ""}
        </span>
      </h2>
      {dados.falhas.length > 0 && (
        <p className="situacao-painel">Não foi possível ler agora: {dados.falhas.join(", ")}.</p>
      )}

      <section className="cartao cartao-corpo" aria-labelledby="titulo-mandatos">
        <h2 id="titulo-mandatos" className="titulo-secao">Mandato a mandato</h2>
        {resumos.length === 0 ? (
          <p className="busca-detalhe">Nenhum resultado de eleição municipal publicado no Lumen para este município.</p>
        ) : (
          <div className="tabela-rolavel">
            <table className="tabela">
              <thead>
                <tr>
                  <th>Mandato</th>
                  <th>População</th>
                  <th className="n">Despesa por ano ({reais})</th>
                  <th className="n">Por habitante</th>
                  {POR_HABITANTE.map((f) => (
                    <th key={f.id} className="n">
                      {f.rotulo} por habitante
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {resumos.map((r) => (
                  <tr key={r.mandato.eleicao}>
                    <td>
                      {r.mandato.de}–{r.mandato.ate}
                      <div className="busca-detalhe">
                        {quemGovernou(r.mandato)}
                        {r.mandato.turno === 2 ? " · 2º turno" : ""}
                      </div>
                    </td>
                    <td>
                      {r.populacaoInicio ? numero(r.populacaoInicio[1]) : "—"} →{" "}
                      {r.populacaoFim ? numero(r.populacaoFim[1]) : "—"}
                      <div className="busca-detalhe">
                        {r.quebraPopulacao
                          ? `variação não calculada: mudança de método em ${r.quebraPopulacao}`
                          : r.variacaoPopulacao !== null
                            ? `${r.variacaoPopulacao > 0 ? "+" : ""}${percentual(r.variacaoPopulacao)}`
                            : ""}
                        {r.populacaoInicio && r.populacaoFim ? ` (${r.populacaoInicio[0]} a ${r.populacaoFim[0]})` : ""}
                      </div>
                    </td>
                    <td className="n">
                      {r.anosComContas ? moedaCompacta(r.mediaReal.total) : "—"}
                      <div className="busca-detalhe">
                        {r.anosComContas
                          ? `média de ${r.anosComContas} de 4 anos`
                          : r.mandato.ate < PRIMEIRO_ANO_DCA
                            ? `contas anuais só de ${PRIMEIRO_ANO_DCA} em diante`
                            : "contas ainda não entregues"}
                      </div>
                    </td>
                    <td className="n">{r.anosComContas ? moeda(r.mediaPorHabitante.total) : "—"}</td>
                    {POR_HABITANTE.map((f) => (
                      <td key={f.id} className="n">
                        {r.anosComContas ? moeda(r.mediaPorHabitante[f.id]) : "—"}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <details className="cartao cartao-corpo">
        <summary className="titulo-secao">Ano a ano</summary>
        <div className="tabela-rolavel">
          <table className="tabela">
            <thead>
              <tr>
                <th>Ano</th>
                <th className="n">População</th>
                <th className="n">Despesa (R$ da época)</th>
                <th className="n">Despesa ({reais})</th>
                <th className="n">Por habitante</th>
                {POR_HABITANTE.map((f) => (
                  <th key={f.id} className="n">
                    {f.rotulo}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {[...anos].reverse().map((a) => (
                <tr key={a.ano}>
                  <td>{a.ano}</td>
                  <td className="n">{numero(a.populacao)}</td>
                  <td className="n">{a.despesas ? moedaCompacta(a.despesas.total) : "contas não entregues"}</td>
                  <td className="n">{moedaCompacta(a.reais.total)}</td>
                  <td className="n">{moeda(a.porHabitante.total)}</td>
                  {POR_HABITANTE.map((f) => (
                    <td key={f.id} className="n">
                      {moeda(a.porHabitante[f.id])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>

      <section className="cartao cartao-corpo">
        <h2 className="titulo-secao">Fontes e cuidados</h2>
        <ul className="busca-detalhe">
          <li>
            Prefeitos: resultados do TSE publicados na aba{" "}
            <Link href={`/eleicoes/?a=mu-${ente.codigo}`}>Eleições</Link>; o eleito do 2º turno vem do 2º turno.
            Eleições suplementares (depois de cassação ou anulação) não estão nos dados.
          </li>
          <li>
            População:{" "}
            <a href={urlPopulacao(ente.codigo)} target="_blank" rel="noreferrer">
              estimativas do IBGE
            </a>{" "}
            (tabela 6579) e, em 2022 e 2023, o Censo 2022. As estimativas de antes do Censo 2022 vêm de outro método
            e, em muitos municípios, previam mais gente do que o censo contou: a despesa por habitante desses anos sai
            menor do que sairia com a população do censo.
          </li>
          <li>
            Despesa: contas anuais entregues ao Tesouro (DCA, Anexo I-E, despesa liquidada, sem as
            intraorçamentárias), de {PRIMEIRO_ANO_DCA} em diante; corrigida pelo IPCA médio de cada ano para{" "}
            {reais}.
          </li>
        </ul>
      </section>
    </>
  );
}
