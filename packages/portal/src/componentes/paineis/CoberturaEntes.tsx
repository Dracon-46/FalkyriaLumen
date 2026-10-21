"use client";

/**
 * Cobertura por ente e UF (ADR-048), na situação das coletas: quantos entes de cada UF têm o dado escolhido no
 * Lumen (publicação no PNCP num ano, o extrato de entregas, a DCA, o RGF ou a RCL) e quais não têm. Mede o que o
 * Lumen e as fontes cobrem, não o ente.
 */

import Link from "next/link";
import { Fragment, useEffect, useMemo, useState } from "react";
import { Escolha } from "@/componentes/Escolha";
import {
  carregarCobertura,
  contarPorUf,
  dadoDoValor,
  dadoPadrao,
  opcoesDeDado,
  pncpPorAno,
  rotuloDoDado,
  valorDoDado,
  type Cobertura,
  type ContagemCobertura,
  type Dado,
  type Recorte,
} from "@/lib/cobertura";
import { numero, percentual } from "@/lib/formato";
import { carregarEntes, dataCurta } from "@/lib/paineis";
import { GraficoBarras } from "./Comuns";

const METODO = "https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-048.md";
const LISTA_MAXIMA = 300;

const RECORTES: { valor: Recorte; rotulo: string }[] = [
  { valor: "todos", rotulo: "Todos" },
  { valor: "acima", rotulo: "Estados, DF e municípios acima de 20 mil hab." },
  { valor: "ate", rotulo: "Municípios até 20 mil hab." },
];

/** Carregando, o arquivo lido (null quando ainda não publicado) ou o erro. */
type Estado = { fase: "carregando" } | { fase: "pronto"; dados: Cobertura | null } | { fase: "erro"; erro: string };

