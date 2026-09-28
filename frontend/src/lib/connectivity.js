import { isNative } from "./platform.js";

let deviceOnline = typeof navigator === "undefined" || navigator.onLine !== false;
let serverReachable = true;
const listeners = new Set();

export function isOnline() {
  return deviceOnline && serverReachable;
}

export function onConnectivity(handler) {
  listeners.add(handler);
  return () => listeners.delete(handler);
}

function emit() {
  const online = isOnline();
  listeners.forEach((handler) => handler(online));
}

function setDeviceOnline(online) {
  if (online) serverReachable = true;
  if (deviceOnline === online) {
    if (online) emit();
    return;
  }
  deviceOnline = online;
  emit();
}

export function reportReachable(reachable) {
  if (serverReachable === reachable) return;
  const before = isOnline();
  serverReachable = reachable;
  if (before !== isOnline()) emit();
}

export async function watchConnectivity() {
  window.addEventListener("online", () => setDeviceOnline(true));
  window.addEventListener("offline", () => setDeviceOnline(false));
  if (!isNative) return;
  try {
    const { Network } = await import("@capacitor/network");
    const status = await Network.getStatus();
    setDeviceOnline(status.connected);
    Network.addListener("networkStatusChange", (change) => setDeviceOnline(change.connected));
  } catch {
    setDeviceOnline(navigator.onLine !== false);
  }
}
