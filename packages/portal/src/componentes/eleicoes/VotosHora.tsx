"use client";

/**
 * Votos por hora do lugar aberto (ADR-057): quantos eleitores votaram em cada hora, a hora de mais votos, até que
 * horas metade votou e quantos votaram depois das 17h (na fila); abaixo, as UFs, os municípios ou as zonas, e no
 * município cada seção. Dados do TSE: os logs das urnas (cada voto computado tem a hora do relógio da urna).
 */

import { useEffect, useMemo, useState } from "react";
import { BaixarCsv } from "@/componentes/BaixarCsv";
import { Paginacao, usePaginacao } from "@/componentes/Paginacao";
import { GraficoBarras } from "@/componentes/paineis/Comuns";
import { pct } from "@/lib/eleitorado";
import { numero, percentual } from "@/lib/formato";
import { hhmm } from "@/lib/horarios";
import type { ArquivoVotosHora, TurnoVotosHora } from "@/lib/tipos";
import {
  FIM_DA_VOTACAO,
  depoisDoFim,
  horaDePico,
  horas,
  lugaresDosVotos,
  metadeAte,
  rotuloHora,
  secoesDosVotos,
  turnoDosVotos,
} from "@/lib/votosHora";

/** Entrada do painel: o arquivo do lugar, o turno da eleição aberta, a zona escolhida e a navegação. */
interface Props {
  arquivo: ArquivoVotosHora;
  /** Turno da eleição aberta: o painel abre nele, quando o arquivo o tem. */
  turno: number | null;
  /** Zona escolhida no mapa do município. */
  zonaEscolhida?: string | null;
  /** Nome do local de votação de cada seção (`"<zona>-<seção>"`), do eleitorado do município, quando carregado. */
  locais?: Map<string, string>;
  /** Abre outro lugar (a abrangência do feed, como `uf-sp` ou `mu-3550308`). */
  onSelecionar: (abrangencia: string) => void;
}

/** Um número com rótulo e, quando há, o detalhe logo abaixo (como no painel do eleitorado). */
function Bloco({ rotulo, valor, detalhe }: { rotulo: string; valor: string; detalhe?: string }) {
  return (
    <div>
      <div className="total-rotulo">{rotulo}</div>
      <div className="total-valor">{valor}</div>
      {detalhe && <div className="total-detalhe">{detalhe}</div>}
    </div>
  );
}

const votosTexto = (n: number) => `${numero(n)} ${n === 1 ? "voto" : "votos"}`;

