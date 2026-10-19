import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { createMidiController, midiSupport, noteName, parseMidiMessage, SUPPORTED_BROWSERS } from "../src/lib/midi.js";
import { keyboardPanel } from "../src/views/keyboardPractice.js";

function fakeInput(id, name, manufacturer = "Yamaha") {
  return { id, name, manufacturer, state: "connected", onmidimessage: null };
}

function fakeAccess(inputs) {
  const map = new Map(inputs.map((input) => [input.id, input]));
  return {
    inputs: map,
    onstatechange: null,
    plug(input) {
      map.set(input.id, input);
      this.onstatechange?.({ port: input });
    },
    unplug(id) {
      map.get(id).state = "disconnected";
      this.onstatechange?.({ port: map.get(id) });
    },
  };
}

const supported = { supported: true, reason: null, message: null };

describe("web midi support", () => {
  it("says which browsers work when the API is missing", () => {
    const result = midiSupport({ navigator: {}, isSecureContext: true });
    expect(result.supported).toBe(false);
    expect(result.reason).toBe("unsupported");
    expect(result.message).toContain(SUPPORTED_BROWSERS);
    expect(result.message).toContain("Safari");
  });

  it("asks for https on an insecure page", () => {
    const result = midiSupport({ navigator: { requestMIDIAccess() {} }, isSecureContext: false });
    expect(result.reason).toBe("insecure");
  });

  it("is supported with the API on a secure page", () => {
    expect(midiSupport({ navigator: { requestMIDIAccess() {} }, isSecureContext: true }).supported).toBe(true);
  });

  it("never asks for access when unsupported", async () => {
    let asked = false;
    const controller = createMidiController({
      support: midiSupport({ navigator: {} }),
      requestAccess: () => {
        asked = true;
      },
    });
    expect(controller.state.status).toBe("unsupported");
    expect(await controller.connect()).toBe(false);
    expect(asked).toBe(false);
  });
});

describe("midi messages", () => {
  it("reads note on, note off and a note on with zero velocity", () => {
    expect(parseMidiMessage([0x90, 60, 80], 12)).toEqual({ type: "on", midi: 60, velocity: 80, channel: 0, time: 12 });
    expect(parseMidiMessage([0x80, 60, 0], 20).type).toBe("off");
    expect(parseMidiMessage([0x93, 64, 0], 30)).toMatchObject({ type: "off", midi: 64, channel: 3 });
  });

  it("reads the sustain pedal and ignores everything else", () => {
    expect(parseMidiMessage([0xb0, 64, 127], 1)).toMatchObject({ type: "pedal", value: 127 });
    expect(parseMidiMessage([0xb0, 7, 90], 1)).toBeNull();
    expect(parseMidiMessage([0xf8], 1)).toBeNull();
    expect(parseMidiMessage(null, 1)).toBeNull();
  });

  it("names notes", () => {
    expect(noteName(60)).toBe("C4");
    expect(noteName(61)).toBe("C♯4");
    expect(noteName(21)).toBe("A0");
  });
});

