"use client";

/**
 * Comparação do preço de combustível e de gás de cozinha com o preço de revenda da ANP (ADR-037; regra A-05):
 * o preço homologado (ou o estimado) contra a distribuição do levantamento semanal, posto a posto, no
 * município da unidade compradora ou na UF, na semana da compra. Pedida só quando a pessoa clica.
 */

import { useEffect, useState } from "react";
import type { ItemProcesso, Processo } from "@/lib/contratacao";
import { numero } from "@/lib/formato";
import {
  carregarComparacaoAnp, type ComparacaoAnp, NOME_PRODUTO, type ProdutoAnp, UNIDADE_PRODUTO,
} from "@/lib/mercado";
import { dataCurta, moeda } from "@/lib/paineis";
import { Faixa, Numeros, precoDoItem } from "./ComparacaoPreco";

/** O andamento da comparação. */
type Estado = { fase: "carregando" } | { fase: "pronto"; c: ComparacaoAnp } | { fase: "erro"; erro: string };

/** "1,44×", com duas casas. */
const vezes = (x: number | null) => (x === null ? "—" : `${x.toLocaleString("pt-BR", { maximumFractionDigits: 2, minimumFractionDigits: 2 })}×`);

/** Pede o preço do item e a referência da ANP, e mostra a comparação. */
export function ComparacaoMercado({ item, processo, produto }: { item: ItemProcesso; processo: Processo; produto: ProdutoAnp }) {
  const [estado, setEstado] = useState<Estado>({ fase: "carregando" });
  useEffect(() => {
    const c = new AbortController();
    (async () => {
      const { preco, tipoPreco, data } = await precoDoItem(item, processo, c.signal);
      const quando = (data ?? processo.publicadoEm ?? new Date().toISOString()).slice(0, 10);
      return carregarComparacaoAnp(produto, preco, tipoPreco, quando, processo.unidade.uf, processo.unidade.ibge, c.signal);
    })()
      .then((comp) => setEstado({ fase: "pronto", c: comp }))
      .catch((e: Error) => {
        if (e.name !== "AbortError") setEstado({ fase: "erro", erro: e.message });
      });
    return () => c.abort();
  }, [item, processo, produto]);

  if (estado.fase === "carregando") return <p className="busca-detalhe">Buscando o preço de revenda da ANP…</p>;
  if (estado.fase === "erro") return <p className="busca-detalhe">Não deu para comparar agora: {estado.erro}.</p>;
  return <Resultado c={estado.c} processo={processo} />;
}

/** A frase do resultado, na linguagem do DOC-08. */
function Leitura({ c, lugar }: { c: ComparacaoAnp; lugar: string }) {
  const r = c.referencia;
  if (!r) return <p className="preco-leitura"><strong>Sem referência da ANP:</strong> {c.motivo}.</p>;
  const base = `${vezes(c.razao)} a mediana do preço de revenda de ${NOME_PRODUTO[c.produto]} em ${lugar}, na semana de ` +
    `${dataCurta(r.inicio)} a ${dataCurta(r.fim)} (${numero(r.n)} coletas da ANP)`;
  const limiar = c.limiar.toLocaleString("pt-BR", { minimumFractionDigits: 2 });
  switch (c.situacao) {
    case "acima":
      return (
        <p className="faixa preco-leitura" role="note">
          <strong>Preço acima da referência de mercado:</strong> {base}; a regra A-05 marca a partir de {limiar}×.
          Compra pública costuma incluir entrega no local, prazo de pagamento e cartão de abastecimento: vale conferir o
          que o preço inclui. Não é conclusão sobre a compra.
          {c.conferirUnidade && " A razão passa de 3×: confira antes a unidade e a quantidade (galão contra litro, total lançado como unitário)."}
        </p>
      );
    case "fora_de_escala":
      return (
        <p className="preco-leitura">
          <strong>Razão fora de escala ({vezes(c.razao)} a mediana):</strong> quase sempre é unidade diferente, preço
          simbólico ou o valor total lançado como unitário. Confira a unidade antes de qualquer leitura.
        </p>
      );
    default:
      return <p className="preco-leitura"><strong>Sem marcação pela A-05:</strong> {base}; a marcação começa em {limiar}×.</p>;
  }
}

/** A comparação inteira: o preço, a leitura, a faixa, os números e a fonte. */
function Resultado({ c, processo }: { c: ComparacaoAnp; processo: Processo }) {
  const r = c.referencia;
  const lugar = !r ? "" : r.escopo === "municipio" ? `${processo.unidade.municipio ?? "no município"}/${processo.unidade.uf ?? ""}`
    : `${processo.unidade.uf ?? "na UF"} (a UF inteira: o município não tem coletas suficientes)`;
  return (
    <div className="preco-comparacao">
      <p className="busca-detalhe">
        Preço comparado: <strong>{moeda(c.preco)}</strong> por {UNIDADE_PRODUTO(c.produto)} ({c.tipoPreco}
        {c.tipoPreco === "estimado" ? ", sem resultado publicado" : ""}), {NOME_PRODUTO[c.produto]}, em {dataCurta(c.data)}.
      </p>
      <Leitura c={c} lugar={lugar} />
      {r && (
        <>
          {c.situacao !== "fora_de_escala" && (
            <Faixa d={{ minimo: r.minimo, q1: r.q1, mediana: r.mediana, q3: r.q3, maximo: r.maximo, preco: c.preco,
                        marcado: c.situacao === "acima", rotulo: "Preços de revenda" }} />
          )}
          <Numeros d={r} />
        </>
      )}
      <p className="busca-detalhe">
        Fonte: ANP, levantamento semanal de preços de combustíveis e GLP (revenda, posto a posto)
        {r && <>, <a href={r.planilha} target="_blank" rel="noreferrer">planilha da semana</a></>}; o município conta
        com 5 coletas ou mais, senão vale a UF com 10 ou mais. Limiar da regra A-05 (ADR-027): 1,20× a mediana no
        combustível e 1,25× no gás de cozinha, iniciais e não calibrados.
      </p>
    </div>
  );
}
