// One illustrative bar per technique category, in the same shape the backend's
// SightReadingForge emits (backend/app/services/notation.py), so renderNotation()
// draws it as is. These are static on purpose: no technique carries its own note
// pattern, and the forge's builders are randomised eight-bar exercises.
// renderNotation() has no tuplets, so polyrhythm is shown as two hands against
// each other rather than a true three-against-two.
const n = (pitch, duration) => ({ pitch, duration });
const c = (pitches, duration) => ({ pitches, duration });

export const TECHNIQUE_SNIPPETS = {
  dexterity: [
    ...["C4", "D4", "E4", "F4", "G4", "A4", "B4", "C5"].map((p) => n(p, "s")),
    n("D5", "h"),
  ],
  double_notes: [
    c(["C4", "E4"], "e"), c(["D4", "F4"], "e"), c(["E4", "G4"], "e"), c(["F4", "A4"], "e"),
    c(["G4", "B4"], "e"), c(["F4", "A4"], "e"), c(["E4", "G4"], "e"), c(["D4", "F4"], "e"),
  ],
  octaves: [c(["C4", "C5"], "q"), c(["E4", "E5"], "q"), c(["G4", "G5"], "q"), c(["B4", "B5"], "q")],
  leaps: [
    n("C3", "e"), c(["E4", "G4", "C5"], "e"), n("G2", "e"), c(["D4", "G4", "B4"], "e"),
    n("C3", "e"), c(["E4", "G4", "C5"], "e"), n("G2", "e"), c(["D4", "F4", "B4"], "e"),
  ],
  chords: [
    c(["C4", "E4", "G4", "C5"], "q"), c(["C4", "E4", "G4", "C5"], "q"),
    c(["C4", "F4", "A4", "C5"], "q"), c(["D4", "G4", "B4"], "q"),
  ],
  repeated_notes: [...Array.from({ length: 8 }, () => n("G4", "e"))],
  trills: [...["E4", "F4", "E4", "F4", "E4", "F4", "E4", "F4"].map((p) => n(p, "s")), n("E4", "h")],
  stretches: [c(["C4", "E5"], "h"), c(["D4", "F5"], "h")],
  polyrhythm: [
    c(["C3", "C4"], "e"), n("E4", "e"), n("G4", "e"),
    c(["G2", "C5"], "e"), n("G4", "e"), n("E4", "e"),
    c(["C3", "C4"], "q"),
  ],
  voicing: [c(["C4", "E4", "G5"], "q"), c(["C4", "F4", "A5"], "q"), c(["D4", "G4", "B5"], "q"), c(["E4", "G4", "C6"], "q")],
  pedaling: [c(["F2", "C3", "A4"], "h"), c(["C3", "G3", "E4", "G4"], "h")],
  endurance: ["C4", "E4", "G4", "C5", "G4", "E4", "C4", "E4"].map((p) => n(p, "e")),
};

export function techniqueSnippet(category) {
  const notes = TECHNIQUE_SNIPPETS[category];
  if (!notes) return null;
  return { key: "C", time_signature: "4/4", tempo_bpm: 96, measures: [{ notes }] };
}