describe("midi controller", () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => localStorage.clear());

  it("reports a blocked permission clearly", async () => {
    const denied = Object.assign(new Error("blocked"), { name: "SecurityError" });
    const controller = createMidiController({ support: supported, requestAccess: async () => Promise.reject(denied) });
    expect(await controller.connect()).toBe(false);
    expect(controller.state.status).toBe("denied");
    expect(controller.state.message).toContain("site settings");
  });

  it("connects and picks the only keyboard automatically", async () => {
    const input = fakeInput("a", "P-125");
    const controller = createMidiController({ support: supported, requestAccess: async () => fakeAccess([input]) });
    expect(await controller.connect()).toBe(true);
    expect(controller.state.status).toBe("ready");
    expect(controller.state.devices.map((device) => device.name)).toEqual(["P-125"]);
    expect(controller.state.selectedId).toBe("a");
    expect(typeof input.onmidimessage).toBe("function");
  });

  it("lets the user choose between devices and listens to one at a time", async () => {
    const first = fakeInput("a", "P-125");
    const second = fakeInput("b", "Launchkey", "Novation");
    const controller = createMidiController({ support: supported, requestAccess: async () => fakeAccess([first, second]) });
    await controller.connect();
    expect(controller.state.selectedId).toBe("");
    controller.select("b");
    expect(controller.state.selectedId).toBe("b");
    expect(first.onmidimessage).toBeNull();
    const heard = [];
    controller.onNote((note) => heard.push(note));
    first.onmidimessage?.({ data: [0x90, 60, 90], timeStamp: 1 });
    second.onmidimessage({ data: [0x90, 62, 90], timeStamp: 2 });
    expect(heard.map((note) => note.midi)).toEqual([62]);
    controller.select("a");
    expect(second.onmidimessage).toBeNull();
  });

  it("remembers the chosen keyboard", async () => {
    const accessFor = () => fakeAccess([fakeInput("a", "P-125"), fakeInput("b", "Launchkey")]);
    const first = createMidiController({ support: supported, requestAccess: async () => accessFor() });
    await first.connect();
    first.select("b");
    const again = createMidiController({ support: supported, requestAccess: async () => accessFor() });
    await again.connect();
    expect(again.state.selectedId).toBe("b");
  });

  it("follows a keyboard being plugged in and pulled out", async () => {
    const access = fakeAccess([]);
    const controller = createMidiController({ support: supported, requestAccess: async () => access });
    await controller.connect();
    expect(controller.state.devices).toEqual([]);
    expect(controller.state.message).toContain("No MIDI keyboard found");
    access.plug(fakeInput("a", "P-125"));
    expect(controller.state.selectedId).toBe("a");
    access.unplug("a");
    expect(controller.state.devices).toEqual([]);
    expect(controller.state.selectedId).toBe("");
  });

  it("stops listening when disposed", async () => {
    const input = fakeInput("a", "P-125");
    const controller = createMidiController({ support: supported, requestAccess: async () => fakeAccess([input]) });
    await controller.connect();
    controller.dispose();
    expect(input.onmidimessage).toBeNull();
  });
});

describe("keyboard panel", () => {
  it("explains what to use when Web MIDI is missing and still renders", () => {
    const controller = createMidiController({ support: midiSupport({ navigator: {} }) });
    const panel = keyboardPanel({ controller });
    document.body.append(panel.node);
    const text = panel.node.textContent;
    expect(text).toContain("Keyboard practice");
    expect(text).toContain("Not available");
    expect(text).toContain(SUPPORTED_BROWSERS);
    expect(panel.node.querySelector("button").hidden).toBe(true);
    expect(panel.node.querySelector(".keyboard-device").hidden).toBe(true);
    expect(panel.node.querySelector(".keyboard-readout").hidden).toBe(true);
    panel.dispose();
    panel.node.remove();
  });

  it("shows the connection, the device list and the notes played", async () => {
    const input = fakeInput("a", "P-125");
    const controller = createMidiController({
      support: supported,
      requestAccess: async () => fakeAccess([input, fakeInput("b", "Launchkey", "Novation")]),
    });
    const panel = keyboardPanel({ controller });
    document.body.append(panel.node);
    expect(panel.node.textContent).toContain("Not connected");
    panel.node.querySelector("button").click();
    await new Promise((resolve) => setTimeout(resolve, 0));
    const select = panel.node.querySelector("select");
    expect([...select.options].map((option) => option.textContent)).toEqual(["Choose a keyboard…", "Yamaha P-125", "Novation Launchkey"]);
    select.value = "a";
    select.dispatchEvent(new Event("change"));
    expect(panel.node.textContent).toContain("Connected · P-125");
    input.onmidimessage({ data: [0x90, 61, 70], timeStamp: 5 });
    expect(panel.node.querySelector(".keyboard-note").textContent).toBe("C♯4");
    panel.dispose();
    panel.node.remove();
  });
});
