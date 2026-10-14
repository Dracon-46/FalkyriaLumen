// Leitura dos feeds: arquivo inexistente vira null no servidor local (404) e no Supabase Storage (400).
import { afterEach, describe, expect, it, vi } from "vitest";
import { inexistenteNoSupabase, obterJson } from "../feeds";
import { ErroFeed } from "../validacao";

function responder(status: number, corpo: string) {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(corpo, { status })));
}

afterEach(() => vi.unstubAllGlobals());

describe("obterJson", () => {
  it("devolve o JSON quando existe", async () => {
    responder(200, '{"versao":1}');
    expect(await obterJson("/x.json")).toEqual({ versao: 1 });
  });

  it("devolve null no 404 e no 400 de inexistente do Supabase", async () => {
    responder(404, "");
    expect(await obterJson("/x.json")).toBeNull();
    responder(400, '{"statusCode":"404","error":"not_found","message":"Object not found"}');
    expect(await obterJson("/x.json")).toBeNull();
  });

  it("outros erros viram ErroFeed", async () => {
    responder(400, '{"statusCode":"400","error":"invalid"}');
    await expect(obterJson("/x.json")).rejects.toBeInstanceOf(ErroFeed);
    responder(500, "falha");
    await expect(obterJson("/x.json")).rejects.toThrow("HTTP 500");
    responder(200, "<html>");
    await expect(obterJson("/x.json")).rejects.toThrow("não é JSON");
  });

  it("sem resposta vira ErroFeed; cancelamento passa adiante", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("rede"); }));
    await expect(obterJson("/x.json")).rejects.toThrow("sem resposta");
    const abortado = Object.assign(new Error("abortado"), { name: "AbortError" });
    vi.stubGlobal("fetch", vi.fn(async () => { throw abortado; }));
    await expect(obterJson("/x.json")).rejects.toBe(abortado);
  });
});

describe("inexistenteNoSupabase", () => {
  it("só reconhece o 400 com o corpo de inexistente", async () => {
    expect(await inexistenteNoSupabase(new Response("NoSuchKey", { status: 400 }))).toBe(true);
    expect(await inexistenteNoSupabase(new Response("not_found", { status: 404 }))).toBe(false);
    expect(await inexistenteNoSupabase(new Response("outro", { status: 400 }))).toBe(false);
  });
});
