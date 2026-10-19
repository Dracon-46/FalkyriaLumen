"use client";

/**
 * Comparação de preço de um item do processo (ADR-036): o preço homologado (ou, sem resultado, o estimado)
 * contra o que outros órgãos pagaram pelo mesmo código do catálogo do Compras.gov.br nos 12 meses anteriores.
 * Mostra a referência inteira (quartis, mediana, as compras que entraram e as que ficaram fora, e por quê) e,
 * pelos parâmetros do DOC-07, se o preço fica acima da referência comparada. Pedido só quando a pessoa clica.
 */

import { useEffect, useState } from "react";
import { Paginacao, usePaginacao } from "@/componentes/Paginacao";
import { carregarResultados, type ItemProcesso, type Processo } from "@/lib/contratacao";
import { numero } from "@/lib/formato";
import { reconhecerAnp } from "@/lib/mercado";
import { cnpj, dataCurta, moeda } from "@/lib/paineis";
import {
  carregarComparacao, type ComparacaoPreco as Comparacao, type CompraComparavel, FONTE_PRECOS, PARAMETROS_PRECO,
} from "@/lib/precos";

/** O andamento da comparação. */
type Estado = { fase: "carregando" } | { fase: "pronto"; c: Comparacao } | { fase: "erro"; erro: string };

/** "1,44" para a razão, com duas casas. */
const vezes = (x: number | null) => (x === null ? "—" : `${x.toLocaleString("pt-BR", { maximumFractionDigits: 2, minimumFractionDigits: 2 })}×`);

/** O item tem o código do catálogo do Compras.gov.br, que a comparação exige? */
export const podeComparar = (item: ItemProcesso) => !!item.catalogo && item.material !== null;

/** As comparações de um item: com outros órgãos (catálogo) e com o mercado (ANP). */
export type TipoComparacao = "orgaos" | "anp";

/** Os botões das comparações que o item admite; sem nenhuma, o motivo. */
export function BotoesComparar({ item, aberta, onAbrir }: {
  item: ItemProcesso; aberta: TipoComparacao | null; onAbrir: (t: TipoComparacao | null) => void;
}) {
  const produto = reconhecerAnp(item.descricao, item.unidade);
  if (!podeComparar(item) && !produto) {
    return (
      <div className="busca-detalhe">
        Sem comparação de preço: o órgão não informou o código do catálogo do Compras.gov.br, e o item não é
        combustível nem gás de cozinha reconhecido sem ambiguidade.
      </div>
    );
  }
  const botao = (t: TipoComparacao, rotulo: string) => (
    <button type="button" className="botao-link" aria-expanded={aberta === t} onClick={() => onAbrir(aberta === t ? null : t)}>
      {aberta === t ? "fechar a comparação" : rotulo}
    </button>
  );
  return (
    <div className="preco-botoes">
      {podeComparar(item) && botao("orgaos", "comparar o preço com outros órgãos")}
      {produto && botao("anp", produto === "GLP" ? "comparar com o preço de revenda (ANP)" : "comparar com o preço de bomba (ANP)")}
    </div>
  );
}

/**
 * O preço que se compara: o homologado (o do primeiro resultado com preço, e a data dele), ou, sem resultado,
 * o estimado. Erro quando o item não tem preço unitário.
 */
export async function precoDoItem(item: ItemProcesso, processo: Processo, sinal?: AbortSignal):
  Promise<{ preco: number; tipoPreco: "homologado" | "estimado"; data: string | null }> {
  if (item.temResultado) {
    const r = (await carregarResultados(processo.chave, item.numero, sinal)).find((x) => x.valorUnitario !== null && x.valorUnitario > 0);
    if (r) return { preco: r.valorUnitario!, tipoPreco: "homologado", data: r.data };
  }
  if (item.valorUnitario === null || item.valorUnitario <= 0) throw new Error("o item não tem preço unitário publicado");
  return { preco: item.valorUnitario, tipoPreco: "estimado", data: null };
}

/** Pede o preço homologado (se houver resultado) e a referência, e mostra a comparação. */
export function ComparacaoPreco({ item, processo }: { item: ItemProcesso; processo: Processo }) {
  const [estado, setEstado] = useState<Estado>({ fase: "carregando" });
  useEffect(() => {
    const c = new AbortController();
    (async () => {
      const { preco, tipoPreco } = await precoDoItem(item, processo, c.signal);
      const data = (processo.publicadoEm ?? new Date().toISOString()).slice(0, 10);
      const ano = Number(processo.chave.slice(-4));
      return carregarComparacao({
        catalogo: item.catalogo!, material: item.material!, unidade: item.unidade, preco, tipoPreco, data,
        uasg: processo.unidade.uasg, numeroCompra: processo.numero, ano,
      }, c.signal);
    })()
      .then((comp) => setEstado({ fase: "pronto", c: comp }))
      .catch((e: Error) => {
        if (e.name !== "AbortError") setEstado({ fase: "erro", erro: e.message });
      });
    return () => c.abort();
  }, [item, processo]);

  if (estado.fase === "carregando") return <p className="busca-detalhe">Buscando as compras do mesmo item…</p>;
  if (estado.fase === "erro") return <p className="busca-detalhe">Não deu para comparar agora: {estado.erro}.</p>;
  return <Resultado c={estado.c} item={item} />;
}

