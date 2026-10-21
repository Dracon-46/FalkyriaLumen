import { describe, expect, it } from "vitest";
import { parte } from "../contratacao";
import { cpfValido, mascararCpfs } from "../cpf";

describe("máscara de CPF no que vem direto do PNCP", () => {
  it("mascara o CPF no nome do MEI, colado ou não", () => {
    expect(mascararCpfs("NYARA OLIVEIRA CAVALCANTE 01987103300", true)).toBe("NYARA OLIVEIRA CAVALCANTE ***.871.033-**");
    expect(mascararCpfs("JACKSON GOSSMANN DA SILVA03863498003", true)).toBe("JACKSON GOSSMANN DA SILVA***.634.980-**");
    expect(mascararCpfs("EMPRESA X 12345678000190", true)).toBe("EMPRESA X 12345678000190");
    expect(mascararCpfs(null, true)).toBeNull();
    expect(parte("PJ", "37719249000161", "NYARA OLIVEIRA CAVALCANTE 01987103300").nome)
      .toBe("NYARA OLIVEIRA CAVALCANTE ***.871.033-**");
  });

  it("no objeto, só o que tem forma de CPF", () => {
    expect(mascararCpfs("por intermédio de NELSON SARAIVA ALVES 32620487803, emenda 20253666000"))
      .toBe("por intermédio de NELSON SARAIVA ALVES ***.204.878-**, emenda 20253666000");
    expect(mascararCpfs("CPF 123.456.789-00.")).toBe("CPF ***.456.789-**.");
    expect(cpfValido("32620487803")).toBe(true);
    expect(cpfValido("11111111111")).toBe(false);
  });
});
