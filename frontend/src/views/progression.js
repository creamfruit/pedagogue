import { api } from "../api/client.js";
import { el, empty, skeletonBlock } from "../lib/dom.js";
import { notify } from "../lib/toast.js";
import { store } from "../lib/store.js";
import { navigate } from "../router.js";

export async function progressionView(outlet) {
  const search = el("input", { type: "search", placeholder: "Which piece do you want to reach?", style: "max-width:360px" });
  const resultHost = el("div", { class: "stack" });
  const recHost = el("section", { class: "panel" }, el("h3", {}, "Saved recommendations"), skeletonBlock(3));

  let debounce;
  const suggestions = el("ul", { class: "list" });

  search.addEventListener("input", () => {
    clearTimeout(debounce);
    const term = search.value.trim();
    if (term.length < 2) {
      suggestions.replaceChildren();
      return;
    }
    debounce = setTimeout(async () => {
      try {
        const pieces = await api.searchPieces(term, 8);
        suggestions.replaceChildren(
          ...pieces.map((piece) =>
            el(
              "li",
              { class: "list-item", style: "cursor:pointer", onclick: () => analyse(piece) },
              el("div", {}, el("div", {}, piece.title), el("div", { class: "faint", style: "font-size:12.5px" }, piece.composer?.name || "unknown")),
              piece.difficulty_score ? el("span", { class: "pill mono" }, piece.difficulty_score) : null
            )
          )
        );
      } catch (error) {
        suggestions.replaceChildren(empty(error.detail || "Search failed."));
      }
    }, 300);
  });

  async function analyse(piece) {
    suggestions.replaceChildren();
    search.value = piece.title;
    resultHost.replaceChildren(skeletonBlock(4));
    try {
      const [prereq, pathway] = await Promise.all([
        api.prerequisites(piece.id, { limit: 5, persist: true }),
        api.pathway(piece.id, { max_steps: 4 }),
      ]);

      const prereqPanel = el(
        "section",
        { class: "panel panel-accent" },
        el("h3", {}, "Prerequisites"),
        prereq.prerequisites.length
          ? el(
              "ul",
              { class: "list" },
              ...prereq.prerequisites.map((item) =>
                el(
                  "li",
                  { class: "list-item", style: "align-items:flex-start;flex-direction:column;gap:6px" },
                  el(
                    "div",
                    { class: "row", style: "justify-content:space-between;width:100%" },
                    el("strong", {}, item.piece.title),
                    el("span", { class: "pill pill-accent mono" }, item.score.toFixed(2))
                  ),
                  el("p", { class: "muted", style: "margin:0;font-size:13.5px" }, item.rationale),
                  el(
                    "div",
                    { class: "row" },
                    ...item.shared_techniques.map((t) => el("span", { class: "pill" }, t))
                  )
                )
              )
            )
          : empty("No prerequisites found. This may already be within reach.")
      );

      resultHost.replaceChildren(buildFlowchart(pathway), prereqPanel);
      await renderRecommendations();
    } catch (error) {
      resultHost.replaceChildren(empty(error.detail || "Could not analyse that piece."));
    }
  }

  function flowNode(order, piece, meta, kind) {
    return el(
      "div",
      { class: "flow-node", dataset: { owned: String(kind === "owned"), target: String(kind === "target") } },
      el("span", { class: "flow-index mono" }, kind === "target" ? "★" : String(order)),
      el(
        "div",
        { style: "flex:1;min-width:0" },
        el(
          "div",
          { class: "row", style: "justify-content:space-between;gap:8px" },
          el("strong", { style: "font-weight:500" }, piece.title),
          el("span", { class: "pill mono" }, piece.difficulty_score ?? "--")
        ),
        el("div", { class: "faint", style: "font-size:12.5px" }, piece.composer?.name || "unknown composer"),
        meta ? el("p", { class: "muted", style: "margin:8px 0 0;font-size:13px" }, meta) : null
      )
    );
  }

  function buildFlowchart(pathway) {
    const panel = el("section", { class: "panel panel-accent" });
    panel.append(
      el("h3", {}, "Prerequisite pathway"),
      el(
        "div",
        { class: "row", style: "justify-content:space-between;margin-bottom:14px" },
        el(
          "span",
          { class: "muted", style: "font-size:13.5px" },
          pathway.out_of_reach
            ? `${pathway.target.title} sits ${pathway.gap} points above your ceiling of ${pathway.comfort_ceiling}. Here is the bridge.`
            : `${pathway.target.title} is within reach of your ceiling of ${pathway.comfort_ceiling}.`
        ),
        el(
          "span",
          { class: `pill ${pathway.out_of_reach ? "pill-warn" : "pill-ok"}` },
          pathway.out_of_reach ? `gap ${pathway.gap}` : "in reach"
        )
      )
    );

    if (!pathway.steps.length) {
      panel.append(
        empty("No stepping stones needed. Add it straight to your repertoire."),
        el(
          "button",
          {
            class: "btn",
            onclick: (event) => adopt(pathway, event.target),
          },
          "Add to repertoire"
        )
      );
      return panel;
    }

    const flow = el("div", { class: "flow" });
    pathway.steps.forEach((step, index) => {
      flow.append(
        flowNode(step.order, step.piece, step.rationale, step.owned ? "owned" : "step")
      );
      flow.append(el("div", { class: "flow-arrow" }));
      if (index === pathway.steps.length - 1) {
        flow.append(flowNode(0, pathway.target, "Your target.", "target"));
      }
    });
    panel.append(flow);

    const pending = pathway.steps.filter((step) => !step.owned).length;
    panel.append(
      el(
        "div",
        { class: "row", style: "margin-top:16px;justify-content:space-between" },
        el(
          "span",
          { class: "faint mono", style: "font-size:11.5px" },
          `${pathway.steps.length} step(s) · ${pending} not yet in your repertoire`
        ),
        el(
          "button",
          { class: "btn", onclick: (event) => adopt(pathway, event.target) },
          "Add entire pathway to learning"
        )
      )
    );
    return panel;
  }

  async function adopt(pathway, button) {
    button.disabled = true;
    const original = button.textContent;
    button.textContent = "Adding";
    try {
      const result = await api.adoptPathway(pathway.target.id, {
        piece_ids: pathway.steps.map((step) => step.piece.id),
        include_target: true,
      });
      notify.success(result.message);
      await store.refreshProfile();
      if (result.created.length) navigate("/repertoire");
    } catch (error) {
      notify.error(error.detail || "Could not add that pathway");
    } finally {
      button.disabled = false;
      button.textContent = original;
    }
  }

  async function renderRecommendations() {
    recHost.replaceChildren(el("h3", {}, "Saved recommendations"));
    try {
      const items = await api.recommendations({ status: "suggested", limit: 20 });
      if (!items.length) {
        recHost.append(empty("Nothing saved yet. Analyse a piece above."));
        return;
      }
      recHost.append(
        el(
          "ul",
          { class: "list" },
          ...items.map((rec) =>
            el(
              "li",
              { class: "list-item" },
              el("div", {}, el("div", {}, rec.recommended_piece.title), el("div", { class: "faint", style: "font-size:12.5px" }, rec.reason || "")),
              el(
                "div",
                { class: "row" },
                el(
                  "button",
                  {
                    class: "btn btn-small",
                    onclick: async () => {
                      try {
                        await api.decideRecommendation(rec.id, "accepted");
                        notify.success("Accepted");
                        await renderRecommendations();
                      } catch (error) {
                        notify.error(error.detail || "Could not update");
                      }
                    },
                  },
                  "Accept"
                ),
                el(
                  "button",
                  {
                    class: "btn btn-small btn-ghost",
                    onclick: async () => {
                      try {
                        await api.decideRecommendation(rec.id, "dismissed");
                        await renderRecommendations();
                      } catch (error) {
                        notify.error(error.detail || "Could not update");
                      }
                    },
                  },
                  "Dismiss"
                )
              )
            )
          )
        )
      );
    } catch (error) {
      recHost.append(empty(error.detail || "Could not load recommendations."));
    }
  }

  outlet.append(
    el("h1", {}, "Progression"),
    el("p", { class: "muted" }, "Pick a piece you want to play and the engine works backwards from it."),
    el("div", { class: "panel", style: "margin-bottom:16px" }, search, suggestions),
    resultHost,
    recHost
  );

  await renderRecommendations();
}
