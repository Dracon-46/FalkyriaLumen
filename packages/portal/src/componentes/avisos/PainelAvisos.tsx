"use client";

/**
 * Avisos (ADR-047): o que aconteceu e o que observar, por local, sem precisar abrir cada painel.
 *
 * Sem local, o Brasil: quantos avisos de cada tipo por UF e os mais recentes. Com `?ente=` (o local do
 * cabeçalho), os do ente; num estado, também os dos municípios (`?municipios=1`). Filtros na URL: o tipo
 * (`?tipo=a,b`) e, num local, o período (`?de=&ate=`, pela data do aviso). A ordem é sempre pela data, nunca por ente
 * (PUB-07). Cada aviso diz a fonte, o que observar e como contestar.
 */

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { FiltroPeriodo } from "@/componentes/FiltroPeriodo";
import { Paginacao, usePaginacao } from "@/componentes/Paginacao";
import { BuscaEnte, Numero, Situacao } from "@/componentes/paineis/Comuns";
import {
  type Aviso,
  carregarAvisosDoLocal,
  carregarPanoramaAvisos,
  lerTipos,
  type PanoramaAvisos,
  TIPOS_AVISO,
  type TipoAviso,
  urlContestar,
  urlDaContratacao,
} from "@/lib/avisos";
import { codigoDaUf } from "@/lib/local";
import { numero } from "@/lib/formato";
import { carregarEntes, dataCurta, moeda } from "@/lib/paineis";
import { lerPeriodo, noPeriodo, type PeriodoMeses } from "@/lib/periodo";

const METODOLOGIA = "https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-047.md";

/** Carregando, ou os dados (o panorama, ou a lista do local) e o erro. */
type Estado =
  | { carregando: true }
  | { carregando: false; panorama: PanoramaAvisos | null; lista: Aviso[] | null; erro: string | null };

