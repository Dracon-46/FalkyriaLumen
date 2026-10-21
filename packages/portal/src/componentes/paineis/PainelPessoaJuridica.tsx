"use client";

/**
 * Visão 360 de uma empresa ou entidade pelo CNPJ (ADR-049): o cadastro na Receita, os contratos publicados no PNCP
 * com cada ente, as emendas parlamentares recebidas e os convênios com a União. São fatos das fontes, como
 * publicados; a página não marca nem ordena ninguém por risco. Sem CNPJ, a busca pelo nome (`?busca=`).
 */

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { type FormEvent, useEffect, useState } from "react";
import { numero } from "@/lib/formato";
import { carregarEntes, cnpj as formatarCnpj, dataCurta, moeda, moedaCompacta, tipoDoCodigo } from "@/lib/paineis";
import {
  type AchadoPj,
  buscarPessoasJuridicas,
  carregarPessoaJuridica,
  cnpjDoTexto,
  contratosPorAno,
  contratosPorEnte,
  emendasPorEnte,
  type PessoaJuridica,
  type PorEnte,
  tcePorEnte,
  totaisDaPessoa,
} from "@/lib/pessoaJuridica";
import { GraficoBarras, Situacao } from "./Comuns";
import { EmpresaReceitaCartao } from "./EmpresaReceita";

const METODO = "https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-049.md";
/** Convênios listados, do maior valor ao menor. */
const CONVENIOS_LISTADOS = 100;
/** Entes mostrados antes de "ver todos", nas tabelas por ente. */
const ENTES_INICIAIS = 30;

/** Carregando, o registro lido (null quando o CNPJ não aparece em nenhuma fonte) ou o erro. */
type Estado = { fase: "carregando" } | { fase: "pronto"; dados: PessoaJuridica | null } | { fase: "erro"; erro: string };

/** Nome e UF de cada ente, do cadastro da busca. */
type Nomes = Map<string, { nome: string; uf: string | null }>;

/**
 * A data do arquivo da CGU: "20261009" (convênios, a data na página de download) ou o `Last-Modified` do servidor
 * (emendas) → "09/10/2026".
 */
function dataDoArquivo(d: string | null): string {
  if (d && /^\d{8}$/.test(d)) return `${d.slice(6, 8)}/${d.slice(4, 6)}/${d.slice(0, 4)}`;
  const data = d ? new Date(d) : null;
  return data && !Number.isNaN(data.getTime())
    ? data.toLocaleDateString("pt-BR", { timeZone: "America/Sao_Paulo" }) : "data não informada";
}

/** A busca pelo nome: procurando, os achados (null quando a busca ainda não foi publicada) ou o erro. */
type EstadoBusca = { fase: "procurando" } | { fase: "pronta"; achados: AchadoPj[] | null } | { fase: "erro" };

/** A página: o campo do CNPJ ou do nome; com um CNPJ na URL, tudo o que o Lumen tem dele; com um nome, os achados. */
export function PainelPessoaJuridica() {
  const params = useSearchParams();
  const router = useRouter();
  const cnpj = cnpjDoTexto(params.get("cnpj") ?? "");
  const termo = cnpj ? "" : (params.get("busca") ?? "").trim();
  const [texto, setTexto] = useState(cnpj ? formatarCnpj(cnpj) : termo);
  const [estado, setEstado] = useState<Estado>({ fase: "carregando" });
  const [nomes, setNomes] = useState<Nomes>(new Map());

  useEffect(() => {
    if (!cnpj) return;
    const c = new AbortController();
    setEstado({ fase: "carregando" });
    carregarPessoaJuridica(cnpj, c.signal)
      .then((dados) => setEstado({ fase: "pronto", dados }))
      .catch((e: Error) => {
        if (e.name !== "AbortError") setEstado({ fase: "erro", erro: e.message });
      });
    return () => c.abort();
  }, [cnpj]);

  useEffect(() => {
    carregarEntes()
      .then((entes) => setNomes(new Map(entes.map((e) => [e.codigo, { nome: e.nome, uf: e.uf }]))))
      .catch(() => undefined);
  }, []);

  const buscar = (e: FormEvent) => {
    e.preventDefault();
    const c = cnpjDoTexto(texto);
    if (c) router.push(`/pessoa-juridica/?cnpj=${c}`);
    else if (texto.trim()) router.push(`/pessoa-juridica/?busca=${encodeURIComponent(texto.trim())}`);
  };

  return (
    <>
      <form className="cartao cartao-corpo filtro-periodo" onSubmit={buscar} aria-label="Buscar pelo CNPJ ou pelo nome">
        <label className="filtro-periodo-titulo" htmlFor="campo-cnpj">CNPJ ou nome</label>
        <input id="campo-cnpj" className="seletor campo-pj" placeholder="00.000.000/0000-00 ou parte do nome"
          value={texto} onChange={(e) => setTexto(e.target.value)} />
        <button type="submit" className="botao" disabled={!texto.trim()}>Ver</button>
      </form>
      {cnpj ? (
        <Pessoa cnpj={cnpj} estado={estado} nomes={nomes} />
      ) : termo ? (
        <Achados termo={termo} />
      ) : (
        <Situacao>
          Escreva o CNPJ ou parte do nome de uma empresa ou entidade, ou chegue aqui pelo nome dela nas outras abas.
        </Situacao>
      )}
    </>
  );
}

