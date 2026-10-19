"use client";

/**
 * Empresas estatais (ADR-034): quanto gastam e investem as estatais, que não publicam no PNCP (Lei 13.303/2016).
 *
 * Duas abas, pela fonte, que nunca se somam: as federais pelo Programa de Dispêndios Globais da SEST
 * (aprovado e realizado por rubrica) e as com ações na bolsa pelas demonstrações entregues à CVM (DFP). O
 * estado fica na URL: `?fonte=sest|cvm`, `?ano=`, `?q=` (busca) e `?filtro=`.
 */

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Fragment, useEffect, useMemo, useState } from "react";
import { Escolha } from "@/componentes/Escolha";
import { Paginacao, usePaginacao } from "@/componentes/Paginacao";
import {
  carregarEstatais,
  comoGasto,
  controlePublico,
  estataisDoEnte,
  type CompanhiaCvm,
  type EmpresaSest,
  execucao,
  exerciciosDe,
  type FeedEstatais,
  filtrar,
  mesAbreviado,
  ordenarPor,
  realizado,
  ROTULO_CONTROLE,
  valorCvm,
} from "@/lib/estatais";
import { instante, numero, percentual } from "@/lib/formato";
import { carregarEntes, type EnteBusca, tipoDoCodigo } from "@/lib/paineis";
import { cnpj, moeda, moedaCompacta } from "@/lib/paineis";

const METODOLOGIA = "https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-034.md";

/** Carregando, ou o arquivo lido (null quando ainda não foi publicado) e o erro, se houve. */
type Estado = { carregando: true } | { carregando: false; dados: FeedEstatais | null; erro: string | null };

/** Página inteira das estatais. */
export function PainelEstatais() {
  const params = useSearchParams();
  const router = useRouter();
  const [estado, setEstado] = useState<Estado>({ carregando: true });
  const [entes, setEntes] = useState<EnteBusca[] | null>(null);
  const codigoLocal = params.get("ente");

  useEffect(() => {
    if (codigoLocal && entes === null) carregarEntes().then(setEntes).catch(() => setEntes([]));
  }, [codigoLocal, entes]);

  useEffect(() => {
    const c = new AbortController();
    carregarEstatais(c.signal)
      .then((dados) => setEstado({ carregando: false, dados, erro: null }))
      .catch((e: Error) => {
        if (e.name !== "AbortError") setEstado({ carregando: false, dados: null, erro: e.message });
      });
    return () => c.abort();
  }, []);

  const mudar = (mudancas: Record<string, string | null>) => {
    const novo = new URLSearchParams(params.toString());
    for (const [k, v] of Object.entries(mudancas)) {
      if (v) novo.set(k, v);
      else novo.delete(k);
    }
    router.replace(`?${novo.toString()}`, { scroll: false });
  };

  if (estado.carregando) return <p className="situacao-painel">Carregando as estatais…</p>;
  if (estado.erro) return <p className="situacao-painel">Não foi possível ler as estatais: {estado.erro}</p>;
  if (!estado.dados) {
    return <p className="situacao-painel">As estatais ainda não foram publicadas: a primeira coleta ainda não rodou.</p>;
  }
  const dados = estado.dados;
  // Filtro de local (ADR-035): num estado ou município, só as companhias abertas que ele controla; as federais
  // da SEST só fazem sentido para a União
  const local = codigoLocal && /^(1|\d{2}|\d{7})$/.test(codigoLocal)
    ? { codigo: codigoLocal, nome: entes?.find((e) => e.codigo === codigoLocal)?.nome ?? (codigoLocal === "1" ? "União" : codigoLocal),
        uf: entes?.find((e) => e.codigo === codigoLocal)?.uf ?? null }
    : null;
  const doLocal = local ? { ...dados, companhias: estataisDoEnte(dados, local.nome, local.uf, tipoDoCodigo(local.codigo)) } : dados;
  const fonte = params.get("fonte") === "cvm" || !dados.federais || (local && local.codigo !== "1" && params.get("fonte") !== "sest")
    ? "cvm" : "sest";

  return (
    <div className="painel">
      <nav className="trilha" aria-label="Onde você está">
        <Link href="/economia/">Economia</Link>
        <span aria-current="location">Empresas estatais</span>
      </nav>
      <div className="painel-topo">
        <div>
          <h1>Empresas estatais</h1>
          <p className="painel-periodo">
            Quanto as estatais gastam e investem, pelas fontes oficiais. Publicado em {instante(dados.gerado_em)}.
          </p>
        </div>
      </div>
      <aside className="faixa aviso-metodologico" aria-label="Aviso metodológico">
        As estatais seguem a Lei 13.303/2016 e não publicam as contratações no PNCP. Aqui estão os gastos que elas
        informam: as federais, ao Ministério da Gestão (Programa de Dispêndios Globais, da SEST); as com ações na
        bolsa, à CVM (demonstrações financeiras). Valores em reais correntes, como publicados. Nenhum total soma
        empresas: a controladora inclui as controladas (o Banco do Brasil inclui a BB Seguridade), e somar contaria
        duas vezes.{" "}
        <a href={METODOLOGIA} target="_blank" rel="noreferrer">
          Metodologia completa
        </a>
        .
      </aside>
      {local && (
        <p className="filtro-ativo">
          Filtrado por <strong>{local.nome}</strong>
          {local.codigo === "1" ? ": as estatais federais" : ": as companhias abertas que ele controla"}{" "}
          <button type="button" className="botao-link" onClick={() => mudar({ ente: null })}>ver todas</button>
        </p>
      )}
      <div className="cargos" role="tablist" aria-label="Fonte">
        {dados.federais && (
          <button type="button" role="tab" className="cargo" aria-selected={fonte === "sest"}
                  onClick={() => mudar({ fonte: null, ano: null, filtro: null })}>
            Federais (SEST) · {numero(dados.federais.empresas.filter((e) => e.situacao === "ativa").length)}
          </button>
        )}
        <button type="button" role="tab" className="cargo" aria-selected={fonte === "cvm"}
                onClick={() => mudar({ fonte: "cvm", ano: null, filtro: null })}>
          Com ações na bolsa (CVM) · {numero(doLocal.companhias.length)}
        </button>
      </div>
      {fonte === "sest" && dados.federais ? (
        <Federais federais={dados.federais} params={params} mudar={mudar} />
      ) : (
        <Listadas dados={doLocal} params={params} mudar={mudar} />
      )}
    </div>
  );
}

