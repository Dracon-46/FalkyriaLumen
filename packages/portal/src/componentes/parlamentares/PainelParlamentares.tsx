"use client";

/**
 * A lista dos parlamentares (ADR-060): os deputados federais, os senadores (`?casa=senado`) ou os vereadores de uma
 * câmara municipal (`?casa=<IBGE>`) ou os deputados de uma Assembleia (`?casa=<código da UF>`), pelo SAPL (ADR-062).
 * Filtros de
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
import { NavParlamentares } from "./NavParlamentares";
import {
  apareceNoPeriodo,
  type CamaraMunicipal,
  carregarCamaraDaCasa,
  casaDaUrl,
  carregarIndiceCamara,
  consultaDaCasa,
  daCasa,
  filtrarDeputados,
  type IndiceCamara,
  type LinhaDeputado,
  type Numeros,
  numerosNoPeriodo,
  casaDoSapl,
  tipoDaCasa,
  urlDoParlamentar,
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
  const casa = casaDaUrl(params.get("casa"));
  const uf = params.get("uf")?.toUpperCase() ?? null;
  const partido = params.get("partido");
  const termo = params.get("busca") ?? "";
  const periodo = params.get("periodo") ?? "";
  const [colunaOrdem, sentidoOrdem] = (params.get("ordem") ?? "").split("-");
  const ordem: Ordem | null = colunaOrdem && (sentidoOrdem === "asc" || sentidoOrdem === "desc")
    ? { coluna: colunaOrdem, sentido: sentidoOrdem } : null;
  const [texto, setTexto] = useState(termo);
  const [camara, setCamara] = useState<CamaraMunicipal | null>(null);
  const textos = daCasa(casa);
  const municipal = casaDoSapl(casa);
  const estadual = tipoDaCasa(casa) === "estadual";

  useEffect(() => {
    const c = new AbortController();
    setEstado({ fase: "carregando" });
    carregarIndiceCamara(c.signal, casa)
      .then((indice) => setEstado({ fase: "pronto", indice }))
      .catch((e: Error) => e.name !== "AbortError" && setEstado({ fase: "erro" }));
    setCamara(null);
    carregarCamaraDaCasa(casa, c.signal).then(setCamara).catch(() => undefined);
    return () => c.abort();
  }, [casa]);

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

  const nav = <NavParlamentares atual={estadual ? "estaduais" : municipal ? "vereadores" : casa === "senado" ? "senadores" : "deputados"} />;
  if (estado.fase === "carregando") return <>{nav}<Situacao>Carregando…</Situacao></>;
  if (estado.fase === "erro") return <>{nav}<Situacao>Não foi possível ler os parlamentares agora.</Situacao></>;
  if (!indice) return <>{nav}<Situacao>Os {textos.pessoas.toLowerCase()} ainda não foram publicados.</Situacao></>;
  const ufs = [...new Set(indice.deputados.map((d) => d[3]))].sort();
  const partidos = [...new Set(indice.deputados.map((d) => d[2]))].sort();
  const legislaturas = Object.entries(indice.legislaturas ?? {}).sort((a, b) => b[0].localeCompare(a[0]));
  const mostradas = todos ? linhas : linhas.slice(0, INICIAIS);
  const doPeriodo = anos ?? indice.anos;
  const nomePeriodo = doPeriodo.length === 1 ? `em ${doPeriodo[0]}` : `de ${doPeriodo[0]} a ${doPeriodo[doPeriodo.length - 1]}`;
  const plural = `${textos.singular}${textos.singular.endsWith("r") ? "(es)" : "(s)"}`;
  const ondeMunicipal = camara ? ` de ${camara[1]} (${camara[2]})` : "";
  const th = (coluna: string, rotulo: string, opcoes: { className?: string; texto?: boolean } = {}) => (
    <ThOrdem coluna={coluna} ordem={ordem} className={opcoes.className} texto={opcoes.texto}
      onOrdenar={(o) => mudar("ordem", `${o.coluna}-${o.sentido}`)}>{rotulo}</ThOrdem>
  );

  return (
    <>
      {nav}
      <form className="cartao cartao-corpo filtro-periodo" aria-label="Filtros"
        onSubmit={(e) => { e.preventDefault(); mudar("busca", texto.trim() || null); }}>
        <Escolha rotulo="Período" className="escolha-larga" valor={periodo} onEscolher={(v) => mudar("periodo", v || null)} opcoes={[
          { valor: "", rotulo: "todos os anos" },
          ...legislaturas.map(([l, [a, b]]) => ({ valor: l, rotulo: estadual ? `legislatura de ${a} a ${b}` : municipal ? `mandato de ${a} a ${b}` : `${l}ª legislatura (${a} a ${b})` })),
          ...[...indice.anos].reverse().map((a) => ({ valor: a, rotulo: a })),
        ]} />
        {!municipal && <Escolha rotulo="UF" valor={uf ?? ""} onEscolher={(v) => mudar("uf", v || null)}
          opcoes={[{ valor: "", rotulo: "todas as UFs" }, ...ufs.map((u) => ({ valor: u, rotulo: u }))]} />}
        <Escolha rotulo="Partido" className="escolha-larga" valor={partido ?? ""} onEscolher={(v) => mudar("partido", v || null)}
          opcoes={[{ valor: "", rotulo: "todos os partidos" }, ...partidos.map((p) => ({ valor: p, rotulo: p }))]} />
        <input id="busca-parlamentar" className="seletor" placeholder={`nome do ${textos.singular}`}
          aria-label={`Nome do ${textos.singular}`}
          value={texto} onChange={(e) => setTexto(e.target.value)} />
        <button type="submit" className="botao">Buscar</button>
        {(periodo || uf || partido || termo || ordem) && (
          <button type="button" className="botao-link"
            onClick={() => router.replace(`/parlamentares/?${consultaDaCasa(casa)}`.replace(/[?&]$/, ""), { scroll: false })}>
            limpar filtros
          </button>
        )}
      </form>
      <section className="cartao cartao-corpo" aria-labelledby="titulo-deputados">
        <h2 id="titulo-deputados" className="titulo-secao">{textos.pessoas}{ondeMunicipal}</h2>
        <p>
          {numero(linhas.length)} {plural} com mandato {nomePeriodo}. Clique no cabeçalho de uma coluna para ordenar;
          clique de novo para inverter. O partido{municipal ? "" : " e a UF"} {municipal ? "é o mais recente" : "são os mais recentes"}.
        </p>
        <div className="tabela-rolavel">
          <table className="tabela">
            <thead>
              <tr>
                {th("nome", textos.singular[0]!.toUpperCase() + textos.singular.slice(1), { texto: true })}
                {th("partido", "Partido", { texto: true })}
                {!municipal && th("uf", "UF", { texto: true })}
                {th("votos", "Votos no Plenário", { className: "n" })}
                {th("presenca", "Presença", { className: "n" })}
                {th("proposicoes", "Proposições", { className: "n" })}
                {!municipal && th("cota", "Cota parlamentar", { className: "n" })}
              </tr>
            </thead>
            <tbody>
              {mostradas.map(({ d: [id, nome, p, u], n, presenca }) => (
                <tr key={id}>
                  <td><Link href={urlDoParlamentar(id, casa, anos?.length === 1 ? anos[0] : null)}>{nome}</Link></td>
                  <td>{p}</td>
                  {!municipal && <td>{u}</td>}
                  <td className="n">{numero(n[0])}</td>
                  <td className="n" title={`${numero(n[2])} de ${numero(n[3])} ${municipal ? "sessões com presença registrada no mandato" : "sessões deliberativas em exercício"}`}>
                    {presenca === null ? "—" : percentual(presenca)}
                  </td>
                  <td className="n">{numero(n[1])}</td>
                  {!municipal && <td className="n">{moeda(n[4])}</td>}
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
        <BaixarCsv nome={municipal && camara ? `${textos.arquivo}-${camara[0]}` : textos.arquivo}
          colunas={[textos.idRotulo, textos.singular[0]!.toUpperCase() + textos.singular.slice(1), "Partido", "UF", "Votos no Plenário", "Sessões presentes",
                    "Sessões em exercício", "Proposições", "Cota parlamentar (R$)"]}
          linhas={() => linhas.map(({ d: [id, nome, p, u], n }) => [id, nome, p, u, n[0], n[2], n[3], n[1], n[4]])} />
        <p className="busca-detalhe">
          {municipal
            ? <>Votos nominais nos projetos ({textos.tipos}), presença nas sessões com presença registrada enquanto o{" "}
                {textos.singular} tinha mandato (passe o mouse para ver quantas) e projetos que apresentou, {nomePeriodo},
                {camara?.[7] === "spl" ? "do sistema" : "do SAPL"} {textos.doPlenario}
                {camara ? <> (<a href={`https://${camara[3]}`} target="_blank" rel="noreferrer">{camara[3]}</a>)</> : null}.
                Os números são os que a casa registrou no sistema: casa que registra pouco aparece com pouco. A cota
                parlamentar federal não se aplica aqui.</>
            : casa === "senado"
            ? <>Votos nominais no Plenário, presença nas votações nominais enquanto o senador estava em exercício (passe o
                mouse para ver quantas), matérias de que é autor ou coautor (projetos de lei, de lei complementar, de
                decreto legislativo, de resolução e PECs) e cota parlamentar (CEAPS), {nomePeriodo}, dos dados abertos do
                Senado Federal. O Senado decide muito por votação simbólica, sem voto por senador.</>
            : <>Votos nominais no Plenário, presença nas sessões deliberativas do Plenário enquanto o deputado estava em
                exercício (passe o mouse para ver quantas), proposições que apresentou (projetos de lei, de lei
                complementar, de decreto legislativo, de resolução e PECs) e cota parlamentar (CEAP), {nomePeriodo}, dos
                dados abertos da Câmara dos Deputados.</>}{" "}
          Os números não medem trabalho em comissões, relatorias nem o que não vai a voto nominal.{" "}
          <a href={METODO} target="_blank" rel="noreferrer">como é montado</a>
        </p>
      </section>
    </>
  );
}
