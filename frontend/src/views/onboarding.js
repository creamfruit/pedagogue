import { api } from "../api/client.js";
import { el, empty, skeletonBlock } from "../lib/dom.js";
import { store } from "../lib/store.js";
import { notify } from "../lib/toast.js";
import { navigate } from "../router.js";

export const LEVELS = [
  { value: "beginner", label: "Beginner", hint: "Just starting, or coming back after a long break" },
  { value: "intermediate", label: "Intermediate", hint: "Comfortable with simple pieces" },
  { value: "advanced", label: "Advanced", hint: "Working on demanding repertoire" },
  { value: "professional", label: "Professional", hint: "Performing or teaching" },
];

const SEARCH_MIN = 2;
const SEARCH_DEBOUNCE_MS = 280;

function difficultyWords(score) {
  const value = Number(score);
  if (!Number.isFinite(value)) return "";
  if (value < 30) return "gentle";
  if (value < 50) return "moderate";
  if (value < 70) return "demanding";
  return "very demanding";
}

function pieceButton(piece, onPick) {
  return el(
    "button",
    { type: "button", class: "quick-piece", "data-piece": piece.id, onclick: () => onPick(piece) },
    el("span", { class: "quick-piece-title" }, piece.title),
    el("span", { class: "quick-piece-meta faint" }, [piece.composer?.name || piece.composer, difficultyWords(piece.difficulty_score)].filter(Boolean).join(" · "))
  );
}

export async function onboardingView(outlet) {
  document.title = "Welcome · Piano Pedagogue";
  let level = null;
  let busy = false;
  const stage = el("div", { class: "quick" });
  outlet.append(stage);

  function dots(active) {
    return el(
      "ol",
      { class: "quick-dots", "aria-label": `Step ${active} of 2` },
      ...[1, 2].map((number) => el("li", { class: number === active ? "is-active" : number < active ? "is-done" : "", "aria-current": number === active ? "step" : null }))
    );
  }

  function levelStep() {
    stage.replaceChildren(
      dots(1),
      el("h1", { class: "quick-title" }, "How would you describe your playing?"),
      el("p", { class: "muted quick-sub" }, "Just a rough idea. You can change it any time."),
      el(
        "div",
        { class: "quick-levels" },
        ...LEVELS.map((item) =>
          el(
            "button",
            {
              type: "button",
              class: "quick-level",
              "data-level": item.value,
              onclick: () => {
                level = item.value;
                pieceStep();
              },
            },
            el("strong", {}, item.label),
            el("span", { class: "faint" }, item.hint)
          )
        )
      )
    );
  }

  async function begin(piece) {
    if (busy) return;
    busy = true;
    stage.classList.add("is-busy");
    try {
      await api.quickStart({ self_level: level, piece_id: piece.id });
      await Promise.all([store.refreshOnboarding(), store.refreshProfile()]);
      navigate("/mission?first=1", { replace: true });
    } catch (error) {
      notify.error(error.detail || "Couldn't start with that piece. Try another.");
      busy = false;
      stage.classList.remove("is-busy");
    }
  }

  async function pieceStep() {
    const list = el("div", { class: "quick-pieces" }, skeletonBlock(3));
    const results = el("div", { class: "quick-pieces", "aria-live": "polite" });
    const search = el("input", { type: "search", class: "quick-search", placeholder: "Or search for a piece", "aria-label": "Search for a piece", autocomplete: "off" });
    const back = el("button", { type: "button", class: "back-btn", onclick: levelStep }, el("span", { "aria-hidden": "true" }, "←"), "Back");
    stage.replaceChildren(
      back,
      dots(2),
      el("h1", { class: "quick-title" }, "Pick one piece to start with"),
      el("p", { class: "muted quick-sub" }, "We'll build your first short mission around it."),
      list,
      search,
      results
    );
    try {
      const found = await api.starterPieces(level);
      list.replaceChildren(...(found.length ? found.map((piece) => pieceButton(piece, begin)) : [empty("No suggestions for that level yet. Search for a piece below.")]));
    } catch (error) {
      list.replaceChildren(empty(error.detail || "Couldn't load suggestions. Search for a piece below."));
    }
    let timer;
    let ticket = 0;
    search.addEventListener("input", () => {
      clearTimeout(timer);
      const term = search.value.trim();
      const mine = ++ticket;
      if (term.length < SEARCH_MIN) {
        results.replaceChildren();
        return;
      }
      timer = setTimeout(async () => {
        try {
          const items = await api.searchPieces(term, 8);
          if (mine !== ticket) return;
          results.replaceChildren(...(items.length ? items.map((piece) => pieceButton(piece, begin)) : [empty("Nothing matched that.")]));
        } catch (error) {
          if (mine === ticket) results.replaceChildren(empty(error.detail || "Search failed."));
        }
      }, SEARCH_DEBOUNCE_MS);
    });
  }

  levelStep();
  return () => {
    document.title = "Piano Pedagogue";
  };
}