/** Página inteira da área. */
export function PainelAvisos() {
  const params = useSearchParams();
  const router = useRouter();
  const bruto = params.get("ente");
  const ente = bruto && /^(1|\d{2}|\d{7})$/.test(bruto) ? bruto : null;
  const comMunicipios = params.get("municipios") === "1";
  const tipos = lerTipos(params.get("tipo"));
  const periodo = lerPeriodo(params);
  const [estado, setEstado] = useState<Estado>({ carregando: true });
  const [nome, setNome] = useState<string | null>(null);

  useEffect(() => {
    const c = new AbortController();
    setEstado({ carregando: true });
    const pedido = ente
      ? carregarAvisosDoLocal(ente, comMunicipios, c.signal).then((lista) => ({ panorama: null, lista }))
      : carregarPanoramaAvisos(c.signal).then((panorama) => ({ panorama, lista: panorama?.ultimos ?? null }));
    pedido
      .then((r) => setEstado({ carregando: false, ...r, erro: null }))
      .catch((e: Error) => {
        if (e.name !== "AbortError") setEstado({ carregando: false, panorama: null, lista: null, erro: e.message });
      });
    return () => c.abort();
  }, [ente, comMunicipios]);

  useEffect(() => {
    if (!ente) return setNome(null);
    if (ente === "1") return setNome("União");
    let vivo = true;
    carregarEntes().then((lista) => vivo && setNome(lista.find((e) => e.codigo === ente)?.nome ?? ente)).catch(() => undefined);
    return () => {
      vivo = false;
    };
  }, [ente]);

  const ir = (mudar: Record<string, string | null>) => {
    const novo = new URLSearchParams(params.toString());
    for (const [k, v] of Object.entries(mudar)) {
      if (v) novo.set(k, v);
      else novo.delete(k);
    }
    const q = novo.toString();
    router.replace(`/avisos/${q ? `?${q}` : ""}`, { scroll: false });
  };
  const mudarPeriodo = (p: PeriodoMeses) => ir({ de: p.de, ate: p.ate });
  const alternarTipo = (t: TipoAviso) => {
    const novo = tipos.includes(t) ? tipos.filter((x) => x !== t) : [...tipos, t];
    ir({ tipo: novo.join(",") || null });
  };

  const lista = !estado.carregando && estado.lista ? estado.lista : [];
  const filtrada = useMemo(
    () => lista.filter((a) => (tipos.length === 0 || tipos.includes(a.tipo)) && noPeriodo(a.data, periodo)),
    [lista, tipos, periodo],
  );
  const meses = useMemo(() => [...new Set(lista.map((a) => (a.data ?? "").slice(0, 7)).filter((m) => m.length === 7))], [lista]);
  const ehEstado = ente !== null && ente.length === 2;

  return (
    <div className="painel">
      <div className="painel-topo">
        <div>
          <h1>Avisos{nome ? `: ${nome}` : ""}</h1>
          <p className="painel-periodo">
            O que aconteceu e o que observar, reunido dos painéis do Lumen a partir de dados públicos.
          </p>
        </div>
        <BuscaEnte rotulo="Avisos de um estado ou município" onEscolher={(c) => ir({ ente: c, municipios: null })} />
      </div>
      <aside className="faixa aviso-metodologico" aria-label="Aviso metodológico">
        <strong>Avisos não são acusação.</strong> Cada um é um fato observado nos dados públicos (um cadastro de sanções,
        um valor publicado, um prazo da lei, uma avaliação do portal de transparência) e diz a fonte e o que conferir.
        Há explicações legítimas para quase todos. Quem é citado pode contestar pelo link do aviso: a contestação
        aparece nele na publicação seguinte, sem análise prévia.{" "}
        <a href={METODOLOGIA} target="_blank" rel="noreferrer">
          Como os avisos são gerados
        </a>
        .
      </aside>
      {ente && (
        <p className="busca-detalhe">
          <button type="button" className="botao-link" onClick={() => ir({ ente: null, municipios: null })}>
            Brasil
          </button>
          {ehEstado && (
            <>
              {" · "}
              <label>
                <input type="checkbox" checked={comMunicipios} onChange={(e) => ir({ municipios: e.target.checked ? "1" : null })} />{" "}
                incluir os municípios da UF
              </label>
            </>
          )}
        </p>
      )}
      <section className="cartao cartao-corpo avisos-tipos" aria-label="Tipos de aviso">
        <span className="filtro-periodo-titulo">Tipos</span>
        {TIPOS_AVISO.map((t) => (
          <button key={t.tipo} type="button" className="botao" aria-pressed={tipos.includes(t.tipo)} onClick={() => alternarTipo(t.tipo)}>
            {t.rotulo}
            {!estado.carregando && estado.panorama && ` (${numero(estado.panorama.por_tipo[t.tipo] ?? 0)})`}
          </button>
        ))}
        {tipos.length > 0 && (
          <button type="button" className="botao-link" onClick={() => ir({ tipo: null })}>
            todos os tipos
          </button>
        )}
      </section>
      {ente && (
        <FiltroPeriodo opcoes={meses} periodo={periodo} onMudar={mudarPeriodo}
                       nota="Só os avisos com data no período (a data do contrato, do prazo ou da avaliação)." />
      )}
      {estado.carregando && <Situacao>Carregando os avisos…</Situacao>}
      {!estado.carregando && estado.erro && <Situacao>Não foi possível ler os avisos agora ({estado.erro}).</Situacao>}
      {!estado.carregando && !estado.erro && estado.lista === null && (
        <Situacao>Os avisos ainda não foram publicados: saem na próxima atualização dos painéis.</Situacao>
      )}
      {!estado.carregando && estado.panorama && !ente && (
        <Panorama p={estado.panorama} onLugar={(lugar) => ir({ ente: lugar === "União" ? "1" : codigoDaUf(lugar) })} />
      )}
      {!estado.carregando && estado.lista && (
        <Lista avisos={filtrada} titulo={ente ? `Avisos (${numero(filtrada.length)})` : `Os mais recentes (${numero(filtrada.length)})`} />
      )}
    </div>
  );
}

