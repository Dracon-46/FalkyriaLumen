"use client";

/**
 * Painel da aba Eleições: lê a seleção da URL, carrega índice e feeds e monta
 * a tela (mapa, gráfico de evolução, totais, candidatos ou panorama). O
 * portal nunca fala com o TSE: tudo vem dos arquivos que o coletor grava.
 * Ao vivo, o feed é relido a cada 15 s enquanto a aba do navegador está
 * visível — sem WebSocket, só revalidação HTTP (ver `feeds.ts`).
 */

import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { type Achado } from "@/lib/busca";
import { escreverSelecao, lerSelecao } from "@/lib/estado-url";
import {
  carregarFeed,
  carregarHistorico,
  carregarIndice,
  carregarMunicipios,
  INTERVALO_AO_VIVO_MS,
  urls,
} from "@/lib/feeds";
import { dataPorExtenso, haQuanto, instante, percentual } from "@/lib/formato";
import { cargoNaAbrangencia, escolherCargo, escolherEleicao, gruposDeEleicoes, tipoDeTela } from "@/lib/selecao";
import type { CargoFeed, EleicaoIndice, Feed, FeedHistorico, Indice, Municipio, Parte, Selecao } from "@/lib/tipos";
import { ErroFeed } from "@/lib/validacao";
import { Busca } from "./Busca";
import { Faixas, Origem } from "./Faixas";
import { GraficoEvolucao } from "./GraficoEvolucao";
import { ListaCandidatos } from "./ListaCandidatos";
import { Mapa } from "./Mapa";
import { Panorama } from "./Panorama";
import { Totais } from "./Totais";

/**
 * Última leitura de um feed. A `chave` ("eleição/cargo/abrangência") diz a
 * que seleção os dados pertencem, para a tela não exibir números de outra.
 */
interface EstadoFeed {
  chave: string;
  feed: Feed | null;
  /** Mensagem da leitura que falhou; na mesma chave, `feed` mantém os números da leitura anterior. */
  erro: string | null;
}

/**
 * Contador que avança a cada `intervalo` ms enquanto `ativo`; os efeitos que
 * dependem dele releem os dados. Com a aba do navegador em segundo plano o
 * contador não avança, e nada é baixado sem ninguém olhando.
 */
function useRelogio(ativo: boolean, intervalo: number): number {
  const [tique, setTique] = useState(0);
  useEffect(() => {
    if (!ativo) return;
    const id = window.setInterval(() => {
      if (document.visibilityState === "visible") setTique((t) => t + 1);
    }, intervalo);
    return () => window.clearInterval(id);
  }, [ativo, intervalo]);
  return tique;
}

