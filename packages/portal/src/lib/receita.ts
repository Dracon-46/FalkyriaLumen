/**
 * O fornecedor na base pública de CNPJ da Receita Federal (ADR-043): cadastro, Simples e quadro societário, do
 * arquivo `cnpj/<3 primeiros dígitos>.json.gz` que os painéis publicam (comprimido, com os códigos da Receita) e
 * da tabela dos nomes dos códigos (`cnpj/tabelas.json`). Só as empresas fornecedoras nos contratos do painel estão
 * lá. Endereço de rua, telefone, e-mail e o CPF dos sócios ficam de fora na origem.
 */

import { obterJsonComprimido } from "./comprimido";
import { memorizar, obterJson } from "./feeds";
import { BASE_PAINEL, conferir } from "./paineis";
import { ErroFeed } from "./validacao";

/** Um código da Receita com o nome dele (CNAE, natureza jurídica, motivo, país). */
export interface CodigoNome {
  codigo: string;
  nome: string | null;
}

/** Um sócio: pessoa jurídica (com CNPJ), pessoa física (só o nome) ou estrangeiro (com o país). */
export interface Socio {
  tipo: "PJ" | "PF" | "estrangeiro" | string;
  nome: string;
  qualificacao: string | null;
  desde: string | null;
  cnpj?: string;
  pais?: string;
}

/** A empresa na Receita, como a tela a mostra. */
export interface EmpresaReceita {
  cnpj: string;
  razao_social: string | null;
  natureza: CodigoNome | null;
  porte: string | null;
  capital_social: number | null;
  matriz: boolean | null;
  nome_fantasia: string | null;
  situacao: string | null;
  data_situacao: string | null;
  motivo: CodigoNome | null;
  inicio_atividade: string | null;
  cnae_principal: CodigoNome | null;
  cnaes_secundarios: CodigoNome[];
  municipio: string | null;
  uf: string | null;
  exterior: { cidade: string | null; pais: CodigoNome | null } | null;
  situacao_especial: string | null;
  data_situacao_especial: string | null;
  simples: { simples: boolean; simples_desde: string | null; simples_ate: string | null; mei: boolean;
             mei_desde: string | null; mei_ate: string | null } | null;
  socios: Socio[];
}

/** Uma empresa como vem no arquivo do prefixo: os códigos da Receita, sem os campos vazios. */
export interface EmpresaBruta {
  razao_social?: string;
  natureza?: string;
  porte?: string;
  capital_social?: number;
  matriz?: boolean;
  nome_fantasia?: string;
  situacao?: string;
  data_situacao?: string;
  motivo?: string;
  inicio_atividade?: string;
  cnae_principal?: string;
  cnaes_secundarios?: string[];
  municipio?: string;
  uf?: string;
  cidade_exterior?: string;
  pais?: string;
  situacao_especial?: string;
  data_situacao_especial?: string;
  simples?: Partial<NonNullable<EmpresaReceita["simples"]>>;
  socios?: Socio[];
}

/** Arquivo `cnpj/<prefixo>.json.gz`: o mês da base e as empresas do prefixo. */
export interface ArquivoCnpj {
  versao: 1;
  tipo: "cnpj";
  gerado_em: string;
  mes: string | null;
  fonte: string | null;
  empresas: Record<string, EmpresaBruta>;
}

/** As tabelas dos nomes dos códigos (CNAE, natureza, qualificação, motivo, município, país, situação, porte). */
export type TabelasCnpj = Record<string, Record<string, string>>;

/** Endereço do arquivo do prefixo do CNPJ. */
export function urlCnpj(cnpj: string): string {
  if (!/^\d{14}$/.test(cnpj)) throw new ErroFeed(`CNPJ inválido: ${cnpj}`);
  return `${BASE_PAINEL}/cnpj/${cnpj.slice(0, 3)}.json.gz`;
}

const tabelasLidas = new Map<string, Promise<TabelasCnpj>>();

