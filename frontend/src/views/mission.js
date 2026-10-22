import { api } from "../api/client.js";
import { streakGauge } from "../components/streakGauge.js";
import { segmentPaths, segmentStates } from "../lib/arc.js";
import { el } from "../lib/dom.js";
import { KIND_LABEL, completeStep, loadMission, missionDone } from "../lib/mission.js";
import { markGuestPrompted, shouldPromptGuest } from "../lib/guestPrompt.js";
import { stepComplete, starLit } from "../lib/haptics.js";
import { rememberLit } from "../lib/litStars.js";
import { MAX_BPM, MIN_BPM, clampBpm, createMetronome } from "../lib/metronome.js";
import { reducedMotion } from "../lib/motion.js";
import { renderNotation } from "../lib/notation.js";
import { store } from "../lib/store.js";
import { notify } from "../lib/toast.js";
import { keepAwake } from "../lib/wakeLock.js";
import { navigate } from "../router.js";

const SVG = "http://www.w3.org/2000/svg";
const EARLY_SECONDS = 20;
const CONFIRM_MS = 3000;
const ARMED_MS = 900;
const BPM_STEP = 4;
const METRONOME_KEY = "pp.mission.metronome";
const METRONOME_DEFAULT = { warmup: true, passage: true, review: true, playthrough: false, freeplay: false };

function svg(tag, attrs = {}) {
  const node = document.createElementNS(SVG, tag);
  Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, String(value)));
  return node;
}

export function clock(seconds) {
  const whole = Math.max(0, Math.floor(seconds));
  return `${String(Math.floor(whole / 60)).padStart(2, "0")}:${String(whole % 60).padStart(2, "0")}`;
}

function savedMetronomePreference() {
  try {
    const value = localStorage.getItem(METRONOME_KEY);
    return value === "on" ? true : value === "off" ? false : null;
  } catch {
    return null;
  }
}

function rememberMetronomePreference(on) {
  try {
    localStorage.setItem(METRONOME_KEY, on ? "on" : "off");
  } catch {
    return;
  }
}

const STAR_PATH = "M0 -20 L5.2 -6.2 L20 0 L5.2 6.2 L0 20 L-5.2 6.2 L-20 0 L-5.2 -6.2 Z";
const SPARKS = 8;

export function starBurst() {
  const node = svg("svg", { class: "star-burst", viewBox: "-40 -40 80 80", "aria-hidden": "true" });
  for (let index = 0; index < SPARKS; index += 1) {
    const angle = (index / SPARKS) * Math.PI * 2;
    const spark = svg("circle", { class: "star-burst-spark", cx: 0, cy: 0, r: 1.6 });
    spark.style.setProperty("--dx", `${(Math.cos(angle) * 32).toFixed(1)}px`);
    spark.style.setProperty("--dy", `${(Math.sin(angle) * 32).toFixed(1)}px`);
    node.append(spark);
  }
  node.append(svg("circle", { class: "star-burst-halo", cx: 0, cy: 0, r: 16 }), svg("path", { class: "star-burst-star", d: STAR_PATH }));
  return node;
}

export function progressArc(steps, progress, activeIndex) {
  const states = segmentStates(steps.length, progress, activeIndex);
  const finished = progress.length;
  const node = svg("svg", { class: "mission-arc", viewBox: "0 0 56 56", role: "img", "aria-label": `Step ${Math.min(activeIndex + 1, steps.length)} of ${steps.length}, ${finished} finished` });
  segmentPaths(steps.length).forEach((path, index) => {
    node.append(svg("path", { d: path, class: `mission-arc-seg is-${states[index]}`, fill: "none" }));
  });
  const label = svg("text", { x: 28, y: 33, "text-anchor": "middle", class: "mission-arc-label" });
  label.textContent = `${Math.min(activeIndex + 1, steps.length)}/${steps.length}`;
  node.append(label);
  return node;
}

