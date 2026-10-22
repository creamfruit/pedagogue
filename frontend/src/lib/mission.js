import { api } from "../api/client.js";

export const KIND_LABEL = {
  warmup: "Warm-up",
  passage: "Hardest passage",
  review: "Review",
  playthrough: "Play-through",
  freeplay: "Free play",
};

let current = null;

export function localDay() {
  return new Date().toLocaleDateString("en-CA");
}

export function cachedMission() {
  return current && current.day === localDay() ? current : null;
}

export async function loadMission({ first = false, fresh = false } = {}) {
  const held = cachedMission();
  if (held && !fresh) return held;
  current = await api.missionToday(first);
  return current;
}

export async function completeStep(mission, index, { status = "done", seconds = 0 } = {}) {
  const result = await api.missionStep(mission.id, index, { status, seconds: Math.max(0, Math.round(seconds)) });
  current = result.mission;
  return result;
}

export function clearMission() {
  current = null;
}

export function missionDone(mission) {
  return Boolean(mission?.completed_at);
}

export function nextStepIndex(mission) {
  return mission?.next_index ?? null;
}

export function stepStatus(mission, index) {
  return mission?.progress?.find((item) => item.index === index)?.status || null;
}

export function minutesLabel(mission) {
  return `${mission.total_minutes} minutes`;
}
