"use client";

/**
 * A lista das câmaras municipais com dados do SAPL do Interlegis (ADR-062): filtros de UF e de nome na URL (`?uf=`,
 * `?busca=`) e o município escolhido no cabeçalho (`?municipio=`) em destaque. Cada câmara abre a lista dos vereadores.
 * Com `esfera` `estadual`, a mesma lista para as Assembleias Legislativas que usam o SAPL.
 */

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { Escolha } from "@/componentes/Escolha";
import { ThOrdem } from "@/componentes/ThOrdem";
import { normalizar } from "@/lib/busca";
import { numero } from "@/lib/formato";
import { type Ordem, ordenar } from "@/lib/ordem";
import { type CamaraMunicipal, carregarCamarasMunicipais, type Esfera } from "@/lib/parlamentares";
import { Situacao } from "../paineis/Comuns";
import { NavParlamentares } from "./NavParlamentares";

const METODO = "https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-062.md";

/** A página: as câmaras (ou Assembleias) publicadas, filtradas e ordenáveis. */
export function PainelCamaras({ esfera = "municipal" }: { esfera?: Esfera }) {
  const estadual = esfera === "estadual";
  const rota = estadual ? "/parlamentares/estaduais/" : "/parlamentares/vereadores/";
  const params = useSearchParams();
  const router = useRouter();
  const [camaras, setCamaras] = useState<CamaraMunicipal[] | null | undefined>(undefined);
  const [ordem, setOrdem] = useState<Ordem | null>(null);
  const uf = params.get("uf")?.toUpperCase() ?? "";
  const termo = params.get("busca") ?? "";
  const municipio = params.get("municipio");
  const [texto, setTexto] = useState(termo);

  useEffect(() => {
    const c = new AbortController();
    carregarCamarasMunicipais(c.signal, esfera).then(setCamaras).catch((e: Error) => e.name !== "AbortError" && setCamaras(null));
    return () => c.abort();
  }, [esfera]);

  /** Troca um filtro na URL, sem rolar a página. */
  const mudar = (chave: string, valor: string | null) => {
    const q = new URLSearchParams(params.toString());
    if (valor) q.set(chave, valor);
    else q.delete(chave);
    router.replace(`${rota}?${q.toString()}`, { scroll: false });
  };

  const linhas = useMemo(() => {
    const palavras = normalizar(termo).split(" ").filter(Boolean);
    return ordenar((camaras ?? []).filter(([, nome, u]) => (!uf || u === uf)
      && palavras.every((p) => normalizar(nome).includes(p))), ordem ?? { coluna: "nome", sentido: "asc" }, {
      nome: (c) => c[1], uf: (c) => c[2], vereadores: (c) => c[4], votacoes: (c) => c[5], desde: (c) => c[6][0],
    });
  }, [camaras, uf, termo, ordem]);

  const nav = <NavParlamentares atual={estadual ? "estaduais" : "vereadores"} />;
  if (camaras === undefined) return <>{nav}<Situacao>Carregando…</Situacao></>;
  if (camaras === null) return <>{nav}<Situacao>Não foi possível ler as casas agora.</Situacao></>;
  if (camaras.length === 0) return <>{nav}<Situacao>Os {estadual ? "deputados estaduais" : "vereadores"} ainda não foram publicados.</Situacao></>;
  const ufs = [...new Set(camaras.map((c) => c[2]))].sort();
  const escolhida = municipio ? camaras.find((c) => c[0] === municipio) : undefined;
  const th = (coluna: string, rotulo: string, opcoes: { className?: string; texto?: boolean } = {}) => (
    <ThOrdem coluna={coluna} ordem={ordem ?? { coluna: "nome", sentido: "asc" }} onOrdenar={setOrdem}
      className={opcoes.className} texto={opcoes.texto}>{rotulo}</ThOrdem>
  );

  return (
    <>
      {nav}
      {municipio && !estadual && (
        <section className="cartao cartao-corpo">
          {escolhida
            ? <p><Link href={`/parlamentares/?casa=${escolhida[0]}`}>Vereadores de {escolhida[1]} ({escolhida[2]})</Link>:{" "}
                {numero(escolhida[4])} vereador(es), {numero(escolhida[5])} votação(ões) nominal(is) de projetos registradas.</p>
            : <p>A câmara do município escolhido não está entre as que publicam pelo SAPL do Interlegis no endereço padrão,
                ou ainda não foi lida.</p>}
        </section>
      )}
      <form className="cartao cartao-corpo filtro-periodo" aria-label="Filtros"
        onSubmit={(e) => { e.preventDefault(); mudar("busca", texto.trim() || null); }}>
        <Escolha rotulo="UF" valor={uf} onEscolher={(v) => mudar("uf", v || null)}
          opcoes={[{ valor: "", rotulo: "todas as UFs" }, ...ufs.map((u) => ({ valor: u, rotulo: u }))]} />
        <input id="busca-camara" className="seletor" placeholder={estadual ? "nome do estado" : "nome do município"}
          aria-label={estadual ? "Nome do estado" : "Nome do município"}
          value={texto} onChange={(e) => setTexto(e.target.value)} />
        <button type="submit" className="botao">Buscar</button>
        {(uf || termo) && (
          <button type="button" className="botao-link" onClick={() => router.replace(rota, { scroll: false })}>
            limpar filtros
          </button>
        )}
      </form>
      <section className="cartao cartao-corpo" aria-labelledby="titulo-camaras">
        <h2 id="titulo-camaras" className="titulo-secao">{estadual ? "Assembleias Legislativas" : "Câmaras municipais"}</h2>
        <p>
          {numero(linhas.length)} {estadual ? "Assembleia(s) com os deputados estaduais publicados" : "câmara(s) com os vereadores publicados"}. Clique no cabeçalho de uma coluna para ordenar;
          clique de novo para inverter.
        </p>
        <div className="tabela-rolavel">
          <table className="tabela">
            <thead>
              <tr>
                {th("nome", estadual ? "Estado" : "Município", { texto: true })}
                {th("uf", "UF", { texto: true })}
                {th("vereadores", estadual ? "Deputados" : "Vereadores", { className: "n" })}
                {th("votacoes", "Votações nominais", { className: "n" })}
                {th("desde", "Anos", { className: "n" })}
                <th scope="col">SAPL</th>
              </tr>
            </thead>
            <tbody>
              {linhas.map(([ibge, nome, u, host, vereadores, votacoes, anos]) => (
                <tr key={ibge}>
                  <td><Link href={`/parlamentares/?casa=${ibge}`}>{nome}</Link></td>
                  <td>{u}</td>
                  <td className="n">{numero(vereadores)}</td>
                  <td className="n">{numero(votacoes)}</td>
                  <td className="n">{anos.length ? `${anos[0]} a ${anos[anos.length - 1]}` : "—"}</td>
                  <td><a href={`https://${host}`} target="_blank" rel="noreferrer">{host}</a></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="busca-detalhe">
          {estadual ? <>As Assembleias Legislativas que usam o SAPL do Interlegis (sapl.al.uf.leg.br), com a API aberta,
            de 2017 em diante: os deputados estaduais, os projetos, a presença e o voto de cada um nas votações nominais.
            As Assembleias com sistema próprio entram pelas fontes delas, à parte.{" "}</> : <>
          As câmaras que usam o SAPL do Interlegis no endereço padrão (sapl.cidade.uf.leg.br), com a API aberta, de 2017
          em diante: os vereadores, os projetos que apresentaram, a presença nas sessões e o voto de cada um nas votações
          nominais dos projetos. Muitas câmaras votam quase tudo de forma simbólica, sem voto por vereador. A câmara que
          usa outro sistema não aparece aqui.{" "}</>}
          <a href={METODO} target="_blank" rel="noreferrer">como é montado</a>
        </p>
      </section>
    </>
  );
}
