"use client";

/**
 * Horários das urnas do lugar aberto (ADR-056): quando as urnas abriram e fecharam, quantas fecharam depois das
 * 17h30 (sinal de fila na hora de encerrar) e quando os boletins chegaram ao TSE; abaixo, as UFs, os municípios ou
 * as zonas, e no município cada seção. Dados do TSE (boletim de urna dos dados abertos).
 */

import { useEffect, useMemo, useState } from "react";
import { BaixarCsv } from "@/componentes/BaixarCsv";
import { Paginacao, usePaginacao } from "@/componentes/Paginacao";
import { GraficoBarras } from "@/componentes/paineis/Comuns";
import { pct } from "@/lib/eleitorado";
import { numero, percentual } from "@/lib/formato";
import {
  FILA,
  barrasDoHistograma,
  hhmm,
  lugaresDosHorarios,
  secoesDosHorarios,
  turnoDosHorarios,
} from "@/lib/horarios";
import type { ArquivoHorarios, HistogramaHorarios, ResumoHorarios } from "@/lib/tipos";

/** Entrada do painel: o arquivo do lugar, o turno da eleição aberta, a zona escolhida e a navegação. */
interface Props {
  arquivo: ArquivoHorarios;
  /** Turno da eleição aberta: o painel abre nele, quando o arquivo o tem. */
  turno: number | null;
  /** Zona escolhida no mapa do município. */
  zonaEscolhida?: string | null;
  /** Nomes dos locais de votação (`"<zona>-<local>"`), do eleitorado do mesmo município, quando carregado. */
  locais?: Record<string, string>;
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

const secoesTexto = (n: number) => `${numero(n)} ${n === 1 ? "seção" : "seções"}`;

/** O painel inteiro dos horários do lugar. */
export function Horarios({ arquivo, turno, zonaEscolhida, locais, onSelecionar }: Props) {
  const municipio = arquivo.nivel === "municipio";
  const turnos = Object.keys(arquivo.lugar.turnos).sort();
  const [t, setT] = useState<string | null>(() => turnoDosHorarios(arquivo.lugar.turnos, turno));
  const [zona, setZona] = useState<string | null>(null);
  useEffect(() => setT(turnoDosHorarios(arquivo.lugar.turnos, turno)), [arquivo, turno]);
  useEffect(() => setZona(municipio ? (zonaEscolhida ?? null) : null), [municipio, zonaEscolhida, arquivo.lugar.chave]);
  const daZona = zona && t ? arquivo.zonas?.find((z) => z.zona === zona)?.turnos[t] : undefined;
  const resumo: ResumoHorarios | undefined = daZona ?? (t ? arquivo.lugar.turnos[t] : undefined);
  if (!t || !resumo) return null;
  const nome = zona ? `zona ${zona} de ${arquivo.lugar.nome}` : arquivo.lugar.nome;
  const brasilia = arquivo.horario === "brasilia";
  const h = resumo.histogramas;

  return (
    <section className="cartao cartao-corpo eleitorado horarios" aria-labelledby="titulo-horarios">
      <h2 id="titulo-horarios" className="titulo-secao">
        Horários das urnas: {nome}, {arquivo.ano}
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
        <Bloco rotulo="Seções" valor={numero(resumo.secoes)}
          detalhe={`${percentual(pct(resumo.comparecimento, resumo.aptos))} de comparecimento`} />
        <Bloco rotulo={`Fecharam depois das ${FILA}`} valor={numero(resumo.depois_17h30)}
          detalhe={percentual(pct(resumo.depois_17h30, resumo.secoes))} />
        <Bloco rotulo="Metade das urnas fechou até" valor={hhmm(resumo.encerramento[0])}
          detalhe={`a última às ${hhmm(resumo.encerramento[2])}`} />
        {resumo.recebido[0] !== null && (
          <Bloco rotulo="Metade dos boletins chegou ao TSE até" valor={hhmm(resumo.recebido[0])}
            detalhe={`o último às ${hhmm(resumo.recebido[2])}`} />
        )}
      </div>

      {h && (
        <div className="horarios-graficos">
          <Histograma titulo="Abertura das urnas" h={h.abertura} />
          <Histograma titulo="Encerramento das urnas" h={h.encerramento} />
          {h.recebido && <Histograma titulo="Boletins recebidos pelo TSE" h={h.recebido} />}
        </div>
      )}

      {!zona && <Lugares arquivo={arquivo} turno={t} onSelecionar={onSelecionar} onZona={setZona} />}
      {municipio && <Secoes arquivo={arquivo} turno={t} zona={zona} locais={locais} />}

      <p className="candidato-detalhe">
        Fonte: TSE, boletim de urna de cada seção (dados abertos).{" "}
        {brasilia
          ? "Horários de Brasília: desde 2022 a votação vai das 8h às 17h de Brasília no país todo (no Acre, a urna abre às 6h locais)."
          : "Abertura, encerramento e emissão do boletim no horário local de cada seção; o recebimento, no de Brasília."}{" "}
        O recebimento é a hora em que o boletim chegou ao TSE, registrada por ele; não é a hora do voto. No exterior,
        os horários são os locais de cada país.
      </p>
    </section>
  );
}

/** Um histograma de seções a cada 10 minutos, com as que ficaram antes e depois da faixa do gráfico. */
function Histograma({ titulo, h }: { titulo: string; h: HistogramaHorarios }) {
  const barras = useMemo(() => barrasDoHistograma(h), [h]);
  if (!barras.some((b) => b.valor > 0) && !h.antes && !h.depois) return null;
  const fim = h.inicio + h.contagens.length * h.passo;
  return (
    <div>
      <h3 className="subtitulo-secao">{titulo}</h3>
      <GraficoBarras titulo={`${titulo}: seções a cada ${h.passo} minutos`} barras={barras} formatar={secoesTexto}
        formatarEixo={(n) => numero(Math.round(n))} />
      {(h.antes > 0 || h.depois > 0) && (
        <p className="candidato-detalhe">
          {h.antes > 0 && `Antes das ${hhmm(h.inicio)}: ${secoesTexto(h.antes)}. `}
          {h.depois > 0 && `Depois das ${hhmm(fim)}: ${secoesTexto(h.depois)}.`}
        </p>
      )}
    </div>
  );
}

/** As UFs, os municípios ou as zonas do lugar, 20 por página, com o link para abrir cada um. */
function Lugares({ arquivo, turno, onSelecionar, onZona }: { arquivo: ArquivoHorarios; turno: string;
  onSelecionar: (abrangencia: string) => void; onZona: (zona: string) => void }) {
  const lugares = useMemo(() => lugaresDosHorarios(arquivo, turno), [arquivo, turno]);
  const pagina = usePaginacao(lugares);
  if (lugares.length < 2) return null;
  const nivel = arquivo.nivel === "br" ? "Estado" : arquivo.nivel === "uf" ? "Município" : "Zona";
  const titulo = arquivo.nivel === "br" ? "Por estado" : arquivo.nivel === "uf" ? "Por município" : "Por zona eleitoral";
  const comRecebido = lugares.some((l) => l.resumo.recebido[0] !== null);
  return (
    <>
      <h3 className="subtitulo-secao">{titulo} ({lugares.length})</h3>
      <div className="tabela-rolavel">
        <table className="tabela">
          <thead>
            <tr>
              <th>{nivel}</th>
              <th className="n">Seções</th>
              <th className="n">Depois das {FILA}</th>
              <th className="n">Metade fechou até</th>
              <th className="n">Última fechou</th>
              {comRecebido && <th className="n">Metade dos boletins até</th>}
            </tr>
          </thead>
          <tbody>
            {pagina.visiveis.map((l) => (
              <tr key={l.chave}>
                <td>
                  <button type="button" className="botao-link"
                    onClick={() => (l.abrangencia ? onSelecionar(l.abrangencia) : onZona(l.chave))}>
                    {l.nome}
                  </button>
                </td>
                <td className="n">{numero(l.resumo.secoes)}</td>
                <td className="n">{percentual(pct(l.resumo.depois_17h30, l.resumo.secoes))}</td>
                <td className="n">{hhmm(l.resumo.encerramento[0])}</td>
                <td className="n">{hhmm(l.resumo.encerramento[2])}</td>
                {comRecebido && <td className="n">{hhmm(l.resumo.recebido[0])}</td>}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Paginacao {...pagina} rotulo={arquivo.nivel === "br" ? "estados" : arquivo.nivel === "uf" ? "municípios" : "zonas"} />
      <BaixarCsv nome={`horarios-${arquivo.ano}-${turno}t-${arquivo.lugar.chave}-lugares`}
        colunas={[nivel, "Seções", `Fecharam depois das ${FILA}`, "Metade fechou até", "90% fecharam até", "Última fechou",
          "Metade dos boletins recebidos até", "Último boletim recebido"]}
        linhas={() => lugares.map((l) => [l.nome, l.resumo.secoes, l.resumo.depois_17h30, hhmm(l.resumo.encerramento[0]),
          hhmm(l.resumo.encerramento[1]), hhmm(l.resumo.encerramento[2]), hhmm(l.resumo.recebido[0]),
          hhmm(l.resumo.recebido[2])])} />
    </>
  );
}

/** As seções do município no turno (ou da zona escolhida), com busca pelo local de votação, 20 por página. */
function Secoes({ arquivo, turno, zona, locais }: { arquivo: ArquivoHorarios; turno: string; zona: string | null;
  locais?: Record<string, string> }) {
  const [termo, setTermo] = useState("");
  const secoes = useMemo(() => secoesDosHorarios(arquivo, turno, zona, termo, locais),
    [arquivo, turno, zona, termo, locais]);
  const pagina = usePaginacao(secoes);
  if (!arquivo.secoes?.length) return null;
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
              <th className="n">Compareceram</th>
              <th className="n">Abriu</th>
              <th className="n">Fechou</th>
              <th className="n">Boletim recebido</th>
            </tr>
          </thead>
          <tbody>
            {pagina.visiveis.map((s) => (
              <tr key={`${s.zona}-${s.secao}`}>
                <td className="n">{s.zona}</td>
                <td className="n">{s.secao}</td>
                <td>{s.local}{s.tipo !== "Apurada" && <span className="candidato-detalhe"> ({s.tipo.toLowerCase()})</span>}</td>
                <td className="n">{numero(s.comparecimento)} de {numero(s.aptos)}</td>
                <td className="n">{s.abertura ?? "—"}</td>
                <td className="n">{s.encerramento ?? "—"}</td>
                <td className="n">{s.recebido ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Paginacao {...pagina} rotulo="seções" />
      <BaixarCsv nome={`horarios-${arquivo.ano}-${turno}t-${arquivo.lugar.chave}-secoes${zona ? `-zona-${zona}` : ""}`}
        colunas={["Zona", "Seção", "Local de votação", "Aptos", "Compareceram", "Tipo de urna", "Abertura", "Encerramento",
          "Emissão do boletim", "Boletim recebido"]}
        linhas={() => secoes.map((s) => [s.zona, s.secao, s.local, s.aptos, s.comparecimento, s.tipo, s.abertura,
          s.encerramento, s.emissao, s.recebido])} />
    </>
  );
}
