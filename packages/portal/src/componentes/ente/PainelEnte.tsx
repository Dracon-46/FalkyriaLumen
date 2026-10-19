"use client";

/**
 * Visão 360 de um ente (ADR-035): a União, um estado, o DF ou um município, com tudo o que o Lumen publica sobre
 * ele num lugar só. Eleições (o último prefeito ou governador e o último presidente, com o mapa e as zonas),
 * contratações no PNCP (com os documentos de cada publicação para baixar), entregas da LRF, o portal de
 * transparência avaliado pelo PNTP e as estatais que ele controla. Cada seção lê o arquivo da própria área e
 * leva à página completa; uma seção que falha não derruba as outras.
 *
 * A URL é `/ente/?codigo=<código IBGE>` (1 para a União).
 */

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { type ReactNode, useEffect, useState } from "react";
import { BuscaEnte, Numero, SeloResultado } from "@/componentes/paineis/Comuns";
import { Documentos } from "@/componentes/paineis/Documentos";
import { Paginacao, usePaginacao } from "@/componentes/Paginacao";
import {
  carregarTransparencia,
  eleicoesDoEnte,
  estataisDoEnte,
  type EntidadeTransparencia,
  federaisDaSest,
  type FeedTransparencia,
  type ResultadoDoEnte,
  urlDoEnte,
} from "@/lib/ente360";
import { carregarEstatais, type CompanhiaCvm, ROTULO_CONTROLE, valorCvm } from "@/lib/estatais";
import { carregarFeed, carregarIndice, carregarIndiceZonas } from "@/lib/feeds";
import { escreverSelecao } from "@/lib/estado-url";
import { instante, numero, percentual } from "@/lib/formato";
import {
  carregarConformidadeEnte,
  carregarContratacoesEnte,
  carregarEntes,
  cnpj,
  type ConformidadeEnte,
  type ContratacoesEnte,
  dataCurta,
  descreverEnte,
  type EnteBusca,
  moeda,
  moedaCompacta,
  tipoDoCodigo,
} from "@/lib/paineis";
import type { FeedResultado } from "@/lib/tipos";

type Carga<T> = { fase: "carregando" } | { fase: "pronto"; dados: T } | { fase: "erro"; erro: string };

/** Carrega `fn` quando `chave` muda; cancela a leitura anterior. */
function useCarga<T>(chave: string | null, fn: (sinal: AbortSignal) => Promise<T>): Carga<T> {
  const [estado, setEstado] = useState<Carga<T>>({ fase: "carregando" });
  useEffect(() => {
    if (chave === null) return;
    const c = new AbortController();
    setEstado({ fase: "carregando" });
    fn(c.signal)
      .then((dados) => setEstado({ fase: "pronto", dados }))
      .catch((e: Error) => {
        if (e.name !== "AbortError") setEstado({ fase: "erro", erro: e.message });
      });
    return () => c.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chave]);
  return estado;
}

/** Uma seção da página: título, o link para a área completa e o conteúdo (ou o estado da carga). */
function Secao<T>({ id, titulo, area, carga, children }: {
  id: string; titulo: string; area?: { href: string; rotulo: string }; carga: Carga<T>;
  children: (dados: T) => ReactNode;
}) {
  return (
    <section className="cartao cartao-corpo ente-secao" aria-labelledby={`ente-${id}`}>
      <div className="ente-secao-topo">
        <h2 id={`ente-${id}`} className="titulo-secao">{titulo}</h2>
        {area && <Link href={area.href} className="botao-link">{area.rotulo} ›</Link>}
      </div>
      {carga.fase === "carregando" && <p className="busca-detalhe">Carregando…</p>}
      {carga.fase === "erro" && <p className="busca-detalhe">Não foi possível ler agora ({carga.erro}).</p>}
      {carga.fase === "pronto" && children(carga.dados)}
    </section>
  );
}

