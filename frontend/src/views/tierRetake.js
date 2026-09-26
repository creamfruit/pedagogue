import { api } from "../api/client.js";
import { el, empty, skeletonBlock } from "../lib/dom.js";
import { store } from "../lib/store.js";
import { notify } from "../lib/toast.js";
import { navigate } from "../router.js";
import { savedTiers, tierQuizStep } from "./onboarding.js";

export async function tierRetakeView(outlet) {
  const host = el("div", {}, skeletonBlock(6));
  outlet.append(
    el(
      "div",
      { class: "page-head" },
      el(
        "div",
        {},
        el("h1", { style: "margin:0" }, "Retake the tier quiz"),
        el(
          "p",
          { class: "muted", style: "margin:4px 0 0" },
          "Your current tiers are filled in. Change any you've outgrown; saving updates them in place and re-personalises every piece's difficulty."
        )
      ),
      el("a", { class: "btn btn-ghost btn-small", href: "/settings", "data-link": true }, "Back to settings")
    ),
    el("div", { class: "onboarding" }, host)
  );
  try {
    const [summary, techniques] = await Promise.all([api.onboardingSummary(), api.techniques()]);
    host.replaceChildren(
      tierQuizStep(
        techniques,
        async () => {
          await store.refreshProfile();
          store.setUser(await api.me());
          notify.success("Tiers updated");
          navigate("/settings");
        },
        { initial: savedTiers(summary.techniques), submitLabel: "Save tiers" }
      )
    );
  } catch (error) {
    host.replaceChildren(empty(error.detail || "Could not load your tiers."));
  }
}