/** O painel inteiro dos votos por hora do lugar. */
export function VotosHora({ arquivo, turno, zonaEscolhida, locais, onSelecionar }: Props) {
  const municipio = arquivo.nivel === "municipio";
  const turnos = Object.keys(arquivo.lugar.turnos).sort();
  const [t, setT] = useState<string | null>(() => turnoDosVotos(arquivo.lugar.turnos, turno));
  const [zona, setZona] = useState<string | null>(null);
  useEffect(() => setT(turnoDosVotos(arquivo.lugar.turnos, turno)), [arquivo, turno]);
  useEffect(() => setZona(municipio ? (zonaEscolhida ?? null) : null), [municipio, zonaEscolhida, arquivo.lugar.chave]);
  const daZona = zona && t ? arquivo.zonas?.find((z) => z.zona === zona)?.turnos[t] : undefined;
  const dados: TurnoVotosHora | undefined = daZona ?? (t ? arquivo.lugar.turnos[t] : undefined);
  const barras = useMemo(() => horas(dados?.por_hora ?? []).map((h) => ({ rotulo: rotuloHora(h.hora), valor: h.votos })),
    [dados]);
  if (!t || !dados || dados.votos === 0) return null;
  const nome = zona ? `zona ${zona} de ${arquivo.lugar.nome}` : arquivo.lugar.nome;
  const pico = horaDePico(dados.por_hora);
  const fila = depoisDoFim(dados.por_hora);
  const metade = metadeAte(dados);

  return (
    <section className="cartao cartao-corpo eleitorado horarios" aria-labelledby="titulo-votos-hora">
      <h2 id="titulo-votos-hora" className="titulo-secao">
        Votos por hora: {nome}, {arquivo.ano}
      </h2>
      <div className="horarios-escolhas">
        {turnos.length > 1 && (
          <div className="eleitorado-abas" role="group" aria-label="Turno">
            {turnos.map((x) => (
              <button key={x} type="button" className="botao" aria-pressed={x === t} onClick={() => setT(x)}>
                {x}º turno
              </button>
            ))}
          </div>
        )}
        {municipio && (arquivo.zonas?.length ?? 0) > 1 && (
          <label className="eleitorado-zona">
            Zona eleitoral{" "}
            <select className="seletor" value={zona ?? ""} onChange={(e) => setZona(e.target.value || null)}>
              <option value="">Todas ({arquivo.zonas!.length})</option>
              {arquivo.zonas!.map((z) => (
                <option key={z.zona} value={z.zona}>Zona {z.zona}</option>
              ))}
            </select>
          </label>
        )}
      </div>

      <div className="totais">
        <Bloco rotulo="Votos registrados" valor={numero(dados.votos)} detalhe={`em ${numero(dados.secoes)} seções`} />
        {pico && (
          <Bloco rotulo="Hora com mais votos" valor={`${pico.hora}h às ${pico.hora + 1}h`}
            detalhe={`${votosTexto(pico.votos)} (${percentual(pct(pico.votos, dados.votos))})`} />
        )}
        {metade !== null && <Bloco rotulo="Metade tinha votado até" valor={hhmm(metade)} />}
        <Bloco rotulo={`Votaram depois das ${FIM_DA_VOTACAO}h`} valor={numero(fila)}
          detalhe={`${percentual(pct(fila, dados.votos))}, na fila do encerramento`} />
      </div>

      <GraficoBarras titulo={`Votos a cada hora, ${nome}`} barras={barras} formatar={votosTexto}
        formatarEixo={(n) => numero(Math.round(n))} />

      {!zona && <Lugares arquivo={arquivo} turno={t} onSelecionar={onSelecionar} onZona={setZona} />}
      {municipio && <Secoes arquivo={arquivo} turno={t} zona={zona} locais={locais} />}

      <p className="candidato-detalhe">
        Fonte: TSE, logs das urnas (dados abertos de 2022 em diante): cada voto computado tem a hora do relógio da
        urna, inclusive o eleitor em trânsito. Horário de Brasília (no exterior, o local de cada país). A soma dos
        logs fica a menos de 0,1% do comparecimento do boletim de urna; numa seção em que a urna foi trocada, o log
        pode ter só parte dos votos.
      </p>
    </section>
  );
}

