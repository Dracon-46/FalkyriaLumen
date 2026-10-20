"use client";

/**
 * Governos municipais (ADR-040 e adendo de 20/10/2026): para o município de `?ente=`, cada mandato de prefeito com
 * quem foi eleito, a população e quanto o município gastou. Ao abrir um mandato, com o que foi gasto, por área
 * (função e subfunção) ou por tipo de gasto (natureza e elemento), a comparação com outro mandato e os links do
 * mandato nas outras abas.
 *
 * Os filtros ficam na URL, para o link abrir igual: `ver` (o total gasto, padrão, ou `habitante`), `valores`
 * (`reais`, corrigidos pelo IPCA, padrão, ou `epoca`), `mandato` e `comparar` (o ano da eleição) e `abertura`
 * (`funcao`, padrão, ou `natureza`). Lido sob demanda das fontes (`lib/governos.ts` e `lib/gastos.ts`); como a
 * comparação de presidentes, mostra o que foi registrado, não o que causou a diferença.
 */

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Fragment, useEffect, useMemo, useState } from "react";
import { Escolha } from "@/componentes/Escolha";
import { LigacoesDoEnte } from "@/componentes/Ligacoes";
import { BuscaEnte } from "@/componentes/paineis/Comuns";
import { numero, percentual } from "@/lib/formato";
import { carregarEconomia } from "@/lib/economia";
import { type Abertura, type LinhaGasto, type SomaGastos, somarAberturas, variacao } from "@/lib/gastos";
import {
  anoBase,
  anosMunicipaisComDespesa,
  carregarMunicipio,
  carregarNatureza,
  type DadosMunicipio,
  emReaisDe,
  ipcaMedioAnual,
  type Mandato,
  PRIMEIRO_ANO_DCA,
  populacaoPorAno,
  quemGovernou,
  type ResumoMandato,
  resumirMandatos,
  urlDcaNaFonte,
  urlPopulacao,
} from "@/lib/governos";
import { carregarEntes, type EnteBusca, moeda, moedaCompacta, tipoDoCodigo } from "@/lib/paineis";

const METODO = "https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-040.md";
/** O primeiro ano com contratações no painel do Lumen (o PNCP coletado). */
const PRIMEIRO_ANO_CONTRATACOES = 2026;
/** As funções do ano a ano, pelo código da classificação funcional. */
const FUNCOES_DO_ANO = [["10", "Saúde"], ["12", "Educação"], ["08", "Assistência social"], ["15", "Urbanismo"]];

/** O que a tela mostra: o total gasto ou o gasto por habitante. */
type Medida = "total" | "habitante";
/** Os valores: corrigidos pelo IPCA (reais do ano-base) ou da época. */
type Valores = "reais" | "epoca";
/** A abertura de com o que foi gasto: por área (função) ou por tipo de gasto (natureza). */
type TipoAbertura = "funcao" | "natureza";

/** O que a URL pede: medida, valores, mandato aberto, mandato comparado e abertura. */
interface Opcoes {
  medida: Medida;
  valores: Valores;
  mandato: number | null;
  comparar: number | null;
  abertura: TipoAbertura;
}

/** As opções a partir da URL; valor fora do esperado vira o padrão. */
function lerOpcoes(params: { get(chave: string): string | null }): Opcoes {
  const ano = (chave: string) => {
    const v = params.get(chave);
    return v && /^\d{4}$/.test(v) ? Number(v) : null;
  };
  return {
    medida: params.get("ver") === "habitante" ? "habitante" : "total",
    valores: params.get("valores") === "epoca" ? "epoca" : "reais",
    mandato: ano("mandato"),
    comparar: ano("comparar"),
    abertura: params.get("abertura") === "natureza" ? "natureza" : "funcao",
  };
}