/** A página inteira, a partir do `?codigo=`. */
export function PainelEnte() {
  const params = useSearchParams();
  const router = useRouter();
  const bruto = params.get("codigo");
  const codigo = bruto && /^(1|\d{2}|\d{7})$/.test(bruto) ? bruto : null;
  const tipo = codigo ? tipoDoCodigo(codigo) : null;
  const entes = useCarga<EnteBusca[]>("entes", () => carregarEntes());
  const contratacoes = useCarga<ContratacoesEnte | null>(codigo, (s) => carregarContratacoesEnte(codigo!, s));
  const conformidade = useCarga<ConformidadeEnte | null>(codigo === "1" ? null : codigo,
                                                          (s) => carregarConformidadeEnte(codigo!, s));
  // Nome, UF e população: do cadastro de entes; se ele não tiver o ente, do arquivo de contratações ou do de conformidade
  const doCadastro = entes.fase === "pronto" && codigo ? entes.dados.find((e) => e.codigo === codigo) ?? null : null;
  const doArquivo = (contratacoes.fase === "pronto" && contratacoes.dados?.ente)
    || (conformidade.fase === "pronto" && conformidade.dados?.ente) || null;
  const ente: EnteBusca | null = codigo && (doCadastro?.nome || doArquivo?.nome)
    ? { codigo, nome: doCadastro?.nome || doArquivo!.nome, uf: doCadastro?.uf ?? doArquivo?.uf ?? null,
        esfera: doCadastro?.esfera ?? null, populacao: doCadastro?.populacao ?? doArquivo?.populacao ?? null }
    : null;
  const nome = ente?.nome ?? (codigo === "1" ? "União" : null);
  const transparencia = useCarga(codigo, (s) => carregarTransparencia(codigo!, s));
  const estatais = useCarga(codigo, (s) => carregarEstatais(s));
  const eleicoes = useCarga(codigo, async (s) => {
    const indice = await carregarIndice(s);
    return indice ? eleicoesDoEnte(indice, codigo!, tipo) : [];
  });

  const ir = (c: string) => router.push(urlDoEnte(c), { scroll: true });

  if (!codigo) {
    return (
      <div className="painel">
        <div className="painel-topo">
          <h1>Visão 360 de um ente</h1>
          <BuscaEnte rotulo="Buscar estado ou município" onEscolher={ir} />
        </div>
        <p>
          Escolha a União, um estado, o DF ou um município para ver, numa página só, as eleições, as contratações (com os
          documentos para baixar), as entregas da Lei de Responsabilidade Fiscal, o portal de transparência e as
          estatais de cada um.
        </p>
        <p>
          <button type="button" className="botao" onClick={() => ir("1")}>Ver a União</button>
        </p>
      </div>
    );
  }

  return (
    <div className="painel">
      <div className="painel-topo">
        <div>
          <h1>{nome ?? `Ente ${codigo}`}</h1>
          <p className="painel-periodo">
            {ente ? descreverEnte(ente) : tipo === "uniao" ? "Governo federal" : ""}
            {ente?.populacao ? ` · ${numero(ente.populacao)} habitantes` : ""} · código IBGE {codigo}
          </p>
        </div>
        <BuscaEnte rotulo="Buscar outro estado ou município" onEscolher={ir} />
      </div>
      <nav className="ente-atalhos" aria-label="Nesta página">
        {["eleicoes", "contratacoes", "conformidade", "transparencia", "estatais"]
          .filter((id) => id !== "conformidade" || codigo !== "1").map((id) => (
          <a key={id} href={`#ente-${id}`} className="botao">
            {{ eleicoes: "Eleições", contratacoes: "Contratações", conformidade: "Conformidade",
               transparencia: "Portal de transparência", estatais: "Estatais" }[id]}
          </a>
        ))}
      </nav>
      {tipo === "municipio" && ente?.uf && ente.uf.length === 2 && (
        <p className="busca-detalhe">
          Do estado: <Link href={urlDoEnte(codigo.slice(0, 2))}>
            visão 360 de {ente.uf}
          </Link>
        </p>
      )}

      <Secao id="eleicoes" titulo="Eleições" carga={eleicoes}
             area={{ href: "/eleicoes/", rotulo: "todas as eleições" }}>
        {(lista) => (lista.length === 0
          ? <p className="busca-detalhe">Nenhuma eleição publicada para este ente.</p>
          : <div className="grade-2">{lista.map((r) => <Eleicao key={`${r.eleicao.id}-${r.cargo}`} r={r} codigo={codigo} />)}</div>)}
      </Secao>

      <Secao id="contratacoes" titulo="Contratações (PNCP)" carga={contratacoes}
             area={{ href: `/contratacoes/?ente=${codigo}`, rotulo: "painel completo" }}>
        {(dados) => (dados ? <Contratacoes dados={dados} /> : (
          <p className="busca-detalhe">Nenhuma publicação deste ente no PNCP no período já coletado.</p>
        ))}
      </Secao>

      {codigo !== "1" && (
        <Secao id="conformidade" titulo="Conformidade fiscal (LRF)" carga={conformidade}
               area={{ href: `/conformidade/?ente=${codigo}`, rotulo: "todas as obrigações" }}>
          {(dados) => (dados ? <Conformidade dados={dados} /> : (
            <p className="busca-detalhe">O extrato de entregas deste ente ainda não foi avaliado.</p>
          ))}
        </Secao>
      )}

      <Secao id="transparencia" titulo="Portal de transparência" carga={transparencia}>
        {(dados) => (dados ? <Transparencia feed={dados.feed} entidades={dados.entidades} /> : (
          <p className="busca-detalhe">A avaliação do PNTP ainda não foi publicada pelo Lumen.</p>
        ))}
      </Secao>

      <Secao id="estatais" titulo="Empresas estatais" carga={estatais}
             area={{ href: "/economia/estatais/", rotulo: "todas as estatais" }}>
        {(feed) => (feed ? <Estatais lista={estataisDoEnte(feed, nome ?? "", ente?.uf ?? null, tipo)}
                                     federais={tipo === "uniao" ? federaisDaSest(feed) : null} /> : (
          <p className="busca-detalhe">As estatais ainda não foram publicadas.</p>
        ))}
      </Secao>

      <p className="busca-detalhe">
        Cada número vem da área dele no Lumen, com a fonte e a data de coleta lá. Nada aqui é conclusão sobre o ente:
        são os dados que as fontes oficiais publicaram.
      </p>
    </div>
  );
}

