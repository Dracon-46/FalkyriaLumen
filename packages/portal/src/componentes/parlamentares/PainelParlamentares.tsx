"use client";

/**
 * A lista dos parlamentares (ADR-060): por enquanto, os deputados federais das duas últimas legislaturas. Filtros de
 * período (um ano ou uma legislatura), nome, UF e partido, que ficam na URL (`?periodo=`, `?busca=`, `?uf=`,
 * `?partido=`), e as colunas ordenáveis pelo cabeçalho (`?ordem=coluna-sentido`). Cada nome abre a página do deputado.
 * A ordem padrão é a alfabética: a lista não pontua ninguém.
 */

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { BaixarCsv } from "@/componentes/BaixarCsv";
import { Escolha } from "@/componentes/Escolha";
import { ThOrdem } from "@/componentes/ThOrdem";
import { numero, percentual } from "@/lib/formato";
import { type Ordem, ordenar } from "@/lib/ordem";
import { moeda } from "@/lib/paineis";
import {
  apareceNoPeriodo,
  carregarIndiceCamara,
  filtrarDeputados,
  type IndiceCamara,
  type LinhaDeputado,
  type Numeros,
  numerosNoPeriodo,
} from "@/lib/parlamentares";
import { Situacao } from "../paineis/Comuns";

/** Linhas mostradas antes de "ver todos". */
const INICIAIS = 60;
const METODO = "https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-060.md";

/** Carregando, o índice lido (null quando ainda não foi publicado) ou o erro. */
type Estado = { fase: "carregando" } | { fase: "pronto"; indice: IndiceCamara | null } | { fase: "erro" };

/** Uma linha com os números do período escolhido. */
type Linha = { d: LinhaDeputado; n: Numeros; presenca: number | null };

/** `"57"` → os anos da legislatura que estão no índice; `"2025"` → só ele; vazio → todos (null). */
function anosDoPeriodo(periodo: string, indice: IndiceCamara): string[] | null {
  if (!periodo) return null;
  const leg = indice.legislaturas?.[periodo];
  if (leg) return indice.anos.filter((a) => Number(a) >= leg[0] && Number(a) <= leg[1]);
  return indice.anos.includes(periodo) ? [periodo] : null;
}

