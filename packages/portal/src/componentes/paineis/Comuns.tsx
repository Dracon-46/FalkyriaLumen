"use client";

/**
 * Peças comuns aos painéis de contratações e de conformidade: busca de ente,
 * aviso metodológico (PUB-08), números em destaque, gráfico de barras por mês
 * e o selo de resultado da conformidade.
 */

import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  buscarEntes,
  buscarOrgaos,
  carregarEntes,
  carregarOrgaos,
  cnpj,
  descreverEnte,
  descreverOrgao,
  topoDoEixo,
  type EnteBusca,
  type OrgaoBusca,
  type Resultado,
} from "@/lib/paineis";

/** Endereço da metodologia completa, no repositório público do projeto. */
export const METODOLOGIA = "https://github.com/Dracon-46/FalkyriaLumen/blob/main/docs/adr/ADR-028.md";

// ------------------------------------------------------------------------------------------ busca

/** Um item da lista de resultados: um ente ou, na busca de contratações, um órgão. */
type Item = { tipo: "ente"; e: EnteBusca } | { tipo: "orgao"; o: OrgaoBusca };

/**
 * Campo de busca de ente (União, estado ou município), com a lista de resultados logo abaixo. Com
 * `onEscolherOrgao`, busca também os órgãos que publicaram no PNCP (prefeituras, câmaras, autarquias como um
 * serviço autônomo de água e esgoto, fundações e empresas públicas), pelo nome, pela sigla ou pelo CNPJ.
 */
