import { api } from "../api/client.js";
import { deviceStore } from "./deviceStore.js";

const KEY = "outbox:notes";
const listeners = new Set();
let flushing = null;

export function onOutboxChange(handler) {
  listeners.add(handler);
  return () => listeners.delete(handler);
}

async function read() {
  const items = await deviceStore.get(KEY);
  return Array.isArray(items) ? items : [];
}

async function write(items) {
  if (items.length) await deviceStore.set(KEY, items);
  else await deviceStore.remove(KEY);
  listeners.forEach((handler) => handler(items));
}

export function pendingNotes(entryId) {
  return read().then((items) => (entryId ? items.filter((item) => item.entryId === entryId) : items));
}

export async function queueNote(entryId, body) {
  const items = await read();
  const item = {
    id: globalThis.crypto?.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`,
    entryId,
    body,
    createdAt: new Date().toISOString(),
  };
  await write([...items, item]);
  return item;
}

async function drain() {
  let items = await read();
  let sent = 0;
  let dropped = 0;
  for (const item of [...items]) {
    try {
      await api.submitText(item.entryId, item.body);
      sent += 1;
    } catch (error) {
      if (error.isOffline || error.status >= 500 || error.status === 401) break;
      dropped += 1;
    }
    items = items.filter((candidate) => candidate.id !== item.id);
    await write(items);
  }
  return { sent, dropped, waiting: items.length };
}

export function flushNotes() {
  if (!flushing) {
    flushing = drain().finally(() => {
      flushing = null;
    });
  }
  return flushing;
}
