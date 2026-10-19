/**
 * Tudo sobre uma contratação, para o modal das Contratações (ADR-035): o processo (ou o contrato) como o PNCP o
 * publica, os itens com o preço unitário e o vencedor, os termos aditivos e os documentos.
 *
 * Os dados vêm da API pública do PNCP, pedidos pelo navegador quando o modal abre (a API libera a leitura,
 * CORS). Nada é copiado para o Lumen. Fornecedor pessoa física aparece sem nome nem documento (RNF-19), como
 * nos painéis.
 */

import { ErroFeed } from "./validacao";
import { API_PNCP, lerChave, type PublicacaoPncp } from "./documentos";

/** A API de consulta do PNCP, que tem o detalhe do processo. */
export const API_CONSULTA = "https://pncp.gov.br/api/consulta/v1";

/** Pessoa jurídica com CNPJ e razão social; pessoa física ou estrangeira, sem identificação. */
export interface Parte {
  pj: boolean;
  cnpj: string | null;
  nome: string | null;
}

/** Um processo de contratação (compra, no PNCP). */
export interface Processo {
  chave: string;
  objeto: string | null;
  modalidade: string | null;
  modoDisputa: string | null;
  amparoLegal: { nome: string; descricao: string | null } | null;
  numero: string | null;
  processo: string | null;
  situacao: string | null;
  srp: boolean | null;
  valorEstimado: number | null;
  valorHomologado: number | null;
  publicadoEm: string | null;
  aberturaPropostas: string | null;
  encerramentoPropostas: string | null;
  orgao: { cnpj: string; nome: string | null };
  unidade: { nome: string | null; municipio: string | null; uf: string | null; ibge: string | null; uasg: string | null };
  linkSistemaOrigem: string | null;
  linkProcessoEletronico: string | null;
  informacaoComplementar: string | null;
}

/** Um item do processo, com o vencedor quando já há resultado. */
export interface ItemProcesso {
  numero: number;
  descricao: string;
  tipo: string | null;           // Material ou Serviço
  material: boolean | null;      // M ou S no PNCP; null se não informado
  catalogo: string | null;       // código do item no catálogo do Compras.gov.br (CATMAT ou CATSER), se o órgão informou
  quantidade: number | null;
  unidade: string | null;
  valorUnitario: number | null;
  valorTotal: number | null;
  situacao: string | null;
  temResultado: boolean;
}

/** O resultado (homologação) de um item: o fornecedor e o valor. */
export interface ResultadoItem {
  fornecedor: Parte;
  quantidade: number | null;
  valorUnitario: number | null;
  valorTotal: number | null;
  situacao: string | null;
  data: string | null;           // AAAA-MM-DD do resultado
}

/** Um contrato (ou empenho) publicado. */
export interface Contrato {
  chave: string;
  objeto: string | null;
  tipo: string | null;
  categoria: string | null;
  numero: string | null;
  processo: string | null;
  assinatura: string | null;
  vigenciaInicio: string | null;
  vigenciaFim: string | null;
  valorInicial: number | null;
  valorGlobal: number | null;
  valorAcumulado: number | null;
  fornecedor: Parte;
  chaveProcesso: string | null;
  orgao: { cnpj: string; nome: string | null };
  unidade: { nome: string | null; municipio: string | null; uf: string | null; ibge: string | null; uasg: string | null };
  informacaoComplementar: string | null;
}

/** Um termo aditivo (ou de rescisão, apostilamento) do contrato. */
export interface Termo {
  tipo: string | null;
  numero: string | null;
  assinatura: string | null;
  objeto: string | null;
  valorAcrescido: number | null;
  prazoAditado: number | null;
}

/** Um objeto da resposta da API, ainda sem conferir. */
type Bruto = Record<string, unknown>;
const texto = (v: unknown): string | null => (typeof v === "string" && v.trim() ? v.trim() : null);
const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
const obj = (v: unknown): Bruto => (v && typeof v === "object" ? (v as Bruto) : {});

/** A parte contratada: pessoa física e estrangeira sem nome nem documento. */
export function parte(tipoPessoa: unknown, ni: unknown, nome: unknown): Parte {
  const pj = tipoPessoa === "PJ";
  return { pj, cnpj: pj ? texto(ni) : null, nome: pj ? texto(nome) : null };
}