/** As UFs, os municípios ou as zonas do lugar, 20 por página, com o link para abrir cada um. */
function Lugares({ arquivo, turno, onSelecionar, onZona }: { arquivo: ArquivoVotosHora; turno: string;
  onSelecionar: (abrangencia: string) => void; onZona: (zona: string) => void }) {
  const lugares = useMemo(() => lugaresDosVotos(arquivo, turno), [arquivo, turno]);
  const pagina = usePaginacao(lugares);
  if (lugares.length < 2) return null;
  const nivel = arquivo.nivel === "br" ? "Estado" : arquivo.nivel === "uf" ? "Município" : "Zona";
  const titulo = arquivo.nivel === "br" ? "Por estado" : arquivo.nivel === "uf" ? "Por município" : "Por zona eleitoral";
  const todasAsHoras = [...new Set(lugares.flatMap((l) => horas(l.turno.por_hora).map((h) => h.hora)))].sort((a, b) => a - b);
  return (
    <>
      <h3 className="subtitulo-secao">{titulo} ({lugares.length})</h3>
      <div className="tabela-rolavel">
        <table className="tabela">
          <thead>
            <tr>
              <th>{nivel}</th>
              <th className="n">Votos</th>
              <th className="n">Hora com mais votos</th>
              <th className="n">Depois das {FIM_DA_VOTACAO}h</th>
            </tr>
          </thead>
          <tbody>
            {pagina.visiveis.map((l) => {
              const pico = horaDePico(l.turno.por_hora);
              return (
                <tr key={l.chave}>
                  <td>
                    <button type="button" className="botao-link"
                      onClick={() => (l.abrangencia ? onSelecionar(l.abrangencia) : onZona(l.chave))}>
                      {l.nome}
                    </button>
                  </td>
                  <td className="n">{numero(l.turno.votos)}</td>
                  <td className="n">{pico ? `${pico.hora}h` : "—"}</td>
                  <td className="n">{percentual(pct(depoisDoFim(l.turno.por_hora), l.turno.votos))}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <Paginacao {...pagina} rotulo={arquivo.nivel === "br" ? "estados" : arquivo.nivel === "uf" ? "municípios" : "zonas"} />
      <BaixarCsv nome={`votos-hora-${arquivo.ano}-${turno}t-${arquivo.lugar.chave}-lugares`}
        colunas={[nivel, "Votos", ...todasAsHoras.map((h) => `${h}h às ${h + 1}h`)]}
        linhas={() => lugares.map((l) => {
          const porHora = new Map(horas(l.turno.por_hora).map((h) => [h.hora, h.votos]));
          return [l.nome, l.turno.votos, ...todasAsHoras.map((h) => porHora.get(h) ?? 0)];
        })} />
    </>
  );
}

/** As seções do município no turno (ou da zona escolhida), com busca pelo local de votação, 20 por página. */
function Secoes({ arquivo, turno, zona, locais }: { arquivo: ArquivoVotosHora; turno: string; zona: string | null;
  locais?: Map<string, string> }) {
  const [termo, setTermo] = useState("");
  const secoes = useMemo(() => secoesDosVotos(arquivo, turno, zona, termo, locais), [arquivo, turno, zona, termo, locais]);
  const pagina = usePaginacao(secoes);
  if (!arquivo.secoes?.length) return null;
  const todasAsHoras = [...new Set(secoes.flatMap((s) => horas(s.porHora).map((h) => h.hora)))].sort((a, b) => a - b);
  return (
    <>
      <h3 className="subtitulo-secao">Seções eleitorais ({numero(secoes.length)})</h3>
      <input className="seletor filtro-tabela" type="search" value={termo} placeholder="Local de votação ou número da seção"
        aria-label="Filtrar as seções pelo local de votação ou pelo número" onChange={(e) => setTermo(e.target.value)} />
      <div className="tabela-rolavel">
        <table className="tabela">
          <thead>
            <tr>
              <th className="n">Zona</th>
              <th className="n">Seção</th>
              <th>Local de votação</th>
              <th className="n">Votos</th>
              <th className="n">Hora com mais votos</th>
              <th className="n">Depois das {FIM_DA_VOTACAO}h</th>
            </tr>
          </thead>
          <tbody>
            {pagina.visiveis.map((s) => {
              const pico = horaDePico(s.porHora);
              return (
                <tr key={`${s.zona}-${s.secao}`}>
                  <td className="n">{s.zona}</td>
                  <td className="n">{s.secao}</td>
                  <td>{s.local ?? "—"}</td>
                  <td className="n">{numero(s.votos)}</td>
                  <td className="n">{pico ? `${pico.hora}h (${numero(pico.votos)})` : "—"}</td>
                  <td className="n">{numero(depoisDoFim(s.porHora))}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <Paginacao {...pagina} rotulo="seções" />
      <BaixarCsv nome={`votos-hora-${arquivo.ano}-${turno}t-${arquivo.lugar.chave}-secoes${zona ? `-zona-${zona}` : ""}`}
        colunas={["Zona", "Seção", "Local de votação", "Votos", ...todasAsHoras.map((h) => `${h}h às ${h + 1}h`)]}
        linhas={() => secoes.map((s) => {
          const porHora = new Map(horas(s.porHora).map((h) => [h.hora, h.votos]));
          return [s.zona, s.secao, s.local, s.votos, ...todasAsHoras.map((h) => porHora.get(h) ?? 0)];
        })} />
    </>
  );
}
