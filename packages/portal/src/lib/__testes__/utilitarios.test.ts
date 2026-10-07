/** Formato pt-BR, paleta, busca, URL da tela, endereços dos feeds e regras de navegação. */
import { describe, expect, it } from "vitest";
import { buscar, chaveMunicipio, CODIGO_UF, normalizar, UFS } from "../busca";
import { clarear, CORES_NO_MAPA, PALETA_CLARA, PALETA_ESCURA, varCor, varCorMapa } from "../cores";
import { escreverSelecao, lerSelecao, ufDaAbrangencia } from "../estado-url";
import { BASE_DADOS, urls } from "../feeds";
import { dataPorExtenso, haQuanto, hora, iniciais, instante, numero, numeroCompacto, percentual } from "../formato";
import {
  abrangenciaAcima,
  ajustarAbrangencia,
  cargoNaAbrangencia,
  escolherCargo,
  escolherEleicao,
  gruposDeEleicoes,
  selecaoCompleta,
  tipoDeTela,
} from "../selecao";
import type { CargoFeed, EleicaoIndice, Indice, Municipio } from "../tipos";

describe("formato brasileiro", () => {
  it("números e percentuais", () => {
    expect(numero(56104503)).toBe("56.104.503");
    expect(numero(null)).toBe("—");
    expect(percentual(47.027772356)).toBe("47,03%");
    expect(percentual(undefined)).toBe("—");
    expect(numeroCompacto(1_500_000)).toMatch(/1,5\s?mi/);
  });
  it("datas no horário de Brasília", () => {
    expect(instante("2026-10-05T02:58:39-03:00")).toBe("05/10/2026, 02:58:39");
    expect(instante("lixo")).toBe("—");
    expect(hora("2026-10-04T20:15:00-03:00")).toBe("20:15");
    expect(dataPorExtenso("2026-10-04")).toBe("4 de outubro de 2026");
    expect(dataPorExtenso(null)).toBe("—");
  });
  it("há quanto tempo", () => {
    const agora = new Date("2026-10-04T21:00:00-03:00");
    expect(haQuanto("2026-10-04T20:59:30-03:00", agora)).toBe("há menos de 1 min");
    expect(haQuanto("2026-10-04T20:45:00-03:00", agora)).toBe("há 15 min");
    expect(haQuanto("2026-10-04T18:00:00-03:00", agora)).toBe("há 3 h");
    expect(haQuanto("2026-10-01T21:00:00-03:00", agora)).toBe("há 3 dias");
    expect(haQuanto("2026-10-04T22:00:00-03:00", agora)).toBe("agora");
    expect(haQuanto(null)).toBe("");
  });
  it("iniciais", () => {
    expect(iniciais("FLAVIO BOLSONARO")).toBe("FB");
    expect(iniciais("LULA")).toBe("L");
    expect(iniciais("ESCRITOR AUGUSTO CURY")).toBe("EC");
    expect(iniciais("VETERINÁRIO WILSON GRASSI")).toBe("VG");
  });
});

describe("cores", () => {
  it("paleta fixa de oito posições, clara e escura", () => {
    expect(PALETA_CLARA).toHaveLength(8);
    expect(PALETA_ESCURA).toHaveLength(8);
    expect(varCor(0)).toBe("var(--serie-1)");
    expect(varCor(7)).toBe("var(--serie-8)");
    expect(varCor(8)).toBe("var(--serie-outros)");
    expect(varCor(-1)).toBe("var(--serie-outros)");
  });
  it("mapa pinta só as três primeiras posições", () => {
    expect(CORES_NO_MAPA).toBe(3);
    expect(varCorMapa(2)).toBe("var(--serie-3)");
    expect(varCorMapa(3)).toBe("var(--serie-outros)");
    expect(varCorMapa(null)).toBe("var(--mapa-sem-lider)");
  });
  it("clarear mistura com branco", () => {
    expect(clarear("#000000", 0)).toBe("#ffffff");
    expect(clarear("#2a78d6", 1)).toBe("#2a78d6");
    expect(clarear("#000000", 0.5)).toBe("#808080");
  });
});