/** Os nomes achados pela busca, cada um com o link para a página do CNPJ. */
function Achados({ termo }: { termo: string }) {
  const [estado, setEstado] = useState<EstadoBusca>({ fase: "procurando" });
  useEffect(() => {
    let vale = true;
    setEstado({ fase: "procurando" });
    buscarPessoasJuridicas(termo)
      .then((achados) => vale && setEstado({ fase: "pronta", achados }))
      .catch(() => vale && setEstado({ fase: "erro" }));
    return () => {
      vale = false;
    };
  }, [termo]);

  if (estado.fase === "procurando") return <Situacao>Procurando…</Situacao>;
  if (estado.fase === "erro") return <Situacao>Não foi possível procurar agora.</Situacao>;
  if (estado.achados === null) return <Situacao>A busca pelo nome ainda não foi publicada; use o CNPJ.</Situacao>;
  if (estado.achados.length === 0) {
    return (
      <Situacao>
        Nenhum nome com todas essas palavras. A busca procura pelo começo das palavras, com três letras ou mais.
      </Situacao>
    );
  }
  return (
    <section className="cartao cartao-corpo" aria-labelledby="titulo-achados">
      <h2 id="titulo-achados" className="titulo-secao">Nomes com “{termo}”</h2>
      <ul className="lista-simples">
        {estado.achados.map((a) => (
          <li key={a.cnpj}>
            <Link href={`/pessoa-juridica/?cnpj=${a.cnpj}`}>{a.nome ?? formatarCnpj(a.cnpj)}</Link>
            <span className="busca-detalhe"> · {formatarCnpj(a.cnpj)} · {moedaCompacta(a.peso)} em contratos, emendas e convênios</span>
          </li>
        ))}
      </ul>
      <p className="busca-detalhe">
        Do maior valor ao menor, até {estado.achados.length >= 20 ? "os 20 primeiros" : "o fim da lista"}. Para
        estreitar, acrescente outra palavra do nome.
      </p>
    </section>
  );
}

/** O que há do CNPJ: o cartão da Receita e as três seções das fontes. */
function Pessoa({ cnpj, estado, nomes }: { cnpj: string; estado: Estado; nomes: Nomes }) {
  if (estado.fase === "carregando") return <Situacao>Carregando…</Situacao>;
  if (estado.fase === "erro") return <Situacao>Não foi possível ler agora ({estado.erro}).</Situacao>;
  const p = estado.dados;
  return (
    <>
      <h2 className="painel-ente">
        {p?.nome ?? formatarCnpj(cnpj)}
        <span className="busca-detalhe"> · CNPJ {formatarCnpj(cnpj)}</span>
      </h2>
      <EmpresaReceitaCartao cnpj={cnpj} />
      {!p ? (
        <Situacao>
          Nenhum contrato no PNCP ou no tribunal de contas, emenda parlamentar ou convênio com a União com este CNPJ
          nos dados do Lumen.
        </Situacao>
      ) : (
        <>
          <Contratos p={p} nomes={nomes} />
          <ContratosTce p={p} nomes={nomes} />
          <Emendas p={p} nomes={nomes} />
          <Convenios p={p} nomes={nomes} />
          <p className="busca-detalhe">
            Contratos publicados no PNCP com este CNPJ como fornecedor, somados como no painel de contratações;
            emendas e convênios do Portal da Transparência (arquivos de {dataDoArquivo(p.fontes.emendas)} e de{" "}
            {dataDoArquivo(p.fontes.convenios)}). São os fatos como as fontes publicam, sem juízo sobre a empresa ou
            a entidade.{" "}
            <a href={METODO} target="_blank" rel="noreferrer">como é montado</a>
          </p>
        </>
      )}
    </>
  );
}