/** O que as abas recebem: a URL atual e como mudá-la. */
type Props = { params: URLSearchParams | ReturnType<typeof useSearchParams>; mudar: (m: Record<string, string | null>) => void };

/** Busca, exercício e filtro, comuns às duas abas. */
function Filtros({ anos, ano, termo, filtro, filtros, mudar }: {
  anos: string[]; ano: string; termo: string; filtro: string; filtros: { valor: string; rotulo: string }[];
  mudar: (m: Record<string, string | null>) => void;
}) {
  const [texto, setTexto] = useState(termo);
  useEffect(() => setTexto(termo), [termo]);
  return (
    <div className="controles estatais-filtros">
      <input
        className="seletor filtro-tabela"
        value={texto}
        placeholder="Buscar empresa, sigla, CNPJ ou grupo"
        aria-label="Buscar empresa pelo nome, sigla, CNPJ ou grupo"
        onChange={(e) => {
          setTexto(e.target.value);
          mudar({ q: e.target.value || null });
        }}
      />
      <Escolha
        rotulo="Exercício"
        opcoes={anos.map((a) => ({ valor: a, rotulo: `Exercício de ${a}` }))}
        valor={ano}
        onEscolher={(a) => mudar({ ano: a })}
      />
      <Escolha rotulo="Quais empresas" opcoes={filtros} valor={filtro} onEscolher={(f) => mudar({ filtro: f })} />
    </div>
  );
}

// ------------------------------------------------------------------------------------------ SEST

const COLUNAS_SEST = [
  { id: "total_usos", rotulo: "Total" },
  { id: "pessoal", rotulo: "Pessoal" },
  { id: "servicos", rotulo: "Serviços de terceiros" },
  { id: "materiais", rotulo: "Materiais" },
  { id: "investimentos", rotulo: "Investimentos" },
];

