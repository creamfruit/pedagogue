import { afterEach, describe, expect, it, vi } from "vitest";

async function policyText() {
  const { privacyView } = await import("../src/views/legal.js");
  const outlet = document.createElement("main");
  privacyView(outlet);
  return outlet.textContent;
}

describe("privacy policy", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  it("says there is no crash reporting when no DSN is set", async () => {
    vi.stubEnv("VITE_SENTRY_DSN", "");
    const text = await policyText();
    expect(text).toContain("we do not use analytics or crash-reporting services");
    expect(text).not.toContain("Sentry");
  });

  it("says what keyboard practice keeps and what it does not", async () => {
    vi.stubEnv("VITE_SENTRY_DSN", "");
    const text = await policyText();
    expect(text).toContain("keyboard practice we keep each run's scores");
    expect(text).toContain("are not kept");
  });

  it("names Sentry and what it receives when error reporting is on", async () => {
    vi.stubEnv("VITE_SENTRY_DSN", "https://key@o0.ingest.sentry.io/1");
    const text = await policyText();
    expect(text).toContain("an error report goes to Sentry");
    expect(text).not.toContain("crash-reporting services");
  });
});