// ------------------------------------------------------------------------------------------ seções

/** Um resultado de eleição no ente: os três primeiros, o comparecimento e o link para o mapa (e as zonas). */
function Eleicao({ r, codigo }: { r: ResultadoDoEnte; codigo: string }) {
  const feed = useCarga<FeedResultado | null>(`${r.eleicao.id}/${r.cargo}/${r.abrangencia}`, async (s) => {
    const f = await carregarFeed(r.eleicao.id, r.cargo, r.abrangencia, s, { guardar: !r.eleicao.ao_vivo });
    return f && f.tipo === "resultado" ? f : null;
  });
  const zonas = useCarga(r.abrangencia.startsWith("mu-") ? `${r.eleicao.ano}-${codigo}` : null, async () => {
    const indice = await carregarIndiceZonas(r.eleicao.ano);
    return !!indice && codigo in indice.municipios;
  });
  const href = `/eleicoes/${escreverSelecao({ eleicao: r.eleicao.id, cargo: r.cargo, abrangencia: r.abrangencia, tv: false })}`;
  return (
    <div>
      <h3 className="ente-subtitulo">{r.nomeCargo} · {r.eleicao.nome}</h3>
      {feed.fase === "carregando" && <p className="busca-detalhe">Carregando…</p>}
      {feed.fase === "erro" && <p className="busca-detalhe">Resultado indisponível agora.</p>}
      {feed.fase === "pronto" && !feed.dados && <p className="busca-detalhe">Sem resultado publicado.</p>}
      {feed.fase === "pronto" && feed.dados && (
        <>
          <ol className="ente-candidatos">
            {feed.dados.candidatos.filter((c) => c.valido).slice(0, 3).map((c) => (
              <li key={`${c.numero}-${c.nome_urna}`}>
                <strong>{c.nome_urna}</strong> ({c.partido ?? "—"}) · {percentual(c.pct)}
                {c.eleito ? " · eleito" : c.segundo_turno ? " · 2º turno" : ""}
              </li>
            ))}
          </ol>
          <p className="busca-detalhe">
            {feed.dados.totalizacao.finalizada ? "Totalização concluída" : `${percentual(feed.dados.totalizacao.pct_secoes)} das seções`}
            {" · "}
            <Link href={href}>ver no mapa{zonas.fase === "pronto" && zonas.dados ? " e por zona eleitoral" : ""}</Link>
          </p>
        </>
      )}
    </div>
  );
}

