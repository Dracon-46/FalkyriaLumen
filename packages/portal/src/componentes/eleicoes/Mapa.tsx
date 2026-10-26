"use client";

/**
 * Mapa coroplético das partes (UFs no Brasil, municípios na UF), desenhado em
 * SVG a partir da malha do IBGE. Cada área leva a cor de quem está à frente,
 * mas só as quatro primeiras posições da paleta são pintadas (azul do PL,
 * vermelho do PT, amarelo e verde): da quinta em diante a área fica cinza
 * ("Outros"), porque só essas quatro passam na validação para daltonismo em
 * todos os pares lado a lado (ADR-020, ADR-052). O nome
 * e o percentual de quem lidera continuam na dica e na tabela.
 *
 * Com um município aberto, o mapa da UF aproxima até ele (com animação, que
 * respeita a preferência por menos movimento), apaga os vizinhos e, se o
 * município tem mais de uma zona eleitoral, mostra as zonas: a área de cada
 * uma é a mais perto dos seus locais de votação (ADR-029, `lib/zonas.ts`),
 * recortada pelo contorno fino do município, com a cor de quem lidera na
 * zona quando o feed traz o resultado por zona. Os vizinhos continuam
 * clicáveis: abrir outro município voa até ele.
 *
 * Interativo: botões + e −, Ctrl (ou ⌘) + rolagem e pinça no trackpad para
 * aproximar em torno do cursor; arrastar para mover quando aproximado; dois
 * dedos na tela de toque; teclas +, − e 0 com o foco no mapa. A rolagem
 * simples continua rolando a página. As contas da janela estão em
 * `lib/zoom.ts`; a ligação área ↔ parte, em `lib/areas.ts`.
 *
 * Desempenho: a camada das áreas é memorizada e os eventos do cursor são
 * tratados num ouvinte só (pelo `data-*` do elemento sob o cursor), de modo
 * que mover o cursor só redesenha a dica e o contorno de destaque.
 */

