import { el, sectionBlock } from "../lib/dom.js";
import { createMidiController, noteName } from "../lib/midi.js";
import { keyboardSession } from "./keyboardSession.js";

const STATUS_LABEL = {
  unsupported: ["Not available", "pill-bad"],
  idle: ["Not connected", "pill-warn"],
  requesting: ["Waiting for permission", "pill-warn"],
  denied: ["Blocked", "pill-bad"],
  ready: ["Connected", "pill-ok"],
};

function connectionBlock(controller, onChange) {
  const pill = el("span", { class: "pill" });
  const message = el("p", { class: "keyboard-message", role: "status", "aria-live": "polite" });
  const connect = el("button", { type: "button", class: "btn btn-small" }, "Connect keyboard");
  const select = el("select", { "aria-label": "MIDI keyboard", disabled: true });
  const lastNote = el("output", { class: "keyboard-note mono", "aria-live": "off" }, "—");
  const recent = el("div", { class: "keyboard-recent faint mono" });
  const held = new Set();
  const history = [];
  const deviceRow = el("div", { class: "row keyboard-device" }, el("label", { class: "faint", style: "font-size:12px" }, "Keyboard"), select);
  const readout = el("div", { class: "keyboard-readout" }, el("span", { class: "faint", style: "font-size:12px" }, "Last note"), lastNote, recent);

  connect.addEventListener("click", () => controller.connect());
  select.addEventListener("change", () => controller.select(select.value));

  function draw(state) {
    const [label, tone] = STATUS_LABEL[state.status] || STATUS_LABEL.idle;
    pill.className = `pill ${tone}`;
    pill.textContent = state.status === "ready" && state.selectedId ? `Connected · ${state.devices.find((device) => device.id === state.selectedId)?.name || "keyboard"}` : label;
    message.textContent = state.message || "";
    message.hidden = !state.message;
    message.className = `keyboard-message ${state.status === "unsupported" || state.status === "denied" ? "keyboard-message-problem" : "faint"}`;
    connect.hidden = state.status === "ready" || state.status === "unsupported";
    connect.disabled = state.status === "requesting";
    connect.textContent = state.status === "denied" ? "Try again" : "Connect keyboard";
    select.replaceChildren(
      el("option", { value: "" }, state.devices.length ? "Choose a keyboard…" : "No keyboard found"),
      ...state.devices.map((device) => el("option", { value: device.id, selected: device.id === state.selectedId || null }, device.manufacturer ? `${device.manufacturer} ${device.name}` : device.name))
    );
    select.value = state.selectedId;
    select.disabled = state.status !== "ready" || !state.devices.length;
    deviceRow.hidden = state.status === "unsupported";
    readout.hidden = state.status === "unsupported";
    onChange(state);
  }

  const offState = controller.subscribe(draw);
  const offNote = controller.onNote((note) => {
    if (note.type === "on") {
      held.add(note.midi);
      history.unshift(noteName(note.midi));
      history.length = Math.min(history.length, 12);
      lastNote.textContent = noteName(note.midi);
      recent.textContent = history.slice(1).join("  ");
    } else if (note.type === "off") {
      held.delete(note.midi);
    }
    lastNote.classList.toggle("down", held.size > 0);
  });

  const node = el(
    "div",
    { class: "keyboard-connection" },
    el("div", { class: "row" }, pill, connect),
    message,
    deviceRow,
    readout
  );
  return {
    node,
    dispose: () => {
      offState();
      offNote();
    },
  };
}

export function keyboardPanel({ controller = createMidiController(), api, createRun, onSession } = {}) {
  const body = el("div", { class: "keyboard-body" });
  const session = keyboardSession({ controller, api, createRun, onSession });
  const link = connectionBlock(controller, (state) => {
    session.node.hidden = state.status === "unsupported";
  });
  body.append(link.node, session.node);

  const node = sectionBlock(
    "Keyboard practice",
    { caption: "Play a piece on a MIDI keyboard connected to this computer or phone and see how it went.", className: "keyboard-panel", id: "keyboard-practice" },
    body
  );

  return {
    node,
    controller,
    body,
    session,
    dispose: () => {
      session.dispose();
      link.dispose();
      controller.dispose();
    },
  };
}
