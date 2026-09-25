import { api } from "../api/client.js";
import { el, empty, skeletonBlock } from "../lib/dom.js";
import { ERA_STYLE, eraGlyph } from "../lib/palette.js";
import { store } from "../lib/store.js";
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
        ? ["var(--pink)", "var(--orange)", "var(--yellow)", "var(--text)"]
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
      style: `background-color:var(--black);background-image:${background};border-radius:var(--radius);border:1px solid var(--line)`,
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

export async function shopView(outlet) {
  const walletHost = el("div", { class: "grid", style: "margin-bottom:18px" }, skeletonBlock(2));
  const shopHost = el("div", { class: "stack" }, skeletonBlock(4));
  const achievementHost = el("section", { class: "panel", style: "margin-top:18px" }, skeletonBlock(3));

  outlet.append(
    el("h1", {}, "Observatory"),
    el("p", { class: "muted" }, "Spend gold on how your sky looks. Earn it by learning pieces and passing graded runs."),
    walletHost,
    shopHost,
    achievementHost
  );

  async function renderWallet() {
    try {
      const wallet = await api.wallet();
      walletHost.replaceChildren(
        el(
          "div",
          { class: "panel", style: "display:flex;align-items:center;gap:16px" },
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
          { class: "panel" },
          el("div", { class: "stat-label" }, "Gold"),
          el("div", { class: "stat", style: "color:var(--yellow)" }, wallet.gold.toLocaleString()),
          el("div", { class: "faint mono", style: "font-size:11px" }, `${wallet.lifetime_gold.toLocaleString()} earned in total`)
        ),
        el(
          "div",
          { class: "panel" },
          el("div", { class: "stat-label" }, "Total XP"),
          el("div", { class: "stat" }, wallet.xp.toLocaleString())
        )
      );
    } catch (error) {
      walletHost.replaceChildren(empty(error.detail || "Could not load your wallet."));
    }
  }

  async function renderShop() {
    try {
      const cosmetics = await api.shop();
      const grouped = new Map();
      cosmetics.forEach((item) => {
        if (!grouped.has(item.kind)) grouped.set(item.kind, []);
        grouped.get(item.kind).push(item);
      });

      shopHost.replaceChildren(
        ...KIND_ORDER.filter((kind) => grouped.has(kind)).map((kind) =>
          el(
            "section",
            {},
            el("h3", {}, KIND_LABELS[kind] || kind),
            el(
              "div",
              { class: "shop-grid" },
              ...grouped.get(kind).map((item) => card(item))
            )
          )
        )
      );
    } catch (error) {
      shopHost.replaceChildren(empty(error.detail || "Could not load the shop."));
    }
  }

  function card(item) {
    const locked = !item.unlocked;
    const action = item.equipped
      ? el("span", { class: "pill pill-accent" }, "equipped")
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
                  await store.refreshProfile();
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
        dataset: { equipped: String(item.equipped), locked: String(locked) },
      },
      preview(item),
      el("div", { style: "font-weight:500" }, item.name),
      el("div", { class: "faint", style: "font-size:12.5px;flex:1" }, item.description || ""),
      el("div", { class: "row", style: "justify-content:space-between" }, action, item.price_gold === 0 ? el("span", { class: "pill" }, "free") : null)
    );
  }

  async function renderAchievements() {
    achievementHost.replaceChildren(el("h3", {}, "Achievements"));
    try {
      const rows = await api.achievements();
      const earned = rows.filter((row) => row.earned).length;
      achievementHost.append(
        el("p", { class: "faint mono", style: "font-size:11.5px" }, `${earned} of ${rows.length} unlocked`),
        el(
          "div",
          { class: "shop-grid" },
          ...rows.map((row) =>
            el(
              "div",
              { class: "achievement", dataset: { earned: String(row.earned) } },
              el("span", { class: "achievement-mark" }),
              el(
                "div",
                {},
                el("div", { style: "font-weight:500" }, row.name),
                el("div", { class: "faint", style: "font-size:12.5px" }, row.description),
                el(
                  "div",
                  { class: "faint mono", style: "font-size:11px;margin-top:5px" },
                  `+${row.xp_reward} xp · +${row.gold_reward} gold`
                )
              )
            )
          )
        )
      );
    } catch (error) {
      achievementHost.append(empty(error.detail || "Could not load achievements."));
    }
  }

  await Promise.all([renderWallet(), renderShop(), renderAchievements()]);
}
