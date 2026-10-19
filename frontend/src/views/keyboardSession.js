import { api as realApi } from "../api/client.js";
import { barsFromTally, heatStrip } from "../components/heatStrip.js";
import { el, reveal } from "../lib/dom.js";
import { createRun as realCreateRun } from "../lib/keyboardRun.js";
import { noteName } from "../lib/midi.js";
import { notify } from "../lib/toast.js";

const LATENCY_KEY = "pp.midi-latency";
const FREE_MAX_SECONDS = 120;
const BEAT_CHOICES = [2, 3, 4, 5, 6, 7, 9, 12];

export const NOTE_CHECKING_UNAVAILABLE = "Note checking isn't available for this piece, so free play can only measure how evenly you play against the metronome.";

const MODES = [
  ["scored", "Play along with the metronome", "Scores the notes, the timing against the tempo and how even you are."],
  ["wait", "Wait for me", "The music only moves on when you play the right notes. No timing."],
  ["free", "Free play against the metronome", "Play anything you like. This only measures how evenly you keep time with the click; it can't check notes."],
];

function storedLatency() {
  try {
    return Number(localStorage.getItem(LATENCY_KEY)) || 0;
  } catch {
    return 0;
  }
}

function rememberLatency(value) {
  try {
    localStorage.setItem(LATENCY_KEY, String(value));
  } catch {
    return;
  }
}

function percent(value) {
  return value === null || value === undefined ? "—" : `${Math.round(value)}`;
}

function stat(label, value, unit = "") {
  return el("div", { class: "keyboard-stat" }, el("span", { class: "stat", style: "font-size:22px" }, `${value}${value === "—" ? "" : unit}`), el("span", { class: "stat-label" }, label));
}

