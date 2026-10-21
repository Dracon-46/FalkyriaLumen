import { gzipSync } from "node:zlib";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  buscarEntes,
  buscarOrgaos,
  carregarContratacoesEnte,
  carregarContratacoesOrgao,
  cnpj,
  codigoSeguro,
  conferir,
  dataCurta,
  descreverEnte,
  criterioRcl,
  faixaCentral,
  faixaCentralEmReais,
  faixaDoLimite,
  grupoDoEnte,
  grupoDoOrgao,
  periodoDoRgf,
  urlRgfDoEnte,
  posicaoNoGrupo,
  urlDcaDoEnte,
  descreverOrgao,
  lerEntes,
  lerOrgaos,
  siglaDoNome,
  mesCurto,
  moeda,
  moedaCompacta,
  tipoDoCodigo,
  topoDoEixo,
  urlsPainel,
  type EnteBusca,
} from "../paineis";
import { ErroFeed } from "../validacao";

const ENTES: EnteBusca[] = [
  { codigo: "35", nome: "São Paulo", uf: "SP", esfera: "E", populacao: 46_000_000 },
  { codigo: "3550308", nome: "São Paulo", uf: "SP", esfera: "M", populacao: 11_900_000 },
  { codigo: "3548708", nome: "São Bernardo do Campo", uf: "SP", esfera: "M", populacao: 810_000 },
  { codigo: "2111300", nome: "São Luís", uf: "MA", esfera: "M", populacao: 1_000_000 },
  { codigo: "3304557", nome: "Rio de Janeiro", uf: "RJ", esfera: "M", populacao: 6_200_000 },
  { codigo: "1", nome: "União", uf: null, esfera: "F", populacao: null },
];

describe("busca de entes", () => {
  it("põe estados antes, quem começa com o termo antes e o maior antes", () => {
    expect(buscarEntes("sao", ENTES).map((e) => e.codigo)).toEqual(["35", "3550308", "2111300", "3548708"]);
    expect(buscarEntes("paulo", ENTES).map((e) => e.codigo)).toEqual(["35", "3550308"]);
    expect(buscarEntes("sp", ENTES).map((e) => e.codigo)).toEqual(["35"]);
    expect(buscarEntes("uniao", ENTES)[0]?.codigo).toBe("1");
    expect(buscarEntes("  ", ENTES)).toEqual([]);
    expect(buscarEntes("s", ENTES, 2)).toHaveLength(2);
  });

  it("lê o entes.json pelas colunas e ignora formato desconhecido", () => {
    const bruto = { versao: 1, colunas: ["codigo", "nome", "uf", "esfera", "populacao"], entes: [["43", "Rio Grande do Sul", "RS", "E", 11]] };
    expect(lerEntes(bruto)).toEqual([{ codigo: "43", nome: "Rio Grande do Sul", uf: "RS", esfera: "E", populacao: 11 }]);
    expect(lerEntes({ versao: 2 })).toEqual([]);
    expect(lerEntes(null)).toEqual([]);
  });

  it("descreve e classifica pelo código", () => {
    expect(["1", "53", "35", "3550308", "x"].map(tipoDoCodigo)).toEqual(["uniao", "df", "estado", "municipio", null]);
    expect(descreverEnte({ codigo: "3550308", uf: "SP" })).toBe("Município · SP");
    expect(descreverEnte({ codigo: "3550308", uf: null })).toBe("Município");
    expect(descreverEnte({ codigo: "35", uf: "SP" })).toBe("Estado");
    expect(descreverEnte({ codigo: "53", uf: "DF" })).toBe("Distrito Federal");
    expect(descreverEnte({ codigo: "1", uf: null })).toBe("União");
  });
});

