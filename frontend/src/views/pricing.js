import { backButton, el } from "../lib/dom.js";
import { billingMode, loadOptions, manageBilling, offersVisible, subscribe } from "../lib/billing.js";
import { comparisonRows, describePlan, savingsPercent } from "../lib/planSummary.js";
import { store } from "../lib/store.js";
import { notify } from "../lib/toast.js";

const PERIOD = { month: "month", year: "year" };

function comparisonTable() {
  const limits = store.plan?.limits;
  const rows = comparisonRows(limits);
  return el(
    "div",
    { class: "table-scroll" },
    el(
      "table",
      { class: "plan-table" },
      el("thead", {}, el("tr", {}, el("th", { scope: "col" }, "What you get"), el("th", { scope: "col" }, "Free"), el("th", { scope: "col", class: "plan-table-pro" }, "Pro"))),
      el(
        "tbody",
        {},
        ...rows.map(([feature, free, pro]) => el("tr", {}, el("th", { scope: "row" }, feature), el("td", {}, free), el("td", { class: "plan-table-pro" }, pro)))
      )
    )
  );
}

function optionCard(option, { trial, savings, busyState, onChoose }) {
  const price = option.price ? `${option.price} / ${PERIOD[option.interval] || option.interval}` : option.label;
  const button = el(
    "button",
    {
      type: "button",
      class: "btn",
      onclick: async () => {
        if (busyState.busy) return;
        busyState.set(true);
        try {
          await onChoose(option);
        } catch (error) {
          notify.error(error.detail || error.message || "Could not start that");
          busyState.set(false);
        }
      },
    },
    trial ? `Start ${option.trialDays}-day free trial` : "Subscribe"
  );
  busyState.buttons.push(button);
  return el(
    "div",
    { class: "plan-option", "data-interval": option.interval },
    el("strong", {}, option.label),
    el("div", { class: "plan-price" }, price),
    option.interval === "year" && savings ? el("div", { class: "pill pill-ok" }, `Save ${savings}%`) : null,
    button
  );
}

function trialNote(days) {
  return el(
    "p",
    { class: "faint plan-note" },
    `Try Pro free for ${days} days. You add a card at checkout and aren't charged until the trial ends. Cancel any time before then from Settings, and you'll pay nothing. A trial is offered once per account.`
  );
}

function signedOutPrompt() {
  return el(
    "div",
    { class: "row plan-actions" },
    el("a", { class: "btn", href: "/register", "data-link": true }, "Create a free account"),
    el("a", { class: "btn btn-ghost", href: "/login", "data-link": true }, "Sign in"),
    el("p", { class: "faint", style: "margin:0;font-size:13px" }, "Start your Pro trial once you're signed in.")
  );
}

function proActions() {
  const summary = describePlan(store.plan);
  const manage = el(
    "button",
    {
      type: "button",
      class: "btn",
      onclick: async () => {
        manage.disabled = true;
        try {
          await manageBilling();
        } catch (error) {
          notify.error(error.detail || error.message || "Could not open billing");
          manage.disabled = false;
        }
      },
    },
    "Manage billing"
  );
  const canManage = billingMode() !== "stripe" || store.plan?.billing?.portal;
  return el("div", { class: "stack plan-actions" }, el("p", { style: "margin:0" }, el("strong", {}, "You have Pro. "), ...summary.lines), canManage ? el("div", {}, manage) : null);
}

export async function pricingView(outlet) {
  document.title = "Pricing · Piano Pedagogue";
  const params = new URLSearchParams(window.location.search);
  if (params.get("billing") === "cancelled") {
    notify.info("Checkout was cancelled. Nothing was charged.");
    window.history.replaceState(window.history.state, "", window.location.pathname);
  }

  if (!offersVisible()) {
    const summary = describePlan(store.plan);
    outlet.append(
      backButton("/settings"),
      el("article", { class: "panel pricing" }, el("h1", {}, "Your plan"), el("p", { style: "margin:0" }, el("strong", {}, summary.name || "Free"), summary.lines.length ? ` · ${summary.lines.join(" ")}` : ""), comparisonTable())
    );
    return () => {
      document.title = "Piano Pedagogue";
    };
  }

  const host = el("div", { class: "stack" }, el("p", { class: "faint" }, "Loading prices…"));
  outlet.append(
    backButton(store.isAuthenticated ? "/settings" : "/login"),
    el(
      "article",
      { class: "panel pricing" },
      el("h1", {}, "Pedagogue Pro"),
      el("p", { class: "faint" }, "Pedagogue is free to use. Pro takes the limits off for people who practise a lot."),
      comparisonTable(),
      host
    )
  );

  const proNow = Boolean(store.plan?.limits?.is_pro);
  if (proNow) {
    host.replaceChildren(proActions());
    return () => {
      document.title = "Piano Pedagogue";
    };
  }
  if (!store.isAuthenticated) {
    host.replaceChildren(signedOutPrompt());
  }

  let options = [];
  try {
    options = await loadOptions();
  } catch {
    options = [];
  }
  if (!host.isConnected) return null;
  if (!options.length) {
    host.replaceChildren(el("p", { class: "faint" }, "Pro isn't open for sign-up yet. Everything on the Free plan works as normal."));
    return () => {
      document.title = "Piano Pedagogue";
    };
  }
  if (!store.isAuthenticated) {
    const days = options[0].trialDays;
    host.replaceChildren(
      el("div", { class: "plan-options" }, ...options.map((option) => el("div", { class: "plan-option" }, el("strong", {}, option.label), el("div", { class: "plan-price" }, option.price ? `${option.price} / ${PERIOD[option.interval] || option.interval}` : "")))),
      days ? trialNote(days) : null,
      signedOutPrompt()
    );
    return () => {
      document.title = "Piano Pedagogue";
    };
  }

  const trial = Boolean(store.plan?.can_start_trial) && options[0].trialDays > 0;
  const savings = savingsPercent(options);
  const busyState = {
    busy: false,
    buttons: [],
    set(value) {
      this.busy = value;
      this.buttons.forEach((button) => {
        button.disabled = value;
      });
    },
  };
  host.replaceChildren(
    el("div", { class: "plan-options" }, ...options.map((option) => optionCard(option, { trial, savings, busyState, onChoose: subscribe }))),
    trial ? trialNote(options[0].trialDays) : null
  );
  return () => {
    document.title = "Piano Pedagogue";
  };
}
