"use client";

/**
 * Painel de contratações (UC-01 e UC-02, ADR-028): o que cada ente publicou no PNCP.
 *
 * Sem ente na URL, mostra o Brasil; com `?ente=<código IBGE>`, a União (1), um estado, o DF ou um
 * município; com `?orgao=<CNPJ>`, um órgão só (uma prefeitura, uma câmara, uma autarquia como um serviço
 * autônomo de água e esgoto, uma fundação ou uma empresa pública). Tudo vem dos arquivos que `lumen painel publicar` gera, uma vez por dia. Nada aqui é indício:
 * são somas e listas do que os órgãos publicaram, com o link de cada publicação no PNCP.
 */

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { LigacoesDoEnte } from "@/componentes/Ligacoes";
import { EmpresaReceitaCartao } from "./EmpresaReceita";
import { TceNoEnte } from "./TceNoEnte";
import { FiltroPeriodo } from "@/componentes/FiltroPeriodo";
import { Paginacao, usePaginacao } from "@/componentes/Paginacao";
import { instante } from "@/lib/formato";
import { numero } from "@/lib/formato";
import {
  carregarContratacoesEnte,
  carregarContratacoesOrgao,
  carregarContratacoesPanorama,
  cnpj,
  dataCurta,
  mesCurto,
  moeda,
  moedaCompacta,
  tipoDoCodigo,
  type Cobertura,
  type ContratacoesEnte,
  type ContratacoesOrgao,
  type ContratacoesPanorama,
  type SecoesContratacoes,
} from "@/lib/paineis";
import {
  lerPeriodo,
  mesesDoArquivo,
  porAno,
  recortarMunicipios,
  recortarPanorama,
  recortarSecoes,
  temMesAMes,
  temRecorte,
  type PeriodoMeses,
} from "@/lib/periodo";
import { AvisoMetodologico, BuscaEnte, GraficoBarras, Numero, Situacao } from "./Comuns";
import { Documentos } from "./Documentos";
import { ModalContratacao } from "./ModalContratacao";
import { EVENTO_LOCAL } from "@/lib/local";

const CODIGO_UF: Record<string, string> = {
  RO: "11", AC: "12", AM: "13", RR: "14", PA: "15", AP: "16", TO: "17", MA: "21", PI: "22", CE: "23", RN: "24",
  PB: "25", PE: "26", AL: "27", SE: "28", BA: "29", MG: "31", ES: "32", RJ: "33", SP: "35", PR: "41", SC: "42",
  RS: "43", MS: "50", MT: "51", GO: "52", DF: "53",
};

type Estado<T> = { carregando: true } | { carregando: false; dados: T | null; erro: string | null };

/**
 * O que as listas podem fazer (ADR-035): abrir uma publicação no modal (o que também filtra a página pelo órgão
 * dela) e filtrar pelo fornecedor; e o fornecedor filtrado, se houver.
 */
const Acoes = createContext<{ abrir: (chave: string) => void; fornecedor: (cnpj: string) => void; forn: string | null }>({
  abrir: () => undefined, fornecedor: () => undefined, forn: null,
});

/** As listas só com o fornecedor filtrado: contratos, valores a conferir e a linha dele na tabela. */
function doFornecedor<T extends Omit<SecoesContratacoes, "orgaos"> & { orgaos?: SecoesContratacoes["orgaos"] }>(
  dados: T, forn: string | null): T {
  if (!forn) return dados;
  return {
    ...dados,
    fornecedores: dados.fornecedores.filter((f) => f.cnpj === forn),
    contratos_recentes: dados.contratos_recentes.filter((c) => c.fornecedor_cnpj === forn),
    a_conferir: dados.a_conferir?.filter((x) => x.tipo !== "contrato" || x.fornecedor_cnpj === forn),
  };
}

/** A publicação está entre os valores acima do teto de plausibilidade, fora das somas? */
function valorAConferir(dados: Pick<SecoesContratacoes, "recentes" | "contratos_recentes" | "a_conferir">, chave: string): boolean {
  return !!dados.a_conferir?.some((x) => x.chave === chave) || dados.recentes.some((x) => x.chave === chave && x.a_conferir)
    || dados.contratos_recentes.some((x) => x.chave === chave && x.a_conferir);
}

