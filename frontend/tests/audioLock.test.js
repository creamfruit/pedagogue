import { describe, expect, it } from "vitest";
import { features } from "../src/lib/features.js";
import keyboardMatch from "../src/lib/keyboardMatch.js?raw";
import keyboardRun from "../src/lib/keyboardRun.js?raw";
import midi from "../src/lib/midi.js?raw";
import heatStrip from "../src/components/heatStrip.js?raw";
import keyboardPractice from "../src/views/keyboardPractice.js?raw";
import keyboardSession from "../src/views/keyboardSession.js?raw";
import practice from "../src/views/practice.js?raw";

const RECORDING = /getUserMedia|MediaRecorder|createMediaStreamSource|createMediaElementSource|AudioWorklet|ScriptProcessor|enumerateDevices|audio\/webm/;

describe("audio recording stays behind the Coming soon flag", () => {
  it("is off unless the build turns it on", () => {
    expect(features.audio).toBe(false);
  });

  it("keeps live listening out of the session choices while it is off", () => {
    expect(practice).toMatch(/features\.audio \|\| mode !== "live_listening"/);
  });

  it("offers the keyboard as a session mode without audio", () => {
    expect(practice).toMatch(/"free", "keyboard", "live_listening"/);
  });

  it.each([
    ["midi.js", midi],
    ["keyboardMatch.js", keyboardMatch],
    ["keyboardRun.js", keyboardRun],
    ["heatStrip.js", heatStrip],
    ["keyboardPractice.js", keyboardPractice],
    ["keyboardSession.js", keyboardSession],
  ])("%s never opens the microphone or records", (_name, source) => {
    expect(source).not.toMatch(RECORDING);
  });

  it("only plays the metronome click, which is output, not recording", () => {
    expect(keyboardRun).toMatch(/import \{ audioContext, click \} from "\.\/synth\.js"/);
  });

  it("does not depend on the audio flag to work", () => {
    expect(keyboardSession).not.toMatch(/features\.audio/);
    expect(keyboardPractice).not.toMatch(/features\.audio/);
  });
});
