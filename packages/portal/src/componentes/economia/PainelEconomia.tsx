"use client";

/**
 * Economia e Contas Públicas (ADR-033): os indicadores de inflação, juros, dívida, resultado fiscal e
 * atividade, com a fonte e a data de cada um, a série histórica e a comparação entre dois períodos.
 *
 * O estado fica na URL, para compartilhar a consulta: `?ind=` (o indicador do gráfico), `?a=` e `?b=` (os
 * períodos comparados, `AAAA-MM..AAAA-MM`). A comparação mostra o que as séries oficiais registraram em
 * cada período; ela não atribui o resultado a quem governava.
 */

import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import {
  carregarEconomia,
  type FeedEconomia,
  type Indicador,
  MANDATOS,
  mesValido,
  type Periodo,
  periodoCurto,
  type Resumo,
  resumir,
  valorNaUnidade,
  variacaoTexto,
} from "@/lib/economia";
import { instante } from "@/lib/formato";
import { GraficoLinha } from "./GraficoLinha";

const METODOLOGIA = "https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-033.md";
const DESTAQUES = ["ipca_12m", "selic_anualizada", "juro_real_12m", "divida_bruta", "divida_liquida",
                   "primario_12m", "nominal_12m", "pib_real"];
const PADRAO_A = MANDATOS[MANDATOS.length - 2]!;
const PADRAO_B = MANDATOS[MANDATOS.length - 1]!;
const DIAS_PARA_DEFASADO = 4;

/** Carregando, ou o arquivo lido (null quando ainda não foi publicado) e o erro, se houve. */
type Estado = { carregando: true } | { carregando: false; dados: FeedEconomia | null; erro: string | null };

/** Período da URL (`2019-01..2022-12`), ou o padrão. O rótulo vem do mandato com as mesmas datas, se houver. */
function periodoDaUrl(bruto: string | null, padrao: Periodo): Periodo {
  const [de, ate] = (bruto ?? "").split("..");
  if (!mesValido(de) || !mesValido(ate) || de > ate) return padrao;
  return MANDATOS.find((m) => m.de === de && m.ate === ate) ?? { de, ate, rotulo: `${periodoCurto(de)} a ${periodoCurto(ate)}` };
}

/** A coleta ficou para trás: falhou na última tentativa ou tem mais de alguns dias. */
function defasado(ind: Indicador, agora = Date.now()): boolean {
  if (ind.ultima_falha) return true;
  if (!ind.coletado_em) return true;
  return agora - new Date(ind.coletado_em).getTime() > DIAS_PARA_DEFASADO * 86_400_000;
}

