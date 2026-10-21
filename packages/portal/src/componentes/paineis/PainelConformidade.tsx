"use client";

/**
 * Painel de conformidade fiscal (UC-07, ADR-028): se os relatórios da Lei de Responsabilidade Fiscal constam
 * do extrato de entregas do Tesouro (SICONFI) e em que data, contra o prazo legal.
 *
 * Três telas pela URL: o Brasil (sem parâmetro), uma UF (`?uf=SP`) e um ente (`?ente=<código IBGE>`), com o
 * período em `?de=AAAA-01&ate=AAAA-12` (os exercícios escolhidos; `recortarConformidade`). A ordem é sempre por
 * UF e por nome, nunca por resultado (PUB-07).
 */

import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { FiltroPeriodo } from "@/componentes/FiltroPeriodo";
import { Paginacao, usePaginacao } from "@/componentes/Paginacao";
import { exerciciosDoArquivo, recortarConformidade } from "@/lib/conformidade";
import { lerPeriodo, type PeriodoMeses } from "@/lib/periodo";
import { instante, numero, percentual } from "@/lib/formato";
import {
  type Obrigacao,
  carregarConformidadeEnte,
  carregarConformidadePanorama,
  carregarConformidadeUf,
  dataCurta,
  type ConformidadeEnte,
  type ConformidadePanorama,
  type ConformidadeUf,
  type ResumoConformidade,
} from "@/lib/paineis";
import { AvisoMetodologico, BuscaEnte, Numero, SeloResultado, Situacao } from "./Comuns";
import { GrupoPares } from "./GrupoPares";
import { LigacoesDoEnte } from "@/componentes/Ligacoes";
import { Transparencia } from "./Transparencia";

/** Os três arquivos que a página pode mostrar. */
type Dados = ConformidadePanorama | ConformidadeUf | ConformidadeEnte;
/** Carregando, ou o arquivo lido (null quando não existe) e o erro, se houve. */
type Estado = { carregando: true } | { carregando: false; dados: Dados | null; erro: string | null };

/** "4 de 6 no prazo (66,67%)"; sem obrigação avaliável, "sem obrigação avaliável". */
function noPrazo(r: ResumoConformidade): string {
  if (!r.avaliaveis) return "sem obrigação avaliável";
  return `${numero(r.cumpre)} de ${numero(r.avaliaveis)} (${percentual((r.no_prazo ?? 0) * 100)})`;
}