/** A unidade compradora. */
function unidade(u: Bruto) {
  return { nome: texto(u.nomeUnidade), municipio: texto(u.municipioNome), uf: texto(u.ufSigla), ibge: texto(u.codigoIbge),
           uasg: texto(u.codigoUnidade) };
}

/** O código do item no catálogo do Compras.gov.br (o único que a pesquisa de preços entende), ou `null`. */
function codigoCatalogo(x: Bruto): string | null {
  const cat = obj(x.catalogo);
  const doCompras = cat.id === 1 || /compras\.gov/i.test(texto(cat.nome) ?? "");
  const codigo = texto(x.catalogoCodigoItem) ?? (num(x.catalogoCodigoItem) !== null ? String(x.catalogoCodigoItem) : null);
  return doCompras && codigo && /^\d{1,9}$/.test(codigo) ? codigo : null;
}

/** O processo como o Lumen mostra, a partir da resposta da API de consulta. */
export function lerProcesso(chave: string, b: Bruto): Processo {
  const amparo = obj(b.amparoLegal);
  const orgao = obj(b.orgaoEntidade);
  return {
    chave, objeto: texto(b.objetoCompra), modalidade: texto(b.modalidadeNome), modoDisputa: texto(b.modoDisputaNome),
    amparoLegal: texto(amparo.nome) ? { nome: texto(amparo.nome)!, descricao: texto(amparo.descricao) } : null,
    numero: texto(b.numeroCompra), processo: texto(b.processo), situacao: texto(b.situacaoCompraNome),
    srp: typeof b.srp === "boolean" ? b.srp : null, valorEstimado: num(b.valorTotalEstimado),
    valorHomologado: num(b.valorTotalHomologado), publicadoEm: texto(b.dataPublicacaoPncp),
    aberturaPropostas: texto(b.dataAberturaProposta), encerramentoPropostas: texto(b.dataEncerramentoProposta),
    orgao: { cnpj: texto(orgao.cnpj) ?? chave.slice(0, 14), nome: texto(orgao.razaoSocial) },
    unidade: unidade(obj(b.unidadeOrgao)), linkSistemaOrigem: texto(b.linkSistemaOrigem),
    linkProcessoEletronico: texto(b.linkProcessoEletronico), informacaoComplementar: texto(b.informacaoComplementar),
  };
}

/** Os itens do processo, a partir da resposta da API. */
export function lerItens(bruto: unknown): ItemProcesso[] {
  if (!Array.isArray(bruto)) return [];
  return bruto.map((x) => obj(x)).map((x) => ({
    numero: num(x.numeroItem) ?? 0, descricao: texto(x.descricao) ?? "—", tipo: texto(x.materialOuServicoNome),
    material: x.materialOuServico === "M" ? true : x.materialOuServico === "S" ? false : null, catalogo: codigoCatalogo(x),
    quantidade: num(x.quantidade), unidade: texto(x.unidadeMedida), valorUnitario: num(x.valorUnitarioEstimado),
    valorTotal: num(x.valorTotal), situacao: texto(x.situacaoCompraItemNome), temResultado: x.temResultado === true,
  }));
}

/** Os resultados de um item. */
export function lerResultados(bruto: unknown): ResultadoItem[] {
  if (!Array.isArray(bruto)) return [];
  return bruto.map((x) => obj(x)).map((x) => ({
    fornecedor: parte(x.tipoPessoa, x.niFornecedor, x.nomeRazaoSocialFornecedor),
    quantidade: num(x.quantidadeHomologada), valorUnitario: num(x.valorUnitarioHomologado),
    valorTotal: num(x.valorTotalHomologado), situacao: texto(x.situacaoCompraItemResultadoNome),
    data: texto(x.dataResultado)?.slice(0, 10) ?? null,
  }));
}