/** "Porto Alegre (RS)", "São Paulo (estado)", "Distrito Federal", "União" ou o código. */
function nomeDoEnte(codigo: string, nomes: Nomes): string {
  const e = nomes.get(codigo);
  const tipo = tipoDoCodigo(codigo);
  if (!e) return tipo === "uniao" ? "União" : codigo;
  if (tipo === "municipio" && e.uf) return `${e.nome} (${e.uf})`;
  return tipo === "estado" ? `${e.nome} (estado)` : e.nome;
}

/** Contratos no PNCP: os totais, o ano a ano e a tabela por ente contratante. */
function Contratos({ p, nomes }: { p: PessoaJuridica; nomes: Nomes }) {
  const t = totaisDaPessoa(p);
  const porAno = contratosPorAno(p);
  return (
    <section className="cartao cartao-corpo" aria-labelledby="titulo-pj-contratos">
      <h2 id="titulo-pj-contratos" className="titulo-secao">Contratos publicados no PNCP</h2>
      {t.contratos === 0 ? (
        <p className="busca-detalhe">Nenhum contrato no PNCP com este CNPJ como fornecedor no período coberto.</p>
      ) : (
        <>
          <p>
            {numero(t.contratos)} contrato(s), {moeda(t.valorContratos)}, com {numero(t.entesContratantes)} ente(s).
          </p>
          {porAno.length > 1 && (
            <GraficoBarras titulo="Valor dos contratos por ano de publicação"
              barras={porAno.map((a) => ({ rotulo: a.ano, valor: a.valor }))} formatar={moeda} formatarEixo={moedaCompacta} />
          )}
          <TabelaPorEnte linhas={contratosPorEnte(p)} nomes={nomes} contratos
            href={(ente) => `/contratacoes/?ente=${ente}&forn=${p.cnpj}`} />
        </>
      )}
    </section>
  );
}

/** Contratos registrados no tribunal de contas (ADR-050), por ente; só aparece quando há algum. */
function ContratosTce({ p, nomes }: { p: PessoaJuridica; nomes: Nomes }) {
  if (!p.tce?.length) return null;
  const t = totaisDaPessoa(p);
  return (
    <section className="cartao cartao-corpo" aria-labelledby="titulo-pj-tce">
      <h2 id="titulo-pj-tce" className="titulo-secao">Contratos registrados no tribunal de contas</h2>
      <p>
        {numero(t.contratosTce)} contrato(s), {moeda(t.valorTce)}, registrados pelos órgãos públicos nos sistemas
        dos{" "}
        <a href="https://github.com/Dracon-46/FalkyriaLumen/wiki/Tribunais-de-Contas" target="_blank" rel="noreferrer">
          tribunais de contas que o Lumen já lê
        </a>
        .
      </p>
      <TabelaPorEnte linhas={tcePorEnte(p)} nomes={nomes} contratos
        href={(ente) => (tipoDoCodigo(ente) === "municipio" ? `/economia/municipio/?ente=${ente}` : null)} />
      <p className="busca-detalhe">
        Pelo ano do contrato. A partir de 2021, parte destes contratos é a mesma publicada no PNCP, acima: as duas
        fontes ficam lado a lado e não se somam.
      </p>
    </section>
  );
}