/** Carrega um feed por chave, mantendo o anterior na tela enquanto o novo chega. */
function useFeed(chave: string | null, carregar: (sinal: AbortSignal) => Promise<Feed | null>, tique: number) {
  const [estado, setEstado] = useState<EstadoFeed | null>(null);
  useEffect(() => {
    if (!chave) {
      setEstado(null);
      return;
    }
    const controle = new AbortController();
    carregar(controle.signal)
      .then((feed) => setEstado({ chave, feed, erro: null }))
      .catch((e: Error) => {
        if (e.name === "AbortError") return;
        setEstado((anterior) => ({
          chave,
          // Falha numa atualização ao vivo: mantém os números anteriores e avisa
          feed: anterior?.chave === chave ? anterior.feed : null,
          erro: e instanceof ErroFeed ? e.message : "falha ao carregar os dados",
        }));
      });
    return () => controle.abort();
    // `carregar` muda a cada render; a chave e o relógio decidem quando buscar de novo.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chave, tique]);
  return estado;
}

/** Nome para o título: "Brasil", o nome que o feed traz ou, antes de ele chegar, o código em maiúsculas. */
function nomeAbrangencia(abr: string, feed: Feed | null): string {
  if (abr === "br") return "Brasil";
  return feed?.abrangencia.nome ?? abr.replace(/^(uf|mu)-/, "").toUpperCase();
}

/**
 * A URL é o estado: toda navegação (eleição, cargo, abrangência, modo TV)
 * troca os parâmetros com `router.replace`, e a tela se recalcula a partir
 * deles. No município, o mapa é o da UF, lido do feed da UF. Atalhos:
 * Ctrl+K ou "/" abre a busca; "t" alterna o modo TV (tema escuro e rodízio
 * de cargos a cada 30 s); Esc sai dele.
 */
export function PainelEleicoes() {
  const router = useRouter();
  const params = useSearchParams();
  const selecao = useMemo(() => lerSelecao(new URLSearchParams(params?.toString() ?? "")), [params]);

  const [indice, setIndice] = useState<Indice | null | undefined>(undefined);
  const [erroIndice, setErroIndice] = useState<string | null>(null);
  const [buscaAberta, setBuscaAberta] = useState(false);
  const [municipios, setMunicipios] = useState<Municipio[]>([]);

  const algumaAoVivo = !!indice?.eleicoes.some((e) => e.ao_vivo);
  const tiqueIndice = useRelogio(algumaAoVivo, 60_000);
  useEffect(() => {
    const controle = new AbortController();
    carregarIndice(controle.signal)
      .then((i) => {
        setIndice(i);
        setErroIndice(null);
      })
      .catch((e: Error) => {
        if (e.name !== "AbortError") setErroIndice(e.message);
      });
    return () => controle.abort();
  }, [tiqueIndice]);

  const eleicao: EleicaoIndice | null = indice ? escolherEleicao(indice, selecao.eleicao) : null;
  const cargo: CargoFeed | null = eleicao ? escolherCargo(eleicao, selecao.cargo) : null;
  const abrangencia = selecao.abrangencia;
  const aoVivo = !!eleicao?.ao_vivo;
  const tique = useRelogio(aoVivo, INTERVALO_AO_VIVO_MS);

  const navegar = useCallback(
    (mudanca: Partial<Selecao>) => {
      const s: Selecao = { ...selecao, eleicao: eleicao?.id ?? null, cargo: cargo?.slug ?? null, ...mudanca };
      router.replace(`/eleicoes/${escreverSelecao(s)}`, { scroll: false });
    },
    [router, selecao, eleicao?.id, cargo?.slug],
  );

  const chaveFeed = eleicao && cargo ? `${eleicao.id}/${cargo.slug}/${abrangencia}` : null;
  const principal = useFeed(chaveFeed, (s) => carregarFeed(eleicao!.id, cargo!.slug, abrangencia, s), tique);
  const feed = principal?.chave === chaveFeed ? principal.feed : null;
  const carregando = chaveFeed !== null && principal?.chave !== chaveFeed;

  // No município, o mapa é o da UF, com as partes do arquivo da UF
  const ufDoMunicipio = abrangencia.startsWith("mu-") ? (feed?.abrangencia.uf ?? null) : null;
  const chaveMapa = eleicao && cargo && ufDoMunicipio ? `${eleicao.id}/${cargo.slug}/uf-${ufDoMunicipio}` : null;
  const doMapa = useFeed(chaveMapa, (s) => carregarFeed(eleicao!.id, cargo!.slug, `uf-${ufDoMunicipio}`, s), tique);

  const [historico, setHistorico] = useState<FeedHistorico | null>(null);
  // Evolução da apuração: não existe para as eleições de 1933 a 1990, publicadas só com o resultado final
  const comEvolucao =
    !!feed &&
    feed.tipo === "resultado" &&
    !abrangencia.startsWith("mu-") &&
    cargo?.tipo !== "proporcional" &&
    eleicao?.municipios !== false;
  useEffect(() => {
    if (!comEvolucao || !eleicao || !cargo) {
      setHistorico(null);
      return;
    }
    const controle = new AbortController();
    carregarHistorico(eleicao.id, cargo.slug, abrangencia, controle.signal)
      .then(setHistorico)
      .catch(() => setHistorico(null));
    return () => controle.abort();
  }, [comEvolucao, eleicao?.id, cargo?.slug, abrangencia, tique]); // eslint-disable-line react-hooks/exhaustive-deps

  // Atalhos: Ctrl+K ou "/" abre a busca; "t" liga o modo TV; Esc sai dele
  useEffect(() => {
    const tecla = (e: KeyboardEvent) => {
      const digitando = e.target instanceof HTMLInputElement || e.target instanceof HTMLSelectElement;
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setBuscaAberta(true);
      } else if (!digitando && e.key === "/") {
        e.preventDefault();
        setBuscaAberta(true);
      } else if (!digitando && e.key.toLowerCase() === "t" && !e.ctrlKey && !e.metaKey && !e.altKey) {
        navegar({ tv: !selecao.tv });
      } else if (e.key === "Escape" && selecao.tv) {
        navegar({ tv: false });
      }
    };
    window.addEventListener("keydown", tecla);
    return () => window.removeEventListener("keydown", tecla);
  }, [navegar, selecao.tv]);

  useEffect(() => {
    if (buscaAberta && municipios.length === 0) {
      carregarMunicipios()
        .then((c) => setMunicipios(c?.municipios ?? []))
        .catch(() => setMunicipios([]));
    }
  }, [buscaAberta, municipios.length]);

  // Modo TV: tema escuro e, a cada 30 s, o próximo cargo disponível
  useEffect(() => {
    const raiz = document.documentElement;
    if (selecao.tv) {
      raiz.dataset.tema = "escuro";
      document.body.classList.add("tv");
    } else {
      delete raiz.dataset.tema;
      document.body.classList.remove("tv");
    }
    return () => {
      delete raiz.dataset.tema;
      document.body.classList.remove("tv");
    };
  }, [selecao.tv]);

  const ufAtual = abrangencia.startsWith("uf-") ? abrangencia.slice(3) : ufDoMunicipio;
  const cargosVisiveis = eleicao ? eleicao.cargos.filter((c) => cargoNaAbrangencia(c, ufAtual)) : [];
  useEffect(() => {
    if (!selecao.tv || cargosVisiveis.length < 2 || !cargo) return;
    const id = window.setTimeout(() => {
      const i = cargosVisiveis.findIndex((c) => c.slug === cargo.slug);
      const proximo = cargosVisiveis[(i + 1) % cargosVisiveis.length];
      if (proximo) navegar({ cargo: proximo.slug });
    }, 30_000);
    return () => window.clearTimeout(id);
  }, [selecao.tv, cargo, cargosVisiveis, navegar]);

  // Eleição só por UF (1933 a 1990): o município escolhido na busca leva ao resultado do estado dele
  const porMunicipio = eleicao?.municipios !== false;
  const escolherBusca = (a: Achado) =>
    navegar({ abrangencia: a.tipo === "mu" && !porMunicipio ? `uf-${a.uf}` : a.abrangencia });

  // ------------------------------------------------------------ estados vazios

  if (indice === undefined && !erroIndice) return <p>Carregando…</p>;
  if (erroIndice || !indice || !eleicao || !cargo) {
    return (
      <div className="texto-corrido">
        <h1>Eleições</h1>
        <p>
          {erroIndice
            ? `Os dados das eleições não puderam ser lidos (${erroIndice}).`
            : "Nenhuma eleição foi publicada neste servidor ainda."}
        </p>
        <p>
          Os resultados chegam aqui pelo coletor do Lumen: <code>lumen eleicoes preparar</code> carrega tudo, de 1933
          até a última eleição (no Windows, dois cliques em <code>preparar.cmd</code>);{" "}
          <code>lumen eleicoes ao-vivo</code> acompanha a noite da apuração; <code>lumen eleicoes amostra</code> gera
          uma amostra de desenvolvimento.
        </p>
      </div>
    );
  }

  const tela = tipoDeTela(cargo, abrangencia);
  const nomeAbr = nomeAbrangencia(abrangencia, feed);
  const nivelMapa: "uf" | "mu" = abrangencia === "br" ? "uf" : "mu";
  const ufMapa = abrangencia.startsWith("uf-") ? abrangencia.slice(3) : ufDoMunicipio;
  const malha =
    abrangencia === "br"
      ? urls.malhaBrasil()
      : porMunicipio && ufMapa && ufMapa !== "zz"
        ? urls.malhaUf(ufMapa)
        : null;
  const feedMapa = abrangencia.startsWith("mu-") ? (doMapa?.feed ?? null) : feed;
  const rotuloLider = (p: Parte) =>
    feedMapa?.tipo === "panorama" || cargo.tipo === "proporcional"
      ? p.nome_urna
        ? `${p.nome_urna} (${p.partido ?? "—"})`
        : (p.partido ?? p.lider ?? "—")
      : (p.nome_urna ?? p.lider ?? "—");
  const selecionarParte = (p: Parte) =>
    navegar({ abrangencia: nivelMapa === "uf" ? `uf-${p.codigo}` : `mu-${p.codigo}` });

  const progresso =
    feed?.tipo === "resultado" ? feed.totalizacao.pct_secoes : feed?.tipo === "panorama" ? feed.totalizacao.pct_partes : null;
  const finalizada = feed?.tipo === "resultado" ? feed.totalizacao.finalizada : !feed?.ao_vivo;
  const tituloMapa =
    tela === "panorama"
      ? `${cargo.nome}: quem está à frente em cada ${nivelMapa === "uf" ? "estado" : "município"}`
      : `${cargo.nome}: mais votado em cada ${nivelMapa === "uf" ? "estado" : "município"}`;

  return (
    <div>
      <div className="tv-cabeca">
        <h1>
          {cargo.nome} · {nomeAbr}
        </h1>
        <span>
          {eleicao.nome}
          {feed?.ao_vivo && aoVivo ? <span className="selo-vivo"> ao vivo</span> : null}
        </span>
      </div>

      <div className="controles">
        <label className="so-leitor" htmlFor="seletor-eleicao">
          Eleição
        </label>
        <select
          id="seletor-eleicao"
          className="seletor"
          value={eleicao.id}
          onChange={(e) => navegar({ eleicao: e.target.value, cargo: null, abrangencia: "br" })}
        >
          {gruposDeEleicoes(indice.eleicoes).map(([rotulo, lista]) =>
            rotulo === null ? (
              lista.map((e) => <OpcaoEleicao key={e.id} e={e} />)
            ) : (
              <optgroup key={rotulo} label={rotulo}>
                {lista.map((e) => (
                  <OpcaoEleicao key={e.id} e={e} />
                ))}
              </optgroup>
            ),
          )}
        </select>
        <button type="button" className="botao" onClick={() => setBuscaAberta(true)}>
          Buscar estado ou município <span className="tecla so-largo">Ctrl K</span>
        </button>
        <button
          type="button"
          className="botao so-largo"
          onClick={() => navegar({ tv: true })}
          title="Tela cheia para televisão (tecla T)"
        >
          Modo TV
        </button>
      </div>

      <div className="cargos so-tela" role="tablist" aria-label="Cargo">
        {cargosVisiveis.map((c) => (
          <button
            key={c.slug}
            type="button"
            role="tab"
            className="cargo"
            aria-selected={c.slug === cargo.slug}
            onClick={() => navegar({ cargo: c.slug })}
          >
            {c.nome}
          </button>
        ))}
      </div>

      <nav className="trilha so-tela" aria-label="Onde você está">
        {abrangencia === "br" ? (
          <span aria-current="location">Brasil</span>
        ) : (
          <button type="button" onClick={() => navegar({ abrangencia: "br" })}>
            Brasil
          </button>
        )}
        {ufMapa && (
          <>
            <span aria-hidden="true">›</span>
            {abrangencia.startsWith("uf-") ? (
              <span aria-current="location">{nomeAbr}</span>
            ) : (
              <button type="button" onClick={() => navegar({ abrangencia: `uf-${ufMapa}` })}>
                {doMapa?.feed?.abrangencia.nome ?? ufMapa.toUpperCase()}
              </button>
            )}
          </>
        )}
        {abrangencia.startsWith("mu-") && (
          <>
            <span aria-hidden="true">›</span>
            <span aria-current="location">{nomeAbr}</span>
          </>
        )}
      </nav>

      <div className="situacao">
        {feed?.ao_vivo && aoVivo && <span className="selo-vivo">Ao vivo</span>}
        <span>
          {eleicao.data ? `${dataPorExtenso(eleicao.data)} · ` : ""}
          {feed?.atualizado_em ? `Atualizado em ${instante(feed.atualizado_em)}` : ""}
          {feed?.atualizado_em && aoVivo ? ` (${haQuanto(feed.atualizado_em)})` : ""}
        </span>
        {progresso !== null && progresso !== undefined && (
          <>
            <span className="progresso" role="progressbar" aria-valuenow={progresso} aria-valuemin={0} aria-valuemax={100}
              aria-label={tela === "panorama" ? "Totalizações concluídas" : "Seções totalizadas"}>
              <span style={{ width: `${progresso}%` }} />
            </span>
            <span className="num">
              {percentual(progresso)} {tela === "panorama" ? "das totalizações concluídas" : "das seções totalizadas"}
              {finalizada && feed?.tipo === "resultado" ? " · totalização concluída" : ""}
            </span>
          </>
        )}
      </div>

      <Faixas eleicao={eleicao} feed={feed} />
      {principal?.erro && (
        <div className="faixa" role="alert">
          Não foi possível atualizar agora ({principal.erro}). {feed ? "Os números abaixo são os da última leitura." : ""}
        </div>
      )}

      {carregando && !feed && <p>Carregando…</p>}
      {!carregando && !feed && !principal?.erro && (
        <div className="cartao cartao-corpo">
          <p>
            Não há resultado de {cargo.nome} para {nomeAbr} nesta eleição
            {abrangencia !== "br" ? " — o cargo pode não ter sido disputado aqui, ou os dados ainda não chegaram" : ""}.
          </p>
          {abrangencia !== "br" && (
            <button type="button" className="botao" onClick={() => navegar({ abrangencia: "br" })}>
              Ver o Brasil
            </button>
          )}
        </div>
      )}

      {feed && (
        <div className="grade" style={{ opacity: carregando ? 0.6 : 1 }}>
          <div className="coluna">
            {malha && feedMapa && (
              <section className="cartao cartao-corpo" aria-label={tituloMapa}>
                <h2 className="titulo-secao">{tituloMapa}</h2>
                <Mapa
                  malha={malha}
                  nivel={nivelMapa}
                  partes={feedMapa.partes}
                  selecionado={abrangencia.startsWith("mu-") ? abrangencia.slice(3) : null}
                  onSelecionar={selecionarParte}
                  rotuloLider={rotuloLider}
                  titulo={tituloMapa}
                />
              </section>
            )}
            {!malha && !porMunicipio && abrangencia !== "br" && (
              <p className="cartao cartao-corpo candidato-detalhe">
                Sem mapa por município: o TSE publica o resultado de {eleicao.ano} só por estado.
              </p>
            )}
            {historico && <GraficoEvolucao historico={historico} />}
            {feed.tipo === "resultado" && <Totais feed={feed} />}
          </div>
          <div className="coluna coluna-principal">
            {feed.tipo === "resultado" ? (
              <>
                <ListaCandidatos feed={feed} />
                {feed.partes.length > 0 && (
                  <TabelaPartes partes={feed.partes} rotulo={rotuloLider} nivel={nivelMapa} onSelecionar={selecionarParte} />
                )}
              </>
            ) : (
              <Panorama feed={feed} rotuloParte={nivelMapa === "uf" ? "estado" : "município"} onSelecionar={selecionarParte} />
            )}
          </div>
        </div>
      )}

      {feed && <Origem feed={feed} />}

      <Busca
        aberta={buscaAberta}
        municipios={municipios}
        onFechar={() => setBuscaAberta(false)}
        onEscolher={escolherBusca}
      />
    </div>
  );
}

/** Uma eleição no seletor, com a marca de ao vivo. */
function OpcaoEleicao({ e }: { e: EleicaoIndice }) {
  return (
    <option value={e.id}>
      {e.nome}
      {e.ao_vivo ? " · ao vivo" : ""}
    </option>
  );
}

/** Tabela das partes: a alternativa ao mapa para quem não usa o mapa (ou leitor de tela). */
function TabelaPartes({
  partes,
  rotulo,
  nivel,
  onSelecionar,
}: {
  partes: Parte[];
  rotulo: (p: Parte) => string;
  nivel: "uf" | "mu";
  onSelecionar: (p: Parte) => void;
}) {
  const ordenadas = [...partes].sort((a, b) => a.nome.localeCompare(b.nome, "pt-BR"));
  return (
    <details className="cartao cartao-corpo so-tela" open={partes.length <= 28}>
      <summary>
        {nivel === "uf" ? "Por estado" : "Por município"} ({partes.length})
      </summary>
      <table className="tabela" style={{ marginTop: 8 }}>
        <thead>
          <tr>
            <th>{nivel === "uf" ? "Estado" : "Município"}</th>
            <th>Mais votado</th>
            <th className="n">%</th>
            <th className="n">Seções</th>
          </tr>
        </thead>
        <tbody>
          {ordenadas.slice(0, 700).map((p) => (
            <tr key={p.codigo}>
              <td>
                <button type="button" className="botao-link" onClick={() => onSelecionar(p)}>
                  {p.nome}
                </button>
              </td>
              <td>{p.lider ? rotulo(p) : "—"}</td>
              <td className="n">{percentual(p.pct)}</td>
              <td className="n">{p.finalizada ? "100%" : percentual(p.pct_secoes)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  );
}
