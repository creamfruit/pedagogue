import { api } from "../api/client.js";
import { backButton, el, empty } from "../lib/dom.js";
import { formatDate } from "../lib/planSummary.js";
import { store } from "../lib/store.js";
import { notify } from "../lib/toast.js";

const PAGE = 50;

const FILTERS = [
  ["", "Everyone"],
  ["pro", "Has Pro now"],
  ["trialing", "On a trial"],
  ["active", "Paying"],
  ["past_due", "Payment failed"],
  ["canceled", "Cancelled"],
];

const STATUS_LABEL = {
  trialing: "Trial",
  active: "Paying",
  past_due: "Payment failed",
  canceled: "Cancelled",
  unpaid: "Unpaid",
  incomplete: "Not finished",
  incomplete_expired: "Expired",
  paused: "Paused",
};

function row(item) {
  const ends = item.trial_end && item.status === "trialing" ? item.trial_end : item.current_period_end;
  const endLabel = ends ? `${item.cancel_at_period_end || item.status === "canceled" ? "Ends" : item.status === "trialing" ? "Trial ends" : "Renews"} ${formatDate(ends)}` : "";
  return el(
    "tr",
    { "data-status": item.status },
    el("th", { scope: "row" }, item.email, item.name ? el("div", { class: "faint", style: "font-size:12px" }, item.name) : null),
    el("td", {}, el("span", { class: `pill ${item.is_pro ? "pill-ok" : ""}` }, STATUS_LABEL[item.status] || item.status)),
    el("td", {}, item.interval === "month" ? "Monthly" : item.interval === "year" ? "Yearly" : ""),
    el("td", {}, endLabel),
    el("td", {}, formatDate(item.started_at))
  );
}

export async function subscribersView(outlet) {
  document.title = "Subscribers · Piano Pedagogue";
  const dispose = () => {
    document.title = "Piano Pedagogue";
  };
  if (!store.user?.is_admin) {
    outlet.append(backButton("/settings"), empty("This page is for administrators."));
    return dispose;
  }

  const select = el("select", { "aria-label": "Show" }, ...FILTERS.map(([value, label]) => el("option", { value }, label)));
  const counts = el("p", { class: "faint", style: "margin:0" });
  const body = el("tbody", {});
  const more = el("button", { type: "button", class: "btn btn-small btn-ghost", hidden: true }, "Show more");
  const note = el("p", { class: "faint", role: "status" });
  let shown = 0;

  async function load(reset) {
    if (reset) {
      shown = 0;
      body.replaceChildren();
    }
    more.disabled = true;
    try {
      const page = await api.billingSubscribers({ limit: PAGE, offset: shown, status: select.value || undefined });
      body.append(...page.items.map(row));
      shown += page.items.length;
      counts.textContent = `${page.counts.pro} with Pro now · ${page.total} ${select.value ? "match" : "in total"}`;
      more.hidden = shown >= page.total;
      note.textContent = page.total ? "" : "Nobody here yet.";
    } catch (error) {
      notify.error(error.detail || "Could not load subscribers");
    } finally {
      more.disabled = false;
    }
  }

  select.addEventListener("change", () => load(true));
  more.addEventListener("click", () => load(false));

  outlet.append(
    backButton("/settings"),
    el("div", { class: "page-head" }, el("h1", { style: "margin:0" }, "Subscribers")),
    el(
      "section",
      { class: "panel detail-section" },
      el("div", { class: "row", style: "justify-content:space-between;gap:var(--space-3);flex-wrap:wrap" }, counts, select),
      el(
        "div",
        { class: "table-scroll" },
        el(
          "table",
          { class: "subscriber-table" },
          el("thead", {}, el("tr", {}, ...["Person", "Status", "Plan", "Date", "Started"].map((label) => el("th", { scope: "col" }, label)))),
          body
        )
      ),
      note,
      el("div", {}, more)
    )
  );
  await load(true);
  return dispose;
}
