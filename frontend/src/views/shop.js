import { api } from "../api/client.js";
import { el, empty, reveal, sectionBlock, skeletonBlock, tabs } from "../lib/dom.js";
import { drawSkyPreview } from "../lib/skyPreview.js";
import { navigate } from "../router.js";
import { ERA_STYLE, eraGlyph } from "../lib/palette.js";
import { store, subscribe } from "../lib/store.js";
import { notify } from "../lib/toast.js";

const KIND_LABELS = {
  star_color: "Star colour",
  glow: "Glow",
  nebula: "Nebula",
  link_style: "Connectors",
};

const KIND_ORDER = ["star_color", "glow", "nebula", "link_style"];

function preview(cosmetic) {
  const payload = cosmetic.payload || {};
  if (cosmetic.kind === "star_color") {
    if (payload.mode === "era") {
      return el("div", { class: "swatch-row", style: "gap:10px" }, ...Object.keys(ERA_STYLE).map((era) => eraGlyph(era)));
    }
    // Fixed colours are the cosmetic's own purchased data, not app accents.
    const colors =
      payload.mode === "difficulty"
        ? ["var(--pink)", "var(--orange)", "var(--yellow)", "var(--starlight)"]
        : [payload.color || "var(--orange)"];
    return el(
      "div",
      { class: "swatch-row" },
      ...colors.map((color) =>
        el("span", {
          class: "swatch-dot",
          style: `background:${color};box-shadow:0 0 10px ${color}`,
        })
      )
    );
  }
  if (cosmetic.kind === "glow") {
    const scale = payload.scale ?? 1;
    return el(
      "div",
      { class: "swatch-row" },
      el("span", {
        class: "swatch-dot",
        style: `background:var(--orange);box-shadow:0 0 ${Math.round(4 + scale * 12)}px ${Math.round(
          1 + scale * 5
        )}px rgba(var(--orange-rgb),${0.15 + scale * 0.18})`,
      })
    );
  }
  if (cosmetic.kind === "nebula") {
    const layers = payload.layers || [];
    const background = layers.length
      ? layers
          .map(
            (layer) =>
              `radial-gradient(60px 40px at ${layer.x}% ${layer.y}%, rgba(${layer.color},${
                layer.alpha * 4
              }), transparent 70%)`
          )
          .join(",")
      : "none";
    return el("div", {
      class: "swatch-row",
      style: `background-color:var(--bg-sunk);background-image:${background};border-radius:var(--radius);border:1px solid var(--line)`,
    });
  }
  const dash = payload.dash
    ? "repeating-linear-gradient(90deg,var(--orange) 0 5px,transparent 5px 10px)"
    : "var(--orange)";
  return el(
    "div",
    { class: "swatch-row" },
    el("span", {
      class: "swatch-line",
      style: `height:${Math.max(payload.width || 1, 1)}px;background:${dash};opacity:${payload.alpha ?? 1}`,
    })
  );
}

const OBSERVATORY_TABS = [
  { id: "shop", label: "Sky shop" },
  { id: "achievements", label: "Achievements" },
];

