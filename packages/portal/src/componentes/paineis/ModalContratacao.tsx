"use client";

/**
 * Modal de uma contratação (ADR-035): tudo sobre um processo ou um contrato, como o PNCP publica, pedido à API
 * na hora em que abre. No processo, os dados, os itens com o preço unitário, o vencedor e a comparação do preço
 * com outros órgãos (ADR-036), os documentos e os links do sistema de origem e do processo eletrônico; no
 * contrato, o fornecedor, os valores, a vigência, os termos aditivos, o processo de origem e os documentos. A
 * página por trás fica filtrada pelo órgão (e, no contrato, pelo fornecedor); fechar o modal mantém o filtro.
 */

import Link from "next/link";
import { Fragment, type ReactNode, useEffect, useRef, useState } from "react";
import { Paginacao, usePaginacao } from "@/componentes/Paginacao";
import {
  carregarContrato,
  carregarItens,
  carregarProcesso,
  carregarResultados,
  carregarTermos,
  type Contrato,
  type ItemProcesso,
  type Parte,
  type Processo,
  type ResultadoItem,
  type Termo,
} from "@/lib/contratacao";
import { lerChave } from "@/lib/documentos";
import { reconhecerAnp } from "@/lib/mercado";
import { numero } from "@/lib/formato";
import { cnpj, dataCurta, moeda } from "@/lib/paineis";
import { urlDaPessoa } from "@/lib/pessoaJuridica";
import { ComparacaoMercado } from "./ComparacaoMercado";
import { BotoesComparar, ComparacaoPreco, type TipoComparacao } from "./ComparacaoPreco";
import { Documentos } from "./Documentos";

/** O andamento de um pedido ao PNCP. */
type Carga<T> = { fase: "carregando" } | { fase: "pronto"; dados: T } | { fase: "erro"; erro: string };