describe("busca de órgãos", () => {
  const bruto = {
    versao: 1,
    tipo: "orgaos",
    colunas: ["cnpj", "nome", "ente", "esfera", "processos", "contratos"],
    orgaos: [
      ["71480560000101", "SERVICO AUTONOMO DE AGUA E ESGOTO DE SOROCABA", "3552205", "M", 10, 4],
      ["46634044000174", "MUNICIPIO DE SOROCABA", "3552205", "M", 50, 30],
      ["11111111000111", "SECRETARIA DA ADMINISTRACAO E ASSUNTOS ESTRATEGICOS", "35", "E", 1, 0],
      ["00394460000141", "MINISTERIO DA FAZENDA", "1", "F", 5, 5],
      ["22222222000122", null, null, null, 1, 0],
      ["123", "CNPJ INVÁLIDO", null, null, 1, 0],
    ],
  };
  const entes: EnteBusca[] = [
    { codigo: "3552205", nome: "Sorocaba", uf: "SP", esfera: "M", populacao: 720_000 },
    { codigo: "35", nome: "São Paulo", uf: "SP", esfera: "E", populacao: 46_000_000 },
    { codigo: "1", nome: "União", uf: null, esfera: "F", populacao: null },
  ];
  const orgaos = lerOrgaos(bruto, entes);

  it("lê o orgaos.json pelas colunas, com o ente do cadastro, e descarta CNPJ inválido", () => {
    expect(orgaos.map((o) => o.cnpj)).toEqual([
      "71480560000101",
      "46634044000174",
      "11111111000111",
      "00394460000141",
      "22222222000122",
    ]);
    expect(orgaos[0]).toMatchObject({ enteNome: "Sorocaba", uf: "SP", publicacoes: 14, sigla: "saaes" });
    expect(orgaos[4]?.nome).toBe("22222222000122");
    expect(lerOrgaos({ versao: 2 }, entes)).toEqual([]);
    expect(lerOrgaos(null, entes)).toEqual([]);
  });

  it("acha os Correios, o exemplo do campo de busca, pelo nome publicado no PNCP", () => {
    const correios = lerOrgaos(
      {
        versao: 1,
        tipo: "orgaos",
        colunas: ["cnpj", "nome", "ente", "esfera", "processos", "contratos"],
        orgaos: [["34028316000103", "EMPRESA BRASILEIRA DE CORREIOS E TELEGRAFOS", "1", "F", 121, 0]],
      },
      entes,
    );
    expect(buscarOrgaos("Correios", correios).map((o) => o.cnpj)).toEqual(["34028316000103"]);
  });

  it("acha pela sigla, pelo nome, pelo município e pelo CNPJ", () => {
    expect(buscarOrgaos("SAAE Sorocaba", orgaos).map((o) => o.cnpj)).toEqual(["71480560000101"]);
    expect(buscarOrgaos("saae", orgaos).map((o) => o.cnpj)).toEqual(["71480560000101", "11111111000111"]);
    expect(buscarOrgaos("sorocaba", orgaos).map((o) => o.cnpj)).toEqual(["46634044000174", "71480560000101"]);
    expect(buscarOrgaos("municipio sor", orgaos)[0]?.cnpj).toBe("46634044000174");
    expect(buscarOrgaos("46.634.044", orgaos).map((o) => o.cnpj)).toEqual(["46634044000174"]);
    expect(buscarOrgaos("aa", orgaos)).toEqual([]); // sigla só com três letras ou mais
    expect(buscarOrgaos(" ", orgaos)).toEqual([]);
    expect(buscarOrgaos("e", orgaos, 1)).toHaveLength(1);
  });

  it("descreve o órgão pela esfera e pelo ente", () => {
    expect(siglaDoNome("Serviço Autônomo de Água e Esgoto")).toBe("saae");
    expect(orgaos.map(descreverOrgao)).toEqual([
      "Órgão municipal · Sorocaba (SP)",
      "Órgão municipal · Sorocaba (SP)",
      "Órgão estadual · SP",
      "Órgão federal",
      "Órgão",
    ]);
    expect(urlsPainel.orgaos()).toMatch(/\/orgaos\.json$/);
  });
});

describe("arquivos dos painéis", () => {
  it("só monta caminhos com código e UF válidos", () => {
    expect(urlsPainel.contratacoesEnte("3550308")).toMatch(/\/contratacoes\/ente\/503\.json\.gz$/);
    expect(urlsPainel.contratacoesEnte("35")).toMatch(/\/contratacoes\/ente\/35\.json\.gz$/);
    expect(urlsPainel.contratacoesOrgao("97229181000164")).toMatch(/\/contratacoes\/orgao\/181\.json\.gz$/);
    expect(() => urlsPainel.contratacoesOrgao("9722918100016")).toThrow(ErroFeed);
    expect(urlsPainel.conformidadeUf("SP")).toMatch(/\/conformidade\/uf\/SP\.json$/);
    expect(() => codigoSeguro("../x")).toThrow(ErroFeed);
    expect(() => urlsPainel.conformidadeUf("sp/../")).toThrow(ErroFeed);
    expect(urlsPainel.indice()).toMatch(/\/indice\.json$/);
    expect(urlsPainel.entes()).toMatch(/\/entes\.json$/);
  });

  it("confere versão e tipo", () => {
    expect(conferir({ versao: 1, tipo: "contratacoes-ente" }, "contratacoes-ente", "u")).toBeTruthy();
    expect(() => conferir({ versao: 2, tipo: "contratacoes-ente" }, "contratacoes-ente", "u")).toThrow(/versão/);
    expect(() => conferir({ versao: 1, tipo: "x" }, "contratacoes-ente", "u")).toThrow(/tipo/);
    expect(() => conferir("x", "contratacoes-ente", "u")).toThrow(/inesperado/);
  });
});