/** As tabelas dos códigos, lidas uma vez por visita. */
function carregarTabelas(sinal?: AbortSignal): Promise<TabelasCnpj> {
  const url = `${BASE_PAINEL}/cnpj/tabelas.json`;
  return memorizar(tabelasLidas, url, async () => {
    const bruto = await obterJson(url, { sinal });
    return bruto === null ? {} : conferir<{ tabelas: TabelasCnpj }>(bruto, "cnpj-tabelas", url).tabelas ?? {};
  });
}

/** A empresa do arquivo com os nomes no lugar dos códigos (o código fica ao lado). */
export function resolver(cnpj: string, e: EmpresaBruta, t: TabelasCnpj): EmpresaReceita {
  const nome = (tabela: string, codigo: string | undefined): CodigoNome | null =>
    codigo ? { codigo, nome: t[tabela]?.[codigo] ?? null } : null;
  const s = e.simples;
  return {
    cnpj,
    razao_social: e.razao_social ?? null,
    natureza: nome("natureza", e.natureza),
    porte: e.porte ? t.porte?.[e.porte] ?? e.porte : null,
    capital_social: e.capital_social ?? null,
    matriz: e.matriz ?? null,
    nome_fantasia: e.nome_fantasia ?? null,
    situacao: e.situacao ? t.situacao?.[e.situacao] ?? e.situacao : null,
    data_situacao: e.data_situacao ?? null,
    motivo: nome("motivo", e.motivo),
    inicio_atividade: e.inicio_atividade ?? null,
    cnae_principal: nome("cnae", e.cnae_principal),
    cnaes_secundarios: (e.cnaes_secundarios ?? []).map((c) => nome("cnae", c)!),
    municipio: e.municipio ? t.municipio?.[e.municipio] ?? null : null,
    uf: e.uf ?? null,
    exterior: e.cidade_exterior ? { cidade: e.cidade_exterior, pais: nome("pais", e.pais) } : null,
    situacao_especial: e.situacao_especial ?? null,
    data_situacao_especial: e.data_situacao_especial ?? null,
    simples: s ? { simples: !!s.simples, simples_desde: s.simples_desde ?? null, simples_ate: s.simples_ate ?? null,
                   mei: !!s.mei, mei_desde: s.mei_desde ?? null, mei_ate: s.mei_ate ?? null } : null,
    socios: (e.socios ?? []).map((so) => ({
      ...so,
      qualificacao: so.qualificacao ? t.qualificacao?.[so.qualificacao] ?? so.qualificacao : null,
      desde: so.desde ?? null,
      ...(so.pais ? { pais: t.pais?.[so.pais] ?? so.pais } : {}),
    })),
  };
}

/** A empresa e o mês da base; `null` quando a base não foi publicada ou não tem o CNPJ. */
export async function carregarEmpresa(cnpj: string, sinal?: AbortSignal):
  Promise<{ empresa: EmpresaReceita; mes: string | null } | null> {
  const url = urlCnpj(cnpj);
  const [bruto, tabelas] = await Promise.all([obterJsonComprimido(url, sinal), carregarTabelas(sinal)]);
  if (bruto === null) return null;
  const arquivo = conferir<ArquivoCnpj>(bruto, "cnpj", url);
  const empresa = arquivo.empresas?.[cnpj];
  return empresa ? { empresa: resolver(cnpj, empresa, tabelas), mes: arquivo.mes } : null;
}

/** "2026-10" → "outubro de 2026". */
export function mesPorExtenso(mes: string | null): string {
  const m = /^(\d{4})-(\d{2})$/.exec(mes ?? "");
  if (!m) return "";
  const nomes = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
                 "novembro", "dezembro"];
  return `${nomes[Number(m[2]) - 1]} de ${m[1]}`;
}

/** Anos completos de `desde` (AAAA-MM-DD) até `hoje`. */
export function anosDesde(desde: string | null, hoje: Date = new Date()): number | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(desde ?? "");
  if (!m) return null;
  const [a, me, d] = [Number(m[1]), Number(m[2]), Number(m[3])];
  let anos = hoje.getFullYear() - a;
  if (hoje.getMonth() + 1 < me || (hoje.getMonth() + 1 === me && hoje.getDate() < d)) anos -= 1;
  return Math.max(0, anos);
}
