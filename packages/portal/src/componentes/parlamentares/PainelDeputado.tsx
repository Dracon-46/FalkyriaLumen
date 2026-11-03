"use client";

/**
 * A página de um deputado federal (ADR-060), pelo id da Câmara (`?id=`): os totais, os votos nominais no Plenário com
 * a votação e a orientação do Governo, as proposições que apresentou e a cota parlamentar, num ano (`?ano=`) ou em
 * todos. São os fatos como a Câmara publica: a página não pontua nem ordena ninguém.
 */

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { BaixarCsv, PrefixoCsv } from "@/componentes/BaixarCsv";
import { Escolha } from "@/componentes/Escolha";
import { ThOrdem } from "@/componentes/ThOrdem";
import { numero, percentual } from "@/lib/formato";
import { normalizar } from "@/lib/busca";
import { type Ordem, ordenar } from "@/lib/ordem";
import { cnpj as formatarCnpj, dataCurta, moeda, moedaCompacta } from "@/lib/paineis";
import {
  carregarDeputado,
  carregarVotacoes,
  cotaDoDeputado,
  cotaPorMes,
  type Deputado,
  fotoDoDeputado,
  paginaNaCamara,
  proposicaoNaCamara,
  totaisDoDeputado,
  urlDaVotacao,
  type Votacao,
  votoPorExtenso,
  votosComVotacoes,
} from "@/lib/parlamentares";
import { GraficoBarras, Numero, Situacao } from "../paineis/Comuns";

const METODO = "https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-060.md";
const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
/** Linhas mostradas antes de "ver todas", nas tabelas longas. */
const INICIAIS = 30;

/** Carregando, o deputado lido (null quando não está no Lumen) ou o erro. */
type Estado = { fase: "carregando" } | { fase: "pronto"; deputado: Deputado | null } | { fase: "erro"; erro: string };