/** Painel de contratações, a partir do `?ente=` da URL. */
export function PainelContratacoes() {
  const params = useSearchParams();
  const router = useRouter();
  const bruto = params.get("ente");
  const ente = bruto && /^(1|\d{2}|\d{7})$/.test(bruto) ? bruto : null;
  const brutoOrgao = params.get("orgao");
  const orgao = !ente && brutoOrgao && /^\d{14}$/.test(brutoOrgao) ? brutoOrgao : null;
  const [estado, setEstado] = useState<Estado<ContratacoesEnte | ContratacoesOrgao | ContratacoesPanorama>>({
    carregando: true,
  });

  useEffect(() => {
    const c = new AbortController();
    setEstado({ carregando: true });
    const p: Promise<ContratacoesEnte | ContratacoesOrgao | ContratacoesPanorama | null> = ente
      ? carregarContratacoesEnte(ente, c.signal)
      : orgao
        ? carregarContratacoesOrgao(orgao, c.signal)
        : carregarContratacoesPanorama(c.signal);
    p.then((dados) => setEstado({ carregando: false, dados, erro: null })).catch((e: Error) => {
      if (e.name !== "AbortError") setEstado({ carregando: false, dados: null, erro: e.message });
    });
    return () => c.abort();
  }, [ente, orgao]);

  const periodo = lerPeriodo(params);
  // O período escolhido acompanha a navegação entre entes e órgãos
  const sufixo = (p: PeriodoMeses) => `${p.de ? `&de=${p.de}` : ""}${p.ate ? `&ate=${p.ate}` : ""}`;
  const ir = (codigo: string | null) =>
    router.push(codigo ? `/contratacoes/?ente=${codigo}${sufixo(periodo)}` : `/contratacoes/?${sufixo(periodo).slice(1)}`,
                { scroll: true });
  const irOrgao = (cnpj: string) => router.push(`/contratacoes/?orgao=${cnpj}${sufixo(periodo)}`, { scroll: true });
  const pub = params.get("pub");
  const forn = /^\d{14}$/.test(params.get("forn") ?? "") ? params.get("forn") : null;
  const extras = (o: { pub?: string | null; forn?: string | null }) => {
    const q = new URLSearchParams();
    const p2 = o.pub === undefined ? pub : o.pub;
    const f2 = o.forn === undefined ? forn : o.forn;
    if (p2) q.set("pub", p2);
    if (f2) q.set("forn", f2);
    const s = q.toString();
    return s ? `&${s}` : "";
  };
  // Abrir uma publicação: a página por trás vai para o órgão dela, e o modal abre por cima
  const abrir = useCallback((chave: string) => {
    const cnpjOrgao = chave.slice(0, 14);
    router.push(`/contratacoes/?orgao=${cnpjOrgao}${sufixo(periodo)}${extras({ pub: chave })}`, { scroll: false });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router, periodo.de, periodo.ate, forn]);
  const base = ente ? `ente=${ente}` : orgao ? `orgao=${orgao}` : "";
  const fecharModal = useCallback(() => {
    router.replace(`/contratacoes/?${`${base}${sufixo(periodo)}${extras({ pub: null })}`.replace(/^&/, "")}`, { scroll: false });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router, base, periodo.de, periodo.ate, forn]);
  const filtrarFornecedor = useCallback((cnpjForn: string | null) => {
    router.replace(`/contratacoes/?${`${base}${sufixo(periodo)}${extras({ pub: null, forn: cnpjForn })}`.replace(/^&/, "")}`,
                   { scroll: false });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router, base, periodo.de, periodo.ate, pub]);
  const acoes = useMemo(() => ({ abrir, fornecedor: (c: string) => filtrarFornecedor(c), forn }),
                        [abrir, filtrarFornecedor, forn]);
  const nomeForn = forn && !estado.carregando && estado.dados
    ? (estado.dados.fornecedores.find((f) => f.cnpj === forn)?.nome ?? null) : null;

  // No órgão, o local do cabeçalho passa a ser o ente dele
  useEffect(() => {
    if (estado.carregando || estado.dados?.tipo !== "contratacoes-orgao" || !estado.dados.ente) return;
    const e = estado.dados.ente;
    window.dispatchEvent(new CustomEvent(EVENTO_LOCAL, { detail: { codigo: e.codigo, nome: e.nome, uf: e.uf } }));
  }, [estado]);

  const mudarPeriodo = (p: PeriodoMeses) => {
    const consulta = `${base}${sufixo(p)}${extras({})}`.replace(/^&/, "");
    router.replace(`/contratacoes/${consulta ? `?${consulta}` : ""}`, { scroll: false });
  };

  return (
    <div className="painel">
      <div className="painel-topo">
        <h1>Contratações</h1>
        <BuscaEnte
          rotulo="Buscar ente ou órgão (ex.: Correios)"
          onEscolher={ir}
          onEscolherOrgao={irOrgao}
        />
      </div>
      <AvisoMetodologico>
        Somas e listas do que os próprios órgãos publicaram no Portal Nacional de Contratações Públicas (PNCP), pela
        data de publicação, com o link de cada processo e contrato. Valores como publicados, sem correção: valor
        sigiloso ou zerado conta como processo sem valor estimado; valor acima do teto de plausibilidade fica fora das
        somas, em &ldquo;Valores a conferir na fonte&rdquo;. Contratos com pessoa física aparecem só somados, sem nome
        nem documento. Nada aqui é conclusão sobre os entes ou os fornecedores.
      </AvisoMetodologico>
      {estado.carregando && <Situacao>Carregando…</Situacao>}
      {!estado.carregando && estado.erro && (
        <Situacao>Não foi possível ler os dados agora ({estado.erro}). Tente de novo em alguns minutos.</Situacao>
      )}
      {!estado.carregando && !estado.erro && estado.dados === null && (
        <SemDados ente={ente} orgao={orgao} onVoltar={() => ir(null)} />
      )}
      {!estado.carregando && estado.dados && (
        <FiltroDoArquivo dados={estado.dados} periodo={periodo} onMudar={mudarPeriodo} />
      )}
      {forn && (
        <p className="filtro-ativo">
          Filtrado pelo fornecedor <strong>{nomeForn ?? cnpj(forn)}</strong> ({cnpj(forn)}): contratos e valores dele{" "}
          <button type="button" className="botao-link" onClick={() => filtrarFornecedor(null)}>tirar o filtro</button>
          {" · "}
          <Link href={`/pessoa-juridica/?cnpj=${forn}`}>em todos os entes, com emendas e convênios</Link>
        </p>
      )}
      {forn && <EmpresaReceitaCartao cnpj={forn} />}
      <Acoes.Provider value={acoes}>
      {!estado.carregando && estado.dados?.tipo === "contratacoes-panorama" && (
        <Panorama dados={estado.dados} periodo={periodo} onEnte={ir} />
      )}
      {!estado.carregando && estado.dados?.tipo === "contratacoes-ente" && (
        <Ente dados={estado.dados} periodo={periodo} onEnte={ir} onOrgao={irOrgao} />
      )}
      {!estado.carregando && estado.dados?.tipo === "contratacoes-orgao" && (
        <Orgao dados={estado.dados} periodo={periodo} onEnte={ir} />
      )}
      </Acoes.Provider>
      {pub && (
        <ModalContratacao chave={pub} onFechar={fecharModal} onAbrir={abrir}
                          onFornecedor={(c) => filtrarFornecedor(c)}
                          aConferir={!estado.carregando && !!estado.dados && valorAConferir(estado.dados, pub)} />
      )}
    </div>
  );
}