import { type CSSProperties, memo, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { chaveDaArea, EXTERIOR, formaDoExterior, indexarPartes, parteDaArea, partesSemArea } from "@/lib/areas";
import { UFS } from "@/lib/busca";
import { CORES_NO_MAPA, varCor, varCorMapa } from "@/lib/cores";
import { carregarMalha } from "@/lib/feeds";
import { numero, percentual } from "@/lib/formato";
import {
  type ContextoMudanca,
  corDaParte,
  FAIXAS_ABSTENCAO,
  FAIXAS_MUDANCA,
  FAIXAS_PCT,
  type Faixa,
  misturar,
  type ModoCor,
} from "@/lib/modos-mapa";
import type { ArquivoZonas, Parte, ZonaDoMunicipio } from "@/lib/tipos";
import { type Forma, projetar, projetarCom, pontoProjetado, type MapaProjetado, type Topologia } from "@/lib/topojson";
import { caixaComFolga, desenharZonas, type LocalNoMapa, rarear, rotulosVisiveis } from "@/lib/zonas";
import {
  aproximar,
  centro,
  deslocar,
  enquadrar,
  interpolar,
  type Limites,
  PASSO_ZOOM,
  suavizar,
  type Vista,
  viewBox,
  vistaInicial,
  zoomDe,
  zoomMaximoPara,
} from "@/lib/zoom";

/** O município aberto no mapa da UF, com o que for preciso para desenhar as zonas. */
export interface MunicipioAberto {
  /** Código da área do município na malha (o IBGE). */
  codigo: string;
  /** Contorno fino (qualidade `maxima`); null enquanto não chega, ou se o município não tem. */
  contorno: Topologia | null;
  /** Zonas e locais de votação; null se o município tem uma zona só ou o ano não tem o mapa das zonas. */
  zonas: ArquivoZonas | null;
  /** Resultado por zona (as partes do feed do município); vazio ao vivo, quando o TSE não publica por zona. */
  partes: Parte[];
  /** Zona em destaque: a do cursor na tabela ou a escolhida. */
  destacada: string | null;
  /** Clique numa zona do mapa. */
  onZona: (zona: string) => void;
}

/** Entrada do mapa: a malha a desenhar, as partes do feed que a colorem e as ações de seleção. */
interface Props {
  /** URL da malha do IBGE (Brasil por UF, ou UF por município). */
  malha: string;
  /** "uf" quando as áreas são UFs (mapa do Brasil); "mu" quando são municípios. */
  nivel: "uf" | "mu";
  partes: Parte[];
  /** Município aberto (só no mapa de uma UF). */
  municipio?: MunicipioAberto | null;
  onSelecionar: (parte: Parte) => void;
  /** Cursor parado numa área: a tela pode pré-carregar o que o clique vai abrir. */
  onPrevisualizar?: (parte: Parte) => void;
  /** Rótulo do que lidera: candidato (resultado) ou partido (panorama). Estável entre renderizações. */
  rotuloLider: (parte: Parte) => string;
  titulo: string;
  /** O que a cor das áreas mostra (`lib/modos-mapa.ts`); padrão, quem lidera. */
  modo?: ModoCor;
  /** Partes do 1º turno e os finalistas, para o modo Mudança. */
  contextoMudanca?: ContextoMudanca | null;
  /**
   * Malhas dos municípios de todas as UFs: o mapa do Brasil por município. A `malha` (a das UFs) dá o
   * enquadramento e as fronteiras estaduais, desenhadas por cima; as áreas são os municípios (`nivel` "mu").
   */
  malhasMunicipios?: string[] | null;
}

/** Caixa flutuante do que está sob o cursor ou com foco; `x` e `y` em pixels relativos ao contêiner. */
type Dica = { x: number; y: number } & (
  | { tipo: "area"; parte: Parte | null; nome: string }
  | { tipo: "zona"; zona: string; parte: Parte | null; info: ZonaDoMunicipio | undefined }
  | { tipo: "local"; local: LocalNoMapa }
);

/** Arrasto em curso: onde começou (pixels), a janela de então e a escala pixel → malha. */
interface Arrasto {
  x0: number;
  y0: number;
  vista: Vista;
  escala: number;
  moveu: boolean;
}

/** Deslocamento, em pixels, a partir do qual o gesto é arrasto e não clique. */
const LIMIAR_ARRASTO = 5;
/** Duração da viagem até o município (ms) e a dos botões de aproximar. */
const DURACAO_VOO = 520;
const DURACAO_PASSO = 220;
/** Cursor parado sobre uma área por este tempo (ms) dispara a pré-carga. */
const ESPERA_PREVISUALIZAR = 140;

/** Os dois toques de uma pinça e a distância entre eles, ou null se não há exatamente dois. */
function pincaDe(dedos: Map<number, [number, number]>): { meio: [number, number]; distancia: number } | null {
  const [a, b] = [...dedos.values()];
  if (dedos.size !== 2 || !a || !b) return null;
  return { meio: [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2], distancia: Math.hypot(a[0] - b[0], a[1] - b[1]) };
}

/** Ponto da tela (clientX, clientY) em coordenadas da malha, pela matriz atual do SVG. */
function pontoNaMalha(svg: SVGSVGElement | null, cx: number, cy: number): [number, number] | null {
  const m = svg?.getScreenCTM?.();
  if (!svg || !m) return null;
  const p = new DOMPoint(cx, cy).matrixTransform(m.inverse());
  return [p.x, p.y];
}

/** Se a pessoa pediu menos movimento ao sistema: aí o mapa muda de janela sem animação. */
function menosMovimento(): boolean {
  return typeof window !== "undefined" && !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
}

/** O alvo do evento com `data-area`, `data-zona` ou `data-local`, subindo até o SVG. */
function alvoDe(el: EventTarget | null): { area?: string; zona?: string; local?: number } | null {
  let atual = el as Element | null;
  while (atual && atual.tagName.toLowerCase() !== "svg") {
    const d = (atual as HTMLElement | SVGElement).dataset;
    if (d?.area) return { area: d.area };
    if (d?.zona) return { zona: d.zona };
    if (d?.local) return { local: Number(d.local) };
    atual = atual.parentElement;
  }
  return null;
}

/** As áreas da malha, pintadas pela parte que lidera em cada uma. Memorizada: não muda com o cursor. */
const CamadaAreas = memo(function CamadaAreas({
  formas,
  partes,
  nivel,
  rotuloLider,
  apagadas,
  corDe,
}: {
  formas: Forma[];
  partes: Parte[];
  nivel: "uf" | "mu";
  rotuloLider: (parte: Parte) => string;
  /** Cor da área pela parte, no modo escolhido; estável entre renderizações. */
  corDe: (parte: Parte | undefined) => string;
  /**
   * Com um município aberto, as áreas ficam apagadas (e clicáveis); a do próprio município também, por baixo
   * do contorno fino, e cobre a fresta entre ele e a fronteira simplificada dos vizinhos.
   */
  apagadas: boolean;
}) {
  const porCodigo = useMemo(() => indexarPartes(partes), [partes]);
  return (
    <g className={apagadas ? "areas areas-apagadas" : "areas"}>
      {formas.map((f) => {
        const parte = parteDaArea(porCodigo, f.codigo, nivel);
        const chave = chaveDaArea(f.codigo, nivel);
        const nome = parte?.nome ?? (nivel === "uf" ? (UFS[chave] ?? chave) : chave);
        const rotulo = parte?.lider
          ? `${nome}: ${rotuloLider(parte)} lidera${parte.pct != null ? ` com ${percentual(parte.pct)}` : ""}`
          : `${nome}: sem dados`;
        return (
          <path
            key={f.codigo}
            d={f.d}
            data-area={f.codigo}
            fill={corDe(parte)}
            tabIndex={parte ? 0 : -1}
            role="button"
            aria-label={rotulo}
          />
        );
      })}
    </g>
  );
});

/**
 * As zonas do município aberto, os locais de votação e os números das zonas, recortados pelo contorno do
 * município. Memorizada: o tamanho dos pontos e dos rótulos (`px`, unidades da malha por pixel) muda em
 * degraus, não a cada quadro da animação.
 *
 * Os traços das zonas têm a espessura em unidades da malha (a variável CSS `--px` vezes os pixels), sem
 * `vector-effect: non-scaling-stroke`: com o município muito aproximado, o Chrome com aceleração de vídeo
 * desenhava alguns lados das fronteiras e do destaque com dezenas de pixels (faixas pretas e brancas sobre
 * as zonas, 26/10/2026).
 */
const CamadaZonas = memo(function CamadaZonas({
  desenho,
  partes,
  neutra,
  corMunicipio,
  px,
  recorte,
  rotuloLider,
}: {
  desenho: ReturnType<typeof desenharZonas>;
  partes: Map<string, Parte>;
  /** Sem resultado por zona (ao vivo): todas com a mesma cor, separadas pelas fronteiras. */
  neutra: boolean;
  /** Na zona sem resultado próprio, a cor de quem lidera no município, clareada; sem líder, a neutra. */
  corMunicipio: number | null;
  px: number;
  recorte: string;
  rotuloLider: (parte: Parte) => string;
}) {
  // Rótulos a 28 px uns dos outros e pontos a 6 px: o que não cabe aparece ao aproximar
  const rotulos = useMemo(() => rotulosVisiveis(desenho.zonas, 28 * px), [desenho, px]);
  const pontos = useMemo(() => rarear(desenho.locais, 6 * px), [desenho, px]);
  const corNeutra =
    corMunicipio === null ? "var(--zona-neutra)" : `color-mix(in srgb, ${varCorMapa(corMunicipio)} 70%, var(--superficie))`;
  return (
    <>
      <g clipPath={`url(#${recorte})`} style={{ "--px": px } as CSSProperties}>
        {desenho.zonas.map((z) => {
          const p = partes.get(z.zona);
          const rotulo = p?.lider
            ? `Zona ${z.zona}: ${rotuloLider(p)} lidera${p.pct != null ? ` com ${percentual(p.pct)}` : ""}`
            : `Zona ${z.zona}`;
          return (
            <path
              key={z.zona}
              className="zona"
              d={z.d}
              data-zona={z.zona}
              style={{ "--cor-zona": neutra ? corNeutra : varCorMapa(p?.lider ? p.cor : null) } as CSSProperties}
              tabIndex={0}
              role="button"
              aria-label={rotulo}
            />
          );
        })}
        <path className="zona-fronteiras" d={desenho.fronteiras} aria-hidden="true" />
        <g className="locais" aria-hidden="true">
          {pontos.map((i) => {
            const l = desenho.locais[i]!;
            return <circle key={i} cx={l.x} cy={l.y} r={2.2 * px} data-local={i} />;
          })}
        </g>
      </g>
      <g className="rotulos-zonas" aria-hidden="true" style={{ fontSize: `${11 * px}px` }}>
        {desenho.zonas
          .filter((z) => rotulos.has(z.zona))
          .map((z) => (
            <text key={z.zona} x={z.rotulo[0]} y={z.rotulo[1] - 5 * px} strokeWidth={3 * px}>
              {z.zona}
            </text>
          ))}
      </g>
    </>
  );
});

/** Arredonda para um degrau de 25%: o que depende da escala muda pouco durante uma animação. */
function degrau(valor: number): number {
  return 1.25 ** Math.round(Math.log(valor) / Math.log(1.25));
}

/**
 * Baixa a malha (uma vez por visita, por `carregarMalha`), projeta e pinta.
 * Cada área com dados é um botão: clique, Enter ou espaço abre a parte, e o
 * foco pelo teclado mostra a mesma dica do cursor. Sem malha no servidor, o
 * mapa dá lugar a um aviso e a tabela segue com os números. No mapa do
 * Brasil, o exterior é um quadrado no Atlântico (`formaDoExterior`); as
 * outras partes sem área na malha (UFs que não existem mais) viram botões
 * abaixo do mapa.
 */
export function Mapa({ malha, nivel, partes, municipio, onSelecionar, onPrevisualizar, rotuloLider, titulo,
  modo = "vencedor", contextoMudanca = null, malhasMunicipios = null }: Props) {
  const [mapa, setMapa] = useState<MapaProjetado | null>(null);
  /** No mapa do Brasil por município: as fronteiras das UFs, por cima dos municípios. */
  const [fronteiras, setFronteiras] = useState<Forma[] | null>(null);
  const corDe = useCallback((p: Parte | undefined) => corDaParte(modo, p, contextoMudanca), [modo, contextoMudanca]);
  const [falhou, setFalhou] = useState(false);
  const [dica, setDica] = useState<Dica | null>(null);
  const [ativo, setAtivo] = useState<string | null>(null);
  const [vista, setVista] = useState<Vista | null>(null);
  const [lembrete, setLembrete] = useState(false);
  const [larguraTela, setLarguraTela] = useState(600);
  // Durante o voo até o município, as zonas (milhares de pontos) esperam: o quadro fica leve e a animação, lisa
  const [voando, setVoando] = useState(false);
  const caixa = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const arrasto = useRef<Arrasto | null>(null);
  const dedos = useRef(new Map<number, [number, number]>());
  const pinca = useRef<number | null>(null);
  const cliqueBloqueado = useRef(false);
  const animacao = useRef<number | null>(null);
  /** Janela da última pintura: é de onde parte a animação. */
  const exibida = useRef<Vista | null>(null);
  const quadro = useRef<number | null>(null);
  const previa = useRef<{ codigo: string; id: number } | null>(null);

  useEffect(() => {
    let vivo = true;
    setMapa(null);
    setVista(null);
    setFalhou(false);
    exibida.current = null;
    setFronteiras(null);
    const chaveMalhas = malhasMunicipios?.join("|") ?? "";
    carregarMalha(malha)
      .then(async (topo) => {
        if (!vivo) return;
        if (!topo) {
          setFalhou(true);
          return;
        }
        const base = projetar(topo, 1000);
        if (!chaveMalhas) {
          setMapa(base);
          return;
        }
        // Os municípios de cada UF no enquadramento do Brasil; a malha que faltar só deixa aquela UF vazia
        const malhas = await Promise.all((malhasMunicipios ?? []).map((u) => carregarMalha(u).catch(() => null)));
        if (!vivo) return;
        const formas = malhas.flatMap((m) => (m ? projetarCom(m, base.projecao, 1) : []));
        setFronteiras(base.formas);
        setMapa({ ...base, formas });
      })
      .catch(() => vivo && setFalhou(true));
    return () => {
      vivo = false;
    };
    // As malhas como texto: a mesma lista não recarrega
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [malha, malhasMunicipios?.join("|")]);

  // Largura do SVG na tela: o tamanho dos rótulos e dos pontos é em pixels, não em unidades da malha
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg || typeof ResizeObserver === "undefined") return;
    const obs = new ResizeObserver(([e]) => e && setLarguraTela(e.contentRect.width || 600));
    obs.observe(svg);
    return () => obs.disconnect();
  }, [mapa]);

  const porCodigo = useMemo(() => indexarPartes(partes), [partes]);
  const codigoAberto = municipio?.codigo ?? null;

  // No mapa do Brasil, o exterior ganha uma área no Atlântico (`formaDoExterior`) quando o feed tem a parte dele
  const temExterior = nivel === "uf" && partes.some((p) => p.codigo === EXTERIOR);
  const formas = useMemo(
    () => (mapa ? (temExterior ? [...mapa.formas, formaDoExterior(mapa.projecao, mapa.largura)] : mapa.formas) : []),
    [mapa, temExterior],
  );
  const exterior = temExterior ? formas[formas.length - 1] : undefined;

  // Contorno do município aberto: o fino, projetado no enquadramento da UF; sem ele, o da malha da UF
  const formaFina = useMemo(() => {
    if (!mapa || !municipio?.contorno || !codigoAberto) return null;
    return projetarCom(municipio.contorno, mapa.projecao).find((f) => f.codigo === codigoAberto) ?? null;
  }, [mapa, municipio?.contorno, codigoAberto]);
  const formaAberta = formaFina ?? (codigoAberto ? (mapa?.formas.find((f) => f.codigo === codigoAberto) ?? null) : null);

  const desenho = useMemo(() => {
    if (!mapa || !formaAberta || !municipio?.zonas) return null;
    return desenharZonas(municipio.zonas, (lon, lat) => pontoProjetado(mapa.projecao, lon, lat),
      caixaComFolga(formaAberta.caixa));
  }, [mapa, formaAberta, municipio?.zonas]);

  const zonasPorCodigo = useMemo(() => indexarPartes(municipio?.partes ?? []), [municipio?.partes]);
  const infoZona = useMemo(
    () => new Map((municipio?.zonas?.zonas ?? []).map((z) => [z.zona, z] as const)),
    [municipio?.zonas],
  );

  const caixaAberta = formaAberta?.caixa ?? null;
  const limites: Limites | null = useMemo(
    () =>
      mapa
        ? { largura: mapa.largura, altura: mapa.altura, maxZoom: zoomMaximoPara(caixaAberta, mapa) }
        : null,
    // A caixa como texto: o mesmo enquadramento não refaz os limites
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [mapa, caixaAberta?.join(",")],
  );
  // Com o contorno fino, o município ocupa o mapa; com o simplificado (poucos pontos), fica com a região em volta
  const margem = formaFina ? 0.12 : 0.9;
  const padrao = useMemo(
    () => (limites ? (caixaAberta ? enquadrar(caixaAberta, limites, margem) : vistaInicial(limites)) : null),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [limites, caixaAberta?.join(","), margem],
  );
  const janela = vista ?? padrao;
  const zoom = janela && limites ? zoomDe(janela, limites) : 1;

  /**
   * Leva a janela até `alvo` (null: o enquadramento padrão), com animação quando faz sentido. Parte da
   * janela da última pintura: quando o enquadramento padrão muda, a tela ainda mostra a anterior.
   */
  const animar = useCallback(
    (alvo: Vista | null, duracao: number, voo = false) => {
      if (animacao.current !== null) cancelAnimationFrame(animacao.current);
      animacao.current = null;
      const de = exibida.current;
      const para = alvo ?? padraoRef.current;
      if (!de || !para || duracao <= 0 || menosMovimento()) {
        setVista(alvo);
        setVoando(false);
        return;
      }
      setVista(de);
      setVoando(voo);
      const inicio = performance.now();
      const passo = (agora: number) => {
        const t = suavizar((agora - inicio) / duracao);
        if (t >= 1) {
          animacao.current = null;
          setVista(alvo);
          setVoando(false);
          return;
        }
        setVista(interpolar(de, para, t));
        animacao.current = requestAnimationFrame(passo);
      };
      animacao.current = requestAnimationFrame(passo);
    },
    [],
  );
  const padraoRef = useRef<Vista | null>(null);
  padraoRef.current = padrao;

  const parar = useCallback(() => {
    if (animacao.current !== null) cancelAnimationFrame(animacao.current);
    animacao.current = null;
    setVoando(false);
  }, []);
  useEffect(() => parar, [parar]);

  // Abriu (ou fechou) um município: voa até o novo enquadramento. Os dois efeitos rodam antes da pintura,
  // nesta ordem: o primeiro ainda vê a janela anterior em `exibida`, e o segundo a atualiza.
  const chaveEnquadramento = padrao ? `${codigoAberto}|${caixaAberta?.join(",")}` : null;
  useLayoutEffect(() => {
    if (chaveEnquadramento === null) return;
    animar(null, DURACAO_VOO, true);
  }, [chaveEnquadramento, animar]);
  useLayoutEffect(() => {
    exibida.current = janela;
  });

  const fora = useMemo(
    () => (mapa ? partesSemArea(partes, formas.map((f) => f.codigo), nivel) : []),
    [mapa, formas, partes, nivel],
  );

  const lideres = useMemo(() => {
    // Legenda: quem lidera ao menos uma área (ou zona, com o município aberto), na ordem da cor
    const vistos = new Map<number, string>();
    const fonte = desenho && municipio?.partes.length ? municipio.partes : partes;
    for (const p of fonte) {
      if (!p.lider) continue;
      const k = p.cor >= 0 && p.cor < CORES_NO_MAPA ? p.cor : CORES_NO_MAPA;
      if (!vistos.has(k)) vistos.set(k, k < CORES_NO_MAPA ? rotuloLider(p) : "Outros");
    }
    return [...vistos.entries()].sort((a, b) => a[0] - b[0]);
  }, [partes, rotuloLider, desenho, municipio?.partes]);

  /** Aproxima por `fator` em torno de um ponto da tela (imediato, para rolagem e pinça) ou do centro (animado). */
  const zoomEm = useCallback(
    (fator: number, cliente?: [number, number]) => {
      const atual = exibida.current;
      if (!limites || !atual) return;
      parar();
      const ponto = (cliente && pontoNaMalha(svgRef.current, cliente[0], cliente[1])) ?? centro(atual);
      const alvo = aproximar(atual, fator, ponto, limites);
      if (cliente) setVista(alvo);
      else animar(alvo, DURACAO_PASSO);
      setDica(null);
    },
    [limites, parar, animar],
  );

  // Rolagem: com Ctrl/⌘ (e a pinça do trackpad, que chega assim) aproxima; sem, rola a página e lembra o atalho.
  // O ouvinte é nativo porque o do React é passivo e não pode impedir a rolagem.
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg || !limites) return;
    let id: number | undefined;
    const rolar = (e: WheelEvent) => {
      if (!(e.ctrlKey || e.metaKey)) {
        setLembrete(true);
        window.clearTimeout(id);
        id = window.setTimeout(() => setLembrete(false), 1400);
        return;
      }
      e.preventDefault();
      zoomEm(Math.exp(-e.deltaY * 0.0025), [e.clientX, e.clientY]);
    };
    svg.addEventListener("wheel", rolar, { passive: false });
    return () => {
      svg.removeEventListener("wheel", rolar);
      window.clearTimeout(id);
    };
  }, [limites, zoomEm]);

  if (falhou) {
    return (
      <div className="mapa-vazio">
        Mapa indisponível: as malhas do IBGE não estão neste servidor (o comando <code>lumen eleicoes preparar</code>{" "}
        instala as que vêm com o Lumen). Os resultados estão na tabela abaixo.
      </div>
    );
  }
  if (!mapa || !janela || !limites) return <div className="mapa-vazio mapa-carregando">Carregando o mapa…</div>;

  // ------------------------------------------------------------ dica

  /** Posição da dica: a do cursor, ou, pelo teclado, a de um ponto da malha levado à tela. */
  const posicao = (evento?: { clientX: number; clientY: number }, ponto?: [number, number]) => {
    const r = caixa.current?.getBoundingClientRect();
    if (!r) return { x: 0, y: 0 };
    if (evento) return { x: evento.clientX - r.left, y: evento.clientY - r.top };
    const m = svgRef.current?.getScreenCTM?.();
    if (!m || !ponto) return { x: 0, y: 0 };
    const p = new DOMPoint(ponto[0], ponto[1]).matrixTransform(m);
    return { x: p.x - r.left, y: p.y - r.top };
  };

  /** Dica do alvo (área, zona ou local), pelo evento do cursor ou pelo foco do teclado. */
  const mostrar = (alvo: ReturnType<typeof alvoDe>, evento?: { clientX: number; clientY: number }) => {
    if (!alvo || arrasto.current?.moveu) return;
    if (alvo.area) {
      const f = formas.find((x) => x.codigo === alvo.area);
      const parte = parteDaArea(porCodigo, alvo.area, nivel) ?? null;
      const chave = chaveDaArea(alvo.area, nivel);
      const nome = parte?.nome ?? (nivel === "uf" ? (UFS[chave] ?? chave) : chave);
      setDica({ tipo: "area", parte, nome, ...posicao(evento, f?.centro) });
      setAtivo(alvo.area);
      if (parte && onPrevisualizar && previa.current?.codigo !== alvo.area) {
        if (previa.current) window.clearTimeout(previa.current.id);
        previa.current = { codigo: alvo.area, id: window.setTimeout(() => onPrevisualizar(parte), ESPERA_PREVISUALIZAR) };
      }
    } else if (alvo.zona) {
      const z = desenho?.zonas.find((x) => x.zona === alvo.zona);
      setDica({ tipo: "zona", zona: alvo.zona, parte: zonasPorCodigo.get(alvo.zona) ?? null,
        info: infoZona.get(alvo.zona), ...posicao(evento, z?.rotulo) });
      setAtivo(`zona:${alvo.zona}`);
    } else if (alvo.local !== undefined && desenho) {
      const local = desenho.locais[alvo.local];
      if (local) setDica({ tipo: "local", local, ...posicao(evento, [local.x, local.y]) });
    }
  };
  const esconder = () => {
    setDica(null);
    setAtivo(null);
    if (previa.current) window.clearTimeout(previa.current.id);
    previa.current = null;
  };

  // ------------------------------------------------------------ arrasto, toque e clique

  const aoPressionar = (e: React.PointerEvent<SVGSVGElement>) => {
    parar();
    dedos.current.set(e.pointerId, [e.clientX, e.clientY]);
    cliqueBloqueado.current = false;
    const doisDedos = pincaDe(dedos.current);
    if (doisDedos) {
      pinca.current = doisDedos.distancia;
      arrasto.current = null;
      return;
    }
    const m = svgRef.current?.getScreenCTM?.();
    arrasto.current = { x0: e.clientX, y0: e.clientY, vista: janela, escala: m ? 1 / m.a : 1, moveu: false };
  };

  const aoMover = (e: React.PointerEvent<SVGSVGElement>) => {
    if (dedos.current.has(e.pointerId)) {
      dedos.current.set(e.pointerId, [e.clientX, e.clientY]);
      const doisDedos = pincaDe(dedos.current);
      if (doisDedos && pinca.current) {
        zoomEm(doisDedos.distancia / pinca.current, doisDedos.meio);
        pinca.current = doisDedos.distancia;
        cliqueBloqueado.current = true;
        return;
      }
      const g = arrasto.current;
      if (g) {
        const dx = e.clientX - g.x0;
        const dy = e.clientY - g.y0;
        if (g.moveu || Math.hypot(dx, dy) >= LIMIAR_ARRASTO) {
          if (!g.moveu) {
            g.moveu = true;
            e.currentTarget.setPointerCapture?.(e.pointerId);
            esconder();
          }
          cliqueBloqueado.current = true;
          setVista(deslocar(g.vista, dx * g.escala, dy * g.escala, limites));
          return;
        }
      }
    }
    // Cursor livre: a dica acompanha, no máximo uma vez por quadro
    const alvo = alvoDe(e.target);
    const evento = { clientX: e.clientX, clientY: e.clientY };
    if (quadro.current !== null) cancelAnimationFrame(quadro.current);
    quadro.current = requestAnimationFrame(() => {
      quadro.current = null;
      if (alvo) mostrar(alvo, evento);
      else esconder();
    });
  };

  const aoSoltar = (e: React.PointerEvent<SVGSVGElement>) => {
    dedos.current.delete(e.pointerId);
    if (dedos.current.size < 2) pinca.current = null;
    if (dedos.current.size === 0) arrasto.current = null;
  };

  /** Abre o alvo: a área (UF ou município) ou, no município aberto, a zona. */
  const ativar = (alvo: ReturnType<typeof alvoDe>) => {
    if (!alvo) return;
    if (alvo.area) {
      const parte = parteDaArea(porCodigo, alvo.area, nivel);
      if (parte) onSelecionar(parte);
    } else if (alvo.zona) {
      municipio?.onZona(alvo.zona);
    }
  };

  const aoClicar = (e: React.MouseEvent<SVGSVGElement>) => {
    // O clique que encerra um arrasto (ou uma pinça) não abre a área sob o cursor
    if (cliqueBloqueado.current) {
      cliqueBloqueado.current = false;
      return;
    }
    ativar(alvoDe(e.target));
  };

  const teclas = (e: React.KeyboardEvent) => {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.key === "Enter" || e.key === " ") {
      const alvo = alvoDe(e.target);
      if (alvo) {
        e.preventDefault();
        ativar(alvo);
      }
      return;
    }
    if (e.key === "+" || e.key === "=") zoomEm(PASSO_ZOOM);
    else if (e.key === "-" || e.key === "_") zoomEm(1 / PASSO_ZOOM);
    else if (e.key === "0") animar(null, DURACAO_PASSO);
    else return;
    e.preventDefault();
  };

  // Contorno por cima de tudo: no SVG, quem é desenhado depois cobre a borda dos vizinhos
  const destaque = ativo && ativo !== codigoAberto ? formas.find((f) => f.codigo === ativo) : undefined;
  const aproximado = zoom > 1.001;
  const foraDoPadrao = vista !== null && animacao.current === null;
  // Pixels → unidades da malha, para rótulos e pontos de tamanho fixo na tela
  const px = degrau(janela.w / Math.max(larguraTela, 1));
  const zonaDestacada = municipio?.destacada ? desenho?.zonas.find((z) => z.zona === municipio.destacada) : undefined;
  const zonaSobCursor = ativo?.startsWith("zona:") ? desenho?.zonas.find((z) => `zona:${z.zona}` === ativo) : undefined;
  const parteAberta = codigoAberto ? parteDaArea(porCodigo, codigoAberto, nivel) : undefined;
  const idRecorte = `recorte-${codigoAberto ?? "nenhum"}`;

  return (
    <div className="mapa" ref={caixa} onPointerLeave={esconder} onKeyDown={teclas}>
      <svg
        ref={svgRef}
        viewBox={viewBox(janela)}
        role="group"
        aria-label={titulo}
        className={[aproximado && "mapa-aproximado", fronteiras && "mapa-municipios"].filter(Boolean).join(" ") || undefined}
        onPointerDown={aoPressionar}
        onPointerMove={aoMover}
        onPointerUp={aoSoltar}
        onPointerCancel={aoSoltar}
        onClick={aoClicar}
        onFocus={(e) => mostrar(alvoDe(e.target))}
        onBlur={esconder}
      >
        <CamadaAreas
          formas={formas}
          partes={partes}
          nivel={nivel}
          rotuloLider={rotuloLider}
          apagadas={!!formaAberta}
          corDe={corDe}
        />
        {fronteiras && (
          <g className="fronteiras-uf" aria-hidden="true">
            {fronteiras.map((f) => (
              <path key={f.codigo} d={f.d} />
            ))}
          </g>
        )}
        {formaAberta && (
          <g className="municipio-aberto">
            <defs>
              <clipPath id={idRecorte}>
                <path d={formaAberta.d} />
              </clipPath>
            </defs>
            {!desenho && (
              <path
                className="municipio-fundo"
                d={formaAberta.d}
                fill={varCorMapa(parteAberta?.lider ? parteAberta.cor : null)}
                aria-hidden="true"
              />
            )}
            {desenho && !voando && (
              <CamadaZonas
                desenho={desenho}
                partes={zonasPorCodigo}
                neutra={!municipio?.partes.length}
                corMunicipio={parteAberta?.lider ? parteAberta.cor : null}
                px={px}
                recorte={idRecorte}
                rotuloLider={rotuloLider}
              />
            )}
            {(zonaDestacada || zonaSobCursor) && !voando && (
              <g clipPath={`url(#${idRecorte})`} style={{ "--px": px } as CSSProperties}>
                {zonaSobCursor && zonaSobCursor !== zonaDestacada && (
                  <path className="zona-cursor" d={zonaSobCursor.contorno} aria-hidden="true" />
                )}
                {zonaDestacada && <path className="zona-destaque" d={zonaDestacada.contorno} aria-hidden="true" />}
              </g>
            )}
            <path className="contorno contorno-selecionado" d={formaAberta.d} aria-hidden="true" />
          </g>
        )}
        {exterior && (
          <text className="rotulo-exterior" x={exterior.centro[0]} y={exterior.caixa[3] + mapa.largura * 0.026}
            style={{ fontSize: `${mapa.largura * 0.02}px` }} aria-hidden="true">
            Exterior
          </text>
        )}
        {destaque && <path className="contorno" d={destaque.d} aria-hidden="true" />}
      </svg>

      <div className="mapa-controles" role="group" aria-label="Aproximação do mapa">
        <button type="button" className="botao" onClick={() => zoomEm(PASSO_ZOOM)} aria-label="Aproximar"
          title="Aproximar (tecla +)" disabled={zoom >= limites.maxZoom - 0.001}>
          +
        </button>
        <button type="button" className="botao" onClick={() => zoomEm(1 / PASSO_ZOOM)} aria-label="Afastar"
          title="Afastar (tecla −)" disabled={!aproximado}>
          −
        </button>
        {formaAberta && foraDoPadrao ? (
          <button type="button" className="botao" onClick={() => animar(null, DURACAO_VOO)} title="Enquadrar o município (tecla 0)">
            Município
          </button>
        ) : (
          aproximado && (
            <button
              type="button"
              className="botao"
              onClick={() => animar(formaAberta ? vistaInicial(limites) : null, DURACAO_VOO)}
              title={formaAberta ? "Mapa inteiro da UF" : "Mapa inteiro (tecla 0)"}
            >
              Ver tudo
            </button>
          )
        )}
      </div>
      {lembrete && (
        <div className="mapa-lembrete" aria-hidden="true">
          Use Ctrl + rolagem (⌘ no Mac) ou os botões para aproximar
        </div>
      )}

      {dica && (
        <div
          className="dica"
          style={{
            left: Math.max(0, Math.min(dica.x + 14, (caixa.current?.clientWidth ?? 600) - 270)),
            top: dica.y + 14,
          }}
        >
          <ConteudoDica dica={dica} rotuloLider={rotuloLider} />
        </div>
      )}
      {lideres.length > 0 && modo === "vencedor" && (
        <div className="legenda" aria-label="Legenda do mapa">
          {lideres.map(([cor, rotulo]) => (
            <span key={cor} className="legenda-item">
              <span className="amostra-cor" style={{ background: varCorMapa(cor) }} />
              {rotulo}
            </span>
          ))}
        </div>
      )}
      {modo === "intensidade" && lideres.length > 0 && (
        <div className="legenda escala-lideres" aria-label="Legenda do mapa: % dos válidos de quem lidera">
          {lideres.map(([cor, rotulo]) => (
            <span key={cor} className="legenda-item">
              {FAIXAS_PCT.map((f) => (
                <span key={f.rotulo} className="amostra-cor" title={f.rotulo}
                  style={{ background: misturar(varCorMapa(cor), f.forca) }} />
              ))}
              {rotulo}
            </span>
          ))}
          <span className="legenda-item">
            % dos válidos de quem lidera, do mais claro ao mais forte: {FAIXAS_PCT.map((f) => f.rotulo).join(" · ")}
          </span>
        </div>
      )}
      {modo === "mudanca" && contextoMudanca && (
        <div className="legenda" aria-label="Legenda do mapa">
          <span className="legenda-item">
            <span className="amostra-cor" style={{ background: varCor(contextoMudanca.a.cor) }} />
            {contextoMudanca.a.nome} cresceu mais
          </span>
          <span className="legenda-item">
            <span className="amostra-cor" style={{ background: varCor(contextoMudanca.b.cor) }} />
            {contextoMudanca.b.nome} cresceu mais
          </span>
        </div>
      )}
      {modo === "mudanca" && (
        <Escala titulo="Diferença entre o crescimento dos dois, do 1º para o 2º turno" faixas={FAIXAS_MUDANCA}
          cor="var(--texto-2)" />
      )}
      {modo === "abstencao" && <Escala titulo="Abstenção sobre o eleitorado" faixas={FAIXAS_ABSTENCAO} cor="var(--texto)" />}
      {fora.length > 0 && nivel === "uf" && (
        <div className="legenda" aria-label="Fora do mapa atual">
          {fora.map((p) => (
            <button key={p.codigo} type="button" className="botao" onClick={() => onSelecionar(p)}>
              <span className="amostra-cor" style={{ background: varCorMapa(p.lider ? p.cor : null) }} />
              {p.nome}: {p.lider ? `${rotuloLider(p)} ${percentual(p.pct)}` : "sem dados"}
            </button>
          ))}
        </div>
      )}
      {fora.length > 0 && nivel === "mu" && !formaAberta && (
        <p className="candidato-detalhe">
          {fora.length === 1 ? "1 município não tem área" : `${numero(fora.length)} municípios não têm área`} na malha
          atual do IBGE e aparece{fora.length === 1 ? "" : "m"} só na tabela.
        </p>
      )}
      {desenho && municipio?.zonas && (
        <NotaZonas arquivo={municipio.zonas} semResultado={!municipio.partes.length}
          lider={parteAberta?.lider ? rotuloLider(parteAberta) : null} />
      )}
    </div>
  );
}

