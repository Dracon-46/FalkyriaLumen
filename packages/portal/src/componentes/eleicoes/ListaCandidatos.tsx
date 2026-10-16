"use client";

/**
 * Lista de candidatos de um resultado: um cartão por candidato, com foto,
 * números e barra na cor dele, e, nos proporcionais, a votação por
 * agremiação. A ordem é a do feed (mais votados primeiro).
 */

import { useMemo, useState } from "react";
import { Paginacao, usePaginacao } from "@/componentes/Paginacao";
import { normalizar } from "@/lib/busca";
import { varCor } from "@/lib/cores";
import { urls } from "@/lib/feeds";
import { iniciais, numero, percentual } from "@/lib/formato";
import type { Candidato, FeedResultado } from "@/lib/tipos";

const VISIVEIS_MAJORITARIO = 12;
const VISIVEIS_PROPORCIONAL = 20;

/** Selo de situação: eleito (com o texto do TSE), 2º turno ou, para votos não válidos, a destinação. */
function Selo({ c }: { c: Candidato }) {
  if (c.eleito) return <span className="selo selo-eleito">{c.situacao || "Eleito"}</span>;
  if (c.segundo_turno) return <span className="selo selo-turno">2º turno</span>;
  if (!c.valido) return <span className="selo selo-neutro">{c.destinacao ?? "Voto anulado"}</span>;
  return null;
}

/** Foto do candidato servida junto dos feeds; sem foto, ou se ela não carrega, as iniciais do nome de urna. */
function Foto({ c }: { c: Candidato }) {
  const [falhou, setFalhou] = useState(false);
  const url = c.foto ? urls.foto(c.foto) : null;
  if (url && !falhou) {
    // eslint-disable-next-line @next/next/no-img-element -- site estático, sem otimizador de imagem
    return <img className="candidato-foto" src={url} alt="" loading="lazy" onError={() => setFalhou(true)} />;
  }
  return (
    <span className="candidato-foto" aria-hidden="true">
      {iniciais(c.nome_urna)}
    </span>
  );
}

/** Quem acompanha o titular na chapa: vice (executivo) ou 1º suplente (Senado). */
function rotuloVice(cargo: string): string {
  return cargo === "senador" ? "1º suplente" : "Vice";
}

/**
 * Cartão de um candidato. A barra é relativa ao mais votado, que ocupa a
 * largura toda (não ao total de votos), com um mínimo de 0,5% para continuar
 * visível. Candidato com votos não válidos fica sem barra e sem percentual.
 */
function Cartao({ c, maior, cargo }: { c: Candidato; maior: number; cargo: string }) {
  const largura = c.valido && maior > 0 ? Math.max(0.5, (100 * c.votos) / maior) : 0;
  return (
    <li
      className={`candidato${c.valido ? "" : " candidato-anulado"}`}
      style={{ ["--cor-candidato" as string]: varCor(c.cor) }}
    >
      <Foto c={c} />
      <div>
        <div className="candidato-nome">
          {c.nome_urna}
          <Selo c={c} />
        </div>
        <div className="candidato-detalhe">
          {[c.sem_numero ? null : c.numero, c.partido, c.agremiacao && c.agremiacao !== c.partido ? c.agremiacao : null]
            .filter(Boolean)
            .join(" · ")}
        </div>
        {c.vice && (
          <div className="candidato-detalhe">
            {rotuloVice(cargo)}: {c.vice}
          </div>
        )}
      </div>
      <div className="candidato-numeros">
        <div className="candidato-pct">{c.valido ? percentual(c.pct) : "—"}</div>
        <div className="candidato-votos">{numero(c.votos)} votos</div>
      </div>
      <div className="barra" aria-hidden="true">
        <span style={{ width: `${largura}%` }} />
      </div>
    </li>
  );
}

/**
 * Candidatos do resultado: os 12 primeiros (20 nos proporcionais), com botão
 * para ver todos, 20 por página e com busca por nome, número ou partido. Avisa
 * quando o arquivo do município deixou candidatos de fora e, nos proporcionais,
 * acrescenta a votação por agremiação.
 */
