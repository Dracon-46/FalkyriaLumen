"use client";

/**
 * As votações nominais do Plenário da Câmara (ADR-060): a lista de um ano (`?ano=`), com busca pela proposição, filtros
 * de tipo e resultado e colunas ordenáveis; e a página de uma votação (`?ano=&id=`), com o placar, o voto de cada
 * partido e o de cada deputado, com o partido no dia do voto. São os votos como a Câmara publica.
 */

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { BaixarCsv } from "@/componentes/BaixarCsv";
import { Escolha } from "@/componentes/Escolha";
import { ThOrdem } from "@/componentes/ThOrdem";
import { normalizar } from "@/lib/busca";
import { numero } from "@/lib/formato";
import { type Ordem, ordenar } from "@/lib/ordem";
import { dataCurta } from "@/lib/paineis";
import { NavParlamentares } from "./NavParlamentares";
import {
  type Casa,
  CASAS,
  casaDaUrl,
  carregarIndiceCamara,
  carregarVotacoes,
  carregarVotosDoAno,
  type IndiceCamara,
  placarPorPartido,
  proposicaoNaCamara,
  tipoDaProposicao,
  urlDaVotacao,
  type Votacao,
  type VotoNaVotacao,
  urlDoParlamentar,
  votoPorExtenso,
} from "@/lib/parlamentares";
import { Numero, Situacao } from "../paineis/Comuns";

/** Linhas mostradas antes de "ver todas". */
const INICIAIS = 50;

/** O resultado por extenso. */
const resultado = (v: Votacao) => (v[4] === 1 ? "aprovada" : v[4] === 0 ? "rejeitada" : "—");

/** O que a página leu: o índice dos deputados (nomes e UF), as votações e os votos do ano. */
interface Dados {
  indice: IndiceCamara | null;
  votacoes: Record<string, Votacao>;
  votos: Record<string, VotoNaVotacao[]>;
}

/** A página: a lista do ano ou, com `id`, a votação. */
export function PainelVotacoes() {
  const params = useSearchParams();
  const router = useRouter();
  const [indice, setIndice] = useState<IndiceCamara | null | undefined>(undefined);
  const [dados, setDados] = useState<Dados | null>(null);
  const [erro, setErro] = useState(false);
  const casa = casaDaUrl(params.get("casa"));
  const anos = indice?.anos ?? [];
  const ano = params.get("ano") && anos.includes(params.get("ano")!) ? params.get("ano")! : anos[anos.length - 1] ?? null;
  const id = params.get("id");

  useEffect(() => {
    const c = new AbortController();
    setIndice(undefined);
    carregarIndiceCamara(c.signal, casa).then(setIndice).catch((e: Error) => e.name !== "AbortError" && setErro(true));
    return () => c.abort();
  }, [casa]);

  useEffect(() => {
    if (!ano || !indice) return;
    const c = new AbortController();
    setDados(null);
    Promise.all([carregarVotacoes(ano, c.signal, casa), carregarVotosDoAno(ano, c.signal, casa)])
      .then(([votacoes, votos]) => setDados({ indice, votacoes, votos }))
      .catch((e: Error) => e.name !== "AbortError" && setErro(true));
    return () => c.abort();
  }, [ano, indice, casa]);

  /** Troca parâmetros na URL, sem rolar a página. */
  const mudar = (novos: Record<string, string | null>) => {
    const q = new URLSearchParams(params.toString());
    for (const [k, v] of Object.entries(novos)) {
      if (v) q.set(k, v);
      else q.delete(k);
    }
    router.replace(`/parlamentares/votacoes/?${q.toString()}`, { scroll: false });
  };

  const nav = <NavParlamentares atual="votacoes" />;
  if (erro) return <>{nav}<Situacao>Não foi possível ler as votações agora.</Situacao></>;
  if (indice === undefined || (ano && !dados)) return <>{nav}<Situacao>Carregando…</Situacao></>;
  if (!indice || !ano || !dados) return <>{nav}<Situacao>As votações do {CASAS[casa].nome} ainda não foram publicadas.</Situacao></>;
  if (id) {
    const v = dados.votacoes[id];
    if (!v) return <>{nav}<Situacao>Esta votação não está nos dados de {ano}. <Link href={`/parlamentares/votacoes/?${casa === "senado" ? "casa=senado&" : ""}ano=${ano}`}>Ver as votações do ano</Link>.</Situacao></>;
    return <>{nav}<UmaVotacao id={id} ano={ano} v={v} votos={dados.votos[id] ?? []} indice={indice} casa={casa} /></>;
  }
  return <>{nav}<Lista ano={ano} anos={anos} dados={dados} mudar={mudar} casa={casa} /></>;
}