/** Faz o pedido ao PNCP quando a chave muda e cancela o anterior. */
function useCarga<T>(chave: string, fn: (s: AbortSignal) => Promise<T>): Carga<T> {
  const [estado, setEstado] = useState<Carga<T>>({ fase: "carregando" });
  useEffect(() => {
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

/** O modal; `onAbrir` troca a publicação aberta (do contrato para o processo de origem, por exemplo). */
export function ModalContratacao({ chave, onFechar, onAbrir, onFornecedor, aConferir = false }: {
  chave: string;
  onFechar: () => void;
  onAbrir: (chave: string) => void;
  onFornecedor: (cnpj: string) => void;
  aConferir?: boolean;
}) {
  const caixa = useRef<HTMLDivElement>(null);
  const p = lerChave(chave);

  useEffect(() => {
    caixa.current?.focus();
    const tecla = (e: KeyboardEvent) => e.key === "Escape" && onFechar();
    document.addEventListener("keydown", tecla);
    const rolagem = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", tecla);
      document.body.style.overflow = rolagem;
    };
  }, [onFechar]);

  return (
    <div className="modal-fundo" role="presentation" onPointerDown={(e) => e.target === e.currentTarget && onFechar()}>
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="modal-titulo" tabIndex={-1} ref={caixa}>
        <div className="modal-topo">
          <span className="busca-detalhe num">{chave}</span>
          <button type="button" className="botao" onClick={onFechar} aria-label="Fechar (Esc)">✕ Fechar</button>
        </div>
        {!p && <p>Publicação não reconhecida.</p>}
        {aConferir && (
          <p className="faixa" role="note">
            Valor a conferir: está acima do teto de plausibilidade do Lumen e fica fora das somas dos painéis. Pode
            ser erro de digitação do órgão; confira no documento publicado.
          </p>
        )}
        {p?.tipo === "compra" && <DoProcesso chave={chave} onFornecedor={onFornecedor} />}
        {p?.tipo === "contrato" && <DoContrato chave={chave} onAbrir={onAbrir} onFornecedor={onFornecedor} />}
        <p className="busca-detalhe modal-rodape">
          Dados do Portal Nacional de Contratações Públicas, como o órgão publicou, lidos agora da API do PNCP.
          Fornecedor pessoa física aparece sem nome nem documento. Nada aqui é conclusão sobre o órgão ou o fornecedor.
        </p>
      </div>
    </div>
  );
}

/** Uma linha de campo: rótulo e valor (some quando o valor não existe). */
function Campo({ rotulo, children }: { rotulo: string; children: ReactNode }) {
  if (children === null || children === undefined || children === "") return null;
  return (
    <div className="modal-campo">
      <dt>{rotulo}</dt>
      <dd>{children}</dd>
    </div>
  );
}

/** Fornecedor: pessoa jurídica com CNPJ, o botão de filtrar e a página da empresa; pessoa física sem identificação. */
function Fornecedor({ f, onFornecedor }: { f: Parte; onFornecedor: (cnpj: string) => void }) {
  if (!f.pj || !f.cnpj) return <>Pessoa física ou estrangeira (sem identificação)</>;
  return (
    <>
      {f.nome ?? "—"} <span className="busca-detalhe num">{cnpj(f.cnpj)}</span>{" "}
      <button type="button" className="botao-link" onClick={() => onFornecedor(f.cnpj!)}>filtrar a página por ele</button>
      {" · "}
      <Link href={urlDaPessoa(f.cnpj.replace(/\D/g, ""))}>em todos os entes</Link>
    </>
  );
}

/** Mostra o aviso de carga ou de erro; pronto, desenha o conteúdo. */
function Estado<T>({ carga, children }: { carga: Carga<T>; children: (d: T) => ReactNode }) {
  if (carga.fase === "carregando") return <p className="busca-detalhe">Buscando no PNCP…</p>;
  if (carga.fase === "erro") return <p className="busca-detalhe">O PNCP não respondeu agora ({carga.erro}).</p>;
  return <>{children(carga.dados)}</>;
}

/** Os links para a publicação, só os de endereço web. */
function Links({ links }: { links: [string, string | null][] }) {
  const validos = links.filter(([, u]) => u && /^https?:\/\//.test(u));
  if (!validos.length) return null;
  return (
    <p className="modal-links">
      {validos.map(([rotulo, u]) => (
        <a key={rotulo} className="botao" href={u!} target="_blank" rel="noreferrer">{rotulo} ↗</a>
      ))}
    </p>
  );
}

/** O processo: dados, itens, documentos. */
function DoProcesso({ chave, onFornecedor }: { chave: string; onFornecedor: (cnpj: string) => void }) {
  const processo = useCarga<Processo | null>(chave, (s) => carregarProcesso(chave, s));
  const itens = useCarga<ItemProcesso[]>(`${chave}/itens`, (s) => carregarItens(chave, s));
  const p = lerChave(chave)!;
  return (
    <Estado carga={processo}>
      {(d) => d ? (
        <>
          <h2 id="modal-titulo" className="modal-titulo">{d.objeto ?? "Processo de contratação"}</h2>
          <p className="busca-detalhe">
            {[d.modalidade, d.modoDisputa, d.situacao].filter(Boolean).join(" · ")}
          </p>
          <dl className="modal-campos">
            <Campo rotulo="Valor estimado">{d.valorEstimado !== null ? moeda(d.valorEstimado) : "sem valor estimado"}</Campo>
            <Campo rotulo="Valor homologado">{d.valorHomologado !== null ? moeda(d.valorHomologado) : null}</Campo>
            <Campo rotulo="Órgão">{d.orgao.nome ?? "—"} <span className="busca-detalhe num">{cnpj(d.orgao.cnpj)}</span></Campo>
            <Campo rotulo="Unidade">
              {[d.unidade.nome, d.unidade.municipio && `${d.unidade.municipio}${d.unidade.uf ? `/${d.unidade.uf}` : ""}`]
                .filter(Boolean).join(" · ") || null}
            </Campo>
            <Campo rotulo="Número / processo">{[d.numero, d.processo].filter(Boolean).join(" · ") || null}</Campo>
            <Campo rotulo="Fundamento legal">
              {d.amparoLegal ? <>{d.amparoLegal.nome}{d.amparoLegal.descricao && <div className="busca-detalhe">{d.amparoLegal.descricao}</div>}</> : null}
            </Campo>
            <Campo rotulo="Registro de preços">{d.srp === null ? null : d.srp ? "sim" : "não"}</Campo>
            <Campo rotulo="Publicado no PNCP">{d.publicadoEm ? dataCurta(d.publicadoEm) : null}</Campo>
            <Campo rotulo="Propostas">
              {d.aberturaPropostas || d.encerramentoPropostas
                ? `${dataCurta(d.aberturaPropostas)} a ${dataCurta(d.encerramentoPropostas)}` : null}
            </Campo>
            <Campo rotulo="Informação complementar">{d.informacaoComplementar}</Campo>
          </dl>
          <Links links={[["Ver no PNCP", `https://pncp.gov.br/app/editais/${p.cnpj}/${p.ano}/${p.sequencial}`],
                         ["Sistema de origem", d.linkSistemaOrigem], ["Processo eletrônico", d.linkProcessoEletronico]]} />
          <h3 className="modal-subtitulo">Documentos</h3>
          <Documentos chave={chave} link={null} abrirJa />
          <h3 className="modal-subtitulo">Itens</h3>
          <Estado carga={itens}>{(lista) => <Itens processo={d} itens={lista} onFornecedor={onFornecedor} />}</Estado>
        </>
      ) : <p>O PNCP não tem esta publicação (pode ter sido excluída pelo órgão).</p>}
    </Estado>
  );
}

/** Os itens do processo, 20 por página, com o vencedor e a comparação de preço pedidos quando a pessoa abre. */
function Itens({ processo, itens, onFornecedor }: { processo: Processo; itens: ItemProcesso[]; onFornecedor: (cnpj: string) => void }) {
  const chave = processo.chave;
  const pagina = usePaginacao(itens);
  const [comparando, setComparando] = useState<Record<number, TipoComparacao | null>>({});
  const abrir = (n: number, t: TipoComparacao | null) => setComparando((atual) => ({ ...atual, [n]: t }));
  if (itens.length === 0) return <p className="busca-detalhe">O processo não tem itens publicados.</p>;
  return (
    <>
      <div className="tabela-rolavel">
        <table className="tabela">
          <thead>
            <tr>
              <th>Item</th>
              <th className="n">Quantidade</th>
              <th className="n">Unitário</th>
              <th className="n">Total</th>
            </tr>
          </thead>
          <tbody>
            {pagina.visiveis.map((i) => (
              <Fragment key={i.numero}>
                <tr>
                  <td>
                    <span className="num posicao">{i.numero}.</span> {i.descricao}
                    <div className="busca-detalhe">
                      {[i.tipo, i.situacao].filter(Boolean).join(" · ")}
                      {i.temResultado && <Vencedor chave={chave} item={i.numero} onFornecedor={onFornecedor} />}
                    </div>
                    <BotoesComparar item={i} aberta={comparando[i.numero] ?? null} onAbrir={(t) => abrir(i.numero, t)} />
                  </td>
                  <td className="n">{i.quantidade !== null ? `${numero(i.quantidade)} ${i.unidade ?? ""}` : "—"}</td>
                  <td className="n">{moeda(i.valorUnitario)}</td>
                  <td className="n">{moeda(i.valorTotal)}</td>
                </tr>
                {comparando[i.numero] && (
                  <tr className="linha-comparacao">
                    <td colSpan={4}>
                      {comparando[i.numero] === "orgaos" ? <ComparacaoPreco item={i} processo={processo} />
                        : <ComparacaoMercado item={i} processo={processo} produto={reconhecerAnp(i.descricao, i.unidade)!} />}
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
      <Paginacao {...pagina} rotulo="itens" />
    </>
  );
}

/** O vencedor do item, pedido ao PNCP quando a pessoa clica. */
function Vencedor({ chave, item, onFornecedor }: { chave: string; item: number; onFornecedor: (cnpj: string) => void }) {
  const [aberto, setAberto] = useState(false);
  return (
    <>
      {" · "}
      <button type="button" className="botao-link" aria-expanded={aberto} onClick={() => setAberto(!aberto)}>
        {aberto ? "fechar resultado" : "ver resultado"}
      </button>
      {aberto && <ResultadoDoItem chave={chave} item={item} onFornecedor={onFornecedor} />}
    </>
  );
}

/** O vencedor de um item, pedido ao abrir. */
function ResultadoDoItem({ chave, item, onFornecedor }: { chave: string; item: number; onFornecedor: (cnpj: string) => void }) {
  const r = useCarga<ResultadoItem[]>(`${chave}/${item}`, (s) => carregarResultados(chave, item, s));
  return (
    <span className="documentos-lista">
      <Estado carga={r}>
        {(lista) => lista.length === 0 ? "Sem resultado publicado." : (
          <>
            {lista.map((x, n) => (
              <span key={n} style={{ display: "block" }}>
                <Fornecedor f={x.fornecedor} onFornecedor={onFornecedor} /> · {numero(x.quantidade)} × {moeda(x.valorUnitario)}
                {" = "}{moeda(x.valorTotal)}{x.situacao ? ` · ${x.situacao}` : ""}
              </span>
            ))}
          </>
        )}
      </Estado>
    </span>
  );
}

/** O contrato: fornecedor, valores, vigência, termos, processo de origem e documentos. */
function DoContrato({ chave, onAbrir, onFornecedor }: { chave: string; onAbrir: (chave: string) => void;
                                                          onFornecedor: (cnpj: string) => void }) {
  const contrato = useCarga<Contrato | null>(chave, (s) => carregarContrato(chave, s));
  const termos = useCarga<Termo[]>(`${chave}/termos`, (s) => carregarTermos(chave, s));
  const p = lerChave(chave)!;
  return (
    <Estado carga={contrato}>
      {(d) => d ? (
        <>
          <h2 id="modal-titulo" className="modal-titulo">{d.objeto ?? "Contrato"}</h2>
          <p className="busca-detalhe">{[d.tipo, d.categoria].filter(Boolean).join(" · ")}</p>
          <dl className="modal-campos">
            <Campo rotulo="Fornecedor"><Fornecedor f={d.fornecedor} onFornecedor={onFornecedor} /></Campo>
            <Campo rotulo="Valor global">{d.valorGlobal !== null ? moeda(d.valorGlobal) : null}</Campo>
            <Campo rotulo="Valor inicial">{d.valorInicial !== null && d.valorInicial !== d.valorGlobal ? moeda(d.valorInicial) : null}</Campo>
            <Campo rotulo="Valor acumulado">{d.valorAcumulado ? moeda(d.valorAcumulado) : null}</Campo>
            <Campo rotulo="Assinatura">{d.assinatura ? dataCurta(d.assinatura) : null}</Campo>
            <Campo rotulo="Vigência">
              {d.vigenciaInicio || d.vigenciaFim ? `${dataCurta(d.vigenciaInicio)} a ${dataCurta(d.vigenciaFim)}` : null}
            </Campo>
            <Campo rotulo="Órgão">{d.orgao.nome ?? "—"} <span className="busca-detalhe num">{cnpj(d.orgao.cnpj)}</span></Campo>
            <Campo rotulo="Unidade">
              {[d.unidade.nome, d.unidade.municipio && `${d.unidade.municipio}${d.unidade.uf ? `/${d.unidade.uf}` : ""}`]
                .filter(Boolean).join(" · ") || null}
            </Campo>
            <Campo rotulo="Número / processo">{[d.numero, d.processo].filter(Boolean).join(" · ") || null}</Campo>
            <Campo rotulo="Processo de origem">
              {d.chaveProcesso ? (
                <button type="button" className="botao-link" onClick={() => onAbrir(d.chaveProcesso!)}>
                  abrir o processo {d.chaveProcesso}
                </button>
              ) : null}
            </Campo>
            <Campo rotulo="Informação complementar">{d.informacaoComplementar}</Campo>
          </dl>
          <Links links={[["Ver no PNCP", `https://pncp.gov.br/app/contratos/${p.cnpj}/${p.ano}/${p.sequencial}`]]} />
          <h3 className="modal-subtitulo">Documentos</h3>
          <Documentos chave={chave} link={null} abrirJa />
          <h3 className="modal-subtitulo">Termos aditivos</h3>
          <Estado carga={termos}>
            {(lista) => lista.length === 0 ? <p className="busca-detalhe">Nenhum termo aditivo publicado.</p> : (
              <ul className="lista-simples">
                {lista.map((t, n) => (
                  <li key={n}>
                    {t.tipo ?? "Termo"} {t.numero ?? ""} · {dataCurta(t.assinatura)}
                    {t.valorAcrescido ? ` · ${moeda(t.valorAcrescido)}` : ""}
                    {t.prazoAditado ? ` · ${numero(t.prazoAditado)} dias` : ""}
                    {t.objeto && <div className="busca-detalhe">{t.objeto}</div>}
                  </li>
                ))}
              </ul>
            )}
          </Estado>
        </>
      ) : <p>O PNCP não tem esta publicação (pode ter sido excluída pelo órgão).</p>}
    </Estado>
  );
}
