import { describe, expect, it } from "vitest";
import { rotuloExecucao } from "../operacao";

describe("painel operacional", () => {
  it("põe o resultado da execução em português", () => {
    expect(rotuloExecucao("completed", "success")).toBe("concluída");
    expect(rotuloExecucao("completed", "timed_out")).toBe("passou do prazo da máquina");
    expect(rotuloExecucao("in_progress", null)).toBe("em andamento");
    expect(rotuloExecucao("queued", "")).toBe("na fila");
    expect(rotuloExecucao(null, null)).toBe("—");
  });
});