export async function shopView(outlet, context = {}) {
  const tab = context.query?.tab === "achievements" ? "achievements" : "shop";
  const walletHost = el("div", { style: "margin-bottom:var(--space-5)" }, skeletonBlock(2));
  const shopHost = el("div", { class: "stack", style: "gap:var(--space-5)" }, skeletonBlock(4));
  const achievementHost = el("div", {}, skeletonBlock(3));
  const previewCanvas = el("canvas", { class: "sky-preview", "aria-hidden": "true" });
  const previewLabel = el("p", { class: "faint", style: "margin:var(--space-2) 0 0;font-size:12.5px" }, "Your equipped sky.");
  const previewPanel = sectionBlock(
    "Your sky",
    { caption: "Hover or focus a cosmetic to try it on before you buy.", className: "sky-preview-panel" },
    previewCanvas,
    previewLabel
  );
  let equipped = {};

  function showPreview(item) {
    const loadout = { ...equipped };
    if (item) loadout[item.kind] = item.payload || {};
    drawSkyPreview(previewCanvas, loadout);
    previewLabel.textContent = item && !item.equipped ? `Previewing ${item.name}.` : "Your equipped sky.";
  }

  const strip = tabs(OBSERVATORY_TABS, tab, (id) => navigate(id === "shop" ? "/observatory" : `/observatory?tab=${id}`, { replace: true }), {
    label: "Observatory sections",
    controls: "observatory-panel",
  });
  const panel = el(
    "div",
    { id: "observatory-panel", role: "tabpanel" },
    tab === "shop" ? el("div", { class: "shop-layout" }, shopHost, previewPanel) : achievementHost
  );

  outlet.append(
    el(
      "div",
      { class: "page-head" },
      el(
        "div",
        {},
        el("h1", { style: "margin:0" }, "Observatory"),
        el("p", { class: "muted", style: "margin:4px 0 0" }, "Spend gold on how your sky looks. Earn it by learning pieces and passing graded runs.")
      )
    ),
    walletHost,
    strip,
    panel
  );

  // The wallet comes from the same store.wallet the header reads, so the two can
  // never disagree. drawWallet only renders; the store subscription below calls
  // it on every change, and renderWallet asks the store to refetch.
  let drawnWallet = null;

  function drawWallet(wallet) {
    if (!wallet) {
      drawnWallet = null;
      walletHost.replaceChildren(empty("Could not load your wallet."));
      return;
    }
    const signature = JSON.stringify(wallet);
    if (signature === drawnWallet) return;
    drawnWallet = signature;
    walletHost.replaceChildren(
      el(
        "section",
        { class: "panel summary-bar", "aria-label": "Your wallet" },
        el(
          "div",
          { class: "summary-cell", style: "display:flex;align-items:center;gap:16px" },
          el("div", { class: "stat-ring" }, el("div", { class: "stat" }, wallet.level)),
          el(
            "div",
            {},
            el("div", { class: "stat-label" }, "Level"),
            el("div", { class: "bar", style: "width:150px;margin:6px 0 4px" }, el("span", { style: `width:${wallet.level_progress * 100}%` })),
            el("div", { class: "faint mono", style: "font-size:11px" }, `${wallet.xp_for_next_level} xp to level ${wallet.level + 1}`)
          )
        ),
        el(
          "div",
          { class: "summary-cell" },
          el("div", { class: "stat-label" }, "Gold"),
          el("div", { class: "stat", style: "color:var(--yellow)" }, wallet.gold.toLocaleString()),
          el("div", { class: "faint mono", style: "font-size:11px" }, `${wallet.lifetime_gold.toLocaleString()} earned in total`)
        ),
        el(
          "div",
          { class: "summary-cell" },
          el("div", { class: "stat-label" }, "Total XP"),
          el("div", { class: "stat" }, wallet.xp.toLocaleString())
        )
      )
    );
  }

  async function renderWallet() {
    await store.refreshProfile();
    drawWallet(store.wallet);
  }

  const unsubscribe = subscribe(() => {
    if (!walletHost.isConnected) {
      unsubscribe();
      return;
    }
    drawWallet(store.wallet);
  });

  async function renderShop() {
    try {
      const cosmetics = await api.shop();
      equipped = Object.fromEntries(cosmetics.filter((item) => item.equipped).map((item) => [item.kind, item.payload || {}]));
      requestAnimationFrame(() => showPreview(null));
      const grouped = new Map();
      cosmetics.forEach((item) => {
        if (!grouped.has(item.kind)) grouped.set(item.kind, []);
        grouped.get(item.kind).push(item);
      });

      shopHost.replaceChildren(
        ...KIND_ORDER.filter((kind) => grouped.has(kind)).map((kind) => {
          const items = grouped.get(kind);
          const equipped = items.find((item) => item.equipped);
          const owned = items.filter((item) => item.owned).length;
          return el(
            "section",
            { class: "shop-section" },
            el("h2", { class: "section-title" }, KIND_LABELS[kind] || kind),
            el(
              "p",
              { class: "section-caption" },
              [equipped ? `Equipped: ${equipped.name}` : null, `${owned} of ${items.length} owned`].filter(Boolean).join(" · ")
            ),
            el("div", { class: "shop-grid" }, ...items.map((item) => card(item)))
          );
        })
      );
    } catch (error) {
      shopHost.replaceChildren(empty(error.detail || "Could not load the shop."));
    }
  }

  function card(item) {
    const locked = !item.unlocked;
    const action = item.equipped
      ? el("span", { class: "pill pill-selected" }, "equipped")
      : item.owned
        ? el(
            "button",
            {
              class: "btn btn-small",
              onclick: async (event) => {
                event.target.disabled = true;
                try {
                  await api.equipCosmetic(item.id);
                  notify.success(`${item.name} equipped`);
                  await store.refreshProfile();
                  await renderShop();
                } catch (error) {
                  notify.error(error.detail || "Could not equip that");
                  event.target.disabled = false;
                }
              },
            },
            "Equip"
          )
        : el(
            "button",
            {
              class: "btn btn-small",
              disabled: locked || !item.affordable,
              onclick: async (event) => {
                event.target.disabled = true;
                try {
                  await api.buyCosmetic(item.id);
                  notify.success(`Bought ${item.name}`);
                  await renderWallet();
                  await renderShop();
                } catch (error) {
                  notify.error(error.detail || "Could not buy that");
                  event.target.disabled = false;
                }
              },
            },
            locked ? `Level ${item.min_level}` : `${item.price_gold.toLocaleString()} gold`
          );

    return el(
      "div",
      {
        class: "panel shop-card",
        tabindex: "-1",
        dataset: { equipped: String(item.equipped), locked: String(locked) },
        onmouseenter: () => showPreview(item),
        onmouseleave: () => showPreview(null),
        onfocusin: () => showPreview(item),
        onfocusout: () => showPreview(null),
      },
      preview(item),
      el(
        "div",
        { class: "shop-card-text" },
        el("div", { style: "font-weight:500" }, item.name),
        el("div", { class: "faint", style: "font-size:12.5px" }, item.description || "")
      ),
      el(
        "div",
        { class: "row", style: "justify-content:space-between;margin-top:auto" },
        action,
        item.price_gold === 0 ? el("span", { class: "faint mono", style: "font-size:11px" }, "free") : null
      )
    );
  }

  function achievementCard(row) {
    const progress = row.progress;
    return el(
      "div",
      { class: "achievement", dataset: { earned: String(row.earned) } },
      el("span", { class: "achievement-mark" }),
      el(
        "div",
        { style: "flex:1;min-width:0" },
        el("div", { style: "font-weight:500" }, row.name),
        el("div", { class: "faint", style: "font-size:12.5px" }, row.description),
        !row.earned && progress
          ? el(
              "div",
              { class: "achievement-progress" },
              el(
                "div",
                {
                  class: "bar",
                  role: "progressbar",
                  "aria-valuemin": "0",
                  "aria-valuemax": "100",
                  "aria-valuenow": String(Math.round(progress.fraction * 100)),
                  "aria-label": `${row.name}: ${progress.label}`,
                },
                el("span", { style: `width:${progress.fraction * 100}%` })
              ),
              el("span", { class: "faint mono" }, progress.label)
            )
          : null,
        el(
          "div",
          { class: "faint mono", style: "font-size:11px;margin-top:5px" },
          row.earned && row.earned_at
            ? `earned ${new Date(row.earned_at).toLocaleDateString()} · +${row.xp_reward} xp · +${row.gold_reward} gold`
            : `+${row.xp_reward} xp · +${row.gold_reward} gold`
        )
      )
    );
  }

  function nextTiers(rows) {
    const bySeries = new Map();
    rows.forEach((row) => {
      if (row.earned || !row.series) return;
      const current = bySeries.get(row.series);
      if (!current || (row.tier ?? 0) < (current.tier ?? 0)) bySeries.set(row.series, row);
    });
    return [...bySeries.values()].sort((a, b) => (b.progress?.fraction ?? 0) - (a.progress?.fraction ?? 0));
  }

  async function renderAchievements() {
    try {
      const rows = await api.achievements();
      const earned = rows.filter((row) => row.earned).length;
      const next = nextTiers(rows).slice(0, 4);
      const all = reveal(`All ${rows.length} achievements`, () => el("div", { class: "shop-grid" }, ...rows.map(achievementCard)));
      achievementHost.replaceChildren(
        sectionBlock(
          "Achievements",
          { caption: `${earned} of ${rows.length} unlocked${next.length ? " · the next tier in each series, closest first" : ""}` },
          el("div", { class: "bar", style: "margin:-6px 0 var(--space-4)" }, el("span", { style: `width:${rows.length ? (earned / rows.length) * 100 : 0}%` })),
          next.length ? el("div", { class: "shop-grid" }, ...next.map(achievementCard)) : null,
          all.button,
          all.region
        )
      );
    } catch (error) {
      achievementHost.replaceChildren(empty(error.detail || "Could not load achievements."));
    }
  }

  await Promise.all([renderWallet(), tab === "shop" ? renderShop() : renderAchievements()]);
  return unsubscribe;
}