/** O ente não tem arquivo: nenhuma publicação no período coletado (UC-01, exceção 4a). */
function SemDados({ ente, orgao, onVoltar }: { ente: string | null; orgao: string | null; onVoltar: () => void }) {
  return (
    <section className="cartao cartao-corpo">
      {orgao ? (
        <p>Nenhuma publicação deste CNPJ foi encontrada no PNCP no período já coletado.</p>
      ) : ente ? (
        <p>
          Nenhuma contratação deste ente foi encontrada no PNCP no período já coletado. Isso pode significar que o
          ente não publicou no PNCP ou que publica por outro meio; a situação das entregas fiscais dele está na área{" "}
          <Link href={`/conformidade/?ente=${ente}`}>Conformidade</Link>.
        </p>
      ) : (
        <p>Os dados do painel ainda não foram publicados.</p>
      )}
      {(ente || orgao) && (
        <button type="button" className="botao" onClick={onVoltar}>
          Ver o Brasil
        </button>
      )}
    </section>
  );
}

/** Duas linhas do mês a mês somadas campo a campo (para o gráfico por ano). */
function somarMes<T extends { mes: string }>(a: T, b: T): T {
  const saida = { ...a } as Record<string, unknown>;
  for (const [k, v] of Object.entries(b)) {
    if (k !== "mes" && typeof v === "number") saida[k] = Number(saida[k] ?? 0) + v;
  }
  return saida as T;
}