/** Página inteira da área. */
export function PainelEconomia() {
  const params = useSearchParams();
  const router = useRouter();
  const [estado, setEstado] = useState<Estado>({ carregando: true });
  const a = periodoDaUrl(params.get("a"), PADRAO_A);
  const b = periodoDaUrl(params.get("b"), PADRAO_B);

  useEffect(() => {
    const c = new AbortController();
    carregarEconomia(c.signal)
      .then((dados) => setEstado({ carregando: false, dados, erro: null }))
      .catch((e: Error) => {
        if (e.name !== "AbortError") setEstado({ carregando: false, dados: null, erro: e.message });
      });
    return () => c.abort();
  }, []);

  const mudar = (chave: string, valor: string | null) => {
    const novo = new URLSearchParams(params.toString());
    if (valor) novo.set(chave, valor);
    else novo.delete(chave);
    router.replace(`?${novo.toString()}`, { scroll: false });
  };

  if (estado.carregando) return <p className="situacao-painel">Carregando os indicadores…</p>;
  if (estado.erro) return <p className="situacao-painel">Não foi possível ler os indicadores: {estado.erro}</p>;
  if (!estado.dados) {
    return (
      <p className="situacao-painel">
        Os indicadores ainda não foram publicados: a primeira coleta do fluxo diário ainda não rodou.
      </p>
    );
  }
  const dados = estado.dados;
  const escolhido = params.get("ind") && dados.indicadores[params.get("ind")!] ? params.get("ind")! : "ipca_12m";

  return (
    <div className="painel">
      <div className="painel-topo">
        <div>
          <h1>Economia e Contas Públicas</h1>
          <p className="painel-periodo">
            Inflação, juros, dívida, resultado fiscal e atividade, das séries oficiais do Banco Central e do IBGE.
            Publicado em {instante(dados.gerado_em)}.
          </p>
        </div>
      </div>
      <aside className="faixa aviso-metodologico" aria-label="Aviso metodológico">
        Cada número traz a fonte, o período a que se refere e a data da coleta. Comparar períodos mostra o que as
        séries registraram; não mostra o que causou a mudança, que depende de fatores de fora do governo e de
        decisões de mais de um governo.{" "}
        <a href={METODOLOGIA} target="_blank" rel="noreferrer">
          Metodologia completa
        </a>
        .
      </aside>
      <Destaques dados={dados} escolhido={escolhido} escolher={(id) => mudar("ind", id)} />
      <Detalhe ind={dados.indicadores[escolhido]!} id={escolhido} a={a} b={b} dados={dados}
               escolher={(id) => mudar("ind", id)} />
      <Comparacao dados={dados} a={a} b={b} mudar={mudar} />
    </div>
  );
}

/** Cartões dos indicadores principais: valor, período de referência e coleta. */
function Destaques({ dados, escolhido, escolher }: { dados: FeedEconomia; escolhido: string;
                                                     escolher: (id: string) => void }) {
  return (
    <section aria-labelledby="titulo-destaques">
      <h2 id="titulo-destaques" className="titulo-secao">
        Indicadores principais
      </h2>
      <div className="economia-cartoes">
        {DESTAQUES.filter((id) => dados.indicadores[id]).map((id) => {
          const ind = dados.indicadores[id]!;
          return (
            <button key={id} type="button" className="cartao cartao-corpo economia-cartao"
                    aria-pressed={id === escolhido} onClick={() => escolher(id)}>
              <span className="total-rotulo">{ind.nome}</span>
              <span className="total-valor">{valorNaUnidade(ind.ultimo?.valor, ind.unidade)}</span>
              <span className="total-detalhe">
                {ind.ultimo ? `referência: ${periodoCurto(ind.ultimo.periodo)}` : "sem dado publicado"}
                {defasado(ind) && <span className="economia-alerta"> · coleta atrasada</span>}
              </span>
            </button>
          );
        })}
      </div>
    </section>
  );
}