/** Os anos de um mandato, como texto. */
const anosDo = (m: Mandato) => Array.from({ length: m.ate - m.de + 1 }, (_, i) => String(m.de + i));

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
  const opcoes = lerOpcoes(params);
  const [estado, setEstado] = useState<Estado>({ fase: "vazio" });

  /** Troca parâmetros da URL (nulo apaga), sem rolar a página. */
  const mudar = (troca: Record<string, string | null>) => {
    const p = new URLSearchParams(params.toString());
    for (const [chave, valor] of Object.entries(troca)) {
      if (valor === null) p.delete(chave);
      else p.set(chave, valor);
    }
    router.replace(`/economia/municipio/?${p.toString()}`, { scroll: false });
  };

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
            Quanto o município gastou em cada mandato de prefeito, e com o quê.{" "}
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
      {estado.fase === "pronto" && <Municipio {...estado} opcoes={opcoes} mudar={mudar} />}
    </div>
  );
}

/** A conversão de cada ano para o que a tela mostra: reais de `base` (ou da época), no total ou por habitante. */
function conversor(medida: Medida, valores: Valores, medias: Map<string, number>, base: string | null,
  populacao: Map<string, number>): (valor: number, ano: string) => number | null {
  return (valor, ano) => {
    const reais = valores === "reais" ? (base ? emReaisDe(valor, ano, base, medias) : null) : valor;
    if (reais === null || medida === "total") return reais;
    const pop = populacao.get(ano);
    return pop ? reais / pop : null;
  };
}

/** A natureza de cada ano lido: a abertura, `null` (ano não entregue) ou "erro". */
type Natureza = Map<string, Abertura | null | "erro">;

/** O município lido, com as opções da URL e a função que as troca. */
type PropsMunicipio = Extract<Estado, { fase: "pronto" }> & { opcoes: Opcoes; mudar: (t: Record<string, string | null>) => void };

