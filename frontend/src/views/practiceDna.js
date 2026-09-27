import { api } from "../api/client.js";
import { el, empty, sectionBlock, skeletonBlock } from "../lib/dom.js";

const TIER_ORDER = ["S", "A", "B", "C", "D"];

function surname(name) {
  return name.split(" ").pop();
}

function percent(value) {
  return `${Math.round(value * 100)}%`;
}

function meter(similarity) {
  const share = similarity === null ? 0 : (similarity + 1) / 2;
  return el(
    "span",
    { class: "dna-meter", "aria-hidden": "true" },
    el("span", { class: "dna-meter-fill", style: `width:${Math.round(share * 100)}%` }),
    el("span", { class: "dna-meter-mid" })
  );
}

function composerButton(composer, selected, onSelect) {
  const basis = composer.pieces === 1 ? "based on 1 piece" : `based on ${composer.pieces} pieces`;
  return el(
    "button",
    {
      type: "button",
      class: `dna-composer${selected ? " is-selected" : ""}`,
      "aria-pressed": selected ? "true" : "false",
      onclick: () => onSelect(composer.id),
    },
    el("span", { class: "dna-composer-name" }, composer.name),
    meter(composer.similarity),
    el(
      "span",
      { class: `dna-composer-meta faint${composer.pieces === 1 ? " is-thin" : ""}` },
      el("span", { class: "dna-composer-label" }, composer.label),
      ` · ${[composer.era, basis].filter(Boolean).join(" · ")}`
    )
  );
}

function comparison(dna, composer) {
  const share = new Map(composer.demand.map((item) => [item.technique_id, item.share]));
  const peak = Math.max(...composer.demand.map((item) => item.share), 0.01);
  const rows = [...dna.techniques].sort(
    (a, b) => (share.get(b.id) || 0) - (share.get(a.id) || 0) || TIER_ORDER.indexOf(a.tier ?? "Z") - TIER_ORDER.indexOf(b.tier ?? "Z")
  );
  const who = surname(composer.name);
  return el(
    "table",
    { class: "dna-table" },
    el("caption", { class: "sr-only" }, `Your tier in each technique beside how much of ${composer.name}'s music here leans on it`),
    el(
      "thead",
      {},
      el(
        "tr",
        {},
        el("th", { scope: "col" }, "Technique"),
        el("th", { scope: "col" }, "Your tier"),
        el("th", { scope: "col" }, `${who}'s emphasis`)
      )
    ),
    el(
      "tbody",
      {},
      ...rows.map((technique) => {
        const weight = share.get(technique.id) || 0;
        const level = technique.proficiency === null ? 0 : technique.proficiency / 10;
        return el(
          "tr",
          { class: weight ? "" : "is-unused" },
          el("th", { scope: "row" }, technique.name),
          el(
            "td",
            {},
            el(
              "span",
              { class: "dna-bar-cell" },
              el("span", { class: "dna-track" }, el("span", { class: "dna-bar dna-bar-you", style: `width:${Math.round(level * 100)}%` })),
              el("span", { class: "dna-value mono" }, technique.tier || "–")
            )
          ),
          el(
            "td",
            {},
            el(
              "span",
              { class: "dna-bar-cell" },
              el("span", { class: "dna-track" }, weight ? el("span", { class: "dna-bar dna-bar-them", style: `width:${Math.round((weight / peak) * 100)}%` }) : null),
              el("span", { class: "dna-value mono" }, weight ? percent(weight) : "–")
            )
          )
        );
      })
    )
  );
}

function detail(dna, composer) {
  const ready = composer.readiness_tier
    ? `Weighted by what ${surname(composer.name)} asks for most, your tiers average ${composer.readiness_tier} (${composer.readiness.toFixed(1)} of 10).`
    : "You haven't rated the techniques this music asks for.";
  return el(
    "div",
    { class: "dna-detail" },
    el("div", { class: "row", style: "justify-content:space-between;align-items:baseline;gap:var(--space-3)" }, el("h3", { class: "section-title", style: "margin:0" }, composer.name), el("span", { class: "faint mono", style: "font-size:12px" }, composer.label)),
    el("p", { class: "muted", style: "margin:var(--space-2) 0 var(--space-4);font-size:13.5px" }, ready),
    comparison(dna, composer)
  );
}

export async function practiceDnaView(outlet) {
  const host = el("div", {}, skeletonBlock(5));
  outlet.append(host);
  let dna;
  try {
    dna = await api.practiceDna();
  } catch (error) {
    host.replaceChildren(empty(error.detail || "Could not load your practice DNA."));
    return;
  }
  if (!dna.composers.length) {
    host.replaceChildren(empty("The catalogue has no composers with technique data yet."));
    return;
  }

  let selected = dna.closest?.id ?? dna.composers[0].id;
  const list = el("div", { class: "dna-composers", role: "group", "aria-label": "Composers, closest first" });
  const panel = el("div", {});

  function render() {
    list.replaceChildren(...dna.composers.map((composer) => composerButton(composer, composer.id === selected, select)));
    panel.replaceChildren(detail(dna, dna.composers.find((composer) => composer.id === selected)));
  }

  function select(id) {
    selected = id;
    render();
  }

  const headline = el(
    "div",
    { class: "growth-headline" },
    el("p", { class: "dna-summary" }, dna.summary),
    el(
      "p",
      { class: "faint", style: "margin:0;font-size:12.5px" },
      dna.enough
        ? `A rough read. It compares the shape of your tier profile (which of your ${dna.rated} rated techniques are relatively strong or weak) with how each composer's pieces in this catalogue weight those techniques. It says nothing about musicianship, and a composer with one or two pieces here is a thin sample.`
        : "",
      dna.enough ? null : el("a", { href: "/settings/tiers", "data-link": true }, "Take the tier quiz")
    )
  );

  render();
  host.replaceChildren(
    headline,
    el(
      "div",
      { class: "dna-layout" },
      sectionBlock("Composers", { caption: "Closest first. The bar runs from opposite (left) through unrelated (middle) to the same shape as your strengths (right)." }, list),
      sectionBlock("Side by side", {}, panel)
    )
  );
}