const municipios: Municipio[] = [
  { uf: "sp", tse: "71072", ibge: "3550308", nome: "São Paulo", nome_tse: "SÃO PAULO", capital: true },
  { uf: "pb", tse: "20516", ibge: "2513703", nome: "São Paulo do Potengi", nome_tse: "", capital: false },
  { uf: "sp", tse: "62138", ibge: "3505708", nome: "Barueri", nome_tse: "BARUERI", capital: false },
  { uf: "zz", tse: "29254", ibge: null, nome: "Abidjã", nome_tse: "ABIDJÃ", capital: false },
  { uf: "pr", tse: "75353", ibge: "4106902", nome: "Curitiba", nome_tse: "CURITIBA", capital: true },
];

describe("busca", () => {
  it("normaliza acento, caixa e pontuação", () => {
    expect(normalizar("  São  Paulo! ")).toBe("sao paulo");
    expect(normalizar("Ji-Paraná")).toBe("ji parana");
  });
  it("UF primeiro, depois capital, depois o resto", () => {
    const r = buscar("são paulo", municipios);
    expect(r.map((a) => a.abrangencia)).toEqual(["uf-sp", "mu-3550308", "mu-2513703"]);
    expect(r[1]!.detalhe).toBe("São Paulo · capital");
  });
  it("busca no meio do nome e no exterior", () => {
    expect(buscar("paulo", municipios).map((a) => a.rotulo)).toContain("São Paulo do Potengi");
    expect(buscar("abidja", municipios)[0]).toMatchObject({ abrangencia: "mu-zz-29254", detalhe: "Exterior" });
    expect(buscar("sp", municipios)[0]!.abrangencia).toBe("uf-sp");
    expect(buscar("", municipios)).toEqual([]);
    expect(buscar("a", municipios, 2)).toHaveLength(2);
  });
  it("tabelas de UF completas", () => {
    expect(Object.keys(CODIGO_UF)).toHaveLength(27);
    expect(Object.keys(UFS)).toHaveLength(28);
    expect(chaveMunicipio(municipios[3]!)).toBe("zz-29254");
  });
});

describe("URL da tela", () => {
  it("lê e escreve a seleção", () => {
    const s = lerSelecao(new URLSearchParams("e=2026-1t-geral&c=presidente&a=uf-sp&tv=1"));
    expect(s).toEqual({ eleicao: "2026-1t-geral", cargo: "presidente", abrangencia: "uf-sp", tv: true });
    expect(escreverSelecao(s)).toBe("?e=2026-1t-geral&c=presidente&a=uf-sp&tv=1");
    expect(escreverSelecao({ eleicao: null, cargo: null, abrangencia: "br", tv: false })).toBe("");
  });
  it("descarta o que não é seguro", () => {
    const s = lerSelecao(new URLSearchParams("e=../x&c=<script>&a=uf-sp/../../etc"));
    expect(s).toEqual({ eleicao: null, cargo: null, abrangencia: "br", tv: false });
    expect(lerSelecao(new URLSearchParams("a=mu-zz-29254")).abrangencia).toBe("mu-zz-29254");
    // UFs das eleições de 1933 a 1990: o Distrito Federal antigo e os territórios têm códigos próprios
    expect(lerSelecao(new URLSearchParams("a=uf-df-antigo")).abrangencia).toBe("uf-df-antigo");
    expect(lerSelecao(new URLSearchParams("a=uf-gb")).abrangencia).toBe("uf-gb");
    expect(lerSelecao(new URLSearchParams("a=uf-")).abrangencia).toBe("br");
    expect(lerSelecao(new URLSearchParams("a=uf-1x")).abrangencia).toBe("br");
    expect(ufDaAbrangencia("uf-rj")).toBe("rj");
    expect(ufDaAbrangencia("mu-3550308")).toBeNull();
  });
  it("endereços dos feeds", () => {
    expect(BASE_DADOS).toBe("/dados/eleicoes");
    expect(urls.feed("2026-1t-geral", "presidente", "uf-sp")).toBe("/dados/eleicoes/2026-1t-geral/presidente/uf-sp.json");
    expect(urls.historico("2026-1t-geral", "presidente", "br")).toBe(
      "/dados/eleicoes/2026-1t-geral/presidente/historico-br.json",
    );
    expect(urls.malhaUf("sp")).toBe("/dados/eleicoes/geo/uf-sp-mu.json");
    expect(urls.foto("fotos/ele2026/6257/br/1.jpeg")).toBe("/dados/eleicoes/fotos/ele2026/6257/br/1.jpeg");
    expect(urls.foto("https://outro.site/x.jpeg")).toBeNull();
    expect(() => urls.feed("../x", "presidente", "br")).toThrow();
  });
});