/** A página: lê o deputado e as votações dos anos dele. */
export function PainelDeputado() {
  const params = useSearchParams();
  const router = useRouter();
  const id = params.get("id") ?? "";
  const anoNaUrl = params.get("ano");
  const [estado, setEstado] = useState<Estado>({ fase: "carregando" });
  const [votacoes, setVotacoes] = useState<Record<string, Record<string, Votacao>>>({});

  useEffect(() => {
    const c = new AbortController();
    setEstado({ fase: "carregando" });
    carregarDeputado(id, c.signal)
      .then((deputado) => {
        setEstado({ fase: "pronto", deputado });
        for (const ano of Object.keys(deputado?.anos ?? {})) {
          carregarVotacoes(ano, c.signal).then((v) => setVotacoes((atual) => ({ ...atual, [ano]: v }))).catch(() => undefined);
        }
      })
      .catch((e: Error) => e.name !== "AbortError" && setEstado({ fase: "erro", erro: e.message }));
    return () => c.abort();
  }, [id]);

  if (!id) return <Situacao>Escolha um deputado na <Link href="/parlamentares/">lista dos parlamentares</Link>.</Situacao>;
  if (estado.fase === "carregando") return <Situacao>Carregando…</Situacao>;
  if (estado.fase === "erro") return <Situacao>Não foi possível ler agora ({estado.erro}).</Situacao>;
  const d = estado.deputado;
  if (!d) return <Situacao>Este deputado não está nos dados do Lumen.</Situacao>;
  const anos = Object.keys(d.anos).sort();
  const ano = anoNaUrl && d.anos[anoNaUrl] ? anoNaUrl : null;
  /** Troca o ano na URL, sem rolar a página. */
  const escolherAno = (a: string | null) => {
    const q = new URLSearchParams(params.toString());
    if (a) q.set("ano", a);
    else q.delete("ano");
    router.replace(`/parlamentares/deputado/?${q.toString()}`, { scroll: false });
  };
  const t = totaisDoDeputado(d, ano);
  const periodo = ano ?? (anos.length === 1 ? anos[0] : `${anos[0]} a ${anos[anos.length - 1]}`);

  return (
    <PrefixoCsv.Provider value={["deputado", d.id, ano].filter(Boolean).join("-")}>
      <section className="cartao cartao-corpo deputado-topo">
        <img src={fotoDoDeputado(d.id)} alt={`Foto oficial de ${d.nome}`} width={90} height={120} className="deputado-foto" />
        <div>
          <h2 className="painel-ente">{d.nome}</h2>
          <p>
            Deputado(a) federal · {d.partido}-{d.uf} · legislatura(s) {d.legislaturas.join(" e ")}
            <span className="busca-detalhe"> · <a href={paginaNaCamara(d.id)} target="_blank" rel="noreferrer">página na Câmara</a></span>
          </p>
          <p className="busca-detalhe">
            Em exercício: {d.exercicio.map(([i, f]) => `${dataCurta(i)} a ${f ? dataCurta(f) : "hoje"}`).join("; ") || "sem registro"}
          </p>
        </div>
      </section>
      {anos.length > 1 && (
        <section className="cartao cartao-corpo filtro-periodo" aria-label="Ano">
          <span className="filtro-periodo-titulo">Ano</span>
          <Escolha rotulo="Ano" valor={ano ?? ""} onEscolher={(v) => escolherAno(v || null)}
            opcoes={[{ valor: "", rotulo: `todos (${anos[0]} a ${anos[anos.length - 1]})` }, ...anos.map((a) => ({ valor: a, rotulo: a }))]} />
        </section>
      )}
      <div className="totais">
        <Numero rotulo={`Votos no Plenário, ${periodo}`} valor={numero(t.votos)} detalhe={`${numero(t.sim)} Sim · ${numero(t.nao)} Não`} />
        <Numero rotulo="Presença nas sessões" valor={t.sessoes ? percentual((100 * t.presentes) / t.sessoes) : "—"}
          detalhe={`${numero(t.presentes)} de ${numero(t.sessoes)} em exercício`} />
        <Numero rotulo="Proposições apresentadas" valor={numero(t.proposicoes)} detalhe="PL, PLP, PEC, PDL e PRC" />
        <Numero rotulo="Cota parlamentar" valor={moeda(t.cota)} detalhe="valor reembolsado" />
      </div>
      {anos.length > 1 && <AnoAAno d={d} anos={anos} ano={ano} onAno={escolherAno} />}
      <Votos d={d} ano={ano} votacoes={votacoes} />
      <Proposicoes d={d} ano={ano} contagem={t.contagem} />
      <CotaParlamentar d={d} ano={ano} />
      <p className="busca-detalhe">
        Dados abertos da Câmara dos Deputados: votações nominais do Plenário, presença nas sessões deliberativas do
        Plenário (a presença conta só as sessões realizadas enquanto o deputado estava em exercício), proposições que ele
        apresentou e a cota para o exercício da atividade parlamentar (CEAP). Não medem trabalho em comissões, relatorias
        nem o que não vai a voto nominal. São os fatos como a fonte publica, sem juízo sobre o parlamentar.{" "}
        <a href={METODO} target="_blank" rel="noreferrer">como é montado</a>
      </p>
    </PrefixoCsv.Provider>
  );
}

/** Uma medida do gráfico ano a ano: o rótulo, o valor num ano e os formatos. */
interface Metrica {
  rotulo: string;
  valor: (t: ReturnType<typeof totaisDoDeputado>) => number;
  formatar: (n: number) => string;
  eixo: (n: number) => string;
}

/** As medidas que o gráfico ano a ano oferece. */
const METRICAS: Record<string, Metrica> = {
  presenca: { rotulo: "Presença nas sessões (%)", valor: (t) => (t.sessoes ? (100 * t.presentes) / t.sessoes : 0),
              formatar: (n) => percentual(n), eixo: (n) => `${Math.round(n)}%` },
  votos: { rotulo: "Votos no Plenário", valor: (t) => t.votos, formatar: numero, eixo: numero },
  proposicoes: { rotulo: "Proposições apresentadas", valor: (t) => t.proposicoes, formatar: numero, eixo: numero },
  cota: { rotulo: "Cota parlamentar", valor: (t) => t.cota, formatar: moeda, eixo: moedaCompacta },
};

/** O ano a ano de uma medida, à escolha; clicar numa barra filtra a página por aquele ano (clicar de novo volta). */
function AnoAAno({ d, anos, ano, onAno }: { d: Deputado; anos: string[]; ano: string | null; onAno: (a: string | null) => void }) {
  const [metrica, setMetrica] = useState("presenca");
  const m = METRICAS[metrica] ?? METRICAS.presenca!;
  return (
    <section className="cartao cartao-corpo" aria-labelledby="titulo-ano-a-ano">
      <h2 id="titulo-ano-a-ano" className="titulo-secao">Ano a ano</h2>
      <Escolha rotulo="Medida" valor={metrica} onEscolher={setMetrica}
        opcoes={Object.entries(METRICAS).map(([valor, x]) => ({ valor, rotulo: x.rotulo }))} />
      <GraficoBarras titulo={`${m.rotulo} por ano`} barras={anos.map((a) => ({ rotulo: a, valor: m.valor(totaisDoDeputado(d, a)) }))}
        formatar={m.formatar} formatarEixo={m.eixo} selecionada={ano} onEscolher={(a) => onAno(a === ano ? null : a)} />
      <p className="busca-detalhe">Clique num ano para ver só ele na página; clique de novo para ver todos.</p>
    </section>
  );
}