export function BuscaEnte({
  onEscolher,
  onEscolherOrgao,
  rotulo,
}: {
  onEscolher: (codigo: string) => void;
  onEscolherOrgao?: (cnpj: string) => void;
  rotulo: string;
}) {
  const [entes, setEntes] = useState<EnteBusca[] | null>(null);
  const [orgaos, setOrgaos] = useState<OrgaoBusca[] | null>(null);
  const [erro, setErro] = useState(false);
  const [termo, setTermo] = useState("");
  const [indice, setIndice] = useState(0);
  const [aberta, setAberta] = useState(false);
  const caixa = useRef<HTMLDivElement>(null);
  const comOrgaos = onEscolherOrgao !== undefined;
  const achados = useMemo<Item[]>(
    () => [
      ...(entes ? buscarEntes(termo, entes, comOrgaos ? 6 : 12) : []).map((e) => ({ tipo: "ente" as const, e })),
      ...(orgaos ? buscarOrgaos(termo, orgaos) : []).map((o) => ({ tipo: "orgao" as const, o })),
    ],
    [termo, entes, orgaos, comOrgaos],
  );

  useEffect(() => {
    if (!aberta || entes !== null) return;
    carregarEntes()
      .then(setEntes)
      .catch(() => {
        setErro(true);
        setEntes([]);
      });
  }, [aberta, entes]);

  useEffect(() => {
    if (!aberta || !comOrgaos || orgaos !== null) return;
    carregarOrgaos()
      .then(setOrgaos)
      .catch(() => setOrgaos([]));
  }, [aberta, comOrgaos, orgaos]);

  useEffect(() => {
    const fora = (e: PointerEvent) => {
      if (caixa.current && !caixa.current.contains(e.target as Node)) setAberta(false);
    };
    document.addEventListener("pointerdown", fora);
    return () => document.removeEventListener("pointerdown", fora);
  }, []);

  const escolher = (item: Item | undefined) => {
    if (!item) return;
    if (item.tipo === "ente") onEscolher(item.e.codigo);
    else onEscolherOrgao?.(item.o.cnpj);
    setTermo("");
    setAberta(false);
  };

  return (
    <div className="busca-ente" ref={caixa}>
      <input
        value={termo}
        placeholder={rotulo}
        aria-label={rotulo}
        role="combobox"
        aria-expanded={aberta && achados.length > 0}
        aria-controls="busca-ente-lista"
        aria-activedescendant={aberta && achados[indice] ? `busca-ente-${indice}` : undefined}
        onFocus={() => setAberta(true)}
        onChange={(e) => {
          setTermo(e.target.value);
          setIndice(0);
          setAberta(true);
        }}
        onKeyDown={(e) => {
          if (e.key === "Escape") setAberta(false);
          else if (e.key === "ArrowDown") {
            e.preventDefault();
            setIndice((i) => Math.min(i + 1, achados.length - 1));
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            setIndice((i) => Math.max(i - 1, 0));
          } else if (e.key === "Enter") escolher(achados[indice]);
        }}
      />
      {aberta && termo && (
        <ul id="busca-ente-lista" role="listbox" className="busca-ente-lista">
          {entes === null && <li className="busca-vazio">Carregando o cadastro…</li>}
          {entes !== null && comOrgaos && orgaos === null && achados.length === 0 && (
            <li className="busca-vazio">Carregando os órgãos…</li>
          )}
          {entes !== null && (!comOrgaos || orgaos !== null) && achados.length === 0 && (
            <li className="busca-vazio">{erro ? "O cadastro de entes não está disponível agora." : "Nada encontrado."}</li>
          )}
          {achados.map((item, i) => (
            <li key={item.tipo === "ente" ? `e${item.e.codigo}` : `o${item.o.cnpj}`}>
              <button
                id={`busca-ente-${i}`}
                type="button"
                role="option"
                aria-selected={i === indice}
                onMouseEnter={() => setIndice(i)}
                onClick={() => escolher(item)}
              >
                <span>{item.tipo === "ente" ? item.e.nome : item.o.nome}</span>
                <span className="busca-detalhe">
                  {item.tipo === "ente" ? descreverEnte(item.e) : `${descreverOrgao(item.o)} · CNPJ ${cnpj(item.o.cnpj)}`}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ------------------------------------------------------------------------------------------ aviso

/** Aviso metodológico obrigatório em toda página pública (PUB-08), com o link para a metodologia. */
export function AvisoMetodologico({ children }: { children: ReactNode }) {
  return (
    <aside className="faixa aviso-metodologico" aria-label="Aviso metodológico">
      {children}{" "}
      <a href={METODOLOGIA} target="_blank" rel="noreferrer">
        Metodologia completa
      </a>
      .
    </aside>
  );
}

// ------------------------------------------------------------------------------------------ números

/** Um número com rótulo e, quando há, uma linha de detalhe. */
export function Numero({ rotulo, valor, detalhe }: { rotulo: string; valor: string; detalhe?: string }) {
  return (
    <div>
      <div className="total-rotulo">{rotulo}</div>
      <div className="total-valor">{valor}</div>
      {detalhe && <div className="total-detalhe">{detalhe}</div>}
    </div>
  );
}

// ------------------------------------------------------------------------------------------ gráfico

/** Uma barra do gráfico: o rótulo do mês e o valor. */
export interface Barra {
  rotulo: string;
  valor: number;
}

/**
 * Barras verticais finas, uma por mês, com a grade discreta e um rótulo de valor ao passar o mouse (ou o
 * foco do teclado). Abaixo, a mesma série em tabela, recolhida, para leitor de tela e para conferir.
 */
export function GraficoBarras({
  titulo,
  barras,
  formatar,
  formatarEixo,
}: {
  titulo: string;
  barras: Barra[];
  formatar: (n: number) => string;
  formatarEixo: (n: number) => string;
}) {
  const [ativa, setAtiva] = useState<number | null>(null);
  if (barras.length === 0) return null;
  const L = 640;
  const A = 190;
  const margem = { esq: 64, dir: 8, topo: 26, base: 24 };
  const largura = L - margem.esq - margem.dir;
  const altura = A - margem.topo - margem.base;
  const topo = topoDoEixo(Math.max(...barras.map((b) => b.valor)));
  const passo = largura / barras.length;
  const grossura = Math.max(4, Math.min(28, passo - 6));
  const y = (v: number) => margem.topo + altura - (v / topo) * altura;
  const marcas = [0, topo / 2, topo];
  const rotuloACada = Math.ceil(barras.length / 12);
  return (
    <figure className="grafico grafico-barras">
      <svg viewBox={`0 0 ${L} ${A}`} role="img" aria-label={titulo}>
        {marcas.map((m) => (
          <g key={m}>
            <line className="grade-linha" x1={margem.esq} x2={L - margem.dir} y1={y(m)} y2={y(m)} />
            <text x={margem.esq - 6} y={y(m) + 4} textAnchor="end">
              {formatarEixo(m)}
            </text>
          </g>
        ))}
        {barras.map((b, i) => {
          const cx = margem.esq + passo * i + passo / 2;
          const h = Math.max(b.valor > 0 ? 2 : 0, (b.valor / topo) * altura);
          const raio = Math.min(4, grossura / 2, h / 2);
          const x0 = cx - grossura / 2;
          const yTopo = margem.topo + altura - h;
          return (
            <g
              key={b.rotulo}
              tabIndex={0}
              onMouseEnter={() => setAtiva(i)}
              onMouseLeave={() => setAtiva(null)}
              onFocus={() => setAtiva(i)}
              onBlur={() => setAtiva(null)}
              aria-label={`${b.rotulo}: ${formatar(b.valor)}`}
            >
              <rect x={cx - passo / 2} y={margem.topo} width={passo} height={altura} fill="transparent" />
              {h > 0 && (
                <path
                  className={`barra-mes${ativa === i ? " barra-ativa" : ""}`}
                  d={`M${x0},${margem.topo + altura} V${yTopo + raio} Q${x0},${yTopo} ${x0 + raio},${yTopo} H${
                    x0 + grossura - raio
                  } Q${x0 + grossura},${yTopo} ${x0 + grossura},${yTopo + raio} V${margem.topo + altura} Z`}
                />
              )}
              {i % rotuloACada === 0 && (
                <text x={cx} y={A - 6} textAnchor="middle">
                  {b.rotulo}
                </text>
              )}
              {ativa === i && (
                <text className="grafico-valor" x={cx} y={Math.max(14, yTopo - 8)} textAnchor="middle">
                  {formatar(b.valor)}
                </text>
              )}
            </g>
          );
        })}
        <line className="eixo" x1={margem.esq} x2={L - margem.dir} y1={margem.topo + altura} y2={margem.topo + altura} />
      </svg>
      <figcaption className="so-leitor">{titulo}</figcaption>
      <details className="grafico-tabela">
        <summary>Ver em tabela</summary>
        <table className="tabela">
          <tbody>
            {barras.map((b) => (
              <tr key={b.rotulo}>
                <td>{b.rotulo}</td>
                <td className="n">{formatar(b.valor)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </figure>
  );
}

// ------------------------------------------------------------------------------------------ conformidade

const ICONE: Record<Resultado, string> = {
  cumpre: "✓",
  cumpre_parcialmente: "!",
  nao_cumpre: "×",
  indeterminado: "?",
};

/** Selo do resultado de uma obrigação: ícone e texto, nunca só a cor. */
export function SeloResultado({ resultado, rotulo }: { resultado: Resultado; rotulo: string }) {
  return (
    <span className={`resultado resultado-${resultado}`}>
      <span aria-hidden="true" className="resultado-icone">
        {ICONE[resultado]}
      </span>
      {rotulo}
    </span>
  );
}

/** Estado de carregamento, erro ou ausência, numa linha. */
export function Situacao({ children }: { children: ReactNode }) {
  return <p className="situacao-painel">{children}</p>;
}