/** Os filtros, os mandatos e o mandato aberto do município lido. */
function Municipio({ ente, dados, medias, base, opcoes, mudar }: PropsMunicipio) {
  const valores: Valores = base ? opcoes.valores : "epoca";
  const populacao = useMemo(() => populacaoPorAno(dados.estimativas, dados.censo2022), [dados]);
  const resumos = useMemo(() => {
    const anos = anosMunicipaisComDespesa([...dados.despesas.keys()].sort(), populacao, dados.despesas, medias, base);
    return resumirMandatos(dados.mandatos, dados.estimativas, anos).reverse();
  }, [dados, populacao, medias, base]);
  const conv = useMemo(() => conversor(opcoes.medida, valores, medias, base, populacao),
    [opcoes.medida, valores, medias, base, populacao]);
  const somas = useMemo(() => new Map(resumos.map((r) =>
    [r.mandato.eleicao, somarAberturas(anosDo(r.mandato), dados.contas, conv)] as const)), [resumos, dados, conv]);
  const comContas = resumos.filter((r) => (somas.get(r.mandato.eleicao)?.anos.length ?? 0) > 0);
  const aberto = resumos.find((r) => r.mandato.eleicao === opcoes.mandato) ?? comContas[0] ?? null;
  const comparado = opcoes.comparar !== null && opcoes.comparar !== aberto?.mandato.eleicao
    ? resumos.find((r) => r.mandato.eleicao === opcoes.comparar) ?? null : null;

  // A despesa por natureza vem sob demanda: só os anos dos mandatos abertos, quando a abertura é por tipo de gasto
  const [natureza, setNatureza] = useState<Natureza>(new Map());
  useEffect(() => setNatureza(new Map()), [ente.codigo]);
  const pedidos = opcoes.abertura !== "natureza" ? [] :
    [aberto, comparado].flatMap((r) => (r ? anosDo(r.mandato) : []))
      .filter((ano) => dados.contas.get(ano) && !natureza.has(ano));
  const chavePedidos = pedidos.join(",");
  useEffect(() => {
    if (!chavePedidos) return;
    const c = new AbortController();
    for (const ano of chavePedidos.split(",")) {
      carregarNatureza(ente.codigo, Number(ano), c.signal)
        .then((a) => setNatureza((m) => new Map(m).set(ano, a)))
        .catch((e: Error) => {
          if (e.name !== "AbortError") setNatureza((m) => new Map(m).set(ano, "erro"));
        });
    }
    return () => c.abort();
  }, [chavePedidos, ente.codigo]);

  const fmt = opcoes.medida === "total" ? moedaCompacta : moeda;
  const unidade = `${opcoes.medida === "habitante" ? "por habitante, " : ""}${valores === "reais" ? `em R$ de ${base}` : "em R$ da época"}`;

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

      <section className="cartao cartao-corpo filtro-periodo" aria-label="Filtros">
        <span className="filtro-periodo-titulo">Mostrar</span>
        <span className="filtro-periodo-atalhos">
          <button type="button" className="botao" aria-pressed={opcoes.medida === "total"}
            onClick={() => mudar({ ver: null })}>
            Total gasto
          </button>
          <button type="button" className="botao" aria-pressed={opcoes.medida === "habitante"}
            onClick={() => mudar({ ver: "habitante" })}>
            Por habitante
          </button>
        </span>
        <span className="filtro-periodo-titulo">Valores</span>
        <span className="filtro-periodo-atalhos">
          <button type="button" className="botao" aria-pressed={valores === "reais"} disabled={!base}
            onClick={() => mudar({ valores: null })}>
            Corrigidos pela inflação{base ? ` (R$ de ${base})` : ""}
          </button>
          <button type="button" className="botao" aria-pressed={valores === "epoca"}
            onClick={() => mudar({ valores: "epoca" })}>
            Da época
          </button>
        </span>
      </section>

      <section className="cartao cartao-corpo" aria-labelledby="titulo-mandatos">
        <h2 id="titulo-mandatos" className="titulo-secao">Mandato a mandato</h2>
        {resumos.length === 0 ? (
          <p className="busca-detalhe">Nenhuma eleição municipal no calendário até agora.</p>
        ) : (
          <div className="tabela-rolavel">
            <table className="tabela">
              <thead>
                <tr>
                  <th>Mandato</th>
                  <th>População</th>
                  <th className="n">Gasto no mandato</th>
                  <th className="n">Média por ano</th>
                  <th>
                    <span className="so-leitor">Abrir</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {resumos.map((r) => (
                  <LinhaMandato key={r.mandato.eleicao} resumo={r} soma={somas.get(r.mandato.eleicao)!} fmt={fmt}
                    aberto={r.mandato.eleicao === aberto?.mandato.eleicao}
                    onAbrir={() => mudar({ mandato: String(r.mandato.eleicao) })} />
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="busca-detalhe">Valores {unidade}. Despesa liquidada nas contas anuais, sem as intraorçamentárias.</p>
      </section>

      {aberto && (
        <DetalheMandato codigo={ente.codigo} aberto={aberto} comparado={comparado} opcoes={opcoes}
          somaFuncao={[somas.get(aberto.mandato.eleicao)!, comparado ? somas.get(comparado.mandato.eleicao)! : null]}
          natureza={natureza} conv={conv} fmt={fmt} unidade={unidade} opcoesComparar={comContas} mudar={mudar} />
      )}

      <AnoAAno contas={dados.contas} conv={conv} fmt={fmt} populacao={populacao} unidade={unidade} />

      <LigacoesDoEnte codigo={ente.codigo} atual="governos" />

      <section className="cartao cartao-corpo">
        <h2 className="titulo-secao">Fontes e cuidados</h2>
        <ul className="busca-detalhe">
          <li>
            Prefeitos: resultados do TSE publicados na aba{" "}
            <Link href={`/eleicoes/?a=mu-${ente.codigo}`}>Eleições</Link>; o eleito do 2º turno vem do 2º turno.
            Eleições suplementares (depois de cassação ou anulação) não estão nos dados.
          </li>
          <li>
            Despesa: contas anuais entregues ao Tesouro (DCA), despesa liquidada sem as intraorçamentárias, de{" "}
            {PRIMEIRO_ANO_DCA} em diante. Por área, o Anexo I-E (funções e subfunções); por tipo de gasto, o Anexo
            I-D (natureza e elemento). Os dois somam o mesmo total. Corrigida pelo IPCA médio de cada ano, quando
            escolhido.
          </li>
          <li>
            Por habitante:{" "}
            <a href={urlPopulacao(ente.codigo)} target="_blank" rel="noreferrer">
              estimativas do IBGE
            </a>{" "}
            (tabela 6579) e, em 2022 e 2023, o Censo 2022. As estimativas de antes do Censo 2022 vêm de outro método
            e, em muitos municípios, previam mais gente do que o censo contou.
          </li>
        </ul>
      </section>
    </>
  );
}

/** Uma linha da tabela de mandatos. */
function LinhaMandato({ resumo: r, soma, fmt, aberto, onAbrir }: { resumo: ResumoMandato; soma: SomaGastos;
  fmt: (v: number | null | undefined) => string; aberto: boolean; onAbrir: () => void }) {
  const n = soma.anos.length;
  return (
    <tr className={aberto ? "linha-aberta" : undefined}>
      <td>
        {r.mandato.de}–{r.mandato.ate}
        <div className="busca-detalhe">
          {quemGovernou(r.mandato)}
          {r.mandato.turno === 2 ? " · 2º turno" : ""}
        </div>
      </td>
      <td>
        {r.populacaoInicio ? numero(r.populacaoInicio[1]) : "—"} → {r.populacaoFim ? numero(r.populacaoFim[1]) : "—"}
        <div className="busca-detalhe">
          {r.quebraPopulacao
            ? `variação não calculada: mudança de método em ${r.quebraPopulacao}`
            : r.variacaoPopulacao !== null
              ? `${r.variacaoPopulacao > 0 ? "+" : ""}${percentual(r.variacaoPopulacao)}`
              : ""}
        </div>
      </td>
      <td className="n">
        {n ? fmt(soma.total) : "—"}
        <div className="busca-detalhe">
          {n
            ? `${n} de ${r.mandato.ate - r.mandato.de + 1} anos com contas`
            : r.mandato.ate < PRIMEIRO_ANO_DCA
              ? `contas anuais só de ${PRIMEIRO_ANO_DCA} em diante`
              : "contas ainda não entregues"}
        </div>
      </td>
      <td className="n">{n ? fmt(soma.total / n) : "—"}</td>
      <td>
        {n > 0 && (
          <button type="button" className="botao-link" aria-pressed={aberto} onClick={onAbrir}>
            {aberto ? "aberto abaixo" : "com o que foi gasto ›"}
          </button>
        )}
      </td>
    </tr>
  );
}

/** O mandato aberto: com o que foi gasto, a comparação com outro mandato e os links nas outras abas. */
function DetalheMandato({ codigo, aberto, comparado, opcoes, somaFuncao, natureza, conv, fmt, unidade,
  opcoesComparar, mudar }: {
  codigo: string;
  aberto: ResumoMandato;
  comparado: ResumoMandato | null;
  opcoes: Opcoes;
  somaFuncao: [SomaGastos, SomaGastos | null];
  natureza: Natureza;
  conv: (valor: number, ano: string) => number | null;
  fmt: (v: number | null | undefined) => string;
  unidade: string;
  opcoesComparar: ResumoMandato[];
  mudar: (t: Record<string, string | null>) => void;
}) {
  const m = aberto.mandato;
  const porNatureza = opcoes.abertura === "natureza";
  const anosPedidos = [aberto, comparado].flatMap((r) => (r ? anosDo(r.mandato) : []));
  const lidos = new Map([...natureza].map(([ano, a]) => [ano, a === "erro" ? undefined : a] as const));
  const faltando = porNatureza ? anosPedidos.filter((ano) => !natureza.has(ano) && somaFuncao.some((s) => s?.anos.includes(ano))) : [];
  const comErro = porNatureza ? anosPedidos.filter((ano) => natureza.get(ano) === "erro") : [];
  const [a, b] = porNatureza
    ? [somarAberturas(anosDo(m), lidos, conv), comparado ? somarAberturas(anosDo(comparado.mandato), lidos, conv) : null]
    : somaFuncao;
  const rotulo = (r: ResumoMandato) => `${r.mandato.de}–${r.mandato.ate}`;
  const eleicao = `${m.eleicao}-${m.turno === 2 ? "2t" : "1t"}-municipal`;
  const opcoesC = [{ valor: "", rotulo: "Nenhum" },
    ...opcoesComparar.filter((r) => r.mandato.eleicao !== m.eleicao)
      .map((r) => ({ valor: String(r.mandato.eleicao), rotulo: `${rotulo(r)} · ${quemGovernou(r.mandato)}` }))];

  return (
    <section className="cartao cartao-corpo" aria-labelledby="titulo-gasto" id="com-o-que-foi-gasto">
      <h2 id="titulo-gasto" className="titulo-secao">
        Com o que foi gasto · {rotulo(aberto)} · {quemGovernou(m)}
      </h2>
      <div className="filtro-periodo gasto-controles">
        <span className="filtro-periodo-titulo">Abrir por</span>
        <span className="filtro-periodo-atalhos">
          <button type="button" className="botao" aria-pressed={!porNatureza} onClick={() => mudar({ abertura: null })}>
            Área (saúde, educação…)
          </button>
          <button type="button" className="botao" aria-pressed={porNatureza}
            onClick={() => mudar({ abertura: "natureza" })}>
            Tipo de gasto (pessoal, obras…)
          </button>
        </span>
        <span className="filtro-periodo-titulo">Comparar com</span>
        <Escolha rotulo="Comparar com o mandato" opcoes={opcoesC} valor={comparado ? String(comparado.mandato.eleicao) : ""}
          onEscolher={(v) => mudar({ comparar: v || null, mandato: String(m.eleicao) })} />
      </div>
      {faltando.length > 0 && <p className="busca-detalhe">Lendo as contas por tipo de gasto ({faltando.join(", ")})…</p>}
      {comErro.length > 0 && <p className="busca-detalhe">Não foi possível ler agora o tipo de gasto de {comErro.join(", ")}.</p>}
      {a.anos.length === 0 && faltando.length === 0 ? (
        <p className="busca-detalhe">Sem contas deste mandato nesta abertura.</p>
      ) : (
        <TabelaGastos a={a} b={b} rotuloA={rotulo(aberto)} rotuloB={comparado ? rotulo(comparado) : ""} fmt={fmt}
          coluna={porNatureza ? "Tipo de gasto" : "Área"} />
      )}
      <p className="busca-detalhe">
        Valores {unidade}, somados nos anos do mandato com contas ({a.anos.join(", ") || "nenhum"}
        {b ? `; no outro mandato, ${b.anos.join(", ") || "nenhum"}` : ""}).{" "}
        {porNatureza
          ? "Tipo de gasto: grupos de natureza da despesa (Anexo I-D); clique num grupo para ver os elementos."
          : "Área: funções da despesa (Anexo I-E); clique numa função para ver as subfunções."}
        {b ? " Mandatos com números diferentes de anos com contas se comparam pela média por ano." : ""}
      </p>

      <h3 className="modal-subtitulo">Este mandato nas outras abas</h3>
      <ul className="busca-detalhe">
        {m.publicado && (
          <li>
            <Link href={`/eleicoes/?e=${eleicao}&c=prefeito&a=mu-${codigo}`}>Resultado da eleição de {m.eleicao}</Link>{" "}
            (prefeito{m.turno === 2 ? ", 2º turno" : ""})
          </li>
        )}
        <li>
          {m.ate >= PRIMEIRO_ANO_CONTRATACOES ? (
            <>
              <Link href={`/contratacoes/?ente=${codigo}&de=${Math.max(m.de, PRIMEIRO_ANO_CONTRATACOES)}-01`}>
                Contratações publicadas no PNCP neste mandato
              </Link>{" "}
              (o Lumen as tem desde janeiro de {PRIMEIRO_ANO_CONTRATACOES})
            </>
          ) : (
            <>
              Contratações do PNCP: o Lumen as tem desde janeiro de {PRIMEIRO_ANO_CONTRATACOES}, depois deste mandato
              (<Link href={`/contratacoes/?ente=${codigo}`}>as do município</Link>).
            </>
          )}
        </li>
        <li>
          <Link href={`/conformidade/?ente=${codigo}`}>Conformidade</Link>: entregas fiscais no prazo, grupo de pares e
          despesa com pessoal
        </li>
        {a.anos.length > 0 && (
          <li>
            Contas anuais no SICONFI ({porNatureza ? "Anexo I-D" : "Anexo I-E"}):{" "}
            {a.anos.map((ano, i) => (
              <Fragment key={ano}>
                {i > 0 && " · "}
                <a href={urlDcaNaFonte(codigo, Number(ano), porNatureza ? "I-D" : "I-E")} target="_blank"
                  rel="noreferrer">
                  {ano}
                </a>
              </Fragment>
            ))}
          </li>
        )}
      </ul>
    </section>
  );
}

/** Uma linha das duas somas lado a lado (a de um dos mandatos pode faltar). */
interface LinhaDupla {
  codigo: string;
  nome: string;
  a: LinhaGasto | null;
  b: LinhaGasto | null;
  filhos: LinhaDupla[];
}

/** Junta as linhas das duas somas pelo código, na ordem da primeira e, depois, as que só a segunda tem. */
function juntar(as: LinhaGasto[], bs: LinhaGasto[]): LinhaDupla[] {
  const porCodigo = new Map(bs.map((l) => [l.codigo, l]));
  const saida: LinhaDupla[] = as.map((a) => {
    const b = porCodigo.get(a.codigo) ?? null;
    porCodigo.delete(a.codigo);
    return { codigo: a.codigo, nome: a.nome, a, b, filhos: juntar(a.filhos, b?.filhos ?? []) };
  });
  for (const b of porCodigo.values()) saida.push({ codigo: b.codigo, nome: b.nome, a: null, b, filhos: juntar([], b.filhos) });
  return saida;
}

/** A tabela de com o que foi gasto: uma soma (com os anos) ou duas lado a lado; as linhas abrem os filhos. */
function TabelaGastos({ a, b, rotuloA, rotuloB, fmt, coluna }: { a: SomaGastos; b: SomaGastos | null;
  rotuloA: string; rotuloB: string; fmt: (v: number | null | undefined) => string; coluna: string }) {
  const [abertos, setAbertos] = useState<Set<string>>(new Set());
  const alternar = (codigo: string) => setAbertos((s) => {
    const n = new Set(s);
    if (n.has(codigo)) n.delete(codigo);
    else n.add(codigo);
    return n;
  });
  const linhas = juntar(a.linhas, b?.linhas ?? []);
  const media = (s: SomaGastos | null, l: LinhaGasto | null) => (s && s.anos.length && l ? l.total / s.anos.length : null);

  const celulas = (l: LinhaDupla) => b ? (
    <>
      <td className="n">{fmt(l.a?.total ?? 0)}</td>
      <td className="n">{fmt(media(a, l.a) ?? 0)}</td>
      <td className="n">{fmt(l.b?.total ?? 0)}</td>
      <td className="n">{fmt(media(b, l.b) ?? 0)}</td>
      <td className="n">{formatarVariacao(variacao(media(a, l.a) ?? 0, media(b, l.b) ?? 0))}</td>
    </>
  ) : (
    <>
      <td className="n">{fmt(l.a?.total ?? 0)}</td>
      <td className="n">{a.total ? percentual(((l.a?.total ?? 0) / a.total) * 100) : "—"}</td>
      {a.anos.map((ano) => (
        <td key={ano} className="n">
          {fmt(l.a?.porAno[ano] ?? 0)}
        </td>
      ))}
    </>
  );

  const linhaTotal: LinhaDupla = {
    codigo: "total", nome: "Total",
    a: { codigo: "total", nome: "Total", total: a.total, porAno: {}, filhos: [] },
    b: b ? { codigo: "total", nome: "Total", total: b.total, porAno: {}, filhos: [] } : null, filhos: [],
  };
  const porAnoTotal = (ano: string) => a.linhas.reduce((s, l) => s + (l.porAno[ano] ?? 0), 0);

  return (
    <div className="tabela-rolavel">
      <table className="tabela tabela-gastos">
        <thead>
          <tr>
            <th>{coluna}</th>
            {b ? (
              <>
                <th className="n">{rotuloA}: total</th>
                <th className="n">média por ano</th>
                <th className="n">{rotuloB}: total</th>
                <th className="n">média por ano</th>
                <th className="n">Variação da média</th>
              </>
            ) : (
              <>
                <th className="n">Total no mandato</th>
                <th className="n">% do total</th>
                {a.anos.map((ano) => (
                  <th key={ano} className="n">
                    {ano}
                  </th>
                ))}
              </>
            )}
          </tr>
        </thead>
        <tbody>
          <tr className="linha-total">
            <td>Total</td>
            {b ? celulas(linhaTotal) : (
              <>
                <td className="n">{fmt(a.total)}</td>
                <td className="n">{a.total ? percentual(100) : "—"}</td>
                {a.anos.map((ano) => (
                  <td key={ano} className="n">
                    {fmt(porAnoTotal(ano))}
                  </td>
                ))}
              </>
            )}
          </tr>
          {linhas.map((l) => (
            <Fragment key={l.codigo}>
              <tr>
                <td>
                  {l.filhos.length > 0 ? (
                    <button type="button" className="botao-link gasto-abrir" aria-expanded={abertos.has(l.codigo)}
                      onClick={() => alternar(l.codigo)}>
                      <span aria-hidden="true">{abertos.has(l.codigo) ? "▾" : "▸"}</span> {l.nome}
                    </button>
                  ) : (
                    l.nome
                  )}
                </td>
                {celulas(l)}
              </tr>
              {abertos.has(l.codigo) &&
                l.filhos.map((f) => (
                  <tr key={f.codigo} className="linha-filha">
                    <td>{f.nome}</td>
                    {celulas(f)}
                  </tr>
                ))}
            </Fragment>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** "+12,30%", "−4,10%" ou "—". */
function formatarVariacao(v: number | null): string {
  if (v === null) return "—";
  return `${v > 0 ? "+" : v < 0 ? "−" : ""}${percentual(Math.abs(v))}`;
}

/** O ano a ano: a despesa total e quatro áreas, na medida e nos valores escolhidos. */
function AnoAAno({ contas, conv, fmt, populacao, unidade }: { contas: Map<string, Abertura | null>;
  conv: (valor: number, ano: string) => number | null; fmt: (v: number | null | undefined) => string;
  populacao: Map<string, number>; unidade: string }) {
  const anos = [...contas.keys()].sort().reverse();
  return (
    <details className="cartao cartao-corpo">
      <summary className="titulo-secao">Ano a ano</summary>
      <div className="tabela-rolavel">
        <table className="tabela">
          <thead>
            <tr>
              <th>Ano</th>
              <th className="n">População</th>
              <th className="n">Despesa total</th>
              {FUNCOES_DO_ANO.map(([codigo, nome]) => (
                <th key={codigo} className="n">
                  {nome}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {anos.map((ano) => {
              const c = contas.get(ano);
              const valor = (v: number | undefined) => (c && v !== undefined ? conv(v, ano) : null);
              return (
                <tr key={ano}>
                  <td>{ano}</td>
                  <td className="n">{numero(populacao.get(ano) ?? null)}</td>
                  <td className="n">{c ? fmt(valor(c.total)) : "contas não entregues"}</td>
                  {FUNCOES_DO_ANO.map(([codigo]) => (
                    <td key={codigo} className="n">
                      {c ? fmt(valor(c.valores[codigo!] ?? 0)) : "—"}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="busca-detalhe">Valores {unidade}.</p>
    </details>
  );
}