/** O indicador escolhido: gráfico, definição, como ler, limitações e fonte. */
function Detalhe({ ind, id, a, b, dados, escolher }: { ind: Indicador; id: string; a: Periodo; b: Periodo;
                                                       dados: FeedEconomia; escolher: (id: string) => void }) {
  return (
    <section className="cartao cartao-corpo" aria-labelledby="titulo-detalhe">
      <div className="controles">
        <h2 id="titulo-detalhe">{ind.nome}</h2>
        <label className="so-leitor" htmlFor="escolha-indicador">
          Indicador
        </label>
        <select id="escolha-indicador" className="seletor" value={id} onChange={(e) => escolher(e.target.value)}>
          {dados.grupos.map((g) => (
            <optgroup key={g.id} label={g.nome}>
              {g.indicadores.map((i) => (
                <option key={i} value={i}>
                  {dados.indicadores[i]?.nome}
                </option>
              ))}
            </optgroup>
          ))}
        </select>
      </div>
      <GraficoLinha
        titulo={`${ind.nome}, ${ind.unidade}, série histórica`}
        serie={ind.serie}
        unidade={ind.unidade}
        faixas={[{ ...a, classe: "faixa-periodo-a" }, { ...b, classe: "faixa-periodo-b" }]}
      />
      <div className="legenda">
        <span className="legenda-item">
          <span className="dica-chave faixa-periodo-a" /> {a.rotulo}
        </span>
        <span className="legenda-item">
          <span className="dica-chave faixa-periodo-b" /> {b.rotulo}
        </span>
        <span className="legenda-item">Unidade: {ind.unidade}</span>
      </div>
      <div className="texto-corrido">
        <p>{ind.definicao}</p>
        {ind.leitura && (
          <p>
            <strong>Como ler:</strong> {ind.leitura}
          </p>
        )}
        {ind.limitacoes.length > 0 && (
          <ul>
            {ind.limitacoes.map((l) => (
              <li key={l}>{l}</li>
            ))}
          </ul>
        )}
        <p className="total-detalhe">
          {ind.derivado_de ? (
            <>
              Calculado pelo Lumen a partir de:{" "}
              {ind.derivado_de.map((d) => dados.indicadores[d]?.nome ?? d).join(", ")}.{" "}
            </>
          ) : (
            <>
              Fonte: {ind.fonte_primaria ?? ind.fonte}
              {ind.codigo_sgs && (
                <>
                  {" "}
                  (SGS, série{" "}
                  <a href={ind.url} target="_blank" rel="noreferrer">
                    {ind.codigo_sgs}
                  </a>
                  ){ind.nome_oficial ? `: “${ind.nome_oficial}”` : ""}
                </>
              )}
              .{" "}
            </>
          )}
          Coletado em {instante(ind.coletado_em)}.
          {ind.periodo_parcial_omitido && ` ${periodoCurto(ind.periodo_parcial_omitido)} ainda em curso, fora da série.`}
          {ind.lacunas.length > 0 && ` ${ind.lacunas.length} período(s) sem dado na fonte (não contados como zero).`}
          {ind.ultima_falha && ` A última tentativa de coleta falhou em ${instante(ind.ultima_falha)}.`}
        </p>
      </div>
    </section>
  );
}

/** Uma célula da comparação: nível (início → fim) ou taxa (acumulado e média). */
function Celula({ ind, r, p }: { ind: Indicador; r: Resumo; p: Periodo }) {
  const parcial = r.ateEfetivo < p.ate;
  const cobertura =
    r.observacoes < r.esperadas ? ` · ${r.observacoes} de ${r.esperadas} períodos com dado` : "";
  if (ind.agregacao === "nivel") {
    if (!r.fim) return <span className="situacao-painel">sem dado no período</span>;
    return (
      <>
        <span className="num">
          {r.inicio ? valorNaUnidade(r.inicio.valor, ind.unidade) : "—"} →{" "}
          {valorNaUnidade(r.fim.valor, ind.unidade)}
        </span>
        <span className="total-detalhe">
          {variacaoTexto(r)} ({r.inicio ? periodoCurto(r.inicio.periodo) : "—"} a {periodoCurto(r.fim.periodo)})
          {cobertura}
        </span>
      </>
    );
  }
  return (
    <>
      <span className="num">
        {r.acumulado !== null ? `${valorNaUnidade(r.acumulado, "%")} acumulado` : "acumulado indisponível"}
      </span>
      <span className="total-detalhe">
        média de {valorNaUnidade(r.media, "%")} por {ind.periodicidade === "anual" ? "ano" : "mês"}
        {parcial ? ` · até ${periodoCurto(ind.periodicidade === "anual" ? r.ateEfetivo.slice(0, 4) : r.ateEfetivo)}` : ""}
        {cobertura}
      </span>
    </>
  );
}

