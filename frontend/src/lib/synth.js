const DURATION_BEATS = { s: 0.25, e: 0.5, q: 1, h: 2, w: 4 };
const NOTE_SEMITONE = { C: 0, D: 2, E: 4, F: 5, G: 7, A: 9, B: 11 };

function pitchToFrequency(pitch) {
  const match = /^([A-G])([#b]?)(-?\d+)$/.exec(pitch);
  if (!match) return 440;
  const [, letter, accidental, octaveStr] = match;
  const semitone = NOTE_SEMITONE[letter] + (accidental === "#" ? 1 : accidental === "b" ? -1 : 0);
  const midi = (Number(octaveStr) + 1) * 12 + semitone;
  return 440 * Math.pow(2, (midi - 69) / 12);
}

export function playNotation(notation, { onMeasure, onDone } = {}) {
  const AudioCtx = window.AudioContext || window.webkitAudioContext;
  if (!AudioCtx) return { stop: () => {}, durationMs: 0 };
  const ctx = new AudioCtx();
  const beatSeconds = 60 / (notation.tempo_bpm || 90);
  let time = ctx.currentTime + 0.15;
  const timers = [];

  notation.measures.forEach((measure, measureIndex) => {
    const measureStart = time;
    if (onMeasure) {
      const delay = (measureStart - ctx.currentTime) * 1000;
      timers.push(setTimeout(() => onMeasure(measureIndex), Math.max(delay, 0)));
    }
    let measureEnd = measureStart;
    [measure.notes || [], measure.left || []].forEach((voice) => {
      let at = measureStart;
      voice.forEach((note) => {
        const beats = (DURATION_BEATS[note.duration] || 1) * (note.tuplet === 3 ? 2 / 3 : 1);
        const duration = beats * beatSeconds;
        const pitches = note.pitches || (note.pitch ? [note.pitch] : []);
        pitches.forEach((pitch) => {
          const osc = ctx.createOscillator();
          const gain = ctx.createGain();
          osc.type = "triangle";
          osc.frequency.value = pitchToFrequency(pitch);
          gain.gain.setValueAtTime(0.0001, at);
          gain.gain.linearRampToValueAtTime(0.16, at + 0.012);
          gain.gain.exponentialRampToValueAtTime(0.0001, at + duration * 0.94);
          osc.connect(gain).connect(ctx.destination);
          osc.start(at);
          osc.stop(at + duration);
        });
        at += duration;
      });
      measureEnd = Math.max(measureEnd, at);
    });
    time = measureEnd;
  });

  const totalMs = Math.max((time - ctx.currentTime) * 1000, 0);
  if (onDone) timers.push(setTimeout(onDone, totalMs + 80));

  return {
    durationMs: totalMs,
    stop: () => {
      timers.forEach(clearTimeout);
      ctx.close();
    },
  };
}