/** As estatais federais, pelo PDG. */
function Federais({ federais, params, mudar }: { federais: NonNullable<FeedEstatais["federais"]> } & Props) {
  const anos = useMemo(() => exerciciosDe(federais.empresas), [federais]);
  const ano = params.get("ano") && anos.includes(params.get("ano")!) ? params.get("ano")! : anos[0] ?? "";
  const termo = params.get("q") ?? "";
  const filtro = params.get("filtro") ?? "com_pdg";
  const [aberta, setAberta] = useState<string | null>(null);
  const lista = useMemo(() => {
    const aceita = (e: EmpresaSest) =>
      filtro === "todas" ? true
        : filtro === "dependentes" ? e.dependente === true && e.situacao === "ativa"
          : filtro === "inativas" ? e.situacao === "inativa"
            : !!e.exercicios[ano];
    return ordenarPor(filtrar(federais.empresas, termo, aceita), (e) => realizado(e, ano, "total_usos"), (e) => e.sigla);
  }, [federais, termo, filtro, ano]);
  const pagina = usePaginacao(lista);
  const rubricas = federais.rubricas;
  return (
    <section className="cartao cartao-corpo">
      <p className="busca-detalhe">
        Empresas federais não dependentes do Tesouro (pagam as despesas com receita própria) e o Programa de Dispêndios
        Globais: o orçamento aprovado por decreto e o realizado, informado pela empresa à SEST. As dependentes (EBSERH,
        Embrapa, Conab, HCPA…) não têm PDG: a despesa delas está no Orçamento da União, no{" "}
        <a href="https://portaldatransparencia.gov.br/" target="_blank" rel="noreferrer">Portal da Transparência</a>.
        Nos bancos, o total inclui concessão de crédito e aplicações; para comparar custos, use pessoal, serviços e
        materiais.
      </p>
      <Filtros anos={anos} ano={ano} termo={termo} filtro={filtro} mudar={mudar} filtros={[
        { valor: "com_pdg", rotulo: `Com PDG em ${ano}` },
        { valor: "dependentes", rotulo: "Dependentes do Tesouro (sem PDG)" },
        { valor: "inativas", rotulo: "Inativas (extintas, incorporadas)" },
        { valor: "todas", rotulo: "Todas do cadastro" },
      ]} />
      <div className="tabela-rolavel">
        <table className="tabela">
          <thead>
            <tr>
              <th>Empresa</th>
              {COLUNAS_SEST.map((c, i) => (
                <th key={c.id} className={`n${i > 1 ? " so-largo" : ""}`}>{c.rotulo}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pagina.visiveis.map((e) => (
              <Fragment key={e.codigo_siest}>
                <tr className="clicavel">
                  <td>
                    <button type="button" className="botao-link" aria-expanded={aberta === e.codigo_siest}
                            onClick={() => setAberta(aberta === e.codigo_siest ? null : e.codigo_siest)}>
                      {e.sigla}
                    </button>
                    <div className="busca-detalhe">
                      {e.nome}
                      {e.grupo ? ` · grupo ${e.grupo}` : ""}
                      {e.dependente ? " · dependente do Tesouro" : ""}
                      {e.situacao === "inativa" ? ` · inativa${e.inativa_desde ? ` desde ${e.inativa_desde}` : ""}` : ""}
                    </div>
                  </td>
                  {COLUNAS_SEST.map((c, i) => (
                    <td key={c.id} className={`n${i > 1 ? " so-largo" : ""}`}>{moedaCompacta(realizado(e, ano, c.id))}</td>
                  ))}
                </tr>
                {aberta === e.codigo_siest && (
                  <tr>
                    <td colSpan={COLUNAS_SEST.length + 1}>
                      <DetalheSest e={e} ano={ano} anos={anos} rubricas={rubricas} />
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
      {lista.length === 0 && <p className="busca-detalhe">Nenhuma empresa com esse nome neste filtro.</p>}
      <Paginacao {...pagina} rotulo="empresas federais" />
      <p className="busca-detalhe">
        Fonte:{" "}
        <a href={federais.urls.pagina} target="_blank" rel="noreferrer">dados abertos da SEST/MGI</a> (identificação e
        PDG), coletados em {instante(federais.coletado_em.pdg)}. Clique na sigla para ver todas as rubricas, o aprovado e
        o realizado.
      </p>
    </section>
  );
}

/** Uma empresa federal: cada rubrica no exercício (aprovado, realizado, execução) e o total por ano. */
function DetalheSest({ e, ano, anos, rubricas }: { e: EmpresaSest; ano: string; anos: string[];
                                                  rubricas: NonNullable<FeedEstatais["federais"]>["rubricas"] }) {
  const doAno = e.exercicios[ano];
  if (!doAno) {
    return (
      <p className="busca-detalhe">
        {e.dependente
          ? "Empresa dependente do Tesouro: sem PDG; a despesa está no Orçamento da União."
          : `Sem PDG publicado para ${ano}.`}
        {e.cnpj ? ` CNPJ ${e.cnpj}.` : ""}
        {e.ministerio ? ` Supervisão: ${e.ministerio}.` : ""}
      </p>
    );
  }
  const historico = anos.filter((a) => e.exercicios[a]).sort();
  return (
    <div className="estatais-detalhe">
      <p className="busca-detalhe">
        {e.natureza}
        {e.cnpj ? ` · CNPJ ${e.cnpj}` : ""}
        {e.ministerio ? ` · supervisão: ${e.ministerio}` : ""}
        {e.na_cvm ? " · também na aba das companhias com ações na bolsa" : ""}
      </p>
      <table className="tabela">
        <thead>
          <tr>
            <th>Rubrica ({ano})</th>
            <th className="n">Aprovado</th>
            <th className="n">Realizado</th>
            <th className="n so-largo">Execução</th>
          </tr>
        </thead>
        <tbody>
          {rubricas.map((r) => {
            const v = doAno[r.id];
            return (
              <tr key={r.id}>
                <td>
                  {r.nome}
                  <div className="busca-detalhe">{r.definicao}</div>
                </td>
                <td className="n">{moedaCompacta(v?.aprovado)}</td>
                <td className="n" title={moeda(v?.realizado)}>
                  {moedaCompacta(v?.realizado)}
                  {v?.ate_mes && v.ate_mes < 12 ? <div className="busca-detalhe">até {mesAbreviado(v.ate_mes)}</div> : null}
                </td>
                <td className="n so-largo">{execucao(v) === null ? "—" : percentual(execucao(v))}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {historico.length > 1 && (
        <table className="tabela">
          <thead>
            <tr>
              <th>Exercício</th>
              <th className="n">Total realizado</th>
              <th className="n">Pessoal</th>
              <th className="n so-largo">Investimentos</th>
            </tr>
          </thead>
          <tbody>
            {historico.map((a) => (
              <tr key={a}>
                <td>{a}</td>
                <td className="n">{moedaCompacta(realizado(e, a, "total_usos"))}</td>
                <td className="n">{moedaCompacta(realizado(e, a, "pessoal"))}</td>
                <td className="n so-largo">{moedaCompacta(realizado(e, a, "investimentos"))}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

// ------------------------------------------------------------------------------------------ CVM

const COLUNAS_CVM = [
  { id: "receita", rotulo: "Receita", saida: false },
  { id: "pessoal", rotulo: "Pessoal", saida: false },
  { id: "insumos", rotulo: "Compras de terceiros", saida: true },
  { id: "aquisicoes_ativos", rotulo: "Investimento em ativos", saida: true },
  { id: "resultado", rotulo: "Lucro ou prejuízo", saida: false },
];

/** As companhias abertas que se declaram estatais, pelas DFP. */
function Listadas({ dados, params, mudar }: { dados: FeedEstatais } & Props) {
  const anos = useMemo(() => exerciciosDe(dados.companhias), [dados]);
  const ano = params.get("ano") && anos.includes(params.get("ano")!) ? params.get("ano")! : anos[0] ?? "";
  const termo = params.get("q") ?? "";
  const filtro = params.get("filtro") ?? (params.get("ente") ? "todas" : "publico");
  const [aberta, setAberta] = useState<string | null>(null);
  const lista = useMemo(() => {
    const aceita = (c: CompanhiaCvm) =>
      filtro === "todas" ? true
        : filtro === "a_conferir" ? !controlePublico(c)
          : filtro === "federal" || filtro === "estadual" || filtro === "municipal" || filtro === "distrital"
            ? c.controle.esfera === filtro
            : controlePublico(c);
    return ordenarPor(filtrar(dados.companhias, termo, aceita), (c) => valorCvm(c, ano, "receita"), (c) => c.nome);
  }, [dados, termo, filtro, ano]);
  const pagina = usePaginacao(lista);
  return (
    <section className="cartao cartao-corpo">
      <p className="busca-detalhe">
        Companhias abertas que se declaram estatais no cadastro da CVM, com o controle conferido no Formulário de
        Referência (o campo do cadastro não é atualizado depois de uma privatização) e os números das demonstrações
        financeiras padronizadas do exercício, consolidadas quando a companhia tem controladas.
      </p>
      <Filtros anos={anos} ano={ano} termo={termo} filtro={filtro} mudar={mudar} filtros={[
        { valor: "publico", rotulo: "Controle público conferido" },
        { valor: "federal", rotulo: "Controle federal" },
        { valor: "estadual", rotulo: "Controle estadual" },
        { valor: "distrital", rotulo: "Controle do Distrito Federal" },
        { valor: "municipal", rotulo: "Controle municipal" },
        { valor: "a_conferir", rotulo: "Cadastro diz estatal, FRE não confirma" },
        { valor: "todas", rotulo: "Todas as que se declaram estatais" },
      ]} />
      <div className="tabela-rolavel">
        <table className="tabela">
          <thead>
            <tr>
              <th>Companhia</th>
              {COLUNAS_CVM.map((c, i) => (
                <th key={c.id} className={`n${i > 1 ? " so-largo" : ""}`}>{c.rotulo}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pagina.visiveis.map((c) => (
              <Fragment key={c.cnpj}>
                <tr className="clicavel">
                  <td>
                    <button type="button" className="botao-link" aria-expanded={aberta === c.cnpj}
                            onClick={() => setAberta(aberta === c.cnpj ? null : c.cnpj)}>
                      {c.nome}
                    </button>
                    <div className="busca-detalhe">
                      {ROTULO_CONTROLE[c.controle.classe]}
                      {c.controle.esfera ? ` · ${c.controle.esfera}` : ""}
                      {c.controle.controlada_por_nome ? ` · por ${c.controle.controlada_por_nome}` : ""}
                    </div>
                  </td>
                  {COLUNAS_CVM.map((col, i) => (
                    <td key={col.id} className={`n${i > 1 ? " so-largo" : ""}`}>
                      {moedaCompacta(comoGasto(valorCvm(c, ano, col.id), col.saida))}
                    </td>
                  ))}
                </tr>
                {aberta === c.cnpj && (
                  <tr>
                    <td colSpan={COLUNAS_CVM.length + 1}>
                      <DetalheCvm c={c} ano={ano} anos={anos} indicadores={dados.indicadores} />
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
      {lista.length === 0 && <p className="busca-detalhe">Nenhuma companhia com esse nome neste filtro.</p>}
      <Paginacao {...pagina} rotulo="companhias" />
      <p className="busca-detalhe">
        Fonte: <a href="https://dados.cvm.gov.br/" target="_blank" rel="noreferrer">dados abertos da CVM</a> (cadastro,
        FRE e DFP), coletados em {instante(dados.coletado_em.cadastro)}. Gastos publicados como negativos (custos,
        compras) aparecem como valores positivos. Clique no nome para ver todos os números, o controlador e o documento
        entregue.
      </p>
    </section>
  );
}

/** Uma companhia: controladores, cada indicador no exercício (conta e descrição publicadas) e a série. */
function DetalheCvm({ c, ano, anos, indicadores }: { c: CompanhiaCvm; ano: string; anos: string[];
                                                    indicadores: FeedEstatais["indicadores"] }) {
  const ex = c.exercicios[ano];
  const historico = anos.filter((a) => c.exercicios[a]).sort();
  return (
    <div className="estatais-detalhe">
      <p className="busca-detalhe">
        CNPJ {cnpj(c.cnpj.replace(/\D/g, ""))} · {c.setor} · {c.uf}
        {c.controle.controladores?.length
          ? ` · controlador${c.controle.controladores.length > 1 ? "es" : ""} no FRE de ${c.controle.data_referencia?.slice(0, 4) ?? "—"}: ` +
            c.controle.controladores
              .map((x) => `${x.nome}${x.percentual_ordinarias !== null ? ` (${percentual(x.percentual_ordinarias)} das ordinárias)` : ""}`)
              .join("; ")
          : " · nenhum controlador declarado no FRE"}
        {ex?.documento?.link && (
          <>
            {" · "}
            <a href={ex.documento.link} target="_blank" rel="noreferrer">DFP de {ano} no RAD da CVM</a>
          </>
        )}
      </p>
      {ex ? (
        <table className="tabela">
          <thead>
            <tr>
              <th>Indicador ({ano})</th>
              <th className="n">Valor publicado</th>
            </tr>
          </thead>
          <tbody>
            {indicadores.map((i) => {
              const v = ex.valores[i.id];
              return (
                <tr key={i.id}>
                  <td>
                    {i.nome}
                    <div className="busca-detalhe">
                      {v ? `${v.conta ? `${v.conta} · ` : ""}${v.descricao}` : "Conta não encontrada nesta demonstração."}
                    </div>
                  </td>
                  <td className="n" title={moeda(v?.valor)}>{moedaCompacta(v?.valor)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      ) : (
        <p className="busca-detalhe">Sem DFP de {ano} nos dados abertos.</p>
      )}
      {historico.length > 1 && (
        <table className="tabela">
          <thead>
            <tr>
              <th>Exercício</th>
              <th className="n">Receita</th>
              <th className="n">Pessoal</th>
              <th className="n so-largo">Lucro ou prejuízo</th>
            </tr>
          </thead>
          <tbody>
            {historico.map((a) => (
              <tr key={a}>
                <td>{a}</td>
                <td className="n">{moedaCompacta(valorCvm(c, a, "receita"))}</td>
                <td className="n">{moedaCompacta(valorCvm(c, a, "pessoal"))}</td>
                <td className="n so-largo">{moedaCompacta(valorCvm(c, a, "resultado"))}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