/** Painel de conformidade, a partir de `?uf=` ou `?ente=` na URL. */
export function PainelConformidade() {
  const params = useSearchParams();
  const router = useRouter();
  const brutoEnte = params.get("ente");
  const brutoUf = params.get("uf");
  const ente = brutoEnte && /^(\d{2}|\d{7})$/.test(brutoEnte) ? brutoEnte : null;
  const uf = !ente && brutoUf && /^[A-Za-z]{2}$/.test(brutoUf) ? brutoUf.toUpperCase() : null;
  const [estado, setEstado] = useState<Estado>({ carregando: true });

  useEffect(() => {
    const c = new AbortController();
    setEstado({ carregando: true });
    const p: Promise<Dados | null> = ente
      ? carregarConformidadeEnte(ente, c.signal)
      : uf
        ? carregarConformidadeUf(uf, c.signal)
        : carregarConformidadePanorama(c.signal);
    p.then((dados) => setEstado({ carregando: false, dados, erro: null })).catch((e: Error) => {
      if (e.name !== "AbortError") setEstado({ carregando: false, dados: null, erro: e.message });
    });
    return () => c.abort();
  }, [ente, uf]);

  const periodo = lerPeriodo(params);
  // O período vai junto quando a pessoa navega entre o Brasil, a UF e o ente
  const sufixo = (p: PeriodoMeses) => `${p.de ? `&de=${p.de}` : ""}${p.ate ? `&ate=${p.ate}` : ""}`;
  const url = (base: string, p = periodo) => {
    const q = `${base}${sufixo(p)}`.replace(/^&/, "");
    return `/conformidade/${q ? `?${q}` : ""}`;
  };
  const irEnte = (codigo: string) => router.push(url(`ente=${codigo}`));
  const irUf = (sigla: string | null) => router.push(url(sigla ? `uf=${sigla}` : ""));
  const mudarPeriodo = (p: PeriodoMeses) =>
    router.replace(url(ente ? `ente=${ente}` : uf ? `uf=${uf}` : "", p), { scroll: false });
  const dados = !estado.carregando && estado.dados ? recortarConformidade(estado.dados, periodo) : null;

  return (
    <div className="painel">
      <div className="painel-topo">
        <h1>Conformidade</h1>
        <BuscaEnte rotulo="Buscar estado ou município" onEscolher={irEnte} />
      </div>
      <AvisoMetodologico>
        Compara o extrato de entregas do Tesouro Nacional (SICONFI) com os prazos da Lei de Responsabilidade Fiscal:
        contas anuais (art. 51), RREO de cada bimestre (art. 52) e RGF de cada quadrimestre ou semestre, por Poder
        (art. 55). Só entram as obrigações com prazo já vencido. Quando o extrato do ente não pôde ser lido, ou a
        entrega não tem data conhecida, o resultado é indeterminado e nada é atribuído ao ente.
      </AvisoMetodologico>
      {estado.carregando && <Situacao>Carregando…</Situacao>}
      {!estado.carregando && estado.erro && (
        <Situacao>Não foi possível ler os dados agora ({estado.erro}). Tente de novo em alguns minutos.</Situacao>
      )}
      {!estado.carregando && !estado.erro && estado.dados === null && (
        <section className="cartao cartao-corpo">
          <p>
            {ente || uf
              ? "Este ente ainda não foi avaliado: o extrato de entregas dele entra na próxima coleta diária."
              : "Os dados do painel ainda não foram publicados."}
          </p>
          {(ente || uf) && (
            <button type="button" className="botao" onClick={() => irUf(null)}>
              Ver o Brasil
            </button>
          )}
        </section>
      )}
      {!estado.carregando && estado.dados && (
        <FiltroPeriodo
          titulo="Exercícios"
          opcoes={exerciciosDoArquivo(estado.dados)}
          periodo={periodo}
          onMudar={mudarPeriodo}
          nota="Contagens e frações refeitas só com as obrigações dos exercícios escolhidos."
        />
      )}
      {dados?.tipo === "conformidade-panorama" && <Panorama dados={dados} onUf={irUf} />}
      {dados?.tipo === "conformidade-uf" && <Uf dados={dados} onEnte={irEnte} onBrasil={() => irUf(null)} />}
      {dados?.tipo === "conformidade-ente" && <Ente dados={dados} onUf={irUf} />}
    </div>
  );
}

/** Os quatro resultados e a fração no prazo, em números. */
function Resumo({ r, titulo }: { r: ResumoConformidade; titulo: string }) {
  return (
    <section className="cartao cartao-corpo">
      <h2 className="titulo-secao">{titulo}</h2>
      <div className="totais">
        <Numero rotulo="Entregues no prazo" valor={noPrazo(r)} />
        <Numero rotulo="Após o prazo" valor={numero(r.cumpre_parcialmente)} />
        <Numero rotulo="Não constam no extrato" valor={numero(r.nao_cumpre)} />
        <Numero rotulo="Indeterminadas" valor={numero(r.indeterminado)} />
      </div>
    </section>
  );
}