/** Escala de um modo de cor: as faixas, da mais fraca à mais forte, numa cor neutra. */
function Escala({ titulo, faixas, cor }: { titulo: string; faixas: Faixa[]; cor: string }) {
  return (
    <div className="legenda escala-mapa" aria-label={titulo}>
      <span className="legenda-item">{titulo}:</span>
      {faixas.map((f) => (
        <span key={f.rotulo} className="legenda-item">
          <span className="amostra-cor" style={{ background: misturar(cor, f.forca) }} />
          {f.rotulo}
        </span>
      ))}
    </div>
  );
}

/** O que a dica mostra para uma área, uma zona ou um local de votação. */
function ConteudoDica({ dica, rotuloLider }: { dica: Dica; rotuloLider: (p: Parte) => string }) {
  if (dica.tipo === "local") {
    return (
      <>
        <div>
          <strong>{dica.local.nome}</strong>
        </div>
        <div className="candidato-detalhe">
          Local de votação da zona {dica.local.zona} · {numero(dica.local.eleitores)} eleitores
        </div>
      </>
    );
  }
  const parte = dica.parte;
  const titulo = dica.tipo === "zona" ? `Zona ${dica.zona}` : dica.nome;
  return (
    <>
      <div>
        <strong>{titulo}</strong>
      </div>
      {parte?.lider ? (
        <>
          <div className="dica-valor">
            <span className="dica-chave" style={{ background: varCorMapa(parte.cor) }} />
            {percentual(parte.pct)} · {rotuloLider(parte)}
          </div>
          {parte.margem != null && (
            <div className="candidato-detalhe">Vantagem de {percentual(parte.margem).replace("%", " p.p.")}</div>
          )}
          <div className="candidato-detalhe">
            {parte.finalizada ? "Totalização concluída" : `${percentual(parte.pct_secoes)} das seções`}
            {parte.eleitorado ? ` · ${numero(parte.eleitorado)} eleitores` : ""}
          </div>
        </>
      ) : dica.tipo === "zona" ? (
        <div className="candidato-detalhe">
          {dica.info ? `${numero(dica.info.eleitores)} eleitores · ${numero(dica.info.locais)} locais de votação` : ""}
        </div>
      ) : (
        <div className="candidato-detalhe">Sem dados para esta área.</div>
      )}
      {dica.tipo === "zona" && parte?.lider && dica.info && (
        <div className="candidato-detalhe">{numero(dica.info.locais)} locais de votação</div>
      )}
    </>
  );
}

