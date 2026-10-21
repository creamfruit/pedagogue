import { el } from "../lib/dom.js";
import { canUse } from "../lib/plan.js";
import { isNative } from "../lib/platform.js";
import { shareCard } from "../lib/shareCards.js";
import { notify } from "../lib/toast.js";
import { showUpgrade } from "./upgradePrompt.js";

export function shareCardButton({ label = "Share card", build, className = "btn btn-ghost btn-small" }) {
  const locked = !canUse("share_cards");
  const button = el("button", { type: "button", class: className, "data-share-card": "" }, locked ? `${label} · Pro` : label);
  button.addEventListener("click", async () => {
    if (!canUse("share_cards")) return showUpgrade("share_cards");
    button.disabled = true;
    try {
      const { canvas, copy } = await build();
      const result = await shareCard(canvas, copy);
      if (result === "downloaded") notify.success("Saved the card as an image");
      else if (result === "shared" && !isNative) notify.success("Shared");
    } catch (error) {
      notify.error(error.message || "Could not make the card");
    } finally {
      button.disabled = false;
    }
  });
  return button;
}