/** A página da lista: os filtros e a tabela dos deputados. */
export function PainelParlamentares() {
  const params = useSearchParams();
  const router = useRouter();
  const [estado, setEstado] = useState<Estado>({ fase: "carregando" });
  const [todos, setTodos] = useState(false);
  const uf = params.get("uf")?.toUpperCase() ?? null;
  const partido = params.get("partido");
  const termo = params.get("busca") ?? "";
  const periodo = params.get("periodo") ?? "";
  const [colunaOrdem, sentidoOrdem] = (params.get("ordem") ?? "").split("-");
  const ordem: Ordem | null = colunaOrdem && (sentidoOrdem === "asc" || sentidoOrdem === "desc")
    ? { coluna: colunaOrdem, sentido: sentidoOrdem } : null;
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
  const anos = indice ? anosDoPeriodo(periodo, indice) : null;
  const chaveAnos = anos?.join() ?? "";
  const linhas = useMemo<Linha[]>(() => {
    if (!indice) return [];
    const doPeriodo = chaveAnos ? chaveAnos.split(",") : null;
    const filtradas = filtrarDeputados(indice.deputados, { termo, uf, partido })
      .filter((d) => apareceNoPeriodo(d, doPeriodo) && (!indice.legislaturas?.[periodo] || d[4].includes(Number(periodo))))
      .map((d) => {
        const n = numerosNoPeriodo(d, doPeriodo);
        return { d, n, presenca: n[3] ? (100 * n[2]) / n[3] : null };
      });
    return ordenar(filtradas, colunaOrdem && ordem ? ordem : null, {
      nome: (l) => l.d[1], partido: (l) => l.d[2], uf: (l) => l.d[3], votos: (l) => l.n[0],
      presenca: (l) => l.presenca, proposicoes: (l) => l.n[1], cota: (l) => l.n[4],
    });
  }, [indice, termo, uf, partido, chaveAnos, colunaOrdem, sentidoOrdem]); // eslint-disable-line react-hooks/exhaustive-deps

  if (estado.fase === "carregando") return <Situacao>Carregando…</Situacao>;
  if (estado.fase === "erro") return <Situacao>Não foi possível ler os parlamentares agora.</Situacao>;
  if (!indice) return <Situacao>Os parlamentares ainda não foram publicados.</Situacao>;
  const ufs = [...new Set(indice.deputados.map((d) => d[3]))].sort();
  const partidos = [...new Set(indice.deputados.map((d) => d[2]))].sort();
  const legislaturas = Object.entries(indice.legislaturas ?? {}).sort((a, b) => b[0].localeCompare(a[0]));
  const mostradas = todos ? linhas : linhas.slice(0, INICIAIS);
  const nomePeriodo = !anos ? `de ${indice.anos[0]} a ${indice.anos[indice.anos.length - 1]}`
    : anos.length === 1 ? `em ${anos[0]}` : `de ${anos[0]} a ${anos[anos.length - 1]}`;
  const th = (coluna: string, rotulo: string, opcoes: { className?: string; texto?: boolean } = {}) => (
    <ThOrdem coluna={coluna} ordem={ordem} className={opcoes.className} texto={opcoes.texto}
      onOrdenar={(o) => mudar("ordem", `${o.coluna}-${o.sentido}`)}>{rotulo}</ThOrdem>
  );

  return (
    <>
      <form className="cartao cartao-corpo filtro-periodo" aria-label="Filtros"
        onSubmit={(e) => { e.preventDefault(); mudar("busca", texto.trim() || null); }}>
        <Escolha rotulo="Período" className="escolha-larga" valor={periodo} onEscolher={(v) => mudar("periodo", v || null)} opcoes={[
          { valor: "", rotulo: "todos os anos" },
          ...legislaturas.map(([l, [a, b]]) => ({ valor: l, rotulo: `${l}ª legislatura (${a} a ${b})` })),
          ...[...indice.anos].reverse().map((a) => ({ valor: a, rotulo: a })),
        ]} />
        <Escolha rotulo="UF" valor={uf ?? ""} onEscolher={(v) => mudar("uf", v || null)}
          opcoes={[{ valor: "", rotulo: "todas as UFs" }, ...ufs.map((u) => ({ valor: u, rotulo: u }))]} />
        <Escolha rotulo="Partido" className="escolha-larga" valor={partido ?? ""} onEscolher={(v) => mudar("partido", v || null)}
          opcoes={[{ valor: "", rotulo: "todos os partidos" }, ...partidos.map((p) => ({ valor: p, rotulo: p }))]} />
        <input id="busca-parlamentar" className="seletor" placeholder="nome do deputado" aria-label="Nome do deputado"
          value={texto} onChange={(e) => setTexto(e.target.value)} />
        <button type="submit" className="botao">Buscar</button>
        {(periodo || uf || partido || termo || ordem) && (
          <button type="button" className="botao-link" onClick={() => router.replace("/parlamentares/", { scroll: false })}>
            limpar filtros
          </button>
        )}
      </form>
      <section className="cartao cartao-corpo" aria-labelledby="titulo-deputados">
        <h2 id="titulo-deputados" className="titulo-secao">Deputados federais</h2>
        <p>
          {numero(linhas.length)} deputado(s) com mandato {nomePeriodo}. Clique no cabeçalho de uma coluna para ordenar;
          clique de novo para inverter. O partido e a UF são os mais recentes.
        </p>
        <div className="tabela-rolavel">
          <table className="tabela">
            <thead>
              <tr>
                {th("nome", "Deputado", { texto: true })}
                {th("partido", "Partido", { texto: true })}
                {th("uf", "UF", { texto: true })}
                {th("votos", "Votos no Plenário", { className: "n" })}
                {th("presenca", "Presença", { className: "n" })}
                {th("proposicoes", "Proposições", { className: "n" })}
                {th("cota", "Cota parlamentar", { className: "n" })}
              </tr>
            </thead>
            <tbody>
              {mostradas.map(({ d: [id, nome, p, u], n, presenca }) => (
                <tr key={id}>
                  <td><Link href={`/parlamentares/deputado/?id=${id}${anos?.length === 1 ? `&ano=${anos[0]}` : ""}`}>{nome}</Link></td>
                  <td>{p}</td>
                  <td>{u}</td>
                  <td className="n">{numero(n[0])}</td>
                  <td className="n" title={`${numero(n[2])} de ${numero(n[3])} sessões deliberativas em exercício`}>
                    {presenca === null ? "—" : percentual(presenca)}
                  </td>
                  <td className="n">{numero(n[1])}</td>
                  <td className="n">{moeda(n[4])}</td>
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
          linhas={() => linhas.map(({ d: [id, nome, p, u], n }) => [id, nome, p, u, n[0], n[2], n[3], n[1], n[4]])} />
        <p className="busca-detalhe">
          Votos nominais no Plenário, presença nas sessões deliberativas do Plenário enquanto o deputado estava em
          exercício (passe o mouse para ver quantas), proposições que apresentou (projetos de lei, de lei complementar, de
          decreto legislativo, de resolução e PECs) e cota parlamentar (CEAP), {nomePeriodo}, dos dados abertos da Câmara
          dos Deputados. Os números não medem trabalho em comissões, relatorias nem o que não vai a voto nominal.{" "}
          <a href={METODO} target="_blank" rel="noreferrer">como é montado</a>
        </p>
      </section>
    </>
  );
}