/** O Brasil: totais por tipo e por UF (em ordem de UF, PUB-07). */
function Panorama({ p, onLugar }: { p: PanoramaAvisos; onLugar: (lugar: string) => void }) {
  const pagina = usePaginacao(p.por_lugar);
  return (
    <>
      <section className="cartao cartao-corpo">
        <h2 className="titulo-secao">No Brasil</h2>
        <div className="totais">
          <Numero rotulo="Avisos" valor={numero(p.total)} />
          {TIPOS_AVISO.map((t) => <Numero key={t.tipo} rotulo={t.rotulo} valor={numero(p.por_tipo[t.tipo] ?? 0)} />)}
          <Numero rotulo="Contestados" valor={numero(p.contestados)} />
        </div>
      </section>
      <section className="cartao cartao-corpo">
        <h2 className="titulo-secao">Por UF</h2>
        <div className="tabela-rolavel">
          <table className="tabela">
            <thead>
              <tr>
                <th>UF</th>
                {TIPOS_AVISO.map((t) => <th key={t.tipo} className="n">{t.rotulo}</th>)}
              </tr>
            </thead>
            <tbody>
              {pagina.visiveis.map((l) => (
                <tr key={l.lugar}>
                  <td>
                    <button type="button" className="botao-link" onClick={() => onLugar(l.lugar)}>{l.lugar}</button>
                  </td>
                  {TIPOS_AVISO.map((t) => <td key={t.tipo} className="n">{numero(l[t.tipo] ?? 0)}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Paginacao {...pagina} rotulo="UFs" />
      </section>
    </>
  );
}

/** A lista de avisos, 20 por página. */
function Lista({ avisos, titulo }: { avisos: Aviso[]; titulo: string }) {
  const pagina = usePaginacao(avisos);
  return (
    <section aria-labelledby="titulo-lista">
      <h2 id="titulo-lista" className="titulo-secao">{titulo}</h2>
      {avisos.length === 0 && <p className="busca-detalhe">Nenhum aviso com esses filtros.</p>}
      <ol className="avisos-lista">
        {pagina.visiveis.map((a) => <CartaoAviso key={a.id} a={a} />)}
      </ol>
      <Paginacao {...pagina} rotulo="avisos" />
    </section>
  );
}

/** Um aviso: o tipo, a data, o local, o que aconteceu, o detalhe, o que observar, a fonte e a contestação. */
function CartaoAviso({ a }: { a: Aviso }) {
  const contratacao = urlDaContratacao(a);
  const ente = a.ente.codigo ? `${a.ente.nome}${a.ente.uf && a.ente.tipo === "municipio" ? `/${a.ente.uf}` : ""}` : a.ente.nome;
  return (
    <li className={`cartao cartao-corpo aviso aviso-${a.tipo}`}>
      <p className="aviso-topo">
        <span className="aviso-rotulo">{a.rotulo}</span>
        <span className="busca-detalhe">
          {dataCurta(a.data)} · {ente}
          {a.orgao?.nome && a.orgao.nome !== a.ente.nome ? ` · ${a.orgao.nome}` : ""}
        </span>
      </p>
      {a.contestacao && (
        <p className="aviso-contestado" role="note">
          {a.contestacao.situacao === "em_analise" ? "Contestado, em análise" : a.contestacao.situacao === "retificado"
            ? "Contestado: o Lumen retificou o aviso" : "Contestado: a análise manteve o aviso"}
          {a.contestacao.link && <> · <a href={a.contestacao.link} target="_blank" rel="noreferrer">ver a contestação</a></>}
        </p>
      )}
      <h3 className="aviso-titulo">{a.titulo}</h3>
      {a.detalhe.length > 0 && (
        <ul className="lista-simples">
          {a.detalhe.map((d) => <li key={d}>{d}</li>)}
        </ul>
      )}
      <p><strong>O que observar:</strong> {a.observar}</p>
      <p className="aviso-links">
        {contratacao && <Link href={contratacao}>abrir a contratação</Link>}
        {a.fonte.link && <a href={a.fonte.link} target="_blank" rel="noreferrer">fonte: {a.fonte.nome}</a>}
        {a.fonte.outra && <a href={a.fonte.outra} target="_blank" rel="noreferrer">cadastro de sanções</a>}
        <a href={urlContestar(a)} target="_blank" rel="noreferrer">contestar este aviso</a>
        <span className="busca-detalhe num">código {a.id}</span>
        {a.valor !== null && a.tipo !== "valor_a_conferir" && <span className="busca-detalhe">{moeda(a.valor)}</span>}
      </p>
    </li>
  );
}
