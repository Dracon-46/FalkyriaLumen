"use client";

/**
 * Eleitorado do lugar aberto (ADR-055): quantos eleitores, com biometria, quem compareceu no turno e o perfil
 * (faixa etária, gênero, escolaridade e estado civil), com o comparecimento de cada grupo; abaixo, as UFs, os
 * municípios ou as zonas, e no município as seções com o local de votação. Dados do TSE (perfil do
 * eleitorado e comparecimento por perfil); as características sensíveis, como raça ou cor, não são publicadas.
 */

import { useEffect, useMemo, useState } from "react";
import { BaixarCsv } from "@/componentes/BaixarCsv";
import { Paginacao, usePaginacao } from "@/componentes/Paginacao";
import {
  CARACTERISTICAS,
  type LinhaCaracteristica,
  linhasDaCaracteristica,
  lugaresAbaixo,
  pct,
  secoesDoMunicipio,
  turnoAMostrar,
} from "@/lib/eleitorado";
import { numero, percentual } from "@/lib/formato";
import type { ArquivoEleitorado, Caracteristica, PerfilEleitorado, TurnoEleitorado } from "@/lib/tipos";

/** Entrada do painel: o arquivo do lugar, o turno da eleição aberta, a zona escolhida e a navegação. */
interface Props {
  arquivo: ArquivoEleitorado;
  /** Turno da eleição aberta: o comparecimento mostrado é o dele, quando o TSE já o publicou. */
  turno: number | null;
  /** Zona escolhida no mapa do município (o perfil abre nela). */
  zonaEscolhida?: string | null;
  /** Abre outro lugar (a abrangência do feed, como `uf-sp` ou `mu-3550308`). */
  onSelecionar: (abrangencia: string) => void;
}

/** Um número com rótulo e, quando há, o detalhe logo abaixo (como no quadro de comparecimento). */
function Bloco({ rotulo, valor, detalhe }: { rotulo: string; valor: string; detalhe?: string }) {
  return (
    <div>
      <div className="total-rotulo">{rotulo}</div>
      <div className="total-valor">{valor}</div>
      {detalhe && <div className="total-detalhe">{detalhe}</div>}
    </div>
  );
}

/** O painel inteiro do eleitorado do lugar. */
export function Eleitorado({ arquivo, turno, zonaEscolhida, onSelecionar }: Props) {
  const municipio = arquivo.nivel === "municipio";
  const [zona, setZona] = useState<string | null>(null);
  useEffect(() => setZona(municipio ? (zonaEscolhida ?? null) : null), [municipio, zonaEscolhida, arquivo.lugar.chave]);
  const daZona = zona ? arquivo.zonas?.find((z) => z.zona === zona) : undefined;
  const perfil: PerfilEleitorado = daZona ?? arquivo.lugar;
  const turnos = daZona?.turnos ?? arquivo.lugar.turnos;
  const t = turnoAMostrar(turnos, turno);
  const doTurno: TurnoEleitorado | null = (t ? turnos[t] : null) ?? null;
  const nome = daZona ? `zona ${daZona.zona} de ${arquivo.lugar.nome}` : arquivo.lugar.nome;
  const [caracteristica, setCaracteristica] = useState<Caracteristica>("faixa_etaria");
  const linhas = useMemo(() => linhasDaCaracteristica(perfil, caracteristica, doTurno),
    [perfil, caracteristica, doTurno]);
  const rotuloCaracteristica = CARACTERISTICAS.find((c) => c.id === caracteristica)!.rotulo;

  return (
    <section className="cartao cartao-corpo eleitorado" aria-labelledby="titulo-eleitorado">
      <h2 id="titulo-eleitorado" className="titulo-secao">
        Eleitorado: {nome}, {arquivo.ano}
      </h2>
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
      <div className="totais">
        <Bloco rotulo="Eleitores" valor={numero(perfil.eleitores)} />
        <Bloco rotulo="Com biometria" valor={numero(perfil.biometria)}
          detalhe={percentual(pct(perfil.biometria, perfil.eleitores))} />
        {doTurno && (
          <>
            <Bloco rotulo={`Compareceram no ${t}º turno`} valor={numero(doTurno.comparecimento)}
              detalhe={percentual(pct(doTurno.comparecimento, doTurno.aptos))} />
            <Bloco rotulo="Faltaram" valor={numero(doTurno.abstencao)}
              detalhe={percentual(pct(doTurno.abstencao, doTurno.aptos))} />
          </>
        )}
      </div>

      <div className="eleitorado-abas" role="group" aria-label="Característica do eleitorado">
        {CARACTERISTICAS.map((c) => (
          <button key={c.id} type="button" className="botao" aria-pressed={c.id === caracteristica}
            onClick={() => setCaracteristica(c.id)}>
            {c.rotulo}
          </button>
        ))}
      </div>
      <TabelaCaracteristica linhas={linhas} rotulo={rotuloCaracteristica} turno={doTurno ? t : null} />
      <BaixarCsv nome={`eleitorado-${arquivo.ano}-${arquivo.lugar.chave}${zona ? `-zona-${zona}` : ""}-${caracteristica}`}
        colunas={[rotuloCaracteristica, "Eleitores", "% do eleitorado",
          ...(doTurno ? [`Aptos no ${t}º turno`, "Compareceram", "% de comparecimento"] : [])]}
        linhas={() => linhas.map((l) => [l.rotulo, l.eleitores, l.pctEleitorado,
          ...(doTurno ? [l.aptos, l.comparecimento, l.pctComparecimento] : [])])} />

      {!zona && <Lugares arquivo={arquivo} turno={t} onSelecionar={onSelecionar} onZona={setZona} />}
      {municipio && <Secoes arquivo={arquivo} zona={zona} />}

      <p className="candidato-detalhe">
        Fonte: TSE, perfil do eleitorado (o cadastro fechado antes da eleição)
        {doTurno ? " e comparecimento por perfil" : ""}. Raça ou cor, deficiência, identidade de gênero e outras
        características sensíveis não são publicadas aqui (LGPD).
      </p>
    </section>
  );
}