/** A seção inteira: filtros, a evolução no PNCP, a tabela por UF e, aberta, a lista de quem não tem o dado. */
export function CoberturaEntes() {
  const [estado, setEstado] = useState<Estado>({ fase: "carregando" });
  const [valor, setValor] = useState<string | null>(null);
  const [recorte, setRecorte] = useState<Recorte>("todos");
  const [aberta, setAberta] = useState<string | null>(null);
  const [nomes, setNomes] = useState<Map<string, string> | null>(null);

  useEffect(() => {
    const c = new AbortController();
    carregarCobertura(c.signal)
      .then((dados) => setEstado({ fase: "pronto", dados }))
      .catch((e: Error) => {
        if (e.name !== "AbortError") setEstado({ fase: "erro", erro: e.message });
      });
    return () => c.abort();
  }, []);

  useEffect(() => {
    if (aberta === null || nomes !== null) return;
    carregarEntes()
      .then((entes) => setNomes(new Map(entes.map((e) => [e.codigo, e.nome]))))
      .catch(() => setNomes(new Map()));
  }, [aberta, nomes]);

  const dados = estado.fase === "pronto" ? estado.dados : null;
  const dado: Dado | null = dados ? (valor ? dadoDoValor(valor, dados) : null) ?? dadoPadrao(dados) : null;
  const contagem = useMemo(() => (dados && dado ? contarPorUf(dados, dado, recorte) : null), [dados, dado, recorte]);

  let corpo;
  if (estado.fase === "carregando") corpo = <p className="busca-detalhe">Carregando…</p>;
  else if (estado.fase === "erro") corpo = <p className="busca-detalhe">Não foi possível ler a cobertura agora ({estado.erro}).</p>;
  else if (!dados || !dado || !contagem) corpo = <p className="busca-detalhe">A cobertura ainda não foi publicada.</p>;
  else {
    const serie = pncpPorAno(dados, recorte);
    const pagina = dado.fonte === "pncp" ? "contratacoes" : "conformidade";
    corpo = (
      <>
        <div className="filtro-periodo">
          <span className="filtro-periodo-titulo">Dado</span>
          <Escolha rotulo="Dado medido" className="escolha-larga" opcoes={opcoesDeDado(dados)} valor={valorDoDado(dado)}
            onEscolher={(v) => { setValor(v); setAberta(null); }} />
          <span className="filtro-periodo-titulo">Entes</span>
          <span className="filtro-periodo-atalhos">
            {RECORTES.map((r) => (
              <button key={r.valor} type="button" className="botao" aria-pressed={recorte === r.valor}
                onClick={() => { setRecorte(r.valor); setAberta(null); }}>
                {r.rotulo}
              </button>
            ))}
          </span>
        </div>
        {serie.length > 1 && (
          <GraficoBarras
            titulo="Entes com publicação no PNCP, por ano (%)"
            barras={serie.map((s) => ({ rotulo: s.ano, valor: s.entes ? (100 * s.com) / s.entes : 0 }))}
            formatar={percentual}
            formatarEixo={(n) => `${Math.round(n)}%`}
          />
        )}
        <div className="tabela-rolavel">
          <table className="tabela">
            <thead>
              <tr>
                <th>UF</th>
                <th className="n">Entes</th>
                <th className="n">Com o dado</th>
                <th className="n">%</th>
                <th>Sem o dado</th>
              </tr>
            </thead>
            <tbody>
              <LinhaUf c={contagem.brasil} destaque />
              {contagem.ufs.map((u) => (
                <Fragment key={u.uf}>
                  <LinhaUf c={u} aberta={aberta === u.uf} onAbrir={() => setAberta(aberta === u.uf ? null : u.uf)} />
                  {aberta === u.uf && (
                    <tr className="linha-aberta">
                      <td colSpan={5}>
                        <ListaSem codigos={u.sem} nomes={nomes} pagina={pagina} />
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
        <p className="busca-detalhe">
          {rotuloDoDado(dado, dados)}. PNCP de {dataCurta(dados.pncp.de)} a {dataCurta(dados.pncp.ate)}
          {dados.uniao.pncp.length > 0 && `; a União tem publicação em ${dados.uniao.pncp.join(", ")}`}. Sem publicação
          no PNCP não quer dizer sem contratação: até o fim de 2023, os entes ainda podiam contratar pela Lei 8.666,
          que não usa o PNCP, e os municípios com até {numero(dados.limite_art_176)} habitantes podem divulgar em
          diário oficial até 1º/4/2027 (Lei 14.133, art. 176). No SICONFI, conta o que o Lumen coletou: o extrato
          do exercício e a DCA, o RGF e a RCL do exercício usado nos grupos de pares.{" "}
          <a href={METODO} target="_blank" rel="noreferrer">
            como é medido
          </a>
        </p>
      </>
    );
  }

  return (
    <section className="cartao cartao-corpo" aria-labelledby="titulo-cobertura">
      <h2 id="titulo-cobertura" className="titulo-secao">Cobertura por ente e UF</h2>
      {corpo}
    </section>
  );
}

/** Uma linha da tabela: a UF (ou o Brasil), as contagens e o botão que abre a lista de quem não tem o dado. */
function LinhaUf({ c, destaque = false, aberta = false, onAbrir }: {
  c: ContagemCobertura; destaque?: boolean; aberta?: boolean; onAbrir?: () => void;
}) {
  const faltam = c.entes - c.com;
  return (
    <tr className={destaque ? "linha-total" : undefined}>
      <td>{destaque ? <strong>{c.uf}</strong> : c.uf}</td>
      <td className="n">{numero(c.entes)}</td>
      <td className="n">{numero(c.com)}</td>
      <td className="n">{c.entes ? percentual((100 * c.com) / c.entes) : "—"}</td>
      <td>
        {faltam === 0 ? "nenhum" : onAbrir ? (
          <button type="button" className="botao-link" aria-expanded={aberta} onClick={onAbrir}>
            {aberta ? "fechar" : `ver os ${numero(faltam)}`}
          </button>
        ) : (
          numero(faltam)
        )}
      </td>
    </tr>
  );
}

/** Os entes da UF sem o dado, com o link para a página deles. */
function ListaSem({ codigos, nomes, pagina }: { codigos: string[]; nomes: Map<string, string> | null; pagina: string }) {
  if (nomes === null) return <p className="busca-detalhe">Carregando os nomes…</p>;
  const ordem = [...codigos].sort((a, b) => (nomes.get(a) ?? a).localeCompare(nomes.get(b) ?? b, "pt-BR"));
  const mostrados = ordem.slice(0, LISTA_MAXIMA);
  return (
    <p className="busca-detalhe">
      {mostrados.map((codigo, i) => (
        <Fragment key={codigo}>
          {i > 0 && ", "}
          <Link href={`/${pagina}/?ente=${codigo}`}>{nomes.get(codigo) ?? codigo}</Link>
        </Fragment>
      ))}
      {ordem.length > LISTA_MAXIMA && ` e mais ${numero(ordem.length - LISTA_MAXIMA)}`}.
    </p>
  );
}
