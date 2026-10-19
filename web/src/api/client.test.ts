import { describe, expect, it } from "vitest";

import { ApiError, OFFLINE_STATUS, createClient } from "./client";

interface Seen {
  url?: string | undefined;
  init?: RequestInit | undefined;
}

function fakeFetch(status: number, body: unknown, seen: Seen = {}) {
  return (async (url: string, init?: RequestInit) => {
    seen.url = url;
    seen.init = init;
    return new Response(status === 204 ? null : JSON.stringify(body), { status });
  }) as typeof fetch;
}

describe("the API client", () => {
  it("sends JSON to the documented route and returns the parsed answer", async () => {
    const seen: Seen = {};
    const run = await createClient(fakeFetch(200, { tick: 5 }, seen)).step("a b", 5);
    expect(run).toEqual({ tick: 5 });
    expect(seen.url).toBe("/api/runs/a%20b/step");
    expect(seen.init?.method).toBe("POST");
    expect(seen.init?.body).toBe(JSON.stringify({ ticks: 5 }));
  });

  it("returns nothing for 204", async () => {
    await expect(createClient(fakeFetch(204, null)).deleteRun("x")).resolves.toBeUndefined();
  });

  it("carries the server's reason on an error", async () => {
    const client = createClient(fakeFetch(409, { detail: "run x is completed; it can't become running" }));
    const error = await client.resume("x").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 409, detail: "run x is completed; it can't become running" });
  });

  it("turns FastAPI's validation list into one readable line", async () => {
    const body = { detail: [{ loc: ["body", "ticks"], msg: "Input should be greater than or equal to 1" }] };
    const error = await createClient(fakeFetch(422, body)).step("x", 0).catch((e: unknown) => e);
    expect((error as ApiError).detail).toBe("ticks: Input should be greater than or equal to 1");
  });

  it("says what to do when the server isn't running", async () => {
    const offline = (async () => {
      throw new TypeError("Failed to fetch");
    }) as typeof fetch;
    const error = (await createClient(offline).health().catch((e: unknown) => e)) as ApiError;
    expect(error.status).toBe(OFFLINE_STATUS);
    expect(error.detail).toContain("uv run genesis serve");
  });
});