describe("contratações por grupo de entes e de órgãos", () => {
  afterEach(() => vi.unstubAllGlobals());

  const ente = { versao: 1, tipo: "contratacoes-ente", ente: { codigo: "4319604" } };
  const orgao = { versao: 1, tipo: "contratacoes-orgao", orgao: { cnpj: "97229181000164" } };
  const arquivos: Record<string, unknown> = {
    "/contratacoes/ente/196.json.gz": { versao: 1, tipo: "contratacoes-entes", entes: { "4319604": ente } },
    "/contratacoes/orgao/181.json.gz": { versao: 1, tipo: "contratacoes-orgaos", orgaos: { "97229181000164": orgao } },
    "/contratacoes/ente/3550308.json": { ...ente, ente: { codigo: "3550308" } },
  };
  const responder = vi.fn(async (url: string) => {
    const chave = Object.keys(arquivos).find((k) => url.endsWith(k));
    if (!chave) return new Response("", { status: 404 });
    const corpo = JSON.stringify(arquivos[chave]);
    return new Response(chave.endsWith(".gz") ? gzipSync(corpo) : corpo, { headers: { "content-type": "application/json" } });
  });

  it("acha o ente e o órgão no arquivo do grupo (3º a 5º dígitos do código, 6º a 8º do CNPJ)", async () => {
    expect([grupoDoEnte("4319604"), grupoDoEnte("43"), grupoDoEnte("1")]).toEqual(["196", "43", "1"]);
    expect(grupoDoOrgao("97229181000164")).toBe("181");
    vi.stubGlobal("fetch", responder);
    expect((await carregarContratacoesEnte("4319604"))?.tipo).toBe("contratacoes-ente");
    expect((await carregarContratacoesOrgao("97229181000164"))?.tipo).toBe("contratacoes-orgao");
    expect(await carregarContratacoesEnte("4319699")).toBeNull();      // mesmo grupo, ente que não está nele
  });

  it("lê o arquivo de um ente só enquanto o site não tem o grupo", async () => {
    vi.stubGlobal("fetch", responder);
    expect((await carregarContratacoesEnte("3550308"))?.ente.codigo).toBe("3550308");
    expect(await carregarContratacoesOrgao("46395000000139")).toBeNull();
  });
});

describe("formato", () => {
  it("formata reais, meses, datas e CNPJ", () => {
    expect(moeda(1234.5).replace(/\s/g, " ")).toBe("R$ 1.234,50");
    expect(moeda(null)).toBe("—");
    expect(moedaCompacta(1_500_000)).toMatch(/^R\$ 1,5\s?mi/);
    expect(moedaCompacta(undefined)).toBe("—");
    expect(mesCurto("2026-03")).toBe("mar/2026");
    expect(mesCurto("2026-13")).toBe("2026-13");
    expect(dataCurta("2026-10-13")).toBe("13/10/2026");
    expect(dataCurta("2026-04-30T02:00:00+00:00")).toBe("29/04/2026");
    expect(dataCurta("lixo")).toBe("—");
    expect(dataCurta(null)).toBe("—");
    expect(cnpj("07854402000100")).toBe("07.854.402/0001-00");
    expect(cnpj("123")).toBe("123");
    expect(cnpj(null)).toBe("—");
  });

  it("arredonda o topo do eixo", () => {
    expect([0, 3, 10, 11, 180, 4_200_000].map(topoDoEixo)).toEqual([1, 5, 10, 20, 200, 5_000_000]);
    expect(topoDoEixo(7)).toBe(10);
  });
});

describe("grupo de pares", () => {
  it("monta o endereço do grupo só com um id válido", () => {
    const id = "6f1d3a52-6b0e-5c1e-9a57-4c756d656e00";
    expect(urlsPainel.conformidadePares(id)).toMatch(new RegExp(`/conformidade/pares/${id}\.json$`));
    expect(() => urlsPainel.conformidadePares("../indice")).toThrow(ErroFeed);
  });

  it("descreve a metade central do grupo", () => {
    expect(faixaCentral({ entes: 20, q1: 0.8, mediana: 0.9, q3: 1 })).toBe("entre 80,00% e 100,00%");
    expect(faixaCentral({ entes: 3, q1: 1, mediana: 1, q3: 1 })).toBe("em 100,00%");
  });
});

