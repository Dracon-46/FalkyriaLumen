"use client";

/**
 * Cabeçalho do portal, presente em todas as páginas: a marca, as abas e o filtro de local.
 *
 * O local (União, estado, DF ou município) filtra todas as abas (ADR-035): escolhido aqui, ou ao entrar num
 * município ou estado em qualquer aba, ele vai no endereço de cada aba (Eleições abre no mapa dele,
 * Contratações e Conformidade no ente, as estatais nas que ele controla) e fica guardado no navegador. É
 * componente de cliente porque lê o caminho e a URL, que no site estático só o navegador conhece.
 *
 * A aba Novidades mostra quantas mudanças do Lumen entraram desde a última visita (`lib/novidades.ts`): o layout
 * passa os identificadores, lidos do CHANGELOG na geração do site.
 */

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import { BuscaEnte } from "@/componentes/paineis/Comuns";
import { type Area, codigoNaUrl, EVENTO_LOCAL, gravarMemoria, hrefDaArea, lerMemoria, type Local } from "@/lib/local";
import { CHAVE_VISTA, EVENTO_VISTAS, naoVistas } from "@/lib/novidades";
import { carregarEntes } from "@/lib/paineis";

const ABAS: { area: Area; rotulo: string; prefixo: string }[] = [
  { area: "eleicoes", rotulo: "Eleições", prefixo: "/eleicoes" },
  { area: "contratacoes", rotulo: "Contratações", prefixo: "/contratacoes" },
  { area: "conformidade", rotulo: "Conformidade", prefixo: "/conformidade" },
  { area: "economia", rotulo: "Economia", prefixo: "/economia" },
  { area: "avisos", rotulo: "Avisos", prefixo: "/avisos" },
];

/** Cabeçalho do Lumen. A parte que lê a URL fica num `Suspense`, como o site estático exige. */
export function Cabecalho({ novidades = [] }: { novidades?: string[] }) {
  return (
    <header className="cabecalho">
      <Suspense fallback={<Moldura local={null} novidades={novidades} />}>
        <ComLocal novidades={novidades} />
      </Suspense>
    </header>
  );
}

/**
 * Quantas mudanças entraram desde a última visita à página de novidades. Na primeira visita ao Lumen, guarda a mais
 * nova como ponto de partida, para avisar só do que vier depois.
 */
function useNovidadesNaoVistas(ids: string[]): number {
  const [n, setN] = useState(0);
  useEffect(() => {
    const contar = () => {
      try {
        const vista = window.localStorage.getItem(CHAVE_VISTA);
        if (vista === null && ids[0]) window.localStorage.setItem(CHAVE_VISTA, ids[0]);
        setN(naoVistas(ids, vista));
      } catch {
        setN(0);
      }
    };
    contar();
    window.addEventListener(EVENTO_VISTAS, contar);
    return () => window.removeEventListener(EVENTO_VISTAS, contar);
  }, [ids]);
  return n;
}

