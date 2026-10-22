import { api } from "../api/client.js";
import { disclosure, el } from "../lib/dom.js";
import { excerptPanel, excerptsFor } from "../lib/excerpts.js";
import { notify } from "../lib/toast.js";

const TIERS = ["S", "A", "B", "C", "D"];
const TIER_LABEL = {
  S: "S · mastered",
  A: "A · strong",
  B: "B · solid",
  C: "C · shaky",
  D: "D · weak spot",
};

function setBusy(button, busy) {
  if (busy) {
    button.dataset.idleLabel = button.textContent;
    button.textContent = "Saving…";
    button.setAttribute("aria-busy", "true");
    button.disabled = true;
    return;
  }
  if (button.dataset.idleLabel) button.textContent = button.dataset.idleLabel;
  button.removeAttribute("aria-busy");
  button.disabled = false;
}

export function tierFromScore(score) {
  if (score === null || score === undefined) return null;
  const value = Number(score);
  const tiers = [["S", 9.0], ["A", 7.2], ["B", 5.5], ["C", 3.5], ["D", 1.5]];
  return tiers.reduce((best, tier) => (Math.abs(tier[1] - value) < Math.abs(best[1] - value) ? tier : best))[0];
}

export function savedTiers(profiles) {
  return new Map(
    (profiles || [])
      .map((profile) => [profile.technique_id, tierFromScore(profile.proficiency_score)])
      .filter(([, tier]) => tier)
  );
}

async function fillTechniqueExample(region, technique, register) {
  region.replaceChildren(el("p", { class: "faint tier-example-note" }, "Finding a passage from the repertoire…"));
  try {
    const panel = excerptPanel(await excerptsFor(technique.name));
    register(panel.stop);
    region.replaceChildren(panel.node);
  } catch (error) {
    region.replaceChildren(el("p", { class: "faint tier-example-note" }, error.message || "Could not load an example right now."));
  }
}

export function tierQuizStep(allTechniques, refresh, { initial = new Map(), submitLabel = "Continue" } = {}) {
  const assignments = new Map([...initial].filter(([id]) => allTechniques.some((technique) => technique.id === id)));
  const groups = new Map();
  allTechniques.forEach((technique) => {
    if (!groups.has(technique.category)) groups.set(technique.category, []);
    groups.get(technique.category).push(technique);
  });

  const submit = el(
    "button",
    {
      class: "btn",
      type: "submit",
      disabled: true,
      onclick: async (event) => {
        event.preventDefault();
        setBusy(submit, true);
        try {
          const tiers = Array.from(assignments, ([technique_id, tier]) => ({ technique_id, tier }));
          await api.updateTierList(tiers);
          await refresh();
        } catch (error) {
          notify.error(error.detail || "Could not save your tier list");
          setBusy(submit, false);
        }
      },
    },
    "Continue"
  );

  function updateProgress() {
    submit.disabled = assignments.size < allTechniques.length;
    submit.textContent = submit.disabled
      ? `Rank every technique (${assignments.size}/${allTechniques.length})`
      : submitLabel;
  }

  const rows = [];
  groups.forEach((techniques, category) => {
    rows.push(el("div", { class: "tier-category" }, el("h3", { style: "margin:0" }, category.replace(/_/g, " "))));
    techniques.forEach((technique) => {
      const buttons = TIERS.map((tier) =>
        el(
          "button",
          {
            type: "button",
            class: "btn btn-small btn-ghost tier-btn",
            "aria-pressed": "false",
            "aria-label": `${technique.name}: ${TIER_LABEL[tier]}`,
            onclick: () => {
              assignments.set(technique.id, tier);
              buttons.forEach((button) => {
                button.classList.remove("tier-btn-active");
                button.setAttribute("aria-pressed", "false");
              });
              buttons[TIERS.indexOf(tier)].classList.add("tier-btn-active");
              buttons[TIERS.indexOf(tier)].setAttribute("aria-pressed", "true");
              updateProgress();
            },
          },
          tier
        )
      );
      const saved = assignments.get(technique.id);
      if (saved) {
        buttons[TIERS.indexOf(saved)].classList.add("tier-btn-active");
        buttons[TIERS.indexOf(saved)].setAttribute("aria-pressed", "true");
      }
      let stopExample = null;
      const example = disclosure("?", {
        label: `How ${technique.name} is played, with an example`,
        buttonClass: "tier-help",
        regionClass: "tier-example",
        onFirstOpen: (region) => {
          const exampleHost = el("div");
          if (technique.mechanic) region.append(el("p", { class: "tier-example-mechanic" }, technique.mechanic));
          region.append(exampleHost);
          fillTechniqueExample(exampleHost, technique, (stop) => {
            stopExample = stop;
          });
        },
        onClose: () => {
          if (stopExample) stopExample();
        },
      });
      rows.push(
        el(
          "div",
          { class: "tier-row" },
          el(
            "div",
            { class: "list-item" },
            el(
              "div",
              { class: "tier-name" },
              el("div", { class: "row", style: "gap:8px;flex-wrap:nowrap" }, el("span", { style: "font-weight:500" }, technique.name), example.button)
            ),
            el("div", { class: "row tier-buttons" }, ...buttons)
          ),
          example.region
        )
      );
    });
  });
  updateProgress();

  return el(
    "div",
    { class: "panel panel-accent stack tier-quiz" },
    el(
      "div",
      {},
      el("p", { class: "muted", style: "margin:0 0 6px" }, "Rank every technique against the tier list. This colours requirements on every piece and drives your sight-reading forge."),
      el(
        "p",
        { class: "tier-legend mono" },
        TIERS.map((tier) => TIER_LABEL[tier]).join("   ·   ")
      ),
      el("p", { class: "faint", style: "margin:0;font-size:12.5px" }, "Tap ? beside a technique to see a real passage that uses it and hear it on piano.")
    ),
    el("div", { class: "stack tier-rows" }, ...rows),
    el("div", { class: "sticky-actions" }, submit)
  );
}

