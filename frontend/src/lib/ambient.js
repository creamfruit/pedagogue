import { audioContext } from "./synth.js";

const PAD_NOTES = [110, 164.81, 220, 277.18];
const FADE_IN_S = 3;
const FADE_OUT_S = 1.6;

function noiseBuffer(ctx, seconds = 4) {
  const buffer = ctx.createBuffer(1, Math.floor(ctx.sampleRate * seconds), ctx.sampleRate);
  const data = buffer.getChannelData(0);
  let last = 0;
  for (let i = 0; i < data.length; i += 1) {
    last = (last + 0.02 * (Math.random() * 2 - 1)) / 1.02;
    data[i] = last * 3.5;
  }
  return buffer;
}

export function createAmbientRoom() {
  let ctx = null;
  let master = null;
  let nodes = [];
  let level = 0.35;

  function stopNodes(list, at) {
    list.forEach((node) => {
      try {
        node.stop?.(at);
      } catch {
        /* already stopped */
      }
    });
  }

  return {
    get playing() {
      return Boolean(master);
    },
    setVolume(value) {
      level = Math.max(0, Math.min(1, Number(value)));
      if (master && ctx) master.gain.setTargetAtTime(level * 0.22, ctx.currentTime, 0.4);
    },
    start() {
      if (master) return true;
      ctx = audioContext();
      if (!ctx) return false;
      const now = ctx.currentTime;
      master = ctx.createGain();
      master.gain.setValueAtTime(0.0001, now);
      master.gain.exponentialRampToValueAtTime(Math.max(level * 0.22, 0.0002), now + FADE_IN_S);
      const filter = ctx.createBiquadFilter();
      filter.type = "lowpass";
      filter.frequency.value = 700;
      filter.Q.value = 0.4;
      const lfo = ctx.createOscillator();
      const lfoDepth = ctx.createGain();
      lfo.frequency.value = 0.05;
      lfoDepth.gain.value = 260;
      lfo.connect(lfoDepth).connect(filter.frequency);
      filter.connect(master).connect(ctx.destination);

      const voices = PAD_NOTES.flatMap((frequency, index) =>
        [-4, 4].map((detune) => {
          const osc = ctx.createOscillator();
          const gain = ctx.createGain();
          osc.type = index === 0 ? "sine" : "triangle";
          osc.frequency.value = frequency;
          osc.detune.value = detune;
          gain.gain.value = index === 0 ? 0.5 : 0.18;
          osc.connect(gain).connect(filter);
          return osc;
        })
      );

      const air = ctx.createBufferSource();
      air.buffer = noiseBuffer(ctx);
      air.loop = true;
      const airFilter = ctx.createBiquadFilter();
      airFilter.type = "bandpass";
      airFilter.frequency.value = 900;
      airFilter.Q.value = 0.6;
      const airGain = ctx.createGain();
      airGain.gain.value = 0.12;
      air.connect(airFilter).connect(airGain).connect(master);

      nodes = [lfo, air, ...voices];
      nodes.forEach((node) => node.start(now));
      return true;
    },
    stop() {
      if (!master || !ctx) return;
      const now = ctx.currentTime;
      master.gain.cancelScheduledValues(now);
      master.gain.setValueAtTime(Math.max(master.gain.value, 0.0002), now);
      master.gain.exponentialRampToValueAtTime(0.0001, now + FADE_OUT_S);
      stopNodes(nodes, now + FADE_OUT_S + 0.05);
      nodes = [];
      master = null;
    },
  };
}
