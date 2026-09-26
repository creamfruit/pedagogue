const routes = [];
let outlet = null;
let notFound = null;
let guard = null;
let current = null;
let disposeCurrent = null;

function compile(pattern) {
  const keys = [];
  const source = pattern
    .split("/")
    .map((segment) => {
      if (!segment.startsWith(":")) return segment;
      keys.push(segment.slice(1));
      return "([^/]+)";
    })
    .join("/");
  return { regex: new RegExp(`^${source}/?$`), keys };
}

export function route(pattern, handler, options = {}) {
  const { regex, keys } = compile(pattern);
  routes.push({ pattern, regex, keys, handler, ...options });
}

export function setNotFound(handler) {
  notFound = handler;
}

export function setGuard(handler) {
  guard = handler;
}

export function navigate(path, { replace = false } = {}) {
  if (path === window.location.pathname + window.location.search) {
    return resolve();
  }
  if (replace) window.history.replaceState({}, "", path);
  else window.history.pushState({}, "", path);
  return resolve();
}

export function match(pathname) {
  for (const entry of routes) {
    const found = pathname.match(entry.regex);
    if (!found) continue;
    const params = {};
    entry.keys.forEach((key, index) => {
      params[key] = decodeURIComponent(found[index + 1]);
    });
    return { entry, params };
  }
  return null;
}

function markActive(pathname) {
  document.querySelectorAll("[data-nav]").forEach((link) => {
    const active = link.dataset.nav
      .split(" ")
      .some((target) => (target === "/" ? pathname === "/" : pathname.startsWith(target)));
    link.classList.toggle("active", active);
    if (active) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
}

export async function resolve() {
  if (!outlet) return;
  const pathname = window.location.pathname;
  const query = Object.fromEntries(new URLSearchParams(window.location.search));
  const found = match(pathname);

  if (guard) {
    const redirect = await guard({ pathname, entry: found ? found.entry : null });
    if (redirect && redirect !== pathname) {
      window.history.replaceState({}, "", redirect);
      return resolve();
    }
  }

  if (typeof disposeCurrent === "function") {
    try {
      disposeCurrent();
    } catch {
      /* view cleanup failed, continue */
    }
  }
  disposeCurrent = null;

  const context = { params: found ? found.params : {}, query, pathname };
  const handler = found ? found.entry.handler : notFound;
  if (!handler) return;

  outlet.replaceChildren();
  markActive(pathname);
  current = pathname;

  try {
    const result = await handler(outlet, context);
    if (typeof result === "function") disposeCurrent = result;
  } catch (error) {
    outlet.replaceChildren();
    const box = document.createElement("div");
    box.className = "empty";
    box.textContent = error && error.message ? error.message : "something went wrong";
    outlet.append(box);
  }

  outlet.focus({ preventScroll: true });
  window.scrollTo({ top: 0, behavior: "instant" in window ? "instant" : "auto" });
}

function onClick(event) {
  const link = event.target.closest("a[data-link]");
  if (!link) return;
  const href = link.getAttribute("href");
  if (!href || href.startsWith("http") || link.target === "_blank") return;
  event.preventDefault();
  navigate(href);
}

export function startRouter(outletNode) {
  outlet = outletNode;
  document.addEventListener("click", onClick);
  window.addEventListener("popstate", resolve);
  return resolve();
}

export function currentPath() {
  return current;
}