/** Filtro do período (o componente comum), com as opções do mês a mês do arquivo. */
function FiltroDoArquivo({
  dados,
  periodo,
  onMudar,
}: {
  dados: ContratacoesEnte | ContratacoesOrgao | ContratacoesPanorama;
  periodo: PeriodoMeses;
  onMudar: (p: PeriodoMeses) => void;
}) {
  const meses = mesesDoArquivo(dados);
  if (meses.length < 2) return null;
  if (!temMesAMes(dados)) {
    return (
      <p className="busca-detalhe">
        O filtro de período aparece na próxima atualização dos dados, quando o arquivo trouxer o mês a mês.
      </p>
    );
  }
  return (
    <FiltroPeriodo
      opcoes={meses}
      periodo={periodo}
      onMudar={onMudar}
      nota={
        <>
          Totais, gráficos e tabelas refeitos só com o período escolhido
          {meses.some((m) => m.length === 4) ? " (os anos mais antigos, publicados ano a ano, entram inteiros)" : ""}. Os
          fornecedores são os de maior valor no período coletado inteiro, reordenados no período escolhido; as listas de
          publicações recentes mostram as que caem nele.
        </>
      }
    />
  );
}

/** Linha da data da coleta e dos dias que faltam no período. */
function Periodo({ cobertura, gerado }: { cobertura: Cobertura; gerado: string }) {
  if (!cobertura.de) return null;
  return (
    <p className="painel-periodo">
      Publicações de {dataCurta(cobertura.de)} a {dataCurta(cobertura.ate)} ({numero(cobertura.dias)} dia(s)
      coletado(s)) · atualizado em {instante(gerado)}
      {cobertura.faltando.length > 0 &&
        ` · ${numero(cobertura.faltando.length)} dia(s) do período ainda sem coleta, que entram nas próximas atualizações`}
    </p>
  );
}

