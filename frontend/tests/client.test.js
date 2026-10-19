import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../src/api/client.js";

function reply(status, body, headers = {}) {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json", ...headers } });
}

describe("api client", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("shows the server's message when sign-in is rate limited", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => reply(429, { detail: "Too many sign-in attempts. Wait a little and try again." }, { "retry-after": "42" })));
    const error = await api.login("pianist@example.com", "wrong").catch((caught) => caught);
    expect(error.status).toBe(429);
    expect(error.detail).toBe("Too many sign-in attempts. Wait a little and try again.");
    expect(error.isAuth).toBe(false);
  });

  it("shows the quota message when the upload space is full", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => reply(413, { detail: "you have used your 500 MB of upload space" })));
    const file = new File([new Uint8Array([37, 80, 68, 70])], "score.pdf", { type: "application/pdf" });
    const error = await api.submitScore("entry", file).catch((caught) => caught);
    expect(error.status).toBe(413);
    expect(error.detail).toContain("upload space");
  });
});
