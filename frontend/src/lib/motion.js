const KEY = "pp.motion";
const listeners = new Set();

function systemQuery() {
  try {
    return window.matchMedia("(prefers-reduced-motion: reduce)");
  } catch {
    return null;
  }
}

export function motionSetting() {
  try {
    return localStorage.getItem(KEY) === "reduce" ? "reduce" : "system";
  } catch {
    return "system";
  }
}

export function systemReducesMotion() {
  return Boolean(systemQuery()?.matches);
}

export function reducedMotion() {
  return motionSetting() === "reduce" || systemReducesMotion();
}

export function applyMotion() {
  document.documentElement.classList.toggle("reduce-motion", reducedMotion());
}

function emit() {
  listeners.forEach((handler) => handler(reducedMotion()));
}

export function setMotionSetting(value) {
  try {
    if (value === "reduce") localStorage.setItem(KEY, "reduce");
    else localStorage.removeItem(KEY);
  } catch {
    return;
  }
  applyMotion();
  emit();
}

export function onMotionChange(handler) {
  listeners.add(handler);
  return () => listeners.delete(handler);
}

export function watchMotion() {
  applyMotion();
  const query = systemQuery();
  if (!query) return;
  query.addEventListener("change", () => {
    applyMotion();
    emit();
  });
}
