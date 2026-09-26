const NATURAL_INDEX = { C: 0, D: 1, E: 2, F: 3, G: 4, A: 5, B: 6 };
const FLAG_COUNT = { s: 2, e: 1, q: 0, h: 0, w: 0 };
const BEATS = { s: 0.25, e: 0.5, q: 1, h: 2, w: 4 };
const SVG_NS = "http://www.w3.org/2000/svg";
const LINE_GAP = 9;
const STEM_LENGTH = LINE_GAP * 3.5;
const GLYPH_FONT = '"Segoe UI Symbol", "Noto Music", "Apple Symbols", serif';
const MEASURE_WIDTH = 110;

const KEY_SIGNATURES = {
  C: { type: "#", count: 0 },
  G: { type: "#", count: 1 },
  D: { type: "#", count: 2 },
  A: { type: "#", count: 3 },
  E: { type: "#", count: 4 },
  B: { type: "#", count: 5 },
  F: { type: "b", count: 1 },
  Bb: { type: "b", count: 2 },
  Eb: { type: "b", count: 3 },
  Ab: { type: "b", count: 4 },
  Db: { type: "b", count: 5 },
};
const SHARP_ORDER = ["F", "C", "G", "D", "A", "E", "B"];
const FLAT_ORDER = ["B", "E", "A", "D", "G", "C", "F"];
const SIGNATURE_PITCHES = {
  treble: { "#": ["F5", "C5", "G5", "D5", "A4", "E5", "B4"], b: ["B4", "E5", "A4", "D5", "G4", "C5", "F4"] },
  bass: { "#": ["F3", "C3", "G2", "D3", "A2", "E3", "B2"], b: ["B2", "E3", "A2", "D3", "G2", "C3", "F2"] },
};

function svg(tag, attrs = {}) {
  const node = document.createElementNS(SVG_NS, tag);
  Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, String(value)));
  return node;
}

function svgText(attrs, content) {
  const node = svg("text", { "font-family": GLYPH_FONT, ...attrs });
  node.textContent = content;
  return node;
}

function accidentalPath(type, x, y) {
  if (type === "#") {
    return `M${x - 1.8} ${y - 8} V${y + 7} M${x + 1.8} ${y - 7} V${y + 8} M${x - 4} ${y - 1.4} L${x + 4} ${y - 3.4} M${x - 4} ${y + 3.4} L${x + 4} ${y + 1.4}`;
  }
  if (type === "b") {
    return `M${x - 2.5} ${y - 11} V${y + 4} C${x + 4} ${y + 1} ${x + 4.5} ${y - 5} ${x - 2.5} ${y - 1.5}`;
  }
  return `M${x - 2} ${y - 9} V${y + 3} L${x + 2} ${y + 2} M${x + 2} ${y + 9} V${y - 3} L${x - 2} ${y - 2}`;
}

