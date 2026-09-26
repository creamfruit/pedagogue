import { api } from "../api/client.js";
import { createAmbientRoom } from "../lib/ambient.js";
import { el, reveal, sectionBlock } from "../lib/dom.js";
import { MAX_BPM, MIN_BPM, bpmFromTaps, clampBpm, createMetronome } from "../lib/metronome.js";
import { notify } from "../lib/toast.js";

const METRONOME_BPM_KEY = "pp.metronome-bpm";

function storedBpm() {
  try {
    return clampBpm(localStorage.getItem(METRONOME_BPM_KEY) || 80);
  } catch {
    return 80;
  }
}

function rememberBpm(value) {
  try {
    localStorage.setItem(METRONOME_BPM_KEY, String(value));
  } catch {
    /* storage unavailable */
  }
}

export function metronomePanel() {
  const lights = el("div", { class: "metronome-lights", "aria-hidden": "true" });
  const metronome = createMetronome({
    onBeat: (index, beats) => {
      if (lights.children.length !== beats) {
        lights.replaceChildren(...Array.from({ length: beats }, (_, i) => el("span", { class: i === 0 ? "light light-accent" : "light" })));
      }
      [...lights.children].forEach((light, i) => light.classList.toggle("on", i === index));
    },
  });
  metronome.setBpm(storedBpm());

  const readout = el("output", { class: "metronome-bpm mono", "aria-live": "polite" }, String(metronome.bpm));
  const slider = el("input", { type: "range", min: MIN_BPM, max: MAX_BPM, value: metronome.bpm, "aria-label": "Tempo in beats per minute" });
  const number = el("input", { type: "number", min: MIN_BPM, max: MAX_BPM, value: metronome.bpm, class: "metronome-number", "aria-label": "Tempo" });

  function setTempo(value) {
    const bpm = clampBpm(value);
    metronome.setBpm(bpm);
    slider.value = bpm;
    number.value = bpm;
    readout.textContent = String(bpm);
    rememberBpm(bpm);
  }

  slider.addEventListener("input", () => setTempo(slider.value));
  number.addEventListener("change", () => setTempo(number.value));

  const nudge = (delta) =>
    el(
      "button",
      {
        type: "button",
        class: "btn btn-small btn-ghost",
        "aria-label": `${delta > 0 ? "Faster" : "Slower"} by ${Math.abs(delta)}`,
        onclick: () => setTempo(metronome.bpm + delta),
      },
      delta > 0 ? `+${delta}` : `${delta}`
    );

  const beats = el("select", { "aria-label": "Beats per bar" }, ...[2, 3, 4, 5, 6, 7, 9, 12].map((n) => el("option", { value: n, selected: n === 4 || null }, `${n} per bar`)));
  beats.addEventListener("change", () => {
    metronome.setBeatsPerBar(beats.value);
    lights.replaceChildren();
  });
  const accent = el("input", { type: "checkbox", checked: true });
  accent.addEventListener("change", () => metronome.setAccent(accent.checked));
  const volume = el("input", { type: "range", min: "0", max: "1", step: "0.05", value: "0.7", "aria-label": "Metronome volume" });
  volume.addEventListener("input", () => metronome.setVolume(volume.value));

  let taps = [];
  const tap = el(
    "button",
    {
      type: "button",
      class: "btn btn-small btn-ghost",
      onclick: () => {
        const now = performance.now();
        taps = taps.filter((time) => now - time < 3000);
        taps.push(now);
        const bpm = bpmFromTaps(taps);
        if (bpm) setTempo(bpm);
      },
    },
    "Tap"
  );

  const toggle = el("button", { type: "button", class: "btn metronome-toggle", "aria-pressed": "false" }, "Start");
  toggle.addEventListener("click", () => {
    if (metronome.running) {
      metronome.stop();
      toggle.textContent = "Start";
      toggle.setAttribute("aria-pressed", "false");
      return;
    }
    if (!metronome.start()) {
      notify.error("This browser can't play audio");
      return;
    }
    toggle.textContent = "Stop";
    toggle.setAttribute("aria-pressed", "true");
  });

  const presets = el("select", { "aria-label": "Use a piece's target tempo" }, el("option", { value: "" }, "Use a piece's target tempo…"));
  presets.addEventListener("change", () => {
    if (presets.value) setTempo(presets.value);
  });
  api
    .repertoire({ limit: 100 })
    .then((page) => {
      page.items
        .filter((entry) => entry.target_tempo_bpm && ["learning", "polishing"].includes(entry.status))
        .forEach((entry) => presets.append(el("option", { value: entry.target_tempo_bpm }, `${entry.piece.title} · ${entry.target_tempo_bpm} bpm`)));
      presets.hidden = presets.options.length < 2;
    })
    .catch(() => {
      presets.hidden = true;
    });

  const more = reveal(
    "Beats, accent and volume",
    el(
      "div",
      { class: "metronome-options" },
      beats,
      el("label", { class: "check-label" }, accent, "Accent the downbeat"),
      el("label", { class: "metronome-volume" }, el("span", {}, "Volume"), volume)
    )
  );

  const node = sectionBlock(
    "Metronome",
    { caption: "Sample-accurate clicks on the audio clock, so the beat holds steady even when the page is busy." },
    el(
      "div",
      { class: "metronome" },
      el("div", { class: "metronome-readout" }, readout, el("span", { class: "faint" }, "bpm")),
      lights,
      el("div", { class: "metronome-slider" }, nudge(-5), nudge(-1), slider, nudge(1), nudge(5)),
      el("div", { class: "row" }, toggle, number, tap, presets)
    ),
    more.button,
    more.region
  );

  return { node, dispose: () => metronome.stop() };
}

export function ambientToggle(scope) {
  const room = createAmbientRoom();
  const volume = el("input", { type: "range", min: "0", max: "1", step: "0.05", value: "0.35", "aria-label": "Ambient volume", hidden: true });
  volume.addEventListener("input", () => room.setVolume(volume.value));
  const button = el("button", { type: "button", class: "ambient-toggle", "aria-pressed": "false" }, el("span", { class: "ambient-dot", "aria-hidden": "true" }), "Ambient room");

  function set(on) {
    if (on) {
      if (!room.start()) {
        notify.error("This browser can't play audio");
        return;
      }
      room.setVolume(volume.value);
    } else {
      room.stop();
    }
    scope.classList.toggle("ambient", on);
    button.setAttribute("aria-pressed", String(on));
    volume.hidden = !on;
  }

  button.addEventListener("click", () => set(button.getAttribute("aria-pressed") !== "true"));
  return {
    node: el("div", { class: "ambient-control" }, button, volume),
    dispose: () => set(false),
  };
}