/** Escolha de um período: um mandato ou um intervalo de meses. */
function EscolhaPeriodo({ nome, rotulo, p, mudar }: { nome: string; rotulo: string; p: Periodo;
                                                       mudar: (valor: string) => void }) {
  const mandato = MANDATOS.find((m) => m.de === p.de && m.ate === p.ate);
  return (
    <fieldset className="economia-periodo">
      <legend>{rotulo}</legend>
      <select className="seletor" aria-label={`${rotulo}: mandato`} value={mandato ? `${mandato.de}..${mandato.ate}` : ""}
              onChange={(e) => e.target.value && mudar(e.target.value)}>
        <option value="">Intervalo de meses</option>
        {MANDATOS.map((m) => (
          <option key={m.de} value={`${m.de}..${m.ate}`}>
            {m.rotulo}
          </option>
        ))}
      </select>
      <span className="economia-meses">
        <input type="month" className="seletor" aria-label={`${rotulo}: primeiro mês`} value={p.de}
               max={p.ate} onChange={(e) => mesValido(e.target.value) && mudar(`${e.target.value}..${p.ate}`)} />
        <span aria-hidden="true">a</span>
        <input type="month" className="seletor" aria-label={`${rotulo}: último mês`} value={p.ate}
               min={p.de} onChange={(e) => mesValido(e.target.value) && mudar(`${p.de}..${e.target.value}`)} />
      </span>
      <input type="hidden" name={nome} value={`${p.de}..${p.ate}`} />
    </fieldset>
  );
}

/** Dois períodos lado a lado, para todos os indicadores, agrupados. */
function Comparacao({ dados, a, b, mudar }: { dados: FeedEconomia; a: Periodo; b: Periodo;
                                              mudar: (chave: string, valor: string | null) => void }) {
  const linhas = useMemo(
    () =>
      dados.grupos.map((g) => ({
        grupo: g,
        itens: g.indicadores
          .map((id) => ({ id, ind: dados.indicadores[id]! }))
          .filter((x) => x.ind)
          .map((x) => ({ ...x, ra: resumir(x.ind, a), rb: resumir(x.ind, b) })),
      })),
    [dados, a, b],
  );
  return (
    <section className="cartao cartao-corpo" aria-labelledby="titulo-comparacao">
      <h2 id="titulo-comparacao" className="titulo-secao">
        Comparar dois períodos
      </h2>
      <div className="economia-periodos">
        <EscolhaPeriodo nome="a" rotulo="Período A" p={a} mudar={(v) => mudar("a", v)} />
        <EscolhaPeriodo nome="b" rotulo="Período B" p={b} mudar={(v) => mudar("b", v)} />
        <button type="button" className="botao" onClick={() => { mudar("a", null); mudar("b", null); }}>
          Voltar ao padrão
        </button>
      </div>
      <p className="total-detalhe">
        Nos níveis (dívida, resultado em 12 meses, índices), o início é o último valor antes do período e a
        variação é em pontos percentuais. Nas taxas do mês ou do ano (IPCA, INPC, Selic, PIB real), o acumulado
        só aparece com todos os meses do período publicados. Valores em reais são correntes, da época.
      </p>
      <div className="tabela-rolavel economia-tabela">
        <table className="tabela">
          <caption className="so-leitor">
            Indicadores no período A ({a.rotulo}) e no período B ({b.rotulo})
          </caption>
          <thead>
            <tr>
              <th scope="col">Indicador</th>
              <th scope="col">{a.rotulo}</th>
              <th scope="col">{b.rotulo}</th>
            </tr>
          </thead>
          {linhas.map(({ grupo, itens }) => (
            <tbody key={grupo.id}>
              <tr>
                <th scope="colgroup" colSpan={3} className="economia-grupo">
                  {grupo.nome}
                </th>
              </tr>
              {itens.map(({ id, ind, ra, rb }) => (
                <tr key={id}>
                  <th scope="row">
                    <button type="button" className="botao-link" onClick={() => mudar("ind", id)}>
                      {ind.nome}
                    </button>
                    <span className="total-detalhe">{ind.unidade}</span>
                  </th>
                  <td>
                    <Celula ind={ind} r={ra} p={a} />
                  </td>
                  <td>
                    <Celula ind={ind} r={rb} p={b} />
                  </td>
                </tr>
              ))}
            </tbody>
          ))}
        </table>
      </div>
    </section>
  );
}
