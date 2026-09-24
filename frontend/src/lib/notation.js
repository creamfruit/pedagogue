const NATURAL_INDEX = { C: 0, D: 1, E: 2, F: 3, G: 4, A: 5, B: 6 };
const DURATION_FLAGS = { s: 2, e: 1, q: 0, h: 0, w: 0 };
const SVG_NS = "http://www.w3.org/2000/svg";

function svg(tag, attrs = {}) {
  const node = document.createElementNS(SVG_NS, tag);
  Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, String(value)));
  return node;
}

function svgText(attrs, content) {
  const node = svg("text", attrs);
  node.textContent = content;
  return node;
}

function parsePitch(pitch) {
  const match = /^([A-G])(#?)(-?\d+)$/.exec(pitch);
  if (!match) return { letter: "C", sharp: false, octave: 4 };
  return { letter: match[1], sharp: match[2] === "#", octave: Number(match[3]) };
}

function diatonicStep(pitch) {
  const { letter, octave } = parsePitch(pitch);
  return octave * 7 + NATURAL_INDEX[letter];
}

const MIDDLE_C_STEP = diatonicStep("C4");
const TREBLE_BOTTOM_STEP = diatonicStep("E4");
const BASS_BOTTOM_STEP = diatonicStep("G2");

function clefFor(pitch) {
  return diatonicStep(pitch) >= MIDDLE_C_STEP ? "treble" : "bass";
}

function beatsOf(note) {
  const map = { s: 0.25, e: 0.5, q: 1, h: 2, w: 4 };
  return map[note.duration] || 1;
}

function glyphNote(cx, cy, r = 3.6) {
  return svg("ellipse", { cx, cy, rx: r, ry: r * 0.76, fill: "currentColor", transform: `rotate(-18 ${cx} ${cy})` });
}

function glyphStem(x, y1, y2) {
  return svg("line", { x1: x, y1, x2: x, y2, stroke: "currentColor", "stroke-width": 1.2 });
}

const GLYPH_BUILDERS = {
  double_notes: () => [glyphNote(22, 15), glyphNote(22, 9), glyphStem(25, 15, 2)],
  octaves: () => [
    glyphNote(18, 18),
    glyphNote(18, 6),
    svg("line", { x1: 12, y1: 12, x2: 24, y2: 12, stroke: "currentColor", "stroke-width": 1, "stroke-dasharray": "2,2", opacity: 0.6 }),
    glyphStem(21, 18, 3),
    glyphStem(21, 6, 3),
  ],
  leaps: () => [
    glyphNote(13, 17),
    glyphNote(45, 7),
    svg("path", { d: "M16 15 Q29 4 42 8", fill: "none", stroke: "currentColor", "stroke-width": 1, opacity: 0.7 }),
  ],
  chords: () => [glyphNote(24, 17), glyphNote(24, 12), glyphNote(24, 7), glyphStem(27, 17, 2)],
  dexterity: () => [
    glyphNote(10, 15),
    glyphNote(22, 12),
    glyphNote(34, 9),
    glyphNote(46, 6),
    svg("path", { d: "M10 3 L46 3", stroke: "currentColor", "stroke-width": 1.6, fill: "none" }),
    glyphStem(13, 15, 3),
    glyphStem(25, 12, 3),
    glyphStem(37, 9, 3),
    glyphStem(49, 6, 3),
  ],
  repeated_notes: () => [glyphNote(14, 12), glyphNote(30, 12), glyphNote(46, 12), glyphStem(17, 12, 2), glyphStem(33, 12, 2), glyphStem(49, 12, 2)],
  trills: () => [
    glyphNote(20, 14),
    glyphNote(38, 10),
    svgText({ x: 18, y: 6, "font-size": 8, fill: "currentColor", "font-style": "italic" }, "tr"),
    svg("path", { d: "M30 6 q2 -3 4 0 q2 3 4 0", stroke: "currentColor", fill: "none", "stroke-width": 1 }),
  ],
  stretches: () => [
    glyphNote(12, 16),
    glyphNote(48, 16),
    svg("path", { d: "M12 5 L48 5", stroke: "currentColor", "stroke-width": 1, fill: "none" }),
    svg("path", { d: "M12 5 L12 8 M48 5 L48 8", stroke: "currentColor", "stroke-width": 1, fill: "none" }),
  ],
  polyrhythm: () => [
    glyphNote(12, 8), glyphNote(24, 8), glyphNote(36, 8),
    glyphNote(15, 18), glyphNote(33, 18),
    svg("line", { x1: 6, y1: 12, x2: 42, y2: 12, stroke: "currentColor", "stroke-width": 0.8, opacity: 0.4 }),
  ],
  voicing: () => [
    glyphNote(24, 14),
    svgText({ x: 19, y: 6, "font-size": 11, fill: "currentColor" }, ">"),
    glyphStem(27, 14, 2),
  ],
  pedaling: () => [
    glyphNote(16, 12),
    glyphStem(19, 12, 3),
    svgText({ x: 30, y: 20, "font-size": 8, fill: "currentColor" }, "Ped."),
    svg("path", { d: "M30 16 L52 16", stroke: "currentColor", "stroke-width": 1, fill: "none" }),
  ],
  endurance: () => [
    glyphNote(10, 13), glyphNote(24, 13), glyphNote(38, 13), glyphNote(52, 13),
    svg("path", { d: "M10 19 Q31 26 52 19", stroke: "currentColor", "stroke-width": 1, fill: "none" }),
  ],
};

export function techniqueGlyph(category) {
  const build = GLYPH_BUILDERS[category];
  const root = svg("svg", { viewBox: "0 0 60 24", width: "100%", height: "100%", class: "technique-glyph", "aria-hidden": "true" });
  if (!build) {
    root.append(glyphNote(30, 12));
    return root;
  }
  root.append(...build());
  return root;
}

export function renderNotation(notation, { width = 680, staffGap = 46 } = {}) {
  const lineGap = 9;
  const trebleTop = 26;
  const bassTop = trebleTop + lineGap * 4 + staffGap;
  const height = bassTop + lineGap * 4 + 40;
  const marginLeft = 44;
  const marginRight = 20;
  const usableWidth = width - marginLeft - marginRight;
  const measureCount = notation.measures.length || 1;
  const measureWidth = usableWidth / measureCount;

  const root = svg("svg", { viewBox: `0 0 ${width} ${height}`, width: "100%", height, class: "notation-svg" });
  root.append(svg("rect", { x: 0, y: 0, width, height, fill: "transparent" }));

  [trebleTop, bassTop].forEach((top) => {
    for (let i = 0; i < 5; i += 1) {
      const y = top + i * lineGap;
      root.append(
        svg("line", { x1: marginLeft, y1: y, x2: width - marginRight, y2: y, stroke: "currentColor", "stroke-width": 1, opacity: 0.55 })
      );
    }
  });

  root.append(
    svgText({ x: 8, y: trebleTop + lineGap * 3, "font-size": 26, fill: "currentColor" }, "\u{1D11E}"),
    svgText({ x: 8, y: bassTop + lineGap * 1.6, "font-size": 20, fill: "currentColor" }, "\u{1D122}")
  );

  function yFor(step, clef) {
    const bottomStep = clef === "treble" ? TREBLE_BOTTOM_STEP : BASS_BOTTOM_STEP;
    const bottomY = (clef === "treble" ? trebleTop : bassTop) + lineGap * 4;
    return bottomY - (step - bottomStep) * (lineGap / 2);
  }

  function drawLedgers(x, step, clef) {
    const topPos = clef === "treble" ? TREBLE_BOTTOM_STEP + 8 : BASS_BOTTOM_STEP + 8;
    const bottomPos = clef === "treble" ? TREBLE_BOTTOM_STEP : BASS_BOTTOM_STEP;
    if (step < bottomPos) {
      for (let s = bottomPos - 2; s >= step; s -= 2) {
        const y = yFor(s, clef);
        root.append(svg("line", { x1: x - 9, y1: y, x2: x + 9, y2: y, stroke: "currentColor", "stroke-width": 1 }));
      }
    } else if (step > topPos) {
      for (let s = topPos + 2; s <= step; s += 2) {
        const y = yFor(s, clef);
        root.append(svg("line", { x1: x - 9, y1: y, x2: x + 9, y2: y, stroke: "currentColor", "stroke-width": 1 }));
      }
    }
  }

  function drawNote(x, pitch, duration, stemUp) {
    const { sharp } = parsePitch(pitch);
    const clef = clefFor(pitch);
    const step = diatonicStep(pitch);
    const y = yFor(step, clef);
    drawLedgers(x, step, clef);
    if (sharp) {
      root.append(svgText({ x: x - 13, y: y + 4, "font-size": 12, fill: "currentColor" }, "♯"));
    }
    const open = duration === "w" || duration === "h";
    root.append(
      svg("ellipse", {
        cx: x,
        cy: y,
        rx: 5.2,
        ry: 4,
        fill: open ? "none" : "currentColor",
        stroke: "currentColor",
        "stroke-width": open ? 1.4 : 0,
        transform: `rotate(-18 ${x} ${y})`,
      })
    );
    if (duration !== "w") {
      const stemX = stemUp ? x + 5 : x - 5;
      const stemY = stemUp ? y - 28 : y + 28;
      root.append(svg("line", { x1: stemX, y1: y, x2: stemX, y2: stemY, stroke: "currentColor", "stroke-width": 1.2 }));
      const flags = DURATION_FLAGS[duration] || 0;
      for (let f = 0; f < flags; f += 1) {
        const flagY = stemY + (stemUp ? f * 6 : -f * 6);
        root.append(
          svg("path", {
            d: stemUp
              ? `M${stemX} ${flagY} q7 4 7 12`
              : `M${stemX} ${flagY} q-7 -4 -7 -12`,
            stroke: "currentColor",
            fill: "none",
            "stroke-width": 1.2,
          })
        );
      }
    }
    return y;
  }

  notation.measures.forEach((measure, measureIndex) => {
    const startX = marginLeft + measureIndex * measureWidth;
    root.append(
      svg("line", { x1: startX, y1: trebleTop, x2: startX, y2: bassTop + lineGap * 4, stroke: "currentColor", "stroke-width": 1, opacity: 0.5 })
    );
    let beatCursor = 0;
    measure.notes.forEach((note) => {
      const beats = beatsOf(note);
      const x = startX + (beatCursor / 4) * measureWidth + 14;
      const pitches = note.pitches || (note.pitch ? [note.pitch] : []);
      pitches.forEach((pitch) => drawNote(x, pitch, note.duration, clefFor(pitch) === "treble"));
      beatCursor += beats;
    });
  });
  root.append(
    svg("line", {
      x1: width - marginRight,
      y1: trebleTop,
      x2: width - marginRight,
      y2: bassTop + lineGap * 4,
      stroke: "currentColor",
      "stroke-width": 1.6,
    })
  );

  return root;
}