/** Os números, os gráficos por mês e as tabelas comuns ao Brasil e a um ente. */
function Secoes({
  dados,
  panorama,
  onOrgao,
  orgaoUnico,
}: {
  dados: Omit<SecoesContratacoes, "orgaos"> & { orgaos?: SecoesContratacoes["orgaos"] };
  panorama?: boolean;
  onOrgao?: (cnpj: string) => void;
  /** Página de um órgão só: sem a contagem de órgãos. */
  orgaoUnico?: boolean;
}) {
  const acoes = useContext(Acoes);
  // Com anos publicados ano a ano no período, o gráfico é por ano: barras de ano e de mês juntas enganariam
  const temAno = dados.meses.some((m) => m.mes.length === 4);
  const grafico = temAno ? porAno(dados.meses, somarMes) : dados.meses;
  const unidadeGrafico = temAno ? "ano" : "mês";
  dados = useMemo(() => doFornecedor(dados, acoes.forn), [dados, acoes.forn]);
  const t = dados.totais;
  const modalidades = usePaginacao(dados.modalidades);
  const fornecedores = usePaginacao(dados.fornecedores);
  const orgaos = usePaginacao(dados.orgaos ?? []);
  const aConferir = usePaginacao(dados.a_conferir ?? []);
  const recentes = usePaginacao(dados.recentes);
  const contratos = usePaginacao(dados.contratos_recentes);
  return (
    <>
      <section className="cartao cartao-corpo" aria-labelledby="titulo-totais-c">
        <h2 id="titulo-totais-c" className="titulo-secao">
          No período
        </h2>
        <div className="totais">
          <Numero
            rotulo="Processos publicados"
            valor={numero(t.processos)}
            detalhe={t.processos_sem_valor ? `${numero(t.processos_sem_valor)} sem valor estimado` : undefined}
          />
          <Numero rotulo="Valor estimado" valor={moedaCompacta(t.valor_estimado)} detalhe={moeda(t.valor_estimado)} />
          <Numero rotulo="Contratos publicados" valor={numero(t.contratos)} />
          <Numero
            rotulo="Valor dos contratos"
            valor={moedaCompacta(t.valor_contratos)}
            detalhe={
              t.valores_a_conferir
                ? `${moeda(t.valor_contratos)} · sem ${numero(t.valores_a_conferir)} valor(es) a conferir`
                : moeda(t.valor_contratos)
            }
          />
          {!orgaoUnico && <Numero rotulo="Órgãos" valor={numero(t.orgaos)} />}
          <Numero rotulo="Fornecedores (PJ)" valor={numero(t.fornecedores)} />
        </div>
      </section>

      {dados.meses.length > 0 && (
        <div className="grade-2">
          <section className="cartao cartao-corpo">
            <h2 className="titulo-secao">Processos por {unidadeGrafico}</h2>
            <GraficoBarras
              titulo={`Processos de contratação publicados por ${unidadeGrafico}`}
              barras={grafico.map((m) => ({ rotulo: mesCurto(m.mes), valor: m.processos }))}
              formatar={(n) => `${numero(n)} processo(s)`}
              formatarEixo={(n) => numero(n)}
            />
          </section>
          <section className="cartao cartao-corpo">
            <h2 className="titulo-secao">Valor dos contratos por {unidadeGrafico}</h2>
            <GraficoBarras
              titulo={`Valor global dos contratos publicados por ${unidadeGrafico}`}
              barras={grafico.map((m) => ({ rotulo: mesCurto(m.mes), valor: m.valor_contratos }))}
              formatar={moeda}
              formatarEixo={moedaCompacta}
            />
          </section>
        </div>
      )}

      <div className="grade-2">
        <section className="cartao cartao-corpo">
          <h2 className="titulo-secao">Por modalidade</h2>
          <table className="tabela">
            <thead>
              <tr>
                <th>Modalidade</th>
                <th className="n">Processos</th>
                <th className="n">Valor estimado</th>
              </tr>
            </thead>
            <tbody>
              {modalidades.visiveis.map((m) => (
                <tr key={String(m.codigo)}>
                  <td>{m.nome}</td>
                  <td className="n">{numero(m.processos)}</td>
                  <td className="n">{moedaCompacta(m.valor_estimado)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <Paginacao {...modalidades} rotulo="modalidades" />
        </section>
        <section className="cartao cartao-corpo">
          <h2 className="titulo-secao">Fornecedores com maior valor contratado</h2>
          <table className="tabela">
            <thead>
              <tr>
                <th>Fornecedor (pessoa jurídica)</th>
                <th className="n">Contratos</th>
                <th className="n">Valor</th>
              </tr>
            </thead>
            <tbody>
              {fornecedores.visiveis.map((f, i) => (
                <tr key={f.cnpj}>
                  <td>
                    <span className="num posicao">{numero((fornecedores.pagina - 1) * fornecedores.porPagina + i + 1)}.</span>{" "}
                    <button type="button" className="objeto-abrir" title="Filtrar a página por este fornecedor"
                            onClick={() => acoes.fornecedor(f.cnpj)}>
                      {f.nome ?? "—"}
                    </button>
                    <div className="busca-detalhe num">{cnpj(f.cnpj)}</div>
                  </td>
                  <td className="n">{numero(f.contratos)}</td>
                  <td className="n">{moedaCompacta(f.valor)}</td>
                </tr>
              ))}
              {dados.pessoas_fisicas.contratos > 0 && fornecedores.pagina === 1 && (
                <tr>
                  <td>Pessoas físicas e estrangeiras (somadas, sem identificação)</td>
                  <td className="n">{numero(dados.pessoas_fisicas.contratos)}</td>
                  <td className="n">{moedaCompacta(dados.pessoas_fisicas.valor)}</td>
                </tr>
              )}
            </tbody>
          </table>
          {dados.fornecedores.length === 0 && <p className="busca-detalhe">Nenhum contrato com pessoa jurídica.</p>}
          <Paginacao {...fornecedores} rotulo="fornecedores" />
        </section>
      </div>

      {!panorama && dados.orgaos && dados.orgaos.length > 0 && (
        <section className="cartao cartao-corpo">
          <h2 className="titulo-secao">Órgãos e entidades</h2>
          <p className="busca-detalhe">
            Cada órgão que publicou no PNCP em nome deste ente: administração direta, câmara, autarquias (como um
            serviço autônomo de água e esgoto), fundações e empresas públicas. Clique para ver só o dele.
          </p>
          <table className="tabela">
            <thead>
              <tr>
                <th>Órgão</th>
                <th className="n">Processos</th>
                <th className="n so-largo">Valor estimado</th>
                <th className="n">Contratos</th>
                <th className="n so-largo">Valor dos contratos</th>
              </tr>
            </thead>
            <tbody>
              {orgaos.visiveis.map((o) => (
                <tr key={o.cnpj} className="clicavel">
                  <td>
                    {onOrgao ? (
                      <button type="button" className="botao-link" onClick={() => onOrgao(o.cnpj)}>
                        {o.nome ?? cnpj(o.cnpj)}
                      </button>
                    ) : (
                      (o.nome ?? cnpj(o.cnpj))
                    )}
                    <div className="busca-detalhe num">{cnpj(o.cnpj)}</div>
                  </td>
                  <td className="n">{numero(o.processos)}</td>
                  <td className="n so-largo">{moedaCompacta(o.valor_estimado)}</td>
                  <td className="n">{numero(o.contratos)}</td>
                  <td className="n so-largo">{moedaCompacta(o.valor_contratos)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <Paginacao {...orgaos} rotulo="órgãos" />
        </section>
      )}

      {dados.a_conferir && dados.a_conferir.length > 0 && (
        <section className="cartao cartao-corpo" aria-labelledby="titulo-a-conferir">
          <h2 id="titulo-a-conferir" className="titulo-secao">
            Valores a conferir na fonte
          </h2>
          <p className="busca-detalhe">
            Processos e contratos publicados com valor acima de R$ 10 bilhões, ou de R$ 20 mil por habitante do ente
            (perto de quatro anos do orçamento de um município médio). Eles contam nos números acima, mas o valor fica
            fora das somas e da lista de fornecedores até ser conferido na publicação original: costuma ser erro de
            digitação. Não é juízo sobre o órgão nem sobre o fornecedor.
          </p>
          <ul className="lista-publicacoes">
            {aConferir.visiveis.map((x) => (
              <li key={`${x.tipo}-${x.chave}`}>
                <div className="publicacao-cabeca">
                  <span className="num">{dataCurta(x.data)}</span> ·{" "}
                  {x.tipo === "processo" ? "Processo (valor estimado)" : "Contrato (valor global)"} ·{" "}
                  <span className="num">{moeda(x.valor)}</span>
                </div>
                <div>
                  <button type="button" className="objeto-abrir" onClick={() => acoes.abrir(x.chave)}
                          title="Abrir tudo sobre esta contratação">
                    {x.objeto ?? "—"}
                  </button>
                </div>
                <div className="busca-detalhe">
                  {x.tipo === "contrato" &&
                    (x.fornecedor_cnpj ? `${x.fornecedor ?? "—"} (${cnpj(x.fornecedor_cnpj)}) · ` : "Pessoa física ou estrangeira · ")}
                  {x.orgao ?? "—"}
                  {x.link && (
                    <>
                      {" · "}
                      <a href={x.link} target="_blank" rel="noreferrer">
                        conferir no PNCP
                      </a>
                    </>
                  )}
                  <Documentos chave={x.chave} link={x.link} />
                </div>
              </li>
            ))}
          </ul>
          <Paginacao {...aConferir} rotulo="valores a conferir" />
        </section>
      )}

      <section className="cartao cartao-corpo">
        <h2 className="titulo-secao">Processos publicados mais recentemente</h2>
        {dados.recentes.length === 0 && <p className="busca-detalhe">Nenhum dos processos mais recentes cai no período.</p>}
        <ul className="lista-publicacoes">
          {recentes.visiveis.map((p) => (
            <li key={p.chave}>
              <div className="publicacao-cabeca">
                <span className="num">{dataCurta(p.data)}</span> · {p.modalidade ?? "Modalidade não informada"} ·{" "}
                <span className="num">{p.valor_estimado ? moeda(p.valor_estimado) : "sem valor estimado"}</span>
                {p.a_conferir && " (valor a conferir, fora das somas)"}
              </div>
              <div>
                  <button type="button" className="objeto-abrir" onClick={() => acoes.abrir(p.chave)}
                          title="Abrir tudo sobre esta contratação">
                    {p.objeto ?? "—"}
                  </button>
                </div>
              <div className="busca-detalhe">
                {p.orgao ?? "—"}
                {p.link && (
                  <>
                    {" · "}
                    <a href={p.link} target="_blank" rel="noreferrer">
                      ver no PNCP
                    </a>
                  </>
                )}
                <Documentos chave={p.chave} link={p.link} />
              </div>
            </li>
          ))}
        </ul>
        <Paginacao {...recentes} rotulo="processos recentes" />
      </section>

      {dados.contratos_recentes.length > 0 && (
        <section className="cartao cartao-corpo">
          <h2 className="titulo-secao">Contratos publicados mais recentemente</h2>
          <ul className="lista-publicacoes">
            {contratos.visiveis.map((c) => (
              <li key={c.chave}>
                <div className="publicacao-cabeca">
                  <span className="num">{dataCurta(c.data)}</span> · {c.instrumento ?? "Contrato"} ·{" "}
                  <span className="num">{moeda(c.valor)}</span>
                  {c.a_conferir && " (valor a conferir, fora das somas)"}
                </div>
                <div>
                  <button type="button" className="objeto-abrir" onClick={() => acoes.abrir(c.chave)}
                          title="Abrir tudo sobre esta contratação">
                    {c.objeto ?? "—"}
                  </button>
                </div>
                <div className="busca-detalhe">
                  {c.fornecedor_cnpj ? `${c.fornecedor ?? "—"} (${cnpj(c.fornecedor_cnpj)})` : "Pessoa física ou estrangeira"}
                  {" · "}
                  {c.orgao ?? "—"}
                  {c.link && (
                    <>
                      {" · "}
                      <a href={c.link} target="_blank" rel="noreferrer">
                        ver no PNCP
                      </a>
                    </>
                  )}
                  <Documentos chave={c.chave} link={c.link} />
                </div>
              </li>
            ))}
          </ul>
          <Paginacao {...contratos} rotulo="contratos recentes" />
        </section>
      )}
    </>
  );
}

/** O Brasil: totais, esferas, UFs e as seções comuns. */
function Panorama({
  dados: originais,
  periodo,
  onEnte,
}: {
  dados: ContratacoesPanorama;
  periodo: PeriodoMeses;
  onEnte: (codigo: string) => void;
}) {
  const dados = useMemo(
    () => (temMesAMes(originais) ? recortarPanorama(originais, periodo) : originais),
    [originais, periodo],
  );
  const ufs = usePaginacao(dados.ufs);
  return (
    <>
      <Periodo cobertura={dados.cobertura} gerado={dados.gerado_em} />
      <Secoes dados={dados} panorama />
      <div className="grade-2">
        <section className="cartao cartao-corpo">
          <h2 className="titulo-secao">Por esfera do órgão</h2>
          <table className="tabela">
            <thead>
              <tr>
                <th>Esfera</th>
                <th className="n">Processos</th>
                <th className="n">Contratos</th>
                <th className="n">Valor dos contratos</th>
              </tr>
            </thead>
            <tbody>
              {dados.esferas.map((e) => (
                <tr key={e.esfera}>
                  <td>
                    {e.esfera === "F" ? (
                      <button type="button" className="botao-link" onClick={() => onEnte("1")}>
                        {e.nome}
                      </button>
                    ) : (
                      e.nome
                    )}
                  </td>
                  <td className="n">{numero(e.processos)}</td>
                  <td className="n">{numero(e.contratos)}</td>
                  <td className="n">{moedaCompacta(e.valor_contratos)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="busca-detalhe">
            &ldquo;Não informada&rdquo;: órgão publicado no PNCP sem a esfera, que fica fora dos painéis por ente.
          </p>
        </section>
        <section className="cartao cartao-corpo">
          <h2 className="titulo-secao">Por UF</h2>
          <table className="tabela">
            <thead>
              <tr>
                <th>UF</th>
                <th className="n">Governo do estado</th>
                <th className="n">Municípios</th>
                <th className="n so-largo">Municípios que publicaram</th>
              </tr>
            </thead>
            <tbody>
              {ufs.visiveis.map((u) => (
                <tr key={u.uf} className="clicavel">
                  <td>
                    <button type="button" className="botao-link" onClick={() => onEnte(CODIGO_UF[u.uf] ?? "1")}>
                      {u.uf}
                    </button>
                  </td>
                  <td className="n">{numero(u.estado.processos)}</td>
                  <td className="n">{numero(u.municipios.processos)}</td>
                  <td className="n so-largo">
                    {numero(u.municipios_com_publicacao)}
                    {u.municipios_no_cadastro ? ` de ${numero(u.municipios_no_cadastro)}` : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <Paginacao {...ufs} rotulo="UFs" />
          <p className="busca-detalhe">
            Processos publicados pelo governo do estado (ou do DF) e pelos municípios da UF.
            {temRecorte(periodo) && " A coluna dos municípios que publicaram é do período coletado inteiro."}
          </p>
        </section>
      </div>
    </>
  );
}

/** Um ente: o caminho (Brasil › UF), as seções comuns e, no estado, os municípios. */
function Ente({
  dados: originais,
  periodo,
  onEnte,
  onOrgao,
}: {
  dados: ContratacoesEnte;
  periodo: PeriodoMeses;
  onEnte: (codigo: string | null) => void;
  onOrgao: (cnpj: string) => void;
}) {
  const [filtro, setFiltro] = useState("");
  const dados = useMemo(() => {
    if (!temMesAMes(originais)) return originais;
    const secoes = recortarSecoes(originais, periodo);
    return originais.municipios ? { ...secoes, municipios: recortarMunicipios(originais.municipios, periodo) } : secoes;
  }, [originais, periodo]);
  const e = dados.ente;
  const tipo = tipoDoCodigo(e.codigo);
  const municipios = useMemo(
    () =>
      (dados.municipios ?? []).filter((m) =>
        m.nome.toLocaleLowerCase("pt-BR").includes(filtro.toLocaleLowerCase("pt-BR")),
      ),
    [dados.municipios, filtro],
  );
  const paginaMunicipios = usePaginacao(municipios);
  return (
    <>
      <nav className="trilha" aria-label="Onde você está">
        <button type="button" onClick={() => onEnte(null)}>
          Brasil
        </button>
        {tipo === "municipio" && e.uf && CODIGO_UF[e.uf] && (
          <button type="button" onClick={() => onEnte(CODIGO_UF[e.uf!] ?? null)}>
            {e.uf}
          </button>
        )}
        <span aria-current="location">{e.nome}</span>
      </nav>
      <h2 className="painel-ente">
        {e.nome}
        <span className="busca-detalhe">
          {" "}
          {tipo === "uniao"
            ? "órgãos federais"
            : tipo === "municipio"
              ? `município · ${e.uf}`
              : tipo === "df"
                ? "Distrito Federal"
                : "governo do estado"}
          {e.populacao ? ` · ${numero(e.populacao)} habitantes` : ""}
        </span>
      </h2>
      <Periodo cobertura={dados.cobertura} gerado={dados.gerado_em} />
      <Secoes dados={dados} onOrgao={onOrgao} />
      <TceNoEnte codigo={e.codigo} meses={originais.meses} />
      {dados.municipios && dados.municipios.length > 0 && (
        <section className="cartao cartao-corpo">
          <h2 className="titulo-secao">Municípios de {e.uf}</h2>
          <input
            className="seletor filtro-tabela"
            value={filtro}
            placeholder="Filtrar pelo nome"
            aria-label="Filtrar municípios pelo nome"
            onChange={(ev) => setFiltro(ev.target.value)}
          />
          <table className="tabela">
            <thead>
              <tr>
                <th>Município</th>
                <th className="n">Processos</th>
                <th className="n so-largo">Valor estimado</th>
                <th className="n">Contratos</th>
                <th className="n so-largo">Valor dos contratos</th>
              </tr>
            </thead>
            <tbody>
              {paginaMunicipios.visiveis.map((m) => (
                <tr key={m.codigo} className="clicavel">
                  <td>
                    <button type="button" className="botao-link" onClick={() => onEnte(m.codigo)}>
                      {m.nome}
                    </button>
                  </td>
                  <td className="n">{numero(m.processos)}</td>
                  <td className="n so-largo">{moedaCompacta(m.valor_estimado)}</td>
                  <td className="n">{numero(m.contratos)}</td>
                  <td className="n so-largo">{moedaCompacta(m.valor_contratos)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <Paginacao {...paginaMunicipios} rotulo="municípios" />
        </section>
      )}
      <LigacoesDoEnte codigo={e.codigo} atual="contratacoes" />
    </>
  );
}

/** Um órgão: o ente a que pertence e as seções comuns. */
function Orgao({
  dados: originais,
  periodo,
  onEnte,
}: {
  dados: ContratacoesOrgao;
  periodo: PeriodoMeses;
  onEnte: (codigo: string | null) => void;
}) {
  const dados = useMemo(
    () => (temMesAMes(originais) ? recortarSecoes(originais, periodo) : originais),
    [originais, periodo],
  );
  const ente = dados.ente;
  return (
    <>
      <nav className="trilha" aria-label="Onde você está">
        <button type="button" onClick={() => onEnte(null)}>
          Brasil
        </button>
        {ente && (
          <button type="button" onClick={() => onEnte(ente.codigo)}>
            {ente.nome}
            {ente.tipo === "municipio" && ente.uf ? ` (${ente.uf})` : ""}
          </button>
        )}
        <span aria-current="location">{dados.orgao.nome ?? cnpj(dados.orgao.cnpj)}</span>
      </nav>
      <h2 className="painel-ente">
        {dados.orgao.nome ?? cnpj(dados.orgao.cnpj)}
        <span className="busca-detalhe num"> · CNPJ {cnpj(dados.orgao.cnpj)}</span>
      </h2>
      {!ente && (
        <p className="busca-detalhe">
          O PNCP não informa a esfera deste órgão: ele não entra no painel de nenhum ente, só no do Brasil.
        </p>
      )}
      <Periodo cobertura={dados.cobertura} gerado={dados.gerado_em} />
      <Secoes dados={dados} orgaoUnico />
    </>
  );
}
