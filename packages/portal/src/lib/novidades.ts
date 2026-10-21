/**
 * Novidades: as mudanças e as versões do Lumen, lidas do `CHANGELOG.md` do repositório na hora de gerar o site
 * (a página não busca nada depois). Cada versão (`## 0.9.0 — 2026-10-21`, ou `## Não lançado` para o que já está no
 * ar sem número) tem as mudanças (`### Título`), cada uma com os itens e os subitens da lista.
 *
 * O aviso da aba conta as mudanças que entraram desde a última visita: o navegador guarda o identificador da
 * mais nova que a pessoa já viu (`CHAVE_VISTA`).
 */

/** Um item da lista de uma mudança, com os subitens. */
export interface ItemNovidade {
  texto: string;
  filhos: string[];
}

/** Uma mudança: o título (`###`) e a lista; texto solto entra como item sem subitens. */
export interface Novidade {
  id: string;
  titulo: string;
  itens: ItemNovidade[];
}

/** Uma versão: o número e a data (os dois `null` no que ainda não tem número) e as mudanças, da mais nova à mais velha. */
export interface VersaoNovidades {
  versao: string | null;
  data: string | null;
  novidades: Novidade[];
}

/** Onde o navegador guarda a mudança mais nova já vista. */
export const CHAVE_VISTA = "lumen.novidades.vista";
/** Evento que a página de novidades dispara ao marcar tudo como visto, para a aba apagar o aviso. */
export const EVENTO_VISTAS = "lumen:novidades-vistas";

/** "Tribunais de contas: o TCE-PR (ADR-050)" → "tribunais-de-contas-o-tce-pr-adr-050". */
function slug(texto: string): string {
  return texto.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

/** As versões do CHANGELOG, na ordem do arquivo (a mais nova primeiro); versão sem mudança fica de fora. */
export function lerChangelog(texto: string): VersaoNovidades[] {
  const versoes: VersaoNovidades[] = [];
  let versao: VersaoNovidades | null = null;
  let novidade: Novidade | null = null;
  let item: { texto: string[]; filhos: string[][] } | null = null;
  const fecharItem = () => {
    if (novidade && item) novidade.itens.push({ texto: item.texto.join(" "), filhos: item.filhos.map((f) => f.join(" ")) });
    item = null;
  };
  for (const linha of texto.split(/\r?\n/)) {
    const v = /^## (.+)$/.exec(linha);
    if (v) {
      fecharItem();
      const m = /^(\d+\.\d+\.\d+)\s+—\s+(\d{4}-\d{2}-\d{2})/.exec(v[1]!.trim());
      versao = { versao: m ? m[1]! : null, data: m ? m[2]! : null, novidades: [] };
      versoes.push(versao);
      novidade = null;
      continue;
    }
    const t = /^### (.+)$/.exec(linha);
    if (t && versao) {
      fecharItem();
      const titulo = t[1]!.trim();
      novidade = { id: `${versao.versao ?? "no-ar"}/${slug(titulo)}`, titulo, itens: [] };
      versao.novidades.push(novidade);
      continue;
    }
    if (!novidade) continue;
    const sub = /^\s{2,}- (.*)$/.exec(linha);
    const topo = /^- (.*)$/.exec(linha);
    if (topo) {
      fecharItem();
      item = { texto: [topo[1]!], filhos: [] };
    } else if (sub && item) {
      item.filhos.push([sub[1]!]);
    } else if (linha.trim() === "") {
      continue;
    } else if (item) {
      const continuacao = linha.trim();
      if (item.filhos.length && /^\s{4,}/.test(linha)) item.filhos[item.filhos.length - 1]!.push(continuacao);
      else item.texto.push(continuacao);
    } else {
      item = { texto: [linha.trim()], filhos: [] };
    }
  }
  fecharItem();
  return versoes.filter((x) => x.novidades.length > 0);
}

/** Os identificadores das mudanças, da mais nova à mais velha, para o aviso da aba. */
export function idsDasNovidades(versoes: VersaoNovidades[]): string[] {
  return versoes.flatMap((v) => v.novidades.map((n) => n.id));
}

/**
 * Quantas mudanças entraram desde a vista: as que vêm antes dela na lista. Sem nada guardado (primeira visita),
 * nenhuma; com a vista fora da lista (de uma versão já antiga), todas as da lista.
 */
export function naoVistas(ids: string[], vista: string | null): number {
  if (vista === null) return 0;
  const i = ids.indexOf(vista);
  return i === -1 ? ids.length : i;
}

/** Um pedaço de texto de um item: comum, código (`` `x` ``) ou destaque (`**x**`). */
export type Trecho = { tipo: "texto" | "codigo" | "forte"; valor: string };

/** O texto de um item em pedaços, para a página mostrar o código e o destaque sem interpretar HTML. */
export function trechos(texto: string): Trecho[] {
  const saida: Trecho[] = [];
  const padrao = /`([^`]+)`|\*\*([^*]+)\*\*/g;
  let ultimo = 0;
  for (const m of texto.matchAll(padrao)) {
    if (m.index! > ultimo) saida.push({ tipo: "texto", valor: texto.slice(ultimo, m.index) });
    saida.push(m[1] !== undefined ? { tipo: "codigo", valor: m[1] } : { tipo: "forte", valor: m[2]! });
    ultimo = m.index! + m[0].length;
  }
  if (ultimo < texto.length) saida.push({ tipo: "texto", valor: texto.slice(ultimo) });
  return saida;
}

/** "2026-10-21" → "21/10/2026". */
export function dataDaVersao(iso: string): string {
  const [a, m, d] = iso.split("-");
  return `${d}/${m}/${a}`;
}