/** Os números das contratações, os maiores fornecedores e as publicações recentes com os documentos. */
function Contratacoes({ dados }: { dados: ContratacoesEnte }) {
  const t = dados.totais;
  const recentes = usePaginacao(dados.recentes);
  return (
    <>
      <p className="busca-detalhe">
        Publicações de {dataCurta(dados.cobertura.de)} a {dataCurta(dados.cobertura.ate)} · atualizado em{" "}
        {instante(dados.gerado_em)}
      </p>
      <div className="totais">
        <Numero rotulo="Processos" valor={numero(t.processos)} />
        <Numero rotulo="Valor estimado" valor={moedaCompacta(t.valor_estimado)} detalhe={moeda(t.valor_estimado)} />
        <Numero rotulo="Contratos" valor={numero(t.contratos)} />
        <Numero rotulo="Valor dos contratos" valor={moedaCompacta(t.valor_contratos)} detalhe={moeda(t.valor_contratos)} />
        <Numero rotulo="Órgãos" valor={numero(t.orgaos)} />
        <Numero rotulo="Fornecedores (PJ)" valor={numero(t.fornecedores)} />
      </div>
      {dados.fornecedores.length > 0 && (
        <>
          <h3 className="ente-subtitulo">Maiores fornecedores</h3>
          <ol className="ente-lista">
            {dados.fornecedores.slice(0, 5).map((f) => (
              <li key={f.cnpj}>
                {f.nome ?? "—"} <span className="busca-detalhe num">{cnpj(f.cnpj)}</span> ·{" "}
                <span className="num">{moedaCompacta(f.valor)}</span> em {numero(f.contratos)} contrato(s)
              </li>
            ))}
          </ol>
        </>
      )}
      <h3 className="ente-subtitulo">Processos recentes, com os documentos</h3>
      <ul className="lista-publicacoes">
        {recentes.visiveis.map((p) => (
          <li key={p.chave}>
            <div className="publicacao-cabeca">
              <span className="num">{dataCurta(p.data)}</span> · {p.modalidade ?? "Modalidade não informada"} ·{" "}
              <span className="num">{p.valor_estimado ? moeda(p.valor_estimado) : "sem valor estimado"}</span>
            </div>
            <div>{p.objeto ?? "—"}</div>
            <div className="busca-detalhe">
              {p.orgao ?? "—"}
              {p.link && (
                <>
                  {" · "}
                  <a href={p.link} target="_blank" rel="noreferrer">ver no PNCP</a>
                </>
              )}
              <Documentos chave={p.chave} link={p.link} />
            </div>
          </li>
        ))}
      </ul>
      <Paginacao {...recentes} rotulo="processos recentes" />
    </>
  );
}

/** O resumo das entregas da LRF e as obrigações que não constam. */
function Conformidade({ dados }: { dados: ConformidadeEnte }) {
  const r = dados.resumo;
  const pendentes = dados.obrigacoes.filter((o) => o.resultado === "nao_cumpre").slice(0, 5);
  return (
    <>
      <div className="totais">
        <Numero rotulo="Entregues no prazo" valor={numero(r.cumpre)}
                detalhe={r.no_prazo !== null ? `${percentual(r.no_prazo * 100)} das avaliadas` : undefined} />
        <Numero rotulo="Após o prazo" valor={numero(r.cumpre_parcialmente)} />
        <Numero rotulo="Não constam" valor={numero(r.nao_cumpre)} />
        <Numero rotulo="Indeterminadas" valor={numero(r.indeterminado)} />
      </div>
      {pendentes.length > 0 && (
        <ul className="ente-lista">
          {pendentes.map((o) => (
            <li key={`${o.exercicio}-${o.periodo}-${o.criterio}-${o.poder ?? ""}`}>
              <SeloResultado resultado={o.resultado} rotulo={o.rotulo_resultado} /> {o.rotulo} · prazo {dataCurta(o.prazo)}
            </li>
          ))}
        </ul>
      )}
      <p className="busca-detalhe">Extrato do Tesouro coletado em {dataCurta(dados.coletado_em)}.</p>
    </>
  );
}

