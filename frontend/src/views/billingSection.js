import { billingMode, manageBilling, offersVisible, restorePurchases } from "../lib/billing.js";
import { el, sectionBlock } from "../lib/dom.js";
import { describePlan } from "../lib/planSummary.js";
import { store } from "../lib/store.js";
import { notify } from "../lib/toast.js";

const CHECKOUT_POLLS = 8;
const CHECKOUT_POLL_MS = 1500;

function manageButton(plan) {
  const mode = billingMode();
  if (mode === "stripe" && !plan?.billing?.portal) return null;
  const button = el(
    "button",
    {
      type: "button",
      class: "btn btn-small",
      onclick: async () => {
        button.disabled = true;
        try {
          await manageBilling();
        } catch (error) {
          notify.error(error.detail || error.message || "Could not open billing");
          button.disabled = false;
        }
      },
    },
    mode === "stripe" ? "Manage billing" : "Manage subscription"
  );
  return button;
}

function restoreButton() {
  const button = el(
    "button",
    {
      type: "button",
      class: "btn btn-small btn-ghost",
      onclick: async () => {
        button.disabled = true;
        try {
          const result = await restorePurchases();
          notify[result.restored ? "success" : "info"](result.restored ? "Your purchase was restored" : "No earlier purchase was found");
        } catch (error) {
          notify.error(error.message || "Could not restore purchases");
        } finally {
          button.disabled = false;
        }
      },
    },
    "Restore purchases"
  );
  return button;
}

export function billingSection() {
  const plan = store.plan;
  if (!plan) return null;
  const summary = describePlan(plan);
  const actions = [];
  if (offersVisible()) {
    if (summary.pro) {
      const manage = manageButton(plan);
      if (manage) actions.push(manage);
    } else {
      actions.push(el("a", { class: "btn btn-small", href: "/pricing", "data-link": true }, plan.can_start_trial ? `Try Pro free for ${plan.trial_days} days` : "See Pro"));
    }
    if (billingMode() === "in-app") actions.push(restoreButton());
  }
  if (store.user?.is_admin) {
    actions.push(el("a", { class: "btn btn-small btn-ghost", href: "/admin/subscribers", "data-link": true }, "Subscribers"));
  }
  return sectionBlock(
    "Plan",
    { caption: summary.pro ? "You have Pro." : "You're on the Free plan.", id: "plan" },
    el("div", { class: "stack plan-summary" }, ...summary.lines.map((line) => el("p", { class: summary.warn ? "plan-warning" : "", style: "margin:0" }, line))),
    actions.length ? el("div", { class: "row", style: "gap:var(--space-2);margin-top:var(--space-3)" }, ...actions) : null
  );
}

export async function confirmCheckout() {
  const params = new URLSearchParams(window.location.search);
  if (params.get("billing") !== "success") return false;
  window.history.replaceState(window.history.state, "", window.location.pathname);
  for (let attempt = 0; attempt < CHECKOUT_POLLS; attempt += 1) {
    await store.refreshPlan();
    if (store.plan?.limits?.is_pro) {
      notify.success("Welcome to Pro. Everything is unlocked.");
      return true;
    }
    await new Promise((resolve) => setTimeout(resolve, CHECKOUT_POLL_MS));
  }
  notify.info("Your payment is being confirmed. Pro switches on as soon as it is, usually within a minute.");
  return false;
}
