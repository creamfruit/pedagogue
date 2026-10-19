const EMAIL = /[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+/g;
const BEARER = /bearer\s+[A-Za-z0-9._~+/=-]+/gi;
const SENSITIVE_KEY = /pass(word)?|secret|token|authorization|cookie|api[_-]?key|dsn|e-?mail|credential|session[_-]?id/i;
const SCRUBBED = "[scrubbed]";

let sentry = null;
let pendingUser;

export function scrubValue(value) {
  if (typeof value === "string") return value.replace(EMAIL, "[email]").replace(BEARER, `Bearer ${SCRUBBED}`);
  if (Array.isArray(value)) return value.map(scrubValue);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, SENSITIVE_KEY.test(key) ? SCRUBBED : scrubValue(item)]));
  }
  return value;
}

function withoutQuery(url) {
  return typeof url === "string" ? url.split("?")[0].split("#")[0] : url;
}

export function scrubBreadcrumb(crumb) {
  if (!crumb?.data || typeof crumb.data !== "object") return scrubValue(crumb);
  const data = { ...crumb.data };
  for (const key of ["url", "to", "from"]) if (typeof data[key] === "string") data[key] = withoutQuery(data[key]);
  return scrubValue({ ...crumb, data });
}

export function scrubEvent(event) {
  const id = event.user?.id;
  event.user = id ? { id: String(id) } : {};
  if (event.request) {
    const { cookies, data, headers, query_string, ...rest } = event.request;
    event.request = { ...rest, url: withoutQuery(rest.url) };
  }
  if (Array.isArray(event.breadcrumbs)) event.breadcrumbs = event.breadcrumbs.map(scrubBreadcrumb);
  return scrubValue(event);
}

export function monitoringDsn() {
  return String(import.meta.env.VITE_SENTRY_DSN || "").trim();
}

export async function startMonitoring({ dsn = monitoringDsn(), load = () => import("@sentry/browser"), environment = import.meta.env.MODE, release = import.meta.env.VITE_RELEASE } = {}) {
  if (!dsn) return false;
  try {
    const Sentry = await load();
    Sentry.init({
      dsn,
      environment,
      release: release || undefined,
      sendDefaultPii: false,
      tracesSampleRate: 0,
      beforeSend: scrubEvent,
      beforeBreadcrumb: scrubBreadcrumb,
    });
    sentry = Sentry;
    if (pendingUser !== undefined) identifyUser(pendingUser);
    return true;
  } catch {
    return false;
  }
}

export function identifyUser(id) {
  pendingUser = id ?? null;
  if (!sentry) return;
  sentry.setUser(id ? { id: String(id) } : null);
}