/** Emendas parlamentares recebidas como favorecida, por ente. */
function Emendas({ p, nomes }: { p: PessoaJuridica; nomes: Nomes }) {
  if (p.emendas.length === 0) return null;
  const t = totaisDaPessoa(p);
  return (
    <section className="cartao cartao-corpo" aria-labelledby="titulo-pj-emendas">
      <h2 id="titulo-pj-emendas" className="titulo-secao">Emendas parlamentares recebidas</h2>
      <p>{moeda(t.emendas)} pagos a este CNPJ como favorecido, pelo ano do pagamento.</p>
      <TabelaPorEnte linhas={emendasPorEnte(p)} nomes={nomes}
        href={(ente) => (tipoDoCodigo(ente) === "municipio" ? `/economia/municipio/?ente=${ente}` : null)} />
    </section>
  );
}

/** A tabela de somas por ente, com o link de cada um; as primeiras linhas e, a pedido, todas. */
function TabelaPorEnte({ linhas, nomes, contratos = false, href }: {
  linhas: PorEnte[]; nomes: Nomes; contratos?: boolean; href: (ente: string) => string | null;
}) {
  const [todas, setTodas] = useState(false);
  const mostradas = todas ? linhas : linhas.slice(0, ENTES_INICIAIS);
  return (
    <>
      <div className="tabela-rolavel">
        <table className="tabela">
          <thead>
            <tr>
              <th>Ente</th>
              {contratos && <th className="n">Contratos</th>}
              <th className="n">Valor</th>
              <th>Anos</th>
            </tr>
          </thead>
          <tbody>
            {mostradas.map((l) => {
              const destino = href(l.ente);
              const nome = nomeDoEnte(l.ente, nomes);
              return (
                <tr key={l.ente}>
                  <td>{destino ? <Link href={destino}>{nome}</Link> : nome}</td>
                  {contratos && <td className="n">{numero(l.contratos)}</td>}
                  <td className="n">{moeda(l.valor)}</td>
                  <td>{l.anos.join(", ")}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {linhas.length > ENTES_INICIAIS && (
        <button type="button" className="botao-link" onClick={() => setTodas(!todas)}>
          {todas ? `mostrar só os ${ENTES_INICIAIS} primeiros` : `ver todos os ${numero(linhas.length)} entes`}
        </button>
      )}
    </>
  );
}

/** Convênios com a União como convenente, do maior valor ao menor. */
function Convenios({ p, nomes }: { p: PessoaJuridica; nomes: Nomes }) {
  if (p.convenios.length === 0) return null;
  const t = totaisDaPessoa(p);
  const lista = [...p.convenios].sort((a, b) => b[5] - a[5]).slice(0, CONVENIOS_LISTADOS);
  return (
    <section className="cartao cartao-corpo" aria-labelledby="titulo-pj-convenios">
      <h2 id="titulo-pj-convenios" className="titulo-secao">Convênios com a União</h2>
      <p>
        {numero(t.convenios)} convênio(s) como convenente, {moeda(t.valorConvenios)} conveniados e{" "}
        {moeda(t.liberado)} liberados, de 2001 em diante.
        {p.convenios.length > CONVENIOS_LISTADOS && ` Abaixo, os ${CONVENIOS_LISTADOS} de maior valor.`}
      </p>
      <div className="tabela-rolavel">
        <table className="tabela">
          <thead>
            <tr>
              <th>Ente</th>
              <th>Convênio</th>
              <th>Situação no SIAFI</th>
              <th>Início</th>
              <th className="n">Valor</th>
              <th className="n">Liberado</th>
            </tr>
          </thead>
          <tbody>
            {lista.map(([ente, numeroConvenio, situacao, objeto, orgao, valor, liberado, inicio]) => (
              <tr key={`${ente}-${numeroConvenio}`}>
                <td>{nomeDoEnte(ente, nomes)}</td>
                <td>
                  {numeroConvenio} · {objeto}
                  <div className="busca-detalhe">{orgao}</div>
                </td>
                <td>{situacao}</td>
                <td>{dataCurta(inicio)}</td>
                <td className="n">{moeda(valor)}</td>
                <td className="n">{moeda(liberado)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
