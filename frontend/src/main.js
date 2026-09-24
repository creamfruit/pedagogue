import "./styles.css";
import { onUnauthorized } from "./api/client.js";
import { store, subscribe } from "./lib/store.js";
import { notify } from "./lib/toast.js";
import { navigate, route, setGuard, setNotFound, startRouter } from "./router.js";
import { loginView, registerView } from "./views/auth.js";
import { onboardingView } from "./views/onboarding.js";
import { dashboardView } from "./views/dashboard.js";
import { entryDetailView, newEntryView, repertoireView } from "./views/repertoire.js";
import { constellationView } from "./views/constellation.js";
import { practiceView } from "./views/practice.js";
import { progressionView } from "./views/progression.js";
import { performancesView } from "./views/performances.js";
import { shopView } from "./views/shop.js";
import { notFoundView } from "./views/notfound.js";

const PUBLIC_ROUTES = new Set(["/login", "/register"]);

route("/", dashboardView);
route("/onboarding", onboardingView);
route("/repertoire", repertoireView);
route("/repertoire/new", newEntryView);
route("/repertoire/:id", entryDetailView);
route("/constellation", constellationView);
route("/practice", practiceView);
route("/progression", progressionView);
route("/performances", performancesView);
route("/observatory", shopView);
route("/login", loginView, { public: true });
route("/register", registerView, { public: true });
setNotFound(notFoundView);

setGuard(({ pathname }) => {
  const isPublic = PUBLIC_ROUTES.has(pathname);
  if (!store.isAuthenticated && !isPublic) return "/login";
  if (store.isAuthenticated && isPublic) return "/";
  if (store.isAuthenticated && pathname !== "/onboarding") {
    const onboarding = store.onboarding;
    if (onboarding && !onboarding.complete) return "/onboarding";
  }
  if (store.isAuthenticated && pathname === "/onboarding" && store.onboarding?.complete) return "/";
  return null;
});

function setWallet() {
  const host = document.getElementById("wallet");
  if (!host) return;
  const wallet = store.wallet;
  if (!store.isAuthenticated || !wallet) {
    host.hidden = true;
    return;
  }
  host.hidden = false;
  host.replaceChildren();
  const level = document.createElement("span");
  level.className = "wallet-level";
  level.textContent = `LV ${wallet.level}`;
  const bar = document.createElement("span");
  bar.className = "wallet-bar";
  const fill = document.createElement("span");
  fill.style.width = `${Math.round((wallet.level_progress || 0) * 100)}%`;
  bar.append(fill);
  const gold = document.createElement("span");
  gold.className = "wallet-gold";
  gold.textContent = `${wallet.gold.toLocaleString()}g`;
  host.append(level, bar, gold);
  host.title = `${wallet.xp_for_next_level} xp to level ${wallet.level + 1}`;
}

function setChrome() {
  const authed = store.isAuthenticated;
  document.getElementById("nav").style.display = authed ? "" : "none";
  setWallet();
  const right = document.querySelector(".topbar-right");
  const existing = document.getElementById("sign-out");
  if (authed && !existing) {
    const button = document.createElement("button");
    button.id = "sign-out";
    button.className = "btn btn-small btn-ghost";
    button.textContent = "Sign out";
    button.addEventListener("click", () => {
      store.signOut();
      navigate("/login");
    });
    right.insertBefore(button, right.firstChild);
  } else if (!authed && existing) {
    existing.remove();
  }
}

function wireNetworkStatus() {
  const pill = document.getElementById("net-status");
  const update = () => {
    const online = navigator.onLine;
    pill.textContent = online ? "online" : "offline";
    pill.className = online ? "pill pill-ok" : "pill pill-warn";
  };
  window.addEventListener("online", () => {
    update();
    notify.success("Back online");
  });
  window.addEventListener("offline", () => {
    update();
    notify.info("Offline. Cached pages still work.");
  });
  update();
}

function wireMenu() {
  const toggle = document.getElementById("nav-toggle");
  const nav = document.getElementById("nav");
  toggle.addEventListener("click", () => {
    const open = nav.classList.toggle("open");
    toggle.setAttribute("aria-expanded", open ? "true" : "false");
  });
  nav.addEventListener("click", (event) => {
    if (event.target.closest("a")) {
      nav.classList.remove("open");
      toggle.setAttribute("aria-expanded", "false");
    }
  });
}

async function registerServiceWorker() {
  if (!("serviceWorker" in navigator) || import.meta.env.DEV) return;
  try {
    const { registerSW } = await import("virtual:pwa-register");
    const bar = document.getElementById("update-bar");
    const apply = document.getElementById("update-apply");
    const dismiss = document.getElementById("update-dismiss");
    const updateSW = registerSW({
      onNeedRefresh() {
        bar.hidden = false;
      },
      onOfflineReady() {
        notify.success("Ready to work offline");
      },
    });
    apply.addEventListener("click", () => updateSW(true));
    dismiss.addEventListener("click", () => {
      bar.hidden = true;
    });
  } catch {
    /* service worker unavailable, app still works online */
  }
}

async function boot() {
  wireNetworkStatus();
  wireMenu();

  onUnauthorized(() => {
    store.signOut();
    setChrome();
    notify.error("Your session expired. Sign in again.");
    navigate("/login");
  });

  subscribe(setChrome);
  await store.hydrate();
  setChrome();

  const app = document.getElementById("app");
  const bootScreen = document.getElementById("boot");
  app.hidden = false;
  bootScreen.hidden = true;

  const tag = document.getElementById("build-tag");
  tag.textContent = `Piano Pedagogue · ${import.meta.env.MODE}`;

  await startRouter(document.getElementById("view"));
  if (store.isAuthenticated) {
    store.refreshOnboarding();
    store.refreshProfile();
  }
  registerServiceWorker();
}

boot();
