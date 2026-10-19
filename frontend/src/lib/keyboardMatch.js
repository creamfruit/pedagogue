export const CHORD_WINDOW_MS = 40;
export const REFERENCE_CHORD_QUARTERS = 1 / 32;

export function groupReference(notes) {
  const events = [];
  const ordered = [...notes].sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  for (const [onset, midi, bar] of ordered) {
    const last = events[events.length - 1];
    if (last && onset - last.onset <= REFERENCE_CHORD_QUARTERS) last.pitches.add(midi);
    else events.push({ onset, bar, pitches: new Set([midi]) });
  }
  return events;
}

export function countNotes(events) {
  return events.reduce((total, event) => total + event.pitches.size, 0);
}

export function barOrder(events) {
  return [...new Set(events.map((event) => event.bar))];
}

export function createBarTally(events) {
  const bars = new Map();
  for (const event of events) {
    if (!bars.has(event.bar)) bars.set(event.bar, { bar: event.bar, expected: event.pitches.size, correct: 0, wrong: 0 });
    else bars.get(event.bar).expected += event.pitches.size;
  }
  return bars;
}

export function barStatus(item) {
  if (!item || item.expected + item.wrong === 0) return "idle";
  if (item.wrong > 0) return "wrong";
  if (item.correct >= item.expected) return "right";
  return "pending";
}

export function createWaitMatcher(events) {
  const tally = createBarTally(events);
  let index = 0;
  let remaining = new Set(events[0] ? events[0].pitches : []);
  let correct = 0;
  let wrong = 0;

  return {
    get index() {
      return index;
    },
    get done() {
      return index >= events.length;
    },
    get expected() {
      return events[index] ? [...remaining].sort((a, b) => a - b) : [];
    },
    get bar() {
      return events[Math.min(index, events.length - 1)]?.bar ?? null;
    },
    get totals() {
      return { correct, wrong };
    },
    bars: () => [...tally.values()],
    press(midi) {
      if (index >= events.length) return { result: "done", bar: null };
      const event = events[index];
      const item = tally.get(event.bar);
      if (remaining.has(midi)) {
        remaining.delete(midi);
        item.correct += 1;
        correct += 1;
        const advanced = remaining.size === 0;
        if (advanced) {
          index += 1;
          remaining = new Set(events[index] ? events[index].pitches : []);
        }
        return { result: "correct", bar: event.bar, advanced, done: index >= events.length };
      }
      item.wrong += 1;
      wrong += 1;
      return { result: "wrong", bar: event.bar, advanced: false, done: false };
    },
  };
}

export function createLiveMatcher(events, tempoBpm) {
  const beatMs = 60000 / tempoBpm;
  const tally = createBarTally(events);
  const left = events.map((event) => new Set(event.pitches));
  const window = Math.max(450, beatMs * 1.5);
  let correct = 0;
  let wrong = 0;

  return {
    get totals() {
      return { correct, wrong };
    },
    bars: () => [...tally.values()],
    play(midi, timeMs) {
      let best = -1;
      let bestGap = Infinity;
      for (let i = 0; i < events.length; i += 1) {
        if (!left[i].has(midi)) continue;
        const gap = Math.abs(timeMs - events[i].onset * beatMs);
        if (gap < bestGap) {
          best = i;
          bestGap = gap;
        }
      }
      if (best < 0 || bestGap > window) {
        const nearest = events.reduce((pick, event) => (Math.abs(event.onset * beatMs - timeMs) < Math.abs(pick.onset * beatMs - timeMs) ? event : pick), events[0]);
        tally.get(nearest.bar).wrong += 1;
        wrong += 1;
        return { result: "wrong", bar: nearest.bar };
      }
      left[best].delete(midi);
      tally.get(events[best].bar).correct += 1;
      correct += 1;
      return { result: "correct", bar: events[best].bar, errorMs: timeMs - events[best].onset * beatMs };
    },
  };
}

export function localSummary(tally) {
  const bars = [...tally.values()];
  const expected = bars.reduce((total, item) => total + item.expected, 0);
  const correct = bars.reduce((total, item) => total + item.correct, 0);
  const wrong = bars.reduce((total, item) => total + item.wrong, 0);
  return {
    expected,
    correct,
    wrong,
    missing: Math.max(expected - correct, 0),
    accuracy: expected + wrong ? correct / (expected + wrong) : 0,
    bars: bars.map((item) => ({ ...item, missing: Math.max(item.expected - item.correct, 0), accuracy: item.expected + item.wrong ? item.correct / (item.expected + item.wrong) : null })),
  };
}
