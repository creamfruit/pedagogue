const KEY = "pp.lit";

function today() {
  return new Date().toLocaleDateString("en-CA");
}

function read() {
  try {
    const stored = JSON.parse(localStorage.getItem(KEY) || "null");
    return stored && stored.day === today() && Array.isArray(stored.entries) ? stored : { day: today(), entries: [] };
  } catch {
    return { day: today(), entries: [] };
  }
}

export function rememberLit(entryId) {
  if (!entryId) return;
  const stored = read();
  if (!stored.entries.includes(entryId)) stored.entries.push(entryId);
  try {
    localStorage.setItem(KEY, JSON.stringify(stored));
  } catch {
    return;
  }
}

export function litToday() {
  return new Set(read().entries);
}

export function forgetLit() {
  try {
    localStorage.removeItem(KEY);
  } catch {
    return;
  }
}
