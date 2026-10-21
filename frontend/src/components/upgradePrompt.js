import { PRICING_PATH, offersVisible } from "../lib/billing.js";
import { el, openModal } from "../lib/dom.js";
import { upgradeCopy } from "../lib/plan.js";
import { notify } from "../lib/toast.js";
import { navigate } from "../router.js";

const TITLES = {
  active_pieces: "Your pieces are full",
  pdf_score_reading: "PDF scores are part of Pro",
  keyboard_history: "More keyboard history is part of Pro",
  tempo_ladder: "The full tempo ladder is part of Pro",
  share_cards: "Share cards are part of Pro",
  cloud_sync: "Cloud sync is part of Pro",
};

const FALLBACK_MESSAGE = "This is part of Pedagogue Pro.";

function wording(feature, given) {
  const copy = upgradeCopy(feature);
  return {
    message: given?.message || copy?.message || FALLBACK_MESSAGE,
    upgrade: given?.upgrade || copy?.upgrade || "",
  };
}

export function upgradeNotice(feature, given) {
  const { message, upgrade } = wording(feature, given);
  const parts = [el("span", {}, message)];
  if (offersVisible()) {
    if (upgrade) parts.push(el("span", {}, ` ${upgrade}`));
    parts.push(" ", el("a", { href: PRICING_PATH, "data-link": true }, "See Pro"));
  }
  return el("p", { class: "upgrade-notice", role: "note", "data-feature": feature }, ...parts);
}

export function showUpgrade(feature, given) {
  const { message, upgrade } = wording(feature, given);
  const actions = [];
  let modal = null;
  const close = () => modal?.close();
  if (offersVisible()) {
    actions.push(
      el(
        "button",
        {
          type: "button",
          class: "btn",
          onclick: () => {
            close();
            navigate(PRICING_PATH);
          },
        },
        "See Pro"
      )
    );
  }
  actions.push(el("button", { type: "button", class: "btn btn-ghost", onclick: close }, offersVisible() ? "Not now" : "OK"));
  const body = el(
    "div",
    { class: "stack upgrade-prompt" },
    el("p", { style: "margin:0" }, message),
    offersVisible() && upgrade ? el("p", { class: "faint", style: "margin:0" }, upgrade) : null,
    el("div", { class: "row", style: "gap:var(--space-2)" }, ...actions)
  );
  modal = openModal(body, { title: TITLES[feature] || "Part of Pro" });
  return modal;
}

export function explainFailure(error, fallback) {
  if (error?.isPlanLimit) {
    showUpgrade(error.planFeature, error.payload.detail);
    return true;
  }
  notify.error(error?.detail || fallback);
  return false;
}