/** O contrato como o Lumen mostra, a partir da resposta da API. */
export function lerContrato(chave: string, b: Bruto): Contrato {
  const orgao = obj(b.orgaoEntidade);
  const chaveProcesso = texto(b.numeroControlePncpCompra);
  return {
    chave, objeto: texto(b.objetoContrato), tipo: texto(obj(b.tipoContrato).nome), categoria: texto(obj(b.categoriaProcesso).nome),
    numero: texto(b.numeroContratoEmpenho), processo: texto(b.processo), assinatura: texto(b.dataAssinatura),
    vigenciaInicio: texto(b.dataVigenciaInicio), vigenciaFim: texto(b.dataVigenciaFim),
    valorInicial: num(b.valorInicial), valorGlobal: num(b.valorGlobal), valorAcumulado: num(b.valorAcumulado),
    fornecedor: parte(b.tipoPessoa, b.niFornecedor, b.nomeRazaoSocialFornecedor),
    chaveProcesso: chaveProcesso && lerChave(chaveProcesso) ? chaveProcesso : null,
    orgao: { cnpj: texto(orgao.cnpj) ?? chave.slice(0, 14), nome: texto(orgao.razaoSocial) },
    unidade: unidade(obj(b.unidadeOrgao)), informacaoComplementar: texto(b.informacaoComplementar),
  };
}

/** Os termos do contrato, a partir da resposta da API. */
export function lerTermos(bruto: unknown): Termo[] {
  if (!Array.isArray(bruto)) return [];
  return bruto.map((x) => obj(x)).map((x) => ({
    tipo: texto(x.tipoTermoContratoNome), numero: texto(x.numeroTermoContrato), assinatura: texto(x.dataAssinatura),
    objeto: texto(x.objetoTermoContrato), valorAcrescido: num(x.valorAcrescido), prazoAditado: num(x.prazoAditadoDias),
  }));
}

/** GET na API do PNCP: JSON, `null` quando não há conteúdo (204 ou 404). */
async function pedir(url: string, sinal?: AbortSignal): Promise<unknown> {
  let r: Response;
  try {
    r = await fetch(url, { signal: sinal, headers: { Accept: "application/json" } });
  } catch (erro) {
    if ((erro as Error).name === "AbortError") throw erro;
    throw new ErroFeed(`sem resposta do PNCP (${url})`);
  }
  if (r.status === 204 || r.status === 404) return null;
  if (!r.ok) throw new ErroFeed(`PNCP respondeu ${r.status}`);
  return r.json();
}

/** O trecho do endereço da publicação na API. */
function caminho(p: PublicacaoPncp): string {
  return `orgaos/${p.cnpj}/${p.tipo === "compra" ? "compras" : "contratos"}/${p.ano}/${p.sequencial}`;
}

/** O processo da chave; `null` se o PNCP não o tem. */
export async function carregarProcesso(chave: string, sinal?: AbortSignal): Promise<Processo | null> {
  const p = lerChave(chave);
  if (!p || p.tipo !== "compra") return null;
  const b = await pedir(`${API_CONSULTA}/${caminho(p)}`, sinal);
  return b ? lerProcesso(chave, obj(b)) : null;
}

/** Os itens do processo (até 500, em páginas de 50). */
export async function carregarItens(chave: string, sinal?: AbortSignal): Promise<ItemProcesso[]> {
  const p = lerChave(chave);
  if (!p || p.tipo !== "compra") return [];
  const saida: ItemProcesso[] = [];
  for (let pagina = 1; pagina <= 10; pagina++) {
    const lote = lerItens(await pedir(`${API_PNCP}/${caminho(p)}/itens?pagina=${pagina}&tamanhoPagina=50`, sinal));
    saida.push(...lote);
    if (lote.length < 50) break;
  }
  return saida;
}

/** O resultado de um item do processo. */
export async function carregarResultados(chave: string, item: number, sinal?: AbortSignal): Promise<ResultadoItem[]> {
  const p = lerChave(chave);
  if (!p || p.tipo !== "compra") return [];
  return lerResultados(await pedir(`${API_PNCP}/${caminho(p)}/itens/${item}/resultados`, sinal));
}

/** O contrato da chave; `null` se o PNCP não o tem. */
export async function carregarContrato(chave: string, sinal?: AbortSignal): Promise<Contrato | null> {
  const p = lerChave(chave);
  if (!p || p.tipo !== "contrato") return null;
  const b = await pedir(`${API_PNCP}/${caminho(p)}`, sinal);
  return b ? lerContrato(chave, obj(b)) : null;
}

/** Os termos aditivos do contrato. */
export async function carregarTermos(chave: string, sinal?: AbortSignal): Promise<Termo[]> {
  const p = lerChave(chave);
  if (!p || p.tipo !== "contrato") return [];
  return lerTermos(await pedir(`${API_PNCP}/${caminho(p)}/termos`, sinal));
}
