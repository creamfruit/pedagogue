import { PRICING_PATH, offersVisible } from "../lib/billing.js";
import { el } from "../lib/dom.js";
import { describePlan } from "../lib/planSummary.js";
import { store } from "../lib/store.js";
import { navigate } from "../router.js";

function row(href, title, caption) {
  return el(
    "a",
    { class: "me-row", href, "data-link": true },
    el("span", { class: "me-row-text" }, el("strong", {}, title), el("span", { class: "faint" }, caption)),
    el("span", { class: "me-row-chevron", "aria-hidden": "true" }, "›")
  );
}

function header() {
  const user = store.user;
  const name = user?.display_name || (user?.is_guest ? "Guest pianist" : user?.email?.split("@")[0]) || "You";
  const wallet = store.wallet;
  const plan = describePlan(store.plan);
  return el(
    "section",
    { class: "panel panel-accent me-head" },
    el("span", { class: "me-avatar", "aria-hidden": "true" }, name.trim().charAt(0).toUpperCase()),
    el(
      "div",
      { class: "me-head-text" },
      el("h1", { style: "margin:0" }, name),
      el(
        "p",
        { class: "muted", style: "margin:2px 0 0" },
        [wallet ? `Level ${wallet.level}` : null, plan.name ? `${plan.name} plan` : null].filter(Boolean).join(" · ")
      )
    )
  );
}

export function meView(outlet) {
  document.title = "Me · Piano Pedagogue";
  const rows = [
    row("/progress", "Progress", "Your growth, performances and readiness"),
    row("/observatory", "Observatory", "Spend gold on cosmetics for your sky"),
    row("/practice", "Practice tools", "Free practice, drills and sight-reading"),
    row("/roulette", "Daily roulette", "Today's shared sight-reading snippet"),
    offersVisible() ? row(PRICING_PATH, "Pedagogue Pro", store.plan?.limits?.is_pro ? "Your plan and billing" : "See what Pro adds") : null,
    row("/settings", "Settings", "Account, reminders, motion and your data"),
    row("/credits", "Credits", "Where the scores and data come from"),
  ].filter(Boolean);
  const guest = store.user?.is_guest
    ? el(
        "section",
        { class: "panel me-guest" },
        el("strong", {}, "Keep your progress"),
        el("p", { class: "muted", style: "margin:4px 0 12px" }, "You're practising as a guest. Create an account and everything you've done moves across."),
        el("button", { type: "button", class: "btn", onclick: () => navigate("/register") }, "Create an account")
      )
    : null;
  outlet.append(el("div", { class: "me" }, header(), guest, el("nav", { class: "me-list", "aria-label": "More" }, ...rows)));
  return () => {
    document.title = "Piano Pedagogue";
  };
}