/** A tabela de uma característica, com a barra da parte do eleitorado e o comparecimento do turno. */
function TabelaCaracteristica({ linhas, rotulo, turno }: { linhas: LinhaCaracteristica[]; rotulo: string;
  turno: string | null }) {
  const maior = Math.max(...linhas.map((l) => l.pctEleitorado ?? 0), 1);
  return (
    <div className="tabela-rolavel">
      <table className="tabela eleitorado-tabela">
        <thead>
          <tr>
            <th>{rotulo}</th>
            <th className="n">Eleitores</th>
            <th className="eleitorado-coluna-barra">% do eleitorado</th>
            {turno && <th className="n">Comparecimento no {turno}º turno</th>}
          </tr>
        </thead>
        <tbody>
          {linhas.map((l) => (
            <tr key={l.rotulo}>
              <td>{l.rotulo}</td>
              <td className="n">{numero(l.eleitores)}</td>
              <td className="eleitorado-coluna-barra">
                <span className="eleitorado-barra" aria-hidden="true">
                  <span style={{ width: `${((l.pctEleitorado ?? 0) / maior) * 100}%` }} />
                </span>
                {percentual(l.pctEleitorado)}
              </td>
              {turno && <td className="n">{percentual(l.pctComparecimento)}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** As UFs, os municípios ou as zonas do lugar, 20 por página, com o link para abrir cada um. */
function Lugares({ arquivo, turno, onSelecionar, onZona }: { arquivo: ArquivoEleitorado; turno: string | null;
  onSelecionar: (abrangencia: string) => void; onZona: (zona: string) => void }) {
  const lugares = useMemo(() => lugaresAbaixo(arquivo, turno), [arquivo, turno]);
  const pagina = usePaginacao(lugares);
  if (lugares.length < 2) return null;
  const titulo = arquivo.nivel === "br" ? "Por estado" : arquivo.nivel === "uf" ? "Por município" : "Por zona eleitoral";
  return (
    <>
      <h3 className="subtitulo-secao">{titulo} ({lugares.length})</h3>
      <div className="tabela-rolavel">
        <table className="tabela">
          <thead>
            <tr>
              <th>{arquivo.nivel === "br" ? "Estado" : arquivo.nivel === "uf" ? "Município" : "Zona"}</th>
              <th className="n">Eleitores</th>
              <th className="n">Com biometria</th>
              {turno && <th className="n">Comparecimento no {turno}º turno</th>}
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
                <td className="n">{numero(l.eleitores)}</td>
                <td className="n">{percentual(l.pctBiometria)}</td>
                {turno && <td className="n">{percentual(l.pctComparecimento)}</td>}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Paginacao {...pagina} rotulo={arquivo.nivel === "br" ? "estados" : arquivo.nivel === "uf" ? "municípios" : "zonas"} />
      <BaixarCsv nome={`eleitorado-${arquivo.ano}-${arquivo.lugar.chave}-lugares`}
        colunas={["Lugar", "Eleitores", "% com biometria", ...(turno ? [`% de comparecimento no ${turno}º turno`] : [])]}
        linhas={() => lugares.map((l) => [l.nome, l.eleitores, l.pctBiometria, ...(turno ? [l.pctComparecimento] : [])])} />
    </>
  );
}

/** As seções do município (ou da zona escolhida), com busca pelo local de votação, 20 por página. */
function Secoes({ arquivo, zona }: { arquivo: ArquivoEleitorado; zona: string | null }) {
  const [termo, setTermo] = useState("");
  const secoes = useMemo(() => secoesDoMunicipio(arquivo, zona, termo), [arquivo, zona, termo]);
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
              <th className="n">Eleitores</th>
            </tr>
          </thead>
          <tbody>
            {pagina.visiveis.map((s) => (
              <tr key={`${s.zona}-${s.secao}`}>
                <td className="n">{s.zona}</td>
                <td className="n">{s.secao}</td>
                <td>{s.local}</td>
                <td className="n">{numero(s.eleitores)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Paginacao {...pagina} rotulo="seções" />
      <BaixarCsv nome={`eleitorado-${arquivo.ano}-${arquivo.lugar.chave}-secoes${zona ? `-zona-${zona}` : ""}`}
        colunas={["Zona", "Seção", "Local de votação", "Eleitores"]}
        linhas={() => secoes.map((s) => [s.zona, s.secao, s.local, s.eleitores])} />
    </>
  );
}