/** A frase do resultado, na linguagem do DOC-08. */
function Leitura({ c }: { c: Comparacao }) {
  const pct = c.acimaDe !== null ? `${Math.round(c.acimaDe * 100)}%` : "—";
  const base = `${vezes(c.razao)} a mediana de ${numero(c.n)} compras do mesmo item`;
  switch (c.situacao) {
    case "acima":
      return (
        <p className="faixa preco-leitura" role="note">
          <strong>Preço acima da referência comparada:</strong> {base}, mais alto que {pct} delas (escore robusto{" "}
          {c.escore?.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}; o DOC-07 marca a partir de{" "}
          {PARAMETROS_PRECO.escoreDisparo.toLocaleString("pt-BR")}). Vale conferir a especificação, a quantidade, o
          lugar de entrega e a pesquisa de preços da própria compra. Não é conclusão sobre a compra.
        </p>
      );
    case "abaixo":
      return (
        <p className="preco-leitura">
          <strong>Preço bem abaixo da referência comparada:</strong> {base}. Costuma ser unidade ou especificação
          diferente.
        </p>
      );
    case "dentro":
      return (
        <p className="preco-leitura">
          <strong>Sem marcação pelo critério do DOC-07:</strong> {base}, mais alto que {pct} delas. As compras
          comparáveis variam o bastante para que o preço não destoe (escore robusto{" "}
          {c.escore?.toLocaleString("pt-BR", { maximumFractionDigits: 1 }) ?? "—"}; a marcação começa em{" "}
          {PARAMETROS_PRECO.escoreDisparo.toLocaleString("pt-BR")}).
        </p>
      );
    case "poucas":
      return (
        <p className="preco-leitura">
          <strong>Poucas compras comparáveis:</strong> {numero(c.n)} no período (a comparação estatística pede{" "}
          {PARAMETROS_PRECO.minimoComparaveis}). O preço é {vezes(c.razao)} a mediana delas; os números são contexto, sem
          marcação.
        </p>
      );
    case "fora_de_escala":
      return (
        <p className="preco-leitura">
          <strong>Razão fora de escala ({vezes(c.razao)} a mediana):</strong> quase sempre é unidade diferente, ou o
          valor total lançado como unitário (aqui ou nas outras compras). Confira a unidade antes de qualquer leitura.
        </p>
      );
    default:
      return (
        <p className="preco-leitura">
          <strong>Nenhuma compra comparável</strong> nos 12 meses anteriores
          {c.recebidos > 0 && c.unidadeMaisComum
            ? ` (as ${numero(c.recebidos)} compras do código usam outra unidade; a mais comum: ${c.unidadeMaisComum.toLowerCase()})`
            : ""}.
        </p>
      );
  }
}

/** Os cinco números de uma distribuição de preços, o preço do item e se ele está marcado. */
export interface Distribuicao {
  minimo: number;
  q1: number;
  mediana: number;
  q3: number;
  maximo: number;
  preco: number;
  marcado: boolean;
  rotulo: string;   // "Compras comparáveis", "Preços de revenda"
}

/** A faixa de preços (do mínimo ao máximo, com os quartis) e onde o preço do item cai. */
export function Faixa({ d }: { d: Distribuicao }) {
  // Escala logarítmica: preços variam por ordens de grandeza
  const lo = Math.log(Math.min(d.minimo, d.preco));
  const hi = Math.log(Math.max(d.maximo, d.preco));
  const pos = (v: number) => (hi > lo ? ((Math.log(v) - lo) / (hi - lo)) * 100 : 50);
  return (
    <div className="preco-faixa" role="img"
         aria-label={`${d.rotulo} de ${moeda(d.minimo)} a ${moeda(d.maximo)}, metade entre ${moeda(d.q1)} e ${moeda(d.q3)}, mediana ${moeda(d.mediana)}; o item, ${moeda(d.preco)}`}>
      <span className="preco-faixa-linha" style={{ left: `${pos(d.minimo)}%`, width: `${pos(d.maximo) - pos(d.minimo)}%` }} />
      <span className="preco-faixa-caixa" style={{ left: `${pos(d.q1)}%`, width: `${Math.max(pos(d.q3) - pos(d.q1), 0.5)}%` }} />
      <span className="preco-faixa-mediana" style={{ left: `${pos(d.mediana)}%` }} />
      <span className={`preco-faixa-item${d.marcado ? " preco-faixa-item-acima" : ""}`} style={{ left: `${pos(d.preco)}%` }}
            title={`Este item: ${moeda(d.preco)}`} />
    </div>
  );
}

