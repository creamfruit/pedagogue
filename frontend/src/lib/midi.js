import { isNative } from "./platform.js";

const DEVICE_KEY = "pp.midi-device";

export const SUPPORTED_BROWSERS = "Chrome, Edge or Opera on a computer or Android phone, or Firefox on a computer";

export const NOTE_NAMES = ["C", "C♯", "D", "D♯", "E", "F", "F♯", "G", "G♯", "A", "A♯", "B"];

export function noteName(midi) {
  return `${NOTE_NAMES[((midi % 12) + 12) % 12]}${Math.floor(midi / 12) - 1}`;
}

export function midiSupport(env = globalThis) {
  const nav = env.navigator;
  if (isNative) {
    return { supported: false, reason: "native", message: `Keyboard practice needs Web MIDI, which this app can't use. Open Pedagogue in ${SUPPORTED_BROWSERS} to use it.` };
  }
  if (!nav || typeof nav.requestMIDIAccess !== "function") {
    return {
      supported: false,
      reason: "unsupported",
      message: `This browser can't connect to a MIDI keyboard. Open Pedagogue in ${SUPPORTED_BROWSERS}. Safari and every browser on iPhone and iPad don't support Web MIDI.`,
    };
  }
  if (env.isSecureContext === false) {
    return { supported: false, reason: "insecure", message: "Web MIDI only works on a secure (https) page. Open Pedagogue at its https address." };
  }
  return { supported: true, reason: null, message: null };
}

export function parseMidiMessage(data, time) {
  if (!data || data.length < 2) return null;
  const status = data[0] & 0xf0;
  const channel = data[0] & 0x0f;
  if (status === 0x90 && data[2] > 0) return { type: "on", midi: data[1], velocity: data[2], channel, time };
  if (status === 0x80 || status === 0x90) return { type: "off", midi: data[1], velocity: data[2] || 0, channel, time };
  if (status === 0xb0 && data[1] === 64) return { type: "pedal", value: data[2], channel, time };
  return null;
}

function readStored() {
  try {
    return localStorage.getItem(DEVICE_KEY) || "";
  } catch {
    return "";
  }
}

function writeStored(id) {
  try {
    if (id) localStorage.setItem(DEVICE_KEY, id);
    else localStorage.removeItem(DEVICE_KEY);
  } catch {
    return;
  }
}

function describe(input) {
  return { id: input.id, name: input.name || "MIDI device", manufacturer: input.manufacturer || "", connected: input.state !== "disconnected" };
}

export function denialMessage(error) {
  if (error && (error.name === "SecurityError" || error.name === "NotAllowedError")) {
    return "Permission to use MIDI devices was blocked. Allow MIDI for this site in your browser's site settings, then try again.";
  }
  return "The browser couldn't open its MIDI system. Check that no other app is holding the keyboard, then try again.";
}

export function createMidiController({ support = midiSupport(), requestAccess = () => globalThis.navigator.requestMIDIAccess({ sysex: false }) } = {}) {
  const listeners = new Set();
  const noteHandlers = new Set();
  let access = null;
  let attached = null;
  let state = {
    status: support.supported ? "idle" : "unsupported",
    message: support.message,
    devices: [],
    selectedId: "",
  };

  function emit() {
    listeners.forEach((listener) => listener(state));
  }

  function set(patch) {
    state = { ...state, ...patch };
    emit();
  }

  function inputs() {
    return access ? [...access.inputs.values()].filter((input) => input.state !== "disconnected") : [];
  }

  function detach() {
    if (attached) attached.onmidimessage = null;
    attached = null;
  }

  function attach(id) {
    detach();
    const input = inputs().find((item) => item.id === id);
    if (!input) return false;
    input.onmidimessage = (event) => {
      const message = parseMidiMessage(event.data, event.timeStamp);
      if (message) noteHandlers.forEach((handler) => handler(message));
    };
    attached = input;
    return true;
  }

  function refresh() {
    const devices = inputs().map(describe);
    let selectedId = state.selectedId;
    if (!devices.some((device) => device.id === selectedId)) {
      const remembered = readStored();
      const preferred = devices.find((device) => device.id === remembered) || (devices.length === 1 ? devices[0] : null);
      selectedId = preferred ? preferred.id : "";
    }
    if (selectedId) attach(selectedId);
    else detach();
    set({ devices, selectedId, status: "ready", message: devices.length ? null : "No MIDI keyboard found. Plug one in or switch it on, and it will appear here." });
  }

  async function connect() {
    if (!support.supported || access) return state.status === "ready";
    set({ status: "requesting", message: "Waiting for your browser to allow MIDI…" });
    try {
      access = await requestAccess();
    } catch (error) {
      access = null;
      set({ status: "denied", message: denialMessage(error), devices: [], selectedId: "" });
      return false;
    }
    access.onstatechange = refresh;
    refresh();
    return true;
  }

  function select(id) {
    if (!id) {
      detach();
      writeStored("");
      set({ selectedId: "" });
      return;
    }
    if (attach(id)) {
      writeStored(id);
      set({ selectedId: id });
    }
  }

  return {
    get state() {
      return state;
    },
    get supported() {
      return support.supported;
    },
    connect,
    select,
    subscribe(listener) {
      listeners.add(listener);
      listener(state);
      return () => listeners.delete(listener);
    },
    onNote(handler) {
      noteHandlers.add(handler);
      return () => noteHandlers.delete(handler);
    },
    dispose() {
      detach();
      if (access) access.onstatechange = null;
      access = null;
      listeners.clear();
      noteHandlers.clear();
    },
  };
}
