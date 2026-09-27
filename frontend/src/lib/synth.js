import { playEvents } from "./piano.js";

const DURATION_BEATS = { s: 0.25, e: 0.5, q: 1, h: 2, w: 4 };
const NOTE_SEMITONE = { C: 0, D: 2, E: 4, F: 5, G: 7, A: 9, B: 11 };

let sharedContext = null;

export function audioContext() {
  const AudioCtx = window.AudioContext || window.webkitAudioContext;
  if (!AudioCtx) return null;
  if (!sharedContext || sharedContext.state === "closed") sharedContext = new AudioCtx();
  if (sharedContext.state === "suspended") sharedContext.resume();
  return sharedContext;
}

export function click(ctx, time, { accent = false, volume = 0.5 } = {}) {
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.type = "square";
  osc.frequency.value = accent ? 1760 : 1175;
  const peak = (accent ? 0.28 : 0.18) * volume;
  gain.gain.setValueAtTime(0.0001, time);
  gain.gain.exponentialRampToValueAtTime(peak, time + 0.002);
  gain.gain.exponentialRampToValueAtTime(0.0001, time + 0.045);
  osc.connect(gain).connect(ctx.destination);
  osc.start(time);
  osc.stop(time + 0.06);
}

function pitchToMidi(pitch) {
  const match = /^([A-G])([#b]?)(-?\d+)$/.exec(pitch);
  if (!match) return 69;
  const [, letter, accidental, octaveStr] = match;
  const semitone = NOTE_SEMITONE[letter] + (accidental === "#" ? 1 : accidental === "b" ? -1 : 0);
  return (Number(octaveStr) + 1) * 12 + semitone;
}

export function notationToEvents(notation) {
  const events = [];
  const measureStarts = [];
  let cursor = 0;
  notation.measures.forEach((measure) => {
    measureStarts.push(cursor);
    let measureEnd = cursor;
    [
      [measure.notes || [], "R"],
      [measure.left || [], "L"],
    ].forEach(([voice, hand]) => {
      let at = cursor;
      voice.forEach((note) => {
        const beats = (DURATION_BEATS[note.duration] || 1) * (note.tuplet === 3 ? 2 / 3 : 1);
        const pitches = note.pitches || (note.pitch ? [note.pitch] : []);
        pitches.forEach((pitch) => events.push([at, beats, pitchToMidi(pitch), 0, hand, beats]));
        at += beats;
      });
      measureEnd = Math.max(measureEnd, at);
    });
    cursor = measureEnd;
  });
  return { events, measureStarts };
}

export function playNotation(notation, { onMeasure, onDone } = {}) {
  const tempo = notation.tempo_bpm || 90;
  const { events, measureStarts } = notationToEvents(notation);
  const timers = [];
  const playback = playEvents(events, {
    tempo,
    onDone,
    onStart: () => {
      if (!onMeasure) return;
      measureStarts.forEach((beat, index) => {
        timers.push(setTimeout(() => onMeasure(index), (beat * 60 * 1000) / tempo));
      });
    },
  });
  return {
    durationMs: playback.durationMs,
    stop: () => {
      timers.forEach(clearTimeout);
      playback.stop();
    },
  };
}
