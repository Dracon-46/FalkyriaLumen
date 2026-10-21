/**
 * Máscara de CPF em texto livre, para o que o portal lê direto das fontes no navegador (o PNCP no modal da
 * contratação e na comparação de preço). É a mesma regra de `lumen_canonico.documentos.mascarar_cpfs_no_texto`,
 * que mascara os textos publicados pelo Lumen (DOC-08, seção 5; ADR-043): a razão social do MEI leva o CPF do
 * titular, e o objeto de um contrato às vezes cita o CPF de alguém.
 */

/** No texto: 11 dígitos soltos, com ou sem a pontuação do CPF, fora de um número maior. */
const NO_TEXTO = /(?<![\w./-])(\d{3})\.?(\d{3})\.?(\d{3})-?(\d{2})(?![\w]|[./-]\d)/g;
/** No nome: também colados a letras ou depois de hífen ("SILVA03863498003"). */
const NO_NOME = /(?<![\d.])(\d{3})\.?(\d{3})\.?(\d{3})-?(\d{2})(?!\d|[./-]\d)/g;

/** CPF de 11 dígitos com os dois dígitos verificadores corretos (um dígito repetido não vale). */
export function cpfValido(digitos: string): boolean {
  if (!/^\d{11}$/.test(digitos) || /^(\d)\1{10}$/.test(digitos)) return false;
  for (const tamanho of [9, 10]) {
    let soma = 0;
    for (let i = 0; i < tamanho; i++) soma += Number(digitos[i]) * (tamanho + 1 - i);
    if (((soma * 10) % 11) % 10 !== Number(digitos[tamanho])) return false;
  }
  return true;
}

/**
 * `NOME 12345678909` → `NOME ***.456.789-**`. Com `todos` (nomes), toda sequência de 11 dígitos; sem ele (objeto,
 * descrição), só a que tem o dígito verificador do CPF ou a pontuação dele.
 */
export function mascararCpfs(texto: string | null, todos = false): string | null {
  if (!texto) return texto;
  return texto.replace(todos ? NO_NOME : NO_TEXTO, (achado, a: string, b: string, c: string, d: string) =>
    todos || cpfValido(a + b + c + d) || /^\d{3}\.\d{3}\.\d{3}-\d{2}$/.test(achado) ? `***.${b}.${c}-**` : achado);
}