/** Os votos nominais no Plenário, com a votação, o resultado e se o voto foi igual à orientação do Governo. */
function Votos({ d, ano, votacoes }: { d: Deputado; ano: string | null; votacoes: Record<string, Record<string, Votacao>> }) {
  const [filtro, setFiltro] = useState("");
  const [busca, setBusca] = useState("");
  const [ordem, setOrdem] = useState<Ordem | null>(null);
  const [todas, setTodas] = useState(false);
  const linhas = useMemo(() => votosComVotacoes(d, ano, votacoes), [d, ano, votacoes]);
  const termos = normalizar(busca).split(" ").filter(Boolean);
  const passa = (l: (typeof linhas)[number]) =>
    (!filtro || (filtro === "governo-contra" ? l.comOGoverno === false : l.voto === filtro))
    && termos.every((p) => normalizar(`${l.votacao?.[1] ?? ""} ${l.votacao?.[2] ?? ""} ${l.votacao?.[3] ?? ""}`).includes(p));
  const filtradas = ordenar(linhas.filter(passa), ordem, {
    data: (l) => l.votacao?.[0], proposicao: (l) => l.votacao?.[1], voto: (l) => votoPorExtenso(l.voto),
    governo: (l) => l.votacao?.[8], resultado: (l) => l.votacao?.[4],
  });
  const mostradas = todas ? filtradas : filtradas.slice(0, INICIAIS);
  if (linhas.length === 0) return null;
  return (
    <section className="cartao cartao-corpo" aria-labelledby="titulo-votos">
      <h2 id="titulo-votos" className="titulo-secao">Votos no Plenário</h2>
      <Escolha rotulo="Mostrar" valor={filtro} onEscolher={setFiltro} opcoes={[
        { valor: "", rotulo: "todos os votos" }, { valor: "S", rotulo: "votou Sim" }, { valor: "N", rotulo: "votou Não" },
        { valor: "A", rotulo: "abstenção" }, { valor: "O", rotulo: "obstrução" },
        { valor: "governo-contra", rotulo: "diferente da orientação do Governo" }]} />
      <input className="seletor campo-tabela" placeholder="buscar na proposição (ex.: IBS, PEC 45)" aria-label="Buscar na proposição"
        value={busca} onChange={(e) => setBusca(e.target.value)} />
      <p className="busca-detalhe">{numero(filtradas.length)} de {numero(linhas.length)} votos.</p>
      <div className="tabela-rolavel">
        <table className="tabela">
          <thead>
            <tr>
              <ThOrdem coluna="data" ordem={ordem} onOrdenar={setOrdem}>Data</ThOrdem>
              <ThOrdem coluna="proposicao" ordem={ordem} onOrdenar={setOrdem} texto>Proposição votada</ThOrdem>
              <ThOrdem coluna="voto" ordem={ordem} onOrdenar={setOrdem} texto>Voto</ThOrdem>
              <ThOrdem coluna="governo" ordem={ordem} onOrdenar={setOrdem} texto>Orientação do Governo</ThOrdem>
              <ThOrdem coluna="resultado" ordem={ordem} onOrdenar={setOrdem}>Resultado</ThOrdem>
            </tr>
          </thead>
          <tbody>
            {mostradas.map(({ id, ano: anoDoVoto, voto, votacao: v }) => (
              <tr key={id}>
                <td>{v ? dataCurta(v[0]) : "—"}</td>
                <td>
                  <Link href={urlDaVotacao(anoDoVoto, id)}>{v?.[1] || "Votação"}</Link>{" "}
                  {v?.[2] && <span className="busca-detalhe">· {v[2]}</span>}
                  {v?.[3] && <div className="busca-detalhe">{v[3]}</div>}
                </td>
                <td>{votoPorExtenso(voto)}</td>
                <td>{v?.[8] ?? "—"}</td>
                <td>{v?.[4] === 1 ? "aprovada" : v?.[4] === 0 ? "rejeitada" : "—"}{v ? ` (${numero(v[5])} Sim, ${numero(v[6])} Não)` : ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {filtradas.length > INICIAIS && (
        <button type="button" className="botao-link" onClick={() => setTodas(!todas)}>
          {todas ? `mostrar só as ${INICIAIS} mais recentes` : `ver todos os ${numero(filtradas.length)} votos`}
        </button>
      )}
      <BaixarCsv nome="votos-plenario"
        colunas={["Id da votação", "Data", "Proposição", "Ementa", "Descrição", "Voto", "Orientação do Governo", "Resultado"]}
        linhas={() => filtradas.map(({ id, voto, votacao: v }) => [id, v?.[0] ?? "", v?.[1] ?? "", v?.[2] ?? "", v?.[3] ?? "",
          votoPorExtenso(voto), v?.[8] ?? "", v?.[4] === 1 ? "aprovada" : v?.[4] === 0 ? "rejeitada" : ""])} />
      <p className="busca-detalhe">
        Só as votações nominais do Plenário, em que cada voto é registrado. A orientação do Governo é a que a liderança
        do Governo deu na votação, como a Câmara publica.
      </p>
    </section>
  );
}

/** As proposições que o deputado apresentou como autor, e a contagem de todas por tipo. */
function Proposicoes({ d, ano, contagem }: { d: Deputado; ano: string | null; contagem: Record<string, number> }) {
  const [todas, setTodas] = useState(false);
  const [ordem, setOrdem] = useState<Ordem | null>(null);
  const lista = ordenar(Object.entries(d.anos).filter(([a]) => !ano || a === ano).flatMap(([, a]) => a.autoria)
    .sort((x, y) => y[5].localeCompare(x[5])), ordem, {
    proposicao: (p) => `${p[1]} ${p[3]} ${p[2].padStart(6, "0")}`, ementa: (p) => p[4], data: (p) => p[5], situacao: (p) => p[6],
  });
  const mostradas = todas ? lista : lista.slice(0, INICIAIS);
  const outros = Object.entries(contagem).filter(([tipo]) => !["PL", "PLP", "PEC", "PDL", "PRC"].includes(tipo))
    .sort((a, b) => b[1] - a[1]);
  if (lista.length === 0 && outros.length === 0) return null;
  return (
    <section className="cartao cartao-corpo" aria-labelledby="titulo-proposicoes">
      <h2 id="titulo-proposicoes" className="titulo-secao">Proposições apresentadas</h2>
      {lista.length > 0 && (
        <div className="tabela-rolavel">
          <table className="tabela">
            <thead>
              <tr>
                <ThOrdem coluna="proposicao" ordem={ordem} onOrdenar={setOrdem} texto>Proposição</ThOrdem>
                <ThOrdem coluna="ementa" ordem={ordem} onOrdenar={setOrdem} texto>Ementa</ThOrdem>
                <ThOrdem coluna="data" ordem={ordem} onOrdenar={setOrdem}>Apresentada em</ThOrdem>
                <ThOrdem coluna="situacao" ordem={ordem} onOrdenar={setOrdem} texto>Situação</ThOrdem>
              </tr>
            </thead>
            <tbody>
              {mostradas.map(([pid, tipo, numeroP, anoP, ementa, data, situacao]) => (
                <tr key={pid}>
                  <td><a href={proposicaoNaCamara(pid)} target="_blank" rel="noreferrer">{tipo} {numeroP}/{anoP}</a></td>
                  <td>{ementa}</td>
                  <td>{dataCurta(data)}</td>
                  <td>{situacao ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {lista.length > INICIAIS && (
        <button type="button" className="botao-link" onClick={() => setTodas(!todas)}>
          {todas ? `mostrar só as ${INICIAIS} mais recentes` : `ver todas as ${numero(lista.length)}`}
        </button>
      )}
      {outros.length > 0 && (
        <p className="busca-detalhe">
          Também apresentou: {outros.map(([tipo, n]) => `${numero(n)} ${tipo}`).join(", ")} (requerimentos, emendas,
          pareceres e outros tipos, só contados).
        </p>
      )}
      <BaixarCsv nome="proposicoes"
        colunas={["Id na Câmara", "Tipo", "Número", "Ano", "Ementa", "Apresentada em", "Situação"]}
        linhas={() => lista.map((p) => [...p])} />
      <p className="busca-detalhe">
        Proposições em que o deputado assina como autor, apresentadas no período, com a situação mais recente que a
        Câmara publica. A coautoria conta para cada um dos autores.
      </p>
    </section>
  );
}

/** A cota parlamentar: por categoria, por mês (num ano) e por fornecedor, com a ligação para a página da empresa. */
function CotaParlamentar({ d, ano }: { d: Deputado; ano: string | null }) {
  const [todos, setTodos] = useState(false);
  const [ordemCat, setOrdemCat] = useState<Ordem | null>(null);
  const [ordemForn, setOrdemForn] = useState<Ordem | null>(null);
  const c = cotaDoDeputado(d, ano);
  if (c.categorias.length === 0) return null;
  const meses = ano ? cotaPorMes(d, ano) : [];
  const categorias = ordenar(c.categorias, ordemCat, { categoria: (x) => x[0], valor: (x) => x[1] });
  const fornecedores = ordenar(c.fornecedores, ordemForn, { nome: (f) => f[1] ?? f[0], documentos: (f) => f[2], valor: (f) => f[3] });
  const mostrados = todos ? fornecedores : fornecedores.slice(0, INICIAIS);
  return (
    <section className="cartao cartao-corpo" aria-labelledby="titulo-cota">
      <h2 id="titulo-cota" className="titulo-secao">Cota parlamentar (CEAP)</h2>
      {ano && meses.length > 1 && (
        <GraficoBarras titulo={`Reembolsado por mês em ${ano}`}
          barras={meses.map((m) => ({ rotulo: MESES[Number(m.mes) - 1] ?? m.mes, valor: m.valor }))} formatar={moeda} formatarEixo={moedaCompacta} />
      )}
      <div className="tabela-rolavel">
        <table className="tabela">
          <thead>
            <tr>
              <ThOrdem coluna="categoria" ordem={ordemCat} onOrdenar={setOrdemCat} texto>Categoria</ThOrdem>
              <ThOrdem coluna="valor" ordem={ordemCat} onOrdenar={setOrdemCat} className="n">Valor</ThOrdem>
            </tr>
          </thead>
          <tbody>
            {categorias.map(([categoria, valor]) => (
              <tr key={categoria}>
                <td>{categoria}</td>
                <td className="n">{moeda(valor)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {c.fornecedores.length > 0 && (
        <div className="tabela-rolavel">
          <table className="tabela">
            <thead>
              <tr>
                <ThOrdem coluna="nome" ordem={ordemForn} onOrdenar={setOrdemForn} texto>Fornecedor (pessoa jurídica)</ThOrdem>
                <ThOrdem coluna="documentos" ordem={ordemForn} onOrdenar={setOrdemForn} className="n">Documentos</ThOrdem>
                <ThOrdem coluna="valor" ordem={ordemForn} onOrdenar={setOrdemForn} className="n">Valor</ThOrdem>
              </tr>
            </thead>
            <tbody>
              {mostrados.map(([cnpj, nome, n, valor]) => (
                <tr key={cnpj}>
                  <td>
                    <Link href={`/pessoa-juridica/?cnpj=${cnpj}`}>{nome ?? formatarCnpj(cnpj)}</Link>
                    <div className="busca-detalhe">{formatarCnpj(cnpj)}</div>
                  </td>
                  <td className="n">{numero(n)}</td>
                  <td className="n">{moeda(valor)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {c.fornecedores.length > INICIAIS && (
        <button type="button" className="botao-link" onClick={() => setTodos(!todos)}>
          {todos ? `mostrar só os ${INICIAIS} maiores` : `ver todos os ${numero(c.fornecedores.length)} fornecedores`}
        </button>
      )}
      <BaixarCsv nome="cota-parlamentar-fornecedores" colunas={["CNPJ", "Fornecedor", "Documentos", "Valor (R$)"]}
        linhas={() => c.fornecedores.map(([cnpj, nome, n, valor]) => [formatarCnpj(cnpj), nome ?? "", n, valor])} />
      <p className="busca-detalhe">
        Valor líquido reembolsado, pela data do documento.
        {c.pf[0] > 0 && ` Fornecedores pessoa física, só somados: ${numero(c.pf[0])} documento(s), ${moeda(c.pf[1])}.`}{" "}
        Cada documento, com a nota, está na página do deputado no site da Câmara.
      </p>
    </section>
  );
}