export function keyboardSession({ controller, api = realApi, createRun = realCreateRun } = {}) {
  let reference = null;
  let notesInfo = null;
  let run = null;
  let busy = false;
  let manualTempo = false;
  let ladder = null;
  let chosenMode = null;

  const entrySelect = el("select", { "aria-label": "Piece to practise" }, el("option", { value: "" }, "Loading your pieces…"));
  const info = el("p", { class: "keyboard-message faint", role: "status", hidden: true });
  const modeSelect = el("select", { "aria-label": "How to play" });
  const modeHint = el("p", { class: "faint", style: "margin:0;font-size:12px" });
  const passageSelect = el("select", { "aria-label": "Passage" });
  const fromInput = el("input", { type: "number", min: "0", value: "1", class: "keyboard-bar", "aria-label": "First bar" });
  const toInput = el("input", { type: "number", min: "0", value: "4", class: "keyboard-bar", "aria-label": "Last bar" });
  const barsRow = el("div", { class: "row" }, el("span", { class: "faint", style: "font-size:12px" }, "Bars"), fromInput, el("span", { class: "faint" }, "to"), toInput);
  const passageBox = el("div", { class: "keyboard-options" }, passageSelect, barsRow);
  const tempoInput = el("input", { type: "number", min: "20", max: "400", value: "80", class: "keyboard-bar", "aria-label": "Tempo in beats per minute" });
  const ladderBox = el("input", { type: "checkbox", checked: true });
  const ladderNote = el("p", { class: "faint keyboard-ladder", style: "margin:0;font-size:12px" });
  const beatsSelect = el("select", { "aria-label": "Beats per bar" }, ...BEAT_CHOICES.map((beats) => el("option", { value: beats, selected: beats === 4 || null }, `${beats} beats per bar`)));
  const countIn = el("select", { "aria-label": "Count-in beats" }, ...[0, 2, 3, 4, 6, 8].map((beats) => el("option", { value: beats, selected: beats === 4 || null }, beats ? `${beats} beat count-in` : "No count-in")));
  const latency = el("input", { type: "number", min: "-200", max: "300", step: "5", value: String(storedLatency()), class: "keyboard-bar", "aria-label": "Keyboard delay in milliseconds" });
  const start = el("button", { type: "button", class: "btn" }, "Start");
  const stop = el("button", { type: "button", class: "btn btn-ghost", hidden: true }, "Stop");
  const status = el("p", { class: "keyboard-status", role: "status", "aria-live": "polite" });
  const strip = heatStrip();
  const result = el("div", { class: "keyboard-result", hidden: true });
  const tempoRow = el("div", { class: "row" }, el("span", { class: "faint", style: "font-size:12px" }, "Tempo ♩ ="), tempoInput, el("label", { class: "check-label" }, ladderBox, "Raise it after clean runs"));
  const advanced = reveal(
    "Count-in and keyboard delay",
    el(
      "div",
      { class: "keyboard-advanced" },
      countIn,
      el("label", { class: "row faint", style: "font-size:12px" }, "Keyboard delay (ms)", latency),
      el("p", { class: "faint", style: "margin:0;font-size:12px" }, "If notes always seem to land a little late, set the delay of your keyboard or Bluetooth connection here and it is taken off every note.")
    )
  );
  const advancedBox = el("div", {}, advanced.button, advanced.region);
  const controls = [entrySelect, modeSelect, passageSelect, fromInput, toInput, tempoInput, ladderBox, beatsSelect, countIn, latency];

  function currentMode() {
    return modeSelect.value;
  }

  function hasReference() {
    return Boolean(reference && reference.available);
  }

  function canStart() {
    if (!entrySelect.value || !reference) return false;
    return currentMode() === "free" || hasReference();
  }

  function refreshControls() {
    start.disabled = busy || !canStart();
    controls.forEach((control) => {
      control.disabled = busy;
    });
    modeSelect.disabled = busy || !reference;
  }

  function setBusy(value) {
    busy = value;
    start.hidden = value;
    stop.hidden = !value;
    refreshControls();
  }

  function range() {
    const choice = passageSelect.value;
    if (choice === "whole") return { start: reference.first_bar, end: reference.last_bar, passage: null };
    if (choice === "custom") return { start: Number(fromInput.value), end: Number(toInput.value), passage: null };
    const pick = reference.passages.find((item) => String(item.id) === choice);
    return { start: pick.start_bar, end: pick.end_bar, passage: pick.id };
  }

  function offeredModes() {
    return hasReference() ? MODES : MODES.filter(([value]) => value === "free");
  }

  function syncModes() {
    const offered = offeredModes();
    modeSelect.replaceChildren(...offered.map(([value, label]) => el("option", { value }, label)));
    modeSelect.value = offered.some(([value]) => value === chosenMode) ? chosenMode : offered[0][0];
  }

  function describeMode() {
    const mode = currentMode();
    modeHint.textContent = MODES.find(([value]) => value === mode)?.[2] || "";
    passageBox.hidden = mode === "free" || !hasReference();
    barsRow.hidden = passageSelect.value !== "custom";
    tempoRow.hidden = mode === "wait";
    ladderNote.hidden = mode === "wait";
    advancedBox.hidden = mode === "wait";
    beatsSelect.hidden = mode !== "free";
  }

  async function refreshLadder() {
    ladder = null;
    ladderNote.textContent = "";
    const mode = currentMode();
    if (!reference || mode === "wait") return;
    const params = { mode };
    if (mode !== "free") {
      if (!hasReference()) return;
      const { start: from, end: to } = range();
      params.start_bar = from;
      params.end_bar = to;
    }
    try {
      ladder = await api.keyboardLadder(entrySelect.value, params);
    } catch {
      return;
    }
    describeLadder();
    if (ladderBox.checked && !manualTempo) tempoInput.value = String(ladder.recommended_tempo);
  }

  function describeLadder() {
    if (!ladder) return;
    if (ladder.current_tempo === null) {
      ladderNote.textContent = `Start at ♩ = ${ladder.recommended_tempo}. The tempo climbs towards ${ladder.target_tempo} after ${ladder.runs_needed} clean runs in a row.`;
    } else if (ladder.reached_target) {
      ladderNote.textContent = `You have played this cleanly at the target tempo of ♩ = ${ladder.target_tempo}.`;
    } else if (ladder.raised) {
      ladderNote.textContent = `${ladder.runs_needed} clean runs at ♩ = ${ladder.current_tempo}. Next up: ♩ = ${ladder.recommended_tempo}.`;
    } else {
      ladderNote.textContent = `${ladder.clean_streak} of ${ladder.runs_needed} clean runs at ♩ = ${ladder.current_tempo}. Target ♩ = ${ladder.target_tempo}.`;
    }
  }

  async function loadEntry() {
    result.hidden = true;
    strip.update([]);
    status.textContent = "";
    reference = null;
    notesInfo = null;
    manualTempo = false;
    ladder = null;
    ladderNote.textContent = "";
    if (!entrySelect.value) {
      info.hidden = true;
      syncModes();
      describeMode();
      refreshControls();
      return;
    }
    info.hidden = false;
    info.className = "keyboard-message faint";
    info.textContent = "Looking for note data for this piece…";
    refreshControls();
    try {
      reference = await api.keyboardReference(entrySelect.value);
    } catch (error) {
      info.textContent = error.detail || "Couldn't load this piece for keyboard practice.";
      syncModes();
      describeMode();
      refreshControls();
      return;
    }
    syncModes();
    if (hasReference()) {
      info.hidden = true;
      passageSelect.replaceChildren(
        el("option", { value: "whole" }, `The whole piece (bars ${reference.first_bar}–${reference.last_bar})`),
        ...reference.passages.map((pick) => el("option", { value: String(pick.id) }, `${pick.label} (bars ${pick.start_bar}–${pick.end_bar})`)),
        el("option", { value: "custom" }, "Choose bars…")
      );
      fromInput.value = String(reference.first_bar);
      toInput.value = String(Math.min(reference.first_bar + 3, reference.last_bar));
      beatsSelect.value = BEAT_CHOICES.includes(reference.beats_per_bar) ? String(reference.beats_per_bar) : "4";
    } else {
      info.className = "keyboard-message keyboard-message-problem";
      info.textContent = reference.message || NOTE_CHECKING_UNAVAILABLE;
      passageSelect.replaceChildren();
    }
    tempoInput.value = String(Math.max(40, Math.round((reference.target_tempo_bpm * 0.6) / 2) * 2));
    describeMode();
    refreshControls();
    await refreshLadder();
  }

  function paintState(state) {
    strip.update(barsFromTally(state.bars));
    if (state.phase === "countin") {
      status.textContent = state.countIn ? `Count-in… ${state.countIn}` : "Get ready…";
    } else if (state.phase === "playing") {
      if (state.mode === "wait") {
        status.textContent = state.expected.length ? `Play ${state.expected.map(noteName).join(" + ")}` : "Finished";
      } else if (state.mode === "free") {
        status.textContent = `Keep time with the click. ${state.played} ${state.played === 1 ? "note" : "notes"} so far. Press Stop when you're done.`;
      } else {
        status.textContent = state.silent ? "Play now (no sound available, so the beat is silent)" : "Play now";
      }
    }
  }

  function summaryMessage(data) {
    if (data.mode === "wait") return data.clean ? "You got through it without a slip." : `${data.wrong} wrong ${data.wrong === 1 ? "key" : "keys"} on the way through.`;
    if (data.mode === "free") {
      if (data.timing === null || data.timing === undefined) return "Play a few more notes with the click and your timing will be measured.";
      return data.clean ? "Steady and on the beat." : "Not steady enough yet. Aim to land each note right on a click, or an even fraction of one.";
    }
    if (data.clean) return "A clean run: right notes, on the beat, and even.";
    return "Not clean yet. A clean run needs nearly every note right, close to the beat, and an even pulse.";
  }

  function ladderLine(data) {
    const state = data.ladder;
    if (!state) return null;
    if (state.raised) return `That is ${state.runs_needed} clean runs at ♩ = ${state.current_tempo}. Next run: ♩ = ${state.recommended_tempo}.`;
    if (state.reached_target) return `Clean at the target tempo of ♩ = ${state.target_tempo}.`;
    return `${state.clean_streak} of ${state.runs_needed} clean runs at ♩ = ${state.current_tempo}.`;
  }

  function renderResult(data, { problem } = {}) {
    result.hidden = false;
    const free = data.mode === "free";
    const parts = [
      el("div", { class: "row", style: "align-items:baseline;gap:var(--space-3)" }, el("span", { class: "stat", style: "font-size:34px" }, `${Math.round(data.overall)}`), el("span", { class: `pill ${data.clean ? "pill-ok" : "pill-warn"}` }, data.clean ? "Clean run" : "Keep going")),
      free ? el("p", { class: "keyboard-message keyboard-message-problem" }, data.message || NOTE_CHECKING_UNAVAILABLE) : null,
      el("p", { style: "margin:0" }, summaryMessage(data)),
      el(
        "div",
        { class: "keyboard-stats" },
        free ? null : stat("Notes right", data.accuracy === null || data.accuracy === undefined ? "—" : percent(data.accuracy * 100), "%"),
        data.mode === "wait" ? null : stat("Timing", percent(data.timing), "%"),
        data.mode === "wait" ? null : stat("Evenness", percent(data.evenness), "%")
      ),
      free
        ? el("p", { class: "faint", style: "margin:0;font-size:13px" }, `${data.played} notes played, ${data.late} late and ${data.early} early against the click.`)
        : el(
            "p",
            { class: "faint", style: "margin:0;font-size:13px" },
            `${data.correct} right, ${data.wrong} wrong, ${data.missing} missed` + (data.mode === "scored" ? `, ${data.late} late, ${data.early} early` : "") + (data.achieved_tempo_bpm ? `. You played at about ♩ = ${Math.round(data.achieved_tempo_bpm)}.` : ".")
          ),
      ladderLine(data) ? el("p", { style: "margin:0" }, ladderLine(data)) : null,
      problem ? el("p", { class: "keyboard-message keyboard-message-problem" }, problem) : null,
      el("div", { class: "row" }, el("button", { type: "button", class: "btn btn-small", onclick: () => begin() }, "Play again")),
    ];
    result.replaceChildren(...parts.filter(Boolean));
    strip.update(data.bars.map((item) => ({ ...item, pending: false })));
  }

  async function submit(finished, from, to, passage) {
    status.textContent = "Saving your run…";
    const body = {
      mode: finished.mode,
      start_bar: finished.mode === "free" ? null : from,
      end_bar: finished.mode === "free" ? null : to,
      passage_id: passage,
      beats_per_bar: finished.beatsPerBar,
      count_in_beats: finished.countInBeats,
      latency_ms: finished.latencyMs,
      duration_sec: finished.durationSec,
      notes: finished.notes.map((note) => ({ t: note.t, midi: note.midi })),
    };
    if (finished.tempoBpm) body.tempo_bpm = finished.tempoBpm;
    try {
      const data = await api.keyboardAttempt(entrySelect.value, body);
      status.textContent = "";
      ladder = data.ladder || ladder;
      manualTempo = false;
      renderResult(data);
      if (data.ladder) {
        describeLadder();
        if (ladderBox.checked && data.ladder.raised) {
          tempoInput.value = String(data.ladder.recommended_tempo);
          notify.success(`Tempo raised to ♩ = ${data.ladder.recommended_tempo}`);
        }
      }
    } catch (error) {
      status.textContent = "";
      const local = finished.local;
      renderResult(
        {
          mode: finished.mode,
          overall: local ? local.accuracy * 100 : 0,
          clean: false,
          accuracy: local ? local.accuracy : null,
          timing: null,
          evenness: null,
          played: finished.notes.length,
          correct: local ? local.correct : 0,
          wrong: local ? local.wrong : 0,
          missing: local ? local.missing : 0,
          late: 0,
          early: 0,
          bars: local ? local.bars : [],
          ladder: null,
        },
        { problem: `This run wasn't saved: ${error.detail || "the server couldn't be reached"}.${finished.mode === "free" ? "" : " The result above only counts the notes."}` }
      );
    }
  }

  async function begin() {
    if (busy || !canStart()) return;
    if (controller.state.status !== "ready" || !controller.state.selectedId) {
      notify.error("Connect a MIDI keyboard first, then choose it from the list.");
      return;
    }
    const mode = currentMode();
    const tempo = Number(tempoInput.value);
    if (mode !== "wait" && !(tempo >= 20 && tempo <= 400)) {
      notify.error("Choose a tempo between 20 and 400.");
      return;
    }
    let from = null;
    let to = null;
    let passage = null;
    if (mode !== "free") {
      ({ start: from, end: to, passage } = range());
      if (!(from >= 0 && to >= from)) {
        notify.error("The last bar can't come before the first.");
        return;
      }
    }
    rememberLatency(Number(latency.value) || 0);
    result.hidden = true;
    setBusy(true);
    notesInfo = null;
    if (mode !== "free") {
      status.textContent = "Loading the notes…";
      try {
        notesInfo = await api.keyboardNotes(entrySelect.value, { start_bar: from, end_bar: to });
      } catch (error) {
        setBusy(false);
        status.textContent = error.detail || "Couldn't load those bars.";
        return;
      }
    }
    run = createRun({
      controller,
      mode,
      notes: notesInfo ? notesInfo.notes : [],
      tempoBpm: tempo,
      beatsPerBar: mode === "free" ? Number(beatsSelect.value) : notesInfo.beats_per_bar,
      countInBeats: Number(countIn.value),
      latencyMs: Number(latency.value) || 0,
      maxSeconds: mode === "free" ? FREE_MAX_SECONDS : 600,
      onUpdate: paintState,
      onFinish: async (finished) => {
        run = null;
        await submit(finished, from, to, passage);
        setBusy(false);
        describeMode();
      },
    });
    run.start();
  }

  entrySelect.addEventListener("change", loadEntry);
  passageSelect.addEventListener("change", () => {
    describeMode();
    manualTempo = false;
    refreshLadder();
  });
  [fromInput, toInput].forEach((input) => input.addEventListener("change", () => refreshLadder()));
  modeSelect.addEventListener("change", () => {
    chosenMode = modeSelect.value;
    describeMode();
    refreshControls();
    manualTempo = false;
    refreshLadder();
  });
  tempoInput.addEventListener("input", () => {
    manualTempo = true;
  });
  ladderBox.addEventListener("change", () => {
    manualTempo = false;
    if (ladderBox.checked && ladder) tempoInput.value = String(ladder.recommended_tempo);
  });
  start.addEventListener("click", begin);
  stop.addEventListener("click", () => run && run.stop());

  const node = el(
    "div",
    { class: "keyboard-session" },
    el("div", { class: "row" }, el("label", { class: "faint", style: "font-size:12px" }, "Piece"), entrySelect),
    info,
    el("div", { class: "keyboard-options" }, modeSelect, modeHint, passageBox, beatsSelect, tempoRow, ladderNote, advancedBox),
    el("div", { class: "row" }, start, stop),
    status,
    strip.node,
    result
  );

  syncModes();
  describeMode();
  refreshControls();

  api
    .repertoire({ limit: 100 })
    .then((page) => {
      const learning = (entry) => Number(["learning", "polishing"].includes(entry.status));
      const entries = [...page.items].sort((a, b) => learning(b) - learning(a));
      entrySelect.replaceChildren(
        el("option", { value: "" }, entries.length ? "Choose a piece…" : "Add a piece to your repertoire first"),
        ...entries.map((entry) => el("option", { value: entry.id }, entry.piece.title))
      );
    })
    .catch(() => {
      entrySelect.replaceChildren(el("option", { value: "" }, "Couldn't load your pieces"));
    });

  return {
    node,
    load: loadEntry,
    dispose: () => {
      if (run) run.cancel();
      run = null;
    },
  };
}