const cargo = (slug: string, nivel: "br" | "uf" | "mu", ufs?: string[]): CargoFeed => ({
  slug, codigo: 1, nome: slug, tipo: "majoritario", nivel, vagas: null, ufs,
});

describe("seletor de eleições", () => {
  const e = (id: string, ano: number, municipios?: boolean) =>
    ({ id, ano, municipios, nome: id, turno: 1, tipo: "geral", origem: "dados_abertos", ao_vivo: false,
      atualizado_em: null, cargos: [], ufs: [], data: null }) as unknown as EleicaoIndice;
  it("sem eleições antigas, um grupo só e sem rótulo", () => {
    const lista = [e("2026-1t-geral", 2026), e("2024-1t-municipal", 2024)];
    expect(gruposDeEleicoes(lista)).toEqual([[null, lista]]);
  });
  it("com as de 1933 a 1990, dois grupos na ordem do índice", () => {
    const lista = [e("2026-1t-geral", 2026), e("1989-2t-geral", 1989, false), e("1950-1t-geral", 1950, false)];
    const grupos = gruposDeEleicoes(lista);
    expect(grupos.map(([rotulo, l]) => [rotulo, l.map((x) => x.id)])).toEqual([
      ["Por estado e município", ["2026-1t-geral"]],
      ["1933 a 1990: só por estado", ["1989-2t-geral", "1950-1t-geral"]],
    ]);
    expect(gruposDeEleicoes([lista[2]!]).map(([r]) => r)).toEqual(["1933 a 1990: só por estado"]);
  });
});

describe("navegação", () => {
  const e1 = { id: "2022-1t-geral", ao_vivo: false, cargos: [cargo("presidente", "br")] } as unknown as EleicaoIndice;
  const e2 = { id: "2026-1t-geral", ao_vivo: true, cargos: [cargo("governador", "uf", ["sp"])] } as unknown as EleicaoIndice;
  const indice = { versao: 1, gerado_em: null, eleicoes: [e1, e2] } as Indice;

  it("abre a eleição ao vivo quando a URL não diz qual", () => {
    expect(escolherEleicao(indice, null)?.id).toBe("2026-1t-geral");
    expect(escolherEleicao(indice, "2022-1t-geral")?.id).toBe("2022-1t-geral");
    expect(escolherEleicao(indice, "inexistente")?.id).toBe("2026-1t-geral");
    expect(escolherEleicao({ ...indice, eleicoes: [] }, null)).toBeNull();
    expect(escolherCargo(e2, "nada")?.slug).toBe("governador");
    expect(selecaoCompleta(indice, { eleicao: null, cargo: null, abrangencia: "br", tv: false })).toMatchObject({
      eleicao: "2026-1t-geral", cargo: "governador",
    });
  });
  it("tela de resultado ou de panorama", () => {
    expect(tipoDeTela(cargo("presidente", "br"), "br")).toBe("resultado");
    expect(tipoDeTela(cargo("governador", "uf"), "br")).toBe("panorama");
    expect(tipoDeTela(cargo("governador", "uf"), "uf-sp")).toBe("resultado");
    expect(tipoDeTela(cargo("prefeito", "mu"), "uf-sp")).toBe("panorama");
    expect(tipoDeTela(cargo("prefeito", "mu"), "mu-3550308")).toBe("resultado");
  });
  it("cargo só onde foi disputado", () => {
    const distrital = cargo("deputado-distrital", "uf", ["df"]);
    expect(cargoNaAbrangencia(distrital, "sp")).toBe(false);
    expect(cargoNaAbrangencia(distrital, "df")).toBe(true);
    expect(cargoNaAbrangencia(distrital, null)).toBe(true);
    expect(ajustarAbrangencia(distrital, "uf-sp", "sp")).toBe("br");
    expect(ajustarAbrangencia(distrital, "uf-df", "df")).toBe("uf-df");
    expect(abrangenciaAcima("mu-3550308", "sp")).toBe("uf-sp");
    expect(abrangenciaAcima("mu-3550308", null)).toBe("br");
    expect(abrangenciaAcima("uf-sp", null)).toBe("br");
  });
});