export function ListaCandidatos({ feed }: { feed: FeedResultado }) {
  const [todos, setTodos] = useState(false);
  const [filtro, setFiltro] = useState("");
  const proporcional = feed.cargo.tipo === "proporcional";
  const limite = proporcional ? VISIVEIS_PROPORCIONAL : VISIVEIS_MAJORITARIO;
  const filtrados = useMemo(() => {
    const termo = normalizar(filtro);
    if (!termo) return feed.candidatos;
    return feed.candidatos.filter((c) =>
      normalizar(`${c.nome_urna} ${c.numero} ${c.partido ?? ""} ${c.agremiacao ?? ""}`).includes(termo),
    );
  }, [feed.candidatos, filtro]);
  const pagina = usePaginacao(filtrados);
  const lista = todos ? pagina.visiveis : feed.candidatos.slice(0, limite);
  const maior = feed.candidatos.reduce((m, c) => (c.valido && c.votos > m ? c.votos : m), 0);
  return (
    <section aria-labelledby="titulo-candidatos">
      <h2 id="titulo-candidatos" className="titulo-secao">
        {proporcional ? "Candidatos mais votados" : "Candidatos"}
      </h2>
      {todos && (
        <input
          className="seletor filtro-tabela"
          value={filtro}
          placeholder="Buscar candidato, número ou partido"
          aria-label="Buscar candidato pelo nome, número ou partido"
          onChange={(e) => setFiltro(e.target.value)}
        />
      )}
      {todos && filtrados.length === 0 && <p className="candidato-detalhe">Nenhum candidato com esse nome ou número.</p>}
      <ul className="candidatos" style={{ listStyle: "none", margin: 0, padding: 0 }}>
        {lista.map((c) => (
          <Cartao key={`${c.numero}-${c.nome_urna}`} c={c} maior={maior} cargo={feed.cargo.slug} />
        ))}
      </ul>
      {todos && <Paginacao {...pagina} rotulo="candidatos" />}
      {feed.candidatos.length > limite && (
        <p>
          <button
            type="button"
            className="botao"
            onClick={() => {
              setTodos((v) => !v);
              setFiltro("");
            }}
          >
            {todos ? "Mostrar menos" : `Mostrar todos os ${numero(feed.candidatos.length)} candidatos`}
          </button>
        </p>
      )}
      {feed.candidatos_omitidos > 0 && (
        <p className="candidato-detalhe">
          Neste município, a lista traz os {numero(feed.candidatos.length)} mais votados e os eleitos;{" "}
          {numero(feed.candidatos_omitidos)} candidatos com menos votos estão no resultado do estado.
        </p>
      )}
      {proporcional && feed.agremiacoes.length > 0 && <Agremiacoes feed={feed} />}
    </section>
  );
}

/** Votos e vagas por partido, federação ou coligação, com o quociente eleitoral; começa recolhida. */
function Agremiacoes({ feed }: { feed: FeedResultado }) {
  const pagina = usePaginacao(feed.agremiacoes);
  return (
    <details style={{ marginTop: 16 }}>
      <summary>Votação por partido, federação ou coligação</summary>
      <table className="tabela" style={{ marginTop: 8 }}>
        <thead>
          <tr>
            <th>Agremiação</th>
            <th className="n">Votos</th>
            <th className="n">Vagas</th>
          </tr>
        </thead>
        <tbody>
          {pagina.visiveis.map((a) => (
            <tr key={a.nome}>
              <td>
                {a.nome}
                {a.composicao && a.composicao !== a.nome ? (
                  <div className="candidato-detalhe">{a.composicao}</div>
                ) : null}
              </td>
              <td className="n">{numero(a.votos)}</td>
              <td className="n">{a.vagas ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <Paginacao {...pagina} rotulo="agremiações" />
      {feed.quociente_eleitoral != null && (
        <p className="candidato-detalhe">Quociente eleitoral: {numero(feed.quociente_eleitoral)} votos.</p>
      )}
    </details>
  );
}
