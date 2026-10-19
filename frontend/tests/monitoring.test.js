import { describe, expect, it, vi } from "vitest";
import { identifyUser, scrubBreadcrumb, scrubEvent, startMonitoring } from "../src/lib/monitoring.js";

describe("error reporting", () => {
  it("stays off without a DSN and never loads the SDK", async () => {
    const load = vi.fn();
    expect(await startMonitoring({ dsn: "", load })).toBe(false);
    expect(load).not.toHaveBeenCalled();
  });

  it("starts with personal data off and scrubbers installed", async () => {
    const sdk = { init: vi.fn(), setUser: vi.fn() };
    identifyUser("user-7");
    expect(await startMonitoring({ dsn: "https://key@o0.ingest.sentry.io/1", load: async () => sdk })).toBe(true);
    const options = sdk.init.mock.calls[0][0];
    expect(options.sendDefaultPii).toBe(false);
    expect(options.beforeSend).toBe(scrubEvent);
    expect(options.beforeBreadcrumb).toBe(scrubBreadcrumb);
    expect(sdk.setUser).toHaveBeenLastCalledWith({ id: "user-7" });
    identifyUser(null);
    expect(sdk.setUser).toHaveBeenLastCalledWith(null);
  });

  it("strips everything but the user id, and scrubs emails, tokens and query strings", () => {
    const event = scrubEvent({
      user: { id: 7, email: "pianist@example.com", ip_address: "203.0.113.9" },
      request: {
        url: "https://pedagogue.app/login?email=pianist@example.com",
        query_string: "email=pianist@example.com",
        headers: { Authorization: "Bearer abc.def" },
        cookies: { session: "1" },
      },
      exception: { values: [{ type: "ApiError", value: "no account for pianist@example.com" }] },
      extra: { password: "hunter22", note: "sent Bearer eyJhbGciOi.payload.sig" },
      breadcrumbs: [{ category: "navigation", data: { from: "/login?email=pianist@example.com", to: "/" } }],
    });
    const text = JSON.stringify(event);
    expect(event.user).toEqual({ id: "7" });
    expect(event.request).toEqual({ url: "https://pedagogue.app/login" });
    expect(event.exception.values[0].value).toBe("no account for [email]");
    expect(event.extra.password).toBe("[scrubbed]");
    expect(event.breadcrumbs[0].data.from).toBe("/login");
    for (const leak of ["pianist@example.com", "hunter22", "eyJhbGciOi", "203.0.113.9", "abc.def"]) expect(text).not.toContain(leak);
  });

  it("keeps fetch breadcrumbs without their query strings", () => {
    const crumb = scrubBreadcrumb({ category: "fetch", data: { url: "https://api.test/catalog?q=chopin&token=1", method: "GET", status_code: 200 } });
    expect(crumb.data).toEqual({ url: "https://api.test/catalog", method: "GET", status_code: 200 });
  });
});
