"use client";

/**
 * A lista dos parlamentares (ADR-060): por enquanto, os deputados federais das duas últimas legislaturas, com a busca
 * pelo nome e os filtros de UF e partido, que ficam na URL (`?uf=`, `?partido=`, `?busca=`). Cada nome abre a página
 * do deputado. A lista mostra os totais como a fonte publica, em ordem alfabética, sem ranking.
 */

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { BaixarCsv } from "@/componentes/BaixarCsv";
import { Escolha } from "@/componentes/Escolha";
import { numero, percentual } from "@/lib/formato";
import { moeda } from "@/lib/paineis";
import { carregarIndiceCamara, filtrarDeputados, type IndiceCamara } from "@/lib/parlamentares";
import { Situacao } from "../paineis/Comuns";

/** Linhas mostradas antes de "ver todos". */
const INICIAIS = 60;
const METODO = "https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-060.md";

/** Carregando, o índice lido (null quando ainda não foi publicado) ou o erro. */
type Estado = { fase: "carregando" } | { fase: "pronto"; indice: IndiceCamara | null } | { fase: "erro" };

/** A página da lista: os filtros e a tabela dos deputados. */
export function PainelParlamentares() {
  const params = useSearchParams();
  const router = useRouter();
  const [estado, setEstado] = useState<Estado>({ fase: "carregando" });
  const [todos, setTodos] = useState(false);
  const uf = params.get("uf")?.toUpperCase() ?? null;
  const partido = params.get("partido");
  const termo = params.get("busca") ?? "";
  const [texto, setTexto] = useState(termo);

  useEffect(() => {
    const c = new AbortController();
    carregarIndiceCamara(c.signal)
      .then((indice) => setEstado({ fase: "pronto", indice }))
      .catch((e: Error) => e.name !== "AbortError" && setEstado({ fase: "erro" }));
    return () => c.abort();
  }, []);

  /** Troca um filtro na URL, sem rolar a página. */
  const mudar = (chave: string, valor: string | null) => {
    const q = new URLSearchParams(params.toString());
    if (valor) q.set(chave, valor);
    else q.delete(chave);
    router.replace(`/parlamentares/?${q.toString()}`, { scroll: false });
  };

  const indice = estado.fase === "pronto" ? estado.indice : null;
  const linhas = useMemo(() => (indice ? filtrarDeputados(indice.deputados, { termo, uf, partido }) : []),
    [indice, termo, uf, partido]);
  if (estado.fase === "carregando") return <Situacao>Carregando…</Situacao>;
  if (estado.fase === "erro") return <Situacao>Não foi possível ler os parlamentares agora.</Situacao>;
  if (!indice) return <Situacao>Os parlamentares ainda não foram publicados.</Situacao>;
  const ufs = [...new Set(indice.deputados.map((d) => d[3]))].sort();
  const partidos = [...new Set(indice.deputados.map((d) => d[2]))].sort();
  const mostradas = todos ? linhas : linhas.slice(0, INICIAIS);
  const anos = indice.anos;
  const periodo = anos.length === 1 ? `em ${anos[0]}` : `de ${anos[0]} a ${anos[anos.length - 1]}`;

  return (
    <>
      <form className="cartao cartao-corpo filtro-periodo" aria-label="Filtros"
        onSubmit={(e) => { e.preventDefault(); mudar("busca", texto.trim() || null); }}>
        <label className="filtro-periodo-titulo" htmlFor="busca-parlamentar">Nome</label>
        <input id="busca-parlamentar" className="seletor" placeholder="parte do nome" value={texto}
          onChange={(e) => setTexto(e.target.value)} />
        <button type="submit" className="botao">Buscar</button>
        <Escolha rotulo="UF" valor={uf ?? ""} onEscolher={(v) => mudar("uf", v || null)}
          opcoes={[{ valor: "", rotulo: "todas as UFs" }, ...ufs.map((u) => ({ valor: u, rotulo: u }))]} />
        <Escolha rotulo="Partido" valor={partido ?? ""} onEscolher={(v) => mudar("partido", v || null)}
          opcoes={[{ valor: "", rotulo: "todos os partidos" }, ...partidos.map((p) => ({ valor: p, rotulo: p }))]} />
      </form>
      <section className="cartao cartao-corpo" aria-labelledby="titulo-deputados">
        <h2 id="titulo-deputados" className="titulo-secao">Deputados federais</h2>
        <p>
          {numero(linhas.length)} deputado(s) que estiveram em exercício {periodo}, em ordem
          alfabética. O partido e a UF são os mais recentes.
        </p>
        <div className="tabela-rolavel">
          <table className="tabela">
            <thead>
              <tr>
                <th>Deputado</th>
                <th>Partido</th>
                <th>UF</th>
                <th className="n">Votos no Plenário</th>
                <th className="n">Presença nas sessões</th>
                <th className="n">Proposições</th>
                <th className="n">Cota parlamentar</th>
              </tr>
            </thead>
            <tbody>
              {mostradas.map(([id, nome, p, u, , votos, proposicoes, presentes, sessoes, cota]) => (
                <tr key={id}>
                  <td><Link href={`/parlamentares/deputado/?id=${id}`}>{nome}</Link></td>
                  <td>{p}</td>
                  <td>{u}</td>
                  <td className="n">{numero(votos)}</td>
                  <td className="n">{sessoes ? `${percentual((100 * presentes) / sessoes)} (${numero(presentes)} de ${numero(sessoes)})` : "—"}</td>
                  <td className="n">{numero(proposicoes)}</td>
                  <td className="n">{moeda(cota)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {linhas.length > INICIAIS && (
          <button type="button" className="botao-link" onClick={() => setTodos(!todos)}>
            {todos ? `mostrar só os ${INICIAIS} primeiros` : `ver todos os ${numero(linhas.length)}`}
          </button>
        )}
        <BaixarCsv nome="deputados-federais"
          colunas={["Id na Câmara", "Deputado", "Partido", "UF", "Votos no Plenário", "Sessões presentes",
                    "Sessões em exercício", "Proposições", "Cota parlamentar (R$)"]}
          linhas={() => linhas.map(([id, nome, p, u, , votos, proposicoes, presentes, sessoes, cota]) =>
            [id, nome, p, u, votos, presentes, sessoes, proposicoes, cota])} />
        <p className="busca-detalhe">
          Votos nominais no Plenário, presença nas sessões deliberativas do Plenário enquanto o deputado estava em
          exercício, proposições que apresentou (projetos de lei, de lei complementar, de decreto legislativo, de
          resolução e propostas de emenda à Constituição) e cota parlamentar (CEAP), somados {periodo}, dos dados
          abertos da Câmara dos Deputados. Os números não medem trabalho em comissões,
          relatorias nem o que não vai a voto nominal.{" "}
          <a href={METODO} target="_blank" rel="noreferrer">como é montado</a>
        </p>
      </section>
    </>
  );
}