function parsePitch(pitch) {
  const match = /^([A-G])([#b]?)(-?\d+)$/.exec(pitch);
  if (!match) return { letter: "C", accidental: "", octave: 4 };
  return { letter: match[1], accidental: match[2], octave: Number(match[3]) };
}

function diatonicStep(pitch) {
  const { letter, octave } = parsePitch(pitch);
  return octave * 7 + NATURAL_INDEX[letter];
}

const MIDDLE_C_STEP = diatonicStep("C4");
const STAFF = {
  treble: { bottomStep: diatonicStep("E4"), middleStep: diatonicStep("B4") },
  bass: { bottomStep: diatonicStep("G2"), middleStep: diatonicStep("D3") },
};

function keyAccidentals(key) {
  const signature = KEY_SIGNATURES[key];
  if (!signature) return { signature: null, byLetter: {} };
  const order = signature.type === "#" ? SHARP_ORDER : FLAT_ORDER;
  const byLetter = Object.fromEntries(order.slice(0, signature.count).map((letter) => [letter, signature.type]));
  return { signature, byLetter };
}

function staffForEvent(pitches, hand) {
  if (hand === "right") return "treble";
  if (hand === "left") return "bass";
  const steps = pitches.map(diatonicStep);
  const mean = steps.reduce((sum, step) => sum + step, 0) / steps.length;
  return mean >= MIDDLE_C_STEP ? "treble" : "bass";
}

function stemUpFor(steps, staff) {
  const middle = STAFF[staff].middleStep;
  const above = Math.max(...steps) - middle;
  const below = middle - Math.min(...steps);
  return below > above;
}

function beatsOf(note) {
  const beats = BEATS[note.duration] || 1;
  return note.tuplet === 3 ? (beats * 2) / 3 : beats;
}

export function renderNotation(notation, { width: requestedWidth, staffGap = 46 } = {}) {
  const twoVoices = notation.hand === "both" || notation.measures.some((measure) => measure.left?.length);
  const hand = !twoVoices && (notation.hand === "right" || notation.hand === "left") ? notation.hand : null;
  const staves = hand ? [staffForEvent([], hand)] : ["treble", "bass"];
  const staffTop = {};
  staves.forEach((staff, index) => {
    staffTop[staff] = index * (LINE_GAP * 4 + staffGap);
  });
  const systemTop = 0;
  const systemBottom = staffTop[staves[staves.length - 1]] + LINE_GAP * 4;

  const { signature, byLetter } = keyAccidentals(notation.key);
  const signatureWidth = signature ? signature.count * 8 + 6 : 0;
  const [beatsTop, beatsBottom] = (notation.time_signature || "4/4").split("/");
  const marginLeft = 30 + signatureWidth + 18;
  const marginRight = 14;
  const measures = notation.measures.length ? notation.measures : [{ notes: [] }];
  const width = requestedWidth || marginLeft + marginRight + measures.length * MEASURE_WIDTH;
  const usableWidth = width - marginLeft - marginRight;
  const measureWidth = usableWidth / measures.length;
  const beatsPerMeasure = Number(beatsTop) || 4;

  const layer = svg("g");
  let minY = systemTop;
  let maxY = systemBottom;
  const track = (y) => {
    if (y < minY) minY = y;
    if (y > maxY) maxY = y;
  };
  const line = (x1, y1, x2, y2, extra = {}) => {
    track(y1);
    track(y2);
    layer.append(svg("line", { x1, y1, x2, y2, stroke: "currentColor", "stroke-width": 1.2, ...extra }));
  };

  const drawAccidental = (type, x, y) => {
    track(y - 11);
    track(y + 9);
    layer.append(svg("path", { d: accidentalPath(type, x, y), stroke: "currentColor", fill: "none", "stroke-width": 1.3 }));
  };

  const yFor = (step, staff) => staffTop[staff] + LINE_GAP * 4 - (step - STAFF[staff].bottomStep) * (LINE_GAP / 2);

  staves.forEach((staff) => {
    for (let i = 0; i < 5; i += 1) {
      const y = staffTop[staff] + i * LINE_GAP;
      line(0, y, width - marginRight, y, { "stroke-width": 1, opacity: 0.55 });
    }
    layer.append(
      staff === "treble"
        ? svgText({ x: 4, y: staffTop[staff] + LINE_GAP * 3, "font-size": 26, fill: "currentColor" }, "\u{1D11E}")
        : svgText({ x: 4, y: staffTop[staff] + LINE_GAP * 1.6, "font-size": 20, fill: "currentColor" }, "\u{1D122}")
    );
    if (signature) {
      SIGNATURE_PITCHES[staff][signature.type].slice(0, signature.count).forEach((pitch, index) => {
        drawAccidental(signature.type, 33 + index * 8, yFor(diatonicStep(pitch), staff));
      });
    }
    const timeX = 30 + signatureWidth;
    layer.append(
      svgText({ x: timeX, y: staffTop[staff] + LINE_GAP * 2 - 1, "font-size": 13, "font-weight": 700, fill: "currentColor" }, beatsTop),
      svgText({ x: timeX, y: staffTop[staff] + LINE_GAP * 4 - 1, "font-size": 13, "font-weight": 700, fill: "currentColor" }, beatsBottom || "4")
    );
  });
  line(0, systemTop, 0, systemBottom, { "stroke-width": 1, opacity: 0.55 });

  function drawLedgers(x, step, staff) {
    const bottom = STAFF[staff].bottomStep;
    const top = bottom + 8;
    if (step <= bottom - 2) {
      for (let s = bottom - 2; s >= step; s -= 2) line(x - 8, yFor(s, staff), x + 8, yFor(s, staff), { "stroke-width": 1 });
    } else if (step >= top + 2) {
      for (let s = top + 2; s <= step; s += 2) line(x - 8, yFor(s, staff), x + 8, yFor(s, staff), { "stroke-width": 1 });
    }
  }

  function drawHeads(event) {
    const open = event.duration === "w" || event.duration === "h";
    event.pitches.forEach((pitch) => {
      const { letter, accidental } = parsePitch(pitch);
      const step = diatonicStep(pitch);
      const y = yFor(step, event.staff);
      drawLedgers(event.x, step, event.staff);
      const expected = byLetter[letter] || "";
      if (accidental !== expected) {
        drawAccidental(accidental || "n", event.x - 12, y);
      }
      track(y - 5);
      track(y + 5);
      layer.append(
        svg("ellipse", {
          cx: event.x,
          cy: y,
          rx: 5.2,
          ry: 4,
          fill: open ? "none" : "currentColor",
          stroke: "currentColor",
          "stroke-width": open ? 1.4 : 0,
          transform: `rotate(-18 ${event.x} ${y})`,
        })
      );
    });
  }

  function stemGeometry(event, up) {
    const ys = event.steps.map((step) => yFor(step, event.staff));
    const x = up ? event.x + 5 : event.x - 5;
    const anchor = up ? Math.max(...ys) : Math.min(...ys);
    const tip = up ? Math.min(...ys) - STEM_LENGTH : Math.max(...ys) + STEM_LENGTH;
    return { x, anchor, tip, far: up ? Math.min(...ys) : Math.max(...ys) };
  }

  function drawFlags(x, tip, up, count) {
    for (let f = 0; f < count; f += 1) {
      const y = up ? tip + f * 7 : tip - f * 7;
      layer.append(
        svg("path", {
          d: up ? `M${x} ${y} q8 5 6 14` : `M${x} ${y} q8 -5 6 -14`,
          stroke: "currentColor",
          fill: "none",
          "stroke-width": 1.3,
        })
      );
    }
  }

  function drawSingle(event) {
    if (event.duration === "w") return;
    const up = stemUpFor(event.steps, event.staff);
    const stem = stemGeometry(event, up);
    line(stem.x, stem.anchor, stem.x, stem.tip);
    drawFlags(stem.x, stem.tip, up, FLAG_COUNT[event.duration] || 0);
  }

  function drawBeamGroup(group) {
    const allSteps = group.flatMap((event) => event.steps);
    const up = stemUpFor(allSteps, group[0].staff);
    const stems = group.map((event) => stemGeometry(event, up));
    const first = stems[0];
    const last = stems[stems.length - 1];
    const span = last.x - first.x || 1;
    const slope = Math.max(-LINE_GAP, Math.min(LINE_GAP, last.tip - first.tip)) / span;
    const minimum = LINE_GAP * 2.5;
    let offset = 0;
    stems.forEach((stem) => {
      const beamY = first.tip + slope * (stem.x - first.x);
      const needed = up ? stem.far - minimum : stem.far + minimum;
      offset = up ? Math.min(offset, needed - beamY) : Math.max(offset, needed - beamY);
    });
    const beamAt = (x) => first.tip + offset + slope * (x - first.x);
    stems.forEach((stem) => line(stem.x, stem.anchor, stem.x, beamAt(stem.x)));
    const thickness = 3.6;
    const beamPath = (x1, x2, level) => {
      const shift = (up ? 1 : -1) * level * 6;
      const y1 = beamAt(x1) + shift;
      const y2 = beamAt(x2) + shift;
      const edge = up ? thickness : -thickness;
      track(y1);
      track(y2 + edge);
      layer.append(
        svg("path", { d: `M${x1} ${y1} L${x2} ${y2} L${x2} ${y2 + edge} L${x1} ${y1 + edge} Z`, fill: "currentColor" })
      );
    };
    beamPath(first.x, last.x, 0);
    if (group.every((event) => event.tuplet === 3)) {
      const middle = (first.x + last.x) / 2;
      const y = beamAt(middle) + (up ? -7 : 15);
      track(y - 10);
      track(y + 2);
      layer.append(
        svgText({ x: middle, y, "font-size": 10, "font-style": "italic", "text-anchor": "middle", fill: "currentColor" }, "3")
      );
    }
    for (let i = 0; i < group.length - 1; i += 1) {
      if (FLAG_COUNT[group[i].duration] >= 2 && FLAG_COUNT[group[i + 1].duration] >= 2) {
        beamPath(stems[i].x, stems[i + 1].x, 1);
      }
    }
  }

  measures.forEach((measure, measureIndex) => {
    const startX = marginLeft + measureIndex * measureWidth;
    if (measureIndex > 0) line(startX, systemTop, startX, systemBottom, { "stroke-width": 1, opacity: 0.5 });
    const voices = twoVoices
      ? [
          { notes: measure.notes || [], hand: "right" },
          { notes: measure.left || [], hand: "left" },
        ]
      : [{ notes: measure.notes || [], hand }];
    voices.forEach((voice) => drawVoice(voice, startX));
  });

  function drawVoice(voice, startX) {
    let cursor = 0;
    const events = [];
    voice.notes.forEach((note) => {
      const pitches = note.pitches || (note.pitch ? [note.pitch] : []);
      if (pitches.length) {
        events.push({
          x: startX + (cursor / beatsPerMeasure) * measureWidth + 12,
          pitches,
          steps: pitches.map(diatonicStep),
          staff: staffForEvent(pitches, voice.hand),
          duration: note.duration,
          tuplet: note.tuplet,
          beat: Math.floor(cursor + 1e-6),
        });
      }
      cursor += beatsOf(note);
    });
    events.forEach(drawHeads);
    let group = [];
    const flush = () => {
      if (group.length > 1) drawBeamGroup(group);
      else if (group.length === 1) drawSingle(group[0]);
      group = [];
    };
    events.forEach((event) => {
      const beamable = FLAG_COUNT[event.duration] > 0;
      if (!beamable) {
        flush();
        drawSingle(event);
        return;
      }
      const previous = group[group.length - 1];
      if (previous && (previous.beat !== event.beat || previous.staff !== event.staff)) flush();
      group.push(event);
    });
    flush();
  }
  line(width - marginRight, systemTop, width - marginRight, systemBottom, { "stroke-width": 1.8 });

  const pad = 8;
  const top = Math.floor(minY - pad);
  const height = Math.ceil(maxY + pad - top);
  const root = svg("svg", {
    viewBox: `0 ${top} ${width} ${height}`,
    width,
    height,
    class: "notation-svg",
    role: "img",
  });
  root.append(layer);
  return root;
}