describe("RCL no grupo de pares", () => {
  const grupo = (rcl?: unknown) =>
    ({ id: "x", descricao: "", esfera: "municipal", faixa_populacional: "ate_5_mil", regiao: "S", entes: 30,
       abaixo_do_minimo: false, criterios: { minimo_entes: 15, receita_corrente_liquida: rcl } }) as never;

  it("diz como a RCL entrou no grupo", () => {
    const base = { exercicio: 2025, mediana_por_habitante: 4450.5, entes_com_rcl: 30 };
    expect(criterioRcl(grupo({ ...base, faixa: "acima_da_mediana" }))).toMatch(
      /^Divididos pela receita corrente líquida \(RCL\) por habitante: mediana de R\$\s4\.450,50 por habitante entre 30 entes/,
    );
    expect(criterioRcl(grupo({ ...base, faixa: null, uso: "grupo inteiro" }))).toMatch(
      /^O ente não publicou a RCL de 2025: a comparação é com o grupo inteiro/,
    );
    expect(criterioRcl(grupo("não usada: 3 ente(s)"))).toBe("Receita corrente líquida (RCL) não usada: 3 ente(s).");
    expect(criterioRcl(grupo(undefined))).toBe("A receita corrente líquida ainda não entra nos critérios.");
  });
});

describe("despesa por função no grupo de pares", () => {
  const d = { entes: 15, q1: 5500, mediana: 9000, q3: 12500 };

  it("diz de que lado da metade central o ente fica", () => {
    expect(posicaoNoGrupo(16000, d)).toBe("acima");
    expect(posicaoNoGrupo(1000, d)).toBe("abaixo");
    expect(posicaoNoGrupo(5500, d)).toBe("central");
    expect(posicaoNoGrupo(12500, d)).toBe("central");
  });

  it("escreve a metade central em reais e aponta a DCA do ente", () => {
    expect(faixaCentralEmReais(d)).toMatch(/^entre R\$\s5\.500,00 e R\$\s12\.500,00$/);
    expect(faixaCentralEmReais({ entes: 15, q1: 0, mediana: 0, q3: 0 })).toMatch(/^em R\$\s0,00$/);
    expect(urlDcaDoEnte("4319604", 2025)).toBe(
      "https://apidatalake.tesouro.gov.br/ords/siconfi/tt/dca?an_exercicio=2025&no_anexo=DCA-Anexo%20I-E&id_ente=4319604",
    );
  });
});

describe("despesa com pessoal no grupo de pares", () => {
  const limites = { alerta: 48.6, prudencial: 51.3, maximo: 54 };

  it("diz onde o percentual fica em relação aos limites do próprio RGF", () => {
    expect(faixaDoLimite(48.33, limites)).toBe("abaixo do limite de alerta");
    expect(faixaDoLimite(50, limites)).toBe("entre o limite de alerta e o prudencial");
    expect(faixaDoLimite(52, limites)).toBe("entre o limite prudencial e o máximo");
    expect(faixaDoLimite(54.01, limites)).toBe("acima do limite máximo");
    expect(faixaDoLimite(54, limites)).toBe("entre o limite prudencial e o máximo");
    expect(faixaDoLimite(40, {})).toBeNull();
  });

  it("escreve o período, a metade central em % e aponta o RGF do ente", () => {
    expect(periodoDoRgf(2, "S", 2025)).toBe("2º semestre de 2025");
    expect(periodoDoRgf(3, "Q", 2025)).toBe("3º quadrimestre de 2025");
    expect(faixaCentral({ entes: 15, q1: 43.5, mediana: 47, q3: 50.5 }, 1)).toBe("entre 43,50% e 50,50%");
    expect(urlRgfDoEnte("4319604", 2025, { percentual: 48.33, dtp: null, rcl_ajustada: null, limites,
      demonstrativo: "RGF Simplificado", periodo: 2, periodicidade: "S" })).toBe(
      "https://apidatalake.tesouro.gov.br/ords/siconfi/tt/rgf?an_exercicio=2025&in_periodicidade=S&nr_periodo=2" +
        "&co_tipo_demonstrativo=RGF%20Simplificado&no_anexo=RGF-Anexo%2001&co_poder=E&id_ente=4319604",
    );
  });
});