/** Lê o local da URL (ou da memória), mantém-no em dia e monta as abas filtradas por ele. */
function ComLocal({ novidades }: { novidades: string[] }) {
  const caminho = usePathname() ?? "/";
  const params = useSearchParams();
  const router = useRouter();
  const [local, setLocal] = useState<Local | null>(null);

  // Ao abrir: o local guardado no navegador
  useEffect(() => setLocal(lerMemoria()), []);

  // Uma aba que descobre o local por conta própria (o órgão aberto em Contratações) avisa por evento
  useEffect(() => {
    const ouvir = (ev: Event) => {
      const novo = (ev as CustomEvent<Local | null>).detail ?? null;
      setLocal(novo);
      gravarMemoria(novo);
    };
    window.addEventListener(EVENTO_LOCAL, ouvir);
    return () => window.removeEventListener(EVENTO_LOCAL, ouvir);
  }, []);

  // A aba aberta num município ou estado passa a ser o local
  // (só quando a URL muda: ao tirar o filtro, a URL antiga não pode trazê-lo de volta)
  const naUrl = codigoNaUrl(caminho, new URLSearchParams(params.toString()));
  const visto = useRef<string | null>(null);
  useEffect(() => {
    if (naUrl === visto.current) return;
    visto.current = naUrl;
    if (!naUrl) return;
    carregarEntes()
      .then((entes) => {
        if (visto.current !== naUrl) return; // a URL já mudou de novo
        const e = entes.find((x) => x.codigo === naUrl);
        const novo = { codigo: naUrl, nome: e?.nome ?? (naUrl === "1" ? "União" : naUrl), uf: e?.uf ?? null };
        setLocal(novo);
        gravarMemoria(novo);
      })
      .catch(() => undefined);
  }, [naUrl]);

  const escolher = (novo: Local | null) => {
    window.dispatchEvent(new CustomEvent(EVENTO_LOCAL, { detail: novo }));
    // A aba aberta vai para o local escolhido (ou para o Brasil, ao tirar o filtro)
    const aba = ABAS.find((a) => caminho.startsWith(a.prefixo));
    const area: Area | null = caminho.startsWith("/economia/estatais") ? "estatais" : aba?.area ?? null;
    if (area && area !== "economia") router.push(hrefDaArea(area, novo, new URLSearchParams(params.toString())));
  };

  return <Moldura local={local} caminho={caminho} params={params} onEscolher={escolher} novidades={novidades} />;
}

/** A marca, as abas (com o local no endereço), a aba de novidades e o filtro de local. */
function Moldura({ local, caminho = "/", params, onEscolher, novidades }: {
  local: Local | null; caminho?: string; params?: URLSearchParams | ReturnType<typeof useSearchParams>;
  onEscolher?: (l: Local | null) => void; novidades: string[];
}) {
  const [trocando, setTrocando] = useState(false);
  const naoVistas = useNovidadesNaoVistas(novidades);
  const atual = params ? new URLSearchParams(params.toString()) : undefined;
  return (
    <div className="cabecalho-dentro">
      <Link href="/" className="marca" aria-label="Lumen, página inicial">
        <span className="marca-nome">Lumen</span>
        <span className="marca-casa">Falkyria</span>
      </Link>
      <nav aria-label="Áreas do portal">
        <div className="abas">
          {ABAS.map((a) => (
            <Link key={a.area} href={hrefDaArea(a.area, local, atual)} className="aba"
                  aria-current={caminho.startsWith(a.prefixo) ? "page" : undefined}>
              {a.rotulo}
            </Link>
          ))}
          <Link href="/novidades/" className="aba" aria-current={caminho.startsWith("/novidades") ? "page" : undefined}
                aria-label={naoVistas ? `Novidades: ${naoVistas} mudança(s) desde a sua última visita` : undefined}>
            Novidades
            {naoVistas > 0 && <span className="aba-contador" aria-hidden="true">{naoVistas > 9 ? "9+" : naoVistas}</span>}
          </Link>
        </div>
      </nav>
      {onEscolher && (
        <div className="filtro-local" role="group" aria-label="Local">
          {local && !trocando ? (
            <>
              <span className="filtro-local-rotulo">Local:</span>
              <button type="button" className="filtro-local-nome" title="Trocar o local" onClick={() => setTrocando(true)}>
                {local.nome}{local.uf && local.codigo.length === 7 ? ` · ${local.uf}` : ""}
              </button>
              <button type="button" className="filtro-local-tirar" aria-label="Tirar o filtro de local (ver o Brasil)"
                      title="Ver o Brasil" onClick={() => onEscolher(null)}>
                ✕
              </button>
            </>
          ) : (
            <BuscaEnte
              rotulo={local ? "Trocar o local" : "Filtrar por local (estado ou município)"}
              onEscolher={(codigo) => {
                setTrocando(false);
                carregarEntes()
                  .then((entes) => {
                    const e = entes.find((x) => x.codigo === codigo);
                    onEscolher({ codigo, nome: e?.nome ?? codigo, uf: e?.uf ?? null });
                  })
                  .catch(() => onEscolher({ codigo, nome: codigo, uf: null }));
              }}
            />
          )}
        </div>
      )}
    </div>
  );
}
