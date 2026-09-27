import { api } from "../api/client.js";
import { formatCountdown, deadline, secondsUntil } from "../lib/countdown.js";
import { el, reveal } from "../lib/dom.js";
import { notify } from "../lib/toast.js";

export function rewardLine(shower) {
  return `+${shower.catch_xp} XP · +${shower.catch_gold} gold now, ×${shower.learn_multiplier} when you learn it`;
}

export async function catchPiece(shower, piece, onDone) {
  try {
    const result = await api.catchMeteor(shower.id, piece.id);
    notify.success(result.xp || result.gold ? `Caught ${piece.title}: +${result.xp} XP, +${result.gold} gold` : `${piece.title} is back in your repertoire`);
    onDone?.();
  } catch (error) {
    notify.error(error.detail || "That meteor got away");
    if (error.status === 410) onDone?.();
  }
}

function pieceRow(shower, piece, onCaught) {
  const state =
    piece.state === "open"
      ? el(
          "button",
          {
            type: "button",
            class: "btn btn-small",
            onclick: async (event) => {
              event.currentTarget.disabled = true;
              await catchPiece(shower, piece, onCaught);
            },
          },
          "Catch"
        )
      : el("span", { class: "faint", style: "font-size:12.5px" }, piece.state === "caught" ? "caught ✓" : "already yours");
  return el(
    "li",
    { class: "flat-row" },
    el(
      "div",
      { style: "min-width:0" },
      el("div", {}, piece.title),
      el("div", { class: "faint", style: "font-size:12px" }, [piece.composer, piece.difficulty !== null ? `difficulty ${Math.round(piece.difficulty)}` : null].filter(Boolean).join(" · "))
    ),
    state
  );
}

export function meteorBanner(view, { onCaught, onExpire } = {}) {
  const shower = view?.active;
  const next = view?.upcoming;
  if (!shower && !next) return { node: null, stop() {} };

  const clock = el("span", { class: "meteor-countdown mono" });
  const until = deadline(shower ? shower.seconds_left : next.seconds_to_start);
  const tick = () => {
    const left = secondsUntil(until);
    clock.textContent = formatCountdown(left);
    if (left <= 0) {
      stop();
      onExpire?.();
    }
  };
  const timer = setInterval(tick, 1000);
  const stop = () => clearInterval(timer);
  tick();

  if (!shower) {
    return {
      node: el("p", { class: "meteor-next faint" }, "☄ Next meteor shower, ", el("strong", { style: "font-weight:500" }, next.name), ", starts in ", clock, "."),
      stop,
    };
  }

  const list = reveal(`Catch from a list (${shower.open} left)`, () =>
    el("ul", { class: "flat-list" }, ...shower.pieces.map((piece) => pieceRow(shower, piece, onCaught)))
  );
  const node = el(
    "section",
    { class: "meteor-banner", "aria-label": "Meteor shower" },
    el(
      "div",
      { class: "meteor-banner-head" },
      el("span", { class: "meteor-icon", "aria-hidden": "true" }, "☄"),
      el(
        "div",
        { style: "min-width:0" },
        el("div", { class: "meteor-title" }, shower.name, el("span", { class: "meteor-ends" }, " · ends in ", clock)),
        el(
          "p",
          { class: "muted", style: "margin:2px 0 0;font-size:13px" },
          shower.open
            ? `${shower.open} bonus piece${shower.open === 1 ? " is" : "s are"} streaking through your sky. Tap one to catch it: ${rewardLine(shower)}.`
            : "You've caught everything in this shower. Caught pieces stay in your repertoire after it ends."
        )
      ),
      el("span", { class: "meteor-count mono" }, `${shower.caught}/${shower.pieces.length} caught`)
    ),
    list.button,
    list.region
  );
  return { node, stop };
}
