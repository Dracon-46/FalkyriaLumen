"use client";

/**
 * O fornecedor filtrado na Receita Federal (ADR-043): situação cadastral, abertura, atividade, porte, capital,
 * Simples e quadro societário, da base pública de CNPJ que os painéis publicam. Fatos do cadastro, sem leitura
 * sobre a empresa: a tela não marca nem ordena nada.
 */

import Link from "next/link";
import { useEffect, useState } from "react";
import { numero } from "@/lib/formato";
import { cnpj as formatarCnpj, dataCurta, moeda } from "@/lib/paineis";
import { cnpjDoTexto, urlDaPessoa } from "@/lib/pessoaJuridica";
import { anosDesde, carregarEmpresa, type EmpresaReceita, mesPorExtenso } from "@/lib/receita";
import { Numero } from "./Comuns";

const METODO = "https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-043.md";
/** CNAEs secundários mostrados antes de "ver todos". */
const SECUNDARIOS_INICIAIS = 5;

/** A leitura do fornecedor: carregando, lida, sem a base ou com erro. */
type Estado = { fase: "carregando" } | { fase: "pronta"; empresa: EmpresaReceita; mes: string | null }
  | { fase: "ausente" } | { fase: "erro" };

/** "Ativa desde 03/01/2005" e o motivo, quando há. */
function situacao(e: EmpresaReceita): string {
  const desde = e.data_situacao ? ` desde ${dataCurta(e.data_situacao)}` : "";
  const motivo = e.motivo?.nome ? ` (${e.motivo.nome.toLowerCase()})` : "";
  return `${e.situacao ?? "situação não informada"}${desde}${motivo}`;
}

/** Sócio pessoa jurídica: o CNPJ leva à página da empresa sócia (ADR-049). */
function SocioPj({ cnpj }: { cnpj?: string }) {
  const digitos = cnpj ? cnpjDoTexto(cnpj) : null;
  if (!digitos) return <>pessoa jurídica</>;
  return <>pessoa jurídica · <Link href={urlDaPessoa(digitos)}>{formatarCnpj(digitos)}</Link></>;
}

