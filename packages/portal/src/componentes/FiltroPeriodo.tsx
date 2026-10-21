"use client";

/**
 * Filtro de período das abas (Contratações, Economia, Conformidade): do primeiro ao último mês, com atalhos.
 * Fica na URL (`?de=AAAA-MM&ate=AAAA-MM`, `lerPeriodo`), para compartilhar a consulta.
 *
 * As opções vêm do que a aba tem: meses (`AAAA-MM`) ou anos (`AAAA`). Um ano entra como o ano inteiro
 * (janeiro no primeiro, dezembro no último): é o caso dos anos antigos das Contratações, publicados ano a ano,
 * e das abas que só têm ano (os exercícios da Conformidade, as séries longas da Economia).
 */

import type { ReactNode } from "react";
import { Escolha } from "@/componentes/Escolha";
import { mesCurto } from "@/lib/paineis";
import { type PeriodoMeses, temRecorte } from "@/lib/periodo";

/** Um atalho: o rótulo do botão e o período que ele escolhe. */
export interface AtalhoPeriodo {
  rotulo: string;
  p: PeriodoMeses;
}

/** O primeiro e o último mês de uma opção (`AAAA-MM`, ou o ano inteiro de `AAAA`). */
const inicioDe = (k: string) => (k.length === 4 ? `${k}-01` : k);
const fimDe = (k: string) => (k.length === 4 ? `${k}-12` : k);
const rotuloDe = (k: string) => (k.length === 4 ? k : mesCurto(k));

/** Os atalhos de sempre: tudo, o último mês e os últimos 3 (se houver mês a mês) e cada ano. */
export function atalhosPadrao(opcoes: string[], anos = true): AtalhoPeriodo[] {
  const meses = opcoes.filter((k) => k.length === 7);
  const ultimo = meses[meses.length - 1];
  const lista: AtalhoPeriodo[] = [{ rotulo: "Tudo", p: { de: null, ate: null } }];
  if (ultimo) {
    lista.push({ rotulo: "Último mês", p: { de: ultimo, ate: ultimo } });
    if (meses.length >= 3) lista.push({ rotulo: "Últimos 3 meses", p: { de: meses[meses.length - 3]!, ate: ultimo } });
  }
  if (anos) {
    for (const a of Array.from(new Set(opcoes.map((k) => k.slice(0, 4))))) {
      lista.push({ rotulo: a, p: { de: `${a}-01`, ate: `${a}-12` } });
    }
  }
  return lista;
}

/** O filtro: primeiro e último período, os atalhos e, com recorte, a nota de como o recorte é feito. */
export function FiltroPeriodo({
  opcoes,
  periodo,
  onMudar,
  atalhos,
  nota,
  titulo = "Período",
}: {
  opcoes: string[];
  periodo: PeriodoMeses;
  onMudar: (p: PeriodoMeses) => void;
  atalhos?: AtalhoPeriodo[];
  nota?: ReactNode;
  titulo?: string;
}) {
  const ordenadas = [...new Set(opcoes)].sort();
  if (ordenadas.length < 2) return null;
  const primeiro = inicioDe(ordenadas[0]!);
  const ultimo = fimDe(ordenadas[ordenadas.length - 1]!);
  const deTela = (fn: (k: string) => string) =>
    [...ordenadas].reverse().map((k) => ({ valor: fn(k), rotulo: rotuloDe(k), detalhe: k.length === 4 ? "ano inteiro" : k.slice(0, 4) }));
  // O valor escolhido precisa estar entre as opções: um mês dentro de um ano publicado ano a ano vira o ano
  const ajustar = (m: string | null, fn: (k: string) => string, padrao: string) => {
    if (!m) return padrao;
    const k = ordenadas.find((o) => o === m || (o.length === 4 && m.startsWith(o)));
    return k ? fn(k) : m;
  };
  const lista = atalhos ?? atalhosPadrao(ordenadas);
  const igual = (a: PeriodoMeses, b: PeriodoMeses) =>
    (a.de ?? primeiro) === (b.de ?? primeiro) && (a.ate ?? ultimo) === (b.ate ?? ultimo);
  return (
    <section className="cartao cartao-corpo filtro-periodo" aria-label={titulo}>
      <span className="filtro-periodo-titulo">{titulo}</span>
      <Escolha
        rotulo="Início"
        opcoes={deTela(inicioDe)}
        valor={ajustar(periodo.de, inicioDe, primeiro)}
        onEscolher={(de) => onMudar({ de, ate: periodo.ate && periodo.ate < de ? fimDe(de.slice(0, 4)) : periodo.ate })}
      />
      <span aria-hidden="true">a</span>
      <Escolha
        rotulo="Fim"
        opcoes={deTela(fimDe)}
        valor={ajustar(periodo.ate, fimDe, ultimo)}
        onEscolher={(ate) => onMudar({ de: periodo.de && periodo.de > ate ? inicioDe(ate.slice(0, 4)) : periodo.de, ate })}
      />
      <span className="filtro-periodo-atalhos">
        {lista.map((a) => (
          <button key={a.rotulo} type="button" className="botao" aria-pressed={igual(periodo, a.p)} onClick={() => onMudar(a.p)}>
            {a.rotulo}
          </button>
        ))}
      </span>
      {temRecorte(periodo) && nota && <p className="busca-detalhe filtro-periodo-nota">{nota}</p>}
    </section>
  );
}
