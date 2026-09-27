import { el } from "./dom.js";
import { playEvents } from "./piano.js";
import { renderScore } from "./score.js";

const BASE = `${import.meta.env.BASE_URL || "/"}excerpts/`;
let indexPromise = null;

export function loadExcerpts() {
  if (!indexPromise) {
    indexPromise = fetch(`${BASE}index.json`)
      .then((response) => {
        if (!response.ok) throw new Error("Example library is missing");
        return response.json();
      })
      .catch((error) => {
        indexPromise = null;
        throw error;
      });
  }
  return indexPromise;
}

export async function excerptsFor(techniqueName) {
  const index = await loadExcerpts();
  const ids = index.techniques[techniqueName] || [];
  return ids.map((id) => index.excerpts[id]).filter(Boolean).map((excerpt) => ({ ...excerpt, sourceInfo: index.sources[excerpt.source.kind] }));
}

function barLabel(excerpt) {
  const [first, last] = excerpt.bars;
  const span = first === last ? `bar ${first}` : `bars ${first}–${last}`;
  return excerpt.approx_bars ? `around ${span}` : span;
}

function handLabel(hand) {
  return { right: "right hand", left: "left hand", both: "both hands" }[hand] || "";
}

function checkLabel(excerpt) {
  if (excerpt.manual_check) return excerpt.manual_check;
  const agreeing = (excerpt.checks || []).filter((check) => check.match >= 0.9);
  if (agreeing.length) return agreeing.length > 1 ? "Notes match two independent editions" : "Notes match a second, independent edition";
  return "From one edition; not yet cross-checked";
}

export function excerptView(excerpt, { onPlayStateChange } = {}) {
  const scoreHost = el("div", { class: "excerpt-score" }, el("p", { class: "faint excerpt-status" }, "Engraving the score…"));
  const progress = el("div", { class: "excerpt-progress", "aria-hidden": "true" }, el("span"));
  let playback = null;

  const play = el(
    "button",
    {
      type: "button",
      class: "btn btn-small excerpt-play",
      "aria-pressed": "false",
      onclick: () => {
        if (playback) {
          stop();
          return;
        }
        play.textContent = "Loading piano…";
        play.setAttribute("aria-pressed", "true");
        const bar = progress.firstChild;
        playback = playEvents(excerpt.events, {
          tempo: excerpt.tempo,
          onStart: () => {
            play.textContent = "Stop";
          },
          onProgress: (beat) => {
            bar.style.width = `${Math.min(100, (beat / excerpt.length) * 100)}%`;
          },
          onDone: () => stop(),
        });
        if (onPlayStateChange) onPlayStateChange(true, stop);
      },
    },
    "Play"
  );

  function stop() {
    if (playback) playback.stop();
    playback = null;
    play.textContent = "Play";
    play.setAttribute("aria-pressed", "false");
    progress.firstChild.style.width = "0%";
    if (onPlayStateChange) onPlayStateChange(false, stop);
  }

  const meta = [excerpt.composer, barLabel(excerpt), handLabel(excerpt.hand), excerpt.marking].filter(Boolean).join(" · ");
  const node = el(
    "article",
    { class: "excerpt" },
    el(
      "header",
      { class: "excerpt-head" },
      el("div", {}, el("strong", { class: "excerpt-title" }, excerpt.title), el("div", { class: "faint mono excerpt-meta" }, meta)),
      play
    ),
    el("p", { class: "excerpt-note" }, excerpt.note),
    scoreHost,
    progress,
    el(
      "p",
      { class: "faint excerpt-source" },
      `${checkLabel(excerpt)} · ${excerpt.source.edition}${excerpt.sourceInfo ? ` (${excerpt.sourceInfo.license})` : ""} · played at ♩ = ${excerpt.tempo} on a sampled Yamaha grand`
    )
  );

  renderScore(scoreHost, `${BASE}${excerpt.score}`).catch(() => {
    scoreHost.replaceChildren(el("p", { class: "faint excerpt-status" }, "The score could not be drawn here, but you can still listen."));
  });

  return { node, stop };
}

export function excerptPanel(excerpts) {
  const host = el("div", { class: "excerpt-panel" });
  let current = null;
  const stopCurrent = () => current?.stop();

  if (!excerpts.length) {
    host.append(el("p", { class: "faint" }, "No verified excerpt for this technique yet."));
    return { node: host, stop: stopCurrent };
  }

  const stage = el("div");
  const show = (index) => {
    stopCurrent();
    current = excerptView(excerpts[index]);
    stage.replaceChildren(current.node);
    tabs.forEach((tab, tabIndex) => tab.setAttribute("aria-selected", tabIndex === index ? "true" : "false"));
  };
  const tabs = excerpts.map((excerpt, index) =>
    el(
      "button",
      { type: "button", role: "tab", class: "excerpt-tab", "aria-selected": "false", onclick: () => show(index) },
      excerpt.title.split(",")[0]
    )
  );
  if (tabs.length > 1) host.append(el("div", { class: "excerpt-tabs", role: "tablist" }, ...tabs));
  host.append(stage);
  show(0);
  return { node: host, stop: stopCurrent };
}