/** A lista das votações do ano. */
function Lista({ ano, anos, dados, mudar, casa }: { ano: string; anos: string[]; dados: Dados; mudar: (n: Record<string, string | null>) => void; casa: Casa }) {
  const [busca, setBusca] = useState("");
  const [tipo, setTipo] = useState("");
  const [res, setRes] = useState("");
  const [ordem, setOrdem] = useState<Ordem | null>(null);
  const [todas, setTodas] = useState(false);
  const todasDoAno = useMemo(() => Object.entries(dados.votacoes), [dados]);
  const tipos = [...new Set(todasDoAno.map(([, v]) => tipoDaProposicao(v[1])))].sort();
  const termos = normalizar(busca).split(" ").filter(Boolean);
  const linhas = ordenar(todasDoAno.filter(([, v]) =>
    (!tipo || tipoDaProposicao(v[1]) === tipo) && (!res || resultado(v) === res)
    && termos.every((p) => normalizar(`${v[1]} ${v[2]} ${v[3]}`).includes(p))), ordem ?? { coluna: "data", sentido: "desc" }, {
    data: ([, v]) => v[0], proposicao: ([, v]) => v[1], resultado: ([, v]) => resultado(v), sim: ([, v]) => v[5],
    nao: ([, v]) => v[6], governo: ([, v]) => v[8],
  });
  const mostradas = todas ? linhas : linhas.slice(0, INICIAIS);
  return (
    <>
      <section className="cartao cartao-corpo filtro-periodo" aria-label="Filtros">
        <Escolha rotulo="Casa" className="escolha-larga" valor={casa} onEscolher={(v) => mudar({ casa: v === "senado" ? "senado" : null, ano: null, id: null })}
          opcoes={[{ valor: "camara", rotulo: "Câmara dos Deputados" }, { valor: "senado", rotulo: "Senado Federal" }]} />
        <Escolha rotulo="Ano" valor={ano} onEscolher={(v) => mudar({ ano: v, id: null })}
          opcoes={[...anos].reverse().map((a) => ({ valor: a, rotulo: a }))} />
        <Escolha rotulo="Tipo" valor={tipo} onEscolher={setTipo}
          opcoes={[{ valor: "", rotulo: "todos os tipos" }, ...tipos.map((t) => ({ valor: t, rotulo: t }))]} />
        <Escolha rotulo="Resultado" className="escolha-larga" valor={res} onEscolher={setRes}
          opcoes={[{ valor: "", rotulo: "qualquer resultado" }, { valor: "aprovada", rotulo: "aprovada" }, { valor: "rejeitada", rotulo: "rejeitada" }]} />
        <input className="seletor" placeholder="buscar na proposição (ex.: reforma tributária)" aria-label="Buscar na proposição"
          value={busca} onChange={(e) => setBusca(e.target.value)} />
      </section>
      <section className="cartao cartao-corpo" aria-labelledby="titulo-votacoes">
        <h2 id="titulo-votacoes" className="titulo-secao">Votações nominais no Plenário {casa === "senado" ? "do Senado" : "da Câmara"} em {ano}</h2>
        <p>
          {numero(linhas.length)} de {numero(todasDoAno.length)} votações. Clique numa para ver como votou cada deputado e
          cada partido; clique no cabeçalho de uma coluna para ordenar.
        </p>
        <div className="tabela-rolavel">
          <table className="tabela">
            <thead>
              <tr>
                <ThOrdem coluna="data" ordem={ordem ?? { coluna: "data", sentido: "desc" }} onOrdenar={setOrdem}>Data</ThOrdem>
                <ThOrdem coluna="proposicao" ordem={ordem} onOrdenar={setOrdem} texto>Proposição</ThOrdem>
                <ThOrdem coluna="resultado" ordem={ordem} onOrdenar={setOrdem} texto>Resultado</ThOrdem>
                <ThOrdem coluna="sim" ordem={ordem} onOrdenar={setOrdem} className="n">Sim</ThOrdem>
                <ThOrdem coluna="nao" ordem={ordem} onOrdenar={setOrdem} className="n">Não</ThOrdem>
                <ThOrdem coluna="governo" ordem={ordem} onOrdenar={setOrdem} texto>Orientação do Governo</ThOrdem>
              </tr>
            </thead>
            <tbody>
              {mostradas.map(([vid, v]) => (
                <tr key={vid}>
                  <td>{dataCurta(v[0])}</td>
                  <td>
                    <Link href={urlDaVotacao(ano, vid, casa)}>{v[1] || "Votação"}</Link>
                    {v[2] && <span className="busca-detalhe"> · {v[2]}</span>}
                    {v[3] && <div className="busca-detalhe">{v[3]}</div>}
                  </td>
                  <td>{resultado(v)}</td>
                  <td className="n">{numero(v[5])}</td>
                  <td className="n">{numero(v[6])}</td>
                  <td>{v[8] ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {linhas.length > INICIAIS && (
          <button type="button" className="botao-link" onClick={() => setTodas(!todas)}>
            {todas ? `mostrar só as ${INICIAIS} primeiras` : `ver todas as ${numero(linhas.length)}`}
          </button>
        )}
        <BaixarCsv nome={`votacoes-${ano}`} colunas={["Id", "Data", "Proposição", "Ementa", "Descrição", "Resultado", "Sim", "Não", "Outros", "Orientação do Governo"]}
          linhas={() => linhas.map(([vid, v]) => [vid, v[0], v[1], v[2], v[3], resultado(v), v[5], v[6], v[7], v[8] ?? ""])} />
      </section>
    </>
  );
}

/** Uma votação: o placar, o voto por partido e o voto de cada deputado. */
function UmaVotacao({ id, ano, v, votos, indice, casa }: { id: string; ano: string; v: Votacao; votos: VotoNaVotacao[]; indice: IndiceCamara; casa: Casa }) {
  const [ordemP, setOrdemP] = useState<Ordem | null>(null);
  const [ordemD, setOrdemD] = useState<Ordem | null>(null);
  const [filtroVoto, setFiltroVoto] = useState("");
  const [filtroPartido, setFiltroPartido] = useState("");
  const [filtroUf, setFiltroUf] = useState("");
  const nomes = useMemo(() => new Map(indice.deputados.map((d) => [d[0], { nome: d[1], uf: d[3] }])), [indice]);
  const partidos = ordenar(placarPorPartido(votos), ordemP, {
    partido: (p) => p.partido, sim: (p) => p.sim, nao: (p) => p.nao, abstencao: (p) => p.abstencao,
    obstrucao: (p) => p.obstrucao, total: (p) => p.total,
  });
  const deputados = ordenar(votos.filter(([dep, voto, partido]) =>
    (!filtroVoto || voto === filtroVoto) && (!filtroPartido || partido === filtroPartido)
    && (!filtroUf || nomes.get(dep)?.uf === filtroUf)), ordemD ?? { coluna: "nome", sentido: "asc" }, {
    nome: ([dep]) => nomes.get(dep)?.nome ?? dep, partido: ([, , p]) => p, uf: ([dep]) => nomes.get(dep)?.uf, voto: ([, voto]) => votoPorExtenso(voto),
  });
  const ufs = [...new Set(votos.map(([dep]) => nomes.get(dep)?.uf).filter((u): u is string => !!u))].sort();
  const sim = votos.filter((x) => x[1] === "S").length;
  const nao = votos.filter((x) => x[1] === "N").length;
  return (
    <>
      <section className="cartao cartao-corpo">
        <p className="busca-detalhe"><Link href={`/parlamentares/votacoes/?${casa === "senado" ? "casa=senado&" : ""}ano=${ano}`}>votações {casa === "senado" ? "do Senado" : "da Câmara"} em {ano}</Link> · {dataCurta(v[0])}</p>
        <h2 className="painel-ente">
          {v[9] ? <a href={proposicaoNaCamara(v[9], casa)} target="_blank" rel="noreferrer">{v[1] || "Votação"}</a> : v[1] || "Votação"}
        </h2>
        {v[2] && <p>{v[2]}</p>}
        {v[3] && <p className="busca-detalhe">{v[3]}</p>}
      </section>
      <div className="totais">
        <Numero rotulo="Resultado" valor={resultado(v)} detalhe={`votação ${id}`} />
        <Numero rotulo="Sim" valor={numero(v[5])} detalhe={`${numero(sim)} com o voto registrado aqui`} />
        <Numero rotulo="Não" valor={numero(v[6])} detalhe={`${numero(nao)} com o voto registrado aqui`} />
        <Numero rotulo="Orientação do Governo" valor={v[8] ?? "—"} detalhe={`${numero(v[7])} voto(s) de outro tipo`} />
      </div>
      <section className="cartao cartao-corpo" aria-labelledby="titulo-partidos">
        <h2 id="titulo-partidos" className="titulo-secao">Como votou cada partido</h2>
        <div className="tabela-rolavel">
          <table className="tabela">
            <thead>
              <tr>
                <ThOrdem coluna="partido" ordem={ordemP} onOrdenar={setOrdemP} texto>Partido</ThOrdem>
                <ThOrdem coluna="sim" ordem={ordemP} onOrdenar={setOrdemP} className="n">Sim</ThOrdem>
                <ThOrdem coluna="nao" ordem={ordemP} onOrdenar={setOrdemP} className="n">Não</ThOrdem>
                <ThOrdem coluna="abstencao" ordem={ordemP} onOrdenar={setOrdemP} className="n">Abstenção</ThOrdem>
                <ThOrdem coluna="obstrucao" ordem={ordemP} onOrdenar={setOrdemP} className="n">Obstrução</ThOrdem>
                <ThOrdem coluna="total" ordem={ordemP} onOrdenar={setOrdemP} className="n">Total</ThOrdem>
              </tr>
            </thead>
            <tbody>
              {partidos.map((p) => (
                <tr key={p.partido}>
                  <td><button type="button" className="botao-link" onClick={() => setFiltroPartido(p.partido === filtroPartido ? "" : p.partido)}>{p.partido || "sem partido"}</button></td>
                  <td className="n">{numero(p.sim)}</td>
                  <td className="n">{numero(p.nao)}</td>
                  <td className="n">{numero(p.abstencao)}</td>
                  <td className="n">{numero(p.obstrucao)}</td>
                  <td className="n">{numero(p.total)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="busca-detalhe">O partido de cada deputado no dia do voto. Clique num partido para ver só os deputados dele abaixo.</p>
      </section>
      <section className="cartao cartao-corpo" aria-labelledby="titulo-deputados-votacao">
        <h2 id="titulo-deputados-votacao" className="titulo-secao">Como votou cada {casa === "senado" ? "senador" : "deputado"}</h2>
        <div className="filtro-periodo">
          <Escolha rotulo="Voto" valor={filtroVoto} onEscolher={setFiltroVoto} opcoes={[
            { valor: "", rotulo: "todos os votos" }, { valor: "S", rotulo: "Sim" }, { valor: "N", rotulo: "Não" },
            { valor: "A", rotulo: "Abstenção" }, { valor: "O", rotulo: "Obstrução" }]} />
          <Escolha rotulo="Partido" className="escolha-larga" valor={filtroPartido} onEscolher={setFiltroPartido}
            opcoes={[{ valor: "", rotulo: "todos os partidos" }, ...placarPorPartido(votos).map((p) => p.partido).sort().map((p) => ({ valor: p, rotulo: p }))]} />
          <Escolha rotulo="UF" valor={filtroUf} onEscolher={setFiltroUf}
            opcoes={[{ valor: "", rotulo: "todas as UFs" }, ...ufs.map((u) => ({ valor: u, rotulo: u }))]} />
        </div>
        <p className="busca-detalhe">{numero(deputados.length)} de {numero(votos.length)} deputados.</p>
        <div className="tabela-rolavel">
          <table className="tabela">
            <thead>
              <tr>
                <ThOrdem coluna="nome" ordem={ordemD ?? { coluna: "nome", sentido: "asc" }} onOrdenar={setOrdemD} texto>{casa === "senado" ? "Senador" : "Deputado"}</ThOrdem>
                <ThOrdem coluna="partido" ordem={ordemD} onOrdenar={setOrdemD} texto>Partido</ThOrdem>
                <ThOrdem coluna="uf" ordem={ordemD} onOrdenar={setOrdemD} texto>UF</ThOrdem>
                <ThOrdem coluna="voto" ordem={ordemD} onOrdenar={setOrdemD} texto>Voto</ThOrdem>
              </tr>
            </thead>
            <tbody>
              {deputados.map(([dep, voto, partido]) => (
                <tr key={dep}>
                  <td><Link href={urlDoParlamentar(dep, casa, ano)}>{nomes.get(dep)?.nome ?? dep}</Link></td>
                  <td>{partido}</td>
                  <td>{nomes.get(dep)?.uf ?? "—"}</td>
                  <td>{votoPorExtenso(voto)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <BaixarCsv nome={`votacao-${id}`} colunas={["Id do deputado", "Deputado", "Partido no dia", "UF", "Voto"]}
          linhas={() => deputados.map(([dep, voto, partido]) => [dep, nomes.get(dep)?.nome ?? "", partido, nomes.get(dep)?.uf ?? "", votoPorExtenso(voto)])} />
        <p className="busca-detalhe">
          Só quem registrou voto. O placar oficial (acima) pode ter alguns votos a mais, de deputados que não estão no
          cadastro das legislaturas cobertas.
        </p>
      </section>
    </>
  );
}