/** O Brasil: resumo, por obrigação e por UF (em ordem de UF). */
function Panorama({ dados, onUf }: { dados: ConformidadePanorama; onUf: (uf: string) => void }) {
  const criterios = usePaginacao(dados.criterios);
  const ufs = usePaginacao(dados.ufs);
  return (
    <>
      <p className="painel-periodo">
        {numero(dados.entes)} ente(s) avaliado(s) em {dataCurta(dados.avaliado_em)} · atualizado em{" "}
        {instante(dados.gerado_em)}
      </p>
      <Resumo r={dados.brasil} titulo="Obrigações avaliadas no Brasil" />
      <div className="grade-2">
        <section className="cartao cartao-corpo">
          <h2 className="titulo-secao">Por obrigação</h2>
          <table className="tabela">
            <thead>
              <tr>
                <th>Obrigação</th>
                <th className="n">No prazo</th>
                <th className="n">Após o prazo</th>
                <th className="n">Não consta</th>
                <th className="n">Indeterm.</th>
              </tr>
            </thead>
            <tbody>
              {criterios.visiveis.map((c) => (
                <tr key={c.criterio}>
                  <td>{c.nome}</td>
                  <td className="n">{numero(c.cumpre)}</td>
                  <td className="n">{numero(c.cumpre_parcialmente)}</td>
                  <td className="n">{numero(c.nao_cumpre)}</td>
                  <td className="n">{numero(c.indeterminado)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <Paginacao {...criterios} rotulo="obrigações" />
        </section>
        <section className="cartao cartao-corpo">
          <h2 className="titulo-secao">Por UF</h2>
          <table className="tabela">
            <thead>
              <tr>
                <th>UF</th>
                <th className="n">Entes</th>
                <th className="n">Entregues no prazo</th>
                <th className="n so-largo">Coleta</th>
              </tr>
            </thead>
            <tbody>
              {ufs.visiveis.map((u) => (
                <tr key={u.uf} className="clicavel">
                  <td>
                    {u.entes ? (
                      <button type="button" className="botao-link" onClick={() => onUf(u.uf)}>
                        {u.uf}
                      </button>
                    ) : (
                      u.uf
                    )}
                  </td>
                  <td className="n">{numero(u.entes)}</td>
                  <td className="n">{u.avaliaveis ? percentual((u.no_prazo ?? 0) * 100) : "—"}</td>
                  <td className="n so-largo">{dataCurta(u.coletado_em)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <Paginacao {...ufs} rotulo="UFs" />
        </section>
      </div>
    </>
  );
}

/** Uma UF: os entes por nome (o estado primeiro), com filtro. */
function Uf({ dados, onEnte, onBrasil }: { dados: ConformidadeUf; onEnte: (c: string) => void; onBrasil: () => void }) {
  const [filtro, setFiltro] = useState("");
  const entes = useMemo(
    () => dados.entes.filter((e) => e.nome.toLocaleLowerCase("pt-BR").includes(filtro.toLocaleLowerCase("pt-BR"))),
    [dados.entes, filtro],
  );
  const pagina = usePaginacao(entes);
  return (
    <>
      <nav className="trilha" aria-label="Onde você está">
        <button type="button" onClick={onBrasil}>
          Brasil
        </button>
        <span aria-current="location">{dados.uf}</span>
      </nav>
      <p className="painel-periodo">
        Extrato coletado em {dataCurta(dados.coletado_em)} · avaliado em {dataCurta(dados.avaliado_em)}
      </p>
      <section className="cartao cartao-corpo">
        <h2 className="titulo-secao">Entes de {dados.uf}</h2>
        <input
          className="seletor filtro-tabela"
          value={filtro}
          placeholder="Filtrar pelo nome"
          aria-label="Filtrar entes pelo nome"
          onChange={(e) => setFiltro(e.target.value)}
        />
        <table className="tabela">
          <thead>
            <tr>
              <th>Ente</th>
              <th className="n">Entregues no prazo</th>
              <th className="n so-largo">Após o prazo</th>
              <th className="n so-largo">Não constam</th>
              <th className="n so-largo">Indeterm.</th>
            </tr>
          </thead>
          <tbody>
            {pagina.visiveis.map((e) => (
              <tr key={e.codigo} className="clicavel">
                <td>
                  <button type="button" className="botao-link" onClick={() => onEnte(e.codigo)}>
                    {e.nome}
                  </button>
                  {e.tipo !== "municipio" && <span className="busca-detalhe"> · governo</span>}
                </td>
                <td className="n">{noPrazo(e)}</td>
                <td className="n so-largo">{numero(e.cumpre_parcialmente)}</td>
                <td className="n so-largo">{numero(e.nao_cumpre)}</td>
                <td className="n so-largo">{numero(e.indeterminado)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <Paginacao {...pagina} rotulo="entes" />
      </section>
    </>
  );
}

/** Um ente: o resumo e cada obrigação avaliada, por exercício. */
function Ente({ dados, onUf }: { dados: ConformidadeEnte; onUf: (uf: string | null) => void }) {
  const e = dados.ente;
  const exercicios = [...new Set(dados.obrigacoes.map((o) => o.exercicio))].sort((a, b) => b - a);
  const falhas = Object.entries(dados.coleta).filter(([, ok]) => !ok).map(([a]) => a);
  return (
    <>
      <nav className="trilha" aria-label="Onde você está">
        <button type="button" onClick={() => onUf(null)}>
          Brasil
        </button>
        {e.uf && (
          <button type="button" onClick={() => onUf(e.uf)}>
            {e.uf}
          </button>
        )}
        <span aria-current="location">{e.nome}</span>
      </nav>
      <h2 className="painel-ente">
        {e.nome}
        <span className="busca-detalhe">
          {" "}
          {e.tipo === "municipio" ? `município · ${e.uf}` : e.tipo === "df" ? "Distrito Federal" : "estado"}
          {e.populacao ? ` · ${numero(e.populacao)} habitantes` : ""}
        </span>
      </h2>
      <p className="painel-periodo">
        Extrato coletado em {dataCurta(dados.coletado_em)} · avaliado em {dataCurta(dados.avaliado_em)}
        {falhas.length > 0 && ` · o extrato de ${falhas.join(" e ")} não pôde ser lido: obrigações indeterminadas`}
      </p>
      <Resumo r={dados.resumo} titulo="Obrigações avaliadas" />
      <GrupoPares codigo={dados.ente.codigo} pares={dados.pares} resumo={dados.resumo} />
      <Transparencia codigo={e.codigo} />
      {exercicios.map((ano) => (
        <Exercicio key={ano} ano={ano} obrigacoes={dados.obrigacoes} />
      ))}
      <LigacoesDoEnte codigo={e.codigo} atual="conformidade" />
    </>
  );
}

/** As obrigações de um exercício, 20 por página. */
function Exercicio({ ano, obrigacoes }: { ano: number; obrigacoes: Obrigacao[] }) {
  const doAno = useMemo(() => obrigacoes.filter((o) => o.exercicio === ano), [obrigacoes, ano]);
  const pagina = usePaginacao(doAno);
  return (
    <section className="cartao cartao-corpo">
      <h2 className="titulo-secao">Exercício de {ano}</h2>
      <table className="tabela tabela-obrigacoes">
        <thead>
          <tr>
            <th>Obrigação</th>
            <th className="n">Prazo</th>
            <th className="n">Entregue em</th>
            <th>Resultado</th>
          </tr>
        </thead>
        <tbody>
          {pagina.visiveis.map((o) => (
            <tr key={`${o.periodo}-${o.criterio}-${o.poder ?? ""}`}>
              <td>
                {o.rotulo}
                <div className="busca-detalhe">{o.dispositivo}</div>
              </td>
              <td className="n" data-rotulo="Prazo">
                {dataCurta(o.prazo)}
              </td>
              <td className="n" data-rotulo="Entregue em">
                {dataCurta(o.entregue_em)}
              </td>
              <td>
                <SeloResultado resultado={o.resultado} rotulo={o.rotulo_resultado} />
                {o.motivo && <div className="busca-detalhe">{o.motivo}</div>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <Paginacao {...pagina} rotulo={`obrigações de ${ano}`} />
    </section>
  );
}
