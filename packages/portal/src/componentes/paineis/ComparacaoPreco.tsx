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

/** O botão de abrir a comparação; sem código de catálogo, o motivo de não comparar. */
export function BotaoComparar({ item, aberto, onAlternar }: { item: ItemProcesso; aberto: boolean; onAlternar: () => void }) {
  if (!podeComparar(item)) {
    return (
      <div className="busca-detalhe">
        Sem código do catálogo do Compras.gov.br: o órgão não classificou o item, e sem isso a comparação de preço
        não é segura.
      </div>
    );
  }
  return (
    <div>
      <button type="button" className="botao-link" aria-expanded={aberto} onClick={onAlternar}>
        {aberto ? "fechar a comparação de preço" : "comparar o preço com outros órgãos"}
      </button>
    </div>
  );
}

/** Pede o preço homologado (se houver resultado) e a referência, e mostra a comparação. */
export function ComparacaoPreco({ item, processo }: { item: ItemProcesso; processo: Processo }) {
  const [estado, setEstado] = useState<Estado>({ fase: "carregando" });
  useEffect(() => {
    const c = new AbortController();
    (async () => {
      let preco = item.valorUnitario;
      let tipoPreco: "homologado" | "estimado" = "estimado";
      if (item.temResultado) {
        const r = (await carregarResultados(processo.chave, item.numero, c.signal)).find((x) => x.valorUnitario !== null);
        if (r) {
          preco = r.valorUnitario;
          tipoPreco = "homologado";
        }
      }
      if (preco === null || preco <= 0) throw new Error("o item não tem preço unitário publicado");
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

/** A faixa das compras comparáveis (do mínimo ao máximo, com os quartis) e onde o preço do item cai. */
function Faixa({ c }: { c: Comparacao }) {
  if (c.minimo === null || c.maximo === null || c.q1 === null || c.q3 === null || c.mediana === null) return null;
  // Escala logarítmica: preços de compra variam por ordens de grandeza
  const lo = Math.log(Math.min(c.minimo, c.preco));
  const hi = Math.log(Math.max(c.maximo, c.preco));
  const pos = (v: number) => (hi > lo ? ((Math.log(v) - lo) / (hi - lo)) * 100 : 50);
  return (
    <div className="preco-faixa" role="img"
         aria-label={`Compras comparáveis de ${moeda(c.minimo)} a ${moeda(c.maximo)}, metade entre ${moeda(c.q1)} e ${moeda(c.q3)}, mediana ${moeda(c.mediana)}; o item, ${moeda(c.preco)}`}>
      <span className="preco-faixa-linha" style={{ left: `${pos(c.minimo)}%`, width: `${pos(c.maximo) - pos(c.minimo)}%` }} />
      <span className="preco-faixa-caixa" style={{ left: `${pos(c.q1)}%`, width: `${Math.max(pos(c.q3) - pos(c.q1), 0.5)}%` }} />
      <span className="preco-faixa-mediana" style={{ left: `${pos(c.mediana)}%` }} />
      <span className={`preco-faixa-item${c.situacao === "acima" ? " preco-faixa-item-acima" : ""}`} style={{ left: `${pos(c.preco)}%` }}
            title={`Este item: ${moeda(c.preco)}`} />
    </div>
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
      {c.n > 0 && (
        <>
          <Faixa c={c} />
          <dl className="preco-numeros">
            <div><dt>Mínimo</dt><dd>{moeda(c.minimo)}</dd></div>
            <div><dt>1º quartil</dt><dd>{moeda(c.q1)}</dd></div>
            <div><dt>Mediana</dt><dd>{moeda(c.mediana)}</dd></div>
            <div><dt>3º quartil</dt><dd>{moeda(c.q3)}</dd></div>
            <div><dt>Máximo</dt><dd>{moeda(c.maximo)}</dd></div>
          </dl>
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