/** O cartão do fornecedor na Receita; não aparece enquanto a base de CNPJ não estiver publicada. */
export function EmpresaReceitaCartao({ cnpj }: { cnpj: string }) {
  const [estado, setEstado] = useState<Estado>({ fase: "carregando" });
  const [todos, setTodos] = useState(false);
  useEffect(() => {
    const c = new AbortController();
    setEstado({ fase: "carregando" });
    setTodos(false);
    carregarEmpresa(cnpj, c.signal)
      .then((r) => setEstado(r ? { fase: "pronta", empresa: r.empresa, mes: r.mes } : { fase: "ausente" }))
      .catch((e: Error) => {
        if (e.name !== "AbortError") setEstado({ fase: "erro" });
      });
    return () => c.abort();
  }, [cnpj]);

  if (estado.fase === "carregando" || estado.fase === "ausente") return null;
  if (estado.fase === "erro") {
    return <p className="busca-detalhe">O cadastro deste fornecedor na Receita não pôde ser lido agora.</p>;
  }
  const { empresa: e, mes } = estado;
  const anos = anosDesde(e.inicio_atividade);
  const secundarios = todos ? e.cnaes_secundarios : e.cnaes_secundarios.slice(0, SECUNDARIOS_INICIAIS);
  const lugar = e.exterior ? [e.exterior.cidade, e.exterior.pais?.nome].filter(Boolean).join(", ")
    : [e.municipio, e.uf].filter(Boolean).join(" · ");

  return (
    <section className="cartao cartao-corpo" aria-labelledby="titulo-receita">
      <h2 id="titulo-receita" className="titulo-secao">Na Receita Federal</h2>
      <p>
        <strong>{e.razao_social ?? formatarCnpj(e.cnpj)}</strong>
        {e.nome_fantasia ? ` · ${e.nome_fantasia}` : ""}
        <span className="busca-detalhe">
          {" "}
          {formatarCnpj(e.cnpj)} · {e.matriz === false ? "filial" : "matriz"}
          {lugar ? ` · ${lugar}` : ""}
        </span>
      </p>
      <div className="totais">
        <Numero rotulo="Situação cadastral" valor={e.situacao ?? "—"} detalhe={situacao(e)} />
        <Numero rotulo="Início da atividade" valor={e.inicio_atividade ? dataCurta(e.inicio_atividade) : "—"}
          detalhe={anos !== null ? `${numero(anos)} ${anos === 1 ? "ano" : "anos"}` : undefined} />
        <Numero rotulo="Capital social" valor={moeda(e.capital_social)} detalhe={e.porte ?? undefined} />
        <Numero rotulo="Simples Nacional" valor={e.simples?.mei ? "MEI" : e.simples?.simples ? "Optante" : "Não optante"}
          detalhe={e.simples?.mei && e.simples.mei_desde ? `desde ${dataCurta(e.simples.mei_desde)}`
            : e.simples?.simples && e.simples.simples_desde ? `desde ${dataCurta(e.simples.simples_desde)}` : undefined} />
      </div>
      {e.situacao_especial && (
        <p>
          Situação especial: <strong>{e.situacao_especial.toLowerCase()}</strong>
          {e.data_situacao_especial ? ` desde ${dataCurta(e.data_situacao_especial)}` : ""}.
        </p>
      )}
      <p>
        Natureza jurídica: {e.natureza?.nome ?? e.natureza?.codigo ?? "—"}.
        <br />
        Atividade principal: {e.cnae_principal ? `${e.cnae_principal.nome ?? ""} (CNAE ${e.cnae_principal.codigo})` : "—"}.
      </p>
      {e.cnaes_secundarios.length > 0 && (
        <details>
          <summary className="busca-detalhe">{numero(e.cnaes_secundarios.length)} atividades secundárias</summary>
          <ul className="busca-detalhe">
            {secundarios.map((c) => (
              <li key={c.codigo}>
                {c.nome ?? "—"} (CNAE {c.codigo})
              </li>
            ))}
          </ul>
          {e.cnaes_secundarios.length > SECUNDARIOS_INICIAIS && !todos && (
            <button type="button" className="botao-link" onClick={() => setTodos(true)}>
              ver todas
            </button>
          )}
        </details>
      )}
      <h3 className="modal-subtitulo">Quadro societário</h3>
      {e.socios.length === 0 ? (
        <p className="busca-detalhe">A Receita não lista sócios para esta empresa (é o caso do empresário individual e do MEI).</p>
      ) : (
        <div className="tabela-rolavel">
          <table className="tabela">
            <thead>
              <tr>
                <th>Sócio</th>
                <th>Qualificação</th>
                <th>Desde</th>
              </tr>
            </thead>
            <tbody>
              {e.socios.map((s, i) => (
                <tr key={`${s.nome}-${i}`}>
                  <td>
                    {s.nome}
                    <div className="busca-detalhe">
                      {s.tipo === "PJ" ? <SocioPj cnpj={s.cnpj} />
                        : s.tipo === "estrangeiro" ? `estrangeiro${s.pais ? ` · ${s.pais}` : ""}` : "pessoa física"}
                    </div>
                  </td>
                  <td>{s.qualificacao ?? "—"}</td>
                  <td>{s.desde ? dataCurta(s.desde) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="busca-detalhe">
        Receita Federal, dados abertos do CNPJ{mes ? `, base de ${mesPorExtenso(mes)}` : ""}. São os dados do cadastro,
        como a Receita os publica; endereço, telefone, e-mail e o CPF dos sócios ficam de fora.{" "}
        <a href={METODO} target="_blank" rel="noreferrer">
          O que entra e por quê
        </a>
        .
      </p>
    </section>
  );
}
