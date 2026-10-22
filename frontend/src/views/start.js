import { el } from "../lib/dom.js";
import { store } from "../lib/store.js";
import { navigate } from "../router.js";

export async function startView(outlet) {
  const stage = el("div", { class: "quick quick-start" }, el("p", { class: "muted" }, "Setting things up…"));
  outlet.append(stage);
  try {
    if (!store.isAuthenticated) await store.startGuest();
    markLaunched();
    navigate("/onboarding", { replace: true });
  } catch (error) {
    stage.replaceChildren(
      el("h1", { class: "quick-title" }, "Couldn't get started"),
      el("p", { class: "muted" }, error.detail || "Check your connection and try again."),
      el("div", { class: "row", style: "gap:var(--space-2)" }, el("button", { type: "button", class: "btn", onclick: () => navigate("/start", { replace: true }) }, "Try again"), el("a", { class: "btn btn-ghost", href: "/login", "data-link": true }, "Sign in instead"))
    );
  }
}

const LAUNCH_KEY = "pp.launched";

export function markLaunched() {
  try {
    localStorage.setItem(LAUNCH_KEY, "1");
  } catch {
    return;
  }
}

export function firstLaunch() {
  try {
    return localStorage.getItem(LAUNCH_KEY) !== "1";
  } catch {
    return false;
  }
}