/** As entidades do ente avaliadas pelo PNTP, com o nível e o endereço do portal. */
function Transparencia({ feed, entidades }: { feed: FeedTransparencia; entidades: EntidadeTransparencia[] }) {
  const pagina = usePaginacao(entidades);
  if (entidades.length === 0) {
    return <p className="busca-detalhe">Nenhuma entidade deste ente no ciclo {feed.ciclo} do PNTP.</p>;
  }
  return (
    <>
      <div className="tabela-rolavel">
        <table className="tabela">
          <thead>
            <tr>
              <th>Entidade</th>
              <th>Nível</th>
              <th className="n">Índice</th>
              <th>Portal</th>
            </tr>
          </thead>
          <tbody>
            {pagina.visiveis.map((e) => (
              <tr key={e.codigo_entidade}>
                <td>
                  {e.entidade}
                  <div className="busca-detalhe">{e.poder ?? "—"}</div>
                </td>
                <td>
                  {e.avaliada ? e.nivel ?? "—" : "Não avaliada"}
                  {e.nivel_anterior && e.nivel_anterior !== e.nivel && (
                    <div className="busca-detalhe">antes: {e.nivel_anterior}</div>
                  )}
                </td>
                <td className="n">{e.indice !== null ? percentual(e.indice * 100) : "—"}</td>
                <td>
                  {e.link ? (
                    <a href={e.link.startsWith("http") ? e.link : `https://${e.link}`} target="_blank" rel="noreferrer">
                      abrir o portal
                    </a>
                  ) : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Paginacao {...pagina} rotulo="entidades" />
      <p className="busca-detalhe">
        Ciclo {feed.ciclo} do{" "}
        {feed.url ? <a href={feed.url} target="_blank" rel="noreferrer">PNTP</a> : "PNTP"} (tribunais de contas e
        Atricon), coletado em {dataCurta(feed.coletado_em)}. O índice vai de 0 a 100% dos critérios avaliados.
      </p>
    </>
  );
}

/** As estatais controladas: receita e pessoal do último exercício, e o link da página das estatais. */
function Estatais({ lista, federais }: { lista: CompanhiaCvm[]; federais: number | null }) {
  return (
    <>
      {lista.length === 0 && federais === null && (
        <p className="busca-detalhe">Nenhuma companhia aberta com controle público deste ente nos dados da CVM.</p>
      )}
      {lista.length > 0 && (
        <ul className="ente-lista">
          {lista.map((c) => {
            const ano = Object.keys(c.exercicios).sort().pop();
            return (
              <li key={c.cnpj}>
                <Link href={`/economia/estatais/?fonte=cvm&q=${encodeURIComponent(c.cnpj)}`}>{c.nome}</Link>
                <span className="busca-detalhe">
                  {" "}· {ROTULO_CONTROLE[c.controle.classe]}
                  {ano ? ` · ${ano}: receita ${moedaCompacta(valorCvm(c, ano, "receita"))}, pessoal ${moedaCompacta(valorCvm(c, ano, "pessoal"))}` : ""}
                </span>
              </li>
            );
          })}
        </ul>
      )}
      {federais !== null && (
        <p>
          <Link href="/economia/estatais/">{numero(federais)} empresas estatais federais</Link> no cadastro da SEST, com o
          orçamento aprovado e o realizado de cada uma.
        </p>
      )}
      <p className="busca-detalhe">
        Companhias abertas pela esfera do controlador declarado no Formulário de Referência e pela sede; uma estatal com
        sede em outro lugar pode ficar de fora.
      </p>
    </>
  );
}
