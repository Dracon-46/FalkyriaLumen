/**
 * Página `/novidades/`: as mudanças e as versões do Lumen, da mais nova à mais antiga, lidas do `CHANGELOG.md` na
 * geração do site. As duas versões mais recentes vêm abertas; as anteriores, recolhidas.
 */

import type { Metadata } from "next";
import { Fragment } from "react";
import { MarcarNovidades } from "@/componentes/MarcarNovidades";
import { novidadesDoRepositorio } from "@/lib/changelog";
import { dataDaVersao, idsDasNovidades, type Novidade, trechos, type VersaoNovidades } from "@/lib/novidades";

const REPOSITORIO = "https://github.com/Dracon-46/FalkyriaLumen";
/** Versões abertas na chegada; as outras ficam recolhidas. */
const ABERTAS = 2;

/** Título e descrição da página, usados pelo navegador e nas prévias de link. */
export const metadata: Metadata = {
  title: "Novidades",
  description: "As mudanças e as versões do Lumen, da mais nova à mais antiga.",
};

/** O texto de um item, com o código e o destaque marcados. */
function Texto({ texto }: { texto: string }) {
  return (
    <>
      {trechos(texto).map((t, i) => (
        <Fragment key={i}>
          {t.tipo === "codigo" ? <code>{t.valor}</code> : t.tipo === "forte" ? <strong>{t.valor}</strong> : t.valor}
        </Fragment>
      ))}
    </>
  );
}

/** Uma mudança: o título e a lista, com os subitens. */
function Mudanca({ n }: { n: Novidade }) {
  return (
    <article className="novidade" id={n.id.replace("/", "--")}>
      <h3 className="novidade-titulo">{n.titulo}</h3>
      <ul className="novidade-itens">
        {n.itens.map((item, i) => (
          <li key={i}>
            <Texto texto={item.texto} />
            {item.filhos.length > 0 && (
              <ul>
                {item.filhos.map((f, j) => (
                  <li key={j}>
                    <Texto texto={f} />
                  </li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ul>
    </article>
  );
}

/** O título de uma versão. */
function tituloDaVersao(v: VersaoNovidades): string {
  return v.versao && v.data ? `Versão ${v.versao} · ${dataDaVersao(v.data)}` : "No ar, ainda sem número de versão";
}

/** A página: o aviso das mudanças novas e as versões. */
export default function Novidades() {
  const versoes = novidadesDoRepositorio();
  return (
    <div className="painel">
      <div className="painel-topo">
        <div>
          <h1>Novidades</h1>
          <p className="painel-periodo">
            As mudanças e as versões do Lumen, da mais nova à mais antiga. Cada uma cita a decisão (ADR) que a
            explica, no{" "}
            <a href={REPOSITORIO} target="_blank" rel="noreferrer">
              repositório
            </a>
            .
          </p>
        </div>
      </div>
      <MarcarNovidades ids={idsDasNovidades(versoes)} />
      {versoes.length === 0 ? (
        <p className="situacao-painel">
          O histórico não pôde ser lido nesta publicação. Ele está no{" "}
          <a href={`${REPOSITORIO}/blob/main/CHANGELOG.md`} target="_blank" rel="noreferrer">
            CHANGELOG do repositório
          </a>
          .
        </p>
      ) : (
        versoes.map((v, i) => (
          <details key={v.versao ?? "no-ar"} className="cartao cartao-corpo novidades-versao" open={i < ABERTAS}>
            <summary className="titulo-secao">
              {tituloDaVersao(v)}
              <span className="busca-detalhe"> · {v.novidades.length} mudança(s)</span>
            </summary>
            {v.novidades.map((n) => (
              <Mudanca key={n.id} n={n} />
            ))}
          </details>
        ))
      )}
    </div>
  );
}