/** Mínimo, quartis, mediana e máximo, lado a lado. */
export function Numeros({ d }: { d: Pick<Distribuicao, "minimo" | "q1" | "mediana" | "q3" | "maximo"> }) {
  return (
    <dl className="preco-numeros">
      <div><dt>Mínimo</dt><dd>{moeda(d.minimo)}</dd></div>
      <div><dt>1º quartil</dt><dd>{moeda(d.q1)}</dd></div>
      <div><dt>Mediana</dt><dd>{moeda(d.mediana)}</dd></div>
      <div><dt>3º quartil</dt><dd>{moeda(d.q3)}</dd></div>
      <div><dt>Máximo</dt><dd>{moeda(d.maximo)}</dd></div>
    </dl>
  );
}

/** A comparação inteira: a leitura, a faixa, os números, o que ficou fora e as compras que entraram. */
function Resultado({ c, item }: { c: Comparacao; item: ItemProcesso }) {
  const pagina = usePaginacao(c.comparaveis);
  const fora = c.descartados;
  return (
    <div className="preco-comparacao">
      <p className="busca-detalhe">
        Preço comparado: <strong>{moeda(c.preco)}</strong> por {item.unidade?.toLowerCase() ?? "unidade"} ({c.tipoPreco}
        {c.tipoPreco === "estimado" ? ", sem resultado publicado" : ""}).
      </p>
      <Leitura c={c} />
      {c.n > 0 && c.minimo !== null && c.q1 !== null && c.mediana !== null && c.q3 !== null && c.maximo !== null && (
        <>
          {c.situacao !== "fora_de_escala" && (
            <Faixa d={{ minimo: c.minimo, q1: c.q1, mediana: c.mediana, q3: c.q3, maximo: c.maximo, preco: c.preco,
                        marcado: c.situacao === "acima", rotulo: "Compras comparáveis" }} />
          )}
          <Numeros d={{ minimo: c.minimo, q1: c.q1, mediana: c.mediana, q3: c.q3, maximo: c.maximo }} />
        </>
      )}
      {(fora.outraUnidade + fora.totalComoUnitario + fora.propriaCompra + fora.semPreco) > 0 && (
        <p className="busca-detalhe">
          Fora da conta:{" "}
          {[
            fora.outraUnidade && `${numero(fora.outraUnidade)} em outra unidade`,
            fora.totalComoUnitario && `${numero(fora.totalComoUnitario)} com quantidade 1 em unidade que se divide (costuma ser o valor total lançado como unitário)`,
            fora.propriaCompra && `${numero(fora.propriaCompra)} da própria compra`,
            fora.semPreco && `${numero(fora.semPreco)} sem preço`,
          ].filter(Boolean).join("; ")}.
        </p>
      )}
      {c.n > 0 && (
        <>
          <div className="tabela-rolavel">
            <table className="tabela">
              <thead>
                <tr>
                  <th>Compra comparável</th>
                  <th className="n">Unitário</th>
                </tr>
              </thead>
              <tbody>
                {pagina.visiveis.map((x, n) => <LinhaCompra key={`${x.idCompra}-${n}`} x={x} />)}
              </tbody>
            </table>
          </div>
          <Paginacao {...pagina} rotulo="compras comparáveis" />
        </>
      )}
      <p className="busca-detalhe">
        Fonte: <a href={FONTE_PRECOS.replace("/modulo-pesquisa-preco", "/swagger-ui/index.html")} target="_blank" rel="noreferrer">pesquisa
        de preços do Compras.gov.br</a>, compras de {dataCurta(c.de)} a {dataCurta(c.ate)} com o código {item.catalogo}{" "}
        ({item.material ? "CATMAT" : "CATSER"}), lidas agora; cobre as compras feitas pelo sistema federal, de qualquer
        esfera. Mediana, quartis e escore robusto do DOC-07 (regra A-01), com os parâmetros iniciais, não calibrados.
        Especificação superior, entrega em lugar distante, volume pequeno e urgência explicam boa parte das diferenças.
      </p>
    </div>
  );
}

/** Uma compra comparável: órgão, lugar, data, quantidade e fornecedor (pessoa física sem identificação), e o preço. */
function LinhaCompra({ x }: { x: CompraComparavel }) {
  return (
    <tr>
      <td>
        {x.orgao ?? "—"}
        <div className="busca-detalhe">
          {[x.municipio && `${x.municipio}${x.uf ? `/${x.uf}` : ""}`, dataCurta(x.data),
            x.quantidade !== null && `${numero(x.quantidade)} ${x.unidade?.toLowerCase() ?? ""}`.trim(),
            x.fornecedor ? `${x.fornecedor.nome ?? "—"} (${cnpj(x.fornecedor.cnpj)})` : "fornecedor pessoa física ou estrangeira"]
            .filter(Boolean).join(" · ")}
        </div>
      </td>
      <td className="n">{moeda(x.preco)}</td>
    </tr>
  );
}
