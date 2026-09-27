import { api } from "../api/client.js";
import { el, empty, sectionBlock, skeletonBlock } from "../lib/dom.js";
import { renderNotation } from "../lib/notation.js";
import { notify } from "../lib/toast.js";
import { standingsTable } from "./leaderboards.js";

function describe(snippet) {
  return `${snippet.category.replace(/_/g, " ")} · difficulty ${snippet.difficulty.toFixed(1)} · ${snippet.notation.key} major`;
}

function resultView(snippet, attempt) {
  const review = el(
    "ol",
    { class: "roulette-review" },
    ...snippet.questions.map((question, index) => {
      const right = attempt.given?.[index] === attempt.answers?.[index];
      return el(
        "li",
        { class: right ? "review-right" : "review-wrong" },
        el("span", { class: "mono" }, `Bar ${question.measure + 1}`),
        el("span", {}, right ? `${attempt.answers[index]} ✓` : `${attempt.given?.[index] || "—"} → ${attempt.answers[index]}`)
      )
    })
  );
  return el(
    "div",
    { class: "roulette-result" },
    el("div", { class: "growth-headline" }, el("div", { class: "stat" }, String(attempt.score)), el("p", { class: "muted", style: "margin:0" }, `${attempt.correct} of ${attempt.total} notes in ${Math.round(attempt.seconds)}s${attempt.speed_bonus ? ` · +${attempt.speed_bonus} speed bonus` : ""}. Come back tomorrow for a new snippet.`)),
    review
  );
}

export async function rouletteView(outlet) {
  const stage = el("div", {}, skeletonBlock(4));
  const board = el("div", {}, skeletonBlock(3));
  outlet.append(
    el(
      "div",
      { class: "page-head" },
      el("div", {}, el("h1", { style: "margin:0" }, "Sight-reading roulette"), el("p", { class: "muted", style: "margin:4px 0 0" }, "One snippet a day, identical for every pianist. Name the ringed note in each bar, as fast as you can. You get one attempt.")),
      el("a", { class: "btn btn-ghost btn-small", href: "/progress?tab=leaderboards", "data-link": true }, "All leaderboards")
    ),
    sectionBlock("Today's snippet", {}, stage),
    sectionBlock("Today's standings", {}, board)
  );

  async function renderBoard() {
    try {
      board.replaceChildren(standingsTable(await api.rouletteStandings("global"), { detail: (row) => `${row.detail.correct}/${row.detail.total} in ${Math.round(row.detail.seconds)}s` }));
    } catch (error) {
      board.replaceChildren(empty(error.detail || "Could not load standings."));
    }
  }

  function play(snippet) {
    const answers = [];
    let index = 0;
    const score = el("div", { class: "notation-host roulette-notation" });
    const prompt = el("p", { class: "roulette-prompt" });
    const options = el("div", { class: "roulette-options" });
    const counter = el("span", { class: "faint mono" });

    function show() {
      const question = snippet.questions[index];
      score.replaceChildren(renderNotation(snippet.notation, { highlight: { measure: question.measure, note: question.note } }));
      score.querySelector(".notation-highlight")?.scrollIntoView({ block: "nearest", inline: "center" });
      counter.textContent = `${index + 1} of ${snippet.questions.length}`;
      prompt.textContent = `Bar ${question.measure + 1}: which note is ringed?`;
      options.replaceChildren(
        ...question.options.map((option) =>
          el(
            "button",
            {
              type: "button",
              class: "btn roulette-option",
              onclick: () => answer(option),
            },
            option
          )
        )
      );
      options.querySelector("button")?.focus();
    }

    async function answer(option) {
      answers.push(option);
      index += 1;
      if (index < snippet.questions.length) {
        show();
        return;
      }
      options.replaceChildren(el("p", { class: "faint" }, "Scoring…"));
      try {
        const attempt = await api.rouletteSubmit(answers);
        stage.replaceChildren(el("p", { class: "faint", style: "margin:0 0 var(--space-3)" }, describe(snippet)), resultView(snippet, attempt));
        await renderBoard();
      } catch (error) {
        notify.error(error.detail || "Could not submit your answers");
      }
    }

    stage.replaceChildren(
      el("div", { class: "row", style: "justify-content:space-between" }, el("span", { class: "faint" }, describe(snippet)), counter),
      score,
      prompt,
      options
    );
    show();
  }

  try {
    const today = await api.rouletteToday();
    const { snippet, attempt } = today;
    if (attempt?.finished) {
      stage.replaceChildren(el("p", { class: "faint", style: "margin:0 0 var(--space-3)" }, describe(snippet)), resultView(snippet, attempt));
    } else {
      stage.replaceChildren(
        el("p", { class: "muted" }, describe(snippet)),
        el("p", { class: "faint", style: "font-size:12.5px" }, attempt ? "Your timer started when you first opened this. Pick up where you left off." : "The timer starts when you press Start."),
        el(
          "button",
          {
            type: "button",
            class: "btn",
            onclick: async (event) => {
              event.target.disabled = true;
              try {
                const started = await api.rouletteStart();
                play(started.snippet);
              } catch (error) {
                notify.error(error.detail || "Could not start");
                event.target.disabled = false;
              }
            },
          },
          attempt ? "Resume" : "Start"
        )
      );
    }
  } catch (error) {
    stage.replaceChildren(empty(error.detail || "Could not load today's snippet."));
  }
  await renderBoard();
}