/**
 * Nota de método sob o mapa das zonas: de onde vem o desenho, o que ficou de fora e, sem resultado por
 * zona na fonte, por que todas têm a mesma cor.
 */
function NotaZonas({ arquivo, semResultado, lider }: { arquivo: ArquivoZonas; semResultado: boolean; lider: string | null }) {
  const { sem_coordenada: sem = 0, fora_do_municipio: fora = 0 } = arquivo.descartados ?? {};
  const descartados = sem + fora;
  return (
    <p className="nota-mapa">
      Contorno aproximado das zonas eleitorais: cada zona é a área mais perto dos seus locais de votação (pontos no
      mapa), segundo os dados abertos do TSE de {arquivo.ano}. A Justiça Eleitoral não publica os limites das zonas.
      {descartados > 0 &&
        ` ${numero(descartados)} ${descartados === 1 ? "local ficou" : "locais ficaram"} fora do desenho (sem coordenada ou com coordenada fora do município); os eleitores deles contam na tabela.`}
      {semResultado &&
        ` Esta fonte não traz o resultado de cada zona (sai nos dados abertos do TSE depois da totalização): ${
          lider ? `as zonas aparecem no tom de quem venceu no município, ${lider}` : "as zonas aparecem na mesma cor"
        }, só para mostrar onde ficam.`}
    </p>
  );
}