async function loadVisual(step) {
  if (step.passage_id && step.piece_id) {
    try {
      const overview = await api.pieceOverview(step.piece_id);
      const section = (overview.sections || []).find((item) => item.id === step.passage_id);
      if (section?.score_crop) {
        const blob = await api.blob(section.score_crop);
        return { kind: "image", url: URL.createObjectURL(blob), alt: `${step.bars} of ${step.piece_title}, from your score` };
      }
    } catch {
      /* fall through to a pattern */
    }
    try {
      const notation = await api.passageSightReading(step.passage_id, step.technique_id || undefined);
      return { kind: "notation", notation };
    } catch {
      return { kind: "text" };
    }
  }
  return { kind: "text" };
}

function visualBlock(step) {
  const frame = el("div", { class: "mission-visual", "data-control": "visual" });
  const text = () => {
    const lines = [];
    if (step.bars) lines.push(el("p", { class: "mission-visual-bars" }, `${step.piece_title}, ${step.bars}`));
    else if (step.piece_title) lines.push(el("p", { class: "mission-visual-bars" }, step.piece_title));
    if (step.technique) lines.push(el("p", { class: "mission-visual-bars" }, step.technique));
    const guide = step.cue || step.mechanic;
    if (guide) lines.push(el("p", { class: "mission-visual-cue" }, guide));
    frame.replaceChildren(el("div", { class: "mission-visual-text" }, ...lines));
  };
  if (!step.passage_id) {
    text();
    return { frame, dispose: () => {} };
  }
  frame.replaceChildren(el("p", { class: "faint mission-visual-wait" }, "Finding your score…"));
  let url = null;
  let alive = true;
  loadVisual(step).then((found) => {
    if (!alive) {
      if (found.url) URL.revokeObjectURL(found.url);
      return;
    }
    if (found.kind === "image") {
      url = found.url;
      frame.replaceChildren(el("img", { class: "mission-score", src: found.url, alt: found.alt }), step.cue ? el("p", { class: "mission-visual-cue" }, step.cue) : null);
    } else if (found.kind === "notation") {
      frame.replaceChildren(
        el("div", { class: "mission-notation" }, renderNotation(found.notation)),
        el("p", { class: "faint mission-visual-note" }, `A pattern in the style of ${step.bars}. Upload your score to see the page itself.`),
        step.cue ? el("p", { class: "mission-visual-cue" }, step.cue) : null
      );
    } else {
      text();
    }
  });
  return {
    frame,
    dispose: () => {
      alive = false;
      if (url) URL.revokeObjectURL(url);
    },
  };
}

export async function missionView(outlet, context = {}) {
  document.title = "Mission · Piano Pedagogue";
  document.body.classList.add("immersive");
  const root = el("div", { class: "mission-screen", tabindex: "-1" });
  outlet.append(root);

  const metronome = createMetronome({
    onBeat: (index) => {
      const dot = root.querySelector(".mission-beat");
      if (!dot) return;
      dot.dataset.accent = index === 0 ? "1" : "0";
      dot.classList.toggle("is-on", index >= 0);
      if (index >= 0) setTimeout(() => dot.classList.remove("is-on"), 90);
    },
  });
  let releaseAwake = null;
  let ticker = null;
  let disposeVisual = () => {};
  let transition = null;
  let alive = true;

  function stopTicker() {
    clearInterval(ticker);
    ticker = null;
  }

  function cleanup() {
    alive = false;
    stopTicker();
    metronome.stop();
    disposeVisual();
    clearTimeout(transition);
    if (releaseAwake) releaseAwake();
    releaseAwake = null;
    document.body.classList.remove("immersive");
    document.title = "Piano Pedagogue";
  }

  function frame(mission, activeIndex, { skip } = {}) {
    const close = el("button", { type: "button", class: "mission-icon-btn", "data-control": "close", "aria-label": "Leave the mission, your progress is saved", onclick: () => navigate("/") }, "×");
    const header = el(
      "header",
      { class: "mission-head" },
      close,
      progressArc(mission.steps, mission.progress, activeIndex),
      skip || el("span", { class: "mission-head-spacer" })
    );
    return header;
  }

  function show(...nodes) {
    root.replaceChildren(...nodes.filter(Boolean));
    root.focus({ preventScroll: true });
  }

  async function beginMission(mission) {
    if (!releaseAwake) releaseAwake = await keepAwake();
    runStep(mission, mission.next_index ?? 0);
  }

  function intro(mission) {
    const resuming = mission.progress.length > 0;
    const start = () => beginMission(mission);
    root.onclick = (event) => {
      if (!event.target.closest("[data-control]")) start();
    };
    root.onkeydown = (event) => {
      if (event.target === root && (event.key === " " || event.key === "Enter")) start();
    };
    const first = mission.kind === "first";
    show(
      frame(mission, mission.next_index ?? 0),
      el(
        "div",
        { class: "mission-intro" },
        el("p", { class: "mission-kicker" }, first ? "Your first mission" : resuming ? "Welcome back" : "Today's mission"),
        el("h1", { class: "mission-title" }, `${mission.steps.length} steps, about ${mission.total_minutes} minutes`),
        el("ol", { class: "mission-steps mission-steps-plain" }, ...mission.steps.map((step) => el("li", {}, el("strong", {}, KIND_LABEL[step.kind] || step.title), el("span", { class: "faint" }, ` · ${step.minutes} min`)))),
        el("p", { class: "mission-hint" }, "Prop your phone on the music stand. Tap anywhere to move on, whenever you're ready.")
      ),
      el("div", { class: "mission-foot" }, el("span", { class: "mission-tap" }, resuming ? "Tap anywhere to continue" : "Tap anywhere to begin"))
    );
  }

  function runStep(mission, index) {
    if (!alive) return;
    const step = mission.steps[index];
    if (!step) return finish(mission);
    stopTicker();
    metronome.stop();
    disposeVisual();
    const startedAt = performance.now();
    let confirmUntil = 0;
    let paused = false;
    let pausedAt = 0;
    let pausedTotal = 0;
    const elapsed = () => ((paused ? pausedAt : performance.now()) - startedAt - pausedTotal) / 1000;
    const planned = step.minutes * 60;

    const wanted = savedMetronomePreference();
    const metronomeOn = wanted === null ? METRONOME_DEFAULT[step.kind] !== false : wanted;
    metronome.setBpm(step.tempo_bpm || 72);

    const timer = el("div", { class: "mission-timer", role: "timer", "aria-live": "off" }, "00:00");
    const target = el("div", { class: "mission-timer-target" }, `of ${clock(planned)}`);
    const note = el("p", { class: "mission-note", role: "status", "aria-live": "polite" }, "Tap anywhere when you're done");
    const bpmValue = el("output", { class: "mission-bpm-value", "aria-live": "polite" }, String(metronome.bpm));
    const beat = el("span", { class: "mission-beat", "aria-hidden": "true" });
    const toggle = el("button", { type: "button", class: "mission-metro-toggle", "data-control": "metronome", "aria-pressed": "false", "aria-label": "Metronome" }, "Start");

    function setMetronome(on, remember) {
      if (on) {
        if (!metronome.start()) {
          notify.info("Your device blocked the metronome sound. Tap Start to try again.");
          on = false;
        }
      } else {
        metronome.stop();
      }
      toggle.setAttribute("aria-pressed", on ? "true" : "false");
      toggle.textContent = on ? "Stop" : "Start";
      toggle.classList.toggle("is-on", on);
      if (remember) rememberMetronomePreference(on);
    }

    function nudge(delta) {
      metronome.setBpm(clampBpm(metronome.bpm + delta));
      bpmValue.textContent = String(metronome.bpm);
    }

    const minus = el("button", { type: "button", class: "mission-metro-step", "data-control": "slower", "aria-label": `Slower, now ${metronome.bpm} beats per minute`, disabled: metronome.bpm <= MIN_BPM, onclick: () => nudge(-BPM_STEP) }, "−");
    const plus = el("button", { type: "button", class: "mission-metro-step", "data-control": "faster", "aria-label": `Faster, now ${metronome.bpm} beats per minute`, disabled: metronome.bpm >= MAX_BPM, onclick: () => nudge(BPM_STEP) }, "+");
    const refreshLimits = () => {
      minus.disabled = metronome.bpm <= MIN_BPM;
      plus.disabled = metronome.bpm >= MAX_BPM;
      minus.setAttribute("aria-label", `Slower, now ${metronome.bpm} beats per minute`);
      plus.setAttribute("aria-label", `Faster, now ${metronome.bpm} beats per minute`);
    };
    minus.addEventListener("click", refreshLimits);
    plus.addEventListener("click", refreshLimits);
    toggle.addEventListener("click", () => setMetronome(!metronome.running, true));

    const pause = el("button", { type: "button", class: "mission-icon-btn", "data-control": "pause", "aria-label": "Pause the timer" }, "II");
    pause.addEventListener("click", () => {
      paused = !paused;
      if (paused) {
        pausedAt = performance.now();
        pause.textContent = "▶";
        pause.setAttribute("aria-label", "Resume the timer");
      } else {
        pausedTotal += performance.now() - pausedAt;
        pause.textContent = "II";
        pause.setAttribute("aria-label", "Pause the timer");
      }
    });

    const skip = el("button", { type: "button", class: "mission-skip", "data-control": "skip", onclick: () => finishStep(mission, index, "skipped", 0) }, "Skip");
    const visual = visualBlock(step);
    disposeVisual = visual.dispose;

    const metronomePanel = el(
      "div",
      { class: "mission-metro", "data-control": "metro-panel" },
      minus,
      el("div", { class: "mission-bpm" }, bpmValue, el("span", { class: "mission-bpm-unit" }, "BPM"), beat),
      plus,
      toggle
    );

    show(
      frame(mission, index, { skip }),
      el(
        "div",
        { class: `mission-stage kind-${step.kind}` },
        el(
          "div",
          { class: "mission-copy" },
          el("p", { class: "mission-kicker" }, [KIND_LABEL[step.kind] || step.title, step.piece_title, step.bars].filter(Boolean).join(" · ")),
          el("p", { class: "mission-why" }, step.why)
        ),
        visual.frame,
        el("div", { class: "mission-side" }, el("div", { class: "mission-timer-wrap" }, timer, target, pause), metronomePanel)
      ),
      el("div", { class: "mission-foot" }, note)
    );

    setMetronome(metronomeOn, false);

    ticker = setInterval(() => {
      const seconds = elapsed();
      timer.textContent = clock(seconds);
      if (seconds >= planned) {
        timer.classList.add("is-over");
        note.textContent = "That's the time. Tap anywhere when you're ready.";
      }
    }, 250);

    const tap = (event) => {
      if (event.target.closest("[data-control]")) return;
      if (performance.now() - startedAt < ARMED_MS) return;
      const seconds = elapsed();
      if (seconds < EARLY_SECONDS && performance.now() > confirmUntil) {
        confirmUntil = performance.now() + CONFIRM_MS;
        note.textContent = "Tap again to finish early";
        return;
      }
      finishStep(mission, index, "done", seconds);
    };
    root.onclick = tap;
    root.onkeydown = (event) => {
      if (event.target === root && (event.key === " " || event.key === "Enter")) tap(event);
    };
  }

  async function finishStep(mission, index, status, seconds) {
    if (!alive) return;
    root.onclick = null;
    root.onkeydown = null;
    stopTicker();
    metronome.stop();
    let result;
    try {
      result = await completeStep(mission, index, { status, seconds });
    } catch (error) {
      notify.error(error.detail || "Couldn't save that step. Check your connection and try again.");
      runStep(mission, index);
      return;
    }
    if (!alive) return;
    if (status === "done") stepComplete();
    if (result.finished) return finish(result.mission, result);
    const next = result.mission.next_index ?? index + 1;
    if (status === "done") interlude(result, () => runStep(result.mission, next));
    else runStep(result.mission, next);
  }

  function interlude(result, proceed) {
    const go = () => {
      clearTimeout(transition);
      root.onclick = null;
      proceed();
    };
    root.onclick = go;
    if (result.lit?.entry_id) rememberLit(result.lit.entry_id);
    starLit();
    show(
      el(
        "div",
        { class: `mission-interlude${reducedMotion() ? " is-still" : ""}` },
        starBurst(),
        el("p", { class: "mission-title" }, "Step done"),
        el("p", { class: "mission-hint" }, result.lit?.piece_title ? `${result.lit.piece_title} is brighter in your sky.` : "A star lit in your sky.")
      )
    );
    transition = setTimeout(go, reducedMotion() ? 1100 : 1500);
  }

  function guestCard() {
    const card = el(
      "section",
      { class: "guest-card", "data-control": "guest-card" },
      el("strong", {}, "Keep your progress"),
      el("p", { class: "mission-hint" }, "Create a free account and your pieces, stars and streak are saved, even if you change phone."),
      el(
        "div",
        { class: "guest-card-actions" },
        el("button", { type: "button", class: "btn", "data-control": "guest-create", onclick: () => navigate("/register") }, "Create an account"),
        el("button", { type: "button", class: "btn btn-ghost", "data-control": "guest-later", onclick: () => card.remove() }, "Maybe later")
      )
    );
    return card;
  }

  async function finish(mission, result = null) {
    if (releaseAwake) releaseAwake();
    releaseAwake = null;
    root.onclick = null;
    store.refreshProfile();
    if (result?.lit?.entry_id) {
      rememberLit(result.lit.entry_id);
      starLit();
    }
    const done = mission.progress.filter((item) => item.status === "done").length;
    const prompt = done > 0 && shouldPromptGuest(store.user) ? guestCard() : null;
    if (prompt) markGuestPrompted();
    show(
      el(
        "div",
        { class: `mission-complete${reducedMotion() ? " is-still" : ""}` },
        done ? starBurst() : el("div", { class: "mission-done-mark", "aria-hidden": "true" }, "✓"),
        el("h1", { class: "mission-title" }, done ? "Mission complete" : "That's today's mission"),
        result?.streak ? streakGauge(result.streak, { compact: true }) : null,
        el("p", { class: "mission-hint" }, done ? `${done} of ${mission.steps.length} steps done${result?.xp ? `, +${result.xp} xp` : ""}.` : "No pressure. Tomorrow's mission will be ready."),
        prompt,
        el(
          "div",
          { class: "mission-complete-actions" },
          el("a", { class: "btn mission-start", href: "/constellation", "data-link": true }, "See your sky"),
          el("a", { class: "btn btn-ghost", href: "/", "data-link": true }, "Back to Today")
        )
      )
    );
  }

  let mission;
  try {
    mission = await loadMission({ first: context.query?.first === "1" });
  } catch (error) {
    show(
      el(
        "div",
        { class: "mission-intro" },
        el("h1", { class: "mission-title" }, "Today's mission isn't ready"),
        el("p", { class: "mission-hint" }, error.detail || "Check your connection and try again."),
        el("a", { class: "btn", href: "/", "data-link": true }, "Back to Today")
      )
    );
    return cleanup;
  }
  if (missionDone(mission)) {
    navigate("/", { replace: true });
    return cleanup;
  }
  intro(mission);
  return cleanup;
}
